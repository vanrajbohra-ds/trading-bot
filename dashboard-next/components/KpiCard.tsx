'use client';

interface Props {
  label: string;
  value: string;
  sub?: string;
  subColor?: string;
  valueColor?: string;
}

export default function KpiCard({ label, value, sub, subColor, valueColor }: Props) {
  return (
    <div className="rounded-xl border border-[#1e1e35] bg-[#111122] px-4 py-3 flex flex-col gap-0.5">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-[#6b7280]">{label}</p>
      <p className="text-lg font-bold font-mono tabular-nums leading-tight" style={{ color: valueColor ?? '#e2e8f0' }}>
        {value}
      </p>
      {sub && (
        <p className="text-[11px] font-mono" style={{ color: subColor ?? '#6b7280' }}>{sub}</p>
      )}
    </div>
  );
}
