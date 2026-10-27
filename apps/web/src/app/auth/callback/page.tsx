"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Mark } from "@/components/Mark";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function Callback() {
  const { completeLogin } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    completeLogin()
      .then((to) => router.replace(to))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [completeLogin, router]);

  return (
    <main className="callback" aria-busy={!error}>
      <Mark size={28} />
      <h1>{error ? t("auth.failed") : t("auth.completing")}</h1>
      {!error && <span className="callback-bar" aria-hidden="true" />}
      {error && <p className="note neg">{error}</p>}
    </main>
  );
}
