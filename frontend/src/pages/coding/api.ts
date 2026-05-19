/**
 * Typed wrappers around the AI Coding Assistant backend endpoints.
 * Each function returns the unwrapped response body and lets axios throw on
 * non-2xx so React Query can surface the error.
 */
import { api } from '../../lib/api';
import type {
  ApiExecResponse, ApiRequestSaved, BugFixResponse, ChatMessage, CodeGenResponse,
  CodeProject, CodeSnippet, CodingChatResponse, DBConnection, DBExecuteResult,
  DBSchema, DocstringResponse, ExplainResponse, FileContent, FileNode, FilePatchOp,
  GitCommit, GitStatus, MultiFileEditResponse, RegexExplainResult, RegexLibraryEntry,
  RegexTestResult, ReviewResponse, SupportedLanguage,
} from './types';

const COD = '/coding';

// ---- Projects + file tree ----------------------------------------------
export const listProjects = () => api.get<CodeProject[]>(`${COD}/projects`).then((r) => r.data);

export const createProject = (body: { name: string; path: string; description?: string; language_primary?: string }) =>
  api.post<CodeProject>(`${COD}/projects`, body).then((r) => r.data);

export const deleteProject = (id: string) => api.delete(`${COD}/projects/${id}`);

export const fileTree = (project_id: string, depth = 4) =>
  api.get<FileNode>(`${COD}/tree`, { params: { project_id, depth } }).then((r) => r.data);

export const readFile = (project_id: string, path: string) =>
  api.get<FileContent>(`${COD}/file`, { params: { project_id, path } }).then((r) => r.data);

export const writeFile = (project_id: string, path: string, content: string) =>
  api.post(`${COD}/file`, { path, content }, { params: { project_id } }).then((r) => r.data);

export const deleteFile = (project_id: string, path: string) =>
  api.delete(`${COD}/file`, { params: { project_id, path } });

export const newFile = (project_id: string, path: string, is_dir = false) =>
  api.post(`${COD}/file/new`, null, { params: { project_id, path, is_dir } }).then((r) => r.data);

export const renameFile = (project_id: string, old_path: string, new_path: string) =>
  api
    .post(`${COD}/file/rename`, null, { params: { project_id, old_path, new_path } })
    .then((r) => r.data);

export const searchInFiles = (project_id: string, query: string) =>
  api
    .get<{ hits: { path: string; line: number; snippet: string }[]; truncated: boolean }>(
      `${COD}/search-in-files`,
      { params: { project_id, query } },
    )
    .then((r) => r.data);

// ---- Terminal ----------------------------------------------------------
export const runCommand = (
  project_id: string,
  command: string,
  timeout_seconds = 60,
  cwd?: string,
) =>
  api
    .post<{ stdout: string; stderr: string; exit_code: number; duration_ms: number }>(
      `${COD}/terminal`,
      { command, timeout_seconds, cwd },
      { params: { project_id } },
    )
    .then((r) => r.data);

// ---- Git ---------------------------------------------------------------
export const gitStatus = (project_id: string) =>
  api.get<GitStatus>(`${COD}/git/status`, { params: { project_id } }).then((r) => r.data);

export const gitLog = (project_id: string, limit = 50) =>
  api
    .get<{ branch: string | null; commits: GitCommit[] }>(`${COD}/git/log`, {
      params: { project_id, limit },
    })
    .then((r) => r.data);

export const gitDiff = (project_id: string, path?: string, staged = false) =>
  api
    .get<{ path: string | null; staged: boolean; diff: string }>(`${COD}/git/diff`, {
      params: { project_id, path, staged },
    })
    .then((r) => r.data);

export const gitBranches = (project_id: string) =>
  api
    .get<{ current: string | null; local: string[]; remote: string[] }>(`${COD}/git/branches`, {
      params: { project_id },
    })
    .then((r) => r.data);

export const gitStage = (project_id: string, paths: string[]) =>
  api.post(`${COD}/git/stage`, paths, { params: { project_id } }).then((r) => r.data);

export const gitUnstage = (project_id: string, paths: string[]) =>
  api.post(`${COD}/git/unstage`, paths, { params: { project_id } }).then((r) => r.data);

export const gitCommit = (project_id: string, message: string, add_all = true) =>
  api
    .post(`${COD}/git/commit`, { message, add_all }, { params: { project_id } })
    .then((r) => r.data);

export const gitCheckout = (project_id: string, branch: string, create = false) =>
  api.post(`${COD}/git/checkout`, null, { params: { project_id, branch, create } }).then((r) => r.data);

export const gitPush = (project_id: string, remote = 'origin', branch?: string) =>
  api.post(`${COD}/git/push`, { remote, branch }, { params: { project_id } }).then((r) => r.data);

export const gitPull = (project_id: string, remote = 'origin', branch?: string) =>
  api.post(`${COD}/git/pull`, { remote, branch }, { params: { project_id } }).then((r) => r.data);

export const gitInit = (project_id: string) =>
  api.post(`${COD}/git/init`, null, { params: { project_id } }).then((r) => r.data);

// ---- Snippets ----------------------------------------------------------
export const listSnippets = (q?: string, language?: string) =>
  api.get<CodeSnippet[]>(`${COD}/snippets`, { params: { q, language } }).then((r) => r.data);

export const createSnippet = (body: Omit<CodeSnippet, 'id' | 'use_count' | 'created_at' | 'updated_at'>) =>
  api.post<CodeSnippet>(`${COD}/snippets`, body).then((r) => r.data);

export const updateSnippet = (
  id: string,
  body: Omit<CodeSnippet, 'id' | 'use_count' | 'created_at' | 'updated_at'>,
) => api.put<CodeSnippet>(`${COD}/snippets/${id}`, body).then((r) => r.data);

export const deleteSnippet = (id: string) => api.delete(`${COD}/snippets/${id}`);

export const useSnippet = (id: string) =>
  api.post<CodeSnippet>(`${COD}/snippets/${id}/use`).then((r) => r.data);

export const suggestSnippet = (body: {
  description: string;
  language: string;
  provider?: string;
  api_key_override?: string | null;
}) =>
  api
    .post<{ title: string; code: string; language: string; description: string; provider: string }>(
      `${COD}/snippets/suggest`,
      body,
    )
    .then((r) => r.data);

// ---- API tester --------------------------------------------------------
export const listApiRequests = (collection?: string) =>
  api.get<ApiRequestSaved[]>(`${COD}/api-requests`, { params: { collection } }).then((r) => r.data);

export const saveApiRequest = (body: Omit<ApiRequestSaved, 'id' | 'created_at'>) =>
  api.post<ApiRequestSaved>(`${COD}/api-requests`, body).then((r) => r.data);

export const updateApiRequest = (id: string, body: Omit<ApiRequestSaved, 'id' | 'created_at'>) =>
  api.put<ApiRequestSaved>(`${COD}/api-requests/${id}`, body).then((r) => r.data);

export const deleteApiRequest = (id: string) => api.delete(`${COD}/api-requests/${id}`);

export const executeApiRequest = (body: {
  method: string;
  url: string;
  headers?: Record<string, string>;
  params?: Record<string, string>;
  body?: string | null;
  timeout?: number;
}) =>
  api
    .post<ApiExecResponse>(`${COD}/api-tester/execute`, {
      ...body,
      headers: body.headers ?? {},
      params: body.params ?? {},
    })
    .then((r) => r.data);

// ---- AI: chat / generate / explain / docstring / bugfix / review -----
type Byo = { provider?: string; model?: string; api_key_override?: string | null };

export const codingChat = (body: {
  messages: ChatMessage[];
  project_id?: string;
  context_files?: string[];
  max_tokens?: number;
  temperature?: number;
} & Byo) => api.post<CodingChatResponse>(`${COD}/ai/chat`, body).then((r) => r.data);

export const aiGenerate = (body: {
  prompt: string;
  language?: string;
  project_id?: string;
  context_files?: string[];
} & Byo) => api.post<CodeGenResponse>(`${COD}/ai/generate`, body).then((r) => r.data);

export const aiExplain = (body: { code: string; language: string } & Byo) =>
  api.post<ExplainResponse>(`${COD}/ai/explain`, body).then((r) => r.data);

export const aiDocstring = (body: { code: string; language: string; style?: string } & Byo) =>
  api.post<DocstringResponse>(`${COD}/ai/docstring`, body).then((r) => r.data);

export const aiBugfix = (body: { code: string; error?: string; language: string } & Byo) =>
  api.post<BugFixResponse>(`${COD}/ai/bugfix`, body).then((r) => r.data);

export const aiReview = (body: { code: string; language: string; focus?: string } & Byo) =>
  api.post<ReviewResponse>(`${COD}/ai/review`, body).then((r) => r.data);

// ---- Multi-file ---------------------------------------------------------
export const planMultiFile = (body: {
  project_id: string;
  prompt: string;
  context_files: string[];
  target_files: string[];
}) => api.post<MultiFileEditResponse>(`${COD}/ai/multi-file-plan`, body).then((r) => r.data);

export const applyMultiFile = (project_id: string, changes: FilePatchOp[]) =>
  api
    .post<{ applied: string[]; count: number }>(`${COD}/ai/multi-file-apply`, {
      project_id,
      changes,
    })
    .then((r) => r.data);

// ---- Regex --------------------------------------------------------------
export const regexExplain = (body: { pattern: string; flags?: string } & Byo) =>
  api.post<RegexExplainResult>(`${COD}/regex/explain`, body).then((r) => r.data);

export const regexTest = (body: {
  pattern: string;
  flags?: string;
  text: string;
  replacement?: string;
}) => api.post<RegexTestResult>(`${COD}/regex/test`, body).then((r) => r.data);

export const regexFromDescription = (body: {
  description: string;
  examples_match?: string[];
  examples_no_match?: string[];
} & Byo) =>
  api
    .post<{ pattern: string; flags: string; explanation: string; provider: string }>(
      `${COD}/regex/from-description`,
      body,
    )
    .then((r) => r.data);

export const listRegexLibrary = () =>
  api.get<RegexLibraryEntry[]>(`${COD}/regex/library`).then((r) => r.data);

export const saveRegexLibrary = (body: Omit<RegexLibraryEntry, 'id' | 'created_at'>) =>
  api.post<RegexLibraryEntry>(`${COD}/regex/library`, body).then((r) => r.data);

export const deleteRegexLibrary = (id: string) =>
  api.delete(`${COD}/regex/library/${id}`);

// ---- DB query builder + connections ------------------------------------
export const aiDbQuery = (body: {
  description: string;
  dialect: string;
  schema_hint?: string;
} & Byo) =>
  api
    .post<{ sql: string; explanation: string; provider: string }>(`${COD}/ai/db-query`, body)
    .then((r) => r.data);

export const listDbConnections = () =>
  api.get<DBConnection[]>(`${COD}/db/connections`).then((r) => r.data);

export const createDbConnection = (body: { name: string; dialect: string; dsn: string }) =>
  api.post<DBConnection>(`${COD}/db/connections`, body).then((r) => r.data);

export const deleteDbConnection = (id: string) =>
  api.delete(`${COD}/db/connections/${id}`);

export const dbIntrospect = (id: string) =>
  api.get<DBSchema>(`${COD}/db/connections/${id}/schema`).then((r) => r.data);

export const dbExecute = (body: { connection_id: string; sql: string; limit?: number }) =>
  api.post<DBExecuteResult>(`${COD}/db/execute`, body).then((r) => r.data);

// ---- Languages ----------------------------------------------------------
export const listLanguages = () =>
  api
    .get<{ count: number; languages: SupportedLanguage[] }>(`${COD}/languages`)
    .then((r) => r.data);
