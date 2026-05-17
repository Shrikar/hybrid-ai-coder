from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


def test_list_skills():
    response = client.get('/api/v1/skills')
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert any(s.get('id') == 'spring_boot_scaffold' for s in body)


def test_run_skill_creates_task():
    response = client.post(
        '/api/v1/skills/spring_boot_scaffold/run',
        json={'repoPath': '/tmp/skills-demo', 'userInput': 'Also add health endpoint'},
    )
    assert response.status_code == 200
    data = response.json()
    assert 'taskId' in data
    assert 'status' in data


def test_run_unknown_skill_returns_404():
    response = client.post('/api/v1/skills/unknown_skill/run', json={'repoPath': '/tmp/x', 'userInput': ''})
    assert response.status_code == 404
