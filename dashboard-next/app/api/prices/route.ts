import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { CRYPTO_YF_MAP, toYfSymbol } from '@/lib/utils';
import type { PriceQuote } from '@/lib/types';

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbolsParam = searchParams.get('symbols') ?? '';
  const stockSymbols = symbolsParam ? symbolsParam.split(',').filter(Boolean) : [];

  const cryptoEntries = Object.entries(CRYPTO_YF_MAP);

  const results: PriceQuote[] = [];

  // Stocks
  for (const sym of stockSymbols) {
    try {
      const q = await yahooFinance.quote(sym, {}, { validateResult: false });
      results.push({
        symbol:    sym,
        label:     sym,
        price:     q.regularMarketPrice ?? 0,
        change:    q.regularMarketChange ?? 0,
        changePct: q.regularMarketChangePercent ?? 0,
      });
    } catch {
      results.push({ symbol: sym, label: sym, price: 0, change: 0, changePct: 0 });
    }
  }

  // Crypto
  for (const [alpacaSym, yfSym] of cryptoEntries) {
    try {
      const q = await yahooFinance.quote(yfSym, {}, { validateResult: false });
      results.push({
        symbol:    alpacaSym,
        label:     alpacaSym.replace('/USD', ''),
        price:     q.regularMarketPrice ?? 0,
        change:    q.regularMarketChange ?? 0,
        changePct: q.regularMarketChangePercent ?? 0,
      });
    } catch {
      results.push({ symbol: alpacaSym, label: alpacaSym.replace('/USD', ''), price: 0, change: 0, changePct: 0 });
    }
  }

  return NextResponse.json(results);
}
