import { useMutation } from "@tanstack/react-query";
import { type FormEvent, lazy, Suspense, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";

import { api, ApiError, IS_DEMO } from "../api";
import { DepthFloor } from "../depth";

const HeroScene = lazy(() => import("../scene/HeroScene"));
import { useSession, useSetSession } from "../session";
import { Button, Field, Logo, Notice, ThemeToggle } from "../ui";

export default function Auth({ mode }: { mode: "signin" | "signup" }) {
  const { user } = useSession();
  const setSession = useSetSession();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = (location.state as { from?: string } | null)?.from ?? "/app";

  // The static demo signs anyone in to its one sample course.
  const [name, setName] = useState(IS_DEMO ? "Demo student" : "");
  const [email, setEmail] = useState(IS_DEMO ? "demo@example.com" : "");
  const [password, setPassword] = useState(IS_DEMO ? "demo-password" : "");
  const signup = mode === "signup";

  const submit = useMutation({
    mutationFn: () =>
      signup ? api.register({ name, email, password }) : api.login({ email, password }),
    onSuccess: (account) => {
      setSession(account);
      navigate(destination, { replace: true });
    },
  });

  if (user) return <Navigate to={destination} replace />;

  const passwordTooShort = signup && password.length > 0 && password.length < 8;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!passwordTooShort) submit.mutate();
  }

  return (
    <div className="relative isolate flex min-h-[100dvh] flex-col">
      <DepthFloor />
      {/* The landing page's scene, beside the form on wide screens. */}
      <div
        aria-hidden
        className="absolute inset-y-0 right-0 -z-10 hidden w-[55%] [mask-image:linear-gradient(to_right,transparent,black_30%)] lg:block"
      >
        <Suspense fallback={null}>
          <HeroScene />
        </Suspense>
      </div>
      <header className="mx-auto flex h-16 w-full max-w-[1400px] items-center justify-between px-4 md:px-8">
        <Link to="/" aria-label="Waypoint home">
          <Logo />
        </Link>
        <ThemeToggle />
      </header>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 px-4 pb-24 lg:mr-auto lg:ml-[max(2rem,calc(50vw-36rem))]">
        <div className="flex flex-col gap-2">
          <h1 className="text-4xl font-semibold">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="text-soft">
            {signup
              ? "Your playlists, syllabus and progress are saved to it."
              : "Sign in to pick up your study path where you left it."}
          </p>
        </div>

        {IS_DEMO ? (
          <Notice>
            This is the live demo: it opens a real course (a Neso Academy playlist, a university
            syllabus and past paper, textbook chapters as reading) without a server. Browsing works;
            changes need your own copy.
          </Notice>
        ) : null}

        <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
          {signup ? (
            <Field
              label="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              required
            />
          ) : null}
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={signup ? "new-password" : "current-password"}
            hint={signup ? "At least 8 characters." : undefined}
            error={passwordTooShort ? "Use at least 8 characters." : undefined}
            required
          />
          {submit.error ? (
            <Notice tone="danger">
              {submit.error instanceof ApiError ? submit.error.message : "Something went wrong."}
            </Notice>
          ) : null}
          <Button
            type="submit"
            size="lg"
            busy={submit.isPending}
            disabled={!email || !password || (signup && !name.trim())}
          >
            {signup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="text-sm text-soft">
          {signup ? "Already have an account? " : "New here? "}
          <Link
            to={signup ? "/signin" : "/signup"}
            state={location.state}
            className="font-medium text-accent-ink underline-offset-4 hover:underline"
          >
            {signup ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </main>
    </div>
  );
}
