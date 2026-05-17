from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from backend.executors.gpt_executor import GPTExecutor
from backend.executors.ollama_executor import OllamaExecutor
from backend.models.task_models import ExecutorResult, TaskCreateRequest, TaskMode, TaskRecord, TaskStatus
from backend.router.task_router import TaskRouter
from backend.services.config_loader import ConfigLoader
from backend.services.context_builder import ContextBuilder
from backend.services.file_applier import ApplyPolicy, FileApplier
from backend.services.policy_engine import PolicyEngine
from backend.services.repo_validator import RepoValidator, ValidationConfig
from backend.services.subtask_planner import Subtask, SubtaskPlanner
from backend.services.webhook_dispatcher import WebhookDispatcher
from backend.storage.task_store import TaskStore


class TaskExecutionService:
    def __init__(
        self,
        task_store: TaskStore,
        router: TaskRouter,
        local_executor: OllamaExecutor,
        gpt_executor: GPTExecutor,
        local_retry_limit: int = 2,
    ) -> None:
        self.task_store = task_store
        self.router = router
        self.local_executor = local_executor
        self.gpt_executor = gpt_executor
        self.local_retry_limit = local_retry_limit
        self.context_builder = ContextBuilder()
        self.subtask_planner = SubtaskPlanner()

        cfg = ConfigLoader().load()
        apply_cfg = cfg.get("apply_policy", {})
        self.file_applier = FileApplier(
            policy=ApplyPolicy(
                max_files_per_apply=int(apply_cfg.get("max_files_per_apply", 25)),
                max_file_size_bytes=int(apply_cfg.get("max_file_size_bytes", 200000)),
                blocked_path_fragments=tuple(apply_cfg.get("blocked_path_fragments", [".git/", ".env", "id_rsa", "id_ed25519"])),
            )
        )

        vcfg = cfg.get("validation", {})
        self.repo_validator = RepoValidator(
            ValidationConfig(
                commands=list(vcfg.get("commands", [])),
                timeout_seconds=int(vcfg.get("timeout_seconds", 180)),
                profiles=list(vcfg.get("profiles", [])),
                stop_on_failure=bool(vcfg.get("stop_on_failure", True)),
            )
        )

        self.policy_engine = PolicyEngine(cfg)
        self.webhook_dispatcher = WebhookDispatcher(cfg.get("webhooks", {}).get("task_events_url"))

    async def create_and_execute(self, request: TaskCreateRequest) -> TaskRecord:
        task = self.task_store.create_task(request)
        self._emit(task.taskId, "execution_started", "Task execution started")
        self.task_store.update_task(task.taskId, status=TaskStatus.executing)

        return await self._run_task(task, attachments=request.attachments)

    async def resume_task(self, task_id: str) -> TaskRecord:
        task = self.task_store.get_task(task_id)
        if task is None:
            raise ValueError("Task not found")

        if task.status not in {TaskStatus.failed, TaskStatus.awaiting_approval}:
            return task

        self._emit(task.taskId, "task_resume", "Task resume requested")
        self.task_store.update_task(task.taskId, status=TaskStatus.executing, error=None, budgetExceeded=False)
        task = self.task_store.get_task(task.taskId)
        return await self._run_task(task)

    def approve_task(self, task_id: str) -> TaskRecord:
        pending = self.task_store.get_pending_approval(task_id)
        if pending is None:
            raise ValueError("No pending approval")

        blocks = [(item["path"], item["content"]) for item in pending.files]
        task = self.task_store.get_task(task_id)
        changed = self.file_applier.apply_blocks(blocks, task.repoPath)
        self.task_store.clear_pending_approval(task_id)

        updated = self.task_store.update_task(
            task_id,
            status=TaskStatus.completed,
            requiresApproval=False,
            changedFiles=changed,
            completedAt=datetime.utcnow(),
        )
        self._emit(task_id, "approval_applied", "Pending changes approved and applied", {"files": len(changed)})
        return updated

    async def _run_task(self, task: TaskRecord, attachments: Optional[list[dict[str, str]]] = None) -> TaskRecord:
        subtasks = self.subtask_planner.plan(task.prompt)
        start_index = max(0, task.currentSubtaskIndex)
        total_subtasks = len(subtasks)
        self.task_store.update_task(task.taskId, totalSubtasks=total_subtasks)
        gpt_calls_used = task.gptCallsUsed
        cumulative_tokens = task.gptTokenEstimate
        cumulative_cost = task.gptCostUsd
        cumulative_changed_files: list[str] = list(task.changedFiles)
        last_error: Optional[str] = None

        for i, subtask in enumerate(subtasks):
            if i < start_index:
                continue
            local_retries = 0
            subtask_done = False
            self.task_store.update_task(task.taskId, currentSubtaskIndex=i, totalSubtasks=total_subtasks)
            self._emit(task.taskId, "subtask_started", f"Starting {subtask.title}")

            while True:
                # Local-first rule: in auto mode never force GPT from planner hints.
                # Router decides escalation only via retry/budget/risk logic.
                model_mode = task.mode

                decision = await self.router.route(
                    prompt=subtask.prompt,
                    mode=model_mode,
                    riskHints=[],
                    retryCount=local_retries,
                    gptCallsUsed=gpt_calls_used,
                )
                selected_model = decision.model
                selected_reason = decision.reason
                selected_confidence = decision.confidence
                selected_complexity = decision.complexityScore

                has_image_attachments = any(
                    str(a.get("type", "")).lower() == "image" for a in (attachments or [])
                )
                if has_image_attachments and selected_model == "local" and task.mode == TaskMode.auto:
                    local_has_vision = await self.local_executor.supports_vision()
                    if not local_has_vision:
                        selected_model = "gpt"
                        selected_reason = "image_input_requires_vision_escalation"
                        selected_confidence = 1.0

                self.task_store.update_task(
                    task.taskId,
                    assignedModel=selected_model,
                    routingReason=f"{selected_reason}:{subtask.title}",
                    routerDecision=selected_model,
                    routerConfidence=selected_confidence,
                    routerReason=selected_reason,
                    complexityScore=selected_complexity,
                    gptCallsUsed=gpt_calls_used,
                    localRetries=local_retries,
                )
                self._emit(task.taskId, "route_decision", f"Routed subtask to {selected_model}", {"reason": selected_reason})

                if selected_model == "gpt" and gpt_calls_used >= decision.budgetPolicy.maxGptCalls:
                    last_error = "Manual review required: GPT budget exceeded"
                    break

                exec_context = {"repoPath": task.repoPath, "attachments": attachments or []}
                if selected_model == "gpt":
                    exec_context = self.context_builder.build_escalation_context(
                        prompt=subtask.prompt,
                        repo_path=task.repoPath,
                        allowed_files=[],
                        failing_log=last_error or "",
                        diff_text="",
                    )
                    if attachments:
                        exec_context["attachments"] = attachments

                run_prompt = self._build_execution_prompt(subtask, task.repoPath)
                result = await self._execute(selected_model, run_prompt, exec_context)
                if selected_model == "gpt":
                    gpt_calls_used += 1
                if result.result:
                    self._emit(
                        task.taskId,
                        "llm_output",
                        f"LLM output from {selected_model}",
                        {"model": selected_model, "text": result.result[:8000]},
                    )

                cumulative_tokens += int(result.tokenUsage.totalTokens)
                cumulative_cost += float(result.tokenUsage.costUsd)

                validation = self._validate_result(result)
                result.validationSummary = validation

                if validation.passed and not result.error:
                    candidates = self.file_applier.parse_blocks(result.result or "")
                    candidate_paths = [p for p, _ in candidates]
                    policy = self.policy_engine.evaluate_apply(candidate_paths)
                    if policy.requires_approval and candidates:
                        self.task_store.set_pending_approval(
                            task.taskId,
                            [{"path": p, "content": c} for p, c in candidates],
                        )
                        updated = self.task_store.update_task(
                            task.taskId,
                            status=TaskStatus.awaiting_approval,
                            requiresApproval=True,
                            currentSubtaskIndex=i,
                            totalSubtasks=total_subtasks,
                            gptCallsUsed=gpt_calls_used,
                            gptTokenEstimate=cumulative_tokens,
                            gptCostUsd=round(cumulative_cost, 6),
                            result="Pending approval before apply",
                            error=None,
                        )
                        self._emit(task.taskId, "awaiting_approval", f"Approval required: {policy.reason}")
                        return updated

                    applied = self.file_applier.apply_blocks(candidates, task.repoPath)
                    if applied:
                        cumulative_changed_files.extend(x for x in applied if x not in cumulative_changed_files)

                    repo_validation = self.repo_validator.validate(task.repoPath)
                    result.validationSummary.checksRun.extend(
                        x for x in repo_validation.checksRun if x not in result.validationSummary.checksRun
                    )
                    result.validationSummary.failedChecks.extend(
                        x for x in repo_validation.failedChecks if x not in result.validationSummary.failedChecks
                    )
                    result.validationSummary.passed = result.validationSummary.passed and repo_validation.passed

                    if not result.validationSummary.passed:
                        failed_preview = ", ".join(result.validationSummary.failedChecks[:3]) or "unknown"
                        last_error = f"Repository validation failed: {failed_preview}"
                        self._emit(task.taskId, "validation_failed", last_error)
                        if selected_model == "local":
                            local_retries += 1
                            if local_retries <= self.local_retry_limit:
                                continue
                        elif gpt_calls_used < decision.budgetPolicy.maxGptCalls:
                            continue
                        break

                    subtask_done = True
                    self._emit(task.taskId, "subtask_completed", f"Completed {subtask.title}", {"files": len(applied)})
                    break

                last_error = result.error or "Validation failed"
                self._emit(task.taskId, "subtask_failed", last_error)

                if selected_model == "local":
                    local_retries += 1
                    if local_retries <= self.local_retry_limit:
                        continue
                elif gpt_calls_used < decision.budgetPolicy.maxGptCalls:
                    continue

                break

            if not subtask_done:
                return self._finalize_failure(
                    task.taskId,
                    gpt_calls_used,
                    local_retries,
                    last_error,
                    changed_files=cumulative_changed_files,
                    gpt_cost_usd=cumulative_cost,
                    gpt_tokens=cumulative_tokens,
                )

        updated = self.task_store.update_task(
            task.taskId,
            status=TaskStatus.completed,
            currentSubtaskIndex=total_subtasks,
            totalSubtasks=total_subtasks,
            gptCallsUsed=gpt_calls_used,
            gptTokenEstimate=cumulative_tokens,
            gptCostUsd=round(cumulative_cost, 6),
            localRetries=0,
            result="Subtasks completed and files applied",
            error=None,
            changedFiles=cumulative_changed_files,
            completedAt=datetime.utcnow(),
        )
        self._emit(task.taskId, "execution_completed", "Task completed", {"files": len(cumulative_changed_files)})
        return updated

    async def _execute(self, model: str, prompt: str, context: dict[str, Any]) -> ExecutorResult:
        if model == "gpt":
            return await self.gpt_executor.execute(prompt=prompt, context=context)
        return await self.local_executor.execute(prompt=prompt, context=context)

    def _validate_result(self, result: ExecutorResult):
        checks_run = ["result_present"]
        failed_checks: list[str] = []

        if result.error:
            failed_checks.append("executor_error")
        if not result.result:
            failed_checks.append("empty_result")

        result.validationSummary.checksRun.extend(x for x in checks_run if x not in result.validationSummary.checksRun)
        result.validationSummary.failedChecks.extend(
            x for x in failed_checks if x not in result.validationSummary.failedChecks
        )
        result.validationSummary.passed = len(result.validationSummary.failedChecks) == 0
        return result.validationSummary

    def _finalize_failure(
        self,
        task_id: str,
        gpt_calls_used: int,
        local_retries: int,
        error: Optional[str],
        changed_files: Optional[list[str]] = None,
        gpt_cost_usd: float = 0.0,
        gpt_tokens: int = 0,
    ) -> TaskRecord:
        current = self.task_store.get_task(task_id)
        budget_policy = self.router.budget_policy()
        budget_exceeded = gpt_calls_used >= budget_policy.maxGptCalls
        final_error = error or "Manual review required"
        if budget_exceeded:
            final_error = "Manual review required: GPT budget exceeded"

        updated = self.task_store.update_task(
            task_id,
            status=TaskStatus.failed,
            gptCallsUsed=gpt_calls_used,
            gptTokenEstimate=gpt_tokens,
            gptCostUsd=round(gpt_cost_usd, 6),
            localRetries=local_retries,
            budgetExceeded=budget_exceeded,
            error=final_error,
            changedFiles=changed_files or [],
            completedAt=datetime.utcnow(),
        )
        self._emit(task_id, "execution_failed", final_error)
        return updated

    @staticmethod
    def _build_execution_prompt(subtask: Subtask, repo_path: str) -> str:
        return (
            f"{subtask.prompt}\n\n"
            "Return file outputs only in this exact format for each file:\n"
            "FILE: relative/path/from/repo\n"
            "```language\n"
            "<full file content>\n"
            "```\n\n"
            f"Target repository path: {repo_path}\n"
            "Do not include extra commentary outside file blocks."
        )

    def _emit(self, task_id: str, event_type: str, message: str, payload: Optional[dict[str, Any]] = None) -> None:
        event = self.task_store.add_event(task_id, event_type, message, payload or {})
        self.webhook_dispatcher.emit(event.model_dump(mode="json"))
