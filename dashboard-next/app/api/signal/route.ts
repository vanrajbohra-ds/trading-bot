import { NextResponse } from 'next/server';
import { fetchHistory } from '@/lib/yf-api';
import { rsi as calcRsi, macd as calcMacd, volumeRatio as calcVr } from '@/lib/indicators';
import type { SignalCheck } from '@/lib/types';

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbol = searchParams.get('symbol') ?? '';
  if (!symbol) return NextResponse.json({ error: 'symbol required' }, { status: 400 });

  try {
    const start = new Date();
    start.setMonth(start.getMonth() - 3);
    const hist = await fetchHistory(symbol, start);

    if (!hist || hist.length < 26) {
      return NextResponse.json({ pass: false, checks: 0, rsi: null, volRatio: null, macdHist: null, volOk: false, rsiOk: false, macdOk: false });
    }

    const closes  = hist.map(h => h.close);
    const volumes = hist.map(h => h.volume);

    const rsiVals      = calcRsi(closes);
    const macdVals     = calcMacd(closes);
    const vr           = calcVr(volumes);
    const rsiLast      = rsiVals[rsiVals.length - 1];
    const macdHistLast = macdVals.hist[macdVals.hist.length - 1];

    const volOk  = (vr ?? 0) >= 1.8;
    const rsiOk  = rsiLast !== null && rsiLast >= 55 && rsiLast <= 75;
    const macdOk = macdHistLast > 0;
    const checks = [volOk, rsiOk, macdOk].filter(Boolean).length;

    const result: SignalCheck = {
      pass: checks >= 2,
      checks,
      rsi:      rsiLast,
      volRatio: vr,
      macdHist: macdHistLast,
      volOk,
      rsiOk,
      macdOk,
    };

    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ pass: false, checks: 0, rsi: null, volRatio: null, macdHist: null, volOk: false, rsiOk: false, macdOk: false, error: String(e) });
  }
}
