import base64

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TikTokVideoUpload(models.Model):
    _name = 'tiktok.video.upload'
    _description = 'TikTok Video Upload'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, default='New', tracking=True)
    video_file = fields.Binary(required=True, string='Video File', attachment=True)
    video_filename = fields.Char(string='File Name')
    description = fields.Text(string='Caption')
    privacy_level = fields.Selection(
        [
            ('PUBLIC_TO_EVERYONE', 'Public'),
            ('MUTUAL_FOLLOW_FRIENDS', 'Friends'),
            ('SELF_ONLY', 'Private'),
        ],
        default='PUBLIC_TO_EVERYONE',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('uploaded', 'Uploaded'),
            ('failed', 'Failed'),
        ],
        default='draft',
        tracking=True,
    )
    tiktok_video_id = fields.Char(readonly=True)
    response_body = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('tiktok.video.upload') or 'New'
        return super().create(vals_list)

    def action_upload_to_tiktok(self):
        self.ensure_one()
        if not self.video_file:
            raise UserError(_('Please attach a video file before uploading.'))

        access_token = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.access_token')
        upload_url = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.upload_endpoint',
            default='https://open.tiktokapis.com/v2/post/publish/video/init/',
        )

        if not access_token:
            raise UserError(_('Please configure TikTok Access Token in Settings.'))

        file_name = self.video_filename or f'{self.name}.mp4'
        payload = {
            'description': self.description or '',
            'privacy_level': self.privacy_level,
        }

        try:
            response = requests.post(
                upload_url,
                headers={
                    'Authorization': f'Bearer {access_token}',
                },
                data=payload,
                files={
                    'video': (file_name, base64.b64decode(self.video_file), 'video/mp4'),
                },
                timeout=120,
            )
            response.raise_for_status()
            response_json = response.json()
        except requests.RequestException as exc:
            self.write(
                {
                    'state': 'failed',
                    'error_message': str(exc),
                }
            )
            raise UserError(_('TikTok upload failed: %s') % exc) from exc

        self.write(
            {
                'state': 'uploaded',
                'error_message': False,
                'response_body': str(response_json),
                'tiktok_video_id': (
                    response_json.get('data', {}).get('publish_id')
                    or response_json.get('data', {}).get('video_id')
                    or response_json.get('video_id')
                ),
            }
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upload complete'),
                'message': _('Video uploaded to TikTok successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }
