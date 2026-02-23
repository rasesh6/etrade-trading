# E*TRADE Trading System - Version History

## Current Version: v1.6.0

**Status: WORKING - Premium UI Design**
**Commit:** (pending)
**Date:** 2026-02-23
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
| **Confirmation Stop Limit** | ✅ WORKING | v1.5.0 - Confirmation-based with guaranteed profit |
| **Trailing Stop Limit ($)** | ✅ WORKING | v1.5.9 - TRAILING_STOP_CNST with trigger + limit |
| **Exit Strategy Dropdown** | ✅ WORKING | v1.5.7 - None, Profit Target, Confirmation Stop Limit, Trailing Stop Limit |
| **Robust Fill Detection** | ✅ WORKING | v1.6.0 - API errors don't count toward timeout |
| **API Error Handling** | ✅ WORKING | v1.5.1 - Handles E*TRADE 500 errors gracefully |
| **Premium UI** | ✅ WORKING | v1.5.4 - Terminal Luxe design |
| Redis Token Storage | ✅ WORKING | Using Redis-Y5_F service |

---

## v1.6.0 - Robust Fill Detection (2026-02-23)

### Fixes:
1. **API errors no longer count toward timeout** - If the E*TRADE API returns an error or times out, the monitoring keeps retrying without incrementing the timeout counter

2. **Fill check happens BEFORE timeout check** - Previously, the elapsed counter was incremented before the API call, causing race conditions

3. **Added debug logging** - Console logs for all fill/trigger checks to help diagnose issues

4. **Improved error 5001 handling** - When cancel returns "being executed", re-check fill status instead of giving up

### Monitoring Logic (All Order Types):
```
1. Make API call to check fill/trigger
2. If API error → retry without counting toward timeout
3. If filled/triggered → transition to next state
4. Increment elapsed counter
5. Update status display
6. Check if timeout reached
7. If timeout → attempt cancel (with 5001 recheck)
```

### Files Changed:
- `static/js/app.js` - All three monitoring functions refactored
- `server.py` - Added debug logging for fill detection

---

## v1.5.9 - Trailing Stop Limit with Trigger (2026-02-23)

### Fix:
Added trigger offset to Trailing Stop Limit - now works like Confirmation Stop Limit:
1. Wait for fill
2. Wait for price to reach trigger (fill_price + trigger_offset)
3. THEN place TRAILING_STOP_CNST LIMIT order

### UI Updates:
- Added Trigger field ($ or % offset from fill)
- Added Trail field ($ or % trailing amount)
- Added Trigger Timeout setting

### Flow:
```
1. Place BUY order with Trailing Stop Limit enabled
2. Wait for fill (get fill_price)
3. Calculate trigger_price = fill_price + trigger_offset
4. Monitor price, wait for current_price >= trigger_price
5. When triggered:
   - Place TRAILING_STOP_CNST LIMIT order with specified trail amount
   - E*TRADE manages the trailing automatically
```

### Files Changed:
- `templates/index.html` - Added trigger/trail fields to UI
- `static/js/app.js` - Updated monitoring with trigger phase
- `server.py` - Added check-trigger endpoint, trigger logic

---

## v1.5.8 - Trailing Stop Limit Implementation (2026-02-23)

### New Feature:
**Trailing Stop Limit ($)** - A true trailing stop that follows price by a fixed dollar amount.

### How it works:
1. Place BUY order with Trailing Stop Limit enabled
2. Wait for order to fill
3. Place TRAILING_STOP_CNST LIMIT order that trails price by specified amount
4. E*TRADE manages the trailing automatically

### Order Type: TRAILING_STOP_CNST
- `stopPrice` = trail amount (how far behind price to trail)
- `stopLimitPrice` = limit offset from stop ($0.01 for limit execution)

### UI Changes:
- Renamed "Confirmation Stop" to "Confirmation Stop Limit" for clarity
- Enabled "Trailing Stop Limit ($)" option in dropdown

### Files Changed:
- `templates/index.html` - Enabled trailing stop limit option
- `static/js/app.js` - Added startTrailingStopLimitMonitoring()
- `server.py` - Added /api/trailing-stop-limit endpoints
- `etrade_client.py` - Added TRAILING_STOP_CNST support with stopLimitPrice

---

## v1.5.7 - Exit Strategy Dropdown (2026-02-23)

### Changes:
1. **Replaced two checkboxes with single dropdown** for exit strategy:
   - None (default)
   - Profit Target - place LIMIT sell at fill + offset
   - Confirmation Stop - wait for trigger, then place STOP LIMIT
   - Trailing Stop ($) - coming soon (disabled in dropdown)

2. **Added strategy descriptions** to explain each option

3. **Fixed orders list not refreshing after confirmation stop placed**

### Files Changed:
- `templates/index.html` - New dropdown UI with strategy descriptions
- `static/js/app.js` - toggleExitStrategy() function, updated placeOrder()
- `static/css/style-luxe.css` - Strategy description styles

---

## v1.5.6 - UI Rename & Orders Refresh Fix (2026-02-23)

### Changes:
1. **Renamed "Trailing Stop" to "Confirmation Stop"** in UI labels
   - This is a confirmation-based fixed stop, not a true trailing stop
   - STOP_LIMIT order with limit $0.01 below stop price
2. **Fixed orders list not refreshing after confirmation stop placed**
   - Added `loadOrders()` call after stop is placed

### Files Changed:
- `templates/index.html` - Renamed "Trailing Stop" to "Confirmation Stop"
- `static/js/app.js` - Updated status labels, added loadOrders() after stop placed
- `trailing_stop_manager.py` - Updated docstrings

---

## v1.5.5 - Fill Detection Fix (2026-02-23)

### Problem:
Orders were filling quickly (within 2 seconds) but the system wasn't detecting fills
for 30+ seconds, causing trailing stops to never be placed.

### Root Cause Analysis:
1. Orders list refresh wasn't being called after fill detection
2. Error 5001 handling gave up too quickly
3. **Main issue**: Check-fill was only looking at EXECUTED status, but E*TRADE may
   not immediately update order status. Also, checking OPEN orders with filledQuantity > 0
   had a partial fill problem.

### Solution:
1. Added `loadOrders()` after fill detection
2. Extended polling for 30 seconds after error 5001
3. **Key fix**: Fetch orders WITHOUT status filter (gets all recent orders), then:
   - Find the order by ID
   - Check if `filledQuantity >= orderedQuantity` (FULL fill only, not partial)
   - This works regardless of whether E*TRADE has updated the status field yet

### Files Changed:
- `static/js/app.js` - Persistent fill checking after error 5001
- `server.py` - check_trailing_stop_fill() and check_single_order_fill(): Fetch all orders, check for full fills
- `etrade_client.py` - get_orders(): Handle status=None to fetch all orders

### Partial Fill Handling:
Only triggers confirmation stop/profit order when `filledQuantity >= orderedQuantity` (full fill).

---

## v1.5.4 - Terminal Luxe UI (2026-02-21)

### New Feature:
Premium "Terminal Luxe" trading interface with professional design.

### Design Aesthetic:
Bloomberg terminal precision meets luxury watch craftsmanship.

### Key Design Elements:
- **Typography:** JetBrains Mono (monospace) + Outfit (sans-serif)
- **Color Palette:** Obsidian dark theme with gold accents
- **Trading Colors:** Refined bull (green) and bear (red) indicators
- **Visual Effects:** Subtle noise texture, animations, micro-interactions
- **Components:** Cards with hover effects, staggered animations on load

### Files:
- `static/css/style-luxe.css` - New premium stylesheet
- Original `style.css` preserved as backup

---

## v1.5.3 - Fixed Exponential Backoff (2026-02-20)

### Problem:
v1.5.2's exponential backoff was broken - API calls were still happening every ~300-500ms.

### Root Cause:
The old code called `checkFill()` immediately without any delay:
```javascript
// BROKEN - first call happens immediately
checkFill();

async function checkFill() {
    setTimeout(async () => {
        // ... check logic ...
        checkFill(); // only subsequent calls are delayed
    }, waitTime);
}
```

### Solution:
New pattern using `scheduleNextCheck()`:
```javascript
// FIXED - always wait before API call
function scheduleNextCheck() {
    fillCheckInterval = setTimeout(doCheckFill, waitTime);
}

function doCheckFill() {
    // ... check logic ...
    scheduleNextCheck(); // schedule next with proper delay
}

scheduleNextCheck(); // start - waits 1s before first check
```

This ensures proper delays between ALL API calls, including the first one.

---

## v1.5.2 - Exponential Backoff (2026-02-20)

### Problem:
E*TRADE API was returning repeated 500 errors. The system was polling every 1 second
even during API outages, which may have contributed to rate limiting issues.

### Solution:
Implemented exponential backoff for API error handling:
- Normal polling: 1 second
- First API error: 2 second delay
- Second consecutive error: 4 second delay
- Third: 8 second delay
- Max: 16 second delay
- Resets to 1 second on successful response

### Changes:
- `app.js`: Rewrote `startOrderMonitoring` with exponential backoff
- `app.js`: Rewrote `startTrailingStopMonitoring` with exponential backoff
- Both use setTimeout recursively instead of setInterval for variable delays

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
| v1.6.0 | 2026-02-23 | ✅ CURRENT | Robust fill detection - API errors don't count toward timeout |
| v1.5.9 | 2026-02-23 | Working | Trailing Stop Limit with trigger offset |
| v1.5.8 | 2026-02-23 | Working | Trailing Stop Limit ($), renamed to Confirmation Stop Limit |
| v1.5.7 | 2026-02-23 | Working | Exit strategy dropdown |
| v1.5.6 | 2026-02-23 | Working | Renamed to Confirmation Stop, fixed orders refresh |
| v1.5.5 | 2026-02-23 | Working | Fixed confirmation stop fill not refreshing orders list |
| v1.5.4 | 2026-02-21 | Working | Premium Terminal Luxe UI design |
| v1.5.3 | 2026-02-20 | Working | Fixed exponential backoff implementation |
| v1.5.2 | 2026-02-20 | ❌ BUG | Exponential backoff (broken - first call immediate) |
| v1.5.1 | 2026-02-20 | Working | API error handling, cancel 5001 detection |
| v1.5.0 | 2026-02-20 | Working | Confirmation stop (single exit order, guaranteed profit) |
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
6. **E*TRADE Orders API**: Frequently returns 500 errors - may be rate limiting or API instability

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
│   ├── css/style.css         # Styles (original)
│   ├── css/style-luxe.css    # Premium Terminal Luxe design (CURRENT)
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
