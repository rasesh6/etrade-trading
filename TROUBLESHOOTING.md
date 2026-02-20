# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-20
> **Current Version:** v1.5.2-exponential-backoff
> **Environment:** PRODUCTION
> **Timezone:** All times in **CST (Central Standard Time)** unless otherwise noted
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
- `v1.5.2-exponential-backoff` - Exponential backoff for API errors
- `v1.5.1-api-error-handling` - API error handling fix
- `v1.5.0-trailing-stop` - Trailing stop feature
- `v1.4.0-bracket-orders` - Bracket order feature (failed)

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

### Issue 9: Profit Order Not Placed Despite Fill (FIXED)

**Symptoms:**
- Order fills in production
- Check-fill polling happens but never finds order
- Order cancelled after timeout
- Profit order never placed

**Root Cause:**
Type mismatch in dictionary lookup (order_id string vs int)

**Solution:** Already fixed in v1.3.1

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

---

### Issue 12: Callback OAuth Authentication Fails

**Symptoms:**
- Error when trying to use callback-based OAuth
- `oauth_problem=callback_rejected,oauth_acceptable_callback=oob`

**Root Cause:**
E*TRADE requires callback URLs to be pre-registered in the developer portal. The production API key is configured for `oob` (out-of-band/manual) only.

**Solution:**
Contact E*TRADE developer support to register callback URL.

**Current State:** Using manual verification code flow (oob)

**Test script:** `python test_callback_oauth.py`

---

### Issue 13: Fill Price Returns None (FIXED)

**Symptoms:**
- Order fills successfully
- Profit order not placed
- Error: `unsupported operand type(s) for +: 'NoneType' and 'float'`

**Root Cause:**
Wrong field name used for fill price. E*TRADE API uses `averageExecutionPrice` inside `Instrument`, NOT `executedPrice`.

**Correct approach:**
```python
fill_price = order['OrderDetail'][0]['Instrument'][0]['averageExecutionPrice']
```

---

### Issue 14: Redis Connection Failed (FIXED in v1.4.0)

**Symptoms:**
- Logs show: "Redis connection failed, using file fallback"
- "Error -2 connecting to redis.railway.internal:6379. Name or service not known."
- Tokens stored in /tmp instead of Redis

**Root Cause:**
REDIS_URL pointing to non-existent Redis service. Need to use Redis-Y5_F service.

**Solution:**
```bash
# Update REDIS_URL to reference new Redis service
railway variables --set "REDIS_URL=\${{Redis-Y5_F.REDIS_URL}}"

# Redeploy
railway up
```

**Verify:** Check logs for "Connected to Redis for token storage"

---

### Issue 15: Bracket Order Confirmation Timeout

**Symptoms:**
- Bracket order placed
- "Confirmation timeout - price did not reach trigger"
- Position remains open without bracket

**Root Cause:**
Price did not move to the confirmation trigger level within the timeout period.

**Solution:**
1. Use smaller confirmation offset
2. Increase confirmation timeout (default 300s)
3. Position remains open - can place manual orders or wait

---

### Issue 16: STOP_LIMIT Order Rejected

**Symptoms:**
- STOP_LIMIT order fails
- "Invalid stop price" or similar error

**Root Cause:**
E*TRADE has specific requirements for stop orders.

**Solution:**
- Ensure stopPrice is valid (positive number)
- Ensure limitPrice is valid
- For SELL stop: stop price should be below current price
- For BUY stop: stop price should be above current price

---

### Issue 17: Bracket Order Error 1037 (FIXED - Use Trailing Stop)

**Symptoms:**
- Bracket order placed
- STOP LIMIT order placed successfully
- LIMIT order fails with error 1037: "We did not find enough available shares"

**Root Cause:**
E*TRADE doesn't allow placing two sell orders for the same shares simultaneously. When the STOP LIMIT was placed, it reserved the shares, leaving none available for the LIMIT order.

**Solution:**
Use **Trailing Stop** instead of bracket orders. Trailing stop places only ONE exit order (STOP LIMIT), avoiding the share conflict.

**Reference:** v1.5.0 changed from bracket orders to trailing stops for this reason.

---

### Issue 18: Trailing Stop Timeout Despite Fill (FIXED in v1.5.1)

**Symptoms:**
- Order fills immediately
- UI shows "Timeout - Order cancelled (not filled within 15s)"
- Trailing stop never placed
- Position remains open

**Root Cause:**
E*TRADE API sometimes returns 500 errors ("service not currently available") when checking order fill status. The system incorrectly interpreted API errors as "order not filled", causing timeout.

Additionally, when cancel was attempted, error 5001 ("being executed") was returned, which actually means the order WAS filled.

**Solution (v1.5.1):**
1. API 500 errors now return `api_error: true` - doesn't count towards timeout
2. Cancel error 5001 returns `order_likely_filled: true`
3. Frontend re-verifies fill status when error 5001 received
4. Polling interval increased to 1 second for larger orders

---

### Issue 19: Repeated API 500 Errors Causing Rate Limiting

**Symptoms:**
- E*TRADE API returns 500 errors repeatedly
- System polls every second despite errors
- May contribute to rate limiting

**Root Cause:**
System was polling at fixed 1-second intervals even when API was returning errors,
potentially making the rate limiting worse.

**Solution (v1.5.2):**
Implemented exponential backoff:
- Normal polling: 1 second
- First API error: 2 second delay
- Second consecutive error: 4 second delay
- Third: 8 second delay
- Max: 16 second delay
- Resets to 1 second on successful response

This reduces API load during outages and helps avoid rate limiting.

---

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Flask web server, API endpoints, trailing stop logic |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order building |
| `trailing_stop_manager.py` | Trailing stop lifecycle management |
| `bracket_manager.py` | OLD - bracket order (kept for rollback) |
| `token_manager.py` | Redis token storage |
| `config.py` | Credentials and configuration |
| `static/js/app.js` | Frontend logic, fill & trailing stop monitoring |
| `templates/index.html` | Trading UI |
| `VERSION.md` | Current version and features |
| `ETRADE_API_REFERENCE.md` | Complete API documentation |
| `CALLBACK_OAUTH_RESEARCH.md` | OAuth callback research |

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
2. Update VERSION.md if significant changes
3. Commit with descriptive message
4. Push to main branch
5. Railway auto-deploys (~20-30 seconds)
6. Check logs: `railway logs --tail 30`
7. Test functionality

---

## Rollback Procedure

If a fix breaks something:
```bash
cd ~/Projects/etrade

# Rollback to v1.3.3 (before bracket orders)
git checkout <commit-hash>
git push origin main --force

# Available rollback points:
# v1.3.3 - UI polling fix
# v1.3.1 - Type fix for profit orders
# v1.3.0 - Offset-based profit
# v1.2.0 - Profit target version
# v1.1.0 - Basic order placement
```

---

## Session Quick Start

For a new session, read these files first:
1. `VERSION.md` - Current version, features, Railway info
2. `README.md` - System overview
3. `TROUBLESHOOTING.md` (this file)
4. `trailing_stop_manager.py` - If working on trailing stops

### Quick Verification Commands
```bash
# Health check
curl -s https://web-production-9f73cd.up.railway.app/health

# Railway status
railway status

# Recent logs
railway logs --tail 20

# Check for API errors in logs
railway logs --tail 50 | grep -i "api error\|500"

# Check Redis connection in logs
railway logs --tail 50 | grep -i redis
```

---

## Railway Project Info

| Property | Value |
|----------|-------|
| Project Name | E*Trade Trading |
| Project ID | `1419ac9f-57ed-49ee-8ff3-524ac3c52bf8` |
| Service: web | `524166fa-7207-4399-9383-6158a833eb71` |
| Service: Redis-Y5_F | `4f17f8ad-90a8-4fb5-8e66-44bd8fe6a27a` |
| Public URL | https://web-production-9f73cd.up.railway.app |

---

## Pending Items

### 1. E*TRADE Callback URL Registration
**Status:** Waiting on E*TRADE support
**Action:** Contact E*TRADE to register callback URL
**Callback URL:** `https://web-production-9f73cd.up.railway.app/api/auth/callback`
**API Key:** `353ce1949c42c71cec4785343aa36539`

### 2. Server-Side Trailing Stop Monitoring
**Status:** Future enhancement
**Goal:** Move trailing stop monitoring to server-side (survives browser close)
**Implementation:** Background task with Redis state persistence

### 3. E*TRADE API 500 Error Investigation
**Status:** Ongoing issue
**Problem:** E*TRADE API frequently returns 500 errors ("service not currently available")
**Mitigation:** Exponential backoff implemented (v1.5.2)
**Possible causes:** Rate limiting, API instability, account-specific issues

---

## Session History

### 2026-02-20 Session (Late)

**Issues Fixed:**
1. Fixed API error handling in profit target fill checks (v1.5.1)
2. Added exponential backoff for API errors (v1.5.2)
   - 2s, 4s, 8s, 16s max backoff
   - Resets on successful response

**Key Discovery:**
- E*TRADE API returns 500 errors frequently during fill checks
- Error 5001 on cancel means order filled
- Need backoff to avoid rate limiting

### 2026-02-20 Session (Early)

**Issues Fixed:**
1. Replaced bracket orders with trailing stop (bracket failed due to error 1037)
2. Created `trailing_stop_manager.py` - single exit order approach
3. Updated frontend HTML/JS for trailing stop
4. Updated API endpoints from `/api/brackets` to `/api/trailing-stops`

**Key Discovery:**
- E*TRADE doesn't allow two sell orders for the same shares
- Solution: Use single STOP LIMIT order instead of bracket

**New Files Created:**
- `trailing_stop_manager.py` - Trailing stop lifecycle management

**New API Endpoints:**
- `/api/trailing-stops` - Trailing stop management

### 2026-02-19 Session

**Issues Fixed:**
1. Added confirmation-based bracket order feature
2. Added STOP_LIMIT order support
3. Fixed Redis connection (now using Redis-Y5_F)
4. Researched callback OAuth (still not registered)

**New Files Created:**
- `bracket_manager.py` - Bracket order lifecycle management
- `test_callback_oauth.py` - Test script for callback OAuth
- `CALLBACK_OAUTH_RESEARCH.md` - Callback OAuth research documentation

**New API Endpoints:**
- `/api/brackets` - Bracket order management (replaced by trailing stops in v1.5.0)

---

## API Keys

| Environment | Key | Used For |
|-------------|-----|----------|
| Sandbox | `8a18ff810b153dfd5d9ddce27667d63c` | Testing (simulated) |
| Production | `353ce1949c42c71cec4785343aa36539` | Real trading (CURRENT) |
