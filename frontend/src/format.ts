/** 754 -> "12:34", 4000 -> "1:06:40". */
export function clock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** 5400 -> "1 h 30 min", 1500 -> "25 min". */
export function span(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/** 4200000 -> "4.2M". */
export function compact(value: number | null): string {
  if (value === null) return "";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "in 28 min", "at 14:05" for a planned retry time. */
export function until(iso: string): string {
  const then = new Date(iso);
  const minutes = Math.round((then.getTime() - Date.now()) / 60000);
  if (minutes <= 1) return "in a moment";
  if (minutes < 90) return `in about ${minutes} min`;
  return `at ${then.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

/** The embeddable player address for a video, starting at a given second. */
export function embedUrl(youtubeId: string, startSeconds: number, endSeconds = 0): string {
  const params = new URLSearchParams({ rel: "0", modestbranding: "1", autoplay: "1" });
  if (startSeconds >= 1) params.set("start", String(Math.floor(startSeconds)));
  if (endSeconds > startSeconds) params.set("end", String(Math.ceil(endSeconds)));
  return `https://www.youtube-nocookie.com/embed/${youtubeId}?${params}`;
}

/** What to watch: "2:43 to 6:10", "2:43 to the end", or "the whole video". */
export function studyRange(startS: number, endS: number): string {
  if (startS < 1 && endS <= 0) return "the whole video";
  const from = startS >= 1 ? clock(startS) : "0:00";
  return endS > startS ? `${from} to ${clock(endS)}` : `${from} to the end`;
}

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
