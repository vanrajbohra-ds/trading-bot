'use client';

import { useState, useRef } from 'react';
import useSWR from 'swr';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, Legend, ResponsiveContainer,
} from 'recharts';
import Spinner from '@/components/Spinner';
import Badge from '@/components/Badge';
import { scoreTechnical, scoreFundamental, exploreVerdict } from '@/lib/scoring';
import { fmtPrice, fmtCryptoPrice, fmt$, fmtCap } from '@/lib/utils';
import type { ExploreData, ScoreSignal } from '@/lib/types';

const fetcher = (url: string) => fetch(url).then(r => r.json());

function normalizeInput(raw: string): string {
  const u = raw.toUpperCase().trim().replace(/\s+/g, '');
  if (u.endsWith('-USD')) return u.slice(0, -4) + '/USD';
  if (/^(BTC|ETH|SOL|DOGE|AVAX|LTC|BCH|LINK|UNI|AAVE|GRT|MKR|XLM|XTZ|BAT|SHIB)$/.test(u)) return u + '/USD';
  return u;
}

export default function ExploreTab() {
  const [input,  setInput]  = useState('');
  const [symbol, setSymbol] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, error } = useSWR<ExploreData>(
    symbol ? `/api/explore/${encodeURIComponent(symbol)}` : null,
    fetcher,
    { revalidateOnFocus: false },
  );

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const norm = normalizeInput(input);
    if (norm) setSymbol(norm);
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="NVDA · AAPL · ETH/USD · DOGE · SOL"
          className="flex-1 px-4 py-2.5 bg-[#111122] border border-[#1e1e35] rounded-xl text-sm text-white placeholder-[#4b5563] focus:border-green-500/50 focus:outline-none transition-colors"
        />
        <button
          type="submit"
          className="px-5 py-2.5 bg-green-900/50 border border-green-800/50 text-green-400 rounded-xl text-sm font-semibold hover:bg-green-900/70 transition-colors"
        >
          Analyse →
        </button>
      </form>

      {!symbol && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-10 text-center text-[#6b7280] text-sm">
          💡 Enter any stock (NVDA, AAPL, SMCI) or crypto (ETH/USD, DOGE, SOL) and click Analyse →
        </div>
      )}

      {isLoading && <Spinner text={`Analysing ${symbol}…`} />}

      {error || data?.error ? (
        <div className="rounded-xl border border-red-800/40 bg-red-900/20 p-4 text-red-400 text-sm">
          Could not load data for {symbol}. Check the symbol and try again.
        </div>
      ) : null}

      {data && !data.error && !isLoading && (
        <ExploreResult data={data} />
      )}
    </div>
  );
}

function ExploreResult({ data }: { data: ExploreData }) {
  const techScore = scoreTechnical(data.technical);
  const fundScore = scoreFundamental(data.fundamental);
  const { verdict, color, icon, combined } = exploreVerdict(techScore.score, fundScore.score);

  const curPrice = data.currentPrice;
  const priceStr = curPrice
    ? (data.isCrypto ? fmtCryptoPrice(curPrice) : fmt$(curPrice))
    : 'N/A';

  return (
    <div className="space-y-4">
      {/* Verdict banner */}
      <div
        className="rounded-xl p-4 flex flex-wrap items-center gap-4"
        style={{ background: `${color}11`, border: `1px solid ${color}33`, borderLeft: `4px solid ${color}` }}
      >
        <span className="text-xl font-bold" style={{ color }}>{icon} {verdict}</span>
        <div className="text-sm flex gap-4 text-[#9ca3af]">
          <span>Score <b style={{ color }}>{combined}/100</b></span>
          <span>Tech <b className="text-white">{techScore.score}</b></span>
          <span>Fund <b className="text-white">{fundScore.score}</b></span>
        </div>
        <span className="ml-auto text-xs text-[#6b7280] font-mono">{data.symbol} · {priceStr}</span>
      </div>

      {/* Chart + Signals */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Price chart */}
        <div className="lg:col-span-3 rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <PriceChart data={data} verdictColor={color} />
        </div>

        {/* Signals panel */}
        <div className="lg:col-span-2 rounded-xl border border-[#1e1e35] bg-[#111122] p-4 space-y-4 overflow-y-auto max-h-[480px]">
          <SignalGroup
            title={`📊 Technical — ${techScore.score}/100`}
            signals={techScore.signals}
          />
          <SignalGroup
            title={`${data.isCrypto ? '🔗' : '🏢'} Fundamental — ${fundScore.score}/100`}
            signals={fundScore.signals}
          />
        </div>
      </div>

      {/* Insider activity (stocks only) */}
      {!data.isCrypto && data.insider.length > 0 && (
        <div className="rounded-xl border border-[#1e1e35] bg-[#111122] p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#6b7280] mb-3">🧑‍💼 Insider Activity (last 90 days)</p>
          <div className="space-y-2">
            {data.insider.slice(0, 5).map((tx, i) => {
              const isSale = tx.type.toLowerCase().includes('sale') || tx.type.toLowerCase().includes('sell');
              return (
                <div key={i} className="flex items-start gap-3 text-sm">
                  <span>{isSale ? '🔴' : '🟢'}</span>
                  <div>
                    <span className="font-semibold">{tx.name}</span>
                    <span className="text-[#6b7280] mx-1">({tx.role})</span>
                    <span className={isSale ? 'text-red-400' : 'text-green-400'}>{tx.type}</span>
                    <span className="text-[#6b7280] ml-2 text-xs font-mono">
                      {tx.shares.toLocaleString()} shares · {tx.value ? fmt$(tx.value) : '—'} · {tx.date}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* News */}
      {data.news.length > 0 && (
        <details className="rounded-xl border border-[#1e1e35] bg-[#111122]">
          <summary className="px-4 py-3 cursor-pointer list-none flex items-center justify-between hover:bg-white/[0.02] text-sm font-semibold">
            📰 Recent News ({data.news.length} headlines)
            <span className="text-[#6b7280] text-lg select-none">▾</span>
          </summary>
          <div className="p-4 border-t border-[#1e1e35] grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.news.slice(0, 8).map((n, i) => (
              <div key={i} className="text-xs leading-relaxed">
                <span className="mr-1">{n.tag}</span>
                <span className="text-[#6b7280] mr-1">{n.dt}</span>
                <span className="font-medium text-[#e2e8f0]">{n.title}</span>
                <span className="text-[#4b5563]"> — {n.source}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      <p className="text-[10px] text-[#4b5563] leading-relaxed">
        {data.symbol} · Technical signals from 1-year OHLCV (RSI, MACD, BB, OBV, volume ratio, golden cross) ·
        Fundamental from Yahoo Finance · Scores are rule-based heuristics, not AI predictions ·
        Past signals do not guarantee future price direction.
      </p>
    </div>
  );
}

function SignalGroup({ title, signals }: { title: string; signals: ScoreSignal[] }) {
  return (
    <div>
      <p className="text-xs font-semibold text-[#e2e8f0] mb-2">{title}</p>
      {signals.length > 0 ? (
        <div className="space-y-1.5">
          {signals.map((s, i) => (
            <div key={i} className="flex gap-2 text-xs leading-relaxed">
              <span className="shrink-0">{s.icon}</span>
              <span className="text-[#9ca3af]">{s.label}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-[#6b7280]">No data available</p>
      )}
    </div>
  );
}

const ChartTooltip = ({ active, payload, label }: Record<string, unknown>) => {
  if (!(active as boolean) || !(payload as unknown[])?.[0]) return null;
  const rows = (payload as Record<string, unknown>[]).filter(p => (p.dataKey as string) !== 'bbUpper' && (p.dataKey as string) !== 'bbLower');
  return (
    <div className="bg-[#111122] border border-[#1e1e35] rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-[#6b7280] mb-1">{label as string}</p>
      {rows.map((p, i) => (
        <p key={i} className="font-mono" style={{ color: p.stroke as string ?? '#e2e8f0' }}>
          {p.name as string}: {typeof p.value === 'number' ? p.value.toFixed(2) : p.value as string}
        </p>
      ))}
    </div>
  );
};

const RsiTooltip = ({ active, payload, label }: Record<string, unknown>) => {
  if (!(active as boolean) || !(payload as unknown[])?.[0]) return null;
  const val = ((payload as Record<string, unknown>[])[0].value as number);
  return (
    <div className="bg-[#111122] border border-[#1e1e35] rounded-lg px-2 py-1 text-xs shadow-xl">
      <p className="text-[#6b7280]">{label as string}</p>
      <p className="font-mono text-white">RSI {val?.toFixed(1)}</p>
    </div>
  );
};

function PriceChart({ data, verdictColor }: { data: ExploreData; verdictColor: string }) {
  const chart = data.chart;
  if (!chart.length) return <div className="h-64 flex items-center justify-center text-[#6b7280] text-sm">No chart data.</div>;

  const isCrypto = data.isCrypto;
  const prices   = chart.map(d => d.close);
  const minP     = Math.min(...prices.filter(Boolean));
  const maxP     = Math.max(...prices.filter(Boolean));
  const padP     = (maxP - minP) * 0.05 || 1;

  const priceFormatter = (v: number) => isCrypto ? `$${v.toFixed(v < 1 ? 4 : 2)}` : `$${v.toFixed(2)}`;

  return (
    <div>
      <p className="text-xs text-[#6b7280] mb-3">Price · 3 months · Bollinger Bands</p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={chart} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="bbGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#93c5fd" stopOpacity={0.08} />
              <stop offset="100%" stopColor="#93c5fd" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} axisLine={false} interval={14} />
          <YAxis
            domain={[minP - padP, maxP + padP]}
            tickFormatter={priceFormatter}
            tick={{ fontSize: 9, fill: '#6b7280' }}
            tickLine={false}
            axisLine={false}
            width={65}
          />
          <Tooltip content={<ChartTooltip />} />
          {/* BB band fill */}
          <Area dataKey="bbUpper" stroke="rgba(147,197,253,0.2)" strokeWidth={1} fill="url(#bbGrad)" name="BB Upper" dot={false} legendType="none" />
          <Area dataKey="bbLower" stroke="rgba(147,197,253,0.2)" strokeWidth={1} fill="white" fillOpacity={0} name="BB Lower" dot={false} legendType="none" />
          {/* SMAs */}
          <Line dataKey="sma20" stroke="#f59e0b" strokeWidth={1} strokeDasharray="3 2" dot={false} name="SMA20" />
          <Line dataKey="sma50" stroke="#ec4899" strokeWidth={1} strokeDasharray="3 2" dot={false} name="SMA50" />
          {/* Price */}
          <Line dataKey="close" stroke={verdictColor} strokeWidth={2} dot={false} name="Price" />
        </ComposedChart>
      </ResponsiveContainer>

      <p className="text-xs text-[#6b7280] mt-4 mb-2">RSI (14)</p>
      <ResponsiveContainer width="100%" height={90}>
        <ComposedChart data={chart} margin={{ top: 0, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} axisLine={false} interval={14} />
          <YAxis domain={[0, 100]} ticks={[30, 50, 70]} tick={{ fontSize: 9, fill: '#6b7280' }} tickLine={false} axisLine={false} width={30} />
          <Tooltip content={<RsiTooltip />} />
          <ReferenceLine y={70} stroke="rgba(248,113,113,0.3)" strokeDasharray="3 2" />
          <ReferenceLine y={30} stroke="rgba(74,222,128,0.3)" strokeDasharray="3 2" />
          <Line dataKey="rsi" stroke="#94a3b8" strokeWidth={1.5} dot={false} name="RSI" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
