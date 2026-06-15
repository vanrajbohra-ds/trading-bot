'use client';

interface Props {
  children: React.ReactNode;
  color?: 'green' | 'red' | 'amber' | 'blue' | 'gray';
}

const COLORS = {
  green: 'bg-green-900/40 text-green-400 border-green-800/50',
  red:   'bg-red-900/40 text-red-400 border-red-800/50',
  amber: 'bg-amber-900/40 text-amber-400 border-amber-800/50',
  blue:  'bg-blue-900/40 text-blue-400 border-blue-800/50',
  gray:  'bg-gray-800/60 text-gray-400 border-gray-700/50',
};

export default function Badge({ children, color = 'gray' }: Props) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold border ${COLORS[color]}`}>
      {children}
    </span>
  );
}
