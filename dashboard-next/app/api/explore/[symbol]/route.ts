import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { fetchHistory } from '@/lib/yf-api';
import {
  rollingMean, rsi as calcRsi, macd as calcMacd,
  bollingerBands, obv as calcObv, obvTrend, volumeRatio as calcVr,
} from '@/lib/indicators';
import { toYfSymbol, isCryptoSymbol } from '@/lib/utils';
import type { ExploreData, OHLCVRow, TechnicalSignals, FundamentalData, NewsItem, InsiderTransaction } from '@/lib/types';

// Cast so we can call without TypeScript complaining (TS errors disabled anyway)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const YF = yahooFinance as any;

const BULL = ['surge','soar','beat','upgrade','buy','bullish','rally','strong','record','growth','profit','jump','rise','gain'];
const BEAR = ['drop','fall','miss','downgrade','sell','bearish','warning','probe','fraud','decline','loss','cut','slump','crash'];

function sentimentTag(title: string): '🟢' | '🔴' | '⚪' {
  const t = title.toLowerCase();
  if (BULL.some(w => t.includes(w))) return '🟢';
  if (BEAR.some(w => t.includes(w))) return '🔴';
  return '⚪';
}

function newsSentiment(news: NewsItem[]) {
  if (!news.length) return { label: null as null, score: null as null };
  const score = news.reduce((s, n) => s + (n.tag === '🟢' ? 1 : n.tag === '🔴' ? -1 : 0), 0) / news.length;
  return { label: (score > 0.1 ? 'BULLISH' : score < -0.1 ? 'BEARISH' : 'NEUTRAL') as 'BULLISH' | 'BEARISH' | 'NEUTRAL', score };
}

function parseRating(r: unknown): string | null {
  if (!r) return null;
  const s = String(r);
  // "1.5 - Strong Buy" → "strong buy", "buy" → "buy"
  const m = s.match(/-\s*(.+)$/);
  return (m ? m[1].trim() : s).toLowerCase() || null;
}

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const num = Number(v);
  return isFinite(num) && num !== 0 ? num : null;
}

async function fetchNews(symbol: string): Promise<NewsItem[]> {
  try {
    const res = await fetch(
      `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=10&quotesCount=0`,
      { headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' } },
    );
    if (!res.ok) return [];
    const json = await res.json() as Record<string, unknown>;
    return ((json.news as Record<string, unknown>[]) ?? []).slice(0, 10).map(item => ({
      dt:     item.providerPublishTime ? new Date(Number(item.providerPublishTime) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
      title:  String(item.title ?? ''),
      source: String(item.publisher ?? ''),
      tag:    sentimentTag(String(item.title ?? '')),
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
    // ── 1. OHLCV via direct chart API ────────────────────────────────────────
    const period1 = new Date();
    period1.setFullYear(period1.getFullYear() - 1);
    const histRaw = await fetchHistory(yfsymbol, period1);
    if (!histRaw.length) throw new Error(`No price data for ${yfsymbol}`);

    const closes  = histRaw.map(h => h.close);
    const volumes = histRaw.map(h => h.volume);
    const len     = closes.length;

    // ── 2. Indicators ─────────────────────────────────────────────────────────
    const sma20s  = rollingMean(closes, 20);
    const sma50s  = rollingMean(closes, 50);
    const sma200s = rollingMean(closes, 200);
    const bb      = bollingerBands(closes, 20);
    const rsiVals = calcRsi(closes);
    const macdVal = calcMacd(closes);
    const obvVals = calcObv(closes, volumes);

    const technical: TechnicalSignals = {
      rsi:        rsiVals[len-1],
      macdHist:   macdVal.hist[len-1],
      macd:       macdVal.macd[len-1],
      macdSignal: macdVal.signal[len-1],
      volRatio:   calcVr(volumes),
      goldenCross: sma50s[len-1] !== null && sma200s[len-1] !== null ? sma50s[len-1]! > sma200s[len-1]! : null,
      bbPband: bb.pband[len-1], bbUpper: bb.upper[len-1], bbLower: bb.lower[len-1],
      obvTrend: obvTrend(obvVals),
      sma20: sma20s[len-1], sma50: sma50s[len-1],
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

    // ── 3. Fundamentals via quote() ───────────────────────────────────────────
    // quote() uses Yahoo Finance v7 (no crumb needed — works on all IPs)
    // It returns: trailingPE, marketCap, 52W high/low, averageAnalystRating,
    //             targetMeanPrice, earningsTimestamp, epsForward, bookValue etc.
    let fundamental: FundamentalData = {
      currentPrice: closes[len-1] ?? null, analystRecommendation: null, analystTargetPrice: null,
      peRatio: null, revenueGrowth: null, newsSentimentLabel: null, newsSentimentScore: null,
      week52High: null, week52Low: null, marketCap: null, putCallRatio: null, earningsInDays: null,
      isCrypto,
    };

    try {
      // IMPORTANT: same call signature as prices/route.ts which is confirmed working
      // args: (symbol, queryOpts, moduleOpts) — queryOpts={} for default fields
      const q = await YF.quote(yfsymbol, {}, { validateResult: false });

      // Earnings days from earningsTimestamp
      const earningsTs   = Number(q.earningsTimestamp ?? q.earningsTimestampStart ?? 0);
      const earningsDiff = earningsTs > 0 ? Math.round((earningsTs * 1000 - Date.now()) / 86_400_000) : null;
      const earningsInDays = earningsDiff !== null && earningsDiff >= 0 && earningsDiff <= 90 ? earningsDiff : null;

      fundamental = {
        ...fundamental,
        currentPrice:          n(q.regularMarketPrice) ?? closes[len-1],
        week52High:            n(q.fiftyTwoWeekHigh),
        week52Low:             n(q.fiftyTwoWeekLow),
        marketCap:             n(q.marketCap),
        peRatio:               n(q.trailingPE) ?? n(q.forwardPE),
        analystRecommendation: parseRating(q.averageAnalystRating),
        analystTargetPrice:    n(q.targetMeanPrice),
        earningsInDays,
      };
    } catch (e) {
      console.error('quote() failed:', e);
    }

    // ── 4. Revenue growth via quoteSummary (try, fails gracefully on Vercel) ──
    // Yahoo Finance v10 requires a crumb which is often blocked on cloud IPs.
    // We try it anyway — on warm Lambdas or less-restricted IPs it may succeed.
    if (!isCrypto) {
      try {
        const qs  = await YF.quoteSummary(yfsymbol, { modules: ['financialData'] }, { validateResult: false });
        const fin = qs?.financialData ?? {};
        if (fin.revenueGrowth != null) fundamental.revenueGrowth = Number(fin.revenueGrowth?.raw ?? fin.revenueGrowth) || null;
        if (fin.targetMeanPrice != null && !fundamental.analystTargetPrice) {
          fundamental.analystTargetPrice = Number(fin.targetMeanPrice?.raw ?? fin.targetMeanPrice) || null;
        }
        if (fin.recommendationKey) {
          fundamental.analystRecommendation = String(fin.recommendationKey).toLowerCase() || fundamental.analystRecommendation;
        }
      } catch { /* quoteSummary blocked on this IP — skip */ }
    }

    // ── 5. News via direct search (no crumb, always works) ────────────────────
    const news = await fetchNews(yfsymbol);
    const sent = newsSentiment(news);
    fundamental.newsSentimentLabel = sent.label;
    fundamental.newsSentimentScore = sent.score;

    // ── 6. Insider transactions via quoteSummary (graceful skip) ──────────────
    let insider: InsiderTransaction[] = [];
    if (!isCrypto) {
      try {
        const it   = await YF.quoteSummary(yfsymbol, { modules: ['insiderTransactions'] }, { validateResult: false });
        const txns = it?.insiderTransactions?.transactions as Record<string, unknown>[] | undefined;
        if (Array.isArray(txns)) {
          const cutoff = Date.now() - 90 * 86_400_000;
          insider = txns
            .filter(t => {
              const ts = Number((t.startDate as Record<string, unknown>)?.raw ?? t.startDate ?? 0) * 1000;
              return ts >= cutoff;
            })
            .slice(0, 5)
            .map(t => {
              const sd = Number((t.startDate as Record<string, unknown>)?.raw ?? t.startDate ?? 0);
              return {
                name:   String(t.filerName   ?? ''),
                role:   String(t.filerRelation ?? ''),
                shares: Number((t.shares as Record<string, unknown>)?.raw ?? t.shares ?? 0),
                value:  Number((t.value  as Record<string, unknown>)?.raw ?? t.value  ?? 0),
                type:   String(t.transactionDescription ?? ''),
                date:   new Date(sd * 1000).toISOString().slice(0, 10),
              };
            });
        }
      } catch { /* insider blocked — show empty */ }
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
