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

# --- Crypto ---
# Alpaca symbol → yfinance symbol
CRYPTO_WATCHLIST = ["BTC/USD", "SOL/USD", "DOGE/USD", "AVAX/USD"]
CRYPTO_YFINANCE_MAP = {
    "BTC/USD":  "BTC-USD",
    "SOL/USD":  "SOL-USD",
    "DOGE/USD": "DOGE-USD",
    "AVAX/USD": "AVAX-USD",
}
MAX_CRYPTO_POSITIONS   = 4
CRYPTO_STOP_LOSS_PCT   = 0.12   # wider stop — crypto is more volatile
CRYPTO_TAKE_PROFIT_PCT = 0.25
CRYPTO_PORTFOLIO_CAP   = 0.35   # max 35% of total portfolio value in crypto

# LLM provider: "groq" (recommended, 14400 free req/day) or "gemini" (1500 free req/day)
LLM_PROVIDER = "groq"

# Groq model (free, fast, high quality)
GROQ_MODEL = "llama-3.3-70b-versatile"

# Gemini fallback model
GEMINI_MODEL = "gemini-2.0-flash"

HIST_PERIOD = "6mo"
