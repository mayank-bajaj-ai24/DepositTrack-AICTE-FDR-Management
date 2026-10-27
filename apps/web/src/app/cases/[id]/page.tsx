"use client";

// A release, discharge or refund case: "Can this be approved, and if not, what is missing?"

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, ReasonDialog, StatePill } from "@/components/ui";
import { errorText, useApi, useResource } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Case, InstrumentDetail } from "@/lib/types";

function CaseView({ id }: { id: string }) {
  const { t, money, date, dateTime } = useI18n();
  const auth = useAuth();
  const api = useApi();
  const res = useResource<Case>(`/api/v1/cases/${id}`);
  const inst = useResource<InstrumentDetail>(res.data ? `/api/v1/instruments/${res.data.instrument_id}` : null);
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadFor, setUploadFor] = useState<string | null>(null);

  if (res.error) return <ErrorBox error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading rows={6} />;
  const c = res.data;
  const i = inst.data?.instrument;
  const canDecide = auth.has("competent_authority") && c.state === "open";

  async function tick(itemId: string) {
    setError(null);
    try {
      await api(`/api/v1/cases/${id}/checklist/${itemId}`, { method: "POST", body: JSON.stringify({}) });
      res.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function upload(file: File) {
    if (!uploadFor) return;
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await api(`/api/v1/cases/${id}/evidence?item_id=${encodeURIComponent(uploadFor)}`, { method: "POST", body: form });
      res.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <>
      <div className="title-row">
        <div>
          <p className="crumb">
            <Link href={auth.has("institution") && auth.roles.length === 1 ? "/my" : "/cases"}>
              {auth.has("institution") && auth.roles.length === 1 ? t("nav.my") : t("cases.title")}
            </Link>
            <span>/</span>
          </p>
          <h1>{t("cases.request.title", { type: t(`cases.type.${c.type}`) })}</h1>
          <p className="sub">
            {i ? `${i.institution?.name} · ` : ""}
            <span className="mono">{i?.instrument_no}</span>
            {i ? ` · ${money(i.amount)}` : ""} · {t("cases.policy", { v: c.policy_version ?? "—" })}
          </p>
        </div>
        <div className="actions">
          {canDecide && (
            <>
              <button className="btn" onClick={() => setDecision("reject")}>{t("cases.reject")}</button>
              <button className="btn primary" disabled={c.blockers.length > 0} onClick={() => setDecision("approve")}>{t("cases.approve")}</button>
            </>
          )}
          {c.state !== "open" && <span className="pill">{t(`cases.state.${c.state}`)}</span>}
        </div>
      </div>

      {error && <p className="note neg" style={{ marginBottom: 12 }}>{error}</p>}

      <div className="grid top">
        <section className="panel span-7">
          <header>
            <h2>{t("cases.checklist")}</h2>
            <span className="meta">{c.checklist.filter((x) => x.done).length} / {c.checklist.length}</span>
          </header>
          <div className="rows">
            {c.checklist.map((item) => {
              const mine =
                (item.evidence === "officer" && auth.has("scrutiny_officer")) ||
                (item.evidence !== "officer" && auth.has("institution"));
              return (
                <div className="row" key={item.id}>
                  <span aria-hidden="true" style={{ width: 18, height: 18, borderRadius: 4, border: `1.5px solid ${item.done ? "var(--text)" : "var(--control)"}`, background: item.done ? "var(--text)" : "transparent", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, flex: "none" }}>
                    {item.done ? <Icon name="check" size={12} /> : null}
                  </span>
                  <span className="grow">
                    {item.label}
                    {item.done && <span className="line2">{item.by} · {dateTime(item.at)}</span>}
                  </span>
                  {!item.done && c.state === "open" && mine && (
                    item.evidence === "document" ? (
                      <button className="btn small" onClick={() => { setUploadFor(item.id); fileInput.current?.click(); }}>{t("cases.evidence.upload")}</button>
                    ) : (
                      <button className="btn small" onClick={() => tick(item.id)}>
                        {item.evidence === "declaration" ? t("cases.evidence.declare") : t("cases.evidence.recommend")}
                      </button>
                    )
                  )}
                </div>
              );
            })}
          </div>
          <input ref={fileInput} type="file" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </section>

        <section className="panel span-5">
          <header>
            <h2>{t("cases.decision")}</h2>
            {i && <StatePill state={i.state} />}
          </header>
          {c.state === "open" ? (
            c.blockers.length ? (
              <>
                <p style={{ fontWeight: 500, marginBottom: 6 }}>{t("cases.blockers")}</p>
                <ul style={{ margin: 0, paddingLeft: 18, color: "var(--muted)" }}>
                  {c.blockers.map((b) => <li key={b}>{b}</li>)}
                </ul>
              </>
            ) : (
              <p className="note pos">{t("cases.ready")}</p>
            )
          ) : (
            <div className="rows">
              <div className="row"><span className="grow muted">{t("cases.decision")}</span><span>{t(`cases.state.${c.state}`)}</span></div>
              <div className="row"><span className="grow muted">{c.decided_by}</span><span className="muted small">{c.decision_reason}</span></div>
            </div>
          )}
          <div className="rows" style={{ marginTop: 12 }}>
            <div className="row"><span className="grow muted">{t("common.reason")}</span><span className="end truncate">{c.reason}</span></div>
            <div className="row"><span className="grow muted">{t("col.due")}</span><span className="num">{date(c.due_at)}</span></div>
          </div>
          {i && (
            <p style={{ marginTop: 12 }}>
              <Link className="card-link" href={`/instruments/${i.id}`}>{i.instrument_no}</Link>
            </p>
          )}
        </section>
      </div>

      <ReasonDialog
        open={decision !== null}
        title={decision === "approve" ? t("cases.approve") : t("cases.reject")}
        confirmLabel={decision === "approve" ? t("cases.approve") : t("cases.reject")}
        danger={decision === "reject"}
        onClose={() => setDecision(null)}
        onConfirm={async (reason) => {
          await api(`/api/v1/cases/${id}/decision`, { method: "POST", body: JSON.stringify({ approve: decision === "approve", reason }) });
          res.reload();
          inst.reload();
        }}
      />
    </>
  );
}

function Routed() {
  const { id } = useParams<{ id: string }>();
  return (
    <Shell>
      <CaseView id={id} />
    </Shell>
  );
}

export default function CasePage() {
  return (
    <Suspense>
      <Routed />
    </Suspense>
  );
}
