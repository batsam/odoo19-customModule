import base64
import json
import mimetypes
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialVideoPost(models.Model):
    _name = 'social.video.post'
    _description = 'Social Video Post'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, default='New', tracking=True)
    platform = fields.Selection(  # legacy field kept for backward compatibility
        [('tiktok', 'TikTok'), ('facebook', 'Facebook'), ('instagram', 'Instagram')],
        default='tiktok',
        tracking=True,
    )
    publish_tiktok = fields.Boolean(default=True, tracking=True)
    publish_facebook = fields.Boolean(default=True, tracking=True)
    publish_instagram = fields.Boolean(default=True, tracking=True)
    target_account_ids = fields.Many2many(
        'social.media.account',
        'social_video_post_account_rel',
        'post_id',
        'account_id',
        string='Target Accounts',
        help='If empty, all active connected accounts for selected platforms are used.',
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
            ('in_review', 'In Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('scheduled', 'Scheduled'),
            ('uploaded', 'Uploaded'),
            ('partial', 'Partially Uploaded'),
            ('failed', 'Failed'),
            ('dead_letter', 'Dead Letter'),
        ],
        default='draft',
        tracking=True,
    )
    requires_approval = fields.Boolean(default=True, tracking=True)
    publish_mode = fields.Selection(
        [('now', 'Publish Now'), ('schedule', 'Schedule')],
        default='now',
        required=True,
        tracking=True,
    )
    scheduled_datetime = fields.Datetime(tracking=True)
    last_attempt_at = fields.Datetime(readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    max_retry = fields.Integer(default=3)
    next_retry_at = fields.Datetime(readonly=True)
    external_id = fields.Char(readonly=True)
    tiktok_external_id = fields.Char(readonly=True)
    facebook_external_id = fields.Char(readonly=True)
    instagram_external_id = fields.Char(readonly=True)
    response_body = fields.Text(readonly=True)
    tiktok_response_body = fields.Text(readonly=True)
    facebook_response_body = fields.Text(readonly=True)
    instagram_response_body = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    tiktok_error_message = fields.Text(readonly=True)
    facebook_error_message = fields.Text(readonly=True)
    instagram_error_message = fields.Text(readonly=True)

    @api.model
    def _max_video_size_bytes(self):
        max_mb = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'tiktok_video_uploader.max_video_size_mb',
                default='200',
            )
        )
        return max_mb * 1024 * 1024

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('social.video.post') or 'New'
        return super().create(vals_list)

    def action_publish(self):
        self.ensure_one()
        if self.requires_approval and self.state in ('draft', 'in_review', 'rejected'):
            raise UserError(_('This post requires approval before publishing.'))
        if (
            self.publish_mode == 'schedule'
            and not self.env.context.get('force_publish_now')
            and self.scheduled_datetime
            and self.scheduled_datetime > fields.Datetime.now()
        ):
            self.write({'state': 'scheduled'})
            return self._success_notification(_('Post scheduled successfully.'))

        video_bytes = self._validate_video_payload()
        selected_publishers = self._selected_publishers()
        if not selected_publishers:
            raise UserError(_('Select at least one destination platform.'))

        results = {}
        failures = {}
        for platform, publish_method in selected_publishers:
            accounts = self._get_target_accounts(platform)
            if not accounts:
                failures[platform] = _('No connected active account found.')
                continue
            platform_results = []
            platform_failures = []
            for account in accounts:
                try:
                    external_id, response_payload = publish_method(video_bytes, account)
                    platform_results.append(
                        {
                            'account': account.name,
                            'account_id': account.external_account_id,
                            'external_id': external_id,
                            'response': response_payload,
                        }
                    )
                except UserError as exc:
                    platform_failures.append(f'{account.name}: {exc}')
            if platform_results:
                results[platform] = platform_results
            if platform_failures:
                failures[platform] = ' || '.join(platform_failures)

        self._write_publish_results(results, failures)
        if failures and results:
            return self._success_notification(
                _('Video published with partial success. Failed: %s') % ', '.join(sorted(failures.keys()))
            )
        if failures:
            raise UserError(_('All selected publishes failed: %s') % ' | '.join(f'{k}: {v}' for k, v in failures.items()))
        return self._success_notification(_('Video published to selected platforms successfully.'))

    def action_submit_review(self):
        for record in self:
            record.write({'state': 'in_review'})
        return self._success_notification(_('Post submitted for review.'))

    def action_approve(self):
        for record in self:
            record.write({'state': 'approved'})
        return self._success_notification(_('Post approved.'))

    def action_reject(self):
        for record in self:
            record.write({'state': 'rejected'})
        return self._success_notification(_('Post rejected.'))

    def action_schedule_publish(self):
        for record in self:
            if record.publish_mode != 'schedule':
                raise UserError(_('Set Publish Mode to Schedule before scheduling.'))
            if not record.scheduled_datetime:
                raise UserError(_('Please set Scheduled Datetime.'))
            if record.scheduled_datetime <= fields.Datetime.now():
                raise UserError(_('Scheduled Datetime must be in the future.'))
            record.write({'state': 'scheduled'})
        return self._success_notification(_('Post(s) scheduled.'))

    @api.model
    def cron_publish_scheduled_posts(self):
        scheduled_posts = self.search(
            [
                ('state', 'in', ['scheduled', 'failed']),
                ('next_retry_at', '=', False),
                '|',
                ('scheduled_datetime', '<=', fields.Datetime.now()),
                ('scheduled_datetime', '=', False),
            ],
            limit=100,
        )
        retry_posts = self.search(
            [
                ('state', '=', 'failed'),
                ('next_retry_at', '!=', False),
                ('next_retry_at', '<=', fields.Datetime.now()),
            ],
            limit=100,
        )
        posts_to_run = scheduled_posts | retry_posts
        for post in posts_to_run:
            if post.attempt_count >= post.max_retry:
                post.write({'state': 'dead_letter'})
                continue
            try:
                post.with_context(force_publish_now=True).action_publish()
            except UserError:
                # state/error fields are already set by publish flow
                continue

    def _selected_publishers(self):
        selected = []
        if self.publish_tiktok:
            selected.append(('tiktok', self._publish_tiktok))
        if self.publish_facebook:
            selected.append(('facebook', self._publish_facebook))
        if self.publish_instagram:
            selected.append(('instagram', self._publish_instagram))
        return selected

    def _get_target_accounts(self, platform):
        target_accounts = self.target_account_ids.filtered(lambda acc: acc.platform == platform and acc.active)
        if target_accounts:
            return target_accounts
        matched_rules = self.env['social.publish.rule'].search([('active', '=', True), ('platform', '=', platform)])
        for rule in matched_rules:
            if rule.keyword and rule.keyword.lower() not in (self.caption or '').lower():
                continue
            rule_accounts = rule.target_account_ids.filtered(lambda acc: acc.active and acc.platform == platform)
            if rule_accounts:
                return rule_accounts
        return self.env['social.media.account'].search(
            [('platform', '=', platform), ('active', '=', True), ('company_id', '=', self.env.company.id)]
        )

    def _validate_video_payload(self):
        if not self.video_file:
            raise UserError(_('Please attach a video file before publishing.'))
        video_bytes = base64.b64decode(self.video_file)
        if not video_bytes:
            raise UserError(_('Uploaded file is empty.'))
        if len(video_bytes) > self._max_video_size_bytes():
            raise UserError(_('Video exceeds configured max size.'))
        content_type = mimetypes.guess_type(self.video_filename or '')[0] or ''
        if self.video_filename and not content_type.startswith('video/'):
            raise UserError(_('File type must be a video format.'))
        return video_bytes

    def _get_tiktok_access_token(self, account=False):
        if account and account.access_token:
            return account.access_token
        icp = self.env['ir.config_parameter'].sudo()
        access_token = icp.get_param('tiktok_video_uploader.access_token')
        expire_at = icp.get_param('tiktok_video_uploader.access_token_expire_at')
        if access_token and expire_at:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(expire_at).replace(tzinfo=timezone.utc):
                    return access_token
            except ValueError:
                return access_token
        refresh_token = icp.get_param('tiktok_video_uploader.refresh_token')
        client_key = icp.get_param('tiktok_video_uploader.client_key')
        client_secret = icp.get_param('tiktok_video_uploader.client_secret')
        token_endpoint = icp.get_param(
            'tiktok_video_uploader.token_endpoint',
            default='https://open.tiktokapis.com/v2/oauth/token/',
        )
        if not refresh_token or not client_key or not client_secret:
            return access_token
        refresh_res = requests.post(
            token_endpoint,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_key': client_key,
                'client_secret': client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            timeout=60,
        )
        refresh_res.raise_for_status()
        payload = refresh_res.json()
        data = payload.get('data', {})
        new_access_token = payload.get('access_token') or data.get('access_token')
        if not new_access_token:
            return access_token
        icp.set_param('tiktok_video_uploader.access_token', new_access_token)
        new_refresh_token = payload.get('refresh_token') or data.get('refresh_token')
        if new_refresh_token:
            icp.set_param('tiktok_video_uploader.refresh_token', new_refresh_token)
        expires_in = payload.get('expires_in') or data.get('expires_in')
        if expires_in:
            expire_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            icp.set_param('tiktok_video_uploader.access_token_expire_at', expire_at.isoformat())
        return new_access_token

    def _get_meta_access_token(self, account=False):
        if account and account.access_token:
            return account.access_token
        icp = self.env['ir.config_parameter'].sudo()
        override_token = icp.get_param('tiktok_video_uploader.facebook_access_token')
        if override_token:
            return override_token

        access_token = icp.get_param('tiktok_video_uploader.meta_access_token')
        expire_at = icp.get_param('tiktok_video_uploader.meta_access_token_expire_at')
        if access_token and expire_at:
            try:
                if datetime.now(timezone.utc) < datetime.fromisoformat(expire_at).replace(tzinfo=timezone.utc):
                    return access_token
                raise UserError(_('Meta access token has expired. Please reconnect Meta OAuth in Settings.'))
            except ValueError:
                return access_token
        return access_token

    def _publish_tiktok(self, video_bytes, account):
        access_token = self._get_tiktok_access_token(account)
        init_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.upload_endpoint',
            default='https://open.tiktokapis.com/v2/post/publish/video/init/',
        )
        if not access_token:
            raise UserError(_('Configure TikTok access token in Settings.'))

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
            return publish_id or init_json.get('video_id'), init_json
        except requests.RequestException as exc:
            raise UserError(_('TikTok upload failed: %s') % self._format_http_exception(exc)) from exc

    def _publish_facebook(self, video_bytes, account):
        page_id = account.external_account_id or self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.facebook_page_id')
        access_token = self._get_meta_access_token(account)
        graph_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.facebook_graph_endpoint',
            default='https://graph.facebook.com/v23.0',
        )
        if not page_id or not access_token:
            raise UserError(_('Configure Facebook Page ID and Access Token in Settings.'))

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
            return data.get('id') or data.get('video_id'), data
        except requests.RequestException as exc:
            raise UserError(_('Facebook upload failed: %s') % self._format_http_exception(exc)) from exc

    def _publish_instagram(self, video_bytes, account):
        ig_user_id = account.external_account_id or self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.instagram_user_id')
        access_token = self.env['ir.config_parameter'].sudo().get_param('tiktok_video_uploader.instagram_access_token')
        if not access_token:
            access_token = self._get_meta_access_token(account)
        graph_endpoint = self.env['ir.config_parameter'].sudo().get_param(
            'tiktok_video_uploader.instagram_graph_endpoint',
            default='https://graph.facebook.com/v23.0',
        )
        if not ig_user_id or not access_token:
            raise UserError(_('Configure Instagram User ID and Access Token in Settings.'))
        if self.publish_instagram and not self.video_public_url:
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
            return publish_json.get('id') or creation_id, publish_json
        except requests.RequestException as exc:
            raise UserError(_('Instagram publish failed: %s') % self._format_http_exception(exc)) from exc

    def _write_publish_results(self, results, failures):
        tiktok_responses = results.get('tiktok', [])
        facebook_responses = results.get('facebook', [])
        instagram_responses = results.get('instagram', [])
        first_tiktok = tiktok_responses[0] if tiktok_responses else {}
        first_facebook = facebook_responses[0] if facebook_responses else {}
        first_instagram = instagram_responses[0] if instagram_responses else {}
        vals = {
            'tiktok_external_id': first_tiktok.get('external_id'),
            'facebook_external_id': first_facebook.get('external_id'),
            'instagram_external_id': first_instagram.get('external_id'),
            'tiktok_response_body': json.dumps(tiktok_responses) if tiktok_responses else False,
            'facebook_response_body': json.dumps(facebook_responses) if facebook_responses else False,
            'instagram_response_body': json.dumps(instagram_responses) if instagram_responses else False,
            'tiktok_error_message': failures.get('tiktok'),
            'facebook_error_message': failures.get('facebook'),
            'instagram_error_message': failures.get('instagram'),
            'external_id': ', '.join(
                filter(
                    None,
                    [
                        first_tiktok.get('external_id'),
                        first_facebook.get('external_id'),
                        first_instagram.get('external_id'),
                    ],
                )
            )
            or False,
            'response_body': json.dumps(results) if results else False,
            'error_message': ' | '.join(f'{platform}: {message}' for platform, message in failures.items()) if failures else False,
            'last_attempt_at': fields.Datetime.now(),
            'attempt_count': self.attempt_count + 1,
            'next_retry_at': False,
        }
        if results and not failures:
            vals['state'] = 'uploaded'
        elif results and failures:
            vals['state'] = 'partial'
        else:
            attempt_after_write = self.attempt_count + 1
            if attempt_after_write >= self.max_retry:
                vals['state'] = 'dead_letter'
            else:
                vals['state'] = 'failed'
                backoff_minutes = min(60, 2 ** min(attempt_after_write, 6))
                vals['next_retry_at'] = fields.Datetime.add(fields.Datetime.now(), minutes=backoff_minutes)
        self.write(vals)

    def _format_http_exception(self, exc):
        details = ''
        if exc.response is not None:
            details = f' | status={exc.response.status_code} body={exc.response.text}'
        return f'{exc}{details}'

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
