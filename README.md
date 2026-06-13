# Autonomous Multi-Agent Trading Bot

An autonomous paper trading system that runs 24/7. Three AI agents analyze stocks and crypto every 2 minutes, execute trades via Alpaca's paper API, and send Telegram alerts. No human intervention needed.

---

## How It Works — Big Picture

```
cron-job.org  ──►  GitHub Actions  ──►  main.py  ──►  orchestrator.py
  every 2 min         (free tier)         entry           3 cycles run
                                          point           in parallel
```

Every 2 minutes:
1. **Stock Cycle** runs during NYSE hours (Mon–Fri 9:30–4:00 ET)
2. **Crypto Cycle** runs 24/7 — crypto never sleeps
3. **Momentum Cycle** runs whenever market is open — hunts live trending stocks + volatile crypto

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ENTRY LAYER                                  │
│                                                                      │
│   cron-job.org (every 2 min)                                         │
│        │                                                             │
│        ▼                                                             │
│   GitHub Actions  ──►  main.py                                       │
│                         │                                            │
│                         ├─ Is it just after 4 PM?  → daily_summary  │
│                         ├─ No trades this hour?    → heartbeat ping  │
│                         └─ Otherwise               → run_cycle()     │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ORCHESTRATOR LAYER                             │
│                        (orchestrator.py)                             │
│                                                                      │
│   ┌─────────────────────┐  ┌──────────────────────┐                 │
│   │   STOCK CYCLE        │  │    CRYPTO CYCLE       │                │
│   │  (market hours only) │  │    (24/7 always)      │                │
│   │                      │  │                       │                │
│   │  Core watchlist:     │  │  Core watchlist:      │                │
│   │  AAPL TSLA NVDA      │  │  SOL/USD              │                │
│   │  MSFT AMZN + custom  │  │                       │                │
│   │                      │  │  Cap: max 35% of      │                │
│   │  Max 5 positions     │  │  total portfolio      │                │
│   └──────────┬───────────┘  └──────────┬────────────┘                │
│              │                         │                             │
│              └────────────┬────────────┘                             │
│                           │                                          │
│   ┌───────────────────────▼──────────────────────────────────────┐  │
│   │                  MOMENTUM CYCLE                               │  │
│   │                  (market hours)                               │  │
│   │                                                               │  │
│   │  Step 1: market_scanner.py                                    │  │
│   │          Yahoo Finance screeners → most_actives + day_gainers │  │
│   │          No hardcoded list — discovers what's moving TODAY    │  │
│   │                                                               │  │
│   │  Step 2: Technical pre-filter (FREE — no LLM)                 │  │
│   │          volume ≥ 1.8×avg  AND  RSI 55–75  AND  MACD > 0     │  │
│   │          Pass 2/3 checks → send to LLM   Fail → skip          │  │
│   │                                                               │  │
│   │  Step 3: LLM decision (only on 2–3 pre-filtered candidates)   │  │
│   │          Tight exits: stocks −4%/+8%  crypto −6%/+12%        │  │
│   │          Shared 10% portfolio budget across stocks + crypto   │  │
│   └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼─────────────────┐
          ▼                ▼                 ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────────┐
│   AGENT LAYER   │ │ EXECUTION     │ │   NOTIFICATION    │
│                 │ │ LAYER         │ │   LAYER           │
│ fundamental_    │ │               │ │                   │
│  agent.py       │ │ alpaca_       │ │ telegram_         │
│  • stocks: P/E, │ │  client.py    │ │  notifier.py      │
│    EPS, analyst │ │  • REST API   │ │  • trade alert    │
│    news,insider │ │  • stock +    │ │    (every trade)  │
│  • crypto: mcap,│ │    crypto     │ │  • risk exit      │
│    52w range,   │ │    orders     │ │  • error alert    │
│    news         │ │  • dedup      │ │  • EOD summary    │
│                 │ │    guard      │ │  • hourly         │
│ technical_      │ │               │ │    heartbeat      │
│  agent.py       │ │ risk_         │ │                   │
│  • RSI, MACD,   │ │  manager.py   │ └───────────────────┘
│    BB, SMA,     │ │  • stop-loss  │
│    OBV, volume  │ │  • take-profit│
│                 │ │  • position   │
│ decision_       │ │    sizing     │
│  agent.py       │ │  • reserve    │
│  • 4-provider   │ │    floor      │
│    LLM failover │ │               │
│  • bull/bear    │ └───────────────┘
│    debate       │
└─────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DASHBOARD LAYER                               │
│                        (dashboard/app.py)                            │
│                                                                      │
│   Streamlit Cloud — auto-deploys on every push to main               │
│                                                                      │
│   [📊 Overview] [💼 Positions] [🚀 Momentum] [📜 History]            │
│   [📋 Reports]  [📡 Prices]                                          │
│                                                                      │
│   Single-view layout — no scrolling on standard 1080p screen         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Three AI Agents

### 1. Fundamental Agent
Fetches data via `yfinance` — adapts automatically to stock vs crypto input.

**Stocks:** P/E ratio · EPS · revenue growth · earnings growth · debt/equity · ROE · analyst rating + price target · recent upgrades/downgrades · earnings surprises · **last 5 news headlines** · **recent insider transactions** (name, role, shares, dollar value)

**Crypto:** market cap · circulating supply · 52-week range · 24h volume · **last 3 news headlines**

### 2. Technical Agent
Computes price action indicators on 6 months of OHLCV data. Same logic for stocks and crypto.

| Indicator | What It Signals |
|-----------|----------------|
| RSI (14) | < 30 oversold → potential buy · > 70 overbought → potential sell |
| MACD histogram | Positive = bullish momentum · Negative = bearish momentum |
| Bollinger Bands | Near lower band = potential bounce |
| SMA 50 / 200 | Golden cross = bullish trend · Death cross = bearish trend |
| OBV | Rising = accumulation · Falling = distribution |
| Volume ratio | 5d vs 20d avg — confirms whether a move has real money behind it |

### 3. Decision Agent — 4-Provider LLM Failover

Every decision uses an automatic failover chain. Any 429 / quota error silently moves to the next provider — the bot never fails on an LLM call during normal trading.

```
Cerebras (gpt-oss-120b, 120B reasoning model, ~2s)
    │  rate-limited? ↓
Groq (llama-3.3-70b-versatile, ~3s)
    │  rate-limited? ↓
Gemini (gemini-2.0-flash, ~5s)
    │  rate-limited? ↓
OpenRouter (llama-3.3-70b:free, last resort)
```

**Mandatory Bull/Bear Debate — every decision:**

Before outputting any action, the LLM must:
1. **BULL CASE** — 3 strongest data-backed reasons to BUY (cite specific numbers)
2. **BEAR CASE** — 3 strongest data-backed reasons NOT to buy / to SELL (cite specific numbers)
3. **VERDICT** — only BUY/SELL when one side clearly dominates

This prevents one-sided bias and forces the model to find the best counter-argument before committing.

**Every prompt includes:**
- Macro context (SPY regime: BULL/BEAR vs SMA20 + portfolio drawdown %)
- Portfolio context (available cash, current holding, open position count)
- Fundamental report (incl. news + insider data)
- Technical report

**Calibration rules baked into system prompt:**
- BEAR market regime → raise confidence bar by +5 pts for any BUY
- Insider SELLING → strong bear signal
- Insider BUYING → moderate bull signal
- Confidence < 65 → HOLD (never trades on weak signals)

**Sample output:**
```json
{
  "symbol": "NVDA",
  "action": "HOLD",
  "confidence": 62,
  "bull_case": ["RSI 37 approaching oversold", "Analyst target $298 = 46% upside", "Revenue growth 85%"],
  "bear_case": ["MACD bearish, hist −5.4", "Insider STEVENS sold $221M shares Jun 4", "BEAR regime +5pt bar applies"],
  "rationale": "Insider sale of $221M outweighs technical oversold setup. Bear side wins on insider signal alone.",
  "time_horizon": "hold"
}
```

---

## Capital Allocation — Three Guardrails

```
Portfolio: $100,000
│
├── 20% Cash Reserve Floor ($20,000 locked as dry powder)
│   └── Unlocks partially at confidence ≥ 88% (up to 50% of reserve per trade)
│
├── 65% Core Investing Pool ($65,000 available for core trades)
│   ├── Core Stocks (no fixed cap — respects MAX_POSITIONS = 5)
│   └── Core Crypto (capped at 35% of total portfolio = $35,000)
│
└── 10% Momentum Budget ($10,000 shared across stocks + crypto momentum)
    ├── Momentum Stocks — discovered live via Yahoo screeners
    └── Momentum Crypto — DOGE, AVAX, LINK, UNI
        (tight exits: −4%/+8% stocks, −6%/+12% crypto)
```

**Why the reserve?** Expert traders always keep dry powder. When a once-in-a-year opportunity hits (RSI 20, major catalyst), the bot can deploy reserve cash instead of being stuck 100% invested.

---

## Watchlists

### Core Stocks (editable via dashboard)
| Symbol | Company |
|--------|---------|
| AAPL | Apple |
| TSLA | Tesla |
| NVDA | NVIDIA |
| MSFT | Microsoft |
| AMZN | Amazon |

Exits: stop-loss −7% · take-profit +15%

### Core Crypto (fixed — runs 24/7)
| Symbol | Asset | Stop | Target |
|--------|-------|------|--------|
| SOL/USD | Solana | −12% | +25% |

> **Note:** BTC/USD was removed — Alpaca paper trading never fills BTC market orders (65 cancelled orders, 0 filled). The dedup guard also blocks any symbol with a recently-cancelled buy for 90 minutes, preventing infinite retry loops.

Max 35% of total portfolio in crypto (core + momentum combined).

### Momentum Universe (self-discovering stocks + fixed crypto)
Momentum **stocks** are discovered live each cycle from Yahoo Finance screeners — no hardcoded list. The system asks: "what's actually moving today?"

Momentum **crypto** is fixed to the most liquid volatile coins on Alpaca:
`DOGE/USD` · `AVAX/USD` · `LINK/USD` · `UNI/USD`

Exits: −4% stop / +8% take for stocks · −6% stop / +12% take for crypto

---

## Ghost Order Protection

The dedup guard (`get_recent_buy_symbols`) blocks re-buying a symbol if:
- It had a **filled or pending buy** in the last **15 minutes** (handles positions API lag after crypto fills)
- It had a **cancelled buy** in the last **90 minutes** (breaks phantom-order retry loops)

This replaced the previous logic that only tracked non-cancelled orders, which caused BTC/USD to be re-ordered every 18 minutes forever.

---

## File Structure

```
trading_bot/
│
├── main.py                 # Entry point
│                           #   python main.py            → single cycle (GitHub Actions)
│                           #   python main.py --daemon   → continuous loop (AWS EC2)
│
├── config.py               # All tuneable constants — edit here, push, done
├── env_loader.py           # Manual .env parser (no python-dotenv required)
├── watchlist.json          # Stock watchlist — editable via dashboard UI
│
├── orchestrator.py         # Wires everything into one trading cycle
│                           #   _run_stock_cycle()    — core stocks (market hours)
│                           #   _run_crypto_cycle()   — core crypto (24/7)
│                           #   _run_momentum_cycle() — screener → pre-filter → LLM
│                           #   _build_macro_context()— SPY regime + drawdown for LLM
│
├── agents/
│   ├── fundamental_agent.py  # yfinance: fundamentals + news headlines + insider transactions
│   ├── technical_agent.py    # RSI, MACD, Bollinger Bands, SMA50/200, OBV via ta library
│   └── decision_agent.py     # 4-provider failover LLM with mandatory bull/bear debate
│
├── execution/
│   ├── alpaca_client.py      # Alpaca Paper Trading REST API wrapper
│   │                         #   get_recent_buy_symbols() — dedup guard (15 min active, 90 min cancelled)
│   │                         #   cancel_stale_open_orders() — kills stuck GTC crypto orders only
│   ├── risk_manager.py       # Stop-loss, take-profit, position sizing, cash reserve
│   ├── market_scanner.py     # Live Yahoo Finance screeners (most_actives + day_gainers)
│   └── telegram_notifier.py  # Trade alerts, risk exits, errors, EOD summary, heartbeat
│
├── dashboard/
│   └── app.py              # Streamlit dashboard — 6-tab compact single-view layout
│
├── .github/
│   └── workflows/
│       └── trading_bot.yml # GitHub Actions — triggered by cron-job.org every 2 min
│                           #   uses requirements-bot.txt (includes cerebras-cloud-sdk)
│
├── requirements.txt        # Dashboard dependencies only (used by Streamlit Cloud)
└── requirements-bot.txt    # Full bot dependencies (used by GitHub Actions)
```

---

## Momentum Scanner — How It Discovers Stocks

```
Every 2-min cycle (market hours):
│
▼
market_scanner.py
  ├── most_actives screener  (highest volume today)
  └── day_gainers screener   (biggest % gain today)
        │
        ▼  deduplicate + filter (no ETFs, no penny stocks < $2)
        │
        ▼  Technical pre-filter (FREE — yfinance, no LLM)
           volume ≥ 1.8× avg  ·  RSI 55–75  ·  MACD hist > 0
           Pass 2 of 3 → candidate     Fail → discard immediately
                │
                ▼ (typically 2–4 candidates survive)
           Decision Agent (LLM) → BUY / HOLD
```

This design saves ~90% of LLM API calls — the expensive model only sees candidates that already show momentum signals.

---

## Risk Management

### Position Sizing (scales with LLM confidence)
| Confidence | Cash Deployed |
|---|---|
| 65–79% | 5% of investable cash |
| 80–89% | 10% of investable cash |
| ≥ 90% | 20% of investable cash |

Investable cash = `available_cash − (portfolio_value × 0.20)` (reserves excluded)

At confidence ≥ 88%, up to 50% of the reserve floor can be deployed.

### Stop-Loss / Take-Profit

| Type | Stop-Loss | Take-Profit |
|---|---|---|
| Core Stocks | −7% | +15% |
| Core Crypto | −12% | +25% |
| Momentum Stocks | −4% | +8% |
| Momentum Crypto | −6% | +12% |

Momentum exits are tighter because the goal is riding short-term waves, not holding through drawdowns.

---

## Telegram Alerts

Silent by default — only sends a message when something matters.

**Trade Alert** — every filled order:
```
🟢 TRADE ALERT — BUY NVDA
Units:      12 shares @ $875.20
Cost:       $10,502.40
Confidence: 82%

📊 Technical:
  RSI 28.4 · OVERSOLD
  MACD · BULLISH (hist +0.0231)
  Trend · GOLDEN CROSS (SMA50=820.10)
  Volume · 2.3x avg [HIGH]

🏢 Fundamental:
  Analyst · Strong Buy · target $950.00 (+8.5%)
  P/E · 45.2x
  Revenue growth · +122.0%

💬 Rationale: RSI oversold + golden cross + analyst upgrades
Cash left:  $52,800.00
```

**Risk Exit:**
```
⚠️ RISK EXIT
Action: SELL TSLA (STOP LOSS −7.2%)
Units:  8
```

**Hourly Heartbeat** (when no trades fire for an hour):
```
🤖 BOT HEARTBEAT  (no trades this hour)
🔴 Stock market CLOSED  ·  🔗 Crypto 24/7
Portfolio:  $99,786.00
Cash:       $17,232.00
Total P&L:  📉 $-214.00

Open Positions:
  📈 NVDA: 2 shares (+3.2%)
  🔗 SOL/USD: 1.2 units (+1.8%)
```

**End-of-Day Summary** (fired 0–6 min after 4 PM ET):
```
📅 END OF DAY SUMMARY
────────────────────────────────
Trades Today:  3 buys | 1 sells
Day P&L:       📈 +$234.50
Total P&L:     📈 +$234.50
Portfolio:     $100,234.50
Cash:          $68,120.30
```

---

## Dashboard

Hosted on [Streamlit Community Cloud](https://streamlit.io/cloud). Auto-deploys on every push to `main`.

**6-tab single-view layout:**

```
┌─ 8 KPI Metrics ──────────────────────────────────────────────────────────┐
│ Portfolio │ Cash │ Total P&L │ Positions │ Win Rate │ PF │ Weekly │ Mom  │
├───────────────────────────────────────────────────────────────────────────┤
│ [📊 Overview] [💼 Positions] [🚀 Momentum] [📜 History] [📋 Reports]      │
│ [📡 Prices]                                                               │
│                                                                           │
│  Overview:   Performance chart (60%) │ Allocation pie (40%)              │
│              Combined P&L bar — all open positions                       │
│                                                                           │
│  Positions:  Merged table (stocks + crypto) with stop/target cols        │
│                                                                           │
│  Momentum:   Budget strip + [Screener│Filter│Open│Trades] sub-nav       │
│                                                                           │
│  History:    Trade log with All / Stocks / Crypto filter                 │
│                                                                           │
│  Reports:    Realized P&L per trade · filters: Side / Range / Type       │
│              By Day view (collapsible) + All Trades flat table           │
│                                                                           │
│  Prices:     Live price tiles (stocks + crypto) + performance stats      │
└───────────────────────────────────────────────────────────────────────────┘
```

Run locally:
```bash
streamlit run dashboard/app.py
```

---

## Configuration (`config.py`)

All tunable settings live here. Push a change and the next cycle picks it up automatically.

```python
# Core watchlists
WATCHLIST        = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]  # also editable via dashboard
CRYPTO_WATCHLIST = ["SOL/USD"]                                 # runs 24/7 (BTC removed — never fills on paper)

# Position limits
MAX_POSITIONS        = 5
MAX_CRYPTO_POSITIONS = 2

# Core risk thresholds
STOP_LOSS_PCT          = 0.07   # 7%  stock stop-loss
TAKE_PROFIT_PCT        = 0.15   # 15% stock take-profit
CRYPTO_STOP_LOSS_PCT   = 0.12   # 12% crypto stop-loss
CRYPTO_TAKE_PROFIT_PCT = 0.25   # 25% crypto take-profit
CRYPTO_PORTFOLIO_CAP   = 0.35   # max 35% of portfolio in crypto

# Capital guardrails
MIN_CASH_RESERVE_PCT      = 0.20  # always keep 20% as dry powder
RESERVE_DEPLOY_CONFIDENCE = 88    # unlock reserve at ≥88% confidence
RESERVE_MAX_DEPLOY_PCT    = 0.50  # deploy at most 50% of reserve per trade

# Momentum tier
MOMENTUM_TOTAL_BUDGET_PCT = 0.10   # 10% shared across stocks + crypto momentum
MAX_MOMENTUM_POSITIONS    = 4
MOMENTUM_MIN_CONFIDENCE   = 80     # higher bar than core 65%
MOMENTUM_VOLUME_RATIO_MIN = 1.8    # 1.8× avg volume required
MOMENTUM_STOCK_STOP_PCT   = 0.04   # −4%  (tighter than core)
MOMENTUM_STOCK_TAKE_PCT   = 0.08   # +8%  (faster profit-taking)
MOMENTUM_CRYPTO_STOP_PCT  = 0.06
MOMENTUM_CRYPTO_TAKE_PCT  = 0.12

# LLM — 4-provider failover (Cerebras → Groq → Gemini → OpenRouter)
MIN_CONFIDENCE   = 65
CEREBRAS_MODEL   = "gpt-oss-120b"           # primary: fastest (~2s)
GROQ_MODEL       = "llama-3.3-70b-versatile"
GEMINI_MODEL     = "gemini-2.0-flash"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
HIST_PERIOD      = "6mo"
```

---

## Hosting

### GitHub Actions + cron-job.org (Current — Free)

[cron-job.org](https://cron-job.org) fires a `workflow_dispatch` POST to GitHub every 2 minutes. GitHub Actions runs the cycle and exits. No server needed.

**Why cron-job.org instead of GitHub's built-in cron?**
GitHub's scheduler can delay up to 15 minutes on new repos. cron-job.org fires within seconds and is free.

**cron-job.org setup:**
- URL: `https://api.github.com/repos/{owner}/{repo}/actions/workflows/trading_bot.yml/dispatches`
- Method: `POST`
- Headers: `Authorization: Bearer {github-pat}`, `Accept: application/vnd.github+json`
- Body: `{"ref":"main"}`
- Schedule: every 2 minutes 24/7 (crypto runs overnight; stock/momentum skip outside market hours automatically)

**LLM quota at 2-minute intervals:**

| Provider | Free Limit | Usage at 2-min | Status |
|---|---|---|---|
| Cerebras | ~60 req/min | ~4/min | ✅ Fine |
| Groq | 14,400 req/day | ~5,760/day | ✅ Fine |
| Gemini | 1,500 req/day | overflow only | ✅ Fine |
| OpenRouter | generous free tier | last resort | ✅ Fine |

### AWS EC2 (Alternative)
```bash
python3 main.py --daemon   # runs every 60 sec during market hours, idles overnight
```

---

## Required Credentials

```
# Alpaca Paper Trading — app.alpaca.markets
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

# LLM — 4-provider failover chain
CEREBRAS_API_KEY=...     # free at cloud.cerebras.ai  (fastest, 120B model)
GROQ_API_KEY=...         # free at console.groq.com   (14,400 req/day)
GOOGLE_API_KEY=...       # free at aistudio.google.com
OPENROUTER_API_KEY=...   # free at openrouter.ai      (last resort)

# Telegram
TELEGRAM_BOT_TOKEN=...   # from @BotFather
TELEGRAM_CHAT_ID=...     # from api.telegram.org/bot{token}/getUpdates
```

For GitHub Actions: add these as **Repository Secrets** (Settings → Secrets → Actions). Never committed to the repo.

---

## Tuning Guide

| Goal | Setting to change |
|------|------------------|
| Bot trades too rarely | Lower `MIN_CONFIDENCE` to 60 |
| Bot trades too aggressively | Raise `MIN_CONFIDENCE` to 75 |
| Positions stopped out too often | Raise `STOP_LOSS_PCT` / `CRYPTO_STOP_LOSS_PCT` |
| Lock in gains faster | Lower `TAKE_PROFIT_PCT` / `CRYPTO_TAKE_PROFIT_PCT` |
| More momentum trades | Lower `MOMENTUM_MIN_CONFIDENCE` to 75 |
| Less crypto exposure | Lower `CRYPTO_PORTFOLIO_CAP` to 0.20 |
| More dry powder | Raise `MIN_CASH_RESERVE_PCT` to 0.30 |

After any change:
```bash
git add config.py && git commit -m "update config" && git push
```
The next cycle picks it up automatically.

---

## Dependencies

Two requirements files — split so Streamlit Cloud stays lean:

**`requirements.txt`** — Dashboard (Streamlit Cloud):
```
yfinance>=0.2.65         market data via Yahoo Finance
ta>=0.11.0               technical indicators
google-genai>=2.0.0      Gemini LLM
requests>=2.31.0         HTTP client
pandas>=2.3.0
numpy>=1.26.4
plotly>=5.22.0           dashboard charts
streamlit-autorefresh>=1.0.1
```

**`requirements-bot.txt`** — Trading bot (GitHub Actions):
```
# all of the above, plus:
cerebras-cloud-sdk>=1.21.0   official Cerebras SDK (primary LLM)
```

```bash
# Dashboard
pip install -r requirements.txt

# Trading bot (GitHub Actions uses this)
pip install -r requirements-bot.txt
```
