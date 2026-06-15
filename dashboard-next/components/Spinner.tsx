'use client';

export default function Spinner({ text = 'Loading…' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-[#6b7280]">
      <div className="w-8 h-8 rounded-full border-2 border-[#1e1e35] border-t-green-400 animate-spin" />
      <p className="text-sm">{text}</p>
    </div>
  );
}
