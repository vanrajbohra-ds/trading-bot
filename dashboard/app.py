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
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .positive { color: #00c853; font-size: 1.6rem; font-weight: bold; }
    .negative { color: #ff1744; font-size: 1.6rem; font-weight: bold; }
    .neutral  { color: #90caf9; font-size: 1.6rem; font-weight: bold; }
    div[data-testid="stMetricValue"] > div { font-size: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ── Credentials ───────────────────────────────────────────────────────────────
def get_creds():
    # Streamlit Cloud: use st.secrets
    # Local: use .env file
    try:
        return {
            "key":    st.secrets["ALPACA_API_KEY"],
            "secret": st.secrets["ALPACA_SECRET_KEY"],
            "base":   st.secrets.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"),
            "gh_token": st.secrets.get("GITHUB_TOKEN", ""),
            "gh_repo":  st.secrets.get("GITHUB_REPO", "vanrajbohra-ds/trading-bot"),
        }
    except Exception:
        from env_loader import load_env
        load_env()
        return {
            "key":    os.environ.get("ALPACA_API_KEY", ""),
            "secret": os.environ.get("ALPACA_SECRET_KEY", ""),
            "base":   os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"),
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
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
    }
    # Get current file SHA
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
    st.subheader("📋 Watchlist Manager")
    watchlist = get_watchlist()
    st.write("**Current stocks:**")
    for sym in watchlist:
        col1, col2 = st.columns([3, 1])
        col1.write(f"• {sym}")
        if col2.button("✕", key=f"remove_{sym}"):
            new_wl = [s for s in watchlist if s != sym]
            ok, msg = save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            if ok:
                st.success(f"Removed {sym}")
                st.cache_data.clear()
                st.rerun()
            else:
                # Save locally if no GitHub
                path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
                with open(path, "w") as f:
                    json.dump(new_wl, f)
                st.success(f"Removed {sym} (local only)")
                st.cache_data.clear()
                st.rerun()

    new_sym = st.text_input("Add symbol (e.g. GOOGL)", max_chars=10).upper().strip()
    if st.button("➕ Add Stock", use_container_width=True):
        if new_sym and new_sym not in watchlist:
            new_wl = watchlist + [new_sym]
            ok, msg = save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
            with open(path, "w") as f:
                json.dump(new_wl, f)
            st.success(f"Added {new_sym}")
            st.cache_data.clear()
            st.rerun()
        elif new_sym in watchlist:
            st.warning(f"{new_sym} already in watchlist")

    st.divider()
    st.caption("Auto-refreshes every 30 seconds")

# ── Main content ───────────────────────────────────────────────────────────────
st.title("📈 Trading Bot Dashboard")
st.caption(f"Paper Trading • Last updated: {datetime.now().strftime('%b %d, %Y %I:%M %p')}")

account  = get_account()
positions = get_positions()
orders   = get_orders()

portfolio_value  = float(account.get("portfolio_value", 0))
cash             = float(account.get("cash", 0))
starting_capital = 100_000.0
total_pnl        = portfolio_value - starting_capital
total_pnl_pct    = (total_pnl / starting_capital) * 100

# ── Closed trades P&L ─────────────────────────────────────────────────────────
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

trade_pnls   = [calc_trade_pnl(o, filled_orders) for o in closed_sells]
wins         = [p for p in trade_pnls if p > 0]
losses       = [p for p in trade_pnls if p <= 0]
win_rate     = (len(wins) / len(trade_pnls) * 100) if trade_pnls else 0
profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")

# ── Row 1: Key metrics ─────────────────────────────────────────────────────────
st.subheader("Portfolio Overview")
c1, c2, c3, c4, c5, c6 = st.columns(6)

pnl_color  = "normal" if total_pnl >= 0 else "inverse"
c1.metric("Portfolio Value",   f"${portfolio_value:,.2f}")
c2.metric("Cash Available",    f"${cash:,.2f}")
c3.metric("Total P&L",         f"${total_pnl:+,.2f}", f"{total_pnl_pct:+.2f}%", delta_color=pnl_color)
c4.metric("Open Positions",    len([p for p in positions if isinstance(p, dict)]))
c5.metric("Win Rate",          f"{win_rate:.1f}%",    f"{len(wins)}W / {len(losses)}L")
c6.metric("Profit Factor",     f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞")

st.divider()

# ── Row 2: Portfolio chart + positions ────────────────────────────────────────
col_chart, col_pos = st.columns([3, 2])

with col_chart:
    st.subheader("📊 Portfolio Performance")
    history = get_portfolio_history(period="1M", timeframe="1D")
    timestamps = history.get("timestamp", [])
    equity     = history.get("equity", [])

    if timestamps and equity:
        df_hist = pd.DataFrame({
            "date":  [datetime.fromtimestamp(t) for t in timestamps],
            "value": equity,
        })
        df_hist["pnl"]   = df_hist["value"] - starting_capital
        df_hist["color"] = df_hist["pnl"].apply(lambda x: "#00c853" if x >= 0 else "#ff1744")

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
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Portfolio history will appear after the first trading day.")

with col_pos:
    st.subheader("🏦 Open Positions")
    if positions and isinstance(positions[0], dict):
        rows = []
        for p in positions:
            qty       = float(p.get("qty", 0))
            entry     = float(p.get("avg_entry_price", 0))
            cur       = float(p.get("current_price") or entry)
            mkt_val   = float(p.get("market_value", 0))
            unreal_pl = float(p.get("unrealized_pl", 0))
            unreal_pct= float(p.get("unrealized_plpc", 0)) * 100
            stop      = entry * 0.93
            target    = entry * 1.15
            rows.append({
                "Symbol":    p["symbol"],
                "Shares":    int(qty),
                "Entry":     f"${entry:.2f}",
                "Current":   f"${cur:.2f}",
                "Mkt Value": f"${mkt_val:,.0f}",
                "P&L":       f"${unreal_pl:+,.2f}",
                "P&L %":     f"{unreal_pct:+.2f}%",
                "Stop":      f"${stop:.2f}",
                "Target":    f"${target:.2f}",
            })
        df_pos = pd.DataFrame(rows)

        def color_pnl(val):
            color = "#00c853" if val.startswith("+") else "#ff1744"
            return f"color: {color}"

        styled = df_pos.style.applymap(color_pnl, subset=["P&L", "P&L %"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")

st.divider()

# ── Row 3: P&L by stock + trade history ───────────────────────────────────────
col_breakdown, col_history = st.columns([2, 3])

with col_breakdown:
    st.subheader("💰 P&L by Stock")
    if positions and isinstance(positions[0], dict):
        syms = [p["symbol"] for p in positions]
        pnls = [float(p.get("unrealized_pl", 0)) for p in positions]
        colors = ["#00c853" if v >= 0 else "#ff1744" for v in pnls]
        fig2 = go.Figure(go.Bar(
            x=syms, y=pnls,
            marker_color=colors,
            text=[f"${v:+,.0f}" for v in pnls],
            textposition="outside",
            hovertemplate="%{x}: $%{y:+,.2f}<extra></extra>",
        ))
        fig2.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="white"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)",
                       color="white", tickformat="$,.0f"),
            height=260,
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Closed trade P&L by stock
        if closed_sells:
            sell_syms  = [o["symbol"] for o in closed_sells]
            sell_pnls  = trade_pnls
            df_closed = pd.DataFrame({"symbol": sell_syms, "pnl": sell_pnls})
            df_closed = df_closed.groupby("symbol")["pnl"].sum().reset_index()
            st.caption("Closed trade P&L by stock:")
            for _, row in df_closed.iterrows():
                color = "🟢" if row["pnl"] >= 0 else "🔴"
                st.write(f"{color} **{row['symbol']}**: ${row['pnl']:+,.2f}")
    else:
        st.info("No position data yet.")

with col_history:
    st.subheader("📜 Trade History")
    if filled_orders:
        rows = []
        for o in filled_orders[:50]:
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
            rows.append({
                "Date":   filled_at,
                "Symbol": o.get("symbol", ""),
                "Action": side,
                "Shares": int(qty),
                "Price":  f"${price:.2f}",
                "Value":  f"${qty * price:,.2f}",
                "Status": o.get("status", "").title(),
            })
        df_hist2 = pd.DataFrame(rows)

        def color_action(val):
            return "color: #00c853" if val == "BUY" else "color: #ff1744"

        styled2 = df_hist2.style.applymap(color_action, subset=["Action"])
        st.dataframe(styled2, use_container_width=True, hide_index=True, height=280)
    else:
        st.info("No trade history yet.")

st.divider()

# ── Row 4: Success metrics ─────────────────────────────────────────────────────
st.subheader("🎯 Success Metrics")
m1, m2, m3, m4, m5 = st.columns(5)

total_trades  = len(filled_orders)
total_closed  = len(closed_sells)
total_won_amt = sum(wins)
total_lost_amt= abs(sum(losses)) if losses else 0
best_trade    = max(trade_pnls) if trade_pnls else 0
worst_trade   = min(trade_pnls) if trade_pnls else 0
avg_win       = sum(wins) / len(wins) if wins else 0
avg_loss      = sum(losses) / len(losses) if losses else 0

m1.metric("Total Orders",    total_trades)
m2.metric("Closed Trades",   total_closed)
m3.metric("Best Trade",      f"${best_trade:+,.2f}")
m4.metric("Worst Trade",     f"${worst_trade:+,.2f}")
m5.metric("Avg Win / Loss",  f"${avg_win:+,.0f} / ${avg_loss:+,.0f}")

# Weekly return estimate
weekly_return = (portfolio_value / starting_capital - 1) * 100
target_weekly = 30.0
progress = min(weekly_return / target_weekly * 100, 100) if weekly_return > 0 else 0

st.divider()
st.subheader("🎯 Weekly Target Progress (30%)")
col_prog, col_num = st.columns([4, 1])
col_prog.progress(int(progress))
col_num.metric("Return", f"{weekly_return:+.2f}%", f"Target: {target_weekly:.0f}%",
               delta_color="normal" if weekly_return >= 0 else "inverse")

# ── Row 5: Watchlist stock cards ───────────────────────────────────────────────
st.divider()
st.subheader("📡 Watchlist Live Prices")
watchlist = get_watchlist()
cols = st.columns(len(watchlist))

@st.cache_data(ttl=60)
def get_quick_price(symbol):
    try:
        t = yf.Ticker(symbol)
        h = t.history(period="2d")
        if len(h) >= 2:
            prev  = h["Close"].iloc[-2]
            cur   = h["Close"].iloc[-1]
            chg   = cur - prev
            chgpct= chg / prev * 100
            return cur, chg, chgpct
        return 0, 0, 0
    except Exception:
        return 0, 0, 0

for i, sym in enumerate(watchlist):
    price, chg, chgpct = get_quick_price(sym)
    with cols[i]:
        delta_color = "normal" if chg >= 0 else "inverse"
        st.metric(sym, f"${price:.2f}", f"{chg:+.2f} ({chgpct:+.2f}%)", delta_color=delta_color)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.markdown("""
<script>
setTimeout(function() { window.location.reload(); }, 30000);
</script>
""", unsafe_allow_html=True)
