from pathlib import Path

from video_downloader.core import extract_url_from_text, unique_path


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

