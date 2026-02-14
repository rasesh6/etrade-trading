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
from rauth import OAuth1Service
from requests import Session
from config import (
    get_base_url, get_credentials,
    REQUEST_TOKEN_URL, ACCESS_TOKEN_URL, AUTHORIZE_URL,
    USE_SANDBOX
)

logger = logging.getLogger(__name__)


class ETradeClient:
    """E*TRADE API Client with OAuth 1.0a support"""

    def __init__(self):
        """Initialize the E*TRADE client"""
        self.base_url = get_base_url()
        self.consumer_key, self.consumer_secret = get_credentials()
        self.session = None
        self.access_token = None
        self.access_token_secret = None

        # Initialize OAuth service
        self.oauth_service = OAuth1Service(
            name='etrade',
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            request_token_url=REQUEST_TOKEN_URL,
            access_token_url=ACCESS_TOKEN_URL,
            authorize_url=AUTHORIZE_URL,
            base_url=self.base_url
        )

    def get_authorization_url(self):
        """
        Step 1: Get request token and authorization URL

        Returns:
            dict with 'authorize_url' and 'request_token_secret'
        """
        try:
            request_token, request_token_secret = self.oauth_service.get_request_token(
                params={'oauth_callback': 'oob', 'format': 'json'}
            )

            authorize_url = AUTHORIZE_URL.format(
                self.consumer_key,
                request_token
            )

            logger.info("Generated authorization URL")

            return {
                'authorize_url': authorize_url,
                'request_token': request_token,
                'request_token_secret': request_token_secret
            }

        except Exception as e:
            logger.error(f"Failed to get authorization URL: {e}")
            raise Exception(f"Authorization URL generation failed: {str(e)}")

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
            session = self.oauth_service.get_auth_session(
                request_token,
                request_token_secret,
                params={'oauth_verifier': verifier_code}
            )

            # Extract tokens from the session
            self.session = session
            self.access_token = session.access_token
            self.access_token_secret = session.access_token_secret

            logger.info("Authentication completed successfully")

            return {
                'access_token': self.access_token,
                'access_token_secret': self.access_token_secret,
                'success': True
            }

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise Exception(f"Authentication failed: {str(e)}")

    def set_session(self, access_token, access_token_secret):
        """
        Set the OAuth session from stored tokens

        Args:
            access_token: Stored access token
            access_token_secret: Stored access token secret
        """
        self.access_token = access_token
        self.access_token_secret = access_token_secret

        # Create session with existing tokens
        self.session = OAuth1Service(
            name='etrade',
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            base_url=self.base_url
        ).get_session(access_token, access_token_secret)

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
        if not self.session:
            raise Exception("Not authenticated. Please authenticate first.")

        url = f"{self.base_url}{endpoint}"

        default_headers = {'consumerKey': self.consumer_key}
        if headers:
            default_headers.update(headers)

        try:
            if method == 'GET':
                response = self.session.get(url, params=params, headers=default_headers, header_auth=True)
            elif method == 'POST':
                response = self.session.post(url, params=params, data=data, headers=default_headers, header_auth=True)
            elif method == 'PUT':
                response = self.session.put(url, params=params, data=data, headers=default_headers, header_auth=True)
            else:
                raise Exception(f"Unsupported method: {method}")

            logger.debug(f"API Request: {method} {url}")
            logger.debug(f"Response Status: {response.status_code}")

            if response.status_code == 204:
                return {'status': 'success', 'data': None}

            if response.status_code not in [200, 201]:
                error_msg = "Unknown error"
                try:
                    error_data = response.json()
                    if 'Error' in error_data:
                        error_msg = error_data['Error'].get('message', str(error_data))
                except:
                    error_msg = response.text[:200]
                raise Exception(f"API Error ({response.status_code}): {error_msg}")

            return response.json()

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
        if 'AccountListResponse' in response:
            if 'Accounts' in response['AccountListResponse']:
                account_data = response['AccountListResponse']['Accounts']
                if 'Account' in account_data:
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

        if 'QuoteResponse' in response:
            if 'QuoteData' in response['QuoteResponse']:
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
