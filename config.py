WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MIN_CONFIDENCE = 70
MAX_POSITIONS = 5
STOP_LOSS_PCT = 0.07
TAKE_PROFIT_PCT = 0.15

POSITION_SIZE_BANDS = [
    (70, 79,  0.05),
    (80, 89,  0.10),
    (90, 100, 0.20),
]

# LLM provider: "groq" (recommended, 14400 free req/day) or "gemini" (1500 free req/day)
LLM_PROVIDER = "groq"

# Groq model (free, fast, high quality)
GROQ_MODEL = "llama-3.3-70b-versatile"

# Gemini fallback model
GEMINI_MODEL = "gemini-2.0-flash"

HIST_PERIOD = "6mo"
