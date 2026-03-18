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
        account_data = payload.get('data', {})
        tiktok_account_id = account_data.get('open_id') or account_data.get('union_id') or 'tiktok_default'
        request.env['social.media.account'].sudo().upsert_connected_account(
            {
                'name': f'TikTok {tiktok_account_id}',
                'platform': 'tiktok',
                'external_account_id': tiktok_account_id,
                'access_token': access_token,
                'refresh_token': refresh_token or False,
                'scope': icp.get_param('tiktok_video_uploader.scopes', default='user.info.basic,video.publish'),
            }
        )

        return request.make_response(
            'TikTok connected successfully. You can return to Odoo and upload videos now.',
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
            status=200,
        )

    @http.route('/facebook/connect', type='http', auth='user', methods=['GET'])
    def facebook_connect(self, **kwargs):
        icp = request.env['ir.config_parameter'].sudo()
        app_id = icp.get_param('tiktok_video_uploader.meta_app_id')
        redirect_uri = icp.get_param('tiktok_video_uploader.meta_redirect_uri')
        scopes = icp.get_param(
            'tiktok_video_uploader.meta_scopes',
            default='pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish',
        )
        authorize_endpoint = icp.get_param(
            'tiktok_video_uploader.meta_authorize_endpoint',
            default='https://www.facebook.com/v23.0/dialog/oauth',
        )

        if not app_id or not redirect_uri:
            return request.make_response(
                'Missing Meta OAuth configuration. Please set Meta App ID and Redirect URI in Odoo settings.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        state = secrets.token_urlsafe(24)
        request.session['tiktok_video_uploader.meta_oauth_state'] = state
        query = urlencode(
            {
                'client_id': app_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': scopes,
                'state': state,
            }
        )
        return request.redirect(f'{authorize_endpoint}?{query}', local=False)

    @http.route('/facebook/callback', type='http', auth='public', methods=['GET'], csrf=False)
    def facebook_callback(self, code=None, state=None, error=None, error_description=None, **kwargs):
        if error:
            message = f'Meta authorization failed: {error} {error_description or ""}'.strip()
            return request.make_response(message, headers=[('Content-Type', 'text/plain; charset=utf-8')], status=400)

        if not code or not state:
            return request.make_response(
                'Missing OAuth code/state in callback.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        expected_state = request.session.get('tiktok_video_uploader.meta_oauth_state')
        if not expected_state or expected_state != state:
            return request.make_response(
                'Invalid OAuth state. Please retry Meta connect.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )
        request.session.pop('tiktok_video_uploader.meta_oauth_state', None)

        icp = request.env['ir.config_parameter'].sudo()
        app_id = icp.get_param('tiktok_video_uploader.meta_app_id')
        app_secret = icp.get_param('tiktok_video_uploader.meta_app_secret')
        redirect_uri = icp.get_param('tiktok_video_uploader.meta_redirect_uri')
        token_endpoint = icp.get_param(
            'tiktok_video_uploader.meta_token_endpoint',
            default='https://graph.facebook.com/v23.0/oauth/access_token',
        )
        graph_endpoint = icp.get_param(
            'tiktok_video_uploader.meta_graph_endpoint',
            default='https://graph.facebook.com/v23.0',
        )

        if not app_id or not app_secret or not redirect_uri:
            return request.make_response(
                'Missing Meta OAuth settings (app id/secret/redirect URI).',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        try:
            short_res = requests.get(
                token_endpoint,
                params={
                    'client_id': app_id,
                    'client_secret': app_secret,
                    'redirect_uri': redirect_uri,
                    'code': code,
                },
                timeout=60,
            )
            short_res.raise_for_status()
            short_payload = short_res.json()
            short_token = short_payload.get('access_token')
            if not short_token:
                raise ValueError(f'No short-lived access token in response: {short_payload}')

            long_res = requests.get(
                token_endpoint,
                params={
                    'grant_type': 'fb_exchange_token',
                    'client_id': app_id,
                    'client_secret': app_secret,
                    'fb_exchange_token': short_token,
                },
                timeout=60,
            )
            long_res.raise_for_status()
            long_payload = long_res.json()
            long_token = long_payload.get('access_token') or short_token
            expires_in = long_payload.get('expires_in')

            me_res = requests.get(
                f'{graph_endpoint}/me',
                params={'fields': 'id', 'access_token': long_token},
                timeout=60,
            )
            me_res.raise_for_status()
            me_payload = me_res.json()

            page_res = requests.get(
                f'{graph_endpoint}/me/accounts',
                params={'fields': 'id,name,access_token', 'access_token': long_token},
                timeout=60,
            )
            page_res.raise_for_status()
            pages = page_res.json().get('data', [])
            primary_page = pages[0] if pages else {}
            page_id = primary_page.get('id')
            page_access_token = primary_page.get('access_token')

            ig_user_id = None
            if page_id:
                ig_res = requests.get(
                    f'{graph_endpoint}/{page_id}',
                    params={'fields': 'connected_instagram_account{id}', 'access_token': page_access_token or long_token},
                    timeout=60,
                )
                if ig_res.ok:
                    ig_payload = ig_res.json()
                    ig_user_id = (ig_payload.get('connected_instagram_account') or {}).get('id')
        except (requests.RequestException, ValueError) as exc:
            return request.make_response(
                f'Meta token exchange failed: {exc}',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=400,
            )

        icp.set_param('tiktok_video_uploader.meta_access_token', long_token)
        icp.set_param('tiktok_video_uploader.meta_user_id', me_payload.get('id') or '')
        if expires_in:
            expire_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
            icp.set_param('tiktok_video_uploader.meta_access_token_expire_at', expire_at.isoformat())
        if page_id:
            icp.set_param('tiktok_video_uploader.facebook_page_id', page_id)
            request.env['social.media.account'].sudo().upsert_connected_account(
                {
                    'name': f'Facebook Page {primary_page.get("name") or page_id}',
                    'platform': 'facebook',
                    'external_account_id': page_id,
                    'access_token': page_access_token or long_token,
                    'scope': icp.get_param('tiktok_video_uploader.meta_scopes'),
                }
            )
        if page_access_token:
            icp.set_param('tiktok_video_uploader.facebook_access_token', page_access_token)
        if ig_user_id:
            icp.set_param('tiktok_video_uploader.instagram_user_id', ig_user_id)
            icp.set_param('tiktok_video_uploader.instagram_access_token', page_access_token or long_token)
            request.env['social.media.account'].sudo().upsert_connected_account(
                {
                    'name': f'Instagram {ig_user_id}',
                    'platform': 'instagram',
                    'external_account_id': ig_user_id,
                    'access_token': page_access_token or long_token,
                    'scope': icp.get_param('tiktok_video_uploader.meta_scopes'),
                }
            )

        return request.make_response(
            'Meta connected successfully. Facebook/Instagram credentials were synced.',
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
            status=200,
        )
