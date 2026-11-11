/** Building blocks of the learning path, shared by the app and by the landing
 *  page (which shows these same components with sample data). */
import { ArrowBendDownRight, Check, Notebook, Play, Target, Warning } from "@phosphor-icons/react";
import type { ReactNode } from "react";

import type { Question, Topic, Video } from "../api";
import { clock, compact, cx, plural, studyRange } from "../format";
import { Layer, Tilt } from "../depth";
import { Chip } from "../ui";

export function Thumb({ video, className }: { video: Video; className?: string }) {
  return (
    <img
      src={video.thumbnail_url}
      alt=""
      loading="lazy"
      width={320}
      height={180}
      className={cx("aspect-video rounded-field bg-sunken object-cover", className)}
    />
  );
}

export function VideoMeta({ video, startS, endS = 0 }: { video: Video; startS?: number; endS?: number }) {
  const parts = [video.channel, clock(video.duration_s)];
  if (video.view_count) parts.push(`${compact(video.view_count)} views`);
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-[13px] text-faint">
      <span>{parts.filter(Boolean).join(", ")}</span>
      {startS !== undefined && (startS >= 1 || endS > 0) ? (
        <span className="tabular font-mono text-xs text-accent-ink">study {studyRange(startS, endS)}</span>
      ) : null}
    </p>
  );
}

export function TopicBadges({ topic }: { topic: Topic }) {
  if (topic.exam_hits === 0 && !topic.in_notes) return null;
  return (
    <span className="flex flex-wrap gap-1.5">
      {topic.exam_hits > 0 ? (
        <Chip tone="accent">
          <Target size={13} weight="bold" aria-hidden />
          Asked {plural(topic.exam_hits, "time")}
        </Chip>
      ) : null}
      {topic.in_notes ? (
        <Chip>
          <Notebook size={13} aria-hidden />
          In your notes
        </Chip>
      ) : null}
    </span>
  );
}

function PlayButton({ onPlay, label }: { onPlay?: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onPlay}
      aria-label={label}
      className={cx(
        "absolute inset-0 grid place-items-center rounded-field bg-black/0 text-white opacity-0",
        "transition duration-200 hover:bg-black/45 hover:opacity-100 focus-visible:bg-black/45 focus-visible:opacity-100",
      )}
    >
      <span className="grid size-11 place-items-center rounded-full bg-accent text-on-accent">
        <Play size={18} weight="fill" aria-hidden />
      </span>
    </button>
  );
}

const rowGrid =
  "grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 py-4 " +
  "md:grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,1.25fr)] md:gap-x-5";

function RowHead({ topic, number }: { topic: Topic; number: number }) {
  return (
    <>
      <span className="tabular pt-0.5 font-mono text-[13px] text-faint">
        {String(number).padStart(2, "0")}
      </span>
      <div className="flex min-w-0 flex-col gap-2">
        <h4 className="text-[15px] font-medium leading-snug text-ink">{topic.name}</h4>
        <TopicBadges topic={topic} />
      </div>
    </>
  );
}

/** One step of the path: a topic and the video that teaches it. */
export function PathRow({
  topic,
  number,
  continues = false,
  onPlay,
  children,
}: {
  topic: Topic;
  number: number;
  continues?: boolean; // same video as the step before
  onPlay?: () => void;
  children?: ReactNode; // feedback controls, alternates
}) {
  const pick = topic.primary!;
  return (
    <li className={rowGrid}>
      <RowHead topic={topic} number={number} />
      <div className="col-start-2 mt-3 flex min-w-0 flex-col gap-3 md:col-start-3 md:mt-0">
        {continues ? (
          <button
            type="button"
            onClick={onPlay}
            className="flex items-center gap-2 text-left text-sm text-soft transition-colors hover:text-ink"
          >
            <ArrowBendDownRight size={16} className="shrink-0 text-accent-ink" aria-hidden />
            <span className="min-w-0 truncate">Same video, study</span>
            <span className="tabular font-mono text-xs text-accent-ink">{studyRange(pick.start_s, pick.end_s)}</span>
          </button>
        ) : (
          <div className="flex min-w-0 gap-3">
            <div className="relative w-28 shrink-0 sm:w-36">
              <Thumb video={pick.video} className={cx("w-full", pick.video.watched && "opacity-50")} />
              {pick.video.watched ? (
                <span className="absolute right-1.5 bottom-1.5 grid size-5 place-items-center rounded-full bg-accent text-on-accent">
                  <Check size={12} weight="bold" aria-label="Watched" />
                </span>
              ) : null}
              <PlayButton onPlay={onPlay} label={`Play ${pick.video.title}`} />
            </div>
            <div className="flex min-w-0 flex-col gap-1">
              <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">
                {pick.video.title}
              </p>
              <VideoMeta video={pick.video} startS={pick.start_s} endS={pick.end_s} />
              {pick.snippet ? (
                <p className="line-clamp-2 text-[13px] leading-relaxed text-soft">“{pick.snippet}”</p>
              ) : null}
              {pick.reasons[0] ? (
                <p className="line-clamp-1 text-[13px] text-faint">{pick.reasons[0]}</p>
              ) : null}
            </div>
          </div>
        )}
        {children}
      </div>
    </li>
  );
}

/** A topic no video covers. Said plainly, so the student knows to study it. */
export function GapRow({
  topic,
  number,
  children,
}: {
  topic: Topic;
  number: number;
  children?: ReactNode;
}) {
  return (
    <li className={rowGrid}>
      <RowHead topic={topic} number={number} />
      <div className="col-start-2 mt-3 flex min-w-0 flex-col gap-3 md:col-start-3 md:mt-0">
        <p className="flex items-start gap-2 rounded-field border border-warn/30 bg-warn-bg px-3 py-2.5 text-sm text-warn">
          <Warning size={17} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          <span>Video not found for “{topic.name}”. Study this one from your notes or textbook.</span>
        </p>
        {children}
      </div>
    </li>
  );
}

/** A topic the student marked as already known. */
export function KnownRow({
  topic,
  number,
  children,
}: {
  topic: Topic;
  number: number;
  children?: ReactNode;
}) {
  return (
    <li className={cx(rowGrid, "opacity-70")}>
      <RowHead topic={topic} number={number} />
      <div className="col-start-2 mt-3 flex min-w-0 flex-wrap items-center gap-3 md:col-start-3 md:mt-0">
        <span className="flex items-center gap-2 text-sm text-soft">
          <Check size={16} weight="bold" className="text-accent-ink" aria-hidden />
          You have this covered already
        </span>
        {children}
      </div>
    </li>
  );
}

/** A past exam question and where it is explained. */
export function QuestionCard({
  question,
  onPlay,
  className,
}: {
  question: Question;
  onPlay?: () => void;
  className?: string;
}) {
  const answer = question.answer;
  return (
    <Tilt className={cx("rounded-card border border-line bg-raised shadow-card", className)}>
    <article className="flex h-full flex-col gap-4 p-5">
      <Layer z={20} className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-1.5">
          <Chip>{question.source}</Chip>
          {question.topic_name ? <Chip tone="accent">{question.topic_name}</Chip> : null}
        </div>
        <p className="text-[15px] leading-relaxed text-ink">{question.text}</p>
      </Layer>
      {answer ? (
        <Layer z={42} className="mt-auto">
        <div className="flex gap-3 border-t border-line pt-4">
          <div className="relative w-28 shrink-0">
            <Thumb video={answer.video} className="w-full" />
            <PlayButton onPlay={onPlay} label={`Play the answer in ${answer.video.title}`} />
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <p className="flex items-center gap-1.5 text-[13px] text-soft">
              Study
              <span className="tabular font-mono text-xs text-accent-ink">
                {studyRange(answer.start_s, answer.end_s)}
              </span>
            </p>
            <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">
              {answer.video.title}
            </p>
            {answer.snippet ? (
              <p className="line-clamp-2 text-[13px] leading-relaxed text-faint">“{answer.snippet}”</p>
            ) : null}
          </div>
        </div>
        </Layer>
      ) : (
        <p className="mt-auto flex items-start gap-2 border-t border-line pt-4 text-sm text-warn">
          <Warning size={17} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          No video in your playlists explains this yet.
        </p>
      )}
    </article>
    </Tilt>
  );
}

/** One line of the "most important topics" ranking. */
export function FocusRow({
  topic,
  rank,
  onPlay,
}: {
  topic: Topic;
  rank: number;
  onPlay?: () => void;
}) {
  return (
    <li className="flex items-center gap-4 py-3.5">
      <span className="tabular w-7 shrink-0 font-mono text-xl font-medium text-faint">{rank}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <p className="truncate text-[15px] font-medium text-ink">{topic.name}</p>
        <TopicBadges topic={topic} />
      </div>
      {topic.status === "gap" ? (
        <Chip tone="warn">
          <Warning size={13} weight="fill" aria-hidden />
          No video
        </Chip>
      ) : topic.status === "covered" ? (
        <Chip>
          <Check size={13} weight="bold" aria-hidden />
          Known
        </Chip>
      ) : onPlay ? (
        <button
          type="button"
          onClick={onPlay}
          aria-label={`Play the video for ${topic.name}`}
          className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-on-accent transition-transform active:scale-95"
        >
          <Play size={15} weight="fill" aria-hidden />
        </button>
      ) : null}
    </li>
  );
}
