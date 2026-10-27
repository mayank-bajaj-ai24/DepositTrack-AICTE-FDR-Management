"use client";

import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, StatePill, TrustLadder } from "@/components/ui";
import { download, useResource } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

const REPORTS = ["interventions", "pending-verifications", "upcoming-maturities", "missing-documents"] as const;
type Report = { name: string; title: string; header: string[]; rows: (string | number)[][] };

function Reports() {
  const { t, money, date } = useI18n();
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
            <table className="report responsive">
              <thead>
                <tr>
                  {/* One fixed column order for every report (apps/api/app/api/dashboard.py); the AICTE ID
                      and the report's detail ride under the institution, as in the export's columns 2 and 10. */}
                  <th>{t("reports.col.0", undefined, res.data.header[0])}</th>
                  <th>{t("reports.col.2", undefined, res.data.header[2])}</th>
                  <th className="hide-md">{t("reports.col.3", undefined, res.data.header[3])}</th>
                  <th className="hide-md">{t("reports.col.4", undefined, res.data.header[4])}</th>
                  <th className="n">{t("reports.col.5", undefined, res.data.header[5])}</th>
                  <th className="n hide-sm">{t("reports.col.6", undefined, res.data.header[6])}</th>
                  <th>{t("reports.col.7", undefined, res.data.header[7])}</th>
                  <th className="hide-md">{t("reports.col.8", undefined, res.data.header[8])}</th>
                </tr>
              </thead>
              <tbody>
                {res.data.rows.map((row, ri) => {
                  const v = (i: number) => (row[i] === "" || row[i] === null || row[i] === undefined ? null : String(row[i]));
                  const dash = <span className="muted">—</span>;
                  return (
                    <tr key={ri}>
                      <td>
                        <span className="truncate" style={{ display: "block" }} title={v(0) ?? ""}>{v(0) ?? "—"}</span>
                        <span className="sub mono">{v(1) ?? "—"}</span>
                        {v(9) && <span className="sub">{v(9)}</span>}
                      </td>
                      <td className="mono nowrap">{v(2) ?? dash}</td>
                      <td className="nowrap hide-md">{v(3) ?? dash}</td>
                      <td className="mono nowrap hide-md">{v(4) ?? dash}</td>
                      <td className="n num nowrap">{v(5) ? money(v(5)) : dash}</td>
                      <td className="n num nowrap hide-sm">{v(6) ? date(v(6)) : dash}</td>
                      <td>{v(7) ? <StatePill state={v(7)!} /> : dash}</td>
                      <td className="hide-md">{v(8) ? <TrustLadder level={Number(v(8))} label={false} /> : dash}</td>
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

export default function ReportsPage() {
  return (
    <Shell roles={["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"]}>
      <Reports />
    </Shell>
  );
}
