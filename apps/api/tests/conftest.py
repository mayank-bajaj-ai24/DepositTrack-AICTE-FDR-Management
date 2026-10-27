import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from tests.flow_support import make_sessionmaker

# Tests must not pick up a developer's apps/api/.env (settings for the local stack); modules
# imported above may already have cached settings read from it.
Settings.model_config["env_file"] = None
get_settings.cache_clear()


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(rsa_key, monkeypatch):
    """Test client whose token verification uses a local key instead of Keycloak JWKS, on an
    empty in-memory database, so no test reaches a developer's Postgres (CI has none)."""
    monkeypatch.setattr(security, "get_signing_key", lambda token, settings: rsa_key.public_key())
    factory = make_sessionmaker()

    def session_override():
        with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


@pytest.fixture
def make_token(rsa_key):
    settings = get_settings()

    def _make(
        roles=("institution",),
        *,
        issuer=None,
        azp="depositrack-web",
        expires_in=300,
        key=None,
        username="tester",
    ):
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "preferred_username": username,
            "iss": issuer or settings.keycloak_issuer,
            "azp": azp,
            "iat": now,
            "exp": now + expires_in,
            "realm_access": {"roles": list(roles)},
        }
        return jwt.encode(claims, key or rsa_key, algorithm="RS256")

    return _make
