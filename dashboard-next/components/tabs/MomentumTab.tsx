'use client';

import { useState } from 'react';
import useSWR from 'swr';
import KpiCard from '@/components/KpiCard';
import Badge from '@/components/Badge';
import Spinner from '@/components/Spinner';
import { fmt$, fmtPrice, fmtPct, fmtDate, colorStyle, fmtCap, CRYPTO_SYMBOLS } from '@/lib/utils';
import type { ScreenerQuote, SignalCheck, Order, Position } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

const CORE_SYMS = new Set(['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD']);
const MOM_BUDGET_PCT = 0.10;

interface Props { positions: Position[]; orders: Order[]; portfolioValue: number }

type SubTab = 'screener' | 'signals' | 'positions' | 'trades';

interface ScreenerData { actives: ScreenerQuote[]; gainers: ScreenerQuote[]; error?: string }

export default function MomentumTab({ positions, orders, portfolioValue }: Props) {
  const [sub, setSub] = useState<SubTab>('screener');
  const { data: screener, isLoading: screenerLoading } = useSWR<ScreenerData>(
    sub === 'screener' || sub === 'signals' ? '/api/screener' : null,
    fetcher, { refreshInterval: 120_000 },
  );

  const momPos     = positions.filter(p => !CORE_SYMS.has(p.symbol));
  const momBudget  = portfolioValue * MOM_BUDGET_PCT;
  const momUsed    = momPos.reduce((s, p) => s + parseFloat(p.market_value), 0);
  const momPct     = momBudget > 0 ? momUsed / momBudget * 100 : 0;

  const filled     = orders.filter(o => o.status === 'filled');
  const momOrders  = filled.filter(o => !CORE_SYMS.has(o.symbol));
  const momBuys    = momOrders.filter(o => o.side === 'buy');

  const SUB_TABS: { key: SubTab; label: string }[] = [
    { key: 'screener',  label: '🔍 Live Screener' },
    { key: 'signals',   label: '📡 Signal Filter' },
    { key: 'positions', label: '📊 Open Positions' },
    { key: 'trades',    label: '📜 Trades' },
  ];

  return (
    <div className="space-y-4">
      {/* Budget strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard label="Budget"         value={fmt$(momBudget)} sub={`${(MOM_BUDGET_PCT * 100).toFixed(0)}% of portfolio`} />
        <KpiCard label="Used"           value={fmt$(momUsed)}   sub={`${momPct.toFixed(0)}% of budget`} subColor={momPct > 80 ? '#f87171' : '#4ade80'} />
        <KpiCard label="Remaining"      value={fmt$(Math.max(0, momBudget - momUsed))} />
        <KpiCard label="Open Positions" value={String(momPos.length)} />
      </div>

      {/* Sub-tab bar */}
      <div className="flex gap-1 border-b border-[#1e1e35] pb-0">
        {SUB_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setSub(t.key)}
            className={`px-4 py-2 text-xs font-semibold rounded-t transition-colors ${
              sub === t.key
                ? 'bg-[#111122] text-green-400 border-b-2 border-green-400'
                : 'text-[#6b7280] hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Live Screener */}
      {sub === 'screener' && (
        screenerLoading ? <Spinner text="Loading screener…" /> :
        screener?.error ? (
          <div className="text-amber-400 text-sm p-4 bg-amber-900/20 rounded-lg border border-amber-800/40">
            Screener unavailable: {screener.error}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ScreenerTable title="⚡ Most Active by Volume" quotes={screener?.actives ?? []} />
            <ScreenerTable title="📈 Top Gainers Today"    quotes={screener?.gainers ?? []} />
          </div>
        )
      )}

      {/* Signal Filter */}
      {sub === 'signals' && (
        screenerLoading ? <Spinner text="Running pre-filter…" /> :
        <SignalFilterTable
          candidates={[
            ...Object.fromEntries((screener?.actives ?? []).map(q => [q.symbol, q])).values(),
            ...Object.fromEntries((screener?.gainers ?? []).map(q => [q.symbol, q])).values(),
          ].slice(0, 20)}
        />
      )}

      {/* Open momentum positions */}
      {sub === 'positions' && (
        momPos.length === 0 ? (
          <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-10 text-center text-[#6b7280] text-sm">
            No open momentum positions. Hunter is scanning for setups…
          </div>
        ) : (
          <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="text-right">Mkt Value</th>
                  <th className="text-right">P&amp;L $</th>
                  <th className="text-right">P&amp;L %</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {momPos.map(p => {
                  const pnl    = parseFloat(p.unrealized_pl);
                  const pnlPct = parseFloat(p.unrealized_plpc) * 100;
                  return (
                    <tr key={p.symbol}>
                      <td className="font-semibold">{p.symbol}</td>
                      <td className="text-right font-mono">{fmt$(parseFloat(p.market_value))}</td>
                      <td className="text-right font-mono" style={{ color: colorStyle(pnl) }}>
                        {pnl >= 0 ? '+' : ''}{fmt$(pnl)}
                      </td>
                      <td className="text-right font-mono" style={{ color: colorStyle(pnlPct) }}>
                        {fmtPct(pnlPct)}
                      </td>
                      <td>
                        <Badge color={pnlPct >= 0 ? 'green' : 'red'}>{pnlPct >= 0 ? 'Profit' : 'Loss'}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Momentum trades */}
      {sub === 'trades' && (
        momOrders.length === 0 ? (
          <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-10 text-center text-[#6b7280] text-sm">
            No momentum trades yet.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <KpiCard label="Total Orders" value={String(momOrders.length)} />
              <KpiCard label="Total Bought" value={fmt$(momBuys.reduce((s, o) => s + parseFloat(o.filled_qty ?? '0') * parseFloat(o.filled_avg_price ?? '0'), 0))} />
              <KpiCard label="Sells"        value={String(momOrders.filter(o => o.side === 'sell').length)} />
            </div>
            <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th className="text-right">Units</th>
                    <th className="text-right">Price</th>
                    <th className="text-right">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {momOrders.slice(0, 120).map(o => {
                    const isCrypto = CRYPTO_SYMBOLS.has(o.symbol);
                    const qty   = parseFloat(o.filled_qty ?? '0');
                    const price = parseFloat(o.filled_avg_price ?? '0');
                    return (
                      <tr key={o.id}>
                        <td className="text-[#6b7280] text-xs">{fmtDate(o.filled_at)}</td>
                        <td className="font-semibold">{o.symbol}</td>
                        <td>
                          <Badge color={o.side === 'buy' ? 'green' : 'red'}>
                            {o.side.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="text-right font-mono text-xs">{isCrypto ? qty.toFixed(4) : qty.toFixed(0)}</td>
                        <td className="text-right font-mono text-xs">{fmtPrice(price, isCrypto)}</td>
                        <td className="text-right font-mono">{fmt$(qty * price)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function ScreenerTable({ title, quotes }: { title: string; quotes: ScreenerQuote[] }) {
  return (
    <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e1e35]">
        <p className="text-xs font-semibold text-[#6b7280]">{title}</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="text-right">Price</th>
            <th className="text-right">Chg %</th>
            <th className="text-right">Vol×</th>
            <th className="text-right">MCap</th>
          </tr>
        </thead>
        <tbody>
          {quotes.slice(0, 12).map(q => (
            <tr key={q.symbol}>
              <td>
                <div className="font-semibold">{q.symbol}</div>
                <div className="text-[10px] text-[#6b7280] truncate max-w-28">{q.name}</div>
              </td>
              <td className="text-right font-mono text-xs">${q.price.toFixed(2)}</td>
              <td className="text-right font-mono text-xs" style={{ color: colorStyle(q.changePct) }}>
                {fmtPct(q.changePct)}
              </td>
              <td className="text-right font-mono text-xs">
                <span style={{ color: q.volumeRatio >= 2 ? '#fbbf24' : q.volumeRatio >= 1.5 ? '#e2e8f0' : '#6b7280' }}>
                  {q.volumeRatio.toFixed(1)}×
                </span>
              </td>
              <td className="text-right text-xs text-[#6b7280]">{fmtCap(q.marketCap)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignalFilterTable({ candidates }: { candidates: ScreenerQuote[] }) {
  const [results, setResults] = useState<Record<string, SignalCheck>>({});
  const [loading, setLoading] = useState(false);
  const [ran, setRan] = useState(false);

  async function run() {
    setLoading(true);
    const out: Record<string, SignalCheck> = {};
    await Promise.all(
      candidates.map(async q => {
        try {
          const r = await fetch(`/api/signal?symbol=${q.symbol}`);
          out[q.symbol] = await r.json() as SignalCheck;
        } catch {
          out[q.symbol] = { pass: false, checks: 0, rsi: null, volRatio: null, macdHist: null, volOk: false, rsiOk: false, macdOk: false };
        }
      })
    );
    setResults(out);
    setLoading(false);
    setRan(true);
  }

  if (!candidates.length) return (
    <div className="text-[#6b7280] text-sm p-6 text-center">No screener data — open Live Screener first.</div>
  );

  return (
    <div className="space-y-3">
      {!ran && (
        <button
          onClick={run}
          disabled={loading}
          className="px-4 py-2 bg-green-900/40 border border-green-800/50 text-green-400 rounded-lg text-sm font-semibold hover:bg-green-900/60 disabled:opacity-50 transition-colors"
        >
          {loading ? 'Running pre-filter…' : `▶ Run Pre-filter on ${candidates.length} symbols`}
        </button>
      )}
      {ran && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="text-right">Price</th>
                <th className="text-right">Chg %</th>
                <th className="text-right">RSI</th>
                <th className="text-right">MACD</th>
                <th className="text-right">Vol×</th>
                <th>Vol✓</th>
                <th>RSI✓</th>
                <th>MACD✓</th>
                <th>Score</th>
                <th>Signal</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map(q => {
                const s = results[q.symbol];
                return (
                  <tr key={q.symbol}>
                    <td className="font-semibold">{q.symbol}</td>
                    <td className="text-right font-mono text-xs">${q.price.toFixed(2)}</td>
                    <td className="text-right font-mono text-xs" style={{ color: colorStyle(q.changePct) }}>{fmtPct(q.changePct)}</td>
                    <td className="text-right font-mono text-xs">{s ? (s.rsi?.toFixed(1) ?? '—') : '…'}</td>
                    <td className="text-right font-mono text-xs">{s ? (s.macdHist?.toFixed(4) ?? '—') : '…'}</td>
                    <td className="text-right font-mono text-xs">{s ? (s.volRatio?.toFixed(1) ?? '—') : '…'}×</td>
                    <td>{s ? (s.volOk  ? '✅' : '❌') : '…'}</td>
                    <td>{s ? (s.rsiOk  ? '✅' : '❌') : '…'}</td>
                    <td>{s ? (s.macdOk ? '✅' : '❌') : '…'}</td>
                    <td className="font-mono text-xs">{s ? `${s.checks}/3` : '…'}</td>
                    <td>
                      {s ? (
                        <Badge color={s.pass ? 'green' : 'gray'}>
                          {s.pass ? '🟢 PASS' : '⛔ SKIP'}
                        </Badge>
                      ) : '…'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="px-4 py-2 text-xs text-[#6b7280] border-t border-[#1e1e35]">
            {Object.values(results).filter(r => r.pass).length}/{candidates.length} pass pre-filter → eligible for LLM
          </div>
        </div>
      )}
    </div>
  );
}
