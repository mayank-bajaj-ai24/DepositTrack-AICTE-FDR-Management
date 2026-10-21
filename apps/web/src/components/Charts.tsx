"use client";

// Thin React wrappers over taste-skill's charts.js (public/charts.js, loaded once).

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";

type ChartsLib = {
  bars: (el: HTMLElement, opts: Record<string, unknown>) => unknown;
  barList: (el: HTMLElement, rows: { label: string; value: number }[], opts?: Record<string, unknown>) => unknown;
};

declare global {
  interface Window {
    Charts?: ChartsLib;
  }
}

function useCharts(): ChartsLib | null {
  const [lib, setLib] = useState<ChartsLib | null>(() => (typeof window !== "undefined" ? (window.Charts ?? null) : null));
  useEffect(() => {
    if (lib) return;
    const id = window.setInterval(() => {
      if (window.Charts) {
        setLib(window.Charts);
        window.clearInterval(id);
      }
    }, 50);
    return () => window.clearInterval(id);
  }, [lib]);
  return lib;
}

export function BarsChart({ labels, values, highlight, height = 180 }: { labels: string[]; values: number[]; highlight?: number; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const lib = useCharts();
  const { locale } = useI18n();
  useEffect(() => {
    if (!lib || !ref.current) return;
    ref.current.innerHTML = "";
    lib.bars(ref.current, { labels, values, highlight, height });
  }, [lib, labels, values, highlight, height, locale]);
  return <div className="chart" ref={ref} style={{ minHeight: height }} />;
}

export function BarList({ rows }: { rows: { label: string; value: number }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const lib = useCharts();
  const { locale } = useI18n();
  useEffect(() => {
    if (!lib || !ref.current) return;
    ref.current.innerHTML = "";
    lib.barList(ref.current, rows, { thin: true });
  }, [lib, rows, locale]);
  return <div className="chart" ref={ref} />;
}
