"use client";

// Submit an FDR: upload the scan, confirm the fields read from it (those needing a look are
// marked), submit. The institution's confirmed values are the declared values (Trust Ladder L0).

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { Shell } from "@/components/Shell";
import { errorText, useApi, useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { FIELD_ORDER, type ExtractionPreview, type InstrumentDetail } from "@/lib/types";

const DATE_FIELDS = new Set(["issue_date", "maturity_date"]);
const WIDE = new Set(["amount_words", "lien_text", "depositor", "beneficiary"]);

function Submit() {
  const { t } = useI18n();
  const api = useApi();
  const router = useRouter();
  const params = useSearchParams();
  const replaces = params.get("replaces");
  const previous = useResource<InstrumentDetail>(replaces ? `/api/v1/instruments/${replaces}` : null);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ExtractionPreview | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const imageUrl = useMemo(() => (file && file.type.startsWith("image/") ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);
  const step = preview ? 2 : 1;

  async function read(f: File) {
    setFile(f);
    setPreview(null);
    setError(null);
    setBusy(true);
    const form = new FormData();
    form.append("file", f);
    try {
      const p = await api<ExtractionPreview>("/api/v1/extract", { method: "POST", body: form });
      setPreview(p);
      setValues(Object.fromEntries(FIELD_ORDER.map((k) => [k, p.fields[k]?.value ?? ""])));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("declared", JSON.stringify(values));
    form.append("kind", "fdr");
    if (replaces) form.append("replaces_id", replaces);
    try {
      const r = await api<{ id: string }>("/api/v1/instruments", { method: "POST", body: form });
      router.push(`/instruments/${r.id}`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("submit.title")}</h1>
          <p className="sub">
            {previous.data ? t("submit.renewalOf", { fdr: previous.data.instrument.instrument_no }) + " · " : ""}
            {t("submit.sub")}
          </p>
        </div>
      </div>
      <ol className="steps" aria-label={t("submit.steps")}>
        {[1, 2, 3].map((n) => (
          <li key={n} aria-current={step === n ? "step" : undefined}>
            <span className="n num">{step > n ? <Icon name="check" size={12} /> : n}</span>
            {t(`submit.step.${n}`)}
          </li>
        ))}
      </ol>
      {error && <p className="note note-in neg" style={{ marginBottom: 16 }} role="alert">{error}</p>}
      <div className="grid top">
        <section className="span-4 stack">
          <label
            className={`drop${over ? " over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f) read(f);
            }}
          >
            <Icon name="upload" size={24} />
            <span style={{ fontWeight: 500, color: "var(--text)" }}>{busy && !preview ? t("submit.reading") : file ? file.name : t("submit.drop")}</span>
            <span className="small" id="file-hint">{file ? t("submit.replace") : t("submit.limits")}</span>
            <input ref={input} type="file" accept="image/png,image/jpeg" className="visually-hidden" aria-describedby="file-hint" onChange={(e) => e.target.files?.[0] && read(e.target.files[0])} />
          </label>
          {imageUrl && file && (
            <figure className={`scan${busy && !preview ? " reading" : ""}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl} alt={file.name} />
            </figure>
          )}
        </section>
        <section className="panel span-8">
          <header>
            <div>
              <h2>{t("submit.confirm")}</h2>
              <p className="meta" style={{ marginTop: 2 }}>{t("submit.confirmSub")}</p>
            </div>
          </header>
          {!preview ? (
            // Before a scan: the fields that will be read, each still a dash, in the form's order.
            <div className="rows" aria-busy={busy}>
              {FIELD_ORDER.map((k) => (
                <div className="row" key={k}>
                  <span className="grow muted">{t(`field.${k}`)}</span>
                  {busy ? <span className="skeleton" style={{ width: 140, height: 14 }} /> : <span className="muted">—</span>}
                </div>
              ))}
            </div>
          ) : (
            <form onSubmit={submit}>
              <div className="form-grid">
                {FIELD_ORDER.map((k) => {
                  const info = preview.fields[k];
                  const attention = info?.needs_review;
                  return (
                    <div className="field" key={k} style={WIDE.has(k) ? { gridColumn: "1 / -1" } : undefined}>
                      <label htmlFor={k}>{t(`field.${k}`)}</label>
                      <input
                        id={k}
                        className={`input${attention ? " attention" : ""}${k === "fdr_no" || k === "ifsc" ? " mono" : ""}`}
                        type={DATE_FIELDS.has(k) ? "date" : "text"}
                        inputMode={k === "amount" ? "decimal" : undefined}
                        value={values[k] ?? ""}
                        onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                        required={k === "fdr_no"}
                      />
                      {attention && <span className="warn">{t("submit.review")}{info?.reason ? ` · ${info.reason}` : ""}</span>}
                    </div>
                  );
                })}
              </div>
              <div className="form-actions">
                <button type="submit" className="btn primary" disabled={busy}>{t("common.submit")}</button>
              </div>
            </form>
          )}
        </section>
      </div>
    </>
  );
}

export default function SubmitPage() {
  return (
    <Shell roles={["institution"]}>
      <Suspense>
        <Submit />
      </Suspense>
    </Shell>
  );
}
