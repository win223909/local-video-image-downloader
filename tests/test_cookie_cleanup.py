import os
from pathlib import Path
import threading
import time

import pytest

from local_agent import server
from video_downloader import browser_session, resolver
from video_downloader.browser_session import BrowserResolveResult
from video_downloader.core import VideoDownloaderError, make_direct_video_info


def exported_cookie_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(browser_session, "TEMP_DIR", tmp_path)
    path = browser_session.export_cookies(
        [{"domain": ".example.test", "name": "fixture", "value": "not-a-real-cookie", "path": "/"}],
        "https://example.test/post/1",
    )
    assert path is not None
    return path


def test_cookie_export_skips_empty_and_is_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(browser_session, "TEMP_DIR", tmp_path)
    assert browser_session.export_cookies([], "https://example.test/") is None
    assert list(tmp_path.iterdir()) == []

    path = exported_cookie_file(monkeypatch, tmp_path)
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_cookie_cleanup_only_removes_own_exports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = exported_cookie_file(monkeypatch, tmp_path)
    unrelated = tmp_path / "user.cookies.txt"
    unrelated.write_text("keep", encoding="utf-8")
    outside = tmp_path.parent / path.name
    outside.write_text("keep", encoding="utf-8")
    try:
        browser_session.remove_exported_cookie_file(unrelated)
        browser_session.remove_exported_cookie_file(outside)
        browser_session.remove_exported_cookie_file(path)
        assert not path.exists()
        assert unrelated.exists()
        assert outside.exists()
    finally:
        outside.unlink(missing_ok=True)


def test_prune_removes_only_stale_exports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    old = exported_cookie_file(monkeypatch, tmp_path)
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    fresh = exported_cookie_file(monkeypatch, tmp_path)
    browser_session.prune_exported_cookie_files(max_age_seconds=3600)

    assert not old.exists()
    assert fresh.exists()


def test_failed_browser_resolution_removes_exported_cookies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = exported_cookie_file(monkeypatch, tmp_path)
    url = "https://www.instagram.com/p/fixture/"
    result = BrowserResolveResult(
        requested_url=url, final_url=url, title="Instagram", description=None,
        thumbnail_url=None, canonical_url=url, video_url=None,
        post_incomplete=True, cookie_file=path,
    )
    monkeypatch.setattr(resolver, "parse_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        VideoDownloaderError("No formats", code="unsupported_url")
    ))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda *args, **kwargs: result)

    with pytest.raises(VideoDownloaderError, match="完整组图"):
        resolver.resolve_video(url)

    assert not path.exists()


def test_clear_history_removes_retained_cookie_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = exported_cookie_file(monkeypatch, tmp_path)
    agent_state = server.AgentState.__new__(server.AgentState)
    agent_state.lock = threading.RLock()
    info = make_direct_video_info(
        url="https://example.test/video.mp4", webpage_url="https://example.test/post/1", title="Fixture",
    )
    task = server.AgentTask(
        id="fixture", text="https://example.test/post/1", status="resolved",
        resolved=resolver.ResolvedVideo(info=info, cookie_file=path),
    )
    agent_state.tasks = {task.id: task}

    assert agent_state.clear_completed_tasks() == 1
    assert not path.exists()
