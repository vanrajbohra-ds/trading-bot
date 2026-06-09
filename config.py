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
# BTC and SOL are treated as "core" crypto — more mature, lower volatility.
CRYPTO_WATCHLIST = ["BTC/USD", "SOL/USD"]
CRYPTO_YFINANCE_MAP = {
    "BTC/USD":  "BTC-USD",
    "SOL/USD":  "SOL-USD",
    "DOGE/USD": "DOGE-USD",
    "AVAX/USD": "AVAX-USD",
}
MAX_CRYPTO_POSITIONS   = 2
CRYPTO_STOP_LOSS_PCT   = 0.12   # wider stop — crypto is more volatile
CRYPTO_TAKE_PROFIT_PCT = 0.25
CRYPTO_PORTFOLIO_CAP   = 0.35   # max 35% of total portfolio value in crypto (core + momentum combined)

# ── Momentum / Speculative Tier ───────────────────────────────────────────────
# 5% portfolio → high-beta stocks  |  5% portfolio → volatile crypto
# These positions are meant to ride short-term momentum and exit quickly.
# Entry: volume surge + trending RSI + MACD positive + higher confidence bar.
# Exit: tighter stop-loss and take-profit so gains are locked in fast.
#
# Stock symbols: completely separate from WATCHLIST to avoid double-trading.
# Crypto symbols: DOGE and AVAX — more speculative than BTC/SOL.
MOMENTUM_STOCK_WATCHLIST  = ["COIN", "AMD", "PLTR", "MSTR"]
MOMENTUM_CRYPTO_WATCHLIST = ["DOGE/USD", "AVAX/USD"]

MOMENTUM_STOCK_BUDGET_PCT  = 0.05   # max 5% of portfolio in momentum stocks at any time
MOMENTUM_CRYPTO_BUDGET_PCT = 0.05   # max 5% of portfolio in momentum crypto at any time

MOMENTUM_MIN_CONFIDENCE    = 80     # higher entry bar (core is 65%)
MOMENTUM_VOLUME_RATIO_MIN  = 1.8    # need 1.8× average volume — confirms a real catalyst

MOMENTUM_STOCK_STOP_PCT    = 0.04   # tight -4% stop  (core stocks: -7%)
MOMENTUM_STOCK_TAKE_PCT    = 0.08   # quick +8% target (core stocks: +15%)
MOMENTUM_CRYPTO_STOP_PCT   = 0.06   # tight -6% stop  (core crypto: -12%)
MOMENTUM_CRYPTO_TAKE_PCT   = 0.12   # quick +12% target (core crypto: +25%)

MAX_MOMENTUM_STOCK_POSITIONS  = 2   # hold at most 2 momentum stock positions at once
MAX_MOMENTUM_CRYPTO_POSITIONS = 2   # hold at most 2 momentum crypto positions at once

# ── Cash reserve ──────────────────────────────────────────────────────────────
MIN_CASH_RESERVE_PCT = 0.20   # always keep 20% of portfolio as cash (dry powder)

# Reserve is unlocked only for very high-conviction signals
RESERVE_DEPLOY_CONFIDENCE = 88    # minimum confidence % to tap the reserve
RESERVE_MAX_DEPLOY_PCT    = 0.50  # deploy at most 50% of the reserve floor per trade

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER = "groq"
GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

HIST_PERIOD = "6mo"
