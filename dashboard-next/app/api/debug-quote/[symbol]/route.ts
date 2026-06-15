import { NextResponse } from 'next/server';

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params;
  const sym = decodeURIComponent(symbol).toUpperCase();

  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
  };

  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(sym)}`;

  try {
    const res  = await fetch(url, { headers });
    const body = await res.json();
    const q    = (body?.quoteResponse?.result ?? [])[0] ?? {};
    return NextResponse.json({
      status:   res.status,
      symbol:   sym,
      raw_keys: Object.keys(q),
      relevant: {
        regularMarketPrice:   q.regularMarketPrice,
        trailingPE:           q.trailingPE,
        forwardPE:            q.forwardPE,
        marketCap:            q.marketCap,
        fiftyTwoWeekHigh:     q.fiftyTwoWeekHigh,
        fiftyTwoWeekLow:      q.fiftyTwoWeekLow,
        averageAnalystRating: q.averageAnalystRating,
        targetMeanPrice:      q.targetMeanPrice,
        earningsTimestamp:    q.earningsTimestamp,
      },
      full_result: q,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
