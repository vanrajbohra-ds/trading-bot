'use client';

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { fmt$ } from '@/lib/utils';

interface Props { stockVal: number; cryptoVal: number; cash: number }

const COLORS = ['#4ade80', '#818cf8', '#60a5fa'];

const CustomTooltip = ({ active, payload }: Record<string, unknown>) => {
  if (!(active as boolean) || !(payload as unknown[])?.[0]) return null;
  const p = (payload as Record<string, unknown>[])[0];
  return (
    <div className="bg-[#111122] border border-[#1e1e35] rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold" style={{ color: p.fill as string }}>{p.name as string}</p>
      <p className="font-mono text-white">{fmt$(p.value as number)}</p>
    </div>
  );
};

export default function AllocationPie({ stockVal, cryptoVal, cash }: Props) {
  const data = [
    { name: '📈 Stocks',  value: stockVal  },
    { name: '🔗 Crypto',  value: cryptoVal },
    { name: '💰 Cash',    value: cash      },
  ].filter(d => d.value > 0);

  if (!data.length) return null;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="45%"
          innerRadius="52%"
          outerRadius="75%"
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
