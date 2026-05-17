from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api import tasks as tasks_api
from backend.models.task_models import TaskCreateRequest, TaskStatus


client = TestClient(app)


def test_ui_home_loads():
    r = client.get('/ui')
    assert r.status_code == 200
    assert 'Hybrid AI Coder' in r.text
    assert 'id="toast"' in r.text
    assert 'id="run-task-status"' in r.text
    assert 'id="run-skill-status"' in r.text


def test_ui_task_list_partial_loads():
    r = client.get('/ui/tasks')
    assert r.status_code == 200


def test_ui_detail_partial_loads_for_created_task():
    create = client.post('/api/v1/tasks', json={'prompt': 'create class dto', 'repoPath': '/tmp/repo', 'mode': 'local'})
    task_id = create.json()['taskId']
    r = client.get(f'/ui/tasks/{task_id}')
    assert r.status_code == 200
    assert 'Hybrid AI Coder' in r.text
    assert task_id in r.text
    assert 'Router Decision' in r.text
    assert 'Confidence' in r.text
    assert 'Review Panel' in r.text


def test_ui_detail_returns_partial_for_htmx_request():
    create = client.post('/api/v1/tasks', json={'prompt': 'create class dto', 'repoPath': '/tmp/repo', 'mode': 'local'})
    task_id = create.json()['taskId']
    r = client.get(f'/ui/tasks/{task_id}', headers={'HX-Request': 'true'})
    assert r.status_code == 200
    assert 'Hybrid AI Coder' not in r.text
    assert 'Router Decision' in r.text


def test_ui_task_list_shows_pending_file_count(tmp_path):
    req = TaskCreateRequest(prompt='manual approval flow', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.awaiting_approval, requiresApproval=True)
    tasks_api._task_store.set_pending_approval(
        task.taskId,
        [{'path': 'README.md', 'content': '# proposed'}],
    )

    r = client.get('/ui/tasks')
    assert r.status_code == 200
    assert 'Pending files: 1' in r.text


def test_approve_redirects_to_full_ui_with_task_query(tmp_path):
    req = TaskCreateRequest(prompt='manual approval flow', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.awaiting_approval, requiresApproval=True)
    tasks_api._task_store.set_pending_approval(
        task.taskId,
        [{'path': 'README.md', 'content': '# proposed'}],
    )

    res = client.post(f'/ui/tasks/{task.taskId}/approve', follow_redirects=False)
    assert res.status_code == 303
    assert res.headers['location'] == f'/ui?task_id={task.taskId}'


def test_review_panel_shows_diff_for_pending_approval(tmp_path):
    req = TaskCreateRequest(prompt='manual approval flow', repoPath=str(tmp_path), mode='local')
    task = tasks_api._task_store.create_task(req)
    tasks_api._task_store.update_task(task.taskId, status=TaskStatus.awaiting_approval, requiresApproval=True)
    tasks_api._task_store.set_pending_approval(
        task.taskId,
        [{'path': 'README.md', 'content': '# proposed'}],
    )

    r = client.get(f'/ui/tasks/{task.taskId}', headers={'HX-Request': 'true'})
    assert r.status_code == 200
    assert 'Review Panel' in r.text
    assert 'a/README.md' in r.text
    assert 'b/README.md' in r.text


def test_ui_create_task_accepts_file_upload():
    files = {"attachments": ("notes.txt", b"line1\nline2\n", "text/plain")}
    data = {"prompt": "use attached file", "repo_path": "/tmp/repo", "mode": "local"}
    r = client.post("/ui/tasks/create", data=data, files=files)
    assert r.status_code == 200
