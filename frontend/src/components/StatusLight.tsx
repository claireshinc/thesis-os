interface Props {
  status: string; // "ok" | "watch" | "breach" | "no_data"
  size?: 'sm' | 'md';
}

const COLOR_MAP: Record<string, string> = {
  ok: 'bg-green',
  watch: 'bg-yellow',
  breach: 'bg-red',
  no_data: 'bg-text-dim',
  supported: 'bg-green',
  mixed: 'bg-yellow',
  challenged: 'bg-red',
  unverified: 'bg-orange',
  info: 'bg-text-dim',
};

const LABEL_MAP: Record<string, string> = {
  ok: 'OK',
  watch: 'WATCH',
  breach: 'BREACH',
  no_data: 'NO DATA',
  supported: 'SUPPORTED',
  mixed: 'MIXED',
  challenged: 'CHALLENGED',
  unverified: 'UNVERIFIED',
  info: 'INFO',
};

export default function StatusLight({ status, size = 'sm' }: Props) {
  const color = COLOR_MAP[status] ?? 'bg-text-dim';
  const label = LABEL_MAP[status] ?? status.toUpperCase();
  const dim = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5';

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`${dim} rounded-full ${color} shrink-0`} />
      <span className="text-xs uppercase tracking-wide">{label}</span>
    </span>
  );
}
