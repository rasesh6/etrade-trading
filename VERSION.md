# E*TRADE Trading System - Version History

## Current Version: v1.5.1-api-error-handling

**Status: WORKING - Improved API Error Handling**
**Commit:** (pending)
**Date:** 2026-02-20
**Deployed At:** https://web-production-9f73cd.up.railway.app
**Environment:** PRODUCTION (real trading)
**Timezone:** All times in **CST (Central Standard Time)** unless otherwise noted

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
| Auto Fill Checking | ✅ WORKING | Polls every 1 second |
| Auto Cancel on Timeout | ✅ WORKING | Cancel if not filled within timeout |
| STOP_LIMIT Orders | ✅ WORKING | Stop price + limit price |
| **Trailing Stop** | ✅ WORKING | v1.5.0 - Confirmation-based with guaranteed profit |
| **API Error Handling** | ✅ NEW | v1.5.1 - Handles E*TRADE 500 errors gracefully |
| Redis Token Storage | ✅ WORKING | Using Redis-Y5_F service |

---

## v1.5.1 - API Error Handling Fix (2026-02-20)

### Problem:
E*TRADE API sometimes returns 500 errors ("service not currently available") during fill checks. This caused:
1. Fill check to fail repeatedly
2. Frontend timeout triggered after 15 seconds
3. Cancel attempted but got error 5001 ("being executed")
4. Error 5001 actually means order WAS filled
5. Trailing stop never placed

### Solution:
1. **Server-side**: When E*TRADE API returns 500 error, return `api_error: true` flag
2. **Frontend**: Don't count API errors towards fill timeout
3. **Cancel endpoint**: Detect error 5001 and return `order_likely_filled: true`
4. **Frontend**: When cancel returns 5001, re-verify fill status

### Changes:
- `server.py`: Updated `check_trailing_stop_fill` to handle API errors
- `server.py`: Updated `cancel_order` to detect error 5001
- `app.js`: Handle `api_error` flag in trailing stop monitoring
- `app.js`: Handle error 5001 and re-verify fill status
- `app.js`: Polling interval changed to 1 second for all monitoring

---

## v1.5.0 - Trailing Stop Feature (2026-02-20)

### Background:
v1.4.0 bracket orders failed because E*TRADE doesn't allow placing two sell orders for the same shares (error 1037). The STOP LIMIT order reserves the shares, leaving none available for the LIMIT order.

### Solution:
Simplified to a **single exit order** - trailing stop:
1. Wait for fill
2. Wait for price to rise by trigger offset
3. Place STOP LIMIT order at trigger - stop offset
4. Since stop is above fill price = **guaranteed profit**

### New Features:

1. **Confirmation-Based Trailing Stop**
   - Wait for price to move UP by trigger amount from fill
   - Place STOP LIMIT order below trigger (but above fill = profit)
   - Single exit order - no share conflict
   - Guaranteed profit when stop fills

2. **Configuration Options**
   - **Upper Trigger ($)**: How much price must rise before placing stop
   - **Stop Offset ($)**: How far below trigger to place stop
   - Fill timeout: Time to wait for order fill
   - Confirmation timeout: Time to wait for price trigger

### New Files:
- `trailing_stop_manager.py` - Trailing stop lifecycle management

### New API Endpoints:
- `GET /api/trailing-stops` - List all active trailing stops
- `GET /api/trailing-stops/<opening_order_id>` - Get trailing stop status
- `GET /api/trailing-stops/<opening_order_id>/check-fill` - Check if opening filled
- `GET /api/trailing-stops/<opening_order_id>/check-confirmation` - Check price confirmation
- `GET /api/trailing-stops/<opening_order_id>/check-stop` - Check stop order fill
- `POST /api/trailing-stops/<opening_order_id>/cancel` - Cancel trailing stop

### Trailing Stop Flow:
```
1. Place BUY order with trailing stop enabled
2. Wait for fill (get fill_price)
3. Calculate trigger_price = fill_price + trigger_offset
4. Monitor price, wait for current_price >= trigger_price
5. When triggered:
   - Calculate stop_price = trigger_price - stop_offset
   - Place STOP LIMIT SELL @ stop_price
6. Monitor stop order
7. When stop fills = guaranteed profit!
```

### Example:
```
BUY @ $100 (fill)
Trigger offset = $2 (wait for $102)
Stop offset = $1 (place stop at $101)

When price hits $102:
- Place STOP LIMIT @ $101 (stop), $100.99 (limit)
- Min guaranteed profit = $101 - $100 = $1/share
```

### UI Changes:
- Replaced bracket order section with trailing stop section
- Upper Trigger: $ or % offset from fill
- Stop Offset: $ or % below trigger
- Fill timeout and confirmation timeout settings
- Real-time trailing stop status monitoring

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.5.0 | 2026-02-20 | ✅ CURRENT | Trailing stop (single exit order, guaranteed profit) |
| v1.4.0 | 2026-02-19 | ❌ FAILED | Bracket orders failed (error 1037 - two sell orders not allowed) |
| v1.3.3 | 2026-02-19 | Working | Fixed UI polling order (check fill BEFORE timeout) |
| v1.3.2 | 2026-02-18 | Working | Faster fill polling (500ms) |
| v1.3.1 | 2026-02-18 | Working | Fixed order_id type mismatch |
| v1.3.0 | 2026-02-18 | Working | Offset-based profit, auto fill checking, PRODUCTION mode |
| v1.2.0 | 2026-02-18 | Working | Profit target feature, sandbox mode |
| v1.1.0 | 2026-02-18 | Working | Fixed order placement with PreviewIds wrapper |
| v1.0.0 | 2026-02-15 | Working | OAuth, accounts, quotes working |

---

## Key Technical Details

### Order Placement XML Format (CRITICAL)

E*TRADE requires the `<PreviewIds>` wrapper around `<previewId>`:

```xml
<PlaceOrderRequest>
    <PreviewIds><previewId>169280196200</previewId></PreviewIds>
    <orderType>EQ</orderType>
    ...
</PlaceOrderRequest>
```

### STOP_LIMIT Order XML Format

```xml
<Order>
    <priceType>STOP_LIMIT</priceType>
    <stopPrice>175.75</stopPrice>
    <limitPrice>175.74</limitPrice>
    ...
</Order>
```

### Order ID Types (CRITICAL)

E*TRADE API returns order IDs as **integers**. URL parameters are **strings**.
Always convert to same type before comparison.

### Trailing Stop Data Structure

```python
PendingTrailingStop:
    opening_order_id: int
    symbol: str
    quantity: int
    fill_price: float
    trigger_price: float  # Price at which stop is placed
    stop_order_id: int    # STOP LIMIT order ID
    stop_price: float     # Stop trigger price
    stop_limit_price: float  # Stop limit price
    state: TrailingStopState  # pending_fill, waiting_confirmation, stop_placed, etc.
```

---

## Railway Services

| Service | Purpose | Status |
|---------|---------|--------|
| web | Flask application | Running |
| Redis-Y5_F | Token & trailing stop storage | Running |

### Railway CLI Commands

```bash
# Check status
railway status

# View logs
railway logs --tail 50

# View variables
railway variables
```

---

## Redis Configuration

**Current Redis Service:** Redis-Y5_F
**REDIS_URL:** `${{Redis-Y5_F.REDIS_URL}}`
**Internal Hostname:** `redis-y5f.railway.internal:6379`

---

## Known Limitations

1. **Extended Hours Trading**: Market orders not supported - must use LIMIT orders
2. **Callback OAuth**: NOT registered - using manual verification code flow
3. **Trailing Stop Monitoring**: Frontend-based, stops if browser is closed
4. **Confirmation Timeout**: If price doesn't reach trigger, position remains open
5. **No OCO Orders**: E*TRADE API doesn't support One-Cancels-Other orders

---

## Callback OAuth Status

**Status:** NOT REGISTERED

E*TRADE has not activated the callback URL. Test with:
```bash
ETRADE_USE_SANDBOX=false python test_callback_oauth.py
```

See `CALLBACK_OAUTH_RESEARCH.md` for details.

---

## Rollback Instructions

```bash
cd ~/Projects/etrade

# Rollback to v1.4.0-bracket-orders (bracket order feature)
git checkout v1.4.0-bracket-orders
git push origin main --force

# Rollback to v1.3.3 (before bracket orders)
git checkout 3eaa205
git push origin main --force
```

---

## API Keys

| Environment | Key | Used For |
|-------------|-----|----------|
| Sandbox | `8a18ff810b153dfd5d9ddce27667d63c` | Testing (simulated) |
| Production | `353ce1949c42c71cec4785343aa36539` | Real trading (CURRENT) |

---

## File Structure

```
etrade/
├── server.py                 # Flask web server, API endpoints
├── etrade_client.py          # E*TRADE API wrapper, OAuth, orders
├── trailing_stop_manager.py  # Trailing stop lifecycle management (NEW)
├── bracket_manager.py        # OLD - bracket order (kept for rollback)
├── token_manager.py          # OAuth token storage (Redis)
├── config.py                 # Credentials and configuration
├── static/
│   ├── css/style.css         # Styles
│   └── js/app.js             # Application logic
├── templates/
│   └── index.html            # Trading UI
├── requirements.txt          # Python dependencies
├── VERSION.md                # This file
├── README.md                 # System overview
├── TROUBLESHOOTING.md        # Debug guide
├── ETRADE_API_REFERENCE.md   # API documentation
├── CALLBACK_OAUTH_RESEARCH.md # OAuth callback research
├── CALLBACK_URL_STATUS.md    # Callback registration status
└── test_callback_oauth.py    # Test script for callback OAuth
```

---

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
