'use client';

import { useState, useMemo } from 'react';
import Badge from '@/components/Badge';
import { CRYPTO_SYMBOLS, fmt$, fmtPrice, fmtDate, colorStyle } from '@/lib/utils';
import type { Order } from '@/lib/types';

type Filter = 'all' | 'stocks' | 'crypto';

interface Props { orders: Order[] }

function buildPnlMap(orders: Order[]): Map<string, number> {
  const buyMap = new Map<string, { qty: number; px: number }[]>();
  const pnlMap = new Map<string, number>();
  for (const o of [...orders].sort((a, b) => (a.filled_at ?? '').localeCompare(b.filled_at ?? ''))) {
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
        pnlMap.set(o.id, (px - ap) * qty);
      }
    }
  }
  return pnlMap;
}

export default function HistoryTab({ orders }: Props) {
  const [filter, setFilter] = useState<Filter>('all');

  const filled = orders.filter(o => o.status === 'filled');
  const pnlMap = useMemo(() => buildPnlMap(filled), [filled]);

  const shown = filled.filter(o => {
    if (filter === 'stocks') return !CRYPTO_SYMBOLS.has(o.symbol);
    if (filter === 'crypto') return  CRYPTO_SYMBOLS.has(o.symbol);
    return true;
  }).slice(0, 150);

  // Summary stats
  const sells      = filled.filter(o => o.side === 'sell');
  const pnlVals    = sells.map(o => pnlMap.get(o.id)).filter((v): v is number => v !== undefined);
  const totalPnl   = pnlVals.reduce((s, v) => s + v, 0);
  const wins       = pnlVals.filter(v => v > 0).length;
  const winRate    = pnlVals.length > 0 ? (wins / pnlVals.length * 100).toFixed(0) : '—';

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all',    label: 'All' },
    { key: 'stocks', label: '📈 Stocks' },
    { key: 'crypto', label: '🔗 Crypto' },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex gap-1">
          {FILTERS.map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                filter === f.key
                  ? 'bg-emerald-900/50 text-emerald-400 border border-emerald-800/50'
                  : 'text-[#718096] hover:text-white bg-[#1c2333] border border-[#2d3748]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-[#718096]">{shown.length} orders</span>
          <span className="text-[#718096]">Realized P&L: <b style={{ color: colorStyle(totalPnl) }}>{totalPnl !== 0 ? fmt$(totalPnl) : '—'}</b></span>
          <span className="text-[#718096]">Win rate: <b className="text-white">{winRate}{typeof winRate === 'string' && winRate !== '—' ? '%' : ''}</b></span>
        </div>
      </div>

      {shown.length > 0 ? (
        <div className="rounded-xl border border-[#2d3748] bg-[#1c2333] overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Date &amp; Time</th>
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
              {shown.map(o => {
                const isCrypto = CRYPTO_SYMBOLS.has(o.symbol);
                const qty      = parseFloat(o.filled_qty ?? '0');
                const price    = parseFloat(o.filled_avg_price ?? '0');
                const pnl      = pnlMap.get(o.id);
                return (
                  <tr key={o.id}>
                    <td className="text-xs text-[#718096]">{fmtDate(o.filled_at)}</td>
                    <td className="font-semibold">{o.symbol}</td>
                    <td><Badge color={isCrypto ? 'blue' : 'green'}>{isCrypto ? '🔗' : '📈'}</Badge></td>
                    <td><Badge color={o.side === 'buy' ? 'green' : 'red'}>{o.side.toUpperCase()}</Badge></td>
                    <td className="text-right font-mono text-xs">{isCrypto ? qty.toFixed(4) : qty.toFixed(0)}</td>
                    <td className="text-right font-mono text-xs">{fmtPrice(price, isCrypto)}</td>
                    <td className="text-right font-mono">{fmt$(qty * price)}</td>
                    <td className="text-right font-mono text-xs" style={{ color: pnl !== undefined ? colorStyle(pnl) : '#718096' }}>
                      {pnl !== undefined ? `${pnl >= 0 ? '+' : ''}${fmt$(pnl)}` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-xl border border-[#2d3748] bg-[#1c2333] p-10 text-center text-[#718096] text-sm">
          No trade history yet.
        </div>
      )}
    </div>
  );
}
