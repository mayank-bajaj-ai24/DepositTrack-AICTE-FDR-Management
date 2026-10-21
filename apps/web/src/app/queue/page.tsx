"use client";

// Scrutiny queue: "Who is waiting for scrutiny, and what is wrong with the oldest one?"
// A list of waiting instruments (oldest first) drives the detail pane.

import { useState } from "react";
import { InstrumentView } from "@/components/InstrumentView";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { InstrumentSummary } from "@/lib/types";

function Queue() {
  const { t, money, date } = useI18n();
  const res = useResource<{ total: number; items: InstrumentSummary[] }>(
    "/api/v1/instruments?state=submitted&state=scrutiny&state=discrepancy&state=verified&limit=200",
  );
  const items = [...(res.data?.items ?? [])].sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? items[0]?.id ?? null;

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("queue.title")}</h1>
          <p className="sub">{t("queue.sub")} · {t("common.total", { n: res.data?.total ?? 0 })}</p>
        </div>
      </div>
      {res.error && <ErrorBox error={res.error} onRetry={res.reload} />}
      <div className="split">
        <section className="panel flush list-pane" aria-label={t("queue.title")}>
          {!res.data && res.loading ? (
            <div style={{ padding: 20 }}><Loading rows={6} /></div>
          ) : items.length === 0 ? (
            <div style={{ padding: 20 }}><p className="empty">{t("queue.empty")}</p></div>
          ) : (
            <div role="listbox">
              {items.map((i) => (
                <div
                  key={i.id}
                  role="option"
                  tabIndex={0}
                  className="queue-row"
                  aria-selected={current === i.id}
                  onClick={() => setSelected(i.id)}
                  onKeyDown={(e) => e.key === "Enter" && setSelected(i.id)}
                >
                  <span className="top">
                    <span className="truncate">{i.institution?.name}</span>
                    {i.open_flags > 0 ? (
                      <span className="pill neg">{t("col.flags")} {i.open_flags}</span>
                    ) : (
                      <span className="pill">{t(`state.${i.state}`)}</span>
                    )}
                  </span>
                  <span className="muted small" style={{ display: "block", marginTop: 4 }}>
                    <span className="mono">{i.instrument_no}</span> · {money(i.amount)} · {date(i.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
        <div>
          {current ? <InstrumentView key={current} id={current} compact /> : <p className="empty">{t("queue.select")}</p>}
        </div>
      </div>
    </>
  );
}

export default function QueuePage() {
  return (
    <Shell roles={["scrutiny_officer", "verifying_officer"]}>
      <Queue />
    </Shell>
  );
}
