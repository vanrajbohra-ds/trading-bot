import logging

from config import WATCHLIST, MIN_CONFIDENCE, HIST_PERIOD
from agents.fundamental_agent import FundamentalAgent
from agents.technical_agent import TechnicalAgent
from agents.decision_agent import DecisionAgent
from execution.alpaca_client import AlpacaClient
from execution.risk_manager import RiskManager
from execution.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


def run_cycle() -> dict:
    """Run one trading cycle. Returns summary dict for end-of-day reporting."""
    alpaca = AlpacaClient()
    risk = RiskManager()
    telegram = TelegramNotifier()
    fundamental_agent = FundamentalAgent()
    technical_agent = TechnicalAgent()
    decision_agent = DecisionAgent()

    if not alpaca.is_market_open():
        logger.info("Market is closed — skipping cycle")
        return {"trades_placed": 0, "trades_sold": 0}

    try:
        account = alpaca.get_account()
        positions = alpaca.get_positions()
    except Exception as e:
        telegram.error_alert("Fetching account/positions", str(e))
        raise

    logger.info(
        f"Account: cash=${account['cash']:.2f} "
        f"portfolio=${account['portfolio_value']:.2f} | "
        f"Positions: {list(positions.keys())}"
    )

    # --- Risk sweep: stop-loss / take-profit exits ---
    trades_sold = 0
    triggers = risk.check_all_stop_take(positions)
    for t in triggers:
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account = alpaca.get_account()
            positions = alpaca.get_positions()

    # --- Agent analysis and trading ---
    trades_placed = 0
    trades_skipped = 0

    for symbol in WATCHLIST:
        logger.info(f"--- Analyzing {symbol} ---")

        try:
            fundamental = fundamental_agent.analyze(symbol)
            technical = technical_agent.analyze(symbol, period=HIST_PERIOD)
        except Exception as e:
            telegram.error_alert(f"Data fetch for {symbol}", str(e))
            trades_skipped += 1
            continue

        pos = positions.get(symbol, {"qty": 0, "avg_entry_price": 0.0})

        try:
            decision = decision_agent.decide(
                fundamental=fundamental,
                technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"],
                avg_entry_price=pos["avg_entry_price"],
                open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
            )
        except Exception as e:
            telegram.error_alert(f"LLM decision for {symbol}", str(e))
            trades_skipped += 1
            continue

        logger.info(
            f"[{symbol}] Decision: {decision.action} "
            f"confidence={decision.confidence}% | {decision.rationale}"
        )

        if decision.confidence < MIN_CONFIDENCE:
            logger.info(
                f"[{symbol}] Skipped — confidence {decision.confidence}% "
                f"< threshold {MIN_CONFIDENCE}%"
            )
            trades_skipped += 1
            continue

        if decision.action == "HOLD":
            logger.info(f"[{symbol}] HOLD — no trade")
            trades_skipped += 1
            continue

        if decision.action == "BUY":
            if not risk.can_open_position(symbol, positions):
                logger.info(f"[{symbol}] Skipped BUY — max positions reached")
                trades_skipped += 1
                continue
            price = technical.current_price or 1.0
            qty = risk.calculate_position_size(decision.confidence, account["cash"], price)
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped BUY — insufficient cash")
                trades_skipped += 1
                continue
        elif decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped SELL — no position")
                trades_skipped += 1
                continue
        else:
            trades_skipped += 1
            continue

        result = alpaca.submit_market_order(symbol, decision.action, qty)
        if result["success"]:
            trades_placed += 1
            account = alpaca.get_account()
            positions = alpaca.get_positions()
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
            telegram.error_alert(
                f"Order {decision.action} {symbol}",
                result.get("error", "unknown error"),
            )
            trades_skipped += 1

    logger.info(f"Cycle complete — {trades_placed} trades placed, {trades_skipped} skipped")
    return {"trades_placed": trades_placed, "trades_sold": trades_sold}
