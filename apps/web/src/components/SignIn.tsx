"use client";

// Sign-in: the one screen read rather than worked in. It says what DepositTrack is, offers one
// action, and shows the Trust Ladder every FDR climbs, in words and as the 3D scene beside them.

import { useMemo } from "react";
import { Icon } from "@/components/Icon";
import { LadderScene } from "@/components/LadderScene";
import { Mark } from "@/components/Mark";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

const LEVELS = [0, 1, 2, 3, 4];

export function SignIn() {
  const { login } = useAuth();
  const { t, locale, setLocale } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const labels = useMemo(() => [t("signin.receipt"), ...LEVELS.map((l) => `L${l} · ${t(`trust.${l}`)}`)], [t]);
  const otherLocale = locale === "en" ? "hi" : "en";

  return (
    <div className="signin">
      <section className="signin-copy">
        <header className="signin-top">
          <span className="brand">
            <Mark size={24} />
            <span className="brand-name">
              <span>{t("app.name")}</span>
              <span className="brand-scope">{t("app.scope")}</span>
            </span>
          </span>
          <span className="top-actions">
            <button className="icon-btn lang-btn" onClick={() => setLocale(otherLocale)} lang={otherLocale}>{t("nav.language")}</button>
            <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "dark" ? t("theme.light") : t("theme.dark")}>
              <Icon name={theme === "dark" ? "sun" : "moon"} />
            </button>
          </span>
        </header>
        <div className="signin-body">
          <h1>{t("signin.title")}</h1>
          <p className="signin-lead">{t("signin.lead")}</p>
          <div className="signin-actions">
            <button className="btn primary signin-btn" onClick={() => login()}>
              {t("auth.signin")}
              <Icon name="arrow" />
            </button>
            <span className="muted">{t("auth.body")}</span>
          </div>
          <ol className="signin-levels" aria-label={t("trust.explain")}>
            {LEVELS.map((l) => (
              <li key={l} className={l >= 3 ? "bank" : ""} style={{ ["--i" as string]: l }}>
                <span className="lv num">L{l}</span>
                <span>
                  <b>{t(`trust.${l}`)}</b>
                  <span className="muted">{t(`signin.level.${l}`)}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
        <footer className="signin-foot muted small">{t("signin.foot")}</footer>
      </section>
      <section className="signin-stage" aria-label={t("signin.stage")}>
        <LadderScene labels={labels} />
      </section>
    </div>
  );
}
