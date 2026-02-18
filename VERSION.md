# E*TRADE Trading System - Version History

## Current Version: v1.3.0-auto-profit

**Status: WORKING - Auto Fill Checking & Offset-Based Profit Targets**

**Git Tag:** `v1.3.0-auto-profit` (to be created)
**Commit:** `4b4a088`
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
| Market Quotes | ✅ WORKING | Note: Sandbox returns GOOG for all symbols |
| Order Preview | ✅ WORKING | Preview before place |
| Order Placement | ✅ WORKING | FIXED 2026-02-18 |
| Profit Target (Offset) | ✅ NEW | $ or % offset from fill price |
| Auto Fill Checking | ✅ NEW | Polls every 2s, cancels if timeout |
| Auto Cancel on Timeout | ✅ NEW | Cancel if not filled within timeout |

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.3.0 | 2026-02-18 | ✅ CURRENT | Offset-based profit, auto fill checking, auto-cancel |
| v1.2.0 | 2026-02-18 | Working | Profit target feature, sandbox mode |
| v1.1.0 | 2026-02-18 | Working | Fixed order placement with PreviewIds wrapper |
| v1.0.0 | 2026-02-15 | Working | OAuth, accounts, quotes working |

---

## v1.3.0 - Offset-Based Profit Target & Auto Fill Checking (2026-02-18)

### New Features:

1. **Offset-Based Profit Target**
   - Specify profit as $ offset (e.g., +$5 from fill price)
   - Or as % offset (e.g., +5% from fill price)
   - Profit price calculated from actual fill price

2. **Automatic Fill Checking**
   - Frontend polls every 2 seconds after order placement
   - No manual "Check Fills" button needed
   - Real-time order status display

3. **Auto-Cancel on Timeout**
   - If order not filled within timeout (default 15s), auto-cancel
   - Prevents stale orders sitting unfilled

4. **Quote Display Fix**
   - UI now shows requested symbol, not returned symbol
   - Sandbox API returns GOOG for all symbols (known limitation)

### UI Changes:
- Removed manual "Check Fills & Place Profit Orders" button
- Added "Order Status" card for real-time monitoring
- Profit target input changed from price to offset type + offset value
- Added "Fill Timeout" field (default 15 seconds)

### Example Workflow:
```
1. Place BUY 1 AAPL @ Market
2. Enable Profit Target: $1.00 offset, 15s timeout
3. Order placed, monitoring starts
4. If filled @ $175 within 15s:
   - Profit order placed: SELL 1 AAPL @ $176 LIMIT
5. If NOT filled within 15s:
   - Order cancelled automatically
```

---

## Previous: v1.2.0 - Profit Target Feature (2026-02-18)

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
