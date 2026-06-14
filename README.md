# Autonomous Multi-Agent Trading Bot

An autonomous paper trading system that runs 24/7. Three AI agents analyze stocks and crypto every 2 minutes, execute trades via Alpaca's paper API, and send Telegram alerts. No human intervention needed.

---

## System Architecture

```mermaid
flowchart TD
    CRON["cron-job.org - every 2 min"] -->|POST workflow_dispatch| GH["GitHub Actions"]
    GH --> MAIN["main.py"]

    MAIN -->|Market hours| SC["Stock Cycle\nAAPL / TSLA / NVDA / MSFT / AMZN"]
    MAIN -->|24 slash 7| CC["Crypto Cycle\nETH / SOL / DOGE / AVAX"]
    MAIN -->|Stocks + Crypto| MC["Momentum Cycle\nStocks: Yahoo Finance screeners\nCrypto: CoinGecko top-100"]

    SC --> FA["Fundamental Agent\nP/E, EPS, Analyst rating\nNews headlines, Insider trades"]
    CC --> FA
    MC --> FA

    SC --> TA["Technical Agent\nRSI, MACD, Bollinger Bands\nSMA 50/200, OBV, Volume"]
    CC --> TA
    MC --> TA

    FA --> DA["Decision Agent - Bull/Bear Debate\nCerebras, Groq, Gemini, OpenRouter\nBUY / SELL / HOLD + confidence 0-100"]
    TA --> DA
    MACRO["Macro Context\nSPY BULL/BEAR regime\nPortfolio drawdown"] --> DA

    DA --> RM["Risk Manager\nPosition sizing by confidence\nStop-loss and take-profit sweep"]

    RM --> ALP["Alpaca Paper Trading"]
    RM --> TG["Telegram Alerts"]
    RM --> DASH["Streamlit Dashboard"]
```

---

## Component Architecture

End-to-end process flow — from raw data sources through AI analysis to trade execution and alerts.

![Component Architecture](docs/architecture.svg)

---

## LLM Load Balancing

Every LLM call uses **round-robin** across all 4 providers so each handles ~25% of daily volume — no single provider absorbs the full load and hits its quota. If the assigned provider returns a 429 / quota error, the call automatically falls through to the next in the rotated chain.

**Rotation formula:** `start = (time_offset + call_count) % 4`
- `time_offset` advances every 2 minutes → different lead provider each GitHub Actions run
- `call_count` increments per symbol → consecutive symbols within the same run use different providers

```mermaid
flowchart LR
    REQ(["LLM Request\nstart = time+count mod 4"])

    REQ -->|"slot 1 (rotates)"| C["Cerebras\ngpt-oss-120b\n~2s"]
    REQ -->|"slot 1 (rotates)"| G["Groq\nllama-3.3-70b\n~3s"]
    REQ -->|"slot 1 (rotates)"| GE["Gemini\ngemini-2.0-flash\n~5s"]
    REQ -->|"slot 1 (rotates)"| OR["OpenRouter\nllama-3.3-70b free\n~6s"]

    C -->|success| OUT(["Decision JSON"])
    G -->|success| OUT
    GE -->|success| OUT
    OR -->|success| OUT

    C -->|429| G
    G -->|429| GE
    GE -->|429| OR
```

---

## Capital Allocation

```mermaid
pie title "Portfolio Target Allocation"
    "Cash Reserve locked" : 20
    "Core Stocks - up to 5 positions" : 45
    "Core Crypto - max 35 percent" : 25
    "Momentum Budget" : 10
```

| Tier | Budget | Rules |
|---|---|---|
| 🔒 Cash Reserve | **20%** always locked | Unlocks at confidence ≥ 88% (up to 50% of reserve per trade) |
| 📈 Core Stocks | Up to 65% investable pool | Max 5 positions · −7% stop / +15% take |
| 🔗 Core Crypto | Max 35% of total portfolio | ETH / SOL / DOGE / AVAX · −12% stop / +25% take · max 3 positions |
| 🚀 Momentum | **10%** shared budget | Live-discovered stocks (Yahoo) + crypto (CoinGecko) · −4%/+8% stops |

---

## Momentum Discovery Pipeline

Both stocks and crypto are discovered dynamically every cycle — no hardcoded ticker lists.

```mermaid
flowchart TD
    YF["Yahoo Finance\nScreeners - market hours only"]
    CG["CoinGecko\nTop-100 coins by 24h volume - 24/7"]

    YF -->|most actives| SA["Most Active Stocks by Volume"]
    YF -->|top gainers| SB["Top Day Gainers"]
    CG -->|filter to Alpaca-tradeable| CA["Crypto Candidates\nScore: 24h change x vol/mcap ratio"]

    SA --> DEDUP["Deduplicate and Filter\nno ETFs, no penny stocks under 2 USD\nexclude core watchlist symbols"]
    SB --> DEDUP
    CA --> DEDUP

    DEDUP --> PRE["Technical Pre-filter - no LLM\nvolume 1.8x avg AND RSI 55-75 AND MACD positive\nPass 2 of 3 checks to proceed"]

    PRE -->|2-4 candidates survive| LLM["Decision Agent\nLLM call only on pre-filtered candidates"]
    PRE -->|fail| SKIP["Skip - no LLM call"]

    LLM -->|conf 80+| BUY["BUY momentum position"]
    LLM -->|conf below 80| HOLD["HOLD"]
```

---

## Decision Agent — Bull / Bear Debate

Every decision follows a mandatory 3-step process before outputting any action:

```mermaid
flowchart TD
    DATA["Input: Fundamentals + Technicals\nNews, Insider trades, Macro regime, Portfolio context"]

    DATA --> S1["Step 1 - Bull Case\n3 strongest data-backed reasons to BUY\nRSI value, EPS growth, analyst target upside"]
    DATA --> S2["Step 2 - Bear Case\n3 strongest data-backed reasons to SELL\nMACD signal, insider sale amount, debt/equity"]

    S1 --> S3["Step 3 - Verdict\nWeigh both sides\nOnly act when one side clearly dominates"]
    S2 --> S3

    S3 -->|conf 75+ and clear winner| ACT["BUY or SELL"]
    S3 -->|conf 60-74 or mixed signals| HOLD2["HOLD"]
    S3 -->|conf below 60| HOLD3["HOLD"]

    ACT --> RULES["Calibration applied automatically\nBEAR regime: +5 pts required for any BUY\nInsider SELLING: strong bear signal\nInsider BUYING: moderate bull signal\nNegative news: bear case weighted higher"]
```

**Sample output:**
```json
{
  "symbol": "NVDA",
  "action": "HOLD",
  "confidence": 62,
  "bull_case": [
    "RSI 37 approaching oversold — historically reversal zone",
    "Analyst consensus strong_buy, target $298 = 46% upside from $205",
    "Revenue growth 85.2%, earnings growth 214% — exceptional fundamentals"
  ],
  "bear_case": [
    "MACD histogram −5.42, signal line bearish for 3 weeks",
    "Insider STEVENS MARK A sold 1,000,000 shares ($221M) on 2026-06-04",
    "BEAR regime active — SPY below SMA20, confidence bar raised +5pts"
  ],
  "rationale": "Insider sale of $221M outweighs technical oversold setup. Bear side wins on insider signal alone. Waiting for regime to flip BULL before entering.",
  "time_horizon": "hold"
}
```

---

## Watchlists

### Core Stocks (editable via dashboard)
| Symbol | Company | Stop | Target |
|--------|---------|------|--------|
| AAPL | Apple | −7% | +15% |
| TSLA | Tesla | −7% | +15% |
| NVDA | NVIDIA | −7% | +15% |
| MSFT | Microsoft | −7% | +15% |
| AMZN | Amazon | −7% | +15% |

### Core Crypto (fixed — runs 24/7)
| Symbol | Asset | Stop | Target |
|--------|-------|------|--------|
| ETH/USD | Ethereum | −12% | +25% |
| SOL/USD | Solana | −12% | +25% |
| DOGE/USD | Dogecoin | −12% | +25% |
| AVAX/USD | Avalanche | −12% | +25% |

> **Note:** BTC/USD is excluded — Alpaca paper trading accepts BTC orders but never fills them (65 cancelled orders, 0 filled). The dedup guard blocks any symbol with a recently-cancelled buy for 90 minutes, preventing infinite retry loops.

### Momentum Crypto (dynamic — via CoinGecko)
No hardcoded list. Every cycle the bot queries CoinGecko's top 100 coins by 24h volume, filters to Alpaca-tradeable symbols, scores each by `24h_change × (1 + volume/marketcap_ratio × 10)`, and picks the top 3 positive-momentum candidates. Exits: −6% stop / +12% take.

---

## Risk Management

### Position Sizing — scales with LLM confidence

| Confidence | Cash Deployed | When Used |
|---|---|---|
| 65 – 79% | 5% of investable cash | Moderate signal, some uncertainty |
| 80 – 89% | 10% of investable cash | Strong signal, most data aligned |
| ≥ 90% | 20% of investable cash | Overwhelming evidence |
| ≥ 88% | Unlocks reserve too | Up to 50% of the 20% reserve |

*Investable cash = `available_cash − (portfolio_value × 0.20)`* (reserves always excluded)

### Stop-Loss / Take-Profit by Tier

| Tier | Stop-Loss | Take-Profit | Rationale |
|---|---|---|---|
| Core Stocks | −7% | +15% | Hold through normal volatility |
| Core Crypto | −12% | +25% | Crypto needs wider room |
| Momentum Stocks | −4% | +8% | Short-term wave riding |
| Momentum Crypto | −6% | +12% | Fast in, fast out |

---

## Ghost Order Protection

The dedup guard prevents two specific failure modes:

```mermaid
flowchart LR
    CHECK["get_recent_buy_symbols()"]

    CHECK -->|active buy in last 15 min| B1["BLOCK\nPositions API lag after crypto fill"]
    CHECK -->|cancelled buy in last 90 min| B2["BLOCK\nGhost order retry loop"]
    CHECK -->|nothing recent| OK["ALLOW BUY"]
```

This replaced the old logic that only tracked non-cancelled orders, which caused BTC/USD to be re-ordered every 18 minutes in a loop (65 phantom orders, 0 filled).

---

## File Structure

```
trading_bot/
│
├── main.py                 # Entry point — single cycle (GitHub Actions) or --daemon loop
├── config.py               # All tuneable constants — push a change, next cycle picks it up
├── env_loader.py           # Manual .env parser — no python-dotenv needed
├── watchlist.json          # Stock watchlist — editable via dashboard without redeploying
│
├── orchestrator.py         # Wires all agents + execution into one cycle
│                           #   _run_stock_cycle()     market hours only
│                           #   _run_crypto_cycle()    24/7
│                           #   _run_momentum_cycle()  screener → pre-filter → LLM
│                           #   _build_macro_context() SPY regime + drawdown for LLM
│
├── agents/
│   ├── fundamental_agent.py  # yfinance: fundamentals + news headlines + insider transactions
│   │                         # Stocks: FinBERT sentiment via HuggingFace API (keyword fallback)
│   │                         # Crypto: CoinGecko community sentiment votes (no API key needed)
│   ├── technical_agent.py    # RSI, MACD, Bollinger Bands, SMA50/200, OBV via ta library
│   └── decision_agent.py     # Round-robin across 4 LLM providers + fallback on 429
│                             #   start = (time_offset + call_count) % 4 — stateless rotation
│                             #   Missing-key errors skip provider (don't abort the chain)
│
├── execution/
│   ├── alpaca_client.py      # Alpaca Paper Trading REST wrapper
│   │                         #   submit_market_order()       auto-uses gtc for crypto (/ in sym),
│   │                         #                               day for stocks — Alpaca rejects day on crypto
│   │                         #   get_recent_buy_symbols()    dedup guard (15 min / 90 min)
│   │                         #   cancel_stale_open_orders()  kills stuck GTC crypto orders
│   ├── risk_manager.py       # Stop-loss, take-profit, position sizing, cash reserve
│   ├── market_scanner.py     # Stock discovery: Yahoo screeners (most_actives + day_gainers)
│   │                         # Crypto discovery: CoinGecko top-100, scored by momentum
│   └── telegram_notifier.py  # Trade alerts, risk exits, EOD summary, heartbeat
│
├── dashboard/
│   └── app.py              # Streamlit — 7-tab layout, auto-refreshes every 10s
│                           #   Overview · Positions · Momentum · History · Reports · Prices
│                           #   Explore — on-demand analysis of any symbol (rule-based scoring)
│
├── .github/workflows/
│   └── trading_bot.yml     # GitHub Actions — triggered by cron-job.org every 2 min
│                           #   uses requirements-bot.txt
│
├── requirements.txt        # Dashboard only (Streamlit Cloud) — plotly, streamlit-autorefresh
└── requirements-bot.txt    # Full bot (GitHub Actions) — adds cerebras-cloud-sdk
```

---

## Dashboard

Live at **[trading-bot-test.streamlit.app](https://trading-bot-test.streamlit.app)** — auto-deploys on every push to `main`.

```
┌─ 8 KPI Metrics ──────────────────────────────────────────────────────────────┐
│  Portfolio │ Cash │ Total P&L │ Positions │ Win Rate │ PF │ Weekly │ Mom Used │
├───────────────────────────────────────────────────────────────────────────────┤
│ [📊 Overview] [💼 Positions] [🚀 Momentum] [📜 History] [📋 Reports]         │
│ [📡 Prices]   [🔍 Explore]                                                    │
│                                                                               │
│  Overview   Performance chart + Allocation pie + Unrealized P&L bar          │
│  Positions  Merged table (stocks + crypto) with stop/target distance cols     │
│  Momentum   Budget strip → Live Screener │ Signal Filter │ Momentum Trades    │
│  History    Trade log — filter: All / Stocks / Crypto                         │
│  Reports    Realized P&L · filters: Side / Range / Type (By Day or Flat)      │
│  Prices     Live price tiles (stocks + 16 crypto pairs) + performance stats   │
│  Explore    On-demand full analysis of any stock or crypto symbol (see below) │
└───────────────────────────────────────────────────────────────────────────────┘
```

Run locally:
```bash
streamlit run dashboard/app.py
```

### 🔍 Explore Tab

Enter any stock ticker (`NVDA`, `SMCI`, `AAPL`) or crypto (`ETH/USD`, `DOGE`, `SOL`) and get the same analysis the bot runs before every trade — without placing an order.

```
┌─ Verdict ────────────────────────────────────────────────────────────────────┐
│  📈 BUY   Combined score: 71/100   Tech 74 | Fund 68   NVDA · $875.20        │
├─ Market Context ──────────────────────────────────────────────────────────────┤
│  🌐 Regime: BULL   📊 SPY: +0.54% today   😨 VIX: 17.7 — Calm               │
├─ Chart (left 58%) ──────────────┬─ Signals (right 42%) ──────────────────────┤
│                                  │ 📊 Technical — 74/100                      │
│  Price line + Bollinger Bands    │  ✅ RSI 38.2 — approaching oversold        │
│  SMA 20 + SMA 50 overlaid        │  ✅ MACD histogram +0.48 — bullish         │
│                                  │  🟡 Volume 1.2× avg — above average        │
│  RSI (14) sub-chart below        │  ✅ Golden Cross — long-term uptrend        │
│  overbought/oversold shading     │  🟡 Mid Bollinger Band (52%)               │
│                                  │  ✅ OBV Rising — accumulation               │
│                                  │──────────────────────────────────────────  │
│                                  │ 🏢 Fundamental — 68/100                    │
│                                  │  ✅ Analyst consensus: Strong Buy           │
│                                  │  ✅ Price target $298 (+43% upside)         │
│                                  │  ✅ Revenue growth +85% YoY                 │
│                                  │  🟡 P/E 35.2× — growth premium             │
│                                  │  ✅ Put/Call 0.65 — bullish positioning     │
├─ Insider Activity ────────────────────────────────────────────────────────────┤
│  🔴 Sale at $875 — STEVENS M (Officer) 100,000 shares on 2026-06-04          │
├─ ▶ Recent News (8 headlines) ─────────────────────────────────────────────────┤
│  Click to expand                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

**How scoring works:**

| Signal | Bullish → score | Bearish → score |
|---|---|---|
| RSI < 30 (oversold) | +20 pts | RSI > 70 (overbought): 0 pts |
| MACD histogram > 0 | +20 pts | MACD histogram ≤ 0: 0 pts |
| Volume ≥ 1.8× avg | +15 pts | Volume < 0.7×: +2 pts |
| Golden Cross | +20 pts | Death Cross: 0 pts |
| Near lower Bollinger Band | +15 pts | Near upper: +3 pts |
| OBV Rising | +10 pts | OBV Falling: 0 pts |
| Analyst Strong Buy (stocks) | +25 pts | Sell/Underperform: +2 pts |
| Revenue growth > 20% (stocks) | +15 pts | Revenue declining: 0 pts |
| 52W range < 20% from low (crypto) | +30 pts | Near 52W high: +2 pts |
| Sentiment BULLISH | +20 pts | BEARISH: 0 pts |

Combined score ≥ 68 → **BUY** · 48–67 → **HOLD / WATCH** · < 48 → **AVOID / SELL**

Technical signals are computed from 1-year OHLCV price data (RSI, MACD, Bollinger %B, volume ratio, OBV trend, golden/death cross). Fundamental data from yfinance (stocks) and CoinGecko (crypto). Scores are rule-based heuristics — not LLM predictions, not financial advice.

---

## Telegram Alerts

**Trade Alert — BUY (stock):**
```
🟢 BUY NVDA  ·  82% conf
────────────────────────
📈 12 shares @ $875.20  ·  cost $10,502
💵 Cash: $52,800

📊 RSI 28.4 OVERSOLD · MACD ▲ · Vol 2.3×avg HIGH
🏢 Strong Buy · target $950 (+8%) · Rev +122% · Sentiment BULLISH

💬 RSI oversold + golden cross + analyst upgrades outweigh macro headwinds
```

**Trade Alert — SELL (crypto, showing P&L):**
```
🔴 SELL DOGE/USD  ·  78% conf
────────────────────────
🪙 32,619 units @ $0.0868  ·  value $2,832
📉 Loss  –$180  (–6.2%)  [entry $0.0924]
💵 Cash: $72,375

🔗 Sentiment NEUTRAL · 38% into 52W range
💬 Stop-loss triggered — momentum exhausted below entry
```

**Risk Exit (stop-loss or take-profit):**
```
⚠️ RISK EXIT — AVAX/USD
🛑 STOP LOSS -12.3%  ·  0.54 units
📉 –$432 (–12.3%)  [$18.50 → $16.22]
```

**Hourly Heartbeat** (no trades that hour):
```
🤖 BOT HEARTBEAT  (no trades this hour)
────────────────────────────────
🔴 Stock market CLOSED  ·  🔗 Crypto 24/7
Portfolio:  $99,786.00
Cash:       $17,232.00
Total P&L:  📉 $-214.00

Open Positions:
  📉 NVDA: 12 shares (-1.2%)
  📈 ETH/USD: 0.45 units (+3.1%)
```

**End-of-Day Summary:**
```
📅 END OF DAY SUMMARY
────────────────────────────────
Trades Today:  3 buys | 1 sell
Day P&L:       📈 +$234.50
Total P&L:     📈 +$234.50
Portfolio:     $100,234.50
Cash:          $68,120.30
```

---

## Hosting

### GitHub Actions + cron-job.org (current — free)

[cron-job.org](https://cron-job.org) fires a `workflow_dispatch` POST every 2 minutes. GitHub Actions runs the cycle and exits.

The workflow sets `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` to run all actions on Node.js 24 (required after June 2026 — GitHub dropped Node.js 20).

**cron-job.org setup:**
- URL: `https://api.github.com/repos/{owner}/{repo}/actions/workflows/trading_bot.yml/dispatches`
- Method: `POST`
- Headers: `Authorization: Bearer {github-pat}` · `Accept: application/vnd.github+json`
- Body: `{"ref":"main"}`

**LLM quota at 2-minute intervals (round-robin, ~25% each):**

| Provider | Free Limit | Est. Daily Usage (25%) | Headroom |
|---|---|---|---|
| Cerebras | ~60 req/min · token-based daily | ~965 calls / ~480K tokens | ✅ well within |
| Groq | 14,400 req/day | ~965 calls | ✅ 15× headroom |
| Gemini | 1,500 req/day | ~965 calls | ✅ 535 calls to spare |
| OpenRouter | generous free tier | ~965 calls | ✅ fine |

### AWS EC2 (alternative)
```bash
python3 main.py --daemon   # runs every 60 sec during market hours
```

---

## Configuration (`config.py`)

```python
# Core watchlists
WATCHLIST        = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
CRYPTO_WATCHLIST = ["ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD"]  # BTC excluded — never fills

# Position limits
MAX_POSITIONS        = 5
MAX_CRYPTO_POSITIONS = 3
CRYPTO_PORTFOLIO_CAP = 0.35             # max 35% of portfolio in crypto

# Core exits
STOP_LOSS_PCT          = 0.07           # −7%  stock stop-loss
TAKE_PROFIT_PCT        = 0.15           # +15% stock take-profit
CRYPTO_STOP_LOSS_PCT   = 0.12           # −12% crypto stop-loss
CRYPTO_TAKE_PROFIT_PCT = 0.25           # +25% crypto take-profit

# Capital guardrails
MIN_CASH_RESERVE_PCT      = 0.20        # always keep 20% locked
RESERVE_DEPLOY_CONFIDENCE = 88          # unlock reserve at ≥88% confidence
RESERVE_MAX_DEPLOY_PCT    = 0.50        # max 50% of reserve per trade

# Momentum tier
MOMENTUM_TOTAL_BUDGET_PCT = 0.10        # 10% shared budget
MOMENTUM_MIN_CONFIDENCE   = 80          # higher bar than core 65%
MOMENTUM_VOLUME_RATIO_MIN = 1.8         # 1.8× avg volume required
MOMENTUM_STOCK_STOP_PCT   = 0.04        # −4% (tighter than core)
MOMENTUM_STOCK_TAKE_PCT   = 0.08        # +8%
MOMENTUM_CRYPTO_STOP_PCT  = 0.06
MOMENTUM_CRYPTO_TAKE_PCT  = 0.12

# LLM — 4-provider round-robin + automatic fallback on 429
MIN_CONFIDENCE   = 65
CEREBRAS_MODEL   = "gpt-oss-120b"                          # primary ~2s
GROQ_MODEL       = "llama-3.3-70b-versatile"
GEMINI_MODEL     = "gemini-2.0-flash"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
```

### Tuning Guide

| Goal | Setting to change |
|---|---|
| Bot trades too rarely | Lower `MIN_CONFIDENCE` to 60 |
| Bot trades too aggressively | Raise `MIN_CONFIDENCE` to 75 |
| Stop-outs too frequent | Raise `STOP_LOSS_PCT` |
| Lock in gains faster | Lower `TAKE_PROFIT_PCT` |
| More momentum trades | Lower `MOMENTUM_MIN_CONFIDENCE` to 75 |
| Less crypto exposure | Lower `CRYPTO_PORTFOLIO_CAP` to 0.20 |
| More dry powder | Raise `MIN_CASH_RESERVE_PCT` to 0.30 |

---

## Required Credentials

```bash
# Alpaca Paper Trading — app.alpaca.markets
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

# LLM failover chain
CEREBRAS_API_KEY=...      # cloud.cerebras.ai   — fastest, 120B model, free
GROQ_API_KEY=...          # console.groq.com    — 14,400 req/day free
GOOGLE_API_KEY=...        # aistudio.google.com — 1,500 req/day free
OPENROUTER_API_KEY=...    # openrouter.ai       — free tier, last resort

# FinBERT sentiment (stock news) — huggingface.co/settings/tokens
HUGGINGFACE_API_TOKEN=... # ProsusAI/finbert via Inference API; falls back to keyword scoring if unset

# Telegram
TELEGRAM_BOT_TOKEN=...    # from @BotFather
TELEGRAM_CHAT_ID=...      # from api.telegram.org/bot{token}/getUpdates
```

Add all as **GitHub Repository Secrets** (Settings → Secrets → Actions). Never committed to the repo.

---

## Dependencies

| File | Used by | Contents |
|---|---|---|
| `requirements.txt` | Streamlit Cloud (dashboard) | yfinance · ta · google-genai · requests · pandas · numpy · plotly · streamlit-autorefresh |
| `requirements-bot.txt` | GitHub Actions (trading bot) | all of the above + cerebras-cloud-sdk |

```bash
pip install -r requirements-bot.txt   # for running the bot locally
```

---

## Bug Fixes Log

| Fix | Symptom | Root Cause | Commit |
|---|---|---|---|
| Crypto SELL `time_in_force` | `❌ BOT ERROR: Order SELL AVAX/USD — invalid crypto time_in_force` on every crypto stop-loss and LLM SELL | `submit_market_order` hardcoded `"day"` which Alpaca rejects for crypto (only accepts `gtc`/`ioc`/`fok`). All crypto exits were silently failing. | `fc935a4` |
| LLM failover missing-key skip | All crypto decisions returned `HOLD 0%` when `CEREBRAS_API_KEY` was not in GitHub Secrets | `RuntimeError("CEREBRAS_API_KEY not set")` was re-raised immediately instead of falling through to Groq. Fixed by adding `_is_missing_key_error()` check. | `7d25b49` |
| Crypto sentiment always `N/A` | `Sentiment=N/A` in every crypto LLM signal log — LLM had no sentiment signal for crypto | yfinance does not return news headlines for crypto tickers (`ETH-USD` etc.). Fixed by falling back to CoinGecko community sentiment votes. | `fc935a4` |
| Flip-flop churn trades | AVAX/USD bought then sold twice in one hour, both at ~$25 loss each | LLM alternated BUY/SELL on identical signals (RSI oversold vs MACD bearish). Fixed with 30-min sell cooldown (`get_recent_sell_symbols`) + 85% confidence bar for crypto BUYs in BEAR regime. | `8d19f35` |
| Alpaca API timeout killed cycle | No Telegram messages for hours; `Read timed out (read timeout=15)` error | `_get()` had a 15s timeout with zero retries. One slow Alpaca response crashed the full cycle. Fixed: 3 retries with 5s wait and 25s timeout each. | `1ee8cf3` |
| Hourly heartbeat never fired | `_send_heartbeat()` existed but Telegram received no hourly status messages | `run_once()` never called `_send_heartbeat()`. Fixed by adding `if _is_top_of_hour(): _send_heartbeat(market_open)` to `run_once()`. | `1ee8cf3` |
| LLM quota exhaustion (all 4 providers) | All 4 providers returned 429 simultaneously mid-day; SOL/DOGE/AVAX defaulted to `HOLD 0%` | Waterfall fallback sent ~99% of calls to Cerebras. When its daily quota died, the other 3 were hit in rapid burst and also rate-limited. Fixed with round-robin rotation so each provider handles ~25% of calls (~965/day, well within free tier limits). | `09b8035` |

---

## Inspiration & References

This bot was designed by studying the architectures and research behind several leading open-source trading AI projects. Key learnings from each:

### Research Papers & Repositories

| Project | What We Borrowed |
|---|---|
| [**TradingAgents**](https://github.com/tauricresearch/tradingagents) — Tauric Research | Multi-agent bull/bear debate before any decision. Forced the LLM to argue both sides with specific data points before committing. Directly inspired our `SYSTEM_PROMPT` structure. |
| [**FinceptTerminal**](https://github.com/Fincept-Corporation/FinceptTerminal) — Fincept Corp | Evaluated for fundamental + alternative data connectivity. Decided against integrating (C++20 desktop app, not pip-installable, $10,200/yr commercial licence) but the data source ideas influenced what fields we pull from yfinance. |

### Data Sources

| Source | Used For |
|---|---|
| [Yahoo Finance (yfinance)](https://github.com/ranaroussi/yfinance) | Stock + crypto prices, fundamentals (P/E, EPS, growth, analyst ratings), news headlines, insider transactions, technical history |
| [Yahoo Finance Screeners](https://finance.yahoo.com/screener) | Momentum stock discovery — `most_actives` and `day_gainers` screeners surface what's actually moving each cycle |
| [CoinGecko API](https://www.coingecko.com/en/api) | Momentum crypto discovery — top 100 coins by 24h volume, scored by price change × volume/market-cap ratio. Also provides community sentiment votes (`sentiment_votes_up_percentage`) used as LLM signal for all 16 crypto pairs when yfinance returns no news. |
| [Alpaca Paper Trading API](https://alpaca.markets) | Order execution, position tracking, account state, portfolio history |
| [SPY via yfinance](https://finance.yahoo.com/quote/SPY) | Market regime detection — BULL when SPY > SMA20, BEAR when below |

### LLM Providers

| Provider | Model | Role |
|---|---|---|
| [Cerebras](https://cloud.cerebras.ai) | gpt-oss-120b | Primary — wafer-scale chips, fastest inference (~2s), 120B reasoning model |
| [Groq](https://console.groq.com) | llama-3.3-70b-versatile | Secondary — dedicated LPU silicon, very fast |
| [Google Gemini](https://aistudio.google.com) | gemini-2.0-flash | Tertiary — reliable fallback |
| [OpenRouter](https://openrouter.ai) | llama-3.3-70b:free | Last resort — routes to 100+ models |

### Libraries

| Library | Used For |
|---|---|
| [ta](https://github.com/bukosabino/ta) | Technical indicators (RSI, MACD, Bollinger Bands, SMA, OBV) |
| [cerebras-cloud-sdk](https://github.com/Cerebras/cerebras-cloud-python) | Official Cerebras Python SDK |
| [streamlit](https://streamlit.io) | Live trading dashboard |
| [plotly](https://plotly.com/python) | Interactive charts in dashboard |
