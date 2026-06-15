'use client';

import useSWR from 'swr';
import PortfolioChart from '@/components/charts/PortfolioChart';
import AllocationPie from '@/components/charts/AllocationPie';
import PnlBar from '@/components/charts/PnlBar';
import { CRYPTO_SYMBOLS, fmt$, colorStyle } from '@/lib/utils';
import type { Position, PortfolioHistory } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

interface Props { positions: Position[]; cash: number }

export default function OverviewTab({ positions, cash }: Props) {
  const { data: hist } = useSWR<PortfolioHistory>('/api/portfolio-history', fetcher, { refreshInterval: 300_000 });

  const stockPos  = positions.filter(p => !CRYPTO_SYMBOLS.has(p.symbol));
  const cryptoPos = positions.filter(p =>  CRYPTO_SYMBOLS.has(p.symbol));
  const stockVal  = stockPos.reduce((s, p)  => s + parseFloat(p.market_value), 0);
  const cryptoVal = cryptoPos.reduce((s, p) => s + parseFloat(p.market_value), 0);

  // Portfolio chart data
  const chartData = (() => {
    if (!hist?.timestamp?.length) return [];
    return hist.timestamp
      .map((ts, i) => ({
        date:  new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        value: hist.equity[i] ?? 0,
      }))
      .filter(d => d.value > 0);
  })();

  // P&L bar data
  const pnlData = positions.map(p => ({
    symbol: p.symbol,
    pnl:    parseFloat(p.unrealized_pl),
    label:  `${CRYPTO_SYMBOLS.has(p.symbol) ? '🔗' : '📈'} ${p.symbol}`,
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Performance chart */}
        <div className="lg:col-span-3 rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">Portfolio Performance (1M)</p>
          <PortfolioChart data={chartData} />
        </div>

        {/* Allocation pie */}
        <div className="lg:col-span-2 rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">Capital Allocation</p>
          <AllocationPie
            stockVal={stockVal}
            cryptoVal={cryptoVal}
            cash={cash}
          />
        </div>
      </div>

      {/* Open positions P&L bar */}
      {pnlData.length > 0 && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">Unrealized P&amp;L by Position</p>
          <PnlBar data={pnlData} />
        </div>
      )}

      {/* Position summary table */}
      {positions.length > 0 && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-hidden">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th className="text-right">Market Value</th>
                <th className="text-right">Unrealized P&amp;L</th>
                <th className="text-right">P&amp;L %</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const isCrypto = CRYPTO_SYMBOLS.has(p.symbol);
                const pnl      = parseFloat(p.unrealized_pl);
                const pnlPct   = parseFloat(p.unrealized_plpc) * 100;
                return (
                  <tr key={p.symbol}>
                    <td className="font-semibold">{p.symbol}</td>
                    <td className="text-[#6b7280]">{isCrypto ? '🔗 Crypto' : '📈 Stock'}</td>
                    <td className="text-right font-mono">{fmt$(parseFloat(p.market_value))}</td>
                    <td className="text-right font-mono" style={{ color: colorStyle(pnl) }}>{fmt$(pnl)}</td>
                    <td className="text-right font-mono" style={{ color: colorStyle(pnlPct) }}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {positions.length === 0 && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-8 text-center text-[#6b7280] text-sm">
          No open positions — bot is scanning for entry signals.
        </div>
      )}
    </div>
  );
}
