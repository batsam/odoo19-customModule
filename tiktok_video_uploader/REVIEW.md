# Code Review: `tiktok_video_uploader` (Odoo 19)

## Scope
Reviewed module manifest, models, controllers, security groups/rules, ACLs, and views for production-readiness with focus on **feature** and **security** recommendations.

---

## 1) Security Findings

### [High] Approval workflow can be bypassed by any publisher with write access
**Where:** `models/social_video_post.py`, `security/ir.model.access.csv`

- `action_approve()` and `action_reject()` do not enforce group checks.
- `group_social_publisher` has write permission on `social.video.post`.
- Result: publisher-level users can approve/reject by calling object methods directly (RPC), bypassing intended separation of duties.

**Recommendation**
- Enforce role-based checks inside methods (`has_group`) for approve/reject actions.
- Keep UI button visibility restrictions, but do not rely on UI alone.
- Optionally split state transitions into server-side guarded methods only.

---

### [High] Access tokens are stored in plain `Char` fields and readable by broad model readers
**Where:** `models/social_media_account.py`, `views/social_media_account_views.xml`, `security/ir.model.access.csv`

- `access_token` / `refresh_token` are regular fields on `social.media.account`.
- If non-admin users can read account records, secrets exposure risk increases.

**Recommendation**
- Restrict read access on `social.media.account` to admin/manager groups only.
- Move long-lived secrets to `ir.config_parameter` (sudo-only access), and keep account model token-light when possible.
- Hide token fields from non-admin groups in forms and lists.

---

### [Medium] OAuth callback endpoints are public and return raw exception text
**Where:** `controllers/main.py`

- Public callbacks are normal for OAuth, but responses currently expose raw exception messages.
- This can leak internals during failures.

**Recommendation**
- Return generic user-facing error messages.
- Log detailed exceptions server-side (`_logger.exception`) with sanitized context.

---

### [Medium] Sensitive API response payloads are stored and visible in business records
**Where:** `models/social_video_post.py`, `views/social_video_post_views.xml`

- Full response/error bodies are persisted and shown in form view.
- External payloads can include IDs, internal error traces, and integration metadata.

**Recommendation**
- Keep normalized fields (`external_id`, platform status, error code/message).
- Gate raw payload fields behind admin-only group or a debug flag.

---

## 2) Feature Recommendations

### Priority: High
1. **Platform-specific approval policy**  
   Add configurable approval matrix by platform/account (e.g., TikTok needs approval, Facebook doesn’t).

2. **Retry policy controls per platform**  
   Today retry/backoff is global per post. Add platform-level retry counters and limits to avoid one failed platform blocking success analytics.

3. **Operational dashboard**  
   Add kanban + pivots for states (`scheduled`, `partial`, `failed`, `dead_letter`) with filters by company/platform/account.

### Priority: Medium
4. **Asynchronous publish queue**  
   Offload API calls to queue/cron job records to avoid long synchronous requests from form actions.

5. **Preflight validation**  
   Add validation per platform before publish: caption length, media URL accessibility, allowed mime/codec, privacy constraints.

6. **Post-publish audit trail**  
   Track per-platform timeline entries (queued, sent, acknowledged, failed, retried).

### Priority: Low
7. **Template library for captions/hashtags**  
   Reusable caption templates with variables and company branding defaults.

8. **Rule simulation mode**  
   “Test routing rule” action to preview which accounts a post will target before publish.

---

## 3) Architecture / Maintainability Recommendations

1. **Extract shared API client services** (TikTok + Meta helpers) into reusable service classes/mixins to avoid drift.
2. **Add centralized exception normalization** for HTTP/API errors to standardize UX and logs.
3. **Add automated tests** for:
   - Approval authorization checks
   - Retry transitions (`failed -> dead_letter`)
   - Rule matching precedence
   - Multi-company isolation

---

## 4) Suggested Implementation Order

1. Fix approval authorization checks (**Security High**).  
2. Tighten token/data visibility ACLs (**Security High**).  
3. Add sanitized logging + generic callback responses (**Security Medium**).  
4. Add async queue execution path (**Feature High/Medium**).  
5. Add reporting/dashboard and routing simulation (**Feature Medium/Low**).

---

## 5) Notes

- The recent Odoo 19 group migration to `res.groups.privilege` is directionally correct.
- Next hardening phase should focus on **authorization enforcement in methods** and **secret visibility boundaries**.
