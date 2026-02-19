# E*TRADE OAuth Callback Research

> **Date:** 2026-02-19
> **Status:** RESEARCH COMPLETE - Implementation pending E*TRADE callback registration
> **Reference:** pyetrade Issue #104 (closed 2025-03-19)

---

## Executive Summary

OAuth callback-based authentication IS supported by E*TRADE and works. The pyetrade library has this feature working (Issue #104 closed as completed March 2025). Our current blocker is that E*TRADE has not activated our callback URL on our API key.

---

## Key Finding: pyetrade Issue #104

**Issue:** "Feature Request: Automatic Authorization via Callback URL with Verification Code"
**Author:** @danchev
**Status:** Closed as "completed" on 2025-03-19
**URL:** https://github.com/jessecooper/pyetrade/issues/104

This proves that callback OAuth DOES work with E*TRADE's API.

---

## How Callback OAuth Works (from E*TRADE Documentation)

From Issue #104 and E*TRADE docs:

### Configuring a Callback

> Using a callback requires that the callback URL be associated with your consumer key in the ETRADE system. To request this, log in to your ETRADE account and send a secure message to Customer Service. Select the subject "Technical Issues" and the topic "E*TRADE API". State that you would like to have a callback configured, and specify your consumer key and the desired callback URL.

### What Changes When Callback is Registered

Once the callback is configured, two system behaviors are changed:

1. **`oauth_callback_confirmed` property of `request_token` API returns TRUE**
2. **Users who approve the authorization request are automatically redirected to the callback URL**, with the verification code appended as a query parameter

---

## pyetrade Implementation Analysis

### Location
`/opt/miniconda3/lib/python3.13/site-packages/pyetrade/authorization.py`

### Key Code (lines 27-72)

```python
class ETradeOAuth(object):
    def __init__(
        self, consumer_key: str, consumer_secret: str, callback_url: str = "oob"
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        # ...
        self.callback_url = callback_url  # <-- Callback URL stored

    def get_request_token(self) -> str:
        # Set up session with callback URL
        self.session = OAuth1Session(
            self.consumer_key,
            self.consumer_secret,
            callback_uri=self.callback_url,  # <-- Callback passed here
            signature_type="AUTH_HEADER",
        )
        # get request token
        self.session.fetch_request_token(self.req_token_url)
        # ...

    def get_access_token(self, verifier: str) -> dict:
        # Set verifier
        self.session._client.client.verifier = verifier
        # Get access token
        self.access_token = self.session.fetch_access_token(self.access_token_url)
        return self.access_token
```

### Key Differences from Our Implementation

| Aspect | pyetrade | Our Implementation |
|--------|----------|-------------------|
| OAuth Class | `OAuth1Session` | `OAuth1` |
| Request Token | `fetch_request_token()` | Manual GET with `auth=oauth` |
| Access Token | `fetch_access_token()` | Manual GET with `auth=oauth` |
| Verifier | Set on client object | Passed to OAuth1 constructor |
| Session Persistence | Session object maintained | Tokens stored separately |

---

## Current Status of Our API Key

### Diagnostic Test Results (2026-02-17)

| Test | Callback URL | Result |
|------|--------------|--------|
| Production key + callback URL | `https://web-production-9f73cd.up.railway.app/api/auth/callback` | HTTP 400, `callback_rejected` |
| Production key + 'oob' | `oob` | HTTP 200, `oauth_callback_confirmed=true` |

### What This Means

The API returns `oauth_acceptable_callback=oob` which confirms:
- Our callback URL is NOT active in E*TRADE's system
- It may be "submitted" but not "activated/propagated"
- The API key only accepts manual verification code flow

---

## API Key Details

| Environment | Consumer Key | Callback Status |
|-------------|--------------|-----------------|
| Production | `353ce1949c42c71cec4785343aa36539` | NOT ACTIVE |
| Sandbox | `8a18ff810b153dfd5d9ddce27667d63c` | NOT ACTIVE |

**Callback URL to Register:**
```
https://web-production-9f73cd.up.railway.app/api/auth/callback
```

---

## Action Required: Contact E*TRADE Support

### Specific Questions to Ask

1. **Is the callback marked as "ACTIVE" (not just "SUBMITTED")?**
   - Support may say "done" but it might just be submitted, not propagated

2. **Has it propagated to the production API servers?**
   - There may be a 24-48 hour propagation delay

3. **Can you test from your end?**
   - Ask them to verify `oauth_callback_confirmed=true` is returned

4. **Request a support ticket reference**
   - For escalation if needed

### Updated Support Request Template

```
Subject: Callback URL Activation Status - Reference: pyetrade Issue #104

My callback URL is still not working despite registration attempts.

Consumer Key: 353ce1949c42c71cec4785343aa36539
Callback URL: https://web-production-9f73cd.up.railway.app/api/auth/callback

The API still returns: oauth_acceptable_callback=oob

This callback OAuth feature IS supported - see pyetrade Issue #104
(https://github.com/jessecooper/pyetrade/issues/104) which was closed
as completed in March 2025.

Please verify:
1. Is the callback marked as "ACTIVE" in your system?
2. Has it propagated to production API servers?
3. Can you test the request_token call from your end?
```

---

## Implementation Plan (Once Callback is Registered)

### Changes Needed in Our Code

#### 1. Update `etrade_client.py` - Switch to OAuth1Session

The pyetrade library uses `OAuth1Session` instead of `OAuth1`. This provides:
- Automatic token fetching (`fetch_request_token`, `fetch_access_token`)
- Built-in callback handling
- Cleaner session management

```python
from requests_oauthlib import OAuth1Session

class ETradeClient:
    def get_authorization_url(self, callback_url=None):
        callback_uri = callback_url or 'oob'

        # Use OAuth1Session (like pyetrade)
        self.oauth_session = OAuth1Session(
            self.consumer_key,
            self.consumer_secret,
            callback_uri=callback_uri,
            signature_type='AUTH_HEADER'
        )

        # Fetch request token automatically
        self.oauth_session.fetch_request_token(REQUEST_TOKEN_URL)

        # Get authorization URL
        auth_url = self.oauth_session.authorization_url(AUTHORIZE_URL)
        # Format for E*TRADE: url?key=consumer_key&token=request_token
        formatted_url = f"{AUTHORIZE_URL}?key={self.consumer_key}&token={self.oauth_session.token['oauth_token']}"

        return {
            'authorize_url': formatted_url,
            'request_token': self.oauth_session.token['oauth_token'],
            'request_token_secret': self.oauth_session.token['oauth_token_secret']
        }

    def complete_authentication(self, verifier_code, request_token=None, request_token_secret=None):
        # With OAuth1Session, verifier can come from callback URL or manual entry
        self.oauth_session._client.client.verifier = verifier_code
        access_token = self.oauth_session.fetch_access_token(ACCESS_TOKEN_URL)

        self.access_token = access_token['oauth_token']
        self.access_token_secret = access_token['oauth_token_secret']

        return {
            'access_token': self.access_token,
            'access_token_secret': self.access_token_secret,
            'success': True
        }
```

#### 2. Add Callback Endpoint in `server.py`

```python
@app.route('/api/auth/callback')
def auth_callback():
    """
    OAuth callback endpoint - receives verifier from E*TRADE

    E*TRADE redirects here with: ?oauth_token=xxx&oauth_verifier=xxx
    """
    oauth_token = request.args.get('oauth_token')
    oauth_verifier = request.args.get('oauth_verifier')

    if not oauth_verifier:
        return redirect(url_for('index', error='No verifier received'))

    try:
        client = get_etrade_client()

        # Get stored request token from session
        request_token = session.get('request_token')
        request_token_secret = session.get('request_token_secret')

        result = client.complete_authentication(
            oauth_verifier,
            request_token,
            request_token_secret
        )

        # Store tokens
        token_manager.store_tokens(
            result['access_token'],
            result['access_token_secret']
        )

        # Redirect to main page with success
        return redirect(url_for('index', auth_success='true'))

    except Exception as e:
        logger.error(f"Callback authentication failed: {e}")
        return redirect(url_for('index', error=str(e)))
```

#### 3. Update Frontend for Callback Flow

When callback is registered, the flow becomes:

1. User clicks "Connect to E*TRADE"
2. Popup/tab opens to E*TRADE authorization
3. User authorizes
4. E*TRADE redirects to our callback URL with `oauth_verifier`
5. Our server exchanges verifier for access token
6. User is redirected back to main page, authenticated

No manual code entry needed!

---

## Benefits of Callback OAuth

| Current (OOB) | With Callback |
|---------------|---------------|
| User must copy/paste code | Automatic redirect |
| Code expires in 5 minutes | Seamless flow |
| Confusing UX | Better UX |
| Manual error possible | No manual steps |

---

## Testing Checklist (Once Registered)

1. [ ] Verify `oauth_callback_confirmed=true` in request_token response
2. [ ] Test callback URL receives `oauth_verifier` parameter
3. [ ] Test access token exchange works with callback verifier
4. [ ] Test full flow from authorization to API access
5. [ ] Update UI to show callback-based flow (remove manual code entry)

---

## References

- pyetrade Library: https://github.com/jessecooper/pyetrade
- pyetrade Issue #104: https://github.com/jessecooper/pyetrade/issues/104
- E*TRADE OAuth Docs: https://apisb.etrade.com/docs/api/authorization/request_token.html
- requests-oauthlib Docs: https://requests-oauthlib.readthedocs.io/
