"""
E*TRADE Trading System - Flask Server

A simple web-based trading interface for E*TRADE
"""
import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from config import SECRET_KEY, USE_SANDBOX
from etrade_client import ETradeClient
from token_manager import get_token_manager
from bracket_manager import get_bracket_manager, PendingBracket, BracketState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Store request tokens temporarily during auth flow
_request_tokens = {}

# Store OAuth sessions for callback-based auth (OAuth1Session objects)
_oauth_sessions = {}

# Store pending profit orders (in memory - will be lost on restart)
# Format: {order_id: {symbol, quantity, profit_offset_type, profit_offset, account_id_key, opening_side}}
_pending_profit_orders = {}


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Main trading UI"""
    return render_template('index.html',
                           sandbox_mode=USE_SANDBOX,
                           environment='SANDBOX' if USE_SANDBOX else 'PRODUCTION')


# ==================== AUTH API ====================

@app.route('/api/auth/status')
def auth_status():
    """Check authentication status"""
    token_manager = get_token_manager()
    status = token_manager.get_token_status()

    return jsonify({
        'authenticated': status['authenticated'],
        'environment': 'SANDBOX' if USE_SANDBOX else 'PRODUCTION',
        'message': status.get('message', ''),
        'expires_at': status.get('expires_at', '')
    })


@app.route('/api/auth/login', methods=['POST'])
def start_login():
    """Start OAuth login flow - get authorization URL

    Supports two modes:
    1. Callback mode (use_callback=True): User is redirected back automatically
    2. OOB mode (use_callback=False): User manually enters verification code
    """
    try:
        # Handle both JSON and empty POST requests
        try:
            data = request.get_json(silent=True) or {}
        except:
            data = {}
        use_callback = data.get('use_callback', False)

        client = ETradeClient()
        auth_data = client.get_authorization_url(use_callback=use_callback)

        # Store request tokens for later use
        import secrets
        flow_id = secrets.token_urlsafe(16)

        if use_callback:
            # Store the OAuth session for callback mode
            _oauth_sessions[flow_id] = client._oauth_session
            logger.info(f"Stored OAuth1Session for callback flow_id={flow_id}")
        else:
            # Store tokens for OOB mode
            _request_tokens[flow_id] = {
                'request_token': auth_data['request_token'],
                'request_token_secret': auth_data['request_token_secret']
            }

        return jsonify({
            'success': True,
            'authorize_url': auth_data['authorize_url'],
            'flow_id': flow_id,
            'callback_mode': use_callback,
            'message': 'Please visit the URL and authorize the application'
        })

    except Exception as e:
        logger.error(f"Login start failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/verify', methods=['POST'])
def verify_code():
    """Verify OAuth code and complete authentication (OOB mode)"""
    try:
        data = request.get_json()
        verifier_code = data.get('verifier_code', '').strip()
        flow_id = data.get('flow_id', '')

        if not verifier_code:
            return jsonify({'success': False, 'error': 'Verification code is required'}), 400

        if flow_id not in _request_tokens:
            return jsonify({'success': False, 'error': 'Invalid or expired flow. Please start over.'}), 400

        # Get stored request tokens
        tokens = _request_tokens.pop(flow_id)

        # Complete authentication
        client = ETradeClient()
        result = client.complete_authentication(
            verifier_code,
            tokens['request_token'],
            tokens['request_token_secret']
        )

        # Save tokens to storage
        token_manager = get_token_manager()
        token_manager.save_tokens(
            result['access_token'],
            result['access_token_secret']
        )

        return jsonify({
            'success': True,
            'message': 'Authentication successful! You can now place orders.'
        })

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/callback')
def auth_callback():
    """
    OAuth callback endpoint - receives verifier from E*TRADE (callback mode)

    E*TRADE redirects here with: ?oauth_token=xxx&oauth_verifier=xxx
    This is called automatically when callback URL is registered with E*TRADE.
    """
    try:
        oauth_token = request.args.get('oauth_token')
        oauth_verifier = request.args.get('oauth_verifier')
        flow_id = request.args.get('state')  # We may pass flow_id as state

        logger.info(f"=" * 60)
        logger.info(f"OAUTH CALLBACK RECEIVED")
        logger.info(f"oauth_token: {oauth_token[:30] if oauth_token else 'None'}...")
        logger.info(f"oauth_verifier: {oauth_verifier}")
        logger.info(f"state/flow_id: {flow_id}")
        logger.info(f"=" * 60)

        if not oauth_verifier:
            logger.error("No verifier received in callback")
            return redirect(url_for('index', error='No+verifier+received+from+E*TRADE'))

        # Try to find the OAuth session
        client = ETradeClient()

        if flow_id and flow_id in _oauth_sessions:
            # Use stored OAuth session
            logger.info(f"Found OAuth session for flow_id={flow_id}")
            client._oauth_session = _oauth_sessions.pop(flow_id)
            result = client.complete_authentication(oauth_verifier)
        else:
            # Fallback: try to find any pending session
            if _oauth_sessions:
                logger.info("Using first available OAuth session")
                flow_id = list(_oauth_sessions.keys())[0]
                client._oauth_session = _oauth_sessions.pop(flow_id)
                result = client.complete_authentication(oauth_verifier)
            else:
                logger.error("No OAuth session found for callback")
                return redirect(url_for('index', error='Session+expired.+Please+try+again.'))

        # Save tokens to storage
        token_manager = get_token_manager()
        token_manager.save_tokens(
            result['access_token'],
            result['access_token_secret']
        )

        logger.info("Callback authentication successful!")

        # Redirect to main page with success
        return redirect(url_for('index', auth_success='true'))

    except Exception as e:
        logger.error(f"Callback authentication failed: {e}")
        return redirect(url_for('index', error=str(e).replace(' ', '+')))


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout and clear tokens"""
    token_manager = get_token_manager()
    token_manager.delete_tokens()

    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })


# ==================== ACCOUNT API ====================

@app.route('/api/accounts')
def get_accounts():
    """Get list of accounts"""
    try:
        client = _get_authenticated_client()
        accounts = client.get_accounts()

        # Simplify response
        result = []
        for acc in accounts:
            result.append({
                'account_id': acc.get('accountId'),
                'account_id_key': acc.get('accountIdKey'),
                'description': acc.get('accountDesc', '').strip(),
                'type': acc.get('institutionType'),
                'status': acc.get('accountStatus')
            })

        return jsonify({'success': True, 'accounts': result})

    except Exception as e:
        logger.error(f"Get accounts failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<account_id_key>/balance')
def get_balance(account_id_key):
    """Get account balance"""
    try:
        client = _get_authenticated_client()
        balance = client.get_account_balance(account_id_key)

        # Extract key balance info
        result = {
            'account_id': balance.get('accountId'),
            'description': balance.get('accountDescription'),
            'net_account_value': None,
            'cash_available': None,
            'margin_buying_power': None
        }

        if 'Computed' in balance:
            comp = balance['Computed']
            if 'RealTimeValues' in comp:
                result['net_account_value'] = comp['RealTimeValues'].get('totalAccountValue')
            result['cash_available'] = comp.get('cashBuyingPower')
            result['margin_buying_power'] = comp.get('marginBuyingPower')

        return jsonify({'success': True, 'balance': result})

    except Exception as e:
        logger.error(f"Get balance failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<account_id_key>/portfolio')
def get_portfolio(account_id_key):
    """Get portfolio positions"""
    try:
        client = _get_authenticated_client()
        positions = client.get_portfolio(account_id_key)

        # Simplify positions
        result = []
        for pos in positions:
            result.append({
                'symbol': pos.get('symbolDescription'),
                'quantity': pos.get('quantity'),
                'price_paid': pos.get('pricePaid'),
                'market_value': pos.get('marketValue'),
                'total_gain': pos.get('totalGain'),
                'last_price': pos.get('Quick', {}).get('lastTrade') if 'Quick' in pos else None
            })

        return jsonify({'success': True, 'positions': result})

    except Exception as e:
        logger.error(f"Get portfolio failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== MARKET API ====================

@app.route('/api/quote/<symbol>')
def get_quote(symbol):
    """Get market quote for a symbol"""
    try:
        client = _get_authenticated_client()
        quote = client.get_quote(symbol)

        # Extract useful quote data
        result = {
            'symbol': symbol.upper(),
            'last_price': None,
            'bid': None,
            'ask': None,
            'bid_size': None,
            'ask_size': None,
            'change': None,
            'change_percent': None,
            'volume': None,
            'high': None,
            'low': None,
            'open': None,
            'previous_close': None
        }

        # Handle None response
        if quote is None:
            return jsonify({'success': False, 'error': 'No quote data returned from API'}), 500

        # Check for error in response
        if isinstance(quote, dict):
            if 'QuoteResponse' in quote and quote['QuoteResponse'] is not None:
                qr = quote['QuoteResponse']
                if 'Messages' in qr and qr['Messages'] is not None:
                    if 'Message' in qr['Messages']:
                        msg = qr['Messages']['Message']
                        if isinstance(msg, list) and len(msg) > 0:
                            return jsonify({'success': False, 'error': msg[0].get('description', 'Quote error')}), 500

            if 'All' in quote and quote['All'] is not None:
                all_data = quote['All']
                result['last_price'] = all_data.get('lastTrade')
                result['bid'] = all_data.get('bid')
                result['ask'] = all_data.get('ask')
                result['bid_size'] = all_data.get('bidSize')
                result['ask_size'] = all_data.get('askSize')
                result['change'] = all_data.get('changeClose')
                result['change_percent'] = all_data.get('changeClosePercentage')
                result['volume'] = all_data.get('totalVolume')
                result['high'] = all_data.get('high')
                result['low'] = all_data.get('low')
                result['open'] = all_data.get('open')
                result['previous_close'] = all_data.get('previousClose')

            if 'Product' in quote and quote['Product'] is not None:
                result['symbol'] = quote['Product'].get('symbol', symbol.upper())

        return jsonify({'success': True, 'quote': result})

    except Exception as e:
        logger.error(f"Get quote failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== ORDER API ====================

@app.route('/api/orders/preview', methods=['POST'])
def preview_order():
    """Preview an order before placing"""
    try:
        client = _get_authenticated_client()
        data = request.get_json()

        # Validate required fields
        account_id_key = data.get('account_id_key')
        if not account_id_key:
            return jsonify({'success': False, 'error': 'account_id_key is required'}), 400

        symbol = data.get('symbol', '').upper()
        if not symbol:
            return jsonify({'success': False, 'error': 'symbol is required'}), 400

        quantity = int(data.get('quantity', 0))
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'quantity must be positive'}), 400

        # Get quote for price if needed
        price_type = data.get('priceType', 'MARKET').upper()
        limit_price = data.get('limitPrice')

        # If using BID/ASK, fetch current quote
        limit_price_source = data.get('limitPriceSource', 'manual')
        if price_type == 'LIMIT' and limit_price_source in ['bid', 'ask']:
            quote = client.get_quote(symbol)
            if 'All' in quote:
                if limit_price_source == 'bid':
                    limit_price = quote['All'].get('bid')
                else:
                    limit_price = quote['All'].get('ask')

            if not limit_price:
                return jsonify({
                    'success': False,
                    'error': f'Could not fetch {limit_price_source} price for {symbol}'
                }), 400

        # Build order data
        order_data = {
            'symbol': symbol,
            'quantity': quantity,
            'orderAction': data.get('side', 'BUY').upper(),
            'priceType': price_type,
            'orderTerm': data.get('orderTerm', 'GOOD_FOR_DAY'),
            'limitPrice': str(limit_price) if limit_price else ''
        }

        # Preview order
        result = client.preview_order(account_id_key, order_data)

        return jsonify({
            'success': True,
            'preview': {
                'preview_id': result.get('preview_id'),
                'symbol': symbol,
                'quantity': quantity,
                'action': order_data['orderAction'],
                'price_type': price_type,
                'limit_price': limit_price,
                'estimated_commission': result.get('estimated_commission'),
                'estimated_total': result.get('estimated_total'),
                'message': 'Preview generated successfully'
            }
        })

    except Exception as e:
        logger.error(f"Preview order failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/place', methods=['POST'])
def place_order():
    """Place an order (with automatic preview as required by E*TRADE)"""
    try:
        client = _get_authenticated_client()
        data = request.get_json()

        # Validate required fields
        account_id_key = data.get('account_id_key')
        if not account_id_key:
            return jsonify({'success': False, 'error': 'account_id_key is required'}), 400

        symbol = data.get('symbol', '').upper()
        if not symbol:
            return jsonify({'success': False, 'error': 'symbol is required'}), 400

        quantity = int(data.get('quantity', 0))
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'quantity must be positive'}), 400

        side = data.get('side', 'BUY').upper()
        if side not in ['BUY', 'SELL', 'BUY_TO_COVER', 'SELL_SHORT']:
            return jsonify({'success': False, 'error': 'Invalid side'}), 400

        price_type = data.get('priceType', 'MARKET').upper()
        limit_price = data.get('limitPrice')
        limit_price_source = data.get('limitPriceSource', 'manual')

        # Profit target offset (optional)
        profit_offset_type = data.get('profit_offset_type')  # 'dollar' or 'percent'
        profit_offset = data.get('profit_offset')  # numeric offset value
        fill_timeout = data.get('fill_timeout', 15)  # seconds to wait for fill

        # Fetch price if using BID/ASK
        if price_type == 'LIMIT' and limit_price_source in ['bid', 'ask']:
            quote = client.get_quote(symbol)
            if 'All' in quote:
                if limit_price_source == 'bid':
                    limit_price = quote['All'].get('bid')
                else:
                    limit_price = quote['All'].get('ask')

            if not limit_price:
                return jsonify({
                    'success': False,
                    'error': f'Could not fetch {limit_price_source} price for {symbol}'
                }), 400

        # Build order data
        order_data = {
            'symbol': symbol,
            'quantity': quantity,
            'orderAction': side,
            'priceType': price_type,
            'orderTerm': data.get('orderTerm', 'GOOD_FOR_DAY'),
            'limitPrice': str(limit_price) if limit_price else ''
        }

        # Check if we should skip preview
        skip_preview = data.get('skipPreview', False)

        if skip_preview:
            # Place directly without preview
            logger.info(f"Placing order WITHOUT preview: {symbol} {side} {quantity} @ {price_type}")
            result = client.place_order(
                account_id_key,
                order_data,
                preview_id=None,
                client_order_id=None
            )
            preview_result = {}  # No preview data
        else:
            # STEP 1: Preview the order first (E*TRADE requirement)
            logger.info(f"Previewing order: {symbol} {side} {quantity} @ {price_type}")
            preview_result = client.preview_order(account_id_key, order_data)

            preview_id = preview_result.get('preview_id')
            client_order_id = preview_result.get('client_order_id')

            if not preview_id:
                raise Exception('Preview failed - no preview_id returned from E*TRADE')

            logger.info(f"Preview successful, preview_id={preview_id}, client_order_id={client_order_id}")

            # STEP 2: Place the order with preview data
            logger.info(f"Placing order with preview_id={preview_id}")
            result = client.place_order(
                account_id_key,
                order_data,
                preview_id=preview_id,
                client_order_id=client_order_id
            )

        order_id = result.get('order_id')

        # If profit offset is set, store the pending profit order
        if profit_offset_type and profit_offset and order_id:
            _pending_profit_orders[order_id] = {
                'symbol': symbol,
                'quantity': quantity,
                'profit_offset_type': profit_offset_type,  # 'dollar' or 'percent'
                'profit_offset': float(profit_offset),
                'account_id_key': account_id_key,
                'opening_side': side,
                'status': 'waiting',
                'created_at': datetime.utcnow().isoformat()
            }
            logger.info(f"Stored pending profit order for order_id={order_id}, offset={profit_offset} ({profit_offset_type})")

        # If bracket order is enabled, create pending bracket
        bracket_enabled = data.get('bracket_enabled', False)
        bracket_response = None

        if bracket_enabled and order_id:
            bracket_manager = get_bracket_manager()

            bracket = PendingBracket(
                opening_order_id=order_id,
                symbol=symbol,
                quantity=quantity,
                account_id_key=account_id_key,
                opening_side=side,

                # Confirmation config
                confirmation_type=data.get('bracket_confirmation_type', 'dollar'),
                confirmation_offset=float(data.get('bracket_confirmation_offset', 0)),

                # Stop loss config
                stop_loss_type=data.get('bracket_stop_type', 'dollar'),
                stop_loss_offset=float(data.get('bracket_stop_offset', 0)),

                # Profit config
                profit_type=data.get('bracket_profit_type', 'dollar'),
                profit_offset=float(data.get('bracket_profit_offset', 0)),

                # Timeouts
                fill_timeout=int(data.get('fill_timeout', 15)),
                confirmation_timeout=int(data.get('bracket_confirmation_timeout', 300))
            )

            bracket_manager.add_bracket(bracket)
            bracket_response = {
                'enabled': True,
                'confirmation_type': bracket.confirmation_type,
                'confirmation_offset': bracket.confirmation_offset,
                'stop_loss_type': bracket.stop_loss_type,
                'stop_loss_offset': bracket.stop_loss_offset,
                'profit_type': bracket.profit_type,
                'profit_offset': bracket.profit_offset,
                'fill_timeout': bracket.fill_timeout,
                'confirmation_timeout': bracket.confirmation_timeout
            }
            logger.info(f"Created bracket for order {order_id}: confirm {bracket.confirmation_offset}({bracket.confirmation_type}), "
                       f"stop {bracket.stop_loss_offset}({bracket.stop_loss_type}), profit {bracket.profit_offset}({bracket.profit_type})")

        return jsonify({
            'success': True,
            'order': {
                'order_id': order_id,
                'symbol': symbol,
                'quantity': quantity,
                'side': side,
                'price_type': price_type,
                'limit_price': limit_price,
                'estimated_commission': preview_result.get('estimated_commission'),
                'message': result.get('message', 'Order placed successfully'),
                'profit_offset_type': profit_offset_type,
                'profit_offset': profit_offset,
                'bracket': bracket_response
            }
        })

    except Exception as e:
        logger.error(f"Place order failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/<account_id_key>')
def get_orders(account_id_key):
    """Get orders for an account"""
    try:
        client = _get_authenticated_client()
        status = request.args.get('status', 'OPEN')

        orders = client.get_orders(account_id_key, status)

        # Simplify orders
        result = []
        for order in orders:
            order_info = {
                'order_id': order.get('orderId'),
                'order_type': order.get('orderType'),
                'status': None,
                'symbol': None,
                'action': None,
                'quantity': None,
                'price_type': None,
                'limit_price': None
            }

            if 'OrderDetail' in order:
                for detail in order['OrderDetail']:
                    order_info['status'] = detail.get('status')
                    order_info['price_type'] = detail.get('priceType')
                    order_info['limit_price'] = detail.get('limitPrice')

                    if 'Instrument' in detail:
                        for inst in detail['Instrument']:
                            order_info['symbol'] = inst.get('Product', {}).get('symbol')
                            order_info['action'] = inst.get('orderAction')
                            order_info['quantity'] = inst.get('orderedQuantity')

            result.append(order_info)

        return jsonify({'success': True, 'orders': result})

    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/<account_id_key>/<order_id>/cancel', methods=['POST'])
def cancel_order(account_id_key, order_id):
    """Cancel an order"""
    try:
        client = _get_authenticated_client()
        result = client.cancel_order(account_id_key, order_id)

        # Also remove any pending profit order for this order
        # Fix: order_id from URL is string, need to match with integer key
        matching_key = None
        for k in _pending_profit_orders.keys():
            if str(k) == str(order_id):
                matching_key = k
                break
        if matching_key:
            del _pending_profit_orders[matching_key]
            logger.info(f"Removed pending profit order for cancelled order_id={order_id}")

        return jsonify({
            'success': True,
            'order_id': result.get('order_id'),
            'message': result.get('message', 'Order cancelled')
        })

    except Exception as e:
        logger.error(f"Cancel order failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== PENDING PROFIT ORDERS API ====================

@app.route('/api/orders/pending-profits')
def get_pending_profits():
    """Get list of pending profit orders"""
    pending_list = []
    for order_id, profit_order in _pending_profit_orders.items():
        pending_list.append({
            'order_id': order_id,
            'symbol': profit_order['symbol'],
            'quantity': profit_order['quantity'],
            'profit_offset_type': profit_order['profit_offset_type'],
            'profit_offset': profit_order['profit_offset'],
            'status': profit_order['status'],
            'created_at': profit_order.get('created_at', '')
        })

    return jsonify({
        'success': True,
        'pending_profits': pending_list
    })


@app.route('/api/orders/<account_id_key>/check-fill/<order_id>')
def check_single_order_fill(account_id_key, order_id):
    """
    Check if a specific order is filled and place profit order if so.
    Called by frontend polling for automatic fill detection.
    """
    try:
        logger.info(f"Check-fill called for order_id={order_id}, account={account_id_key}")
        logger.info(f"Pending profit orders keys: {list(_pending_profit_orders.keys())}")

        client = _get_authenticated_client()

        # Check if this order has a pending profit target
        # Fix: Convert both to strings for comparison (order_id from URL is string, stored key may be int)
        order_id_str = str(order_id)
        matching_key = None
        for k in _pending_profit_orders.keys():
            if str(k) == order_id_str:
                matching_key = k
                break

        if not matching_key:
            logger.warning(f"No matching profit target for order_id={order_id}")
            return jsonify({
                'success': True,
                'filled': False,
                'message': 'No profit target for this order'
            })

        logger.info(f"Found matching profit target with key={matching_key}")
        profit_order = _pending_profit_orders[matching_key]

        if profit_order['status'] != 'waiting':
            logger.warning(f"Profit order status is {profit_order['status']}, not waiting")
            return jsonify({
                'success': True,
                'filled': False,
                'message': f"Profit order status: {profit_order['status']}"
            })

        # Get order details to check status and fill price
        orders = client.get_orders(account_id_key, status='EXECUTED')
        logger.info(f"Found {len(orders)} EXECUTED orders")

        order_filled = False
        fill_price = None

        for order in orders:
            logger.debug(f"Checking order {order.get('orderId')} against {order_id}")
            if str(order.get('orderId')) == str(order_id):
                order_filled = True
                logger.info(f"Order {order_id} found in EXECUTED orders!")

                # Get fill price from Instrument.averageExecutionPrice (per E*TRADE API docs)
                # https://apisb.etrade.com/docs/api/order/api-order-v1.html#/definition/getOrders
                if 'OrderDetail' in order:
                    for detail in order['OrderDetail']:
                        if 'Instrument' in detail:
                            for inst in detail['Instrument']:
                                # averageExecutionPrice is the correct field per API docs
                                if inst.get('averageExecutionPrice'):
                                    fill_price = float(inst.get('averageExecutionPrice'))
                                    logger.info(f"Fill price from Instrument.averageExecutionPrice: {fill_price}")
                                    break
                                # Fallback to other field names just in case
                                elif inst.get('executedPrice'):
                                    fill_price = float(inst.get('executedPrice'))
                                    logger.info(f"Fill price from Instrument.executedPrice: {fill_price}")
                                    break
                            if fill_price is not None:
                                break
                break

        if not order_filled:
            return jsonify({
                'success': True,
                'filled': False,
                'message': 'Order not yet filled'
            })

        # Safety check - if fill_price is still None, we can't place profit order
        if fill_price is None:
            logger.error(f"Order {order_id} EXECUTED but executedPrice NOT FOUND in API response!")
            logger.error(f"This is a critical issue - executedPrice MUST be available for filled orders")
            return jsonify({
                'success': True,
                'filled': True,
                'fill_price': None,
                'profit_order_placed': False,
                'error': 'Order executed but executedPrice not found in API response - check logs for full JSON structure'
            })

        # Calculate profit price from fill price + offset
        profit_offset_type = profit_order['profit_offset_type']
        profit_offset = profit_order['profit_offset']

        if profit_offset_type == 'dollar':
            # For BUY: profit = fill + offset (sell higher)
            # For SELL_SHORT: profit = fill - offset (buy lower)
            if profit_order['opening_side'] in ['BUY', 'BUY_TO_COVER']:
                profit_price = fill_price + profit_offset
            else:
                profit_price = fill_price - profit_offset
        else:  # percent
            if profit_order['opening_side'] in ['BUY', 'BUY_TO_COVER']:
                profit_price = fill_price * (1 + profit_offset / 100)
            else:
                profit_price = fill_price * (1 - profit_offset / 100)

        logger.info(f"Order {order_id} filled at {fill_price}, profit price calculated: {profit_price}")

        # Determine closing side
        opening_side = profit_order['opening_side']
        if opening_side in ['BUY', 'BUY_TO_COVER']:
            closing_side = 'SELL'
        else:
            closing_side = 'BUY'

        # Place the profit order
        profit_order_data = {
            'symbol': profit_order['symbol'],
            'quantity': profit_order['quantity'],
            'orderAction': closing_side,
            'priceType': 'LIMIT',
            'orderTerm': 'GOOD_FOR_DAY',
            'limitPrice': str(round(profit_price, 2))
        }

        try:
            # Preview first
            preview_result = client.preview_order(account_id_key, profit_order_data)
            preview_id = preview_result.get('preview_id')

            if preview_id:
                # Place the profit order
                result = client.place_order(
                    account_id_key,
                    profit_order_data,
                    preview_id=preview_id,
                    client_order_id=preview_result.get('client_order_id')
                )

                logger.info(f"Placed profit order for {profit_order['symbol']} @ ${profit_price}")

                # Update status - use matching_key (int) not order_id (string)
                _pending_profit_orders[matching_key]['status'] = 'placed'

                return jsonify({
                    'success': True,
                    'filled': True,
                    'fill_price': fill_price,
                    'profit_price': round(profit_price, 2),
                    'profit_order_placed': True,
                    'message': f"Filled at {fill_price}, profit order placed at {profit_price}"
                })
            else:
                # Preview failed - no preview_id returned
                logger.error(f"Preview failed for profit order - no preview_id returned")
                _pending_profit_orders[matching_key]['status'] = 'error: preview failed'
                return jsonify({
                    'success': True,
                    'filled': True,
                    'fill_price': fill_price,
                    'profit_order_placed': False,
                    'error': 'Preview failed - no preview_id returned'
                })

        except Exception as e:
            logger.error(f"Failed to place profit order: {e}")
            _pending_profit_orders[matching_key]['status'] = f'error: {str(e)}'
            return jsonify({
                'success': True,
                'filled': True,
                'fill_price': fill_price,
                'profit_order_placed': False,
                'error': str(e)
            })

    except Exception as e:
        logger.error(f"Check fill failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/check-fills', methods=['POST'])
def check_fills_and_place_profits():
    """
    Check for filled orders and place corresponding profit orders.
    This is a manual backup trigger - the frontend now polls automatically.
    """
    try:
        client = _get_authenticated_client()
        data = request.get_json()
        account_id_key = data.get('account_id_key')

        if not account_id_key:
            return jsonify({'success': False, 'error': 'account_id_key is required'}), 400

        # Get all orders (EXECUTED status to find fills)
        try:
            executed_orders = client.get_orders(account_id_key, status='EXECUTED')
        except Exception as e:
            logger.warning(f"Could not fetch executed orders: {e}")
            executed_orders = []

        placed_orders = []
        checked_count = 0
        placed_count = 0

        # Check each pending profit order
        for order_id, profit_order in list(_pending_profit_orders.items()):
            if profit_order['account_id_key'] != account_id_key:
                continue

            if profit_order['status'] != 'waiting':
                continue

            checked_count += 1

            # Check if the opening order has been executed
            order_filled = False
            fill_price = None
            for executed in executed_orders:
                if str(executed.get('orderId')) == str(order_id):
                    order_filled = True
                    # Get fill price from OrderDetail
                    if 'OrderDetail' in executed:
                        for detail in executed['OrderDetail']:
                            if detail.get('executedPrice'):
                                fill_price = float(detail.get('executedPrice'))
                                break
                    break

            if order_filled:
                # Calculate profit price from fill price + offset
                profit_offset_type = profit_order['profit_offset_type']
                profit_offset = profit_order['profit_offset']

                # If we couldn't get fill price, use a default
                if fill_price is None:
                    logger.warning(f"Could not get fill price for order {order_id}, using 0")
                    fill_price = 0

                if profit_offset_type == 'dollar':
                    if profit_order['opening_side'] in ['BUY', 'BUY_TO_COVER']:
                        profit_price = fill_price + profit_offset
                    else:
                        profit_price = fill_price - profit_offset
                else:  # percent
                    if profit_order['opening_side'] in ['BUY', 'BUY_TO_COVER']:
                        profit_price = fill_price * (1 + profit_offset / 100)
                    else:
                        profit_price = fill_price * (1 - profit_offset / 100)

                # Determine closing side
                opening_side = profit_order['opening_side']
                if opening_side in ['BUY', 'BUY_TO_COVER']:
                    closing_side = 'SELL'
                else:
                    closing_side = 'BUY'

                # Place the profit order
                profit_order_data = {
                    'symbol': profit_order['symbol'],
                    'quantity': profit_order['quantity'],
                    'orderAction': closing_side,
                    'priceType': 'LIMIT',
                    'orderTerm': 'GOOD_FOR_DAY',
                    'limitPrice': str(round(profit_price, 2))
                }

                try:
                    # Preview first
                    preview_result = client.preview_order(account_id_key, profit_order_data)
                    preview_id = preview_result.get('preview_id')

                    if preview_id:
                        # Place the profit order
                        result = client.place_order(
                            account_id_key,
                            profit_order_data,
                            preview_id=preview_id,
                            client_order_id=preview_result.get('client_order_id')
                        )

                        placed_orders.append({
                            'symbol': profit_order['symbol'],
                            'quantity': profit_order['quantity'],
                            'side': closing_side,
                            'fill_price': fill_price,
                            'limit_price': round(profit_price, 2),
                            'order_id': result.get('order_id')
                        })
                        placed_count += 1

                        # Remove from pending
                        _pending_profit_orders[order_id]['status'] = 'placed'
                        logger.info(f"Placed profit order for {profit_order['symbol']} @ ${profit_price} (fill: {fill_price})")

                except Exception as e:
                    logger.error(f"Failed to place profit order for {profit_order['symbol']}: {e}")
                    _pending_profit_orders[order_id]['status'] = f'error: {str(e)}'

        return jsonify({
            'success': True,
            'checked_count': checked_count,
            'placed_count': placed_count,
            'placed_orders': placed_orders
        })

    except Exception as e:
        logger.error(f"Check fills failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== BRACKET ORDER API ====================

@app.route('/api/brackets', methods=['GET'])
def get_brackets():
    """Get all pending bracket orders"""
    bracket_manager = get_bracket_manager()
    brackets = bracket_manager.get_all_brackets()

    result = []
    for order_id, bracket in brackets.items():
        result.append(bracket.to_dict())

    return jsonify({
        'success': True,
        'brackets': result,
        'count': len(result)
    })


@app.route('/api/brackets/<int:opening_order_id>', methods=['GET'])
def get_bracket_status(opening_order_id):
    """Get status of a specific bracket order"""
    bracket_manager = get_bracket_manager()
    bracket = bracket_manager.get_bracket(opening_order_id)

    if not bracket:
        return jsonify({
            'success': False,
            'error': f'No bracket found for order {opening_order_id}'
        }), 404

    return jsonify({
        'success': True,
        'bracket': bracket.to_dict()
    })


@app.route('/api/brackets/<int:opening_order_id>/check-fill', methods=['GET'])
def check_bracket_fill(opening_order_id):
    """
    Check if opening order is filled and update bracket state.
    Called by frontend polling during PENDING_FILL state.
    """
    try:
        bracket_manager = get_bracket_manager()
        bracket = bracket_manager.get_bracket(opening_order_id)

        if not bracket:
            return jsonify({
                'success': False,
                'error': f'No bracket found for order {opening_order_id}'
            }), 404

        if bracket.state != BracketState.PENDING_FILL:
            return jsonify({
                'success': True,
                'filled': bracket.state != BracketState.PENDING_FILL,
                'state': bracket.state,
                'bracket': bracket.to_dict()
            })

        client = _get_authenticated_client()

        # Check if order is filled
        orders = client.get_orders(bracket.account_id_key, status='EXECUTED')

        fill_price = None
        for order in orders:
            if str(order.get('orderId')) == str(opening_order_id):
                # Get fill price
                if 'OrderDetail' in order:
                    for detail in order['OrderDetail']:
                        if 'Instrument' in detail:
                            for inst in detail['Instrument']:
                                if inst.get('averageExecutionPrice'):
                                    fill_price = float(inst.get('averageExecutionPrice'))
                                    break
                            if fill_price:
                                break
                break

        if fill_price:
            bracket_manager.mark_filled(opening_order_id, fill_price)
            logger.info(f"Bracket opening order {opening_order_id} filled at {fill_price}")

            return jsonify({
                'success': True,
                'filled': True,
                'fill_price': fill_price,
                'trigger_price': bracket.trigger_price,
                'state': bracket.state,
                'bracket': bracket.to_dict()
            })

        return jsonify({
            'success': True,
            'filled': False,
            'state': bracket.state,
            'bracket': bracket.to_dict()
        })

    except Exception as e:
        logger.error(f"Check bracket fill failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/brackets/<int:opening_order_id>/check-confirmation', methods=['GET'])
def check_bracket_confirmation(opening_order_id):
    """
    Check if price has reached confirmation trigger and place bracket if so.
    Called by frontend polling during WAITING_CONFIRMATION state.
    """
    try:
        bracket_manager = get_bracket_manager()
        bracket = bracket_manager.get_bracket(opening_order_id)

        if not bracket:
            return jsonify({
                'success': False,
                'error': f'No bracket found for order {opening_order_id}'
            }), 404

        if bracket.state != BracketState.WAITING_CONFIRMATION:
            return jsonify({
                'success': True,
                'confirmed': False,
                'state': bracket.state,
                'message': f'Bracket in state {bracket.state}',
                'bracket': bracket.to_dict()
            })

        # Check for confirmation timeout
        if bracket.is_confirmation_timeout():
            bracket_manager.mark_error(opening_order_id, 'Confirmation timeout - price did not reach trigger')
            return jsonify({
                'success': True,
                'confirmed': False,
                'timeout': True,
                'state': bracket.state,
                'message': 'Confirmation timeout - price did not reach trigger',
                'bracket': bracket.to_dict()
            })

        client = _get_authenticated_client()

        # Get current price
        quote = client.get_quote(bracket.symbol)
        current_price = None
        if quote and 'All' in quote:
            current_price = quote['All'].get('lastTrade')

        if not current_price:
            return jsonify({
                'success': True,
                'confirmed': False,
                'state': bracket.state,
                'message': 'Could not get current price',
                'bracket': bracket.to_dict()
            })

        # Check if confirmation reached
        if bracket.check_confirmation(current_price):
            logger.info(f"Confirmation reached for order {opening_order_id} at price {current_price}")

            # Calculate bracket prices
            stop_price, stop_limit_price, profit_limit_price = bracket.calculate_bracket_prices(current_price)

            # Place bracket orders
            try:
                # Place STOP LIMIT order
                stop_order_data = {
                    'symbol': bracket.symbol,
                    'quantity': bracket.quantity,
                    'orderAction': bracket.get_closing_side(),
                    'priceType': 'STOP_LIMIT',
                    'orderTerm': 'GOOD_FOR_DAY',
                    'stopPrice': str(stop_price),
                    'limitPrice': str(stop_limit_price)
                }

                stop_preview = client.preview_order(bracket.account_id_key, stop_order_data)
                stop_result = client.place_order(
                    bracket.account_id_key,
                    stop_order_data,
                    preview_id=stop_preview.get('preview_id'),
                    client_order_id=stop_preview.get('client_order_id')
                )
                stop_order_id = stop_result.get('order_id')

                logger.info(f"Placed STOP LIMIT order {stop_order_id} for {bracket.symbol} @ stop {stop_price}, limit {stop_limit_price}")

                # Place LIMIT order for profit target
                profit_order_data = {
                    'symbol': bracket.symbol,
                    'quantity': bracket.quantity,
                    'orderAction': bracket.get_closing_side(),
                    'priceType': 'LIMIT',
                    'orderTerm': 'GOOD_FOR_DAY',
                    'limitPrice': str(profit_limit_price)
                }

                profit_preview = client.preview_order(bracket.account_id_key, profit_order_data)
                profit_result = client.place_order(
                    bracket.account_id_key,
                    profit_order_data,
                    preview_id=profit_preview.get('preview_id'),
                    client_order_id=profit_preview.get('client_order_id')
                )
                profit_order_id = profit_result.get('order_id')

                logger.info(f"Placed LIMIT order {profit_order_id} for {bracket.symbol} @ {profit_limit_price}")

                # Update bracket state
                bracket_manager.mark_bracket_placed(opening_order_id, stop_order_id, profit_order_id)

                return jsonify({
                    'success': True,
                    'confirmed': True,
                    'bracket_placed': True,
                    'current_price': current_price,
                    'stop_order_id': stop_order_id,
                    'profit_order_id': profit_order_id,
                    'stop_price': stop_price,
                    'stop_limit_price': stop_limit_price,
                    'profit_limit_price': profit_limit_price,
                    'state': bracket.state,
                    'bracket': bracket.to_dict()
                })

            except Exception as e:
                logger.error(f"Failed to place bracket orders: {e}")
                bracket_manager.mark_error(opening_order_id, str(e))
                return jsonify({
                    'success': False,
                    'confirmed': True,
                    'bracket_placed': False,
                    'error': str(e),
                    'bracket': bracket.to_dict()
                }), 500

        return jsonify({
            'success': True,
            'confirmed': False,
            'current_price': current_price,
            'trigger_price': bracket.trigger_price,
            'fill_price': bracket.fill_price,
            'state': bracket.state,
            'bracket': bracket.to_dict()
        })

    except Exception as e:
        logger.error(f"Check bracket confirmation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/brackets/<int:opening_order_id>/check-bracket', methods=['GET'])
def check_bracket_orders(opening_order_id):
    """
    Check if either bracket order has filled and cancel the other.
    Called by frontend polling during BRACKET_PLACED state.
    """
    try:
        bracket_manager = get_bracket_manager()
        bracket = bracket_manager.get_bracket(opening_order_id)

        if not bracket:
            return jsonify({
                'success': False,
                'error': f'No bracket found for order {opening_order_id}'
            }), 404

        if bracket.state != BracketState.BRACKET_PLACED:
            return jsonify({
                'success': True,
                'state': bracket.state,
                'message': f'Bracket in state {bracket.state}',
                'bracket': bracket.to_dict()
            })

        client = _get_authenticated_client()

        # Check if stop order filled
        orders = client.get_orders(bracket.account_id_key, status='EXECUTED')
        stop_filled = False
        profit_filled = False

        for order in orders:
            order_id = order.get('orderId')
            if str(order_id) == str(bracket.stop_order_id):
                stop_filled = True
                break
            if str(order_id) == str(bracket.profit_order_id):
                profit_filled = True
                break

        if stop_filled:
            # Cancel profit order
            try:
                client.cancel_order(bracket.account_id_key, bracket.profit_order_id)
                logger.info(f"Cancelled profit order {bracket.profit_order_id} (stop filled)")
            except Exception as e:
                logger.warning(f"Could not cancel profit order: {e}")

            bracket_manager.mark_stop_filled(opening_order_id)
            return jsonify({
                'success': True,
                'stop_filled': True,
                'profit_filled': False,
                'state': bracket.state,
                'message': 'Stop loss filled - bracket complete',
                'bracket': bracket.to_dict()
            })

        if profit_filled:
            # Cancel stop order
            try:
                client.cancel_order(bracket.account_id_key, bracket.stop_order_id)
                logger.info(f"Cancelled stop order {bracket.stop_order_id} (profit filled)")
            except Exception as e:
                logger.warning(f"Could not cancel stop order: {e}")

            bracket_manager.mark_profit_filled(opening_order_id)
            return jsonify({
                'success': True,
                'stop_filled': False,
                'profit_filled': True,
                'state': bracket.state,
                'message': 'Profit target filled - bracket complete',
                'bracket': bracket.to_dict()
            })

        return jsonify({
            'success': True,
            'stop_filled': False,
            'profit_filled': False,
            'state': bracket.state,
            'bracket': bracket.to_dict()
        })

    except Exception as e:
        logger.error(f"Check bracket orders failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/brackets/<int:opening_order_id>/cancel', methods=['POST'])
def cancel_bracket(opening_order_id):
    """Cancel a bracket order and optionally the opening position"""
    try:
        bracket_manager = get_bracket_manager()
        bracket = bracket_manager.get_bracket(opening_order_id)

        if not bracket:
            return jsonify({
                'success': False,
                'error': f'No bracket found for order {opening_order_id}'
            }), 404

        client = _get_authenticated_client()
        cancelled_orders = []

        # Cancel bracket orders if placed
        if bracket.stop_order_id:
            try:
                client.cancel_order(bracket.account_id_key, bracket.stop_order_id)
                cancelled_orders.append(f'stop:{bracket.stop_order_id}')
            except Exception as e:
                logger.warning(f"Could not cancel stop order: {e}")

        if bracket.profit_order_id:
            try:
                client.cancel_order(bracket.account_id_key, bracket.profit_order_id)
                cancelled_orders.append(f'profit:{bracket.profit_order_id}')
            except Exception as e:
                logger.warning(f"Could not cancel profit order: {e}")

        # Update state
        bracket.state = BracketState.CANCELLED
        bracket.completed_at = datetime.utcnow()

        # Remove from manager
        bracket_manager.remove_bracket(opening_order_id)

        return jsonify({
            'success': True,
            'cancelled_orders': cancelled_orders,
            'message': 'Bracket cancelled'
        })

    except Exception as e:
        logger.error(f"Cancel bracket failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== HELPER FUNCTIONS ====================

def _get_authenticated_client():
    """Get an authenticated E*TRADE client"""
    token_manager = get_token_manager()
    tokens = token_manager.get_tokens()

    if not tokens:
        raise Exception('Not authenticated. Please login first.')

    client = ETradeClient()
    client.set_session(tokens['access_token'], tokens['access_token_secret'])

    return client


# ==================== HEALTH CHECK ====================

@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'environment': 'SANDBOX' if USE_SANDBOX else 'PRODUCTION'
    })


@app.route('/api/debug/test')
def debug_test():
    """Debug endpoint to test API connection"""
    try:
        client = _get_authenticated_client()

        # Test raw API call
        import requests
        url = f"{client.base_url}/v1/accounts/list.json"

        # Log session details
        session_info = {
            'has_session': client.session is not None,
            'access_token': client.access_token[:20] + '...' if client.access_token else None,
            'consumer_key': client.consumer_key[:10] + '...' if client.consumer_key else None,
            'base_url': client.base_url
        }

        # Try raw request (using OAuth1 auth)
        try:
            response = client.session.get(url, headers={'consumerkey': client.consumer_key}, auth=client._oauth)
            raw_response = {
                'status_code': response.status_code,
                'text': response.text[:500] if response.text else None
            }
        except Exception as e:
            raw_response = {'error': str(e)}

        return jsonify({
            'session_info': session_info,
            'raw_response': raw_response
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting E*TRADE Trading System on port {port}")
    logger.info(f"Environment: {'SANDBOX' if USE_SANDBOX else 'PRODUCTION'}")

    app.run(host='0.0.0.0', port=port, debug=debug)
