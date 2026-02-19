# E*TRADE Trading System - Version History

## Current Version: v1.3.4-auto-profit

**Status: ✅ WORKING - Full Profit Order Flow Verified**

**Commit:** `2008f54`
**Date:** 2026-02-19
**Deployed At:** https://web-production-9f73cd.up.railway.app
**Environment:** PRODUCTION (real trading)
**Timezone:** All times in **CST (Central Standard Time)** unless otherwise noted

---

## ⭐ WORKING VERSION - DO NOT DELETE

**To restore this working version:**
```bash
git checkout 2008f54
git push origin main --force
```

---

## Confirmed Working Features

| Feature | Status | Notes |
|---------|--------|-------|
| OAuth 1.0a Authentication | ✅ WORKING | Sandbox/Production |
| Account List | ✅ WORKING | Shows all accounts |
| Account Balance | ✅ WORKING | Net value, cash, buying power |
| Portfolio Positions | ✅ WORKING | Shows holdings with P&L |
| Market Quotes | ✅ WORKING | Real quotes in production |
| Order Preview | ✅ WORKING | Preview before place |
| Order Placement | ✅ WORKING | FIXED 2026-02-18 |
| Profit Target (Offset) | ✅ WORKING | $ or % offset from fill price |
| Auto Fill Checking | ✅ WORKING | Polls every 500ms (v1.3.2) |
| Auto Cancel on Timeout | ✅ WORKING | Cancel if not filled within timeout |

---

## v1.3.4 - Fixed KeyError in Profit Order Flow (2026-02-19) ⭐ WORKING

### Bug Fixed:
**KeyError when accessing _pending_profit_orders with string order_id**

**Problem:**
- `order_id` from URL parameter is a string ('54')
- Dictionary keys stored as integers (54)
- `order_id in _pending_profit_orders` always returned False
- KeyError `'54'` when trying to update status after profit order preview

**Result:**
- Order would fill, profit order would be placed successfully
- But UI would show "cancelled" because check-fill crashed with KeyError
- Frontend never received "filled" response

**Solution:**
Use `matching_key` (integer) instead of `order_id` (string) for all dictionary access:
```python
# Find matching key with correct type
matching_key = None
for k in _pending_profit_orders.keys():
    if str(k) == str(order_id):
        matching_key = k
        break

# Use matching_key for all dict operations
_pending_profit_orders[matching_key]['status'] = 'placed'
```

**Fixed in:**
- `check_single_order_fill()`: Lines 729, 742, 753
- `cancel_order()`: Line 547

**Verified Working:**
- Order 56 filled at $63.80
- Profit order placed at $63.84
- UI correctly showed: "✅ Order filled @ $63.80. Profit order placed @ $63.84"

---

## v1.3.3 - Fixed UI Polling Order (2026-02-19)

### Bug Fixed:
**UI showed "Order cancelled" even when profit order was placed successfully**

**Problem:**
The frontend polling logic checked for timeout BEFORE checking for fill. If the order filled at the exact timeout moment, the UI would show "cancelled" even though the backend correctly detected the fill and placed the profit order.

**Solution:**
Reordered the polling logic:
1. First, check if order is filled
2. If filled, show success and stop polling
3. Only if NOT filled, then check if timeout reached
4. If timeout, cancel order

### Changes:
- `static/js/app.js`: Reordered timeout/fill check logic
- `static/js/app.js`: Changed polling interval from 2000ms to 500ms
- `static/js/app.js`: Added decimal formatting for elapsed time (e.g., "3.5/15s")

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.3.4 | 2026-02-19 | ✅ CURRENT | **WORKING** - Fixed KeyError in profit order placement |
| v1.3.3 | 2026-02-19 | Working | Fixed UI polling order (check fill BEFORE timeout), 500ms polling |
| v1.3.2 | 2026-02-18 | Working | Faster fill polling (500ms instead of 2s) |
| v1.3.1 | 2026-02-18 | Working | Fixed order_id type mismatch in check-fill |
| v1.3.0 | 2026-02-18 | Working | Offset-based profit, auto fill checking, PRODUCTION mode |
| v1.2.0 | 2026-02-18 | Working | Profit target feature, sandbox mode |
| v1.1.0 | 2026-02-18 | Working | Fixed order placement with PreviewIds wrapper |
| v1.0.0 | 2026-02-15 | Working | OAuth, accounts, quotes working |

---

## v1.3.2 - Faster Fill Detection (2026-02-18)

### Improvement:
**Reduced fill polling interval from 2s to 500ms**

**Before:**
- Poll every 2 seconds
- 15-second timeout = 7-8 checks
- Average fill detection: ~1 second after actual fill

**After:**
- Poll every 500ms
- 15-second timeout = 30 checks
- Average fill detection: ~0.25 seconds after actual fill

**Changes:**
- `static/js/app.js`: Changed `pollInterval` from 2000 to 500
- Updated elapsed time display to show 1 decimal place (e.g., "3.5/15s")

**Note:** More frequent polling means more API calls. E*TRADE rate limits apply.

---

## v1.3.1 - Type Mismatch Bug Fix (2026-02-18)

### Bug Fixed:
**Order ID type mismatch in check-fill endpoint**

**Problem:**
- Order ID from URL parameter: `"40"` (string)
- Order ID stored in `_pending_profit_orders`: `40` (integer)
- Python `in` check: `"40" in {40: ...}` returns `False`
- Result: Profit orders never placed despite fills happening

**Solution:**
Convert both to strings for comparison before dictionary lookup.

```python
# Fixed code in server.py check_single_order_fill()
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

### Debug Logging Added:
- Log when check-fill is called with account_id and order_id
- Log pending profit orders keys and their types
- Log EXECUTED orders found
- Log each order being checked
- Log when order is found or not found

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

### Production Mode (Enabled 2026-02-18)
- Switched from sandbox to production environment
- Real market quotes for requested symbols
- Real order execution with actual fills
- Production API key: `353ce1949c42c71cec4785343aa36539`

---

## Current Environment: PRODUCTION

System is now in production mode:
- **Production API URL:** `https://api.etrade.com`
- **Real brokerage accounts** shown
- **Real orders** - use with caution!
- Market orders fill instantly during market hours (9:30 AM - 4:00 PM ET)
- **Extended hours**: Must use LIMIT orders (market orders not supported)

To switch back to sandbox:
```bash
railway variables set ETRADE_USE_SANDBOX=true
```

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

### Order ID Types (CRITICAL)

E*TRADE API returns order IDs as **integers**. When comparing:
- URL parameters are **strings**
- Dictionary keys may be **integers**
- Always convert to same type before comparison

```python
# Safe comparison
if str(url_order_id) == str(stored_order_id):
    # match!
```

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
- Keys are integers (from E*TRADE API response)
- For production, should migrate to Redis

---

## Railway CLI Access (Configured 2026-02-18)

Railway CLI is configured and working. Useful commands:

```bash
# Check service status
railway status

# View recent logs
railway logs --tail 50

# View all environment variables
railway variables

# Check auth status
railway whoami
```

**Project Info:**
- Project ID: `1419ac9f-57ed-49ee-8ff3-524ac3c52bf8`
- Service ID: `524166fa-7207-4399-9383-6158a833eb71`
- Service Name: `web`

---

## Rollback Instructions

If future changes break the system, rollback:

```bash
cd ~/Projects/etrade

# Rollback to v1.3.1 (type fix for profit orders)
git checkout 5e76a12
git push origin main --force

# Rollback to v1.3.0 (offset-based profit)
git checkout 4b4a088
git push origin main --force

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
| Production | `353ce1949c42c71cec4785343aa36539` | Real trading (CURRENT) |

---

## Known Limitations

1. **Extended Hours Trading**: Market orders not supported - must use LIMIT orders
2. **Pending Profit Orders**: Stored in memory, lost on server restart
3. **Fill Monitoring**: Frontend-based, stops if browser is closed

---

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
