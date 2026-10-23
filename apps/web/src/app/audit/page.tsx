"use client";

// Audit: "Is the record intact, and was the procedure followed?"

import Link from "next/link";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { InstrumentSummary } from "@/lib/types";

type Chains = { checked: number; broken: { instrument: InstrumentSummary; broken_at_seq: number }[]; system_chain: { intact: boolean; length: number } };
type Anchors = { items: { id: string; batch_start: string; batch_end: string; merkle_root: string; store_tx: string | null; valid: boolean }[] };
type Conformance = {
  constraints_version: string;
  validated_by: string | null;
  constraints: { id: string; description: string }[];
  checked: number;
  conforming_share: number | null;
  violations_by_constraint: Record<string, number>;
  cases: { instrument: InstrumentSummary; violations: { constraint: string; seq: number; explanation: string }[] }[];
};

function Audit() {
  const { t, dateTime, percent, number } = useI18n();
  const chains = useResource<Chains>("/api/v1/audit/chains");
  const anchors = useResource<Anchors>("/api/v1/audit/anchors");
  const conf = useResource<Conformance>("/api/v1/audit/conformance");

  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("audit.title")}</h1>
          <p className="sub">{t("audit.sub")}</p>
        </div>
        <div className="actions">
          <Link className="btn" href="/verify">{t("nav.verify")}</Link>
        </div>
      </div>
      <div className="grid top">
        <section className="panel span-5">
          <header>
            <h2>{t("audit.chains")}</h2>
          </header>
          {chains.error && <ErrorBox error={chains.error} onRetry={chains.reload} />}
          {!chains.data ? (
            <Loading rows={3} />
          ) : chains.data.broken.length === 0 ? (
            <p className="note pos">{t("audit.chains.ok", { n: chains.data.checked })}</p>
          ) : (
            <>
              <p className="note neg">{t("audit.chains.broken", { n: chains.data.broken.length })}</p>
              <div className="rows" style={{ marginTop: 8 }}>
                {chains.data.broken.map((b) => (
                  <Link className="row" key={b.instrument.id} href={`/instruments/${b.instrument.id}`}>
                    <span className="grow truncate">{b.instrument.institution?.name}<span className="line2 mono">{b.instrument.instrument_no}</span></span>
                    <span className="pill neg">#{b.broken_at_seq}</span>
                  </Link>
                ))}
              </div>
            </>
          )}

          <h3 style={{ fontSize: 14, fontWeight: 500, margin: "20px 0 4px" }}>{t("audit.anchors")}</h3>
          {!anchors.data ? (
            <Loading rows={2} />
          ) : anchors.data.items.length === 0 ? (
            <p className="muted">{t("audit.anchors.none")}</p>
          ) : (
            <div className="rows">
              {anchors.data.items.slice(0, 5).map((a) => (
                <div className="row" key={a.id}>
                  <span className="grow">
                    <span className="mono">{a.merkle_root.slice(0, 16)}…</span>
                    <span className="line2">{dateTime(a.batch_end)}{a.store_tx ? ` · immudb tx ${a.store_tx}` : ""}</span>
                  </span>
                  <span className={`pill ${a.valid ? "pos" : "neg"}`}>{a.valid ? t("audit.anchor.valid") : t("audit.anchor.invalid")}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel span-7">
          <header>
            <h2>{t("audit.conformance")}</h2>
            {conf.data && <span className="meta">{conf.data.constraints_version}</span>}
          </header>
          {conf.error && <ErrorBox error={conf.error} onRetry={conf.reload} />}
          {!conf.data ? (
            <Loading rows={4} />
          ) : (
            <>
              <p className="figure-lead num">{percent(conf.data.conforming_share)}</p>
              <p className="muted">{t("audit.conformance.share", { p: percent(conf.data.conforming_share) })} · {number(conf.data.checked)}</p>
              {!conf.data.validated_by && <p className="note warn" style={{ marginTop: 12 }}>{t("audit.conformance.unvalidated")}</p>}
              <div className="rows" style={{ marginTop: 12 }}>
                {conf.data.constraints.map((c) => (
                  <div className="row" key={c.id}>
                    <span className="grow">{c.description}</span>
                    <span className="num" style={conf.data!.violations_by_constraint[c.id] ? { color: "var(--negative)" } : { color: "var(--muted)" }}>
                      {conf.data!.violations_by_constraint[c.id] || "—"}
                    </span>
                  </div>
                ))}
              </div>
              {conf.data.cases.length > 0 && (
                <div className="rows" style={{ marginTop: 12 }}>
                  {conf.data.cases.slice(0, 6).map((c) => (
                    <Link className="row" key={c.instrument.id} href={`/instruments/${c.instrument.id}`}>
                      <span className="grow">
                        <span className="truncate" style={{ display: "block" }}>{c.instrument.institution?.name}</span>
                        <span className="line2">{c.violations.map((v) => `#${v.seq} ${v.explanation}`).join(" · ")}</span>
                      </span>
                    </Link>
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

export default function AuditPage() {
  return (
    <Shell roles={["auditor", "admin", "competent_authority"]}>
      <Audit />
    </Shell>
  );
}
