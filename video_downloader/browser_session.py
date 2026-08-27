from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
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
    post_image_urls: list[str] = field(default_factory=list)
    post_media_type: int | None = None
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

    media_urls: list[str] = []
    media_headers: dict[str, dict[str, str]] = {}
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
                const currentCode = (location.pathname.match(/\\/(?:p|reel|tv)\\/([^/]+)/i) || [])[1] || null;
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
                        for (const child of value) {
                            const found = findStructuredPost(child, depth + 1);
                            if (found) return found;
                        }
                        return null;
                    }
                    if (typeof value !== 'object') return null;
                    if (currentCode && value.code === currentCode && (
                        Array.isArray(value.carousel_media) || value.image_versions2 || value.display_uri
                    )) return value;
                    for (const child of Object.values(value)) {
                        const found = findStructuredPost(child, depth + 1);
                        if (found) return found;
                    }
                    return null;
                };
                let structuredPost = null;
                for (const script of document.querySelectorAll('script[type="application/json"]')) {
                    try {
                        structuredPost = findStructuredPost(JSON.parse(script.textContent || ''));
                    } catch (_error) {
                        structuredPost = null;
                    }
                    if (structuredPost) break;
                }
                const postImageUrls = structuredPost
                    ? (Array.isArray(structuredPost.carousel_media)
                        ? structuredPost.carousel_media.map(bestImageCandidate)
                        : [bestImageCandidate(structuredPost)])
                    : [];
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
                    postImageUrls: uniq(postImageUrls),
                    postMediaType: structuredPost?.media_type ?? null,
                    text: (document.body?.innerText || '').slice(0, 2000),
                };
            }"""
        )
        final_url = page.url
        cookie_file = export_cookies(context.cookies(), url)
        context.close()

    video_url, video_url_source = first_remote_candidate(
        ("dom", data.get("videoSrc")),
        ("og", data.get("ogVideo")),
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
        post_image_urls=data.get("postImageUrls") or [],
        post_media_type=data.get("postMediaType"),
        http_headers=http_headers,
        cookie_file=cookie_file,
        html_excerpt=data.get("text") or "",
        blocked_reason=blocked_reason,
    )


def export_cookies(cookies: list[dict[str, Any]], source_url: str) -> Path:
    host = urlparse(source_url).netloc.replace(":", "_") or "cookies"
    cookie_file = TEMP_DIR / f"{host}-{int(time.time())}.cookies.txt"
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
    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cookie_file


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
