# E*TRADE Stock Trading System

A simple, efficient web-based trading interface for E*TRADE with advanced bracket order functionality.

**Live URL**: https://web-production-9f73cd.up.railway.app
**GitHub**: https://github.com/rasesh6/etrade-trading
**Current Version**: v1.4.0 (Production Mode)

## Features

- OAuth 1.0a authentication with token persistence (Redis)
- Real-time market quotes with BID/ASK display
- Account balance and buying power display
- Portfolio positions view with P&L
- Market and Limit order placement
- Limit orders with BID/ASK or manual price selection
- **Profit Target Orders** - Auto place closing order when opening fills
- **Offset-Based Profit** - Use $ or % offset from fill price
- **Auto Fill Monitoring** - System polls every 500ms for order fills
- **Auto-Cancel on Timeout** - Cancel unfilled orders automatically
- **🆕 Bracket Orders (Confirmation-Based)** - Wait for price confirmation, then place bracket with guaranteed profit
- **🆕 STOP_LIMIT Orders** - Stop price + limit price for protected exits
- Open orders view with cancel functionality
- Responsive dark-themed UI
- Sandbox/Production environment toggle

## Bracket Orders (New in v1.4.0)

The system supports **confirmation-based bracket orders** where both exit orders are placed ABOVE the fill price, guaranteeing a profit:

1. **Place Opening Order**: Check "Add Bracket Order" and configure offsets
2. **Wait for Fill**: System monitors for order execution
3. **Wait for Confirmation**: Price must move in your favor by the trigger amount
4. **Bracket Placed**: Two orders placed simultaneously:
   - **STOP LIMIT** just below current price (but above fill = profit)
   - **LIMIT** above current price (profit target)
5. **OCA Logic**: When one fills, the other is automatically cancelled

**Example (BUY AAPL @ $175):**
```
Confirmation: $1.00 above fill → Trigger at $176.00
Stop Loss: $0.25 below trigger → Stop at $175.75
Profit Target: $1.00 above trigger → Limit at $177.00

Result: Minimum guaranteed profit = $0.75/share!
```

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
```

4. Open http://localhost:5000 in your browser

## Railway Deployment

Deployed at: https://web-production-9f73cd.up.railway.app

Environment variables (configured):
- `ETRADE_USE_SANDBOX=false` - Production mode (REAL TRADING)
- `FLASK_SECRET_KEY` - Session security
- `REDIS_URL` - Token storage (references Redis-Y5_F service)

### Railway Services

| Service | Purpose |
|---------|---------|
| web | Flask application |
| Redis-Y5_F | Token & bracket state storage |

### Railway CLI Commands

```bash
# Check status
railway status

# View logs
railway logs --tail 50

# View variables
railway variables
```

## OAuth Flow

1. Click "Connect to E*TRADE"
2. A new tab opens to E*TRADE authorization
3. Login and authorize the application
4. Copy the verification code from the page
5. Paste the code and click "Verify"
6. You're now authenticated for 24 hours (or until midnight ET)

## API Endpoints

### Authentication
- `GET /api/auth/status` - Check authentication status
- `POST /api/auth/login` - Start OAuth flow
- `POST /api/auth/verify` - Complete OAuth with verification code
- `POST /api/auth/logout` - Clear authentication
- `GET /api/auth/callback` - OAuth callback (requires E*TRADE registration)

### Accounts
- `GET /api/accounts` - List accounts
- `GET /api/accounts/{id}/balance` - Get balance
- `GET /api/accounts/{id}/portfolio` - Get positions

### Market
- `GET /api/quote/{symbol}` - Get market quote

### Orders
- `POST /api/orders/preview` - Preview order
- `POST /api/orders/place` - Place order (supports bracket params)
- `GET /api/orders/{account_id}` - List orders
- `POST /api/orders/{account_id}/{order_id}/cancel` - Cancel order
- `GET /api/orders/pending-profits` - List pending profit orders
- `GET /api/orders/{account_id}/check-fill/{order_id}` - Check fill status

### Bracket Orders (New)
- `GET /api/brackets` - List all brackets
- `GET /api/brackets/{opening_order_id}` - Get bracket status
- `GET /api/brackets/{opening_order_id}/check-fill` - Check opening fill
- `GET /api/brackets/{opening_order_id}/check-confirmation` - Check price confirmation
- `GET /api/brackets/{opening_order_id}/check-bracket` - Check bracket fills
- `POST /api/brackets/{opening_order_id}/cancel` - Cancel bracket

## File Structure

```
etrade/
├── server.py              # Flask web server, API endpoints
├── etrade_client.py       # E*TRADE API wrapper, OAuth, orders
├── bracket_manager.py     # Bracket order lifecycle management
├── token_manager.py       # OAuth token storage (Redis)
├── config.py              # Credentials and configuration
├── requirements.txt       # Python dependencies
├── runtime.txt            # Python version for Railway
├── Procfile               # Railway deployment config
├── templates/
│   └── index.html         # Trading UI
└── static/
    ├── css/style.css      # Styles
    └── js/app.js          # Application logic
```

## Important Notes

1. **Production Mode**: System is currently in PRODUCTION mode. Orders are REAL and will execute actual trades.

2. **Token Expiry**: E*TRADE tokens expire at midnight Eastern Time. You'll need to re-authenticate daily.

3. **Order Flow**: E*TRADE requires orders to be previewed before placing. This is handled automatically.

4. **Rate Limits**: E*TRADE has API rate limits. The system handles basic error cases.

5. **Bracket Monitoring**: Handled by frontend JavaScript. Closing the browser stops monitoring.

6. **Callback OAuth**: NOT registered with E*TRADE. Using manual verification code flow.

## Documentation

- **VERSION.md** - Version history and current status
- **ETRADE_API_REFERENCE.md** - Complete OAuth and API documentation
- **TROUBLESHOOTING.md** - Common issues and solutions
- **CALLBACK_OAUTH_RESEARCH.md** - OAuth callback research
- **CALLBACK_URL_STATUS.md** - Callback registration status

## Security

- API keys are stored as environment variables (never in code)
- OAuth tokens are stored in Redis
- HTTPS required for production deployment
- Input validation on all endpoints

## Quick Session Start

For a new development session, read these files first:
1. `VERSION.md` - Current version, features, and Railway info
2. `README.md` - This file
3. `TROUBLESHOOTING.md` - Common issues
4. `bracket_manager.py` - Bracket order logic (if working on brackets)
