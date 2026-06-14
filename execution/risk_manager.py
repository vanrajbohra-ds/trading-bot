import logging
from config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_POSITIONS, POSITION_SIZE_BANDS

logger = logging.getLogger(__name__)


class RiskManager:
    def calculate_position_size(self, confidence: int, available_cash: float,
                               price: float, buying_power: float = None) -> int:
        fraction = 0.0
        for low, high, frac in POSITION_SIZE_BANDS:
            if low <= confidence <= high:
                fraction = frac
                break
        if fraction == 0 or price <= 0:
            return 0
        # Use the smaller of (fraction of cash) and (actual buying power) to avoid rejected orders
        budget = available_cash * fraction
        if buying_power is not None:
            budget = min(budget, buying_power)
        shares = int(budget / price)
        return max(1, shares) if budget >= price else 0

    def calculate_notional_size(self, confidence: int, available_cash: float,
                                buying_power: float = None) -> float:
        """Return dollar notional for a crypto order."""
        fraction = 0.0
        for low, high, frac in POSITION_SIZE_BANDS:
            if low <= confidence <= high:
                fraction = frac
                break
        budget = available_cash * fraction
        if buying_power is not None:
            budget = min(budget, buying_power)
        return round(budget, 2)

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
                            take_profit_pct: float = None,
                            stops_data: dict = None) -> list:
        """Check each position for stop-loss or take-profit.

        Priority: ATR-based absolute prices from stops_data (set at entry).
        Fallback: percentage thresholds from config when no stops_data entry exists
        (covers positions opened before dynamic stops were deployed).
        """
        triggers = []
        for symbol, pos in positions.items():
            avg = pos.get("avg_entry_price", 0)
            cur = pos.get("current_price", 0)
            qty = pos.get("qty", 0)
            if qty <= 0:
                continue
            pct = (cur - avg) / avg * 100 if avg > 0 else 0

            dynamic = (stops_data or {}).get(symbol)
            if dynamic:
                stop_hit   = cur <= dynamic["stop_price"]
                target_hit = cur >= dynamic["target_price"]
                stop_reason   = (f"STOP LOSS {pct:.2f}% "
                                 f"[ATR stop ${dynamic['stop_price']:.4f} / −{dynamic['stop_pct']:.1f}%]")
                target_reason = (f"TAKE PROFIT {pct:.2f}% "
                                 f"[ATR target ${dynamic['target_price']:.4f} / +{dynamic['target_pct']:.1f}%]")
            else:
                stop_hit      = self.check_stop_loss(avg, cur, stop_loss_pct)
                target_hit    = self.check_take_profit(avg, cur, take_profit_pct)
                stop_reason   = f"STOP LOSS {pct:.2f}% [config fallback]"
                target_reason = f"TAKE PROFIT {pct:.2f}% [config fallback]"

            if stop_hit:
                logger.info(f"STOP LOSS triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty,
                                  "reason": stop_reason})
            elif target_hit:
                logger.info(f"TAKE PROFIT triggered for {symbol}: {pct:.2f}%")
                triggers.append({"symbol": symbol, "action": "SELL", "qty": qty,
                                  "reason": target_reason})
        return triggers
