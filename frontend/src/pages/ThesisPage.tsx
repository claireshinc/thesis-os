import { useState, useRef, useEffect } from 'react';
import StatusLight from '../components/StatusLight';
import { sendCommand, listTheses, getThesis } from '../lib/api';
import { fmtNumber, fmtDelta } from '../lib/format';
import type { Thesis, CommandResponse } from '../lib/types';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  data?: Record<string, unknown> | null;
}

export default function ThesisPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [pinnedThesis, setPinnedThesis] = useState<Thesis | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load most recent thesis on mount
  useEffect(() => {
    listTheses()
      .then(async (res) => {
        if (res.theses.length > 0) {
          const full = await getThesis(res.theses[0].id);
          setPinnedThesis(full);
        }
      })
      .catch(() => {});
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages]);

  async function handleSend() {
    const cmd = input.trim();
    if (!cmd) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: cmd }]);
    setLoading(true);

    try {
      const res: CommandResponse = await sendCommand(cmd);
      if (res.error) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${res.error}` },
        ]);
      } else {
        // If the command compiled a thesis, pin it
        const result = res.result;
        if (result && 'id' in result && 'claims' in result) {
          const thesis = result as unknown as Thesis;
          setPinnedThesis(thesis);
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: `Thesis compiled for ${thesis.ticker}. Pinned to the right panel.`,
              data: result,
            },
          ]);
        } else {
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: formatResult(res),
              data: result,
            },
          ]);
        }
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${e instanceof Error ? e.message : 'Request failed'}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full">
      {/* Left Panel — Chat */}
      <div className="flex-1 flex flex-col border-r border-border min-w-0">
        <div className="px-4 py-3 border-b border-border text-xs text-text-dim">
          Commands: /thesis, /stress, /brief, /export
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-text-dim text-sm mt-8 text-center">
              <p>Type a command to get started.</p>
              <p className="mt-2 mono text-xs">
                /thesis AAPL long &mdash; Services revenue will grow 20%...
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatBubble key={i} message={msg} />
          ))}
          {loading && (
            <div className="text-text-dim text-sm animate-pulse">
              Processing...
            </div>
          )}
        </div>

        {/* Input */}
        <form
          className="p-3 border-t border-border"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              placeholder="/thesis AAPL long — ..."
              className="flex-1 bg-surface border border-border rounded px-3 py-2 text-sm
                         text-text placeholder:text-text-dim focus:outline-none
                         focus:border-accent mono"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-4 py-2 bg-accent/10 border border-accent/30 rounded text-sm
                         text-accent hover:bg-accent/20 disabled:opacity-40
                         disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </div>
        </form>
      </div>

      {/* Right Panel — Pinned Cards */}
      <div className="w-96 shrink-0 overflow-y-auto p-4 bg-surface">
        {pinnedThesis ? (
          <ThesisCard thesis={pinnedThesis} />
        ) : (
          <div className="text-text-dim text-sm text-center mt-8">
            No thesis pinned.
            <p className="text-xs mt-1">
              Use /thesis to compile one.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded px-3 py-2 text-sm ${
          isUser
            ? 'bg-accent/10 border border-accent/20 text-accent mono'
            : 'bg-surface-2 border border-border text-text'
        }`}
      >
        <pre className="whitespace-pre-wrap font-[inherit]">
          {message.content}
        </pre>
      </div>
    </div>
  );
}

function formatResult(res: CommandResponse): string {
  if (!res.result) return `Command "${res.command}" executed.`;
  try {
    return JSON.stringify(res.result, null, 2).slice(0, 2000);
  } catch {
    return `Command "${res.command}" executed.`;
  }
}

/* ─── Thesis Card ─── */

function ThesisCard({ thesis }: { thesis: Thesis }) {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="border border-border rounded bg-bg p-3">
        <div className="flex items-center justify-between">
          <span className="mono font-bold text-lg">{thesis.ticker}</span>
          <span
            className={`text-xs uppercase font-medium px-2 py-0.5 rounded ${
              thesis.direction === 'long'
                ? 'bg-green/10 text-green'
                : 'bg-red/10 text-red'
            }`}
          >
            {thesis.direction}
          </span>
        </div>
        <p className="text-xs text-text-dim mt-1">
          {thesis.sector_template} &middot; {thesis.status}
        </p>
        <p className="text-sm mt-2">{thesis.thesis_text}</p>
      </div>

      {/* Claims */}
      {thesis.claims.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wide text-text-dim mb-2">
            Claims
          </h3>
          <div className="space-y-1.5">
            {thesis.claims.map((c) => (
              <div
                key={c.id}
                className="border border-border rounded bg-bg p-2.5 text-xs"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="mono text-text-dim">{c.id}</span>
                  <StatusLight status={c.status} />
                </div>
                <p className="text-sm">{c.statement}</p>
                <div className="flex gap-3 mt-1.5 text-text-dim">
                  <span>KPI: {c.kpi_id}</span>
                  {c.current_value != null && (
                    <span className="mono">{fmtNumber(c.current_value)}</span>
                  )}
                  {c.qoq_delta != null && (
                    <span className="mono">
                      QoQ: <DeltaSpan v={c.qoq_delta} />
                    </span>
                  )}
                  {c.yoy_delta != null && (
                    <span className="mono">
                      YoY: <DeltaSpan v={c.yoy_delta} />
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Kill Criteria */}
      {thesis.kill_criteria.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wide text-text-dim mb-2">
            Kill Criteria
          </h3>
          <div className="space-y-1.5">
            {thesis.kill_criteria.map((kc) => (
              <div
                key={kc.id}
                className="border border-border rounded bg-bg p-2.5 text-xs"
              >
                <div className="flex items-center justify-between mb-1">
                  <StatusLight status={kc.status} size="md" />
                  {kc.distance_pct != null && (
                    <span className="mono text-text-dim">
                      {kc.distance_pct.toFixed(1)}% headroom
                    </span>
                  )}
                </div>
                <p className="text-sm">{kc.description}</p>
                <div className="flex gap-3 mt-1.5 text-text-dim">
                  <span>
                    {kc.metric} {kc.operator} {fmtNumber(kc.threshold)}
                  </span>
                  {kc.current_value != null && (
                    <span className="mono">
                      Current: {fmtNumber(kc.current_value)}
                    </span>
                  )}
                  {kc.duration && <span>({kc.duration})</span>}
                </div>
                {kc.watch_reason && (
                  <p className="mt-1 text-yellow">{kc.watch_reason}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Catalysts */}
      {thesis.catalysts.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wide text-text-dim mb-2">
            Catalyst Calendar
          </h3>
          <div className="space-y-1">
            {thesis.catalysts
              .sort(
                (a, b) =>
                  new Date(a.event_date).getTime() -
                  new Date(b.event_date).getTime(),
              )
              .map((cat) => (
                <div
                  key={cat.id}
                  className="flex items-start gap-2 text-xs border border-border rounded bg-bg p-2"
                >
                  <span className="mono text-text-dim shrink-0 w-20">
                    {cat.event_date}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm">{cat.event}</p>
                    {cat.claims_tested && cat.claims_tested.length > 0 && (
                      <p className="text-text-dim mt-0.5">
                        Tests: {cat.claims_tested.join(', ')}
                      </p>
                    )}
                  </div>
                  {cat.occurred && (
                    <span className="text-green uppercase text-xs shrink-0">
                      Done
                    </span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DeltaSpan({ v }: { v: number }) {
  const color = v > 0 ? 'text-green' : v < 0 ? 'text-red' : '';
  return <span className={color}>{fmtDelta(v)}</span>;
}
