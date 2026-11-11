# Goal and Requirements

Back to [[Project Map]].

## The idea

Students use YouTube when lectures are not enough, but finding the right videos
for an exam syllabus by hand is slow. This product takes what a student already
has and returns an ordered list of videos that covers the syllabus.

**Inputs**

- One or more YouTube playlists (the pool of videos to choose from).
- The exam syllabus.
- The teacher's notes: PDFs, typed handouts, scans, photos of handwriting.
- Past exam papers.

**Outputs**

- An ordered learning path: each syllabus topic, in syllabus order, with the video
  that teaches it and the second at which that topic starts.
- A clear flag where no video covers a topic ("Video not found for ...").
- Search for any topic on demand.
- A feedback loop: Correct, Wrong topic, Already in my playlist / I know this,
  Irrelevant. Feedback changes the path and the matching threshold.

The original document is `idea.docx` in the project root (not in git).

## Requirements added by the owner during the build

These carry the same weight as the idea document.

1. Build it end to end without asking questions. Work only in the project folder.
   Save to the GitHub repository.
2. Production grade: advanced ML system design, robust CI/CD, scalable, deployable.
3. The interface must not look like generic AI output. Modern, with a real 3D look.
   See [[Frontend]].
4. Use the resources in the four `AI Agent Skills*.docx` link lists where useful
   (Three.js / React Three Fiber, GSAP, Lenis, Motion, Tailwind, shadcn/ui, the
   taste design skill).
5. Videos in any language must be supported.
6. Test extensively on real, free, public playlists.
7. Show the most important topics, and a question-and-answer section built from
   past papers.
8. Keep checkpoints and a progress file so the work can be resumed by anyone.
   See [[Progress]].

## What "done" means

- A student can sign up, add playlists and documents, press one button, and get a
  path that is right for a real playlist. Verified in a browser.
- Tests, the evaluation gate and the frontend build pass in CI.
- A Docker image runs the whole thing; a README explains how to deploy it.

## Related

[[Architecture]], [[Matching Pipeline]], [[Decisions]]
