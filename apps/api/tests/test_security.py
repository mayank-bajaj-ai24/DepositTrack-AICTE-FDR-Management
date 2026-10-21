from fastapi import Depends

from app.core.permissions import Action
from app.core.security import require


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_me_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401


def test_me_returns_roles_and_permissions(client, make_token):
    response = client.get("/api/v1/me", headers=auth(make_token(["auditor"], username="aud")))
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "aud"
    assert body["roles"] == ["auditor"]
    assert "audit:read" in body["permissions"]


def test_keycloak_default_roles_are_ignored(client, make_token):
    token = make_token(["institution", "offline_access", "default-roles-depositrack"])
    assert client.get("/api/v1/me", headers=auth(token)).json()["roles"] == ["institution"]


def test_expired_token_rejected(client, make_token):
    token = make_token(expires_in=-10)
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_wrong_issuer_rejected(client, make_token):
    token = make_token(issuer="http://evil.example/realms/x")
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_unknown_client_rejected(client, make_token):
    token = make_token(azp="some-other-client")
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_bad_signature_rejected(client, make_token, other_rsa_key):
    token = make_token(key=other_rsa_key)
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_require_dependency_allows_and_denies(client, make_token):
    @client.app.get("/_test/approve")
    def approve(principal=Depends(require(Action.RELEASE_APPROVE))):
        return {"ok": True}

    allowed = client.get("/_test/approve", headers=auth(make_token(["competent_authority"])))
    denied = client.get("/_test/approve", headers=auth(make_token(["institution"])))
    assert allowed.status_code == 200
    assert denied.status_code == 403
