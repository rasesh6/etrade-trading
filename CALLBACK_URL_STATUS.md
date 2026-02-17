# E*TRADE Callback URL Status

## Current Status: WAITING

**Date**: 2026-02-17

### Issue
E*TRADE API is rejecting our callback URL despite support saying it's configured.

### Error Received
```
oauth_problem=callback_rejected,oauth_acceptable_callback=oob
```

### Callback URL Requested
```
https://web-production-9f73cd.up.railway.app/api/auth/callback
```

### Keys Configuration Status
| Environment | Consumer Key | Callback Status |
|-------------|--------------|-----------------|
| Production  | `353ce1949c42c71cec4785343aa36539` | NOT ACTIVE (API rejects) |
| Sandbox     | `8a18ff810b153dfd5d9ddce27667d63c` | NOT ACTIVE (API rejects) |

### Diagnostic Test Results (2026-02-17)
```python
# Production key + callback URL: HTTP 400, callback_rejected
# Sandbox key + callback URL: HTTP 400, callback_rejected
# Production key + 'oob': HTTP 200, oauth_callback_confirmed=true
```

### What This Means
E*TRADE support may have "submitted" the callback configuration, but it's NOT YET ACTIVE on the API. The API explicitly states `oauth_acceptable_callback=oob`, meaning only manual verification code flow is accepted.

### Action Required
Contact E*TRADE support and ask:
1. Is the callback URL ACTIVE or just SUBMITTED?
2. Is it configured for production key: `353ce1949c42c71cec4785343aa36539`?
3. Are there propagation delays? How long until active?

### Current Workaround
Using manual verification code flow (oob) - working fine.

### Rollback Info
- Baseline tag: `v1.0.0-callback-baseline`
- Rollback commit: `26efbfc`
- App is currently in working manual verification mode
