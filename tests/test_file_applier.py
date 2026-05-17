from pathlib import Path

from backend.services.file_applier import FileApplier


def test_file_applier_writes_files(tmp_path: Path):
    applier = FileApplier()
    output = (
        "FILE: src/main/java/com/example/App.java\n"
        "```java\n"
        "class App {}\n"
        "```\n"
        "FILE: pom.xml\n"
        "```xml\n"
        "<project/>\n"
        "```\n"
    )

    changed = applier.apply(output, str(tmp_path))
    assert len(changed) == 2
    assert (tmp_path / "src/main/java/com/example/App.java").exists()
    assert (tmp_path / "pom.xml").exists()


def test_file_applier_blocks_path_escape(tmp_path: Path):
    applier = FileApplier()
    output = "FILE: ../../etc/passwd\n```txt\nnope\n```\n"
    changed = applier.apply(output, str(tmp_path))
    assert changed == []
