import { FolderSimplePlus, Plus, SignOut, Trash } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router";

import { api, ApiError, type ProjectSummary } from "../api";
import { DepthFloor, Layer, Tilt } from "../depth";
import { plural } from "../format";
import { useSession, useSetSession } from "../session";
import {
  Button,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  Logo,
  Notice,
  Skeleton,
  ThemeToggle,
} from "../ui";

/** Top bar shared by the signed-in screens. */
export function AppBar({ children }: { children?: ReactNode }) {
  const { user } = useSession();
  const setSession = useSetSession();
  const navigate = useNavigate();
  const signOut = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      setSession(null);
      navigate("/", { replace: true });
    },
  });
  return (
    <>
      {/* Outside the header: its backdrop blur would trap a fixed element. */}
      <DepthFloor />
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 md:px-6">
        <div className="flex min-w-0 items-center gap-4">
          <Link to="/app" aria-label="Your projects" className="shrink-0">
            <Logo />
          </Link>
          {children}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span className="mr-2 hidden max-w-40 truncate text-sm text-soft sm:block">{user?.name}</span>
          <ThemeToggle />
          <IconButton label="Sign out" onClick={() => signOut.mutate()}>
            <SignOut size={18} />
          </IconButton>
        </div>
      </div>
      </header>
    </>
  );
}

function ProjectCard({ project, onDelete }: { project: ProjectSummary; onDelete: () => void }) {
  const done = project.matched + project.covered;
  const running = project.job?.status === "queued" || project.job?.status === "running";
  return (
    <li className="group relative">
      <Tilt className="h-full rounded-card border border-line bg-raised shadow-card transition-colors duration-200 hover:border-line-strong">
      <Link to={`/app/p/${project.id}`} className="flex h-full flex-col gap-6 rounded-card p-6">
        <Layer z={34} className="flex flex-col gap-1 pr-10">
          <h2 className="truncate text-xl font-semibold">{project.name}</h2>
          <p className="truncate text-sm text-soft">{project.subject || "No subject set"}</p>
        </Layer>
        {project.topics > 0 ? (
          <Layer z={18} className="mt-auto">
          <dl className="grid grid-cols-3 gap-4">
            <div>
              <dt className="text-xs text-faint">Topics matched</dt>
              <dd className="tabular mt-1 font-mono text-lg">
                {done}
                <span className="text-faint">/{project.topics}</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Gaps</dt>
              <dd className={`tabular mt-1 font-mono text-lg ${project.gaps ? "text-warn" : ""}`}>
                {project.gaps}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Watched</dt>
              <dd className="tabular mt-1 font-mono text-lg">{project.watched}</dd>
            </div>
          </dl>
          </Layer>
        ) : (
          <p className="mt-auto text-sm text-faint">
            {running ? "Analysing your sources…" : "Add playlists and a syllabus to begin."}
          </p>
        )}
      </Link>
      <IconButton
        label={`Delete ${project.name}`}
        onClick={onDelete}
        className="absolute top-4 right-4 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      >
        <Trash size={17} />
      </IconButton>
      </Tilt>
    </li>
  );
}

export default function Projects() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [creating, setCreating] = useState(false);
  const [doomed, setDoomed] = useState<ProjectSummary | null>(null);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");

  const create = useMutation({
    mutationFn: () => api.createProject({ name: name.trim(), subject: subject.trim() }),
    onSuccess: (project) => {
      client.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/app/p/${project.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: () => {
      setDoomed(null);
      client.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  function onCreate(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) create.mutate();
  }

  const newButton = (
    <Button icon={<Plus size={17} weight="bold" />} onClick={() => setCreating(true)}>
      New course
    </Button>
  );

  return (
    <div className="min-h-[100dvh]">
      <AppBar />
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 md:px-6 md:py-14">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-4xl font-semibold">Your courses</h1>
            <p className="text-soft">One project per subject you are studying for.</p>
          </div>
          {projects.data?.length ? newButton : null}
        </div>

        {projects.isLoading ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <Skeleton className="h-44 rounded-card" />
            <Skeleton className="h-44 rounded-card" />
          </div>
        ) : projects.error ? (
          <Notice tone="danger">Your courses could not be loaded. Refresh the page to try again.</Notice>
        ) : projects.data!.length === 0 ? (
          <EmptyState
            icon={<FolderSimplePlus size={22} />}
            title="Start with one course"
            action={newButton}
          >
            Create a project for a subject, then add its playlists and syllabus. Your study path is
            built from those.
          </EmptyState>
        ) : (
          <ul className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {projects.data!.map((project) => (
              <ProjectCard key={project.id} project={project} onDelete={() => setDoomed(project)} />
            ))}
          </ul>
        )}
      </main>

      <Dialog open={creating} onClose={() => setCreating(false)} title="New course">
        <form onSubmit={onCreate} className="flex flex-col gap-5">
          <Field
            label="Course name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Operating Systems, 5th semester"
            maxLength={160}
            autoFocus
            required
          />
          <Field
            label="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Operating Systems"
            hint="Used to spell out abbreviations in your syllabus, such as OS."
            maxLength={160}
          />
          {create.error ? (
            <Notice tone="danger">
              {create.error instanceof ApiError ? create.error.message : "Could not create the course."}
            </Notice>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="quiet" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" busy={create.isPending} disabled={!name.trim()}>
              Create course
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog open={doomed !== null} onClose={() => setDoomed(null)} title="Delete this course?">
        <div className="flex flex-col gap-5">
          <p className="leading-relaxed text-soft">
            “{doomed?.name}” will be deleted with its {plural(doomed?.topics ?? 0, "topic")},
            documents and progress. This cannot be undone.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="quiet" onClick={() => setDoomed(null)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              busy={remove.isPending}
              onClick={() => doomed && remove.mutate(doomed.id)}
            >
              Delete course
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
