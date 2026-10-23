"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { errorText, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { DocumentInfo, InstrumentSummary } from "@/lib/types";

type Result = {
  sha256: string;
  matched: boolean;
  matches: { document: DocumentInfo; instrument: InstrumentSummary; chain_intact: boolean; broken_at_seq: number | null }[];
};

function Verify() {
  const { t, dateTime } = useI18n();
  const api = useApi();
  const input = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function check(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      setResult(await api<Result>("/api/v1/verify-file", { method: "POST", body: form }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("verify.title")}</h1>
          <p className="sub">{t("verify.sub")}</p>
        </div>
      </div>
      <div className="grid top">
        <section className="span-5">
          <label
            className="drop"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) check(f);
            }}
          >
            <span style={{ fontWeight: 500, color: "var(--text)" }}>{busy ? t("common.loading") : t("verify.choose")}</span>
            <span className="small">PNG · JPG · PDF</span>
            <input ref={input} type="file" hidden onChange={(e) => e.target.files?.[0] && check(e.target.files[0])} />
          </label>
        </section>
        <section className="panel span-7">
          {error && <p className="note neg">{error}</p>}
          {!result && !error && <p className="muted">sha256</p>}
          {result && (
            <>
              <p className="mono small muted" style={{ wordBreak: "break-all" }}>sha256 {result.sha256}</p>
              {!result.matched ? (
                <p className="note warn" style={{ marginTop: 12 }}>{t("verify.nomatch")}</p>
              ) : (
                <div className="rows" style={{ marginTop: 8 }}>
                  {result.matches.map((m) => (
                    <div className="row" key={m.document.id} style={{ alignItems: "flex-start" }}>
                      <span className="grow">
                        {t("verify.match", {
                          date: dateTime(m.document.uploaded_at),
                          institution: m.instrument.institution?.name ?? "",
                          kind: m.document.kind,
                          version: m.document.version,
                        })}
                        <span className="line2">
                          <Link className="card-link" href={`/instruments/${m.instrument.id}`}>{m.instrument.instrument_no}</Link>
                        </span>
                      </span>
                      <span className={`pill ${m.chain_intact ? "pos" : "neg"}`}>
                        {m.chain_intact ? t("verify.chainOk") : t("verify.chainBroken", { seq: m.broken_at_seq ?? "?" })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}

export default function VerifyPage() {
  return (
    <Shell>
      <Verify />
    </Shell>
  );
}
