'use client';

import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, Cell, ResponsiveContainer } from 'recharts';
import { fmt$ } from '@/lib/utils';

interface Row { symbol: string; pnl: number; label: string }
interface Props { data: Row[] }

const CustomTooltip = ({ active, payload }: Record<string, unknown>) => {
  if (!(active as boolean) || !(payload as unknown[])?.[0]) return null;
  const p = (payload as Record<string, unknown>[])[0];
  return (
    <div className="bg-[#111122] border border-[#1e1e35] rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold text-white">{(p.payload as Record<string, unknown>).symbol as string}</p>
      <p className="font-mono" style={{ color: (p.value as number) >= 0 ? '#4ade80' : '#f87171' }}>
        {fmt$(p.value as number)}
      </p>
    </div>
  );
};

export default function PnlBar({ data }: Props) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
        <YAxis
          tickFormatter={v => (Math.abs(v) >= 1000 ? `$${(v/1000).toFixed(0)}K` : `$${v.toFixed(0)}`)}
          tick={{ fontSize: 10, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          width={50}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
        <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl >= 0 ? '#4ade80' : '#f87171'} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
