from odoo import fields, models


class SocialPublishRule(models.Model):
    _name = 'social.publish.rule'
    _description = 'Social Publish Routing Rule'
    _order = 'priority asc, id asc'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(default=10)
    platform = fields.Selection(
        [('tiktok', 'TikTok'), ('facebook', 'Facebook'), ('instagram', 'Instagram')],
        required=True,
    )
    keyword = fields.Char(
        help='If keyword is in caption, this rule matches. Leave empty to match all posts for this platform.',
    )
    target_account_ids = fields.Many2many(
        'social.media.account',
        'social_publish_rule_account_rel',
        'rule_id',
        'account_id',
        string='Target Accounts',
    )
    notes = fields.Text()
