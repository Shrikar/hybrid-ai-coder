from backend.models.task_models import TaskCreateRequest, TaskStatus
from backend.storage.task_store import TaskStore


def test_create_fetch_and_update_status(tmp_path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db_path=str(db))
    record = store.create_task(TaskCreateRequest(prompt="hello", repoPath="/tmp/repo"))

    fetched = store.get_task(record.taskId)
    assert fetched is not None
    assert fetched.taskId == record.taskId

    updated = store.update_status(record.taskId, TaskStatus.executing)
    assert updated is not None
    assert updated.status == TaskStatus.executing


def test_persists_across_store_instances(tmp_path):
    db = tmp_path / "tasks.db"
    store1 = TaskStore(db_path=str(db))
    created = store1.create_task(TaskCreateRequest(prompt="persist-me", repoPath="/tmp/repo"))
    store1.update_task(created.taskId, status=TaskStatus.completed, result="done")

    store2 = TaskStore(db_path=str(db))
    fetched = store2.get_task(created.taskId)
    assert fetched is not None
    assert fetched.prompt == "persist-me"
    assert fetched.status == TaskStatus.completed
    assert fetched.result == "done"


def test_recover_interrupted_tasks_is_persistent(tmp_path):
    db = tmp_path / "tasks.db"
    store1 = TaskStore(db_path=str(db))
    created = store1.create_task(TaskCreateRequest(prompt="resume check", repoPath="/tmp/repo"))
    store1.update_task(created.taskId, status=TaskStatus.executing)

    store2 = TaskStore(db_path=str(db))
    recovered = store2.recover_interrupted_tasks()
    assert recovered == 1
    fetched = store2.get_task(created.taskId)
    assert fetched is not None
    assert fetched.status == TaskStatus.failed
