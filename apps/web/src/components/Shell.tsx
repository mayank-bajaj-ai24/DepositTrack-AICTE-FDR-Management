"use client";

// The frame: a tinted L of sidebar and 48px top bar, and the white sheet the work sits on.
// The sidebar names the product and the scope; the top bar holds the search (officers), the
// demo-clock stamp and the theme and language switches.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ViewTransition, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Mark } from "@/components/Mark";
import { SignIn } from "@/components/SignIn";
import { useResource } from "@/lib/api";
import { Role, homeFor, useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import type { SystemStatus } from "@/lib/types";

type NavItem = { href: string; key: string; icon: string; roles: Role[]; count?: "queue" };

const OFFICERS: Role[] = ["scrutiny_officer", "verifying_officer", "competent_authority", "auditor", "admin"];
const QUEUE_ROLES: Role[] = ["scrutiny_officer", "verifying_officer"];
export const QUEUE_PATH = "/api/v1/instruments?state=submitted&state=scrutiny&state=discrepancy&state=verified";

const GROUPS: { key: string; items: NavItem[] }[] = [
  {
    key: "nav.group.work",
    items: [
      { href: "/overview", key: "nav.overview", icon: "overview", roles: OFFICERS },
      { href: "/queue", key: "nav.queue", icon: "queue", roles: QUEUE_ROLES, count: "queue" },
      { href: "/instruments", key: "nav.instruments", icon: "instruments", roles: OFFICERS },
      { href: "/cases", key: "nav.cases", icon: "cases", roles: ["scrutiny_officer", "competent_authority"] },
      { href: "/my", key: "nav.my", icon: "my", roles: ["institution"] },
      { href: "/my/submit", key: "nav.submit", icon: "submit", roles: ["institution"] },
      { href: "/bank", key: "nav.bank", icon: "bank", roles: ["bank_service"] },
    ],
  },
  {
    key: "nav.group.oversight",
    items: [
      { href: "/reports", key: "nav.reports", icon: "reports", roles: OFFICERS },
      { href: "/audit", key: "nav.audit", icon: "audit", roles: ["auditor", "admin", "competent_authority"] },
      { href: "/verify", key: "nav.verify", icon: "verify", roles: ["auditor", "institution"] },
      { href: "/admin", key: "nav.admin", icon: "admin", roles: ["admin"] },
    ],
  },
];

// A stable pale tint per person, from their username (identity, not data).
function avatarTint(name: string): { bg: string; ink: string } {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return { bg: `hsl(${h} 45% 90%)`, ink: `hsl(${h} 45% 24%)` };
}

function QueueCount() {
  const res = useResource<{ total: number }>(`${QUEUE_PATH}&limit=1`);
  if (!res.data?.total) return null;
  return <span className="count">{res.data.total}</span>;
}

function Search() {
  const { t } = useI18n();
  const router = useRouter();
  const [q, setQ] = useState("");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <form
      className="search"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) router.push(`/instruments?q=${encodeURIComponent(q.trim())}`);
      }}
    >
      <Icon name="search" size={14} />
      <input id="global-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search.placeholder")} aria-label={t("common.search")} />
      <kbd aria-hidden="true">/</kbd>
    </form>
  );
}

export function Shell({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const auth = useAuth();
  const { t, locale, setLocale, date } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const pathname = usePathname();
  const router = useRouter();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const status = useResource<SystemStatus>(auth.user ? "/api/v1/system/status" : null);

  const allowed = !roles || auth.has(...roles);
  useEffect(() => {
    if (auth.ready && auth.user && !allowed) router.replace(homeFor(auth.roles));
  }, [auth.ready, auth.user, allowed, auth.roles, router]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenOn(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!auth.ready) return null;
  if (!auth.user) return <SignIn />;
  if (!allowed) return null;

  const current = (href: string) =>
    pathname === href || (href !== "/my" && pathname.startsWith(`${href}/`)) ? "page" : undefined;
  const s = status.data;
  const name = auth.username ?? "";
  const tint = avatarTint(name);
  const roleNames = auth.roles.map((r) => t(`role.${r}`)).join(" · ");
  const officer = auth.has(...OFFICERS);
  const otherLocale = locale === "en" ? "hi" : "en";

  return (
    <div className="app">
      <a className="skip" href="#main">{t("nav.skip")}</a>
      <aside className={`sidebar${open ? " open" : ""}`} aria-label={t("nav.menu")}>
        <Link href={homeFor(auth.roles)} className="brand">
          <Mark />
          <span className="brand-name">
            <span>{t("app.name")}</span>
            <span className="brand-scope">{t("app.scope")}</span>
          </span>
        </Link>
        <nav aria-label="Main">
          {GROUPS.map((g) => {
            const items = g.items.filter((n) => auth.has(...n.roles));
            if (!items.length) return null;
            return (
              <div className="nav-group" key={g.key}>
                <p className="group-label">{t(g.key)}</p>
                {items.map((n) => (
                  <Link key={n.href} href={n.href} className="nav-item" aria-current={current(n.href)} onClick={() => setOpenOn(null)}>
                    <Icon name={n.icon} />
                    <span>{t(n.key)}</span>
                    {n.count === "queue" && <QueueCount />}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="bottom">
          <div className="user-row">
            <span className="avatar" style={{ ["--avatar-bg" as string]: tint.bg, ["--avatar-ink" as string]: tint.ink }} aria-hidden="true">
              {name.slice(0, 1).toUpperCase()}
            </span>
            <span className="who">
              <span>{name}</span>
              <span className="role">{roleNames}</span>
            </span>
          </div>
          <button className="nav-item" style={{ border: 0, background: "none", cursor: "pointer", width: "100%" }} onClick={() => auth.logout()}>
            <Icon name="signout" />
            <span>{t("nav.signout")}</span>
          </button>
        </div>
      </aside>
      {open && <div className="nav-scrim" onClick={() => setOpenOn(null)} aria-hidden="true" />}

      <header className="topbar">
        <button className="icon-btn menu-toggle" aria-expanded={open} aria-label={t("nav.menu")} onClick={() => setOpenOn(open ? null : pathname)}>
          <Icon name={open ? "close" : "menu"} />
        </button>
        <Link href={homeFor(auth.roles)} className="brand" aria-label={t("app.name")}>
          <Mark />
          <span className="brand-name">{t("app.name")}</span>
        </Link>
        {officer ? <Search /> : <span className="spacer" />}
        <div className="top-actions">
          {s && s.clock_offset_days > 0 && <span className="stamp">{t("banner.clock.short", { date: date(s.today) })}</span>}
          <button className="icon-btn lang-btn" onClick={() => setLocale(otherLocale)} lang={otherLocale}>
            {t("nav.language")}
          </button>
          <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "dark" ? t("theme.light") : t("theme.dark")} title={theme === "dark" ? t("theme.light") : t("theme.dark")}>
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
        </div>
      </header>

      <main className="sheet" id="main">
        <div className="canvas">
          {s?.demo_policy && <p className="banner">{t("banner.demo")}</p>}
          {s && !s.demo_policy && s.unconfirmed.length > 0 && <p className="banner">{t("banner.awaiting", { list: s.unconfirmed.join(", ") })}</p>}
          {s && s.clock_offset_days > 0 && <p className="banner">{t("banner.clock", { date: date(s.today), days: s.clock_offset_days })}</p>}
          <ViewTransition enter="page" exit="page" default="none">
            <div>{children}</div>
          </ViewTransition>
        </div>
      </main>
    </div>
  );
}
