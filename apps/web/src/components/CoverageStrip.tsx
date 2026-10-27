"use client";

// The coverage strip (N2), DepositTrack's signature element: how much of an institution's
// deposit requirement is covered on each day. Declared coverage is grey, bank-attested
// coverage carries the one hue, the requirement is a dashed reference line, today is a
// 1px ink line and the first forecast gap is marked in the negative colour.

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import type { Coverage } from "@/lib/types";

const H = 148;
const TOP = 18;
const BOTTOM = 22;
const LEFT = 56;

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * mag > v) return m * mag;
  return 10 * mag;
}

export function CoverageStrip({ coverage, today }: { coverage: Coverage; today: string }) {
  const { t, money, date } = useI18n();
  // Drawn at the figure's real width, so 11px text stays 11px at every size.
  const box = useRef<HTMLElement>(null);
  const [W, setW] = useState(720);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const segs = coverage.segments;
  if (!segs.length) return null;
  const start = new Date(segs[0].start).getTime();
  const end = new Date(segs[segs.length - 1].end).getTime() + 86_400_000;
  const required = Number(coverage.required);
  const top = niceMax(Math.max(required, ...segs.map((s) => Number(s.declared))) * 1.05);
  const x = (ms: number) => LEFT + ((ms - start) / (end - start)) * (W - LEFT);
  const y = (v: number) => TOP + (1 - v / top) * (H - TOP - BOTTOM);
  const baseline = y(0);

  const area = (key: "declared" | "attested") => {
    let d = `M${x(start)},${baseline}`;
    for (const s of segs) {
      const a = x(new Date(s.start).getTime());
      const b = x(new Date(s.end).getTime() + 86_400_000);
      const v = y(Number(s[key]));
      d += ` L${a},${v} L${b},${v}`;
    }
    return `${d} L${x(end)},${baseline} Z`;
  };

  const yearTicks: number[] = [];
  const first = new Date(start);
  for (let yr = first.getFullYear() + 1; ; yr++) {
    const ms = new Date(yr, 0, 1).getTime();
    if (ms >= end) break;
    yearTicks.push(ms);
  }
  const todayMs = new Date(today).getTime();
  const gapMs = coverage.first_gap ? new Date(coverage.first_gap).getTime() : null;

  return (
    <figure className="strip" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${t("overview.coverage.required")} ${money(required)}; ${t("overview.coverage.declared")} ${money(coverage.declared_today)}; ${t("overview.coverage.attested")} ${money(coverage.attested_today)}`}>
        {[0, top / 2, top].map((v) => (
          <g key={v}>
            <line x1={LEFT} x2={W} y1={y(v)} y2={y(v)} stroke="var(--grid)" strokeWidth={v === 0 ? 2 : 1} />
            <text x={LEFT - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--axis-ink)">
              {money(v)}
            </text>
          </g>
        ))}
        <path className="area" d={area("declared")} fill="var(--chart-muted)" />
        <path className="area" d={area("attested")} fill="var(--hue)" />
        <line x1={LEFT} x2={W} y1={y(required)} y2={y(required)} stroke="var(--text)" strokeWidth="1" strokeDasharray="4 3" />
        {yearTicks.map((ms) => (
          <text key={ms} x={x(ms)} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--axis-ink)">
            {new Date(ms).getFullYear()}
          </text>
        ))}
        {todayMs >= start && todayMs <= end && (
          <g>
            <line x1={x(todayMs)} x2={x(todayMs)} y1={TOP - 4} y2={baseline} stroke="var(--text)" strokeWidth="1" />
            <text x={x(todayMs) + 4} y={TOP - 6} fontSize="11" fill="var(--text)">{t("common.today")}</text>
          </g>
        )}
        {gapMs !== null && gapMs <= end && (
          <g>
            <line x1={x(gapMs)} x2={x(gapMs)} y1={TOP + 10} y2={baseline} stroke="var(--negative)" strokeWidth="1.5" />
            {/* A gap that starts today is labelled in words under the Today label, never on top of it. */}
            <text x={Math.min(x(gapMs) + 4, W - 140)} y={Math.abs(x(gapMs) - x(todayMs)) < 120 ? baseline - 8 : TOP + 8} fontSize="11" fill="var(--negative)">
              {gapMs <= todayMs ? t("coverage.gapNow") : t("coverage.gapFrom", { date: date(coverage.first_gap) })}
            </text>
          </g>
        )}
      </svg>
      <figcaption className="strip-legend">
        <span><i style={{ background: "var(--hue)" }} />{t("overview.coverage.attested")} {money(coverage.attested_today)}</span>
        <span><i style={{ background: "var(--chart-muted)" }} />{t("overview.coverage.declared")} {money(coverage.declared_today)}</span>
        <span><i style={{ borderTop: "1px dashed var(--text)", height: 0 }} />{t("overview.coverage.required")} {money(required)}</span>
      </figcaption>
    </figure>
  );
}
