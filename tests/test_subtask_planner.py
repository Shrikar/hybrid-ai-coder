from backend.services.subtask_planner import SubtaskPlanner


def test_planner_splits_then_and_sets_preferences():
    planner = SubtaskPlanner()
    subtasks = planner.plan(
        "Setup Java Spring Boot base project then wire Vaadin UI with button and label"
    )

    assert len(subtasks) == 2
    assert subtasks[0].preferred_model == "local"
    assert subtasks[1].preferred_model == "cloud"


def test_planner_local_first_for_generic_prompt():
    planner = SubtaskPlanner()
    subtasks = planner.plan("create dto and repository class")
    assert len(subtasks) == 1
    assert subtasks[0].preferred_model == "local"
