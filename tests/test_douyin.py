import json

import pytest

from video_downloader.platforms import douyin


VIDEO_ID = "1234567890123456789"
NOTE_URL = f"https://www.douyin.com/note/{VIDEO_ID}"


def patch_share_page(
    monkeypatch: pytest.MonkeyPatch,
    item: dict,
    *,
    final_url: str = NOTE_URL,
) -> None:
    payload = {"item_list": [item]}
    html = f"{douyin.ROUTER_DATA_MARKER}{json.dumps(payload)}</script>"
    monkeypatch.setattr(
        douyin,
        "fetch_mobile_share_page",
        lambda url, timeout: (html, final_url),
    )
    monkeypatch.setattr(douyin, "preferred_video_url", lambda url, referer: url)


def test_image_post_with_video_field_stays_image(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_share_page(
        monkeypatch,
        {
            "aweme_id": VIDEO_ID,
            "desc": "图文内容",
            "media_type": 2,
            "video": {"play_addr": {"url_list": ["https://example.test/placeholder.mp4"]}},
            "image_post_info": {
                "images": [
                    {"display_image": {"url_list": ["https://example.test/1.jpg"]}},
                    {"url_list": ["https://example.test/2.jpg"]},
                ]
            },
        },
    )

    result = douyin.resolve_share_info(NOTE_URL)

    assert result is not None
    assert result.media_type == "image"
    assert result.play_url is None
    assert result.image_urls == ["https://example.test/1.jpg", "https://example.test/2.jpg"]
    assert result.webpage_url == NOTE_URL


def test_image_post_camel_case_fields_are_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_share_page(
        monkeypatch,
        {
            "aweme_id": VIDEO_ID,
            "desc": "轮播图文",
            "aweme_type": 68,
            "imagePost": {
                "images": [
                    {"displayImage": {"urlList": ["https://example.test/1.webp"]}},
                    "https://example.test/2.webp",
                ]
            },
        },
    )

    result = douyin.resolve_share_info(NOTE_URL)

    assert result is not None
    assert result.media_type == "image"
    assert result.image_urls == ["https://example.test/1.webp", "https://example.test/2.webp"]


def test_regular_video_remains_video(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_share_page(
        monkeypatch,
        {
            "aweme_id": VIDEO_ID,
            "desc": "普通视频",
            "media_type": 4,
            "video": {
                "play_addr": {"url_list": ["https://example.test/video.mp4"]},
                "cover": {"url_list": ["https://example.test/cover.jpg"]},
                "duration": 5000,
            },
        },
        final_url=f"https://www.douyin.com/video/{VIDEO_ID}",
    )

    result = douyin.resolve_share_info(f"https://www.douyin.com/video/{VIDEO_ID}")

    assert result is not None
    assert result.media_type == "video"
    assert result.play_url == "https://example.test/video.mp4"
    assert result.image_urls == []


def test_image_post_without_images_does_not_fall_back_to_video(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_share_page(
        monkeypatch,
        {
            "aweme_id": VIDEO_ID,
            "desc": "缺少图片资源的图文",
            "media_type": 42,
            "video": {"play_addr": {"url_list": ["https://example.test/placeholder.mp4"]}},
            "image_post_info": {"images": []},
        },
    )

    assert douyin.resolve_share_info(NOTE_URL) is None
