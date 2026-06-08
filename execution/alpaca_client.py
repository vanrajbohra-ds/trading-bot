import os
import logging
import requests

logger = logging.getLogger(__name__)


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
            symbol = p["symbol"]
            positions[symbol] = {
                "qty": int(float(p["qty"])),
                "avg_entry_price": float(p["avg_entry_price"]),
                "current_price": float(p.get("current_price") or p["avg_entry_price"]),
                "market_value": float(p["market_value"]),
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)),
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

    def submit_market_order(self, symbol: str, side: str, qty: int) -> dict:
        side = side.lower()
        if side == "sell":
            self.cancel_all_orders_for(symbol)

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
