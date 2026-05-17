from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def test_project_mode_discover_returns_questions_partial():
    res = client.post(
        "/ui/projects/discover",
        data={"goal": "Build inventory management app", "repo_path": "/tmp/project", "mode": "auto"},
    )
    assert res.status_code == 200
    assert "Clarifying Questions" in res.text
    assert 'name="outcome"' in res.text
    assert 'name="scope"' in res.text
    assert 'name="auto_execute"' in res.text


def test_project_mode_execute_creates_tasks():
    res = client.post(
        "/ui/projects/execute",
        data={
            "goal": "Build todo service",
            "repo_path": "/tmp/project",
            "mode": "local",
            "outcome": "Users can CRUD todos",
            "scope": "Create models\nCreate endpoints",
            "stack": "Spring Boot + Postgres",
            "quality": "Unit tests",
            "constraints": "Keep it simple",
            "auto_execute": "",
        },
    )
    assert res.status_code == 200
    assert "Project Plan" in res.text
    assert "Generated Tasks" in res.text
    assert "Created Task Records" in res.text
