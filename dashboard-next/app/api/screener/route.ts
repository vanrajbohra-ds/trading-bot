import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import type { ScreenerQuote } from '@/lib/types';

const CORE_SYMBOLS = new Set([
  'AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN',
  'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD',
]);

function mapQuote(q: Record<string, unknown>): ScreenerQuote | null {
  const sym   = String(q.symbol ?? '');
  const price = Number(q.regularMarketPrice ?? 0);
  const chgPct= Number(q.regularMarketChangePercent ?? 0);
  const vol   = Number(q.regularMarketVolume ?? 0);
  const avg   = Number(q.averageDailyVolume3Month ?? q.averageDailyVolume10Day ?? 1);
  const mcap  = Number(q.marketCap ?? 0);
  const name  = String(q.shortName ?? q.longName ?? sym);

  if (!sym || price < 2 || sym.includes('=') || CORE_SYMBOLS.has(sym)) return null;
  // Skip ETFs (simple heuristic: ends in X, or common ETF suffix)
  if (/^[A-Z]{4,5}X$/.test(sym)) return null;

  return {
    symbol: sym,
    name,
    price,
    changePct: chgPct,
    volumeRatio: avg > 0 ? vol / avg : 0,
    marketCap: mcap,
  };
}

export async function GET() {
  try {
    const [activesRaw, gainersRaw] = await Promise.allSettled([
      yahooFinance.screener({ scrIds: 'most_actives', count: 20, region: 'US', lang: 'en-US' }, { validateResult: false }),
      yahooFinance.screener({ scrIds: 'day_gainers',  count: 20, region: 'US', lang: 'en-US' }, { validateResult: false }),
    ]);

    const actives = activesRaw.status === 'fulfilled'
      ? (activesRaw.value.quotes as Record<string, unknown>[]).map(mapQuote).filter(Boolean) as ScreenerQuote[]
      : [];

    const gainers = gainersRaw.status === 'fulfilled'
      ? (gainersRaw.value.quotes as Record<string, unknown>[]).map(mapQuote).filter(Boolean) as ScreenerQuote[]
      : [];

    return NextResponse.json({ actives, gainers });
  } catch (e) {
    return NextResponse.json({ actives: [], gainers: [], error: String(e) });
  }
}
