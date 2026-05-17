from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api import tasks as tasks_module


client = TestClient(app)


def test_diagnostics_endpoint_exists():
    response = client.get('/api/v1/health/diagnostics')
    assert response.status_code == 200
    body = response.json()
    assert 'local_provider' in body
    assert 'warnings' in body


def test_optional_local_token_guard(monkeypatch):
    monkeypatch.setenv('HYBRID_AI_LOCAL_TOKEN', 'secret123')
    # no header should fail when token is configured
    bad = client.get('/api/v1/tasks')
    assert bad.status_code == 401

    ok = client.get('/api/v1/tasks', headers={'x-local-token': 'secret123'})
    assert ok.status_code == 200
