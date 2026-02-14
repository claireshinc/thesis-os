import { useState } from 'react';
import TickerInput from '../components/TickerInput';
import { getChangeFeed } from '../lib/api';
import type { ChangeFeed, ChangeEvent } from '../lib/types';

export default function FeedPage() {
  const [feed, setFeed] = useState<ChangeFeed | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [since, setSince] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().slice(0, 10);
  });

  async function handleSubmit(ticker: string) {
    setLoading(true);
    setError(null);
    setFeed(null);
    try {
      const data = await getChangeFeed(ticker, since);
      setFeed(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load feed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <TickerInput onSubmit={handleSubmit} loading={loading} />
        <label className="text-xs text-text-dim">
          Since:
          <input
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="ml-1 bg-surface border border-border rounded px-2 py-1.5
                       text-sm text-text mono focus:outline-none focus:border-accent"
          />
        </label>
      </div>

      {loading && (
        <div className="text-text-dim text-sm animate-pulse">
          Checking for changes...
        </div>
      )}

      {error && (
        <div className="text-red text-sm border border-red/30 rounded p-3 bg-red/5">
          {error}
        </div>
      )}

      {feed && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h1 className="mono font-bold text-lg">{feed.ticker}</h1>
            <span className="text-xs text-text-dim mono">
              {feed.event_count} events since {feed.since}
            </span>
          </div>

          {feed.events.length === 0 ? (
            <p className="text-text-dim text-sm">No changes detected.</p>
          ) : (
            <div className="space-y-2">
              {feed.events.map((evt, i) => (
                <EventCard key={i} event={evt} />
              ))}
            </div>
          )}

          <p className="text-xs text-text-dim mt-4 mono">
            Checked at: {feed.checked_at}
          </p>
        </div>
      )}
    </div>
  );
}

const SEVERITY_STYLES: Record<string, { border: string; badge: string }> = {
  breach: {
    border: 'border-red/40',
    badge: 'bg-red/20 text-red',
  },
  watch: {
    border: 'border-yellow/40',
    badge: 'bg-yellow/20 text-yellow',
  },
  info: {
    border: 'border-border',
    badge: 'bg-surface-2 text-text-dim',
  },
};

function EventCard({ event }: { event: ChangeEvent }) {
  const styles = SEVERITY_STYLES[event.severity] ?? SEVERITY_STYLES.info;

  return (
    <div className={`border ${styles.border} rounded bg-surface p-3`}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-1.5 py-0.5 rounded uppercase font-medium ${styles.badge}`}
          >
            {event.severity}
          </span>
          <span className="text-xs text-text-dim uppercase tracking-wide">
            {event.event_type}
          </span>
        </div>
        {event.source_date && (
          <span className="text-xs mono text-text-dim">
            {event.source_date}
          </span>
        )}
      </div>
      <p className="text-sm font-medium">{event.summary}</p>
      <p className="text-xs text-text-dim mt-1">{event.detail}</p>
    </div>
  );
}
