from dataclasses import dataclass, field
from typing import Optional
import yfinance as yf


@dataclass
class FundamentalReport:
    symbol: str
    asset_type: str = "stock"       # "stock" or "crypto"
    fetch_error: Optional[str] = None
    current_price: Optional[float] = None
    # Stock fields
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    analyst_recommendation: Optional[str] = None
    analyst_target_price: Optional[float] = None
    recent_upgrades: list = field(default_factory=list)
    recent_earnings_surprises: list = field(default_factory=list)
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

            return FundamentalReport(
                symbol=symbol,
                asset_type="crypto",
                current_price=current_price,
                market_cap=info.get("marketCap"),
                circulating_supply=info.get("circulatingSupply"),
                week52_high=info.get("fiftyTwoWeekHigh"),
                week52_low=info.get("fiftyTwoWeekLow"),
                volume_24h=info.get("volume24Hr") or info.get("regularMarketVolume"),
            )
        except Exception as e:
            return FundamentalReport(symbol=symbol, asset_type="crypto", fetch_error=str(e))
