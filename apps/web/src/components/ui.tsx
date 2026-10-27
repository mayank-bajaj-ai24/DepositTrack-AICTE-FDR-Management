"use client";

import { useEffect, useRef, useState } from "react";
import { errorText } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const STATE_TONE: Record<string, string> = {
  active: "pos",
  verified: "pos",
  renewed: "",
  released: "",
  archived: "",
  matured: "",
  expiring: "warn",
  releasing: "warn",
  discrepancy: "warn",
  overdue: "neg",
  rejected: "neg",
  submitted: "",
  scrutiny: "",
  draft: "",
};

export function StatePill({ state }: { state: string }) {
  const { t } = useI18n();
  return <span className={`pill ${STATE_TONE[state] ?? ""}`}>{t(`state.${state}`, undefined, state)}</span>;
}

export function SeverityPill({ severity }: { severity: string }) {
  const { t } = useI18n();
  const tone = severity === "critical" || severity === "high" ? "neg" : severity === "medium" ? "warn" : "";
  return <span className={`pill ${tone}`}>{t(`severity.${severity}`, undefined, severity)}</span>;
}

/** Trust Ladder (N1): five steps filled to the level; bank levels (L3, L4) take the hue. */
export function TrustLadder({ level, label = true }: { level: number; label?: boolean }) {
  const { t } = useI18n();
  return (
    <span className="ladder" title={`${t("trust.explain")}: L${level} ${t(`trust.${level}`)}`}>
      <span className={`ladder-steps${level >= 3 ? " bank" : ""}`} aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={i <= level ? "on" : ""} />
        ))}
      </span>
      {label && <span className="ladder-label">L{level} {t(`trust.${level}`)}</span>}
      {!label && <span className="visually-hidden">L{level} {t(`trust.${level}`)}</span>}
    </span>
  );
}

export function Loading({ rows = 3, height = 20 }: { rows?: number; height?: number }) {
  const { t } = useI18n();
  return (
    <div aria-busy="true" aria-label={t("common.loading")} style={{ display: "grid", gap: 12 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <span key={i} className="skeleton" style={{ height, width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="error-box" role="alert">
      <span>{t("common.error", { message: errorText(error) })}</span>
      {onRetry && (
        <button className="btn ghost small" onClick={onRetry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

/** A reason-first confirmation: every officer action carries a written reason. */
export function ReasonDialog({
  open,
  title,
  confirmLabel,
  onConfirm,
  onClose,
  danger,
}: {
  open: boolean;
  title: string;
  confirmLabel: string;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
  danger?: boolean;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setReason("");
      setError(null);
      d.showModal();
    }
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog ref={ref} className="modal" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!reason.trim()) return setError(new Error(t("common.reasonRequired")));
          setBusy(true);
          try {
            await onConfirm(reason.trim());
            onClose();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>{title}</h2>
        <div className="field">
          <label htmlFor="reason">{t("common.reason")}</label>
          <textarea id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </div>
        {error ? <p className="note neg" style={{ marginTop: 12 }}>{errorText(error)}</p> : null}
        <div className="form-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button type="submit" className={`btn ${danger ? "danger" : "primary"}`} disabled={busy}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 86_400_000);
}

/** The Trust Ladder as a flight of five steps in perspective, climbed up to the instrument's
 *  level; the bank levels (L3, L4) take the hue. The legend under it says each level in words,
 *  so the picture is never the only carrier of the meaning. */
export function TrustStairs({ level }: { level: number }) {
  const { t } = useI18n();
  return (
    <figure className="stairs" aria-label={`${t("trust.explain")}: L${level} ${t(`trust.${level}`)}`}>
      <div className="stairs-stage" aria-hidden="true">
        <div className="stairs-flight">
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className={`step${i <= level ? " on" : ""}${i >= 3 ? " bank" : ""}${i === level ? " current" : ""}`}
              style={{ left: i * 42, ["--z" as string]: `${(i + 1) * 9}px` }}
            >
              <i />
            </span>
          ))}
        </div>
      </div>
      <figcaption className="stairs-legend">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={i <= level ? "on" : "off"}>
            <b>L{i}</b>
            <span className="name">{t(`trust.${i}`)}</span>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
