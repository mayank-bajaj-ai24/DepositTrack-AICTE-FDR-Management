"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Shell } from "@/components/Shell";
import { ErrorBox, Loading, StatePill, TrustLadder } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { InstrumentSummary } from "@/lib/types";

const PAGE = 50;
const FILTERS = ["", "scrutiny", "active", "expiring", "overdue", "released"] as const;

function List() {
  const { t, money, date, number } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const state = params.get("state") ?? "";
  const flagged = params.get("flagged") === "true";
  const [q, setQ] = useState(params.get("q") ?? "");
  const filterKey = `${state}|${flagged}|${q}`;
  const [paging, setPaging] = useState({ key: filterKey, offset: 0 });
  const offset = paging.key === filterKey ? paging.offset : 0;
  const setOffset = (value: number) => setPaging({ key: filterKey, offset: value });

  const query = new URLSearchParams();
  if (state) query.append("state", state);
  if (flagged) query.set("flagged", "true");
  if (q.trim()) query.set("q", q.trim());
  query.set("limit", String(PAGE));
  query.set("offset", String(offset));
  const res = useResource<{ total: number; items: InstrumentSummary[] }>(`/api/v1/instruments?${query}`);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`/instruments?${next}`);
  };

  const total = res.data?.total ?? 0;
  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("list.title")}</h1>
          <p className="sub">{t("list.sub")}</p>
        </div>
      </div>
      <div className="toolbar">
        <input
          className="input"
          type="search"
          placeholder={t("list.search")}
          aria-label={t("common.search")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="segmented" role="group">
          {FILTERS.map((f) => (
            <button key={f || "all"} aria-pressed={state === f && !flagged} onClick={() => { setParam("flagged", null); setParam("state", f || null); }}>
              {f ? t(`state.${f}`) : t("list.filter.all")}
            </button>
          ))}
          <button aria-pressed={flagged} onClick={() => setParam("flagged", flagged ? null : "true")}>{t("list.filter.flagged")}</button>
        </div>
        <span className="spacer" />
        {res.data && <span className="muted num">{t("common.total", { n: number(total) })}</span>}
      </div>
      {res.error && <ErrorBox error={res.error} onRetry={res.reload} />}
      <section className="panel flush">
        {!res.data && res.loading ? (
          <div style={{ padding: 20 }}><Loading rows={8} /></div>
        ) : res.data && res.data.items.length === 0 ? (
          <div style={{ padding: 20 }}><p className="empty">{t("list.empty")}</p></div>
        ) : (
          <div className="table-wrap">
            <table className="responsive">
              <thead>
                <tr>
                  <th>{t("col.institution")}</th>
                  <th>{t("col.fdr")}</th>
                  <th className="hide-sm">{t("col.bank")}</th>
                  <th className="n">{t("col.amount")}</th>
                  <th className="n hide-sm">{t("col.maturity")}</th>
                  <th>{t("col.state")}</th>
                  <th className="hide-sm">{t("col.trust")}</th>
                  <th className="n hide-sm">{t("col.flags")}</th>
                </tr>
              </thead>
              <tbody>
                {res.data?.items.map((i) => (
                  <tr key={i.id} className="link-row" onClick={() => router.push(`/instruments/${i.id}`)}>
                    <td>
                      <a href={`/instruments/${i.id}`} onClick={(e) => e.preventDefault()} className="truncate" style={{ display: "block" }}>
                        {i.institution?.name}
                      </a>
                      <span className="sub">{i.institution?.aicte_id}</span>
                    </td>
                    <td className="mono">{i.instrument_no}</td>
                    <td className="hide-sm truncate">{i.bank_name ?? "—"}</td>
                    <td className="n num">{money(i.amount)}</td>
                    <td className="n num hide-sm">{date(i.maturity_date)}</td>
                    <td><StatePill state={i.state} /></td>
                    <td className="hide-sm"><TrustLadder level={i.trust_level} label={false} /></td>
                    <td className="n num hide-sm" style={i.open_flags ? { color: "var(--negative)" } : { color: "var(--muted)" }}>
                      {i.open_flags || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {total > PAGE && (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <span className="muted num">{t("list.range", { from: offset + 1, to: Math.min(offset + PAGE, total), total })}</span>
          <span className="spacer" />
          <button className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>‹</button>
          <button className="btn small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>›</button>
        </div>
      )}
    </>
  );
}

export default function InstrumentsPage() {
  return (
    <Shell roles={["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"]}>
      <Suspense>
        <List />
      </Suspense>
    </Shell>
  );
}
