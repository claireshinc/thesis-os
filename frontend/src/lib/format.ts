// Formatting utilities

export function fmtDollars(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

export function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return 'N/A';
  return `${(v * 100).toFixed(decimals)}%`;
}

export function fmtPctRaw(v: number | null | undefined, decimals = 2): string {
  if (v == null) return 'N/A';
  return `${v.toFixed(decimals)}%`;
}

export function fmtDelta(v: number | null | undefined): string {
  if (v == null) return '-';
  return v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
}

export function fmtNumber(v: number | null | undefined, decimals = 2): string {
  if (v == null) return 'N/A';
  return v.toFixed(decimals);
}

export function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  return d;
}
