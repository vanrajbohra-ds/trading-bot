import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import {
  rollingMean, ema, rsi as calcRsi, macd as calcMacd,
  bollingerBands, obv as calcObv, obvTrend, volumeRatio as calcVr,
} from '@/lib/indicators';
import { toYfSymbol, isCryptoSymbol } from '@/lib/utils';
import type { ExploreData, OHLCVRow, TechnicalSignals, FundamentalData, NewsItem, InsiderTransaction } from '@/lib/types';

const BULL_WORDS  = ['surge', 'soar', 'beat', 'upgrade', 'buy', 'bullish', 'rally', 'strong', 'record', 'growth', 'profit'];
const BEAR_WORDS  = ['drop', 'fall', 'miss', 'downgrade', 'sell', 'bearish', 'warning', 'probe', 'fraud', 'decline', 'loss', 'cut'];

function sentimentTag(title: string): '🟢' | '🔴' | '⚪' {
  const t = title.toLowerCase();
  if (BULL_WORDS.some(w => t.includes(w))) return '🟢';
  if (BEAR_WORDS.some(w => t.includes(w))) return '🔴';
  return '⚪';
}

function newsSentiment(news: NewsItem[]): { label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null; score: number | null } {
  if (!news.length) return { label: null, score: null };
  const score = news.reduce((s, n) => s + (n.tag === '🟢' ? 1 : n.tag === '🔴' ? -1 : 0), 0) / news.length;
  const label = score > 0.1 ? 'BULLISH' : score < -0.1 ? 'BEARISH' : 'NEUTRAL';
  return { label, score };
}

function daysUntil(ts: number | Date | null): number | null {
  if (!ts) return null;
  const d = typeof ts === 'number' ? new Date(ts * 1000) : ts;
  const diff = Math.round((d.getTime() - Date.now()) / 86_400_000);
  return diff >= 0 && diff <= 90 ? diff : null;
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
    // ── 1. Historical OHLCV (1 year) ─────────────────────────────────────────
    const period1 = new Date();
    period1.setFullYear(period1.getFullYear() - 1);

    const histRaw = await yahooFinance.historical(
      yfsymbol,
      { period1, interval: '1d' },
      { validateResult: false },
    );

    const closes  = histRaw.map(h => h.close);
    const highs   = histRaw.map(h => h.high);
    const lows    = histRaw.map(h => h.low);
    const volumes = histRaw.map(h => h.volume ?? 0);

    // ── 2. Compute indicators ─────────────────────────────────────────────────
    const sma20s  = rollingMean(closes, 20);
    const sma50s  = rollingMean(closes, 50);
    const sma200s = rollingMean(closes, 200);
    const bb      = bollingerBands(closes, 20);
    const rsiVals = calcRsi(closes);
    const macdVal = calcMacd(closes);
    const obvVals = calcObv(closes, volumes);
    const vr      = calcVr(volumes);

    const n         = closes.length;
    const rsiLast   = rsiVals[n - 1];
    const macdLast  = macdVal.hist[n - 1];
    const macdLine  = macdVal.macd[n - 1];
    const macdSig   = macdVal.signal[n - 1];
    const bbPband   = bb.pband[n - 1];
    const bbUpper   = bb.upper[n - 1];
    const bbLower   = bb.lower[n - 1];
    const s50       = sma50s[n - 1];
    const s200      = sma200s[n - 1];
    const obvT      = obvTrend(obvVals);

    const technical: TechnicalSignals = {
      rsi:        rsiLast,
      macdHist:   macdLast,
      macd:       macdLine,
      macdSignal: macdSig,
      volRatio:   vr,
      goldenCross: (s50 !== null && s200 !== null) ? s50 > s200 : null,
      bbPband,
      bbUpper,
      bbLower,
      obvTrend:   obvT,
      sma20:      sma20s[n - 1],
      sma50:      s50,
    };

    // ── 3. Chart rows (last 90 trading days) ─────────────────────────────────
    const chart: OHLCVRow[] = histRaw.slice(-90).map((h, i) => {
      const idx = histRaw.length - 90 + i;
      return {
        date:       h.date.toISOString().slice(0, 10),
        open:       h.open,
        high:       h.high,
        low:        h.low,
        close:      h.close,
        volume:     h.volume ?? 0,
        sma20:      sma20s[idx],
        sma50:      sma50s[idx],
        sma200:     sma200s[idx],
        bbUpper:    bb.upper[idx],
        bbLower:    bb.lower[idx],
        bbMid:      bb.mid[idx],
        rsi:        rsiVals[idx],
        macd:       macdVal.macd[idx],
        macdSignal: macdVal.signal[idx],
        macdHist:   macdVal.hist[idx],
      };
    });

    // ── 4. Fundamentals via quoteSummary ──────────────────────────────────────
    let fundamental: FundamentalData = {
      currentPrice: closes[n - 1] ?? null,
      analystRecommendation: null, analystTargetPrice: null,
      peRatio: null, revenueGrowth: null,
      newsSentimentLabel: null, newsSentimentScore: null,
      week52High: null, week52Low: null, marketCap: null,
      putCallRatio: null, earningsInDays: null,
      isCrypto,
    };

    try {
      const modules = isCrypto
        ? ['price', 'summaryDetail'] as const
        : ['price', 'summaryDetail', 'financialData', 'defaultKeyStatistics', 'recommendationTrend', 'calendarEvents'] as const;

      const qs = await yahooFinance.quoteSummary(yfsymbol, { modules }, { validateResult: false });

      const price      = qs.price ?? {};
      const detail     = qs.summaryDetail ?? {};
      const financial  = (qs as Record<string, unknown>).financialData as Record<string, unknown> | undefined ?? {};
      const keyStats   = (qs as Record<string, unknown>).defaultKeyStatistics as Record<string, unknown> | undefined ?? {};
      const calendar   = (qs as Record<string, unknown>).calendarEvents as Record<string, unknown> | undefined ?? {};

      fundamental = {
        ...fundamental,
        currentPrice:          Number(price.regularMarketPrice ?? closes[n - 1] ?? 0) || null,
        week52High:            Number(detail.fiftyTwoWeekHigh ?? 0) || null,
        week52Low:             Number(detail.fiftyTwoWeekLow  ?? 0) || null,
        marketCap:             Number(price.marketCap ?? detail.marketCap ?? 0) || null,
        peRatio:               Number(detail.trailingPE ?? keyStats.trailingPE ?? 0) || null,
        revenueGrowth:         Number((financial.revenueGrowth as Record<string, unknown>)?.raw ?? financial.revenueGrowth ?? 0) || null,
        analystTargetPrice:    Number((financial.targetMeanPrice as Record<string, unknown>)?.raw ?? financial.targetMeanPrice ?? 0) || null,
        analystRecommendation: String((financial.recommendationKey as string) ?? '') || null,
        earningsInDays:        daysUntil((calendar.earnings as Record<string, unknown>)?.earningsDate as number ?? null),
        isCrypto,
      };
    } catch { /* use defaults */ }

    // ── 5. News ───────────────────────────────────────────────────────────────
    let news: NewsItem[] = [];
    try {
      const sr = await yahooFinance.search(yfsymbol, { newsCount: 10, quotesCount: 0 }, { validateResult: false });
      news = ((sr.news ?? []) as Record<string, unknown>[]).slice(0, 10).map(n => ({
        dt:     n.providerPublishTime ? new Date(Number(n.providerPublishTime) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
        title:  String(n.title ?? ''),
        source: String(n.publisher ?? ''),
        tag:    sentimentTag(String(n.title ?? '')),
      }));
    } catch { /* no news */ }

    // Apply sentiment from news
    const sent = newsSentiment(news);
    fundamental.newsSentimentLabel = sent.label;
    fundamental.newsSentimentScore = sent.score;

    // ── 6. Insider transactions (stocks only) ─────────────────────────────────
    let insider: InsiderTransaction[] = [];
    if (!isCrypto) {
      try {
        const it = await yahooFinance.quoteSummary(yfsymbol, { modules: ['insiderTransactions'] }, { validateResult: false });
        const txns = ((it as Record<string, unknown>).insiderTransactions as Record<string, unknown> | undefined)?.transactions;
        if (Array.isArray(txns)) {
          // Filter last 90 days
          const cutoff = Date.now() - 90 * 86_400_000;
          insider = txns
            .filter((t: Record<string, unknown>) => {
              const ts = Number((t.startDate as Record<string, unknown>)?.raw ?? 0) * 1000;
              return ts >= cutoff;
            })
            .slice(0, 5)
            .map((t: Record<string, unknown>) => ({
              name:   String((t.filerName as string) ?? ''),
              role:   String((t.filerRelation as string) ?? ''),
              shares: Number((t.shares as Record<string, unknown>)?.raw ?? 0),
              value:  Number((t.value as Record<string, unknown>)?.raw ?? 0),
              type:   String((t.transactionDescription as string) ?? ''),
              date:   new Date(Number((t.startDate as Record<string, unknown>)?.raw ?? 0) * 1000).toISOString().slice(0, 10),
            }));
        }
      } catch { /* no insider data */ }
    }

    const result: ExploreData = {
      symbol, yfsymbol, isCrypto,
      currentPrice: fundamental.currentPrice,
      chart, technical, fundamental, news, insider,
    };

    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ symbol, error: String(e) } as Partial<ExploreData>, { status: 500 });
  }
}
