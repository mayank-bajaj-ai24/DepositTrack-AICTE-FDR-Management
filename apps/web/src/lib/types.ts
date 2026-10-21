// Shapes returned by the DepositTrack API (apps/api/app/api/serializers.py).

export type Institution = {
  id: string;
  aicte_id: string;
  name: string;
  institution_type: string | null;
  state: string | null;
  region: string | null;
};

export type InstrumentSummary = {
  id: string;
  institution: Institution | null;
  kind: string;
  instrument_no: string;
  bank_name: string | null;
  bank_ifsc: string | null;
  amount: string | null;
  issue_date: string | null;
  maturity_date: string | null;
  state: string;
  trust_level: number;
  risk_score: number | null;
  replaces_id: string | null;
  open_flags: number;
  created_at: string | null;
};

export type FieldValue = {
  field: string;
  declared: string | null;
  extracted_a: string | null;
  extracted_b: string | null;
  bank_value: string | null;
  confidence: number | null;
  trust_level: number;
  fresh_until: string | null;
};

export type DocumentInfo = {
  id: string;
  kind: string;
  version: number;
  sha256: string;
  uploaded_by: string;
  uploaded_at: string | null;
  forgery_score: number | null;
};

export type Flag = {
  id: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low";
  fact: Record<string, unknown> | null;
  rule_id: string | null;
  clause_ref: string | null;
  reason: string;
  status: "open" | "resolved";
  raised_by: string;
  resolved_by: string | null;
  created_at: string | null;
};

export type ChecklistItem = {
  id: string;
  label: string;
  evidence: "document" | "declaration" | "officer";
  done: boolean;
  by: string | null;
  at: string | null;
  ref: string | null;
};

export type Case = {
  id: string;
  type: "release" | "discharge" | "refund";
  state: "open" | "approved" | "rejected";
  instrument_id: string;
  due_at: string | null;
  escalation_level: number;
  policy_version: string | null;
  checklist: ChecklistItem[];
  opened_by: string | null;
  reason: string | null;
  decision: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  blockers: string[];
  created_at: string | null;
  instrument?: InstrumentSummary;
};

export type AuditEvent = {
  id: string;
  seq: number;
  action: string;
  actor: string;
  role: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  ts: string | null;
  hash: string;
  prev_hash: string | null;
};

export type Notification = {
  id: string;
  instrument_id: string;
  kind: string;
  audience_role: string;
  message: string;
  created_at: string | null;
};

export type CoverageSegment = { start: string; end: string; declared: string; attested: string; required: string };
export type Coverage = {
  obligation_id: string;
  required: string;
  declared_today: string;
  attested_today: string;
  exposure_today: string;
  first_gap: string | null;
  segments: CoverageSegment[];
};

export type InstrumentDetail = {
  instrument: InstrumentSummary;
  today: string;
  beneficiary_text: string | null;
  lien_marked: boolean | null;
  fields: FieldValue[];
  documents: DocumentInfo[];
  flags: Flag[];
  observations: { id: string; officer: string; text: string; created_at: string | null }[];
  cases: Case[];
  events: AuditEvent[];
  chain: { intact: boolean; length: number; broken_at_seq: number | null; head_hash: string | null };
  replaced_by: InstrumentSummary[];
  notifications: Notification[];
  coverage: Coverage | null;
  editable_fields: string[];
  next_states: string[];
};

export type Dashboard = {
  today: string;
  clock_offset_days: number;
  total: number;
  states: Record<string, number>;
  tiles: Record<string, number>;
  coverage: { required: string; declared: string; attested: string; exposure: string };
  gaps: { institution: Institution; first_gap: string; required: string }[];
  trust_distribution: Record<string, number>;
  flags_by_type: Record<string, number>;
  ageing: Record<string, number>;
  bank_turnaround_hours: Record<string, number>;
  risk_by_region: Record<string, number>;
};

export type SystemStatus = {
  policy_version: string;
  demo_policy: boolean;
  unconfirmed: string[];
  today: string;
  clock_offset_days: number;
  bank_channel_configured: boolean;
  bank_keys_pinned: number;
  layoutlm_available: boolean;
  forgery_model_available: boolean;
  risk_model_available: boolean;
  immudb_enabled: boolean;
};

export type ExtractionPreview = {
  pass_a_available: boolean;
  fields: Record<
    string,
    { value: string | null; pass_a: string | null; pass_b: string | null; confidence: number; needs_review: boolean; reason: string | null }
  >;
};

export const FIELD_ORDER = [
  "fdr_no",
  "bank",
  "branch",
  "ifsc",
  "amount",
  "amount_words",
  "issue_date",
  "maturity_date",
  "depositor",
  "beneficiary",
  "lien_text",
] as const;
