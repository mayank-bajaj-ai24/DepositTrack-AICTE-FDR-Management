"use client";

// Institution home: "Is my deposit requirement covered, and what do I need to do?"

import Link from "next/link";
import { ViewTransition } from "react";
import { CoverageStrip } from "@/components/CoverageStrip";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, StatePill, TrustLadder } from "@/components/ui";
import { groupAlerts, useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Case, Coverage, InstrumentSummary, Me, Notification } from "@/lib/types";

function Home() {
  const { t, money, date, dateTime } = useI18n();
  // The account's own institution, from /me: the institution list also holds an officer's region.
  const me = useResource<Me>("/api/v1/me");
  const list = useResource<{ total: number; items: InstrumentSummary[] }>("/api/v1/instruments?limit=200");
  const cov = useResource<{ today: string; items: { coverage: Coverage; basis_ref: string }[] }>("/api/v1/coverage");
  const alerts = useResource<{ items: Notification[] }>("/api/v1/notifications");
  const cases = useResource<{ items: Case[] }>("/api/v1/cases?state=open");
  const name = me.data?.institution?.name ?? "";
  const reminders = groupAlerts(alerts.data?.items ?? []);
  const needsRenewal = (list.data?.items ?? []).filter((i) => i.state === "expiring" || i.state === "overdue");

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("my.title")}</h1>
          <p className="sub">{name ? t("my.sub", { institution: name }) : "\u00a0"}</p>
        </div>
        <div className="actions">
          <Link className="btn primary" href="/my/submit">{t("nav.submit")}</Link>
        </div>
      </div>
      {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
      <div className="grid top">
        <section className="panel span-12">
          <header>
            <h2>{t("my.requirement")}</h2>
            {cov.data?.items[0] && <span className="meta">{cov.data.items[0].basis_ref}</span>}
          </header>
          {!cov.data ? (
            <Loading rows={2} height={40} />
          ) : cov.data.items.length === 0 ? (
            <p className="empty">{t("overview.coverage.awaiting")}</p>
          ) : (
            cov.data.items.map((c) => <CoverageStrip key={c.coverage.obligation_id} coverage={c.coverage} today={cov.data!.today} />)
          )}
        </section>

        <section className="panel flush span-8">
          <header>
            <h2>{t("my.list")}</h2>
            <span className="meta">{t("common.total", { n: list.data?.total ?? 0 })}</span>
          </header>
          {!list.data ? (
            <div style={{ padding: 20 }}><Loading rows={4} /></div>
          ) : list.data.items.length === 0 ? (
            <div style={{ padding: 20 }}><p className="empty">{t("my.empty")}</p></div>
          ) : (
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table className="responsive">
                <thead>
                  <tr>
                    <th>{t("col.fdr")}</th>
                    <th className="n">{t("col.amount")}</th>
                    <th className="n hide-sm">{t("col.maturity")}</th>
                    <th>{t("col.state")}</th>
                    <th className="hide-sm">{t("col.trust")}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <Link className="mono" href={`/instruments/${i.id}`}>
                          <ViewTransition name={`fdr-${i.id}`} share="morph" default="none">
                            <span>{i.instrument_no}</span>
                          </ViewTransition>
                        </Link>
                        <span className="sub">{i.bank_name}</span>
                      </td>
                      <td className="n num">{money(i.amount)}</td>
                      <td className="n num hide-sm">{date(i.maturity_date)}</td>
                      <td><StatePill state={i.state} /></td>
                      <td className="hide-sm"><TrustLadder level={i.trust_level} label={false} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="span-4 stack">
          {needsRenewal.length > 0 && (
            <section className="panel">
              <header><h2>{t("detail.submitRenewal")}</h2></header>
              <div className="rows">
                {needsRenewal.map((i) => (
                  <div className="row" key={i.id}>
                    <span className="grow">
                      <span className="mono">{i.instrument_no}</span>
                      <span className="line2">{t("col.maturity")} {date(i.maturity_date)}</span>
                    </span>
                    <Link className="btn small" href={`/my/submit?replaces=${i.id}`}>{t("detail.submitRenewal")}</Link>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section className="panel">
            <header><h2>{t("my.alerts")}</h2></header>
            {!alerts.data ? (
              <Loading rows={2} />
            ) : alerts.data.items.length === 0 ? (
              <p className="muted">{t("overview.alerts.none")}</p>
            ) : (
              <div className="rows">
                {reminders.slice(0, 5).map(({ n, times }) => (
                  <Link className="row" key={n.id} href={`/instruments/${n.instrument_id}`}>
                    <span className="grow">
                      {t(`notify.${n.kind}`, undefined, n.kind)}
                      <span className="line2">{n.message}</span>
                      <span className="line2">{dateTime(n.created_at)}{times > 1 ? ` · ${t("my.reminder.times", { n: times })}` : ""}</span>
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </section>
          <section className="panel">
            <header><h2>{t("nav.requests")}</h2></header>
            {!cases.data ? (
              <Loading rows={2} />
            ) : cases.data.items.length === 0 ? (
              <p className="muted">{t("cases.empty")}</p>
            ) : (
              <div className="rows">
                {cases.data.items.map((c) => (
                  <Link className="row" key={c.id} href={`/cases/${c.id}`}>
                    <span className="grow">
                      {t(`cases.type.${c.type}`)}
                      <span className="line2 mono">{c.instrument?.instrument_no}</span>
                    </span>
                    <span className="num muted">{c.checklist.filter((x) => x.done).length}/{c.checklist.length}</span>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

export default function MyPage() {
  return (
    <Shell roles={["institution"]}>
      <Home />
    </Shell>
  );
}
