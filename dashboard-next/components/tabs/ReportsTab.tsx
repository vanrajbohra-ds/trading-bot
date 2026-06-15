'use client';

import { useState, useMemo } from 'react';
import KpiCard from '@/components/KpiCard';
import Badge from '@/components/Badge';
import { CRYPTO_SYMBOLS, fmt$, fmtPrice, fmtDate, fmtDateShort, colorStyle } from '@/lib/utils';
import type { Order } from '@/lib/types';

const CORE_SYMS = new Set(['AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD']);

type ViewMode = 'day' | 'flat';
type SideFilter = 'all' | 'buy' | 'sell';
type RangeFilter = 'all' | '7d' | 'today';
type TypeFilter = 'all' | 'stocks' | 'crypto' | 'momentum';

interface Props { orders: Order[] }

function buildPnlMap(orders: Order[]): Map<string, number> {
  const buyHistory = new Map<string, { qty: number; px: number }[]>();
  const pnlMap     = new Map<string, number>();

  for (const o of [...orders].sort((a, b) => (a.filled_at ?? '').localeCompare(b.filled_at ?? ''))) {
    const sym = o.symbol;
    const qty = parseFloat(o.filled_qty ?? '0');
    const px  = parseFloat(o.filled_avg_price ?? '0');

    if (o.side === 'buy') {
      if (!buyHistory.has(sym)) buyHistory.set(sym, []);
      buyHistory.get(sym)!.push({ qty, px });
    } else if (o.side === 'sell') {
      const buys = buyHistory.get(sym) ?? [];
      if (buys.length) {
        const tq = buys.reduce((s, b) => s + b.qty, 0);
        const ap = buys.reduce((s, b) => s + b.qty * b.px, 0) / tq;
        pnlMap.set(o.id, (px - ap) * qty);
      }
    }
  }
  return pnlMap;
}

export default function ReportsTab({ orders }: Props) {
  const [view,  setView]  = useState<ViewMode>('day');
  const [side,  setSide]  = useState<SideFilter>('all');
  const [range, setRange] = useState<RangeFilter>('all');
  const [type,  setType]  = useState<TypeFilter>('all');

  const filled = useMemo(() => orders.filter(o => o.status === 'filled'), [orders]);
  const pnlMap = useMemo(() => buildPnlMap(filled), [filled]);

  // Summary KPIs
  const buys  = filled.filter(o => o.side === 'buy');
  const sells = filled.filter(o => o.side === 'sell');
  const oval  = (o: Order) => parseFloat(o.filled_qty ?? '0') * parseFloat(o.filled_avg_price ?? '0');
  const buyVol  = buys.reduce((s, o) => s + oval(o), 0);
  const sellVol = sells.reduce((s, o) => s + oval(o), 0);
  const realPnl = Array.from(pnlMap.values()).reduce((s, v) => s + v, 0);
  const wins    = Array.from(pnlMap.values()).filter(v => v > 0).length;
  const losses  = Array.from(pnlMap.values()).filter(v => v <= 0).length;

  // Apply filters
  const now = Date.now();
  let shown = filtered(filled, side, range, type, now);

  function filtered(orders: Order[], side: SideFilter, range: RangeFilter, type: TypeFilter, now: number) {
    return orders.filter(o => {
      if (side === 'buy' && o.side !== 'buy') return false;
      if (side === 'sell' && o.side !== 'sell') return false;
      if (type === 'stocks' && CRYPTO_SYMBOLS.has(o.symbol)) return false;
      if (type === 'crypto' && !CRYPTO_SYMBOLS.has(o.symbol)) return false;
      if (type === 'momentum' && CORE_SYMS.has(o.symbol)) return false;
      if (range === 'today') {
        const d = new Date(o.filled_at ?? '');
        if (d.toDateString() !== new Date().toDateString()) return false;
      }
      if (range === '7d') {
        if (!o.filled_at || new Date(o.filled_at).getTime() < now - 7 * 86_400_000) return false;
      }
      return true;
    });
  }

  // Group by day
  const grouped = useMemo(() => {
    const g = new Map<string, Order[]>();
    for (const o of shown) {
      const key = o.filled_at ? new Date(o.filled_at).toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' }) : 'Unknown';
      if (!g.has(key)) g.set(key, []);
      g.get(key)!.push(o);
    }
    return g;
  }, [shown]);

  const FilterRow = ({ label, options, value, onChange }: {
    label: string;
    options: { key: string; label: string }[];
    value: string;
    onChange: (v: string) => void;
  }) => (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-[#6b7280] w-12 shrink-0">{label}</span>
      {options.map(o => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`px-2.5 py-1 text-xs rounded transition-colors ${
            value === o.key
              ? 'bg-green-900/50 text-green-400 border border-green-800/50'
              : 'text-[#6b7280] bg-[#111122] border border-[#1e1e35] hover:text-white'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Summary KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
        <KpiCard label="Total Buys"    value={String(buys.length)} />
        <KpiCard label="Total Sells"   value={String(sells.length)} />
        <KpiCard label="Vol Bought"    value={fmt$(buyVol)} />
        <KpiCard label="Vol Sold"      value={fmt$(sellVol)} />
        <KpiCard label="Realized P&L"  value={fmt$(realPnl)} valueColor={colorStyle(realPnl)} />
        <KpiCard label="Closed Trades" value={`${wins}W / ${losses}L`} />
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-4 space-y-3">
        <div className="flex gap-1 mb-2">
          {([['day', '📅 By Day'], ['flat', '📋 All Trades']] as const).map(([k, l]) => (
            <button
              key={k}
              onClick={() => setView(k)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                view === k
                  ? 'bg-green-900/50 text-green-400 border border-green-800/50'
                  : 'text-[#6b7280] hover:text-white bg-[#0d0d1a] border border-[#1e1e35]'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        <FilterRow label="Side"  value={side}  onChange={v => setSide(v as SideFilter)}
          options={[{ key: 'all', label: 'All' }, { key: 'buy', label: 'BUY' }, { key: 'sell', label: 'SELL' }]} />
        <FilterRow label="Range" value={range} onChange={v => setRange(v as RangeFilter)}
          options={[{ key: 'all', label: 'All time' }, { key: '7d', label: 'Last 7 days' }, { key: 'today', label: 'Today' }]} />
        <FilterRow label="Type"  value={type}  onChange={v => setType(v as TypeFilter)}
          options={[
            { key: 'all', label: 'All' },
            { key: 'stocks', label: '📈 Stocks' },
            { key: 'crypto', label: '🔗 Crypto' },
            { key: 'momentum', label: '🚀 Momentum' },
          ]} />
      </div>

      {shown.length === 0 ? (
        <div className="p-8 text-center text-[#6b7280] text-sm">No trades match the current filter.</div>
      ) : view === 'flat' ? (
        <FlatTable orders={shown} pnlMap={pnlMap} />
      ) : (
        <div className="space-y-3">
          {Array.from(grouped.entries()).map(([day, dayOrders]) => {
            const dayBuys  = dayOrders.filter(o => o.side === 'buy');
            const daySells = dayOrders.filter(o => o.side === 'sell');
            const dayPnl   = daySells.reduce((s, o) => s + (pnlMap.get(o.id) ?? 0), 0);
            const dayBuyV  = dayBuys.reduce( (s, o) => s + oval(o), 0);
            const daySellV = daySells.reduce((s, o) => s + oval(o), 0);

            return (
              <details key={day} className="rounded-xl border border-[#1e1e35] bg-[#111122]" open={Array.from(grouped.keys())[0] === day}>
                <summary className="px-4 py-3 cursor-pointer list-none flex items-center justify-between hover:bg-white/[0.02] rounded-xl">
                  <div className="flex items-center gap-3 flex-wrap text-sm">
                    <span className="font-semibold">{day}</span>
                    <Badge color="green">{dayBuys.length} buy{dayBuys.length !== 1 ? 's' : ''}</Badge>
                    <Badge color="red">{daySells.length} sell{daySells.length !== 1 ? 's' : ''}</Badge>
                    <span className="text-[#6b7280] text-xs">{fmt$(dayBuyV)} bought · {fmt$(daySellV)} sold</span>
                    {dayPnl !== 0 && <span className="text-xs font-mono" style={{ color: colorStyle(dayPnl) }}>P&L {fmt$(dayPnl)}</span>}
                  </div>
                  <span className="text-[#6b7280] text-lg select-none">▾</span>
                </summary>
                <div className="border-t border-[#1e1e35]">
                  <FlatTable orders={dayOrders} pnlMap={pnlMap} hideDate />
                </div>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}

function FlatTable({ orders, pnlMap, hideDate }: { orders: Order[]; pnlMap: Map<string, number>; hideDate?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table>
        <thead>
          <tr>
            {!hideDate && <th>Date</th>}
            <th>Time</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Side</th>
            <th className="text-right">Units</th>
            <th className="text-right">Price</th>
            <th className="text-right">Value</th>
            <th className="text-right">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {orders.map(o => {
            const isCrypto = CRYPTO_SYMBOLS.has(o.symbol);
            const qty      = parseFloat(o.filled_qty ?? '0');
            const price    = parseFloat(o.filled_avg_price ?? '0');
            const pnl      = pnlMap.get(o.id);
            const dt       = o.filled_at ? new Date(o.filled_at) : null;
            return (
              <tr key={o.id}>
                {!hideDate && <td className="text-xs text-[#6b7280]">{dt ? fmtDateShort(o.filled_at) : '—'}</td>}
                <td className="text-xs text-[#6b7280]">{dt ? dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC' : '—'}</td>
                <td className="font-semibold">{o.symbol}</td>
                <td><Badge color={isCrypto ? 'blue' : 'green'}>{isCrypto ? '🔗' : '📈'}</Badge></td>
                <td><Badge color={o.side === 'buy' ? 'green' : 'red'}>{o.side.toUpperCase()}</Badge></td>
                <td className="text-right font-mono text-xs">{isCrypto ? qty.toFixed(4) : qty.toFixed(0)}</td>
                <td className="text-right font-mono text-xs">{fmtPrice(price, isCrypto)}</td>
                <td className="text-right font-mono">{fmt$(qty * price)}</td>
                <td className="text-right font-mono text-xs" style={{ color: pnl !== undefined ? colorStyle(pnl) : '#6b7280' }}>
                  {pnl !== undefined ? `${pnl >= 0 ? '+' : ''}${fmt$(pnl)}` : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
