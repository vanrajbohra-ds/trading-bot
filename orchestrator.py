import logging

from config import WATCHLIST, MIN_CONFIDENCE, HIST_PERIOD
from agents.fundamental_agent import FundamentalAgent
from agents.technical_agent import TechnicalAgent
from agents.decision_agent import DecisionAgent
from execution.alpaca_client import AlpacaClient
from execution.risk_manager import RiskManager
from execution.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


def run_cycle():
    alpaca = AlpacaClient()
    risk = RiskManager()
    telegram = TelegramNotifier()
    fundamental_agent = FundamentalAgent()
    technical_agent = TechnicalAgent()
    decision_agent = DecisionAgent()

    if not alpaca.is_market_open():
        logger.info("Market is closed — skipping cycle")
        return

    account = alpaca.get_account()
    positions = alpaca.get_positions()
    logger.info(f"Account: cash=${account['cash']:.2f} portfolio=${account['portfolio_value']:.2f} | Positions: {list(positions.keys())}")

    # --- Risk sweep: stop-loss / take-profit exits ---
    triggers = risk.check_all_stop_take(positions)
    for t in triggers:
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account = alpaca.get_account()
            positions = alpaca.get_positions()

    # --- Agent analysis and trading ---
    trades_placed = 0
    trades_skipped = 0
    decisions_log = []

    for symbol in WATCHLIST:
        logger.info(f"--- Analyzing {symbol} ---")

        fundamental = fundamental_agent.analyze(symbol)
        technical = technical_agent.analyze(symbol, period=HIST_PERIOD)

        pos = positions.get(symbol, {"qty": 0, "avg_entry_price": 0.0})
        decision = decision_agent.decide(
            fundamental=fundamental,
            technical=technical,
            available_cash=account["cash"],
            current_qty=pos["qty"],
            avg_entry_price=pos["avg_entry_price"],
            open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
        )

        logger.info(f"[{symbol}] Decision: {decision.action} confidence={decision.confidence}% | {decision.rationale}")

        decision_entry = {"symbol": symbol, "action": decision.action, "confidence": decision.confidence}

        if decision.confidence < MIN_CONFIDENCE:
            logger.info(f"[{symbol}] Skipped — confidence {decision.confidence}% < threshold {MIN_CONFIDENCE}%")
            decision_entry["skip_reason"] = f"low conf"
            decisions_log.append(decision_entry)
            trades_skipped += 1
            continue

        if decision.action == "HOLD":
            logger.info(f"[{symbol}] HOLD — no trade")
            decisions_log.append(decision_entry)
            trades_skipped += 1
            continue

        if decision.action == "BUY":
            if not risk.can_open_position(symbol, positions):
                logger.info(f"[{symbol}] Skipped BUY — max positions reached")
                decision_entry["skip_reason"] = "max positions"
                decisions_log.append(decision_entry)
                trades_skipped += 1
                continue
            price = technical.current_price or 1.0
            qty = risk.calculate_position_size(decision.confidence, account["cash"], price)
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped BUY — insufficient cash")
                decision_entry["skip_reason"] = "no cash"
                decisions_log.append(decision_entry)
                trades_skipped += 1
                continue
        elif decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped SELL — no position")
                decision_entry["skip_reason"] = "no position"
                decisions_log.append(decision_entry)
                trades_skipped += 1
                continue
        else:
            decisions_log.append(decision_entry)
            trades_skipped += 1
            continue

        result = alpaca.submit_market_order(symbol, decision.action, qty)
        if result["success"]:
            trades_placed += 1
            account = alpaca.get_account()
            positions = alpaca.get_positions()
            decisions_log.append(decision_entry)
            telegram.trade_alert(
                symbol=symbol,
                action=decision.action,
                qty=qty,
                confidence=decision.confidence,
                rationale=decision.rationale,
                cash_remaining=account["cash"],
            )
        else:
            logger.error(f"[{symbol}] Order failed: {result.get('error')}")
            decision_entry["skip_reason"] = "order failed"
            decisions_log.append(decision_entry)
            trades_skipped += 1

    telegram.cycle_summary(
        trades_placed=trades_placed,
        trades_skipped=trades_skipped,
        portfolio_value=account["portfolio_value"],
        cash=account["cash"],
        decisions=decisions_log,
    )
    logger.info(f"Cycle complete — {trades_placed} trades placed, {trades_skipped} skipped")
