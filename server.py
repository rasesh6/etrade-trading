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
from trailing_stop_manager import get_trailing_stop_manager, PendingTrailingStop, TrailingStopState

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

# Store pending trailing stop limit orders (in memory - will be lost on restart)
# Format: {order_id: {symbol, quantity, trail_amount, account_id_key, opening_side, fill_timeout, stop_order_id}}
_pending_trailing_stop_limit_orders = {}


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
            # E*TRADE returns costPerShare directly - use it!
            # pricePaid is actually the same as costPerShare (per-share cost)
            # totalCost is the actual total cost
            result.append({
                'symbol': pos.get('symbolDescription'),
                'quantity': pos.get('quantity'),
                'cost_per_share': pos.get('costPerShare'),  # E*TRADE's field
                'total_cost': pos.get('totalCost'),
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

        # If trailing stop is enabled, create pending trailing stop
        trailing_stop_enabled = data.get('trailing_stop_enabled', False)
        trailing_stop_response = None

        if trailing_stop_enabled and order_id:
            trailing_stop_manager = get_trailing_stop_manager()

            trailing_stop = PendingTrailingStop(
                opening_order_id=order_id,
                symbol=symbol,
                quantity=quantity,
                account_id_key=account_id_key,
                opening_side=side,

                # Trigger config (confirmation)
                trigger_type=data.get('trailing_stop_trigger_type', 'dollar'),
                trigger_offset=float(data.get('trailing_stop_trigger_offset', 0)),

                # Stop config
                stop_type=data.get('trailing_stop_stop_type', 'dollar'),
                stop_offset=float(data.get('trailing_stop_stop_offset', 0)),

                # Timeouts
                fill_timeout=int(data.get('fill_timeout', 15)),
                confirmation_timeout=int(data.get('trailing_stop_confirmation_timeout', 300))
            )

            trailing_stop_manager.add_trailing_stop(trailing_stop)
            trailing_stop_response = {
                'enabled': True,
                'trigger_type': trailing_stop.trigger_type,
                'trigger_offset': trailing_stop.trigger_offset,
                'stop_type': trailing_stop.stop_type,
                'stop_offset': trailing_stop.stop_offset,
                'fill_timeout': trailing_stop.fill_timeout,
                'confirmation_timeout': trailing_stop.confirmation_timeout
            }
            logger.info(f"Created trailing stop for order {order_id}: trigger {trailing_stop.trigger_offset}({trailing_stop.trigger_type}), "
                       f"stop {trailing_stop.stop_offset}({trailing_stop.stop_type})")

        # If trailing stop limit is enabled, create pending trailing stop limit
        trailing_stop_limit_enabled = data.get('trailing_stop_limit_enabled', False)
        trailing_stop_limit_response = None

        if trailing_stop_limit_enabled and order_id:
            tsl_trigger_type = data.get('tsl_trigger_type', 'dollar')
            tsl_trigger_offset = float(data.get('tsl_trigger_offset', 0))
            tsl_trail_type = data.get('tsl_trail_type', 'dollar')
            tsl_trail_amount = float(data.get('tsl_trail_amount', 0))
            tsl_fill_timeout = int(data.get('fill_timeout', 15))
            tsl_trigger_timeout = int(data.get('tsl_trigger_timeout', 300))

            _pending_trailing_stop_limit_orders[order_id] = {
                'symbol': symbol,
                'quantity': quantity,
                'account_id_key': account_id_key,
                'opening_side': side,
                # Trigger settings (wait for price to rise before placing trailing stop)
                'trigger_type': tsl_trigger_type,
                'trigger_offset': tsl_trigger_offset,
                'trigger_timeout': tsl_trigger_timeout,
                # Trail settings (for the trailing stop order)
                'trail_type': tsl_trail_type,
                'trail_amount': tsl_trail_amount,
                # State
                'fill_timeout': tsl_fill_timeout,
                'fill_price': None,
                'trigger_price': None,
                'stop_order_id': None,
                'status': 'waiting_fill',
                'created_at': datetime.utcnow().isoformat()
            }
            trailing_stop_limit_response = {
                'enabled': True,
                'trigger_type': tsl_trigger_type,
                'trigger_offset': tsl_trigger_offset,
                'trail_type': tsl_trail_type,
                'trail_amount': tsl_trail_amount,
                'fill_timeout': tsl_fill_timeout,
                'trigger_timeout': tsl_trigger_timeout
            }
            logger.info(f"Created trailing stop limit for order {order_id}: trigger={tsl_trigger_offset}({tsl_trigger_type}), trail={tsl_trail_amount}({tsl_trail_type})")

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
                'trailing_stop': trailing_stop_response,
                'trailing_stop_limit': trailing_stop_limit_response
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
        error_msg = str(e)
        logger.error(f"Cancel order failed: {e}")

        # Error 5001 means order is being executed (likely filled!)
        if '5001' in error_msg or 'being executed' in error_msg:
            return jsonify({
                'success': False,
                'error': error_msg,
                'error_code': 5001,
                'order_likely_filled': True,
                'message': 'Order is being executed - it likely filled!'
            }), 400

        return jsonify({'success': False, 'error': error_msg}), 500


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
        # Try without status filter first to catch orders regardless of their current status
        order_filled = False
        fill_price = None
        orders_checked = []
        all_orders = []

        try:
            all_orders = client.get_orders(account_id_key, status=None)
            orders_checked.append(f"ALL:{len(all_orders)}")
            logger.info(f"Fetched {len(all_orders)} orders without status filter")
        except Exception as api_error:
            error_msg = str(api_error)
            if '500' in error_msg or 'not currently available' in error_msg:
                logger.warning(f"E*TRADE API temporarily unavailable: {error_msg}")
                return jsonify({
                    'success': True,
                    'filled': False,
                    'api_error': True,
                    'api_error_message': 'E*TRADE API temporarily unavailable, retrying...'
                })
            raise

        for order in all_orders:
            logger.debug(f"Checking order {order.get('orderId')} against {order_id}")
            if str(order.get('orderId')) == str(order_id):
                logger.info(f"Found order {order_id} in response")

                if 'OrderDetail' in order:
                    for detail in order['OrderDetail']:
                        order_status = detail.get('status', '')
                        logger.info(f"Order {order_id} status: {order_status}")

                        if 'Instrument' in detail:
                            for inst in detail['Instrument']:
                                filled_qty = int(inst.get('filledQuantity', 0))
                                ordered_qty = int(inst.get('orderedQuantity', 0))

                                logger.info(f"Order {order_id}: filled_qty={filled_qty}, ordered_qty={ordered_qty}")

                                # Only consider filled if FULLY filled (not partial)
                                if filled_qty > 0 and filled_qty >= ordered_qty:
                                    order_filled = True
                                    logger.info(f"Order {order_id} FULLY filled!")

                                    # Get fill price
                                    if inst.get('averageExecutionPrice'):
                                        fill_price = float(inst.get('averageExecutionPrice'))
                                        logger.info(f"Fill price: {fill_price}")
                                    elif inst.get('executedPrice'):
                                        fill_price = float(inst.get('executedPrice'))
                                        logger.info(f"Fill price: {fill_price}")
                                    break
                            if order_filled:
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


# ==================== TRAILING STOP API ====================

@app.route('/api/trailing-stops', methods=['GET'])
def get_trailing_stops():
    """Get all pending trailing stop orders"""
    trailing_stop_manager = get_trailing_stop_manager()
    trailing_stops = trailing_stop_manager.get_all_trailing_stops()

    result = []
    for order_id, ts in trailing_stops.items():
        result.append(ts.to_dict())

    return jsonify({
        'success': True,
        'trailing_stops': result,
        'count': len(result)
    })


@app.route('/api/trailing-stops/<int:opening_order_id>', methods=['GET'])
def get_trailing_stop_status(opening_order_id):
    """Get status of a specific trailing stop order"""
    trailing_stop_manager = get_trailing_stop_manager()
    ts = trailing_stop_manager.get_trailing_stop(opening_order_id)

    if not ts:
        return jsonify({
            'success': False,
            'error': f'No trailing stop found for order {opening_order_id}'
        }), 404

    return jsonify({
        'success': True,
        'trailing_stop': ts.to_dict()
    })


@app.route('/api/trailing-stops/<int:opening_order_id>/check-fill', methods=['GET'])
def check_trailing_stop_fill(opening_order_id):
    """
    Check if opening order is filled and update trailing stop state.
    Called by frontend polling during PENDING_FILL state.
    """
    try:
        trailing_stop_manager = get_trailing_stop_manager()
        ts = trailing_stop_manager.get_trailing_stop(opening_order_id)

        if not ts:
            return jsonify({
                'success': False,
                'error': f'No trailing stop found for order {opening_order_id}'
            }), 404

        if ts.state != TrailingStopState.PENDING_FILL:
            return jsonify({
                'success': True,
                'filled': ts.state != TrailingStopState.PENDING_FILL,
                'state': ts.state,
                'trailing_stop': ts.to_dict()
            })

        client = _get_authenticated_client()

        # Try fetching orders without status filter first, then fall back to EXECUTED
        # This handles cases where E*TRADE hasn't updated the status yet
        fill_price = None
        orders_checked = []
        all_orders = []

        # First try without status filter (gets all recent orders)
        try:
            all_orders = client.get_orders(ts.account_id_key, status=None)
            orders_checked.append(f"ALL:{len(all_orders)}")
            logger.info(f"Fetched {len(all_orders)} orders without status filter")
        except Exception as api_error:
            error_msg = str(api_error)
            logger.warning(f"Failed to fetch orders without filter: {error_msg}")
            # Fall back to EXECUTED only
            try:
                all_orders = client.get_orders(ts.account_id_key, status='EXECUTED')
                orders_checked.append(f"EXECUTED:{len(all_orders)}")
            except Exception as e2:
                if '500' in str(e2) or 'not currently available' in str(e2):
                    return jsonify({
                        'success': True,
                        'filled': False,
                        'api_error': True,
                        'api_error_message': 'E*TRADE API temporarily unavailable',
                        'state': ts.state
                    })
                raise

        for order in all_orders:
            order_id = order.get('orderId')
            logger.debug(f"Checking order {order_id} against {opening_order_id}")

            if str(order_id) == str(opening_order_id):
                logger.info(f"Found order {opening_order_id} in response")

                if 'OrderDetail' in order:
                    for detail in order['OrderDetail']:
                        order_status = detail.get('status', '')
                        logger.info(f"Order {opening_order_id} status: {order_status}")

                        if 'Instrument' in detail:
                            for inst in detail['Instrument']:
                                filled_qty = int(inst.get('filledQuantity', 0))
                                ordered_qty = int(inst.get('orderedQuantity', 0))

                                logger.info(f"Order {opening_order_id}: filled_qty={filled_qty}, ordered_qty={ordered_qty}")

                                # Only consider filled if FULLY filled (not partial)
                                if filled_qty > 0 and filled_qty >= ordered_qty:
                                    if inst.get('averageExecutionPrice'):
                                        fill_price = float(inst.get('averageExecutionPrice'))
                                        logger.info(f"Order {opening_order_id} FULLY filled at {fill_price}")
                                        break
                            if fill_price:
                                break
                break

        if fill_price:
            trailing_stop_manager.mark_filled(opening_order_id, fill_price)
            logger.info(f"Trailing stop opening order {opening_order_id} filled at {fill_price}")

            return jsonify({
                'success': True,
                'filled': True,
                'fill_price': fill_price,
                'trigger_price': ts.trigger_price,
                'state': ts.state,
                'trailing_stop': ts.to_dict(),
                'orders_checked': orders_checked
            })

        return jsonify({
            'success': True,
            'filled': False,
            'state': ts.state,
            'trailing_stop': ts.to_dict(),
            'orders_checked': orders_checked
        })

    except Exception as e:
        logger.error(f"Check trailing stop fill failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trailing-stops/<int:opening_order_id>/check-confirmation', methods=['GET'])
def check_trailing_stop_confirmation(opening_order_id):
    """
    Check if price has reached confirmation trigger and place stop if so.
    Called by frontend polling during WAITING_CONFIRMATION state.
    """
    try:
        trailing_stop_manager = get_trailing_stop_manager()
        ts = trailing_stop_manager.get_trailing_stop(opening_order_id)

        if not ts:
            return jsonify({
                'success': False,
                'error': f'No trailing stop found for order {opening_order_id}'
            }), 404

        if ts.state != TrailingStopState.WAITING_CONFIRMATION:
            return jsonify({
                'success': True,
                'confirmed': False,
                'state': ts.state,
                'message': f'Trailing stop in state {ts.state}',
                'trailing_stop': ts.to_dict()
            })

        # Check for confirmation timeout
        if ts.is_confirmation_timeout():
            trailing_stop_manager.mark_error(opening_order_id, 'Confirmation timeout - price did not reach trigger')
            return jsonify({
                'success': True,
                'confirmed': False,
                'timeout': True,
                'state': ts.state,
                'message': 'Confirmation timeout - price did not reach trigger. Position remains open.',
                'trailing_stop': ts.to_dict()
            })

        client = _get_authenticated_client()

        # Get current price
        quote = client.get_quote(ts.symbol)
        current_price = None
        if quote and 'All' in quote:
            current_price = quote['All'].get('lastTrade')

        if not current_price:
            return jsonify({
                'success': True,
                'confirmed': False,
                'state': ts.state,
                'message': 'Could not get current price',
                'trailing_stop': ts.to_dict()
            })

        # Check if confirmation reached
        if ts.check_confirmation(current_price):
            logger.info(f"Confirmation reached for order {opening_order_id} at price {current_price}")

            # Calculate stop prices
            stop_price, stop_limit_price = ts.calculate_stop_prices(current_price)

            # Place STOP LIMIT order
            try:
                stop_order_data = {
                    'symbol': ts.symbol,
                    'quantity': ts.quantity,
                    'orderAction': ts.get_closing_side(),
                    'priceType': 'STOP_LIMIT',
                    'orderTerm': 'GOOD_FOR_DAY',
                    'stopPrice': str(stop_price),
                    'limitPrice': str(stop_limit_price)
                }

                stop_preview = client.preview_order(ts.account_id_key, stop_order_data)
                stop_result = client.place_order(
                    ts.account_id_key,
                    stop_order_data,
                    preview_id=stop_preview.get('preview_id'),
                    client_order_id=stop_preview.get('client_order_id')
                )
                stop_order_id = stop_result.get('order_id')

                logger.info(f"Placed STOP LIMIT order {stop_order_id} for {ts.symbol} @ stop {stop_price}, limit {stop_limit_price}")

                # Update trailing stop state
                trailing_stop_manager.mark_stop_placed(opening_order_id, stop_order_id)

                return jsonify({
                    'success': True,
                    'confirmed': True,
                    'stop_placed': True,
                    'current_price': current_price,
                    'stop_order_id': stop_order_id,
                    'stop_price': stop_price,
                    'stop_limit_price': stop_limit_price,
                    'min_profit': ts.get_min_profit(),
                    'state': ts.state,
                    'trailing_stop': ts.to_dict()
                })

            except Exception as e:
                logger.error(f"Failed to place stop order: {e}")
                trailing_stop_manager.mark_error(opening_order_id, str(e))
                return jsonify({
                    'success': False,
                    'confirmed': True,
                    'stop_placed': False,
                    'error': str(e),
                    'trailing_stop': ts.to_dict()
                }), 500

        return jsonify({
            'success': True,
            'confirmed': False,
            'current_price': current_price,
            'trigger_price': ts.trigger_price,
            'fill_price': ts.fill_price,
            'state': ts.state,
            'trailing_stop': ts.to_dict()
        })

    except Exception as e:
        logger.error(f"Check trailing stop confirmation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trailing-stops/<int:opening_order_id>/check-stop', methods=['GET'])
def check_trailing_stop_order(opening_order_id):
    """
    Check if stop order has filled.
    Called by frontend polling during STOP_PLACED state.
    """
    try:
        trailing_stop_manager = get_trailing_stop_manager()
        ts = trailing_stop_manager.get_trailing_stop(opening_order_id)

        if not ts:
            return jsonify({
                'success': False,
                'error': f'No trailing stop found for order {opening_order_id}'
            }), 404

        if ts.state != TrailingStopState.STOP_PLACED:
            return jsonify({
                'success': True,
                'state': ts.state,
                'message': f'Trailing stop in state {ts.state}',
                'trailing_stop': ts.to_dict()
            })

        client = _get_authenticated_client()

        # Check if stop order filled
        orders = client.get_orders(ts.account_id_key, status='EXECUTED')
        stop_filled = False

        for order in orders:
            order_id = order.get('orderId')
            if str(order_id) == str(ts.stop_order_id):
                stop_filled = True
                break

        if stop_filled:
            trailing_stop_manager.mark_stop_filled(opening_order_id)
            return jsonify({
                'success': True,
                'stop_filled': True,
                'state': ts.state,
                'min_profit': ts.get_min_profit(),
                'message': f'Stop order filled - guaranteed profit of ${ts.get_min_profit():.2f}/share',
                'trailing_stop': ts.to_dict()
            })

        return jsonify({
            'success': True,
            'stop_filled': False,
            'state': ts.state,
            'trailing_stop': ts.to_dict()
        })

    except Exception as e:
        logger.error(f"Check trailing stop order failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trailing-stops/<int:opening_order_id>/cancel', methods=['POST'])
def cancel_trailing_stop(opening_order_id):
    """Cancel a trailing stop order"""
    try:
        trailing_stop_manager = get_trailing_stop_manager()
        ts = trailing_stop_manager.get_trailing_stop(opening_order_id)

        if not ts:
            return jsonify({
                'success': False,
                'error': f'No trailing stop found for order {opening_order_id}'
            }), 404

        client = _get_authenticated_client()
        cancelled_orders = []

        # Cancel stop order if placed
        if ts.stop_order_id:
            try:
                client.cancel_order(ts.account_id_key, ts.stop_order_id)
                cancelled_orders.append(f'stop:{ts.stop_order_id}')
            except Exception as e:
                logger.warning(f"Could not cancel stop order: {e}")

        # Update state
        ts.state = TrailingStopState.CANCELLED
        ts.completed_at = datetime.utcnow()

        # Remove from manager
        trailing_stop_manager.remove_trailing_stop(opening_order_id)

        return jsonify({
            'success': True,
            'cancelled_orders': cancelled_orders,
            'message': 'Trailing stop cancelled'
        })

    except Exception as e:
        logger.error(f"Cancel trailing stop failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== TRAILING STOP LIMIT API ====================

@app.route('/api/trailing-stop-limit/<int:order_id>/check-fill', methods=['GET'])
def check_trailing_stop_limit_fill(order_id):
    """
    Check if opening order filled. If filled, calculate trigger price
    and transition to waiting_trigger state.
    """
    try:
        tsl = _pending_trailing_stop_limit_orders.get(order_id)
        if not tsl:
            return jsonify({
                'filled': False,
                'error': f'No trailing stop limit found for order {order_id}'
            })

        # If already in waiting_trigger or stop_placed state, return current status
        if tsl.get('status') == 'waiting_trigger':
            return jsonify({
                'filled': True,
                'waiting_trigger': True,
                'fill_price': tsl.get('fill_price'),
                'trigger_price': tsl.get('trigger_price')
            })

        if tsl.get('stop_order_id'):
            return jsonify({
                'filled': True,
                'trailing_stop_placed': True,
                'stop_order_id': tsl['stop_order_id'],
                'fill_price': tsl.get('fill_price')
            })

        client = _get_authenticated_client()

        # Fetch ALL orders (no status filter) to find the order
        # Same pattern as working confirmation stop
        try:
            all_orders = client.get_orders(tsl['account_id_key'], status=None)
            logger.info(f"TSL check-fill: Fetched {len(all_orders)} orders")
        except Exception as api_error:
            error_msg = str(api_error)
            logger.warning(f"TSL check-fill: API error fetching orders: {error_msg}")
            if '500' in error_msg or 'not currently available' in error_msg:
                return jsonify({
                    'filled': False,
                    'api_error': True,
                    'api_error_message': 'E*TRADE API temporarily unavailable'
                })
            raise

        fill_price = None
        order_filled = False
        found_order = False

        logger.info(f"TSL check-fill: Looking for order {order_id} in {len(all_orders)} orders")

        for order in all_orders:
            # Handle nested Orders structure
            if 'Orders' in order:
                order = order['Orders']

            order_id_from_api = order.get('orderId')
            if str(order_id_from_api) != str(order_id):
                continue

            found_order = True
            logger.info(f"TSL check-fill: Found order {order_id}")

            # Check OrderDetail -> Instrument for fill info (same structure as working confirmation stop)
            if 'OrderDetail' in order:
                for detail in order['OrderDetail']:
                    status = detail.get('status', 'UNKNOWN')
                    logger.info(f"TSL check-fill: Order {order_id} status={status}")

                    if 'Instrument' in detail:
                        for inst in detail['Instrument']:
                            filled_qty = int(inst.get('filledQuantity', 0))
                            ordered_qty = int(inst.get('orderedQuantity', 0))

                            logger.info(f"TSL check-fill: Order {order_id} - ordered={ordered_qty}, filled={filled_qty}")

                            # Only consider filled if FULLY filled (not partial)
                            if filled_qty > 0 and filled_qty >= ordered_qty:
                                order_filled = True
                                if inst.get('averageExecutionPrice'):
                                    fill_price = float(inst.get('averageExecutionPrice'))
                                    logger.info(f"TSL check-fill: Order {order_id} FULLY filled at {fill_price}")
                                    break
                        if order_filled:
                            break
            break

        if not found_order:
            logger.warning(f"TSL check-fill: Order {order_id} not found in orders list")

        if not order_filled:
            return jsonify({'filled': False})

        logger.info(f"Trailing stop limit order {order_id} filled at {fill_price}")

        # Calculate trigger price
        trigger_type = tsl.get('trigger_type', 'dollar')
        trigger_offset = tsl.get('trigger_offset', 0)

        if trigger_type == 'dollar':
            trigger_price = fill_price + trigger_offset
        else:
            trigger_price = fill_price * (1 + trigger_offset / 100)

        trigger_price = round(trigger_price, 2)

        # Update state to waiting_trigger
        tsl['fill_price'] = fill_price
        tsl['trigger_price'] = trigger_price
        tsl['status'] = 'waiting_trigger'
        tsl['fill_time'] = datetime.utcnow()

        logger.info(f"Trailing stop limit {order_id} waiting for trigger at {trigger_price}")

        return jsonify({
            'filled': True,
            'waiting_trigger': True,
            'fill_price': fill_price,
            'trigger_price': trigger_price
        })

    except Exception as e:
        logger.error(f"Check trailing stop limit fill failed: {e}")
        return jsonify({'filled': False, 'error': str(e)})


@app.route('/api/trailing-stop-limit/<int:order_id>/check-trigger', methods=['GET'])
def check_trailing_stop_limit_trigger(order_id):
    """
    Check if trigger price reached and place trailing stop limit if so.
    """
    try:
        tsl = _pending_trailing_stop_limit_orders.get(order_id)
        if not tsl:
            return jsonify({
                'success': False,
                'error': f'No trailing stop limit found for order {order_id}'
            })

        # If stop already placed, return status
        if tsl.get('stop_order_id'):
            return jsonify({
                'triggered': True,
                'trailing_stop_placed': True,
                'stop_order_id': tsl['stop_order_id']
            })

        # If not in waiting_trigger state, return current status
        if tsl.get('status') != 'waiting_trigger':
            return jsonify({
                'triggered': False,
                'status': tsl.get('status')
            })

        client = _get_authenticated_client()

        # Get current price from quote
        quote = client.get_quote(tsl['symbol'])
        current_price = None
        if 'All' in quote:
            current_price = float(quote['All'].get('lastTrade', 0))
            if current_price == 0:
                current_price = float(quote['All'].get('bid', 0))

        if not current_price:
            return jsonify({
                'triggered': False,
                'error': 'Could not get current price'
            })

        trigger_price = tsl.get('trigger_price')

        # Check if trigger reached
        if current_price < trigger_price:
            return jsonify({
                'triggered': False,
                'current_price': current_price,
                'trigger_price': trigger_price
            })

        logger.info(f"Trailing stop limit {order_id} trigger reached at {current_price} (trigger was {trigger_price})")

        # Calculate trail amount
        trail_type = tsl.get('trail_type', 'dollar')
        trail_amount = tsl.get('trail_amount', 0)

        if trail_type == 'percent':
            # Convert percent to dollar amount based on current price
            trail_amount = round(current_price * trail_amount / 100, 2)

        # Place TRAILING_STOP_CNST LIMIT order
        closing_side = 'SELL' if tsl['opening_side'] in ['BUY', 'BUY_TO_COVER'] else 'BUY'

        stop_order_data = {
            'symbol': tsl['symbol'],
            'quantity': tsl['quantity'],
            'orderAction': closing_side,
            'priceType': 'TRAILING_STOP_CNST',
            'orderTerm': 'GOOD_FOR_DAY',
            'stopPrice': str(trail_amount),           # Trail amount (how far behind)
            'stopLimitPrice': '0.01'                   # Limit offset from stop
        }

        try:
            stop_preview = client.preview_order(tsl['account_id_key'], stop_order_data)
            stop_result = client.place_order(
                tsl['account_id_key'],
                stop_order_data,
                preview_id=stop_preview.get('preview_id'),
                client_order_id=stop_preview.get('client_order_id')
            )
            stop_order_id = stop_result.get('order_id')

            logger.info(f"Placed TRAILING_STOP_CNST order {stop_order_id} for {tsl['symbol']} @ trail {trail_amount}")

            # Update state
            tsl['stop_order_id'] = stop_order_id
            tsl['trail_amount_used'] = trail_amount
            tsl['status'] = 'stop_placed'
            tsl['stop_placed_at'] = datetime.utcnow()

            return jsonify({
                'triggered': True,
                'trailing_stop_placed': True,
                'current_price': current_price,
                'trigger_price': trigger_price,
                'stop_order_id': stop_order_id,
                'trail_amount': trail_amount
            })

        except Exception as e:
            logger.error(f"Failed to place trailing stop limit order: {e}")
            tsl['status'] = 'error'
            tsl['error'] = str(e)
            return jsonify({
                'triggered': True,
                'trailing_stop_placed': False,
                'error': str(e)
            })

    except Exception as e:
        logger.error(f"Check trailing stop limit trigger failed: {e}")
        return jsonify({'triggered': False, 'error': str(e)})


@app.route('/api/trailing-stop-limit/<int:order_id>/cancel', methods=['POST'])
def cancel_trailing_stop_limit(order_id):
    """Cancel a trailing stop limit order"""
    try:
        tsl = _pending_trailing_stop_limit_orders.get(order_id)
        if not tsl:
            return jsonify({
                'success': False,
                'error': f'No trailing stop limit found for order {order_id}'
            }), 404

        client = _get_authenticated_client()
        cancelled_orders = []

        # Cancel stop order if placed
        if tsl.get('stop_order_id'):
            try:
                client.cancel_order(tsl['account_id_key'], tsl['stop_order_id'])
                cancelled_orders.append(f'stop:{tsl["stop_order_id"]}')
            except Exception as e:
                logger.warning(f"Could not cancel stop order: {e}")

        # Cancel opening order
        try:
            client.cancel_order(tsl['account_id_key'], order_id)
            cancelled_orders.append(f'opening:{order_id}')
        except Exception as e:
            logger.warning(f"Could not cancel opening order: {e}")

        # Remove from pending
        del _pending_trailing_stop_limit_orders[order_id]

        return jsonify({
            'success': True,
            'cancelled_orders': cancelled_orders,
            'message': 'Trailing stop limit cancelled'
        })

    except Exception as e:
        logger.error(f"Cancel trailing stop limit failed: {e}")
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
