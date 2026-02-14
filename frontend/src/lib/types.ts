// Types mirroring backend Pydantic response models

export interface SourceMeta {
  source_type: string;
  filer: string;
  filing_date: string | null;
  section: string | null;
  accession_number: string | null;
  url: string;
  description: string;
}

export interface EVComponent {
  label: string;
  value: number;
  computation: string | null;
  source: SourceMeta;
}

export interface EVBuild {
  market_cap: EVComponent;
  total_debt: EVComponent;
  cash: EVComponent;
  enterprise_value: number;
  summary: string;
}

export interface MarketImplied {
  implied_fcf_growth_10yr: number | null;
  wacc: number;
  wacc_build: string;
  fcf_used: number;
  fcf_computation: string;
  ocf_used: number;
  capex_used: number;
  fcf_source: SourceMeta;
  ocf_source: SourceMeta;
  capex_source: SourceMeta;
  terminal_growth: number;
  ev_used: number;
  sensitivity: Record<string, number | null>;
}

export interface KPI {
  kpi_id: string;
  label: string;
  value: number | null;
  unit: string;
  period: string;
  prior_value: number | null;
  yoy_delta: number | null;
  qoq_value: number | null;
  qoq_prior: number | null;
  qoq_delta: number | null;
  qoq_period: string | null;
  source: SourceMeta | null;
  computation: string | null;
  note: string | null;
}

export interface QualityScore {
  name: string;
  value: number;
  interpretation: string;
  components: Record<string, number>;
  source_periods: string[];
}

export interface InsiderTransaction {
  owner_name: string;
  owner_title: string;
  transaction_date: string;
  transaction_type: string;
  shares: number | null;
  price_per_share: number | null;
  value: number | null;
  shares_owned_after: number | null;
  is_10b5_1: boolean;
  is_discretionary: boolean;
  pct_of_holdings: number | null;
  is_notable: boolean;
  context_note: string;
  source: SourceMeta;
}

export interface HolderEntry {
  filer_name: string;
  form_type: string;
  filing_date: string;
  accession_number: string | null;
  shares: number | null;
  value: number | null;
  fund_type: string;
}

export interface HolderMap {
  top_holders: HolderEntry[];
  holder_count: number;
  insider_activity: InsiderTransaction[];
  insider_summary: string;
  data_freshness: Record<string, string>;
  holder_data_note: string;
}

export interface RedFlag {
  flag: string;
  severity: string;
  section: string;
  page: number | null;
  page_unverified: boolean;
  evidence: string;
  context: string;
  source: SourceMeta;
}

export interface RedFlagReport {
  red_flags: RedFlag[];
  clean_areas: string[];
  filing_source: SourceMeta;
}

export interface ModelInputs {
  wacc: number | null;
  risk_free_rate: number | null;
  beta: number;
  equity_risk_premium: number;
  terminal_growth: number;
  sector_template: string;
  filing_used: string | null;
  filing_date: string | null;
  data_freshness: Record<string, string>;
}

export interface DecisionBrief {
  ticker: string;
  entity_name: string;
  sector: string;
  sector_display_name: string;
  generated_at: string;
  ev_build: EVBuild;
  market_implied: MarketImplied | null;
  sector_kpis: KPI[];
  quality_scores: QualityScore[];
  excluded_scores: Record<string, string>;
  holder_map: HolderMap;
  red_flags: RedFlagReport | null;
  model_inputs: ModelInputs;
}

// Thesis types

export interface Claim {
  id: string;
  statement: string;
  kpi_id: string;
  current_value: number | null;
  qoq_delta: number | null;
  yoy_delta: number | null;
  status: string;
}

export interface KillCriterion {
  id: string;
  description: string;
  metric: string;
  operator: string;
  threshold: number;
  duration: string | null;
  current_value: number | null;
  status: string;
  distance_pct: number | null;
  watch_reason: string | null;
}

export interface Catalyst {
  id: number;
  ticker: string;
  event_date: string;
  event: string;
  claims_tested: string[] | null;
  kill_criteria_tested: string[] | null;
  occurred: boolean;
  outcome_notes: string | null;
}

export interface Thesis {
  id: string;
  ticker: string;
  direction: string;
  thesis_text: string;
  sector_template: string;
  status: string;
  entry_price: number | null;
  entry_date: string | null;
  close_price: number | null;
  close_date: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
  claims: Claim[];
  kill_criteria: KillCriterion[];
  catalysts: Catalyst[];
}

export interface ThesisListItem {
  id: string;
  ticker: string;
  direction: string;
  status: string;
  sector_template: string;
  thesis_text: string;
  entry_price: number | null;
  entry_date: string | null;
  created_at: string;
}

export interface ThesisListResponse {
  theses: ThesisListItem[];
  count: number;
}

// Change feed types

export interface ChangeEvent {
  event_type: string;
  ticker: string;
  summary: string;
  detail: string;
  severity: string;
  source_date: string | null;
}

export interface ChangeFeed {
  ticker: string;
  since: string;
  events: ChangeEvent[];
  event_count: number;
  checked_at: string;
}

// Command types

export interface CommandResponse {
  command: string;
  result: Record<string, unknown> | null;
  error: string | null;
}
