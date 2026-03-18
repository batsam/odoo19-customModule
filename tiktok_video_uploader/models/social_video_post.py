import base64
import json

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialVideoPost(models.Model):
    _name = 'social.video.post'
    _description = 'Social Video Post'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, default='New', tracking=True)
    platform = fields.Selection(
        [
            ('tiktok', 'TikTok'),
            ('facebook', 'Facebook'),
            ('instagram', 'Instagram'),
        ],
        required=True,
        default='tiktok',
        tracking=True,
    )
    video_file = fields.Binary(required=True, string='Video File', attachment=True)
    video_filename = fields.Char(string='File Name')
    video_public_url = fields.Char(
        string='Public Video URL',
        help='Required for Instagram Graph API publishing.',
    )
    caption = fields.Text(string='Caption')
    privacy_level = fields.Selection(
        [
            ('PUBLIC_TO_EVERYONE', 'Public'),
            ('MUTUAL_FOLLOW_FRIENDS', 'Friends'),
            ('SELF_ONLY', 'Private'),
        ],
        default='SELF_ONLY',
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
    external_id = fields.Char(readonly=True)
    response_body = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('social.video.post') or 'New'
        return super().create(vals_list)

    def action_publish(self):
        self.ensure_one()
        if self.platform == 'tiktok':
            return self._publish_tiktok()
        if self.platform == 'facebook':
            return self._publish_facebook()
        if self.platform == 'instagram':
            return self._publish_instagram()
        raise UserError(_('Unsupported platform.'))

    def _publish_tiktok(self):
        access_token = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.access_token')
        init_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.upload_endpoint',
            default='https://open.tiktokapis.com/v2/post/publish/video/init/',
        )
        if not access_token:
            raise UserError(_('Configure TikTok access token in Settings.'))

        video_bytes = base64.b64decode(self.video_file)
        video_size = len(video_bytes)
        payload = {
            'post_info': {
                'title': self.caption or self.video_filename or self.name,
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
            init_res = requests.post(
                init_endpoint,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json; charset=UTF-8',
                },
                data=json.dumps(payload),
                timeout=120,
            )
            init_res.raise_for_status()
            init_json = init_res.json()
            upload_url = init_json.get('data', {}).get('upload_url')
            publish_id = init_json.get('data', {}).get('publish_id')
            if not upload_url:
                raise UserError(_('TikTok response missing upload_url: %s') % init_json)

            upload_res = requests.put(
                upload_url,
                headers={
                    'Content-Type': 'video/mp4',
                    'Content-Length': str(video_size),
                    'Content-Range': f'bytes 0-{video_size - 1}/{video_size}',
                },
                data=video_bytes,
                timeout=300,
            )
            upload_res.raise_for_status()
            self._mark_uploaded(publish_id or init_json.get('video_id'), init_json)
        except requests.RequestException as exc:
            self._mark_failed(exc)
            raise UserError(_('TikTok upload failed: %s') % self.error_message) from exc

        return self._success_notification(_('TikTok upload complete'))

    def _publish_facebook(self):
        page_id = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.facebook_page_id')
        access_token = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.facebook_access_token')
        graph_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.facebook_graph_endpoint',
            default='https://graph.facebook.com/v23.0',
        )
        if not page_id or not access_token:
            raise UserError(_('Configure Facebook Page ID and Access Token in Settings.'))

        video_bytes = base64.b64decode(self.video_file)
        file_name = self.video_filename or f'{self.name}.mp4'
        url = f"{graph_endpoint}/{page_id}/videos"

        try:
            response = requests.post(
                url,
                data={
                    'description': self.caption or '',
                    'access_token': access_token,
                },
                files={
                    'source': (file_name, video_bytes, 'video/mp4'),
                },
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            self._mark_uploaded(data.get('id') or data.get('video_id'), data)
        except requests.RequestException as exc:
            self._mark_failed(exc)
            raise UserError(_('Facebook upload failed: %s') % self.error_message) from exc

        return self._success_notification(_('Facebook upload complete'))

    def _publish_instagram(self):
        ig_user_id = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.instagram_user_id')
        access_token = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.instagram_access_token')
        graph_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.instagram_graph_endpoint',
            default='https://graph.facebook.com/v23.0',
        )
        if not ig_user_id or not access_token:
            raise UserError(_('Configure Instagram User ID and Access Token in Settings.'))
        if not self.video_public_url:
            raise UserError(_('Instagram requires a public Video URL for publishing.'))

        create_url = f"{graph_endpoint}/{ig_user_id}/media"
        publish_url = f"{graph_endpoint}/{ig_user_id}/media_publish"

        try:
            create_res = requests.post(
                create_url,
                data={
                    'media_type': 'REELS',
                    'video_url': self.video_public_url,
                    'caption': self.caption or '',
                    'access_token': access_token,
                },
                timeout=120,
            )
            create_res.raise_for_status()
            create_json = create_res.json()
            creation_id = create_json.get('id')
            if not creation_id:
                raise UserError(_('Instagram media creation failed: %s') % create_json)

            publish_res = requests.post(
                publish_url,
                data={
                    'creation_id': creation_id,
                    'access_token': access_token,
                },
                timeout=120,
            )
            publish_res.raise_for_status()
            publish_json = publish_res.json()
            self._mark_uploaded(publish_json.get('id') or creation_id, publish_json)
        except requests.RequestException as exc:
            self._mark_failed(exc)
            raise UserError(_('Instagram publish failed: %s') % self.error_message) from exc

        return self._success_notification(_('Instagram publish request sent'))

    def _mark_failed(self, exc):
        details = ''
        body = False
        if exc.response is not None:
            body = exc.response.text
            details = f' | status={exc.response.status_code} body={body}'
        self.write(
            {
                'state': 'failed',
                'error_message': f'{exc}{details}',
                'response_body': body,
            }
        )

    def _mark_uploaded(self, external_id, response_data):
        self.write(
            {
                'state': 'uploaded',
                'error_message': False,
                'external_id': external_id,
                'response_body': json.dumps(response_data),
            }
        )

    def _success_notification(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upload complete'),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
