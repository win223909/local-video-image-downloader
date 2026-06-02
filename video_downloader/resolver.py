from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

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
                    note="优先无水印",
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

    title = clean_title(browser_result.title) or "未命名视频"
    info = make_direct_video_info(
        url=browser_result.video_url,
        webpage_url=browser_result.canonical_url or browser_result.final_url or original_url,
        title=title,
        thumbnail=browser_result.thumbnail_url,
        preview_url=browser_result.video_url,
        extractor="Browser",
        cookie_file=str(cookie_file) if cookie_file else None,
        http_headers=browser_result.http_headers,
    )
    return ResolvedVideo(info=info, cookie_file=cookie_file, browser_result=browser_result, source="browser")


def direct_browser_image_fallback(
    original_url: str,
    browser_result: BrowserResolveResult,
) -> ResolvedVideo | None:
    image_urls = dedupe_urls(browser_result.image_urls)
    if not image_urls:
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

    if resolved.source == "douyin-share" or (selected and selected.key == "direct-best"):
        return download_direct_video(
            info=resolved.info,
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
    suffixes = [" - 抖音", " - Douyin", " | 抖音", " | Douyin"]
    for suffix in suffixes:
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    return title.strip()


def dedupe_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    for url in urls:
        if url and url not in result:
            result.append(url)
    return result


def is_xiaohongshu_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in {"xhslink.com", "www.xhslink.com", "xiaohongshu.com", "www.xiaohongshu.com"} or host.endswith(".xiaohongshu.com")
