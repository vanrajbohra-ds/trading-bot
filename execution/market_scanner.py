"""
Discovers high-momentum stock candidates dynamically every cycle.

Uses Yahoo Finance pre-built screeners so the momentum hunter never needs
a hardcoded stock list — it always works from what's actually moving today.

Screeners:
  most_actives  — highest volume today (real money behind the move)
  day_gainers   — biggest % gain today (momentum already in motion)
  day_losers    — biggest % drop  (oversold bounce candidates)

Falls back to yfinance.screen(), then direct HTTP, then an empty list.
The orchestrator skips momentum stock entry if the screener returns nothing
rather than crashing.
"""

import logging
import requests

logger = logging.getLogger(__name__)

_YF_SCREENER_URL = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Minimum price filter — ignore penny stocks (< $2) which are hard to trade
_MIN_PRICE = 2.0

# Asset types to skip — Alpaca stock orders don't handle these well
_SKIP_TYPES = {"ETF", "MUTUALFUND", "FUND", "INDEX", "FUTURE", "CURRENCY"}


def _fetch_screener(screener_id: str, limit: int) -> list[dict]:
    """Return raw quote dicts from a Yahoo Finance predefined screener."""
    # Try yfinance built-in screener first (cleaner, handles auth)
    try:
        import yfinance as yf
        result = yf.screen(screener_id, count=limit)
        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        if quotes:
            return quotes
    except Exception:
        pass

    # Fallback: direct HTTP
    try:
        r = requests.get(
            _YF_SCREENER_URL,
            params={"scrIds": screener_id, "count": limit, "formatted": "false"},
            headers=_HEADERS,
            timeout=10,
        )
        data = r.json()
        return data["finance"]["result"][0]["quotes"]
    except Exception as e:
        logger.warning(f"[scanner] screener '{screener_id}' failed: {e}")
        return []


def _extract_symbols(quotes: list[dict]) -> list[str]:
    """Pull clean, tradeable symbols out of raw Yahoo quote dicts."""
    syms = []
    for q in quotes:
        sym  = q.get("symbol", "")
        typ  = q.get("quoteType", "").upper()
        price = q.get("regularMarketPrice") or q.get("ask") or 0
        # Skip options, warrants, ETFs, funds, indices, non-US
        if not sym or "." in sym or "^" in sym:
            continue
        if typ in _SKIP_TYPES:
            continue
        if price and float(price) < _MIN_PRICE:
            continue
        syms.append(sym)
    return syms


def get_screener_quotes(limit_per_screen: int = 20,
                        exclude: set | None = None) -> dict:
    """
    Return rich quote data for dashboard display.

    Returns:
      {
        "actives": [ {symbol, price, change_pct, volume, avg_volume, volume_ratio,
                      market_cap, name}, ... ],
        "gainers": [ same structure ],
      }
    """
    exclude = exclude or set()

    def _enrich(quotes: list[dict]) -> list[dict]:
        out = []
        for q in quotes:
            sym = q.get("symbol", "")
            if not sym or sym in exclude:
                continue
            if "." in sym or "^" in sym:
                continue
            typ = q.get("quoteType", "").upper()
            if typ in _SKIP_TYPES:
                continue
            price = float(q.get("regularMarketPrice") or 0)
            if price < _MIN_PRICE:
                continue
            avg_vol = float(q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day") or 1)
            vol     = float(q.get("regularMarketVolume") or 0)
            out.append({
                "symbol":       sym,
                "name":         q.get("shortName") or q.get("longName") or sym,
                "price":        price,
                "change_pct":   float(q.get("regularMarketChangePercent") or 0),
                "change_abs":   float(q.get("regularMarketChange") or 0),
                "volume":       int(vol),
                "avg_volume":   int(avg_vol),
                "volume_ratio": round(vol / avg_vol, 2) if avg_vol > 0 else 0,
                "market_cap":   float(q.get("marketCap") or 0),
            })
        return out

    actives_raw = _fetch_screener("most_actives", limit_per_screen)
    gainers_raw = _fetch_screener("day_gainers",  limit_per_screen)
    return {
        "actives": _enrich(actives_raw),
        "gainers": _enrich(gainers_raw),
    }


def get_momentum_candidates(limit_per_screen: int = 20,
                            exclude: set | None = None) -> list[str]:
    """
    Return a deduplicated list of stocks showing momentum today.

    Combines most_actives (volume surge) and day_gainers (price surge).
    Symbols in `exclude` (core watchlist etc.) are removed.
    Returns at most 2 × limit_per_screen unique symbols.
    """
    exclude = exclude or set()

    actives = _extract_symbols(_fetch_screener("most_actives", limit_per_screen))
    gainers = _extract_symbols(_fetch_screener("day_gainers",  limit_per_screen))

    seen       = set(exclude)
    candidates = []
    for sym in actives + gainers:
        if sym not in seen:
            seen.add(sym)
            candidates.append(sym)

    logger.info(
        f"[scanner] {len(actives)} most-active + {len(gainers)} top-gainers "
        f"→ {len(candidates)} unique candidates (after excluding {len(exclude)} core)"
    )
    return candidates
