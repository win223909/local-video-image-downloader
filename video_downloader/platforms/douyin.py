from __future__ import annotations

from dataclasses import dataclass
import json
import re
import ssl
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from video_downloader.browser_session import BrowserResolveResult, default_http_headers

import certifi


DOUYIN_HOSTS = {"douyin.com", "www.douyin.com", "v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}
CONTENT_ID_PATTERN = re.compile(
    r"(?:douyin\.com/(?:video|note|slides)/|aweme_id=|modal_id=|note_id=|item_id=)(?P<id>\d{10,})"
)
IMAGE_PAGE_PATTERN = re.compile(r"douyin\.com/(?:note|slides)/\d{10,}")
ROUTER_DATA_MARKER = "window._ROUTER_DATA = "
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class DouyinShareInfo:
    aweme_id: str
    title: str
    uploader: str
    webpage_url: str
    media_type: str
    play_url: str | None
    image_urls: list[str]
    thumbnail_url: str | None
    duration: int | None
    width: int | None
    height: int | None
    http_headers: dict[str, str]


def is_douyin_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in DOUYIN_HOSTS or host.endswith(".douyin.com")


def extract_video_id(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        match = CONTENT_ID_PATTERN.search(value)
        if match:
            return match.group("id")
    return None


def normalized_video_url(result: BrowserResolveResult) -> str | None:
    video_id = extract_video_id(result.final_url, result.canonical_url, result.html_excerpt)
    if video_id:
        return f"https://www.douyin.com/video/{video_id}"
    return None


def resolve_share_info(url: str, timeout: int = 20) -> DouyinShareInfo | None:
    target = mobile_share_url(url)
    html, final_url = fetch_mobile_share_page(target, timeout=timeout)
    router_data = parse_router_data(html)
    item = find_aweme_item(router_data, extract_video_id(url, final_url))
    if not item:
        return None

    aweme_id = str(item.get("aweme_id") or item.get("group_id_str") or "")
    if not aweme_id:
        return None

    video = item.get("video") or {}
    play_url = preferred_video_url(first_url(video.get("play_addr")), final_url)
    image_urls = collect_image_urls(item)
    if not play_url and not image_urls:
        return None

    duration_ms = video.get("duration")
    duration = int(duration_ms / 1000) if isinstance(duration_ms, (int, float)) and duration_ms > 1000 else duration_ms
    page_kind = "note" if is_image_post(item, final_url) else "video"
    webpage_url = f"https://www.douyin.com/{page_kind}/{aweme_id}"
    thumbnail_url = (
        first_url(video.get("cover"))
        or first_url(video.get("origin_cover"))
        or first_url(video.get("dynamic_cover"))
        or (image_urls[0] if image_urls else None)
    )
    return DouyinShareInfo(
        aweme_id=aweme_id,
        title=str(item.get("desc") or "抖音视频"),
        uploader=str((item.get("author") or {}).get("nickname") or "未知作者"),
        webpage_url=webpage_url,
        media_type="image" if image_urls and is_image_post(item, final_url) else "video",
        play_url=play_url,
        image_urls=image_urls,
        thumbnail_url=thumbnail_url,
        duration=int(duration) if isinstance(duration, (int, float)) else None,
        width=as_int(video.get("width")),
        height=as_int(video.get("height")),
        http_headers={
            **default_http_headers(final_url or webpage_url),
            "User-Agent": MOBILE_USER_AGENT,
            "Referer": final_url or webpage_url,
        },
    )


def mobile_share_url(url: str) -> str:
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.iesdouyin.com/share/video/{video_id}/"
    return url


def looks_like_image_page(*values: str | None) -> bool:
    return any(value and IMAGE_PAGE_PATTERN.search(value) for value in values)


def fetch_mobile_share_page(url: str, timeout: int) -> tuple[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": MOBILE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout, context=ssl_context()) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="ignore"), response.geturl()


def ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def parse_router_data(html: str) -> dict[str, Any]:
    start = html.find(ROUTER_DATA_MARKER)
    if start < 0:
        return {}
    start += len(ROUTER_DATA_MARKER)
    end = html.find("</script>", start)
    if end < 0:
        return {}
    raw = html[start:end].strip().rstrip(";")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def find_aweme_item(data: dict[str, Any], expected_id: str | None = None) -> dict[str, Any] | None:
    for item in iter_aweme_items(data):
        aweme_id = str(item.get("aweme_id") or item.get("group_id_str") or "")
        if expected_id and aweme_id != expected_id:
            continue
        if first_url((item.get("video") or {}).get("play_addr")) or collect_image_urls(item):
            return item
    return None


def iter_aweme_items(value: Any):
    if isinstance(value, dict):
        item_list = value.get("item_list")
        if isinstance(item_list, list):
            for item in item_list:
                if isinstance(item, dict):
                    yield item
        for child in value.values():
            yield from iter_aweme_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_aweme_items(child)


def first_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if not isinstance(value, dict):
        return None
    urls = value.get("url_list")
    if isinstance(urls, list):
        for url in urls:
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    url = value.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    return None


def preferred_video_url(url: str | None, referer: str | None) -> str | None:
    if not url:
        return None
    candidates = dedupe_urls([unwatermarked_play_url(url), url])
    headers = {
        **default_http_headers(referer or url),
        "User-Agent": MOBILE_USER_AGENT,
        "Referer": referer or url,
    }
    for candidate in candidates:
        if candidate and video_url_works(candidate, headers):
            return candidate
    return url


def unwatermarked_play_url(url: str) -> str:
    return url.replace("/playwm/", "/play/").replace("playwm?", "play?")


def video_url_works(url: str, headers: dict[str, str]) -> bool:
    request = Request(url, headers={**headers, "Range": "bytes=0-1"})
    try:
        with urlopen(request, timeout=12, context=ssl_context()) as response:
            content_type = (response.headers.get("content-type") or "").lower()
            return 200 <= getattr(response, "status", 200) < 400 and "video" in content_type
    except OSError:
        return False


def dedupe_urls(urls: list[str | None]) -> list[str]:
    result: list[str] = []
    for url in urls:
        if url and url not in result:
            result.append(url)
    return result


def collect_image_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for image in iter_image_entries(item):
        for url in image_url_candidates(image):
            if url not in urls:
                urls.append(url)
    return urls


def iter_image_entries(item: dict[str, Any]):
    containers: list[Any] = [
        item.get("images"),
        item.get("image_infos"),
        item.get("image_list"),
        (item.get("image_post_info") or {}).get("images") if isinstance(item.get("image_post_info"), dict) else None,
        (item.get("imagePost") or {}).get("images") if isinstance(item.get("imagePost"), dict) else None,
    ]
    for container in containers:
        if isinstance(container, list):
            for image in container:
                if isinstance(image, dict):
                    yield image


def image_url_candidates(image: dict[str, Any]) -> list[str]:
    clean_candidates: list[Any] = [
        image.get("download_url"),
        image.get("download_url_list"),
        image.get("origin_url"),
        image.get("origin_image"),
        image.get("display_image"),
        image.get("url"),
        image.get("url_list"),
        image.get("large"),
    ]
    urls = collect_urls_from_values(clean_candidates)
    if urls:
        return urls

    fallback_candidates = [
        value
        for key, value in image.items()
        if "watermark" not in str(key).lower() and "avatar" not in str(key).lower()
    ]
    return collect_urls_from_values(fallback_candidates)


def collect_urls_from_values(values: list[Any]) -> list[str]:
    urls: list[str] = []
    for value in values:
        for url in iter_urls(value):
            if url not in urls:
                urls.append(url)
    return urls


def iter_urls(value: Any):
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            yield value
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_urls(child)
        return
    if isinstance(value, dict):
        direct = first_url(value)
        if direct:
            yield direct
        for key in ("url_list", "urlList", "urls", "download_url_list", "downloadUrlList"):
            yield from iter_urls(value.get(key))


def is_image_post(item: dict[str, Any], final_url: str | None = None) -> bool:
    if looks_like_image_page(final_url):
        return True
    if collect_image_urls(item):
        return True
    return any(isinstance(item.get(key), dict) for key in ("image_post_info", "imagePost"))


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def looks_like_homepage(result: BrowserResolveResult) -> bool:
    parsed = urlparse(result.final_url)
    path = parsed.path.rstrip("/")
    return parsed.netloc.endswith("douyin.com") and path in {"", "/home", "/jingxuan"}
