# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-18
> **Current Version:** v1.2.0-profit-target
> **Purpose:** Quick reference for debugging issues in future sessions

---

## Quick Diagnostics

### Check System Status
```bash
# Check Railway deployment health
curl -s https://web-production-9f73cd.up.railway.app/health

# Check local server (if running)
curl -s http://localhost:5000/health
```

### Check Recent Logs
Look for deployment markers in Railway logs:
- `FIX4-2026-02-18-PREVIEWIDS-WRAPPER` - Order placement fix

---

## Common Issues & Solutions

### Issue 1: Sandbox Shows Wrong Accounts

**Symptoms:**
- See accounts like "NickName-1", "NickName-2" instead of your real accounts
- Positions in BR, GLD, MSFT, etc. that you don't own

**Root Cause:**
E*TRADE Sandbox uses simulated test accounts, not your real brokerage accounts.

**Solution:**
This is expected behavior. Sandbox is for testing only. To see real accounts:
1. Set `ETRADE_USE_SANDBOX=false` in Railway environment
2. Railway will redeploy with production API

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

Set via environment variable:
```bash
export ETRADE_USE_SANDBOX=false  # Production
export ETRADE_USE_SANDBOX=true   # Sandbox
```

---

### Issue 5: Quote Shows Wrong Symbol (GOOG)

**Symptoms:**
- Request quote for SOXL, AAPL, etc.
- UI shows GOOG with Google Inc data

**Root Cause:**
E*TRADE Sandbox API returns old test data (GOOG from 2012) for any symbol requested.

**Solution:**
This is expected sandbox behavior. The UI now displays the requested symbol, not the returned symbol. The quote data (bid/ask/last) is still simulated sandbox data.

For real quotes, switch to production mode by setting `ETRADE_USE_SANDBOX=false`.

---

### Issue 6: Profit Order Not Placed / Timeout

**Symptoms:**
- Order placed with profit target
- No profit order created
- Order cancelled after timeout

**Root Cause:**
- Opening order not filled within timeout period
- Sandbox orders may not fill immediately (or at all)

**Solution:**
1. Check the Order Status card for real-time status
2. Increase timeout if needed (default 15s)
3. Sandbox market orders may not fill - this is a sandbox limitation

**Note:** In production, market orders typically fill instantly during market hours.

---

### Issue 7: Fill Price Shows as 0

**Symptoms:**
- Order filled but profit order has strange price
- Fill price reported as 0 or missing

**Root Cause:**
E*TRADE API may not always include `executedPrice` in order details.

**Solution:**
The system defaults to 0 if fill price unavailable. In sandbox, this is common. In production, fill prices are typically available.

---

## Key Files

| File | Purpose |
|------|---------|
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order logic |
| `server.py` | Flask web server, API endpoints |
| `token_manager.py` | Redis token storage |
| `config.py` | Credentials and configuration |
| `ETRADE_API_REFERENCE.md` | Complete API documentation |
| `ORDER_FIX_PLAN.md` | Order placement fix history |

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
6. Check logs for new deployment marker
7. Test order placement

---

## Rollback Procedure

If a fix breaks something:
```bash
cd ~/Projects/etrade

# Rollback to v1.2.0 (profit target version)
git checkout dd8831f
git push origin main --force

# Rollback to v1.1.0 (basic order placement)
git checkout fbc4050
git push origin main --force
```

---

## Session Quick Start

For a new session, read these files first:
1. `VERSION.md` - Current version and features
2. `README.md` - System overview
3. `TROUBLESHOOTING.md` (this file)
4. `ETRADE_API_REFERENCE.md` - API details
