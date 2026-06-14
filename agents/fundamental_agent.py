import os
import datetime
import requests
from dataclasses import dataclass, field
from typing import Optional
import yfinance as yf


# FinBERT via HuggingFace Inference API — free, no GPU needed
_HF_FINBERT_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"

# CoinGecko ID for each Alpaca crypto symbol — used for community sentiment fallback
_COINGECKO_ID_MAP = {
    "BTC/USD":  "bitcoin",
    "ETH/USD":  "ethereum",
    "SOL/USD":  "solana",
    "DOGE/USD": "dogecoin",
    "AVAX/USD": "avalanche-2",
    "LTC/USD":  "litecoin",
    "BCH/USD":  "bitcoin-cash",
    "LINK/USD": "chainlink",
    "UNI/USD":  "uniswap",
    "AAVE/USD": "aave",
    "GRT/USD":  "the-graph",
    "MKR/USD":  "maker",
    "XLM/USD":  "stellar",
    "XTZ/USD":  "tezos",
    "BAT/USD":  "basic-attention-token",
    "SHIB/USD": "shiba-inu",
}

_BULLISH_TERMS = {
    "upgrade", "beat", "beats", "exceeds", "record", "strong", "growth",
    "surge", "bullish", "profit", "gains", "soars", "raised", "outperform",
    "positive", "buy", "overweight", "above expectations", "revenue growth",
}
_BEARISH_TERMS = {
    "downgrade", "miss", "misses", "below", "weak", "decline", "loss",
    "cut", "layoffs", "lawsuit", "fraud", "negative", "falls", "drops",
    "lowered", "concern", "risk", "warning", "probe", "investigation", "sell",
}


@dataclass
class FundamentalReport:
    symbol: str
    asset_type: str = "stock"       # "stock" or "crypto"
    fetch_error: Optional[str] = None
    current_price: Optional[float] = None
    # Valuation
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    # Analyst signals
    analyst_recommendation: Optional[str] = None
    analyst_target_price: Optional[float] = None
    recent_upgrades: list = field(default_factory=list)
    recent_earnings_surprises: list = field(default_factory=list)
    # News & insider
    recent_news: list = field(default_factory=list)
    insider_activity: list = field(default_factory=list)
    # Sentiment & options signals
    news_sentiment_score: Optional[float] = None   # -1.0 (bearish) to +1.0 (bullish)
    news_sentiment_label: Optional[str] = None     # BULLISH / BEARISH / NEUTRAL
    earnings_in_days: Optional[int] = None         # days until next earnings (None if >14)
    put_call_ratio: Optional[float] = None         # options P/C ratio (stocks only)
    # Congressional trades (stocks only — Quiver Quantitative)
    congressional_trades: list = field(default_factory=list)
    # Crypto fields
    market_cap: Optional[float] = None
    circulating_supply: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    volume_24h: Optional[float] = None

    def to_prompt_text(self) -> str:
        if self.fetch_error:
            return f"DATA for {self.symbol}: Unavailable ({self.fetch_error})"
        if self.asset_type == "crypto":
            return self._crypto_prompt()
        return self._stock_prompt()

    def _stock_prompt(self) -> str:
        lines = [f"FUNDAMENTAL ANALYSIS — {self.symbol}"]
        lines.append(f"  Current Price:        ${self.current_price:.2f}" if self.current_price else "  Current Price:        N/A")
        lines.append(f"  P/E Ratio:            {self.pe_ratio:.1f}x" if self.pe_ratio else "  P/E Ratio:            N/A")
        lines.append(f"  EPS (TTM):            ${self.eps:.2f}" if self.eps else "  EPS:                  N/A")
        lines.append(f"  Revenue Growth (YoY): {self.revenue_growth*100:.1f}%" if self.revenue_growth else "  Revenue Growth:       N/A")
        lines.append(f"  Earnings Growth:      {self.earnings_growth*100:.1f}%" if self.earnings_growth else "  Earnings Growth:      N/A")
        lines.append(f"  Debt/Equity:          {self.debt_to_equity:.2f}" if self.debt_to_equity else "  Debt/Equity:          N/A")
        lines.append(f"  ROE:                  {self.roe*100:.1f}%" if self.roe else "  ROE:                  N/A")
        lines.append(f"  Analyst Rating:       {self.analyst_recommendation}" if self.analyst_recommendation else "  Analyst Rating:       N/A")
        lines.append(f"  Analyst Target:       ${self.analyst_target_price:.2f}" if self.analyst_target_price else "  Analyst Target:       N/A")
        if self.recent_upgrades:
            lines.append(f"  Recent Upgrades:      {', '.join(self.recent_upgrades[:3])}")
        if self.recent_earnings_surprises:
            lines.append(f"  Earnings Surprises:   {', '.join(self.recent_earnings_surprises[:4])}")
        if self.news_sentiment_score is not None:
            lines.append(f"  News Sentiment:       {self.news_sentiment_label} (score {self.news_sentiment_score:+.2f})")
        if self.put_call_ratio is not None:
            pcr_label = "BEARISH" if self.put_call_ratio > 1.3 else ("BULLISH" if self.put_call_ratio < 0.7 else "NEUTRAL")
            lines.append(f"  Put/Call Ratio:       {self.put_call_ratio:.2f} [{pcr_label}]")
        if self.earnings_in_days is not None:
            lines.append(f"  *** EARNINGS IN {self.earnings_in_days} DAYS — elevated volatility, extra caution on BUY ***")
        if self.recent_news:
            lines.append("  Recent News:")
            for headline in self.recent_news[:5]:
                lines.append(f"    • {headline}")
        if self.insider_activity:
            lines.append("  Insider Activity:")
            for activity in self.insider_activity[:3]:
                lines.append(f"    • {activity}")
        if self.congressional_trades:
            buys  = sum(1 for t in self.congressional_trades if "purchase" in str(t.get("Transaction", "")).lower())
            sells = sum(1 for t in self.congressional_trades if "sale"     in str(t.get("Transaction", "")).lower())
            lines.append(f"  Congressional Trades (last 30 days): {buys} buy(s) | {sells} sell(s)")
            for t in self.congressional_trades[:4]:
                action  = "BUY"  if "purchase" in str(t.get("Transaction", "")).lower() else "SELL"
                name    = t.get("Representative", "Unknown")
                party   = t.get("Party", "?")
                chamber = t.get("Chamber", "")
                amount  = t.get("Amount") or t.get("Range") or "undisclosed"
                date    = str(t.get("Date", ""))[:10]
                lines.append(f"    • {action} — {name} ({party}, {chamber}) — {amount} on {date}")
        return "\n".join(lines)

    def _crypto_prompt(self) -> str:
        lines = [f"CRYPTO MARKET DATA — {self.symbol}"]
        lines.append(f"  Current Price:      ${self.current_price:,.4f}" if self.current_price else "  Current Price:      N/A")
        if self.market_cap:
            lines.append(f"  Market Cap:         ${self.market_cap/1e9:.2f}B")
        if self.circulating_supply:
            lines.append(f"  Circulating Supply: {self.circulating_supply:,.0f}")
        if self.week52_high and self.week52_low and self.current_price:
            pct_from_high = (self.current_price - self.week52_high) / self.week52_high * 100
            pct_from_low  = (self.current_price - self.week52_low)  / self.week52_low  * 100
            lines.append(f"  52-Week High:       ${self.week52_high:,.4f} ({pct_from_high:+.1f}% from now)")
            lines.append(f"  52-Week Low:        ${self.week52_low:,.4f} ({pct_from_low:+.1f}% from now)")
        if self.volume_24h:
            lines.append(f"  24h Volume:         ${self.volume_24h/1e6:.1f}M")
        if self.news_sentiment_score is not None:
            lines.append(f"  News Sentiment:     {self.news_sentiment_label} (score {self.news_sentiment_score:+.2f})")
        if self.recent_news:
            lines.append("  Recent News:")
            for headline in self.recent_news[:3]:
                lines.append(f"    • {headline}")
        lines.append("  (No P/E or EPS — use technical analysis for primary signal)")
        return "\n".join(lines)


class FundamentalAgent:
    def analyze(self, symbol: str, yf_symbol: str = None) -> FundamentalReport:
        """Analyze a symbol. Pass yf_symbol if Alpaca symbol differs from yfinance symbol."""
        lookup = yf_symbol or symbol
        is_crypto = yf_symbol is not None and "-USD" in yf_symbol
        if is_crypto:
            return self._analyze_crypto(symbol, lookup)
        return self._analyze_stock(symbol, lookup)

    # ── Signal helpers ──────────────────────────────────────────────────────────

    def _score_news_sentiment(self, headlines: list) -> tuple:
        """Score headlines using FinBERT (HuggingFace API) with keyword fallback.

        Primary: ProsusAI/finbert via HF Inference API — needs HUGGINGFACE_API_TOKEN.
        Fallback: lightweight keyword scoring (no API key required).
        Returns (score -1.0 to +1.0, label).
        """
        if not headlines:
            return None, None

        token = os.environ.get("HUGGINGFACE_API_TOKEN")
        if token:
            try:
                r = requests.post(
                    _HF_FINBERT_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json={"inputs": [h[:512] for h in headlines[:5]]},
                    timeout=20,
                )
                if r.ok:
                    results = r.json()
                    # FinBERT returns [[{label, score}, ...], ...] — one list per input
                    if isinstance(results, list) and results:
                        # Handle both nested [[...]] and flat [{...}] responses
                        items_list = results if isinstance(results[0], list) else [results]
                        total, count = 0.0, 0
                        for item in items_list:
                            if not isinstance(item, list):
                                continue
                            top = max(item, key=lambda x: x.get("score", 0))
                            lbl = top.get("label", "neutral").lower()
                            sc  = top.get("score", 0.5)
                            total += sc if lbl == "positive" else (-sc if lbl == "negative" else 0.0)
                            count += 1
                        if count:
                            avg = round(total / count, 3)
                            label = "BULLISH" if avg > 0.2 else ("BEARISH" if avg < -0.2 else "NEUTRAL")
                            return avg, label
            except Exception:
                pass  # fall through to keyword scoring

        # Keyword fallback — no API key required
        text = " ".join(headlines).lower()
        bull = sum(1 for w in _BULLISH_TERMS if w in text)
        bear = sum(1 for w in _BEARISH_TERMS if w in text)
        if bull + bear == 0:
            return 0.0, "NEUTRAL"
        score = round((bull - bear) / (bull + bear), 3)
        label = "BULLISH" if score > 0.1 else ("BEARISH" if score < -0.1 else "NEUTRAL")
        return score, label

    def _get_earnings_warning(self, ticker) -> Optional[int]:
        """Return days until next earnings if within 14 days, else None."""
        try:
            cal = ticker.calendar
            if cal is None:
                return None
            if hasattr(cal, "to_dict"):
                cal = cal.to_dict()
            if not isinstance(cal, dict):
                return None
            date_val = cal.get("Earnings Date")
            if date_val is None:
                return None
            if isinstance(date_val, (list, tuple)):
                date_val = date_val[0]
            if hasattr(date_val, "date"):
                date_val = date_val.date()
            elif isinstance(date_val, str):
                date_val = datetime.datetime.strptime(date_val[:10], "%Y-%m-%d").date()
            days = (date_val - datetime.date.today()).days
            return days if 0 <= days <= 14 else None
        except Exception:
            return None

    def _fetch_crypto_sentiment_coingecko(self, alpaca_symbol: str) -> tuple:
        """Community sentiment from CoinGecko as proxy for news sentiment.
        Uses sentiment_votes_up/down_percentage from the free /coins/{id} endpoint.
        Returns (score -1.0 to +1.0, label) or (None, None) on any failure."""
        cg_id = _COINGECKO_ID_MAP.get(alpaca_symbol)
        if not cg_id:
            return None, None
        try:
            r = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{cg_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "true",
                    "developer_data": "false",
                    "sparkline": "false",
                },
                headers={"User-Agent": "trading-bot/1.0"},
                timeout=10,
            )
            if not r.ok:
                return None, None
            cd = r.json().get("community_data") or {}
            up_pct = cd.get("sentiment_votes_up_percentage")
            if up_pct is None:
                return None, None
            down_pct = cd.get("sentiment_votes_down_percentage") or (100.0 - up_pct)
            score = round((up_pct - down_pct) / 100.0, 3)
            label = "BULLISH" if up_pct > 60 else ("BEARISH" if up_pct < 40 else "NEUTRAL")
            return score, label
        except Exception:
            return None, None

    def _get_put_call_ratio(self, ticker) -> Optional[float]:
        """Compute put/call volume ratio from nearest expiry options chain.
        >1.3 = bearish hedging, <0.7 = bullish positioning."""
        try:
            exps = ticker.options
            if not exps:
                return None
            chain    = ticker.option_chain(exps[0])
            put_vol  = float(chain.puts["volume"].fillna(0).sum())
            call_vol = float(chain.calls["volume"].fillna(0).sum())
            if call_vol <= 0:
                return None
            return round(put_vol / call_vol, 2)
        except Exception:
            return None

    def _get_congressional_trades(self, symbol: str, days: int = 30) -> list:
        """Fetch congressional trades from House + Senate Stock Watcher (100% free, no API key).
        Both sources pull directly from official STOCK Act disclosures filed with Congress.
        Downloads the full JSON, filters in memory for the target symbol and date window.
        Returns empty list silently on any network failure."""
        _HOUSE_URL  = "https://house-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/data/all_transactions.json"
        _SENATE_URL = "https://senate-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/aggregate/all_transactions.json"

        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        trades = []

        # House of Representatives
        try:
            r = requests.get(_HOUSE_URL, timeout=15)
            if r.ok:
                for t in r.json():
                    raw_ticker = str(t.get("ticker") or "").strip().upper().rstrip("_")
                    if raw_ticker != symbol:
                        continue
                    date = str(t.get("transaction_date") or t.get("disclosure_date") or "")[:10]
                    if date < cutoff:
                        continue
                    txn = str(t.get("type", "")).lower()
                    trades.append({
                        "Date":           date,
                        "Representative": t.get("representative", "Unknown"),
                        "Transaction":    "Purchase" if "purchase" in txn else "Sale",
                        "Amount":         t.get("amount", "undisclosed"),
                        "Party":          t.get("party", ""),
                        "Chamber":        "House",
                    })
        except Exception:
            pass

        # Senate
        try:
            r = requests.get(_SENATE_URL, timeout=15)
            if r.ok:
                for t in r.json():
                    raw_ticker = str(t.get("ticker") or "").strip().upper().rstrip("_")
                    if raw_ticker != symbol:
                        continue
                    date = str(t.get("transaction_date") or t.get("disclosure_date") or "")[:10]
                    if date < cutoff:
                        continue
                    txn  = str(t.get("type", "")).lower()
                    name = t.get("senator") or (
                        f"{t.get('first_name','')} {t.get('last_name','')}".strip()
                    ) or "Unknown"
                    trades.append({
                        "Date":           date,
                        "Representative": name,
                        "Transaction":    "Purchase" if "purchase" in txn else "Sale",
                        "Amount":         t.get("amount", "undisclosed"),
                        "Party":          t.get("party", ""),
                        "Chamber":        "Senate",
                    })
        except Exception:
            pass

        trades.sort(key=lambda t: t["Date"], reverse=True)
        return trades

    # ── Data fetchers ───────────────────────────────────────────────────────────

    def _fetch_news(self, ticker) -> list:
        """Return up to 5 recent headline strings."""
        headlines = []
        try:
            raw = None
            if hasattr(ticker, "get_news"):
                try:
                    raw = ticker.get_news()
                except Exception:
                    pass
            if raw is None:
                raw = ticker.news
            for item in (raw or [])[:5]:
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or item.get("headline", "")
                pub   = item.get("publisher") or item.get("source", "")
                if title:
                    entry = title[:120]
                    if pub:
                        entry += f" [{pub}]"
                    headlines.append(entry)
        except Exception:
            pass
        return headlines

    def _fetch_insider_activity(self, ticker) -> list:
        """Return up to 3 recent insider transaction strings."""
        lines = []
        try:
            it = ticker.insider_transactions
            if it is None or it.empty:
                return lines
            for _, row in it.head(4).iterrows():
                try:
                    txn    = str(row.get("Transaction") or row.get("Text") or "").strip()[:30]
                    name   = str(row.get("Insider", "")).strip()
                    pos    = str(row.get("Position", "")).strip()[:25]
                    shares = int(row.get("Shares") or 0)
                    val    = int(row.get("Value") or 0)
                    date   = str(row.get("Start Date") or "")[:10]
                    if txn and shares:
                        lines.append(f"{txn}: {name} ({pos}) {shares:,} shares ${val:,} on {date}")
                except Exception:
                    continue
        except Exception:
            pass
        return lines

    # ── Analysis ────────────────────────────────────────────────────────────────

    def _analyze_stock(self, symbol: str, yf_symbol: str) -> FundamentalReport:
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info or {}

            current_price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )

            upgrades = []
            try:
                ud = ticker.upgrades_downgrades
                if ud is not None and not ud.empty:
                    for _, row in ud.head(5).iterrows():
                        firm   = row.get("Firm", "")
                        action = row.get("Action", row.get("ToGrade", ""))
                        upgrades.append(f"{firm}:{action}")
            except Exception:
                pass

            earnings_surprises = []
            try:
                eh = ticker.earnings_history
                if eh is not None and not eh.empty:
                    for _, row in eh.tail(4).iterrows():
                        surprise = row.get("surprisePercent", None)
                        if surprise is not None:
                            earnings_surprises.append(f"{surprise*100:+.1f}%")
            except Exception:
                pass

            news = self._fetch_news(ticker)
            sentiment_score, sentiment_label = self._score_news_sentiment(news)
            congressional = self._get_congressional_trades(symbol)

            return FundamentalReport(
                symbol=symbol,
                asset_type="stock",
                pe_ratio=info.get("trailingPE") or info.get("forwardPE"),
                eps=info.get("trailingEps"),
                revenue_growth=info.get("revenueGrowth"),
                earnings_growth=info.get("earningsGrowth"),
                debt_to_equity=info.get("debtToEquity"),
                roe=info.get("returnOnEquity"),
                analyst_recommendation=info.get("recommendationKey"),
                analyst_target_price=info.get("targetMeanPrice"),
                current_price=current_price,
                recent_upgrades=upgrades,
                recent_earnings_surprises=earnings_surprises,
                recent_news=news,
                insider_activity=self._fetch_insider_activity(ticker),
                news_sentiment_score=sentiment_score,
                news_sentiment_label=sentiment_label,
                earnings_in_days=self._get_earnings_warning(ticker),
                put_call_ratio=self._get_put_call_ratio(ticker),
                congressional_trades=congressional,
            )
        except Exception as e:
            return FundamentalReport(symbol=symbol, fetch_error=str(e))

    def _analyze_crypto(self, symbol: str, yf_symbol: str) -> FundamentalReport:
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info or {}

            current_price = (
                info.get("regularMarketPrice")
                or info.get("previousClose")
                or info.get("open")
            )

            news = self._fetch_news(ticker)
            sentiment_score, sentiment_label = self._score_news_sentiment(news)

            # yfinance rarely returns news for crypto tickers — fall back to
            # CoinGecko community sentiment votes (free, no API key required)
            if sentiment_score is None:
                sentiment_score, sentiment_label = self._fetch_crypto_sentiment_coingecko(symbol)

            return FundamentalReport(
                symbol=symbol,
                asset_type="crypto",
                current_price=current_price,
                market_cap=info.get("marketCap"),
                circulating_supply=info.get("circulatingSupply"),
                week52_high=info.get("fiftyTwoWeekHigh"),
                week52_low=info.get("fiftyTwoWeekLow"),
                volume_24h=info.get("volume24Hr") or info.get("regularMarketVolume"),
                recent_news=news,
                news_sentiment_score=sentiment_score,
                news_sentiment_label=sentiment_label,
            )
        except Exception as e:
            return FundamentalReport(symbol=symbol, asset_type="crypto", fetch_error=str(e))
