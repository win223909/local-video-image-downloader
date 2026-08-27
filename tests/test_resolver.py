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


def test_instagram_image_fallback_uses_current_post_images_only() -> None:
    post_images = [f"https://cdn.example.com/post-{index}.jpg" for index in range(1, 17)]
    result = BrowserResolveResult(
        requested_url="https://www.instagram.com/p/example/",
        final_url="https://www.instagram.com/p/example/",
        title="Instagram",
        description=None,
        thumbnail_url="https://cdn.example.com/post-1.jpg",
        canonical_url="https://www.instagram.com/p/example/",
        video_url=None,
        image_urls=[
            "https://cdn.example.com/post-1.jpg",
            "https://cdn.example.com/recommended-1.jpg",
        ],
        post_image_urls=post_images,
    )

    fallback = resolver.direct_browser_image_fallback(
        "https://www.instagram.com/p/example/",
        result,
    )

    assert fallback is not None
    assert [image.url for image in fallback.info.images] == post_images


def test_douyin_note_with_video_response_prefers_image_fallback() -> None:
    video_id = "7676089518466771683"
    note_url = f"https://www.douyin.com/note/{video_id}"
    browser_result = BrowserResolveResult(
        requested_url="https://v.douyin.com/example/",
        final_url=note_url,
        title="图文内容 - 抖音",
        description=None,
        thumbnail_url="https://example.com/cover.webp",
        canonical_url=note_url,
        video_url="https://example.com/placeholder.mp4",
        video_url_source="dom",
        image_urls=[
            "https://example.com/image-1.webp",
            "https://example.com/image-2.webp",
        ],
    )

    assert resolver.direct_browser_fallback(
        "https://v.douyin.com/example/",
        browser_result,
        None,
    ) is None

    fallback = resolver.direct_browser_image_fallback(
        "https://v.douyin.com/example/",
        browser_result,
    )

    assert fallback is not None
    assert fallback.info.media_type == "image"
    assert len(fallback.info.images) == 2
