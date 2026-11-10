from dataclasses import replace
from urllib.error import HTTPError
from unittest.mock import Mock

import pytest

from video_downloader.browser_session import BrowserResolveResult
from video_downloader.core import VideoDownloaderError
from video_downloader import resolver
from video_downloader import core


@pytest.mark.parametrize("source", ["browser", "browser+yt-dlp"])
@pytest.mark.parametrize("direct", [False, True])
def test_browser_download_refreshes_expired_resource(tmp_path, monkeypatch, source, direct):
    url = "https://example.test/post"
    old = core.make_direct_video_info(url="https://example.test/expired.mp4", webpage_url=url, title="Fixture")
    fresh = core.make_direct_video_info(url="https://example.test/fresh.mp4", webpage_url=url, title="Fixture")
    browser = BrowserResolveResult(url, url, "Fixture", None, None, url, fresh.url)
    resolved = resolver.ResolvedVideo(info=old, source=source, browser_result=browser)
    refresh = Mock(return_value=browser)
    cleanup = Mock()
    download = Mock(side_effect=[core.VideoDownloaderError("expired", code="resource_forbidden"), core.DownloadResult(tmp_path, [])])
    monkeypatch.setattr(resolver, "resolve_with_browser", refresh)
    monkeypatch.setattr(resolver, "direct_browser_fallback", lambda *args: resolver.ResolvedVideo(info=fresh, source="browser"))
    monkeypatch.setattr(resolver, "remove_exported_cookie_file", cleanup)
    monkeypatch.setattr(resolver, "download_direct_video" if direct else "download_video", download)
    result = resolver.download_resolved_video(resolved, old.formats[0] if direct else None, tmp_path)
    assert result.output_dir == tmp_path
    refresh.assert_called_once_with(url)
    assert download.call_count == 2
    assert download.call_args.kwargs["info" if direct else "url"] == (fresh if direct else fresh.url)
    cleanup.assert_called_once_with(browser.cookie_file)


@pytest.mark.parametrize("error", [core.DownloadCancelled(), core.VideoDownloaderError("denied", code="unsupported_url")])
def test_browser_download_does_not_refresh_cancel_or_nonretryable_error(tmp_path, monkeypatch, error):
    browser = browser_result_with_images()
    info = core.make_direct_video_info(url="https://example.test/video.mp4", webpage_url=browser.requested_url, title="Fixture")
    resolved = resolver.ResolvedVideo(info=info, source="browser+yt-dlp", browser_result=browser)
    refresh = Mock()
    monkeypatch.setattr(resolver, "resolve_with_browser", refresh)
    monkeypatch.setattr(resolver, "download_video", Mock(side_effect=error))
    with pytest.raises(core.VideoDownloaderError) as raised:
        resolver.download_resolved_video(resolved, None, tmp_path)
    assert raised.value is error
    refresh.assert_not_called()


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


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BVfixture", "https://b23.tv/fixture",
])
def test_bilibili_player_and_recommendations_are_not_download_results(monkeypatch, url):
    result = BrowserResolveResult(
        requested_url=url, final_url="https://www.bilibili.com/video/BVfixture",
        title="Fixture", description=None, thumbnail_url="https://cdn.example/cover.jpg",
        canonical_url=None, video_url="https://player.bilibili.com/player.html?bvid=BVfixture",
        video_url_source="og", image_urls=["https://cdn.example/recommendation.jpg"],
    )
    assert resolver.direct_browser_fallback(url, result, None) is None
    assert resolver.direct_browser_image_fallback(url, result) is None
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda *a, **kw: result)
    monkeypatch.setattr(resolver, "parse_video", Mock(side_effect=VideoDownloaderError(
        "No public video", code="parse_format_unavailable")))
    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video(url)
    assert error.value.code == "parse_format_unavailable"


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
    assert fallback.info.title == "Instagram 图文"


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


def test_douyin_shortlink_uses_matching_detail_instead_of_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short_url = "https://v.douyin.com/example/"
    video_id = "7699071391610571621"
    page_url = f"https://www.douyin.com/video/{video_id}"
    result = BrowserResolveResult(
        requested_url=short_url,
        final_url=page_url,
        title="数学视频 - 抖音",
        description=None,
        thumbnail_url=None,
        canonical_url=page_url,
        video_url="https://example.test/placeholder.mp4",
        video_url_source="network",
        douyin_detail_items=[{
            "aweme_id": video_id,
            "desc": "数学视频",
            "video": {"play_addr": {"url_list": ["https://example.test/target.mp4"]}},
        }],
    )
    monkeypatch.setattr(resolver, "resolve_douyin_share", lambda url: None)
    monkeypatch.setattr(resolver.douyin, "preferred_video_url", lambda url, referer: url)
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)
    monkeypatch.setattr(resolver, "parse_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("shortlink with confirmed detail should not use yt-dlp")
    ))

    resolved = resolver.resolve_video(short_url)

    assert resolved.source == "douyin-share"
    assert resolved.info.media_type == "video"
    assert resolved.info.video_id == video_id
    assert resolved.info.preview_url == "https://example.test/target.mp4"


def test_douyin_unrelated_detail_does_not_verify_network_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short_url = "https://v.douyin.com/example/"
    video_id = "7699071391610571621"
    page_url = f"https://www.douyin.com/video/{video_id}"
    result = BrowserResolveResult(
        requested_url=short_url,
        final_url=page_url,
        title="数学视频 - 抖音",
        description=None,
        thumbnail_url=None,
        canonical_url=page_url,
        video_url="https://example.test/placeholder.mp4",
        video_url_source="network",
        douyin_detail_items=[{
            "aweme_id": "9999999999999999999",
            "video": {"play_addr": {"url_list": ["https://example.test/unrelated.mp4"]}},
        }],
    )
    monkeypatch.setattr(resolver, "resolve_douyin_share", lambda url: None)
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)
    monkeypatch.setattr(resolver, "parse_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        VideoDownloaderError("平台没有返回视频", code="unsupported_url")
    ))

    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_video(short_url)

    assert error.value.code == "unverified_media"


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


def test_tiktok_login_page_title_is_not_used_as_photo_title() -> None:
    photo_url = "https://www.tiktok.com/@ryanair/photo/7579672560401452311"
    result = BrowserResolveResult(
        requested_url=photo_url, final_url=photo_url, title="登录 | TikTok",
        description=None, thumbnail_url=None, canonical_url=photo_url,
        video_url=None, tiktok_image_urls=["https://example.com/one.jpg"],
    )

    fallback = resolver.direct_browser_image_fallback(photo_url, result)

    assert fallback is not None
    assert fallback.info.title == "TikTok 图文"


def test_tiktok_network_playback_fragment_is_not_downloaded_as_full_video() -> None:
    video_url = "https://www.tiktok.com/@nasa/video/7665840565958872333"
    result = BrowserResolveResult(
        requested_url=video_url, final_url=video_url, title="登录 | TikTok",
        description=None, thumbnail_url=None, canonical_url=video_url,
        video_url="https://cdn.example/first-segment.mp4", video_url_source="network",
    )

    assert resolver.direct_browser_fallback(video_url, result, None) is None
    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_from_browser_result(video_url, result)
    assert error.value.code == "media_unreachable"


def tiktok_structured_result():
    url = "https://www.tiktok.com/@fixture/video/7665840565958872333"
    return BrowserResolveResult(
        requested_url=url, final_url=url, title="Fixture", description=None, thumbnail_url=None,
        canonical_url=url, video_url="https://cdn.example/fragment.mp4", video_url_source="network",
        tiktok_item={"id": "7665840565958872333", "desc": "Fixture", "privateItem": False,
                     "video": {"duration": 47, "PlayAddrStruct": {"UrlList": [
                         "https://cdn.example/blocked.mp4",
                         "https://www.tiktok.com/aweme/v1/play/?item_id=7665840565958872333&signature=fixture%2B",
                     ]}}},
    )


def test_tiktok_refresh_uses_unchanged_same_post_public_url(monkeypatch):
    result = tiktok_structured_result()
    probes = []
    def probe(url, headers, *, timeout):
        probes.append(url)
        return url.startswith("https://www.tiktok.com/aweme/")
    monkeypatch.setattr(core, "media_url_readable", probe)
    monkeypatch.setattr(resolver, "parse_video", Mock(side_effect=VideoDownloaderError("CDN blocked", code="media_unreachable")))
    monkeypatch.setattr(resolver, "resolve_with_browser", lambda url: result)
    resolved = resolver.resolve_video(result.requested_url)
    assert resolved.info.url == result.tiktok_item["video"]["PlayAddrStruct"]["UrlList"][1]
    assert resolved.info.duration == 47
    assert resolved.source == "browser"
    assert result.video_url not in probes


@pytest.mark.parametrize("change", [
    {"id": "different"}, {"privateItem": True}, {"forFriend": True}, {"secret": True},
    {"isProhibited": True}, {"takeDown": True}, {"imagePost": {"images": []}},
    {"video": {"PlayAddrStruct": {"UrlList": ["https://cdn.example/unproven.mp4"]}}},
])
def test_tiktok_does_not_use_unproven_or_restricted_structured_video(monkeypatch, change):
    result = tiktok_structured_result()
    result.tiktok_item.update(change)
    probe = Mock(side_effect=AssertionError("restricted data must not be probed"))
    monkeypatch.setattr(core, "media_url_readable", probe)
    assert resolver.direct_browser_fallback(result.requested_url, result, None) is None
    probe.assert_not_called()


@pytest.mark.parametrize("final", [
    "https://www.tiktok.com/@fixture/video/9999999999999999999",
    "https://evil.example/@fixture/video/7665840565958872333",
])
def test_tiktok_does_not_follow_different_post_or_host(final):
    result = tiktok_structured_result()
    result = replace(result, final_url=final)
    result.tiktok_item["id"] = final.rsplit("/", 1)[-1]
    assert resolver.direct_browser_fallback(result.requested_url, result, None) is None


def tiktok_gallery_result():
    result = tiktok_structured_result()
    photo_url = result.final_url.replace("/video/", "/photo/")
    result.tiktok_item["imagePost"] = {"images": [
        {"imageURL": {"urlList": [f"https://cdn.example/{name}.jpg", f"https://backup.example/{name}.jpg"]}}
        for name in ("one", "two", "three")
    ]}
    return replace(result, requested_url=photo_url, final_url=photo_url,
                   image_urls=["https://cdn.example/recommended.jpg"],
                   tiktok_image_urls=["https://cdn.example/one.jpg"])


def test_tiktok_gallery_uses_all_structured_images_not_only_visible_slide():
    result = tiktok_gallery_result()
    resolved = resolver.resolve_from_browser_result(result.requested_url, result)
    assert resolved.info.media_type == "image"
    assert [image.url for image in resolved.info.images] == [
        f"https://cdn.example/{name}.jpg" for name in ("one", "two", "three")
    ]
    assert resolved.info.images[0].alternative_urls == ["https://backup.example/one.jpg"]


@pytest.mark.parametrize("change", [
    {"id": "different"}, {"privateItem": True},
    {"imagePost": {"images": [{"imageURL": {"urlList": ["https://cdn.example/one.jpg"]}}, {}]}},
    {"imagePost": {"images": []}}, {"imagePost": {"images": [{}] * 51}},
])
def test_tiktok_gallery_rejects_incomplete_or_unrelated_structured_data(change):
    result = tiktok_gallery_result()
    result.tiktok_item.update(change)
    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_from_browser_result(result.requested_url, result)
    assert error.value.code == "incomplete_gallery"


def test_tiktok_photo_retries_same_post_document_once_and_cleans_cookies(monkeypatch, tmp_path):
    result = tiktok_gallery_result()
    first_cookie, second_cookie = tmp_path / "first", tmp_path / "second"
    empty = replace(result, tiktok_item=None, tiktok_image_urls=[], cookie_file=first_cookie)
    complete = replace(result, cookie_file=second_cookie)
    load = Mock(side_effect=[empty, complete])
    cleanup = Mock()
    monkeypatch.setattr(resolver, "resolve_with_browser", load)
    monkeypatch.setattr(resolver, "remove_exported_cookie_file", cleanup)
    resolved = resolver.resolve_browser_fallback("https://vm.tiktok.com/fixture/")
    assert len(resolved.info.images) == 3
    assert [call.args[0] for call in load.call_args_list] == [
        "https://vm.tiktok.com/fixture/", result.final_url.replace("/photo/", "/video/"),
    ]
    assert [call.args[0] for call in cleanup.call_args_list] == [first_cookie, second_cookie]


def test_tiktok_photo_retry_cannot_follow_a_different_post_from_shortlink(monkeypatch):
    result = tiktok_gallery_result()
    empty = replace(result, tiktok_item=None, tiktok_image_urls=[])
    other = replace(result, final_url=result.final_url.replace("7665840565958872333", "9999999999999999999"))
    other.tiktok_item["id"] = "9999999999999999999"
    load = Mock(side_effect=[empty, other])
    monkeypatch.setattr(resolver, "resolve_with_browser", load)
    with pytest.raises(VideoDownloaderError) as error:
        resolver.resolve_browser_fallback("https://vm.tiktok.com/fixture/")
    assert error.value.code == "incomplete_gallery"
    assert load.call_count == 2


def test_x_photo_without_confirmed_media_has_clear_error() -> None:
    error = VideoDownloaderError(
        "操作失败", code="unknown",
        raw_message="ERROR: [twitter] 123: No video could be found in this tweet",
    )

    result = resolver.public_error(error, "https://x.com/example/status/123")

    assert result.code == "unsupported_media"
    assert "图片帖" in str(result)
