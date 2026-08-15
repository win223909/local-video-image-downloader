import pytest

from video_downloader.browser_session import BrowserResolveResult
from video_downloader.core import VideoDownloaderError
from video_downloader import resolver


def browser_result_with_images() -> BrowserResolveResult:
    return BrowserResolveResult(
        requested_url="https://www.youtube.com/watch?v=example",
        final_url="https://www.youtube.com/watch?v=example",
        title="Example video",
        description=None,
        thumbnail_url="https://i.ytimg.com/vi/example/hqdefault.jpg",
        canonical_url=None,
        video_url=None,
        image_urls=[
            "https://i.ytimg.com/vi/example/hqdefault.jpg",
            "https://www.youtube.com/img/branding/youtube-logo.png",
        ],
    )


def test_youtube_thumbnail_is_not_returned_as_image_fallback() -> None:
    assert resolver.direct_browser_image_fallback(
        "https://www.youtube.com/watch?v=example",
        browser_result_with_images(),
    ) is None


def test_youtube_verification_failure_is_not_downgraded_to_image(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_parse(*args, **kwargs):
        raise VideoDownloaderError("需要验证", code="cookies_required")

    monkeypatch.setattr(resolver, "parse_video", fail_parse)
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda *args, **kwargs: browser_result_with_images())

    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video("https://www.youtube.com/watch?v=example")

    assert error.value.code == "platform_verification_required"
    assert "图片" not in str(error.value)


def test_non_youtube_image_page_can_still_use_image_fallback() -> None:
    result = BrowserResolveResult(
        requested_url="https://example.com/gallery/1",
        final_url="https://example.com/gallery/1",
        title="Gallery",
        description=None,
        thumbnail_url="https://example.com/gallery/cover.jpg",
        canonical_url="https://example.com/gallery/1",
        video_url=None,
        image_urls=["https://example.com/gallery/1.jpg", "https://example.com/gallery/2.jpg"],
    )

    fallback = resolver.direct_browser_image_fallback("https://example.com/gallery/1", result)

    assert fallback is not None
    assert fallback.info.media_type == "image"
