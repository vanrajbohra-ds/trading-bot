import json as _json, os as _os
_wl_path = _os.path.join(_os.path.dirname(__file__), "watchlist.json")
WATCHLIST = _json.load(open(_wl_path)) if _os.path.exists(_wl_path) else ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MIN_CONFIDENCE = 75
MAX_POSITIONS  = 5
STOP_LOSS_PCT   = 0.07
TAKE_PROFIT_PCT = 0.15

POSITION_SIZE_BANDS = [
    (70, 79,  0.05),
    (80, 89,  0.10),
    (90, 100, 0.20),
]

# ── Core Crypto ───────────────────────────────────────────────────────────────
# Top market-cap cryptos traded 24/7 — BTC excluded (never fills on paper trading)
CRYPTO_WATCHLIST = ["ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD"]
CRYPTO_YFINANCE_MAP = {
    "BTC/USD":  "BTC-USD",
    "ETH/USD":  "ETH-USD",
    "SOL/USD":  "SOL-USD",
    "DOGE/USD": "DOGE-USD",
    "AVAX/USD": "AVAX-USD",
    "LTC/USD":  "LTC-USD",
    "BCH/USD":  "BCH-USD",
    "LINK/USD": "LINK-USD",
    "UNI/USD":  "UNI-USD",
    "AAVE/USD": "AAVE-USD",
    "GRT/USD":  "GRT-USD",
    "MKR/USD":  "MKR-USD",
    "XLM/USD":  "XLM-USD",
    "XTZ/USD":  "XTZ-USD",
    "BAT/USD":  "BAT-USD",
    "SHIB/USD": "SHIB-USD",
}
MAX_CRYPTO_POSITIONS   = 3      # increased to match 4-coin core watchlist
CRYPTO_STOP_LOSS_PCT   = 0.12
CRYPTO_TAKE_PROFIT_PCT = 0.25
CRYPTO_PORTFOLIO_CAP   = 0.35   # max 35% of total portfolio value in crypto (core + momentum)

# ── Momentum / Speculative Tier ───────────────────────────────────────────────
# Stocks: discovered LIVE via Yahoo Finance screeners (most-active + top-gainers).
# Crypto: discovered LIVE via CoinGecko top-100 by volume — no hardcoded universe.
#         get_momentum_crypto_candidates() picks whichever Alpaca-tradeable coins
#         are actually surging today, based on 24h change × volume/market-cap ratio.

# How many results to pull from each Yahoo Finance screener per cycle.
# actives + gainers are combined → up to 2× this many stock candidates.
MOMENTUM_SCREENER_LIMIT = 20

MOMENTUM_TOTAL_BUDGET_PCT  = 0.10   # 10% of portfolio across ALL momentum positions combined
MAX_MOMENTUM_POSITIONS     = 4      # max simultaneous momentum positions (stocks + crypto)

MOMENTUM_MIN_CONFIDENCE    = 82     # higher bar than core (75%)
MOMENTUM_VOLUME_RATIO_MIN  = 1.8    # 1.8× average volume — confirms a real catalyst

# Tight exits — ride the wave, take profit fast, cut losses faster
MOMENTUM_STOCK_STOP_PCT    = 0.04   # -4%  (core stocks: -7%)
MOMENTUM_STOCK_TAKE_PCT    = 0.08   # +8%  (core stocks: +15%)
MOMENTUM_CRYPTO_STOP_PCT   = 0.06   # -6%  (core crypto: -12%)
MOMENTUM_CRYPTO_TAKE_PCT   = 0.12   # +12% (core crypto: +25%)

# ── Cash reserve ──────────────────────────────────────────────────────────────
MIN_CASH_RESERVE_PCT = 0.20   # always keep 20% of portfolio as cash (dry powder)

RESERVE_DEPLOY_CONFIDENCE = 88    # minimum confidence % to tap the reserve
RESERVE_MAX_DEPLOY_PCT    = 0.50  # deploy at most 50% of the reserve floor per trade

# ── LLM ───────────────────────────────────────────────────────────────────────
# LLM_PROVIDER is kept for legacy references but decision_agent now uses
# automatic failover: Cerebras → Groq → Gemini → OpenRouter
LLM_PROVIDER     = "cerebras"
CEREBRAS_MODEL   = "gpt-oss-120b"
GROQ_MODEL       = "llama-3.3-70b-versatile"
GEMINI_MODEL     = "gemini-2.0-flash"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

HIST_PERIOD = "6mo"
