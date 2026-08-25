export interface InterestTag {
  key: string;
  label: string;
  weight: number;
}

export interface ValueTagHit {
  id: number;
  label: string;
  polarity: 1 | 0 | -1;
  weight: number;
  evidence: string;
  auto?: boolean;
  manual: boolean;
  matched: boolean;
  source?: "rule" | "manual" | "ai_assist" | "ai_ingest" | "ingest_gap";
}

export interface ValueTagLibraryEntry {
  id: number;
  label: string;
  category: string;
  polarity: 1 | 0 | -1;
  weight: number;
  applied: boolean;
  auto: boolean;
  manual: boolean;
  pinned?: boolean;
  matched?: boolean;
  source?: "rule" | "manual" | "ai_assist" | "ai_ingest" | "ingest_gap";
}

export type ValueTagStatus = "draft" | "approved";

export interface ValueTag {
  id: number;
  category: string;
  description: string;
  label: string;
  pattern: string;
  polarity: 1 | 0 | -1;
  weight: number;
  rationale: string;
  status: ValueTagStatus;
  pinned: boolean;
  created_at: string;
}

export interface Job {
  id: number;
  channel: string;
  external_id: string;
  title: string;
  company: string;
  salary: string;
  salary_cny?: string;
  city: string;
  skills: string[];
  core_tags: string[];
  regions: string[];
  is_remote: boolean;
  interest_tags: InterestTag[];
  preference_score: number;
  value_score: number;
  value_tags: ValueTagHit[];
  description: string;
  url: string;
  source_label?: string;
  match_score: number;
  posted_at: string | null;
  last_seen_at: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  offset: number;
  total: number;
  has_more: boolean;
}

export interface ChannelSummary {
  channel: string;
  count: number;
}

export interface PreferenceCount {
  key: string;
  label: string;
  count: number;
}

export interface ScrapedSummary {
  total: number;
  channels: ChannelSummary[];
  within_days: number;
  tech_counts: Record<string, number>;
  preference_counts: PreferenceCount[];
}

export interface MarkIndex {
  saved: string[];
  archived: string[];
  read: string[];
}

export type MarkState = "saved" | "archived";

export interface MarkRow {
  id: number;
  channel: string;
  external_id: string;
  state: MarkState;
  scraped_job_id: number | null;
  title: string;
  company: string;
  salary: string;
  city: string;
  skills: string[];
  description: string;
  url: string;
  source_label?: string;
  is_remote?: boolean;
  value_tags?: ValueTagHit[];
  note: string;
  read_at: string | null;
  created_at: string;
}

export interface JobDetail {
  id: number;
  channel: string;
  external_id: string;
  title: string;
  company: string;
  salary: string;
  salary_cny: string;
  salary_min_usd: number;
  salary_max_usd: number;
  salary_bucket: string;
  city: string;
  is_remote: boolean;
  experience: string;
  education: string;
  district: string;
  industry: string;
  stage: string;
  scale: string;
  welfare: string[];
  recruiter: string;
  skills: string[];
  description: string;
  sections: { title: string; body: string }[];
  company_intro: string;
  url: string;
  source_label?: string;
  match_score: number;
  value_score: number;
  posted_at: string | null;
  last_seen_at: string | null;
  has_real_jd: boolean;
  profile: JobProfileData | null;
  profile_generated_at: string | null;
  mark_state: MarkState | null;
  read_at: string | null;
  value_tags: ValueTagHit[];
  value_tag_library: ValueTagLibraryEntry[];
}

export type AskAction = "features" | "values" | "requirements" | "preference" | "resume" | "chat";

export interface AskReply {
  title: string;
  summary: string;
  score: number | null;
  bullets: string[];
  inferred: Record<string, string>;
  cached?: boolean;
}

export interface HiringIntent {
  type: string;
  reason: string;
}

export interface JobProfileData {
  verdict?: string;
  fit_score?: number;
  one_liner?: string;
  salary_min_usd?: number;
  salary_max_usd?: number;
  salary_note?: string;
  china_applicable?: string;
  china_reason?: string;
  stack_match?: string[];
  stack_gap?: string[];
  seniority?: string;
  hiring_intent?: HiringIntent;
  job_portrait?: string;
  company_profile?: string;
  red_flags?: string[];
  apply_tips?: string[];
  info_quality?: string;
  comment_sources?: string[];
  [key: string]: unknown;
}

export interface ChannelListItem {
  id: string;
  name: string;
  board: string;
  description: string;
  status: "active" | "missing_config" | "disabled";
  sync_supported?: boolean;
  sync_coverage?: string;
  last_sync?: {
    status: "queued" | "running" | "succeeded" | "failed";
    pulled: number;
    finished_at: string | null;
    error: string;
  } | null;
}

export interface ChannelField {
  key: string;
  label: string;
  type: "text" | "password" | "textarea";
  placeholder?: string;
  help?: string;
  required?: boolean;
}

export interface ChannelSchemaEntry {
  name: string;
  board: string;
  description: string;
  fields: ChannelField[];
}

export interface BoardInfo {
  name: string;
  desc: string;
}

export interface ChannelStatusEntry {
  stored: number;
  recent: number;
  scored_recent: number;
  latest_posted_at: string | null;
  last_synced_at: string | null;
}

export interface SalaryBucket {
  label: string;
  count: number;
}

export interface SalaryByChannel {
  channel: string;
  total: number;
  disclosed: number;
  avg: number;
}

export interface SalaryStats {
  total: number;
  disclosed: number;
  disclose_rate: number;
  median: number;
  p25: number;
  p75: number;
  max: number;
  buckets: SalaryBucket[];
  by_channel: SalaryByChannel[];
}

export interface DrillVideo {
  id: string;
  title: string;
  channel: string;
  description: string;
  thumbnail: string;
  published_at: string;
}

export interface DrillSearchResponse {
  videos: DrillVideo[];
  next_page_token: string;
  total_results: number;
}

export type ResumeModelId = "claude" | "codex" | "cursor";

export interface Resume {
  id: number;
  title: string;
  source_name: string;
  source_format: "pdf" | "word" | "md" | string;
  is_active: boolean;
  chars: number;
  final_chars: number;
  version_count: number;
  current_version: number;
  created_at: string | null;
  updated_at: string | null;
  markdown?: string;
  final_markdown?: string;
}

export type SuggestionStatus = "pending" | "adopted" | "rejected";

export type SuggestionKind = "analysis" | "optimize";

export interface AnalysisFinding {
  title: string;
  quote: string;
  body: string;
}

export interface ResumeAnalysis {
  id: number;
  resume_id: number;
  sop_id: number | null;
  sop_name: string;
  title: string;
  finding_count: number;
  findings?: AnalysisFinding[];
  created_at: string | null;
  updated_at: string | null;
}

export interface ResumeSuggestion {
  id: number;
  resume_id: number;
  model: ResumeModelId | string;
  title: string;
  quote: string;
  body: string;
  status: SuggestionStatus;
  kind: SuggestionKind | string;
  created_at: string | null;
}

export interface ResumeVersion {
  id: number;
  resume_id: number;
  version: number;
  markdown: string;
  note: string;
  model: ResumeModelId | string;
  is_current: boolean;
  chars: number;
  created_at: string | null;
}

export interface ResumeListResponse {
  resumes: Resume[];
  total: number;
}

export interface SopStep {
  id: string;
  from: "claude" | "codex" | "cursor";
  at: "claude" | "codex" | "cursor" | "" | "all";
  title: string;
  body: string;
}

export interface SopPlaybook {
  id: number;
  resume_id: number | null;
  name: string;
  description: string;
  brief: string;
  models: ResumeModelId[];
  steps: SopStep[];
  purpose: "analyze" | "optimize" | string;
  status: "draft" | "used" | string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SopListResponse {
  sops: SopPlaybook[];
  total: number;
}

export type JobRuleCategory =
  | "match_config"
  | "match_stack"
  | "match_signal"
  | "match_cap"
  | "match_verdict"
  | "quality_block"
  | "quality_suspect"
  | "recall"
  | "ingest_gate"
  | "ingest_gate_config"
  | string;

export interface JobRule {
  id: number;
  category: JobRuleCategory;
  key: string;
  label: string;
  pattern: string;
  weight: number;
  severity: "block" | "suspect" | "";
  enabled: boolean;
  rationale: string;
  config: Record<string, unknown>;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface JobRuleListResponse {
  rules: JobRule[];
  categories: string[];
  total: number;
}

export interface TelegramAccount {
  id: number;
  label: string;
  phone: string;
  api_id: string;
  api_hash: string;
  is_active: boolean;
  has_session: boolean;
}
