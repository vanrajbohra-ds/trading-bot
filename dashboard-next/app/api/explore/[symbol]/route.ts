import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { fetchHistory } from '@/lib/yf-api';
import {
  rollingMean, ema, rsi as calcRsi, macd as calcMacd,
  bollingerBands, obv as calcObv, obvTrend, volumeRatio as calcVr,
} from '@/lib/indicators';
import { toYfSymbol, isCryptoSymbol } from '@/lib/utils';
import type { ExploreData, OHLCVRow, TechnicalSignals, FundamentalData, NewsItem, InsiderTransaction } from '@/lib/types';

const BULL_WORDS = ['surge', 'soar', 'beat', 'upgrade', 'buy', 'bullish', 'rally', 'strong', 'record', 'growth', 'profit'];
const BEAR_WORDS = ['drop', 'fall', 'miss', 'downgrade', 'sell', 'bearish', 'warning', 'probe', 'fraud', 'decline', 'loss', 'cut'];

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

function daysUntil(ts: number | null): number | null {
  if (!ts) return null;
  const diff = Math.round((ts * 1000 - Date.now()) / 86_400_000);
  return diff >= 0 && diff <= 90 ? diff : null;
}

function raw(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'object' && v !== null && 'raw' in v) return Number((v as Record<string, unknown>).raw) || null;
  return Number(v) || null;
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

    const histRaw = await fetchHistory(yfsymbol, period1);
    if (!histRaw.length) throw new Error(`No price data for ${yfsymbol}`);

    const closes  = histRaw.map(h => h.close);
    const highs   = histRaw.map(h => h.high);
    const lows    = histRaw.map(h => h.low);
    const volumes = histRaw.map(h => h.volume);

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
      bbPband, bbUpper, bbLower,
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
        volume:     h.volume,
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

    // ── 4. Fundamentals ───────────────────────────────────────────────────────
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
        : ['price', 'summaryDetail', 'financialData', 'defaultKeyStatistics', 'calendarEvents'] as const;

      const qs         = await (yahooFinance as unknown as Record<string, (s: string, o: unknown, opts: unknown) => Promise<Record<string, unknown>>>).quoteSummary(yfsymbol, { modules }, { validateResult: false });
      const price      = (qs.price      as Record<string, unknown>) ?? {};
      const detail     = (qs.summaryDetail as Record<string, unknown>) ?? {};
      const financial  = (qs.financialData as Record<string, unknown>) ?? {};
      const keyStats   = (qs.defaultKeyStatistics as Record<string, unknown>) ?? {};
      const calendar   = (qs.calendarEvents as Record<string, unknown>) ?? {};
      const earnings   = (calendar.earnings as Record<string, unknown>) ?? {};
      const earningsDateArr = (earnings.earningsDate as Record<string, unknown>[]) ?? [];
      const firstEarnings   = earningsDateArr[0] ? raw(earningsDateArr[0]) : null;

      fundamental = {
        ...fundamental,
        currentPrice:          raw(price.regularMarketPrice) ?? closes[n - 1],
        week52High:            raw(detail.fiftyTwoWeekHigh),
        week52Low:             raw(detail.fiftyTwoWeekLow),
        marketCap:             raw(price.marketCap) ?? raw(detail.marketCap),
        peRatio:               raw(detail.trailingPE) ?? raw(keyStats.trailingPE),
        revenueGrowth:         raw(financial.revenueGrowth),
        analystTargetPrice:    raw(financial.targetMeanPrice),
        analystRecommendation: String(financial.recommendationKey ?? '') || null,
        earningsInDays:        daysUntil(firstEarnings),
        isCrypto,
      };
    } catch { /* use defaults */ }

    // ── 5. News ───────────────────────────────────────────────────────────────
    let news: NewsItem[] = [];
    try {
      const yf = yahooFinance as unknown as Record<string, (s: string, o: unknown, opts: unknown) => Promise<Record<string, unknown>>>;
      const sr = await yf.search(yfsymbol, { newsCount: 10, quotesCount: 0 }, { validateResult: false });
      news = ((sr.news ?? []) as Record<string, unknown>[]).slice(0, 10).map(n => ({
        dt:     n.providerPublishTime ? new Date(Number(n.providerPublishTime) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
        title:  String(n.title ?? ''),
        source: String(n.publisher ?? ''),
        tag:    sentimentTag(String(n.title ?? '')),
      }));
    } catch { /* no news */ }

    const sent = newsSentiment(news);
    fundamental.newsSentimentLabel = sent.label;
    fundamental.newsSentimentScore = sent.score;

    // ── 6. Insider transactions (stocks only) ─────────────────────────────────
    let insider: InsiderTransaction[] = [];
    if (!isCrypto) {
      try {
        const yfi  = yahooFinance as unknown as Record<string, (s: string, o: unknown, opts: unknown) => Promise<Record<string, unknown>>>;
        const it   = await yfi.quoteSummary(yfsymbol, { modules: ['insiderTransactions'] }, { validateResult: false });
        const txns = ((it as Record<string, unknown>).insiderTransactions as Record<string, unknown> | undefined)?.transactions as Record<string, unknown>[] | undefined;
        if (Array.isArray(txns)) {
          const cutoff = Date.now() - 90 * 86_400_000;
          insider = txns
            .filter(t => (raw(t.startDate) ?? 0) * 1000 >= cutoff)
            .slice(0, 5)
            .map(t => ({
              name:   String(t.filerName ?? ''),
              role:   String(t.filerRelation ?? ''),
              shares: raw(t.shares) ?? 0,
              value:  raw(t.value)  ?? 0,
              type:   String(t.transactionDescription ?? ''),
              date:   new Date((raw(t.startDate) ?? 0) * 1000).toISOString().slice(0, 10),
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
