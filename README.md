# E*TRADE Stock Trading System

A simple, efficient web-based trading interface for E*TRADE.

## Features

- OAuth 1.0a authentication with token persistence (Redis)
- Real-time market quotes with BID/ASK display
- Account balance and buying power display
- Portfolio positions view
- Market and Limit order placement
- Limit orders with BID/ASK or manual price selection
- Open orders view with cancel functionality
- Responsive dark-themed UI

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
- `POST /api/orders/place` - Place order
- `GET /api/orders/{account_id}` - List orders
- `POST /api/orders/{account_id}/{order_id}/cancel` - Cancel order

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

## Security

- API keys are stored as environment variables (never in code)
- OAuth tokens are stored in Redis (encrypted in production)
- HTTPS required for production deployment
- Input validation on all endpoints
