"use client";

// System: "Is everything DepositTrack depends on in place, and what is switched on?"
// Settings rows: a label column with what the setting means, a panel with its current values.
// A live model is named with what it was trained on (AGENTS.md rule 5); an off model says why.

import { useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { errorText, useApi, useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { SystemStatus } from "@/lib/types";

function Setting({ title, help, children }: { title: string; help: string; children: React.ReactNode }) {
  return (
    <section className="setting">
      <div className="setting-label">
        <h2>{title}</h2>
        <p className="muted">{help}</p>
      </div>
      <div className="setting-panel">{children}</div>
    </section>
  );
}

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

  // A model row: on with its training data, or off with the reason.
  const model = (name: string, on: boolean, trainedOn: string | null, offReason: string) => (
    <div className="row">
      <span className="grow">
        {name}
        <span className="line2">{on ? t("admin.model.trainedOn", { data: trainedOn ?? t("admin.model.unnamed") }) : offReason}</span>
      </span>
      <span className={`pill ${on ? "pos" : ""}`}>{on ? t("admin.model.live") : t("admin.model.off")}</span>
    </div>
  );

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("admin.title")}</h1>
          <p className="sub">{t("admin.sub")}</p>
        </div>
      </div>
      {message && <p className={`note note-in ${message.tone}`} style={{ marginBottom: 16 }} role="status">{message.text}</p>}
      {status.error && <ErrorBox error={status.error} onRetry={status.reload} />}
      {!s ? (
        <Loading rows={6} />
      ) : (
        <div className="settings">
          <Setting title={t("admin.policy")} help={t("admin.policy.help")}>
            <dl className="kv">
              <dt>{t("admin.policy.version")}</dt>
              <dd className="mono">{s.policy_version}</dd>
              <dt>{t("admin.policy.demo")}</dt>
              <dd>{s.demo_policy ? t("common.yes") : t("common.no")}</dd>
            </dl>
            {s.unconfirmed.length > 0 && (
              <>
                <h3>{t("admin.policy.unconfirmed", { n: s.unconfirmed.length })}</h3>
                <div className="rows">
                  {s.unconfirmed.map((k) => (
                    <div className="row" key={k}>
                      <span className="grow mono small">{k}</span>
                      <span className="pill warn">{t("admin.policy.awaiting")}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Setting>

          <Setting title={t("admin.models")} help={t("admin.models.help")}>
            <div className="rows">
              {model(t("admin.model.extraction"), s.layoutlm_available, s.layoutlm_training_data, t("admin.model.extraction.off"))}
              {model(t("admin.model.forgery"), s.forgery_model_available, s.forgery_model_training_data, t("admin.model.forgery.off"))}
              {model(t("admin.model.risk"), s.risk_model_available, null, t("admin.model.risk.off"))}
            </div>
          </Setting>

          <Setting title={t("admin.bank")} help={t("admin.bank.help")}>
            <dl className="kv">
              <dt>{t("admin.bank.channel")}</dt>
              <dd>{s.bank_channel_configured ? t("admin.bank.configured") : t("admin.bank.missing")}</dd>
              <dt>{t("admin.bank.keys")}</dt>
              <dd className="num">{s.bank_keys_pinned}</dd>
            </dl>
            <div className="form-actions" style={{ justifyContent: "flex-start" }}>
              <button
                className="btn"
                disabled={busy || !s.bank_channel_configured}
                onClick={() =>
                  run(async () => {
                    const r = await api<{ added: string[]; pinned: Record<string, string> }>("/api/v1/admin/bank-keys/pin", { method: "POST" });
                    return t("admin.pin.result", { n: Object.keys(r.pinned).length, added: r.added.length });
                  })
                }
              >
                {t("admin.pin")}
              </button>
              {!s.bank_channel_configured && <span className="muted small" style={{ alignSelf: "center" }}>{t("admin.bank.missing.help")}</span>}
            </div>
          </Setting>

          <Setting title={t("admin.anchoring")} help={t("admin.anchoring.help")}>
            <dl className="kv">
              <dt>immudb</dt>
              <dd>{s.immudb_enabled ? t("admin.anchoring.on") : t("admin.anchoring.off")}</dd>
              <dt>{t("admin.anchoring.client")}</dt>
              <dd>{s.immudb_client_installed ? t("admin.available") : t("admin.unavailable")}</dd>
            </dl>
            {s.immudb_problem && <p className="note warn" style={{ marginTop: 12 }}>{s.immudb_problem}</p>}
            <div className="form-actions" style={{ justifyContent: "flex-start" }}>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await api<{ anchored: boolean; merkle_root?: string; message?: string; store_error?: string | null }>("/api/v1/audit/anchors", { method: "POST" });
                    if (!r.anchored) return r.message ?? t("admin.anchor.nothing");
                    return r.store_error
                      ? t("admin.anchor.storedOnly", { root: r.merkle_root?.slice(0, 16) ?? "", error: r.store_error })
                      : t("admin.anchor.done", { root: r.merkle_root?.slice(0, 16) ?? "" });
                  })
                }
              >
                {t("admin.anchor")}
              </button>
            </div>
          </Setting>

          <Setting title={t("admin.clock")} help={t("admin.clock.help")}>
            <dl className="kv">
              <dt>{t("admin.clock.today")}</dt>
              <dd>{date(s.today)}</dd>
              <dt>{t("admin.clock.offset")}</dt>
              <dd className="num">{s.clock_offset_days}</dd>
            </dl>
            <div className="toolbar" style={{ margin: "16px 0 0", alignItems: "end" }}>
              <div className="field" style={{ width: 200 }}>
                <label htmlFor="days">{t("admin.clock.days")}</label>
                <input id="days" className="input num" type="number" min={0} value={days} onChange={(e) => setDays(Math.max(0, Number(e.target.value)))} disabled={!s.demo_policy} aria-describedby="days-hint" />
              </div>
              <button
                className="btn"
                disabled={busy || !s.demo_policy}
                onClick={() =>
                  run(async () => {
                    const r = await api<{ today: string }>("/api/v1/admin/clock", { method: "POST", body: JSON.stringify({ days }) });
                    return `${t("admin.clock")}: ${date(r.today)}`;
                  })
                }
              >
                {t("admin.clock.set")}
              </button>
              <span className="spacer" />
              <button
                className="btn primary"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const r = await api<{ moved: unknown[]; notifications: number; risk_scored: number }>("/api/v1/admin/sweep", { method: "POST" });
                    return t("admin.sweep.result", { moved: r.moved.length, notified: r.notifications, scored: r.risk_scored });
                  })
                }
              >
                {t("admin.sweep")}
              </button>
            </div>
            <p id="days-hint" className="muted small" style={{ marginTop: 8 }}>{s.demo_policy ? t("admin.clock.hint") : t("admin.clock.locked")}</p>
          </Setting>
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
