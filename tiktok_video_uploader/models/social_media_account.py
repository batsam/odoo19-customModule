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
