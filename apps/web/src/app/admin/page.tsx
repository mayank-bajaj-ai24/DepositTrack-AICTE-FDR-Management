"use client";

import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { errorText, useApi, useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { SystemStatus } from "@/lib/types";

function Admin() {
  const { t, date } = useI18n();
  const api = useApi();
  const status = useResource<SystemStatus>("/api/v1/system/status");
  const [days, setDays] = useState<number>(0);
  const [message, setMessage] = useState<{ tone: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    setMessage(null);
    try {
      setMessage({ tone: "pos", text: await fn() });
      status.reload();
    } catch (e) {
      setMessage({ tone: "neg", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  const s = status.data;
  const available = (ok: boolean) => <span className={`pill ${ok ? "pos" : ""}`}>{ok ? t("admin.available") : t("admin.unavailable")}</span>;

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("admin.title")}</h1>
          <p className="sub">{t("admin.sub")}</p>
        </div>
      </div>
      {message && <p className={`note ${message.tone}`} style={{ marginBottom: 12 }}>{message.text}</p>}
      {status.error && <ErrorBox error={status.error} onRetry={status.reload} />}
      {!s ? (
        <Loading rows={6} />
      ) : (
        <div className="grid top">
          <section className="panel span-6">
            <header>
              <h2>{t("admin.policy")}</h2>
              <span className="meta mono">{s.policy_version}</span>
            </header>
            <div className="rows">
              <div className="row">
                <span className="grow muted">Demo</span>
                <span className={`pill ${s.demo_policy ? "warn" : ""}`}>{s.demo_policy ? t("common.yes") : t("common.no")}</span>
              </div>
              {s.unconfirmed.map((k) => (
                <div className="row" key={k}>
                  <span className="grow mono small">{k}</span>
                  <span className="pill warn">{t("banner.awaiting", { list: "" }).replace(/:\s*$/, "")}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel span-6">
            <header>
              <h2>{t("admin.integrations")}</h2>
            </header>
            <div className="rows">
              <div className="row"><span className="grow">{t("admin.bank")}</span>{available(s.bank_channel_configured)}</div>
              <div className="row"><span className="grow muted">Pinned keys</span><span className="num">{s.bank_keys_pinned}</span></div>
              <div className="row"><span className="grow">LayoutLMv3</span>{available(s.layoutlm_available)}</div>
              <div className="row"><span className="grow">Forgery model</span>{available(s.forgery_model_available)}</div>
              <div className="row"><span className="grow">Renewal-risk model</span>{available(s.risk_model_available)}</div>
              <div className="row"><span className="grow">immudb</span>{available(s.immudb_enabled)}</div>
            </div>
            <div className="form-actions" style={{ justifyContent: "flex-start" }}>
              <button className="btn" disabled={busy || !s.bank_channel_configured} onClick={() => run(async () => {
                const r = await api<{ added: string[]; pinned: Record<string, string> }>("/api/v1/admin/bank-keys/pin", { method: "POST" });
                return `${t("admin.pin")}: ${Object.keys(r.pinned).length}`;
              })}>{t("admin.pin")}</button>
              <button className="btn" disabled={busy} onClick={() => run(async () => {
                const r = await api<{ anchored: boolean; merkle_root?: string; message?: string }>("/api/v1/audit/anchors", { method: "POST" });
                return r.anchored ? `${t("admin.anchor")}: ${r.merkle_root?.slice(0, 16)}…` : r.message ?? "";
              })}>{t("admin.anchor")}</button>
            </div>
          </section>

          <section className="panel span-12">
            <header>
              <h2>{t("admin.clock")}</h2>
              <span className="meta">{date(s.today)}</span>
            </header>
            <div className="toolbar" style={{ marginBottom: 0 }}>
              <div className="field" style={{ width: 220 }}>
                <label htmlFor="days">{t("admin.clock.days")}</label>
                <input id="days" className="input num" type="number" min={0} value={days} onChange={(e) => setDays(Math.max(0, Number(e.target.value)))} disabled={!s.demo_policy} />
              </div>
              <button className="btn" style={{ alignSelf: "end" }} disabled={busy || !s.demo_policy} onClick={() => run(async () => {
                const r = await api<{ today: string }>("/api/v1/admin/clock", { method: "POST", body: JSON.stringify({ days }) });
                return `${t("admin.clock")}: ${date(r.today)}`;
              })}>{t("admin.clock.set")}</button>
              <span className="spacer" />
              <button className="btn primary" style={{ alignSelf: "end" }} disabled={busy} onClick={() => run(async () => {
                const r = await api<{ moved: unknown[]; notifications: number; risk_scored: number }>("/api/v1/admin/sweep", { method: "POST" });
                return t("admin.sweep.result", { moved: r.moved.length, notified: r.notifications, scored: r.risk_scored });
              })}>{t("admin.sweep")}</button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

export default function AdminPage() {
  return (
    <Shell roles={["admin"]}>
      <Admin />
    </Shell>
  );
}
