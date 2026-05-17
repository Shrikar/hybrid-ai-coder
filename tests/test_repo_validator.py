from backend.services.repo_validator import RepoValidator, ValidationConfig


def test_no_validation_config_returns_pass(tmp_path):
    validator = RepoValidator(ValidationConfig(commands=[]))
    result = validator.validate(str(tmp_path))
    assert result.passed is True
    assert result.checksRun == ["no_validation_configured"]


def test_profile_detection_runs_matching_profile(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    validator = RepoValidator(
        ValidationConfig(
            commands=[],
            profiles=[
                {"name": "java_maven", "exists_any": ["pom.xml"], "commands": ["echo ok"]},
                {"name": "node", "exists_any": ["package.json"], "commands": ["echo no"]},
            ],
        )
    )
    result = validator.validate(str(tmp_path))
    assert result.passed is True
    assert result.checksRun == ["java_maven:echo ok"]


def test_failure_marks_failed_checks(tmp_path):
    validator = RepoValidator(
        ValidationConfig(
            commands=["python3 -c \"import sys; sys.exit(3)\""],
            stop_on_failure=True,
        )
    )
    result = validator.validate(str(tmp_path))
    assert result.passed is False
    assert len(result.failedChecks) == 1
    assert "exit=3" in result.failedChecks[0]


def test_stop_on_failure_false_runs_all(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    validator = RepoValidator(
        ValidationConfig(
            commands=["python3 -c \"import sys; sys.exit(1)\""],
            profiles=[
                {"name": "node", "exists_any": ["package.json"], "commands": ["echo still-runs"]},
            ],
            stop_on_failure=False,
        )
    )
    result = validator.validate(str(tmp_path))
    assert len(result.checksRun) == 2
    assert any("still-runs" in check for check in result.checksRun)
