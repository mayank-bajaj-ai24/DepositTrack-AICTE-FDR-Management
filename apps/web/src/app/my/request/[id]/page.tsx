"use client";

import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { errorText, useApi, useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Case, InstrumentDetail } from "@/lib/types";

const TYPES = ["release", "discharge", "refund"] as const;

function RequestForm({ id }: { id: string }) {
  const { t, money } = useI18n();
  const api = useApi();
  const router = useRouter();
  const res = useResource<InstrumentDetail>(`/api/v1/instruments/${id}`);
  const [type, setType] = useState<(typeof TYPES)[number]>("release");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (res.error) return <ErrorBox error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Loading rows={4} />;
  const i = res.data.instrument;

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("cases.request.title", { type: t(`cases.type.${type}`) })}</h1>
          <p className="sub"><span className="mono">{i.instrument_no}</span> · {i.bank_name} · {money(i.amount)}</p>
        </div>
      </div>
      <section className="panel" style={{ maxWidth: 640 }}>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!reason.trim()) return setError(t("common.reasonRequired"));
            setBusy(true);
            setError(null);
            try {
              const c = await api<Case>(`/api/v1/instruments/${id}/release-requests`, {
                method: "POST",
                body: JSON.stringify({ case_type: type, reason: reason.trim() }),
              });
              router.push(`/cases/${c.id}`);
            } catch (err) {
              setError(errorText(err));
              setBusy(false);
            }
          }}
          style={{ display: "grid", gap: 16 }}
        >
          <div className="segmented" role="group">
            {TYPES.map((k) => (
              <button type="button" key={k} aria-pressed={type === k} onClick={() => setType(k)}>{t(`cases.type.${k}`)}</button>
            ))}
          </div>
          <div className="field">
            <label htmlFor="reason">{t("cases.request.reason")}</label>
            <textarea id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          {error && <p className="note neg">{error}</p>}
          <div className="form-actions" style={{ marginTop: 0 }}>
            <button type="submit" className="btn primary" disabled={busy}>{t("common.submit")}</button>
          </div>
        </form>
      </section>
    </>
  );
}

function Routed() {
  const { id } = useParams<{ id: string }>();
  return (
    <Shell roles={["institution"]}>
      <RequestForm id={id} />
    </Shell>
  );
}

export default function RequestPage() {
  return (
    <Suspense>
      <Routed />
    </Suspense>
  );
}
