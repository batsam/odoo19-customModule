from odoo import fields, models


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

    facebook_page_id = fields.Char(
        string='Facebook Page ID',
        config_parameter='tiktok_video_uploader.facebook_page_id',
    )
    meta_app_id = fields.Char(
        string='Meta App ID',
        config_parameter='tiktok_video_uploader.meta_app_id',
    )
    meta_app_secret = fields.Char(
        string='Meta App Secret',
        config_parameter='tiktok_video_uploader.meta_app_secret',
    )
    meta_redirect_uri = fields.Char(
        string='Meta Redirect URI',
        config_parameter='tiktok_video_uploader.meta_redirect_uri',
    )
    meta_scopes = fields.Char(
        string='Meta OAuth Scopes',
        config_parameter='tiktok_video_uploader.meta_scopes',
        default='pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish',
    )
    meta_authorize_endpoint = fields.Char(
        string='Meta Authorize Endpoint',
        config_parameter='tiktok_video_uploader.meta_authorize_endpoint',
        default='https://www.facebook.com/v23.0/dialog/oauth',
    )
    meta_token_endpoint = fields.Char(
        string='Meta Token Endpoint',
        config_parameter='tiktok_video_uploader.meta_token_endpoint',
        default='https://graph.facebook.com/v23.0/oauth/access_token',
    )
    meta_graph_endpoint = fields.Char(
        string='Meta Graph Endpoint',
        config_parameter='tiktok_video_uploader.meta_graph_endpoint',
        default='https://graph.facebook.com/v23.0',
    )
    meta_access_token = fields.Char(
        string='Meta Access Token',
        config_parameter='tiktok_video_uploader.meta_access_token',
    )
    meta_access_token_expire_at = fields.Char(
        string='Meta Token Expire At',
        config_parameter='tiktok_video_uploader.meta_access_token_expire_at',
    )
    meta_user_id = fields.Char(
        string='Meta User ID',
        config_parameter='tiktok_video_uploader.meta_user_id',
    )
    facebook_access_token = fields.Char(
        string='Facebook Access Token (Override)',
        config_parameter='tiktok_video_uploader.facebook_access_token',
    )
    facebook_graph_endpoint = fields.Char(
        string='Facebook Graph Endpoint',
        config_parameter='tiktok_video_uploader.facebook_graph_endpoint',
        default='https://graph.facebook.com/v23.0',
    )

    instagram_user_id = fields.Char(
        string='Instagram Business User ID',
        config_parameter='tiktok_video_uploader.instagram_user_id',
    )
    instagram_access_token = fields.Char(
        string='Instagram Access Token (Override)',
        config_parameter='tiktok_video_uploader.instagram_access_token',
    )
    instagram_graph_endpoint = fields.Char(
        string='Instagram Graph Endpoint',
        config_parameter='tiktok_video_uploader.instagram_graph_endpoint',
        default='https://graph.facebook.com/v23.0',
    )
    max_video_size_mb = fields.Integer(
        string='Max Upload Size (MB)',
        config_parameter='tiktok_video_uploader.max_video_size_mb',
        default=200,
    )

    def action_tiktok_connect(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/tiktok/connect',
            'target': 'self',
        }

    def action_meta_connect(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return {
            'type': 'ir.actions.act_url',
            'url': f'{base_url}/facebook/connect',
            'target': 'self',
        }
