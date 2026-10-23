"use client";

// One instrument. The question: "Can we trust this FDR, and what happens next?"
// Fields with their Trust Ladder level lead; discrepancies and the next action sit beside them.

import Link from "next/link";
import { useState } from "react";
import { CoverageStrip } from "@/components/CoverageStrip";
import { ErrorBox, Loading, ReasonDialog, SeverityPill, StatePill, TrustLadder } from "@/components/ui";
import { download, errorText, useApi, useResource } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { FIELD_ORDER, type InstrumentDetail } from "@/lib/types";

type Pending =
  | { kind: "move"; target: string }
  | { kind: "resolve"; flagId: string }
  | { kind: "verify"; field: string }
  | { kind: "observe" }
  | null;

function fmtValue(field: string, v: string | null, money: (x: string) => string, date: (x: string) => string) {
  if (v === null || v === "") return <span className="muted">—</span>;
  if (field === "amount") return money(v);
  if (field === "issue_date" || field === "maturity_date") return date(v);
  if (field === "fdr_no" || field === "ifsc") return <span className="mono">{v}</span>;
  return v;
}

export function InstrumentView({ id, compact = false }: { id: string; compact?: boolean }) {
  const { t, money, date, dateTime, percent } = useI18n();
  const auth = useAuth();
  const api = useApi();
  const res = useResource<InstrumentDetail>(`/api/v1/instruments/${id}`);
  const [pending, setPending] = useState<Pending>(null);
  const [notice, setNotice] = useState<{ tone: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (res.error) return <ErrorBox error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading rows={8} />;
  const d = res.data;
  const i = d.instrument;
  const isOfficer = auth.has("scrutiny_officer", "verifying_officer");
  const openFlags = d.flags.filter((f) => f.status === "open");
  const fields = [...d.fields].sort((a, b) => FIELD_ORDER.indexOf(a.field as never) - FIELD_ORDER.indexOf(b.field as never));
  const flaggedFields = new Set(openFlags.map((f) => (f.fact?.field as string | undefined) ?? ""));

  async function act(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true);
    setNotice(null);
    try {
      const r = await fn();
      if (ok) setNotice({ tone: "pos", text: ok });
      res.reload();
      return r;
    } catch (e) {
      setNotice({ tone: "neg", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  async function bankVerify() {
    const r = (await act(() => api<{ result: string; mismatched?: string[]; reason?: string; problem?: string }>(`/api/v1/instruments/${id}/bank-verification`, { method: "POST" }))) as
      | { result: string; mismatched?: string[]; reason?: string; problem?: string }
      | undefined;
    if (!r) return;
    if (r.result === "attested") setNotice({ tone: "pos", text: t("detail.bankResult.attested") });
    else if (r.result === "rejected") setNotice({ tone: "neg", text: t("detail.bankResult.rejected", { reason: r.reason ?? "" }) });
    else setNotice({ tone: "neg", text: t("detail.bankResult.mismatch", { fields: [...(r.mismatched ?? []).map((f) => t(`field.${f}`)), r.problem].filter(Boolean).join(", ") }) });
  }

  const dialogTitle =
    pending?.kind === "move"
      ? t("detail.move", { state: t(`state.${pending.target}`) })
      : pending?.kind === "resolve"
        ? t("detail.resolve")
        : pending?.kind === "verify"
          ? `${t("detail.verifyField")}: ${t(`field.${pending.field}`)}`
          : t("detail.observation.add");

  async function confirm(reason: string) {
    if (!pending) return;
    if (pending.kind === "move")
      await api(`/api/v1/instruments/${id}/transition`, { method: "POST", body: JSON.stringify({ target: pending.target, reason }) });
    if (pending.kind === "resolve")
      await api(`/api/v1/instruments/${id}/flags/${pending.flagId}/resolve`, { method: "POST", body: JSON.stringify({ resolution: reason }) });
    if (pending.kind === "verify")
      await api(`/api/v1/instruments/${id}/fields/${pending.field}`, { method: "POST", body: JSON.stringify({ verify: true, reason }) });
    if (pending.kind === "observe")
      await api(`/api/v1/instruments/${id}/observations`, { method: "POST", body: JSON.stringify({ text: reason }) });
    res.reload();
  }

  const replaces = i.replaces_id;
  const risk = i.risk_score;

  return (
    <>
      <div className="title-row">
        <div>
          {!compact && (
            <p className="crumb">
              <Link href={auth.has("institution") && auth.roles.length === 1 ? "/my" : "/instruments"}>
                {auth.has("institution") && auth.roles.length === 1 ? t("nav.my") : t("nav.instruments")}
              </Link>
              <span>/</span>
            </p>
          )}
          <h1 className="mono" style={{ fontFamily: "var(--mono)" }}>{i.instrument_no}</h1>
          <p className="sub">
            {i.institution?.name} · {i.bank_name ?? "—"} · {money(i.amount)} · {t("col.maturity")} {date(i.maturity_date)}
          </p>
        </div>
        <div className="actions" style={{ alignItems: "center" }}>
          <StatePill state={i.state} />
          <TrustLadder level={i.trust_level} />
        </div>
      </div>

      {notice && <p className={`note ${notice.tone}`} style={{ marginBottom: 12 }}>{notice.text}</p>}

      <div className="grid top">
        <section className="panel flush span-8">
          <header>
            <div>
              <h2>{t("detail.fields")}</h2>
              <p className="meta" style={{ marginTop: 2 }}>{t("detail.fields.sub")}</p>
            </div>
          </header>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="responsive">
              <thead>
                <tr>
                  <th>{t("detail.fields")}</th>
                  <th>{t("col.declared")}</th>
                  <th className="hide-sm">{t("col.extracted")}</th>
                  <th className="hide-sm">{t("col.bankValue")}</th>
                  <th>{t("col.trust")}</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((f) => {
                  const read = f.extracted_b ?? f.extracted_a;
                  const differs = read && f.declared && read.replace(/\s/g, "").toUpperCase() !== f.declared.replace(/\s/g, "").toUpperCase();
                  return (
                    <tr key={f.field}>
                      <td className="muted">
                        {t(`field.${f.field}`)}
                        {flaggedFields.has(f.field) && <span className="dot" style={{ display: "inline-block", marginLeft: 6, color: "var(--negative)" }} aria-label="flagged" />}
                      </td>
                      <td className="truncate">{fmtValue(f.field, f.declared, money, date)}</td>
                      <td className="hide-sm truncate" style={differs ? { color: "var(--negative)" } : undefined}>
                        {fmtValue(f.field, read, money, date)}
                      </td>
                      <td className="hide-sm truncate">{fmtValue(f.field, f.bank_value, money, date)}</td>
                      <td>
                        <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                          <TrustLadder level={f.trust_level} label={false} />
                          {isOfficer && f.trust_level < 2 && f.declared && (
                            <button className="btn ghost small" onClick={() => setPending({ kind: "verify", field: f.field })}>
                              {t("detail.verifyField")}
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <div className="span-4 stack">
          <section className="panel">
            <header>
              <h2>{t("detail.actions")}</h2>
            </header>
            <div style={{ display: "grid", gap: 8 }}>
              {d.next_states.map((s) => (
                <button key={s} className={`btn ${s === "verified" || s === "active" ? "primary" : ""}`} disabled={busy} onClick={() => setPending({ kind: "move", target: s })}>
                  {t("detail.move", { state: t(`state.${s}`) })}
                </button>
              ))}
              {auth.has("verifying_officer") && (
                <>
                  <button className="btn" disabled={busy} onClick={bankVerify}>{t("detail.verifyBank")}</button>
                  {i.trust_level >= 3 && (
                    <button className="btn ghost" disabled={busy} onClick={() => act(() => api(`/api/v1/instruments/${id}/bank-status`, { method: "POST" }))}>
                      {t("detail.refreshBank")}
                    </button>
                  )}
                </>
              )}
              {auth.has("scrutiny_officer", "verifying_officer") && (
                <button className="btn ghost" onClick={() => setPending({ kind: "observe" })}>{t("detail.observation.add")}</button>
              )}
              {auth.has("institution") && (i.state === "active" || i.state === "matured") && (
                <Link className="btn" href={`/my/request/${id}`}>{t("detail.requestRelease")}</Link>
              )}
              {auth.has("institution") && (i.state === "expiring" || i.state === "overdue") && (
                <Link className="btn primary" href={`/my/submit?replaces=${id}`}>{t("detail.submitRenewal")}</Link>
              )}
              {d.next_states.length === 0 && !isOfficer && !auth.has("institution") && <p className="muted">{t("common.none")}</p>}
            </div>
          </section>

          <section className="panel">
            <header>
              <h2>{t("detail.risk")}</h2>
            </header>
            {risk === null ? (
              <p className="muted">{t("detail.risk.none")}</p>
            ) : (
              <>
                <p className="figure num" style={{ color: risk >= 0.7 ? "var(--negative)" : "var(--text)" }}>{percent(risk)}</p>
                <p className="muted">{t("detail.risk.value", { p: percent(risk) })}</p>
              </>
            )}
          </section>
        </div>

        <section className="panel span-7">
          <header>
            <h2>{t("detail.flags")}</h2>
            <span className="meta">{openFlags.length}</span>
          </header>
          {d.flags.length === 0 ? (
            <p className="empty">{t("detail.flags.none")}</p>
          ) : (
            <div className="rows">
              {d.flags.map((f) => (
                <div className="row" key={f.id} style={{ alignItems: "flex-start", opacity: f.status === "resolved" ? 0.6 : 1 }}>
                  <span className="grow">
                    <span style={{ fontWeight: 500 }}>{t(`flag.${f.type}`, undefined, f.type)}</span>
                    <span className="line2">{f.reason}</span>
                    {f.clause_ref && <span className="line2">{f.clause_ref}</span>}
                    {f.status === "resolved" && <span className="line2">✓ {f.resolved_by}</span>}
                  </span>
                  <span style={{ display: "grid", gap: 6, justifyItems: "end" }}>
                    <SeverityPill severity={f.severity} />
                    {f.status === "open" && auth.has("scrutiny_officer") && (
                      <button className="btn ghost small" onClick={() => setPending({ kind: "resolve", flagId: f.id })}>{t("detail.resolve")}</button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel span-5">
          <header>
            <h2>{t("detail.documents")}</h2>
          </header>
          <div className="rows">
            {d.documents.map((doc) => (
              <div className="row" key={doc.id}>
                <span className="grow">
                  {doc.kind.replace("evidence:", "")} · v{doc.version}
                  <span className="line2 mono" title={doc.sha256}>sha256 {doc.sha256.slice(0, 12)}…</span>
                </span>
                {doc.forgery_score !== null && <span className="muted small">{doc.forgery_score.toFixed(2)}</span>}
                <button className="btn ghost small" onClick={() => download(auth.token, `/api/v1/instruments/${id}/documents/${doc.id}`, `${i.instrument_no}-${doc.kind}-v${doc.version}`)}>
                  {t("common.download")}
                </button>
              </div>
            ))}
          </div>
          {(replaces || d.replaced_by.length > 0) && (
            <>
              <h3 style={{ fontSize: 14, fontWeight: 500, margin: "16px 0 4px" }}>{t("detail.renewal")}</h3>
              {replaces && (
                <Link className="card-link" href={`/instruments/${replaces}`}>{t("detail.replaces", { fdr: replaces.slice(0, 8) })}</Link>
              )}
              {d.replaced_by.map((r) => (
                <p key={r.id}>
                  <Link className="card-link" href={`/instruments/${r.id}`}>{t("detail.replacedBy", { fdr: r.instrument_no })}</Link>
                </p>
              ))}
            </>
          )}
        </section>

        {d.coverage && (
          <section className="panel span-12">
            <header>
              <h2>{t("detail.coverage")}</h2>
            </header>
            <CoverageStrip coverage={d.coverage} today={d.today} />
          </section>
        )}

        {d.cases.length > 0 && (
          <section className="panel span-6">
            <header>
              <h2>{t("detail.cases")}</h2>
            </header>
            <div className="rows">
              {d.cases.map((c) => (
                <Link className="row" key={c.id} href={`/cases/${c.id}`}>
                  <span className="grow">
                    {t(`cases.type.${c.type}`)}
                    <span className="line2">{c.reason}</span>
                  </span>
                  <span className="pill">{t(`cases.state.${c.state}`)}</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {d.observations.length > 0 && (
          <section className="panel span-6">
            <header>
              <h2>{t("detail.observations")}</h2>
            </header>
            <div className="rows">
              {d.observations.map((o) => (
                <div className="row" key={o.id}>
                  <span className="grow">
                    {o.text}
                    <span className="line2">{o.officer} · {dateTime(o.created_at)}</span>
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {d.events.length > 0 && (
          <section className="panel span-12">
            <header>
              <h2>{t("detail.timeline")}</h2>
              <span className={`pill ${d.chain.intact ? "pos" : "neg"}`}>
                {d.chain.intact ? t("detail.chain.intact", { n: d.chain.length }) : t("detail.chain.broken", { seq: d.chain.broken_at_seq ?? "?" })}
              </span>
            </header>
            <div className="timeline">
              {[...d.events].reverse().map((e) => (
                <div className="ev" key={e.id}>
                  <span className="when num">{dateTime(e.ts)}</span>
                  <span className="what">
                    {t(`event.${e.action}`, undefined, e.action)}
                    {e.action === "instrument.state_changed" && e.after?.state ? ` → ${t(`state.${String(e.after.state)}`)}` : ""}
                    <span className="line2" style={{ display: "block" }}>
                      {e.actor} · {e.role}
                      {e.reason ? ` · ${e.reason}` : ""}
                    </span>
                    <span className="hash mono">#{e.seq} {e.hash.slice(0, 16)}…</span>
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      <ReasonDialog
        open={pending !== null}
        title={dialogTitle}
        confirmLabel={t("common.save")}
        onClose={() => setPending(null)}
        onConfirm={confirm}
      />
    </>
  );
}
