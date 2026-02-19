"""
Bracket Order Manager for E*TRADE Trading System

Implements confirmation-based bracket orders:
1. Place opening order (BUY or SELL_SHORT)
2. Wait for fill
3. Wait for price confirmation (move in favorable direction)
4. Place bracket orders (STOP LIMIT + LIMIT) both above fill price
5. Monitor and cancel other order when one fills

All times in CST (Central Standard Time)
"""
import json
import logging
from datetime import datetime, timedelta, timezone, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# CST timezone offset
CST_OFFSET = timedelta(hours=-6)


class BracketState:
    """Bracket order states"""
    PENDING_FILL = 'pending_fill'           # Waiting for opening order to fill
    WAITING_CONFIRMATION = 'waiting_confirmation'  # Filled, waiting for price confirmation
    BRACKET_PLACED = 'bracket_placed'       # Bracket orders placed, monitoring
    STOP_FILLED = 'stop_filled'             # Stop loss order filled
    PROFIT_FILLED = 'profit_filled'         # Profit target order filled
    CANCELLED = 'cancelled'                 # Bracket cancelled
    ERROR = 'error'                         # Error state


class PendingBracket:
    """Represents a pending bracket order"""

    def __init__(
        self,
        opening_order_id: int,
        symbol: str,
        quantity: int,
        account_id_key: str,
        opening_side: str,

        # Confirmation trigger config
        confirmation_type: str = 'dollar',  # 'dollar' or 'percent'
        confirmation_offset: float = 0.0,    # How much price must move before bracket

        # Stop loss config (placed below trigger price but above fill price)
        stop_loss_type: str = 'dollar',      # 'dollar' or 'percent'
        stop_loss_offset: float = 0.0,       # How far below trigger price for stop

        # Profit target config
        profit_type: str = 'dollar',         # 'dollar' or 'percent'
        profit_offset: float = 0.0,          # How far above trigger price for profit

        # Timeouts
        fill_timeout: int = 15,              # Seconds to wait for fill
        confirmation_timeout: int = 300,     # Seconds to wait for price confirmation
    ):
        self.opening_order_id = opening_order_id
        self.symbol = symbol.upper()
        self.quantity = quantity
        self.account_id_key = account_id_key
        self.opening_side = opening_side.upper()

        # Confirmation config
        self.confirmation_type = confirmation_type
        self.confirmation_offset = confirmation_offset

        # Stop loss config
        self.stop_loss_type = stop_loss_type
        self.stop_loss_offset = stop_loss_offset

        # Profit config
        self.profit_type = profit_type
        self.profit_offset = profit_offset

        # Timeouts
        self.fill_timeout = fill_timeout
        self.confirmation_timeout = confirmation_timeout

        # State (filled in during lifecycle)
        self.state = BracketState.PENDING_FILL
        self.fill_price: Optional[float] = None
        self.fill_time: Optional[datetime] = None

        # Trigger price (when price reaches this, place bracket)
        self.trigger_price: Optional[float] = None

        # Bracket order IDs (set when bracket is placed)
        self.stop_order_id: Optional[int] = None
        self.profit_order_id: Optional[int] = None

        # Final prices used for bracket
        self.stop_price: Optional[float] = None      # Stop trigger price
        self.stop_limit_price: Optional[float] = None  # Stop limit price
        self.profit_limit_price: Optional[float] = None  # Profit limit price

        # Timestamps
        self.created_at = datetime.utcnow()
        self.bracket_placed_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Error message if any
        self.error_message: Optional[str] = None

    def is_buy_to_open(self) -> bool:
        """Check if opening order is a BUY (vs SELL_SHORT)"""
        return self.opening_side in ['BUY', 'BUY_TO_COVER']

    def calculate_trigger_price(self) -> float:
        """
        Calculate the trigger price based on fill price and confirmation offset.
        For BUY: trigger = fill + offset (wait for price to go up)
        For SELL_SHORT: trigger = fill - offset (wait for price to go down)
        """
        if self.fill_price is None:
            raise ValueError("Fill price not set")

        if self.is_buy_to_open():
            # For long positions, wait for price to rise
            if self.confirmation_type == 'dollar':
                self.trigger_price = self.fill_price + self.confirmation_offset
            else:
                self.trigger_price = self.fill_price * (1 + self.confirmation_offset / 100)
        else:
            # For short positions, wait for price to fall
            if self.confirmation_type == 'dollar':
                self.trigger_price = self.fill_price - self.confirmation_offset
            else:
                self.trigger_price = self.fill_price * (1 - self.confirmation_offset / 100)

        return self.trigger_price

    def calculate_bracket_prices(self, current_price: float) -> tuple:
        """
        Calculate stop and profit prices based on current price (at trigger).

        For BUY positions:
        - Stop loss: current - offset (below current, but above fill = profit)
        - Profit target: current + offset

        For SELL_SHORT positions:
        - Stop loss: current + offset (above current, but below fill = profit)
        - Profit target: current - offset

        Returns: (stop_price, stop_limit_price, profit_limit_price)
        """
        if self.is_buy_to_open():
            # Long position
            if self.stop_loss_type == 'dollar':
                self.stop_price = current_price - self.stop_loss_offset
                self.stop_limit_price = self.stop_price - 0.01  # Slightly below stop for limit
            else:
                self.stop_price = current_price * (1 - self.stop_loss_offset / 100)
                self.stop_limit_price = self.stop_price * 0.9999

            if self.profit_type == 'dollar':
                self.profit_limit_price = current_price + self.profit_offset
            else:
                self.profit_limit_price = current_price * (1 + self.profit_offset / 100)
        else:
            # Short position (reversed)
            if self.stop_loss_type == 'dollar':
                self.stop_price = current_price + self.stop_loss_offset
                self.stop_limit_price = self.stop_price + 0.01  # Slightly above stop for limit
            else:
                self.stop_price = current_price * (1 + self.stop_loss_offset / 100)
                self.stop_limit_price = self.stop_price * 1.0001

            if self.profit_type == 'dollar':
                self.profit_limit_price = current_price - self.profit_offset
            else:
                self.profit_limit_price = current_price * (1 - self.profit_offset / 100)

        # Round to 2 decimal places
        self.stop_price = round(self.stop_price, 2)
        self.stop_limit_price = round(self.stop_limit_price, 2)
        self.profit_limit_price = round(self.profit_limit_price, 2)

        return (self.stop_price, self.stop_limit_price, self.profit_limit_price)

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
            'profit_order_id': self.profit_order_id,
            'stop_price': self.stop_price,
            'stop_limit_price': self.stop_limit_price,
            'profit_limit_price': self.profit_limit_price,
            'confirmation_type': self.confirmation_type,
            'confirmation_offset': self.confirmation_offset,
            'stop_loss_type': self.stop_loss_type,
            'stop_loss_offset': self.stop_loss_offset,
            'profit_type': self.profit_type,
            'profit_offset': self.profit_offset,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'fill_time': self.fill_time.isoformat() if self.fill_time else None,
            'bracket_placed_at': self.bracket_placed_at.isoformat() if self.bracket_placed_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingBracket':
        """Create from dictionary"""
        bracket = cls(
            opening_order_id=data['opening_order_id'],
            symbol=data['symbol'],
            quantity=data['quantity'],
            account_id_key=data['account_id_key'],
            opening_side=data['opening_side'],
            confirmation_type=data.get('confirmation_type', 'dollar'),
            confirmation_offset=data.get('confirmation_offset', 0),
            stop_loss_type=data.get('stop_loss_type', 'dollar'),
            stop_loss_offset=data.get('stop_loss_offset', 0),
            profit_type=data.get('profit_type', 'dollar'),
            profit_offset=data.get('profit_offset', 0),
            fill_timeout=data.get('fill_timeout', 15),
            confirmation_timeout=data.get('confirmation_timeout', 300),
        )

        # Restore state
        bracket.state = data.get('state', BracketState.PENDING_FILL)
        bracket.fill_price = data.get('fill_price')
        bracket.trigger_price = data.get('trigger_price')
        bracket.stop_order_id = data.get('stop_order_id')
        bracket.profit_order_id = data.get('profit_order_id')
        bracket.stop_price = data.get('stop_price')
        bracket.stop_limit_price = data.get('stop_limit_price')
        bracket.profit_limit_price = data.get('profit_limit_price')
        bracket.error_message = data.get('error_message')

        # Restore timestamps
        if data.get('created_at'):
            bracket.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('fill_time'):
            bracket.fill_time = datetime.fromisoformat(data['fill_time'])
        if data.get('bracket_placed_at'):
            bracket.bracket_placed_at = datetime.fromisoformat(data['bracket_placed_at'])
        if data.get('completed_at'):
            bracket.completed_at = datetime.fromisoformat(data['completed_at'])

        return bracket


class BracketManager:
    """
    Manages pending bracket orders.

    In-memory storage for now, can be migrated to Redis for persistence.
    """

    def __init__(self):
        # Key: opening_order_id (int), Value: PendingBracket
        self._brackets: Dict[int, PendingBracket] = {}

    def add_bracket(self, bracket: PendingBracket) -> None:
        """Add a new pending bracket"""
        self._brackets[bracket.opening_order_id] = bracket
        logger.info(f"Added bracket for order {bracket.opening_order_id}: {bracket.symbol} "
                   f"confirm={bracket.confirmation_offset}({bracket.confirmation_type}), "
                   f"stop={bracket.stop_loss_offset}({bracket.stop_loss_type}), "
                   f"profit={bracket.profit_offset}({bracket.profit_type})")

    def get_bracket(self, opening_order_id: int) -> Optional[PendingBracket]:
        """Get bracket by opening order ID"""
        return self._brackets.get(opening_order_id)

    def get_all_brackets(self) -> Dict[int, PendingBracket]:
        """Get all pending brackets"""
        return self._brackets.copy()

    def get_brackets_by_state(self, state: str) -> list:
        """Get all brackets in a specific state"""
        return [b for b in self._brackets.values() if b.state == state]

    def update_bracket(self, bracket: PendingBracket) -> None:
        """Update an existing bracket"""
        self._brackets[bracket.opening_order_id] = bracket

    def remove_bracket(self, opening_order_id: int) -> Optional[PendingBracket]:
        """Remove a bracket"""
        bracket = self._brackets.pop(opening_order_id, None)
        if bracket:
            logger.info(f"Removed bracket for order {opening_order_id}")
        return bracket

    def mark_filled(self, opening_order_id: int, fill_price: float) -> Optional[PendingBracket]:
        """Mark an opening order as filled"""
        bracket = self._brackets.get(opening_order_id)
        if bracket:
            bracket.fill_price = fill_price
            bracket.fill_time = datetime.utcnow()
            bracket.state = BracketState.WAITING_CONFIRMATION
            bracket.calculate_trigger_price()
            logger.info(f"Order {opening_order_id} filled at {fill_price}, "
                       f"waiting for confirmation at {bracket.trigger_price}")
        return bracket

    def mark_bracket_placed(
        self,
        opening_order_id: int,
        stop_order_id: int,
        profit_order_id: int
    ) -> Optional[PendingBracket]:
        """Mark bracket orders as placed"""
        bracket = self._brackets.get(opening_order_id)
        if bracket:
            bracket.stop_order_id = stop_order_id
            bracket.profit_order_id = profit_order_id
            bracket.state = BracketState.BRACKET_PLACED
            bracket.bracket_placed_at = datetime.utcnow()
            logger.info(f"Bracket placed for order {opening_order_id}: "
                       f"stop={stop_order_id} @ {bracket.stop_limit_price}, "
                       f"profit={profit_order_id} @ {bracket.profit_limit_price}")
        return bracket

    def mark_stop_filled(self, opening_order_id: int) -> Optional[PendingBracket]:
        """Mark stop loss order as filled"""
        bracket = self._brackets.get(opening_order_id)
        if bracket:
            bracket.state = BracketState.STOP_FILLED
            bracket.completed_at = datetime.utcnow()
            profit = bracket.stop_limit_price - bracket.fill_price if bracket.is_buy_to_open() else bracket.fill_price - bracket.stop_limit_price
            logger.info(f"Stop loss filled for order {opening_order_id}, profit per share: {profit:.2f}")
        return bracket

    def mark_profit_filled(self, opening_order_id: int) -> Optional[PendingBracket]:
        """Mark profit target as filled"""
        bracket = self._brackets.get(opening_order_id)
        if bracket:
            bracket.state = BracketState.PROFIT_FILLED
            bracket.completed_at = datetime.utcnow()
            profit = bracket.profit_limit_price - bracket.fill_price if bracket.is_buy_to_open() else bracket.fill_price - bracket.profit_limit_price
            logger.info(f"Profit target filled for order {opening_order_id}, profit per share: {profit:.2f}")
        return bracket

    def mark_error(self, opening_order_id: int, error_message: str) -> Optional[PendingBracket]:
        """Mark bracket as error"""
        bracket = self._brackets.get(opening_order_id)
        if bracket:
            bracket.state = BracketState.ERROR
            bracket.error_message = error_message
            bracket.completed_at = datetime.utcnow()
            logger.error(f"Bracket error for order {opening_order_id}: {error_message}")
        return bracket

    def to_json(self) -> str:
        """Serialize all brackets to JSON for storage"""
        data = {str(k): v.to_dict() for k, v in self._brackets.items()}
        return json.dumps(data)

    def from_json(self, json_str: str) -> None:
        """Load brackets from JSON"""
        data = json.loads(json_str)
        self._brackets = {
            int(k): PendingBracket.from_dict(v)
            for k, v in data.items()
        }


# Global bracket manager instance
_bracket_manager = None

def get_bracket_manager() -> BracketManager:
    """Get or create bracket manager instance"""
    global _bracket_manager
    if _bracket_manager is None:
        _bracket_manager = BracketManager()
    return _bracket_manager
