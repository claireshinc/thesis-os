import { useState } from 'react';
import TickerInput from '../components/TickerInput';
import SectionHeader from '../components/SectionHeader';
import CitationTooltip from '../components/CitationTooltip';
import StatusLight from '../components/StatusLight';
import { getBrief, exportBriefPdfUrl, exportBriefMdUrl } from '../lib/api';
import { fmtDollars, fmtPct, fmtPctRaw, fmtDelta, fmtNumber } from '../lib/format';
import type { DecisionBrief, KPI, QualityScore } from '../lib/types';

export default function BriefPage() {
  const [brief, setBrief] = useState<DecisionBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ticker, setTicker] = useState('');

  async function handleSubmit(t: string) {
    setTicker(t);
    setLoading(true);
    setError(null);
    setBrief(null);
    try {
      const data = await getBrief(t);
      setBrief(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load brief');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <TickerInput onSubmit={handleSubmit} loading={loading} />
        {brief && (
          <div className="flex gap-2">
            <a
              href={exportBriefMdUrl(ticker)}
              className="text-xs text-text-dim hover:text-accent transition-colors"
            >
              Export MD
            </a>
            <a
              href={exportBriefPdfUrl(ticker)}
              className="text-xs text-text-dim hover:text-accent transition-colors"
            >
              Export PDF
            </a>
          </div>
        )}
      </div>

      {loading && (
        <div className="text-text-dim text-sm animate-pulse">
          Generating brief for {ticker}...
        </div>
      )}

      {error && (
        <div className="text-red text-sm border border-red/30 rounded p-3 bg-red/5">
          {error}
        </div>
      )}

      {brief && <BriefContent brief={brief} />}
    </div>
  );
}

function BriefContent({ brief }: { brief: DecisionBrief }) {
  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="border border-border rounded bg-surface p-4 mb-6">
        <h1 className="text-lg font-bold mono">{brief.ticker}</h1>
        <p className="text-sm text-text-dim mt-0.5">
          {brief.entity_name} &middot; {brief.sector_display_name}
        </p>
        <p className="text-xs text-text-dim mt-1 mono">
          Generated: {brief.generated_at}
        </p>
      </div>

      <VariantPerception brief={brief} />
      <SectorKPIs kpis={brief.sector_kpis} />
      <QualityScores
        scores={brief.quality_scores}
        excluded={brief.excluded_scores}
      />
      <HolderMapSection brief={brief} />
      <RedFlagsSection brief={brief} />
      <ModelInputsSection brief={brief} />
    </div>
  );
}

/* ─── Variant Perception ─── */

function VariantPerception({ brief }: { brief: DecisionBrief }) {
  const mi = brief.market_implied;
  const ev = brief.ev_build;

  return (
    <section>
      <SectionHeader>Variant Perception</SectionHeader>
      <div className="border border-border rounded bg-surface p-4 space-y-3">
        {/* EV Build summary */}
        <div className="text-sm">
          <CitationTooltip source={ev.market_cap.source}>
            <span className="mono">{fmtDollars(ev.enterprise_value)}</span>
          </CitationTooltip>
          <span className="text-text-dim"> EV &mdash; {ev.summary}</span>
        </div>

        {mi ? (
          <>
            {/* Implied FCF growth */}
            <div className="flex items-baseline gap-4 flex-wrap">
              <div>
                <span className="text-xs text-text-dim uppercase tracking-wide">
                  Implied FCF Growth (10yr)
                </span>
                <p className="mono text-lg font-bold text-accent">
                  {mi.implied_fcf_growth_10yr != null
                    ? fmtPct(mi.implied_fcf_growth_10yr)
                    : 'N/A'}
                </p>
              </div>
              <div>
                <span className="text-xs text-text-dim uppercase tracking-wide">
                  WACC
                </span>
                <p className="mono text-sm">{fmtPct(mi.wacc)}</p>
                <p className="text-xs text-text-dim">{mi.wacc_build}</p>
              </div>
              <div>
                <span className="text-xs text-text-dim uppercase tracking-wide">
                  Terminal Growth
                </span>
                <p className="mono text-sm">{fmtPct(mi.terminal_growth)}</p>
              </div>
            </div>

            {/* FCF computation trail */}
            <div className="text-xs bg-surface-2 rounded p-2.5 mono text-text-dim">
              <CitationTooltip source={mi.fcf_source}>
                {mi.fcf_computation}
              </CitationTooltip>
              <span className="mx-2">&middot;</span>
              <CitationTooltip source={mi.ocf_source}>
                OCF: {fmtDollars(mi.ocf_used)}
              </CitationTooltip>
              <span className="mx-2">&middot;</span>
              <CitationTooltip source={mi.capex_source}>
                CapEx: {fmtDollars(mi.capex_used)}
              </CitationTooltip>
            </div>

            {/* Sensitivity */}
            {Object.keys(mi.sensitivity).length > 0 && (
              <div className="text-xs text-text-dim">
                <span className="uppercase tracking-wide">Sensitivity: </span>
                {Object.entries(mi.sensitivity).map(([k, v], i) => (
                  <span key={k}>
                    {i > 0 && ', '}
                    {k}: <span className="mono">{v != null ? fmtPct(v) : 'N/A'}</span>
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-sm text-text-dim">
            Market-implied data not available.
          </p>
        )}
      </div>
    </section>
  );
}

/* ─── Sector KPIs ─── */

function SectorKPIs({ kpis }: { kpis: KPI[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <section>
      <SectionHeader>Sector KPIs</SectionHeader>
      <div className="border border-border rounded bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-text-dim uppercase tracking-wide">
              <th className="text-left p-3">KPI</th>
              <th className="text-right p-3">Value</th>
              <th className="text-right p-3">Period</th>
              <th className="text-right p-3">QoQ</th>
              <th className="text-right p-3">YoY</th>
            </tr>
          </thead>
          <tbody>
            {kpis.map((kpi) => (
              <KPIRow
                key={kpi.kpi_id}
                kpi={kpi}
                expanded={expanded === kpi.kpi_id}
                onToggle={() =>
                  setExpanded(expanded === kpi.kpi_id ? null : kpi.kpi_id)
                }
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function KPIRow({
  kpi,
  expanded,
  onToggle,
}: {
  kpi: KPI;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasDetail = kpi.computation || kpi.note;

  return (
    <>
      <tr
        className={`border-b border-border/50 hover:bg-surface-2 transition-colors
                     ${hasDetail ? 'cursor-pointer' : ''}`}
        onClick={hasDetail ? onToggle : undefined}
      >
        <td className="p-3">
          <CitationTooltip source={kpi.source}>
            {kpi.label}
          </CitationTooltip>
        </td>
        <td className="p-3 text-right mono">
          {kpi.value != null ? `${fmtNumber(kpi.value)}${kpi.unit}` : 'N/A'}
        </td>
        <td className="p-3 text-right text-text-dim">{kpi.period}</td>
        <td className="p-3 text-right mono">
          <DeltaValue v={kpi.qoq_delta} />
        </td>
        <td className="p-3 text-right mono">
          <DeltaValue v={kpi.yoy_delta} />
        </td>
      </tr>
      {expanded && hasDetail && (
        <tr className="border-b border-border/50 bg-surface-2">
          <td colSpan={5} className="p-3 text-xs text-text-dim">
            {kpi.computation && (
              <p className="mono">{kpi.computation}</p>
            )}
            {kpi.note && <p className="mt-1 italic">{kpi.note}</p>}
            {kpi.qoq_period && (
              <p className="mt-1">
                QoQ period: {kpi.qoq_period} (
                {kpi.qoq_value != null ? fmtNumber(kpi.qoq_value) : '?'} vs{' '}
                {kpi.qoq_prior != null ? fmtNumber(kpi.qoq_prior) : '?'})
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function DeltaValue({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-text-dim">-</span>;
  const color = v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-text-dim';
  return <span className={color}>{fmtDelta(v)}</span>;
}

/* ─── Quality Scores ─── */

function QualityScores({
  scores,
  excluded,
}: {
  scores: QualityScore[];
  excluded: Record<string, string>;
}) {
  const [expandedScore, setExpandedScore] = useState<string | null>(null);
  const [showExcluded, setShowExcluded] = useState(false);

  return (
    <section>
      <SectionHeader>Quality Scores</SectionHeader>
      <div className="border border-border rounded bg-surface p-4 space-y-2">
        {scores.length === 0 && (
          <p className="text-sm text-text-dim">
            No applicable quality scores for this sector template.
          </p>
        )}
        {scores.map((score) => (
          <div key={score.name}>
            <div
              className="flex items-center justify-between cursor-pointer hover:bg-surface-2 rounded px-2 py-1.5 -mx-2"
              onClick={() =>
                setExpandedScore(
                  expandedScore === score.name ? null : score.name,
                )
              }
            >
              <span className="text-sm font-medium">{score.name}</span>
              <span className="mono text-sm">{fmtNumber(score.value)}</span>
            </div>
            <p className="text-xs text-text-dim px-2">
              {score.interpretation}
            </p>
            {expandedScore === score.name && (
              <div className="ml-2 mt-2 bg-surface-2 rounded p-2.5 text-xs space-y-1">
                <p className="text-text-dim">
                  Periods: {score.source_periods.join(', ')}
                </p>
                <div className="grid grid-cols-4 gap-1 mono">
                  {Object.entries(score.components).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-text-dim">{k}:</span>{' '}
                      <span>{fmtNumber(v, 3)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {Object.keys(excluded).length > 0 && (
          <div className="mt-3 pt-3 border-t border-border/50">
            <button
              className="text-xs text-text-dim hover:text-text transition-colors"
              onClick={() => setShowExcluded(!showExcluded)}
            >
              {showExcluded ? 'Hide' : 'Show'} excluded scores (
              {Object.keys(excluded).length})
            </button>
            {showExcluded && (
              <div className="mt-2 space-y-1.5">
                {Object.entries(excluded).map(([name, reason]) => (
                  <div key={name} className="text-xs">
                    <span className="text-text-dim font-medium">{name}:</span>{' '}
                    <span className="text-text-dim">{reason}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/* ─── Holder Map ─── */

function HolderMapSection({ brief }: { brief: DecisionBrief }) {
  const hm = brief.holder_map;

  return (
    <section>
      <SectionHeader>Holder Map</SectionHeader>
      <div className="border border-border rounded bg-surface p-4 space-y-4">
        {hm.holder_data_note && (
          <div className="text-xs text-yellow border border-yellow/20 bg-yellow/5 rounded p-2">
            {hm.holder_data_note}
          </div>
        )}

        <p className="text-sm">
          <span className="text-text-dim">Institutional holders:</span>{' '}
          <span className="mono">{hm.holder_count}</span>
        </p>

        {/* Top holders table */}
        {hm.top_holders.length > 0 && (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-text-dim uppercase tracking-wide">
                <th className="text-left p-2">Holder</th>
                <th className="text-left p-2">Type</th>
                <th className="text-right p-2">Filed</th>
                <th className="text-right p-2">Shares</th>
              </tr>
            </thead>
            <tbody>
              {hm.top_holders.slice(0, 10).map((h, i) => (
                <tr
                  key={i}
                  className="border-b border-border/30 hover:bg-surface-2"
                >
                  <td className="p-2">{h.filer_name}</td>
                  <td className="p-2 text-text-dim">{h.fund_type}</td>
                  <td className="p-2 text-right mono text-text-dim">
                    {h.filing_date}
                  </td>
                  <td className="p-2 text-right mono">
                    {h.shares ? h.shares.toLocaleString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Insider activity */}
        <div>
          <h3 className="text-xs uppercase tracking-wide text-text-dim mb-2">
            Insider Activity
          </h3>
          <p className="text-sm mb-2">{hm.insider_summary}</p>
          <div className="space-y-1.5">
            {hm.insider_activity.map((txn, i) => (
              <div
                key={i}
                className={`text-xs rounded p-2 ${
                  txn.is_notable
                    ? 'border border-yellow/30 bg-yellow/5'
                    : 'bg-surface-2'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span>
                    <span className="font-medium">{txn.owner_name}</span>
                    <span className="text-text-dim">
                      {' '}
                      ({txn.owner_title})
                    </span>
                  </span>
                  <span className="mono text-text-dim">
                    {txn.transaction_date}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className={`uppercase font-medium ${
                      txn.transaction_type === 'purchase'
                        ? 'text-green'
                        : txn.transaction_type === 'sale'
                          ? 'text-red'
                          : 'text-text-dim'
                    }`}
                  >
                    {txn.transaction_type}
                  </span>
                  {txn.shares && (
                    <span className="mono">
                      {txn.shares.toLocaleString()} shares
                    </span>
                  )}
                  {txn.value != null && txn.value > 0 && (
                    <span className="mono text-text-dim">
                      ({fmtDollars(txn.value)})
                    </span>
                  )}
                  {txn.is_notable && (
                    <span className="text-yellow uppercase tracking-wide font-medium">
                      Notable
                    </span>
                  )}
                </div>
                <p className="text-text-dim mt-1">{txn.context_note}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Data freshness */}
        <div className="text-xs text-text-dim space-y-0.5 pt-2 border-t border-border/50">
          {Object.entries(hm.data_freshness).map(([k, v]) => (
            <p key={k}>
              <span className="text-text-dim">{k}:</span> {v}
            </p>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─── Red Flags ─── */

function RedFlagsSection({ brief }: { brief: DecisionBrief }) {
  const rf = brief.red_flags;
  if (!rf) return null;

  const SEVERITY_COLOR: Record<string, string> = {
    high: 'border-red/40 bg-red/5',
    medium: 'border-yellow/40 bg-yellow/5',
    low: 'border-text-dim/20 bg-surface-2',
  };

  const SEVERITY_BADGE: Record<string, string> = {
    high: 'bg-red/20 text-red',
    medium: 'bg-yellow/20 text-yellow',
    low: 'bg-surface-2 text-text-dim',
  };

  return (
    <section>
      <SectionHeader>Red Flags</SectionHeader>
      <div className="space-y-2">
        {rf.red_flags.map((flag, i) => (
          <details
            key={i}
            className={`border rounded p-3 ${
              SEVERITY_COLOR[flag.severity] ?? SEVERITY_COLOR.low
            }`}
          >
            <summary className="text-sm cursor-pointer flex items-center gap-2">
              <span
                className={`text-xs px-1.5 py-0.5 rounded uppercase font-medium ${
                  SEVERITY_BADGE[flag.severity] ?? SEVERITY_BADGE.low
                }`}
              >
                {flag.severity}
              </span>
              {flag.flag}
            </summary>
            <div className="mt-2 text-xs text-text-dim space-y-1.5">
              <p>
                <span className="text-text font-medium">Section:</span>{' '}
                {flag.section}
              </p>
              <p>
                <span className="text-text font-medium">Evidence:</span>{' '}
                {flag.evidence}
              </p>
              {flag.context && (
                <p>
                  <span className="text-text font-medium">Context:</span>{' '}
                  {flag.context}
                </p>
              )}
              <CitationTooltip source={flag.source}>
                <span className="text-accent">View source</span>
              </CitationTooltip>
            </div>
          </details>
        ))}

        {rf.clean_areas.length > 0 && (
          <div className="border border-green/20 bg-green/5 rounded p-3">
            <h3 className="text-xs uppercase tracking-wide text-green mb-1.5">
              Clean Areas
            </h3>
            <ul className="text-xs text-text-dim space-y-0.5">
              {rf.clean_areas.map((area, i) => (
                <li key={i}>&bull; {area}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

/* ─── Model Inputs ─── */

function ModelInputsSection({ brief }: { brief: DecisionBrief }) {
  const [expanded, setExpanded] = useState(false);
  const mi = brief.model_inputs;

  return (
    <section>
      <SectionHeader>Model Inputs</SectionHeader>
      <div className="border border-border rounded bg-surface p-4">
        <button
          className="text-sm text-text-dim hover:text-text transition-colors w-full text-left"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Collapse' : 'Expand'} model assumptions
          <span className="ml-2 text-xs">{expanded ? '\u25B2' : '\u25BC'}</span>
        </button>
        {expanded && (
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-text-dim">WACC:</span>{' '}
              <span className="mono">
                {mi.wacc != null ? fmtPct(mi.wacc) : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-text-dim">Risk-free rate:</span>{' '}
              <span className="mono">
                {mi.risk_free_rate != null ? fmtPct(mi.risk_free_rate) : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-text-dim">Beta:</span>{' '}
              <span className="mono">{fmtNumber(mi.beta)}</span>
            </div>
            <div>
              <span className="text-text-dim">ERP:</span>{' '}
              <span className="mono">{fmtPct(mi.equity_risk_premium)}</span>
            </div>
            <div>
              <span className="text-text-dim">Terminal growth:</span>{' '}
              <span className="mono">{fmtPct(mi.terminal_growth)}</span>
            </div>
            <div>
              <span className="text-text-dim">Sector template:</span>{' '}
              <span>{mi.sector_template}</span>
            </div>
            {mi.filing_used && (
              <div className="col-span-2">
                <span className="text-text-dim">Filing:</span>{' '}
                <span className="mono">{mi.filing_used}</span>
                {mi.filing_date && (
                  <span className="text-text-dim"> ({mi.filing_date})</span>
                )}
              </div>
            )}
            {Object.entries(mi.data_freshness).length > 0 && (
              <div className="col-span-2 mt-2 pt-2 border-t border-border/50 space-y-0.5">
                {Object.entries(mi.data_freshness).map(([k, v]) => (
                  <p key={k} className="text-text-dim">
                    {k}: {v}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
