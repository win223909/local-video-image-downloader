from pathlib import Path
import stat
import zipfile

import pytest

from local_agent import updater


def make_zip(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "test")


def make_complete_staging(staging: Path) -> None:
    directories = {"web", "local_agent", "video_downloader"}
    for rel in updater.MANAGED_PATHS:
        target = staging / rel
        if rel in directories:
            target.mkdir(parents=True, exist_ok=True)
            (target / "marker.txt").write_text("test", encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("test", encoding="utf-8")
    (staging / "local_agent" / "server.py").write_text("test", encoding="utf-8")


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


def test_safe_extract_rejects_symbolic_link(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    staging = tmp_path / "staging"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "target")

    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(RuntimeError, match="符号链接"):
            updater.safe_extract_zip(archive, staging)

    assert not (staging / "link").exists()


def test_validate_accepts_complete_staging_package(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    make_complete_staging(staging)

    updater.validate_staging_package(staging)


def test_validate_rejects_missing_web_before_replace(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    staging = tmp_path / "staging"
    make_complete_staging(staging)
    (staging / "web" / "marker.txt").unlink()
    (staging / "web").rmdir()
    (app_dir / "web").mkdir(parents=True)
    (app_dir / "web" / "existing.txt").write_text("old", encoding="utf-8")

    with pytest.raises(RuntimeError, match="web"):
        updater.validate_staging_package(staging)
        updater.replace_managed_files(app_dir, staging)

    assert (app_dir / "web" / "existing.txt").read_text() == "old"


def test_validate_rejects_missing_managed_path_before_replace(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    staging = tmp_path / "staging"
    make_complete_staging(staging)
    (staging / "requirements.txt").unlink()
    (app_dir / "local_agent").mkdir(parents=True)
    (app_dir / "local_agent" / "server.py").write_text("old", encoding="utf-8")

    with pytest.raises(RuntimeError, match="requirements.txt"):
        updater.validate_staging_package(staging)
        updater.replace_managed_files(app_dir, staging)

    assert (app_dir / "local_agent" / "server.py").read_text() == "old"


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
