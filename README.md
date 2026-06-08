# Autonomous Multi-Agent Trading Bot

An autonomous paper trading system powered by AI agents that analyze stocks and crypto every few minutes during market hours — buying, selling, and managing risk without any human intervention.

---

## What It Does

The bot monitors **9 assets** (5 stocks + 4 crypto) during NYSE market hours. For each asset, three AI agents collaborate to decide whether to buy, sell, or hold. Approved decisions are executed instantly via Alpaca's paper trading API. You receive a Telegram notification only when something happens — a trade, a risk exit, an error, or an end-of-day summary.

```
Every ~2 minutes (Mon–Fri, 9:30 AM – 4:00 PM ET)
         │
         ▼
┌────────────────────────────────────────────────────────┐
│                    TRADING CYCLE                        │
│                                                         │
│  1. Risk Sweep — check all positions for                │
│     stop-loss or take-profit triggers                   │
│                                                         │
│  For each asset in watchlist:                           │
│  ┌───────────────────────────────────────────────┐     │
│  │  Fundamental Agent   yfinance                 │     │
│  │  → Stocks: P/E, EPS, analyst ratings          │     │
│  │  → Crypto: market cap, 52w range, supply      │     │
│  │                                               │     │
│  │  Technical Agent     yfinance + ta library    │     │
│  │  → RSI, MACD, Bollinger Bands, SMA, OBV       │     │
│  │                                               │     │
│  │  Decision Agent      Groq (Llama 3.3 70B)    │     │
│  │  → BUY / SELL / HOLD + confidence score       │     │
│  └───────────────────────────────────────────────┘     │
│                                                         │
│  2. Execute trade if confidence ≥ 65%                   │
│  3. Send Telegram alert (trades and errors only)        │
│  4. End-of-day summary sent at ~3:45–4:00 PM ET        │
└────────────────────────────────────────────────────────┘
```

---

## Watchlist

### Stocks
| Symbol | Company |
|--------|---------|
| AAPL   | Apple |
| TSLA   | Tesla |
| NVDA   | NVIDIA |
| MSFT   | Microsoft |
| AMZN   | Amazon |

### Crypto
| Symbol   | Asset     | Stop-Loss | Take-Profit |
|----------|-----------|-----------|-------------|
| BTC/USD  | Bitcoin   | −12%      | +25% |
| SOL/USD  | Solana    | −12%      | +25% |
| DOGE/USD | Dogecoin  | −12%      | +25% |
| AVAX/USD | Avalanche | −12%      | +25% |

Crypto uses wider thresholds because it is more volatile than stocks (stocks: −7% / +15%).

---

## Architecture

### The Three Agents

#### 1. Fundamental Agent (`agents/fundamental_agent.py`)
Adapts automatically to stock vs. crypto:

**For stocks** — fetches company financials via `yfinance`:

| Data Point | Why It Matters |
|---|---|
| P/E Ratio | Valuation vs sector peers |
| EPS (TTM) | Actual earnings power |
| Revenue & Earnings Growth | Business momentum |
| Debt/Equity + ROE | Financial health |
| Analyst Rating + Price Target | Wall St. consensus |
| Recent Upgrades/Downgrades | Sentiment shifts |
| Earnings Surprises | Beat/miss history |

**For crypto** — fetches market data via `yfinance`:

| Data Point | Why It Matters |
|---|---|
| Market Cap | Size and liquidity |
| Circulating Supply | Inflation/scarcity signal |
| 52-Week High / Low | Where price sits in its range |
| 24h Volume | Current market interest |

#### 2. Technical Agent (`agents/technical_agent.py`)
Computes price action indicators on 6 months of OHLCV data. Works identically for stocks and crypto.

| Indicator | Signal |
|---|---|
| RSI (14) | < 30 = oversold (buy), > 70 = overbought (sell) |
| MACD | Histogram direction — bullish or bearish crossover |
| Bollinger Bands | % position in bands — near lower = potential bounce |
| SMA 50 / 200 | Golden cross (bullish) or Death cross (bearish) |
| OBV | Rising = accumulation, Falling = distribution |
| Volume Ratio | 5-day vs 20-day avg — confirms strength of moves |

#### 3. Decision Agent (`agents/decision_agent.py`)
Receives both expert reports plus portfolio context, calls **Groq (Llama 3.3 70B)**, and returns structured JSON:

```json
{
  "symbol": "NVDA",
  "action": "BUY",
  "confidence": 82,
  "rationale": "RSI bouncing off oversold + MACD bullish crossover + analyst upgrades",
  "key_bull_factors": ["RSI 28 oversold", "Golden cross", "Revenue growth 122%"],
  "key_bear_factors": ["High P/E ratio", "Bearish volume trend"]
}
```

Falls back to **Gemini (gemini-2.0-flash)** automatically if Groq fails.

---

### Risk Manager (`execution/risk_manager.py`)

Runs **before** agent analysis every cycle to protect existing positions.

**Stocks:**
| Trigger | Threshold |
|---|---|
| Stop-Loss | −7% from entry price |
| Take-Profit | +15% from entry price |

**Crypto:**
| Trigger | Threshold |
|---|---|
| Stop-Loss | −12% from entry price |
| Take-Profit | +25% from entry price |

**Position Sizing** (scales with confidence):
| Confidence | Cash Deployed |
|---|---|
| 65–79% | 5% of available cash |
| 80–89% | 10% of available cash |
| 90–100% | 20% of available cash |

Stocks are sized in **whole shares**. Crypto is sized in **dollar notional** (e.g. $500 of BTC) so fractional amounts work automatically.

**Limits:**
- Max 5 stock positions simultaneously
- Max 4 crypto positions simultaneously

---

### Alpaca Client (`execution/alpaca_client.py`)

Handles all Alpaca Paper Trading API communication:
- Market open/close check (respects holidays via `/clock` endpoint)
- Account balance, buying power, portfolio value
- All current positions with live prices
- Stock orders: whole-share market orders (`time_in_force: day`)
- Crypto orders: notional market orders (`time_in_force: gtc`)
- Wash trade protection — cancels open orders for a symbol before placing a sell
- `get_orders_today()` and `get_daily_pnl()` for end-of-day reporting

---

### Telegram Notifier (`execution/telegram_notifier.py`)

Silent by default — only sends a message when something worth knowing happens.

**Trade Alert** (on every filled order):
```
🟢 TRADE ALERT
Action:     BUY NVDA
Amount:     12 shares
Confidence: 82%
Rationale:  RSI oversold bounce + analyst upgrades + golden cross
Cash Left:  $87,420.00
```

```
🟢 TRADE ALERT
Action:     BUY BTC/USD
Amount:     $500.00 notional
Confidence: 71%
Rationale:  RSI oversold, strong OBV accumulation
Cash Left:  $62,000.00
```

**Risk Exit** (stop-loss or take-profit triggered):
```
⚠️ RISK EXIT
Action: SELL TSLA (STOP LOSS -7.2%)
Shares: 8
```

**Error Alert** (data fetch failure, LLM error, order rejection):
```
❌ BOT ERROR
Context: Order BUY NVDA
Error:   insufficient buying power
```

**End-of-Day Summary** (sent once, within 15 min of market close):
```
📅 END OF DAY SUMMARY
────────────────────────────────
Trades Today:  3 buys | 1 sells
Day P&L:       📈 +$234.50
Total P&L:     📈 +$234.50
Portfolio:     $100,234.50
Cash:          $68,120.30

Open Positions:
  📈 NVDA: 2 shares (+3.2%)
  📉 TSLA: 1 share (-1.1%)
  📈 BTC/USD: 0.005 shares (+1.8%)
```

---

## File Structure

```
trading_bot/
│
├── main.py                        # Entry point
│                                  # python main.py          → single cycle
│                                  # python main.py --daemon → continuous loop (AWS EC2)
│
├── config.py                      # All tunable settings
├── env_loader.py                  # Reads .env credentials
├── orchestrator.py                # Wires agents + execution into one cycle
│                                  # Split into _run_stock_cycle + _run_crypto_cycle
│
├── agents/
│   ├── fundamental_agent.py       # yfinance — stocks and crypto fundamentals
│   ├── technical_agent.py         # RSI, MACD, Bollinger Bands via ta library
│   └── decision_agent.py          # Groq LLM + Gemini fallback
│
├── execution/
│   ├── alpaca_client.py           # Alpaca REST API (stocks + crypto orders)
│   ├── risk_manager.py            # Stop-loss, take-profit, position sizing
│   └── telegram_notifier.py       # Trade alerts, error alerts, daily summary
│
├── dashboard/
│   └── app.py                     # Streamlit dashboard (hosted on Streamlit Cloud)
│
├── .github/
│   └── workflows/
│       └── trading_bot.yml        # GitHub Actions — triggered by cron-job.org
│
├── watchlist.json                 # Editable stock watchlist (managed via dashboard)
├── requirements.txt
└── .gitignore
```

---

## Configuration (`config.py`)

```python
# Stocks (also editable via watchlist.json / dashboard)
WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

# Crypto
CRYPTO_WATCHLIST = ["BTC/USD", "SOL/USD", "DOGE/USD", "AVAX/USD"]

MIN_CONFIDENCE     = 65     # Minimum confidence % to place any trade
MAX_POSITIONS      = 5      # Max simultaneous stock positions
MAX_CRYPTO_POSITIONS = 4    # Max simultaneous crypto positions

# Stock risk
STOP_LOSS_PCT      = 0.07   # 7%  drop triggers automatic sell
TAKE_PROFIT_PCT    = 0.15   # 15% gain triggers automatic sell

# Crypto risk (wider — crypto is more volatile)
CRYPTO_STOP_LOSS_PCT   = 0.12   # 12%
CRYPTO_TAKE_PROFIT_PCT = 0.25   # 25%

# Position sizing bands (fraction of available cash)
POSITION_SIZE_BANDS = [
    (65, 79,  0.05),   # 5%  of cash
    (80, 89,  0.10),   # 10% of cash
    (90, 100, 0.20),   # 20% of cash
]

LLM_PROVIDER = "groq"              # "groq" (primary) or "gemini" (fallback)
GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"
HIST_PERIOD  = "6mo"               # Price history window for technical indicators
```

---

## Hosting

### GitHub Actions + cron-job.org (Current — Free)

GitHub Actions runs each trading cycle. [cron-job.org](https://cron-job.org) acts as the external scheduler — it sends an HTTP POST to GitHub's `workflow_dispatch` endpoint every 2 minutes during market hours.

**Why not GitHub's built-in cron?** GitHub's scheduler is unreliable for new repos and has delays up to 15 minutes. cron-job.org fires within seconds and is free.

**Setup:**
1. Push this repo to GitHub (public or private)
2. Add all secrets under Settings → Secrets → Actions
3. Create a cron-job.org job:
   - URL: `https://api.github.com/repos/{owner}/{repo}/actions/workflows/trading_bot.yml/dispatches`
   - Method: POST
   - Headers: `Authorization: Bearer {your-github-pat}`, `Accept: application/vnd.github+json`
   - Body: `{"ref":"main"}`
   - Schedule: every 2 minutes, Mon–Fri

**GitHub Actions free tier:** 2,000 min/month. Market hours ≈ 1,950 min/month — fits comfortably.

### AWS EC2 (Alternative — Always-on daemon)

For continuous operation without GitHub Actions:
```bash
python3 main.py --daemon   # loops every 60 seconds during market hours
```

Install as a systemd service so it survives reboots:
```bash
sudo cp trading_bot.service /etc/systemd/system/
sudo systemctl enable trading_bot
sudo systemctl start trading_bot
```

---

## Dashboard

A Streamlit dashboard hosted on [Streamlit Community Cloud](https://streamlit.io/cloud) shows live portfolio state pulled from Alpaca:

- Portfolio value and total P&L
- All open positions with unrealized gain/loss
- Trade history
- Watchlist manager (add/remove stocks)

To run locally:
```bash
streamlit run dashboard/app.py
```

---

## Required Credentials (`.env`)

```
ALPACA_API_KEY=...        # Paper trading key — app.alpaca.markets
ALPACA_SECRET_KEY=...     # Paper trading secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

GROQ_API_KEY=...          # Free at console.groq.com (14,400 req/day)
GOOGLE_API_KEY=...        # Gemini fallback — aistudio.google.com (free)

TELEGRAM_BOT_TOKEN=...    # From @BotFather on Telegram
TELEGRAM_CHAT_ID=...      # Your chat ID from api.telegram.org/bot{token}/getUpdates
```

For GitHub Actions, these are stored as encrypted **Repository Secrets** — never committed to the repo.

---

## Dependencies

```
yfinance>=0.2.65    — stock and crypto market data
ta>=0.11.0          — technical indicators (RSI, MACD, Bollinger Bands, etc.)
google-genai>=2.0.0 — Gemini LLM fallback
requests>=2.31.0    — HTTP client (Alpaca, Groq, Telegram APIs)
pandas>=2.3.0       — data manipulation
numpy>=1.26.4       — numerical operations
```

Install:
```bash
pip install -r requirements.txt
```

---

## Tuning Tips

**Bot trades too rarely?**
Lower `MIN_CONFIDENCE` to 60 in `config.py`.

**Bot trades too aggressively or losing money?**
Raise `MIN_CONFIDENCE` to 70 or 75.

**Positions stopped out too often?**
Raise `STOP_LOSS_PCT` (stocks) or `CRYPTO_STOP_LOSS_PCT` to give more room on volatile assets.

**Want to lock in gains faster?**
Lower `TAKE_PROFIT_PCT` / `CRYPTO_TAKE_PROFIT_PCT`.

**Switch LLM to Gemini:**
```python
LLM_PROVIDER = "gemini"
```

After any config change, push to GitHub and the next cycle picks it up automatically:
```bash
git add config.py
git commit -m "update config"
git push
```
