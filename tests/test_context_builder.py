from backend.services.context_builder import ContextBuilder


def test_context_builder_minimizes_payload():
    b = ContextBuilder()
    ctx = b.build_escalation_context(
        prompt="Fix architecture issue in retries",
        repo_path="/tmp/repo",
        allowed_files=["a.py", "b.py"],
        failing_log="line1\nERROR: failed thing\nline3",
        diff_text="x" * 3000,
    )
    assert set(ctx.keys()) == {"task", "repoPath", "allowedFiles", "failingLogSummary", "unifiedDiffSnippet"}
    assert ctx["repoPath"] == "/tmp/repo"
    assert ctx["allowedFiles"] == ["a.py", "b.py"]
    assert len(ctx["unifiedDiffSnippet"]) <= 2003


def test_summarize_log_truncates_and_keeps_errors():
    b = ContextBuilder()
    log = "\n".join([f"line-{i}" for i in range(100)]) + "\nException: boom"
    summary = b.summarize_log(log, max_chars=200)
    assert len(summary) <= 203
    assert "Exception" in summary or "line" in summary
