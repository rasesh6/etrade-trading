# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-18
> **Current Version:** v1.3.1-auto-profit
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
- Check-fill polling happens every 2 seconds
- Order cancelled after timeout
- Profit order never placed

**Root Cause:**
Type mismatch in dictionary lookup:
- Order ID from URL parameter: `"40"` (string)
- Order ID stored in `_pending_profit_orders`: `40` (integer)
- Python `in` check: `"40" in {40: ...}` returns `False`

**Solution (commit `5e76a12`):**
```python
# BEFORE (broken)
if order_id not in _pending_profit_orders:
    profit_order = _pending_profit_orders[order_id]

# AFTER (fixed)
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

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Flask web server, API endpoints, profit order logic |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order logic |
| `token_manager.py` | Redis token storage |
| `config.py` | Credentials and configuration |
| `static/js/app.js` | Frontend logic, fill monitoring (polls every 2s) |
| `templates/index.html` | Trading UI |
| `VERSION.md` | Current version and features |
| `ETRADE_API_REFERENCE.md` | Complete API documentation |

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

# Rollback to v1.3.1 (type fix for profit orders)
git checkout 5e76a12
git push origin main --force

# Rollback to v1.3.0 (offset-based profit)
git checkout 4b4a088
git push origin main --force

# Rollback to v1.2.0 (absolute price profit target)
git checkout dd8831f
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

### Issue 12: Callback OAuth Authentication Fails

**Symptoms:**
- Error when trying to use callback-based OAuth
- `oauth_problem=callback_rejected,oauth_acceptable_callback=oob`

**Root Cause:**
E*TRADE requires callback URLs to be pre-registered in the developer portal. The application is configured for `oob` (out-of-band/manual) only.

**Solution:**
1. Go to E*TRADE developer portal
2. Edit application settings
3. Add callback URL: `https://web-production-9f73cd.up.railway.app/api/auth/callback`
4. Re-apply callback auth changes (commit `3910f18`)

**Current State:** Using manual verification code flow (oob)

---

## Session History

### 2026-02-18 Session
**Issues Fixed:**
1. Switched from SANDBOX to PRODUCTION mode
2. Configured Railway CLI access for direct log viewing
3. Fixed type mismatch bug in check-fill endpoint (order_id string vs int)
4. Documented extended hours trading limitation (must use LIMIT orders)

**Commits:**
- `4d5d945` - Documentation update for production mode
- `c7da7b1` - Debug logging for check-fill endpoint
- `5e76a12` - Fix order_id type mismatch
- `3910f18` - Attempted callback auth (reverted)
- `ec6b4f8` - Revert callback auth due to E*TRADE callback_rejected

**Key Learnings:**
- E*TRADE order IDs from API are integers, URL parameters are strings
- Market orders don't work in extended hours - use LIMIT orders
- "Order being executed" error on cancel means order filled successfully
- Always add logging when debugging async polling issues
- E*TRADE callback URLs must be pre-registered in developer portal
