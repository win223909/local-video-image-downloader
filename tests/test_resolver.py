from urllib.error import HTTPError

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
        douyin_image_urls=[
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


def test_douyin_gallery_excludes_recommended_images() -> None:
    note_url = "https://www.douyin.com/note/7676089518466771683"
    result = BrowserResolveResult(
        requested_url=note_url,
        final_url=note_url,
        title="图文",
        description=None,
        thumbnail_url=None,
        canonical_url=note_url,
        video_url="https://example.com/placeholder.mp4",
        image_urls=["https://example.com/recommended.jpg"],
        douyin_image_urls=["https://example.com/one.jpg", "https://example.com/two.jpg"],
    )

    fallback = resolver.direct_browser_image_fallback(note_url, result)

    assert fallback is not None
    assert [item.url for item in fallback.info.images] == [
        "https://example.com/one.jpg", "https://example.com/two.jpg",
    ]


def test_douyin_video_page_does_not_use_recommended_images() -> None:
    video_url = "https://www.douyin.com/video/7676778645365158587"
    result = BrowserResolveResult(
        requested_url=video_url,
        final_url=video_url,
        title="视频",
        description=None,
        thumbnail_url=None,
        canonical_url=video_url,
        video_url=None,
        image_urls=["https://example.com/recommended-1.jpg", "https://example.com/recommended-2.jpg"],
    )

    assert resolver.direct_browser_image_fallback(video_url, result) is None


def test_douyin_long_gallery_is_not_truncated() -> None:
    note_url = "https://www.douyin.com/note/7676089518466771683"
    images = [f"https://example.com/{index}.jpg" for index in range(16)]
    result = BrowserResolveResult(
        requested_url=note_url,
        final_url=note_url,
        title="图文",
        description=None,
        thumbnail_url=None,
        canonical_url=note_url,
        video_url=None,
        douyin_image_urls=images,
    )

    fallback = resolver.direct_browser_image_fallback(note_url, result)

    assert fallback is not None
    assert [item.url for item in fallback.info.images] == images


def test_douyin_gallery_precedes_yt_dlp_video_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    note_url = "https://www.douyin.com/note/7676089518466771683"
    result = BrowserResolveResult(
        requested_url=note_url,
        final_url=note_url,
        title="图文",
        description=None,
        thumbnail_url=None,
        canonical_url=note_url,
        video_url="https://example.com/placeholder.mp4",
        douyin_image_urls=["https://example.com/one.jpg"],
    )
    calls = 0

    def never_parse_as_video(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("a confirmed gallery must not be parsed as video")

    monkeypatch.setattr(resolver, "resolve_douyin_share", lambda url: None)
    monkeypatch.setattr(resolver, "parse_video", never_parse_as_video)
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)

    resolved = resolver.resolve_video(note_url)

    assert resolved.info.media_type == "image"
    assert calls == 0


def test_douyin_shortlink_checks_gallery_before_video(monkeypatch: pytest.MonkeyPatch) -> None:
    short_url = "https://v.douyin.com/example/"
    note_url = "https://www.douyin.com/note/7676089518466771683"
    result = BrowserResolveResult(
        requested_url=short_url,
        final_url=note_url,
        title="图文",
        description=None,
        thumbnail_url=None,
        canonical_url=note_url,
        video_url="https://example.com/placeholder.mp4",
        douyin_image_urls=["https://example.com/one.jpg"],
    )
    monkeypatch.setattr(resolver, "resolve_douyin_share", lambda url: None)
    monkeypatch.setattr(resolver, "parse_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("shortlink gallery must be inspected before video parsing")
    ))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)

    assert resolver.resolve_video(short_url).info.media_type == "image"


def test_douyin_note_without_scoped_images_does_not_return_placeholder_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note_url = "https://www.douyin.com/note/7676089518466771683"
    result = BrowserResolveResult(
        requested_url=note_url,
        final_url=note_url,
        title="图文",
        description=None,
        thumbnail_url="https://example.com/cover.jpg",
        canonical_url=note_url,
        video_url="https://example.com/placeholder.mp4",
        image_urls=["https://example.com/recommended.jpg"],
    )
    monkeypatch.setattr(resolver, "resolve_douyin_share", lambda url: None)
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)

    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video(note_url)

    assert error.value.code == "incomplete_gallery"


@pytest.mark.parametrize(
    ("final_path", "error_code"),
    [("/404", "platform_link_expired"), ("/login", "platform_verification_required")],
)
def test_xiaohongshu_unavailable_page_stops_before_retry(
    monkeypatch: pytest.MonkeyPatch, final_path: str, error_code: str,
) -> None:
    note_url = "https://www.xiaohongshu.com/explore/640eea470000000012032c4e"
    result = BrowserResolveResult(
        requested_url=note_url,
        final_url=f"https://www.xiaohongshu.com{final_path}",
        title="小红书",
        description=None,
        thumbnail_url=None,
        canonical_url=None,
        video_url=None,
    )
    browser_calls = 0

    def load_page(*args, **kwargs):
        nonlocal browser_calls
        browser_calls += 1
        return result

    monkeypatch.setattr(resolver, "parse_video", lambda url: (_ for _ in ()).throw(VideoDownloaderError("No formats")))
    monkeypatch.setattr(resolver, "resolve_with_browser", load_page)

    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video(note_url)

    assert error.value.code == error_code
    assert browser_calls == 1


def test_xiaohongshu_shortlink_uses_public_note_target(monkeypatch: pytest.MonkeyPatch) -> None:
    target = "https://www.xiaohongshu.com/discovery/item/6a9e234f00000000250363b5?xsec_token=public"

    class RedirectingOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://xhslink.com/o/8wvDcEylIRP"
            assert timeout == 10
            raise HTTPError(request.full_url, 302, "Found", {"Location": target}, None)

    monkeypatch.setattr(resolver, "build_opener", lambda *args: RedirectingOpener())

    assert resolver.resolve_xiaohongshu_shortlink("http://xhslink.com/o/8wvDcEylIRP") == target


@pytest.mark.parametrize("location", [
    "https://example.com/discovery/item/6a9e234f00000000250363b5",
    "https://www.xiaohongshu.com.example.com/discovery/item/6a9e234f00000000250363b5",
    "http://www.xiaohongshu.com/discovery/item/6a9e234f00000000250363b5",
    "https://www.xiaohongshu.com/login",
    "https://[bad",
])
def test_xiaohongshu_shortlink_rejects_other_redirects(
    monkeypatch: pytest.MonkeyPatch, location: str,
) -> None:
    class RedirectingOpener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 302, "Found", {"Location": location}, None)

    monkeypatch.setattr(resolver, "build_opener", lambda *args: RedirectingOpener())

    assert resolver.resolve_xiaohongshu_shortlink("https://xhslink.com/o/example") is None


def test_other_urls_do_not_make_shortlink_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resolver, "build_opener", lambda *args: (_ for _ in ()).throw(
        AssertionError("only xhslink.com/o/ should make a shortlink request")
    ))

    assert resolver.resolve_xiaohongshu_shortlink("https://www.xiaohongshu.com/explore/123") is None
    assert resolver.resolve_xiaohongshu_shortlink("https://xhslink.com.example.com/o/123") is None


def test_xiaohongshu_shortlink_parses_expanded_note(monkeypatch: pytest.MonkeyPatch) -> None:
    shortlink = "https://xhslink.com/o/example"
    target = "https://www.xiaohongshu.com/discovery/item/6a9e234f00000000250363b5"
    info = object()
    monkeypatch.setattr(resolver, "resolve_xiaohongshu_shortlink", lambda url: target if url == shortlink else None)
    monkeypatch.setattr(resolver, "parse_video", lambda url: info if url == target else None)

    resolved = resolver.resolve_video(shortlink)

    assert resolved.info is info
    assert resolved.source == "yt-dlp"


def test_tiktok_photo_uses_current_slides_not_network_video(monkeypatch: pytest.MonkeyPatch) -> None:
    photo_url = "https://www.tiktok.com/@ryanair/photo/7579672560401452311"
    result = BrowserResolveResult(
        requested_url=photo_url,
        final_url=photo_url,
        title="Photo post",
        description=None,
        thumbnail_url=None,
        canonical_url=photo_url,
        video_url="https://example.com/unrelated.mp4",
        video_url_source="network",
        image_urls=["https://example.com/recommended.jpg"],
        tiktok_image_urls=["https://example.com/one.jpg", "https://example.com/two.jpg"],
    )
    monkeypatch.setattr(resolver, "parse_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("photo posts must not be parsed as video")
    ))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)

    resolved = resolver.resolve_video(photo_url)

    assert resolved.info.media_type == "image"
    assert [item.url for item in resolved.info.images] == [
        "https://example.com/one.jpg", "https://example.com/two.jpg",
    ]


def test_tiktok_photo_without_scoped_slides_is_not_video(monkeypatch: pytest.MonkeyPatch) -> None:
    photo_url = "https://www.tiktok.com/@ryanair/photo/7579672560401452311"
    result = BrowserResolveResult(
        requested_url=photo_url,
        final_url=photo_url,
        title="Photo post",
        description=None,
        thumbnail_url=None,
        canonical_url=photo_url,
        video_url="https://example.com/unrelated.mp4",
        image_urls=["https://example.com/recommended.jpg"],
    )
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)

    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video(photo_url)

    assert error.value.code == "incomplete_gallery"


def test_tiktok_photo_shortlink_uses_scoped_images() -> None:
    photo_url = "https://www.tiktok.com/@ryanair/photo/7579672560401452311"
    result = BrowserResolveResult(
        requested_url="https://vm.tiktok.com/example/",
        final_url=photo_url,
        title="Photo post",
        description=None,
        thumbnail_url=None,
        canonical_url=photo_url,
        video_url="https://example.com/unrelated.mp4",
        image_urls=["https://example.com/recommended.jpg"],
        tiktok_image_urls=["https://example.com/one.jpg"],
    )

    fallback = resolver.direct_browser_image_fallback(result.requested_url, result)

    assert fallback is not None
    assert [item.url for item in fallback.info.images] == ["https://example.com/one.jpg"]


def test_x_photo_without_confirmed_media_has_clear_error() -> None:
    error = VideoDownloaderError(
        "操作失败", code="unknown",
        raw_message="ERROR: [twitter] 123: No video could be found in this tweet",
    )

    result = resolver.public_error(error, "https://x.com/example/status/123")

    assert result.code == "unsupported_media"
    assert "图片帖" in str(result)
