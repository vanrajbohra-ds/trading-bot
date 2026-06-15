import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { fetchHistory } from '@/lib/yf-api';
import {
  rollingMean, rsi as calcRsi, macd as calcMacd,
  bollingerBands, obv as calcObv, obvTrend, volumeRatio as calcVr,
} from '@/lib/indicators';
import { toYfSymbol, isCryptoSymbol } from '@/lib/utils';
import type { ExploreData, OHLCVRow, TechnicalSignals, FundamentalData, NewsItem, InsiderTransaction } from '@/lib/types';

const YF = yahooFinance as unknown as {
  quote:        (s: string, opts?: unknown) => Promise<Record<string, unknown>>;
  quoteSummary: (s: string, opts: unknown, qopts?: unknown) => Promise<Record<string, unknown>>;
};

const BULL = ['surge','soar','beat','upgrade','buy','bullish','rally','strong','record','growth','profit','jump','rise','gain'];
const BEAR = ['drop','fall','miss','downgrade','sell','bearish','warning','probe','fraud','decline','loss','cut','slump','crash'];

function sentimentTag(title: string): '🟢' | '🔴' | '⚪' {
  const t = title.toLowerCase();
  if (BULL.some(w => t.includes(w))) return '🟢';
  if (BEAR.some(w => t.includes(w))) return '🔴';
  return '⚪';
}

function newsSentiment(news: NewsItem[]): { label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null; score: number | null } {
  if (!news.length) return { label: null, score: null };
  const score = news.reduce((s, n) => s + (n.tag === '🟢' ? 1 : n.tag === '🔴' ? -1 : 0), 0) / news.length;
  return { label: score > 0.1 ? 'BULLISH' : score < -0.1 ? 'BEARISH' : 'NEUTRAL', score };
}

function parseRating(r: unknown): string | null {
  if (!r) return null;
  const s = String(r);
  const m = s.match(/-\s*(.+)$/);
  return m ? m[1].trim().toLowerCase() : s.toLowerCase() || null;
}

function rawNum(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'object' && v !== null && 'raw' in v) {
    const n = Number((v as Record<string, unknown>).raw);
    return isNaN(n) ? null : n || null;
  }
  const n = Number(v);
  return isNaN(n) ? null : n || null;
}

async function fetchNews(symbol: string): Promise<NewsItem[]> {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=10&quotesCount=0`,
      { headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' } },
    );
    if (!res.ok) return [];
    const json = await res.json() as Record<string, unknown>;
    return ((json.news as Record<string, unknown>[]) ?? []).slice(0, 10).map(n => ({
      dt:     n.providerPublishTime ? new Date(Number(n.providerPublishTime) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
      title:  String(n.title ?? ''),
      source: String(n.publisher ?? ''),
      tag:    sentimentTag(String(n.title ?? '')),
    }));
  } catch { return []; }
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol: rawSym } = await params;
  const symbol   = decodeURIComponent(rawSym).toUpperCase().trim();
  const isCrypto = isCryptoSymbol(symbol);
  const yfsymbol = toYfSymbol(symbol);

  try {
    // ── 1. OHLCV via direct chart API (no crumb needed) ──────────────────────
    const period1 = new Date();
    period1.setFullYear(period1.getFullYear() - 1);
    const histRaw = await fetchHistory(yfsymbol, period1);
    if (!histRaw.length) throw new Error(`No price data for ${yfsymbol}`);

    const closes  = histRaw.map(h => h.close);
    const volumes = histRaw.map(h => h.volume);
    const n       = closes.length;

    // ── 2. Indicators ─────────────────────────────────────────────────────────
    const sma20s  = rollingMean(closes, 20);
    const sma50s  = rollingMean(closes, 50);
    const sma200s = rollingMean(closes, 200);
    const bb      = bollingerBands(closes, 20);
    const rsiVals = calcRsi(closes);
    const macdVal = calcMacd(closes);
    const obvVals = calcObv(closes, volumes);

    const technical: TechnicalSignals = {
      rsi:        rsiVals[n - 1],
      macdHist:   macdVal.hist[n - 1],
      macd:       macdVal.macd[n - 1],
      macdSignal: macdVal.signal[n - 1],
      volRatio:   calcVr(volumes),
      goldenCross: sma50s[n-1] !== null && sma200s[n-1] !== null ? sma50s[n-1]! > sma200s[n-1]! : null,
      bbPband: bb.pband[n-1], bbUpper: bb.upper[n-1], bbLower: bb.lower[n-1],
      obvTrend: obvTrend(obvVals),
      sma20: sma20s[n-1], sma50: sma50s[n-1],
    };

    const chart: OHLCVRow[] = histRaw.slice(-90).map((h, i) => {
      const idx = histRaw.length - 90 + i;
      return {
        date: h.date.toISOString().slice(0, 10),
        open: h.open, high: h.high, low: h.low, close: h.close, volume: h.volume,
        sma20: sma20s[idx], sma50: sma50s[idx], sma200: sma200s[idx],
        bbUpper: bb.upper[idx], bbLower: bb.lower[idx], bbMid: bb.mid[idx],
        rsi: rsiVals[idx], macd: macdVal.macd[idx], macdSignal: macdVal.signal[idx], macdHist: macdVal.hist[idx],
      };
    });

    // ── 3. Fundamentals ───────────────────────────────────────────────────────
    // Step A: quote() — warms the crumb cache AND gives us basic fields
    let fundamental: FundamentalData = {
      currentPrice: closes[n-1] ?? null, analystRecommendation: null, analystTargetPrice: null,
      peRatio: null, revenueGrowth: null, newsSentimentLabel: null, newsSentimentScore: null,
      week52High: null, week52Low: null, marketCap: null, putCallRatio: null, earningsInDays: null,
      isCrypto,
    };

    try {
      const q = await YF.quote(yfsymbol, { validateResult: false });
      fundamental = {
        ...fundamental,
        currentPrice:       rawNum(q.regularMarketPrice) ?? closes[n-1],
        week52High:         rawNum(q.fiftyTwoWeekHigh),
        week52Low:          rawNum(q.fiftyTwoWeekLow),
        marketCap:          rawNum(q.marketCap),
        peRatio:            rawNum(q.trailingPE) ?? rawNum(q.forwardPE),
        analystRecommendation: parseRating(q.averageAnalystRating),
      };
    } catch { /* use history defaults */ }

    // Step B: quoteSummary() — crumb now cached in-memory by quote() above
    if (!isCrypto) {
      try {
        const qs = await YF.quoteSummary(yfsymbol, {
          modules: ['financialData', 'defaultKeyStatistics', 'calendarEvents'],
        }, { validateResult: false });

        const fin = (qs.financialData  as Record<string, unknown>) ?? {};
        const cal = (qs.calendarEvents as Record<string, unknown>) ?? {};
        const earningsArr = ((cal.earnings as Record<string, unknown>)?.earningsDate as Record<string, unknown>[]) ?? [];
        let earningsInDays: number | null = null;
        if (earningsArr[0]) {
          const ts   = rawNum(earningsArr[0]);
          const diff = ts ? Math.round((ts * 1000 - Date.now()) / 86_400_000) : null;
          earningsInDays = diff !== null && diff >= 0 && diff <= 90 ? diff : null;
        }

        fundamental = {
          ...fundamental,
          revenueGrowth:      rawNum(fin.revenueGrowth),
          analystTargetPrice: rawNum(fin.targetMeanPrice),
          analystRecommendation: String(fin.recommendationKey ?? fundamental.analystRecommendation ?? '').toLowerCase() || fundamental.analystRecommendation,
          earningsInDays,
          putCallRatio:       rawNum((qs.defaultKeyStatistics as Record<string, unknown>)?.impliedSharesOutstanding) ?? null,
        };
      } catch { /* keep basic fundamentals from quote() */ }
    }

    // ── 4. News ───────────────────────────────────────────────────────────────
    const news = await fetchNews(yfsymbol);
    const sent = newsSentiment(news);
    fundamental.newsSentimentLabel = sent.label;
    fundamental.newsSentimentScore = sent.score;

    // ── 5. Insider transactions ───────────────────────────────────────────────
    let insider: InsiderTransaction[] = [];
    if (!isCrypto) {
      try {
        const it   = await YF.quoteSummary(yfsymbol, { modules: ['insiderTransactions'] }, { validateResult: false });
        const txns = ((it.insiderTransactions as Record<string, unknown>)?.transactions) as Record<string, unknown>[] | undefined;
        if (Array.isArray(txns)) {
          const cutoff = Date.now() - 90 * 86_400_000;
          insider = txns
            .filter(t => (rawNum(t.startDate) ?? 0) * 1000 >= cutoff)
            .slice(0, 5)
            .map(t => ({
              name:   String(t.filerName   ?? ''),
              role:   String(t.filerRelation ?? ''),
              shares: rawNum(t.shares) ?? 0,
              value:  rawNum(t.value)  ?? 0,
              type:   String(t.transactionDescription ?? ''),
              date:   new Date((rawNum(t.startDate) ?? 0) * 1000).toISOString().slice(0, 10),
            }));
        }
      } catch { /* no insider data */ }
    }

    return NextResponse.json({
      symbol, yfsymbol, isCrypto,
      currentPrice: fundamental.currentPrice,
      chart, technical, fundamental, news, insider,
    } as ExploreData);
  } catch (e) {
    return NextResponse.json({ symbol, error: String(e) } as Partial<ExploreData>, { status: 500 });
  }
}
