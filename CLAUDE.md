# E*TRADE Trading System - Context for Claude Sessions

> **Last Updated:** 2026-03-05
> **Current Version:** v1.7.1

## Quick Start for New Sessions

1. Read this file first for full context
2. Read `VERSION.md` for version history and technical details
3. Read `TROUBLESHOOTING.md` if debugging issues

## Project Overview

A web-based E*TRADE trading interface with:
- OAuth 1.0a authentication (callback-based flow via Railway)
- Real-time market quotes with live streaming (SSE-powered Watch button)
- Account balance and positions display
- Order placement with profit targets, confirmation stops, and trailing stops
- Server-side order monitoring (survives browser close)
- Premium "Terminal Luxe" UI design

**Live URL:** https://web-production-9f73cd.up.railway.app
**GitHub:** https://github.com/rasesh6/etrade-trading
**Environment:** PRODUCTION (real trading)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│  templates/index.html + static/js/app.js + static/css/      │
│  - SSE (Server-Sent Events) for real-time updates           │
│  - Live quote streaming via Watch button                    │
│  - Order fill/cancel status via SSE push                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend (server.py)                    │
│  - Flask API endpoints                                      │
│  - E*TRADE API integration via etrade_client.py             │
│  - Server-side order monitoring via order_monitor.py        │
│  - Trailing stop management via trailing_stop_manager.py    │
│  - Gunicorn + gevent for concurrent SSE connections         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Services                        │
│  - E*TRADE API (production)                                 │
│  - Redis (token & state storage via Railway)                │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Flask web server, all API endpoints, SSE endpoint |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order placement |
| `order_monitor.py` | **Server-side order monitoring + quote streaming (SSE)** |
| `trailing_stop_manager.py` | Trailing stop lifecycle management |
| `token_manager.py` | OAuth token storage (Redis) |
| `gunicorn.conf.py` | Gunicorn config (gevent worker, critical for SSE) |
| `config.py` | Credentials and configuration |
| `static/js/app.js` | Frontend application logic, SSE client |
| `static/css/style-luxe.css` | Premium Terminal Luxe design |
| `templates/index.html` | Trading UI |

## Real-Time Architecture (SSE)

### How it works:
1. **Quote streaming**: User clicks "Watch" → POST `/api/quote/SYMBOL/watch` → server starts background thread polling E*TRADE every 3s → pushes quote events via SSE
2. **Order monitoring**: Order placed with exit strategy → server starts background thread → polls for fill → pushes status/fill/cancel events via SSE
3. **SSE endpoint**: GET `/api/events` → long-lived connection, server pushes events as they happen

### Key design decisions:
- **Gunicorn + gevent** (`gunicorn.conf.py`): Single worker with green threads for concurrent SSE + HTTP. Must use config file (CLI flags were ignored by Railway).
- **Singleton `OrderMonitor`**: Single worker = single process = singleton works. Multiple workers would break this.
- **SSE connects on demand**: Only when monitoring an order or watching quotes (not on page load) to avoid unnecessary connections.

## Order Types and Monitoring

1. **Simple Orders** - No automatic fill monitoring. User must refresh to see status.

2. **Profit Target Orders** - Server monitors fill, then places limit sell order.
   - Monitoring: `order_monitor.py` → `monitor_profit_target()`
   - SSE events: `monitoring_started`, `status`, `filled`, `timeout`, `cancelled`

3. **Confirmation Stop Orders** - Server monitors fill, waits for price trigger, places stop.
   - Monitoring: `order_monitor.py` → `monitor_trailing_stop()`
   - SSE events: `ts_status`, `ts_filled`, `ts_stop_placed`, `ts_timeout`

4. **Trailing Stop Limit Orders** - Server monitors fill, waits for trigger, places trailing stop.
   - Monitoring: `order_monitor.py` → `monitor_tsl()`
   - SSE events: `tsl_status`, `tsl_filled`, `tsl_stop_placed`, `tsl_timeout`
   - E*TRADE order type: `TRAILING_STOP_CNST` + `stopLimitPrice` (true trailing stop LIMIT, not market)
   - UI fields: Trigger ($ or %), Trail (`stopPrice`), Limit Offset (`stopLimitPrice`, default $0.01)

## OAuth Flow

E*TRADE now redirects to callback URL instead of showing OOB verification code:
1. User clicks "Connect to E*TRADE" → server generates auth URL
2. E*TRADE redirects to `/api/auth/callback?oauth_token=...&oauth_verifier=...`
3. Server looks up request token secret from Redis, completes OAuth
4. Request tokens stored in Redis for cross-process callback lookup

**Important**: Token in authorize URL must be URL-encoded (`quote(request_token, safe='')`) because it contains `/`, `+`, `=` characters.

## Git Workflow

### Committing Changes

```bash
git status
git log --oneline -5
git add <files>
git commit -m "$(cat <<'EOF'
fix: Description of what was fixed

Brief explanation of the problem and solution.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

### Commit Message Style

- Use `fix:` prefix for bug fixes
- Use `feat:` prefix for new features
- Use `docs:` prefix for documentation
- Keep first line concise (50 chars ideal)
- Include Co-Authored-By for Claude contributions

### Deployment

Changes pushed to `main` branch auto-deploy to Railway:
- URL: https://web-production-9f73cd.up.railway.app
- View logs: `railway logs --tail 50`
- Build logs: `railway logs --build --tail 50`

## Recent Changes

### v1.7.1 (2026-03-05)
**Fixes: TSL limit offset + cancel reliability across all monitors**

- **Configurable limit offset for TSL**: `stopLimitPrice` was hardcoded to $0.01. Now user can set via "Limit Offset" field (default $0.01). This is the max slippage from the trailing stop trigger price.
- **TSL API-error timeout now cancels**: When E*TRADE API returned 500 errors throughout the fill timeout, the order was left open. Now it attempts cancel via `_cancel_and_recheck()`.
- **Delayed order refresh on all timeouts**: `ts_timeout` and `tsl_timeout` now delay `loadOrders()` by 2s (matching profit target), giving E*TRADE time to process the cancel.

### v1.7.0 (2026-03-05)
**Major: Server-side monitoring + SSE + Live quotes**

- **Server-side order monitoring** (`order_monitor.py`): Background threads monitor fills and place exit orders even if browser closes
- **SSE push events**: Real-time status updates pushed to frontend (replaces browser-based polling)
- **Live quote streaming**: "Watch" button streams NBBO bid/ask/last every 3s via SSE
- **OAuth callback flow**: E*TRADE now redirects to callback URL, fixed cross-process token lookup
- **Gunicorn gevent worker**: Required for concurrent SSE connections, configured via `gunicorn.conf.py`
- **Cancel status fix**: `timeout` event no longer disconnects SSE prematurely; `cancelled` event triggers delayed order refresh
- **User-friendly status messages**: API errors shown as "Waiting for fill..." instead of "API error, retrying..."

## Common Tasks

### Debugging Order Issues

1. Check Railway logs: `railway logs --tail 100`
2. Check browser console for frontend errors
3. Look at `TROUBLESHOOTING.md` for common issues
4. Check SSE connection: browser DevTools → Network → EventStream

### Adding New Order Features

1. Update `etrade_client.py` for E*TRADE API changes
2. Update `server.py` for new endpoints
3. Add monitoring in `order_monitor.py` (server-side)
4. Update `app.js` for SSE event handling
5. Ensure `loadOrders()` is called after fill detection
6. Update VERSION.md and this file

### Gunicorn / Railway Deployment

- **Config file is critical**: `gunicorn.conf.py` must set `worker_class = "gevent"`. CLI flags in Procfile/nixpacks.toml were ignored by Railway.
- **Single worker required**: `workers = 1` for singleton OrderMonitor to work
- **Verify worker type**: Check deploy logs for `Using worker: gevent` (not `sync`)
- **Cross-reference**: Alpaca project (`~/Projects/Alpaca`) uses same pattern successfully

### Testing

No automated tests. Test manually via:
1. Local: `python server.py` then http://localhost:5001 (port 5000 blocked by AirPlay)
2. Production: https://web-production-9f73cd.up.railway.app

## Known Limitations

1. E*TRADE API frequently returns 500 errors - handled with retries and user-friendly messages
2. OAuth callback flow requires Redis for cross-process token storage
3. CometD/Bayeux streaming API is dead (tested, all endpoints return 400 or DNS failure)
4. No automated tests
5. Single gunicorn worker means limited concurrent connections (mitigated by gevent green threads)

## References

- `VERSION.md` - Detailed version history
- `README.md` - Project overview
- `TROUBLESHOOTING.md` - Debug guide
- `ETRADE_API_REFERENCE.md` - API documentation
- `~/Projects/Alpaca` - Reference for gunicorn.conf.py and SSE patterns
