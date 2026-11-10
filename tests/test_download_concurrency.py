from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Lock

import pytest

from video_downloader import core


@pytest.mark.parametrize("kind", ["video", "audio", "image"])
def test_concurrent_direct_downloads_keep_both_files(tmp_path, monkeypatch, kind):
    barrier = Barrier(2)
    lock = Lock()
    parts = []
    info = core.make_direct_video_info(
        url="https://example.test/video.mp4", webpage_url="https://example.test/post", title="Fixture"
    )
    if kind == "audio":
        info = replace(info, audio_url="https://example.test/audio.m4a")
        monkeypatch.setattr(core.shutil, "which", lambda name: "fixture-ffmpeg")
        monkeypatch.setattr(core, "merge_direct_media", lambda ffmpeg, video, audio, output: output.write_bytes(video.read_bytes()))
    elif kind == "image":
        info = replace(info, media_type="image", images=[core.ImageItem("https://example.test/image.jpg")])

    def download(url, path, headers, progress_hook=None):
        with lock:
            parts.append(path)
            payload = f"fixture-{len(parts)}".encode()
        path.write_bytes(payload)
        barrier.wait(timeout=5)

    monkeypatch.setattr(core, "download_direct_file", download)
    monkeypatch.setattr(core, "validate_media_file", lambda *args, **kwargs: None)
    operation = core.download_images if kind == "image" else core.download_direct_video
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(operation, info, tmp_path) for _ in range(2)]
        results = [future.result() for future in futures]
    files = [result.files[0] for result in results]
    assert len(set(parts)) == len(parts)
    assert len(set(files)) == 2
    assert len({path.read_bytes() for path in files}) == 2
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob(".media-download-*"))


def test_finalize_download_preserves_existing_file_and_symlink(tmp_path):
    original = tmp_path / "original.mp4"
    original.write_bytes(b"original")
    requested = tmp_path / "video.mp4"
    requested.symlink_to(original)
    occupied = tmp_path / "video (1).mp4"
    occupied.write_bytes(b"existing")
    part = tmp_path / "fixture.part"
    part.write_bytes(b"new")
    result = core.finalize_download(part, requested)
    assert result.name == "video (2).mp4"
    assert result.read_bytes() == b"new"
    assert original.read_bytes() == b"original"
    assert requested.is_symlink()
    assert occupied.read_bytes() == b"existing"


def test_finalize_failure_removes_only_its_reservation(tmp_path, monkeypatch):
    part = tmp_path / "fixture.part"
    part.write_bytes(b"fixture")
    requested = tmp_path / "video.mp4"
    def fail(*args):
        raise OSError("fixture replace failure")
    monkeypatch.setattr(core.os, "replace", fail)
    with pytest.raises(OSError):
        core.finalize_download(part, requested)
    assert not requested.exists()
    assert part.read_bytes() == b"fixture"


@pytest.mark.parametrize("kind", ["video", "image"])
def test_cancel_cleans_only_own_temporary_files(tmp_path, monkeypatch, kind):
    existing = tmp_path / "keep.mp4"
    existing.write_bytes(b"keep")
    info = core.make_direct_video_info(url="https://example.test/video.mp4", webpage_url="https://example.test/post", title="Fixture")
    if kind == "image":
        info = replace(info, media_type="image", images=[core.ImageItem("https://example.test/image.jpg")])
    def cancelled(url, path, headers, progress_hook=None):
        path.write_bytes(b"partial")
        raise core.DownloadCancelled()
    monkeypatch.setattr(core, "download_direct_file", cancelled)
    with pytest.raises(core.DownloadCancelled):
        (core.download_images if kind == "image" else core.download_direct_video)(info, tmp_path)
    assert existing.read_bytes() == b"keep"
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob(".media-download-*"))
