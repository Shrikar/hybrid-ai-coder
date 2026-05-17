from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"
