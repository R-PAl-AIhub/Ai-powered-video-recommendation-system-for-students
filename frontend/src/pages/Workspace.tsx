import {
  ArrowLeft,
  ArrowRight,
  ArrowSquareOut,
  CheckCircle,
  ClipboardText,
  FileText,
  Trash,
  UploadSimple,
  Warning,
  YoutubeLogo,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import {
  api,
  ApiError,
  type DocumentInfo,
  type DocumentKind,
  type Job,
  type ProjectDetail,
  type Video,
} from "../api";
import { clock, cx, embedUrl, fileSize, plural, until } from "../format";
import { Button, Dialog, Field, IconButton, Notice, Skeleton, TextArea } from "../ui";
import { FocusTab, QuestionsTab, SearchTab, TopicsTab } from "./MoreTabs";
import { PathTab } from "./PathTab";
import { AppBar } from "./Projects";

/** Something to play: a video, where to start, and what it is for. */
export interface PlayItem {
  video: Video;
  startS: number;
  label: string;
}

export interface TabProps {
  project: ProjectDetail;
  busy: boolean; // an analysis is running; changes are refused until it ends
  play: (items: PlayItem[], index?: number) => void;
}

const TABS = [
  { key: "sources", label: "Sources" },
  { key: "path", label: "Path" },
  { key: "focus", label: "Focus" },
  { key: "questions", label: "Questions" },
  { key: "search", label: "Search" },
  { key: "topics", label: "Topics" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const isActive = (job: Job | null | undefined) =>
  job?.status === "queued" || job?.status === "running";

export function errorText(error: unknown, fallback = "Something went wrong. Please try again.") {
  return error instanceof ApiError ? error.message : fallback;
}

// ---------------------------------------------------------------------- player

function Player({
  projectId,
  queue,
  onClose,
  onMove,
}: {
  projectId: number;
  queue: { items: PlayItem[]; index: number } | null;
  onClose: () => void;
  onMove: (index: number) => void;
}) {
  const client = useQueryClient();
  const item = queue ? queue.items[queue.index] : null;
  const [watched, setWatched] = useState(false);
  useEffect(() => setWatched(item?.video.watched ?? false), [item]);

  const mark = useMutation({
    mutationFn: (next: boolean) => api.setWatched(projectId, item!.video.id, next),
    onSuccess: (_, next) => {
      setWatched(next);
      client.invalidateQueries({ queryKey: ["path", projectId] });
      client.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  return (
    <Dialog open={item !== null} onClose={onClose} title={item?.label ?? ""} wide>
      {item && queue ? (
        <div className="flex flex-col gap-4">
          <div className="aspect-video overflow-hidden rounded-field bg-black">
            <iframe
              key={`${item.video.youtube_id}-${item.startS}`}
              src={embedUrl(item.video.youtube_id, item.startS)}
              title={item.video.title}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              className="size-full"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 flex-col">
              <p className="truncate font-medium">{item.video.title}</p>
              <p className="text-[13px] text-faint">
                {item.video.channel}
                {item.startS >= 1 ? `, from ${clock(item.startS)}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant={watched ? "primary" : "outline"}
                size="sm"
                busy={mark.isPending}
                icon={<CheckCircle size={16} weight={watched ? "fill" : "regular"} />}
                onClick={() => mark.mutate(!watched)}
              >
                {watched ? "Watched" : "Mark as watched"}
              </Button>
              <a
                href={`https://www.youtube.com/watch?v=${item.video.youtube_id}${item.startS >= 1 ? `&t=${Math.floor(item.startS)}s` : ""}`}
                target="_blank"
                rel="noreferrer"
                className="inline-grid size-9 place-items-center rounded-full text-soft hover:bg-ink/5 hover:text-ink"
                aria-label="Open on YouTube"
                title="Open on YouTube"
              >
                <ArrowSquareOut size={18} />
              </a>
              {queue.items.length > 1 ? (
                <>
                  <IconButton
                    label="Previous"
                    disabled={queue.index === 0}
                    onClick={() => onMove(queue.index - 1)}
                  >
                    <ArrowLeft size={18} />
                  </IconButton>
                  <span className="tabular font-mono text-xs text-faint">
                    {queue.index + 1}/{queue.items.length}
                  </span>
                  <IconButton
                    label="Next"
                    disabled={queue.index === queue.items.length - 1}
                    onClick={() => onMove(queue.index + 1)}
                  >
                    <ArrowRight size={18} />
                  </IconButton>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}

// --------------------------------------------------------------------- sources

const KINDS: { kind: DocumentKind; title: string; hint: string }[] = [
  { kind: "syllabus", title: "Syllabus", hint: "The list of topics your exam covers." },
  { kind: "exam", title: "Past papers", hint: "Shows which topics are asked most." },
  { kind: "notes", title: "Class notes", hint: "Typed or handwritten. Photos work." },
];

function DocumentRow({ doc, onRemove, locked }: { doc: DocumentInfo; onRemove: () => void; locked: boolean }) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <FileText size={18} className="shrink-0 text-faint" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col">
        <p className="truncate text-sm font-medium">{doc.filename}</p>
        <p className={cx("truncate text-[13px]", doc.status === "error" ? "text-danger" : "text-faint")}>
          {doc.status === "error"
            ? doc.error || "Could not be read"
            : doc.status === "pending"
              ? `${fileSize(doc.size_bytes)}, read when you build the path`
              : [
                  doc.page_count > 1 ? plural(doc.page_count, "page") : "",
                  `${doc.characters.toLocaleString()} characters`,
                  doc.ocr_pages ? `${plural(doc.ocr_pages, "page")} read with OCR` : "",
                ]
                  .filter(Boolean)
                  .join(", ")}
        </p>
      </div>
      <IconButton label={`Remove ${doc.filename}`} onClick={onRemove} disabled={locked}>
        <Trash size={16} />
      </IconButton>
    </li>
  );
}

function SourcesTab({ project, busy }: TabProps) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["project", project.id] });
  const [url, setUrl] = useState("");
  const [pasting, setPasting] = useState<DocumentKind | null>(null);
  const [pasted, setPasted] = useState("");
  const [uploadError, setUploadError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadKind = useRef<DocumentKind>("syllabus");

  const addPlaylist = useMutation({
    mutationFn: () => api.addPlaylist(project.id, url.trim()),
    onSuccess: () => {
      setUrl("");
      refresh();
    },
  });
  const removePlaylist = useMutation({
    mutationFn: (playlistId: number) => api.removePlaylist(project.id, playlistId),
    onSuccess: () => {
      refresh();
      client.invalidateQueries({ queryKey: ["path", project.id] });
    },
  });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadDocument(project.id, uploadKind.current, file);
    },
    onMutate: () => setUploadError(""),
    onError: (error) => setUploadError(errorText(error)),
    onSettled: refresh,
  });
  const addText = useMutation({
    mutationFn: () => api.addText(project.id, pasting!, pasted, ""),
    onSuccess: () => {
      setPasting(null);
      setPasted("");
      refresh();
    },
  });
  const removeDocument = useMutation({
    mutationFn: (documentId: number) => api.removeDocument(project.id, documentId),
    onSuccess: refresh,
  });
  const run = useMutation({ mutationFn: () => api.process(project.id), onSuccess: refresh });

  function onAddPlaylist(event: FormEvent) {
    event.preventDefault();
    if (url.trim()) addPlaylist.mutate();
  }

  function chooseFiles(kind: DocumentKind) {
    uploadKind.current = kind;
    fileInput.current?.click();
  }

  const hasSources = project.playlists.length > 0 || project.documents.length > 0;
  const job = project.job;

  return (
    <div className="flex flex-col gap-12">
      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-semibold">Playlists</h2>
          <p className="text-soft">
            The videos to choose from. List your favourite teacher first: the path stays with
            earlier playlists where it can.
          </p>
        </div>
        {project.playlists.length ? (
          <ul className="divide-y divide-line rounded-card border border-line bg-raised px-4">
            {project.playlists.map((playlist) => (
              <li key={playlist.id} className="flex items-center gap-3 py-3">
                <YoutubeLogo size={20} className="shrink-0 text-faint" aria-hidden />
                <div className="flex min-w-0 flex-1 flex-col">
                  <p className="truncate text-sm font-medium">{playlist.title || playlist.url}</p>
                  <p
                    className={cx(
                      "truncate text-[13px]",
                      playlist.status === "error" ? "text-danger" : "text-faint",
                    )}
                  >
                    {playlist.status === "error"
                      ? playlist.error
                      : playlist.status === "pending"
                        ? "Read when you build the path"
                        : `${playlist.channel}, ${plural(playlist.video_count, "video")}`}
                  </p>
                </div>
                <IconButton
                  label="Remove playlist"
                  disabled={busy}
                  onClick={() => removePlaylist.mutate(playlist.id)}
                >
                  <Trash size={16} />
                </IconButton>
              </li>
            ))}
          </ul>
        ) : null}
        <form onSubmit={onAddPlaylist} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Field
              label="YouTube playlist link"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/playlist?list=..."
              error={addPlaylist.error ? errorText(addPlaylist.error) : undefined}
              inputMode="url"
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            className={cx("h-11", addPlaylist.error && "sm:mb-7")}
            busy={addPlaylist.isPending}
            disabled={!url.trim() || busy}
          >
            Add playlist
          </Button>
        </form>
      </section>

      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-semibold">Documents</h2>
          <p className="text-soft">PDF, Word, text, or photos and scans. Up to 25 MB each.</p>
        </div>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length) upload.mutate(files);
          }}
        />
        {uploadError ? <Notice tone="danger">{uploadError}</Notice> : null}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {KINDS.map(({ kind, title, hint }) => {
            const docs = project.documents.filter((d) => d.kind === kind);
            return (
              <div key={kind} className="flex flex-col gap-3 rounded-card border border-line bg-raised p-5">
                <div className="flex flex-col gap-0.5">
                  <h3 className="font-semibold">{title}</h3>
                  <p className="text-[13px] text-faint">{hint}</p>
                </div>
                {docs.length ? (
                  <ul className="divide-y divide-line">
                    {docs.map((doc) => (
                      <DocumentRow
                        key={doc.id}
                        doc={doc}
                        locked={busy}
                        onRemove={() => removeDocument.mutate(doc.id)}
                      />
                    ))}
                  </ul>
                ) : null}
                <div className="mt-auto flex flex-wrap gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    icon={<UploadSimple size={15} />}
                    disabled={busy}
                    busy={upload.isPending && uploadKind.current === kind}
                    onClick={() => chooseFiles(kind)}
                  >
                    Upload
                  </Button>
                  <Button
                    variant="quiet"
                    size="sm"
                    icon={<ClipboardText size={15} />}
                    disabled={busy}
                    onClick={() => setPasting(kind)}
                  >
                    Paste text
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-card border border-line bg-sunken p-5 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex max-w-[56ch] flex-col gap-1">
            <h2 className="text-xl font-semibold">
              {project.processed_at ? "Update your study path" : "Build your study path"}
            </h2>
            <p className="text-sm text-soft">
              Reads the transcripts and documents, finds the topics, and matches them. A playlist of
              80 videos takes about two minutes the first time.
            </p>
          </div>
          <Button
            size="lg"
            busy={busy || run.isPending}
            disabled={!hasSources}
            onClick={() => run.mutate()}
          >
            {busy ? "Analysing" : project.processed_at ? "Update the path" : "Build the path"}
          </Button>
        </div>
        {run.error ? <Notice tone="danger">{errorText(run.error)}</Notice> : null}
        {job?.status === "failed" ? <Notice tone="danger">{job.error}</Notice> : null}
        {job?.status === "done" && job.warnings.length ? (
          <Notice tone="warn" icon={<Warning size={17} weight="fill" />}>
            <ul className="flex list-none flex-col gap-1.5">
              {job.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </Notice>
        ) : null}
        {job?.retry_at ? (
          <p className="text-sm text-soft">Automatic retry {until(job.retry_at)}.</p>
        ) : null}
      </section>

      <Dialog
        open={pasting !== null}
        onClose={() => setPasting(null)}
        title={`Paste ${KINDS.find((k) => k.kind === pasting)?.title.toLowerCase() ?? "text"}`}
      >
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            addText.mutate();
          }}
        >
          <TextArea
            label="Text"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            placeholder={"Unit 1: Introduction\nConcept of Operating Systems, System Calls, ..."}
            error={addText.error ? errorText(addText.error) : undefined}
            rows={10}
          />
          <div className="flex justify-end gap-2">
            <Button variant="quiet" onClick={() => setPasting(null)}>
              Cancel
            </Button>
            <Button type="submit" busy={addText.isPending} disabled={pasted.trim().length < 10}>
              Add
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

// ----------------------------------------------------------------------- shell

export default function Workspace() {
  const projectId = Number(useParams().projectId);
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [queue, setQueue] = useState<{ items: PlayItem[]; index: number } | null>(null);

  const detail = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.project(projectId),
    // While the analysis runs, poll for its progress.
    refetchInterval: (query) => (isActive(query.state.data?.job) ? 1500 : false),
  });
  const project = detail.data;
  const busy = isActive(project?.job);

  // When an analysis finishes, everything derived from it is out of date.
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) {
      client.invalidateQueries({ queryKey: ["path", projectId] });
      client.invalidateQueries({ queryKey: ["questions", projectId] });
      client.invalidateQueries({ queryKey: ["projects"] });
    }
    wasBusy.current = busy;
  }, [busy, client, projectId]);

  if (detail.isLoading) {
    return (
      <div className="min-h-[100dvh]">
        <AppBar />
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-12 md:px-6">
          <Skeleton className="h-10 w-72" />
          <Skeleton className="h-64 w-full rounded-card" />
        </div>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="min-h-[100dvh]">
        <AppBar />
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-4 px-4 py-12 md:px-6">
          <Notice tone="danger">{errorText(detail.error, "This course could not be found.")}</Notice>
          <Link to="/app" className="text-sm font-medium text-accent-ink hover:underline">
            Back to your courses
          </Link>
        </div>
      </div>
    );
  }

  const requested = params.get("tab") as TabKey | null;
  const tab: TabKey =
    requested && TABS.some((t) => t.key === requested)
      ? requested
      : project.topics > 0
        ? "path"
        : "sources";
  const tabProps: TabProps = {
    project,
    busy,
    play: (items, index = 0) => setQueue({ items, index }),
  };

  return (
    <div className="min-h-[100dvh]">
      <AppBar>
        <span className="hidden min-w-0 items-center gap-2 text-sm text-soft sm:flex">
          <span aria-hidden>/</span>
          <span className="truncate font-medium text-ink">{project.name}</span>
        </span>
      </AppBar>

      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <nav
          aria-label="Course sections"
          className="scrollbar-none -mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 pt-4 md:mx-0 md:px-0"
        >
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setParams({ tab: key }, { replace: true })}
              aria-current={tab === key ? "page" : undefined}
              className={cx(
                "relative h-11 shrink-0 rounded-t-field px-3.5 text-sm font-medium transition-colors",
                tab === key ? "text-ink" : "text-faint hover:text-ink",
              )}
            >
              {label}
              {key === "path" && project.gaps > 0 ? (
                <span className="tabular ml-1.5 font-mono text-xs text-warn">{project.gaps}</span>
              ) : null}
              {tab === key ? (
                <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-accent-ink" />
              ) : null}
            </button>
          ))}
        </nav>

        {busy && project.job ? (
          <div role="status" className="mt-6 flex flex-col gap-2 rounded-field border border-line bg-raised px-4 py-3">
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="truncate">{project.job.message || "Starting"}</span>
              <span className="tabular font-mono text-xs text-faint">
                {Math.round(project.job.progress * 100)}%
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent-ink transition-[width] duration-700 ease-out-expo"
                style={{ width: `${Math.max(3, project.job.progress * 100)}%` }}
              />
            </div>
          </div>
        ) : project.stale && project.processed_at && tab !== "sources" ? (
          <div className="mt-6">
            <Notice tone="warn" icon={<Warning size={17} weight="fill" />}>
              Your sources changed since the last analysis.{" "}
              <button
                type="button"
                className="font-medium underline underline-offset-4"
                onClick={() => setParams({ tab: "sources" }, { replace: true })}
              >
                Update the path
              </button>
            </Notice>
          </div>
        ) : null}

        <main className="py-8 md:py-10">
          {tab === "sources" ? <SourcesTab {...tabProps} /> : null}
          {tab === "path" ? <PathTab {...tabProps} /> : null}
          {tab === "focus" ? <FocusTab {...tabProps} /> : null}
          {tab === "questions" ? <QuestionsTab {...tabProps} /> : null}
          {tab === "search" ? <SearchTab {...tabProps} /> : null}
          {tab === "topics" ? <TopicsTab {...tabProps} /> : null}
        </main>
      </div>

      <Player
        projectId={project.id}
        queue={queue}
        onClose={() => setQueue(null)}
        onMove={(index) => setQueue((current) => (current ? { ...current, index } : current))}
      />
    </div>
  );
}
