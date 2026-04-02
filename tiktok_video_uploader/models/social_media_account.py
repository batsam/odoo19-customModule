from odoo import api, fields, models


class SocialMediaAccount(models.Model):
    _name = 'social.media.account'
    _description = 'Connected Social Media Account'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    platform = fields.Selection(
        [('tiktok', 'TikTok'), ('facebook', 'Facebook'), ('instagram', 'Instagram')],
        required=True,
        tracking=True,
    )
    external_account_id = fields.Char(string='External Account ID', tracking=True)
    access_token = fields.Char(required=True)
    refresh_token = fields.Char()
    token_expire_at = fields.Datetime()
    scope = fields.Char()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    notes = fields.Text()

    state = fields.Selection(
        [('draft', 'Draft'), ('configured', 'Configured'), ('validated', 'Validated'), ('failed', 'Failed')],
        default='draft',
        tracking=True,
    )
    last_validated_at = fields.Datetime(tracking=True)
    last_error_message = fields.Text()
    token_expires_at = fields.Datetime()
    app_id = fields.Char(groups='tiktok_video_uploader.group_social_admin')
    app_secret = fields.Char(groups='tiktok_video_uploader.group_social_admin')
    client_id = fields.Char(groups='tiktok_video_uploader.group_social_admin')
    client_secret = fields.Char(groups='tiktok_video_uploader.group_social_admin')
    business_id = fields.Char()
    ad_account_id = fields.Char()
    pixel_id = fields.Char()

    _sql_constraints = [
        (
            'social_account_platform_external_uniq',
            'unique(platform, external_account_id, company_id)',
            'This social account already exists for this company.',
        )
    ]

    @api.model
    def upsert_connected_account(self, vals):
        domain = [
            ('platform', '=', vals.get('platform')),
            ('external_account_id', '=', vals.get('external_account_id')),
            ('company_id', '=', vals.get('company_id', self.env.company.id)),
        ]
        account = self.search(domain, limit=1)
        if account:
            account.write(vals)
            return account
        return self.create(vals)

    def action_open_setup_wizard(self):
        self.ensure_one()
        provider = 'meta' if self.platform in ('facebook', 'instagram') else 'tiktok'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Setup Credentials',
            'res_model': 'social.account.setup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_provider': provider,
                'default_account_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }
