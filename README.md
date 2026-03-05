# E*TRADE Stock Trading System

A web-based trading interface for E*TRADE with server-side order monitoring, live quote streaming, and advanced exit strategies.

**Live URL**: https://web-production-9f73cd.up.railway.app
**GitHub**: https://github.com/rasesh6/etrade-trading
**Current Version**: v1.7.2 (Production Mode)

## Features

- OAuth 1.0a authentication with callback flow and token persistence (Redis)
- Real-time market quotes with **live streaming** (Watch button, SSE push)
- Account balance and buying power display
- Portfolio positions view with P&L
- Market and Limit order placement
- Limit orders with BID/ASK or manual price selection
- **Server-Side Order Monitoring** - Survives browser close
- **SSE (Server-Sent Events)** - Real-time push updates to frontend
- **Profit Target Orders** - Auto place closing order when opening fills
- **Offset-Based Profit** - Use $ or % offset from fill price
- **Confirmation Stop Limit** - Wait for price confirmation, then place STOP LIMIT
- **Trailing Stop Limit ($)** - TRAILING_STOP_CNST with trigger + trailing amount
- **Exit Strategy Dropdown** - None, Profit Target, Confirmation Stop, Trailing Stop
- Open orders view with cancel functionality
- Premium "Terminal Luxe" dark-themed UI
- Sandbox/Production environment toggle

## Architecture

- **Frontend**: HTML + vanilla JS with SSE EventSource for real-time updates
- **Backend**: Flask + gunicorn (gevent worker for concurrent SSE)
- **Monitoring**: `order_monitor.py` - background threads for fill detection + quote streaming
- **Storage**: Redis for OAuth tokens and state persistence
- **Deployment**: Railway (auto-deploy on push to main)

## Local Development

1. Install dependencies:
```bash
cd ~/Projects/etrade
pip install -r requirements.txt
```

2. Set environment variables (or create .env file):
```bash
export ETRADE_USE_SANDBOX=false  # Production mode
export REDIS_URL=redis://localhost:6379
```

3. Run the server:
```bash
python server.py
# Opens at http://localhost:5001 (port 5000 blocked by macOS AirPlay)
```

## Railway Deployment

Deployed at: https://web-production-9f73cd.up.railway.app

Auto-deploys on push to `main` branch. Key config:
- `gunicorn.conf.py` - gevent worker (CRITICAL for SSE concurrency)
- `Procfile` / `nixpacks.toml` - reference gunicorn.conf.py

### Railway Services

| Service | Purpose |
|---------|---------|
| web | Flask application (gunicorn + gevent) |
| Redis-Y5_F | Token & state storage |

### Railway CLI Commands

```bash
railway status          # Check status
railway logs --tail 50  # View deploy logs
railway logs --build --tail 50  # View build logs
railway variables       # View environment variables
```

## OAuth Flow

1. Click "Connect to E*TRADE"
2. A new tab opens to E*TRADE authorization
3. Login and click "Accept"
4. E*TRADE redirects to callback URL — authentication completes automatically
5. Authenticated for 24 hours (or until midnight ET)

## API Endpoints

### Authentication
- `GET /api/auth/status` - Check authentication status
- `POST /api/auth/login` - Start OAuth flow
- `POST /api/auth/verify` - Complete OAuth with verification code
- `POST /api/auth/logout` - Clear authentication
- `GET /api/auth/callback` - OAuth callback (automatic)

### Accounts
- `GET /api/accounts` - List accounts
- `GET /api/accounts/{id}/balance` - Get balance
- `GET /api/accounts/{id}/portfolio` - Get positions

### Market
- `GET /api/quote/{symbol}` - Get market quote
- `POST /api/quote/{symbol}/watch` - Start live quote streaming
- `DELETE /api/quote/watch` - Stop live quote streaming

### Real-Time Events
- `GET /api/events` - SSE endpoint for push updates

### Orders
- `POST /api/orders/preview` - Preview order
- `POST /api/orders/place` - Place order (supports exit strategies)
- `GET /api/orders/{account_id}` - List orders
- `POST /api/orders/{account_id}/{order_id}/cancel` - Cancel order
- `GET /api/orders/pending-profits` - List pending profit orders
- `GET /api/orders/{account_id}/check-fill/{order_id}` - Check fill status

### Trailing Stops
- `GET /api/trailing-stops` - List all trailing stops
- `GET /api/trailing-stops/{order_id}` - Get trailing stop status

## File Structure

```
etrade/
├── server.py                 # Flask web server, API endpoints, SSE
├── etrade_client.py          # E*TRADE API wrapper, OAuth, orders
├── order_monitor.py          # Server-side monitoring + quote streaming
├── trailing_stop_manager.py  # Trailing stop lifecycle management
├── token_manager.py          # OAuth token storage (Redis)
├── config.py                 # Credentials and configuration
├── gunicorn.conf.py          # Gunicorn config (gevent, CRITICAL)
├── requirements.txt          # Python dependencies
├── Procfile                  # Railway start command
├── nixpacks.toml             # Railway build config
├── templates/
│   └── index.html            # Trading UI
└── static/
    ├── css/style-luxe.css    # Premium Terminal Luxe design
    └── js/app.js             # Application logic + SSE client
```

## Security

All routes protected by HTTP Basic Auth when `AUTH_USERNAME` and `AUTH_PASSWORD` environment variables are set. Browser prompts for credentials once and caches them for the session.

Set these as **shared variables** in Railway (project-level vars must be explicitly shared with each service).

## Important Notes

1. **Production Mode**: System is in PRODUCTION mode. Orders are REAL.
2. **Token Expiry**: Tokens expire at midnight ET. Re-authenticate daily.
3. **Gevent Worker**: `gunicorn.conf.py` must set `worker_class = "gevent"` for SSE to work.
4. **Single Worker**: Must use 1 worker for singleton OrderMonitor.
5. **E*TRADE API**: Frequently returns 500 errors — handled with retries.
6. **Basic Auth**: Set `AUTH_USERNAME` + `AUTH_PASSWORD` env vars to protect all routes.

## Documentation

- **CLAUDE.md** - Claude session context and architecture
- **VERSION.md** - Version history and technical details
- **TROUBLESHOOTING.md** - Common issues and solutions
- **ETRADE_API_REFERENCE.md** - Complete OAuth and API documentation

## Quick Session Start

For a new development session, read these files first:
1. `CLAUDE.md` - Architecture, key files, recent changes
2. `VERSION.md` - Version history and features
3. `TROUBLESHOOTING.md` - Common issues
