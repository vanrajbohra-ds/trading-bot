import logging
import yfinance as yf

from config import (
    WATCHLIST, MIN_CONFIDENCE, HIST_PERIOD,
    CRYPTO_WATCHLIST, CRYPTO_YFINANCE_MAP,
    MAX_CRYPTO_POSITIONS, CRYPTO_STOP_LOSS_PCT, CRYPTO_TAKE_PROFIT_PCT,
    CRYPTO_PORTFOLIO_CAP, MIN_CASH_RESERVE_PCT,
    RESERVE_DEPLOY_CONFIDENCE, RESERVE_MAX_DEPLOY_PCT,
    MOMENTUM_CRYPTO_UNIVERSE, MOMENTUM_SCREENER_LIMIT,
    MOMENTUM_TOTAL_BUDGET_PCT, MAX_MOMENTUM_POSITIONS,
    MOMENTUM_MIN_CONFIDENCE, MOMENTUM_VOLUME_RATIO_MIN,
    MOMENTUM_STOCK_STOP_PCT, MOMENTUM_STOCK_TAKE_PCT,
    MOMENTUM_CRYPTO_STOP_PCT, MOMENTUM_CRYPTO_TAKE_PCT,
)
from execution.market_scanner import get_momentum_candidates
from agents.fundamental_agent import FundamentalAgent
from agents.technical_agent import TechnicalAgent
from agents.decision_agent import DecisionAgent
from execution.alpaca_client import AlpacaClient
from execution.risk_manager import RiskManager
from execution.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)

STARTING_CAPITAL   = 100_000.0
DAILY_LOSS_LIMIT   = 0.03   # pause NEW buys if portfolio drops >3% from starting capital


# ── Market regime ──────────────────────────────────────────────────────────────

def _is_bull_market() -> bool:
    """True when SPY is above its 20-day SMA — broad market in uptrend.
    Gates stock BUY orders. Sells and stop-losses always run regardless."""
    try:
        spy   = yf.Ticker("SPY").history(period="1mo", interval="1d")
        if len(spy) < 20:
            return True  # not enough data — don't block
        sma20 = float(spy["Close"].rolling(20).mean().iloc[-1])
        price = float(spy["Close"].iloc[-1])
        bull  = price > sma20
        logger.info(f"[regime] SPY={price:.2f}  SMA20={sma20:.2f}  {'BULL ✓' if bull else 'BEAR — skipping stock BUYs'}")
        return bull
    except Exception as e:
        logger.warning(f"[regime] SPY check failed ({e}) — allowing buys")
        return True


def _ok_to_buy(account: dict) -> bool:
    """False when portfolio is down >3% from starting capital.
    Prevents doubling down into a deepening drawdown."""
    loss_pct = (STARTING_CAPITAL - account["portfolio_value"]) / STARTING_CAPITAL
    if loss_pct > DAILY_LOSS_LIMIT:
        logger.warning(
            f"[circuit-breaker] Portfolio down {loss_pct:.1%} "
            f"(${account['portfolio_value']:,.0f}) — pausing new BUYs"
        )
        return False
    return True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_macro_context(bull_market: bool, account: dict) -> str:
    """One-paragraph market backdrop injected into every LLM decision prompt."""
    regime = (
        "BULL — SPY is above its 20-day SMA (stock buys permitted)"
        if bull_market else
        "BEAR — SPY is below its 20-day SMA (raise confidence bar by 5 pts for any BUY)"
    )
    drawdown = (STARTING_CAPITAL - account["portfolio_value"]) / STARTING_CAPITAL * 100
    status = (
        f"{drawdown:.1f}% drawdown from ${STARTING_CAPITAL:,.0f} starting capital"
        if drawdown > 0 else
        f"{abs(drawdown):.1f}% gain above starting capital"
    )
    return (
        "MACRO CONTEXT:\n"
        f"  Market Regime:    {regime}\n"
        f"  Portfolio Status: {status}"
    )


def _investable_cash(account: dict, confidence: int = 0) -> float:
    """Cash available after the 20% reserve floor.
    Reserve unlocks partially only at >= RESERVE_DEPLOY_CONFIDENCE."""
    reserve    = account["portfolio_value"] * MIN_CASH_RESERVE_PCT
    investable = account["cash"] - reserve

    if investable < 1.0 and confidence >= RESERVE_DEPLOY_CONFIDENCE:
        reserve_budget = reserve * RESERVE_MAX_DEPLOY_PCT
        investable     = min(account["cash"], reserve_budget)
        logger.info(
            f"High-conviction signal ({confidence}%) — reserve partially unlocked "
            f"(up to ${investable:,.0f} of the ${reserve:,.0f} floor)"
        )
    return max(0.0, investable)


def _reload_positions(positions: dict, alpaca: AlpacaClient) -> None:
    """Replace positions dict in-place — prevents stale sold entries causing double-sells."""
    new = alpaca.get_positions()
    positions.clear()
    positions.update(new)


def _is_momentum_signal(technical) -> bool:
    """True when at least 2 of 3 momentum checks fire:
      - Volume surge  : volume_ratio >= MOMENTUM_VOLUME_RATIO_MIN
      - RSI trending  : 55 <= RSI <= 75  (uptrend, not yet overbought)
      - MACD positive : histogram > 0    (momentum accelerating)
    Requiring 2/3 reduces false positives while still catching early moves.
    """
    if technical is None or technical.fetch_error:
        return False
    checks = [
        technical.volume_ratio is not None and technical.volume_ratio >= MOMENTUM_VOLUME_RATIO_MIN,
        technical.rsi         is not None and 55 <= technical.rsi <= 75,
        technical.macd_hist   is not None and technical.macd_hist > 0,
    ]
    fired = sum(checks)
    if fired >= 2:
        logger.info(
            f"  momentum check: volume={technical.volume_ratio:.2f}x "
            f"rsi={technical.rsi:.1f} macd={technical.macd_hist:.4f} → {fired}/3 fired"
        )
    return fired >= 2


# ── Core stock cycle ───────────────────────────────────────────────────────────

def _run_stock_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent,
                     decision_agent, account, positions,
                     bull_market: bool = True,
                     macro_context: str = "") -> tuple:
    """Core WATCHLIST stocks. Returns (trades_placed, trades_sold)."""
    # Exclude crypto momentum symbols so they're never treated as stocks
    excl = set(MOMENTUM_CRYPTO_UNIVERSE)
    stock_pos = {s: p for s, p in positions.items() if "/" not in s and s not in excl}

    trades_sold = 0
    for t in risk.check_all_stop_take(stock_pos):
        if alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    stock_pos = {s: p for s, p in positions.items() if "/" not in s and s not in excl}

    trades_placed = 0
    for symbol in WATCHLIST:
        logger.info(f"--- [core] {symbol} ---")
        try:
            fundamental = fundamental_agent.analyze(symbol)
            technical   = technical_agent.analyze(symbol, period=HIST_PERIOD)
        except Exception as e:
            telegram.error_alert(f"Data fetch {symbol}", str(e)); continue

        pos = positions.get(symbol, {"qty": 0, "avg_entry_price": 0.0})
        try:
            decision = decision_agent.decide(
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=sum(1 for p in positions.values() if p["qty"] > 0),
                macro_context=macro_context,
            )
        except Exception as e:
            telegram.error_alert(f"LLM {symbol}", str(e)); continue

        logger.info(f"[{symbol}] {decision.action} {decision.confidence}% | {decision.rationale}")
        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            continue

        if decision.action == "BUY":
            if not bull_market:
                logger.info(f"[{symbol}] BUY skipped — SPY below SMA20 (bear regime)")
                continue
            if not _ok_to_buy(account):
                continue
            if not risk.can_open_position(symbol, stock_pos):
                continue
            investable = _investable_cash(account, decision.confidence)
            if investable < 1.0:
                logger.info(f"[{symbol}] Skipped — reserve floor ({decision.confidence}% < {RESERVE_DEPLOY_CONFIDENCE}%)")
                continue
            qty = risk.calculate_position_size(decision.confidence, investable,
                                               technical.current_price or 1.0,
                                               buying_power=account.get("buying_power"))
            if qty <= 0: continue
        elif decision.action == "SELL":
            # Re-read from live positions (not stale snapshot) to prevent accidental shorts
            # when stop/take already sold this symbol and positions haven't been reloaded yet.
            qty = positions.get(symbol, {}).get("qty", 0)
            if qty <= 0: continue
        else:
            continue

        result = alpaca.submit_market_order(symbol, decision.action, qty)
        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)
            stock_pos = {s: p for s, p in positions.items() if "/" not in s and s not in excl}
            telegram.trade_alert(symbol, decision.action, qty, decision.confidence,
                                  decision.rationale, account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            telegram.error_alert(f"Order {decision.action} {symbol}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Core crypto cycle ──────────────────────────────────────────────────────────

def _run_crypto_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent,
                      decision_agent, account, positions,
                      recently_bought: set = None,
                      macro_context: str = "") -> tuple:
    """Core crypto (BTC, SOL). Returns (trades_placed, trades_sold)."""
    excl = set(MOMENTUM_CRYPTO_UNIVERSE)
    core_crypto = {s: p for s, p in positions.items() if "/" in s and s not in excl}

    trades_sold = 0
    for t in risk.check_all_stop_take(core_crypto,
                                       stop_loss_pct=CRYPTO_STOP_LOSS_PCT,
                                       take_profit_pct=CRYPTO_TAKE_PROFIT_PCT):
        if alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], t["reason"])
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    core_crypto = {s: p for s, p in positions.items() if "/" in s and s not in excl}

    trades_placed = 0
    for alpaca_sym in CRYPTO_WATCHLIST:
        yf_sym = CRYPTO_YFINANCE_MAP[alpaca_sym]
        logger.info(f"--- [core crypto] {alpaca_sym} ---")
        try:
            fundamental = fundamental_agent.analyze(alpaca_sym, yf_symbol=yf_sym)
            technical   = technical_agent.analyze(yf_sym, period=HIST_PERIOD)
            technical.symbol = alpaca_sym
        except Exception as e:
            telegram.error_alert(f"Data fetch {alpaca_sym}", str(e)); continue

        pos = positions.get(alpaca_sym, {"qty": 0, "avg_entry_price": 0.0})
        try:
            decision = decision_agent.decide(
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=sum(1 for p in positions.values() if p["qty"] > 0),
                macro_context=macro_context,
            )
        except Exception as e:
            telegram.error_alert(f"LLM {alpaca_sym}", str(e)); continue

        logger.info(f"[{alpaca_sym}] {decision.action} {decision.confidence}% | {decision.rationale}")
        if decision.confidence < MIN_CONFIDENCE or decision.action == "HOLD":
            continue

        if decision.action == "BUY":
            # Dedup guard: Alpaca positions API lags 2-3min after a crypto fill.
            # Check orders history so we never re-buy a symbol we just bought.
            if recently_bought and alpaca_sym in recently_bought:
                logger.info(f"[{alpaca_sym}] BUY skipped — recent buy order exists (dedup)")
                continue
            core_count = sum(1 for s, p in core_crypto.items() if p["qty"] > 0)
            if alpaca_sym not in core_crypto and core_count >= MAX_CRYPTO_POSITIONS:
                continue
            investable = _investable_cash(account, decision.confidence)
            if investable < 1.0:
                continue
            pv = account["portfolio_value"]
            total_crypto_val = sum(p.get("market_value", 0) for s, p in positions.items() if "/" in s)
            cap_budget = pv * CRYPTO_PORTFOLIO_CAP - total_crypto_val
            if cap_budget < 1.0:
                logger.info(f"[{alpaca_sym}] Skipped — crypto portfolio cap reached")
                continue
            notional = min(
                risk.calculate_notional_size(decision.confidence, investable,
                                             buying_power=account.get("buying_power")),
                cap_budget,
            )
            if notional < 10.0: continue
            result = alpaca.submit_crypto_order(alpaca_sym, "BUY", notional)
            qty_for_alert = notional
        elif decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0: continue
            result = alpaca.submit_market_order(alpaca_sym, "SELL", qty)
            qty_for_alert = qty
        else:
            continue

        if result["success"]:
            trades_placed += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)
            core_crypto = {s: p for s, p in positions.items() if "/" in s and s not in excl}
            telegram.trade_alert(alpaca_sym, decision.action, qty_for_alert,
                                  decision.confidence, decision.rationale, account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            telegram.error_alert(f"Order {decision.action} {alpaca_sym}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Momentum cycle ─────────────────────────────────────────────────────────────

def _run_momentum_cycle(alpaca, risk, telegram, fundamental_agent, technical_agent,
                        decision_agent, account, positions,
                        stock_market_open: bool = True, bull_market: bool = True,
                        recently_bought: set = None,
                        macro_context: str = "") -> tuple:
    """
    Hunts for momentum across a broad universe of high-beta stocks + volatile crypto.

    Flow:
      1. Exit existing momentum positions (tight stop/take, no LLM needed).
      2. Technical pre-scan across the full universe — only calls yfinance, no LLM.
      3. Sort candidates by volume ratio (strongest surge first).
      4. Call LLM only for the top N candidates that have available budget slots.
      This keeps LLM call count low even with a large universe.

    Single shared 10% budget across ALL momentum positions (stocks + crypto combined).
    """
    # Exclude core symbols so we never double-trade the same asset.
    core_syms = set(WATCHLIST) | set(CRYPTO_WATCHLIST)

    # Live screener: ask Yahoo Finance what stocks are actually moving today.
    # Falls back to an empty list if the screener is unavailable — the cycle
    # will still run crypto momentum and exit any open momentum positions.
    if stock_market_open:
        stock_universe = get_momentum_candidates(
            limit_per_screen=MOMENTUM_SCREENER_LIMIT,
            exclude=core_syms,
        )
    else:
        stock_universe = []  # no point scanning stocks when market is closed

    crypto_universe = [s for s in MOMENTUM_CRYPTO_UNIVERSE if s not in core_syms]
    all_universe    = stock_universe + crypto_universe
    universe_set    = set(all_universe)

    # Also include any symbols we're already holding (in case screener misses them)
    open_momentum_held = {s for s in positions if s not in core_syms and positions[s]["qty"] > 0}
    universe_set |= open_momentum_held
    all_universe  = list(universe_set)

    momentum_pos = {s: p for s, p in positions.items() if s in universe_set}

    # ── 1. Exit momentum positions with TIGHT thresholds ──────────────────────
    trades_sold = 0
    stock_mom  = {s: p for s, p in momentum_pos.items() if "/" not in s}
    crypto_mom = {s: p for s, p in momentum_pos.items() if "/" in s}

    for t in risk.check_all_stop_take(stock_mom,
                                       stop_loss_pct=MOMENTUM_STOCK_STOP_PCT,
                                       take_profit_pct=MOMENTUM_STOCK_TAKE_PCT):
        if alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], f"[MOMENTUM] {t['reason']}")
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    for t in risk.check_all_stop_take(crypto_mom,
                                       stop_loss_pct=MOMENTUM_CRYPTO_STOP_PCT,
                                       take_profit_pct=MOMENTUM_CRYPTO_TAKE_PCT):
        if alpaca.submit_market_order(t["symbol"], "SELL", t["qty"])["success"]:
            trades_sold += 1
            telegram.risk_exit_alert(t["symbol"], t["qty"], f"[MOMENTUM] {t['reason']}")
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)

    momentum_pos = {s: p for s, p in positions.items() if s in universe_set}

    # ── 2. Budget check ────────────────────────────────────────────────────────
    pv = account["portfolio_value"]
    total_momentum_val = sum(p.get("market_value", 0) for p in momentum_pos.values())
    momentum_budget    = pv * MOMENTUM_TOTAL_BUDGET_PCT - total_momentum_val

    open_momentum_count = sum(1 for p in momentum_pos.values() if p["qty"] > 0)
    slots_available     = MAX_MOMENTUM_POSITIONS - open_momentum_count

    logger.info(
        f"[momentum] budget=${momentum_budget:,.0f} | "
        f"positions {open_momentum_count}/{MAX_MOMENTUM_POSITIONS}"
    )

    # ── 3. Technical pre-scan — no LLM, just yfinance ─────────────────────────
    # Already-open momentum positions are always included so the LLM can decide to SELL.
    open_syms       = {s for s, p in momentum_pos.items() if p["qty"] > 0}
    signal_hits     = []   # (symbol, technical, is_crypto)

    for sym in all_universe:
        is_crypto = "/" in sym
        if not stock_market_open and not is_crypto:
            continue  # stocks need an open market

        yf_sym = CRYPTO_YFINANCE_MAP.get(sym, sym) if is_crypto else sym
        try:
            technical = technical_agent.analyze(yf_sym, period=HIST_PERIOD)
            if is_crypto:
                technical.symbol = sym
        except Exception as e:
            logger.warning(f"[momentum] Technical fetch failed for {sym}: {e}")
            continue

        if sym in open_syms or _is_momentum_signal(technical):
            signal_hits.append((sym, technical, is_crypto))

    # Sort by volume ratio descending (strongest surge first); open positions first
    signal_hits.sort(key=lambda x: (
        x[0] not in open_syms,               # open positions come first
        -(x[1].volume_ratio or 0),            # then highest volume
    ))

    # Keep: all open positions (for possible SELL) + top `slots_available` new candidates
    new_hits    = [(s, t, c) for s, t, c in signal_hits if s not in open_syms]
    final_hits  = [(s, t, c) for s, t, c in signal_hits if s in open_syms]
    final_hits += new_hits[:max(0, slots_available)]

    if not final_hits:
        logger.info("[momentum] No momentum signals found this cycle")
        return 0, trades_sold

    logger.info(f"[momentum] {len(final_hits)} candidates → LLM")

    # ── 4. LLM decision + order for candidates only ────────────────────────────
    trades_placed = 0
    for sym, technical, is_crypto in final_hits:
        yf_sym = CRYPTO_YFINANCE_MAP.get(sym, sym) if is_crypto else sym
        logger.info(f"--- [momentum] {sym} ---")

        try:
            fundamental = fundamental_agent.analyze(sym, yf_symbol=yf_sym if is_crypto else None)
        except Exception as e:
            telegram.error_alert(f"Fundamental fetch {sym}", str(e)); continue

        pos = positions.get(sym, {"qty": 0, "avg_entry_price": 0.0})
        try:
            decision = decision_agent.decide(
                fundamental=fundamental, technical=technical,
                available_cash=account["cash"],
                current_qty=pos["qty"], avg_entry_price=pos["avg_entry_price"],
                open_position_count=sum(1 for p in positions.values() if p["qty"] > 0),
                macro_context=macro_context,
            )
        except Exception as e:
            telegram.error_alert(f"LLM {sym}", str(e)); continue

        logger.info(f"[{sym}/momentum] {decision.action} {decision.confidence}% | {decision.rationale}")

        # ── SELL ──
        if decision.action == "SELL":
            qty = pos["qty"]
            if qty <= 0: continue
            result = alpaca.submit_market_order(sym, "SELL", qty)
            if result["success"]:
                trades_placed += 1
                account.update(alpaca.get_account())
                _reload_positions(positions, alpaca)
                momentum_pos = {s: p for s, p in positions.items() if s in universe_set}
                telegram.trade_alert(sym, "SELL", qty, decision.confidence,
                                      f"[MOMENTUM] {decision.rationale}", account["cash"],
                                      price=technical.current_price,
                                      fundamental=fundamental, technical=technical)
            else:
                telegram.error_alert(f"Momentum SELL {sym}", result.get("error", ""))
            continue

        if decision.action != "BUY":
            continue

        # ── BUY entry gates ──
        if decision.confidence < MOMENTUM_MIN_CONFIDENCE:
            logger.info(f"[{sym}/momentum] confidence {decision.confidence}% < {MOMENTUM_MIN_CONFIDENCE}%")
            continue

        # Dedup guard: positions API lags for crypto — check order history instead
        if recently_bought and sym in recently_bought:
            logger.info(f"[{sym}/momentum] BUY skipped — recent buy order exists (dedup)")
            continue

        if not is_crypto and not bull_market:
            logger.info(f"[{sym}/momentum] BUY skipped — SPY below SMA20 (bear regime)")
            continue

        if not _ok_to_buy(account):
            continue

        if sym in open_syms:
            logger.info(f"[{sym}/momentum] already holding — skipping BUY")
            continue

        if momentum_budget < 1.0:
            logger.info(f"[{sym}/momentum] momentum budget exhausted")
            continue

        if open_momentum_count >= MAX_MOMENTUM_POSITIONS:
            logger.info(f"[{sym}/momentum] max momentum positions reached")
            break  # no point checking more

        # Crypto also respects the overall 35% crypto cap
        if is_crypto:
            total_crypto_val = sum(p.get("market_value", 0) for s, p in positions.items() if "/" in s)
            cap_remaining    = pv * CRYPTO_PORTFOLIO_CAP - total_crypto_val
            if cap_remaining < 1.0:
                logger.info(f"[{sym}/momentum] overall crypto cap reached")
                continue
        else:
            cap_remaining = float("inf")

        investable = _investable_cash(account, decision.confidence)
        if investable < 1.0:
            logger.info(f"[{sym}/momentum] reserve floor reached")
            continue

        budget_to_use = min(investable, momentum_budget, cap_remaining)

        # ── Place order ──
        if is_crypto:
            notional = risk.calculate_notional_size(decision.confidence, budget_to_use,
                                                     buying_power=account.get("buying_power"))
            if notional < 10.0: continue
            result = alpaca.submit_crypto_order(sym, "BUY", notional)
            qty_for_alert = notional
        else:
            qty = risk.calculate_position_size(decision.confidence, budget_to_use,
                                               technical.current_price or 1.0,
                                               buying_power=account.get("buying_power"))
            if qty <= 0: continue
            result = alpaca.submit_market_order(sym, "BUY", qty)
            qty_for_alert = qty

        if result["success"]:
            trades_placed += 1
            open_momentum_count += 1
            account.update(alpaca.get_account())
            _reload_positions(positions, alpaca)
            momentum_pos       = {s: p for s, p in positions.items() if s in universe_set}
            total_momentum_val = sum(p.get("market_value", 0) for p in momentum_pos.values())
            momentum_budget    = pv * MOMENTUM_TOTAL_BUDGET_PCT - total_momentum_val
            open_syms.add(sym)
            telegram.trade_alert(sym, "BUY", qty_for_alert, decision.confidence,
                                  f"[MOMENTUM] {decision.rationale}", account["cash"],
                                  price=technical.current_price,
                                  fundamental=fundamental, technical=technical)
        else:
            logger.error(f"[{sym}/momentum] Order failed: {result.get('error')}")
            telegram.error_alert(f"Momentum BUY {sym}", result.get("error", ""))

    return trades_placed, trades_sold


# ── Main cycle ─────────────────────────────────────────────────────────────────

def run_cycle() -> dict:
    """Run one full trading cycle. Returns summary dict."""
    alpaca = AlpacaClient()
    risk   = RiskManager()
    telegram = TelegramNotifier()
    fundamental_agent = FundamentalAgent()
    technical_agent   = TechnicalAgent()
    decision_agent    = DecisionAgent()

    stock_market_open = alpaca.is_market_open()
    bull_market       = _is_bull_market() if stock_market_open else False

    try:
        account   = alpaca.get_account()
        positions = alpaca.get_positions()
    except Exception as e:
        telegram.error_alert("Fetching account/positions", str(e))
        raise

    # Cancel any zombie orders stuck in 'new'/'accepted' status for >5 minutes.
    # This cleans up BTC/USD phantom orders that Alpaca accepts but never fills.
    alpaca.cancel_stale_open_orders(min_age_minutes=5)

    # Fetch recent buy history ONCE per cycle.
    # Used across all sub-cycles to prevent re-buying crypto when Alpaca positions
    # API hasn't caught up yet (typically 2-3 min lag after a crypto fill).
    recently_bought = alpaca.get_recent_buy_symbols(lookback_minutes=15)

    # Build macro context block — injected into every LLM decision prompt so the
    # model knows the broad market regime and portfolio health before deciding.
    macro_context = _build_macro_context(bull_market, account)

    logger.info(
        f"Account: cash=${account['cash']:.2f} portfolio=${account['portfolio_value']:.2f} | "
        f"Positions: {list(positions.keys())} | "
        f"Stock market {'OPEN' if stock_market_open else 'CLOSED'} | "
        f"Regime: {'BULL' if bull_market else 'BEAR'}"
    )

    s_placed = s_sold = c_placed = c_sold = m_placed = m_sold = 0

    if stock_market_open:
        s_placed, s_sold = _run_stock_cycle(
            alpaca, risk, telegram, fundamental_agent, technical_agent,
            decision_agent, account, positions,
            bull_market=bull_market, macro_context=macro_context)
    else:
        logger.info("Stock market closed — skipping core stock cycle")

    # Core crypto: always runs 24/7 (no regime filter — crypto has its own cycle)
    c_placed, c_sold = _run_crypto_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent,
        decision_agent, account, positions,
        recently_bought=recently_bought, macro_context=macro_context)

    # Momentum: crypto 24/7, stocks only in bull regime
    m_placed, m_sold = _run_momentum_cycle(
        alpaca, risk, telegram, fundamental_agent, technical_agent,
        decision_agent, account, positions,
        stock_market_open=stock_market_open, bull_market=bull_market,
        recently_bought=recently_bought, macro_context=macro_context)

    total_placed = s_placed + c_placed + m_placed
    total_sold   = s_sold   + c_sold   + m_sold
    logger.info(
        f"Cycle done — {total_placed} placed, {total_sold} exits "
        f"(core stocks={s_placed} crypto={c_placed} momentum={m_placed})"
    )
    return {"trades_placed": total_placed, "trades_sold": total_sold}
