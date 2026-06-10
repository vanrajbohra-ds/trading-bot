import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timezone, timedelta
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Trading Bot", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

# Auto-refresh every 30 s — clears cache so API calls re-fire
_refresh_count = st_autorefresh(interval=10_000, limit=None, key="autorefresh")

st.markdown("""<style>
    .block-container{padding-top:1.5rem!important;padding-bottom:.5rem!important}
    div[data-testid="stMetricValue"]>div{font-size:1.05rem!important}
    div[data-testid="stMetricDelta"]>div{font-size:.68rem!important}
    div[data-testid="stMetricLabel"] p{font-size:.72rem!important;color:#aaa!important}
    .stTabs [data-baseweb="tab-list"]{gap:3px}
    .stTabs [data-baseweb="tab"]{padding:4px 14px;font-size:.85rem}
    hr{margin:.3rem 0!important}
    div[data-testid="stRadio"] label{font-size:.82rem}
</style>""", unsafe_allow_html=True)

CRYPTO_SYMBOLS = {"BTC/USD", "SOL/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "UNI/USD"}
CRYPTO_YF_MAP  = {"BTC/USD": "BTC-USD", "SOL/USD": "SOL-USD",
                  "DOGE/USD": "DOGE-USD", "AVAX/USD": "AVAX-USD"}
_CRYPTO_NORM   = {
    "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD",
    "DOGEUSD": "DOGE/USD", "AVAXUSD": "AVAX/USD", "LTCUSD": "LTC/USD",
    "LINKUSD": "LINK/USD", "UNIUSD": "UNI/USD",
}

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
        from env_loader import load_env; load_env()
        return {
            "key":      os.environ.get("ALPACA_API_KEY", ""),
            "secret":   os.environ.get("ALPACA_SECRET_KEY", ""),
            "base":     os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2"),
            "gh_token": os.environ.get("GITHUB_TOKEN", ""),
            "gh_repo":  os.environ.get("GITHUB_REPO", "vanrajbohra-ds/trading-bot"),
        }

creds   = get_creds()
HEADERS = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"],
           "Content-Type": "application/json"}
BASE    = creds["base"].rstrip("/")

# ── Data fetchers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_account():
    r = requests.get(f"{BASE}/account", headers=HEADERS, timeout=10)
    return r.json()

@st.cache_data(ttl=30)
def get_positions():
    r = requests.get(f"{BASE}/positions", headers=HEADERS, timeout=10)
    if not r.ok: return []
    raw = r.json()
    for p in raw:
        if isinstance(p, dict):
            p["symbol"] = _CRYPTO_NORM.get(p["symbol"], p["symbol"])
    return raw

@st.cache_data(ttl=60)
def get_orders(status="all", limit=200):
    r = requests.get(f"{BASE}/orders", headers=HEADERS,
                     params={"status": status, "limit": limit, "direction": "desc"}, timeout=10)
    return r.json() if r.ok else []

@st.cache_data(ttl=300)
def get_portfolio_history():
    r = requests.get(f"{BASE}/account/portfolio/history", headers=HEADERS,
                     params={"period": "1M", "timeframe": "1D", "extended_hours": False}, timeout=10)
    return r.json() if r.ok else {}

@st.cache_data(ttl=60)
def get_orders_report():
    """Fetch up to 500 filled orders for the Reports tab."""
    r = requests.get(f"{BASE}/orders", headers=HEADERS,
                     params={"status": "filled", "limit": 500, "direction": "desc"}, timeout=15)
    if not r.ok:
        return []
    raw = r.json()
    for o in (raw if isinstance(raw, list) else []):
        if isinstance(o, dict):
            o["symbol"] = _CRYPTO_NORM.get(o["symbol"], o["symbol"])
    return raw if isinstance(raw, list) else []

@st.cache_data(ttl=60)
def get_watchlist():
    path = os.path.join(os.path.dirname(__file__), "..", "watchlist.json")
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

@st.cache_data(ttl=60)
def get_quick_price(symbol):
    try:
        h = yf.Ticker(symbol).history(period="2d")
        if len(h) >= 2:
            prev, cur = h["Close"].iloc[-2], h["Close"].iloc[-1]
            chg = cur - prev
            return cur, chg, chg / prev * 100
    except Exception: pass
    return 0, 0, 0

def save_watchlist_github(new_list, gh_token, gh_repo):
    if not gh_token: return False, "No GitHub token"
    hdrs = {"Authorization": f"token {gh_token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/repos/{gh_repo}/contents/watchlist.json",
                     headers=hdrs, timeout=10)
    if not r.ok: return False, r.text
    import base64
    sha     = r.json()["sha"]
    content = base64.b64encode(json.dumps(new_list, indent=2).encode()).decode()
    r = requests.put(f"https://api.github.com/repos/{gh_repo}/contents/watchlist.json",
                     headers=hdrs,
                     json={"message": f"update watchlist: {new_list}", "content": content, "sha": sha},
                     timeout=10)
    return r.ok, r.text

# ── Shared style helpers ──────────────────────────────────────────────────────
def _style_pnl(val):
    return f"color: {'#00c853' if '+' in str(val) else '#ff1744'}"

def _vol_fmt(v):
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000:     return f"{v/1_000:.0f}K"
    return str(v)

def _cap_fmt(v):
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.0f}M"
    return "—"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Controls")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.subheader("📋 Watchlist")
    _wl = get_watchlist()
    for sym in _wl:
        c1, c2 = st.columns([3, 1])
        c1.write(f"• {sym}")
        if c2.button("✕", key=f"rm_{sym}"):
            new_wl = [s for s in _wl if s != sym]
            save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            with open(os.path.join(os.path.dirname(__file__), "..", "watchlist.json"), "w") as f:
                json.dump(new_wl, f)
            st.cache_data.clear(); st.rerun()
    new_sym = st.text_input("Add symbol", max_chars=10).upper().strip()
    if st.button("➕ Add", use_container_width=True):
        if new_sym and new_sym not in _wl:
            new_wl = _wl + [new_sym]
            save_watchlist_github(new_wl, creds["gh_token"], creds["gh_repo"])
            with open(os.path.join(os.path.dirname(__file__), "..", "watchlist.json"), "w") as f:
                json.dump(new_wl, f)
            st.cache_data.clear(); st.rerun()
    st.caption("Crypto (BTC/SOL/DOGE/AVAX) fixed in config.py")

# ── Load data ─────────────────────────────────────────────────────────────────
account   = get_account()
positions = get_positions()
orders    = get_orders()
watchlist = get_watchlist()

portfolio_value  = float(account.get("portfolio_value", 0))
cash             = float(account.get("cash", 0))
STARTING_CAP     = 100_000.0
total_pnl        = portfolio_value - STARTING_CAP
total_pnl_pct    = total_pnl / STARTING_CAP * 100

stock_pos  = [p for p in positions if isinstance(p, dict) and p.get("symbol", "") not in CRYPTO_SYMBOLS]
crypto_pos = [p for p in positions if isinstance(p, dict) and p.get("symbol", "") in CRYPTO_SYMBOLS]
stock_val  = sum(float(p.get("market_value", 0)) for p in stock_pos)
crypto_val = sum(float(p.get("market_value", 0)) for p in crypto_pos)
stock_pnl  = sum(float(p.get("unrealized_pl", 0)) for p in stock_pos)
crypto_pnl = sum(float(p.get("unrealized_pl", 0)) for p in crypto_pos)

filled = [o for o in orders if o.get("status") == "filled"]
sells  = [o for o in filled if o.get("side") == "sell"]

def _calc_trade_pnl(sell_o, all_o):
    sym  = sell_o["symbol"]
    qty  = float(sell_o.get("filled_qty", 0))
    sp   = float(sell_o.get("filled_avg_price") or 0)
    buys = [o for o in all_o if o["symbol"] == sym and o["side"] == "buy"
            and o["status"] == "filled" and o["filled_at"] < sell_o["filled_at"]]
    if not buys: return 0
    return (sp - sum(float(b.get("filled_avg_price") or 0) for b in buys) / len(buys)) * qty

trade_pnls  = [_calc_trade_pnl(o, filled) for o in sells]
wins        = [p for p in trade_pnls if p > 0]
losses      = [p for p in trade_pnls if p <= 0]
win_rate    = len(wins) / len(trade_pnls) * 100 if trade_pnls else 0
pf          = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
weekly_ret  = (portfolio_value / STARTING_CAP - 1) * 100

# Config
try:
    from config import (WATCHLIST as _CORE_STOCKS, CRYPTO_WATCHLIST as _CORE_CRYPTO,
                        MOMENTUM_CRYPTO_UNIVERSE as _MOMENTUM_CRYPTO,
                        MOMENTUM_STOCK_STOP_PCT, MOMENTUM_STOCK_TAKE_PCT,
                        MOMENTUM_CRYPTO_STOP_PCT, MOMENTUM_CRYPTO_TAKE_PCT,
                        MOMENTUM_TOTAL_BUDGET_PCT)
    _CORE_SYMS = set(_CORE_STOCKS) | set(_CORE_CRYPTO)
except Exception:
    _CORE_SYMS = set()
    MOMENTUM_STOCK_STOP_PCT  = 0.04; MOMENTUM_STOCK_TAKE_PCT  = 0.08
    MOMENTUM_CRYPTO_STOP_PCT = 0.06; MOMENTUM_CRYPTO_TAKE_PCT = 0.12
    MOMENTUM_TOTAL_BUDGET_PCT = 0.10; _MOMENTUM_CRYPTO = ["DOGE/USD","AVAX/USD","LINK/USD","UNI/USD"]

mom_pos      = [p for p in positions if isinstance(p, dict)
                and p.get("symbol", "") not in _CORE_SYMS and float(p.get("qty", 0)) != 0]
mom_val_used = sum(float(p.get("market_value", 0)) for p in mom_pos)
mom_budget   = portfolio_value * MOMENTUM_TOTAL_BUDGET_PCT

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([5, 1])
h1.markdown("### 📈 Trading Bot &nbsp; <span style='font-size:.8rem;color:#888'>Paper Trading</span>",
            unsafe_allow_html=True)
h2.caption(f"Updated: {datetime.now().strftime('%b %d %I:%M %p')}")

# ── KPI strip (8 metrics) ─────────────────────────────────────────────────────
k = st.columns(8)
k[0].metric("Portfolio",     f"${portfolio_value:,.0f}")
k[1].metric("Cash",          f"${cash:,.0f}")
k[2].metric("Total P&L",     f"${total_pnl:+,.0f}", f"{total_pnl_pct:+.1f}%",
            delta_color="normal" if total_pnl >= 0 else "inverse")
k[3].metric("Positions",     len(positions))
k[4].metric("Win Rate",      f"{win_rate:.0f}%", f"{len(wins)}W / {len(losses)}L")
k[5].metric("Profit Factor", f"{pf:.2f}" if pf != float("inf") else "∞")
k[6].metric("Weekly Return", f"{weekly_ret:+.1f}%",
            delta_color="normal" if weekly_ret >= 0 else "inverse")
k[7].metric("Momentum Used", f"${mom_val_used:,.0f}", f"of ${mom_budget:,.0f}")

st.divider()

# ── Main tabs ─────────────────────────────────────────────────────────────────
t_ov, t_pos, t_mom, t_hist, t_rep, t_px = st.tabs(
    ["📊 Overview", "💼 Positions", "🚀 Momentum", "📜 History", "📋 Reports", "📡 Prices"]
)

# ════════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ════════════════════════════════════════════════════════════════════════════════
with t_ov:
    col_chart, col_pie = st.columns([6, 4])

    with col_chart:
        hist_data  = get_portfolio_history()
        timestamps = hist_data.get("timestamp", [])
        equity     = hist_data.get("equity", [])
        if timestamps and equity:
            df_h = pd.DataFrame({
                "date":  [datetime.fromtimestamp(t) for t in timestamps],
                "value": [v for v in equity],
            })
            # Drop leading zeros/nulls that Alpaca pads before trading started
            df_h = df_h[df_h["value"] > 0]

            # Zoom y-axis to actual range so small moves are visible
            lo = min(df_h["value"].min(), STARTING_CAP)
            hi = max(df_h["value"].max(), STARTING_CAP)
            pad = max((hi - lo) * 0.15, 200)   # at least $200 padding
            y_min = lo - pad
            y_max = hi + pad

            # Green above baseline, red below — use two filled areas
            above = df_h["value"].clip(lower=STARTING_CAP)
            below = df_h["value"].clip(upper=STARTING_CAP)

            fig = go.Figure()
            # Red fill below $100K
            fig.add_trace(go.Scatter(
                x=df_h["date"], y=below, fill="tozeroy",
                fillcolor="rgba(255,23,68,0.0)", line=dict(width=0),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=df_h["date"], y=below,
                fill="tonexty", fillcolor="rgba(255,23,68,0.15)",
                line=dict(width=0), hoverinfo="skip", showlegend=False,
            ))
            # Green fill above $100K
            fig.add_trace(go.Scatter(
                x=df_h["date"], y=[STARTING_CAP] * len(df_h),
                line=dict(width=0), hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=df_h["date"], y=above,
                fill="tonexty", fillcolor="rgba(0,200,83,0.2)",
                line=dict(width=0), hoverinfo="skip", showlegend=False,
            ))
            # Main value line
            fig.add_trace(go.Scatter(
                x=df_h["date"], y=df_h["value"],
                line=dict(color="#00c853", width=2),
                hovertemplate="<b>%{x|%b %d}</b><br>$%{y:,.2f}<extra></extra>",
                showlegend=False,
            ))
            fig.add_hline(y=STARTING_CAP, line_dash="dash",
                          line_color="rgba(255,255,255,0.35)",
                          annotation_text="$100K start",
                          annotation_font_color="rgba(255,255,255,0.5)")
            fig.update_layout(
                title=dict(text="Portfolio Performance", font=dict(color="white", size=13)),
                margin=dict(l=0, r=0, t=30, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, color="white"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)",
                           color="white", tickformat="$,.0f",
                           range=[y_min, y_max]),
                height=215, hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Portfolio history will appear after the first trading day.")

    with col_pie:
        total_invested = stock_val + crypto_val + cash
        if total_invested > 0:
            fig_pie = go.Figure(go.Pie(
                labels=["📈 Stocks", "🔗 Crypto", "💰 Cash"],
                values=[stock_val, crypto_val, cash],
                marker=dict(colors=["#00c853", "#7c4dff", "#90caf9"]),
                hole=0.5, textinfo="label+percent", textfont=dict(size=11),
                hovertemplate="%{label}: $%{value:,.0f}<extra></extra>", sort=False,
            ))
            fig_pie.update_layout(
                title=dict(text="Allocation", font=dict(color="white", size=13)),
                margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(font=dict(color="white", size=10), orientation="h",
                            yanchor="bottom", y=-0.15),
                height=215, showlegend=True,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # Combined P&L bar — all open positions
    all_pos = stock_pos + crypto_pos
    if all_pos:
        syms   = [p["symbol"] for p in all_pos]
        pnls   = [float(p.get("unrealized_pl", 0)) for p in all_pos]
        colors = ["#00c853" if v >= 0 else "#ff1744" for v in pnls]
        labels = [f"{'🔗' if s in CRYPTO_SYMBOLS else '📈'} {s}" for s in syms]
        fig_pnl = go.Figure(go.Bar(
            x=labels, y=pnls, marker_color=colors,
            text=[f"${v:+,.0f}" for v in pnls], textposition="outside",
            hovertemplate="%{x}: $%{y:+,.2f}<extra></extra>",
        ))
        fig_pnl.update_layout(
            title=dict(text="Unrealized P&L by Position", font=dict(color="white", size=12)),
            margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="white"), yaxis=dict(showgrid=True,
            gridcolor="rgba(255,255,255,0.1)", color="white", tickformat="$,.0f"),
            height=165, showlegend=False,
        )
        st.plotly_chart(fig_pnl, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# POSITIONS
# ════════════════════════════════════════════════════════════════════════════════
with t_pos:
    sc = st.columns(5)
    sc[0].metric("📈 Stock Value",  f"${stock_val:,.0f}", f"P&L ${stock_pnl:+,.0f}")
    sc[1].metric("🔗 Crypto Value", f"${crypto_val:,.0f}", f"P&L ${crypto_pnl:+,.0f}")
    sc[2].metric("💰 Cash",         f"${cash:,.0f}")
    sc[3].metric("Stock Count",     len(stock_pos))
    sc[4].metric("Crypto Count",    len(crypto_pos))

    def _build_pos_rows(pos_list, is_crypto):
        rows = []
        stop_pct = 0.12 if is_crypto else 0.07
        take_pct = 0.25 if is_crypto else 0.15
        for p in pos_list:
            qty   = float(p.get("qty", 0))
            entry = float(p.get("avg_entry_price", 0))
            cur   = float(p.get("current_price") or entry)
            mv    = float(p.get("market_value", 0))
            upl   = float(p.get("unrealized_pl", 0))
            uppc  = float(p.get("unrealized_plpc", 0)) * 100
            fmt   = lambda v, c=is_crypto: (f"${v:.4f}" if c else f"${v:.2f}")
            rows.append({
                "Type":    "🔗" if is_crypto else "📈",
                "Symbol":  p["symbol"],
                "Units":   f"{qty:.4f}" if is_crypto else str(int(qty)),
                "Entry":   fmt(entry),
                "Current": fmt(cur),
                "Mkt Val": f"${mv:,.2f}",
                "P&L $":   f"${upl:+,.2f}",
                "P&L %":   f"{uppc:+.2f}%",
                "Stop":    fmt(entry * (1 - stop_pct)),
                "Target":  fmt(entry * (1 + take_pct)),
            })
        return rows

    all_rows = _build_pos_rows(stock_pos, False) + _build_pos_rows(crypto_pos, True)
    if all_rows:
        df_pos = pd.DataFrame(all_rows)
        st.dataframe(df_pos.style.map(_style_pnl, subset=["P&L $", "P&L %"]),
                     use_container_width=True, hide_index=True, height=380)
    else:
        st.info("No open positions — bot is scanning for entry signals.")

# ════════════════════════════════════════════════════════════════════════════════
# MOMENTUM
# ════════════════════════════════════════════════════════════════════════════════
with t_mom:
    mb = st.columns(4)
    mb[0].metric("Budget",          f"${mom_budget:,.0f}", f"{MOMENTUM_TOTAL_BUDGET_PCT*100:.0f}% of portfolio")
    mom_pct_used = mom_val_used / mom_budget * 100 if mom_budget > 0 else 0
    mb[1].metric("Used",            f"${mom_val_used:,.0f}", f"{mom_pct_used:.0f}%",
                 delta_color="inverse" if mom_pct_used > 80 else "normal")
    mb[2].metric("Remaining",       f"${max(0, mom_budget - mom_val_used):,.0f}")
    mb[3].metric("Open Positions",  len(mom_pos))

    sub = st.radio("", ["🔍 Live Screener", "📡 Signal Filter", "📊 Open Positions", "📜 Trades"],
                   horizontal=True, label_visibility="collapsed")

    @st.cache_data(ttl=120)
    def _get_screener():
        try:
            from execution.market_scanner import get_screener_quotes
            return get_screener_quotes(limit_per_screen=15, exclude=_CORE_SYMS)
        except Exception as e:
            return {"actives": [], "gainers": [], "error": str(e)}

    @st.cache_data(ttl=60)
    def _check_signal(symbol):
        try:
            df = yf.Ticker(symbol).history(period="3mo")
            if df.empty or len(df) < 26:
                return {"pass": False, "rsi": None, "vol_ratio": None, "macd_hist": None}
            close  = df["Close"]; volume = df["Volume"]
            vr     = float(volume.iloc[-1] / volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else 0
            delta  = close.diff()
            gain   = delta.clip(lower=0).rolling(14).mean()
            loss   = (-delta.clip(upper=0)).rolling(14).mean()
            rs     = gain / loss.replace(0, float("nan"))
            rsi    = float(100 - 100 / (1 + rs.iloc[-1]))
            ema12  = close.ewm(span=12, adjust=False).mean()
            ema26  = close.ewm(span=26, adjust=False).mean()
            ml     = ema12 - ema26
            mh     = float((ml - ml.ewm(span=9, adjust=False).mean()).iloc[-1])
            chks   = [vr >= 1.8, 55 <= rsi <= 75, mh > 0]
            return {"pass": sum(chks) >= 2, "checks": sum(chks),
                    "vol_ratio": round(vr, 2), "rsi": round(rsi, 1), "macd_hist": round(mh, 4),
                    "vol_ok": vr >= 1.8, "rsi_ok": 55 <= rsi <= 75, "macd_ok": mh > 0}
        except Exception:
            return {"pass": False, "rsi": None, "vol_ratio": None, "macd_hist": None}

    if sub == "🔍 Live Screener":
        sdata = _get_screener()
        if sdata.get("error"):
            st.warning(f"Screener unavailable: {sdata['error']}")
        col_act, col_gain = st.columns(2)

        def _screener_tbl(quotes, title, col):
            with col:
                st.caption(title)
                if not quotes: st.info("No data."); return
                rows = [{"Sym": q["symbol"],
                         "Price": f"${q['price']:,.2f}",
                         "Chg":   f"{q['change_pct']:+.2f}%",
                         "Vol×":  f"{q['volume_ratio']:.1f}×",
                         "MCap":  _cap_fmt(q["market_cap"])} for q in quotes[:12]]
                df = pd.DataFrame(rows)
                def _cc(v): return "color:#00c853" if "+" in str(v) else "color:#ff1744"
                def _cv(v):
                    try:
                        x = float(v.replace("×", ""))
                        if x >= 2.0: return "color:#ff9800;font-weight:bold"
                        if x >= 1.5: return "color:#ffeb3b"
                    except Exception: pass
                    return ""
                st.dataframe(df.style.map(_cc, subset=["Chg"]).map(_cv, subset=["Vol×"]),
                             use_container_width=True, hide_index=True, height=370)

        _screener_tbl(sdata.get("actives", []), "⚡ Most Active by Volume", col_act)
        _screener_tbl(sdata.get("gainers", []), "📈 Top Gainers Today", col_gain)
        st.caption("🟠 Vol× ≥ 2.0 = unusually high  ·  Cached 2 min")

    elif sub == "📡 Signal Filter":
        sdata = _get_screener()
        _all  = {q["symbol"]: q for q in sdata.get("actives", []) + sdata.get("gainers", [])}
        candidates = list(_all.values())[:20]
        if not candidates:
            st.info("No screener data — check Live Screener first.")
        else:
            with st.spinner(f"Running pre-filter on {len(candidates)} symbols…"):
                sig_rows = []
                for q in candidates:
                    s = _check_signal(q["symbol"])
                    sig_rows.append({
                        "Symbol": q["symbol"], "Price": f"${q['price']:,.2f}",
                        "Chg":    f"{q['change_pct']:+.2f}%", "Vol×": f"{q['volume_ratio']:.1f}×",
                        "RSI":    f"{s['rsi']:.1f}" if s.get("rsi") else "—",
                        "MACD":   f"{s['macd_hist']:+.4f}" if s.get("macd_hist") is not None else "—",
                        "Vol✓":   "✅" if s.get("vol_ok") else "❌",
                        "RSI✓":   "✅" if s.get("rsi_ok") else "❌",
                        "MACD✓":  "✅" if s.get("macd_ok") else "❌",
                        "Score":  f"{s.get('checks', 0)}/3",
                        "Signal": "🟢 PASS" if s.get("pass") else "⛔ SKIP",
                    })
            df_sig = pd.DataFrame(sig_rows)
            def _csig(v):
                if "PASS" in str(v): return "color:#00c853;font-weight:bold"
                if "SKIP" in str(v): return "color:#555"
                return ""
            st.dataframe(df_sig.style.map(_csig, subset=["Signal"]),
                         use_container_width=True, hide_index=True, height=420)
            passed = sum(1 for r in sig_rows if "PASS" in r["Signal"])
            st.caption(f"**{passed}/{len(sig_rows)}** pass pre-filter → eligible for LLM decision")

    elif sub == "📊 Open Positions":
        if not mom_pos:
            st.info("No open momentum positions. Hunter is scanning for setups…")
        else:
            prows = []
            for p in mom_pos:
                sym  = p["symbol"]; is_c = "/" in sym
                qty  = float(p.get("qty", 0))
                en   = float(p.get("avg_entry_price", 0))
                cur  = float(p.get("current_price") or en)
                mv   = float(p.get("market_value", 0))
                upl  = float(p.get("unrealized_pl", 0))
                uppc = float(p.get("unrealized_plpc", 0)) * 100
                sp   = MOMENTUM_CRYPTO_STOP_PCT if is_c else MOMENTUM_STOCK_STOP_PCT
                tp   = MOMENTUM_CRYPTO_TAKE_PCT if is_c else MOMENTUM_STOCK_TAKE_PCT
                sl   = en * (1 - sp); tl = en * (1 + tp); rng = tl - sl
                pct  = int(max(0, min(100, (cur - sl) / rng * 100))) if rng > 0 else 50
                fmt  = lambda v, c=is_c: (f"${v:.4f}" if c else f"${v:.2f}")
                stat = ("🔴 NEAR STOP" if cur <= sl * 1.01 else
                        "🟡 NEAR TARGET" if cur >= tl * 0.98 else "🟢 SAFE")
                prows.append({"Type": "🔗" if is_c else "📈", "Symbol": sym,
                              "Units": f"{qty:.4f}" if is_c else str(int(qty)),
                              "Mkt Val": f"${mv:,.2f}", "P&L $": f"${upl:+,.2f}",
                              "P&L %": f"{uppc:+.2f}%", "Stop": fmt(sl), "Target": fmt(tl),
                              "_pct": pct, "Status": stat})

            disp = [c for c in prows[0] if c != "_pct"]
            df_m = pd.DataFrame(prows)
            def _sstat(v):
                if "SAFE" in str(v): return "color:#00c853"
                if "TARGET" in str(v): return "color:#ff9800"
                return "color:#ff1744"
            st.dataframe(df_m[disp].style
                         .map(_style_pnl, subset=["P&L $", "P&L %"])
                         .map(_sstat, subset=["Status"]),
                         use_container_width=True, hide_index=True)
            st.caption("Stop → Target progress:")
            for r in prows:
                pct  = r["_pct"]
                col  = "#ff1744" if pct < 20 else ("#ff9800" if pct > 80 else "#00c853")
                bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)
                st.markdown(
                    f"`{r['Symbol']}` "
                    f"<span style='color:#888;font-size:.8rem'>{r['Stop']}</span> "
                    f"`{bar}` "
                    f"<span style='color:#888;font-size:.8rem'>{r['Target']}</span>"
                    f"&nbsp;<span style='color:{col}'>{r['P&L %']}</span>",
                    unsafe_allow_html=True)

    else:  # Trades
        mom_orders = [o for o in filled if o.get("symbol", "") not in _CORE_SYMS]
        if not mom_orders:
            st.info("No momentum trades yet.")
        else:
            mom_buys = [o for o in mom_orders if o.get("side") == "buy"]
            hrows = []
            for o in mom_orders[:120]:
                sym = o.get("symbol", ""); is_c = "/" in sym
                fa  = o.get("filled_at", "")
                try:
                    fa = datetime.fromisoformat(fa.replace("Z", "+00:00")).strftime("%b %d %H:%M")
                except Exception: pass
                qty   = float(o.get("filled_qty", 0))
                price = float(o.get("filled_avg_price") or 0)
                side  = o.get("side", "").upper()
                pnl_s = "—"
                if side == "SELL":
                    pb = [b for b in mom_buys if b["symbol"] == sym
                          and b.get("filled_at", "") < o.get("filled_at", "")]
                    if pb:
                        ab  = sum(float(b.get("filled_avg_price") or 0) for b in pb) / len(pb)
                        pnl_s = f"${(price - ab) * qty:+,.2f}"
                hrows.append({"Date": fa, "Symbol": sym, "Type": "🔗" if is_c else "📈",
                              "Side": side,
                              "Units": f"{qty:.4f}" if is_c else str(int(qty)),
                              "Price": f"${price:.4f}" if is_c else f"${price:.2f}",
                              "Value": f"${qty * price:,.2f}", "P&L": pnl_s})
            df_mh = pd.DataFrame(hrows)
            def _cs(v): return "color:#00c853" if v == "BUY" else "color:#ff1744"
            def _cp(v):
                if "+" in str(v): return "color:#00c853"
                if "-" in str(v): return "color:#ff1744"
                return ""
            st.dataframe(df_mh.style.map(_cs, subset=["Side"]).map(_cp, subset=["P&L"]),
                         use_container_width=True, hide_index=True, height=340)
            tv_buy  = sum(float(o.get("filled_qty",0))*float(o.get("filled_avg_price") or 0)
                         for o in mom_orders if o.get("side")=="buy")
            tv_sell = sum(float(o.get("filled_qty",0))*float(o.get("filled_avg_price") or 0)
                         for o in mom_orders if o.get("side")=="sell")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Total Orders", len(mom_orders))
            mc2.metric("Total Bought", f"${tv_buy:,.0f}")
            mc3.metric("Total Sold",   f"${tv_sell:,.0f}")

# ════════════════════════════════════════════════════════════════════════════════
# HISTORY
# ════════════════════════════════════════════════════════════════════════════════
with t_hist:
    hf1, hf2 = st.columns([3, 1])
    hist_filter = hf1.radio("Show", ["All", "📈 Stocks", "🔗 Crypto"], horizontal=True)
    if hist_filter == "📈 Stocks":
        show_ord = [o for o in filled if o.get("symbol","") not in CRYPTO_SYMBOLS]
    elif hist_filter == "🔗 Crypto":
        show_ord = [o for o in filled if o.get("symbol","") in CRYPTO_SYMBOLS]
    else:
        show_ord = filled
    hf2.metric("Orders", len(show_ord))

    def _hist_df(order_list):
        rows = []
        for o in order_list[:150]:
            sym = o.get("symbol", ""); is_c = sym in CRYPTO_SYMBOLS
            fa  = o.get("filled_at", "")
            try:
                fa = datetime.fromisoformat(fa.replace("Z", "+00:00")).strftime("%b %d %H:%M")
            except Exception: pass
            qty   = float(o.get("filled_qty", 0))
            price = float(o.get("filled_avg_price") or 0)
            rows.append({"Date": fa, "Type": "🔗" if is_c else "📈", "Symbol": sym,
                         "Action": o.get("side","").upper(),
                         "Units":  f"{qty:.4f}" if is_c else str(int(qty)),
                         "Price":  f"${price:.4f}" if is_c else f"${price:.2f}",
                         "Value":  f"${qty * price:,.2f}"})
        return pd.DataFrame(rows)

    df_h = _hist_df(show_ord)
    if not df_h.empty:
        def _ca(v): return "color:#00c853" if v == "BUY" else "color:#ff1744"
        st.dataframe(df_h.style.map(_ca, subset=["Action"]),
                     use_container_width=True, hide_index=True, height=420)
    else:
        st.info("No trade history yet.")

# ════════════════════════════════════════════════════════════════════════════════
# REPORTS
# ════════════════════════════════════════════════════════════════════════════════
with t_rep:
    rep_all = get_orders_report()

    # ── Realized P&L: match sells to prior buys per symbol (chronological) ───
    _buy_history = {}   # sym -> [(qty, price), ...]
    _sell_pnls   = {}   # order_id -> float
    for _o in sorted(rep_all, key=lambda x: x.get("filled_at", "")):
        _sym = _o.get("symbol", ""); _id = _o.get("id", "")
        _qty = float(_o.get("filled_qty", 0))
        _px  = float(_o.get("filled_avg_price") or 0)
        if _o.get("side") == "buy":
            _buy_history.setdefault(_sym, []).append((_qty, _px))
        elif _o.get("side") == "sell" and _buy_history.get(_sym):
            _buys = _buy_history[_sym]
            _tq   = sum(b[0] for b in _buys)
            _ap   = sum(b[0] * b[1] for b in _buys) / _tq if _tq else _px
            _sell_pnls[_id] = (_px - _ap) * _qty

    # ── Summary KPIs ─────────────────────────────────────────────────────────
    def _oval(o):
        return float(o.get("filled_qty", 0)) * float(o.get("filled_avg_price") or 0)

    _r_buys    = [o for o in rep_all if o.get("side") == "buy"]
    _r_sells   = [o for o in rep_all if o.get("side") == "sell"]
    _buy_vol   = sum(_oval(o) for o in _r_buys)
    _sell_vol  = sum(_oval(o) for o in _r_sells)
    _rpnl      = sum(_sell_pnls.values())
    _win_t     = sum(1 for v in _sell_pnls.values() if v > 0)
    _loss_t    = sum(1 for v in _sell_pnls.values() if v <= 0)

    rm = st.columns(6)
    rm[0].metric("Total Buys",   len(_r_buys))
    rm[1].metric("Total Sells",  len(_r_sells))
    rm[2].metric("Vol Bought",   f"${_buy_vol:,.0f}")
    rm[3].metric("Vol Sold",     f"${_sell_vol:,.0f}")
    rm[4].metric("Realized P&L", f"${_rpnl:+,.2f}",
                 delta_color="normal" if _rpnl >= 0 else "inverse")
    rm[5].metric("Closed Trades",f"{_win_t}W / {_loss_t}L")

    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns(4)
    rep_view  = fc1.radio("View",  ["📅 By Day", "📋 All Trades"], horizontal=True,
                          label_visibility="collapsed")
    rep_side  = fc2.radio("Side",  ["All", "BUY only", "SELL only"], horizontal=True,
                          label_visibility="collapsed")
    rep_range = fc3.radio("Range", ["All time", "Last 7 days", "Today"], horizontal=True,
                          label_visibility="collapsed")
    rep_type  = fc4.radio("Type",  ["All", "📈 Stocks", "🔗 Crypto", "🚀 Momentum"],
                          horizontal=True, label_visibility="collapsed")

    # Apply filters
    _now_utc = datetime.now(timezone.utc)

    def _pdt(fa):
        try:    return datetime.fromisoformat(fa.replace("Z", "+00:00"))
        except: return None

    _filtered = list(rep_all)
    if rep_side == "BUY only":
        _filtered = [o for o in _filtered if o.get("side") == "buy"]
    elif rep_side == "SELL only":
        _filtered = [o for o in _filtered if o.get("side") == "sell"]

    if rep_range == "Today":
        _td = _now_utc.date()
        _filtered = [o for o in _filtered
                     if (_pdt(o.get("filled_at", "")) or _now_utc).date() == _td]
    elif rep_range == "Last 7 days":
        _cutoff = _now_utc - timedelta(days=7)
        _filtered = [o for o in _filtered
                     if (_pdt(o.get("filled_at", "")) or _now_utc) >= _cutoff]

    if rep_type == "📈 Stocks":
        _filtered = [o for o in _filtered if "/" not in o.get("symbol", "")]
    elif rep_type == "🔗 Crypto":
        _filtered = [o for o in _filtered if "/" in o.get("symbol", "")]
    elif rep_type == "🚀 Momentum":
        _filtered = [o for o in _filtered if o.get("symbol", "") not in _CORE_SYMS]

    # ── Shared row builder ────────────────────────────────────────────────
    def _rep_row(o, include_date=True):
        dt   = _pdt(o.get("filled_at", ""))
        sym  = o.get("symbol", ""); is_c = "/" in sym
        qty  = float(o.get("filled_qty", 0))
        px   = float(o.get("filled_avg_price") or 0)
        side = o.get("side", "").upper()
        pnl  = _sell_pnls.get(o.get("id", ""), None)
        row  = {}
        if include_date:
            row["Date"] = dt.strftime("%b %d") if dt else "—"
        row["Time"]   = dt.strftime("%H:%M UTC") if dt else "—"
        row["Symbol"] = sym
        row["Type"]   = "🔗" if is_c else "📈"
        row["Side"]   = side
        row["Units"]  = f"{qty:.4f}" if is_c else str(int(qty))
        row["Price"]  = f"${px:.4f}" if is_c else f"${px:.2f}"
        row["Value"]  = f"${qty * px:,.2f}"
        row["P&L"]    = f"${pnl:+,.2f}" if pnl is not None else "—"
        return row

    def _style_rep(df):
        def _cs(v): return "color:#00c853" if v == "BUY" else "color:#ff1744"
        def _cp(v):
            sv = str(v)
            if "$+" in sv: return "color:#00c853"
            if "$-" in sv: return "color:#ff1744"
            return ""
        return df.style.map(_cs, subset=["Side"]).map(_cp, subset=["P&L"])

    if not _filtered:
        st.info("No trades match the current filter.")

    elif rep_view == "📅 By Day":
        # Group by calendar date (API returns desc order already)
        _day_groups = {}
        for _o in _filtered:
            _dt  = _pdt(_o.get("filled_at", ""))
            _key = _dt.strftime("%A, %b %d %Y") if _dt else "Unknown"
            _day_groups.setdefault(_key, []).append(_o)

        for _day_str, _day_orders in _day_groups.items():
            _nb  = sum(1 for o in _day_orders if o.get("side") == "buy")
            _ns  = sum(1 for o in _day_orders if o.get("side") == "sell")
            _dbv = sum(_oval(o) for o in _day_orders if o.get("side") == "buy")
            _dsv = sum(_oval(o) for o in _day_orders if o.get("side") == "sell")
            _dpnl = sum(_sell_pnls.get(o.get("id", ""), 0)
                        for o in _day_orders if o.get("side") == "sell")
            _pnl_tag = f"P&L ${_dpnl:+,.2f}" if _ns > 0 else ""

            with st.expander(
                f"**{_day_str}** — "
                f"🟢 {_nb} buy{'s' if _nb != 1 else ''}  "
                f"🔴 {_ns} sell{'s' if _ns != 1 else ''}  |  "
                f"${_dbv:,.0f} bought  ·  ${_dsv:,.0f} sold"
                + (f"  |  {_pnl_tag}" if _pnl_tag else ""),
                expanded=(_day_str == next(iter(_day_groups))),
            ):
                _rows = [_rep_row(o, include_date=False) for o in _day_orders]
                st.dataframe(_style_rep(pd.DataFrame(_rows)),
                             use_container_width=True, hide_index=True)

    else:  # 📋 All Trades
        _rows = [_rep_row(o) for o in _filtered]
        if _rows:
            st.dataframe(_style_rep(pd.DataFrame(_rows)),
                         use_container_width=True, hide_index=True, height=480)


# ════════════════════════════════════════════════════════════════════════════════
# PRICES
# ════════════════════════════════════════════════════════════════════════════════
with t_px:
    st.caption("📈 Stocks — live")
    scols = st.columns(max(len(watchlist), 1))
    for i, sym in enumerate(watchlist):
        price, chg, chgpct = get_quick_price(sym)
        scols[i].metric(sym, f"${price:.2f}", f"{chgpct:+.2f}%",
                        delta_color="normal" if chg >= 0 else "inverse")

    st.caption("🔗 Crypto — live")
    ccols = st.columns(len(CRYPTO_YF_MAP))
    for i, (asym, ysym) in enumerate(CRYPTO_YF_MAP.items()):
        price, chg, chgpct = get_quick_price(ysym)
        label = asym.replace("/USD", "")
        pfmt  = f"${price:,.2f}" if price > 1 else f"${price:.4f}"
        ccols[i].metric(label, pfmt, f"{chgpct:+.2f}%",
                        delta_color="normal" if chg >= 0 else "inverse")

    st.divider()
    st.caption("📊 Performance Stats")
    best  = max(trade_pnls) if trade_pnls else 0
    worst = min(trade_pnls) if trade_pnls else 0
    avg_w = sum(wins)   / len(wins)   if wins   else 0
    avg_l = sum(losses) / len(losses) if losses else 0
    ps = st.columns(5)
    ps[0].metric("Total Orders",   len(filled))
    ps[1].metric("Closed Trades",  len(sells))
    ps[2].metric("Best Trade",     f"${best:+,.0f}")
    ps[3].metric("Worst Trade",    f"${worst:+,.0f}")
    ps[4].metric("Avg Win / Loss", f"${avg_w:+,.0f} / ${avg_l:+,.0f}")

