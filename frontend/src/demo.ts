/** The static demo's stand-in for the server (GitHub Pages build, VITE_DEMO=1).
 *
 *  Every answer comes from `demo-data.json`: a real course exported from a real
 *  database by `backend/evaluation/export_demo.py` (a Neso Academy playlist, a
 *  university syllabus and past paper, OSTEP chapters and Wikipedia pages as
 *  study material). Reading works everywhere; anything that would change data
 *  needs the real server and says so. */
import { ApiError } from "./api";
import data from "./demo-data.json";

export const DEMO_EMAIL = "demo@example.com";
export const DEMO_PASSWORD = "demo-password";
export const READ_ONLY =
  "This is a read-only demo running without a server. Run your own copy (docker compose up) to add playlists, give feedback or change topics.";

const SESSION_KEY = "waypoint-demo-session";

function signedIn(): boolean {
  try {
    return window.sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function setSignedIn(value: boolean) {
  try {
    if (value) window.sessionStorage.setItem(SESSION_KEY, "1");
    else window.sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
}

const normalise = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function search(query: string) {
  const searches = data.searches as Record<string, unknown>;
  const wanted = normalise(query);
  const key = Object.keys(searches).find((k) => {
    const known = normalise(k);
    return known === wanted || wanted.includes(known) || known.includes(wanted);
  });
  if (key) return searches[key];
  return {
    query,
    found: false,
    message: `Search runs on the server. In this demo, try: ${Object.keys(searches).join(", ")}.`,
    results: [],
    closest: [],
  };
}

export async function demoRequest<T>(method: string, path: string): Promise<T> {
  // A short pause so loading states behave as they do against a server.
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const [route, queryString = ""] = path.split("?");
  const params = new URLSearchParams(queryString);
  const projectId = String(data.project.id);

  if (route === "/auth/me") {
    if (!signedIn()) throw new ApiError(401, "Not signed in");
    return data.user as T;
  }
  if (route === "/auth/login" || route === "/auth/register") {
    setSignedIn(true);
    return data.user as T;
  }
  if (route === "/auth/logout") {
    setSignedIn(false);
    return undefined as T;
  }
  if (!signedIn()) throw new ApiError(401, "Not signed in");
  if (method !== "GET") throw new ApiError(403, READ_ONLY);

  if (route === "/projects") return data.projects as T;
  const match = route.match(/^\/projects\/(\d+)(\/.*)?$/);
  if (!match || match[1] !== projectId) throw new ApiError(404, "Not found");
  switch (match[2] ?? "") {
    case "":
      return data.project as T;
    case "/path":
      return data.path as T;
    case "/questions":
      return data.questions as T;
    case "/topic-map":
      return data.topic_map as T;
    case "/job":
      return data.project.job as T;
    case "/search":
      return search(params.get("q") ?? "") as T;
    default:
      throw new ApiError(404, "Not found");
  }
}
