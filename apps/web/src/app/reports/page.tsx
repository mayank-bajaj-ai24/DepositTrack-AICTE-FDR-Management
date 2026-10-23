"use client";

import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { download, useResource } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

const REPORTS = ["interventions", "pending-verifications", "upcoming-maturities", "missing-documents"] as const;
type Report = { name: string; title: string; header: string[]; rows: (string | number)[][] };

function Reports() {
  const { t } = useI18n();
  const { token } = useAuth();
  const [name, setName] = useState<(typeof REPORTS)[number]>("interventions");
  const res = useResource<Report>(`/api/v1/reports/${name}`);
  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("reports.title")}</h1>
          <p className="sub">{t("reports.sub")}</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => download(token, `/api/v1/reports/${name}?format=csv`, `${name}.csv`)}>CSV</button>
          <button className="btn primary" onClick={() => download(token, `/api/v1/reports/${name}?format=xlsx`, `${name}.xlsx`)}>Excel</button>
        </div>
      </div>
      <div className="toolbar">
        <div className="segmented" role="group">
          {REPORTS.map((r) => (
            <button key={r} aria-pressed={name === r} onClick={() => setName(r)}>{t(`reports.${r}`)}</button>
          ))}
        </div>
        <span className="spacer" />
        {res.data && <span className="muted num">{t("reports.rows", { n: res.data.rows.length })}</span>}
      </div>
      {res.error && <ErrorBox error={res.error} onRetry={res.reload} />}
      <section className="panel flush">
        {!res.data && res.loading ? (
          <div style={{ padding: 20 }}><Loading rows={6} /></div>
        ) : !res.data?.rows.length ? (
          <div style={{ padding: 20 }}><p className="empty">{t("reports.empty")}</p></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>{res.data.header.map((h, i) => <th key={h} className={i === 5 || i === 6 || i === 8 ? "n" : undefined}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {res.data.rows.map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} className={ci === 5 || ci === 6 || ci === 8 ? "n num" : ci === 2 || ci === 4 ? "mono" : ci === 0 || ci === 9 ? "truncate" : undefined}>
                        {cell === "" || cell === null ? "—" : String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default function ReportsPage() {
  return (
    <Shell roles={["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"]}>
      <Reports />
    </Shell>
  );
}
