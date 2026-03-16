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
