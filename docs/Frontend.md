# Frontend

Back to [[Project Map]]. React 19, Vite 7, TypeScript, Tailwind CSS v4, Motion,
React Three Fiber. In the interface the product is called **Waypoint**.

## Design decisions (keep these consistent)

The owner's standard: it must not look like generic AI output, and it must have a
real 3D look. The taste design skill (`anthropic-skills:design-taste-frontend`) was
applied; load it again before any visual work.

- **Design read:** a study tool for university students; dark, spatial, confident.
  Variance 8, motion 7, density 4.
- **Colour:** one accent, volt lime `#c8f542`, on cool off-black and off-white.
  Amber only for "no video found". No purple, no gradient text, no glow.
- **Type:** Geist and Geist Mono, self-hosted via `@fontsource-variable`.
- **Shape:** buttons and chips are pills, cards 20px, fields 12px. Everywhere.
- **Icons:** `@phosphor-icons/react` only. **Motion:** `motion/react` only.
- **Copy:** plain and specific. No em-dashes anywhere visible. One label per action
  ("Start a study path").
- **3D with a reason:** the hero scene is the product's idea as an object (see below),
  not decoration. The path preview tilts flat as it scrolls into view.
- **No fake screenshots:** the landing page renders the app's real components with
  real sample data (`src/sample.ts`, taken from a real playlist run).
- Both themes, following the system unless the student chooses. Reduced motion is
  honoured. The server's Content-Security-Policy forbids inline scripts, so the
  theme script is a file (`public/theme.js`).

## The 3D scene (`src/scene/HeroScene.tsx`)

Video slabs float in depth along a glowing line, which is the learning path. The
slabs are dark "screens" (`--screen` in `styles.css`) in both themes; with the page
colour they disappeared into a light background. One
slab is only a dashed amber outline: a syllabus topic no video covers. A light
travels the line like a student moving through it. The whole thing leans toward
the pointer. It is lazy-loaded (three.js is about 180 kB gzipped and only the
landing page needs it), static under reduced motion, and simply absent if WebGL
is unavailable.

## Depth across the whole site (`src/depth.tsx`)

The owner asked for the whole site, not only the hero, to have a 3D look.

- **`Tilt` and `Layer`:** cards lean toward the pointer (spring-driven Motion
  values, no React re-renders) with a moving sheen; `Layer` lifts content above the
  card (titles about 20 to 34px, the answering video in question cards 42px). Used on
  course cards, question cards and the landing bento cells. Off on touch screens and
  under reduced motion, where cards render flat and identical.
- **`DepthFloor`:** a perspective grid plane fixed at the bottom of every signed-in
  page and the sign-in page. Pure CSS (`.depth-floor` in `styles.css`). Rendered by
  `AppBar` as a sibling of the header, because the header's backdrop blur would
  trap a fixed element.
- **Coverflow:** the landing page's question cards turn like a coverflow as they
  scroll past the centre (`.coverflow`, CSS scroll-driven animation; flat where
  unsupported or under reduced motion).
- **Sign-in page:** the hero's 3D scene sits beside the form on wide screens.

Note for whoever tests this: Windows with "Animation effects" off reports
`prefers-reduced-motion: reduce`, so all motion stays still. The owner's machine
had this setting on 2026-11-11. To test motion in Chrome DevTools, override
`matchMedia` with an init script.

## Files (`frontend/src/`)

| File | Purpose |
|---|---|
| `main.tsx`, `App.tsx` | Providers and routes |
| `styles.css` | Tailwind and the design tokens for both themes |
| `api.ts` | Typed client for every endpoint |
| `session.tsx` | Current user, sign-in guard |
| `ui.tsx` | Button, Field, Chip, Card, Notice, Dialog, ThemeToggle, Logo |
| `format.ts` | Time, numbers, class names |
| `depth.tsx` | `Tilt`, `Layer`, `DepthFloor`: the 3D look outside the hero |
| `sample.ts` | Real sample data for the landing page |
| `scene/HeroScene.tsx` | The 3D hero |
| `pages/parts.tsx` | PathRow, GapRow, KnownRow, QuestionCard, FocusRow (shared with the landing page); `Readings`: where to read about a topic (document, pages, § heading, deep link for web pages). On a gap row the reading is the main suggestion with its excerpt; on a matched row it is an "Also read" list |
| `pages/Landing.tsx` | Hero, inputs bento, live path preview, feedback demo, questions, closing |
| `pages/Auth.tsx`, `Projects.tsx` | Sign in and up; course list |
| `pages/Workspace.tsx` | Course shell, tabs, job progress, Sources tab (playlists, documents, and "Study material": web page or online PDF by address, book/article upload, paste), player |
| `pages/PathTab.tsx` | The learning path (each entry shows "study 2:43 to 6:10" and a transcript excerpt; the player stops at the end), feedback with an undo bar ("Already in my playlist" marks a topic covered), alternates, gap filling from YouTube. `TranscriptPaste`: on a pick whose video was matched on its title only (captions refused, none, or unreadable language) a dashed note says why and opens a box to paste the transcript copied from YouTube; `UntranscribedVideos` lists every such video under the playlists in the Sources tab |
| `pages/MoreTabs.tsx` | Focus (most important topics, plus the LDA "What your playlists cover" map), Questions, Search, Topics (with "Order like my playlists") |

## Routes

`/` landing, `/signin`, `/signup`, `/app` courses, `/app/p/:projectId?tab=sources|path|focus|questions|search|topics`.

## Run it

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to 127.0.0.1:8000
npm run build    # type-check and build into dist/, which the backend serves
```

## Status

Type-check and production build pass. The landing hero has been checked in a
browser; the rest is in progress, see [[Progress]].

Browser tools: the Claude-in-Chrome extension may be disconnected; the Chrome
DevTools MCP tools (`mcp__plugin_ecc_chrome-devtools__*`) work. Full-page
screenshots of the WebGL page can hang; viewport screenshots work.

## Related

[[Goal and Requirements]], [[Decisions]]
