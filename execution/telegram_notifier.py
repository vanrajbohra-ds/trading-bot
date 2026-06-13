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
    # Formatting helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _price_str(p: float) -> str:
        """Format price: 4 decimals for sub-$10 assets (crypto), 2 for stocks."""
        if p is None:
            return "N/A"
        return f"${p:,.4f}" if p < 10 else f"${p:,.2f}"

    @staticmethod
    def _qty_str(qty: float, is_crypto: bool) -> str:
        if is_crypto:
            if qty < 1:
                return f"{qty:.6f}"
            if qty < 100:
                return f"{qty:,.2f}"
            return f"{qty:,.0f}"
        return str(int(qty))

    # ------------------------------------------------------------------ #
    # Public alert methods                                                 #
    # ------------------------------------------------------------------ #

    def trade_alert(self, symbol: str, action: str, qty, confidence: int,
                    rationale: str, cash_remaining: float,
                    price: float = None, fundamental=None, technical=None,
                    avg_entry_price: float = None):
        is_crypto   = "/" in symbol
        is_buy      = action == "BUY"
        # Crypto BUYs are submitted as dollar notional; SELLs and stocks use unit count
        is_notional = is_buy and is_crypto
        icon        = "🟢" if is_buy else "🔴"
        asset_icon  = "🪙" if is_crypto else "📈"
        fqty        = float(qty)

        lines = [
            f"{icon} <b>{action} {symbol}</b>  ·  {confidence}% conf",
            "─" * 24,
        ]

        # ── Units / cost line ─────────────────────────────────────────────
        if price and price > 0:
            ps = self._price_str(price)
            if is_notional:
                approx = fqty / price
                u = (f"~{approx:,.0f}" if approx >= 100
                     else (f"~{approx:.3f}" if approx >= 1 else f"~{approx:.6f}"))
                lines.append(f"{asset_icon} {u} units @ {ps}  ·  cost ${fqty:,.0f}")
            else:
                u    = self._qty_str(fqty, is_crypto)
                unit = "units" if is_crypto else ("share" if fqty == 1 else "shares")
                val  = fqty * price
                lbl  = "cost" if is_buy else "value"
                lines.append(f"{asset_icon} {u} {unit} @ {ps}  ·  {lbl} ${val:,.0f}")
        else:
            if is_notional:
                lines.append(f"{asset_icon} ${fqty:,.2f} notional")
            else:
                u    = self._qty_str(fqty, is_crypto)
                unit = "units" if is_crypto else "shares"
                lines.append(f"{asset_icon} {u} {unit}")

        # ── P&L — SELLs only ─────────────────────────────────────────────
        if (not is_buy and avg_entry_price and avg_entry_price > 0
                and price and price > 0 and fqty > 0):
            pnl     = (price - avg_entry_price) * fqty
            pnl_pct = (price - avg_entry_price) / avg_entry_price * 100
            pi      = "📈" if pnl >= 0 else "📉"
            outcome = "Profit" if pnl >= 0 else "Loss"
            sign    = "+" if pnl >= 0 else ""
            entry_s = self._price_str(avg_entry_price)
            lines.append(f"{pi} {outcome}  {sign}${abs(pnl):,.0f}  ({sign}{pnl_pct:.1f}%)  [entry {entry_s}]")

        lines.append(f"💵 Cash: ${cash_remaining:,.0f}")
        lines.append("")

        # ── Technical — single compact line ──────────────────────────────
        if technical and not getattr(technical, "fetch_error", None):
            tech = []
            if technical.rsi is not None:
                lbl = " OVERSOLD" if technical.rsi < 30 else (" OVERBOUGHT" if technical.rsi > 70 else "")
                tech.append(f"RSI {technical.rsi:.1f}{lbl}")
            if technical.macd_hist is not None:
                tech.append(f"MACD {'▲' if technical.macd_hist > 0 else '▼'}")
            if technical.volume_ratio is not None:
                vl = " HIGH" if technical.volume_ratio > 1.5 else (" LOW" if technical.volume_ratio < 0.7 else "")
                tech.append(f"Vol {technical.volume_ratio:.1f}×avg{vl}")
            if tech:
                lines.append(f"📊 {' · '.join(tech)}")

        # ── Fundamental — single compact line ─────────────────────────────
        if fundamental and not getattr(fundamental, "fetch_error", None):
            fund = []
            if is_crypto:
                if fundamental.news_sentiment_label:
                    fund.append(f"Sentiment {fundamental.news_sentiment_label}")
                if (fundamental.week52_high and fundamental.week52_low
                        and fundamental.current_price
                        and fundamental.week52_high > fundamental.week52_low):
                    rng = ((fundamental.current_price - fundamental.week52_low)
                           / (fundamental.week52_high - fundamental.week52_low) * 100)
                    fund.append(f"{rng:.0f}% into 52W range")
            else:
                if fundamental.analyst_recommendation:
                    fund.append(fundamental.analyst_recommendation.replace("_", " ").title())
                if fundamental.analyst_target_price and fundamental.current_price:
                    up = ((fundamental.analyst_target_price - fundamental.current_price)
                          / fundamental.current_price * 100)
                    fund.append(f"target ${fundamental.analyst_target_price:.0f} ({up:+.0f}%)")
                if fundamental.revenue_growth:
                    fund.append(f"Rev {fundamental.revenue_growth * 100:+.0f}%")
                if fundamental.news_sentiment_label:
                    fund.append(f"Sentiment {fundamental.news_sentiment_label}")
            if fund:
                f_icon = "🔗" if is_crypto else "🏢"
                lines.append(f"{f_icon} {' · '.join(fund)}")

        # ── Rationale — trimmed ───────────────────────────────────────────
        r = rationale.strip()
        if len(r) > 140:
            r = r[:137] + "..."
        lines.append("")
        lines.append(f"💬 {r}")

        self.send("\n".join(lines))

    def risk_exit_alert(self, symbol: str, qty, reason: str,
                        avg_entry_price: float = None, current_price: float = None):
        is_crypto = "/" in symbol
        fqty      = float(qty)
        qty_str   = self._qty_str(fqty, is_crypto)
        unit      = "units" if is_crypto else ("share" if fqty == 1 else "shares")

        lines = [
            f"⚠️ <b>RISK EXIT — {symbol}</b>",
            f"🛑 {reason}  ·  {qty_str} {unit}",
        ]

        if avg_entry_price and avg_entry_price > 0 and current_price and current_price > 0:
            pnl     = (current_price - avg_entry_price) * fqty
            pnl_pct = (current_price - avg_entry_price) / avg_entry_price * 100
            pi      = "📈" if pnl >= 0 else "📉"
            sign    = "+" if pnl >= 0 else ""
            entry_s = self._price_str(avg_entry_price)
            curr_s  = self._price_str(current_price)
            lines.append(f"{pi} {sign}${abs(pnl):,.0f} ({sign}{pnl_pct:.1f}%)  [{entry_s} → {curr_s}]")

        self.send("\n".join(lines))

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
                qty_s  = self._qty_str(float(qty), is_crypto)
                unit   = "units" if is_crypto else "shares"
                pct    = p.get("unrealized_plpc", 0) * 100
                icon   = "📈" if pct >= 0 else "📉"
                msg   += f"  {icon} {sym}: {qty_s} {unit} ({pct:+.1f}%)\n"
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
                qty   = p.get("qty", 0)
                qty_s = self._qty_str(float(qty), is_crypto)
                unit  = "units" if is_crypto else "shares"
                pct   = p.get("unrealized_plpc", 0) * 100
                pi    = "📈" if pct >= 0 else "📉"
                msg  += f"  {pi} {sym}: {qty_s} {unit} ({pct:+.1f}%)\n"
        else:
            msg += "\nNo open positions."

        self.send(msg)
