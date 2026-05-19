export type AiProvider = 'anthropic' | 'openai' | 'ollama';

export type CodeProject = {
  id: string;
  name: string;
  path: string;
  description: string | null;
  language_primary: string | null;
  is_git: boolean;
  created_at: string;
  updated_at: string;
};

export type FileNode = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  children?: FileNode[];
};

export type FileContent = {
  path: string;
  content: string;
  language: string | null;
  size: number | null;
};

export type EditorTab = {
  path: string;
  language: string;
  original: string;
  current: string;
  dirty: boolean;
};

export type ChatMessage = { role: 'system' | 'user' | 'assistant'; content: string };

export type CodingChatResponse = {
  text: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
};

export type CodeGenResponse = { code: string; explanation: string; provider: string; model: string };
export type ExplainResponse = { explanation: string; provider: string; model: string };
export type DocstringResponse = { documented_code: string; provider: string; model: string };
export type BugFixResponse = { fixed_code: string; explanation: string; provider: string; model: string };

export type ReviewFinding = {
  line: number | null;
  severity: 'low' | 'medium' | 'high' | string;
  category: string;
  message: string;
  suggestion: string | null;
};

export type ReviewResponse = {
  summary: string;
  findings: ReviewFinding[];
  provider: string;
  model: string;
};

export type FilePatchOp = { path: string; content: string; create_if_missing: boolean };
export type MultiFileEditResponse = {
  summary: string;
  changes: FilePatchOp[];
  provider: string;
  model: string;
};

export type GitStatus = {
  branch: string;
  is_dirty: boolean;
  untracked: string[];
  modified: string[];
  staged: string[];
  ahead: number;
  behind: number;
};

export type GitCommit = {
  sha: string;
  full_sha: string;
  author: string;
  date: string;
  message: string;
  body: string;
};

export type CodeSnippet = {
  id: string;
  title: string;
  language: string;
  code: string;
  description: string | null;
  tags: string[];
  is_public: boolean;
  use_count: number;
  created_at: string;
  updated_at: string;
};

export type ApiRequestSaved = {
  id: string;
  name: string;
  method: string;
  url: string;
  headers: Record<string, string>;
  params: Record<string, string>;
  body: string | null;
  collection: string | null;
  created_at: string;
};

export type ApiExecResponse = {
  status: number;
  headers: Record<string, string>;
  body: string;
  duration_ms: number;
  size_bytes: number;
  content_type: string | null;
};

export type DBConnection = {
  id: string;
  name: string;
  dialect: string;
  created_at: string;
};

export type DBSchemaTable = {
  name: string;
  columns: { name: string; type: string; nullable: boolean; default: string | null }[];
  primary_key: string[];
  foreign_keys: { columns: string[]; referred_table: string; referred_columns: string[] }[];
};

export type DBSchema = { dialect: string; tables: DBSchemaTable[] };

export type DBExecuteResult = {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  duration_ms: number;
  truncated: boolean;
};

export type RegexMatchHit = {
  match: string;
  start: number;
  end: number;
  groups: string[];
};

export type RegexTestResult = {
  matches: RegexMatchHit[];
  is_valid: boolean;
  error: string | null;
  replaced: string | null;
};

export type RegexExplainResult = {
  pattern: string;
  flags: string;
  explanation: string;
  test_cases: { input: string; should_match: boolean; note?: string }[];
  provider: string;
};

export type RegexLibraryEntry = {
  id: string;
  title: string;
  pattern: string;
  flags: string;
  description: string | null;
  explanation: string | null;
  created_at: string;
};

export type SupportedLanguage = { language: string; sample_extension: string };
