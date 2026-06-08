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

    def calculate_notional_size(self, confidence: int, available_cash: float) -> float:
        """Return dollar notional for a crypto order."""
        fraction = 0.0
        for low, high, frac in POSITION_SIZE_BANDS:
            if low <= confidence <= high:
                fraction = frac
                break
        return round(available_cash * fraction, 2)

    def can_open_position(self, symbol: str, positions: dict, max_positions: int = None) -> bool:
        limit = max_positions if max_positions is not None else MAX_POSITIONS
        if symbol in positions and positions[symbol].get("qty", 0) > 0:
            return True
        distinct_open = sum(1 for p in positions.values() if p.get("qty", 0) > 0)
        return distinct_open < limit

    def check_stop_loss(self, avg_entry: float, current_price: float,
                        stop_loss_pct: float = None) -> bool:
        if avg_entry <= 0:
            return False
        pct = stop_loss_pct if stop_loss_pct is not None else STOP_LOSS_PCT
        return (current_price - avg_entry) / avg_entry <= -pct

    def check_take_profit(self, avg_entry: float, current_price: float,
                          take_profit_pct: float = None) -> bool:
        if avg_entry <= 0:
            return False
        pct = take_profit_pct if take_profit_pct is not None else TAKE_PROFIT_PCT
        return (current_price - avg_entry) / avg_entry >= pct

    def check_all_stop_take(self, positions: dict,
                            stop_loss_pct: float = None,
                            take_profit_pct: float = None) -> list:
        triggers = []
        for symbol, pos in positions.items():
            avg = pos.get("avg_entry_price", 0)
            cur = pos.get("current_price", 0)
            qty = pos.get("qty", 0)
            if qty <= 0:
                continue
            pct = (cur - avg) / avg * 100 if avg > 0 else 0
            if self.check_stop_loss(avg, cur, stop_loss_pct):
                logger.info(f"STOP LOSS triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty,
                                  "reason": f"STOP LOSS {pct:.2f}%"})
            elif self.check_take_profit(avg, cur, take_profit_pct):
                logger.info(f"TAKE PROFIT triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty,
                                  "reason": f"TAKE PROFIT {pct:.2f}%"})
        return triggers
