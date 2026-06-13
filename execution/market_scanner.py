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
_COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# CoinGecko lowercase symbol → Alpaca trading symbol.
# Covers the full set of crypto pairs available on Alpaca US.
# The screener scans ALL top-100 coins from CoinGecko and filters to this set —
# so this is a platform-capability map, not a hardcoded trading universe.
_ALPACA_CRYPTO_MAP = {
    "btc":   "BTC/USD",
    "eth":   "ETH/USD",
    "sol":   "SOL/USD",
    "doge":  "DOGE/USD",
    "avax":  "AVAX/USD",
    "ltc":   "LTC/USD",
    "bch":   "BCH/USD",
    "link":  "LINK/USD",
    "uni":   "UNI/USD",
    "aave":  "AAVE/USD",
    "grt":   "GRT/USD",
    "mkr":   "MKR/USD",
    "xlm":   "XLM/USD",
    "xtz":   "XTZ/USD",
    "bat":   "BAT/USD",
    "shib":  "SHIB/USD",
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


def get_momentum_crypto_candidates(
    exclude: "set | None" = None,
    top_n: int = 3,
) -> "list[str]":
    """
    Discovers crypto momentum candidates dynamically via CoinGecko market data.

    No hardcoded trading universe — scans CoinGecko's top 100 coins by 24h volume,
    filters to Alpaca-tradeable symbols, then scores each by:
        score = 24h_change_pct × (1 + volume_to_market_cap_ratio × 10)

    This is the crypto equivalent of Yahoo Finance's most_actives/day_gainers screeners:
    it surfaces whatever is actually surging today, not a predefined list.

    Returns the top N positive-momentum candidates (score > 0).
    Falls back gracefully to an empty list if CoinGecko is unavailable.
    """
    exclude = exclude or set()

    try:
        r = requests.get(
            _COINGECKO_MARKETS_URL,
            params={
                "vs_currency": "usd",
                "order": "volume_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "24h",
                "sparkline": "false",
            },
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        coins = r.json()
    except Exception as e:
        logger.warning(f"[crypto-screener] CoinGecko fetch failed ({e}) — skipping crypto momentum")
        return []

    scored = []
    for coin in coins:
        cg_sym     = (coin.get("symbol") or "").lower()
        alpaca_sym = _ALPACA_CRYPTO_MAP.get(cg_sym)
        if not alpaca_sym or alpaca_sym in exclude:
            continue

        change_24h = float(coin.get("price_change_percentage_24h") or 0.0)
        volume     = float(coin.get("total_volume") or 0.0)
        mcap       = float(coin.get("market_cap") or 1.0)
        vol_ratio  = volume / mcap if mcap > 0 else 0.0

        # Weight both price momentum and unusual trading activity (volume spike)
        score = change_24h * (1.0 + vol_ratio * 10.0)
        scored.append((alpaca_sym, score, change_24h, vol_ratio))
        logger.debug(
            f"[crypto-screener] {alpaca_sym}: 24h={change_24h:+.2f}% "
            f"vol/mcap={vol_ratio:.3f} score={score:.3f}"
        )

    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = [sym for sym, score, _, _ in scored[:top_n] if score > 0]

    logger.info(
        f"[crypto-screener] Scanned {len(scored)} Alpaca-tradeable coins from CoinGecko top-100 → "
        f"{len(candidates)} positive-momentum candidates: {candidates}"
    )
    return candidates


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
