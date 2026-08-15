from __future__ import annotations

import base64
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from video_downloader.browser_session import BrowserResolveResult, resolve_with_browser
from video_downloader.core import (
    CookieOptions,
    DownloadResult,
    FormatOption,
    ImageItem,
    VideoDownloaderError,
    VideoInfo,
    download_direct_video,
    download_images,
    download_video,
    extract_url_from_text,
    image_ext_from_url,
    make_direct_video_info,
    make_image_info,
    parse_video,
)
from video_downloader.platforms import douyin


StatusHook = Callable[[str], None]


@dataclass(frozen=True)
class ResolvedVideo:
    info: VideoInfo
    cookie_file: Path | None = None
    browser_result: BrowserResolveResult | None = None
    source: str = "yt-dlp"


@dataclass(frozen=True)
class BrowserMetadata:
    title: str
    uploader: str
    channel: str
    extractor: str
    webpage_url: str
    video_id: str | None = None


def resolve_video(text: str, status_hook: StatusHook | None = None) -> ResolvedVideo:
    url = extract_url_from_text(text)
    if status_hook:
        status_hook("正在解析视频...")

    direct_image = resolve_direct_image_url(url)
    if direct_image:
        return direct_image

    if douyin.is_douyin_url(url):
        douyin_result = resolve_douyin_share(url)
        if douyin_result:
            return douyin_result

    try:
        return ResolvedVideo(info=parse_video(url), source="yt-dlp")
    except VideoDownloaderError as first_error:
        if not should_use_browser_fallback(first_error, url):
            raise public_error(first_error, url)

    if status_hook:
        status_hook("正在解析视频...")
    try:
        browser_result = resolve_with_browser(url)
    except Exception as exc:
        raise VideoDownloaderError("该视频需要平台验证，当前无法无感解析。", code="browser_fallback_failed", raw_message=str(exc)) from exc
    if is_xiaohongshu_url(url) and not browser_result.video_url and not browser_result.image_urls:
        if status_hook:
            status_hook("正在重新读取公开页面...")
        browser_result = resolve_with_browser(url, timeout_ms=26000)

    cookie_file = browser_result.cookie_file
    cookie_options = CookieOptions(cookie_file=str(cookie_file)) if cookie_file else CookieOptions()

    candidate_urls = candidate_parse_urls(url, browser_result)
    last_error: VideoDownloaderError | None = None
    for candidate_url in candidate_urls:
        try:
            info = parse_video(candidate_url, cookies=cookie_options)
            if browser_result.video_url and not info.preview_url:
                info = replace(
                    info,
                    preview_url=browser_result.video_url,
                    cookie_file=str(cookie_file) if cookie_file else None,
                    http_headers=browser_result.http_headers,
                )
            elif cookie_file and not info.cookie_file:
                info = replace(info, cookie_file=str(cookie_file))
            return ResolvedVideo(info=info, cookie_file=cookie_file, browser_result=browser_result, source="browser+yt-dlp")
        except VideoDownloaderError as exc:
            last_error = exc

    fallback = direct_browser_fallback(url, browser_result, cookie_file)
    if fallback:
        return fallback

    image_fallback = direct_browser_image_fallback(url, browser_result)
    if image_fallback:
        return image_fallback

    if douyin.is_douyin_url(url) and browser_result.video_url_source == "network":
        raise VideoDownloaderError("平台没有返回可确认的目标视频资源，请重新复制链接后再试。", code="unverified_media")

    if douyin.is_douyin_url(url) and douyin.looks_like_homepage(browser_result):
        raise VideoDownloaderError("链接已失效或平台未返回具体视频，请重新复制分享链接。", code="platform_link_expired")

    if last_error:
        raise public_error(last_error, url)
    raise VideoDownloaderError("该视频需要平台验证，当前无法无感解析。", code="platform_verification_required")


def resolve_douyin_share(url: str) -> ResolvedVideo | None:
    try:
        share_info = douyin.resolve_share_info(url)
    except Exception:
        return None
    if not share_info:
        return None

    if share_info.media_type == "image":
        images = [
            ImageItem(
                url=image_url,
                thumbnail_url=image_url,
                ext=image_ext_from_url(image_url) or "jpg",
                note="抖音图文",
                http_headers=share_info.http_headers,
            )
            for image_url in share_info.image_urls
        ]
        info = make_image_info(
            url=url,
            webpage_url=share_info.webpage_url,
            title=share_info.title,
            uploader=share_info.uploader,
            channel=share_info.uploader,
            images=images,
            thumbnail=share_info.thumbnail_url,
            extractor="Douyin",
            http_headers=share_info.http_headers,
            video_id=share_info.aweme_id,
        )
        return ResolvedVideo(info=info, source="douyin-share")

    resolution = (
        f"{share_info.width}x{share_info.height}"
        if share_info.width and share_info.height
        else "自动最高"
    )
    info = make_direct_video_info(
        url=share_info.play_url or "",
        webpage_url=share_info.webpage_url,
        title=share_info.title,
        uploader=share_info.uploader,
        channel=share_info.uploader,
        thumbnail=share_info.thumbnail_url,
        duration=share_info.duration,
        ext="mp4",
        preview_url=share_info.play_url,
        extractor="Douyin",
        http_headers=share_info.http_headers,
        video_id=share_info.aweme_id,
    )
    if info.formats:
        first = info.formats[0]
        info = replace(
            info,
            formats=[
                replace(
                    first,
                    resolution=resolution,
                    note="优先原始资源",
                )
            ],
        )
    return ResolvedVideo(info=info, source="douyin-share")


def resolve_direct_image_url(url: str) -> ResolvedVideo | None:
    ext = image_ext_from_url(url)
    if not ext:
        return None
    image = ImageItem(url=url, thumbnail_url=url, ext=ext, note="直接图片链接")
    info = make_image_info(
        url=url,
        webpage_url=url,
        title="图片",
        uploader="未知作者",
        channel="未知频道",
        images=[image],
        thumbnail=url,
        extractor="Image",
    )
    return ResolvedVideo(info=info, source="direct-image")


def candidate_parse_urls(original_url: str, browser_result: BrowserResolveResult) -> list[str]:
    candidates: list[str] = []
    if douyin.is_douyin_url(original_url):
        normalized = douyin.normalized_video_url(browser_result)
        if normalized:
            candidates.append(normalized)

    for value in [browser_result.canonical_url, browser_result.final_url, original_url]:
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def direct_browser_fallback(
    original_url: str,
    browser_result: BrowserResolveResult,
    cookie_file: Path | None,
) -> ResolvedVideo | None:
    if not browser_result.video_url:
        return None
    if douyin.is_douyin_url(original_url) and not douyin.normalized_video_url(browser_result):
        return None
    if douyin.is_douyin_url(original_url) and browser_result.video_url_source == "network":
        return None

    metadata = browser_metadata(original_url, browser_result)
    media_url = browser_download_url(original_url, browser_result.video_url, browser_result)
    audio_url = browser_audio_url(original_url, browser_result)
    info = make_direct_video_info(
        url=media_url,
        webpage_url=metadata.webpage_url,
        title=metadata.title,
        uploader=metadata.uploader,
        channel=metadata.channel,
        thumbnail=browser_result.thumbnail_url,
        preview_url=media_url,
        extractor=metadata.extractor,
        cookie_file=str(cookie_file) if cookie_file else None,
        http_headers=browser_result.http_headers,
        video_id=metadata.video_id,
        audio_url=audio_url,
    )
    return ResolvedVideo(info=info, cookie_file=cookie_file, browser_result=browser_result, source="browser")


def direct_browser_image_fallback(
    original_url: str,
    browser_result: BrowserResolveResult,
) -> ResolvedVideo | None:
    image_urls = dedupe_urls(browser_result.image_urls)
    if not image_urls:
        return None
    # A normal YouTube page always exposes a thumbnail, and often several
    # related images, even when the video itself could not be extracted.
    # Never turn that verification failure into a misleading image result.
    if any(
        is_youtube_url(value)
        for value in (original_url, browser_result.final_url, browser_result.canonical_url)
        if value
    ):
        return None
    if is_instagram_reel_url(original_url) or is_instagram_reel_url(browser_result.canonical_url or ""):
        return None
    if douyin.is_douyin_url(original_url):
        if douyin.looks_like_homepage(browser_result):
            return None
        is_image_page = douyin.looks_like_image_page(browser_result.final_url, browser_result.canonical_url)
        if not is_image_page and len(image_urls) < 2:
            return None
    headers = browser_result.http_headers
    images = [
        ImageItem(
            url=image_url,
            thumbnail_url=image_url,
            ext=image_ext_from_url(image_url) or "jpg",
            note="页面图片",
            http_headers=headers,
        )
        for image_url in image_urls[:12]
    ]
    info = make_image_info(
        url=original_url,
        webpage_url=browser_result.canonical_url or browser_result.final_url or original_url,
        title=clean_title(browser_result.title) or "图片",
        uploader="未知作者",
        channel="未知频道",
        images=images,
        thumbnail=browser_result.thumbnail_url,
        extractor="Image",
        http_headers=headers,
    )
    return ResolvedVideo(info=info, browser_result=browser_result, source="browser-image")


def download_resolved_video(
    resolved: ResolvedVideo,
    selected: FormatOption | None,
    output_dir: str | Path,
    progress_hook=None,
    status_hook: StatusHook | None = None,
) -> DownloadResult:
    if resolved.info.media_type == "image":
        return download_images(
            info=resolved.info,
            output_dir=output_dir,
            progress_hook=progress_hook,
        )

    cookie_file = resolved.info.cookie_file or (str(resolved.cookie_file) if resolved.cookie_file else None)
    cookies = CookieOptions(cookie_file=cookie_file) if cookie_file else CookieOptions()

    if resolved.source == "douyin-share":
        return download_direct_video(
            info=resolved.info,
            output_dir=output_dir,
            progress_hook=progress_hook,
        )
    if selected and selected.key == "direct-best":
        try:
            return download_direct_video(
                info=resolved.info,
                output_dir=output_dir,
                progress_hook=progress_hook,
            )
        except VideoDownloaderError as exc:
            if resolved.source != "browser" or not resolved.browser_result:
                raise exc
            if exc.code not in {"resource_not_found", "resource_forbidden", "network_timeout", "unknown", "incomplete_media_fragment"}:
                raise exc
            if status_hook:
                status_hook("下载地址已刷新，正在重新下载...")
            refreshed = resolve_with_browser(resolved.browser_result.requested_url)
            refreshed_fallback = direct_browser_fallback(resolved.browser_result.requested_url, refreshed, refreshed.cookie_file)
            if not refreshed_fallback:
                raise VideoDownloaderError("平台没有返回可下载的视频资源，请重新复制链接后再试。", code="browser_download_refresh_failed") from exc
            return download_direct_video(
                info=refreshed_fallback.info,
                output_dir=output_dir,
                progress_hook=progress_hook,
            )

    if resolved.source != "browser" or not resolved.browser_result:
        return download_video(
            url=resolved.info.url,
            selector=selected.selector if selected else "bestvideo+bestaudio/best",
            output_dir=output_dir,
            progress_hook=progress_hook,
            cookies=cookies,
            http_headers=resolved.info.http_headers,
        )

    try:
        return download_video(
            url=resolved.info.url,
            selector=selected.selector if selected else "bestvideo+bestaudio/best",
            output_dir=output_dir,
            progress_hook=progress_hook,
            cookies=cookies,
            http_headers=resolved.info.http_headers,
        )
    except VideoDownloaderError as exc:
        if exc.code not in {"resource_not_found", "resource_forbidden", "network_timeout", "unknown"}:
            raise exc

    if status_hook:
        status_hook("下载地址已刷新，正在重新下载...")
    refreshed = resolve_with_browser(resolved.browser_result.requested_url)
    refreshed_fallback = direct_browser_fallback(resolved.browser_result.requested_url, refreshed, refreshed.cookie_file)
    if not refreshed_fallback:
        raise VideoDownloaderError("平台没有返回可下载的视频资源，请重新复制链接后再试。", code="browser_download_refresh_failed")

    refreshed_info = refreshed_fallback.info
    refreshed_cookies = (
        CookieOptions(cookie_file=refreshed_info.cookie_file)
        if refreshed_info.cookie_file
        else CookieOptions()
    )
    return download_video(
        url=refreshed_info.url,
        selector=refreshed_info.formats[0].selector,
        output_dir=output_dir,
        progress_hook=progress_hook,
        cookies=refreshed_cookies,
        http_headers=refreshed_info.http_headers,
    )


def should_use_browser_fallback(error: VideoDownloaderError, url: str) -> bool:
    if douyin.is_douyin_url(url):
        return True
    if is_xiaohongshu_url(url):
        return True
    if is_instagram_url(url):
        return True
    return error.code in {"unsupported_url", "cookies_required", "login_required", "network_timeout", "unknown"}


def public_error(error: VideoDownloaderError, url: str) -> VideoDownloaderError:
    if douyin.is_douyin_url(url) and error.code in {"douyin_shortlink_home", "unsupported_url"}:
        return VideoDownloaderError("链接已失效或平台未返回具体视频，请重新复制分享链接。", code="platform_link_expired", raw_message=error.raw_message)
    if error.code in {"cookies_required", "login_required", "cookies_load_failed", "auto_cookies_failed"}:
        return VideoDownloaderError("该视频需要平台验证，当前无法无感解析。", code="platform_verification_required", raw_message=error.raw_message)
    if error.code == "unsupported_url":
        return VideoDownloaderError("暂不支持这个链接，或平台没有返回可解析的视频。", code=error.code, raw_message=error.raw_message)
    return error


def clean_title(title: str | None) -> str:
    if not title:
        return ""
    title = title.strip()
    suffixes = [" - 抖音", " - Douyin", " | 抖音", " | Douyin", " • Instagram photos and videos"]
    for suffix in suffixes:
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    return title.strip()


def browser_metadata(original_url: str, browser_result: BrowserResolveResult) -> BrowserMetadata:
    webpage_url = browser_result.canonical_url or browser_result.final_url or original_url
    if (
        is_instagram_url(original_url)
        or is_instagram_url(browser_result.final_url)
        or is_instagram_url(browser_result.canonical_url or "")
    ):
        return instagram_browser_metadata(original_url, browser_result)

    title = clean_title(browser_result.title)
    if title.lower() in {"instagram", "log in", "登录"}:
        title = ""
    title = title or clean_description_title(browser_result.description) or "未命名视频"
    return BrowserMetadata(
        title=title,
        uploader="未知作者",
        channel="未知频道",
        extractor="Browser",
        webpage_url=webpage_url,
    )


def instagram_browser_metadata(original_url: str, browser_result: BrowserResolveResult) -> BrowserMetadata:
    webpage_url = browser_result.canonical_url or browser_result.final_url or original_url
    shortcode = instagram_shortcode(webpage_url) or instagram_shortcode(original_url)
    uploader, caption = instagram_caption_from_description(browser_result.description or "")

    if not uploader:
        uploader = instagram_uploader_from_excerpt(browser_result.html_excerpt)
    if not caption:
        caption = instagram_caption_from_excerpt(browser_result.html_excerpt)

    title = clean_instagram_text(caption)
    if not title:
        title = clean_title(browser_result.title)
    if title.lower() in {"instagram", "log in", "登录"}:
        title = ""
    if not title and uploader:
        title = f"Instagram Reel by {uploader}"
    if not title:
        title = "Instagram Reel"

    return BrowserMetadata(
        title=title,
        uploader=uploader or "未知作者",
        channel=uploader or "未知频道",
        extractor="Instagram",
        webpage_url=webpage_url,
        video_id=shortcode,
    )


def instagram_caption_from_description(description: str) -> tuple[str, str]:
    if not description:
        return "", ""
    normalized = " ".join(description.split())
    match = re.search(
        r"-\s*([A-Za-z0-9_.]+)\s*[，,]\s*[^:：]{0,120}[:：]\s*[\"“](.+?)[\"”]\.?\s*$",
        normalized,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()

    match = re.search(r"-\s*([A-Za-z0-9_.]+)\s*[，,]\s*(.+)$", normalized)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", ""


def instagram_uploader_from_excerpt(excerpt: str) -> str:
    if not excerpt:
        return ""
    for token in re.findall(r"\b[A-Za-z0-9_][A-Za-z0-9_.]{2,29}\b", excerpt):
        lowered = token.lower()
        if lowered not in {"instagram", "reels", "login", "meta"}:
            return token
    return ""


def instagram_caption_from_excerpt(excerpt: str) -> str:
    if not excerpt:
        return ""
    lines = [line.strip() for line in re.split(r"[\n|]", excerpt) if line.strip()]
    for line in lines:
        if "#" in line and len(line) > 8:
            return line
    return ""


def clean_description_title(description: str | None) -> str:
    if not description:
        return ""
    title = " ".join(description.split()).strip()
    if len(title) > 180:
        title = title[:180].rstrip() + "..."
    return title


def clean_instagram_text(value: str | None) -> str:
    if not value:
        return ""
    value = " ".join(value.split()).strip(" \"“”'")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def browser_download_url(original_url: str, media_url: str, browser_result: BrowserResolveResult | None = None) -> str:
    if is_instagram_url(original_url):
        selected = select_instagram_media_url(browser_result.media_urls if browser_result else [], want_audio=False)
        return strip_byte_range_query(selected or media_url)
    return media_url


def browser_audio_url(original_url: str, browser_result: BrowserResolveResult) -> str | None:
    if not is_instagram_url(original_url):
        return None
    selected = select_instagram_media_url(browser_result.media_urls, want_audio=True)
    return strip_byte_range_query(selected) if selected else None


def select_instagram_media_url(urls: list[str], *, want_audio: bool) -> str | None:
    candidates = [
        url
        for url in dedupe_urls(urls)
        if ".mp4" in url.lower() and instagram_media_is_audio(url) == want_audio
    ]
    if not candidates:
        return None
    return max(candidates, key=instagram_media_score)


def instagram_media_is_audio(url: str) -> bool:
    metadata = instagram_media_metadata(url)
    tag = str(metadata.get("vencode_tag") or metadata.get("encode_tag") or "").lower()
    if "audio" in tag:
        return True
    path = urlparse(url).path.lower()
    return "/m78/" in path and "dash_ln_heaac" in tag


def instagram_media_score(url: str) -> tuple[int, int, int]:
    metadata = instagram_media_metadata(url)
    tag = str(metadata.get("vencode_tag") or metadata.get("encode_tag") or "").lower()
    bitrate = as_int(metadata.get("bitrate"))
    resolution = 0
    match = re.search(r"(\d{3,4})p", tag)
    if match:
        resolution = int(match.group(1))
    return (resolution, bitrate, -len(url))


def instagram_media_metadata(url: str) -> dict[str, object]:
    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    raw = query.get("efg")
    if not raw:
        return {}
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore")
        value = json.loads(decoded)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def as_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def strip_byte_range_query(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in {"bytestart", "byteend"}
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def dedupe_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    for url in urls:
        if url and url not in result:
            result.append(url)
    return result


def is_xiaohongshu_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in {"xhslink.com", "www.xhslink.com", "xiaohongshu.com", "www.xiaohongshu.com"} or host.endswith(".xiaohongshu.com")


def is_instagram_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in {"instagram.com", "www.instagram.com"} or host.endswith(".instagram.com")


def is_youtube_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def is_instagram_reel_url(url: str) -> bool:
    if not is_instagram_url(url):
        return False
    path = urlparse(url).path.lower()
    return path.startswith("/reel/") or path.startswith("/tv/")


def instagram_shortcode(url: str) -> str | None:
    path = urlparse(url).path
    match = re.search(r"/(?:reel|p|tv)/([^/?#]+)/?", path, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)
