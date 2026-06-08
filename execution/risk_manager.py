import logging
from config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_POSITIONS, POSITION_SIZE_BANDS

logger = logging.getLogger(__name__)


class RiskManager:
    def calculate_position_size(self, confidence: int, available_cash: float, price: float) -> int:
        fraction = 0.0
        for low, high, frac in POSITION_SIZE_BANDS:
            if low <= confidence <= high:
                fraction = frac
                break
        if fraction == 0 or price <= 0:
            return 0
        shares = int((available_cash * fraction) / price)
        return max(1, shares)

    def check_stop_loss(self, avg_entry: float, current_price: float) -> bool:
        if avg_entry <= 0:
            return False
        return (current_price - avg_entry) / avg_entry <= -STOP_LOSS_PCT

    def check_take_profit(self, avg_entry: float, current_price: float) -> bool:
        if avg_entry <= 0:
            return False
        return (current_price - avg_entry) / avg_entry >= TAKE_PROFIT_PCT

    def check_all_stop_take(self, positions: dict) -> list:
        triggers = []
        for symbol, pos in positions.items():
            avg = pos.get("avg_entry_price", 0)
            cur = pos.get("current_price", 0)
            qty = pos.get("qty", 0)
            if qty <= 0:
                continue
            pct = (cur - avg) / avg * 100 if avg > 0 else 0
            if self.check_stop_loss(avg, cur):
                logger.info(f"STOP LOSS triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty, "reason": f"STOP LOSS {pct:.2f}%"})
            elif self.check_take_profit(avg, cur):
                logger.info(f"TAKE PROFIT triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty, "reason": f"TAKE PROFIT {pct:.2f}%"})
        return triggers

    def can_open_position(self, symbol: str, positions: dict) -> bool:
        if symbol in positions and positions[symbol].get("qty", 0) > 0:
            return True
        distinct_open = sum(1 for s, p in positions.items() if p.get("qty", 0) > 0)
        return distinct_open < MAX_POSITIONS
