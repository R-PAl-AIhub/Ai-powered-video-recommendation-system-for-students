import {
  ArrowsClockwise,
  ChatsCircle,
  Check,
  DotsSixVertical,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Target,
  Trash,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Reorder, useDragControls } from "motion/react";
import { type FormEvent, useEffect, useState } from "react";

import { api, type SearchResult, type Topic } from "../api";
import { clock, cx, plural } from "../format";
import { Button, EmptyState, Field, IconButton, Notice, Skeleton } from "../ui";
import { FocusRow, QuestionCard, Thumb, VideoMeta } from "./parts";
import { playQueue, usePath, usePathChange, YouTubeFinder } from "./PathTab";
import { errorText, type TabProps } from "./Workspace";

// ------------------------------------------------------------------------ focus

/** The most important topics: what past papers ask most and the notes stress. */
export function FocusTab({ project, play }: TabProps) {
  const path = usePath(project.id);
  if (path.isLoading) return <Skeleton className="h-64 w-full" />;
  if (!path.data) return <Notice tone="danger">{errorText(path.error)}</Notice>;

  const ranked = path.data.topics
    .filter((topic) => topic.importance > 0)
    .sort((a, b) => b.importance - a.importance || a.position - b.position);
  if (ranked.length === 0) {
    return (
      <EmptyState icon={<Target size={22} />} title="Nothing to rank yet">
        Upload past exam papers or class notes on the Sources tab and build the path again. Topics
        are then ranked by how often they are asked and whether your teacher covered them.
      </EmptyState>
    );
  }
  const queue = playQueue(ranked);
  const gaps = ranked.filter((topic) => topic.status === "gap").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex max-w-[62ch] flex-col gap-1">
        <h2 className="text-2xl font-semibold">Most important topics</h2>
        <p className="text-soft">
          Ranked by how often past papers ask about each topic, with extra weight for topics in your
          class notes. Start at the top if time is short.
        </p>
      </div>
      {gaps ? (
        <Notice tone="warn" icon={<Warning size={17} weight="fill" />}>
          {plural(gaps, "important topic has", "important topics have")} no video. Find one from
          the Path tab, or study {gaps === 1 ? "it" : "them"} from your notes.
        </Notice>
      ) : null}
      <ol className="divide-y divide-line">
        {ranked.map((topic, index) => (
          <FocusRow
            key={topic.id}
            topic={topic}
            rank={index + 1}
            onPlay={() => play(queue.items, queue.indexOf.get(topic.id))}
          />
        ))}
      </ol>
    </div>
  );
}

// -------------------------------------------------------------------- questions

export function QuestionsTab({ project, play }: TabProps) {
  const questions = useQuery({
    queryKey: ["questions", project.id],
    queryFn: () => api.questions(project.id),
  });
  const [onlyOpen, setOnlyOpen] = useState(false);

  if (questions.isLoading) return <Skeleton className="h-64 w-full" />;
  if (!questions.data) return <Notice tone="danger">{errorText(questions.error)}</Notice>;
  const { total, answered } = questions.data;
  if (total === 0) {
    return (
      <EmptyState icon={<ChatsCircle size={22} />} title="No past questions yet">
        Upload past exam papers on the Sources tab and build the path again. Each question is then
        linked to the video moment that explains it.
      </EmptyState>
    );
  }
  const shown = questions.data.questions.filter((q) => !onlyOpen || q.answer === null);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-[60ch] flex-col gap-1">
          <h2 className="text-2xl font-semibold">Questions and answers</h2>
          <p className="text-soft">
            {answered} of {plural(total, "past question")} explained by a video in your playlists.
          </p>
        </div>
        {answered < total ? (
          <Button
            variant={onlyOpen ? "primary" : "outline"}
            size="sm"
            aria-pressed={onlyOpen}
            onClick={() => setOnlyOpen(!onlyOpen)}
          >
            {onlyOpen ? "Showing unanswered" : `Show ${total - answered} unanswered`}
          </Button>
        ) : null}
      </div>
      <ul className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {shown.map((question) => (
          <li key={question.id}>
            <QuestionCard
              question={question}
              className="h-full"
              onPlay={
                question.answer
                  ? () =>
                      play([
                        {
                          video: question.answer!.video,
                          startS: question.answer!.start_s,
                          endS: question.answer!.end_s,
                          label: question.text,
                        },
                      ])
                  : undefined
              }
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

// ----------------------------------------------------------------------- search

function ResultRow({ result, onPlay }: { result: SearchResult; onPlay: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onPlay}
        className="flex w-full gap-4 rounded-field py-3 text-left transition-colors hover:bg-ink/[0.03]"
      >
        <Thumb video={result.video} className="w-32 shrink-0 sm:w-40" />
        <span className="flex min-w-0 flex-col gap-1">
          <span className="line-clamp-2 text-[15px] font-medium text-ink">{result.video.title}</span>
          <VideoMeta video={result.video} startS={result.start_s} endS={result.end_s} />
          {result.snippet ? (
            <span className="line-clamp-2 text-[13px] leading-relaxed text-soft">
              “{result.snippet}”
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

export function SearchTab({ project, busy, play }: TabProps) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const change = usePathChange(project.id);
  const search = useQuery({
    queryKey: ["search", project.id, query],
    queryFn: () => api.search(project.id, query),
    enabled: query.length >= 2,
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setQuery(text.trim());
  }

  const outcome = search.data;
  const open = (results: SearchResult[], index: number) =>
    play(
      results.map((r) => ({
        video: r.video,
        startS: r.start_s,
        endS: r.end_s,
        label: outcome?.query ?? "",
      })),
      index,
    );

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Field
            label="Search your playlists for a topic"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Banker's algorithm"
            maxLength={200}
          />
        </div>
        <Button
          type="submit"
          className="h-11"
          icon={<MagnifyingGlass size={17} weight="bold" />}
          busy={search.isFetching}
          disabled={text.trim().length < 2}
        >
          Search
        </Button>
      </form>

      {search.error ? <Notice tone="danger">{errorText(search.error)}</Notice> : null}

      {outcome?.found ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">{outcome.message}</h2>
          <ul className="divide-y divide-line">
            {outcome.results.map((result, index) => (
              <ResultRow
                key={result.video.id}
                result={result}
                onPlay={() => open(outcome.results, index)}
              />
            ))}
          </ul>
        </section>
      ) : null}

      {outcome && !outcome.found ? (
        <section className="flex flex-col gap-5">
          <Notice tone="warn" icon={<Warning size={17} weight="fill" />}>
            {outcome.message}. None of your playlists explain it.
          </Notice>
          {outcome.closest.length ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium text-soft">Closest, but probably not what you need</h3>
              <ul className="divide-y divide-line opacity-80">
                {outcome.closest.map((result, index) => (
                  <ResultRow
                    key={result.video.id}
                    result={result}
                    onPlay={() => open(outcome.closest, index)}
                  />
                ))}
              </ul>
            </div>
          ) : null}
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-soft">Look beyond your playlists</h3>
            <YouTubeFinder
              key={outcome.query}
              projectId={project.id}
              query={outcome.query}
              locked={busy}
              change={change}
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------------------- topics

function TopicItem({
  topic,
  locked,
  onRename,
  onDelete,
  onDrop,
}: {
  topic: Topic;
  locked: boolean;
  onRename: (name: string) => void;
  onDelete: () => void;
  onDrop: () => void;
}) {
  const controls = useDragControls();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(topic.name);

  function save(event: FormEvent) {
    event.preventDefault();
    const next = name.trim();
    if (next.length >= 2 && next !== topic.name) onRename(next);
    setEditing(false);
  }

  return (
    <Reorder.Item
      value={topic.id}
      dragListener={false}
      dragControls={controls}
      onDragEnd={onDrop}
      className="flex items-center gap-2 border-b border-line bg-bg py-2"
    >
      <button
        type="button"
        aria-label={`Drag to reorder ${topic.name}`}
        disabled={locked}
        onPointerDown={(event) => controls.start(event)}
        className="grid size-8 shrink-0 cursor-grab touch-none place-items-center rounded-md text-faint hover:text-ink active:cursor-grabbing disabled:opacity-40"
      >
        <DotsSixVertical size={18} weight="bold" />
      </button>
      {editing ? (
        <form onSubmit={save} className="flex min-w-0 flex-1 items-center gap-1">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Topic name"
            autoFocus
            maxLength={300}
            className="h-9 min-w-0 flex-1 rounded-field border border-line-strong bg-raised px-3 text-sm focus:border-accent-ink focus:outline-none"
          />
          <IconButton label="Save" type="submit">
            <Check size={17} weight="bold" />
          </IconButton>
          <IconButton
            label="Cancel"
            onClick={() => {
              setName(topic.name);
              setEditing(false);
            }}
          >
            <X size={17} />
          </IconButton>
        </form>
      ) : (
        <>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-medium">{topic.name}</span>
            <span className="truncate text-[13px] text-faint">
              {[
                topic.unit,
                topic.status === "gap" ? "no video" : "",
                topic.source === "manual" ? "added by you" : "",
              ]
                .filter(Boolean)
                .join(", ")}
            </span>
          </div>
          <IconButton label={`Rename ${topic.name}`} disabled={locked} onClick={() => setEditing(true)}>
            <PencilSimple size={16} />
          </IconButton>
          <IconButton label={`Delete ${topic.name}`} disabled={locked} onClick={onDelete}>
            <Trash size={16} />
          </IconButton>
        </>
      )}
    </Reorder.Item>
  );
}

export function TopicsTab({ project, busy }: TabProps) {
  const client = useQueryClient();
  const path = usePath(project.id);
  const change = usePathChange(project.id);
  const [order, setOrder] = useState<number[]>([]);
  const [newName, setNewName] = useState("");

  const topics = path.data?.topics;
  useEffect(() => {
    if (topics) setOrder(topics.map((topic) => topic.id));
  }, [topics]);

  const reread = useMutation({
    mutationFn: () => api.process(project.id, true),
    onSuccess: () => client.invalidateQueries({ queryKey: ["project", project.id] }),
  });

  if (path.isLoading) return <Skeleton className="h-64 w-full" />;
  if (!topics) return <Notice tone="danger">{errorText(path.error)}</Notice>;

  const byId = new Map(topics.map((topic) => [topic.id, topic]));
  const locked = busy || change.isPending;
  const moved = order.some((id, index) => topics[index]?.id !== id);

  function onAdd(event: FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (name.length < 2) return;
    change.mutate(() => api.addTopic(project.id, name), { onSuccess: () => setNewName("") });
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-[60ch] flex-col gap-1">
          <h2 className="text-2xl font-semibold">Topics</h2>
          <p className="text-soft">
            Read from your syllabus. Rename, remove, add or drag to reorder; the path follows this
            order. {plural(topics.length, "topic")}.
          </p>
        </div>
        {project.topics_locked ? (
          <Button
            variant="outline"
            size="sm"
            icon={<ArrowsClockwise size={15} />}
            busy={reread.isPending}
            disabled={busy}
            onClick={() => reread.mutate()}
          >
            Read again from documents
          </Button>
        ) : null}
      </div>

      {change.error ? <Notice tone="danger">{errorText(change.error)}</Notice> : null}
      {reread.error ? <Notice tone="danger">{errorText(reread.error)}</Notice> : null}

      <form onSubmit={onAdd} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Field
            label="Add a topic"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Thrashing"
            maxLength={300}
          />
        </div>
        <Button
          type="submit"
          variant="outline"
          className="h-11"
          icon={<Plus size={16} weight="bold" />}
          disabled={locked || newName.trim().length < 2}
        >
          Add topic
        </Button>
      </form>

      {topics.length ? (
        <Reorder.Group
          axis="y"
          values={order}
          onReorder={locked ? () => undefined : setOrder}
          className={cx("flex flex-col", locked && "opacity-70")}
        >
          {order.map((id) => {
            const topic = byId.get(id);
            if (!topic) return null;
            return (
              <TopicItem
                key={id}
                topic={topic}
                locked={locked}
                onRename={(name) =>
                  change.mutate(() => api.updateTopic(project.id, id, { name }))
                }
                onDelete={() => change.mutate(() => api.deleteTopic(project.id, id))}
                onDrop={() => {
                  if (moved) change.mutate(() => api.reorderTopics(project.id, order));
                }}
              />
            );
          })}
        </Reorder.Group>
      ) : (
        <p className="text-soft">
          No topics yet. Add them here, or upload a syllabus on the Sources tab.
        </p>
      )}
      <p className="text-[13px] text-faint">
        Times in the path, such as {clock(754)}, are where a topic starts inside its video.
      </p>
    </div>
  );
}
