import io
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.requests import Request
import pytest

from local_agent import server
from video_downloader import core, resolver, system
from video_downloader.browser_session import BrowserResolveResult
from video_downloader.platforms import douyin
from video_downloader.processes import run_media_process


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNTIME_DIR", tmp_path)
    for attribute, name in [("TOKEN_FILE", "token.json"), ("SETTINGS_FILE", "settings.json"),
                            ("INSTALL_SOURCE_FILE", "source.json"), ("UPDATE_STATUS_FILE", "update.json")]:
        monkeypatch.setattr(server, attribute, tmp_path / name)
    state = server.AgentState()
    monkeypatch.setattr(server, "state", state)
    return state


def request(client="127.0.0.1", host="127.0.0.1:17890", **headers):
    return Request({"type": "http", "method": "GET", "scheme": "http", "path": "/api/local-token",
                    "query_string": b"", "headers": [(k.encode(), v.encode()) for k, v in {"host": host, **headers}.items()],
                    "client": (client, 45678), "server": ("127.0.0.1", 17890)})


@pytest.mark.parametrize("peer", ["192.168.1.2", "10.0.0.2", "203.0.113.1", "invalid"])
def test_local_token_rejects_remote_peer_with_loopback_host(isolated_state, peer):
    with pytest.raises(HTTPException) as error:
        server.local_token(request(client=peer))
    assert error.value.status_code == 403
    assert isolated_state.token is None


@pytest.mark.parametrize("headers", [{"origin": "https://evil.example"}, {"x-forwarded-for": "127.0.0.1"},
                                    {"sec-fetch-site": "cross-site"}, {"referer": "https://evil.example"}])
def test_local_token_rejects_untrusted_origin_and_proxy(isolated_state, headers):
    with pytest.raises(HTTPException):
        server.local_token(request(**headers))


@pytest.mark.parametrize("peer,host", [("127.0.0.1", "localhost:17890"), ("::1", "[::1]:17890")])
def test_local_token_accepts_real_loopback(isolated_state, peer, host):
    assert server.local_token(request(client=peer, host=host))["token"]


def test_windows_bom_settings_are_read(isolated_state):
    server.TOKEN_FILE.write_text(json.dumps({"token": "fixture-only"}), encoding="utf-8-sig")
    server.INSTALL_SOURCE_FILE.write_text(json.dumps({"update_manifest_url": "https://example.test/update.json"}), encoding="utf-8-sig")
    assert server.AgentState().token == "fixture-only"
    assert server.read_install_source()["update_manifest_url"].startswith("https://example.test/")


def test_allowed_cors_delete():
    options = next(m.kwargs for m in server.app.user_middleware if m.cls is CORSMiddleware)
    middleware = CORSMiddleware(server.app, **options)
    for origin, status in [("http://localhost:8000", 200), ("https://evil.example", 400)]:
        result = middleware.preflight_response(Headers({"Origin": origin, "Access-Control-Request-Method": "DELETE",
                                                       "Access-Control-Request-Headers": "Authorization,Content-Type"}))
        assert result.status_code == status


def test_write_probe_preserves_existing_file_and_symlink(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("original")
    marker = tmp_path / ".write_test"
    marker.write_text("original marker")
    system.ensure_writable_directory(tmp_path)
    assert marker.read_text() == "original marker"
    marker.unlink()
    marker.symlink_to(target)
    system.ensure_writable_directory(tmp_path)
    assert marker.is_symlink() and target.read_text() == "original"


@pytest.mark.parametrize("picker", [system._choose_folder_windows, system._choose_video_file_windows])
def test_windows_picker_uses_utf8(tmp_path, monkeypatch, picker):
    def run(*args, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(args, 0, "D:\\桌面\\视频.mp4\n", "")
    monkeypatch.setattr(system.subprocess, "run", run)
    assert str(picker(tmp_path)) == "D:\\桌面\\视频.mp4"


def fake_ydl(monkeypatch, output):
    class YDL:
        def __init__(self, options):
            self.params = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def add_post_processor(self, pp, when):
            assert when == "after_move"
            pp._progress_hooks = []
            self.pp = pp
        def download(self, urls):
            if output is not None:
                self.pp.run({"filepath": str(output)})
            return 0
    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", YDL)


def test_download_returns_own_existing_file_not_newer_neighbor(tmp_path, monkeypatch):
    own = tmp_path / "own.mp4"
    own.write_bytes(b"fixture")
    (tmp_path / "private.txt").write_text("fixture")
    fake_ydl(monkeypatch, own)
    assert core.download_video("https://example.test/video", "best", tmp_path).files == [own]


def test_download_never_falls_back_to_unrelated_file(tmp_path, monkeypatch):
    (tmp_path / "private.txt").write_text("fixture")
    fake_ydl(monkeypatch, None)
    with pytest.raises(core.VideoDownloaderError, match="输出文件"):
        core.download_video("https://example.test/video", "best", tmp_path)


@pytest.mark.parametrize("body,mime", [(b"<html>denied</html>", "text/html"), (b'{"error":1}', "application/octet-stream"), (b"", "video/mp4")])
def test_error_responses_not_saved_as_mp4(tmp_path, monkeypatch, body, mime):
    response = io.BytesIO(body)
    response.headers = {"content-type": mime}
    response.length = len(body)
    monkeypatch.setattr(core, "urlopen", lambda *a, **k: response)
    info = core.make_direct_video_info(url="https://example.test/video.mp4", webpage_url="https://example.test/post", title="Fixture")
    with pytest.raises(core.VideoDownloaderError):
        core.download_direct_video(info, tmp_path)
    assert not list(tmp_path.iterdir())


def test_instagram_gallery_wins_over_recommendation_video(monkeypatch):
    url = "https://www.instagram.com/p/fixture/"
    result = BrowserResolveResult(url, url, "Fixture", None, None, url, "https://example.test/recommendation.mp4",
                                  video_url_source="network", post_media_type=8,
                                  post_image_urls=["https://example.test/one.jpg", "https://example.test/two.jpg"])
    monkeypatch.setattr(resolver, "parse_video", Mock(side_effect=core.VideoDownloaderError("No video")))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda *a, **k: result)
    parsed = resolver.resolve_video(url)
    assert parsed.info.media_type == "image"
    assert len(parsed.info.images) == 2


def test_instagram_mixed_gallery_is_not_silently_flattened(monkeypatch):
    url = "https://www.instagram.com/p/fixture/"
    result = BrowserResolveResult(url, url, "Fixture", None, None, url, None, post_media_type=8, post_has_video=True)
    monkeypatch.setattr(resolver, "parse_video", Mock(side_effect=core.VideoDownloaderError("No video")))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda *a, **k: result)
    with pytest.raises(core.VideoDownloaderError) as error:
        resolver.resolve_video(url)
    assert error.value.code == "mixed_media_unsupported"


def test_instagram_thumbnail_alone_is_not_a_complete_gallery():
    url = "https://www.instagram.com/p/fixture/"
    result = BrowserResolveResult(url, url, "Fixture", None, "https://example.test/cover.jpg", url, None)
    assert resolver.direct_browser_image_fallback(url, result) is None


def test_update_cannot_interrupt_media_work(isolated_state, monkeypatch):
    isolated_state.create_task("fixture")
    monkeypatch.setattr(server, "fetch_update_manifest", lambda: {"version": "0.1.53"})
    launch = Mock()
    monkeypatch.setattr(server, "start_update_process", launch)
    with pytest.raises(HTTPException) as error:
        server.start_update(server.UpdateStartRequest())
    assert error.value.status_code == 409
    launch.assert_not_called()


def test_media_cannot_start_during_update(isolated_state):
    isolated_state.write_update_status({"state": "queued", "updated_at": time.time()})
    with pytest.raises(HTTPException) as error:
        isolated_state.create_task("fixture")
    assert error.value.status_code == 409


def test_same_conversion_output_cannot_be_claimed_twice(isolated_state, tmp_path):
    task = server.AgentTask(id="one", text="fixture", status="converting")
    other = server.AgentTask(id="two", text="fixture", status="converting")
    isolated_state.claim_conversion(task, tmp_path / "fixture.mp4")
    with pytest.raises(HTTPException) as error:
        isolated_state.claim_conversion(other, tmp_path / "fixture.mp4")
    assert error.value.status_code == 409


def test_douyin_cdn_alternatives_are_one_image():
    item = {"images": [{"url_list": ["https://a.example/image.jpg", "https://b.example/image.jpg"]}]}
    assert douyin.collect_image_urls(item) == ["https://a.example/image.jpg"]
    assert len(douyin.collect_image_candidates(item)[0]) == 2


def test_download_rejected_during_conversion(isolated_state, monkeypatch):
    task = server.AgentTask(id="fixture", text="fixture", status="converting", resolved=Mock())
    isolated_state.tasks[task.id] = task
    start = Mock()
    monkeypatch.setattr(server.threading.Thread, "start", start)
    with pytest.raises(HTTPException) as error:
        server.start_download(task.id, server.DownloadRequest())
    assert error.value.status_code == 409
    assert task.status == "converting"
    start.assert_not_called()


def test_active_download_is_restorable(isolated_state):
    task = server.AgentTask(id="fixture", text="fixture", status="downloading")
    isolated_state.tasks[task.id] = task
    assert isolated_state.latest_result_task() is task


def test_task_concurrency_limit(isolated_state):
    for _ in range(server.MAX_ACTIVE_TASKS):
        isolated_state.create_task("fixture")
    with pytest.raises(HTTPException) as error:
        isolated_state.create_task("fixture")
    assert error.value.status_code == 429


def test_media_process_drains_large_error_output():
    code, output = run_media_process([sys.executable, "-c", "import sys; sys.stderr.write('x'*2000000); print('progress=end')"],
                                     check_cancelled=lambda: None, timeout=10)
    assert code == 0 and "progress=end" in output
    assert len(output) < 10000


def test_silent_media_process_can_be_cancelled():
    started = time.monotonic()
    def check():
        if time.monotonic() - started > 0.2:
            raise core.DownloadCancelled()
    with pytest.raises(core.DownloadCancelled):
        run_media_process([sys.executable, "-c", "import time; time.sleep(30)"], check_cancelled=check)
    assert time.monotonic() - started < 5
