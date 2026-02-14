"""
E*TRADE Trading System Configuration

Railway URL: https://web-production-9f73cd.up.railway.app
GitHub: https://github.com/rasesh6/etrade-trading

API Keys are loaded from environment variables.
Set these in Railway or your local .env file.
"""
import os

# E*TRADE API Credentials
# Sandbox keys (for testing - no real trades)
SANDBOX_KEY = os.environ.get('ETRADE_SANDBOX_KEY', '8a18ff810b153dfd5d9ddce27667d63c')
SANDBOX_SECRET = os.environ.get('ETRADE_SANDBOX_SECRET', '58d4a4193e4efa091657d60079a63e31b472d559c48c890c660b29f4a57e2cbb')

# Production keys (for real trading - use with caution!)
PROD_KEY = os.environ.get('ETRADE_PROD_KEY', '353ce1949c42c71cec4785343aa36539')
PROD_SECRET = os.environ.get('ETRADE_PROD_SECRET', '6bef9b896a9d6d4c42807eb5d223b645862cfca48f986c0a3fea4b8dce43a3f5')

# API URLs
SANDBOX_BASE_URL = 'https://apisb.etrade.com'
PROD_BASE_URL = 'https://api.etrade.com'

# OAuth URLs
REQUEST_TOKEN_URL = 'https://api.etrade.com/oauth/request_token'
ACCESS_TOKEN_URL = 'https://api.etrade.com/oauth/access_token'
AUTHORIZE_URL = 'https://us.etrade.com/e/t/etws/authorize?key={}&token={}'

# Environment mode
USE_SANDBOX = os.environ.get('ETRADE_USE_SANDBOX', 'true').lower() == 'true'

# Redis configuration (for token storage)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
TOKEN_KEY_PREFIX = 'etrade:token:'
TOKEN_EXPIRY_HOURS = 24  # E*TRADE tokens expire at midnight ET

# Flask configuration
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'etrade-trading-secret-key-change-in-production')

def get_base_url():
    """Get the appropriate base URL based on environment"""
    return SANDBOX_BASE_URL if USE_SANDBOX else PROD_BASE_URL

def get_credentials():
    """Get the appropriate credentials based on environment"""
    if USE_SANDBOX:
        return SANDBOX_KEY, SANDBOX_SECRET
    return PROD_KEY, PROD_SECRET
