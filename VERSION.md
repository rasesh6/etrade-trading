# E*TRADE Trading System - Version History

## Current Version: v1.3.0-auto-profit

**Status: WORKING - Auto Fill Checking & Offset-Based Profit Targets**

**Git Tag:** `v1.3.0-auto-profit` (to be created)
**Commit:** `4b4a088`
**Date:** 2026-02-18
**Deployed At:** https://web-production-9f73cd.up.railway.app
**Environment:** PRODUCTION (real trading)

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
| Profit Target (Offset) | ✅ NEW | $ or % offset from fill price |
| Auto Fill Checking | ✅ NEW | Polls every 2s, cancels if timeout |
| Auto Cancel on Timeout | ✅ NEW | Cancel if not filled within timeout |

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.3.0 | 2026-02-18 | ✅ CURRENT | Offset-based profit, auto fill checking, auto-cancel, PRODUCTION mode |
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
- Market orders fill instantly during market hours

To switch back to sandbox:
1. `railway variables set ETRADE_USE_SANDBOX=true`
2. Or via Railway dashboard

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

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
