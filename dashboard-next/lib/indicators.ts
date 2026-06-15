/** Technical indicator implementations matching the Python ta library. */

export function rollingMean(values: number[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    const slice = values.slice(i - window + 1, i + 1);
    return slice.reduce((s, v) => s + v, 0) / window;
  });
}

export function ema(values: number[], span: number): number[] {
  const k = 2 / (span + 1);
  const result: number[] = [];
  let prev = values[0] ?? 0;
  for (const v of values) {
    prev = v * k + prev * (1 - k);
    result.push(prev);
  }
  return result;
}

export function rsi(closes: number[], window = 14): (number | null)[] {
  const n = closes.length;
  const gains = new Array(n).fill(0);
  const losses = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) gains[i] = d;
    else losses[i] = -d;
  }

  const result: (number | null)[] = new Array(window).fill(null);
  let avgG = gains.slice(1, window + 1).reduce((s, v) => s + v, 0) / window;
  let avgL = losses.slice(1, window + 1).reduce((s, v) => s + v, 0) / window;
  const rs0 = avgL === 0 ? 100 : avgG / avgL;
  result.push(100 - 100 / (1 + rs0));

  for (let i = window + 1; i < n; i++) {
    avgG = (avgG * (window - 1) + gains[i]) / window;
    avgL = (avgL * (window - 1) + losses[i]) / window;
    const rs = avgL === 0 ? 100 : avgG / avgL;
    result.push(100 - 100 / (1 + rs));
  }
  return result;
}

export interface MACDResult {
  macd: number[];
  signal: number[];
  hist: number[];
}

export function macd(
  closes: number[],
  fast = 12,
  slow = 26,
  signal = 9,
): MACDResult {
  const fastEma  = ema(closes, fast);
  const slowEma  = ema(closes, slow);
  const macdLine = fastEma.map((v, i) => v - slowEma[i]);
  const sigLine  = ema(macdLine, signal);
  const hist     = macdLine.map((v, i) => v - sigLine[i]);
  return { macd: macdLine, signal: sigLine, hist };
}

export interface BBResult {
  upper: (number | null)[];
  lower: (number | null)[];
  mid:   (number | null)[];
  pband: (number | null)[];
}

export function bollingerBands(closes: number[], window = 20, mult = 2): BBResult {
  const mid   = rollingMean(closes, window);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  const pband: (number | null)[] = [];

  for (let i = 0; i < closes.length; i++) {
    if (mid[i] === null || i < window - 1) {
      upper.push(null); lower.push(null); pband.push(null);
    } else {
      const slice = closes.slice(i - window + 1, i + 1);
      const mean  = mid[i]!;
      const std   = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / window);
      const u = mean + mult * std;
      const l = mean - mult * std;
      upper.push(u); lower.push(l);
      pband.push(u === l ? 0.5 : (closes[i] - l) / (u - l));
    }
  }
  return { upper, lower, mid, pband };
}

export function obv(closes: number[], volumes: number[]): number[] {
  const result: number[] = [0];
  for (let i = 1; i < closes.length; i++) {
    const dir = closes[i] > closes[i - 1] ? 1 : closes[i] < closes[i - 1] ? -1 : 0;
    result.push(result[i - 1] + dir * volumes[i]);
  }
  return result;
}

export function obvTrend(obvValues: number[], lookback = 10): 'RISING' | 'FALLING' | 'FLAT' {
  if (obvValues.length < lookback + 5) return 'FLAT';
  const n    = obvValues.length;
  const rec  = obvValues.slice(n - 5).reduce((s, v) => s + v, 0) / 5;
  const prev = obvValues.slice(n - lookback, n - 5).reduce((s, v) => s + v, 0) / 5;
  if (rec > prev * 1.005) return 'RISING';
  if (rec < prev * 0.995) return 'FALLING';
  return 'FLAT';
}

export function volumeRatio(volumes: number[], fast = 5, slow = 20): number | null {
  if (volumes.length < slow) return null;
  const n = volumes.length;
  const fastAvg = volumes.slice(n - fast).reduce((s, v) => s + v, 0) / fast;
  const slowAvg = volumes.slice(n - slow).reduce((s, v) => s + v, 0) / slow;
  return slowAvg > 0 ? fastAvg / slowAvg : null;
}
