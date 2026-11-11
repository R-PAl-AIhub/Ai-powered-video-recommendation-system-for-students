/** Example data for the landing page previews.
 *
 *  These are real, public lectures from Neso Academy's "Operating System"
 *  playlist, with the matches this product actually produced for a university
 *  operating-systems syllabus. Nothing here is invented, including the gap:
 *  that playlist has no lecture on RAID. */
import type { Question, Recommendation, Topic, Video } from "./api";

function video(
  id: number,
  youtubeId: string,
  title: string,
  durationS: number,
  views: number,
  position: number,
): Video {
  return {
    id,
    youtube_id: youtubeId,
    title,
    channel: "Neso Academy",
    duration_s: durationS,
    view_count: views,
    like_count: null,
    thumbnail_url: `https://i.ytimg.com/vi/${youtubeId}/mqdefault.jpg`,
    playlist_id: 1,
    playlist_title: "Operating System",
    playlist_position: position,
    transcript_status: "ok",
    transcript_language: "en",
    source: "playlist",
    watched: false,
  };
}

function pick(
  v: Video,
  startS: number,
  reason: string,
  snippet: string,
  endS = 0,
): Recommendation {
  return {
    video: v,
    rank: 0,
    relevance: 0.97,
    quality: 0.9,
    score: 0.96,
    start_s: startS,
    end_s: endS,
    coverage_s: 300,
    snippet,
    reasons: [reason],
    url: `https://www.youtube.com/watch?v=${v.youtube_id}${startS ? `&t=${startS}s` : ""}`,
    feedback: null,
  };
}

export const sampleVideos = {
  intro: video(1, "vBURTt97EkA", "Introduction to Operating Systems", 1005, 4_200_000, 0),
  syscalls: video(2, "lhToWeuWWfw", "System Calls", 759, 996_000, 8),
  structures: video(3, "XXPBl20J22w", "Structures of Operating System", 1167, 826_000, 12),
  pcb: video(4, "4s2MKuVYKV8", "Process Control Block", 422, 701_000, 17),
  fcfs: video(5, "7DoP1L9nAAs", "Scheduling Algorithms - First Come First Served (FCFS)", 1020, 506_000, 39),
  roundRobin: video(6, "YzBBJYfwdi8", "Scheduling Algorithms - Round Robin Scheduling", 916, 354_000, 48),
  critical: video(7, "UtEORPakw5Y", "The Critical-Section Problem", 830, 472_000, 56),
  semaphores: video(8, "XDIOC2EY5JE", "Semaphores", 1371, 715_000, 59),
  dining: video(9, "FYUi-u7UWgw", "The Dining Philosophers Problem", 1216, 508_000, 63),
};

function topic(
  id: number,
  name: string,
  unit: string,
  primary: Recommendation | null,
  extra: Partial<Topic> = {},
): Topic {
  return {
    id,
    name,
    unit,
    position: id,
    source: "syllabus",
    status: primary ? "matched" : "gap",
    exam_hits: 0,
    exam_weight: 0,
    in_notes: false,
    notes_snippet: "",
    importance: 0,
    primary,
    alternates: [],
    ...extra,
  };
}

const v = sampleVideos;

export const samplePath: Topic[] = [
  topic(
    1,
    "Structure of an OS: Layered",
    "Unit 1: Introduction",
    pick(
      v.structures,
      163,
      "Spends about 4 min on this topic",
      "the next structure is the layered approach, where the operating system is broken into a number of layers",
    ),
  ),
  topic(
    2,
    "Structure of an OS: Monolithic",
    "Unit 1: Introduction",
    pick(
      v.structures,
      242,
      "Continues the video you are already watching",
      "in a monolithic structure all the functionality of the kernel is packed into one level",
    ),
  ),
  topic(
    3,
    "Scheduling algorithms: Round Robin",
    "Unit 3: CPU Scheduling",
    pick(
      v.roundRobin,
      0,
      "The title and the transcript both match this topic",
      "round robin scheduling is designed especially for time sharing systems, each process gets a small unit of CPU time",
    ),
    { exam_hits: 3, exam_weight: 1, importance: 1, in_notes: true },
  ),
  topic(
    4,
    "Semaphores",
    "Unit 4: Process Synchronization",
    pick(
      v.semaphores,
      0,
      "Spends about 9 min on this topic",
      "a semaphore is simply a variable which is non-negative and shared between threads",
    ),
    { exam_hits: 2, exam_weight: 0.67, importance: 0.75, in_notes: true },
  ),
  topic(5, "RAID levels", "Unit 7: Storage and File Systems", null, {
    exam_hits: 1,
    exam_weight: 0.33,
    importance: 0.25,
  }),
];

export const sampleFocus: Topic[] = [
  samplePath[2],
  samplePath[3],
  topic(
    6,
    "Dining philosophers problem",
    "Unit 4: Process Synchronization",
    pick(v.dining, 0, "The title and the transcript both match this topic", ""),
    { exam_hits: 2, exam_weight: 0.67, importance: 0.5 },
  ),
];

export const sampleQuestions: Question[] = [
  {
    id: 1,
    text: "What is a semaphore? Solve the bounded buffer problem using semaphores.",
    source: "End semester 2023",
    topic_id: 4,
    topic_name: "Semaphores",
    answer: {
      video: v.semaphores,
      relevance: 0.95,
      start_s: 0,
      end_s: 0,
      snippet: "a semaphore is simply a variable which is non-negative and shared between threads",
      url: `https://www.youtube.com/watch?v=${v.semaphores.youtube_id}`,
    },
  },
  {
    id: 2,
    text: "Calculate the average waiting time for the given processes using round robin with a time quantum of 2 ms.",
    source: "End semester 2022",
    topic_id: 3,
    topic_name: "Scheduling algorithms: Round Robin",
    answer: {
      video: v.roundRobin,
      relevance: 0.98,
      start_s: 579,
      end_s: 0,
      snippet: "now let us calculate the waiting time and the turnaround time for each of these processes",
      url: `https://www.youtube.com/watch?v=${v.roundRobin.youtube_id}&t=579s`,
    },
  },
  {
    id: 3,
    text: "Explain the critical section problem and the three requirements a solution must satisfy.",
    source: "Mid semester 2023",
    topic_id: 7,
    topic_name: "Critical section problem",
    answer: {
      video: v.critical,
      relevance: 0.96,
      start_s: 0,
      end_s: 0,
      snippet: "",
      url: `https://www.youtube.com/watch?v=${v.critical.youtube_id}`,
    },
  },
  {
    id: 4,
    text: "Compare RAID 0, RAID 1 and RAID 5 with respect to redundancy and performance.",
    source: "End semester 2023",
    topic_id: 5,
    topic_name: "RAID levels",
    answer: null,
  },
];

export const sampleThumbs = [v.intro, v.syscalls, v.pcb, v.fcfs, v.dining];
