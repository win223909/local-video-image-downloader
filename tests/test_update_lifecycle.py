import argparse
import json
from pathlib import Path
import plistlib
import shutil
import time
import zipfile
from unittest.mock import Mock

import pytest

from local_agent import updater


def package(root, version):
    for name in updater.MANAGED_PATHS:
        target = root / name
        if name in {"web", "local_agent", "video_downloader"}:
            target.mkdir(parents=True)
            (target / "fixture.txt").write_text(version)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(version)
    (root / "local_agent/server.py").write_text(f'AGENT_VERSION = "{version}"\n')


@pytest.fixture
def update_case(tmp_path, monkeypatch):
    app = tmp_path / "app"
    source = tmp_path / "package"
    package(app, "0.1.1")
    package(source, "0.1.2")
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in source.rglob("*"):
            if path.is_file():
                output.write(path, path.relative_to(source))
    monkeypatch.setattr(updater, "parse_args", lambda: argparse.Namespace(app_dir=str(app), manifest_url="https://example.test/update.json", restart=True))
    monkeypatch.setattr(updater, "fetch_json", lambda url: {"version": "0.1.2", "agent_url": "source.zip", "agent_sha256": updater.sha256(archive)})
    monkeypatch.setattr(updater, "download_file", lambda url, target: shutil.copy2(archive, target))
    monkeypatch.setattr(updater, "install_requirements", lambda app: None)
    monkeypatch.setattr(updater, "install_playwright_chromium", lambda app: None)
    monkeypatch.setattr(updater, "read_agent_health", lambda: {"instance_id": "old", "pid": 123})
    return app


def status(app):
    return json.loads((app / ".runtime/update-status.json").read_text())


def test_completed_only_after_verified_restart(update_case, monkeypatch):
    monkeypatch.setattr(updater, "restart_agent", lambda *args: True)
    verified = Mock()
    monkeypatch.setattr(updater, "wait_for_agent", verified)
    assert updater.main() == 0
    verified.assert_called_once()
    assert status(update_case)["state"] == "completed"
    assert updater.package_version(update_case) == "0.1.2"
    assert not (update_case / ".runtime/update/backup").exists()


def test_manual_restart_keeps_backup_and_is_not_success(update_case, monkeypatch):
    monkeypatch.setattr(updater, "restart_agent", lambda *args: False)
    assert updater.main() == 0
    data = status(update_case)
    assert data["state"] == "awaiting_restart"
    assert (update_case / ".runtime/update/backup/README.md").read_text() == "0.1.1"
    assert updater.reconcile_status(data, "0.1.1", "old-build", "old")["state"] == "awaiting_restart"
    assert updater.reconcile_status(data, "0.1.2", updater.build_fingerprint(update_case), "new")["state"] == "completed"


def test_failed_health_rolls_back_and_keeps_recovery_copy(update_case, monkeypatch):
    restarted = Mock(return_value=True)
    monkeypatch.setattr(updater, "restart_agent", restarted)
    monkeypatch.setattr(updater, "wait_for_agent", Mock(side_effect=RuntimeError("fixture failed health")))
    assert updater.main() == 1
    assert status(update_case)["state"] == "failed"
    assert updater.package_version(update_case) == "0.1.1"
    assert (update_case / ".runtime/update/backup").is_dir()
    assert restarted.call_count == 2


def test_restart_command_failure_also_restarts_restored_files(update_case, monkeypatch):
    restarted = Mock(side_effect=[RuntimeError("fixture restart failed"), True])
    monkeypatch.setattr(updater, "restart_agent", restarted)
    assert updater.main() == 1
    assert updater.package_version(update_case) == "0.1.1"
    assert status(update_case)["state"] == "failed"
    assert restarted.call_count == 2


def test_version_mismatch_rejected_before_backup(update_case, monkeypatch):
    original_fetch = updater.fetch_json
    monkeypatch.setattr(updater, "fetch_json", lambda url: {**original_fetch(url), "version": "0.1.3"})
    replace = Mock()
    monkeypatch.setattr(updater, "replace_managed_files", replace)
    assert updater.main() == 1
    replace.assert_not_called()
    assert updater.package_version(update_case) == "0.1.1"


@pytest.mark.parametrize("state", ["queued", "running", "restarting"])
def test_dead_updater_is_not_permanently_running(monkeypatch, state):
    monkeypatch.setattr(updater, "process_is_alive", lambda pid: False)
    data = {"state": state, "pid": 123, "updated_at": time.time()}
    assert updater.reconcile_status(data, "0.1.2", "build", "instance")["state"] == "failed"


def test_live_updater_and_queued_startup_grace(monkeypatch):
    monkeypatch.setattr(updater, "process_is_alive", lambda pid: True)
    data = {"state": "running", "pid": 123, "updated_at": time.time()}
    assert updater.reconcile_status(data, "0.1.2", "build", "instance") == data
    queued = {"state": "queued", "updated_at": time.time()}
    assert updater.reconcile_status(queued, "0.1.2", "build", "instance") == queued
    queued["updated_at"] -= 61
    assert updater.reconcile_status(queued, "0.1.2", "build", "instance")["state"] == "failed"


def test_wrong_build_never_passes_health_check(monkeypatch):
    monkeypatch.setattr(updater, "read_agent_health", lambda: {"ok": True, "version": "0.1.2", "build_id": "old", "instance_id": "new"})
    with pytest.raises(RuntimeError):
        updater.wait_for_agent("0.1.2", "expected", {"instance_id": "old"}, timeout=0.01)


def test_new_instance_required_for_health_check(monkeypatch):
    data = {"ok": True, "version": "0.1.2", "build_id": "expected", "instance_id": "old"}
    monkeypatch.setattr(updater, "read_agent_health", lambda: data)
    with pytest.raises(RuntimeError):
        updater.wait_for_agent("0.1.2", "expected", data, timeout=0.01)
    updater.wait_for_agent("0.1.2", "expected", {"instance_id": "previous"}, timeout=0.01)


def test_legacy_mac_service_is_restarted_only_for_matching_app(tmp_path, monkeypatch):
    app = tmp_path / "app"
    plist = tmp_path / "Library/LaunchAgents/xyz.k666.video-downloader-agent.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(plistlib.dumps({"WorkingDirectory": str(app)}))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(updater.platform, "system", lambda: "Darwin")
    run = Mock()
    monkeypatch.setattr(updater.subprocess, "run", run)
    assert updater.restart_agent(app)
    assert run.call_args.args[0][-1].endswith("/xyz.k666.video-downloader-agent")
    assert not updater.restart_agent(tmp_path / "different-app")
    assert run.call_count == 1


def test_build_id_tracks_code_but_not_user_data(tmp_path):
    package(tmp_path / "app", "0.1.2")
    app = tmp_path / "app"
    before = updater.build_fingerprint(app)
    (app / ".runtime").mkdir()
    (app / ".runtime/private.txt").write_text("fixture")
    assert updater.build_fingerprint(app) == before
    (app / "web/app.js").write_text("const changed = true;")
    assert updater.build_fingerprint(app) != before
