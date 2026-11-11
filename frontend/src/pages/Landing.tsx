import { ArrowRight, CheckCircle, GithubLogo, Prohibit, Swap, ThumbsUp } from "@phosphor-icons/react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { lazy, type ReactNode, Suspense, useRef, useState } from "react";
import { Link } from "react-router";

import { cx } from "../format";
import { sampleFocus, samplePath, sampleQuestions, sampleThumbs } from "../sample";
import { useSession } from "../session";
import { buttonClass, Logo, ThemeToggle } from "../ui";
import { FocusRow, GapRow, PathRow, QuestionCard, Thumb } from "./parts";

const HeroScene = lazy(() => import("../scene/HeroScene"));

const EASE = [0.16, 1, 0.3, 1] as const;

/** Fades and lifts its children into place the first time they scroll into view. */
function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.7, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

function useStartLink() {
  const { user } = useSession();
  return user
    ? { to: "/app", label: "Open your projects" }
    : { to: "/signup", label: "Start a study path" };
}

function Nav() {
  const { user } = useSession();
  const start = useStartLink();
  return (
    <header className="absolute inset-x-0 top-0 z-20">
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between gap-4 px-4 md:px-8">
        <Link to="/" aria-label="Waypoint home">
          <Logo />
        </Link>
        <div className="flex items-center gap-1 sm:gap-2">
          <a href="#how" className={buttonClass("quiet", "sm", "hidden sm:inline-flex")}>
            How it works
          </a>
          <ThemeToggle />
          {user ? null : (
            <Link to="/signin" className={buttonClass("quiet", "sm")}>
              Sign in
            </Link>
          )}
          <Link to={start.to} className={buttonClass("primary", "sm", "hidden sm:inline-flex")}>
            {start.label}
          </Link>
        </div>
      </nav>
    </header>
  );
}

function Hero() {
  const reduce = useReducedMotion();
  const start = useStartLink();
  const rise = (delay: number) => ({
    initial: reduce ? false : ({ opacity: 0, y: 24 } as const),
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.8, delay, ease: EASE },
  });
  return (
    <section className="relative isolate flex min-h-[100dvh] items-center overflow-hidden">
      {/* The scene sits behind the copy on phones and beside it on wide screens. */}
      <div
        className={cx(
          "absolute inset-0 -z-10 opacity-45 lg:left-[34%] lg:opacity-100",
          "[mask-image:linear-gradient(to_right,transparent,black_28%)]",
        )}
      >
        <Suspense fallback={null}>
          <HeroScene />
        </Suspense>
      </div>

      <div className="mx-auto w-full max-w-[1400px] px-4 pt-24 pb-16 md:px-8">
        <div className="flex max-w-[42rem] flex-col gap-7">
          <motion.h1
            {...rise(0.05)}
            className="text-5xl leading-[1.04] font-semibold md:text-6xl"
          >
            Your syllabus, turned into a watch list.
          </motion.h1>
          <motion.p {...rise(0.15)} className="max-w-[46ch] text-lg leading-relaxed text-soft">
            Paste your playlists and syllabus. Waypoint matches every topic to the exact minute a
            video teaches it, in exam order.
          </motion.p>
          <motion.div {...rise(0.25)} className="flex flex-wrap items-center gap-3">
            <Link to={start.to} className={buttonClass("primary", "lg")}>
              {start.label}
              <ArrowRight size={18} weight="bold" aria-hidden />
            </Link>
            <a href="#how" className={buttonClass("outline", "lg")}>
              See it work
            </a>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

const TOPIC_NAMES = [
  "Process states",
  "Context switching",
  "Round Robin",
  "Semaphores",
  "Banker's algorithm",
  "Demand paging",
  "RAID levels",
];

/** What goes in: three kinds of input, three differently built cells. */
function Inputs() {
  return (
    <section className="mx-auto max-w-[1400px] px-4 py-20 md:px-8 md:py-28">
      <Reveal>
        <h2 className="max-w-2xl text-4xl leading-[1.05] font-semibold md:text-5xl">
          Give it what you already have.
        </h2>
      </Reveal>

      <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-5">
        <Reveal className="lg:col-span-3">
          <div className="flex h-full flex-col justify-between gap-10 overflow-hidden rounded-card border border-line bg-raised p-6 md:p-8">
            <div className="perspective-scene flex justify-center py-4">
              {/* Thumbnails fanned like cards held in a hand. */}
              <div className="preserve-3d flex -space-x-10 md:-space-x-14">
                {sampleThumbs.slice(0, 4).map((video, index) => (
                  <div
                    key={video.id}
                    style={{
                      transform: `rotateY(${-28 + index * 6}deg) translateZ(${index * 26}px)`,
                    }}
                  >
                    <Thumb video={video} className="w-36 shadow-card md:w-52" />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex max-w-[52ch] flex-col gap-2">
              <h3 className="text-2xl font-semibold">Your playlists</h3>
              <p className="leading-relaxed text-soft">
                Any YouTube playlists. Waypoint reads what is said in each video, not only its
                title.
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.08} className="lg:col-span-2">
          <div className="flex h-full flex-col justify-between gap-10 rounded-card bg-accent p-6 text-on-accent md:p-8">
            <ul className="flex flex-wrap gap-2">
              {TOPIC_NAMES.map((name) => (
                <li
                  key={name}
                  className="rounded-full border border-on-accent/25 px-3 py-1.5 text-sm font-medium"
                >
                  {name}
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2">
              <h3 className="text-2xl font-semibold">Your syllabus and notes</h3>
              <p className="leading-relaxed text-on-accent/75">
                PDFs, Word files, or photos of handwritten pages. Scans are read with OCR and turned
                into an ordered topic list you can edit.
              </p>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.05} className="lg:col-span-5">
          <div className="grid grid-cols-1 items-center gap-8 rounded-card border border-line bg-sunken p-6 md:grid-cols-2 md:p-8">
            <div className="flex max-w-[48ch] flex-col gap-2">
              <h3 className="text-2xl font-semibold">Your past papers</h3>
              <p className="leading-relaxed text-soft">
                Every question is counted against its topic, so the topics examiners keep returning
                to rise to the top of your list.
              </p>
            </div>
            <ol className="divide-y divide-line">
              {sampleFocus.map((topic, index) => (
                <FocusRow key={topic.id} topic={topic} rank={index + 1} />
              ))}
            </ol>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/** The real path component with real matches, tilting flat as it scrolls into view. */
function PathPreview() {
  const frame = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: frame, offset: ["start end", "center center"] });
  const rotateX = useTransform(scrollYProgress, [0, 1], [22, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [0.92, 1]);

  return (
    <section id="how" className="scroll-mt-8 px-4 py-20 md:px-8 md:py-28">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-12">
        <Reveal className="flex max-w-2xl flex-col gap-4">
          <h2 className="text-4xl leading-[1.05] font-semibold md:text-5xl">
            One path, in the order your exam expects.
          </h2>
          <p className="max-w-[60ch] text-lg leading-relaxed text-soft">
            Topics follow your syllabus. Videos stay in one playlist where they can, and open at the
            minute the topic begins. These are real matches from a real playlist.
          </p>
        </Reveal>

        <div ref={frame} className="perspective-scene">
          <motion.div
            style={reduce ? undefined : { rotateX, scale, transformOrigin: "50% 0%" }}
            className="mx-auto max-w-5xl rounded-card border border-line bg-raised px-4 shadow-card md:px-8"
          >
            <ol className="divide-y divide-line">
              {samplePath.map((topic, index) =>
                topic.primary ? (
                  <PathRow
                    key={topic.id}
                    topic={topic}
                    number={index + 1}
                    continues={
                      index > 0 && samplePath[index - 1].primary?.video.id === topic.primary.video.id
                    }
                  />
                ) : (
                  <GapRow key={topic.id} topic={topic} number={index + 1} />
                ),
              )}
            </ol>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

const FEEDBACK = [
  {
    key: "correct",
    label: "Correct",
    icon: ThumbsUp,
    effect: "Pinned. This video stays on this topic, whatever else changes.",
  },
  {
    key: "wrong",
    label: "Wrong topic",
    icon: Swap,
    effect: "Removed from this topic. The next best video takes its place.",
  },
  {
    key: "known",
    label: "I know this",
    icon: CheckCircle,
    effect: "Topic taken off your path. Your remaining watch time drops.",
  },
  {
    key: "irrelevant",
    label: "Irrelevant",
    icon: Prohibit,
    effect: "Video removed from the whole course, and matching gets stricter.",
  },
] as const;

/** Feedback, as something to press rather than something to read about. */
function Feedback() {
  const [choice, setChoice] = useState<(typeof FEEDBACK)[number]["key"]>("correct");
  const active = FEEDBACK.find((item) => item.key === choice)!;
  return (
    <section className="mx-auto max-w-[1400px] px-4 py-20 md:px-8 md:py-28">
      <Reveal className="mx-auto flex max-w-3xl flex-col items-center gap-4 text-center">
        <h2 className="text-4xl leading-[1.05] font-semibold md:text-5xl">
          Tell it when it is wrong.
        </h2>
        <p className="max-w-[56ch] text-lg leading-relaxed text-soft">
          One tap on any pick and the whole path is planned again in under a second.
        </p>
      </Reveal>

      <Reveal delay={0.1} className="mx-auto mt-10 flex max-w-2xl flex-col items-center gap-5">
        <div role="group" aria-label="Feedback options" className="flex flex-wrap justify-center gap-2">
          {FEEDBACK.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setChoice(key)}
              aria-pressed={choice === key}
              className={buttonClass(choice === key ? "primary" : "outline", "md")}
            >
              <Icon size={17} weight={choice === key ? "fill" : "regular"} aria-hidden />
              {label}
            </button>
          ))}
        </div>
        <motion.p
          key={active.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE }}
          aria-live="polite"
          className="text-center text-lg text-ink"
        >
          {active.effect}
        </motion.p>
      </Reveal>
    </section>
  );
}

/** Past questions, each with the video moment that answers it. */
function Questions() {
  return (
    <section className="py-20 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <Reveal className="flex max-w-2xl flex-col gap-4">
          <h2 className="text-4xl leading-[1.05] font-semibold md:text-5xl">
            Past papers, answered on video.
          </h2>
          <p className="max-w-[58ch] text-lg leading-relaxed text-soft">
            Upload old question papers and each question gets a link to the moment it is explained.
            Questions nobody explains are flagged too.
          </p>
        </Reveal>
      </div>
      <Reveal delay={0.1}>
        <ul className="scrollbar-none mt-12 flex snap-x snap-mandatory gap-5 overflow-x-auto px-4 pb-4 md:px-8">
          {sampleQuestions.map((question) => (
            <li key={question.id} className="w-[min(86vw,24rem)] shrink-0 snap-start">
              <QuestionCard question={question} className="h-full" />
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  );
}

function Closing() {
  const start = useStartLink();
  return (
    <section className="px-4 py-24 md:px-8 md:py-36">
      <Reveal className="mx-auto flex max-w-[1400px] flex-col items-start gap-8">
        <h2 className="max-w-4xl text-5xl leading-[1.02] font-semibold md:text-7xl">
          Exam in three weeks? Start tonight.
        </h2>
        <Link to={start.to} className={buttonClass("primary", "lg")}>
          {start.label}
          <ArrowRight size={18} weight="bold" aria-hidden />
        </Link>
      </Reveal>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-faint md:px-8">
        <Logo className="text-ink" />
        <p>Links to public YouTube videos. Nothing is downloaded or re-hosted.</p>
        <a
          href="https://github.com/R-PAl-AIhub/Ai-powered-video-recommendation-system-for-students"
          className="inline-flex items-center gap-2 transition-colors hover:text-ink"
        >
          <GithubLogo size={18} aria-hidden />
          Source code
        </a>
      </div>
    </footer>
  );
}

export function Landing() {
  return (
    <div className="overflow-x-clip">
      <Nav />
      <main>
        <Hero />
        <Inputs />
        <PathPreview />
        <Feedback />
        <Questions />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
