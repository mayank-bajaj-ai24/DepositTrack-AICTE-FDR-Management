def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_policy_status_lists_unconfirmed_values(client):
    response = client.get("/api/v1/policy/status")
    assert response.status_code == 200
    assert "deposit_requirements" in response.json()["unconfirmed"]
