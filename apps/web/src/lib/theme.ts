"use client";

// Light or dark, saved per browser (a convenience; the server never needs it).

import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "dt.theme";
const listeners = new Set<() => void>();

function read(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore(subscribe, read, () => "light" as Theme);
  const toggle = useCallback(() => {
    const next: Theme = read() === "dark" ? "light" : "dark";
    const apply = () => {
      document.documentElement.dataset.theme = next;
      listeners.forEach((fn) => fn());
    };
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* storage blocked: the choice lasts until reload */
    }
    // A cross-fade between themes where the browser supports it.
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) doc.startViewTransition(apply);
    else apply();
  }, []);
  return [theme, toggle];
}
