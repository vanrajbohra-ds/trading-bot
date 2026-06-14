import sys
import os
import logging
import time
import datetime

sys.path.insert(0, os.path.dirname(__file__))

from env_loader import load_env
load_env()

_fmt = "%(asctime)s %(levelname)s %(message)s"
_logs_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_logs_dir, exist_ok=True)

_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(logging.Formatter(_fmt))
if hasattr(_console.stream, "reconfigure"):
    _console.stream.reconfigure(encoding="utf-8", errors="replace")
_file = logging.FileHandler(
    os.path.join(_logs_dir, "trading_bot.log"), encoding="utf-8"
)
_file.setFormatter(logging.Formatter(_fmt))
logging.basicConfig(level=logging.INFO, handlers=[_console, _file])
logger = logging.getLogger(__name__)

MARKET_OPEN_ET  = datetime.time(9, 30)
MARKET_CLOSE_ET = datetime.time(16, 0)
CYCLE_INTERVAL  = 60    # seconds between cycles (1 minute, used in --daemon/AWS mode)
ET_OFFSET       = -4    # EDT (summer). Change to -5 in winter (EST)
EOD_WINDOW_MIN     = 6   # send daily summary if within this many minutes AFTER close
HEARTBEAT_MINUTE   = 2   # send heartbeat in the first HEARTBEAT_MINUTE mins of every hour


def _now_et() -> datetime.datetime:
    utc = datetime.datetime.utcnow()
    return utc + datetime.timedelta(hours=ET_OFFSET)


def _is_market_hours() -> bool:
    now = _now_et()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN_ET <= now.time() <= MARKET_CLOSE_ET


def _is_near_close() -> bool:
    """True in the EOD_WINDOW_MIN-minute window just after 4 PM ET.

    Fires AFTER close (not before) so GitHub Actions startup latency (~2 min)
    doesn't cause the summary to miss the window.  With a 6-min window and
    2-min cron cadence this fires at most 3 times — acceptable; the summary is
    idempotent and users prefer a duplicate over a missing one.
    """
    now = _now_et()
    if now.weekday() >= 5:
        return False
    close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
    mins_after_close = (now - close_dt).total_seconds() / 60
    return 0 <= mins_after_close <= EOD_WINDOW_MIN


def _is_top_of_hour() -> bool:
    """True during the first HEARTBEAT_MINUTE minutes of any hour.
    With a 2-min cron cadence this fires exactly once per hour."""
    return _now_et().minute < HEARTBEAT_MINUTE


def _send_heartbeat(market_open: bool):
    from execution.alpaca_client import AlpacaClient
    from execution.telegram_notifier import TelegramNotifier
    alpaca   = AlpacaClient()
    telegram = TelegramNotifier()
    try:
        account   = alpaca.get_account()
        positions = alpaca.get_positions()
        telegram.heartbeat(
            portfolio_value=account["portfolio_value"],
            cash=account["cash"],
            positions=positions,
            market_open=market_open,
        )
        logger.info("Hourly heartbeat sent to Telegram")
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")


def _send_daily_summary():
    from execution.alpaca_client import AlpacaClient
    from execution.telegram_notifier import TelegramNotifier
    alpaca   = AlpacaClient()
    telegram = TelegramNotifier()
    try:
        account    = alpaca.get_account()
        positions  = alpaca.get_positions()
        pnl_today  = alpaca.get_daily_pnl()
        orders     = alpaca.get_orders_today()
        buys  = sum(1 for o in orders if o.get("side") == "buy")
        sells = sum(1 for o in orders if o.get("side") == "sell")
        telegram.daily_summary(
            trades_placed=buys,
            trades_sold=sells,
            pnl_today=pnl_today,
            portfolio_value=account["portfolio_value"],
            cash=account["cash"],
            positions=positions,
        )
        logger.info("End-of-day summary sent to Telegram")
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")


def run_once():
    logger.info("=== Trading Bot starting cycle ===")
    try:
        from orchestrator import run_cycle
        from execution.alpaca_client import AlpacaClient
        result = run_cycle()
        market_open = AlpacaClient().is_market_open()
    except Exception as e:
        logger.exception(f"Unhandled error in trading cycle: {e}")
        # Don't sys.exit(1) — let GitHub Actions mark run as failed but still
        # attempt the heartbeat/EOD so Telegram always gets something this hour.
        from execution.telegram_notifier import TelegramNotifier
        TelegramNotifier().error_alert("Trading cycle crashed", str(e))
        sys.exit(1)

    if _is_top_of_hour():
        logger.info("Top of hour — sending heartbeat")
        _send_heartbeat(market_open)

    if _is_near_close():
        logger.info("Just after market close — sending end-of-day summary")
        _send_daily_summary()

    logger.info("=== Cycle finished ===")


def run_daemon():
    """Daemon mode for AWS EC2 — runs every hour during market hours, idles otherwise."""
    logger.info("=== Trading Bot daemon started (AWS EC2 mode) ===")
    while True:
        if _is_market_hours():
            logger.info("Market hours — running cycle")
            try:
                from orchestrator import run_cycle
                run_cycle()
            except Exception as e:
                logger.exception(f"Unhandled error in trading cycle: {e}")
            logger.info(f"Sleeping {CYCLE_INTERVAL // 60} minutes until next cycle")
            time.sleep(CYCLE_INTERVAL)
        else:
            now = _now_et()
            logger.info(f"Market closed ({now.strftime('%a %H:%M ET')}) — sleeping 15 minutes")
            time.sleep(900)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon()
    else:
        run_once()
