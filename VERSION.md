# E*TRADE Trading System - Version History

## Current Version: v1.2.0-profit-target

**Status: FULLY WORKING - Profit Target Feature Added**

**Git Tag:** `v1.2.0-profit-target` (to be created)
**Commit:** `dd8831f`
**Date:** 2026-02-18
**Deployed At:** https://web-production-9f73cd.up.railway.app
**Environment:** SANDBOX (testing mode)

---

## Confirmed Working Features

| Feature | Status | Notes |
|---------|--------|-------|
| OAuth 1.0a Authentication | ✅ WORKING | Sandbox/Production |
| Account List | ✅ WORKING | Shows all accounts |
| Account Balance | ✅ WORKING | Net value, cash, buying power |
| Portfolio Positions | ✅ WORKING | Shows holdings with P&L |
| Market Quotes | ✅ WORKING | Real-time quotes with bid/ask |
| Order Preview | ✅ WORKING | Preview before place |
| Order Placement | ✅ WORKING | FIXED 2026-02-18 |
| Profit Target Orders | ✅ NEW | Auto place profit order on fill |

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.2.0 | 2026-02-18 | ✅ CURRENT | Profit target feature, sandbox mode |
| v1.1.0 | 2026-02-18 | Working | Fixed order placement with PreviewIds wrapper |
| v1.0.0 | 2026-02-15 | Working | OAuth, accounts, quotes working |

---

## v1.2.0 - Profit Target Feature (2026-02-18)

### New Feature: Profit Target Orders

Automatically places a closing limit order when the opening order fills.

**Workflow:**
1. Place BUY/SELL order with profit target price enabled
2. System stores pending profit order (in memory)
3. Click "Check Fills & Place Profit Orders" button
4. System checks executed orders and places profit orders

**UI Components Added:**
- "Add Profit Target" checkbox in order form
- Profit Price input field
- "Pending Profit Orders" section
- "Check Fills & Place Profit Orders" button

**Example:**
```
Opening: BUY 100 AAPL @ Market
Profit Target: $180

After fill → SELL 100 AAPL @ $180 LIMIT is placed
```

### Current Environment: SANDBOX

System is currently in sandbox mode for testing:
- **Sandbox API URL:** `https://apisb.etrade.com`
- **Sandbox accounts are simulated** (not your real accounts)
- Orders are simulated (no real trades)

To switch to production:
1. Go to Railway dashboard
2. Change `ETRADE_USE_SANDBOX` to `false`
3. Railway will redeploy

---

## Key Technical Details

### Order Placement XML Format (CRITICAL)

E*TRADE requires the `<PreviewIds>` wrapper around `<previewId>`:

```xml
<!-- CORRECT Format - Required for order placement -->
<PlaceOrderRequest>
    <PreviewIds><previewId>169280196200</previewId></PreviewIds>
    <orderType>EQ</orderType>
    <clientOrderId>2255377809</clientOrderId>
    <Order>...</Order>
</PlaceOrderRequest>
```

**Note:** The wrapper is `<PreviewIds>` (capital P, capital I, plural), not `<previewId>` directly.

### OAuth Implementation (Working)
```python
# Uses requests-oauthlib (NOT rauth)
from requests_oauthlib import OAuth1

oauth = OAuth1(
    consumer_key,
    client_secret=consumer_secret,
    callback_uri='oob',           # For request token
    signature_method='HMAC-SHA1', # Required by E*TRADE
    signature_type='auth_header',
    realm=''                      # E*TRADE expects empty realm
)
```

### Headers (Working)
```python
headers = {'consumerkey': consumer_key}  # lowercase!
```

### Pending Profit Orders Storage

Currently stored in memory (`_pending_profit_orders` dict in server.py):
- Lost on server restart
- For production, should migrate to Redis

---

## Rollback Instructions

If future changes break the system, rollback:

```bash
# Rollback to v1.2.0 (profit target version)
git checkout dd8831f
git push origin main --force

# Rollback to v1.1.0 (basic order placement)
git checkout fbc4050
git push origin main --force
```

---

## API Keys

| Environment | Key | Used For |
|-------------|-----|----------|
| Sandbox | `8a18ff810b153dfd5d9ddce27667d63c` | Testing (simulated) |
| Production | `353ce1949c42c71cec4785343aa36539` | Real trading |

---

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
