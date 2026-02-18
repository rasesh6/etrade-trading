# E*TRADE Stock Trading System

A simple, efficient web-based trading interface for E*TRADE.

**Live URL**: https://web-production-9f73cd.up.railway.app
**GitHub**: https://github.com/rasesh6/etrade-trading
**Current Version**: v1.2.0 (Sandbox Mode)

## Features

- OAuth 1.0a authentication with token persistence (Redis)
- Real-time market quotes with BID/ASK display
- Account balance and buying power display
- Portfolio positions view
- Market and Limit order placement
- Limit orders with BID/ASK or manual price selection
- **Profit Target Orders** - Auto place closing order when opening fills
- Open orders view with cancel functionality
- Responsive dark-themed UI
- Sandbox/Production environment toggle

## Local Development

1. Install dependencies:
```bash
cd ~/Projects/etrade
pip install -r requirements.txt
```

2. Set environment variables (or create .env file):
```bash
export ETRADE_USE_SANDBOX=true
export REDIS_URL=redis://localhost:6379
```

3. Run the server:
```bash
python server.py
```

4. Open http://localhost:5000 in your browser

## Railway Deployment

1. Create a new Railway project
2. Add Redis service
3. Deploy this folder with the following environment variables:
   - `ETRADE_USE_SANDBOX=true` (or false for production)
   - `ETRADE_SANDBOX_KEY` and `ETRADE_SANDBOX_SECRET` (if different from defaults)
   - `FLASK_SECRET_KEY` (random string)

## OAuth Flow

1. Click "Connect to E*TRADE"
2. A new tab opens to E*TRADE authorization
3. Login and authorize the application
4. Copy the verification code from the page
5. Paste the code and click "Verify"
6. You're now authenticated for 24 hours (or until midnight ET)

## Profit Target Orders

The system supports automatic profit order placement with offset-based targeting:

1. **Place Opening Order**: Check "Add Profit Target"
2. **Specify Offset**: Choose $ (dollar) or % (percent) offset from fill price
3. **Set Timeout**: How long to wait for fill before auto-cancelling (default 15s)
4. **Auto Monitoring**: System polls every 2 seconds for fill status
5. **Profit Order Placed**: When filled, profit order placed at (fill_price + offset)

**Example:**
```
Opening: BUY 1 AAPL @ Market
Profit Target: $1.00 offset (dollar)
Timeout: 15 seconds

If filled @ $175 → SELL 1 AAPL @ $176 LIMIT is placed automatically
If not filled within 15s → Order cancelled
```

**Note:** The monitoring is handled by the frontend. If you close the browser, pending orders will not be monitored.

## API Endpoints

### Authentication
- `GET /api/auth/status` - Check authentication status
- `POST /api/auth/login` - Start OAuth flow
- `POST /api/auth/verify` - Complete OAuth with verification code
- `POST /api/auth/logout` - Clear authentication

### Accounts
- `GET /api/accounts` - List accounts
- `GET /api/accounts/{id}/balance` - Get balance
- `GET /api/accounts/{id}/portfolio` - Get positions

### Market
- `GET /api/quote/{symbol}` - Get market quote

### Orders
- `POST /api/orders/preview` - Preview order
- `POST /api/orders/place` - Place order (supports profit_offset parameters)
- `GET /api/orders/{account_id}` - List orders
- `POST /api/orders/{account_id}/{order_id}/cancel` - Cancel order
- `GET /api/orders/pending-profits` - List pending profit orders
- `GET /api/orders/{account_id}/check-fill/{order_id}` - Check single order fill status
- `POST /api/orders/check-fills` - Check all fills (backup manual trigger)

## File Structure

```
etrade/
├── server.py              # Flask application
├── config.py              # Configuration and credentials
├── etrade_client.py       # E*TRADE API wrapper
├── token_manager.py       # OAuth token storage
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

1. **Sandbox Mode**: By default, the system uses E*TRADE's sandbox environment. Orders are simulated and no real transactions occur.

2. **Token Expiry**: E*TRADE tokens expire at midnight Eastern Time. You'll need to re-authenticate daily.

3. **Order Flow**: E*TRADE requires orders to be previewed before placing. This is handled automatically.

4. **Rate Limits**: E*TRADE has API rate limits. The system handles basic error cases.

## Documentation

- **ETRADE_API_REFERENCE.md** - Complete OAuth and API documentation
- **TROUBLESHOOTING.md** - Common issues and solutions
- **ORDER_FIX_PLAN.md** - Order placement fix history and status

## Security

- API keys are stored as environment variables (never in code)
- OAuth tokens are stored in Redis (encrypted in production)
- HTTPS required for production deployment
- Input validation on all endpoints
