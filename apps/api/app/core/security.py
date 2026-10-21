"""Keycloak token verification and permission dependencies (M1)."""

import logging
from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.permissions import Action, actions_for, is_allowed, known_roles

logger = logging.getLogger("depositrack.security")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    roles: frozenset[str] = field(default_factory=frozenset)


@lru_cache
def _jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def get_signing_key(token: str, settings: Settings):
    return _jwk_client(settings.jwks_url).get_signing_key_from_jwt(token).key


def decode_token(token: str, key, settings: Settings) -> Principal:
    """Validate signature, expiry, issuer and authorised client; return the caller."""
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    if claims.get("azp") not in settings.allowed_clients:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token issued to an unknown client")

    roles = claims.get("realm_access", {}).get("roles", [])
    return Principal(
        subject=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        roles=frozenset(r.value for r in known_roles(roles)),
    )


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = credentials.credentials
    try:
        key = get_signing_key(token, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    return decode_token(token, key, settings)


def require(action: Action):
    """Dependency factory: allow the request only if the caller's roles grant `action`."""

    def checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not is_allowed(principal.roles, action):
            logger.warning(
                "Denied %s for user=%s roles=%s",
                action.value,
                principal.username,
                sorted(principal.roles),
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not permitted: {action.value}")
        return principal

    return checker


def permissions_of(principal: Principal) -> list[str]:
    return sorted(a.value for a in actions_for(principal.roles))
