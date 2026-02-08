# Phase 6b: Email Allowlist Authorization

## Problem

Firebase Authentication allows **any Google account** to sign in. While data is scoped by `user_id` (strangers see empty dashboards), unauthorized users can still:

- Create runs (triggering Gemini API calls)
- Index documents (consuming embedding API quota)
- Trigger REMME scans
- Use the sandbox

This consumes GCP resources (Vertex AI, AlloyDB compute) with no access control beyond "has a Google account."

## Solution

Add an **email allowlist** to `core/auth.py` via the `ALLOWED_EMAILS` environment variable. When set, only JWTs from listed email addresses pass through. When unset, all authenticated users are allowed (current behavior preserved).

## Design Decisions

### 1. 403 Forbidden (not 401 Unauthorized)

- **401** = "who are you?" (missing/invalid token)
- **403** = "you can't come in" (valid token, email not in allowlist)

This follows HTTP semantics correctly and lets the frontend show different messages for each case.

### 2. Case-Insensitive Comparison

Emails are lowercased before comparison (`e.strip().lower()`) to prevent `User@Gmail.com` vs `user@gmail.com` mismatches.

### 3. Empty `ALLOWED_EMAILS` = Open Access

If the env var is set but blank (`ALLOWED_EMAILS=""`), it's treated the same as unset (open access). This prevents accidental lockout from misconfiguration.

### 4. `frozenset` for Lookup

Immutable, parsed once at module load, O(1) lookup. Follows the existing pattern of `_AUTH_DISABLED` being a module-level constant.

### 5. No Wildcard/Domain Matching

Keep it simple: comma-separated email addresses only. Domain-based rules (`*@company.com`) can be added later if needed.

### 6. Logging

Rejected emails are logged at WARNING level for audit trail. Full JWT claims are not logged (privacy).

## Implementation

### Backend: `core/auth.py`

**Module-level variable** (parsed once at import):

```python
_ALLOWED_EMAILS: frozenset[str] | None = (
    frozenset(e.strip().lower() for e in os.environ["ALLOWED_EMAILS"].split(",") if e.strip())
    if os.environ.get("ALLOWED_EMAILS")
    else None
)
_ALLOWED_EMAILS = _ALLOWED_EMAILS if _ALLOWED_EMAILS else None
```

**Check in `dispatch()`** (after token verification, before setting `user_id`):

```python
if _ALLOWED_EMAILS is not None:
    email = claims.get("email", "").lower()
    if email not in _ALLOWED_EMAILS:
        logger.warning("Access denied for email: %s", email)
        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied. Your account is not authorized."},
        )
```

### Frontend: `services/api.ts`

New `isForbiddenError()` helper alongside existing `isUnauthorizedError()`:

```typescript
export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}
```

### Frontend: `App.tsx`

Retry logic updated to also suppress retries on 403:

```typescript
retry: (failureCount, error) =>
  !isUnauthorizedError(error) && !isForbiddenError(error) && failureCount < 3,
```

### Frontend: `RunList.tsx`

Added 403-specific message before the existing 401 check:

```typescript
if (isForbiddenError(error)) {
  return <div>Access denied. Your account is not authorized to use this application.</div>
}
```

Also stops refetch polling on 403 (same as 401).

## Operational Guide

### Setting the Allowlist

```bash
# Single user
ALLOWED_EMAILS=user@gmail.com

# Multiple users
ALLOWED_EMAILS=user1@gmail.com,user2@company.com,admin@org.com

# Open access (unset or empty — same behavior)
# ALLOWED_EMAILS=     (unset)
# ALLOWED_EMAILS=""   (empty string)
```

### Cloud Run Deployment

```bash
gcloud run services update apexflow-api \
  --region=us-central1 \
  --update-env-vars="ALLOWED_EMAILS=pravin.gadekar@gmail.com" \
  --project=apexflow-ai
```

### Adding a New User

Update the env var on Cloud Run. The change takes effect on the next cold start (or redeploy).

```bash
gcloud run services update apexflow-api \
  --region=us-central1 \
  --update-env-vars="ALLOWED_EMAILS=existing@gmail.com,newuser@gmail.com" \
  --project=apexflow-ai
```

### Removing the Allowlist (Open Access)

```bash
gcloud run services update apexflow-api \
  --region=us-central1 \
  --remove-env-vars=ALLOWED_EMAILS \
  --project=apexflow-ai
```

## Request Flow

```
Browser → Firebase Auth (Google sign-in) → JWT token
    │
    ▼
Cloud Run (FastAPI middleware)
    │
    ├─ Path in SKIP_PATHS? → Pass through (no auth)
    │
    ├─ AUTH_DISABLED=1? → Set user_id="dev-user", pass through
    │
    ├─ No token? → 401 "Missing or invalid Authorization header"
    │
    ├─ Invalid token? → 401 "Invalid or expired token"
    │
    ├─ ALLOWED_EMAILS set AND email not in list? → 403 "Access denied"
    │
    └─ All checks pass → Set user_id, proceed to endpoint
```

## Verification

1. **Allowed email**: Sign in with a listed email → all endpoints work normally
2. **Unlisted email**: Sign in with a different Google account → 403 on all API calls, frontend shows "Access denied" message
3. **Unset allowlist**: Remove `ALLOWED_EMAILS` → any authenticated user gets through (open access)
4. **Empty string**: Set `ALLOWED_EMAILS=""` → behaves like unset (open access, no lockout)
5. **Case insensitivity**: `User@Gmail.com` in JWT matches `user@gmail.com` in allowlist

## Files Changed

| File | Change |
|------|--------|
| `core/auth.py` | Parse `ALLOWED_EMAILS`, add 403 check after token verification |
| `frontend/src/services/api.ts` | Add `isForbiddenError()` helper |
| `frontend/src/services/api.test.ts` | Add test for 403 detection |
| `frontend/src/App.tsx` | Suppress retries on 403 |
| `frontend/src/components/runs/RunList.tsx` | Handle 403 with distinct message, stop polling |
| `docs/phase-6b-email-allowlist.md` | This design document |
| `CLAUDE.md` | Add `ALLOWED_EMAILS` to env vars table and auth description |
| `AGENTS.md` | Add `ALLOWED_EMAILS` to env vars table |
| `README.md` | Add `ALLOWED_EMAILS` to configuration table, update roadmap |
| `docs/infrastructure-setup.md` | Add `ALLOWED_EMAILS` to Cloud Run deploy command |
