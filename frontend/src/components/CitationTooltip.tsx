import { useState, useRef, type ReactNode } from 'react';
import type { SourceMeta } from '../lib/types';

interface Props {
  source: SourceMeta | null | undefined;
  children: ReactNode;
}

export default function CitationTooltip({ source, children }: Props) {
  const [show, setShow] = useState(false);
  const timeout = useRef<ReturnType<typeof setTimeout>>(undefined);

  if (!source) return <>{children}</>;

  function handleEnter() {
    clearTimeout(timeout.current);
    setShow(true);
  }

  function handleLeave() {
    timeout.current = setTimeout(() => setShow(false), 150);
  }

  return (
    <span
      className="relative inline cursor-help border-b border-dotted border-text-dim"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {children}
      {show && (
        <span
          className="absolute z-50 bottom-full left-0 mb-1 w-72 p-2.5
                     bg-surface-2 border border-border rounded shadow-lg
                     text-xs text-text-dim leading-relaxed"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <span className="block text-text font-medium mb-1">
            {source.source_type}
            {source.filer ? ` — ${source.filer}` : ''}
          </span>
          {source.filing_date && (
            <span className="block">Filed: {source.filing_date}</span>
          )}
          {source.section && (
            <span className="block">Section: {source.section}</span>
          )}
          {source.description && (
            <span className="block mt-1 text-text">
              {source.description}
            </span>
          )}
          {source.url && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block mt-1 text-accent hover:underline truncate"
            >
              View filing
            </a>
          )}
        </span>
      )}
    </span>
  );
}
