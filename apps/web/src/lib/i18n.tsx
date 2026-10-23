"use client";

// English and Hindi. Text lives in src/i18n/*.json; codes from the API (states, flag
// types, event actions) are translated here by key, with the API's English as fallback.

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import en from "@/i18n/en.json";
import hi from "@/i18n/hi.json";

export type Locale = "en" | "hi";
const DICTS: Record<Locale, Record<string, string>> = { en, hi };
const STORAGE_KEY = "dt.locale";

type I18n = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>, fallback?: string) => string;
  money: (value: number | string | null | undefined) => string;
  number: (value: number | null | undefined, digits?: number) => string;
  percent: (value: number | null | undefined, digits?: number) => string;
  date: (iso: string | null | undefined) => string;
  dateTime: (iso: string | null | undefined) => string;
};

const I18nContext = createContext<I18n | null>(null);

// The chosen language lives in localStorage; the server and the first client render use English.
const listeners = new Set<() => void>();
function readLocale(): Locale {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(subscribe, readLocale, () => "en" as Locale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* storage blocked: the choice lasts until reload */
    }
    listeners.forEach((fn) => fn());
  }, []);

  const value = useMemo<I18n>(() => {
    const tag = locale === "hi" ? "hi-IN" : "en-IN";
    const dict = DICTS[locale];
    const t = (key: string, vars?: Record<string, string | number>, fallback?: string) => {
      let text = dict[key] ?? DICTS.en[key] ?? fallback ?? key;
      if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
      return text;
    };
    const nf = (o: Intl.NumberFormatOptions) => new Intl.NumberFormat(tag, o);
    return {
      locale,
      setLocale,
      t,
      money: (v) => {
        if (v === null || v === undefined || v === "") return "—";
        const n = typeof v === "string" ? Number(v) : v;
        return nf({ style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
      },
      number: (v, digits = 0) =>
        v === null || v === undefined ? "—" : nf({ maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v),
      percent: (v, digits = 0) =>
        v === null || v === undefined ? "—" : nf({ style: "percent", maximumFractionDigits: digits }).format(v),
      date: (iso) => (iso ? new Intl.DateTimeFormat(tag, { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso)) : "—"),
      dateTime: (iso) =>
        iso ? new Intl.DateTimeFormat(tag, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "—",
    };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
