from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def test_health_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_list_get_task():
    create = client.post(
        "/api/v1/tasks",
        json={"prompt": "create class dto", "repoPath": "/tmp/repo", "mode": "local"},
    )
    assert create.status_code == 200
    data = create.json()
    task_id = data["taskId"]

    listed = client.get("/api/v1/tasks")
    assert listed.status_code == 200
    assert any(t["taskId"] == task_id for t in listed.json())

    fetched = client.get(f"/api/v1/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["taskId"] == task_id


def test_savings_metrics_endpoint():
    response = client.get("/api/v1/tasks/metrics/savings")
    assert response.status_code == 200
    body = response.json()
    assert "totalTasks" in body
    assert "localOnlyRate" in body


def test_savings_metrics_per_project_endpoint():
    client.post(
        "/api/v1/tasks",
        json={"prompt": "create class dto", "repoPath": "/tmp/proj-a", "mode": "local"},
    )
    client.post(
        "/api/v1/tasks",
        json={"prompt": "create class dto", "repoPath": "/tmp/proj-b", "mode": "local"},
    )

    response = client.get("/api/v1/tasks/metrics/savings/projects")
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert len(rows) >= 2
    assert all("repoPath" in row for row in rows)
    assert all("totalTasks" in row for row in rows)
