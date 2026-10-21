"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Mark } from "@/components/Mark";
import { useResource } from "@/lib/api";
import { Role, homeFor, useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { SystemStatus } from "@/lib/types";

type NavItem = { href: string; key: string; roles: Role[] };

const OFFICERS: Role[] = ["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"];

const NAV: NavItem[] = [
  { href: "/overview", key: "nav.overview", roles: OFFICERS },
  { href: "/queue", key: "nav.queue", roles: ["scrutiny_officer", "verifying_officer"] },
  { href: "/instruments", key: "nav.instruments", roles: OFFICERS },
  { href: "/cases", key: "nav.cases", roles: ["scrutiny_officer", "competent_authority"] },
  { href: "/reports", key: "nav.reports", roles: ["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"] },
  { href: "/audit", key: "nav.audit", roles: ["auditor", "admin", "competent_authority"] },
  { href: "/admin", key: "nav.admin", roles: ["admin"] },
  { href: "/my", key: "nav.my", roles: ["institution"] },
  { href: "/my/submit", key: "nav.submit", roles: ["institution"] },
  { href: "/verify", key: "nav.verify", roles: ["auditor", "institution"] },
];

function SignIn() {
  const { login } = useAuth();
  const { t, locale, setLocale } = useI18n();
  return (
    <main className="canvas" style={{ maxWidth: 520, paddingTop: "18vh" }}>
      <div className="brand" style={{ marginBottom: 24 }}>
        <Mark size={28} />
        <span>{t("app.name")}</span>
        <span className="brand-scope">{t("app.scope")}</span>
      </div>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>{t("auth.title")}</h1>
      <p className="muted" style={{ marginBottom: 24 }}>{t("auth.body")}</p>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn primary" onClick={() => login()}>{t("auth.signin")}</button>
        <button className="btn ghost" onClick={() => setLocale(locale === "en" ? "hi" : "en")}>{t("nav.language")}</button>
      </div>
    </main>
  );
}

export function Shell({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const auth = useAuth();
  const { t, locale, setLocale, date } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (fn: (o: boolean) => boolean) => setOpenOn(fn(open) ? pathname : null);
  const [scrolled, setScrolled] = useState(false);
  const status = useResource<SystemStatus>(auth.user ? "/api/v1/system/status" : null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const allowed = !roles || auth.has(...roles);
  useEffect(() => {
    if (auth.ready && auth.user && !allowed) router.replace(homeFor(auth.roles));
  }, [auth.ready, auth.user, allowed, auth.roles, router]);

  if (!auth.ready) return null;
  if (!auth.user) return <SignIn />;
  if (!allowed) return null;

  const items = NAV.filter((n) => auth.has(...n.roles));
  const current = (href: string) =>
    pathname === href || (href !== "/my" && pathname.startsWith(`${href}/`)) ? "page" : undefined;
  const s = status.data;

  return (
    <>
      <header className={`topbar${scrolled ? " scrolled" : ""}`}>
        <div className="topbar-inner">
          <Link href={homeFor(auth.roles)} className="brand">
            <Mark />
            <span>{t("app.name")}</span>
            <span className="brand-scope">{t("app.scope")}</span>
          </Link>
          <nav className="navlinks" aria-label="Main">
            {items.map((n) => (
              <Link key={n.href} href={n.href} aria-current={current(n.href)}>
                {t(n.key)}
              </Link>
            ))}
          </nav>
          <span className="spacer" />
          <div className="account">
            <button className="btn ghost small" onClick={() => setLocale(locale === "en" ? "hi" : "en")} lang={locale === "en" ? "hi" : "en"}>
              {t("nav.language")}
            </button>
            <span className="who">{auth.username}</span>
            <button className="btn ghost small who" onClick={() => auth.logout()}>{t("nav.signout")}</button>
            <button className="btn small menu-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
              {t("nav.menu")}
            </button>
          </div>
        </div>
        <nav className={`sheet${open ? " open" : ""}`} aria-label="Menu">
          {items.map((n) => (
            <Link key={n.href} href={n.href} aria-current={current(n.href)}>
              {t(n.key)}
            </Link>
          ))}
          <span className="muted" style={{ padding: "12px 8px 4px" }}>{auth.username}</span>
          <button onClick={() => auth.logout()}>{t("nav.signout")}</button>
        </nav>
      </header>
      <main className="canvas">
        {s?.demo_policy && <p className="banner">{t("banner.demo")}</p>}
        {s && !s.demo_policy && s.unconfirmed.length > 0 && (
          <p className="banner">{t("banner.awaiting", { list: s.unconfirmed.join(", ") })}</p>
        )}
        {s && s.clock_offset_days > 0 && (
          <p className="banner">{t("banner.clock", { date: date(s.today), days: s.clock_offset_days })}</p>
        )}
        {children}
      </main>
    </>
  );
}
