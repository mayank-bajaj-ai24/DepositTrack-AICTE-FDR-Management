"use client";

import Link from "next/link";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Case } from "@/lib/types";

function Cases() {
  const { t, money, date } = useI18n();
  const [state, setState] = useState<"open" | "approved" | "rejected">("open");
  const res = useResource<{ total: number; items: Case[] }>(`/api/v1/cases?state=${state}`);
  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("cases.title")}</h1>
          <p className="sub">{t("cases.sub")}</p>
        </div>
      </div>
      <div className="toolbar">
        <div className="segmented" role="group">
          {(["open", "approved", "rejected"] as const).map((s) => (
            <button key={s} aria-pressed={state === s} onClick={() => setState(s)}>{t(`cases.state.${s}`)}</button>
          ))}
        </div>
      </div>
      {res.error && <ErrorBox error={res.error} onRetry={res.reload} />}
      <section className="panel flush">
        {!res.data && res.loading ? (
          <div style={{ padding: 20 }}><Loading rows={5} /></div>
        ) : !res.data?.items.length ? (
          <div style={{ padding: 20 }}><p className="empty">{t("cases.empty")}</p></div>
        ) : (
          <div className="table-wrap">
            <table className="responsive">
              <thead>
                <tr>
                  <th>{t("col.institution")}</th>
                  <th>{t("col.type")}</th>
                  <th className="n">{t("col.amount")}</th>
                  <th className="hide-sm">{t("cases.checklist")}</th>
                  <th className="n hide-sm">{t("col.due")}</th>
                </tr>
              </thead>
              <tbody>
                {res.data.items.map((c) => {
                  const done = c.checklist.filter((i) => i.done).length;
                  return (
                    <tr key={c.id}>
                      <td>
                        <Link href={`/cases/${c.id}`} className="truncate" style={{ display: "block" }}>{c.instrument?.institution?.name}</Link>
                        <span className="sub mono">{c.instrument?.instrument_no}</span>
                      </td>
                      <td>{t(`cases.type.${c.type}`)}</td>
                      <td className="n num">{money(c.instrument?.amount ?? null)}</td>
                      <td className="hide-sm">
                        {state === "open" && c.blockers.length === 0 ? (
                          <span className="pill pos">{t("cases.ready")}</span>
                        ) : (
                          <span className="num">{done} / {c.checklist.length}</span>
                        )}
                      </td>
                      <td className="n num hide-sm" style={c.escalation_level > 0 ? { color: "var(--negative)" } : undefined}>{date(c.due_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default function CasesPage() {
  return (
    <Shell roles={["scrutiny_officer", "competent_authority", "auditor", "admin"]}>
      <Cases />
    </Shell>
  );
}
