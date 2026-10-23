"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "./auth";
import { config } from "./config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
}

export type Fetcher = <T>(path: string, init?: RequestInit) => Promise<T>;

async function request<T>(token: string | null, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${config.apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? body;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, detail);
  }
  const type = response.headers.get("Content-Type") ?? "";
  if (type.includes("application/json")) return (await response.json()) as T;
  return (await response.blob()) as T;
}

export function useApi(): Fetcher {
  const { token } = useAuth();
  return useCallback(<T,>(path: string, init?: RequestInit) => request<T>(token, path, init), [token]);
}

/** Load JSON for a screen; `reload()` refetches. Keeps old data while refreshing. */
export function useResource<T>(path: string | null) {
  const api = useApi();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [tick, setTick] = useState(0);
  const [settled, setSettled] = useState<string | null>(null);
  const key = path ? `${path}#${tick}` : null;

  useEffect(() => {
    if (!path || !key) return;
    let alive = true;
    api<T>(path)
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setSettled(key));
    return () => {
      alive = false;
    };
  }, [api, path, key]);

  return { data, error, loading: key !== null && settled !== key, reload: () => setTick((t) => t + 1) };
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { message?: string; blockers?: string[] } | string;
    if (typeof d === "string") return d;
    if (d?.message) return d.blockers?.length ? `${d.message}: ${d.blockers.join("; ")}` : d.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export async function download(token: string | null, path: string, filename: string) {
  const blob = await request<Blob>(token, path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
