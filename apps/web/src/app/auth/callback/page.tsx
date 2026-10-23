"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
    <main className="canvas" style={{ maxWidth: 520, paddingTop: "18vh" }}>
      <h1 style={{ fontSize: 20, fontWeight: 600 }}>{error ? t("auth.failed") : t("auth.completing")}</h1>
      {error && <p className="note neg" style={{ marginTop: 12 }}>{error}</p>}
    </main>
  );
}
