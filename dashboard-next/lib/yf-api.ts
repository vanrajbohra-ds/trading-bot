// Direct Yahoo Finance API calls — avoids yahoo-finance2 version/interop issues

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  'Accept': 'application/json',
};

export interface HistoryRow {
  date: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchHistory(
  symbol: string,
  period1: Date,
  period2: Date = new Date(),
  interval: '1d' | '1wk' | '1mo' = '1d',
): Promise<HistoryRow[]> {
  const p1 = Math.floor(period1.getTime() / 1000);
  const p2 = Math.floor(period2.getTime() / 1000);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?period1=${p1}&period2=${p2}&interval=${interval}&events=history`;

  const res  = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`YF chart ${symbol} → ${res.status}`);
  const json = await res.json() as Record<string, unknown>;

  const result = (json?.chart as Record<string, unknown>)?.result as Record<string, unknown>[] | null;
  if (!result?.[0]) return [];

  const r          = result[0];
  const timestamps = (r.timestamp as number[]) ?? [];
  const quote      = ((r.indicators as Record<string, unknown>)?.quote as Record<string, unknown>[])?.[0] ?? {};
  const opens      = (quote.open   as (number | null)[]) ?? [];
  const highs      = (quote.high   as (number | null)[]) ?? [];
  const lows       = (quote.low    as (number | null)[]) ?? [];
  const closes     = (quote.close  as (number | null)[]) ?? [];
  const volumes    = (quote.volume as (number | null)[]) ?? [];

  const rows: HistoryRow[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const c = closes[i];
    if (c === null || c === undefined) continue;
    rows.push({
      date:   new Date(timestamps[i] * 1000),
      open:   opens[i]   ?? c,
      high:   highs[i]   ?? c,
      low:    lows[i]    ?? c,
      close:  c,
      volume: volumes[i] ?? 0,
    });
  }
  return rows;
}

export async function fetchQuoteSummary(
  symbol: string,
  modules: string[],
): Promise<Record<string, unknown>> {
  const mods = modules.join(',');
  const url  = `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(symbol)}?modules=${mods}`;

  const res  = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`YF quoteSummary ${symbol} → ${res.status}`);
  const json = await res.json() as Record<string, unknown>;

  const result = (json?.quoteSummary as Record<string, unknown>)?.result as Record<string, unknown>[] | null;
  return result?.[0] ?? {};
}

export async function fetchSearch(
  symbol: string,
  newsCount = 10,
): Promise<{ news: Record<string, unknown>[] }> {
  const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=${newsCount}&quotesCount=0`;

  const res  = await fetch(url, { headers: HEADERS });
  if (!res.ok) return { news: [] };
  const json = await res.json() as Record<string, unknown>;
  return { news: (json?.news as Record<string, unknown>[]) ?? [] };
}

export async function fetchCurrentPrice(symbol: string): Promise<number | null> {
  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=1d`;
    const res  = await fetch(url, { headers: HEADERS });
    if (!res.ok) return null;
    const json = await res.json() as Record<string, unknown>;
    const meta = ((json?.chart as Record<string, unknown>)?.result as Record<string, unknown>[])?.[0]?.meta as Record<string, unknown>;
    return Number(meta?.regularMarketPrice ?? 0) || null;
  } catch { return null; }
}
