# E*TRADE Trading System - Context for Claude Sessions

> **Last Updated:** 2026-02-23
> **Current Version:** v1.5.5

## Quick Start for New Sessions

1. Read this file first for full context
2. Read `VERSION.md` for version history and technical details
3. Read `TROUBLESHOOTING.md` if debugging issues

## Project Overview

A web-based E*TRADE trading interface with:
- OAuth 1.0a authentication (manual verification code flow)
- Real-time market quotes
- Account balance and positions display
- Order placement with profit targets and trailing stops
- Premium "Terminal Luxe" UI design

**Live URL:** https://web-production-9f73cd.up.railway.app
**GitHub:** https://github.com/rasesh6/etrade-trading
**Environment:** PRODUCTION (real trading)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│  templates/index.html + static/js/app.js + static/css/      │
│  - Polls for fill status every 1 second                     │
│  - Handles trailing stop monitoring                         │
│  - Auto-refreshes orders list on fills                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend (server.py)                    │
│  - Flask API endpoints                                      │
│  - E*TRADE API integration via etrade_client.py             │
│  - Trailing stop management via trailing_stop_manager.py    │
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
| `server.py` | Flask web server, all API endpoints |
| `etrade_client.py` | E*TRADE API wrapper, OAuth, order placement |
| `trailing_stop_manager.py` | Trailing stop lifecycle management |
| `token_manager.py` | OAuth token storage (Redis) |
| `static/js/app.js` | Frontend application logic |
| `static/css/style-luxe.css` | Premium Terminal Luxe design |
| `templates/index.html` | Trading UI |

## Order Types and Monitoring

1. **Simple Orders** - No automatic fill monitoring. User must refresh to see status.

2. **Profit Target Orders** - System polls for fill, then places limit sell order.
   - Monitoring: `startOrderMonitoring()` in app.js
   - Refreshes orders list on fill ✅

3. **Trailing Stop Orders** - System polls for fill, waits for price trigger, places stop.
   - Monitoring: `startTrailingStopMonitoring()` in app.js
   - Refreshes orders list on fill ✅ (fixed in v1.5.5)

## Git Workflow

### Committing Changes

```bash
# Check current status
git status

# View recent commits for style
git log --oneline -5

# Stage specific files (avoid git add .)
git add <files>

# Commit with message
git commit -m "$(cat <<'EOF'
fix: Description of what was fixed

Brief explanation of the problem and solution.

Files changed:
- path/to/file.py - what changed

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"

# Push to origin
git push origin main
```

### Commit Message Style

Based on recent commits:
- Use `fix:` prefix for bug fixes
- Use `feat:` prefix for new features
- Use `docs:` prefix for documentation
- Keep first line concise (50 chars ideal)
- Include Co-Authored-By for Claude contributions

### Deployment

Changes pushed to `main` branch auto-deploy to Railway:
- URL: https://web-production-9f73cd.up.railway.app
- View logs: `railway logs --tail 50`

## Recent Changes

### v1.5.5 (2026-02-23)
**Fix:** Trailing stop orders not refreshing orders list after fill

- **Problem 1:** When trailing stop detected fill and transitioned to "waiting for confirmation", the orders list still showed the order as OPEN.
- **Problem 2:** When fill timeout occurred and cancel returned error 5001 ("being executed"), the system gave up instead of continuing with trailing stop placement.
- **Fix 1:** Added `loadOrders(currentAccountIdKey);` in `app.js` line 862 after fill detection.
- **Fix 2:** When error 5001 occurs, re-check fill status and if confirmed, continue with trailing stop flow.
- **File:** `static/js/app.js`

## Common Tasks

### Debugging Order Issues

1. Check Railway logs: `railway logs --tail 100`
2. Check browser console for frontend errors
3. Look at `TROUBLESHOOTING.md` for common issues

### Adding New Order Features

1. Update `etrade_client.py` for E*TRADE API changes
2. Update `server.py` for new endpoints
3. Update `app.js` for frontend monitoring
4. Ensure `loadOrders()` is called after fill detection
5. Update VERSION.md and this file

### Testing

No automated tests. Test manually via:
1. Local: `python server.py` then http://localhost:5000
2. Production: https://web-production-9f73cd.up.railway.app

## Known Limitations

1. E*TRADE API frequently returns 500 errors - handled with exponential backoff
2. Callback OAuth not registered - using manual verification code
3. Trailing stop monitoring stops if browser is closed
4. No automated tests

## References

- `VERSION.md` - Detailed version history
- `README.md` - Project overview
- `TROUBLESHOOTING.md` - Debug guide
- `ETRADE_API_REFERENCE.md` - API documentation
