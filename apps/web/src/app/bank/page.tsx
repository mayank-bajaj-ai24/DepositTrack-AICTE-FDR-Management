"use client";

import { Shell } from "@/components/Shell";
import { useI18n } from "@/lib/i18n";

function Bank() {
  const { t } = useI18n();
  return (
    <div className="title-row">
      <div>
        <h1>{t("bank.title")}</h1>
        <p className="sub">{t("bank.body")}</p>
      </div>
    </div>
  );
}

export default function BankPage() {
  return (
    <Shell roles={["bank_service"]}>
      <Bank />
    </Shell>
  );
}
