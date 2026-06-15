import { NextResponse } from 'next/server';
import yahooFinance from 'yahoo-finance2';
import { fetchHistory } from '@/lib/yf-api';
import {
  rollingMean, rsi as calcRsi, macd as calcMacd,
  bollingerBands, obv as calcObv, obvTrend, volumeRatio as calcVr,
} from '@/lib/indicators';
import { toYfSymbol, isCryptoSymbol } from '@/lib/utils';
import type { ExploreData, OHLCVRow, TechnicalSignals, FundamentalData, NewsItem, InsiderTransaction } from '@/lib/types';

const BULL_WORDS = ['surge', 'soar', 'beat', 'upgrade', 'buy', 'bullish', 'rally', 'strong', 'record', 'growth', 'profit', 'jump', 'rise'];
const BEAR_WORDS = ['drop', 'fall', 'miss', 'downgrade', 'sell', 'bearish', 'warning', 'probe', 'fraud', 'decline', 'loss', 'cut', 'slump', 'crash'];

function sentimentTag(title: string): '🟢' | '🔴' | '⚪' {
  const t = title.toLowerCase();
  if (BULL_WORDS.some(w => t.includes(w))) return '🟢';
  if (BEAR_WORDS.some(w => t.includes(w))) return '🔴';
  return '⚪';
}

function newsSentiment(news: NewsItem[]): { label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null; score: number | null } {
  if (!news.length) return { label: null, score: null };
  const score = news.reduce((s, n) => s + (n.tag === '🟢' ? 1 : n.tag === '🔴' ? -1 : 0), 0) / news.length;
  return { label: score > 0.1 ? 'BULLISH' : score < -0.1 ? 'BEARISH' : 'NEUTRAL', score };
}

// Parse "2.0 - Buy" or "1.5 - Strong Buy" from Yahoo averageAnalystRating
function parseRating(r: string | null | undefined): string | null {
  if (!r) return null;
  const m = r.match(/-\s*(.+)$/);
  return m ? m[1].trim().toLowerCase() : null;
}

// Direct search (no crumb needed)
async function fetchNews(symbol: string): Promise<NewsItem[]> {
  try {
    const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=10&quotesCount=0&enableFuzzyQuery=false`;
    const res  = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0', Accept: 'application/json' },
    });
    if (!res.ok) return [];
    const json = await res.json() as Record<string, unknown>;
    const items = (json.news as Record<string, unknown>[]) ?? [];
    return items.slice(0, 10).map(n => ({
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
    // ── 1. OHLCV history via direct chart API ─────────────────────────────────
    const period1 = new Date();
    period1.setFullYear(period1.getFullYear() - 1);
    const histRaw = await fetchHistory(yfsymbol, period1);
    if (!histRaw.length) throw new Error(`No price data for ${yfsymbol}`);

    const closes  = histRaw.map(h => h.close);
    const volumes = histRaw.map(h => h.volume);

    // ── 2. Indicators ─────────────────────────────────────────────────────────
    const sma20s  = rollingMean(closes, 20);
    const sma50s  = rollingMean(closes, 50);
    const sma200s = rollingMean(closes, 200);
    const bb      = bollingerBands(closes, 20);
    const rsiVals = calcRsi(closes);
    const macdVal = calcMacd(closes);
    const obvVals = calcObv(closes, volumes);
    const vr      = calcVr(volumes);
    const n       = closes.length;

    const technical: TechnicalSignals = {
      rsi:        rsiVals[n - 1],
      macdHist:   macdVal.hist[n - 1],
      macd:       macdVal.macd[n - 1],
      macdSignal: macdVal.signal[n - 1],
      volRatio:   vr,
      goldenCross: (sma50s[n - 1] !== null && sma200s[n - 1] !== null) ? (sma50s[n - 1]! > sma200s[n - 1]!) : null,
      bbPband:    bb.pband[n - 1],
      bbUpper:    bb.upper[n - 1],
      bbLower:    bb.lower[n - 1],
      obvTrend:   obvTrend(obvVals),
      sma20:      sma20s[n - 1],
      sma50:      sma50s[n - 1],
    };

    // ── 3. Chart rows (last 90 days) ─────────────────────────────────────────
    const chart: OHLCVRow[] = histRaw.slice(-90).map((h, i) => {
      const idx = histRaw.length - 90 + i;
      return {
        date:       h.date.toISOString().slice(0, 10),
        open: h.open, high: h.high, low: h.low, close: h.close, volume: h.volume,
        sma20:      sma20s[idx],  sma50:  sma50s[idx],  sma200:     sma200s[idx],
        bbUpper:    bb.upper[idx], bbLower: bb.lower[idx], bbMid:   bb.mid[idx],
        rsi:        rsiVals[idx],
        macd:       macdVal.macd[idx], macdSignal: macdVal.signal[idx], macdHist: macdVal.hist[idx],
      };
    });

    // ── 4. Fundamentals via yahooFinance.quote() ──────────────────────────────
    // quote() is the one method that reliably works (same endpoint as Prices tab)
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
      const q = await (yahooFinance as unknown as Record<string, (s: string, opts: unknown) => Promise<Record<string, unknown>>>)
        .quote(yfsymbol, { validateResult: false });

      fundamental = {
        ...fundamental,
        currentPrice:          Number(q.regularMarketPrice ?? closes[n - 1]) || null,
        week52High:            Number(q.fiftyTwoWeekHigh  ?? 0) || null,
        week52Low:             Number(q.fiftyTwoWeekLow   ?? 0) || null,
        marketCap:             Number(q.marketCap ?? 0) || null,
        peRatio:               Number(q.trailingPE ?? q.forwardPE ?? 0) || null,
        analystRecommendation: parseRating(q.averageAnalystRating as string),
        analystTargetPrice:    Number(q.targetMeanPrice  ?? 0) || null,
        isCrypto,
      };
    } catch { /* use history close price */ }

    // ── 5. News via direct search ─────────────────────────────────────────────
    const news = await fetchNews(yfsymbol);
    const sent = newsSentiment(news);
    fundamental.newsSentimentLabel = sent.label;
    fundamental.newsSentimentScore = sent.score;

    // ── 6. Insider transactions (try quoteSummary, skip gracefully) ───────────
    let insider: InsiderTransaction[] = [];
    if (!isCrypto) {
      try {
        const yf  = yahooFinance as unknown as Record<string, (s: string, o: unknown, opts: unknown) => Promise<Record<string, unknown>>>;
        const it  = await yf.quoteSummary(yfsymbol, { modules: ['insiderTransactions'] }, { validateResult: false });
        const txns = ((it as Record<string, unknown>).insiderTransactions as Record<string, unknown> | undefined)?.transactions as Record<string, unknown>[] | undefined;
        if (Array.isArray(txns)) {
          const cutoff = Date.now() - 90 * 86_400_000;
          insider = txns
            .filter(t => {
              const raw = t.startDate as Record<string, unknown> | undefined;
              const ts  = Number(raw?.raw ?? 0) * 1000;
              return ts >= cutoff;
            })
            .slice(0, 5)
            .map(t => {
              const sd = (t.startDate as Record<string, unknown>)?.raw;
              return {
                name:   String(t.filerName ?? ''),
                role:   String(t.filerRelation ?? ''),
                shares: Number((t.shares as Record<string, unknown>)?.raw ?? 0),
                value:  Number((t.value  as Record<string, unknown>)?.raw ?? 0),
                type:   String(t.transactionDescription ?? ''),
                date:   new Date(Number(sd ?? 0) * 1000).toISOString().slice(0, 10),
              };
            });
        }
      } catch { /* insider unavailable */ }
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
