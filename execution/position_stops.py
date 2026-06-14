"""
ATR-based stop-loss and take-profit manager.

Prices are fixed at entry time (Option A) so volatility spikes after entry
cannot widen a stop that was already set. Persisted to positions_stops.json
which the GitHub Actions workflow commits back to the repo after each run —
the next stateless run picks it up via git checkout.

Fallback: if a symbol has no entry in the file (e.g. positions held before
this feature was deployed), risk_manager falls back to the config percentages.
"""
import os
import json
import logging
import datetime

logger = logging.getLogger(__name__)

_STOPS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "positions_stops.json")

# ATR multipliers — how many ATR units wide each side is
CORE_STOP_MULT   = 2.0   # core stocks & crypto
CORE_TARGET_MULT = 3.0   # 3:2 risk-reward ratio
MOM_STOP_MULT    = 1.5   # momentum tier (tighter — fast in, fast out)
MOM_TARGET_MULT  = 2.0

# Absolute guardrails — prevent extreme values on illiquid/volatile moments
MIN_STOP_PCT   = 0.015   # never tighter than 1.5% (avoid noise-outs)
MAX_STOP_PCT   = 0.20    # never wider than 20%
MIN_TARGET_PCT = 0.025   # never less than 2.5% upside
MAX_TARGET_PCT = 0.45    # never more than 45% (sanity cap)


def load_stops() -> dict:
    """Load stops file. Returns empty dict if missing or unreadable."""
    try:
        if os.path.exists(_STOPS_FILE):
            with open(_STOPS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[stops] Could not read {_STOPS_FILE}: {e}")
    return {}


def save_stops(stops: dict) -> None:
    """Write stops to disk. GitHub Actions workflow commits this file after each run."""
    try:
        with open(_STOPS_FILE, "w") as f:
            json.dump(stops, f, indent=2)
    except Exception as e:
        logger.warning(f"[stops] Could not write {_STOPS_FILE}: {e}")


def set_stop(symbol: str, entry_price: float, atr: float,
             is_momentum: bool = False) -> tuple:
    """Compute and persist ATR-based stop/target for a new position.

    Returns (stop_price, target_price).
    ATR fallback: if atr is None or zero, uses 2% of entry price for stocks
    and 4% for crypto (identified by '/' in symbol).
    """
    if not atr or atr <= 0:
        default_pct = 0.04 if "/" in symbol else 0.02
        atr = entry_price * default_pct
        logger.warning(f"[stops] ATR unavailable for {symbol} — using {default_pct*100:.0f}% fallback")

    stop_mult   = MOM_STOP_MULT   if is_momentum else CORE_STOP_MULT
    target_mult = MOM_TARGET_MULT if is_momentum else CORE_TARGET_MULT

    raw_stop_pct   = (stop_mult   * atr) / entry_price
    raw_target_pct = (target_mult * atr) / entry_price

    stop_pct   = max(MIN_STOP_PCT,   min(MAX_STOP_PCT,   raw_stop_pct))
    target_pct = max(MIN_TARGET_PCT, min(MAX_TARGET_PCT, raw_target_pct))

    stop_price   = round(entry_price * (1 - stop_pct),   6)
    target_price = round(entry_price * (1 + target_pct), 6)

    stops = load_stops()
    stops[symbol] = {
        "stop_price":   stop_price,
        "target_price": target_price,
        "entry_price":  round(entry_price, 6),
        "atr_used":     round(atr, 6),
        "stop_pct":     round(stop_pct * 100, 2),
        "target_pct":   round(target_pct * 100, 2),
        "tier":         "momentum" if is_momentum else "core",
        "entry_date":   datetime.datetime.utcnow().strftime("%Y-%m-%d"),
    }
    save_stops(stops)
    logger.info(
        f"[stops] {symbol} entry=${entry_price:.4f} ATR={atr:.4f} "
        f"→ stop=${stop_price:.4f} (−{stop_pct*100:.1f}%) "
        f"target=${target_price:.4f} (+{target_pct*100:.1f}%)"
    )
    return stop_price, target_price


def remove_stop(symbol: str) -> None:
    """Remove a position's entry after it is closed."""
    stops = load_stops()
    if symbol in stops:
        del stops[symbol]
        save_stops(stops)
        logger.info(f"[stops] Cleared stop entry for {symbol}")


def get_stops(symbol: str) -> tuple:
    """Return (stop_price, target_price) or (None, None) if no entry exists."""
    entry = load_stops().get(symbol)
    if not entry:
        return None, None
    return entry.get("stop_price"), entry.get("target_price")
