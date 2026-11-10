import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { api, ApiError, type User } from "./api";
import { Skeleton } from "./ui";

/** The signed-in user, or null. A 401 is an answer ("nobody"), not an error. */
export function useSession() {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<User | null> => {
      try {
        return await api.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
  return { user: query.data ?? null, loading: query.isLoading };
}

export function useSetSession() {
  const client = useQueryClient();
  return (user: User | null) => {
    if (user === null) client.clear(); // signing out drops every cached project
    client.setQueryData(["me"], user);
  };
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  const location = useLocation();
  if (loading) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-16">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!user) return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
