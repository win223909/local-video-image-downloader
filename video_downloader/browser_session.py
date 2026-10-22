from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import time
from uuid import uuid4
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
BROWSER_PROFILE_DIR = RUNTIME_DIR / "browser-profile"
TEMP_DIR = RUNTIME_DIR / "temp"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
NO_WATERMARK_MARKERS = ("no_watermark", "no-watermark", "nowatermark", "without_watermark", "without-watermark", "无水印")
WATERMARK_MARKERS = ("playwm", "watermark", "watermarked", "with_watermark", "with-watermark")


@dataclass(frozen=True)
class BrowserResolveResult:
    requested_url: str
    final_url: str
    title: str
    description: str | None
    thumbnail_url: str | None
    canonical_url: str | None
    video_url: str | None
    video_url_source: str | None = None
    media_urls: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    douyin_image_urls: list[str] = field(default_factory=list)
    douyin_detail_items: list[dict[str, Any]] = field(default_factory=list)
    tiktok_image_urls: list[str] = field(default_factory=list)
    post_image_urls: list[str] = field(default_factory=list)
    post_media_type: int | None = None
    post_has_video: bool = False
    post_incomplete: bool = False
    http_headers: dict[str, str] = field(default_factory=dict)
    cookie_file: Path | None = None
    html_excerpt: str = ""
    blocked_reason: str | None = None


def resolve_with_browser(url: str, timeout_ms: int = 18000) -> BrowserResolveResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("后台浏览器依赖尚未安装，请先运行 python -m playwright install chromium。") from exc

    RUNTIME_DIR.mkdir(exist_ok=True)
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    prune_exported_cookie_files()

    media_urls: list[str] = []
    media_headers: dict[str, dict[str, str]] = {}
    douyin_detail_items: list[dict[str, Any]] = []
    blocked_reason: str | None = None

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=True,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 900},
            user_agent=BROWSER_USER_AGENT,
        )
        page = context.new_page()

        def on_response(response: Any) -> None:
            detail = douyin_detail_from_response(response)
            if detail and len(douyin_detail_items) < 8 and not any(
                item["aweme_id"] == detail["aweme_id"] for item in douyin_detail_items
            ):
                douyin_detail_items.append(detail)
            response_url = response.url
            lowered = response_url.lower()
            try:
                content_type = response.headers.get("content-type", "").lower()
            except Exception:
                content_type = ""
            if (
                "video" in content_type
                or "mpegurl" in content_type
                or ".mp4" in lowered
                or ".m3u8" in lowered
                or "playwm" in lowered
                or "playaddr" in lowered
            ):
                if not 200 <= response.status < 400:
                    return
                if response_url not in media_urls:
                    media_urls.append(response_url)
                    media_headers[response_url] = sanitize_headers(response.request.headers)

        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(2500)
        except PlaywrightTimeoutError:
            blocked_reason = "页面加载超时"
        except Exception as exc:
            blocked_reason = str(exc)

        data = page.evaluate(
            """() => {
                const meta = (selector) => document.querySelector(selector)?.content || null;
                const attr = (selector, name) => document.querySelector(selector)?.getAttribute(name) || null;
                const allMeta = (selector) => Array.from(document.querySelectorAll(selector)).map((node) => node.content).filter(Boolean);
                const isRemote = (value) => value && /^https?:\\/\\//.test(value);
                const uniq = (items) => Array.from(new Set(items.filter(isRemote)));
                const isInstagram = /(^|\\.)instagram\\.com$/i.test(location.hostname);
                const isDouyin = /(^|\\.)douyin\\.com$/i.test(location.hostname);
                const douyinImageUrls = isDouyin ? uniq(Array.from(document.querySelectorAll('.dySwiperSlide')).map((slide) =>
                    Array.from(slide.querySelectorAll('img')).map((img) => img.currentSrc || img.src).find(isRemote)
                )) : [];
                const isTikTokPhoto = /(^|\\.)tiktok\\.com$/i.test(location.hostname) && /^\\/@[^/]+\\/photo\\/\\d+/.test(location.pathname);
                const tiktokImageUrls = isTikTokPhoto ? uniq(Array.from(document.querySelectorAll(
                    '.swiper-slide:not(.swiper-slide-duplicate) img[class*="ImgPhotoSlide"]'
                )).map((img) => img.currentSrc || img.src)) : [];
                const currentCode = isInstagram ? (location.pathname.match(/\\/(?:p|reel|tv)\\/([^/]+)/i) || [])[1] || null : null;
                const postScore = (post) => post ? (post.carousel_media?.length || 0) + 1 : 0;
                const bestImageCandidate = (media) => {
                    const candidates = [
                        ...(media?.image_versions2?.candidates || []),
                        ...(media?.image_versions2?.additional_candidates ? Object.values(media.image_versions2.additional_candidates) : []),
                    ].filter((candidate) => isRemote(candidate?.url));
                    return candidates.sort((a, b) => {
                        const aArea = Number(a.width || 0) * Number(a.height || 0);
                        const bArea = Number(b.width || 0) * Number(b.height || 0);
                        return bArea - aArea;
                    })[0]?.url || media?.display_uri || null;
                };
                const findStructuredPost = (value, depth = 0) => {
                    if (!value || depth > 18) return null;
                    if (Array.isArray(value)) {
                        let best = null;
                        for (const child of value) {
                            const found = findStructuredPost(child, depth + 1);
                            if (postScore(found) > postScore(best)) best = found;
                        }
                        return best;
                    }
                    if (typeof value !== 'object') return null;
                    let best = currentCode && value.code === currentCode && (
                        Array.isArray(value.carousel_media) || value.image_versions2 || value.display_uri
                    ) ? value : null;
                    for (const child of Object.values(value)) {
                        const found = findStructuredPost(child, depth + 1);
                        if (postScore(found) > postScore(best)) best = found;
                    }
                    return best;
                };
                let structuredPost = null;
                for (const script of document.querySelectorAll('script[type="application/json"]')) {
                    try {
                        const found = findStructuredPost(JSON.parse(script.textContent || ''));
                        if (postScore(found) > postScore(structuredPost)) structuredPost = found;
                    } catch (_error) {
                        // Ignore unrelated or incomplete JSON blocks.
                    }
                }
                const postItems = structuredPost ? structuredPost.carousel_media || [structuredPost] : [];
                const postImageUrls = postItems.filter((item) => item.media_type !== 2).map(bestImageCandidate);
                const postVideo = structuredPost?.media_type === 2
                    ? [...(structuredPost.video_versions || [])].filter((item) => isRemote(item.url))
                        .sort((a,b) => (b.width || 0)*(b.height || 0) - (a.width || 0)*(a.height || 0))[0]?.url
                    : null;
                const videos = Array.from(document.querySelectorAll('video')).map((video) => {
                    const rect = video.getBoundingClientRect();
                    const style = window.getComputedStyle(video);
                    const src = video.currentSrc || video.src || null;
                    return {
                        src,
                        poster: video.poster || null,
                        visible: Boolean(src) && rect.width > 40 && rect.height > 40 && style.visibility !== 'hidden' && style.display !== 'none',
                        area: Math.max(rect.width, 0) * Math.max(rect.height, 0),
                    };
                }).sort((a, b) => Number(b.visible) - Number(a.visible) || b.area - a.area);
                const visibleImages = Array.from(document.querySelectorAll('img')).map((img) => {
                    const rect = img.getBoundingClientRect();
                    const style = window.getComputedStyle(img);
                    const src = img.currentSrc || img.src || null;
                    return {
                        src,
                        visible: Boolean(src) && rect.width > 80 && rect.height > 80 && style.visibility !== 'hidden' && style.display !== 'none',
                        area: Math.max(rect.width, 0) * Math.max(rect.height, 0),
                    };
                }).filter((img) => img.visible && isRemote(img.src)).sort((a, b) => b.area - a.area).map((img) => img.src);
                const sources = Array.from(document.querySelectorAll('source')).map((source) => source.src).filter(Boolean);
                const mainVideo = videos.find((video) => video.visible && isRemote(video.src)) || videos.find((video) => isRemote(video.src));
                const imageUrls = uniq([
                    ...allMeta('meta[property="og:image"]'),
                    ...allMeta('meta[name="twitter:image"]'),
                    ...visibleImages.slice(0, 12),
                ]);
                return {
                    title: document.title || '',
                    description: meta('meta[property="og:description"]') || meta('meta[name="description"]'),
                    thumbnail: meta('meta[property="og:image"]') || meta('meta[name="twitter:image"]') || videos.find((v) => v.poster)?.poster || null,
                    canonical: attr('link[rel="canonical"]', 'href') || meta('meta[property="og:url"]'),
                    ogVideo: meta('meta[property="og:video"]') || meta('meta[property="og:video:url"]') || meta('meta[property="og:video:secure_url"]'),
                    videoSrc: mainVideo?.src || sources.find(isRemote) || null,
                    imageUrls,
                    douyinImageUrls,
                    tiktokImageUrls,
                    postImageUrls: uniq(postImageUrls),
                    postMediaType: structuredPost?.media_type ?? null,
                    postHasVideo: postItems.some((item) => item.media_type === 2),
                    postVideo: postVideo || null,
                    postIncomplete: postImageUrls.some((url) => !isRemote(url)) ||
                        Number(structuredPost?.carousel_media_count || 0) > postItems.length,
                    text: (document.body?.innerText || '').slice(0, 2000),
                };
            }"""
        )
        final_url = page.url
        cookie_file = export_cookies(context.cookies(), url)
        context.close()

    video_url, video_url_source = first_remote_candidate(
        ("post", data.get("postVideo")),
        ("og", data.get("ogVideo")),
        ("dom", data.get("videoSrc")),
        ("network", first_media_url(media_urls)),
    )
    http_headers = media_headers.get(video_url or "", default_http_headers(final_url))
    return BrowserResolveResult(
        requested_url=url,
        final_url=final_url,
        title=data.get("title") or "",
        description=data.get("description"),
        thumbnail_url=data.get("thumbnail"),
        canonical_url=data.get("canonical"),
        video_url=video_url,
        video_url_source=video_url_source,
        media_urls=media_urls,
        image_urls=data.get("imageUrls") or [],
        douyin_image_urls=data.get("douyinImageUrls") or [],
        douyin_detail_items=douyin_detail_items,
        tiktok_image_urls=data.get("tiktokImageUrls") or [],
        post_image_urls=data.get("postImageUrls") or [],
        post_media_type=data.get("postMediaType"),
        post_has_video=bool(data.get("postHasVideo")),
        post_incomplete=bool(data.get("postIncomplete")),
        http_headers=http_headers,
        cookie_file=cookie_file,
        html_excerpt=data.get("text") or "",
        blocked_reason=blocked_reason,
    )


def douyin_detail_from_response(response: Any) -> dict[str, Any] | None:
    parsed = urlparse(response.url)
    if (parsed.scheme, parsed.hostname, parsed.path) != (
        "https", "www.douyin.com", "/aweme/v1/web/aweme/detail/"
    ) or response.status != 200:
        return None
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("status_code") != 0:
        return None
    item = payload.get("aweme_detail")
    if not isinstance(item, dict):
        return None
    aweme_id = str(item.get("aweme_id") or "")
    if len(aweme_id) < 10 or not aweme_id.isdecimal():
        return None
    fields = (
        "aweme_id", "group_id_str", "desc", "aweme_type", "media_type",
        "is_slides", "is_image_post", "isImagePost", "images", "image_infos",
        "image_list", "imageList", "image_infos_v2", "image_list_v2",
        "image_post_info", "imagePost", "image_post", "imagePostInfo",
    )
    detail = {key: item[key] for key in fields if key in item}
    author = item.get("author")
    if isinstance(author, dict):
        detail["author"] = {"nickname": author.get("nickname")}
    video = item.get("video")
    if isinstance(video, dict):
        video_fields = ("play_addr", "cover", "origin_cover", "dynamic_cover", "duration", "width", "height")
        detail["video"] = {key: video[key] for key in video_fields if key in video}
    return detail


def export_cookies(cookies: list[dict[str, Any]], source_url: str) -> Path | None:
    host = urlparse(source_url).netloc.replace(":", "_") or "cookies"
    cookie_file = TEMP_DIR / f"{host}-{uuid4().hex}.cookies.txt"
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in cookies:
        domain = cookie.get("domain") or ""
        if not domain:
            continue
        name = safe_cookie_field(cookie.get("name") or "")
        value = safe_cookie_field(cookie.get("value") or "")
        if not name:
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path") or "/"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires = max(int(cookie.get("expires") or 0), 0)
        lines.append("\t".join([domain, include_subdomains, path, secure, str(expires), name, value]))
    if len(lines) == 1:
        return None
    try:
        fd = os.open(cookie_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
        cookie_file.chmod(0o600)
    except Exception:
        cookie_file.unlink(missing_ok=True)
        raise
    return cookie_file


def remove_exported_cookie_file(path: Path | None) -> None:
    if path is None:
        return
    candidate = Path(path)
    if not re.fullmatch(r".+-[0-9a-f]{32}\.cookies\.txt", candidate.name):
        return
    try:
        if candidate.resolve().parent == TEMP_DIR.resolve():
            candidate.unlink(missing_ok=True)
    except OSError:
        pass


def prune_exported_cookie_files(max_age_seconds: int = 24 * 60 * 60) -> None:
    if not TEMP_DIR.is_dir():
        return
    cutoff = time.time() - max_age_seconds
    for path in TEMP_DIR.glob("*.cookies.txt"):
        try:
            if path.stat().st_mtime < cutoff:
                remove_exported_cookie_file(path)
        except OSError:
            continue


def safe_cookie_field(value: str) -> str:
    return str(value).replace("\t", " ").replace("\r", "").replace("\n", "")


def first_media_url(urls: list[str]) -> str | None:
    for url in sorted(urls, key=media_url_sort_key):
        lowered = url.lower()
        if ".mp4" in lowered or ".m3u8" in lowered:
            return url
    return urls[0] if urls else None


def media_url_sort_key(url: str) -> tuple[int, int]:
    lowered = url.lower()
    media_rank = 0 if ".mp4" in lowered or ".m3u8" in lowered else 1
    return (watermark_penalty_for_url(lowered), media_rank)


def watermark_penalty_for_url(lowered_url: str) -> int:
    if any(marker in lowered_url for marker in NO_WATERMARK_MARKERS):
        return 0
    penalty = 0
    if any(marker in lowered_url for marker in WATERMARK_MARKERS):
        penalty += 10
    return penalty


def first_remote_candidate(*candidates: tuple[str, str | None]) -> tuple[str | None, str | None]:
    for source, value in candidates:
        if value and value.startswith(("http://", "https://")):
            return value, source
    return None, None


def default_http_headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"host", "connection", "content-length", "cookie", "range", "if-range", "accept-encoding"}
    sanitized = {
        key: value
        for key, value in headers.items()
        if key.lower() not in blocked and value is not None
    }
    setdefault_header(sanitized, "User-Agent", BROWSER_USER_AGENT)
    setdefault_header(sanitized, "Accept", "*/*")
    setdefault_header(sanitized, "Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    return sanitized


def setdefault_header(headers: dict[str, str], name: str, value: str) -> None:
    if not any(key.lower() == name.lower() for key in headers):
        headers[name] = value
