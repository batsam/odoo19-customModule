from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tiktok_access_token = fields.Char(
        string='TikTok Access Token',
        config_parameter='tiktok_video_uploader.access_token',
    )
    tiktok_upload_endpoint = fields.Char(
        string='TikTok Upload Endpoint',
        config_parameter='tiktok_video_uploader.upload_endpoint',
        default='https://open.tiktokapis.com/v2/post/publish/video/init/',
    )
    tiktok_client_key = fields.Char(
        string='TikTok Client Key',
        config_parameter='tiktok_video_uploader.client_key',
    )
    tiktok_client_secret = fields.Char(
        string='TikTok Client Secret',
        config_parameter='tiktok_video_uploader.client_secret',
    )
    tiktok_redirect_uri = fields.Char(
        string='TikTok Redirect URI',
        config_parameter='tiktok_video_uploader.redirect_uri',
    )
    tiktok_scopes = fields.Char(
        string='TikTok OAuth Scopes',
        config_parameter='tiktok_video_uploader.scopes',
        default='user.info.basic,video.publish',
    )
    tiktok_authorize_endpoint = fields.Char(
        string='TikTok Authorize Endpoint',
        config_parameter='tiktok_video_uploader.authorize_endpoint',
        default='https://www.tiktok.com/v2/auth/authorize/',
    )
    tiktok_token_endpoint = fields.Char(
        string='TikTok Token Endpoint',
        config_parameter='tiktok_video_uploader.token_endpoint',
        default='https://open.tiktokapis.com/v2/oauth/token/',
    )

    def action_tiktok_connect(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/tiktok/connect',
            'target': 'self',
        }
