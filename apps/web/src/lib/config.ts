// Runtime configuration, read from NEXT_PUBLIC_* environment variables (see .env.example).
// Next.js inlines these at build time, so each one is referenced by its full name.

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name} is not set. Copy apps/web/.env.example to .env.local.`);
  }
  return value.replace(/\/$/, "");
}

export const config = {
  apiUrl: required("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL),
  keycloakUrl: required("NEXT_PUBLIC_KEYCLOAK_URL", process.env.NEXT_PUBLIC_KEYCLOAK_URL),
  keycloakRealm: required("NEXT_PUBLIC_KEYCLOAK_REALM", process.env.NEXT_PUBLIC_KEYCLOAK_REALM),
  keycloakClientId: required("NEXT_PUBLIC_KEYCLOAK_CLIENT_ID", process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID),
};
