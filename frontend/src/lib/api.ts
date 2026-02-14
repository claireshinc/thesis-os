import type {
  DecisionBrief,
  Thesis,
  ThesisListResponse,
  ChangeFeed,
  CommandResponse,
} from './types';

const BASE = '/api';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// Decision Brief
export async function getBrief(
  ticker: string,
  sector?: string,
): Promise<DecisionBrief> {
  const params = new URLSearchParams();
  if (sector) params.set('sector', sector);
  const qs = params.toString();
  return fetchJSON<DecisionBrief>(
    `${BASE}/brief/${encodeURIComponent(ticker)}${qs ? `?${qs}` : ''}`,
  );
}

// Thesis CRUD
export async function compileThesis(
  ticker: string,
  direction: string,
  thesisText: string,
  sector?: string,
  entryPrice?: number,
): Promise<Thesis> {
  return fetchJSON<Thesis>(
    `${BASE}/thesis/${encodeURIComponent(ticker)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        direction,
        thesis_text: thesisText,
        sector: sector || null,
        entry_price: entryPrice ?? null,
      }),
    },
  );
}

export async function getThesis(thesisId: string): Promise<Thesis> {
  return fetchJSON<Thesis>(`${BASE}/thesis/${thesisId}`);
}

export async function listTheses(
  ticker?: string,
  status?: string,
): Promise<ThesisListResponse> {
  const params = new URLSearchParams();
  if (ticker) params.set('ticker', ticker);
  if (status) params.set('status', status);
  const qs = params.toString();
  return fetchJSON<ThesisListResponse>(
    `${BASE}/theses${qs ? `?${qs}` : ''}`,
  );
}

export async function lockThesis(
  thesisId: string,
  entryPrice?: number,
): Promise<Thesis> {
  return fetchJSON<Thesis>(`${BASE}/thesis/${thesisId}/lock`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entry_price: entryPrice ?? null }),
  });
}

export async function closeThesis(
  thesisId: string,
  reason: string,
  closePrice?: number,
): Promise<Thesis> {
  return fetchJSON<Thesis>(`${BASE}/thesis/${thesisId}/close`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason, close_price: closePrice ?? null }),
  });
}

// Stress test
export async function stressTest(
  ticker: string,
  memoText: string,
): Promise<Record<string, unknown>> {
  return fetchJSON<Record<string, unknown>>(
    `${BASE}/stress/${encodeURIComponent(ticker)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memo_text: memoText }),
    },
  );
}

// Export
export function exportBriefMdUrl(ticker: string, sector?: string): string {
  const params = new URLSearchParams({ format: 'md' });
  if (sector) params.set('sector', sector);
  return `${BASE}/export/brief/${encodeURIComponent(ticker)}?${params}`;
}

export function exportBriefPdfUrl(ticker: string, sector?: string): string {
  const params = new URLSearchParams({ format: 'pdf' });
  if (sector) params.set('sector', sector);
  return `${BASE}/export/brief/${encodeURIComponent(ticker)}?${params}`;
}

export function exportThesisMdUrl(thesisId: string): string {
  return `${BASE}/export/thesis/${thesisId}`;
}

// Change feed
export async function getChangeFeed(
  ticker: string,
  since: string,
): Promise<ChangeFeed> {
  return fetchJSON<ChangeFeed>(
    `${BASE}/feed/${encodeURIComponent(ticker)}?since=${since}`,
  );
}

// Chat/command
export async function sendCommand(command: string): Promise<CommandResponse> {
  return fetchJSON<CommandResponse>(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });
}
