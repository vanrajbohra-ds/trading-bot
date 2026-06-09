import logging

from config import (
    WATCHLIST, MIN_CONFIDENCE, HIST_PERIOD,
    CRYPTO_WATCHLIST, CRYPTO_YFINANCE_MAP,
    MAX_CRYPTO_POSITIONS, CRYPTO_STOP_LOSS_PCT, CRYPTO_TAKE_PROFIT_PCT,
)
from agents.fundamental_agent import FundamentalAgent
from agents.technical_agent import TechnicalAgent
from agents.decision_agent import DecisionAgent
from execution.alpaca_client import AlpacaClient
from execution.risk_manager import RiskManager
from execution.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


def _reload_positions(positions: dict, alpaca: AlpacaClient) -> None:
    """Replace positions dict in-place so stale sold/closed positions are removed."""
    new = alpaca.get_positions()
    positions.clear()
    positions.update(new)


def _run_stock_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
                     account, positions) -> tuple:
    """Analyze and trade stocks. Returns (trades_placed, trades_sold)."""
    stock_positions = {s: p for s, p in positions.items() if "/" not in s}
    trades_sold = 0
    for t in risk.check_all_stop_take(stock_positions):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)    # clear+update — removes sold positions

    # Rebuild after risk sweep so agent sees fresh state
    stock_positions = {s: p for s, p in positions.items() if "/" not in s}

    trades_placed = 0
    for symbol in WATCHLIST:
        logger.info(f"--- Analyzing {symbol} ---")

        try:
            fundamental = fundamental_agent.analyze(symbol)
            technical   = technical_agent.analyze(symbol, period=HIST_PERIOD)
        except Exception as e:
            telegram.error_alert(f"Data fetch for {symbol}", str(e))
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
            continue

        logger.info(f"[{symbol}] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            logger.info(f"[{symbol}] Skipped — {decision.action} ({decision.confidence}%)")
            continue

        if decision.action == "BUY":
            if not risk.can_open_position(symbol, stock_positions):
                logger.info(f"[{symbol}] Skipped BUY — max stock positions reached")
                continue
            price = technical.current_price or 1.0
            qty   = risk.calculate_position_size(
                decision.confidence, account["cash"], price,
                buying_power=account.get("buying_power"),
            )
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped BUY — insufficient cash/buying power")
                continue
        elif decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped SELL — no position")
                continue
        else:
            continue

        result = alpaca.submit_market_order(symbol, decision.action, qty)
        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)    # clear+update
            stock_positions = {s: p for s, p in positions.items() if "/" not in s}
            telegram.trade_alert(
                symbol, decision.action, qty,
                decision.confidence, decision.rationale, account["cash"],
                price=technical.current_price,
                fundamental=fundamental,
                technical=technical,
            )
        else:
            logger.error(f"[{symbol}] Order failed: {result.get('error')}")
            telegram.error_alert(f"Order {decision.action} {symbol}", result.get("error", ""))

    return trades_placed, trades_sold


def _run_crypto_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
                      account, positions) -> tuple:
    """Analyze and trade crypto. Returns (trades_placed, trades_sold)."""
    crypto_positions = {s: p for s, p in positions.items() if "/" in s}
    trades_sold = 0
    for t in risk.check_all_stop_take(crypto_positions,
                                       stop_loss_pct=CRYPTO_STOP_LOSS_PCT,
                                       take_profit_pct=CRYPTO_TAKE_PROFIT_PCT):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)    # clear+update — removes sold crypto

    # Rebuild after risk sweep
    crypto_positions = {s: p for s, p in positions.items() if "/" in s}

    trades_placed = 0
    for alpaca_sym in CRYPTO_WATCHLIST:
        yf_sym = CRYPTO_YFINANCE_MAP[alpaca_sym]
        logger.info(f"--- Analyzing {alpaca_sym} ---")

        try:
            fundamental = fundamental_agent.analyze(alpaca_sym, yf_symbol=yf_sym)
            technical   = technical_agent.analyze(yf_sym, period=HIST_PERIOD)
            technical.symbol = alpaca_sym
        except Exception as e:
            telegram.error_alert(f"Data fetch for {alpaca_sym}", str(e))
            continue

        pos = positions.get(alpaca_sym, {"qty": 0, "avg_entry_price": 0.0})
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
            telegram.error_alert(f"LLM decision for {alpaca_sym}", str(e))
            continue

        logger.info(f"[{alpaca_sym}] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            logger.info(f"[{alpaca_sym}] Skipped — {decision.action} ({decision.confidence}%)")
            continue

        if decision.action == "BUY":
            crypto_pos_count = sum(1 for s, p in crypto_positions.items() if p["qty"] > 0)
            if alpaca_sym not in crypto_positions and crypto_pos_count >= MAX_CRYPTO_POSITIONS:
                logger.info(f"[{alpaca_sym}] Skipped BUY — max crypto positions reached")
                continue
            notional = risk.calculate_notional_size(
                decision.confidence, account["cash"],
                buying_power=account.get("buying_power"),
            )
            if notional < 1.0:
                logger.info(f"[{alpaca_sym}] Skipped BUY — insufficient cash")
                continue
            result = alpaca.submit_crypto_order(alpaca_sym, "BUY", notional)
            qty_for_alert = notional
        elif decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                logger.info(f"[{alpaca_sym}] Skipped SELL — no position")
                continue
            result = alpaca.submit_market_order(alpaca_sym, "SELL", qty)
            qty_for_alert = qty
        else:
            continue

        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)    # clear+update
            crypto_positions = {s: p for s, p in positions.items() if "/" in s}
            telegram.trade_alert(
                alpaca_sym, decision.action, qty_for_alert,
                decision.confidence, decision.rationale, account["cash"],
                price=technical.current_price,
                fundamental=fundamental,
                technical=technical,
            )
        else:
            logger.error(f"[{alpaca_sym}] Order failed: {result.get('error')}")
            telegram.error_alert(f"Order {decision.action} {alpaca_sym}", result.get("error", ""))

    return trades_placed, trades_sold


def run_cycle() -> dict:
    """Run one full trading cycle (stocks + crypto). Returns summary dict."""
    alpaca = AlpacaClient()
    risk   = RiskManager()
    telegram = TelegramNotifier()
    fundamental_agent = FundamentalAgent()
    technical_agent   = TechnicalAgent()
    decision_agent    = DecisionAgent()

    if not alpaca.is_market_open():
        logger.info("Market is closed — skipping cycle")
        return {"trades_placed": 0, "trades_sold": 0}

    try:
        account   = alpaca.get_account()
        positions = alpaca.get_positions()
    except Exception as e:
        telegram.error_alert("Fetching account/positions", str(e))
        raise

    logger.info(
        f"Account: cash=${account['cash']:.2f} "
        f"portfolio=${account['portfolio_value']:.2f} | "
        f"Positions: {list(positions.keys())}"
    )

    s_placed, s_sold = _run_stock_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
        account, positions,
    )

    c_placed, c_sold = _run_crypto_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
        account, positions,
    )

    total_placed = s_placed + c_placed
    total_sold   = s_sold + c_sold
    logger.info(f"Cycle complete — {total_placed} trades placed, {total_sold} risk exits")
    return {"trades_placed": total_placed, "trades_sold": total_sold}
