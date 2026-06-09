import os
import logging
import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id)
        if not self._enabled:
            logger.warning("Telegram not configured — notifications disabled")

    def send(self, text: str):
        if not self._enabled:
            safe = text.encode("ascii", errors="replace").decode("ascii")
            logger.info("[TELEGRAM DISABLED] %s", safe)
            return
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            r = requests.post(url, json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
            if not r.ok:
                logger.warning("Telegram send failed: %s", r.status_code)
        except Exception as e:
            logger.warning("Telegram error: %s", e)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fmt_technical(technical) -> str:
        if technical is None or technical.fetch_error:
            return "  Data unavailable"
        lines = []

        if technical.rsi is not None:
            signal = "OVERSOLD" if technical.rsi < 30 else ("OVERBOUGHT" if technical.rsi > 70 else "neutral")
            lines.append(f"  RSI {technical.rsi:.1f} · <b>{signal}</b>")

        if technical.macd_hist is not None:
            direction = "BULLISH" if technical.macd_hist > 0 else "BEARISH"
            lines.append(f"  MACD · <b>{direction}</b> (hist {technical.macd_hist:+.4f})")

        if technical.bb_pband is not None:
            pos = "NEAR UPPER band" if technical.bb_pband > 0.8 else (
                  "NEAR LOWER band" if technical.bb_pband < 0.2 else "mid-band")
            lines.append(f"  Bollinger · {pos} ({technical.bb_pband:.0%})")

        if technical.golden_cross is not None:
            cross = "GOLDEN CROSS" if technical.golden_cross else "DEATH CROSS"
            lines.append(f"  Trend · <b>{cross}</b> (SMA50={technical.sma50:.2f})")

        if technical.obv_trend:
            lines.append(f"  OBV · {technical.obv_trend}")

        if technical.volume_ratio is not None:
            vol_label = "HIGH" if technical.volume_ratio > 1.5 else (
                        "LOW"  if technical.volume_ratio < 0.7 else "normal")
            lines.append(f"  Volume · {technical.volume_ratio:.1f}x avg [{vol_label}]")

        return "\n".join(lines) if lines else "  No indicator data"

    @staticmethod
    def _fmt_fundamental(fundamental) -> str:
        if fundamental is None or fundamental.fetch_error:
            return "  Data unavailable"

        if fundamental.asset_type == "crypto":
            lines = []
            if fundamental.market_cap:
                cap = fundamental.market_cap
                cap_str = f"${cap/1e12:.2f}T" if cap >= 1e12 else f"${cap/1e9:.1f}B"
                lines.append(f"  Market Cap · {cap_str}")
            if fundamental.week52_high and fundamental.week52_low and fundamental.current_price:
                rng_pct = (fundamental.current_price - fundamental.week52_low) / (
                           fundamental.week52_high - fundamental.week52_low) * 100
                lines.append(
                    f"  52W · ${fundamental.week52_low:,.2f} – ${fundamental.week52_high:,.2f}"
                    f"  ({rng_pct:.0f}% into range)"
                )
            return "\n".join(lines) if lines else "  No market data"

        # Stock
        lines = []
        if fundamental.analyst_recommendation:
            rating = fundamental.analyst_recommendation.replace("_", " ").title()
            target_str = ""
            if fundamental.analyst_target_price and fundamental.current_price:
                upside = (fundamental.analyst_target_price - fundamental.current_price) / fundamental.current_price * 100
                target_str = f" · target ${fundamental.analyst_target_price:.2f} ({upside:+.1f}%)"
            lines.append(f"  Analyst · <b>{rating}</b>{target_str}")
        if fundamental.pe_ratio:
            lines.append(f"  P/E · {fundamental.pe_ratio:.1f}x")
        if fundamental.revenue_growth:
            lines.append(f"  Revenue growth · {fundamental.revenue_growth*100:+.1f}%")
        if fundamental.earnings_growth:
            lines.append(f"  Earnings growth · {fundamental.earnings_growth*100:+.1f}%")
        if fundamental.recent_upgrades:
            lines.append(f"  Upgrades · {', '.join(fundamental.recent_upgrades[:2])}")
        return "\n".join(lines) if lines else "  No fundamental data"

    # ------------------------------------------------------------------ #
    # Public alert methods                                                 #
    # ------------------------------------------------------------------ #

    def trade_alert(self, symbol: str, action: str, qty, confidence: int,
                    rationale: str, cash_remaining: float,
                    price: float = None, fundamental=None, technical=None):
        icon = "🟢" if action == "BUY" else "🔴"
        is_notional = isinstance(qty, float)

        # Units + cost line
        if is_notional:
            units_line = f"Notional:   <b>${qty:,.2f}</b>"
            cost_line  = ""
        else:
            unit_label = "shares" if qty != 1 else "share"
            if price:
                cost = qty * price
                units_line = f"Units:      <b>{qty} {unit_label} @ ${price:,.2f}</b>"
                cost_line  = f"Cost:       ${cost:,.2f}\n"
            else:
                units_line = f"Units:      <b>{qty} {unit_label}</b>"
                cost_line  = ""

        msg = (
            f"{icon} <b>TRADE ALERT — {action} {symbol}</b>\n"
            f"{units_line}\n"
            f"{cost_line}"
            f"Confidence: {confidence}%\n"
        )

        # Technical signals
        tech_section = self._fmt_technical(technical)
        fund_icon = "🔗" if (fundamental and fundamental.asset_type == "crypto") else "🏢"
        fund_section = self._fmt_fundamental(fundamental)

        msg += (
            f"\n<b>📊 Technical:</b>\n{tech_section}\n"
            f"\n<b>{fund_icon} Fundamental:</b>\n{fund_section}\n"
            f"\n<b>💬 Rationale:</b> {rationale}\n"
            f"Cash left:  ${cash_remaining:,.2f}"
        )

        self.send(msg)

    def risk_exit_alert(self, symbol: str, qty, reason: str):
        msg = (
            f"⚠️ <b>RISK EXIT</b>\n"
            f"Action: SELL {symbol} ({reason})\n"
            f"Units:  {qty}"
        )
        self.send(msg)

    def error_alert(self, context: str, error: str):
        msg = (
            f"❌ <b>BOT ERROR</b>\n"
            f"Context: {context}\n"
            f"Error:   {error}"
        )
        self.send(msg)

    def heartbeat(self, portfolio_value: float, cash: float,
                  positions: dict, market_open: bool,
                  cycles_this_hour: int = 0):
        """Hourly status ping — sent when no trades fired in the past hour."""
        total_pnl = portfolio_value - 100_000
        pnl_icon  = "📈" if total_pnl >= 0 else "📉"
        market_str = "🟢 Stock market OPEN" if market_open else "🔴 Stock market CLOSED"

        msg = (
            f"🤖 <b>BOT HEARTBEAT</b>  (no trades this hour)\n"
            f"{'─' * 28}\n"
            f"{market_str}  ·  🔗 Crypto 24/7\n"
            f"Portfolio:  ${portfolio_value:,.2f}\n"
            f"Cash:       ${cash:,.2f}\n"
            f"Total P&L:  {pnl_icon} ${total_pnl:+,.2f}\n"
        )

        if positions:
            msg += "\n<b>Open Positions:</b>\n"
            for sym, p in positions.items():
                is_crypto = "/" in sym
                qty    = p.get("qty", 0)
                qty_str = f"{float(qty):.4f}" if is_crypto else str(int(qty))
                unit    = "units" if is_crypto else "shares"
                pct     = p.get("unrealized_plpc", 0) * 100
                icon    = "📈" if pct >= 0 else "📉"
                msg    += f"  {icon} {sym}: {qty_str} {unit} ({pct:+.1f}%)\n"
        else:
            msg += "\nNo open positions — scanning for signals.\n"

        self.send(msg)

    def daily_summary(self, trades_placed: int, trades_sold: int,
                      pnl_today: float, portfolio_value: float,
                      cash: float, positions: dict):
        total_pnl = portfolio_value - 100_000
        day_icon  = "📈" if pnl_today >= 0 else "📉"
        tot_icon  = "📈" if total_pnl >= 0 else "📉"

        msg = (
            f"📅 <b>END OF DAY SUMMARY</b>\n"
            f"{'─' * 28}\n"
            f"Trades Today:  {trades_placed} buys | {trades_sold} sells\n"
            f"Day P&L:       {day_icon} ${pnl_today:+,.2f}\n"
            f"Total P&L:     {tot_icon} ${total_pnl:+,.2f}\n"
            f"Portfolio:     ${portfolio_value:,.2f}\n"
            f"Cash:          ${cash:,.2f}\n"
        )

        if positions:
            msg += "\n<b>Open Positions:</b>\n"
            for sym, p in positions.items():
                is_crypto = "/" in sym
                qty = p.get("qty", 0)
                qty_str = f"{float(qty):.4f}" if is_crypto else str(int(qty))
                unit = "units" if is_crypto else "shares"
                pct = p.get("unrealized_plpc", 0) * 100
                pct_icon = "📈" if pct >= 0 else "📉"
                msg += f"  {pct_icon} {sym}: {qty_str} {unit} ({pct:+.1f}%)\n"
        else:
            msg += "\nNo open positions."

        self.send(msg)
