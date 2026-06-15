'use client';

import { useState } from 'react';
import Badge from '@/components/Badge';
import { CRYPTO_SYMBOLS, fmt$, fmtPrice, fmtDate, colorStyle } from '@/lib/utils';
import type { Order } from '@/lib/types';

type Filter = 'all' | 'stocks' | 'crypto';

interface Props { orders: Order[] }

export default function HistoryTab({ orders }: Props) {
  const [filter, setFilter] = useState<Filter>('all');

  const filled = orders.filter(o => o.status === 'filled');

  const shown = filled.filter(o => {
    if (filter === 'stocks') return !CRYPTO_SYMBOLS.has(o.symbol);
    if (filter === 'crypto') return  CRYPTO_SYMBOLS.has(o.symbol);
    return true;
  }).slice(0, 150);

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all',    label: 'All' },
    { key: 'stocks', label: '📈 Stocks' },
    { key: 'crypto', label: '🔗 Crypto' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex gap-1">
          {FILTERS.map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                filter === f.key
                  ? 'bg-green-900/50 text-green-400 border border-green-800/50'
                  : 'text-[#6b7280] hover:text-white bg-[#111122] border border-[#1e1e35]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-[#6b7280]">{shown.length} orders</span>
      </div>

      {shown.length > 0 ? (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-x-auto">
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
              </tr>
            </thead>
            <tbody>
              {shown.map(o => {
                const isCrypto = CRYPTO_SYMBOLS.has(o.symbol);
                const qty      = parseFloat(o.filled_qty ?? '0');
                const price    = parseFloat(o.filled_avg_price ?? '0');
                return (
                  <tr key={o.id}>
                    <td className="text-xs text-[#6b7280]">{fmtDate(o.filled_at)}</td>
                    <td className="font-semibold">{o.symbol}</td>
                    <td><Badge color={isCrypto ? 'blue' : 'green'}>{isCrypto ? '🔗' : '📈'}</Badge></td>
                    <td><Badge color={o.side === 'buy' ? 'green' : 'red'}>{o.side.toUpperCase()}</Badge></td>
                    <td className="text-right font-mono text-xs">{isCrypto ? qty.toFixed(4) : qty.toFixed(0)}</td>
                    <td className="text-right font-mono text-xs">{fmtPrice(price, isCrypto)}</td>
                    <td className="text-right font-mono">{fmt$(qty * price)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-10 text-center text-[#6b7280] text-sm">
          No trade history yet.
        </div>
      )}
    </div>
  );
}
