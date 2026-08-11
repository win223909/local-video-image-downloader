from pathlib import Path
import zipfile

import pytest

from local_agent import updater


def make_zip(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "test")


def test_safe_extract_accepts_normal_zip(tmp_path: Path) -> None:
    archive_path = tmp_path / "agent.zip"
    staging = tmp_path / "staging"
    make_zip(archive_path, ["local_agent/server.py", "nested/file.txt"])

    with zipfile.ZipFile(archive_path) as archive:
        updater.safe_extract_zip(archive, staging)

    assert (staging / "local_agent/server.py").read_text() == "test"
    assert (staging / "nested/file.txt").read_text() == "test"


@pytest.mark.parametrize(
    "name",
    [
        "../evil.txt",
        "/absolute/evil.txt",
        "C:\\absolute\\evil.txt",
        "nested/../../evil.txt",
        "nested\\..\\..\\evil.txt",
    ],
)
def test_safe_extract_rejects_escape_paths(tmp_path: Path, name: str) -> None:
    archive_path = tmp_path / "malicious.zip"
    staging = tmp_path / "staging"
    make_zip(archive_path, ["safe.txt", name])

    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(RuntimeError):
            updater.safe_extract_zip(archive, staging)

    assert not (staging / "safe.txt").exists()
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "absolute" / "evil.txt").exists()


def test_replace_and_restore_managed_files(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    staging = tmp_path / "staging"
    backup = tmp_path / "backup"
    (app_dir / "local_agent").mkdir(parents=True)
    (app_dir / "local_agent/server.py").write_text("old", encoding="utf-8")
    (staging / "local_agent").mkdir(parents=True)
    (staging / "local_agent/server.py").write_text("new", encoding="utf-8")

    updater.backup_managed_files(app_dir, backup)
    updater.replace_managed_files(app_dir, staging)
    assert (app_dir / "local_agent/server.py").read_text() == "new"

    updater.restore_managed_files(app_dir, backup)
    assert (app_dir / "local_agent/server.py").read_text() == "old"
