import io
from pathlib import Path
from urllib.error import HTTPError

import pytest

from video_downloader import core
from video_downloader.core import VideoDownloaderError, extract_url_from_text, unique_path


def test_extract_url_from_share_text() -> None:
    text = "复制打开平台 https://example.com/video/123/ :abc"

    assert extract_url_from_text(text) == "https://example.com/video/123/"


def test_extract_url_rejects_empty_text() -> None:
    try:
        extract_url_from_text("  ")
    except Exception as error:
        assert "请输入视频链接" in str(error)
    else:
        raise AssertionError("empty text should be rejected")


def test_unique_path_adds_suffix(tmp_path: Path) -> None:
    original = tmp_path / "video.mp4"
    original.write_bytes(b"old")

    assert unique_path(original).name == "video (1).mp4"


def tiktok_info() -> dict:
    return {
        "extractor_key": "TikTok",
        "title": "Public test video",
        "id": "123",
        "http_headers": {"Referer": "https://www.tiktok.com/"},
        "formats": [
            {"format_id": "high", "url": "https://cdn.example/high.mp4", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 1080},
            {"format_id": "low", "url": "https://cdn.example/low.mp4", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 720},
        ],
    }


def test_tiktok_uses_readable_alternative_when_recommended_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = []

    def probe(url, headers, *, timeout):
        probes.append((url, headers, timeout))
        return url.endswith("low.mp4")

    monkeypatch.setattr(core, "media_url_readable", probe)
    info = core.validated_tiktok_info(tiktok_info())

    assert [fmt["format_id"] for fmt in info["formats"]] == ["low"]
    assert info["url"] == "https://cdn.example/low.mp4"
    assert [url for url, _, _ in probes] == ["https://cdn.example/high.mp4", "https://cdn.example/low.mp4"]
    assert all(headers["Referer"] == "https://www.tiktok.com/" for _, headers, _ in probes)


def test_tiktok_does_not_report_blocked_media_as_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "media_url_readable", lambda *args, **kwargs: False)

    with pytest.raises(VideoDownloaderError) as error:
        core.validated_tiktok_info(tiktok_info())

    assert error.value.code == "media_unreachable"


def test_tiktok_keeps_formats_when_recommended_is_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = []

    def probe(url, *args, **kwargs):
        probes.append(url)
        return True

    monkeypatch.setattr(core, "media_url_readable", probe)
    original = tiktok_info()

    assert core.validated_tiktok_info(original) is original
    assert probes == ["https://cdn.example/high.mp4"]


def test_tiktok_parse_rejects_unreadable_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            return tiktok_info()

    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(core, "media_url_readable", lambda *args, **kwargs: False)

    with pytest.raises(VideoDownloaderError) as error:
        core.parse_video("https://www.tiktok.com/@nasa/video/123")

    assert error.value.code == "media_unreachable"


def test_parse_rejects_empty_video_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            return {"extractor_key": "Generic", "title": "Fixture", "formats": []}

    monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYDL)

    with pytest.raises(VideoDownloaderError) as error:
        core.parse_video("https://example.test/video")

    assert error.value.code == "parse_format_unavailable"


def test_media_probe_checks_first_bytes_and_rejects_error_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response(io.BytesIO):
        status = 206

        def __init__(self, body: bytes, content_type: str):
            super().__init__(body)
            self.headers = {"content-type": content_type}

    def success(request, *, timeout, context):
        assert request.get_header("Range") == "bytes=0-31"
        assert request.get_header("Referer") == "https://www.tiktok.com/"
        return Response(b"\x00\x00\x00\x18ftypisom", "video/mp4")

    monkeypatch.setattr(core, "urlopen", success)
    assert core.media_url_readable("https://cdn.example/video.mp4", {"Referer": "https://www.tiktok.com/"}, timeout=4)

    monkeypatch.setattr(core, "urlopen", lambda *args, **kwargs: Response(b"<html>denied", "application/octet-stream"))
    assert not core.media_url_readable("https://cdn.example/video.mp4", {}, timeout=4)

    def forbidden(request, *, timeout, context):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(core, "urlopen", forbidden)
    assert not core.media_url_readable("https://cdn.example/video.mp4", {}, timeout=4)


def test_direct_video_retries_same_posts_alternative_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = "https://cdn.example/expired.mp4"
    second = "https://cdn.example/working.mp4"
    info = core.make_direct_video_info(
        url=first, webpage_url="https://www.douyin.com/video/123", title="Fixture",
        alternative_video_urls=[second],
    )
    attempts = []

    def download(url, part_path, headers, progress_hook=None):
        attempts.append(url)
        if url == first:
            raise VideoDownloaderError("expired", code="resource_forbidden")
        part_path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"fixture")

    monkeypatch.setattr(core, "download_direct_file", download)
    monkeypatch.setattr(core, "validate_media_file", lambda path, media_type, expected_duration=None: None)

    result = core.download_direct_video(info, tmp_path)

    assert attempts == [first, second]
    assert result.files[0].read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize(
    ("actual_duration", "should_pass"),
    [(2.1, False), (46.5, True)],
)
def test_direct_video_rejects_incomplete_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, actual_duration: float, should_pass: bool,
) -> None:
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"fixture")
    monkeypatch.setattr(core.shutil, "which", lambda name: "ffprobe")
    monkeypatch.setattr(
        core.subprocess, "run",
        lambda *args, **kwargs: core.subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"streams":[{"width":720,"height":1280}],"format":{"duration":"%s"}}' % actual_duration,
        ),
    )

    if should_pass:
        core.validate_media_file(video, "video", expected_duration=47)
    else:
        with pytest.raises(VideoDownloaderError) as error:
            core.validate_media_file(video, "video", expected_duration=47)
        assert error.value.code == "invalid_media"

