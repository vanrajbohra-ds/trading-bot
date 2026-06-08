import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import json
from datetime import datetime, timedelta
import yfinance as yf

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card { background: #1e1e2e; border-radius: 12px; padding: 20px; text-align: center; }
    .positive    { color: #00c853; font-size: 1.6rem; font-weight: bold; }
    .negative    { color: #ff1744; font-size: 1.6rem; font-weight: bold; }
    .neutral     { color: #90caf9; font-size: 1.6rem; font-weight: bold; }
    div[data-testid="stMetricValue"] > div { font-size: 1.5rem; }
    .section-header { font-size: 1.1rem; font-weight: 600; margin-bottom: 4px; }
    .crypto-tag { background: #2a1f4e; color: #b39ddb; border-radius: 6px;
                  padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }
    .stock-tag  { background: #1a3a2a; color: #80cbc4; border-radius: 6px;
                  padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

CRYPTO_SYMBOLS    = {"BTC/USD", "SOL/USD", "DOGE/USD", "AVAX/USD"}
CRYPTO_YF_MAP     = {"BTC/USD": "BTC-USD", "SOL/USD": "SOL-USD",
                     "DOGE/USD": "DOGE-USD", "AVAX/USD": "AVAX-USD"}

# ── Credentials ───────────────────────────────────────────────────────────────
def get_creds():
    try:
        return {
            "key":      st.secrets["ALPACA_API_KEY"],
            "secret":   st.secrets["ALPACA_SECRET_KEY"],
            "base":     st.secrets.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"),
            "gh_token": st.secrets.get("GITHUB_TOKEN", ""),
            "gh_repo":  st.secrets.get("GITHUB_REPO", "vanrajbohra-ds/trading-bot"),
        }
    except Exception:
        from env_loader import load_env
        load_env()
        return {
            "key":      os.environ.get("ALPACA_API_KEY", ""),
            "secret":   os.environ.get("ALPACA_SECRET_KEY", ""),
            "base":     os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"),
            "gh_token": os.environ.get("GITHUB_TOKEN", ""),
            "gh_repo":  os.environ.get("GITHUB_REPO", "vanrajbohra-ds/trading-bot"),
        }

creds = get_creds()
HEADERS = {
    "APCA-API-KEY-ID":     creds["key"],
    "APCA-API-SECRET-KEY": creds["secret"],
    "Content-Type":        "application/json",
}
BASE = creds["base"].rstrip("/")

# ── Alpaca helpers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_account():
    r = requests.get(f"{BASE}/account", headers=HEADERS, timeout=10)
    return r.json()

@st.cache_data(ttl=30)
def get_positions():
    r = requests.get(f"{BASE}/positions", headers=HEADERS, timeout=10)
    return r.json() if r.ok else []

@st.cache_data(ttl=60)
def get_orders(status="all", limit=200):
    r = requests.get(f"{BASE}/orders", headers=HEADERS,
                     params={"status": status, "limit": limit, "direction": "desc"}, timeout=10)
    return r.json() if r.ok else []

@st.cache_data(ttl=300)
def get_portfolio_history(period="1M", timeframe="1D"):
    r = requests.get(f"{BASE}/account/portfolio/history",
                     headers=HEADERS,
                     params={"period": period, "timeframe": timeframe, "extended_hours": False},
                     timeout=10)
    return r.json() if r.ok else {}

@st.cache_data(ttl=60)
def get_watchlist():
    path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

def save_watchlist_github(new_list, gh_token, gh_repo):
    if not gh_token:
        return False, "No GitHub token configured"
    headers = {"Authorization": f"token {gh_token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/repos/{gh_repo}/contents/watchlist.json",
                     headers=headers, timeout=10)
    if not r.ok:
        return False, r.text
    sha = r.json()["sha"]
    import base64
    content = base64.b64encode(json.dumps(new_list, indent=2).encode()).decode()
    payload = {"message": f"update watchlist: {new_list}", "content": content, "sha": sha}
    r = requests.put(f"https://api.github.com/repos/{gh_repo}/contents/watchlist.json",
                     headers=headers, json=payload, timeout=10)
    return r.ok, r.text

@st.cache_data(ttl=60)
def get_quick_price(symbol):
    try:
        t = yf.Ticker(symbol)
        h = t.history(period="2d")
        if len(h) >= 2:
            prev = h["Close"].iloc[-2]
            cur  = h["Close"].iloc[-1]
            chg  = cur - prev
            return cur, chg, chg / prev * 100
        return 0, 0, 0
    except Exception:
        return 0, 0, 0

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Alpaca_icon.svg/240px-Alpaca_icon.svg.png", width=60)
    st.title("Trading Bot")
    st.caption("Autonomous AI Trading System")
    st.divider()

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("📋 Stock Watchlist")
    watchlist = get_watchlist()
    for sym in watchlist:
        col1, col2 = st.columns([3, 1])
        col1.write(f"• {sym}")
        if col2.button("✕", key=f"remove_{sym}"):
            new_wl = [s for s in watchlist if s != sym]
            ok, _ = save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
            with open(path, "w") as f:
                json.dump(new_wl, f)
            st.success(f"Removed {sym}")
            st.cache_data.clear()
            st.rerun()

    new_sym = st.text_input("Add symbol (e.g. GOOGL)", max_chars=10).upper().strip()
    if st.button("➕ Add Stock", use_container_width=True):
        if new_sym and new_sym not in watchlist:
            new_wl = watchlist + [new_sym]
            save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
            with open(path, "w") as f:
                json.dump(new_wl, f)
            st.success(f"Added {new_sym}")
            st.cache_data.clear()
            st.rerun()
        elif new_sym in watchlist:
            st.warning(f"{new_sym} already in watchlist")

    st.divider()
    st.caption("🔗 Crypto watchlist (BTC, SOL, DOGE, AVAX) is fixed in config.py")
    st.caption("Auto-refreshes every 30 seconds")

# ── Load data ──────────────────────────────────────────────────────────────────
st.title("📈 Trading Bot Dashboard")
st.caption(f"Paper Trading · Last updated: {datetime.now().strftime('%b %d, %Y %I:%M %p')}")

account   = get_account()
positions = get_positions()
orders    = get_orders()

portfolio_value  = float(account.get("portfolio_value", 0))
cash             = float(account.get("cash", 0))
starting_capital = 100_000.0
total_pnl        = portfolio_value - starting_capital
total_pnl_pct    = total_pnl / starting_capital * 100

# Split positions into stocks and crypto
stock_positions  = [p for p in positions if isinstance(p, dict) and p.get("symbol", "") not in CRYPTO_SYMBOLS]
crypto_positions = [p for p in positions if isinstance(p, dict) and p.get("symbol", "") in CRYPTO_SYMBOLS]

stock_mkt_value  = sum(float(p.get("market_value", 0)) for p in stock_positions)
crypto_mkt_value = sum(float(p.get("market_value", 0)) for p in crypto_positions)
stock_pnl        = sum(float(p.get("unrealized_pl", 0)) for p in stock_positions)
crypto_pnl       = sum(float(p.get("unrealized_pl", 0)) for p in crypto_positions)

# Order analytics
filled_orders = [o for o in orders if o.get("status") == "filled"]
closed_sells  = [o for o in filled_orders if o.get("side") == "sell"]

def calc_trade_pnl(sell_order, all_orders):
    sym  = sell_order["symbol"]
    qty  = float(sell_order.get("filled_qty", 0))
    sell_price = float(sell_order.get("filled_avg_price") or 0)
    buys = [o for o in all_orders
            if o["symbol"] == sym and o["side"] == "buy"
            and o["status"] == "filled"
            and o["filled_at"] < sell_order["filled_at"]]
    if not buys:
        return 0
    avg_buy = sum(float(o.get("filled_avg_price") or 0) for o in buys) / len(buys)
    return (sell_price - avg_buy) * qty

trade_pnls    = [calc_trade_pnl(o, filled_orders) for o in closed_sells]
wins          = [p for p in trade_pnls if p > 0]
losses        = [p for p in trade_pnls if p <= 0]
win_rate      = len(wins) / len(trade_pnls) * 100 if trade_pnls else 0
profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")

# ── Row 1: Portfolio overview ──────────────────────────────────────────────────
st.subheader("Portfolio Overview")
c1, c2, c3, c4, c5, c6 = st.columns(6)
pnl_color = "normal" if total_pnl >= 0 else "inverse"
c1.metric("Portfolio Value",  f"${portfolio_value:,.2f}")
c2.metric("Cash Available",   f"${cash:,.2f}")
c3.metric("Total P&L",        f"${total_pnl:+,.2f}", f"{total_pnl_pct:+.2f}%", delta_color=pnl_color)
c4.metric("Open Positions",   len(positions))
c5.metric("Win Rate",         f"{win_rate:.1f}%", f"{len(wins)}W / {len(losses)}L")
c6.metric("Profit Factor",    f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞")

st.divider()

# ── Row 2: Stocks vs Crypto allocation summary ────────────────────────────────
st.subheader("📊 Allocation Split — Stocks vs Crypto")
a1, a2, a3, a4, a5 = st.columns(5)

a1.metric("📈 Stock Value",   f"${stock_mkt_value:,.2f}")
a2.metric("📈 Stock P&L",     f"${stock_pnl:+,.2f}",
          delta_color="normal" if stock_pnl >= 0 else "inverse")
a3.metric("💰 Cash",          f"${cash:,.2f}")
a4.metric("🔗 Crypto Value",  f"${crypto_mkt_value:,.2f}")
a5.metric("🔗 Crypto P&L",    f"${crypto_pnl:+,.2f}",
          delta_color="normal" if crypto_pnl >= 0 else "inverse")

# Allocation pie chart
total_invested = stock_mkt_value + crypto_mkt_value + cash
if total_invested > 0:
    pie_labels = ["Stocks", "Crypto", "Cash"]
    pie_values = [stock_mkt_value, crypto_mkt_value, cash]
    pie_colors = ["#00c853", "#7c4dff", "#90caf9"]
    fig_pie = go.Figure(go.Pie(
        labels=pie_labels, values=pie_values,
        marker=dict(colors=pie_colors),
        hole=0.5,
        textinfo="label+percent",
        hovertemplate="%{label}: $%{value:,.2f} (%{percent})<extra></extra>",
    ))
    fig_pie.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(font=dict(color="white")),
        height=220,
        showlegend=True,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ── Row 3: Portfolio chart + open positions ────────────────────────────────────
col_chart, col_pos = st.columns([3, 2])

with col_chart:
    st.subheader("📊 Portfolio Performance")
    history    = get_portfolio_history(period="1M", timeframe="1D")
    timestamps = history.get("timestamp", [])
    equity     = history.get("equity", [])

    if timestamps and equity:
        df_hist = pd.DataFrame({
            "date":  [datetime.fromtimestamp(t) for t in timestamps],
            "value": equity,
        })
        df_hist["pnl"] = df_hist["value"] - starting_capital

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist["date"], y=df_hist["value"],
            fill="tozeroy",
            fillcolor="rgba(0,200,83,0.1)",
            line=dict(color="#00c853", width=2),
            hovertemplate="<b>%{x|%b %d}</b><br>Value: $%{y:,.2f}<extra></extra>",
        ))
        fig.add_hline(y=starting_capital, line_dash="dash",
                      line_color="rgba(255,255,255,0.3)",
                      annotation_text="Starting $100,000")
        fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="white"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", color="white",
                       tickformat="$,.0f"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Portfolio history will appear after the first trading day.")

with col_pos:
    st.subheader("🏦 Open Positions")
    tab_stocks, tab_crypto = st.tabs(["📈 Stocks", "🔗 Crypto"])

    def _position_rows(pos_list, is_crypto=False):
        rows = []
        for p in pos_list:
            qty       = float(p.get("qty", 0))
            entry     = float(p.get("avg_entry_price", 0))
            cur       = float(p.get("current_price") or entry)
            mkt_val   = float(p.get("market_value", 0))
            unreal_pl = float(p.get("unrealized_pl", 0))
            unreal_pct= float(p.get("unrealized_plpc", 0)) * 100
            stop_pct  = 0.12 if is_crypto else 0.07
            take_pct  = 0.25 if is_crypto else 0.15
            rows.append({
                "Symbol":   p["symbol"],
                "Units":    f"{qty:.4f}" if is_crypto else str(int(qty)),
                "Entry":    f"${entry:.4f}" if is_crypto else f"${entry:.2f}",
                "Current":  f"${cur:.4f}" if is_crypto else f"${cur:.2f}",
                "Mkt Value":f"${mkt_val:,.2f}",
                "P&L":      f"${unreal_pl:+,.2f}",
                "P&L %":    f"{unreal_pct:+.2f}%",
                "Stop":     f"${entry*(1-stop_pct):.4f}" if is_crypto else f"${entry*0.93:.2f}",
                "Target":   f"${entry*(1+take_pct):.4f}" if is_crypto else f"${entry*1.15:.2f}",
            })
        return rows

    def _style_pnl(val):
        color = "#00c853" if val.startswith("+") else "#ff1744"
        return f"color: {color}"

    with tab_stocks:
        rows = _position_rows(stock_positions, is_crypto=False)
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df.style.map(_style_pnl, subset=["P&L", "P&L %"]),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No stock positions open.")

    with tab_crypto:
        rows = _position_rows(crypto_positions, is_crypto=True)
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df.style.map(_style_pnl, subset=["P&L", "P&L %"]),
                         use_container_width=True, hide_index=True)
            st.caption("Stop-loss: −12%  ·  Take-profit: +25%  ·  Units are fractional")
        else:
            st.info("No crypto positions open.")

st.divider()

# ── Row 4: P&L breakdown by stock vs crypto ────────────────────────────────────
st.subheader("💰 P&L Breakdown")
col_stock_bar, col_crypto_bar = st.columns(2)

def _pnl_bar(pos_list, title, color_pos, color_neg):
    syms  = [p["symbol"] for p in pos_list]
    pnls  = [float(p.get("unrealized_pl", 0)) for p in pos_list]
    if not syms:
        st.info(f"No {title} positions.")
        return
    colors = [color_pos if v >= 0 else color_neg for v in pnls]
    fig = go.Figure(go.Bar(
        x=syms, y=pnls,
        marker_color=colors,
        text=[f"${v:+,.0f}" for v in pnls],
        textposition="outside",
        hovertemplate="%{x}: $%{y:+,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color="white", size=14)),
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(color="white"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)",
                   color="white", tickformat="$,.0f"),
        height=240,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_stock_bar:
    _pnl_bar(stock_positions, "📈 Stocks — Unrealized P&L", "#00c853", "#ff1744")

with col_crypto_bar:
    _pnl_bar(crypto_positions, "🔗 Crypto — Unrealized P&L", "#7c4dff", "#e040fb")

st.divider()

# ── Row 5: Trade history ───────────────────────────────────────────────────────
st.subheader("📜 Trade History")
tab_all, tab_stocks_hist, tab_crypto_hist = st.tabs(["All Trades", "📈 Stocks", "🔗 Crypto"])

def _build_history_df(order_list):
    rows = []
    for o in order_list[:100]:
        sym = o.get("symbol", "")
        filled_at = o.get("filled_at", "")
        if filled_at:
            try:
                dt = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
                filled_at = dt.strftime("%b %d %H:%M")
            except Exception:
                pass
        qty   = float(o.get("filled_qty", 0))
        price = float(o.get("filled_avg_price") or 0)
        side  = o.get("side", "").upper()
        asset = "🔗 Crypto" if sym in CRYPTO_SYMBOLS else "📈 Stock"
        rows.append({
            "Date":   filled_at,
            "Type":   asset,
            "Symbol": sym,
            "Action": side,
            "Units":  f"{qty:.4f}" if sym in CRYPTO_SYMBOLS else str(int(qty)),
            "Price":  f"${price:.4f}" if sym in CRYPTO_SYMBOLS else f"${price:.2f}",
            "Value":  f"${qty * price:,.2f}",
        })
    return pd.DataFrame(rows)

def _color_action(val):
    return "color: #00c853" if val == "BUY" else "color: #ff1744"

stock_orders  = [o for o in filled_orders if o.get("symbol", "") not in CRYPTO_SYMBOLS]
crypto_orders = [o for o in filled_orders if o.get("symbol", "") in CRYPTO_SYMBOLS]

with tab_all:
    df = _build_history_df(filled_orders)
    if not df.empty:
        st.dataframe(df.style.map(_color_action, subset=["Action"]),
                     use_container_width=True, hide_index=True, height=300)
    else:
        st.info("No trade history yet.")

with tab_stocks_hist:
    df = _build_history_df(stock_orders)
    if not df.empty:
        st.dataframe(df.drop(columns=["Type"]).style.map(_color_action, subset=["Action"]),
                     use_container_width=True, hide_index=True, height=300)
    else:
        st.info("No stock trades yet.")

with tab_crypto_hist:
    df = _build_history_df(crypto_orders)
    if not df.empty:
        st.dataframe(df.drop(columns=["Type"]).style.map(_color_action, subset=["Action"]),
                     use_container_width=True, hide_index=True, height=300)
    else:
        st.info("No crypto trades yet.")

st.divider()

# ── Row 6: Success metrics ─────────────────────────────────────────────────────
st.subheader("🎯 Performance Metrics")
m1, m2, m3, m4, m5 = st.columns(5)
best_trade  = max(trade_pnls) if trade_pnls else 0
worst_trade = min(trade_pnls) if trade_pnls else 0
avg_win     = sum(wins) / len(wins) if wins else 0
avg_loss    = sum(losses) / len(losses) if losses else 0
m1.metric("Total Orders",   len(filled_orders))
m2.metric("Closed Trades",  len(closed_sells))
m3.metric("Best Trade",     f"${best_trade:+,.2f}")
m4.metric("Worst Trade",    f"${worst_trade:+,.2f}")
m5.metric("Avg Win / Loss", f"${avg_win:+,.0f} / ${avg_loss:+,.0f}")

weekly_return = (portfolio_value / starting_capital - 1) * 100
target_weekly = 30.0
progress = min(max(weekly_return / target_weekly * 100, 0), 100) if weekly_return > 0 else 0

st.divider()
st.subheader("🎯 Weekly Target Progress (30%)")
col_prog, col_num = st.columns([4, 1])
col_prog.progress(int(progress))
col_num.metric("Return", f"{weekly_return:+.2f}%", f"Target: {target_weekly:.0f}%",
               delta_color="normal" if weekly_return >= 0 else "inverse")

st.divider()

# ── Row 7: Live prices — Stocks ────────────────────────────────────────────────
st.subheader("📡 Live Prices")

st.markdown("**📈 Stocks**")
watchlist = get_watchlist()
cols = st.columns(len(watchlist))
for i, sym in enumerate(watchlist):
    price, chg, chgpct = get_quick_price(sym)
    with cols[i]:
        st.metric(sym, f"${price:.2f}", f"{chg:+.2f} ({chgpct:+.2f}%)",
                  delta_color="normal" if chg >= 0 else "inverse")

st.markdown("**🔗 Crypto**")
crypto_list = list(CRYPTO_YF_MAP.items())   # [(alpaca_sym, yf_sym), ...]
cols2 = st.columns(len(crypto_list))
for i, (alpaca_sym, yf_sym) in enumerate(crypto_list):
    price, chg, chgpct = get_quick_price(yf_sym)
    with cols2[i]:
        label = alpaca_sym.replace("/USD", "")
        price_fmt = f"${price:,.2f}" if price > 1 else f"${price:.4f}"
        st.metric(label, price_fmt, f"{chg:+.4f} ({chgpct:+.2f}%)",
                  delta_color="normal" if chg >= 0 else "inverse")

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.markdown("""
<script>
setTimeout(function() { window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)
