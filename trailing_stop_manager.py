"""
Confirmation Stop Manager for E*TRADE Trading System

Implements confirmation-based stop orders:
1. Place opening order (BUY or SELL_SHORT)
2. Wait for fill
3. Wait for price confirmation (move in favorable direction by trigger amount)
4. Place STOP_LIMIT order at trigger_price - stop_offset

Since E*TRADE API doesn't support native trailing stops or OCO orders,
we implement this as a single exit order that gets placed after confirmation.

All times in CST (Central Standard Time)
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TrailingStopState:
    """Confirmation stop order states"""
    PENDING_FILL = 'pending_fill'           # Waiting for opening order to fill
    WAITING_CONFIRMATION = 'waiting_confirmation'  # Filled, waiting for price confirmation
    STOP_PLACED = 'stop_placed'             # Stop order placed, monitoring
    STOP_FILLED = 'stop_filled'             # Stop order filled - complete
    CANCELLED = 'cancelled'                 # Cancelled
    ERROR = 'error'                         # Error state


class PendingTrailingStop:
    """Represents a pending confirmation stop order"""

    def __init__(
        self,
        opening_order_id: int,
        symbol: str,
        quantity: int,
        account_id_key: str,
        opening_side: str,

        # Upper trigger config (confirmation)
        trigger_type: str = 'dollar',        # 'dollar' or 'percent'
        trigger_offset: float = 0.0,         # How much price must move before placing stop

        # Stop offset from trigger price
        stop_type: str = 'dollar',           # 'dollar' or 'percent'
        stop_offset: float = 0.0,            # How far below trigger price for stop

        # Timeouts
        fill_timeout: int = 15,              # Seconds to wait for fill
        confirmation_timeout: int = 300,     # Seconds to wait for price confirmation
    ):
        self.opening_order_id = opening_order_id
        self.symbol = symbol.upper()
        self.quantity = quantity
        self.account_id_key = account_id_key
        self.opening_side = opening_side.upper()

        # Trigger config (confirmation)
        self.trigger_type = trigger_type
        self.trigger_offset = trigger_offset

        # Stop config
        self.stop_type = stop_type
        self.stop_offset = stop_offset

        # Timeouts
        self.fill_timeout = fill_timeout
        self.confirmation_timeout = confirmation_timeout

        # State (filled in during lifecycle)
        self.state = TrailingStopState.PENDING_FILL
        self.fill_price: Optional[float] = None
        self.fill_time: Optional[datetime] = None

        # Trigger price (when price reaches this, place stop)
        self.trigger_price: Optional[float] = None

        # Stop order ID (set when stop is placed)
        self.stop_order_id: Optional[int] = None

        # Final prices used for stop
        self.stop_price: Optional[float] = None           # Stop trigger price
        self.stop_limit_price: Optional[float] = None     # Stop limit price (slightly below stop)

        # Timestamps
        self.created_at = datetime.utcnow()
        self.stop_placed_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Error message if any
        self.error_message: Optional[str] = None

    def is_buy_to_open(self) -> bool:
        """Check if opening order is a BUY (vs SELL_SHORT)"""
        return self.opening_side in ['BUY', 'BUY_TO_COVER']

    def calculate_trigger_price(self) -> float:
        """
        Calculate the trigger price based on fill price and trigger offset.
        For BUY: trigger = fill + offset (wait for price to go up)
        For SELL_SHORT: trigger = fill - offset (wait for price to go down)
        """
        if self.fill_price is None:
            raise ValueError("Fill price not set")

        if self.is_buy_to_open():
            # For long positions, wait for price to rise
            if self.trigger_type == 'dollar':
                self.trigger_price = self.fill_price + self.trigger_offset
            else:
                self.trigger_price = self.fill_price * (1 + self.trigger_offset / 100)
        else:
            # For short positions, wait for price to fall
            if self.trigger_type == 'dollar':
                self.trigger_price = self.fill_price - self.trigger_offset
            else:
                self.trigger_price = self.fill_price * (1 - self.trigger_offset / 100)

        return self.trigger_price

    def calculate_stop_prices(self, current_price: float) -> tuple:
        """
        Calculate stop and limit prices based on current price (at trigger).

        For BUY positions:
        - Stop price: current - offset (below current, but above fill = profit)

        For SELL_SHORT positions:
        - Stop price: current + offset (above current, but below fill = profit)

        Returns: (stop_price, stop_limit_price)
        """
        if self.is_buy_to_open():
            # Long position - stop goes below current price
            if self.stop_type == 'dollar':
                self.stop_price = current_price - self.stop_offset
            else:
                self.stop_price = current_price * (1 - self.stop_offset / 100)

            # Limit price slightly below stop for execution
            self.stop_limit_price = round(self.stop_price - 0.01, 2)
        else:
            # Short position - stop goes above current price
            if self.stop_type == 'dollar':
                self.stop_price = current_price + self.stop_offset
            else:
                self.stop_price = current_price * (1 + self.stop_offset / 100)

            # Limit price slightly above stop for execution
            self.stop_limit_price = round(self.stop_price + 0.01, 2)

        # Round to 2 decimal places
        self.stop_price = round(self.stop_price, 2)

        return (self.stop_price, self.stop_limit_price)

    def check_confirmation(self, current_price: float) -> bool:
        """
        Check if price has reached the confirmation trigger.

        For BUY: current_price >= trigger_price
        For SELL_SHORT: current_price <= trigger_price
        """
        if self.trigger_price is None:
            return False

        if self.is_buy_to_open():
            return current_price >= self.trigger_price
        else:
            return current_price <= self.trigger_price

    def is_confirmation_timeout(self) -> bool:
        """Check if we've waited too long for confirmation"""
        if self.fill_time is None:
            return False
        return datetime.utcnow() > self.fill_time + timedelta(seconds=self.confirmation_timeout)

    def get_closing_side(self) -> str:
        """Get the closing order action (opposite of opening)"""
        if self.opening_side in ['BUY', 'BUY_TO_COVER']:
            return 'SELL'
        return 'BUY'

    def get_min_profit(self) -> float:
        """
        Calculate minimum guaranteed profit per share.
        For BUY: stop_price - fill_price
        For SELL_SHORT: fill_price - stop_price
        """
        if self.stop_price is None or self.fill_price is None:
            return 0.0

        if self.is_buy_to_open():
            return self.stop_price - self.fill_price
        else:
            return self.fill_price - self.stop_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses and storage"""
        return {
            'opening_order_id': self.opening_order_id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'account_id_key': self.account_id_key,
            'opening_side': self.opening_side,
            'state': self.state,
            'fill_price': self.fill_price,
            'trigger_price': self.trigger_price,
            'stop_order_id': self.stop_order_id,
            'stop_price': self.stop_price,
            'stop_limit_price': self.stop_limit_price,
            'trigger_type': self.trigger_type,
            'trigger_offset': self.trigger_offset,
            'stop_type': self.stop_type,
            'stop_offset': self.stop_offset,
            'min_profit': self.get_min_profit(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'fill_time': self.fill_time.isoformat() if self.fill_time else None,
            'stop_placed_at': self.stop_placed_at.isoformat() if self.stop_placed_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingTrailingStop':
        """Create from dictionary"""
        trailing_stop = cls(
            opening_order_id=data['opening_order_id'],
            symbol=data['symbol'],
            quantity=data['quantity'],
            account_id_key=data['account_id_key'],
            opening_side=data['opening_side'],
            trigger_type=data.get('trigger_type', 'dollar'),
            trigger_offset=data.get('trigger_offset', 0),
            stop_type=data.get('stop_type', 'dollar'),
            stop_offset=data.get('stop_offset', 0),
            fill_timeout=data.get('fill_timeout', 15),
            confirmation_timeout=data.get('confirmation_timeout', 300),
        )

        # Restore state
        trailing_stop.state = data.get('state', TrailingStopState.PENDING_FILL)
        trailing_stop.fill_price = data.get('fill_price')
        trailing_stop.trigger_price = data.get('trigger_price')
        trailing_stop.stop_order_id = data.get('stop_order_id')
        trailing_stop.stop_price = data.get('stop_price')
        trailing_stop.stop_limit_price = data.get('stop_limit_price')
        trailing_stop.error_message = data.get('error_message')

        # Restore timestamps
        if data.get('created_at'):
            trailing_stop.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('fill_time'):
            trailing_stop.fill_time = datetime.fromisoformat(data['fill_time'])
        if data.get('stop_placed_at'):
            trailing_stop.stop_placed_at = datetime.fromisoformat(data['stop_placed_at'])
        if data.get('completed_at'):
            trailing_stop.completed_at = datetime.fromisoformat(data['completed_at'])

        return trailing_stop


class TrailingStopManager:
    """
    Manages pending confirmation stop orders.

    In-memory storage for now, can be migrated to Redis for persistence.
    """

    def __init__(self):
        # Key: opening_order_id (int), Value: PendingTrailingStop
        self._trailing_stops: Dict[int, PendingTrailingStop] = {}

    def add_trailing_stop(self, trailing_stop: PendingTrailingStop) -> None:
        """Add a new pending trailing stop"""
        self._trailing_stops[trailing_stop.opening_order_id] = trailing_stop
        logger.info(f"Added trailing stop for order {trailing_stop.opening_order_id}: {trailing_stop.symbol} "
                   f"trigger={trailing_stop.trigger_offset}({trailing_stop.trigger_type}), "
                   f"stop={trailing_stop.stop_offset}({trailing_stop.stop_type})")

    def get_trailing_stop(self, opening_order_id: int) -> Optional[PendingTrailingStop]:
        """Get trailing stop by opening order ID"""
        return self._trailing_stops.get(opening_order_id)

    def get_all_trailing_stops(self) -> Dict[int, PendingTrailingStop]:
        """Get all pending trailing stops"""
        return self._trailing_stops.copy()

    def get_trailing_stops_by_state(self, state: str) -> list:
        """Get all trailing stops in a specific state"""
        return [ts for ts in self._trailing_stops.values() if ts.state == state]

    def update_trailing_stop(self, trailing_stop: PendingTrailingStop) -> None:
        """Update an existing trailing stop"""
        self._trailing_stops[trailing_stop.opening_order_id] = trailing_stop

    def remove_trailing_stop(self, opening_order_id: int) -> Optional[PendingTrailingStop]:
        """Remove a trailing stop"""
        trailing_stop = self._trailing_stops.pop(opening_order_id, None)
        if trailing_stop:
            logger.info(f"Removed trailing stop for order {opening_order_id}")
        return trailing_stop

    def mark_filled(self, opening_order_id: int, fill_price: float) -> Optional[PendingTrailingStop]:
        """Mark an opening order as filled"""
        trailing_stop = self._trailing_stops.get(opening_order_id)
        if trailing_stop:
            trailing_stop.fill_price = fill_price
            trailing_stop.fill_time = datetime.utcnow()
            trailing_stop.state = TrailingStopState.WAITING_CONFIRMATION
            trailing_stop.calculate_trigger_price()
            logger.info(f"Order {opening_order_id} filled at {fill_price}, "
                       f"waiting for confirmation at {trailing_stop.trigger_price}")
        return trailing_stop

    def mark_stop_placed(self, opening_order_id: int, stop_order_id: int) -> Optional[PendingTrailingStop]:
        """Mark stop order as placed"""
        trailing_stop = self._trailing_stops.get(opening_order_id)
        if trailing_stop:
            trailing_stop.stop_order_id = stop_order_id
            trailing_stop.state = TrailingStopState.STOP_PLACED
            trailing_stop.stop_placed_at = datetime.utcnow()
            logger.info(f"Stop order {stop_order_id} placed for {opening_order_id}: "
                       f"stop @ {trailing_stop.stop_price}, limit @ {trailing_stop.stop_limit_price}, "
                       f"min_profit @ {trailing_stop.get_min_profit():.2f}")
        return trailing_stop

    def mark_stop_filled(self, opening_order_id: int) -> Optional[PendingTrailingStop]:
        """Mark stop order as filled"""
        trailing_stop = self._trailing_stops.get(opening_order_id)
        if trailing_stop:
            trailing_stop.state = TrailingStopState.STOP_FILLED
            trailing_stop.completed_at = datetime.utcnow()
            profit = trailing_stop.get_min_profit()
            logger.info(f"Stop filled for order {opening_order_id}, guaranteed profit: {profit:.2f}/share")
        return trailing_stop

    def mark_error(self, opening_order_id: int, error_message: str) -> Optional[PendingTrailingStop]:
        """Mark trailing stop as error"""
        trailing_stop = self._trailing_stops.get(opening_order_id)
        if trailing_stop:
            trailing_stop.state = TrailingStopState.ERROR
            trailing_stop.error_message = error_message
            trailing_stop.completed_at = datetime.utcnow()
            logger.error(f"Trailing stop error for order {opening_order_id}: {error_message}")
        return trailing_stop

    def to_json(self) -> str:
        """Serialize all trailing stops to JSON for storage"""
        data = {str(k): v.to_dict() for k, v in self._trailing_stops.items()}
        return json.dumps(data)

    def from_json(self, json_str: str) -> None:
        """Load trailing stops from JSON"""
        data = json.loads(json_str)
        self._trailing_stops = {
            int(k): PendingTrailingStop.from_dict(v)
            for k, v in data.items()
        }


# Global trailing stop manager instance
_trailing_stop_manager = None

def get_trailing_stop_manager() -> TrailingStopManager:
    """Get or create trailing stop manager instance"""
    global _trailing_stop_manager
    if _trailing_stop_manager is None:
        _trailing_stop_manager = TrailingStopManager()
    return _trailing_stop_manager
