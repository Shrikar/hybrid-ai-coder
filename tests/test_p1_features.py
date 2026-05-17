from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api import tasks as tasks_api
from backend.models.task_models import TaskCreateRequest, TaskStatus

client = TestClient(app)


def test_events_endpoint_returns_task_events():
    create = client.post('/api/v1/tasks', json={'prompt': 'create class dto', 'repoPath': '/tmp/repo', 'mode': 'local'})
    task_id = create.json()['taskId']
    events = client.get(f'/api/v1/tasks/{task_id}/events')
    assert events.status_code == 200
    body = events.json()
    assert len(body) >= 1
    assert body[0]['taskId'] == task_id


def test_approve_endpoint_applies_pending_files(tmp_path: Path):
    req = TaskCreateRequest(prompt='manual approval flow', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.awaiting_approval, requiresApproval=True)
    tasks_api._task_store.set_pending_approval(
        task.taskId,
        [{'path': 'README.md', 'content': '# approved'}],
    )
    res = client.post(f'/api/v1/tasks/{task.taskId}/approve')
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'completed'
    assert (tmp_path / 'README.md').exists()


def test_approval_preview_endpoint(tmp_path: Path):
    req = TaskCreateRequest(prompt='manual approval flow', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.awaiting_approval, requiresApproval=True)
    (tmp_path / 'README.md').write_text('# existing')
    tasks_api._task_store.set_pending_approval(
        task.taskId,
        [{'path': 'README.md', 'content': '# proposed'}],
    )
    res = client.get(f'/api/v1/tasks/{task.taskId}/approval/preview')
    assert res.status_code == 200
    body = res.json()
    assert body['taskId'] == task.taskId
    assert body['files'][0]['path'] == 'README.md'
    assert '# existing' in body['files'][0]['existing']
    assert '# proposed' in body['files'][0]['proposed']


def test_resume_endpoint_exists_for_failed_tasks(tmp_path: Path):
    req = TaskCreateRequest(prompt='resume me', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.failed, error='previous failure')
    res = client.post(f'/api/v1/tasks/{task.taskId}/resume')
    assert res.status_code == 200
    assert 'status' in res.json()


def test_stream_endpoint_returns_sse_events():
    create = client.post('/api/v1/tasks', json={'prompt': 'create class dto', 'repoPath': '/tmp/repo', 'mode': 'local'})
    task_id = create.json()['taskId']

    response = client.get(f'/api/v1/tasks/{task_id}/events/stream')
    assert response.status_code == 200
    assert len(response.text) > 0
    assert 'task_event' in response.text


def test_stream_endpoint_supports_cursor():
    create = client.post('/api/v1/tasks', json={'prompt': 'create class dto', 'repoPath': '/tmp/repo', 'mode': 'local'})
    task_id = create.json()['taskId']
    events = client.get(f'/api/v1/tasks/{task_id}/events').json()
    last_id = events[0]['eventId'] if events else None
    response = client.get(f'/api/v1/tasks/{task_id}/events/stream', params={'last_event_id': last_id})
    assert response.status_code == 200
