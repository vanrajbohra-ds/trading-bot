import { NextResponse } from 'next/server';
import type { ScreenerQuote } from '@/lib/types';

const CORE_SYMBOLS = new Set([
  'AAPL', 'TSLA', 'NVDA', 'MSFT', 'AMZN',
  'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD',
]);

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  'Accept': 'application/json',
};

async function fetchScreener(scrId: string): Promise<ScreenerQuote[]> {
  const url = `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${scrId}&count=25&region=US&lang=en-US`;
  const res  = await fetch(url, { headers: HEADERS, next: { revalidate: 120 } });
  if (!res.ok) throw new Error(`Yahoo screener ${scrId} returned ${res.status}`);
  const json = await res.json();
  const quotes: Record<string, unknown>[] =
    json?.finance?.result?.[0]?.quotes ?? [];

  return quotes
    .map((q): ScreenerQuote | null => {
      const sym    = String(q.symbol ?? '');
      const price  = Number(q.regularMarketPrice ?? 0);
      const chgPct = Number(q.regularMarketChangePercent ?? 0);
      const vol    = Number(q.regularMarketVolume ?? 0);
      const avg    = Number(q.averageDailyVolume3Month ?? q.averageDailyVolume10Day ?? 1);
      const mcap   = Number(q.marketCap ?? 0);
      const name   = String(q.shortName ?? q.longName ?? sym);

      if (!sym || price < 2 || sym.includes('=') || sym.includes('.')) return null;
      if (CORE_SYMBOLS.has(sym)) return null;
      if (/^[A-Z]{4,5}X$/.test(sym)) return null; // skip ETFs

      return {
        symbol: sym,
        name,
        price,
        changePct: chgPct,
        volumeRatio: avg > 0 ? vol / avg : 0,
        marketCap: mcap,
      };
    })
    .filter(Boolean) as ScreenerQuote[];
}

export async function GET() {
  try {
    const [activesResult, gainersResult] = await Promise.allSettled([
      fetchScreener('most_actives'),
      fetchScreener('day_gainers'),
    ]);

    const actives = activesResult.status === 'fulfilled' ? activesResult.value : [];
    const gainers = gainersResult.status === 'fulfilled' ? gainersResult.value : [];

    return NextResponse.json({ actives, gainers });
  } catch (e) {
    return NextResponse.json({ actives: [], gainers: [], error: String(e) });
  }
}
