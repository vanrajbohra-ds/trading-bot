import logging

from config import (
    WATCHLIST, MIN_CONFIDENCE, HIST_PERIOD,
    CRYPTO_WATCHLIST, CRYPTO_YFINANCE_MAP,
    MAX_CRYPTO_POSITIONS, CRYPTO_STOP_LOSS_PCT, CRYPTO_TAKE_PROFIT_PCT,
    CRYPTO_PORTFOLIO_CAP, MIN_CASH_RESERVE_PCT,
    RESERVE_DEPLOY_CONFIDENCE, RESERVE_MAX_DEPLOY_PCT,
    MOMENTUM_STOCK_WATCHLIST, MOMENTUM_CRYPTO_WATCHLIST,
    MOMENTUM_STOCK_BUDGET_PCT, MOMENTUM_CRYPTO_BUDGET_PCT,
    MOMENTUM_MIN_CONFIDENCE, MOMENTUM_VOLUME_RATIO_MIN,
    MOMENTUM_STOCK_STOP_PCT, MOMENTUM_STOCK_TAKE_PCT,
    MOMENTUM_CRYPTO_STOP_PCT, MOMENTUM_CRYPTO_TAKE_PCT,
    MAX_MOMENTUM_STOCK_POSITIONS, MAX_MOMENTUM_CRYPTO_POSITIONS,
)
from agents.fundamental_agent import FundamentalAgent
from agents.technical_agent import TechnicalAgent
from agents.decision_agent import DecisionAgent
from execution.alpaca_client import AlpacaClient
from execution.risk_manager import RiskManager
from execution.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _investable_cash(account: dict, confidence: int = 0) -> float:
    """Cash available for new positions after honouring the reserve floor.

    Below RESERVE_DEPLOY_CONFIDENCE: reserve is protected.
    At/above RESERVE_DEPLOY_CONFIDENCE: up to half the reserve is unlocked.
    """
    reserve = account["portfolio_value"] * MIN_CASH_RESERVE_PCT
    investable = account["cash"] - reserve

    if investable < 1.0 and confidence >= RESERVE_DEPLOY_CONFIDENCE:
        reserve_budget = reserve * RESERVE_MAX_DEPLOY_PCT
        investable = min(account["cash"], reserve_budget)
        logger.info(
            f"High-conviction signal ({confidence}%) — reserve partially unlocked "
            f"(up to ${investable:,.0f} of the ${reserve:,.0f} floor)"
        )

    return max(0.0, investable)


def _reload_positions(positions: dict, alpaca: AlpacaClient) -> None:
    """Replace positions dict in-place so stale sold/closed positions are removed."""
    new = alpaca.get_positions()
    positions.clear()
    positions.update(new)


def _is_momentum_signal(technical) -> bool:
    """True when at least 2 of 3 momentum indicators are firing:
    - Volume surge  (≥ MOMENTUM_VOLUME_RATIO_MIN × average)
    - RSI trending  (55–75: trending up, not yet overbought)
    - MACD positive (histogram > 0 means momentum is accelerating)
    """
    if technical is None or technical.fetch_error:
        return False
    checks = [
        technical.volume_ratio is not None and technical.volume_ratio >= MOMENTUM_VOLUME_RATIO_MIN,
        technical.rsi is not None and 55 <= technical.rsi <= 75,
        technical.macd_hist is not None and technical.macd_hist > 0,
    ]
    fired = sum(checks)
    if fired >= 2:
        logger.info(
            f"[momentum] signal confirmed — volume_ratio={technical.volume_ratio:.2f} "
            f"rsi={technical.rsi:.1f} macd_hist={technical.macd_hist:.4f} ({fired}/3 checks)"
        )
    return fired >= 2


# ── Core stock cycle ───────────────────────────────────────────────────────────

def _run_stock_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
                     account, positions) -> tuple:
    """Analyze and trade core stocks. Returns (trades_placed, trades_sold)."""
    # Exclude momentum symbols so we don't double-trade them
    momentum_set  = set(MOMENTUM_STOCK_WATCHLIST)
    stock_positions = {s: p for s, p in positions.items()
                       if "/" not in s and s not in momentum_set}
    trades_sold = 0
    for t in risk.check_all_stop_take(stock_positions):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    stock_positions = {s: p for s, p in positions.items()
                       if "/" not in s and s not in momentum_set}

    trades_placed = 0
    for symbol in WATCHLIST:
        logger.info(f"--- [core stock] Analyzing {symbol} ---")
        try:
            fundamental = fundamental_agent.analyze(symbol)
            technical   = technical_agent.analyze(symbol, period=HIST_PERIOD)
        except Exception as e:
            telegram.error_alert(f"Data fetch for {symbol}", str(e))
            continue

        pos = positions.get(symbol, {"qty": 0, "avg_entry_price": 0.0})
        try:
            decision = decision_agent.decide(
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
            )
        except Exception as e:
            telegram.error_alert(f"LLM decision for {symbol}", str(e))
            continue

        logger.info(f"[{symbol}] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            continue

        if decision.action == "BUY":
            if not risk.can_open_position(symbol, stock_positions):
                logger.info(f"[{symbol}] Skipped BUY — max stock positions reached")
                continue
            investable = _investable_cash(account, confidence=decision.confidence)
            if investable < 1.0:
                logger.info(f"[{symbol}] Skipped BUY — reserve floor reached ({decision.confidence}% < {RESERVE_DEPLOY_CONFIDENCE}%)")
                continue
            price = technical.current_price or 1.0
            qty   = risk.calculate_position_size(decision.confidence, investable, price,
                                                  buying_power=account.get("buying_power"))
            if qty <= 0:
                logger.info(f"[{symbol}] Skipped BUY — insufficient investable cash")
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
            _reload_positions(positions, alpaca)
            stock_positions = {s: p for s, p in positions.items()
                               if "/" not in s and s not in momentum_set}
            telegram.trade_alert(symbol, decision.action, qty, decision.confidence,
                                  decision.rationale, account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            logger.error(f"[{symbol}] Order failed: {result.get('error')}")
            telegram.error_alert(f"Order {decision.action} {symbol}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Core crypto cycle ──────────────────────────────────────────────────────────

def _run_crypto_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
                      account, positions) -> tuple:
    """Analyze and trade core crypto (BTC, SOL). Returns (trades_placed, trades_sold)."""
    momentum_crypto_set = set(MOMENTUM_CRYPTO_WATCHLIST)
    core_crypto_positions = {s: p for s, p in positions.items()
                              if "/" in s and s not in momentum_crypto_set}
    trades_sold = 0
    for t in risk.check_all_stop_take(core_crypto_positions,
                                       stop_loss_pct=CRYPTO_STOP_LOSS_PCT,
                                       take_profit_pct=CRYPTO_TAKE_PROFIT_PCT):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    core_crypto_positions = {s: p for s, p in positions.items()
                              if "/" in s and s not in momentum_crypto_set}

    trades_placed = 0
    for alpaca_sym in CRYPTO_WATCHLIST:
        yf_sym = CRYPTO_YFINANCE_MAP[alpaca_sym]
        logger.info(f"--- [core crypto] Analyzing {alpaca_sym} ---")
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
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
            )
        except Exception as e:
            telegram.error_alert(f"LLM decision for {alpaca_sym}", str(e))
            continue

        logger.info(f"[{alpaca_sym}] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            continue

        if decision.action == "BUY":
            core_count = sum(1 for s, p in core_crypto_positions.items() if p["qty"] > 0)
            if alpaca_sym not in core_crypto_positions and core_count >= MAX_CRYPTO_POSITIONS:
                logger.info(f"[{alpaca_sym}] Skipped BUY — max core crypto positions reached")
                continue
            investable = _investable_cash(account, confidence=decision.confidence)
            if investable < 1.0:
                logger.info(f"[{alpaca_sym}] Skipped BUY — reserve floor reached ({decision.confidence}% < {RESERVE_DEPLOY_CONFIDENCE}%)")
                continue
            portfolio_value = account["portfolio_value"]
            current_crypto_value = sum(p.get("market_value", 0) for s, p in positions.items() if "/" in s)
            crypto_cap_budget = portfolio_value * CRYPTO_PORTFOLIO_CAP - current_crypto_value
            if crypto_cap_budget < 1.0:
                logger.info(f"[{alpaca_sym}] Skipped BUY — crypto portfolio cap reached")
                continue
            notional = risk.calculate_notional_size(decision.confidence, investable,
                                                     buying_power=account.get("buying_power"))
            notional = min(notional, crypto_cap_budget)
            if notional < 1.0:
                logger.info(f"[{alpaca_sym}] Skipped BUY — insufficient budget")
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
            _reload_positions(positions, alpaca)
            core_crypto_positions = {s: p for s, p in positions.items()
                                     if "/" in s and s not in momentum_crypto_set}
            telegram.trade_alert(alpaca_sym, decision.action, qty_for_alert,
                                  decision.confidence, decision.rationale, account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            logger.error(f"[{alpaca_sym}] Order failed: {result.get('error')}")
            telegram.error_alert(f"Order {decision.action} {alpaca_sym}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Momentum stock cycle ───────────────────────────────────────────────────────

def _run_momentum_stock_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent,
                               decision_agent, account, positions) -> tuple:
    """High-beta momentum stocks: tighter stop/take, volume+trend entry filter."""
    momentum_positions = {s: p for s, p in positions.items()
                          if s in set(MOMENTUM_STOCK_WATCHLIST)}
    trades_sold = 0

    # Exit momentum positions with TIGHT thresholds
    for t in risk.check_all_stop_take(momentum_positions,
                                       stop_loss_pct=MOMENTUM_STOCK_STOP_PCT,
                                       take_profit_pct=MOMENTUM_STOCK_TAKE_PCT):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], f"[MOMENTUM] {t['reason']}")
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    momentum_positions = {s: p for s, p in positions.items()
                          if s in set(MOMENTUM_STOCK_WATCHLIST)}

    # Budget: 5% of portfolio total for momentum stocks
    portfolio_value = account["portfolio_value"]
    current_momentum_stock_value = sum(p.get("market_value", 0) for p in momentum_positions.values())
    momentum_stock_budget = portfolio_value * MOMENTUM_STOCK_BUDGET_PCT - current_momentum_stock_value

    trades_placed = 0
    for symbol in MOMENTUM_STOCK_WATCHLIST:
        logger.info(f"--- [momentum stock] Analyzing {symbol} ---")
        try:
            fundamental = fundamental_agent.analyze(symbol)
            technical   = technical_agent.analyze(symbol, period=HIST_PERIOD)
        except Exception as e:
            telegram.error_alert(f"Data fetch for {symbol}", str(e))
            continue

        pos = positions.get(symbol, {"qty": 0, "avg_entry_price": 0.0})
        try:
            decision = decision_agent.decide(
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
            )
        except Exception as e:
            telegram.error_alert(f"LLM decision for {symbol}", str(e))
            continue

        logger.info(f"[{symbol}/momentum] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                continue
            result = alpaca.submit_market_order(symbol, "SELL", qty)
            if result["success"]:
                trades_placed += 1
                account.update(alpaca.get_account())
                _reload_positions(positions, alpaca)
                telegram.trade_alert(symbol, "SELL", qty, decision.confidence,
                                      f"[MOMENTUM] {decision.rationale}", account["cash"],
                                      price=technical.current_price,
                                      fundamental=fundamental, technical=technical)
            else:
                telegram.error_alert(f"Momentum SELL {symbol}", result.get("error", ""))
            continue

        if decision.action != "BUY":
            continue

        # Entry filters: higher confidence + momentum technical signal
        if decision.confidence < MOMENTUM_MIN_CONFIDENCE:
            logger.info(f"[{symbol}/momentum] Skipped — confidence {decision.confidence}% < {MOMENTUM_MIN_CONFIDENCE}%")
            continue

        if not _is_momentum_signal(technical):
            logger.info(f"[{symbol}/momentum] Skipped — momentum criteria not met (need volume+RSI+MACD)")
            continue

        # Position count cap
        open_momentum = sum(1 for s, p in momentum_positions.items() if p["qty"] > 0)
        if symbol not in momentum_positions and open_momentum >= MAX_MOMENTUM_STOCK_POSITIONS:
            logger.info(f"[{symbol}/momentum] Skipped BUY — max momentum stock positions reached")
            continue

        # Budget cap
        if momentum_stock_budget < 1.0:
            logger.info(f"[{symbol}/momentum] Skipped BUY — momentum stock budget exhausted")
            continue

        investable = _investable_cash(account, confidence=decision.confidence)
        if investable < 1.0:
            logger.info(f"[{symbol}/momentum] Skipped BUY — reserve floor reached")
            continue

        price = technical.current_price or 1.0
        qty = risk.calculate_position_size(
            decision.confidence,
            min(investable, momentum_stock_budget),
            price, buying_power=account.get("buying_power"),
        )
        if qty <= 0:
            logger.info(f"[{symbol}/momentum] Skipped BUY — qty=0")
            continue

        result = alpaca.submit_market_order(symbol, "BUY", qty)
        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)
            momentum_positions = {s: p for s, p in positions.items()
                                  if s in set(MOMENTUM_STOCK_WATCHLIST)}
            current_momentum_stock_value = sum(p.get("market_value", 0) for p in momentum_positions.values())
            momentum_stock_budget = portfolio_value * MOMENTUM_STOCK_BUDGET_PCT - current_momentum_stock_value
            telegram.trade_alert(symbol, "BUY", qty, decision.confidence,
                                  f"[MOMENTUM] {decision.rationale}", account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            logger.error(f"[{symbol}/momentum] Order failed: {result.get('error')}")
            telegram.error_alert(f"Momentum BUY {symbol}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Momentum crypto cycle ──────────────────────────────────────────────────────

def _run_momentum_crypto_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent,
                                decision_agent, account, positions) -> tuple:
    """High-volatility momentum crypto (DOGE, AVAX): tighter stop/take, trend-filter entry."""
    momentum_crypto_set = set(MOMENTUM_CRYPTO_WATCHLIST)
    momentum_positions = {s: p for s, p in positions.items() if s in momentum_crypto_set}
    trades_sold = 0

    for t in risk.check_all_stop_take(momentum_positions,
                                       stop_loss_pct=MOMENTUM_CRYPTO_STOP_PCT,
                                       take_profit_pct=MOMENTUM_CRYPTO_TAKE_PCT):
        result = alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])
        if result["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], f"[MOMENTUM] {t['reason']}")
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    momentum_positions = {s: p for s, p in positions.items() if s in momentum_crypto_set}

    portfolio_value = account["portfolio_value"]
    current_momentum_crypto_value = sum(p.get("market_value", 0) for p in momentum_positions.values())
    momentum_crypto_budget = portfolio_value * MOMENTUM_CRYPTO_BUDGET_PCT - current_momentum_crypto_value

    # Also check overall crypto portfolio cap
    total_crypto_value = sum(p.get("market_value", 0) for s, p in positions.items() if "/" in s)
    crypto_cap_remaining = portfolio_value * CRYPTO_PORTFOLIO_CAP - total_crypto_value

    trades_placed = 0
    for alpaca_sym in MOMENTUM_CRYPTO_WATCHLIST:
        yf_sym = CRYPTO_YFINANCE_MAP[alpaca_sym]
        logger.info(f"--- [momentum crypto] Analyzing {alpaca_sym} ---")
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
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=len([p for p in positions.values() if p["qty"] > 0]),
            )
        except Exception as e:
            telegram.error_alert(f"LLM decision for {alpaca_sym}", str(e))
            continue

        logger.info(f"[{alpaca_sym}/momentum] {decision.action} conf={decision.confidence}% | {decision.rationale}")

        if decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0:
                continue
            result = alpaca.submit_market_order(alpaca_sym, "SELL", qty)
            if result["success"]:
                trades_placed += 1
                account.update(alpaca.get_account())
                _reload_positions(positions, alpaca)
                telegram.trade_alert(alpaca_sym, "SELL", qty, decision.confidence,
                                      f"[MOMENTUM] {decision.rationale}", account["cash"],
                                      price=technical.current_price,
                                      fundamental=fundamental, technical=technical)
            else:
                telegram.error_alert(f"Momentum SELL {alpaca_sym}", result.get("error", ""))
            continue

        if decision.action != "BUY":
            continue

        if decision.confidence < MOMENTUM_MIN_CONFIDENCE:
            logger.info(f"[{alpaca_sym}/momentum] Skipped — confidence {decision.confidence}% < {MOMENTUM_MIN_CONFIDENCE}%")
            continue

        if not _is_momentum_signal(technical):
            logger.info(f"[{alpaca_sym}/momentum] Skipped — momentum criteria not met")
            continue

        open_momentum = sum(1 for s, p in momentum_positions.items() if p["qty"] > 0)
        if alpaca_sym not in momentum_positions and open_momentum >= MAX_MOMENTUM_CRYPTO_POSITIONS:
            logger.info(f"[{alpaca_sym}/momentum] Skipped BUY — max momentum crypto positions reached")
            continue

        effective_budget = min(momentum_crypto_budget, crypto_cap_remaining)
        if effective_budget < 1.0:
            logger.info(f"[{alpaca_sym}/momentum] Skipped BUY — momentum crypto budget or portfolio cap exhausted")
            continue

        investable = _investable_cash(account, confidence=decision.confidence)
        if investable < 1.0:
            logger.info(f"[{alpaca_sym}/momentum] Skipped BUY — reserve floor reached")
            continue

        notional = risk.calculate_notional_size(
            decision.confidence,
            min(investable, effective_budget),
            buying_power=account.get("buying_power"),
        )
        if notional < 1.0:
            logger.info(f"[{alpaca_sym}/momentum] Skipped BUY — insufficient notional")
            continue

        result = alpaca.submit_crypto_order(alpaca_sym, "BUY", notional)
        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)
            momentum_positions = {s: p for s, p in positions.items() if s in momentum_crypto_set}
            current_momentum_crypto_value = sum(p.get("market_value", 0) for p in momentum_positions.values())
            momentum_crypto_budget = portfolio_value * MOMENTUM_CRYPTO_BUDGET_PCT - current_momentum_crypto_value
            total_crypto_value = sum(p.get("market_value", 0) for s, p in positions.items() if "/" in s)
            crypto_cap_remaining = portfolio_value * CRYPTO_PORTFOLIO_CAP - total_crypto_value
            telegram.trade_alert(alpaca_sym, "BUY", notional, decision.confidence,
                                  f"[MOMENTUM] {decision.rationale}", account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            logger.error(f"[{alpaca_sym}/momentum] Order failed: {result.get('error')}")
            telegram.error_alert(f"Momentum BUY {alpaca_sym}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Main cycle ─────────────────────────────────────────────────────────────────

def run_cycle() -> dict:
    """Run one full trading cycle (core stocks + core crypto + momentum). Returns summary dict."""
    alpaca = AlpacaClient()
    risk   = RiskManager()
    telegram = TelegramNotifier()
    fundamental_agent = FundamentalAgent()
    technical_agent   = TechnicalAgent()
    decision_agent    = DecisionAgent()

    stock_market_open = alpaca.is_market_open()

    try:
        account   = alpaca.get_account()
        positions = alpaca.get_positions()
    except Exception as e:
        telegram.error_alert("Fetching account/positions", str(e))
        raise

    logger.info(
        f"Account: cash=${account['cash']:.2f} "
        f"portfolio=${account['portfolio_value']:.2f} | "
        f"Positions: {list(positions.keys())} | "
        f"Stock market {'OPEN' if stock_market_open else 'CLOSED'}"
    )

    s_placed = s_sold = c_placed = c_sold = ms_placed = ms_sold = mc_placed = mc_sold = 0

    if stock_market_open:
        s_placed,  s_sold  = _run_stock_cycle(
            alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
            account, positions)
        ms_placed, ms_sold = _run_momentum_stock_cycle(
            alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
            account, positions)
    else:
        logger.info("Stock market closed — skipping stock + momentum stock cycles")

    # Crypto (core + momentum) trades 24/7
    c_placed,  c_sold  = _run_crypto_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
        account, positions)
    mc_placed, mc_sold = _run_momentum_crypto_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent, decision_agent,
        account, positions)

    total_placed = s_placed + c_placed + ms_placed + mc_placed
    total_sold   = s_sold   + c_sold   + ms_sold   + mc_sold
    logger.info(
        f"Cycle complete — {total_placed} trades placed, {total_sold} risk exits "
        f"(core: {s_placed}s/{c_placed}c  momentum: {ms_placed}s/{mc_placed}c)"
    )
    return {"trades_placed": total_placed, "trades_sold": total_sold}
