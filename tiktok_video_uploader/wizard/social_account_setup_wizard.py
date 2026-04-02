from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services.parsers.credential_parser import CredentialParser


class SocialAccountSetupWizard(models.TransientModel):
    _name = 'social.account.setup.wizard'
    _description = 'Social Account Setup Wizard'

    provider = fields.Selection(
        [('tiktok', 'TikTok'), ('meta', 'Meta (Facebook/Instagram)')],
        required=True,
        default='tiktok',
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    raw_payload = fields.Text(string='Pasted Credentials')
    line_ids = fields.One2many('social.account.setup.wizard.line', 'wizard_id', string='Detected Credentials')
    account_id = fields.Many2one('social.media.account', string='Target Account')
    has_parsed_payload = fields.Boolean(default=False)

    detected_total = fields.Integer(compute='_compute_mapping_stats')
    mapped_total = fields.Integer(compute='_compute_mapping_stats')
    unmapped_total = fields.Integer(compute='_compute_mapping_stats')
    selected_total = fields.Integer(compute='_compute_mapping_stats')
    accepted_formats_hint = fields.Char(compute='_compute_accepted_formats_hint')

    @api.depends('line_ids', 'line_ids.apply', 'line_ids.target_field')
    def _compute_mapping_stats(self):
        for wizard in self:
            lines = wizard.line_ids
            wizard.detected_total = len(lines)
            wizard.mapped_total = len(lines.filtered(lambda l: l.target_field))
            wizard.unmapped_total = len(lines.filtered(lambda l: not l.target_field))
            wizard.selected_total = len(lines.filtered(lambda l: l.apply and l.target_field))

    @api.depends('provider')
    def _compute_accepted_formats_hint(self):
        for wizard in self:
            if wizard.provider == 'meta':
                wizard.accepted_formats_hint = _(
                    'Accepted formats: JSON, key=value, key:value. Common Meta keys: app_id, app_secret, access_token.'
                )
            else:
                wizard.accepted_formats_hint = _(
                    'Accepted formats: JSON, key=value, key:value. Common TikTok keys: client_key/client_id, client_secret, access_token.'
                )

    def action_parse_payload(self):
        self.ensure_one()
        parsed_values = CredentialParser.parse(self.raw_payload)
        if not parsed_values:
            raise UserError(_('No credential key/value pairs were found in the pasted payload.'))

        previews = CredentialParser.build_preview(parsed_values, self.provider)
        self.line_ids.unlink()
        self.write({'has_parsed_payload': True})

        for preview in previews:
            self.line_ids.create({'wizard_id': self.id, **preview})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_ignore_unmapped(self):
        self.ensure_one()
        self.line_ids.filtered(lambda l: not l.target_field).write({'apply': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_credentials(self):
        self.ensure_one()
        values = {}
        for line in self.line_ids.filtered(lambda l: l.apply and l.target_field):
            values[line.target_field] = line.detected_value

        if not values:
            raise UserError(_('No mapped credentials were selected to apply.'))

        values.update(
            {
                'platform': 'facebook' if self.provider == 'meta' else 'tiktok',
                'company_id': self.company_id.id,
                'state': 'configured',
            }
        )

        if self.account_id:
            self.account_id.write(values)
            account = self.account_id
        else:
            values.setdefault('name', _('New %s Account') % dict(self._fields['provider'].selection).get(self.provider))
            account = self.env['social.media.account'].create(values)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social.media.account',
            'res_id': account.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SocialAccountSetupWizardLine(models.TransientModel):
    _name = 'social.account.setup.wizard.line'
    _description = 'Social Account Setup Wizard Line'

    wizard_id = fields.Many2one('social.account.setup.wizard', required=True, ondelete='cascade')
    source_key = fields.Char(required=True)
    target_field = fields.Selection(
        selection=[
            ('app_id', 'App ID'),
            ('app_secret', 'App Secret'),
            ('client_id', 'Client ID'),
            ('client_secret', 'Client Secret'),
            ('access_token', 'Access Token'),
            ('refresh_token', 'Refresh Token'),
            ('external_account_id', 'External Account ID'),
            ('business_id', 'Business ID'),
            ('ad_account_id', 'Ad Account ID'),
            ('pixel_id', 'Pixel ID'),
            ('scope', 'Scope'),
        ],
        string='Map To',
    )
    detected_value = fields.Char(required=True)
    detected_value_masked = fields.Char(compute='_compute_detected_value_masked')
    confidence = fields.Selection([('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], required=True)
    note = fields.Char()
    apply = fields.Boolean(default=True)

    @api.depends('detected_value')
    def _compute_detected_value_masked(self):
        for line in self:
            value = line.detected_value or ''
            if len(value) <= 8:
                line.detected_value_masked = '*' * len(value)
            else:
                line.detected_value_masked = f'{value[:4]}…{value[-4:]}'
