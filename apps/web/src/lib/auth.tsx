"use client";

// Keycloak login with the authorization-code flow and PKCE (public client, no secret in the browser).

import { User, UserManager, WebStorageStateStore } from "oidc-client-ts";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { config } from "./config";

export type Role =
  | "institution"
  | "scrutiny_officer"
  | "verifying_officer"
  | "competent_authority"
  | "auditor"
  | "admin"
  | "bank_service";

const KNOWN: Role[] = [
  "institution",
  "scrutiny_officer",
  "verifying_officer",
  "competent_authority",
  "auditor",
  "admin",
  "bank_service",
];

let manager: UserManager | null = null;
function userManager(): UserManager {
  if (!manager) {
    manager = new UserManager({
      authority: `${config.keycloakUrl}/realms/${config.keycloakRealm}`,
      client_id: config.keycloakClientId,
      redirect_uri: `${window.location.origin}/auth/callback`,
      post_logout_redirect_uri: window.location.origin,
      response_type: "code",
      scope: "openid profile email",
      automaticSilentRenew: true,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    });
  }
  return manager;
}

function rolesOf(user: User | null): Role[] {
  if (!user) return [];
  try {
    const payload = JSON.parse(atob(user.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    const roles: string[] = payload?.realm_access?.roles ?? [];
    return KNOWN.filter((r) => roles.includes(r));
  } catch {
    return [];
  }
}

type AuthState = {
  ready: boolean;
  user: User | null;
  roles: Role[];
  username: string | null;
  token: string | null;
  has: (...roles: Role[]) => boolean;
  login: (returnTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  completeLogin: () => Promise<string>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const um = userManager();
    um.getUser().then((u) => {
      setUser(u && !u.expired ? u : null);
      setReady(true);
    });
    const onLoaded = (u: User) => setUser(u);
    const onUnloaded = () => setUser(null);
    um.events.addUserLoaded(onLoaded);
    um.events.addUserUnloaded(onUnloaded);
    return () => {
      um.events.removeUserLoaded(onLoaded);
      um.events.removeUserUnloaded(onUnloaded);
    };
  }, []);

  const login = useCallback(async (returnTo?: string) => {
    await userManager().signinRedirect({ state: { returnTo: returnTo ?? window.location.pathname } });
  }, []);

  const logout = useCallback(async () => {
    await userManager().signoutRedirect();
  }, []);

  const completeLogin = useCallback(async () => {
    const u = await userManager().signinRedirectCallback();
    setUser(u);
    const state = u.state as { returnTo?: string } | undefined;
    return state?.returnTo && state.returnTo !== "/auth/callback" ? state.returnTo : "/";
  }, []);

  const value = useMemo<AuthState>(() => {
    const roles = rolesOf(user);
    return {
      ready,
      user,
      roles,
      username: (user?.profile?.preferred_username as string | undefined) ?? null,
      token: user?.access_token ?? null,
      has: (...wanted: Role[]) => wanted.some((r) => roles.includes(r)),
      login,
      logout,
      completeLogin,
    };
  }, [user, ready, login, logout, completeLogin]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function homeFor(roles: Role[]): string {
  if (roles.includes("institution") && roles.length === 1) return "/my";
  if (roles.includes("bank_service") && roles.length === 1) return "/bank";
  return "/overview";
}
