# E*TRADE Trading System - Version History

## Current Version: v1.4.0-bracket-orders

**Status: WORKING - Confirmation-Based Bracket Orders**
**Commit:** (pending)
**Date:** 2026-02-19
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
| Auto Fill Checking | ✅ WORKING | Polls every 500ms (v1.3.2) |
| Auto Cancel on Timeout | ✅ WORKING | Cancel if not filled within timeout |
| STOP_LIMIT Orders | ✅ NEW | v1.4.0 - Stop price + limit price |
| **Bracket Orders** | ✅ NEW | v1.4.0 - Confirmation-based with guaranteed profit |
| Redis Token Storage | ✅ FIXED | v1.4.0 - Now using Redis-Y5_F service |

---

## v1.4.0 - Bracket Orders & STOP_LIMIT Support (2026-02-19)

### New Features:

1. **Confirmation-Based Bracket Orders**
   - Wait for price confirmation before placing bracket
   - Both exit orders above fill price = **guaranteed profit**
   - STOP LIMIT order for protected stop loss
   - LIMIT order for profit target
   - Automatic OCA (One Cancels All) when either fills

2. **STOP_LIMIT Order Support**
   - Added `stopPrice` to order XML payload
   - Required for bracket order stop loss functionality

3. **Redis Connection Fixed**
   - Updated REDIS_URL to point to Redis-Y5_F service
   - Tokens now persist in Redis properly

### New Files:
- `bracket_manager.py` - Bracket order lifecycle management

### New API Endpoints:
- `GET /api/brackets` - List all active brackets
- `GET /api/brackets/<opening_order_id>` - Get bracket status
- `GET /api/brackets/<opening_order_id>/check-fill` - Check if opening filled
- `GET /api/brackets/<opening_order_id>/check-confirmation` - Check price confirmation
- `GET /api/brackets/<opening_order_id>/check-bracket` - Check bracket order fills
- `POST /api/brackets/<opening_order_id>/cancel` - Cancel bracket

### Bracket Order Flow:
```
1. Place BUY order with bracket enabled
2. Wait for fill
3. Wait for price to move UP to trigger level
4. Place bracket orders:
   - STOP LIMIT SELL @ trigger - offset (above fill!)
   - LIMIT SELL @ trigger + offset
5. Monitor both orders
6. When one fills, cancel the other
```

### UI Changes:
- Added bracket order section with configuration fields
- Confirmation trigger: $ or % offset from fill
- Protected stop loss: $ or % below trigger
- Profit target: $ or % above trigger
- Fill timeout and confirmation timeout settings
- Real-time bracket status monitoring

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| v1.4.0 | 2026-02-19 | ✅ CURRENT | Bracket orders, STOP_LIMIT, Redis fix |
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

### Bracket Order Data Structure

```python
PendingBracket:
    opening_order_id: int
    symbol: str
    quantity: int
    fill_price: float
    trigger_price: float  # Price at which bracket is placed
    stop_order_id: int    # STOP LIMIT order ID
    profit_order_id: int  # LIMIT order ID
    state: BracketState   # pending_fill, waiting_confirmation, bracket_placed, etc.
```

---

## Railway Services

| Service | Purpose | Status |
|---------|---------|--------|
| web | Flask application | Running |
| Redis-Y5_F | Token & bracket storage | Running |

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
3. **Bracket Monitoring**: Frontend-based, stops if browser is closed
4. **Confirmation Timeout**: If price doesn't reach trigger, position remains open

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

# Rollback to v1.3.3 (before bracket orders)
git checkout 3eaa205
git push origin main --force

# Rollback to v1.3.0 (offset-based profit)
git checkout 4b4a088
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
├── server.py              # Flask web server, API endpoints
├── etrade_client.py       # E*TRADE API wrapper, OAuth, orders
├── bracket_manager.py     # Bracket order lifecycle management (NEW)
├── token_manager.py       # OAuth token storage (Redis)
├── config.py              # Credentials and configuration
├── static/
│   ├── css/style.css      # Styles (includes bracket styles)
│   └── js/app.js          # Application logic (includes bracket monitoring)
├── templates/
│   └── index.html         # Trading UI (includes bracket form)
├── requirements.txt       # Python dependencies
├── VERSION.md             # This file
├── README.md              # System overview
├── TROUBLESHOOTING.md     # Debug guide
├── ETRADE_API_REFERENCE.md # API documentation
├── CALLBACK_OAUTH_RESEARCH.md # OAuth callback research
├── CALLBACK_URL_STATUS.md # Callback registration status
└── test_callback_oauth.py # Test script for callback OAuth
```

---

## References

- Official E*TRADE Python Example: `~/Downloads/EtradePythonClient`
- API Documentation: `ETRADE_API_REFERENCE.md`
- Troubleshooting: `TROUBLESHOOTING.md`
- GitHub Repo: https://github.com/rasesh6/etrade-trading
- pyetrade Reference: `/opt/miniconda3/lib/python3.13/site-packages/pyetrade/order.py`
