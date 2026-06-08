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

    def trade_alert(self, symbol: str, action: str, qty: int, confidence: int,
                    rationale: str, cash_remaining: float):
        icon = "🟢" if action == "BUY" else "🔴"
        msg = (
            f"{icon} <b>TRADE ALERT</b>\n"
            f"Action:    <b>{action} {symbol}</b>\n"
            f"Shares:    {qty}\n"
            f"Confidence:{confidence}%\n"
            f"Rationale: {rationale}\n"
            f"Cash Left: ${cash_remaining:,.2f}"
        )
        self.send(msg)

    def risk_exit_alert(self, symbol: str, qty: int, reason: str):
        msg = (
            f"⚠️ <b>RISK EXIT</b>\n"
            f"Action: SELL {symbol} ({reason})\n"
            f"Shares: {qty}"
        )
        self.send(msg)

    def cycle_summary(self, trades_placed: int, trades_skipped: int,
                      portfolio_value: float, cash: float):
        msg = (
            f"📊 <b>CYCLE COMPLETE</b>\n"
            f"Trades Placed:  {trades_placed}\n"
            f"Skipped:        {trades_skipped}\n"
            f"Portfolio:      ${portfolio_value:,.2f}\n"
            f"Cash:           ${cash:,.2f}"
        )
        self.send(msg)
