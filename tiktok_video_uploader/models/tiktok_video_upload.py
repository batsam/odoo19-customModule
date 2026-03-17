import base64
import json

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
        init_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.upload_endpoint',
            default='https://open.tiktokapis.com/v2/post/publish/video/init/',
        )

        if not access_token:
            raise UserError(_('Please configure TikTok Access Token in Settings.'))

        file_name = self.video_filename or f'{self.name}.mp4'
        video_bytes = base64.b64decode(self.video_file)
        video_size = len(video_bytes)

        init_payload = {
            'post_info': {
                'title': self.description or file_name,
                'privacy_level': self.privacy_level,
                'disable_duet': False,
                'disable_comment': False,
                'disable_stitch': False,
            },
            'source_info': {
                'source': 'FILE_UPLOAD',
                'video_size': video_size,
                'chunk_size': video_size,
                'total_chunk_count': 1,
            },
        }

        try:
            init_response = requests.post(
                init_endpoint,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json; charset=UTF-8',
                },
                data=json.dumps(init_payload),
                timeout=120,
            )
            init_response.raise_for_status()
            init_json = init_response.json()

            data = init_json.get('data', {})
            upload_url = data.get('upload_url')
            publish_id = data.get('publish_id')
            if not upload_url:
                raise UserError(_('TikTok response missing upload URL: %s') % init_json)

            upload_response = requests.put(
                upload_url,
                headers={
                    'Content-Type': 'video/mp4',
                    'Content-Length': str(video_size),
                    'Content-Range': f'bytes 0-{video_size - 1}/{video_size}',
                },
                data=video_bytes,
                timeout=300,
            )
            upload_response.raise_for_status()

        except requests.RequestException as exc:
            details = ''
            if exc.response is not None:
                details = f' | status={exc.response.status_code} body={exc.response.text}'
            message = f'{exc}{details}'
            self.write(
                {
                    'state': 'failed',
                    'error_message': message,
                    'response_body': getattr(exc.response, 'text', False),
                }
            )
            raise UserError(_('TikTok upload failed: %s') % message) from exc

        self.write(
            {
                'state': 'uploaded',
                'error_message': False,
                'response_body': json.dumps(init_json),
                'tiktok_video_id': publish_id or data.get('video_id') or init_json.get('video_id'),
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
