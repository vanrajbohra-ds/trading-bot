'use client';

import useSWR from 'swr';
import KpiCard from '@/components/KpiCard';
import Spinner from '@/components/Spinner';
import { fmtCryptoPrice, fmt$, colorStyle } from '@/lib/utils';
import type { PriceQuote, Order } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

interface Props { watchlist: string[]; orders: Order[] }

export default function PricesTab({ watchlist, orders }: Props) {
  const symbolsParam = watchlist.join(',');
  const { data: prices, isLoading } = useSWR<PriceQuote[]>(
    `/api/prices?symbols=${symbolsParam}`,
    fetcher,
    { refreshInterval: 30_000 },
  );

  const filled = orders.filter(o => o.status === 'filled');
  const sells  = filled.filter(o => o.side === 'sell');

  function calcPnl(o: Order): number {
    const buys = filled.filter(b => b.symbol === o.symbol && b.side === 'buy' && (b.filled_at ?? '') < (o.filled_at ?? ''));
    if (!buys.length) return 0;
    const ap = buys.reduce((s, b) => s + parseFloat(b.filled_avg_price ?? '0'), 0) / buys.length;
    return (parseFloat(o.filled_avg_price ?? '0') - ap) * parseFloat(o.filled_qty ?? '0');
  }

  const tradePnls = sells.map(o => calcPnl(o));
  const wins      = tradePnls.filter(v => v > 0);
  const losses    = tradePnls.filter(v => v <= 0);
  const best      = wins.length   ? Math.max(...wins)   : 0;
  const worst     = losses.length ? Math.min(...losses) : 0;
  const avgW      = wins.length   ? wins.reduce((s, v) => s + v, 0) / wins.length     : 0;
  const avgL      = losses.length ? losses.reduce((s, v) => s + v, 0) / losses.length : 0;

  const stockPrices  = prices?.filter(p => !p.symbol.includes('/')) ?? [];
  const cryptoPrices = prices?.filter(p =>  p.symbol.includes('/')) ?? [];

  if (isLoading) return <Spinner text="Fetching live prices…" />;

  return (
    <div className="space-y-6">
      {/* Stocks */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">📈 Stocks — live</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {stockPrices.map(q => (
            <PriceCard key={q.symbol} quote={q} />
          ))}
        </div>
      </div>

      {/* Crypto */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">🔗 Crypto — live</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-3">
          {cryptoPrices.map(q => (
            <PriceCard key={q.symbol} quote={q} isCrypto />
          ))}
        </div>
      </div>

      {/* Performance stats */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">📊 Performance Stats</p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <KpiCard label="Total Orders"   value={String(filled.length)} />
          <KpiCard label="Closed Trades"  value={String(sells.length)} />
          <KpiCard label="Best Trade"     value={fmt$(best)}  valueColor={colorStyle(best)} />
          <KpiCard label="Worst Trade"    value={fmt$(worst)} valueColor={colorStyle(worst)} />
          <KpiCard label="Avg Win / Loss" value={`${fmt$(avgW)} / ${fmt$(avgL)}`} />
        </div>
      </div>
    </div>
  );
}

function PriceCard({ quote, isCrypto = false }: { quote: PriceQuote; isCrypto?: boolean }) {
  const priceStr = isCrypto ? fmtCryptoPrice(quote.price) : fmt$(quote.price);
  const pctColor = colorStyle(quote.changePct);
  const sign     = quote.changePct >= 0 ? '+' : '';

  return (
    <div className="rounded-xl border border-[#1e1e35] bg-[#111122] px-3 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#6b7280] truncate">
        {quote.label}
      </p>
      <p className="text-base font-bold font-mono mt-0.5">{priceStr}</p>
      <p className="text-xs font-mono mt-0.5" style={{ color: pctColor }}>
        {sign}{quote.changePct.toFixed(2)}%
      </p>
    </div>
  );
}
