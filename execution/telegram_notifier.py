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

    def trade_alert(self, symbol: str, action: str, qty, confidence: int,
                    rationale: str, cash_remaining: float):
        icon  = "🟢" if action == "BUY" else "🔴"
        label = f"${qty}" if isinstance(qty, float) else str(qty)
        unit  = "notional" if isinstance(qty, float) else "shares"
        msg = (
            f"{icon} <b>TRADE ALERT</b>\n"
            f"Action:     <b>{action} {symbol}</b>\n"
            f"Amount:     {label} {unit}\n"
            f"Confidence: {confidence}%\n"
            f"Rationale:  {rationale}\n"
            f"Cash Left:  ${cash_remaining:,.2f}"
        )
        self.send(msg)

    def risk_exit_alert(self, symbol: str, qty: int, reason: str):
        msg = (
            f"⚠️ <b>RISK EXIT</b>\n"
            f"Action: SELL {symbol} ({reason})\n"
            f"Shares: {qty}"
        )
        self.send(msg)

    def error_alert(self, context: str, error: str):
        msg = (
            f"❌ <b>BOT ERROR</b>\n"
            f"Context: {context}\n"
            f"Error:   {error}"
        )
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
            msg += f"\n<b>Open Positions:</b>\n"
            for sym, p in positions.items():
                pct = p.get("unrealized_plpc", 0) * 100
                pct_icon = "📈" if pct >= 0 else "📉"
                msg += f"  {pct_icon} {sym}: {p['qty']} shares ({pct:+.1f}%)\n"
        else:
            msg += "\nNo open positions."

        self.send(msg)
