"""
E*TRADE API Client

Wraps all E*TRADE API functionality:
- OAuth authentication
- Account management
- Market quotes
- Order placement (preview + place)
- Portfolio/positions
"""
import json
import random
import logging
from urllib.parse import unquote
from requests import Session
from requests_oauthlib import OAuth1
from config import (
    get_base_url, get_credentials,
    REQUEST_TOKEN_URL, ACCESS_TOKEN_URL, AUTHORIZE_URL,
    USE_SANDBOX
)

logger = logging.getLogger(__name__)


class ETradeClient:
    """E*TRADE API Client with OAuth 1.0a support using requests-oauthlib"""

    def __init__(self):
        """Initialize the E*TRADE client"""
        self.base_url = get_base_url()
        self.consumer_key, self.consumer_secret = get_credentials()
        self.session = Session()
        self.access_token = None
        self.access_token_secret = None
        self._oauth = None

        logger.info(f"ETradeClient initialized with base_url: {self.base_url}")

    def get_authorization_url(self):
        """
        Step 1: Get request token and authorization URL

        Returns:
            dict with 'authorize_url' and 'request_token_secret'
        """
        try:
            # Create OAuth1 for request token
            # E*TRADE requires:
            # - HMAC-SHA1 signature method
            # - realm="" in Authorization header
            # - oauth_callback="oob"
            oauth = OAuth1(
                self.consumer_key,
                client_secret=self.consumer_secret,
                callback_uri='oob',
                signature_method='HMAC-SHA1',
                signature_type='auth_header',
                realm=''
            )

            # Request token - E*TRADE uses GET for request_token
            response = self.session.get(
                REQUEST_TOKEN_URL,
                auth=oauth
            )

            logger.info(f"Request token response status: {response.status_code}")
            logger.info(f"Request token response: {response.text[:500] if response.text else 'Empty'}")

            if response.status_code != 200:
                raise Exception(f"Request token failed ({response.status_code}): {response.text}")

            # Parse response - E*TRADE returns URL-encoded format
            token_data = self._parse_oauth_response(response.text)
            request_token = token_data.get('oauth_token')
            request_token_secret = token_data.get('oauth_token_secret')

            if not request_token:
                raise Exception(f"No request token in response: {response.text}")

            authorize_url = AUTHORIZE_URL.format(
                self.consumer_key,
                request_token
            )

            logger.info(f"Generated authorization URL for token: {request_token[:20]}...")

            return {
                'authorize_url': authorize_url,
                'request_token': request_token,
                'request_token_secret': request_token_secret
            }

        except Exception as e:
            logger.error(f"Failed to get authorization URL: {e}")
            raise Exception(f"Authorization URL generation failed: {str(e)}")

    def _parse_oauth_response(self, response_text):
        """Parse URL-encoded OAuth response and decode values"""
        params = {}
        if not response_text:
            return params
        for pair in response_text.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                # URL-decode the value (E*TRADE returns URL-encoded tokens)
                params[key] = unquote(value)
        return params

    def complete_authentication(self, verifier_code, request_token, request_token_secret):
        """
        Step 2: Exchange verification code for access token

        Args:
            verifier_code: Code from E*TRADE authorization page
            request_token: Request token from step 1
            request_token_secret: Request token secret from step 1

        Returns:
            dict with access_token and access_token_secret
        """
        try:
            logger.info(f"Completing authentication with verifier: {verifier_code}")

            # Create OAuth1 for access token
            # E*TRADE requires:
            # - HMAC-SHA1 signature method
            # - realm="" in Authorization header
            # - oauth_token and oauth_verifier
            oauth = OAuth1(
                self.consumer_key,
                client_secret=self.consumer_secret,
                resource_owner_key=request_token,
                resource_owner_secret=request_token_secret,
                verifier=verifier_code,
                signature_method='HMAC-SHA1',
                signature_type='auth_header',
                realm=''
            )

            # Get access token - E*TRADE uses GET for access_token
            response = self.session.get(
                ACCESS_TOKEN_URL,
                auth=oauth
            )

            logger.info(f"Access token response status: {response.status_code}")
            logger.info(f"Access token response: {response.text[:500] if response.text else 'Empty'}")

            if response.status_code != 200:
                raise Exception(f"Access token failed ({response.status_code}): {response.text}")

            # Parse response - E*TRADE returns URL-encoded format
            token_data = self._parse_oauth_response(response.text)
            self.access_token = token_data.get('oauth_token')
            self.access_token_secret = token_data.get('oauth_token_secret')

            if not self.access_token:
                raise Exception(f"No access token in response: {response.text}")

            # Set up OAuth for future requests
            self._setup_oauth()

            logger.info("Authentication completed successfully")

            return {
                'access_token': self.access_token,
                'access_token_secret': self.access_token_secret,
                'success': True
            }

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise Exception(f"Authentication failed: {str(e)}")

    def _setup_oauth(self):
        """Set up OAuth1 for authenticated requests"""
        self._oauth = OAuth1(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_token_secret,
            signature_method='HMAC-SHA1',
            signature_type='auth_header',
            realm=''
        )
        logger.info("OAuth1 configured for authenticated requests")

    def set_session(self, access_token, access_token_secret):
        """
        Set the OAuth session from stored tokens

        Args:
            access_token: Stored access token
            access_token_secret: Stored access token secret
        """
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self._setup_oauth()
        logger.info(f"OAuth session configured from stored tokens, base_url: {self.base_url}")

    def _make_request(self, method, endpoint, params=None, data=None, headers=None):
        """
        Make an authenticated API request

        Args:
            method: HTTP method (GET, POST, PUT)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body (for POST/PUT)
            headers: Additional headers

        Returns:
            dict response data
        """
        if not self._oauth:
            raise Exception("Not authenticated. Please authenticate first.")

        url = f"{self.base_url}{endpoint}"

        default_headers = {'consumerKey': self.consumer_key}
        if headers:
            default_headers.update(headers)

        try:
            logger.info(f"Making {method} request to {url}")

            request_args = {
                'params': params,
                'headers': default_headers,
                'auth': self._oauth
            }

            if method == 'GET':
                response = self.session.get(url, **request_args)
            elif method == 'POST':
                response = self.session.post(url, data=data, **request_args)
            elif method == 'PUT':
                response = self.session.put(url, data=data, **request_args)
            else:
                raise Exception(f"Unsupported method: {method}")

            # Check if response is valid
            if response is None:
                raise Exception("API returned None response")

            logger.info(f"Response Status: {response.status_code}")

            # Log response body for debugging
            logger.info(f"Response text (first 500 chars): {response.text[:500] if response.text else 'Empty'}")

            if response.status_code == 204:
                return {'status': 'success', 'data': None}

            if response.status_code not in [200, 201]:
                error_msg = "Unknown error"
                try:
                    error_data = response.json()
                    if error_data is not None and 'Error' in error_data:
                        error_msg = error_data['Error'].get('message', str(error_data))
                    elif error_data is not None:
                        error_msg = str(error_data)
                except Exception as json_err:
                    error_msg = response.text[:200] if response.text else "No error message"
                raise Exception(f"API Error ({response.status_code}): {error_msg}")

            result = response.json()
            if result is None:
                logger.warning("response.json() returned None")
                return {}

            return result

        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    # ==================== ACCOUNT APIs ====================

    def get_accounts(self):
        """
        Get list of E*TRADE accounts

        Returns:
            list of account objects
        """
        response = self._make_request('GET', '/v1/accounts/list.json')

        accounts = []
        if response is None:
            logger.warning("Accounts API returned None")
            return accounts

        logger.info(f"Accounts API response: {response}")

        if 'AccountListResponse' in response and response['AccountListResponse'] is not None:
            if 'Accounts' in response['AccountListResponse'] and response['AccountListResponse']['Accounts'] is not None:
                account_data = response['AccountListResponse']['Accounts']
                if 'Account' in account_data and account_data['Account'] is not None:
                    accounts = account_data['Account']
                    # Filter out closed accounts
                    accounts = [a for a in accounts if a.get('accountStatus') != 'CLOSED']

        logger.info(f"Retrieved {len(accounts)} accounts")
        return accounts

    def get_account_balance(self, account_id_key):
        """
        Get account balance

        Args:
            account_id_key: Account ID key from account list

        Returns:
            dict with balance information
        """
        params = {'instType': 'BROKERAGE', 'realTimeNAV': 'true'}
        response = self._make_request(
            'GET',
            f'/v1/accounts/{account_id_key}/balance.json',
            params=params
        )

        if 'BalanceResponse' in response:
            return response['BalanceResponse']

        return response

    def get_portfolio(self, account_id_key):
        """
        Get portfolio positions

        Args:
            account_id_key: Account ID key

        Returns:
            list of position objects
        """
        response = self._make_request(
            'GET',
            f'/v1/accounts/{account_id_key}/portfolio.json'
        )

        positions = []
        if 'PortfolioResponse' in response:
            if 'AccountPortfolio' in response['PortfolioResponse']:
                for portfolio in response['PortfolioResponse']['AccountPortfolio']:
                    if 'Position' in portfolio:
                        positions.extend(portfolio['Position'])

        logger.info(f"Retrieved {len(positions)} positions")
        return positions

    # ==================== MARKET APIs ====================

    def get_quote(self, symbol):
        """
        Get market quote for a symbol

        Args:
            symbol: Stock symbol (e.g., AAPL)

        Returns:
            dict with quote data
        """
        response = self._make_request(
            'GET',
            f'/v1/market/quote/{symbol.upper()}.json'
        )

        if response is None:
            logger.warning(f"Quote API returned None for {symbol}")
            return None

        logger.info(f"Quote API response for {symbol}: {response}")

        if 'QuoteResponse' in response and response['QuoteResponse'] is not None:
            if 'QuoteData' in response['QuoteResponse'] and response['QuoteResponse']['QuoteData'] is not None:
                quotes = response['QuoteResponse']['QuoteData']
                if isinstance(quotes, list) and len(quotes) > 0:
                    return quotes[0]

        return response

    def get_quotes(self, symbols):
        """
        Get quotes for multiple symbols

        Args:
            symbols: List of stock symbols

        Returns:
            list of quote data
        """
        if isinstance(symbols, list):
            symbols = ','.join(symbols)

        response = self._make_request(
            'GET',
            f'/v1/market/quote/{symbols.upper()}.json'
        )

        quotes = []
        if 'QuoteResponse' in response:
            if 'QuoteData' in response['QuoteResponse']:
                quotes = response['QuoteResponse']['QuoteData']

        return quotes

    # ==================== ORDER APIs ====================

    def preview_order(self, account_id_key, order_data):
        """
        Preview an order before placing

        Args:
            account_id_key: Account ID key
            order_data: Order details dict

        Returns:
            dict with preview results including previewId
        """
        # Build XML payload
        payload = self._build_order_payload(order_data, preview=True)

        headers = {
            'Content-Type': 'application/xml',
            'consumerKey': self.consumer_key
        }

        response = self._make_request(
            'POST',
            f'/v1/accounts/{account_id_key}/orders/preview.json',
            data=payload,
            headers=headers
        )

        if 'PreviewOrderResponse' in response:
            return {
                'preview_id': response['PreviewOrderResponse'].get('PreviewIds', [{}])[0].get('previewId'),
                'order': response['PreviewOrderResponse'].get('Order', [{}])[0] if 'Order' in response['PreviewOrderResponse'] else {},
                'estimated_commission': response['PreviewOrderResponse'].get('Order', [{}])[0].get('estimatedCommission', 0),
                'estimated_total': response['PreviewOrderResponse'].get('Order', [{}])[0].get('estimatedTotalAmount', 0),
                'raw_response': response
            }

        return response

    def place_order(self, account_id_key, order_data, preview_id=None):
        """
        Place an order

        Args:
            account_id_key: Account ID key
            order_data: Order details dict
            preview_id: Optional preview ID (if already previewed)

        Returns:
            dict with order results
        """
        # Build XML payload
        payload = self._build_order_payload(order_data, preview=preview_id is not None)
        if preview_id:
            # Add preview ID to payload
            payload = payload.replace('<PreviewOrderRequest>', f'<PlaceOrderRequest><previewId>{preview_id}</previewId>')
            payload = payload.replace('</PreviewOrderRequest>', '</PlaceOrderRequest>')

        headers = {
            'Content-Type': 'application/xml',
            'consumerKey': self.consumer_key
        }

        endpoint = f'/v1/accounts/{account_id_key}/orders/place.json'

        response = self._make_request(
            'POST',
            endpoint,
            data=payload,
            headers=headers
        )

        if 'PlaceOrderResponse' in response:
            return {
                'order_id': response['PlaceOrderResponse'].get('OrderIds', [{}])[0].get('orderId'),
                'message': 'Order placed successfully',
                'raw_response': response
            }

        return response

    def _build_order_payload(self, order_data, preview=True):
        """
        Build XML payload for order

        Args:
            order_data: Order details
            preview: Whether this is a preview request

        Returns:
            XML string payload
        """
        client_order_id = str(random.randint(1000000000, 9999999999))

        # Determine price type and limit price
        price_type = order_data.get('priceType', 'MARKET')
        limit_price = order_data.get('limitPrice', '')
        if price_type == 'MARKET':
            limit_price = ''

        order_term = order_data.get('orderTerm', 'GOOD_FOR_DAY')

        # For sandbox, limit orders need a dummy limit price
        if price_type == 'LIMIT' and not limit_price:
            limit_price = '100.00'  # Will be replaced by actual price in preview

        request_type = 'PreviewOrderRequest' if preview else 'PlaceOrderRequest'

        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<{request_type}>
    <orderType>EQ</orderType>
    <clientOrderId>{client_order_id}</clientOrderId>
    <Order>
        <allOrNone>false</allOrNone>
        <priceType>{price_type}</priceType>
        <orderTerm>{order_term}</orderTerm>
        <marketSession>REGULAR</marketSession>
        <stopPrice></stopPrice>
        <limitPrice>{limit_price}</limitPrice>
        <Instrument>
            <Product>
                <securityType>EQ</securityType>
                <symbol>{order_data.get('symbol', '').upper()}</symbol>
            </Product>
            <orderAction>{order_data.get('orderAction', 'BUY')}</orderAction>
            <quantityType>QUANTITY</quantityType>
            <quantity>{order_data.get('quantity', 1)}</quantity>
        </Instrument>
    </Order>
</{request_type}>"""

        return payload

    def get_orders(self, account_id_key, status='OPEN'):
        """
        Get orders for an account

        Args:
            account_id_key: Account ID key
            status: Order status (OPEN, EXECUTED, CANCELLED, etc.)

        Returns:
            list of orders
        """
        params = {'status': status}
        response = self._make_request(
            'GET',
            f'/v1/accounts/{account_id_key}/orders.json',
            params=params
        )

        orders = []
        if 'OrdersResponse' in response:
            if 'Order' in response['OrdersResponse']:
                orders = response['OrdersResponse']['Order']

        return orders

    def cancel_order(self, account_id_key, order_id):
        """
        Cancel an open order

        Args:
            account_id_key: Account ID key
            order_id: Order ID to cancel

        Returns:
            dict with cancellation result
        """
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<CancelOrderRequest>
    <orderId>{order_id}</orderId>
</CancelOrderRequest>"""

        headers = {
            'Content-Type': 'application/xml',
            'consumerKey': self.consumer_key
        }

        response = self._make_request(
            'PUT',
            f'/v1/accounts/{account_id_key}/orders/cancel.json',
            data=payload,
            headers=headers
        )

        if 'CancelOrderResponse' in response:
            return {
                'order_id': response['CancelOrderResponse'].get('orderId'),
                'message': 'Order cancelled successfully'
            }

        return response

    def get_environment(self):
        """Get current environment (sandbox/production)"""
        return 'SANDBOX' if USE_SANDBOX else 'PRODUCTION'
