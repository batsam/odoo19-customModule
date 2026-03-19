# Code Review: `tiktok_video_uploader`

## Scope
Reviewed module manifest, models, controllers, security ACLs, XML views, and sequence data.

## Issues Found

### 1) [High] OAuth state is global and can be overwritten between users
**Where:** `controllers/main.py`

- `oauth_state` is stored in a single system parameter (`ir.config_parameter`), not user/session scoped.
- If two users start OAuth close together, the second login overwrites the state used by the first, causing false failures and opening the door to state confusion.

**Recommendation**
- Store `state` in the HTTP session (`request.session`) or per-user transient storage.
- Clear consumed state after successful callback.

---

### 2) [High] Internal users have full read access to API responses and errors
**Where:** `security/ir.model.access.csv`, `models/*.py`, views

- ACL grants full CRUD to `base.group_user` for both upload models.
- `response_body`/`error_message` may contain API error payloads and implementation details.
- Tokens are not written to these fields directly, but external payloads can still leak sensitive metadata.

**Recommendation**
- Restrict module usage to a dedicated manager/editor group.
- Make deletion (`perm_unlink`) limited to admin-level users.
- Consider hiding or sanitizing `response_body` for non-admin users.

---

### 3) [Medium] Duplicate TikTok upload logic in two models
**Where:** `models/tiktok_video_upload.py` and `models/social_video_post.py`

- TikTok init+upload flow appears in both models with near-identical code.
- This increases maintenance burden and risk of behavior drift.

**Recommendation**
- Extract shared TikTok client/service methods into a reusable abstract model or helper mixin.

---

### 4) [Medium] No input validation for uploaded file content/size
**Where:** `models/tiktok_video_upload.py`, `models/social_video_post.py`

- Binary payload is decoded and sent without validating size, extension, or MIME expectations.
- Large uploads can cause memory pressure and poor UX due to long synchronous requests.

**Recommendation**
- Validate max size and basic file type before API call.
- Add user-facing constraint errors for unsupported files.

---

### 5) [Medium] No refresh-token lifecycle handling
**Where:** `controllers/main.py`, `models/res_config_settings.py`

- Callback stores `refresh_token` and `access_token_expire_at` but publish methods never refresh token when expired.
- Upload failures will occur after token expiration unless manually reconnected.

**Recommendation**
- Implement token refresh service with automatic refresh-before-upload and fallback to reconnect flow.

---

### 6) [Low] Blocking external API calls inside request thread
**Where:** publish/upload methods in model classes

- Calls use long timeouts (120–300s) and run synchronously in UI action.
- This can block workers and degrade responsiveness.

**Recommendation**
- Move uploads to queue jobs/cron workers and surface progress via state tracking.

---

### 7) [Low] Raw external response persisted without normalization
**Where:** `_mark_uploaded`, exception handling

- Entire JSON or raw text is saved in `response_body`.
- Useful for debugging, but noisy and not structured for reporting.

**Recommendation**
- Persist key fields (`external_id`, `status`, `error_code`, `error_message`) and keep full payload optional behind debug mode.

---

## Suggested Refactor (example)

### A) Session-safe OAuth state handling (controller)
```python
# controllers/main.py (example)
state = secrets.token_urlsafe(24)
request.session['tiktok_oauth_state'] = state

expected_state = request.session.get('tiktok_oauth_state')
if not expected_state or expected_state != state:
    return request.make_response('Invalid OAuth state', status=400)
request.session.pop('tiktok_oauth_state', None)
```

### B) Shared TikTok upload helper (service-style)
```python
class TikTokApiMixin(models.AbstractModel):
    _name = 'tiktok.api.mixin'
    _description = 'TikTok API Shared Helpers'

    def _tiktok_init_and_upload(self, video_bytes, title, privacy_level):
        # centralize endpoint/headers/payload/error normalization
        # return (external_id, response_payload)
        ...
```

### C) Safer ACL split (example)
- Create groups:
  - `group_social_video_user` (read/create/write own records)
  - `group_social_video_manager` (full access + settings)
- Restrict unlink and sensitive response fields to manager group.

## Priority Fix Order
1. OAuth state hardening (High)
2. ACL tightening + field visibility controls (High)
3. Token refresh lifecycle (Medium)
4. Shared TikTok service refactor (Medium)
5. File validation and async execution path (Medium/Low)
