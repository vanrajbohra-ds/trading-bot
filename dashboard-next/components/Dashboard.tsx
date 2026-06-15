'use client';

import { useState, useMemo } from 'react';
import useSWR from 'swr';
import KpiCard from '@/components/KpiCard';
import Spinner from '@/components/Spinner';
import OverviewTab    from '@/components/tabs/OverviewTab';
import PositionsTab   from '@/components/tabs/PositionsTab';
import MomentumTab    from '@/components/tabs/MomentumTab';
import HistoryTab     from '@/components/tabs/HistoryTab';
import ReportsTab     from '@/components/tabs/ReportsTab';
import PricesTab      from '@/components/tabs/PricesTab';
import ExploreTab     from '@/components/tabs/ExploreTab';
import { STARTING_CAP, fmt$, fmtPct, colorStyle } from '@/lib/utils';
import type { Account, Position, Order } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

type Tab = 'overview' | 'positions' | 'momentum' | 'history' | 'reports' | 'prices' | 'explore';

const CORE_SYMS = new Set(['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD']);
const MOM_BUDGET_PCT = 0.10;

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview',   label: '📊 Overview'  },
  { key: 'positions',  label: '📁 Positions'  },
  { key: 'momentum',   label: '🚀 Momentum'   },
  { key: 'history',    label: '📜 History'    },
  { key: 'reports',    label: '📈 Reports'    },
  { key: 'prices',     label: '💲 Prices'     },
  { key: 'explore',    label: '🔍 Explore'    },
];

export default function Dashboard() {
  const [tab,         setTab]         = useState<Tab>('overview');
  const [watchOpen,   setWatchOpen]   = useState(false);
  const [watchInput,  setWatchInput]  = useState('');
  const [watchSaving, setWatchSaving] = useState(false);

  // Core data — 30s refresh for live prices/account
  const { data: account,   isLoading: acLoading }  = useSWR<Account>('/api/account',   fetcher, { refreshInterval: 30_000 });
  const { data: positions = [], isLoading: posLoading } = useSWR<Position[]>('/api/positions', fetcher, { refreshInterval: 30_000 });
  const { data: orders    = [], isLoading: ordLoading } = useSWR<Order[]>('/api/orders',    fetcher, { refreshInterval: 30_000 });
  const { data: watchlist = [], mutate: mutateWL }     = useSWR<string[]>('/api/watchlist', fetcher, { revalidateOnFocus: false });

  const isLoading = acLoading || posLoading || ordLoading;

  /* ── KPI computations ─────────────────────────────────────── */
  const kpis = useMemo(() => {
    const portfolioVal = parseFloat(account?.portfolio_value ?? '0');
    const cash         = parseFloat(account?.cash ?? '0');
    const totalPnl     = portfolioVal - STARTING_CAP;

    // Win rate & profit factor from closed trades
    const filled   = orders.filter(o => o.status === 'filled');
    const buyMap   = new Map<string, { qty: number; px: number }[]>();
    let totalWin   = 0;
    let totalLoss  = 0;
    let wins       = 0;
    let total      = 0;

    for (const o of [...filled].sort((a, b) => (a.filled_at ?? '').localeCompare(b.filled_at ?? ''))) {
      const qty = parseFloat(o.filled_qty ?? '0');
      const px  = parseFloat(o.filled_avg_price ?? '0');
      if (o.side === 'buy') {
        if (!buyMap.has(o.symbol)) buyMap.set(o.symbol, []);
        buyMap.get(o.symbol)!.push({ qty, px });
      } else {
        const buys = buyMap.get(o.symbol) ?? [];
        if (buys.length) {
          const tq = buys.reduce((s, b) => s + b.qty, 0);
          const ap = buys.reduce((s, b) => s + b.qty * b.px, 0) / tq;
          const pnl = (px - ap) * qty;
          if (pnl >= 0) { totalWin  += pnl;  wins++; }
          else           { totalLoss += Math.abs(pnl); }
          total++;
        }
      }
    }

    const winRate      = total > 0 ? (wins / total) * 100 : 0;
    const profitFactor = totalLoss > 0 ? totalWin / totalLoss : totalWin > 0 ? Infinity : 1;

    // Momentum budget utilisation
    const momPos   = positions.filter(p => !CORE_SYMS.has(p.symbol));
    const momUsed  = momPos.reduce((s, p) => s + parseFloat(p.market_value), 0);
    const momBudget = portfolioVal * MOM_BUDGET_PCT;
    const momPct    = momBudget > 0 ? (momUsed / momBudget) * 100 : 0;

    // Weekly return — P&L % over last 7 days orders (rough heuristic)
    const weekAgo = Date.now() - 7 * 86_400_000;
    const weekSells = filled.filter(o => o.side === 'sell' && new Date(o.filled_at ?? '').getTime() > weekAgo);
    const weekPnl   = weekSells.reduce((s, o) => {
      const buys = buyMap.get(o.symbol) ?? [];
      if (!buys.length) return s;
      const tq = buys.reduce((a, b) => a + b.qty, 0);
      const ap = buys.reduce((a, b) => a + b.qty * b.px, 0) / tq;
      return s + (parseFloat(o.filled_avg_price ?? '0') - ap) * parseFloat(o.filled_qty ?? '0');
    }, 0);
    const weekReturn = portfolioVal > 0 ? (weekPnl / portfolioVal) * 100 : 0;

    return { portfolioVal, cash, totalPnl, winRate, profitFactor, momPct, weekReturn, posCount: positions.length };
  }, [account, orders, positions]);

  /* ── Watchlist management ─────────────────────────────────── */
  async function addSymbol() {
    const sym = watchInput.trim().toUpperCase();
    if (!sym || watchlist.includes(sym)) { setWatchInput(''); return; }
    setWatchSaving(true);
    const next = [...watchlist, sym];
    await fetch('/api/watchlist', { method: 'PUT', body: JSON.stringify(next), headers: { 'Content-Type': 'application/json' } });
    mutateWL(next);
    setWatchInput('');
    setWatchSaving(false);
  }

  async function removeSymbol(sym: string) {
    const next = watchlist.filter(s => s !== sym);
    await fetch('/api/watchlist', { method: 'PUT', body: JSON.stringify(next), headers: { 'Content-Type': 'application/json' } });
    mutateWL(next);
  }

  /* ── Render ───────────────────────────────────────────────── */
  return (
    <div className="min-h-screen bg-[#0d0d1a] text-[#e2e8f0] flex flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-40 bg-[#0d0d1a]/95 backdrop-blur border-b border-[#1e1e35]">
        <div className="max-w-screen-2xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-green-400 text-lg font-bold">▲</span>
            <span className="font-bold text-white tracking-tight">TradingBot</span>
            <span className="hidden sm:inline text-[10px] font-semibold uppercase bg-[#111122] border border-[#1e1e35] text-[#6b7280] px-2 py-0.5 rounded-full ml-1">
              Paper
            </span>
          </div>

          {isLoading ? (
            <span className="text-[#4b5563] text-xs animate-pulse ml-auto">Connecting…</span>
          ) : (
            <span className="text-[#4b5563] text-xs ml-auto hidden sm:inline">
              Auto-refresh every 30s
            </span>
          )}

          <button
            onClick={() => setWatchOpen(v => !v)}
            className="shrink-0 px-3 py-1.5 text-xs font-semibold rounded-lg border border-[#1e1e35] bg-[#111122] text-[#9ca3af] hover:text-white hover:border-green-800/50 transition-colors"
          >
            📋 Watchlist ({watchlist.length})
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-4 space-y-4">
        {/* KPI strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          <KpiCard
            label="Portfolio"
            value={kpis.portfolioVal > 0 ? fmt$(kpis.portfolioVal) : '—'}
            sub={kpis.totalPnl !== 0 ? fmtPct((kpis.totalPnl / STARTING_CAP) * 100) : undefined}
            subColor={colorStyle(kpis.totalPnl)}
          />
          <KpiCard
            label="Cash"
            value={kpis.cash > 0 ? fmt$(kpis.cash) : '—'}
            sub={kpis.portfolioVal > 0 ? `${((kpis.cash / kpis.portfolioVal) * 100).toFixed(0)}% of portfolio` : undefined}
          />
          <KpiCard
            label="Total P&L"
            value={kpis.portfolioVal > 0 ? fmt$(kpis.totalPnl) : '—'}
            valueColor={kpis.totalPnl !== 0 ? colorStyle(kpis.totalPnl) : undefined}
          />
          <KpiCard
            label="Open Positions"
            value={String(kpis.posCount)}
          />
          <KpiCard
            label="Win Rate"
            value={kpis.winRate > 0 ? `${kpis.winRate.toFixed(0)}%` : '—'}
            valueColor={kpis.winRate >= 50 ? '#4ade80' : kpis.winRate > 0 ? '#f87171' : undefined}
          />
          <KpiCard
            label="Profit Factor"
            value={kpis.profitFactor === Infinity ? '∞' : kpis.profitFactor > 0 ? kpis.profitFactor.toFixed(2) : '—'}
            valueColor={kpis.profitFactor >= 1.5 ? '#4ade80' : kpis.profitFactor >= 1 ? '#fbbf24' : kpis.profitFactor > 0 ? '#f87171' : undefined}
          />
          <KpiCard
            label="Weekly P&L"
            value={kpis.weekReturn !== 0 ? fmtPct(kpis.weekReturn) : '—'}
            valueColor={kpis.weekReturn !== 0 ? colorStyle(kpis.weekReturn) : undefined}
          />
          <KpiCard
            label="Momentum Used"
            value={kpis.momPct > 0 ? `${kpis.momPct.toFixed(0)}%` : '—'}
            valueColor={kpis.momPct > 80 ? '#f87171' : kpis.momPct > 50 ? '#fbbf24' : '#4ade80'}
            sub="of 10% budget"
          />
        </div>

        {/* Tab navigation */}
        <div className="flex gap-1 overflow-x-auto pb-1 border-b border-[#1e1e35]">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`shrink-0 px-4 py-2 text-xs font-semibold rounded-t transition-colors whitespace-nowrap ${
                tab === t.key
                  ? 'bg-[#111122] text-green-400 border-b-2 border-green-400 -mb-px'
                  : 'text-[#6b7280] hover:text-[#9ca3af]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab body */}
        <div>
          {isLoading && tab !== 'explore' ? (
            <Spinner text="Loading account data…" />
          ) : (
            <>
              {tab === 'overview'  && <OverviewTab  positions={positions} />}
              {tab === 'positions' && <PositionsTab positions={positions} />}
              {tab === 'momentum'  && (
                <MomentumTab
                  positions={positions}
                  orders={orders}
                  portfolioValue={kpis.portfolioVal}
                />
              )}
              {tab === 'history'   && <HistoryTab  orders={orders} />}
              {tab === 'reports'   && <ReportsTab  orders={orders} />}
              {tab === 'prices'    && <PricesTab   watchlist={watchlist} orders={orders} />}
              {tab === 'explore'   && <ExploreTab />}
            </>
          )}
        </div>
      </main>

      {/* Watchlist drawer */}
      {watchOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            onClick={() => setWatchOpen(false)}
          />
          <aside className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-[#0d0d1a] border-l border-[#1e1e35] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e1e35]">
              <h2 className="font-bold text-sm">📋 Watchlist</h2>
              <button
                onClick={() => setWatchOpen(false)}
                className="text-[#6b7280] hover:text-white text-xl leading-none"
              >
                ×
              </button>
            </div>

            {/* Add symbol */}
            <div className="p-4 border-b border-[#1e1e35]">
              <div className="flex gap-2">
                <input
                  value={watchInput}
                  onChange={e => setWatchInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addSymbol()}
                  placeholder="Add symbol (AAPL, ETH/USD…)"
                  className="flex-1 px-3 py-2 bg-[#111122] border border-[#1e1e35] rounded-lg text-sm text-white placeholder-[#4b5563] focus:outline-none focus:border-green-500/50"
                />
                <button
                  onClick={addSymbol}
                  disabled={watchSaving}
                  className="px-3 py-2 bg-green-900/50 border border-green-800/50 text-green-400 rounded-lg text-sm hover:bg-green-900/70 disabled:opacity-50 transition-colors"
                >
                  {watchSaving ? '…' : '+'}
                </button>
              </div>
            </div>

            {/* Symbol list */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {watchlist.length === 0 ? (
                <p className="text-[#6b7280] text-sm text-center py-8">No symbols in watchlist</p>
              ) : (
                watchlist.map(sym => (
                  <div
                    key={sym}
                    className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#111122] border border-[#1e1e35] group"
                  >
                    <span className="font-semibold text-sm">{sym}</span>
                    <button
                      onClick={() => removeSymbol(sym)}
                      className="text-[#4b5563] hover:text-red-400 transition-colors text-sm opacity-0 group-hover:opacity-100"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="p-4 border-t border-[#1e1e35] text-[10px] text-[#4b5563] text-center leading-relaxed">
              Changes sync to GitHub repo on save.<br />
              Bot picks up the new watchlist on next cycle.
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
