import { useState, type FormEvent } from 'react';

interface Props {
  onSubmit: (ticker: string) => void;
  loading?: boolean;
  placeholder?: string;
}

export default function TickerInput({
  onSubmit,
  loading = false,
  placeholder = 'Enter ticker...',
}: Props) {
  const [value, setValue] = useState('');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const ticker = value.trim().toUpperCase();
    if (ticker) onSubmit(ticker);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={loading}
        className="mono bg-surface border border-border rounded px-3 py-2 text-sm
                   text-text placeholder:text-text-dim focus:outline-none
                   focus:border-accent w-36 uppercase tracking-wider"
      />
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="px-4 py-2 bg-surface-2 border border-border rounded text-sm
                   text-text-dim hover:text-text hover:border-accent
                   disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Loading...' : 'Go'}
      </button>
    </form>
  );
}
