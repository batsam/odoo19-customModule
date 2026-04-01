from odoo import _, fields, models
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

    def action_parse_payload(self):
        self.ensure_one()
        parsed_values = CredentialParser.parse(self.raw_payload)
        if not parsed_values:
            raise UserError(_('No credential key/value pairs were found in the pasted payload.'))

        previews = CredentialParser.build_preview(parsed_values, self.provider)
        self.line_ids.unlink()
        for preview in previews:
            self.line_ids.create({'wizard_id': self.id, **preview})

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
        string='Mapped Field',
    )
    detected_value = fields.Char(required=True)
    confidence = fields.Selection([('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], required=True)
    apply = fields.Boolean(default=True)
