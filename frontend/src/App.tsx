import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";

import { Landing } from "./pages/Landing";
import { RequireAuth } from "./session";
import { Skeleton } from "./ui";

// The signed-in app is a separate download from the landing page.
const Auth = lazy(() => import("./pages/Auth"));
const Projects = lazy(() => import("./pages/Projects"));
const Workspace = lazy(() => import("./pages/Workspace"));

function PageFallback() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-16">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

export function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/signin" element={<Auth mode="signin" />} />
        <Route path="/signup" element={<Auth mode="signup" />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <Projects />
            </RequireAuth>
          }
        />
        <Route
          path="/app/p/:projectId"
          element={
            <RequireAuth>
              <Workspace />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
