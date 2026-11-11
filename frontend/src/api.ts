/** Typed client for the backend API. The session is an httpOnly cookie, so
 *  requests only need `credentials: "same-origin"`. */

export type DocumentKind = "syllabus" | "exam" | "notes";
export type FeedbackKind = "correct" | "wrong_topic" | "irrelevant" | "already_covered";

export interface User {
  id: number;
  email: string;
  name: string;
}

export interface Job {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  stage: string;
  progress: number;
  message: string;
  error: string;
  warnings: string[];
  created_at: string;
  finished_at: string | null;
  retry_at: string | null;
}

export interface ProjectSummary {
  id: number;
  name: string;
  subject: string;
  description: string;
  created_at: string;
  processed_at: string | null;
  topics: number;
  matched: number;
  gaps: number;
  covered: number;
  videos: number;
  watched: number;
  job: Job | null;
}

export interface Playlist {
  id: number;
  youtube_id: string;
  url: string;
  title: string;
  channel: string;
  status: "pending" | "ready" | "error";
  error: string;
  video_count: number;
}

export interface DocumentInfo {
  id: number;
  kind: DocumentKind;
  filename: string;
  size_bytes: number;
  status: "pending" | "ready" | "error";
  error: string;
  page_count: number;
  ocr_pages: number;
  characters: number;
  preview: string;
}

export interface ProjectDetail extends ProjectSummary {
  relevance_threshold: number;
  topics_locked: boolean;
  stale: boolean;
  playlists: Playlist[];
  documents: DocumentInfo[];
}

export interface Video {
  id: number;
  youtube_id: string;
  title: string;
  channel: string;
  duration_s: number;
  view_count: number | null;
  like_count: number | null;
  thumbnail_url: string;
  playlist_id: number | null;
  playlist_title: string;
  playlist_position: number;
  transcript_status: string;
  transcript_language: string;
  source: string;
  watched: boolean;
}

export interface Recommendation {
  video: Video;
  rank: number;
  relevance: number;
  quality: number;
  score: number;
  start_s: number;
  end_s: number; // 0 = to the end of the video
  coverage_s: number;
  snippet: string;
  reasons: string[];
  url: string;
  feedback: FeedbackKind | null;
}

export interface Topic {
  id: number;
  name: string;
  unit: string;
  position: number;
  source: string;
  status: "matched" | "gap" | "covered";
  exam_hits: number;
  exam_weight: number;
  in_notes: boolean;
  notes_snippet: string;
  importance: number;
  primary: Recommendation | null;
  alternates: Recommendation[];
}

export interface PathStats {
  topics: number;
  matched: number;
  gaps: number;
  covered: number;
  videos: number;
  watched: number;
  total_seconds: number;
  remaining_seconds: number;
}

export interface Path {
  project_id: number;
  relevance_threshold: number;
  stats: PathStats;
  topics: Topic[];
}

export interface QuestionAnswer {
  video: Video;
  relevance: number;
  start_s: number;
  end_s: number;
  snippet: string;
  url: string;
}

export interface Question {
  id: number;
  text: string;
  source: string;
  topic_id: number | null;
  topic_name: string;
  answer: QuestionAnswer | null;
}

export interface Questions {
  total: number;
  answered: number;
  questions: Question[];
}

export interface SearchResult {
  video: Video;
  relevance: number;
  start_s: number;
  end_s: number;
  coverage_s: number;
  snippet: string;
  url: string;
}

export interface SearchOutcome {
  query: string;
  found: boolean;
  message: string;
  results: SearchResult[];
  closest: SearchResult[];
}

export interface YouTubeResult {
  youtube_id: string;
  title: string;
  channel: string;
  duration_s: number;
  view_count: number | null;
  thumbnail_url: string;
  url: string;
  in_project: boolean;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI reports problems as `{detail: "..."}` or, for validation, a list. */
function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
    const text = (first.msg ?? "Invalid input").replace(/^Value error, /, "");
    return field && field !== "body" ? `${field}: ${text}` : text;
  }
  if (status >= 500) return "The server had a problem. Please try again.";
  return "Something went wrong. Please try again.";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body !== undefined && !isForm ? { "Content-Type": "application/json" } : undefined,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection.");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  if (!response.ok) throw new ApiError(response.status, messageFrom(parsed, response.status));
  return parsed as T;
}

const project = (id: number) => `/projects/${id}`;

export const api = {
  // account
  me: () => request<User>("GET", "/auth/me"),
  register: (body: { email: string; name: string; password: string }) =>
    request<User>("POST", "/auth/register", body),
  login: (body: { email: string; password: string }) => request<User>("POST", "/auth/login", body),
  logout: () => request<void>("POST", "/auth/logout"),

  // projects
  projects: () => request<ProjectSummary[]>("GET", "/projects"),
  createProject: (body: { name: string; subject: string }) =>
    request<ProjectDetail>("POST", "/projects", body),
  project: (id: number) => request<ProjectDetail>("GET", project(id)),
  deleteProject: (id: number) => request<void>("DELETE", project(id)),

  // sources
  addPlaylist: (id: number, url: string) =>
    request<Playlist>("POST", `${project(id)}/playlists`, { url }),
  removePlaylist: (id: number, playlistId: number) =>
    request<void>("DELETE", `${project(id)}/playlists/${playlistId}`),
  uploadDocument: (id: number, kind: DocumentKind, file: File) => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return request<DocumentInfo>("POST", `${project(id)}/documents`, form);
  },
  addText: (id: number, kind: DocumentKind, text: string, title: string) =>
    request<DocumentInfo>("POST", `${project(id)}/documents/text`, { kind, text, title }),
  removeDocument: (id: number, documentId: number) =>
    request<void>("DELETE", `${project(id)}/documents/${documentId}`),
  process: (id: number, reextract = false) =>
    request<Job>("POST", `${project(id)}/process`, { reextract }),

  // learning
  path: (id: number) => request<Path>("GET", `${project(id)}/path`),
  questions: (id: number) => request<Questions>("GET", `${project(id)}/questions`),
  search: (id: number, query: string) =>
    request<SearchOutcome>("GET", `${project(id)}/search?q=${encodeURIComponent(query)}`),
  feedback: (id: number, topicId: number, videoId: number, kind: FeedbackKind) =>
    request<Path>("POST", `${project(id)}/feedback`, { topic_id: topicId, video_id: videoId, kind }),
  undoFeedback: (id: number, topicId: number, videoId: number) =>
    request<Path>("DELETE", `${project(id)}/feedback?topic_id=${topicId}&video_id=${videoId}`),
  setWatched: (id: number, videoId: number, watched: boolean) =>
    request<void>("PUT", `${project(id)}/videos/${videoId}/watched`, { watched }),
  addTopic: (id: number, name: string, afterId?: number) =>
    request<Path>("POST", `${project(id)}/topics`, { name, after_id: afterId ?? null }),
  updateTopic: (id: number, topicId: number, body: { name?: string; covered?: boolean }) =>
    request<Path>("PATCH", `${project(id)}/topics/${topicId}`, body),
  deleteTopic: (id: number, topicId: number) =>
    request<Path>("DELETE", `${project(id)}/topics/${topicId}`),
  orderLikePlaylists: (id: number) =>
    request<Path>("POST", `${project(id)}/topics/order/from-playlists`),
  reorderTopics: (id: number, ids: number[]) =>
    request<Path>("PUT", `${project(id)}/topics/order`, { ids }),
  youtubeSearch: (id: number, body: { topic_id?: number; query?: string }) =>
    request<YouTubeResult[]>("POST", `${project(id)}/youtube/search`, body),
  addVideo: (id: number, video: string, topicId?: number) =>
    request<Path>("POST", `${project(id)}/videos`, { video, topic_id: topicId ?? null }),
};
