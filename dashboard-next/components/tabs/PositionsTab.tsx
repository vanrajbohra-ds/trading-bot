'use client';

import useSWR from 'swr';
import KpiCard from '@/components/KpiCard';
import Badge from '@/components/Badge';
import {
  CRYPTO_SYMBOLS, fmt$, fmtPrice, fmtPct, colorStyle, colorClass,
} from '@/lib/utils';
import type { Position, StopsData } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

interface Props { positions: Position[] }

export default function PositionsTab({ positions }: Props) {
  const { data: stops = {} } = useSWR<StopsData>('/api/stops', fetcher, { refreshInterval: 60_000 });

  const stockPos  = positions.filter(p => !CRYPTO_SYMBOLS.has(p.symbol));
  const cryptoPos = positions.filter(p =>  CRYPTO_SYMBOLS.has(p.symbol));
  const stockVal  = stockPos.reduce((s, p)  => s + parseFloat(p.market_value), 0);
  const cryptoVal = cryptoPos.reduce((s, p) => s + parseFloat(p.market_value), 0);
  const stockPnl  = stockPos.reduce((s, p)  => s + parseFloat(p.unrealized_pl), 0);
  const cryptoPnl = cryptoPos.reduce((s, p) => s + parseFloat(p.unrealized_pl), 0);

  function getStopTarget(sym: string, entry: number, isCrypto: boolean): { stop: number; target: number; source: string } {
    const s = (stops as StopsData)[sym];
    if (s) return { stop: s.stop_price, target: s.target_price, source: `ATR (${s.tier})` };
    const sp = isCrypto ? 0.12 : 0.07;
    const tp = isCrypto ? 0.25 : 0.15;
    return { stop: entry * (1 - sp), target: entry * (1 + tp), source: 'config %' };
  }

  function posStatus(cur: number, stop: number, target: number): 'safe' | 'warn-stop' | 'warn-target' {
    if (cur <= stop * 1.02)   return 'warn-stop';
    if (cur >= target * 0.97) return 'warn-target';
    return 'safe';
  }

  const allPos = [...stockPos, ...cryptoPos];

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <KpiCard label="Stock Value"  value={fmt$(stockVal)}  sub={`P&L ${fmtPct(stockPnl / (stockVal - stockPnl || 1) * 100)}`} subColor={colorStyle(stockPnl)} />
        <KpiCard label="Crypto Value" value={fmt$(cryptoVal)} sub={`P&L ${fmtPct(cryptoPnl / (cryptoVal - cryptoPnl || 1) * 100)}`} subColor={colorStyle(cryptoPnl)} />
        <KpiCard label="Stock Positions"  value={String(stockPos.length)} />
        <KpiCard label="Crypto Positions" value={String(cryptoPos.length)} />
        <KpiCard label="Total Positions"  value={String(allPos.length)} />
      </div>

      {/* Positions table */}
      {allPos.length > 0 ? (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th className="text-right">Units</th>
                <th className="text-right">Entry</th>
                <th className="text-right">Current</th>
                <th className="text-right">Mkt Value</th>
                <th className="text-right">P&amp;L $</th>
                <th className="text-right">P&amp;L %</th>
                <th className="text-right">Stop</th>
                <th className="text-right">Target</th>
                <th>Stop Source</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {allPos.map(p => {
                const isCrypto = CRYPTO_SYMBOLS.has(p.symbol);
                const entry    = parseFloat(p.avg_entry_price);
                const cur      = parseFloat(p.current_price) || entry;
                const qty      = parseFloat(p.qty);
                const mv       = parseFloat(p.market_value);
                const pnl      = parseFloat(p.unrealized_pl);
                const pnlPct   = parseFloat(p.unrealized_plpc) * 100;
                const { stop, target, source } = getStopTarget(p.symbol, entry, isCrypto);
                const status   = posStatus(cur, stop, target);

                return (
                  <tr key={p.symbol}>
                    <td className="font-semibold">{p.symbol}</td>
                    <td><Badge color={isCrypto ? 'blue' : 'green'}>{isCrypto ? '🔗' : '📈'}</Badge></td>
                    <td className="text-right font-mono text-xs">
                      {isCrypto ? qty.toFixed(4) : qty.toFixed(0)}
                    </td>
                    <td className="text-right font-mono text-xs">{fmtPrice(entry, isCrypto)}</td>
                    <td className="text-right font-mono text-xs">{fmtPrice(cur,   isCrypto)}</td>
                    <td className="text-right font-mono">{fmt$(mv)}</td>
                    <td className="text-right font-mono" style={{ color: colorStyle(pnl) }}>{pnl >= 0 ? '+' : ''}{fmt$(pnl)}</td>
                    <td className="text-right font-mono" style={{ color: colorStyle(pnlPct) }}>{fmtPct(pnlPct)}</td>
                    <td className="text-right font-mono text-xs text-red-400">{fmtPrice(stop,   isCrypto)}</td>
                    <td className="text-right font-mono text-xs text-green-400">{fmtPrice(target, isCrypto)}</td>
                    <td className="text-xs text-[#6b7280]">{source}</td>
                    <td>
                      {status === 'safe'        && <Badge color="green">Safe</Badge>}
                      {status === 'warn-stop'   && <Badge color="red">Near Stop</Badge>}
                      {status === 'warn-target' && <Badge color="amber">Near Target</Badge>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-10 text-center text-[#6b7280] text-sm">
          No open positions — bot is scanning for entry signals.
        </div>
      )}

      {/* Stop progress bars */}
      {allPos.length > 0 && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-4">Stop → Target Progress</p>
          <div className="space-y-3">
            {allPos.map(p => {
              const isCrypto = CRYPTO_SYMBOLS.has(p.symbol);
              const entry    = parseFloat(p.avg_entry_price);
              const cur      = parseFloat(p.current_price) || entry;
              const { stop, target } = getStopTarget(p.symbol, entry, isCrypto);
              const range    = target - stop;
              const pct      = range > 0 ? Math.max(0, Math.min(100, ((cur - stop) / range) * 100)) : 50;
              const pnlPct   = parseFloat(p.unrealized_plpc) * 100;
              const barColor = pct < 20 ? '#f87171' : pct > 80 ? '#fbbf24' : '#4ade80';

              return (
                <div key={p.symbol} className="flex items-center gap-3">
                  <span className="text-xs font-semibold w-20 shrink-0">{p.symbol}</span>
                  <span className="text-[10px] text-red-400 font-mono w-14 shrink-0 text-right">
                    {fmtPrice(stop, isCrypto)}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-[#1e1e35] overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, background: barColor }}
                    />
                  </div>
                  <span className="text-[10px] text-green-400 font-mono w-14 shrink-0">
                    {fmtPrice(target, isCrypto)}
                  </span>
                  <span className="text-[11px] font-mono w-14 shrink-0 text-right" style={{ color: colorStyle(pnlPct) }}>
                    {fmtPct(pnlPct)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
