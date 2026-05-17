import pytest

from backend.executors.ai_router_executor import RouterDecision
from backend.models.task_models import TaskMode
from backend.router.task_router import TaskRouter


class StubAIRouter:
    def __init__(self, decision=None, should_fail: bool = False):
        self.decision = decision
        self.should_fail = should_fail

    async def decide(self, **kwargs):
        if self.should_fail:
            raise RuntimeError("router unavailable")
        return self.decision


@pytest.mark.asyncio
async def test_local_first_default_for_crud_prompt():
    router = TaskRouter(complexity_threshold=50, local_retry_limit=2, ai_executor=None)
    decision = await router.route("create class for crud dto mapping", TaskMode.auto)
    assert decision.model == "local"
    assert decision.reason == "local_first_default"


@pytest.mark.asyncio
async def test_explicit_modes_override():
    router = TaskRouter(ai_executor=None)
    assert (await router.route("anything", TaskMode.local)).model == "local"
    assert (await router.route("anything", TaskMode.gpt)).model == "gpt"


@pytest.mark.asyncio
async def test_ai_router_drives_decision_when_confident():
    ai = StubAIRouter(
        RouterDecision(model="gpt", confidence=0.91, reason="complex_arch", complexity=83)
    )
    router = TaskRouter(complexity_threshold=20, local_retry_limit=2, ai_executor=ai)
    decision = await router.route("build architecture for secure distributed migration", TaskMode.auto)
    assert decision.model == "gpt"
    assert decision.reason.startswith("ai_router:")
    assert decision.confidence == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_ai_router_fallback_to_rules_on_failure():
    router = TaskRouter(complexity_threshold=20, local_retry_limit=2, ai_executor=StubAIRouter(should_fail=True))
    prompt = "architecture security distributed transaction design for migration with concurrency in kafka"
    decision = await router.route(prompt, TaskMode.auto)
    assert decision.model == "gpt"
    assert decision.reason == "high_risk_and_high_complexity"


@pytest.mark.asyncio
async def test_retry_based_escalation():
    router = TaskRouter(local_retry_limit=2, ai_executor=None)
    decision = await router.route("simple change", TaskMode.auto, retryCount=2)
    assert decision.model == "gpt"
    assert decision.reason == "local_retry_limit_exceeded"
