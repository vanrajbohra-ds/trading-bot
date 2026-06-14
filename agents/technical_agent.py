from dataclasses import dataclass
from typing import Optional
import yfinance as yf
import pandas as pd

try:
    from ta.momentum import RSIIndicator
    from ta.trend import MACD, SMAIndicator
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.volume import OnBalanceVolumeIndicator
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False


@dataclass
class TechnicalReport:
    symbol: str
    fetch_error: Optional[str] = None
    current_price: Optional[float] = None
    rsi: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_pband: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    golden_cross: Optional[bool] = None
    obv_trend: Optional[str] = None
    volume_ratio: Optional[float] = None
    atr: Optional[float] = None          # Average True Range (14-day) — used for dynamic stop sizing

    def to_prompt_text(self) -> str:
        if self.fetch_error:
            return f"TECHNICAL DATA for {self.symbol}: Unavailable ({self.fetch_error})"
        lines = [f"TECHNICAL ANALYSIS — {self.symbol}"]
        lines.append(f"  Current Price:   ${self.current_price:.2f}" if self.current_price else "  Current Price:   N/A")
        if self.rsi is not None:
            signal = "OVERSOLD" if self.rsi < 30 else ("OVERBOUGHT" if self.rsi > 70 else "NEUTRAL")
            lines.append(f"  RSI(14):         {self.rsi:.1f} [{signal}]")
        if self.macd_line is not None:
            cross = "BULLISH" if self.macd_hist and self.macd_hist > 0 else "BEARISH"
            lines.append(f"  MACD:            line={self.macd_line:.4f} signal={self.macd_signal:.4f} hist={self.macd_hist:.4f} [{cross}]")
        if self.bb_pband is not None:
            pos = "NEAR_UPPER" if self.bb_pband > 0.8 else ("NEAR_LOWER" if self.bb_pband < 0.2 else "MID_BAND")
            lines.append(f"  Bollinger Bands: pband={self.bb_pband:.2f} [{pos}] upper={self.bb_upper:.2f} lower={self.bb_lower:.2f}")
        if self.sma50 is not None and self.sma200 is not None:
            cross_type = "GOLDEN CROSS" if self.golden_cross else "DEATH CROSS"
            lines.append(f"  SMA50={self.sma50:.2f}  SMA200={self.sma200:.2f}  [{cross_type}]")
        if self.obv_trend:
            lines.append(f"  OBV Trend:       {self.obv_trend}")
        if self.volume_ratio is not None:
            vol_signal = "HIGH" if self.volume_ratio > 1.5 else ("LOW" if self.volume_ratio < 0.7 else "NORMAL")
            lines.append(f"  Volume Ratio:    {self.volume_ratio:.2f}x 20d avg [{vol_signal}]")
        return "\n".join(lines)


class TechnicalAgent:
    def analyze(self, symbol: str, period: str = "6mo") -> TechnicalReport:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty or len(df) < 50:
                return TechnicalReport(symbol=symbol, fetch_error="Insufficient price history")

            close = df["Close"]
            volume = df["Volume"]
            current_price = float(close.iloc[-1])

            if not TA_AVAILABLE:
                return TechnicalReport(symbol=symbol, current_price=current_price,
                                       fetch_error="ta library not installed")

            rsi_ind = RSIIndicator(close=close, window=14)
            rsi = float(rsi_ind.rsi().iloc[-1])

            macd_ind = MACD(close=close)
            macd_line = float(macd_ind.macd().iloc[-1])
            macd_signal = float(macd_ind.macd_signal().iloc[-1])
            macd_hist = float(macd_ind.macd_diff().iloc[-1])

            bb_ind = BollingerBands(close=close, window=20)
            bb_pband = float(bb_ind.bollinger_pband().iloc[-1])
            bb_upper = float(bb_ind.bollinger_hband().iloc[-1])
            bb_lower = float(bb_ind.bollinger_lband().iloc[-1])

            sma50 = float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
            sma200_series = SMAIndicator(close=close, window=200).sma_indicator()
            sma200 = float(sma200_series.iloc[-1]) if len(close) >= 200 else None
            golden_cross = (sma50 > sma200) if sma200 is not None else None

            obv_series = OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
            obv_diff = obv_series.diff(10).iloc[-1]
            obv_trend = "RISING" if obv_diff > 0 else ("FALLING" if obv_diff < 0 else "FLAT")

            vol_5d = float(volume.tail(5).mean())
            vol_20d = float(volume.tail(20).mean())
            volume_ratio = vol_5d / vol_20d if vol_20d > 0 else None

            try:
                atr = float(
                    AverageTrueRange(
                        high=df["High"], low=df["Low"], close=close, window=14
                    ).average_true_range().iloc[-1]
                )
            except Exception:
                atr = None

            return TechnicalReport(
                symbol=symbol,
                current_price=current_price,
                rsi=rsi,
                macd_line=macd_line,
                macd_signal=macd_signal,
                macd_hist=macd_hist,
                bb_pband=bb_pband,
                bb_upper=bb_upper,
                bb_lower=bb_lower,
                sma50=sma50,
                sma200=sma200,
                golden_cross=golden_cross,
                obv_trend=obv_trend,
                volume_ratio=volume_ratio,
                atr=atr,
            )
        except Exception as e:
            return TechnicalReport(symbol=symbol, fetch_error=str(e))
