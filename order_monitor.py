"""
Server-Side Order Monitor

Replaces browser-based polling with server-side background threads.
Monitors order fills and places exit orders (profit targets, trailing stops)
even if the browser disconnects.

Emits events via callback for SSE delivery to connected clients.
"""
import threading
import time
import queue
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderMonitor:
    """Background order monitoring that survives browser disconnects"""

    POLL_INTERVAL = 2  # seconds between checks

    def __init__(self):
        self._monitors = {}  # order_id -> thread
        self._lock = threading.Lock()
        self._sse_clients = []  # list of Queue objects for SSE listeners
        self._sse_lock = threading.Lock()

    def add_sse_client(self):
        """Register a new SSE listener. Returns a Queue to read events from."""
        q = queue.Queue()
        with self._sse_lock:
            self._sse_clients.append(q)
        logger.info(f"SSE client connected ({len(self._sse_clients)} total)")
        return q

    def remove_sse_client(self, q):
        """Unregister an SSE listener."""
        with self._sse_lock:
            try:
                self._sse_clients.remove(q)
            except ValueError:
                pass
        logger.info(f"SSE client disconnected ({len(self._sse_clients)} total)")

    def _emit(self, event):
        """Send event to all SSE listeners."""
        if event.get('type') != 'quote':
            logger.info(f"Monitor event: {event.get('type')} order={event.get('order_id')}")
        with self._sse_lock:
            dead = []
            for q in self._sse_clients:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._sse_clients.remove(q)

    def is_monitoring(self, order_id):
        """Check if an order is being monitored."""
        with self._lock:
            return str(order_id) in self._monitors

    def stop_monitoring(self, order_id):
        """Stop monitoring an order."""
        with self._lock:
            key = str(order_id)
            if key in self._monitors:
                self._monitors[key]['stop'] = True
                del self._monitors[key]
                logger.info(f"Stopped monitoring order {order_id}")

    # ==================== Quote Streaming ====================

    def start_quote_watch(self, symbol, get_client_fn, interval=3):
        """
        Start streaming quotes for a symbol via polling + SSE.

        Args:
            symbol: Ticker symbol to watch
            get_client_fn: Callable returning authenticated ETradeClient
            interval: Seconds between polls (default 3)
        """
        symbol = symbol.upper()
        key = f"quote:{symbol}"
        with self._lock:
            # If already watching this exact symbol, don't restart
            if key in self._monitors and not self._monitors[key].get('stop'):
                logger.info(f"[QuoteWatch] Already watching {symbol}, skipping restart")
                return

            # Stop any existing quote watch (different symbol)
            for k in list(self._monitors.keys()):
                if k.startswith('quote:'):
                    self._monitors[k]['stop'] = True
                    del self._monitors[k]

            stop_flag = {'stop': False}
            self._monitors[key] = stop_flag

        logger.info(f"[QuoteWatch] Starting quote stream for {symbol}")

        def run():
            while not stop_flag['stop']:
                try:
                    client = get_client_fn()
                    quote = client.get_quote(symbol)

                    if quote and 'All' in quote and quote['All'] is not None:
                        all_data = quote['All']
                        quote_event = {
                            'type': 'quote',
                            'symbol': symbol,
                            'last_price': all_data.get('lastTrade'),
                            'bid': all_data.get('bid'),
                            'ask': all_data.get('ask'),
                            'bid_size': all_data.get('bidSize'),
                            'ask_size': all_data.get('askSize'),
                            'change': all_data.get('changeClose'),
                            'change_percent': all_data.get('changeClosePercentage'),
                            'volume': all_data.get('totalVolume'),
                            'high': all_data.get('high'),
                            'low': all_data.get('low'),
                            'open': all_data.get('open'),
                            'previous_close': all_data.get('previousClose')
                        }
                        self._emit(quote_event)

                except Exception as e:
                    err_msg = str(e)
                    if '500' in err_msg or 'not currently available' in err_msg:
                        logger.debug(f"[QuoteWatch] API error for {symbol}, retrying...")
                    else:
                        logger.error(f"[QuoteWatch] Error fetching quote for {symbol}: {e}")

                time.sleep(interval)

            logger.info(f"[QuoteWatch] Stopped quote stream for {symbol}")

        t = threading.Thread(target=run, daemon=True, name=f"quote-watch-{symbol}")
        t.start()

    def stop_quote_watch(self):
        """Stop watching quotes."""
        with self._lock:
            for k in list(self._monitors.keys()):
                if k.startswith('quote:'):
                    self._monitors[k]['stop'] = True
                    del self._monitors[k]
                    logger.info(f"[QuoteWatch] Stopped {k}")

    def is_watching_quote(self):
        """Check if any quote is being watched."""
        with self._lock:
            return any(k.startswith('quote:') for k in self._monitors)

    # ==================== Order Monitoring ====================

    def monitor_profit_target(self, order_id, config, get_client_fn,
                              pending_orders_dict):
        """
        Start monitoring for profit target fill detection.

        Args:
            order_id: The opening order ID
            config: Dict with symbol, quantity, profit_offset_type, profit_offset,
                    account_id_key, opening_side
            get_client_fn: Callable that returns an authenticated ETradeClient
            pending_orders_dict: Reference to _pending_profit_orders dict
        """
        key = str(order_id)
        with self._lock:
            if key in self._monitors:
                return
            stop_flag = {'stop': False}
            self._monitors[key] = stop_flag

        fill_timeout = config.get('fill_timeout', 15)

        def run():
            elapsed = 0
            logger.info(f"[Monitor] Profit target monitoring started for order {order_id}")
            self._emit({
                'type': 'monitoring_started',
                'order_id': order_id,
                'monitor_type': 'profit_target',
                'timeout': fill_timeout
            })

            while elapsed < fill_timeout and not stop_flag['stop']:
                try:
                    client = get_client_fn()
                    account_id_key = config['account_id_key']

                    try:
                        all_orders = client.get_orders(account_id_key, status=None)
                    except Exception as api_err:
                        if '500' in str(api_err) or 'not currently available' in str(api_err):
                            logger.debug(f"[Monitor] API error checking order {order_id}, retrying...")
                            elapsed += 1
                            self._emit({
                                'type': 'status',
                                'order_id': order_id,
                                'message': f'Waiting for fill... ({elapsed}/{fill_timeout}s)',
                                'elapsed': elapsed,
                                'timeout': fill_timeout
                            })
                            time.sleep(self.POLL_INTERVAL)
                            continue
                        raise

                    # Check if order is filled
                    filled, fill_price = self._check_order_filled(all_orders, order_id)

                    if filled and fill_price:
                        logger.info(f"[Monitor] Order {order_id} filled at {fill_price}")

                        # Calculate profit price
                        profit_price = self._calc_profit_price(
                            fill_price, config['profit_offset_type'],
                            config['profit_offset'], config['opening_side']
                        )

                        # Place profit order
                        exit_result = self._place_exit_limit_order(
                            client, config, fill_price, profit_price
                        )

                        # Update pending dict
                        matching_key = self._find_pending_key(pending_orders_dict, order_id)
                        if matching_key is not None:
                            if exit_result['placed']:
                                pending_orders_dict[matching_key]['status'] = 'placed'
                            else:
                                pending_orders_dict[matching_key]['status'] = f"error: {exit_result.get('error', 'unknown')}"

                        self._emit({
                            'type': 'filled',
                            'order_id': order_id,
                            'fill_price': fill_price,
                            'profit_price': round(profit_price, 2),
                            'profit_order_placed': exit_result['placed'],
                            'error': exit_result.get('error')
                        })
                        self.stop_monitoring(order_id)
                        return

                    elapsed += 1
                    self._emit({
                        'type': 'status',
                        'order_id': order_id,
                        'message': f'Waiting for fill... ({elapsed}/{fill_timeout}s)',
                        'elapsed': elapsed,
                        'timeout': fill_timeout
                    })

                except Exception as e:
                    logger.error(f"[Monitor] Profit target check error: {e}")
                    elapsed += 1
                    self._emit({
                        'type': 'status',
                        'order_id': order_id,
                        'message': f'Error: {e} ({elapsed}/{fill_timeout}s)',
                        'elapsed': elapsed,
                        'timeout': fill_timeout
                    })

                time.sleep(self.POLL_INTERVAL)

            if stop_flag['stop']:
                return

            # Timeout - try to cancel
            logger.info(f"[Monitor] Profit target timeout for order {order_id}")
            self._emit({
                'type': 'timeout',
                'order_id': order_id,
                'message': f'Fill timeout ({fill_timeout}s). Cancelling order...'
            })

            try:
                client = get_client_fn()
                client.cancel_order(config['account_id_key'], order_id)
                self._emit({
                    'type': 'cancelled',
                    'order_id': order_id,
                    'message': f'Order cancelled (not filled within {fill_timeout}s)'
                })
            except Exception as e:
                error_msg = str(e)
                if '5001' in error_msg or 'being executed' in error_msg:
                    # Order may have filled during cancel - recheck
                    self._emit({
                        'type': 'status',
                        'order_id': order_id,
                        'message': 'Order may have filled. Rechecking...'
                    })
                    time.sleep(2)
                    try:
                        client = get_client_fn()
                        all_orders = client.get_orders(config['account_id_key'], status=None)
                        filled, fill_price = self._check_order_filled(all_orders, order_id)
                        if filled and fill_price:
                            profit_price = self._calc_profit_price(
                                fill_price, config['profit_offset_type'],
                                config['profit_offset'], config['opening_side']
                            )
                            exit_result = self._place_exit_limit_order(
                                client, config, fill_price, profit_price
                            )
                            self._emit({
                                'type': 'filled',
                                'order_id': order_id,
                                'fill_price': fill_price,
                                'profit_price': round(profit_price, 2),
                                'profit_order_placed': exit_result['placed'],
                                'error': exit_result.get('error')
                            })
                            return
                    except Exception:
                        pass
                    self._emit({
                        'type': 'error',
                        'order_id': order_id,
                        'message': 'Order status unclear. Check positions.'
                    })
                else:
                    self._emit({
                        'type': 'error',
                        'order_id': order_id,
                        'message': f'Failed to cancel: {error_msg}'
                    })

            self.stop_monitoring(order_id)

        t = threading.Thread(target=run, daemon=True, name=f"monitor-profit-{order_id}")
        t.start()

    def monitor_trailing_stop(self, order_id, config, get_client_fn,
                              trailing_stop_mgr):
        """
        Start monitoring for confirmation stop (trailing stop).

        States: waiting_fill -> waiting_confirmation -> stop_active -> complete
        """
        key = str(order_id)
        with self._lock:
            if key in self._monitors:
                return
            stop_flag = {'stop': False}
            self._monitors[key] = stop_flag

        fill_timeout = config.get('fill_timeout', 15)
        confirm_timeout = config.get('confirmation_timeout', 300)

        def run():
            state = 'waiting_fill'
            fill_elapsed = 0
            confirm_elapsed = 0

            logger.info(f"[Monitor] Trailing stop monitoring started for order {order_id}")
            self._emit({
                'type': 'monitoring_started',
                'order_id': order_id,
                'monitor_type': 'trailing_stop',
                'timeout': fill_timeout
            })

            while not stop_flag['stop']:
                try:
                    client = get_client_fn()
                    ts = trailing_stop_mgr.get_trailing_stop(order_id)
                    if not ts:
                        self._emit({'type': 'error', 'order_id': order_id,
                                    'message': 'Trailing stop not found'})
                        break

                    if state == 'waiting_fill':
                        try:
                            all_orders = client.get_orders(config['account_id_key'], status=None)
                        except Exception as api_err:
                            if '500' in str(api_err) or 'not currently available' in str(api_err):
                                self._emit({
                                    'type': 'ts_status',
                                    'order_id': order_id,
                                    'state': 'waiting_fill',
                                    'message': 'Waiting for fill...'
                                })
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            raise

                        filled, fill_price = self._check_order_filled(all_orders, order_id)

                        if filled and fill_price:
                            trailing_stop_mgr.mark_filled(order_id, fill_price)
                            state = 'waiting_confirmation'
                            self._emit({
                                'type': 'ts_filled',
                                'order_id': order_id,
                                'fill_price': fill_price,
                                'trigger_price': ts.trigger_price,
                                'state': 'waiting_confirmation'
                            })
                            time.sleep(self.POLL_INTERVAL)
                            continue

                        fill_elapsed += 1
                        self._emit({
                            'type': 'ts_status',
                            'order_id': order_id,
                            'state': 'waiting_fill',
                            'message': f'Waiting for fill... ({fill_elapsed}/{fill_timeout}s)',
                            'elapsed': fill_elapsed,
                            'timeout': fill_timeout
                        })

                        if fill_elapsed >= fill_timeout:
                            # Timeout - cancel
                            self._emit({
                                'type': 'ts_status',
                                'order_id': order_id,
                                'state': 'waiting_fill',
                                'message': 'Timeout. Cancelling order...'
                            })
                            cancel_result = self._cancel_and_recheck(
                                client, config, order_id, get_client_fn
                            )
                            if cancel_result.get('filled'):
                                trailing_stop_mgr.mark_filled(order_id, cancel_result['fill_price'])
                                state = 'waiting_confirmation'
                                self._emit({
                                    'type': 'ts_filled',
                                    'order_id': order_id,
                                    'fill_price': cancel_result['fill_price'],
                                    'trigger_price': ts.trigger_price,
                                    'state': 'waiting_confirmation'
                                })
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            else:
                                self._emit({
                                    'type': 'ts_timeout',
                                    'order_id': order_id,
                                    'message': cancel_result.get('message', f'Order cancelled (not filled within {fill_timeout}s)')
                                })
                                break

                    elif state == 'waiting_confirmation':
                        ts = trailing_stop_mgr.get_trailing_stop(order_id)

                        if ts.is_confirmation_timeout():
                            self._emit({
                                'type': 'ts_timeout',
                                'order_id': order_id,
                                'message': 'Trigger timeout. Position remains open without stop.'
                            })
                            break

                        try:
                            quote = client.get_quote(ts.symbol)
                        except Exception as api_err:
                            if '500' in str(api_err) or 'not currently available' in str(api_err):
                                confirm_elapsed += 1
                                self._emit({
                                    'type': 'ts_status',
                                    'order_id': order_id,
                                    'state': 'waiting_confirmation',
                                    'message': f'Waiting for trigger... ({confirm_elapsed}s)'
                                })
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            raise

                        current_price = None
                        if quote and 'All' in quote:
                            current_price = quote['All'].get('lastTrade')

                        if not current_price:
                            time.sleep(self.POLL_INTERVAL)
                            continue

                        if ts.check_confirmation(current_price):
                            logger.info(f"[Monitor] Confirmation reached for {order_id} at {current_price}")
                            stop_price, stop_limit_price = ts.calculate_stop_prices(current_price)

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
                                preview = client.preview_order(ts.account_id_key, stop_order_data)
                                result = client.place_order(
                                    ts.account_id_key, stop_order_data,
                                    preview_id=preview.get('preview_id'),
                                    client_order_id=preview.get('client_order_id')
                                )
                                stop_order_id = result.get('order_id')
                                trailing_stop_mgr.mark_stop_placed(order_id, stop_order_id)

                                self._emit({
                                    'type': 'ts_stop_placed',
                                    'order_id': order_id,
                                    'stop_order_id': stop_order_id,
                                    'stop_price': stop_price,
                                    'current_price': current_price
                                })
                                break  # Done monitoring
                            except Exception as e:
                                logger.error(f"[Monitor] Failed to place stop: {e}")
                                trailing_stop_mgr.mark_error(order_id, str(e))
                                self._emit({
                                    'type': 'ts_error',
                                    'order_id': order_id,
                                    'message': f'Failed to place stop: {e}'
                                })
                                break

                        confirm_elapsed += 1
                        self._emit({
                            'type': 'ts_status',
                            'order_id': order_id,
                            'state': 'waiting_confirmation',
                            'current_price': current_price,
                            'trigger_price': ts.trigger_price,
                            'message': f'Waiting for trigger... ({confirm_elapsed}s)',
                            'elapsed': confirm_elapsed,
                            'timeout': confirm_timeout
                        })

                except Exception as e:
                    logger.error(f"[Monitor] Trailing stop error for {order_id}: {e}")
                    self._emit({
                        'type': 'ts_status',
                        'order_id': order_id,
                        'state': state,
                        'message': f'Error: {e}'
                    })

                time.sleep(self.POLL_INTERVAL)

            self.stop_monitoring(order_id)

        t = threading.Thread(target=run, daemon=True, name=f"monitor-ts-{order_id}")
        t.start()

    def monitor_tsl(self, order_id, config, get_client_fn, pending_tsl_dict):
        """
        Start monitoring for trailing stop limit.

        States: waiting_fill -> waiting_trigger -> stop_placed
        """
        key = str(order_id)
        with self._lock:
            if key in self._monitors:
                return
            stop_flag = {'stop': False}
            self._monitors[key] = stop_flag

        fill_timeout = config.get('fill_timeout', 15)
        trigger_timeout = config.get('trigger_timeout', 300)

        def run():
            state = 'waiting_fill'
            fill_elapsed = 0
            trigger_elapsed = 0

            logger.info(f"[Monitor] TSL monitoring started for order {order_id}")
            self._emit({
                'type': 'monitoring_started',
                'order_id': order_id,
                'monitor_type': 'tsl',
                'timeout': fill_timeout
            })

            while not stop_flag['stop']:
                try:
                    tsl = pending_tsl_dict.get(order_id)
                    if not tsl:
                        self._emit({'type': 'error', 'order_id': order_id,
                                    'message': 'TSL config not found'})
                        break

                    client = get_client_fn()

                    if state == 'waiting_fill':
                        if tsl.get('status') == 'waiting_trigger':
                            # Already transitioned (e.g. by REST endpoint)
                            state = 'waiting_trigger'
                            continue

                        try:
                            all_orders = client.get_orders(config['account_id_key'], status=None)
                        except Exception as api_err:
                            if '500' in str(api_err) or 'not currently available' in str(api_err):
                                fill_elapsed += 1
                                self._emit({
                                    'type': 'tsl_status',
                                    'order_id': order_id,
                                    'state': 'waiting_fill',
                                    'message': f'Waiting for fill... ({fill_elapsed}/{fill_timeout}s)'
                                })
                                if fill_elapsed >= fill_timeout:
                                    self._emit({
                                        'type': 'tsl_timeout',
                                        'order_id': order_id,
                                        'state': 'waiting_fill',
                                        'message': f'Fill timeout (API unavailable). Check E*TRADE.'
                                    })
                                    break
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            raise

                        filled, fill_price = self._check_order_filled(all_orders, order_id)

                        if filled and fill_price:
                            # Calculate trigger price
                            trigger_type = tsl.get('trigger_type', 'dollar')
                            trigger_offset = tsl.get('trigger_offset', 0)
                            if trigger_type == 'dollar':
                                trigger_price = fill_price + trigger_offset
                            else:
                                trigger_price = fill_price * (1 + trigger_offset / 100)
                            trigger_price = round(trigger_price, 2)

                            tsl['fill_price'] = fill_price
                            tsl['trigger_price'] = trigger_price
                            tsl['status'] = 'waiting_trigger'
                            tsl['fill_time'] = datetime.utcnow()

                            state = 'waiting_trigger'
                            self._emit({
                                'type': 'tsl_filled',
                                'order_id': order_id,
                                'fill_price': fill_price,
                                'trigger_price': trigger_price
                            })
                            time.sleep(self.POLL_INTERVAL)
                            continue

                        fill_elapsed += 1
                        self._emit({
                            'type': 'tsl_status',
                            'order_id': order_id,
                            'state': 'waiting_fill',
                            'message': f'Waiting for fill... ({fill_elapsed}/{fill_timeout}s)',
                            'elapsed': fill_elapsed,
                            'timeout': fill_timeout
                        })

                        if fill_elapsed >= fill_timeout:
                            # Cancel order
                            self._emit({
                                'type': 'tsl_status',
                                'order_id': order_id,
                                'state': 'waiting_fill',
                                'message': 'Timeout. Cancelling order...'
                            })
                            cancel_result = self._cancel_and_recheck(
                                client, config, order_id, get_client_fn
                            )
                            if cancel_result.get('filled'):
                                fill_price = cancel_result['fill_price']
                                trigger_type = tsl.get('trigger_type', 'dollar')
                                trigger_offset = tsl.get('trigger_offset', 0)
                                if trigger_type == 'dollar':
                                    trigger_price = fill_price + trigger_offset
                                else:
                                    trigger_price = fill_price * (1 + trigger_offset / 100)
                                trigger_price = round(trigger_price, 2)

                                tsl['fill_price'] = fill_price
                                tsl['trigger_price'] = trigger_price
                                tsl['status'] = 'waiting_trigger'
                                tsl['fill_time'] = datetime.utcnow()

                                state = 'waiting_trigger'
                                self._emit({
                                    'type': 'tsl_filled',
                                    'order_id': order_id,
                                    'fill_price': fill_price,
                                    'trigger_price': trigger_price
                                })
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            else:
                                self._emit({
                                    'type': 'tsl_timeout',
                                    'order_id': order_id,
                                    'state': 'waiting_fill',
                                    'message': cancel_result.get('message',
                                        f'Order cancelled (not filled within {fill_timeout}s)')
                                })
                                break

                    elif state == 'waiting_trigger':
                        if tsl.get('stop_order_id'):
                            # Already placed
                            self._emit({
                                'type': 'tsl_stop_placed',
                                'order_id': order_id,
                                'stop_order_id': tsl['stop_order_id']
                            })
                            break

                        try:
                            quote = client.get_quote(tsl['symbol'])
                        except Exception as api_err:
                            if '500' in str(api_err) or 'not currently available' in str(api_err):
                                trigger_elapsed += 1
                                self._emit({
                                    'type': 'tsl_status',
                                    'order_id': order_id,
                                    'state': 'waiting_trigger',
                                    'message': f'Waiting for trigger... ({trigger_elapsed}/{trigger_timeout}s)'
                                })
                                if trigger_elapsed >= trigger_timeout:
                                    self._emit({
                                        'type': 'tsl_timeout',
                                        'order_id': order_id,
                                        'state': 'waiting_trigger',
                                        'message': 'Trigger timeout. Position open without trailing stop.'
                                    })
                                    break
                                time.sleep(self.POLL_INTERVAL)
                                continue
                            raise

                        current_price = None
                        if 'All' in quote:
                            current_price = float(quote['All'].get('lastTrade', 0))
                            if current_price == 0:
                                current_price = float(quote['All'].get('bid', 0))

                        if not current_price:
                            time.sleep(self.POLL_INTERVAL)
                            continue

                        trigger_price = tsl.get('trigger_price')

                        if current_price >= trigger_price:
                            logger.info(f"[Monitor] TSL trigger reached for {order_id}: {current_price} >= {trigger_price}")

                            # Calculate trail amount
                            trail_type = tsl.get('trail_type', 'dollar')
                            trail_amount = tsl.get('trail_amount', 0)
                            if trail_type == 'percent':
                                trail_amount = round(current_price * trail_amount / 100, 2)

                            closing_side = 'SELL' if tsl['opening_side'] in ['BUY', 'BUY_TO_COVER'] else 'BUY'

                            try:
                                stop_order_data = {
                                    'symbol': tsl['symbol'],
                                    'quantity': tsl['quantity'],
                                    'orderAction': closing_side,
                                    'priceType': 'TRAILING_STOP_CNST',
                                    'orderTerm': 'GOOD_FOR_DAY',
                                    'stopPrice': str(trail_amount),
                                    'stopLimitPrice': '0.01'
                                }
                                preview = client.preview_order(tsl['account_id_key'], stop_order_data)
                                result = client.place_order(
                                    tsl['account_id_key'], stop_order_data,
                                    preview_id=preview.get('preview_id'),
                                    client_order_id=preview.get('client_order_id')
                                )
                                stop_order_id = result.get('order_id')

                                tsl['stop_order_id'] = stop_order_id
                                tsl['trail_amount_used'] = trail_amount
                                tsl['status'] = 'stop_placed'
                                tsl['stop_placed_at'] = datetime.utcnow()

                                self._emit({
                                    'type': 'tsl_stop_placed',
                                    'order_id': order_id,
                                    'stop_order_id': stop_order_id,
                                    'current_price': current_price,
                                    'trigger_price': trigger_price,
                                    'trail_amount': trail_amount
                                })
                                break
                            except Exception as e:
                                logger.error(f"[Monitor] Failed to place TSL stop: {e}")
                                tsl['status'] = 'error'
                                tsl['error'] = str(e)
                                self._emit({
                                    'type': 'tsl_error',
                                    'order_id': order_id,
                                    'message': f'Failed to place trailing stop: {e}'
                                })
                                break

                        trigger_elapsed += 1
                        self._emit({
                            'type': 'tsl_status',
                            'order_id': order_id,
                            'state': 'waiting_trigger',
                            'current_price': current_price,
                            'trigger_price': trigger_price,
                            'message': f'Waiting for trigger... ({trigger_elapsed}/{trigger_timeout}s)',
                            'elapsed': trigger_elapsed,
                            'timeout': trigger_timeout
                        })

                        if trigger_elapsed >= trigger_timeout:
                            self._emit({
                                'type': 'tsl_timeout',
                                'order_id': order_id,
                                'state': 'waiting_trigger',
                                'message': 'Trigger timeout. Position open without trailing stop.'
                            })
                            break

                except Exception as e:
                    logger.error(f"[Monitor] TSL error for {order_id}: {e}")
                    self._emit({
                        'type': 'tsl_status',
                        'order_id': order_id,
                        'state': state,
                        'message': f'Error: {e}'
                    })

                time.sleep(self.POLL_INTERVAL)

            self.stop_monitoring(order_id)

        t = threading.Thread(target=run, daemon=True, name=f"monitor-tsl-{order_id}")
        t.start()

    # ==================== Helper Methods ====================

    def _check_order_filled(self, all_orders, order_id):
        """
        Check if an order is fully filled.
        Returns (filled: bool, fill_price: float or None)
        """
        for order in all_orders:
            if 'Orders' in order:
                order = order['Orders']
            if str(order.get('orderId')) != str(order_id):
                continue

            if 'OrderDetail' in order:
                for detail in order['OrderDetail']:
                    if 'Instrument' in detail:
                        for inst in detail['Instrument']:
                            filled_qty = int(inst.get('filledQuantity', 0))
                            ordered_qty = int(inst.get('orderedQuantity', 0))
                            if filled_qty > 0 and filled_qty >= ordered_qty:
                                fill_price = None
                                if inst.get('averageExecutionPrice'):
                                    fill_price = float(inst['averageExecutionPrice'])
                                elif inst.get('executedPrice'):
                                    fill_price = float(inst['executedPrice'])
                                return True, fill_price
            break

        return False, None

    def _calc_profit_price(self, fill_price, offset_type, offset, opening_side):
        """Calculate profit target price from fill price."""
        if offset_type == 'dollar':
            if opening_side in ['BUY', 'BUY_TO_COVER']:
                return fill_price + offset
            else:
                return fill_price - offset
        else:  # percent
            if opening_side in ['BUY', 'BUY_TO_COVER']:
                return fill_price * (1 + offset / 100)
            else:
                return fill_price * (1 - offset / 100)

    def _place_exit_limit_order(self, client, config, fill_price, profit_price):
        """Place a limit exit order (for profit targets)."""
        opening_side = config['opening_side']
        closing_side = 'SELL' if opening_side in ['BUY', 'BUY_TO_COVER'] else 'BUY'

        order_data = {
            'symbol': config['symbol'],
            'quantity': config['quantity'],
            'orderAction': closing_side,
            'priceType': 'LIMIT',
            'orderTerm': 'GOOD_FOR_DAY',
            'limitPrice': str(round(profit_price, 2))
        }

        try:
            preview = client.preview_order(config['account_id_key'], order_data)
            preview_id = preview.get('preview_id')
            if not preview_id:
                return {'placed': False, 'error': 'Preview failed - no preview_id'}

            result = client.place_order(
                config['account_id_key'], order_data,
                preview_id=preview_id,
                client_order_id=preview.get('client_order_id')
            )
            logger.info(f"[Monitor] Placed profit order for {config['symbol']} @ ${round(profit_price, 2)}")
            return {'placed': True, 'order_id': result.get('order_id')}
        except Exception as e:
            logger.error(f"[Monitor] Failed to place profit order: {e}")
            return {'placed': False, 'error': str(e)}

    def _cancel_and_recheck(self, client, config, order_id, get_client_fn):
        """Cancel an order, recheck if it filled during cancel."""
        try:
            client.cancel_order(config['account_id_key'], order_id)
            return {'filled': False, 'message': 'Order cancelled'}
        except Exception as e:
            error_msg = str(e)
            if '5001' in error_msg or 'being executed' in error_msg:
                # Order might have filled - recheck
                for attempt in range(5):
                    time.sleep(2)
                    try:
                        c = get_client_fn()
                        all_orders = c.get_orders(config['account_id_key'], status=None)
                        filled, fill_price = self._check_order_filled(all_orders, order_id)
                        if filled and fill_price:
                            return {'filled': True, 'fill_price': fill_price}
                    except Exception:
                        continue
                return {'filled': False, 'message': 'Order status unclear. Check positions.'}
            return {'filled': False, 'message': f'Failed to cancel: {error_msg}'}

    def _find_pending_key(self, pending_dict, order_id):
        """Find matching key in pending orders dict (handles int/str mismatch)."""
        order_id_str = str(order_id)
        for k in pending_dict.keys():
            if str(k) == order_id_str:
                return k
        return None


# Singleton instance
_order_monitor = None


def get_order_monitor():
    """Get or create the singleton OrderMonitor instance."""
    global _order_monitor
    if _order_monitor is None:
        _order_monitor = OrderMonitor()
    return _order_monitor
