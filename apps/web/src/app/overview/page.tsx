"use client";

// Officer overview. The screen's question: "Which deposits need action today, and is every
// requirement covered?" The action list and the coverage card are the largest blocks.

import Link from "next/link";
import { useMemo } from "react";
import { BarList, BarsChart } from "@/components/Charts";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Case, Dashboard, InstrumentSummary, Notification } from "@/lib/types";

const STATUS_TILES = [
  { key: "active", state: "active" },
  { key: "expiring_90", state: "expiring" },
  { key: "matured", state: "matured" },
  { key: "renewed", state: "renewed" },
  { key: "released", state: "released" },
  { key: "pending_verification", state: "scrutiny" },
] as const;

function Actions({ dash }: { dash: Dashboard }) {
  const { t, money, date } = useI18n();
  const { has } = useAuth();
  const flagged = useResource<{ items: InstrumentSummary[]; total: number }>("/api/v1/instruments?flagged=true&limit=6");
  const overdue = useResource<{ items: InstrumentSummary[] }>("/api/v1/instruments?state=overdue&limit=6");
  const cases = useResource<{ items: Case[] }>("/api/v1/cases?state=open");
  const loading = flagged.loading || overdue.loading || cases.loading;
  const awaiting = (cases.data?.items ?? []).filter((c) => c.blockers.length === 0);

  type Row = { href: string; title: string; sub: string; tag: string; tone: string };
  const rows: Row[] = [
    ...(overdue.data?.items ?? []).map((i) => ({
      href: `/instruments/${i.id}`,
      title: i.institution?.name ?? i.instrument_no,
      sub: `${i.instrument_no} · ${money(i.amount)} · ${date(i.maturity_date)}`,
      tag: t("action.overdue"),
      tone: "neg",
    })),
    ...(flagged.data?.items ?? [])
      .filter((i) => i.state !== "overdue")
      .map((i) => ({
        href: `/instruments/${i.id}`,
        title: i.institution?.name ?? i.instrument_no,
        sub: `${i.instrument_no} · ${money(i.amount)} · ${t(`state.${i.state}`)}`,
        tag: `${t("col.flags")} ${i.open_flags}`,
        tone: "warn",
      })),
    ...awaiting.map((c) => ({
      href: `/cases/${c.id}`,
      title: c.instrument?.institution?.name ?? c.instrument_id,
      sub: `${t(`cases.type.${c.type}`)} · ${c.instrument?.instrument_no ?? ""}`,
      tag: t("action.awaitingDecision"),
      tone: "",
    })),
  ].slice(0, 6);

  return (
    <section className="panel span-7">
      <header>
        <h2>{t("overview.actions")}</h2>
        {has("scrutiny_officer", "verifying_officer") && dash.tiles.pending_verification > 0 && (
          <Link href="/queue" className="btn primary small">
            {t("action.reviewQueue")} · {dash.tiles.pending_verification}
          </Link>
        )}
      </header>
      {loading && !rows.length ? (
        <Loading rows={4} />
      ) : rows.length ? (
        <div className="rows">
          {rows.map((r) => (
            <Link key={r.href} href={r.href} className="row">
              <span className="grow">
                <span className="truncate" style={{ display: "block" }}>{r.title}</span>
                <span className="line2">{r.sub}</span>
              </span>
              <span className={`pill ${r.tone}`}>{r.tag}</span>
            </Link>
          ))}
        </div>
      ) : (
        <p className="empty">{t("overview.actions.none")}</p>
      )}
      {(flagged.data?.total ?? 0) > 6 && (
        <p style={{ marginTop: 12 }}>
          <Link className="card-link" href="/instruments?flagged=true">{t("common.viewAll")}</Link>
        </p>
      )}
    </section>
  );
}

function CoverageCard({ dash }: { dash: Dashboard }) {
  const { t, money, date } = useI18n();
  const c = dash.coverage;
  const required = Number(c.required);
  const share = required > 0 ? Number(c.attested) / required : 0;
  return (
    <section className="panel span-5">
      <header>
        <h2>{t("overview.coverage")}</h2>
        <span className="meta">{date(dash.today)}</span>
      </header>
      {required === 0 ? (
        <p className="empty">{t("overview.coverage.awaiting")}</p>
      ) : (
        <>
          <p className="kpi-label">{t("overview.coverage.attested")}</p>
          <p className="figure-lead num" style={{ color: "var(--hue)" }}>{money(c.attested)}</p>
          <p className="muted num" style={{ marginTop: 2 }}>
            {t("overview.coverage.required")} {money(c.required)} · {Math.round(share * 100)}%
          </p>
          <div style={{ height: 8, borderRadius: 999, background: "var(--raised)", marginTop: 12, position: "relative", overflow: "hidden" }} aria-hidden="true">
            <span style={{ position: "absolute", inset: 0, width: `${Math.min(100, (Number(c.declared) / required) * 100)}%`, background: "var(--chart-muted)" }} />
            <span style={{ position: "absolute", inset: 0, width: `${Math.min(100, share * 100)}%`, background: "var(--hue)" }} />
          </div>
          <div className="rows" style={{ marginTop: 12 }}>
            <div className="row">
              <span className="grow muted">{t("overview.coverage.declared")}</span>
              <span className="num">{money(c.declared)}</span>
            </div>
            <div className="row">
              <span className="grow muted">{t("overview.coverage.exposure")}</span>
              <span className="num" style={{ fontWeight: 700 }}>{money(c.exposure)}</span>
            </div>
          </div>
          <h3 style={{ fontSize: 14, fontWeight: 500, margin: "16px 0 4px" }}>{t("overview.coverage.gaps")}</h3>
          {dash.gaps.length ? (
            <div className="rows">
              {dash.gaps.slice(0, 4).map((g) => (
                <div className="row" key={g.institution.id}>
                  <span className="grow truncate">{g.institution.name}</span>
                  <span className="num" style={{ color: "var(--negative)" }}>{date(g.first_gap)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">{t("overview.coverage.noGaps")}</p>
          )}
        </>
      )}
    </section>
  );
}

function Maturities({ today }: { today: string }) {
  const { t, locale } = useI18n();
  const data = useResource<{ items: InstrumentSummary[] }>("/api/v1/instruments?state=active&state=expiring&limit=500");
  const series = useMemo(() => {
    const start = new Date(today);
    const labels: string[] = [];
    const values: number[] = [];
    for (let m = 0; m < 12; m++) {
      const d = new Date(start.getFullYear(), start.getMonth() + m, 1);
      labels.push(new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", { month: "short" }).format(d));
      values.push(
        (data.data?.items ?? []).filter((i) => {
          if (!i.maturity_date) return false;
          const md = new Date(i.maturity_date);
          return md.getFullYear() === d.getFullYear() && md.getMonth() === d.getMonth();
        }).length,
      );
    }
    return { labels, values };
  }, [data.data, today, locale]);
  return (
    <section className="panel span-7">
      <header>
        <h2>{t("overview.maturities")}</h2>
        <span className="meta">{t("overview.maturities.caption")}</span>
      </header>
      {data.loading && !data.data ? <Loading rows={2} height={60} /> : <BarsChart labels={series.labels} values={series.values} highlight={0} height={180} />}
    </section>
  );
}

function TrustCard({ dash }: { dash: Dashboard }) {
  const { t } = useI18n();
  const rows = [4, 3, 2, 1, 0].map((l) => ({ label: `L${l} ${t(`trust.${l}`)}`, value: dash.trust_distribution[String(l)] ?? 0 }));
  return (
    <section className="panel span-5">
      <header>
        <h2>{t("overview.trust")}</h2>
        <span className="meta">{t("overview.trust.caption")}</span>
      </header>
      <BarList rows={rows} />
    </section>
  );
}

function Alerts() {
  const { t, dateTime } = useI18n();
  const data = useResource<{ items: Notification[] }>("/api/v1/notifications");
  const items = (data.data?.items ?? []).slice(0, 5);
  return (
    <section className="panel span-12">
      <header>
        <h2>{t("overview.alerts")}</h2>
      </header>
      {data.loading && !data.data ? (
        <Loading rows={3} />
      ) : items.length ? (
        <div className="rows">
          {items.map((n) => (
            <Link className="row" key={n.id} href={`/instruments/${n.instrument_id}`}>
              <span className="grow">
                {t(`notify.${n.kind}`, undefined, n.kind)}
                <span className="line2">{n.message}</span>
              </span>
              <span className="muted small end">{dateTime(n.created_at)}</span>
            </Link>
          ))}
        </div>
      ) : (
        <p className="empty">{t("overview.alerts.none")}</p>
      )}
    </section>
  );
}

export default function OverviewPage() {
  return (
    <Shell roles={["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"]}>
      <Overview />
    </Shell>
  );
}

function Overview() {
  const { t, money, number } = useI18n();
  const dash = useResource<Dashboard>("/api/v1/dashboard");
  const d = dash.data;
  const critical = d?.tiles.critical ?? 0;

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("overview.title")}</h1>
          {d && (
            <p className="sub">
              {critical > 0
                ? t("overview.finding.critical", { n: critical, exposure: money(d.coverage.exposure) })
                : t("overview.finding.clear", { pending: d.tiles.pending_verification })}
            </p>
          )}
        </div>
      </div>
      {dash.error && <ErrorBox error={dash.error} onRetry={dash.reload} />}
      {!d && dash.loading && <Loading rows={6} height={28} />}
      {d && (
        <div className="grid top">
          <Actions dash={d} />
          <CoverageCard dash={d} />
          <section className="span-12 kpis" aria-label={t("overview.status")}>
            {STATUS_TILES.map((tile) => (
              <Link className="kpi" key={tile.key} href={`/instruments?state=${tile.state}`}>
                <span className="kpi-label" style={{ display: "block" }}>
                  {tile.key === "expiring_90" ? `${t("state.expiring")} · 90` : t(`state.${tile.state}`)}
                </span>
                <span className="kpi-value num" style={{ display: "block" }}>{number(d.tiles[tile.key] ?? 0)}</span>
              </Link>
            ))}
          </section>
          <Maturities today={d.today} />
          <TrustCard dash={d} />
          <Alerts />
        </div>
      )}
    </>
  );
}

