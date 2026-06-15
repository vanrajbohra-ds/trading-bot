export const STARTING_CAP = 100_000;

export const CRYPTO_SYMBOLS = new Set([
  'BTC/USD', 'ETH/USD', 'SOL/USD', 'DOGE/USD', 'AVAX/USD',
  'LTC/USD', 'BCH/USD', 'LINK/USD', 'UNI/USD', 'AAVE/USD',
  'GRT/USD', 'MKR/USD', 'XLM/USD', 'XTZ/USD', 'BAT/USD', 'SHIB/USD',
]);

export const CRYPTO_NORM: Record<string, string> = {
  BTCUSD: 'BTC/USD', ETHUSD: 'ETH/USD', SOLUSD: 'SOL/USD',
  DOGEUSD: 'DOGE/USD', AVAXUSD: 'AVAX/USD', LTCUSD: 'LTC/USD',
  BCHUSD: 'BCH/USD', LINKUSD: 'LINK/USD', UNIUSD: 'UNI/USD',
  AAVEUSD: 'AAVE/USD', GRTUSD: 'GRT/USD', MKRUSD: 'MKR/USD',
  XLMUSD: 'XLM/USD', XTZUSD: 'XTZ/USD', BATUSD: 'BAT/USD',
  SHIBUSD: 'SHIB/USD',
};

export const CRYPTO_YF_MAP: Record<string, string> = {
  'BTC/USD': 'BTC-USD', 'ETH/USD': 'ETH-USD', 'SOL/USD': 'SOL-USD',
  'DOGE/USD': 'DOGE-USD', 'AVAX/USD': 'AVAX-USD', 'LTC/USD': 'LTC-USD',
  'BCH/USD': 'BCH-USD', 'LINK/USD': 'LINK-USD', 'UNI/USD': 'UNI-USD',
  'AAVE/USD': 'AAVE-USD', 'GRT/USD': 'GRT-USD', 'MKR/USD': 'MKR-USD',
  'XLM/USD': 'XLM-USD', 'XTZ/USD': 'XTZ-USD', 'BAT/USD': 'BAT-USD',
  'SHIB/USD': 'SHIB-USD',
};

export function normalizeSymbol(raw: string): string {
  return CRYPTO_NORM[raw] ?? raw;
}

export function toYfSymbol(alpacaSym: string): string {
  return CRYPTO_YF_MAP[alpacaSym] ?? alpacaSym.replace('/', '-');
}

export function isCryptoSymbol(sym: string): boolean {
  return sym.includes('/');
}

export function fmt$(v: number, decimals = 2): string {
  return v.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPct(v: number, decimals = 2): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(decimals)}%`;
}

export function fmtCryptoPrice(v: number): string {
  if (v < 0.01) return `$${v.toFixed(6)}`;
  if (v < 1)    return `$${v.toFixed(4)}`;
  if (v < 10)   return `$${v.toFixed(4)}`;
  return fmt$(v);
}

export function fmtPrice(v: number, isCrypto: boolean): string {
  return isCrypto ? fmtCryptoPrice(v) : fmt$(v);
}

export function fmtCap(v: number): string {
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(0)}M`;
  return '—';
}

export function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso.replace('Z', '+00:00'))
      .toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
        hour12: false, timeZone: 'UTC',
      });
  } catch {
    return '—';
  }
}

export function fmtDateShort(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso.replace('Z', '+00:00'))
      .toLocaleString('en-US', {
        month: 'short', day: 'numeric', timeZone: 'UTC',
      });
  } catch {
    return '—';
  }
}

export function colorClass(v: number): string {
  return v >= 0 ? 'text-green-400' : 'text-red-400';
}

export function colorStyle(v: number): string {
  return v >= 0 ? '#4ade80' : '#f87171';
}
