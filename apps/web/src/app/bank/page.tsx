"use client";

// Bank service: an account the bank channel uses, with no work screen of its own. It answers
// "Is our channel to DepositTrack working, and what happens to an attestation we send?"

import { Shell } from "@/components/Shell";
import { ErrorBox, Loading } from "@/components/ui";
import { useResource } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Me, SystemStatus } from "@/lib/types";

function Bank() {
  const { t } = useI18n();
  const status = useResource<SystemStatus>("/api/v1/system/status");
  const me = useResource<Me>("/api/v1/me");
  const s = status.data;
  return (
    <>
      <div className="title-row">
        <div>
          <h1>{t("bank.title")}</h1>
          <p className="sub">{t("bank.body")}</p>
        </div>
      </div>
      <div className="grid top">
        <section className="panel span-5">
          <header>
            <h2>{t("bank.channel")}</h2>
          </header>
          {status.error && <ErrorBox error={status.error} onRetry={status.reload} />}
          {!s ? (
            <Loading rows={3} />
          ) : (
            <dl className="kv">
              <dt>{t("bank.code")}</dt>
              <dd className="mono">{me.data?.bank_code ?? "—"}</dd>
              <dt>{t("admin.bank.channel")}</dt>
              <dd>{s.bank_channel_configured ? t("admin.bank.configured") : t("admin.bank.missing")}</dd>
              <dt>{t("admin.bank.keys")}</dt>
              <dd className="num">{s.bank_keys_pinned}</dd>
            </dl>
          )}
        </section>
        <section className="panel span-7">
          <header>
            <h2>{t("bank.flow")}</h2>
          </header>
          <ol className="rows">
            {[1, 2, 3, 4].map((n) => (
              <li className="row" key={n}>
                <span className="lv-badge num">{n}</span>
                <span className="grow">
                  {t(`bank.flow.${n}`)}
                  <span className="line2">{t(`bank.flow.${n}.sub`)}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}

export default function BankPage() {
  return (
    <Shell roles={["bank_service"]}>
      <Bank />
    </Shell>
  );
}
