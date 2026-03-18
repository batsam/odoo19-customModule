import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

from odoo import http
from odoo.http import request


class TikTokOAuthController(http.Controller):

    @http.route('/tiktok/connect', type='http', auth='user', methods=['GET'])
    def tiktok_connect(self, **kwargs):
        icp = request.env['ir.config_parameter'].sudo()
        client_key = icp.get_param('tiktok_video_uploader.client_key')
        redirect_uri = icp.get_param('tiktok_video_uploader.redirect_uri')
        scopes = icp.get_param('tiktok_video_uploader.scopes', default='user.info.basic,video.publish')
        authorize_endpoint = icp.get_param(
            'tiktok_video_uploader.authorize_endpoint',
            default='https://www.tiktok.com/v2/auth/authorize/',
        )

        if not client_key or not redirect_uri:
            return request.make_response(
                'Missing TikTok configuration. Please set Client Key and Redirect URI in Odoo settings.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        state = secrets.token_urlsafe(24)
        request.session['tiktok_video_uploader.oauth_state'] = state

        query = urlencode(
            {
                'client_key': client_key,
                'response_type': 'code',
                'scope': scopes,
                'redirect_uri': redirect_uri,
                'state': state,
            }
        )
        return request.redirect(f'{authorize_endpoint}?{query}', local=False)

    @http.route('/tiktok/callback', type='http', auth='public', methods=['GET'], csrf=False)
    def tiktok_callback(self, code=None, state=None, error=None, error_description=None, **kwargs):
        if error:
            message = f'TikTok authorization failed: {error} {error_description or ""}'.strip()
            return request.make_response(message, headers=[('Content-Type', 'text/plain; charset=utf-8')], status=400)

        if not code or not state:
            return request.make_response(
                'Missing OAuth code/state in callback.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        icp = request.env['ir.config_parameter'].sudo()
        expected_state = request.session.get('tiktok_video_uploader.oauth_state')
        if not expected_state or expected_state != state:
            return request.make_response(
                'Invalid OAuth state. Please retry TikTok connect.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )
        request.session.pop('tiktok_video_uploader.oauth_state', None)

        client_key = icp.get_param('tiktok_video_uploader.client_key')
        client_secret = icp.get_param('tiktok_video_uploader.client_secret')
        redirect_uri = icp.get_param('tiktok_video_uploader.redirect_uri')
        token_endpoint = icp.get_param(
            'tiktok_video_uploader.token_endpoint',
            default='https://open.tiktokapis.com/v2/oauth/token/',
        )

        if not client_key or not client_secret or not redirect_uri:
            return request.make_response(
                'Missing TikTok OAuth settings (client key/secret/redirect URI).',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        try:
            response = requests.post(
                token_endpoint,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'client_key': client_key,
                    'client_secret': client_secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': redirect_uri,
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            return request.make_response(
                f'Token exchange failed: {exc}',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        access_token = payload.get('access_token')
        if not access_token and payload.get('data'):
            access_token = payload.get('data', {}).get('access_token')

        if not access_token:
            return request.make_response(
                f'Token exchange response has no access_token: {payload}',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        expires_in = payload.get('expires_in') or payload.get('data', {}).get('expires_in')
        refresh_token = payload.get('refresh_token') or payload.get('data', {}).get('refresh_token')

        icp.set_param('tiktok_video_uploader.access_token', access_token)
        icp.set_param('tiktok_video_uploader.refresh_token', refresh_token or '')
        if expires_in:
            expire_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
            icp.set_param('tiktok_video_uploader.access_token_expire_at', expire_at.isoformat())

        return request.make_response(
            'TikTok connected successfully. You can return to Odoo and upload videos now.',
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
            status=200,
        )
