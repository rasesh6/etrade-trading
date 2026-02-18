# E*TRADE Trading System - Troubleshooting Guide

> **Last Updated:** 2026-02-18
> **Purpose:** Quick reference for debugging issues in future sessions

---

## Quick Diagnostics

### Check System Status
```bash
# Check Railway deployment health
curl -s https://web-production-9f73cd.up.railway.app/health

# Check local server (if running)
curl -s http://localhost:5001/health
```

### Check Recent Logs
Look for deployment markers in Railway logs:
- `FIX4-2026-02-18-PREVIEWIDS-WRAPPER` - Current version

---

## Common Issues & Solutions

### Issue 1: Order Placement Error 101/1033

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

### Issue 2: OAuth Token Expired

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

### Issue 3: Sandbox vs Production

**Sandbox:** `https://apisb.etrade.com` (simulated orders)
**Production:** `https://api.etrade.com` (real orders)

Set via environment variable:
```bash
export ETRADE_USE_SANDBOX=false  # Production
export ETRADE_USE_SANDBOX=true   # Sandbox
```

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
git checkout v1.0.0-working
git push origin main --force
```

---

## Session Quick Start

For a new session, read these files first:
1. `README.md` - System overview
2. `TROUBLESHOOTING.md` (this file)
3. `ETRADE_API_REFERENCE.md` - API details
4. `ORDER_FIX_PLAN.md` - Current fix status
