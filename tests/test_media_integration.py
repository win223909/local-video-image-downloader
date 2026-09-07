from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import os
import subprocess
import threading
import time

import pytest

from local_agent import server
from video_downloader import core, resolver
from video_downloader.worker import run_download_worker
from video_downloader import worker


@pytest.fixture
def sample_video(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("Local FFmpeg/ffprobe required for media integration tests")
    path = tmp_path / "fixture.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=64x64:r=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(path)],
                   check=True, capture_output=True, timeout=20)
    return path


@contextmanager
def media_server(body, *, slow=False):
    requested = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            requested.set()
            if slow:
                release.wait(10)
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/fixture.mp4", requested
    finally:
        release.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def resolved_media(url):
    info = core.make_direct_video_info(url=url, webpage_url=url, title="Fixture")
    return resolver.ResolvedVideo(info=info, source="douyin-share")


def test_worker_downloads_real_local_media(sample_video, tmp_path):
    with media_server(sample_video.read_bytes()) as (url, requested):
        result = run_download_worker(resolved_media(url), None, tmp_path / "download", lambda x: None, lambda x: None, lambda: None)
    assert requested.is_set()
    assert len(result.files) == 1
    assert result.files[0].read_bytes() == sample_video.read_bytes()
    core.validate_media_file(result.files[0], "video")


def test_worker_cancels_stalled_transfer_without_waiting_for_socket(tmp_path):
    with media_server(b"fixture", slow=True) as (url, requested):
        def cancel_when_connected():
            if requested.is_set():
                raise core.DownloadCancelled()
        started = time.monotonic()
        with pytest.raises(core.DownloadCancelled):
            run_download_worker(resolved_media(url), None, tmp_path / "download", lambda x: None, lambda x: None, cancel_when_connected)
        assert time.monotonic() - started < 6


def test_real_iphone_conversion_keeps_source(sample_video):
    original = sample_video.read_bytes()
    output = server.iphone_output_path(sample_video)
    task = server.AgentTask(id="fixture", text="fixture", status="converting")
    server.convert_video_for_iphone(Path(shutil.which("ffmpeg")), sample_video, output, task)
    core.validate_media_file(output, "video")
    assert sample_video.read_bytes() == original
    assert task.active_process is None
    assert not output.with_name(f".{output.name}.tmp").exists()


def test_real_conversion_stop_removes_partial_not_source(sample_video, monkeypatch):
    output = server.iphone_output_path(sample_video)
    task = server.AgentTask(id="fixture", text="fixture", status="converting")
    original_run = server.run_media_process

    def slow_run(command, **kwargs):
        command.insert(command.index("-i"), "-re")
        return original_run(command, **kwargs)

    monkeypatch.setattr(server, "run_media_process", slow_run)
    def cancel():
        for _ in range(100):
            if task.active_process:
                task.cancel_requested = True
                return
            time.sleep(0.01)
    thread = threading.Thread(target=cancel)
    thread.start()
    try:
        with pytest.raises(core.DownloadCancelled):
            server.convert_video_for_iphone(Path(shutil.which("ffmpeg")), sample_video, output, task)
    finally:
        thread.join(timeout=2)
    assert sample_video.exists()
    assert not output.exists()
    assert not output.with_name(f".{output.name}.tmp").exists()
    assert task.active_process is None


def test_valid_header_without_video_stream_is_rejected(sample_video, tmp_path):
    truncated = tmp_path / "broken.mp4"
    truncated.write_bytes(sample_video.read_bytes()[:24])
    with pytest.raises(core.VideoDownloaderError):
        core.validate_media_file(truncated, "video")


def ffmpeg_postprocess_worker(send, cancel, resolved, selected, output_dir):
    os.setsid()
    process = subprocess.Popen([shutil.which("ffmpeg"), "-v", "error", "-re", "-stream_loop", "-1",
                                "-i", str(output_dir), "-c", "copy", "-f", "null", "-"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    send.send(("message", str(process.pid)))
    process.wait()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-tree integration; Windows needs device validation")
def test_worker_stops_ffmpeg_postprocessing_child(sample_video, monkeypatch):
    monkeypatch.setattr(worker, "_download", ffmpeg_postprocess_worker)
    child = []
    def cancelled():
        if child:
            raise core.DownloadCancelled()
    with pytest.raises(core.DownloadCancelled):
        worker.run_download_worker(None, None, sample_video, lambda x: None, lambda pid: child.append(pid), cancelled)
    assert child
    for _ in range(20):
        result = subprocess.run(["ps", "-p", child[0], "-o", "stat="], capture_output=True, text=True)
        if not result.stdout.strip() or result.stdout.strip().startswith("Z"):
            break
        time.sleep(0.05)
    assert not result.stdout.strip() or result.stdout.strip().startswith("Z")
