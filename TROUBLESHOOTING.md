# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-18
> **Current Version:** v1.3.0-auto-profit
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
- `v1.3.0-auto-profit` - Current version

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
1. Set `ETRADE_USE_SANDBOX=false` in Railway environment
2. Railway will redeploy with production API
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
3. In production, market orders typically fill instantly

**Note:** This is expected sandbox behavior. In production, market orders fill immediately during market hours.

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

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Flask web server, API endpoints |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order logic |
| `token_manager.py` | Redis token storage |
| `config.py` | Credentials and configuration |
| `static/js/app.js` | Frontend logic, fill monitoring |
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
2. Update deployment marker in `etrade_client.py`
3. Commit with descriptive message
4. Push to main branch
5. Railway auto-deploys
6. Check logs: `railway logs --tail 30`
7. Test order placement

---

## Rollback Procedure

If a fix breaks something:
```bash
cd ~/Projects/etrade

# Rollback to v1.3.0 (current - offset-based profit)
git checkout 4b4a088
git push origin main --force

# Rollback to v1.2.0 (absolute price profit target)
git checkout dd8831f
git push origin main --force

# Rollback to v1.1.0 (basic order placement)
git checkout fbc4050
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
