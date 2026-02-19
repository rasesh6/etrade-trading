# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-19
> **Current Version:** v1.3.3-auto-profit
> **Environment:** PRODUCTION
> **Purpose:** Quick reference for debugging issues in future sessions

---

## Quick Diagnostics

### Check System Status
```bash
# Check Railway deployment health
curl -s https://web-production-9f73cd.up.railway.app/health

# Check auth status
curl -s https://web-production-9f73cd.up.railway.app/api/auth/status | python3 -m json.tool

# Check local server (if running)
curl -s http://localhost:5000/health
```

### Railway CLI Commands
```bash
# Check service status
railway status

# View recent logs (50 lines)
railway logs --tail 50

# View live logs (follow)
railway logs -f

# View environment variables
railway variables

# Check authentication
railway whoami
```

### Check Recent Logs
Look for deployment markers in Railway logs:
- `FIX4-2026-02-18-PREVIEWIDS-WRAPPER` - Order placement fix
- `v1.3.0-auto-profit` - Offset-based profit feature

---

## Common Issues & Solutions

### Issue 1: Sandbox Shows Wrong Accounts

**Symptoms:**
- See accounts like "NickName-1", "NickName-2" instead of your real accounts
- Positions in BR, GLD, MSFT, etc. that you don't own

**Root Cause:**
E*TRADE Sandbox uses simulated test accounts, not your real brokerage accounts.

**Solution:**
This is expected sandbox behavior. To see real accounts:
```bash
# Via Railway CLI
railway variables set ETRADE_USE_SANDBOX=false
```

---

### Issue 2: Order Placement Error 101/1033

**Symptoms:**
- Preview order succeeds
- Place order fails with "timed out your original order request"

**Root Cause:**
XML format missing `<PreviewIds>` wrapper

**Solution:**
```xml
<!-- WRONG -->
<previewId>168321663200</previewId>

<!-- CORRECT -->
<PreviewIds><previewId>168321663200</previewId></PreviewIds>
```

**Reference:** `etrade_client.py` lines 577-583, pyetrade/order.py lines 400-401

---

### Issue 3: OAuth Token Expired

**Symptoms:**
- HTTP 401 errors
- "Token is invalid or has expired"

**Solution:**
Re-authenticate through the web UI:
1. Go to https://web-production-9f73cd.up.railway.app
2. Click "Connect to E*TRADE"
3. Get verification code and enter it

**Token Validity:**
- Request token: 5 minutes
- Access token: Until midnight ET (or 2 hours inactive)

---

### Issue 4: Sandbox vs Production

**Sandbox:** `https://apisb.etrade.com` (simulated orders)
**Production:** `https://api.etrade.com` (real orders)

**Current Mode:** PRODUCTION

Set via environment variable:
```bash
# Via Railway CLI
railway variables set ETRADE_USE_SANDBOX=false  # Production
railway variables set ETRADE_USE_SANDBOX=true   # Sandbox
```

---

### Issue 5: Quote Shows Wrong Symbol (GOOG)

**Symptoms:**
- Request quote for SOXL, AAPL, etc.
- UI shows GOOG with Google Inc data

**Root Cause:**
E*TRADE Sandbox API returns old test data (GOOG from 2012) for any symbol requested.

**Solution:**
This is expected sandbox behavior. The UI displays the requested symbol, not the returned symbol.

For real quotes, use production mode (`ETRADE_USE_SANDBOX=false`).

---

### Issue 6: Profit Order Not Placed / Timeout

**Symptoms:**
- Order placed with profit target
- No profit order created
- Order cancelled after timeout

**Root Cause:**
- Opening order not filled within timeout period
- In sandbox, orders may not fill at all

**Solution:**
1. Check the Order Status card for real-time status
2. Increase timeout if needed (default 15s, max 60s)
3. In production, market orders typically fill instantly during market hours

---

### Issue 7: Fill Price Shows as 0

**Symptoms:**
- Order filled but profit order has strange price
- Fill price reported as 0 or missing

**Root Cause:**
E*TRADE API may not always include `executedPrice` in order details.

**Solution:**
The system defaults to 0 if fill price unavailable. In production, fill prices are typically available immediately.

---

### Issue 8: Railway CLI Not Working

**Symptoms:**
- `railway` command fails
- "Unauthorized" or "Not logged in"

**Solution:**
```bash
# Login to Railway
railway login

# Link to project
railway link --project "E*Trade Trading"

# Verify connection
railway status
railway whoami
```

---

### Issue 9: Profit Order Not Placed Despite Fill (CRITICAL BUG - FIXED)

**Symptoms:**
- Order fills in production
- Check-fill polling happens but never finds order
- Order cancelled after timeout
- Profit order never placed

**Root Cause:**
Type mismatch in dictionary lookup:
- Order ID from URL parameter: `"40"` (string)
- Order ID stored in `_pending_profit_orders`: `40` (integer)
- Python `in` check: `"40" in {40: ...}` returns `False`

**Solution (commit `5e76a12`):**
```python
# Convert both to strings for comparison
order_id_str = str(order_id)
matching_key = None
for k in _pending_profit_orders.keys():
    if str(k) == order_id_str:
        matching_key = k
        break

if not matching_key:
    return ...

profit_order = _pending_profit_orders[matching_key]
```

**File:** `server.py` function `check_single_order_fill()`

---

### Issue 10: Extended Hours Trading - Market Orders Don't Fill

**Symptoms:**
- Market order placed but doesn't fill
- Order cancelled after timeout
- E*TRADE shows order as "being executed"

**Root Cause:**
E*TRADE requires LIMIT orders for extended hours trading. Market orders are not supported outside regular market hours.

**Solution:**
Use LIMIT orders during extended hours:
1. Set Order Type to "LIMIT"
2. Set limit price near current bid/ask
3. The order will fill if price matches

**Note:** Regular market hours are 9:30 AM - 4:00 PM ET.

---

### Issue 11: Order Cancel Fails with "being executed"

**Symptoms:**
- Cancel order returns error 5001
- "This order is currently being executed or rejected. It cannot be cancelled."

**Root Cause:**
The order is actively being filled by E*TRADE. This error means the order DID fill (or is filling).

**Solution:**
This is actually a success case! The order filled before the cancel could process. The check-fill logic should detect this and place the profit order.

**Debugging:** Check Railway logs for the fill detection and profit order placement.

---

### Issue 12: Callback OAuth Authentication Fails

**Symptoms:**
- Error when trying to use callback-based OAuth
- `oauth_problem=callback_rejected,oauth_acceptable_callback=oob`

**Root Cause:**
E*TRADE requires callback URLs to be pre-registered in the developer portal. The production API key is configured for `oob` (out-of-band/manual) only.

**Detailed Testing (2026-02-18):**

| Test | Callback URL | Result |
|------|--------------|--------|
| HTTP callback | `http://web-production-9f73cd.up.railway.app/api/auth/callback` | Rejected |
| HTTPS callback | `https://web-production-9f73cd.up.railway.app/api/auth/callback` | Rejected |

**API Key Details:**
- Production Key: `353ce1949c42c71cec4785343aa36539`
- Request Token URL: `https://api.etrade.com/oauth/request_token`

**Solution:**
Contact E*TRADE developer support to register callback URL. See `etrade_callback_support_request.txt` for template.

**Current State:** Using manual verification code flow (oob)

---

### Issue 13: Fill Price Returns None / Profit Order Not Placed (CRITICAL BUG - FIXED)

**Symptoms:**
- Order fills successfully
- Profit order not placed
- Error: `unsupported operand type(s) for +: 'NoneType' and 'float'`
- `executedPrice` returns None

**Root Cause:**
Wrong field name used for fill price. E*TRADE API uses `averageExecutionPrice` inside the `Instrument` object, NOT `executedPrice` at OrderDetail level.

**Wrong Approach:**
```python
# WRONG - This field doesn't exist at this level
fill_price = order['OrderDetail'][0].get('executedPrice')  # Returns None!
```

**Correct Approach:**
```python
# CORRECT - Use averageExecutionPrice inside Instrument
for detail in order['OrderDetail']:
    if 'Instrument' in detail:
        for inst in detail['Instrument']:
            if inst.get('averageExecutionPrice'):
                fill_price = float(inst.get('averageExecutionPrice'))
                break
```

**API Response Structure:**
```
Order
  └── OrderDetail[]
        └── Instrument[]
              └── averageExecutionPrice  <-- This is the fill price!
              └── filledQuantity
              └── orderedQuantity
              └── orderAction
```

**Reference:** E*TRADE API docs at https://apisb.etrade.com/docs/api/order/api-order-v1.html

**File:** `server.py` function `check_single_order_fill()`

**Commit:** `4feb646`

---

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Flask web server, API endpoints, profit order logic |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order logic |
| `token_manager.py` | Redis token storage |
| `config.py` | Credentials and configuration |
| `static/js/app.js` | Frontend logic, fill monitoring (polls every 500ms) |
| `templates/index.html` | Trading UI |
| `VERSION.md` | Current version and features |
| `ETRADE_API_REFERENCE.md` | Complete API documentation |
| `etrade_callback_support_request.txt` | Template for E*TRADE support request |

---

## Reference Implementations

### pyetrade Library
Known working implementation for E*TRADE API:
```bash
# Location
/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py

# Key function: build_order_payload() lines 336-403
```

### XML Payload Building
```python
# From pyetrade - the correct PreviewIds format
if "previewId" in kwargs:
    payload[order_type]["PreviewIds"] = {"previewId": kwargs["previewId"]}
```

---

## Deployment Checklist

1. Make code changes
2. Update deployment marker in `etrade_client.py` (if relevant)
3. Commit with descriptive message
4. Push to main branch
5. Railway auto-deploys (~20-30 seconds)
6. Check logs: `railway logs --tail 30`
7. Test order placement

---

## Rollback Procedure

If a fix breaks something:
```bash
cd ~/Projects/etrade

# Rollback to v1.3.2 (500ms polling)
git checkout eb89b98
git push origin main --force

# Rollback to v1.3.1 (type fix for profit orders)
git checkout 5e76a12
git push origin main --force

# Rollback to v1.3.0 (offset-based profit)
git checkout 4b4a088
git push origin main --force
```

---

## Session Quick Start

For a new session, read these files first:
1. `VERSION.md` - Current version, features, Railway CLI info
2. `README.md` - System overview
3. `TROUBLESHOOTING.md` (this file)

### Quick Verification Commands
```bash
# Health check
curl -s https://web-production-9f73cd.up.railway.app/health

# Railway status
railway status

# Recent logs
railway logs --tail 20
```

---

## Railway Project Info

| Property | Value |
|----------|-------|
| Project Name | E*Trade Trading |
| Project ID | `1419ac9f-57ed-49ee-8ff3-524ac3c52bf8` |
| Service Name | web |
| Service ID | `524166fa-7207-4399-9383-6158a833eb71` |
| Public URL | https://web-production-9f73cd.up.railway.app |

---

## Pending Items

### 1. E*TRADE Callback URL Registration
**Status:** Waiting on E*TRADE support
**Action:** Submit `etrade_callback_support_request.txt` to E*TRADE
**Callback URL to register:** `https://web-production-9f73cd.up.railway.app/api/auth/callback`
**API Key:** `353ce1949c42c71cec4785343aa36539`

### 2. SSE for Real-time Fill Notifications
**Status:** Planned (after callback auth)
**Goal:** Server-side monitoring with Server-Sent Events push to browser
**Benefits:**
- Monitoring continues even if browser tab is closed
- Real-time push (no polling delay)
- More reliable than client-side polling

**Implementation Plan:**
1. Store pending orders in Redis (survives restarts)
2. Server polls E*TRADE API every 500ms
3. Use SSE to push fills to connected browsers
4. Fallback to current polling if SSE not available

---

## Session History

### 2026-02-18 Session

**Issues Fixed:**
1. Switched from SANDBOX to PRODUCTION mode
2. Configured Railway CLI access for direct log viewing
3. Fixed type mismatch bug in check-fill endpoint (order_id string vs int)
4. Documented extended hours trading limitation (must use LIMIT orders)
5. Improved fill detection speed (500ms polling)

**Commits (chronological):**
| Commit | Description |
|--------|-------------|
| `4d5d945` | Documentation update for production mode |
| `c7da7b1` | Debug logging for check-fill endpoint |
| `5e76a12` | Fix order_id type mismatch |
| `3910f18` | Attempted callback auth (first attempt) |
| `ec6b4f8` | Revert callback auth (first rejection) |
| `03c44c9` | Callback auth with detailed debugging |
| `36620b3` | Fixed HTTPS callback URL |
| `7a1644c` | Reverted to oob (callback still rejected) |
| `e9692f7` | Documentation for callback rejection |
| `3e61b69` | Added E*TRADE support request template |
| `eb89b98` | Reduced fill polling from 2s to 500ms |

**Key Learnings:**
- E*TRADE order IDs from API are integers, URL parameters are strings
- Market orders don't work in extended hours - use LIMIT orders
- "Order being executed" error on cancel means order filled successfully
- Always add logging when debugging async polling issues
- E*TRADE callback URLs must be pre-registered in developer portal
- E*TRADE returns `oauth_acceptable_callback=oob` when callback not registered
- Railway terminates SSL, so `request.host_url` returns HTTP not HTTPS

---

## API Keys

| Environment | Key | Used For |
|-------------|-----|----------|
| Sandbox | `8a18ff810b153dfd5d9ddce27667d63c` | Testing (simulated) |
| Production | `353ce1949c42c71cec4785343aa36539` | Real trading (CURRENT) |
