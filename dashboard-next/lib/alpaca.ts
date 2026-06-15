import { normalizeSymbol } from './utils';
import type { Account, Position, Order, PortfolioHistory } from './types';

const KEY    = process.env.ALPACA_API_KEY    ?? '';
const SECRET = process.env.ALPACA_SECRET_KEY ?? '';
const BASE   = (process.env.ALPACA_BASE_URL  ?? 'https://paper-api.alpaca.markets/v2').replace(/\/$/, '');

const HEADERS = {
  'APCA-API-KEY-ID':     KEY,
  'APCA-API-SECRET-KEY': SECRET,
  'Content-Type':        'application/json',
};

async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString(), { headers: HEADERS, next: { revalidate: 0 } });
  if (!res.ok) throw new Error(`Alpaca ${path} → ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export async function getAccount(): Promise<Account> {
  return apiFetch<Account>('/account');
}

export async function getPositions(): Promise<Position[]> {
  const raw = await apiFetch<Position[]>('/positions');
  return raw.map(p => ({ ...p, symbol: normalizeSymbol(p.symbol) }));
}

export async function getOrders(status = 'all', limit = 200): Promise<Order[]> {
  const raw = await apiFetch<Order[]>('/orders', {
    status, limit: String(limit), direction: 'desc',
  });
  return (Array.isArray(raw) ? raw : []).map(o => ({
    ...o, symbol: normalizeSymbol(o.symbol),
  }));
}

export async function getPortfolioHistory(): Promise<PortfolioHistory> {
  return apiFetch<PortfolioHistory>('/account/portfolio/history', {
    period: '1M', timeframe: '1D', extended_hours: 'false',
  });
}
