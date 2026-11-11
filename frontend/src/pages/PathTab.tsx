import {
  ArrowCounterClockwise,
  CaretDown,
  CheckCircle,
  MagnifyingGlass,
  Path as PathIcon,
  Plus,
  Prohibit,
  Swap,
  ThumbsUp,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  api,
  type FeedbackKind,
  type Path,
  type Recommendation,
  type Topic,
  type YouTubeResult,
} from "../api";
import { clock, compact, cx, plural, span } from "../format";
import { Button, EmptyState, Notice, Skeleton } from "../ui";
import { GapRow, KnownRow, PathRow } from "./parts";
import { errorText, type PlayItem, type TabProps } from "./Workspace";

/** Runs a change that returns the re-planned path, and stores that path. */
export function usePathChange(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (change: () => Promise<Path>) => change(),
    onSuccess: (path) => {
      client.setQueryData(["path", projectId], path);
      client.invalidateQueries({ queryKey: ["project", projectId] });
      client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function usePath(projectId: number) {
  return useQuery({ queryKey: ["path", projectId], queryFn: () => api.path(projectId) });
}

/** Every matched topic, in path order, as something the player can step through. */
export function playQueue(topics: Topic[]): { items: PlayItem[]; indexOf: Map<number, number> } {
  const items: PlayItem[] = [];
  const indexOf = new Map<number, number>();
  for (const topic of topics) {
    if (topic.status === "matched" && topic.primary) {
      indexOf.set(topic.id, items.length);
      const parts = topic.primary.segments.length
        ? topic.primary.segments
        : [{ video: topic.primary.video, start_s: topic.primary.start_s, end_s: topic.primary.end_s }];
      parts.forEach((part, index) =>
        items.push({
          video: part.video,
          startS: part.start_s,
          endS: part.end_s,
          label: parts.length > 1 ? `${topic.name} (part ${index + 1} of ${parts.length})` : topic.name,
        }),
      );
    }
  }
  return { items, indexOf };
}

const FEEDBACK: { kind: FeedbackKind; label: string; done: string; icon: typeof ThumbsUp }[] = [
  { kind: "correct", label: "Correct", done: "You confirmed this video", icon: ThumbsUp },
  { kind: "wrong_topic", label: "Wrong topic", done: "", icon: Swap },
  { kind: "already_covered", label: "Already in my playlist", done: "", icon: CheckCircle },
  { kind: "irrelevant", label: "Irrelevant", done: "", icon: Prohibit },
];

/** The last feedback the student gave, kept so it can be undone. Feedback can
 *  change a row completely (a new video, a gap, a known topic), so the undo
 *  control cannot live inside the row. */
interface SentFeedback {
  topicId: number;
  videoId: number;
  kind: FeedbackKind;
  topicName: string;
}

const SENT_TEXT: Record<FeedbackKind, string> = {
  correct: "Video confirmed for",
  wrong_topic: "Video removed from",
  irrelevant: "Video removed from the course, including",
  already_covered: "Marked as already in your playlist:",
};

function UndoBar({
  sent,
  busy,
  onUndo,
  onDismiss,
}: {
  sent: SentFeedback;
  busy: boolean;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-xl items-center gap-3 rounded-full border border-line-strong bg-raised py-2 pr-2 pl-5 shadow-card"
    >
      <p className="min-w-0 flex-1 truncate text-sm">
        {SENT_TEXT[sent.kind]} “{sent.topicName}”
      </p>
      <Button
        variant="outline"
        size="sm"
        busy={busy}
        icon={<ArrowCounterClockwise size={14} />}
        onClick={onUndo}
      >
        Undo
      </Button>
      <Button variant="quiet" size="sm" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}

function Alternate({
  pick,
  disabled,
  onUse,
  onPlay,
}: {
  pick: Recommendation;
  disabled: boolean;
  onUse: () => void;
  onPlay: () => void;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      <button type="button" onClick={onPlay} className="flex min-w-0 flex-1 flex-col text-left">
        <span className="truncate text-sm text-ink hover:underline">{pick.video.title}</span>
        <span className="truncate text-[13px] text-faint">
          {pick.video.playlist_title || pick.video.channel}, {clock(pick.video.duration_s)}
          {pick.start_s >= 1 ? `, from ${clock(pick.start_s)}` : ""}
        </span>
      </button>
      <Button variant="outline" size="sm" disabled={disabled} onClick={onUse}>
        Use this
      </Button>
    </li>
  );
}

function MatchedControls({
  projectId,
  topic,
  locked,
  change,
  play,
  onSent,
}: {
  projectId: number;
  topic: Topic;
  locked: boolean;
  change: ReturnType<typeof usePathChange>;
  play: TabProps["play"];
  onSent: (sent: SentFeedback) => void;
}) {
  const [open, setOpen] = useState(false);
  const pick = topic.primary!;
  const disabled = locked || change.isPending;
  const send = (kind: FeedbackKind, videoId = pick.video.id) =>
    change.mutate(() => api.feedback(projectId, topic.id, videoId, kind), {
      onSuccess: () => onSent({ topicId: topic.id, videoId, kind, topicName: topic.name }),
    });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {pick.feedback === "correct" ? (
          <>
            <span className="flex items-center gap-1.5 text-[13px] text-accent-ink">
              <ThumbsUp size={14} weight="fill" aria-hidden />
              You confirmed this video
            </span>
            <Button
              variant="quiet"
              size="sm"
              disabled={disabled}
              icon={<ArrowCounterClockwise size={14} />}
              onClick={() =>
                change.mutate(() => api.undoFeedback(projectId, topic.id, pick.video.id))
              }
            >
              Undo
            </Button>
          </>
        ) : (
          FEEDBACK.map(({ kind, label, icon: Icon }) => (
            <Button
              key={kind}
              variant="quiet"
              size="sm"
              disabled={disabled}
              icon={<Icon size={14} />}
              onClick={() => send(kind)}
              className="px-2.5"
            >
              {label}
            </Button>
          ))
        )}
        {topic.alternates.length ? (
          <Button
            variant="quiet"
            size="sm"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="ml-auto px-2.5"
          >
            {plural(topic.alternates.length, "other video")}
            <CaretDown size={13} className={cx("transition-transform", open && "rotate-180")} />
          </Button>
        ) : null}
      </div>
      {open ? (
        <ul className="divide-y divide-line rounded-field border border-line px-3">
          {topic.alternates.map((alternate) => (
            <Alternate
              key={alternate.video.id}
              pick={alternate}
              disabled={disabled}
              onUse={() => send("correct", alternate.video.id)}
              onPlay={() =>
                play([
                  {
                    video: alternate.video,
                    startS: alternate.start_s,
                    endS: alternate.end_s,
                    label: topic.name,
                  },
                ])
              }
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** For a topic with no video: look beyond the student's playlists. */
export function YouTubeFinder({
  projectId,
  topicId,
  query,
  locked,
  change,
}: {
  projectId: number;
  topicId?: number;
  query?: string;
  locked: boolean;
  change: ReturnType<typeof usePathChange>;
}) {
  const find = useMutation({
    mutationFn: () =>
      api.youtubeSearch(projectId, topicId !== undefined ? { topic_id: topicId } : { query }),
  });
  const results: YouTubeResult[] | undefined = find.data;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          icon={<MagnifyingGlass size={15} />}
          busy={find.isPending}
          onClick={() => find.mutate()}
        >
          Find on YouTube
        </Button>
        {topicId !== undefined ? (
          <Button
            variant="quiet"
            size="sm"
            disabled={locked || change.isPending}
            icon={<CheckCircle size={15} />}
            onClick={() =>
              change.mutate(() => api.updateTopic(projectId, topicId, { covered: true }))
            }
          >
            I will study it myself
          </Button>
        ) : null}
      </div>
      {find.error ? <Notice tone="danger">{errorText(find.error)}</Notice> : null}
      {change.error ? <Notice tone="danger">{errorText(change.error)}</Notice> : null}
      {results && results.length === 0 ? (
        <p className="text-sm text-soft">YouTube returned nothing for this topic.</p>
      ) : null}
      {results?.length ? (
        <ul className="divide-y divide-line rounded-field border border-line px-3">
          {results.slice(0, 5).map((result) => (
            <li key={result.youtube_id} className="flex items-center gap-3 py-2.5">
              <img
                src={result.thumbnail_url}
                alt=""
                loading="lazy"
                className="aspect-video w-20 shrink-0 rounded-md bg-sunken object-cover"
              />
              <a
                href={result.url}
                target="_blank"
                rel="noreferrer"
                className="flex min-w-0 flex-1 flex-col"
              >
                <span className="truncate text-sm text-ink hover:underline">{result.title}</span>
                <span className="truncate text-[13px] text-faint">
                  {[
                    result.channel,
                    result.duration_s ? clock(result.duration_s) : "",
                    result.view_count ? `${compact(result.view_count)} views` : "",
                  ]
                    .filter(Boolean)
                    .join(", ")}
                </span>
              </a>
              <Button
                variant="outline"
                size="sm"
                icon={<Plus size={14} weight="bold" />}
                disabled={locked || change.isPending || result.in_project}
                onClick={() =>
                  change.mutate(() => api.addVideo(projectId, result.youtube_id, topicId))
                }
              >
                {result.in_project ? "Added" : "Add"}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: "warn";
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[13px] text-faint">{label}</dt>
      <dd className={cx("tabular font-mono text-2xl md:text-3xl", tone === "warn" && "text-warn")}>
        {value}
      </dd>
      {note ? <dd className="text-[13px] text-soft">{note}</dd> : null}
    </div>
  );
}

export function PathTab({ project, busy, play }: TabProps) {
  const path = usePath(project.id);
  const change = usePathChange(project.id);
  const [sent, setSent] = useState<SentFeedback | null>(null);

  useEffect(() => {
    if (!sent) return;
    const timer = window.setTimeout(() => setSent(null), 12_000);
    return () => window.clearTimeout(timer);
  }, [sent]);

  if (path.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }
  if (path.error || !path.data) {
    return <Notice tone="danger">{errorText(path.error, "The path could not be loaded.")}</Notice>;
  }
  const { topics, stats } = path.data;
  if (topics.length === 0) {
    return (
      <EmptyState icon={<PathIcon size={22} />} title="No study path yet">
        Add a playlist and your syllabus on the Sources tab, then build the path. Your topics and
        their videos will appear here in syllabus order.
      </EmptyState>
    );
  }

  const queue = playQueue(topics);
  // Group consecutive topics that share a unit.
  const units: { name: string; topics: { topic: Topic; number: number }[] }[] = [];
  topics.forEach((topic, index) => {
    const last = units[units.length - 1];
    if (last && last.name === topic.unit) last.topics.push({ topic, number: index + 1 });
    else units.push({ name: topic.unit, topics: [{ topic, number: index + 1 }] });
  });

  return (
    <div className="flex flex-col gap-10">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-6 border-b border-line pb-8 md:grid-cols-4">
        <Stat label="Topics with a video" value={`${stats.matched}/${stats.topics}`} />
        <Stat
          label="No video found"
          value={String(stats.gaps)}
          tone={stats.gaps ? "warn" : undefined}
          note={stats.gaps_with_reading ? `${stats.gaps_with_reading} explained in your reading` : undefined}
        />
        <Stat label="Left to watch" value={span(stats.remaining_seconds)} />
        <Stat label="Videos watched" value={`${stats.watched}/${stats.videos}`} />
      </dl>

      {change.error ? <Notice tone="danger">{errorText(change.error)}</Notice> : null}

      {units.map((unit, unitIndex) => (
        <section key={`${unit.name}-${unitIndex}`} className="flex flex-col">
          <h2 className="sticky top-16 z-10 -mx-4 border-b border-line bg-bg/90 px-4 py-3 text-lg font-semibold backdrop-blur-md md:mx-0 md:px-0">
            {unit.name || "Topics"}
          </h2>
          <ol className="divide-y divide-line">
            {unit.topics.map(({ topic, number }) => {
              if (topic.status === "covered") {
                return (
                  <KnownRow key={topic.id} topic={topic} number={number}>
                    <Button
                      variant="quiet"
                      size="sm"
                      disabled={busy || change.isPending}
                      icon={<ArrowCounterClockwise size={14} />}
                      onClick={() =>
                        change.mutate(() => api.updateTopic(project.id, topic.id, { covered: false }))
                      }
                    >
                      Put it back
                    </Button>
                  </KnownRow>
                );
              }
              if (!topic.primary) {
                return (
                  <GapRow key={topic.id} topic={topic} number={number}>
                    <YouTubeFinder
                      projectId={project.id}
                      topicId={topic.id}
                      locked={busy}
                      change={change}
                    />
                  </GapRow>
                );
              }
              const previous = topics[number - 2];
              const continues =
                previous?.status === "matched" &&
                previous.primary?.video.id === topic.primary.video.id;
              return (
                <PathRow
                  key={topic.id}
                  topic={topic}
                  number={number}
                  continues={continues}
                  onPlay={(part = 0) => play(queue.items, (queue.indexOf.get(topic.id) ?? 0) + part)}
                >
                  <MatchedControls
                    projectId={project.id}
                    topic={topic}
                    locked={busy}
                    change={change}
                    play={play}
                    onSent={setSent}
                  />
                </PathRow>
              );
            })}
          </ol>
        </section>
      ))}

      {sent ? (
        <UndoBar
          sent={sent}
          busy={change.isPending}
          onDismiss={() => setSent(null)}
          onUndo={() =>
            change.mutate(() => api.undoFeedback(project.id, sent.topicId, sent.videoId), {
              onSuccess: () => setSent(null),
            })
          }
        />
      ) : null}
    </div>
  );
}
