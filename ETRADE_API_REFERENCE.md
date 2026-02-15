# E*TRADE API Reference Documentation

> **Last Updated:** 2026-02-15
> **Purpose:** Complete reference for E*TRADE OAuth 1.0a implementation and API endpoints

---

## Table of Contents

1. [OAuth 1.0a Authentication](#oauth-10a-authentication)
2. [API Endpoints](#api-endpoints)
3. [Official Python Example Analysis](#official-python-example-analysis)
4. [Common Issues & Solutions](#common-issues--solutions)
5. [Token Lifecycle](#token-lifecycle)

---

## OAuth 1.0a Authentication

### Overview

E*TRADE uses OAuth 1.0a for authentication. The flow consists of 3 steps:

1. **Request Token** - Get temporary token (valid 5 minutes)
2. **User Authorization** - User logs in and gets verification code
3. **Access Token** - Exchange verification code for access token (valid until midnight ET)

### URLs

| Environment | Base URL | OAuth URL |
|-------------|----------|-----------|
| **Sandbox** | `https://apisb.etrade.com` | `https://api.etrade.com/oauth/*` |
| **Production** | `https://api.etrade.com` | `https://api.etrade.com/oauth/*` |

**Note:** OAuth endpoints use `api.etrade.com` for both sandbox and production!

### Step 1: Request Token

**Endpoint:** `GET https://api.etrade.com/oauth/request_token`

**Required OAuth Parameters (in Authorization header):**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `oauth_consumer_key` | Yes | Your consumer key |
| `oauth_timestamp` | Yes | Epoch time (accurate within 5 minutes) |
| `oauth_nonce` | Yes | Random unique value per request |
| `oauth_signature_method` | Yes | Must be `HMAC-SHA1` |
| `oauth_signature` | Yes | Signature calculated with shared secret |
| `oauth_callback` | Yes | Must be `"oob"` for manual verification |

**Authorization Header Format:**
```
Authorization: OAuth realm="",oauth_callback="oob",
oauth_signature="...",oauth_nonce="...",
oauth_signature_method="HMAC-SHA1",
oauth_consumer_key="...",oauth_timestamp="..."
```

**Response:** URL-encoded string
```
oauth_token=%2FiQRgQCRGPo7Xdk6G8QDSEzX0Jsy6sKNcULcDavAGgU%3D
&oauth_token_secret=%2FrC9scEpzcwSEMy4vE7nodSzPLqfRINnTNY4voczyFM%3D
&oauth_callback_confirmed=true
```

**Token Expiry:** 5 minutes

### Step 2: User Authorization

**URL Format:**
```
https://us.etrade.com/e/t/etws/authorize?key={consumer_key}&token={request_token}
```

User will:
1. Log in to E*TRADE
2. Grant permission to your application
3. Receive a verification code (e.g., `Y27X25F`)

### Step 3: Access Token

**Endpoint:** `GET https://api.etrade.com/oauth/access_token`

**Required OAuth Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `oauth_consumer_key` | Yes | Your consumer key |
| `oauth_timestamp` | Yes | Epoch time |
| `oauth_nonce` | Yes | Random unique value |
| `oauth_signature_method` | Yes | Must be `HMAC-SHA1` |
| `oauth_signature` | Yes | Signature with request token secret |
| `oauth_token` | Yes | Request token from Step 1 |
| `oauth_verifier` | Yes | Verification code from user |

**Authorization Header Format:**
```
Authorization: OAuth realm="",oauth_signature="...",
oauth_nonce="...",oauth_signature_method="HMAC-SHA1",
oauth_consumer_key="...",oauth_timestamp="...",
oauth_verifier="Y27X25F",
oauth_token=%2FiQRgQCRGPo7Xdk6G8QDSEzX0Jsy6sKNcULcDavAGgU%3D
```

**Response:** URL-encoded string
```
oauth_token=%3TiQRgQCRGPo7Xdk6G8QDSEzX0Jsy6sKNcULcDavAGgU%3D
&oauth_token_secret=%7RrC9scEpzcwSEMy4vE7nodSzPLqfRINnTNY4voczyFM%3D
```

**Token Expiry:** Midnight US Eastern Time (or 2 hours of inactivity)

---

## API Endpoints

### Accounts API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/accounts/list.json` | GET | List all accounts |
| `/v1/accounts/{accountIdKey}/balance.json` | GET | Get account balance |
| `/v1/accounts/{accountIdKey}/portfolio.json` | GET | Get portfolio positions |

### Market API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/market/quote/{symbols}.json` | GET | Get quotes (comma-separated symbols) |

### Order API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/accounts/{accountIdKey}/orders.json` | GET | List orders (status param: OPEN, EXECUTED, etc.) |
| `/v1/accounts/{accountIdKey}/orders/preview.json` | POST | Preview order (XML body) |
| `/v1/accounts/{accountIdKey}/orders/place.json` | POST | Place order (XML body) |
| `/v1/accounts/{accountIdKey}/orders/cancel.json` | PUT | Cancel order (XML body) |

### Required Headers for API Calls

All authenticated API calls require:

```python
headers = {
    "consumerKey": "your_consumer_key"
}
```

For POST/PUT with XML payload:
```python
headers = {
    "Content-Type": "application/xml",
    "consumerKey": "your_consumer_key"
}
```

---

## Official Python Example Analysis

### Library Used: `rauth`

```python
from rauth import OAuth1Service

etrade = OAuth1Service(
    name="etrade",
    consumer_key=config["DEFAULT"]["CONSUMER_KEY"],
    consumer_secret=config["DEFAULT"]["CONSUMER_SECRET"],
    request_token_url="https://api.etrade.com/oauth/request_token",
    access_token_url="https://api.etrade.com/oauth/access_token",
    authorize_url="https://us.etrade.com/e/t/etws/authorize?key={}&token={}",
    base_url="https://api.etrade.com"
)
```

### OAuth Flow in Official Example

```python
# Step 1: Get request token
request_token, request_token_secret = etrade.get_request_token(
    params={"oauth_callback": "oob", "format": "json"}
)

# Step 2: User authorization (open browser)
authorize_url = etrade.authorize_url.format(etrade.consumer_key, request_token)
webbrowser.open(authorize_url)
verifier_code = input("Enter verification code: ")

# Step 3: Get access token and session
session = etrade.get_auth_session(
    request_token,
    request_token_secret,
    params={"oauth_verifier": verifier_code}
)
```

### Making API Calls (Official Example)

```python
# GET request - accounts list
url = base_url + "/v1/accounts/list.json"
response = session.get(url, header_auth=True)

# GET request with params - balance
url = base_url + "/v1/accounts/" + accountIdKey + "/balance.json"
params = {"instType": "BROKERAGE", "realTimeNAV": "true"}
headers = {"consumerkey": consumer_key}
response = session.get(url, header_auth=True, params=params, headers=headers)

# POST request - preview order
url = base_url + "/v1/accounts/" + accountIdKey + "/orders/preview.json"
headers = {"Content-Type": "application/xml", "consumerKey": consumer_key}
payload = "<PreviewOrderRequest>...</PreviewOrderRequest>"
response = session.post(url, header_auth=True, headers=headers, data=payload)
```

### Key Observations from Official Example

1. **`header_auth=True`** - Official example uses this parameter for API calls
2. **Lowercase `consumerkey`** - Header uses lowercase `consumerkey` (not `consumerKey`)
3. **No explicit HMAC-SHA1** - rauth handles signature method automatically
4. **No realm parameter** - Official example doesn't explicitly set realm

---

## Common Issues & Solutions

### Issue 1: OAuth1Session signature_type Error

**Error:** `OAuth1Session.__init__() got an unexpected keyword argument 'signature_type'`

**Cause:** rauth 0.7.3 is incompatible with requests-oauthlib >= 2.0.0

**Solution:** Use requests-oauthlib directly instead of rauth, or pin requests-oauthlib<2.0.0

### Issue 2: Token Invalid or Expired

**Error:** `HTTP 401 - Token is invalid, or has expired`

**Causes:**
- Request token expired (> 5 minutes)
- Access token expired (midnight ET or 2hr inactive)
- Using wrong OAuth URL (sandbox vs production)
- Token not URL-decoded properly

**Solutions:**
- Ensure tokens are URL-decoded after receiving them
- Re-authenticate if tokens expired
- Use correct base URL for environment

### Issue 3: POST vs GET for OAuth

**Error:** OAuth endpoints return error

**Cause:** E*TRADE uses GET for both request_token and access_token (not POST)

**Solution:** Use GET method for OAuth endpoints

---

## Token Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    E*TRADE Token Lifecycle                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Request Token                                                │
│     ├─ Obtained via /oauth/request_token                        │
│     ├─ Valid for: 5 MINUTES                                     │
│     └─ Used to generate authorization URL                       │
│                                                                  │
│  2. Verification Code                                            │
│     ├─ User gets this after logging in                          │
│     ├─ Single use only                                          │
│     └─ Must be used with matching request token                 │
│                                                                  │
│  3. Access Token                                                 │
│     ├─ Obtained via /oauth/access_token                         │
│     ├─ Valid until: MIDNIGHT US EASTERN TIME                    │
│     ├─ Inactive after: 2 HOURS of no API calls                  │
│     └─ Used for all authenticated API calls                     │
│                                                                  │
│  4. Token Renewal (optional)                                     │
│     ├─ Use /oauth/renew_access_token before expiry              │
│     └─ Avoids need to re-authenticate                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Notes

### requests-oauthlib Configuration

Our implementation uses `requests-oauthlib` instead of `rauth`:

```python
from requests_oauthlib import OAuth1

oauth = OAuth1(
    consumer_key,
    client_secret=consumer_secret,
    callback_uri='oob',           # For request token
    signature_method='HMAC-SHA1', # Required by E*TRADE
    signature_type='auth_header', # OAuth params in header
    realm=''                      # E*TRADE expects empty realm
)

# For access token, add:
oauth = OAuth1(
    consumer_key,
    client_secret=consumer_secret,
    resource_owner_key=request_token,      # From step 1
    resource_owner_secret=request_token_secret,
    verifier=verifier_code,                 # From user
    signature_method='HMAC-SHA1',
    signature_type='auth_header',
    realm=''
)
```

### URL Decoding Tokens

E*TRADE returns URL-encoded tokens. Must decode before use:

```python
from urllib.parse import unquote

# Parse URL-encoded response
for pair in response_text.split('&'):
    key, value = pair.split('=', 1)
    params[key] = unquote(value)  # Decode the value
```

---

## References

- [E*TRADE Request Token Documentation](https://apisb.etrade.com/docs/api/authorization/request_token.html)
- [E*TRADE Get Access Token Documentation](https://apisb.etrade.com/docs/api/authorization/get_access_token.html)
- [E*TRADE Official Python Example](~/Downloads/EtradePythonClient/)
- [requests-oauthlib Documentation](https://requests-oauthlib.readthedocs.io/)
