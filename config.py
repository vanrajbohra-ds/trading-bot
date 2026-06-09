import json as _json, os as _os
_wl_path = _os.path.join(_os.path.dirname(__file__), "watchlist.json")
WATCHLIST = _json.load(open(_wl_path)) if _os.path.exists(_wl_path) else ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MIN_CONFIDENCE = 65
MAX_POSITIONS  = 5
STOP_LOSS_PCT   = 0.07
TAKE_PROFIT_PCT = 0.15

POSITION_SIZE_BANDS = [
    (70, 79,  0.05),
    (80, 89,  0.10),
    (90, 100, 0.20),
]

# ── Core Crypto ───────────────────────────────────────────────────────────────
CRYPTO_WATCHLIST = ["BTC/USD", "SOL/USD"]
CRYPTO_YFINANCE_MAP = {
    "BTC/USD":  "BTC-USD",
    "SOL/USD":  "SOL-USD",
    "DOGE/USD": "DOGE-USD",
    "AVAX/USD": "AVAX-USD",
    "LINK/USD": "LINK-USD",
    "UNI/USD":  "UNI-USD",
}
MAX_CRYPTO_POSITIONS   = 2
CRYPTO_STOP_LOSS_PCT   = 0.12
CRYPTO_TAKE_PROFIT_PCT = 0.25
CRYPTO_PORTFOLIO_CAP   = 0.35   # max 35% of total portfolio value in crypto (core + momentum)

# ── Momentum / Speculative Tier ───────────────────────────────────────────────
# The bot discovers high-momentum stocks LIVE each cycle using Yahoo Finance
# screeners (most active by volume + top day gainers). No hardcoded list —
# the system hunts wherever the market is actually moving today.
#
# Crypto momentum universe is fixed (only a few volatile coins on Alpaca).
MOMENTUM_CRYPTO_UNIVERSE = ["DOGE/USD", "AVAX/USD", "LINK/USD", "UNI/USD"]

# How many results to pull from each Yahoo Finance screener per cycle.
# actives + gainers are combined → up to 2× this many stock candidates.
MOMENTUM_SCREENER_LIMIT = 20

MOMENTUM_TOTAL_BUDGET_PCT  = 0.10   # 10% of portfolio across ALL momentum positions combined
MAX_MOMENTUM_POSITIONS     = 4      # max simultaneous momentum positions (stocks + crypto)

MOMENTUM_MIN_CONFIDENCE    = 80     # higher bar than core (65%)
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
LLM_PROVIDER = "groq"
GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

HIST_PERIOD = "6mo"
