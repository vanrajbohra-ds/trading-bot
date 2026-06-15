import type { TechnicalSignals, FundamentalData, Score, ScoreSignal } from './types';
import { fmtCap } from './utils';

export function scoreTechnical(t: TechnicalSignals): Score {
  const sigs: ScoreSignal[] = [];
  let raw = 0, mx = 0;

  if (t.rsi !== null) {
    mx += 20;
    if      (t.rsi < 30)  { raw += 20; sigs.push({ icon: '✅', label: `RSI ${t.rsi.toFixed(1)} — OVERSOLD (historical buy zone)` }); }
    else if (t.rsi < 45)  { raw += 13; sigs.push({ icon: '🟡', label: `RSI ${t.rsi.toFixed(1)} — below midline, approaching oversold` }); }
    else if (t.rsi <= 60) { raw += 10; sigs.push({ icon: '🟡', label: `RSI ${t.rsi.toFixed(1)} — neutral` }); }
    else if (t.rsi <= 70) { raw +=  6; sigs.push({ icon: '🟡', label: `RSI ${t.rsi.toFixed(1)} — elevated, nearing overbought` }); }
    else                  {             sigs.push({ icon: '❌', label: `RSI ${t.rsi.toFixed(1)} — OVERBOUGHT (exit risk)` }); }
  }

  if (t.macdHist !== null) {
    mx += 20;
    if (t.macdHist > 0) { raw += 20; sigs.push({ icon: '✅', label: `MACD histogram +${t.macdHist.toFixed(4)} — bullish momentum` }); }
    else                {              sigs.push({ icon: '❌', label: `MACD histogram ${t.macdHist.toFixed(4)} — bearish momentum` }); }
  }

  if (t.volRatio !== null) {
    mx += 15;
    if      (t.volRatio >= 1.8) { raw += 15; sigs.push({ icon: '✅', label: `Volume ${t.volRatio.toFixed(1)}× avg — HIGH (strong conviction)` }); }
    else if (t.volRatio >= 1.2) { raw += 10; sigs.push({ icon: '🟡', label: `Volume ${t.volRatio.toFixed(1)}× avg — above average` }); }
    else if (t.volRatio >= 0.7) { raw +=  7; sigs.push({ icon: '🟡', label: `Volume ${t.volRatio.toFixed(1)}× avg — normal` }); }
    else                        { raw +=  2; sigs.push({ icon: '❌', label: `Volume ${t.volRatio.toFixed(1)}× avg — LOW (weak conviction)` }); }
  }

  if (t.goldenCross !== null) {
    mx += 20;
    if (t.goldenCross) { raw += 20; sigs.push({ icon: '✅', label: 'Golden Cross — SMA50 above SMA200 (long-term uptrend)' }); }
    else               {             sigs.push({ icon: '❌', label: 'Death Cross — SMA50 below SMA200 (long-term downtrend)' }); }
  }

  if (t.bbPband !== null) {
    mx += 15;
    if      (t.bbPband < 0.2) { raw += 15; sigs.push({ icon: '✅', label: `Near lower Bollinger Band (${(t.bbPband * 100).toFixed(0)}%) — potential bounce` }); }
    else if (t.bbPband < 0.4) { raw += 10; sigs.push({ icon: '🟡', label: `Lower-mid Bollinger Band (${(t.bbPband * 100).toFixed(0)}%)` }); }
    else if (t.bbPband < 0.7) { raw +=  7; sigs.push({ icon: '🟡', label: `Mid Bollinger Band (${(t.bbPband * 100).toFixed(0)}%)` }); }
    else                      { raw +=  3; sigs.push({ icon: '❌', label: `Near upper Bollinger Band (${(t.bbPband * 100).toFixed(0)}%) — overbought zone` }); }
  }

  if (t.obvTrend !== null) {
    mx += 10;
    if      (t.obvTrend === 'RISING')  { raw += 10; sigs.push({ icon: '✅', label: 'OBV Rising — accumulation (buying pressure)' }); }
    else if (t.obvTrend === 'FLAT')    { raw +=  5; sigs.push({ icon: '🟡', label: 'OBV Flat — no clear accumulation/distribution' }); }
    else                               {             sigs.push({ icon: '❌', label: 'OBV Falling — distribution (selling pressure)' }); }
  }

  return { score: mx > 0 ? Math.min(100, Math.max(0, Math.round(raw / mx * 100))) : 50, signals: sigs };
}

export function scoreFundamental(f: FundamentalData): Score {
  const sigs: ScoreSignal[] = [];
  let raw = 0, mx = 0;

  if (f.newsSentimentLabel) {
    mx += 20;
    if      (f.newsSentimentLabel === 'BULLISH') { raw += 20; sigs.push({ icon: '✅', label: `News sentiment: BULLISH (${(f.newsSentimentScore ?? 0) >= 0 ? '+' : ''}${(f.newsSentimentScore ?? 0).toFixed(2)})` }); }
    else if (f.newsSentimentLabel === 'NEUTRAL') { raw += 10; sigs.push({ icon: '🟡', label: 'News sentiment: NEUTRAL' }); }
    else                                         {             sigs.push({ icon: '❌', label: `News sentiment: BEARISH (${(f.newsSentimentScore ?? 0).toFixed(2)})` }); }
  }

  if (f.isCrypto) {
    if (f.week52High && f.week52Low && f.currentPrice && f.week52High > f.week52Low) {
      mx += 30;
      const pct = (f.currentPrice - f.week52Low) / (f.week52High - f.week52Low) * 100;
      const lo  = f.week52Low < 10 ? `$${f.week52Low.toFixed(4)}` : `$${f.week52Low.toFixed(2)}`;
      const hi  = f.week52High < 10 ? `$${f.week52High.toFixed(4)}` : `$${f.week52High.toFixed(2)}`;
      if      (pct < 20) { raw += 30; sigs.push({ icon: '✅', label: `${pct.toFixed(0)}% into 52W range [${lo} – ${hi}] — near yearly low` }); }
      else if (pct < 40) { raw += 22; sigs.push({ icon: '✅', label: `${pct.toFixed(0)}% into 52W range — lower half` }); }
      else if (pct < 60) { raw += 15; sigs.push({ icon: '🟡', label: `${pct.toFixed(0)}% into 52W range — mid range` }); }
      else if (pct < 80) { raw +=  8; sigs.push({ icon: '🟡', label: `${pct.toFixed(0)}% into 52W range — upper half` }); }
      else               { raw +=  2; sigs.push({ icon: '❌', label: `${pct.toFixed(0)}% into 52W range — near yearly high` }); }
    }

    if (f.marketCap) {
      mx += 15;
      if      (f.marketCap > 50e9) { raw += 15; sigs.push({ icon: '✅', label: `Market cap ${fmtCap(f.marketCap)} — large cap, established` }); }
      else if (f.marketCap >  5e9) { raw += 10; sigs.push({ icon: '🟡', label: `Market cap ${fmtCap(f.marketCap)} — mid cap` }); }
      else                         { raw +=  5; sigs.push({ icon: '🟡', label: `Market cap ${fmtCap(f.marketCap)} — small cap` }); }
    }
  } else {
    if (f.analystRecommendation) {
      mx += 25;
      const rec = f.analystRecommendation.toLowerCase();
      const rl  = f.analystRecommendation.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      if      (rec.includes('strong_buy') || rec.includes('strong buy')) { raw += 25; sigs.push({ icon: '✅', label: 'Analyst consensus: Strong Buy' }); }
      else if (rec.includes('buy') || rec.includes('outperform'))        { raw += 18; sigs.push({ icon: '✅', label: `Analyst: ${rl}` }); }
      else if (rec.includes('hold') || rec.includes('neutral'))          { raw += 10; sigs.push({ icon: '🟡', label: `Analyst: ${rl}` }); }
      else                                                                { raw +=  2; sigs.push({ icon: '❌', label: `Analyst: ${rl}` }); }
    }

    if (f.analystTargetPrice && f.currentPrice) {
      mx += 15;
      const up = (f.analystTargetPrice - f.currentPrice) / f.currentPrice * 100;
      if      (up > 20) { raw += 15; sigs.push({ icon: '✅', label: `Price target $${f.analystTargetPrice.toFixed(0)} (+${up.toFixed(1)}% upside)` }); }
      else if (up >  5) { raw += 10; sigs.push({ icon: '✅', label: `Price target $${f.analystTargetPrice.toFixed(0)} (+${up.toFixed(1)}% upside)` }); }
      else if (up > -5) { raw +=  5; sigs.push({ icon: '🟡', label: `Price target $${f.analystTargetPrice.toFixed(0)} (${up.toFixed(1)}%)` }); }
      else              {             sigs.push({ icon: '❌', label: `Price target $${f.analystTargetPrice.toFixed(0)} (${up.toFixed(1)}% — below current)` }); }
    }

    if (f.revenueGrowth !== null && f.revenueGrowth !== undefined) {
      mx += 15;
      const rg = f.revenueGrowth * 100;
      if      (rg > 20) { raw += 15; sigs.push({ icon: '✅', label: `Revenue growth +${rg.toFixed(1)}% YoY — strong expansion` }); }
      else if (rg >  0) { raw += 10; sigs.push({ icon: '🟡', label: `Revenue growth +${rg.toFixed(1)}% YoY` }); }
      else              {             sigs.push({ icon: '❌', label: `Revenue declining ${rg.toFixed(1)}% YoY` }); }
    }

    if (f.peRatio) {
      mx += 10;
      if      (f.peRatio < 15) { raw += 10; sigs.push({ icon: '✅', label: `P/E ${f.peRatio.toFixed(1)}× — value territory` }); }
      else if (f.peRatio < 30) { raw +=  7; sigs.push({ icon: '🟡', label: `P/E ${f.peRatio.toFixed(1)}× — fairly valued` }); }
      else if (f.peRatio < 60) { raw +=  4; sigs.push({ icon: '🟡', label: `P/E ${f.peRatio.toFixed(1)}× — growth premium` }); }
      else                     {             sigs.push({ icon: '❌', label: `P/E ${f.peRatio.toFixed(1)}× — expensive` }); }
    }

    if (f.earningsInDays !== null && f.earningsInDays !== undefined) {
      sigs.push({ icon: '⚠️', label: `Earnings in ${f.earningsInDays} days — expect elevated volatility` });
    }
  }

  return { score: mx > 0 ? Math.min(100, Math.max(0, Math.round(raw / mx * 100))) : 50, signals: sigs };
}

export function exploreVerdict(techScore: number, fundScore: number) {
  const combined = Math.round((techScore + fundScore) / 2);
  if (combined >= 68) return { verdict: 'BUY',          color: '#00c853', icon: '📈', combined };
  if (combined >= 48) return { verdict: 'HOLD / WATCH', color: '#f59e0b', icon: '👀', combined };
  return              { verdict: 'AVOID / SELL',         color: '#ef4444', icon: '📉', combined };
}
