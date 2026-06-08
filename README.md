# Autonomous Multi-Agent Trading Bot

An autonomous paper trading system powered by AI agents that analyze stocks and execute trades automatically every 5 minutes during market hours — without any human intervention.

---

## What It Does

The bot monitors a fixed watchlist of 5 stocks (AAPL, TSLA, NVDA, MSFT, AMZN) every 5 minutes during NYSE market hours. For each stock, three specialized AI agents collaborate to decide whether to buy, sell, or hold. Approved decisions are executed instantly via Alpaca's paper trading API, and you receive a Telegram notification on your phone for every trade.

```
Every 5 minutes (Mon–Fri, 9:30 AM – 4:00 PM ET)
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                   TRADING CYCLE                      │
│                                                      │
│  1. Risk Sweep — check all positions for             │
│     stop-loss (−7%) or take-profit (+15%)            │
│                                                      │
│  For each stock in watchlist:                        │
│  ┌──────────────────────────────────────────────┐   │
│  │  Fundamental Agent   yfinance                │   │
│  │  → P/E, EPS, growth, analyst ratings         │   │
│  │                                              │   │
│  │  Technical Agent     yfinance + ta library   │   │
│  │  → RSI, MACD, Bollinger Bands, SMA, OBV      │   │
│  │                                              │   │
│  │  Decision Agent      Groq (Llama 3.3 70B)   │   │
│  │  → BUY / SELL / HOLD + confidence score      │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  2. Execute trade if confidence ≥ 70%                │
│  3. Send Telegram notification                       │
└─────────────────────────────────────────────────────┘
```

---

## Architecture

### The Three Agents

#### 1. Fundamental Agent (`agents/fundamental_agent.py`)
Fetches and interprets company financial health using `yfinance`:

| Data Point | Source | Why It Matters |
|---|---|---|
| P/E Ratio | `ticker.info` | Valuation vs sector peers |
| EPS (TTM) | `ticker.info` | Actual earnings power |
| Revenue Growth | `ticker.info` | Business momentum |
| Earnings Growth | `ticker.info` | Profit trajectory |
| Debt/Equity | `ticker.info` | Financial risk |
| ROE | `ticker.info` | Management efficiency |
| Analyst Rating | `ticker.info` | Wall St. consensus |
| Analyst Price Target | `ticker.info` | Upside/downside to target |
| Recent Upgrades | `ticker.upgrades_downgrades` | Sentiment shifts |
| Earnings Surprises | `ticker.earnings_history` | Beat/miss history |

Outputs a `FundamentalReport` dataclass with a `to_prompt_text()` method that formats all data into a readable report for the LLM.

#### 2. Technical Agent (`agents/technical_agent.py`)
Computes price action indicators on 6 months of OHLCV data using the `ta` library:

| Indicator | Signal Used |
|---|---|
| RSI (14) | < 30 = oversold (buy signal), > 70 = overbought (sell signal) |
| MACD | Histogram crossover direction (bullish/bearish) |
| Bollinger Bands | % position in bands — near lower = potential bounce |
| SMA 50 / 200 | Golden cross (50 > 200 = bullish) or Death cross |
| OBV | Rising = institutional buying, Falling = distribution |
| Volume Ratio | 5-day vs 20-day avg — high volume confirms moves |

Outputs a `TechnicalReport` dataclass with a `to_prompt_text()` method.

#### 3. Decision Agent (`agents/decision_agent.py`)
The brain of the system. Receives both expert reports + current portfolio context, then calls **Groq (Llama 3.3 70B)** to make the final call.

Prompt includes:
- Available cash
- Current position in the stock (shares held, average entry price)
- Number of open positions
- Full fundamental report
- Full technical report

Returns structured JSON:
```json
{
  "symbol": "NVDA",
  "action": "BUY",
  "confidence": 82,
  "quantity_suggestion": 5,
  "rationale": "Strong earnings growth and analyst upgrades align with RSI bouncing off oversold territory and golden cross formation.",
  "key_bull_factors": ["Revenue growth 122%", "RSI oversold bounce", "Analyst upgrades"],
  "key_bear_factors": ["Bearish MACD histogram", "High P/E ratio"],
  "time_horizon": "swing"
}
```

---

### Risk Manager (`execution/risk_manager.py`)

Runs **before** every agent cycle to protect existing positions:

**Stop-Loss:** Automatically sells if a position drops 7% below entry price
```
(current_price - avg_entry) / avg_entry ≤ -0.07
```

**Take-Profit:** Automatically sells if a position gains 15% above entry price
```
(current_price - avg_entry) / avg_entry ≥ 0.15
```

**Position Sizing:** Scales buy size to confidence level
| Confidence | Cash Deployed |
|---|---|
| 70–79% | 5% of available cash |
| 80–89% | 10% of available cash |
| 90–100% | 20% of available cash |

**Max Positions:** Never holds more than 5 stocks simultaneously.

---

### Alpaca Client (`execution/alpaca_client.py`)

Handles all Alpaca Paper Trading API communication:
- Market open/close check (respects holidays)
- Account balance and buying power
- Current positions with live prices
- Order submission (buy/sell)
- Wash trade protection — cancels all open orders for a symbol before placing a sell

---

### Telegram Notifier (`execution/telegram_notifier.py`)

Sends real-time alerts to your phone via Telegram Bot API for:

**Trade Alert:**
```
🟢 TRADE ALERT
Action:    BUY NVDA
Shares:    12
Confidence:82%
Rationale: Strong earnings + RSI oversold bounce
Cash Left: $87,420.00
```

**Risk Exit:**
```
⚠️ RISK EXIT
Action: SELL TSLA (STOP LOSS -7.2%)
Shares: 8
```

**Cycle Summary (every run):**
```
📊 CYCLE COMPLETE
Trades Placed:  2
Skipped:        3
Portfolio:      $104,250.00
Cash:           $81,488.00
```

---

## File Structure

```
trading_bot/
│
├── main.py                        # Entry point
│                                  # python main.py          → single cycle (GitHub Actions)
│                                  # python main.py --daemon → continuous loop (AWS EC2)
│
├── config.py                      # All tunable settings
├── env_loader.py                  # Reads .env credentials
├── orchestrator.py                # Wires all agents into one trading cycle
│
├── agents/
│   ├── fundamental_agent.py       # yfinance fundamentals
│   ├── technical_agent.py         # Price indicators via ta library
│   └── decision_agent.py          # Groq LLM decision engine
│
├── execution/
│   ├── alpaca_client.py           # Alpaca REST API wrapper
│   ├── risk_manager.py            # Stop-loss, take-profit, position sizing
│   └── telegram_notifier.py       # Telegram Bot alerts
│
├── .github/
│   └── workflows/
│       └── trading_bot.yml        # GitHub Actions — runs every 5 min during market hours
│
├── trading_bot.service            # systemd service file for AWS EC2
├── requirements.txt
└── .gitignore                     # Excludes .env and logs from git
```

---

## Configuration (`config.py`)

```python
WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MIN_CONFIDENCE     = 70     # Minimum confidence % to place any trade
MAX_POSITIONS      = 5      # Max simultaneous open positions
STOP_LOSS_PCT      = 0.07   # 7%  drop triggers automatic sell
TAKE_PROFIT_PCT    = 0.15   # 15% gain triggers automatic sell

POSITION_SIZE_BANDS = [
    (70, 79,  0.05),   # 5%  of cash at 70–79% confidence
    (80, 89,  0.10),   # 10% of cash at 80–89% confidence
    (90, 100, 0.20),   # 20% of cash at 90–100% confidence
]

LLM_PROVIDER = "groq"              # "groq" or "gemini"
GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"
```

---

## Hosting

### GitHub Actions (Current — Free)
Runs automatically every 5 minutes during market hours. No server needed.

Cron schedule (UTC, EDT offset):
```
2,7,12,17,22,27,32,37,42,47,52,57  13-19  *  *  1-5
```
= Every 5 minutes, 9:32 AM – 3:57 PM ET, Monday–Friday.

### AWS EC2 (Alternative — Always-on, 1-minute cycles)
For sub-5-minute trading frequency, run the daemon on a free-tier t2.micro:
```bash
python3 main.py --daemon   # loops every 60 seconds during market hours
```
Install as a systemd service so it auto-starts on reboot:
```bash
sudo cp trading_bot.service /etc/systemd/system/
sudo systemctl enable trading_bot
sudo systemctl start trading_bot
```

---

## Required Credentials (`.env`)

```
ALPACA_API_KEY=...        # Paper trading key from app.alpaca.markets
ALPACA_SECRET_KEY=...     # Paper trading secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

GROQ_API_KEY=...          # Free at console.groq.com (14,400 req/day)
GOOGLE_API_KEY=...        # Gemini fallback — free at aistudio.google.com

TELEGRAM_BOT_TOKEN=...    # From @BotFather on Telegram
TELEGRAM_CHAT_ID=...      # Your chat ID from api.telegram.org/bot{token}/getUpdates
```

For GitHub Actions, these are stored as encrypted **Repository Secrets** (Settings → Secrets → Actions) — never committed to the repo.

---

## Dependencies

```
yfinance        — stock data and fundamentals
ta              — technical indicators (RSI, MACD, Bollinger Bands, etc.)
google-genai    — Gemini LLM fallback
requests        — HTTP client (Alpaca API, Groq API, Telegram API)
pandas          — data manipulation
numpy           — numerical operations
```

---

## Tuning Tips

**Bot trades too rarely?** Lower `MIN_CONFIDENCE` from 70 to 65.

**Bot trades too much / losing money?** Raise `MIN_CONFIDENCE` to 75 or 80.

**Positions getting stopped out too often?** Raise `STOP_LOSS_PCT` from 0.07 to 0.10 — gives more room for volatile stocks like TSLA and NVDA.

**Want to lock in gains faster?** Lower `TAKE_PROFIT_PCT` from 0.15 to 0.10.

**Switch LLM provider:**
```python
LLM_PROVIDER = "gemini"   # use Gemini instead of Groq
```

After any config change:
```bash
git add config.py
git commit -m "update config"
git push
```
GitHub Actions picks up the new settings on the next run automatically.
