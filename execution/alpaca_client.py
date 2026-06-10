import os
import logging
import requests

logger = logging.getLogger(__name__)

# Alpaca returns crypto symbols without a slash (AVAXUSD) but we use AVAX/USD internally.
# This map normalises the raw symbol so the rest of the code always sees the slash format.
_CRYPTO_SYMBOL_NORM = {
    "BTCUSD":  "BTC/USD",
    "ETHUSD":  "ETH/USD",
    "SOLUSD":  "SOL/USD",
    "DOGEUSD": "DOGE/USD",
    "AVAXUSD": "AVAX/USD",
    "LTCUSD":  "LTC/USD",
    "LINKUSD": "LINK/USD",
    "UNIUSD":  "UNI/USD",
}


class AlpacaClient:
    def __init__(self):
        self._key = os.environ["ALPACA_API_KEY"]
        self._secret = os.environ["ALPACA_SECRET_KEY"]
        self._base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2").rstrip("/")
        self._headers = {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
        }

    def _get(self, path, params=None):
        r = requests.get(f"{self._base}{path}", headers=self._headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path, body):
        r = requests.post(f"{self._base}{path}", headers=self._headers, json=body, timeout=15)
        return r

    def _delete(self, path):
        r = requests.delete(f"{self._base}{path}", headers=self._headers, timeout=15)
        return r

    def is_market_open(self) -> bool:
        try:
            data = self._get("/clock")
            return bool(data.get("is_open", False))
        except Exception as e:
            logger.error(f"Clock check failed: {e}")
            return False

    def get_account(self) -> dict:
        data = self._get("/account")
        return {
            "cash": float(data["cash"]),
            "portfolio_value": float(data["portfolio_value"]),
            "buying_power": float(data["buying_power"]),
        }

    def get_positions(self) -> dict:
        raw = self._get("/positions")
        positions = {}
        for p in raw:
            # Normalise symbol: Alpaca may return AVAXUSD or AVAX/USD — use slash form always
            symbol    = _CRYPTO_SYMBOL_NORM.get(p["symbol"], p["symbol"])
            is_crypto = "/" in symbol
            raw_qty   = float(p["qty"])
            positions[symbol] = {
                "qty": raw_qty if is_crypto else int(raw_qty),
                "avg_entry_price": float(p["avg_entry_price"]),
                "current_price":   float(p.get("current_price") or p["avg_entry_price"]),
                "market_value":    float(p["market_value"]),
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)),
                "unrealized_pl":   float(p.get("unrealized_pl",   0)),
            }
        return positions

    def cancel_all_orders_for(self, symbol: str):
        try:
            orders = self._get("/orders", params={"status": "open"})
            for o in orders:
                if o.get("symbol") == symbol:
                    self._delete(f"/orders/{o['id']}")
                    logger.info(f"Cancelled open order {o['id']} for {symbol}")
        except Exception as e:
            logger.warning(f"Error cancelling orders for {symbol}: {e}")

    def submit_crypto_order(self, symbol: str, side: str, notional: float) -> dict:
        """Submit a crypto order using notional (dollar) amount. Crypto uses GTC, not DAY."""
        side = side.lower()
        body = {
            "symbol": symbol,
            "notional": str(round(notional, 2)),
            "side": side,
            "type": "market",
            "time_in_force": "gtc",
        }
        r = self._post("/orders", body)
        if r.status_code in (200, 201):
            data = r.json()
            logger.info(f"Crypto order placed: {side.upper()} ${notional:.2f} of {symbol} | id={data.get('id')}")
            return {"success": True, "order": data}
        else:
            logger.error(f"Crypto order failed: {side.upper()} ${notional:.2f} {symbol} | {r.status_code} {r.text}")
            return {"success": False, "error": r.text, "status_code": r.status_code}

    def submit_market_order(self, symbol: str, side: str, qty: int) -> dict:
        side = side.lower()
        self.cancel_all_orders_for(symbol)  # always cancel pending orders first (prevents duplicate/blocking orders)

        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        r = self._post("/orders", body)
        if r.status_code in (200, 201):
            data = r.json()
            logger.info(f"Order placed: {side.upper()} {qty} {symbol} | id={data.get('id')} status={data.get('status')}")
            return {"success": True, "order": data}
        else:
            logger.error(f"Order failed: {side.upper()} {qty} {symbol} | {r.status_code} {r.text}")
            return {"success": False, "error": r.text, "status_code": r.status_code}

    def get_orders_today(self) -> list:
        """Return all filled orders placed today."""
        import datetime
        today = datetime.date.today().isoformat()
        try:
            orders = self._get("/orders", params={
                "status": "filled",
                "after": f"{today}T00:00:00Z",
                "limit": 500,
                "direction": "asc",
            })
            return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.warning(f"Could not fetch today's orders: {e}")
            return []

    def get_recent_buy_symbols(self, lookback_minutes: int = 15) -> set:
        """Return symbols with any non-cancelled buy order in the last N minutes.
        Guards against duplicate crypto buying when the positions API lags after a fill."""
        import datetime
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=lookback_minutes)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            orders = self._get("/orders", params={
                "status": "all",
                "after": cutoff_str,
                "limit": 100,
                "direction": "asc",
            })
            if not isinstance(orders, list):
                return set()
            syms = {
                o["symbol"] for o in orders
                if o.get("side") == "buy"
                and o.get("status") not in {"canceled", "expired", "replaced"}
            }
            if syms:
                logger.info(f"[dedup] Recent buys in last {lookback_minutes}min: {syms}")
            return syms
        except Exception as e:
            logger.warning(f"get_recent_buy_symbols failed ({e}) — allowing buys")
            return set()

    def cancel_stale_open_orders(self, min_age_minutes: int = 5):
        """Cancel orders stuck in 'new'/'accepted'/'pending_new' for longer than min_age_minutes.
        Cleans up BTC/USD phantom orders that Alpaca accepts but never fills."""
        import datetime
        try:
            orders = self._get("/orders", params={"status": "open", "limit": 100})
            if not isinstance(orders, list):
                return
            now = datetime.datetime.utcnow()
            cancelled = 0
            for o in orders:
                if o.get("status") not in {"new", "accepted", "pending_new"}:
                    continue
                try:
                    created = datetime.datetime.fromisoformat(
                        o["created_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    age_min = (now - created).total_seconds() / 60
                except Exception:
                    continue
                if age_min >= min_age_minutes:
                    r = self._delete(f"/orders/{o['id']}")
                    if r.ok:
                        logger.info(
                            f"[cleanup] Cancelled stuck {o['side'].upper()} {o['symbol']} "
                            f"(status={o['status']}, age={age_min:.0f}min)"
                        )
                        cancelled += 1
            if cancelled:
                logger.info(f"[cleanup] Removed {cancelled} stale open orders total")
        except Exception as e:
            logger.warning(f"cancel_stale_open_orders failed ({e})")

    def get_daily_pnl(self) -> float:
        """Return today's P&L from portfolio history."""
        try:
            data = self._get("/account/portfolio/history", params={
                "period": "1D",
                "timeframe": "5Min",
            })
            equities = data.get("equity") or []
            if len(equities) >= 2:
                start = next((v for v in equities if v), None)
                end   = equities[-1]
                if start and end:
                    return float(end) - float(start)
        except Exception as e:
            logger.warning(f"Could not fetch portfolio history: {e}")
        return 0.0

    def get_latest_price(self, symbol: str) -> float:
        try:
            data = self._get(f"/stocks/{symbol}/quotes/latest")
            return float(data["quote"]["ap"])
        except Exception:
            try:
                positions = self._get("/positions")
                for p in positions:
                    if p["symbol"] == symbol:
                        return float(p.get("current_price") or p["avg_entry_price"])
            except Exception:
                pass
            return 0.0
