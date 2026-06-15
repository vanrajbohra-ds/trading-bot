'use client';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { STARTING_CAP, fmt$ } from '@/lib/utils';

interface Row { date: string; value: number }

interface Props { data: Row[] }

function fmt(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

const CustomTooltip = ({ active, payload, label }: Record<string, unknown>) => {
  if (!(active as boolean) || !(payload as unknown[])?.[0]) return null;
  const val = ((payload as Record<string, unknown>[])[0].value as number);
  const pnl = val - STARTING_CAP;
  return (
    <div className="bg-[#111122] border border-[#1e1e35] rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-[#6b7280] mb-1">{label as string}</p>
      <p className="font-mono font-semibold text-white">{fmt$(val)}</p>
      <p className="font-mono" style={{ color: pnl >= 0 ? '#4ade80' : '#f87171' }}>
        {pnl >= 0 ? '+' : ''}{fmt$(pnl)}
      </p>
    </div>
  );
};

export default function PortfolioChart({ data }: Props) {
  if (!data.length) return (
    <div className="flex items-center justify-center h-48 text-[#6b7280] text-sm">
      Portfolio history will appear after the first trading day.
    </div>
  );

  const vals = data.map(d => d.value);
  const lo   = Math.min(...vals, STARTING_CAP);
  const hi   = Math.max(...vals, STARTING_CAP);
  const pad  = Math.max((hi - lo) * 0.15, 200);
  const last = vals[vals.length - 1];
  const isUp = last >= STARTING_CAP;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="pgGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="10%" stopColor={isUp ? '#4ade80' : '#f87171'} stopOpacity={0.25} />
            <stop offset="95%" stopColor={isUp ? '#4ade80' : '#f87171'} stopOpacity={0}   />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[lo - pad, hi + pad]}
          tickFormatter={fmt}
          tick={{ fontSize: 10, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine
          y={STARTING_CAP}
          stroke="rgba(255,255,255,0.2)"
          strokeDasharray="4 3"
          label={{ value: '$100K', position: 'right', fontSize: 10, fill: '#6b7280' }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={isUp ? '#4ade80' : '#f87171'}
          strokeWidth={2}
          fill="url(#pgGrad)"
          dot={false}
          activeDot={{ r: 4, fill: isUp ? '#4ade80' : '#f87171' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
