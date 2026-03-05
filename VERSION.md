# E*TRADE Trading System - Version History

## Current Version: v1.7.1

**Status: WORKING - Server-Side Monitoring + Live Quotes**
**Date:** 2026-03-05
**Deployed At:** https://web-production-9f73cd.up.railway.app
**Environment:** PRODUCTION (real trading)
**Timezone:** All times in **CST (Central Standard Time)** unless otherwise noted

---

## Confirmed Working Features

| Feature | Status | Notes |
|---------|--------|-------|
| OAuth 1.0a Authentication | ✅ WORKING | Callback-based flow via Railway |
| Account List | ✅ WORKING | Shows all accounts |
| Account Balance | ✅ WORKING | Net value, cash, buying power |
| Portfolio Positions | ✅ WORKING | Shows holdings with P&L |
| Market Quotes | ✅ WORKING | Real NBBO quotes in production |
| **Live Quote Streaming** | ✅ WORKING | v1.7.0 - Watch button, SSE push every 3s |
| Order Preview | ✅ WORKING | Preview before place |
| Order Placement | ✅ WORKING | FIXED 2026-02-18 |
| Profit Target (Offset) | ✅ WORKING | $ or % offset from fill price |
| **Server-Side Fill Monitoring** | ✅ WORKING | v1.7.0 - Survives browser close |
| Auto Cancel on Timeout | ✅ WORKING | Cancel if not filled within timeout |
| STOP_LIMIT Orders | ✅ WORKING | Stop price + limit price |
| **Confirmation Stop Limit** | ✅ WORKING | v1.5.0 - Confirmation-based with guaranteed profit |
| **Trailing Stop Limit ($)** | ✅ WORKING | v1.7.1 - TRAILING_STOP_CNST + configurable limit offset |
| **Exit Strategy Dropdown** | ✅ WORKING | v1.5.7 - None, Profit Target, Confirmation Stop, TSL |
| **SSE Real-Time Updates** | ✅ WORKING | v1.7.0 - Push events replace browser polling |
| **Gevent Concurrent Worker** | ✅ WORKING | v1.7.0 - via gunicorn.conf.py |
| **API Error Handling** | ✅ WORKING | User-friendly messages, server-side logging |
| **Premium UI** | ✅ WORKING | v1.5.4 - Terminal Luxe design |
| Redis Token Storage | ✅ WORKING | Using Redis-Y5_F service |

---

## E*TRADE Fill Detection Structure

**IMPORTANT:** E*TRADE API returns fill quantities at the **Instrument** level, not OrderDetail level:

```
Order
└── OrderDetail[]
    └── Instrument[]           ← filledQuantity and orderedQuantity are HERE
        ├── filledQuantity
        ├── orderedQuantity
        └── averageExecutionPrice
```

All fill detection code must iterate through `OrderDetail[].Instrument[]` to check fill status.

---

## v1.7.1 - TSL Limit Offset + Cancel Reliability (2026-03-05)

### Trailing Stop Limit Improvements:

**Configurable Limit Offset (`stopLimitPrice`)**
- The TSL order uses `TRAILING_STOP_CNST` + `stopLimitPrice` (trailing stop LIMIT, not market)
- `stopPrice` = trail amount (how far stop trails behind peak price)
- `stopLimitPrice` = limit offset (max slippage from stop trigger price)
- Was hardcoded to $0.01; now configurable via "Limit Offset" field in UI
- Default: $0.01 (tightest execution)

**TSL API-Error Timeout Cancel Fix**
- When E*TRADE API returned 500 errors throughout the entire fill timeout, the monitor
  emitted a timeout message and broke **without cancelling the order**
- Now both timeout paths (normal and API-error) call `_cancel_and_recheck()`
- If the order filled during cancel attempt, transitions to trigger-waiting phase

### Cancel Reliability (All Monitor Types):

Comprehensive review of timeout/cancel flow across all three monitor types:

| Monitor | Normal timeout | API-error timeout | Frontend refresh |
|---------|---------------|-------------------|-----------------|
| Profit target | ✅ cancels, timeout→cancelled events | ✅ loop exits, cancels | ✅ 2s delay |
| Confirmation stop | ✅ cancels via _cancel_and_recheck | ✅ retries (no elapsed increment) | ✅ 2s delay (NEW) |
| TSL | ✅ cancels via _cancel_and_recheck | ✅ **NOW cancels** (was broken) | ✅ 2s delay (NEW) |

### Files Changed:
- `order_monitor.py` - TSL API-error timeout now cancels; configurable limit_offset
- `server.py` - Pass tsl_limit_offset from frontend to monitor config
- `static/js/app.js` - Read limit offset field; 2s delay on ts_timeout/tsl_timeout refresh
- `templates/index.html` - New "Limit Offset" field for TSL

---

## v1.7.0 - Server-Side Monitoring + SSE + Live Quotes (2026-03-05)

### Major Changes:

**1. Server-Side Order Monitoring (`order_monitor.py`)**
- Background threads monitor order fills and place exit orders server-side
- Survives browser close - no longer dependent on frontend polling
- `OrderMonitor` singleton class with thread-safe SSE event distribution
- Monitors: profit targets, confirmation stops, trailing stop limits
- Helper methods: `_check_order_filled()`, `_calc_profit_price()`, `_place_exit_limit_order()`

**2. Server-Sent Events (SSE)**
- `GET /api/events` - long-lived SSE endpoint for real-time push updates
- Events: quote updates, fill notifications, status messages, cancel confirmations
- Frontend `connectSSE()` / `disconnectSSE()` manages EventSource lifecycle
- SSE connects on demand (during monitoring or quote watch), not on page load

**3. Live Quote Streaming**
- "Watch" button in quote panel starts polling E*TRADE every 3s
- NBBO bid/ask/last/volume pushed to frontend via SSE
- Idempotent: re-clicking Watch for same symbol is a no-op (prevents thread churn)
- Symbol change auto-stops current watch
- `POST /api/quote/SYMBOL/watch` and `DELETE /api/quote/watch` endpoints

**4. OAuth Callback Flow Fix**
- E*TRADE now redirects to callback URL instead of showing OOB code page
- Request tokens stored in Redis for cross-process callback lookup
- Token URL-encoded in authorize URL (contains `/`, `+`, `=`)
- `GET /api/auth/callback` handles the redirect automatically

**5. Gunicorn Gevent Worker**
- `gunicorn.conf.py` config file (CLI flags were ignored by Railway)
- `worker_class = "gevent"` for concurrent SSE + HTTP connections
- Single worker (`workers = 1`) for singleton OrderMonitor
- Matches pattern from working Alpaca project

**6. UI/UX Fixes**
- Cancel status: `timeout` event keeps SSE open, waits for `cancelled` event
- Orders refresh delayed 2s after cancel (lets E*TRADE process)
- API errors shown as "Waiting for fill..." not "API error, retrying..."

### New Files:
- `order_monitor.py` - Server-side order monitoring + quote streaming
- `gunicorn.conf.py` - Gunicorn configuration (gevent, single worker)
- `nixpacks.toml` - Railway build config
- `test_streaming.py` - CometD/Bayeux feasibility test (confirmed dead)

### New/Modified API Endpoints:
- `GET /api/events` - SSE endpoint for real-time events
- `POST /api/quote/<symbol>/watch` - Start live quote streaming
- `DELETE /api/quote/watch` - Stop live quote streaming
- `GET /api/auth/callback` - OAuth callback handler

### Files Changed:
- `server.py` - SSE endpoint, quote watch endpoints, callback auth, monitor wiring
- `etrade_client.py` - URL-encoded token in authorize URL
- `static/js/app.js` - SSE client, Watch button, replaced polling with SSE events
- `templates/index.html` - Added Watch button
- `static/css/style-luxe.css` - Added `.btn-active` style
- `Procfile` - Simplified to use gunicorn.conf.py
- `requirements.txt` - Added gevent, aiocometd, aiohttp

### E*TRADE Streaming API Investigation:
- Tested CometD/Bayeux protocol against 6 E*TRADE endpoints
- All returned 400 (Bad Request) or DNS failures
- Conclusion: E*TRADE streaming API is dead/deprecated
- Implemented Plan B: server-side REST polling + SSE push

---

## v1.6.2 - UI Readability & Fill Detection Consistency (2026-02-23)

### UI Improvements:
- Increased label text brightness (tertiary → secondary color)
- Increased label font weight (500 → 600)
- Increased label font size (0.625rem → 0.6875rem)
- Strategy descriptions now more readable

### Fill Detection:
- Verified all fill detection code uses correct Instrument-level structure
- Added documentation comment about E*TRADE structure

---

## v1.6.1 - TSL Fill Detection Fix (2026-02-23)

### Bug Fix:
Trailing Stop Limit fill detection was looking at the wrong level in E*TRADE's response structure.

- **Wrong:** Looking at `OrderDetail.filledQuantity` (doesn't exist)
- **Correct:** Looking at `OrderDetail.Instrument[].filledQuantity` (where E*TRADE puts it)

This matches the working Confirmation Stop Limit code structure.

### Also Added:
- API error handling for E*TRADE 500 errors
- Better logging for debugging fill detection

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
| v1.7.1 | 2026-03-05 | ✅ CURRENT | TSL configurable limit offset, cancel reliability fix |
| v1.7.0 | 2026-03-05 | Working | Server-side monitoring, SSE, live quotes, gevent worker |
| v1.6.2 | 2026-02-23 | Working | UI readability fix, fill detection consistency check |
| v1.6.1 | 2026-02-23 | Working | Fixed TSL fill detection - use Instrument level |
| v1.6.0 | 2026-02-23 | Working | Robust fill detection - API errors don't count toward timeout |
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

### Trailing Stop Data Structure (Confirmation Stop)

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

### Trailing Stop Limit (TSL) Order Type

E*TRADE `TRAILING_STOP_CNST` + `stopLimitPrice` = true trailing stop LIMIT order.

```xml
<Order>
    <priceType>TRAILING_STOP_CNST</priceType>
    <stopPrice>0.25</stopPrice>          <!-- Trail amount: stop trails $0.25 behind peak -->
    <stopLimitPrice>0.01</stopLimitPrice> <!-- Limit offset: limit is $0.01 below stop -->
    <orderTerm>GOOD_FOR_DAY</orderTerm>
</Order>
```

- `stopPrice` = trail amount (how far stop trails behind peak price)
- `stopLimitPrice` = limit offset (max slippage from stop trigger, default $0.01)
- Without `stopLimitPrice`, it becomes a MARKET order when triggered (potential slippage)

### TSL Config Dictionary (in-memory)

```python
_pending_trailing_stop_limit_orders[order_id] = {
    'symbol': str,
    'quantity': int,
    'account_id_key': str,
    'opening_side': str,          # BUY or SELL
    'trigger_type': str,          # 'dollar' or 'percent'
    'trigger_offset': float,      # e.g., 0.50
    'trail_type': str,            # 'dollar' or 'percent'
    'trail_amount': float,        # e.g., 0.25 → stopPrice
    'limit_offset': float,        # e.g., 0.01 → stopLimitPrice
    'trigger_timeout': int,       # seconds
    'fill_timeout': int,          # seconds
    'fill_price': float | None,
    'trigger_price': float | None,
    'stop_order_id': int | None,
    'status': str,                # waiting_fill, waiting_trigger, stop_placed, error
}
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
2. **Confirmation Timeout**: If price doesn't reach trigger, position remains open
3. **No OCO Orders**: E*TRADE API doesn't support One-Cancels-Other orders
4. **E*TRADE Orders API**: Frequently returns 500 errors - handled with retries
5. **Single Worker**: Must use 1 gunicorn worker for singleton OrderMonitor
6. **CometD Streaming Dead**: E*TRADE's CometD/Bayeux API is dead - using REST polling + SSE instead
7. **No Automated Tests**: Test manually via UI

---

## OAuth Callback Status

**Status:** WORKING (v1.7.0)

E*TRADE redirects to callback URL after authorization. Request tokens stored in Redis for cross-process lookup.
- Callback URL: `https://web-production-9f73cd.up.railway.app/api/auth/callback`

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
├── server.py                 # Flask web server, API endpoints, SSE
├── etrade_client.py          # E*TRADE API wrapper, OAuth, orders
├── order_monitor.py          # Server-side order monitoring + quote streaming (v1.7.0)
├── trailing_stop_manager.py  # Trailing stop lifecycle management
├── token_manager.py          # OAuth token storage (Redis)
├── config.py                 # Credentials and configuration
├── gunicorn.conf.py          # Gunicorn config (gevent worker, CRITICAL for SSE)
├── Procfile                  # Railway start command
├── nixpacks.toml             # Railway build config
├── requirements.txt          # Python dependencies
├── static/
│   ├── css/style.css         # Styles (original backup)
│   ├── css/style-luxe.css    # Premium Terminal Luxe design (CURRENT)
│   └── js/app.js             # Application logic, SSE client
├── templates/
│   └── index.html            # Trading UI (with Watch button)
├── bracket_manager.py        # OLD - bracket order (kept for rollback)
├── test_streaming.py         # CometD/Bayeux feasibility test (dead)
├── test_callback_oauth.py    # Test script for callback OAuth
├── VERSION.md                # This file
├── README.md                 # System overview
├── CLAUDE.md                 # Claude session context
├── TROUBLESHOOTING.md        # Debug guide
└── ETRADE_API_REFERENCE.md   # API documentation
```

---

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
