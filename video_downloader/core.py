from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import platform
import re
import shutil
import ssl
import subprocess
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yt_dlp
import certifi
from yt_dlp.utils import sanitize_filename


OUTPUT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"
URL_PATTERN = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
URL_TRAILING_CHARS = ".,;:!?)]}\"'，。；：！？、）】》”’"
NO_WATERMARK_MARKERS = ("no_watermark", "no-watermark", "nowatermark", "without_watermark", "without-watermark", "无水印")
WATERMARK_MARKERS = ("playwm", "watermark", "watermarked", "with_watermark", "with-watermark")


class VideoDownloaderError(RuntimeError):
    """Raised when parsing or downloading cannot be completed."""

    def __init__(self, message: str, *, code: str = "unknown", raw_message: str | None = None):
        super().__init__(message)
        self.code = code
        self.raw_message = raw_message or message


class DownloadCancelled(VideoDownloaderError):
    """Raised by progress callbacks when the user stops an active download."""

    def __init__(self) -> None:
        super().__init__("下载已停止", code="download_cancelled")


class SilentYtdlpLogger:
    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


@dataclass(frozen=True)
class CookieOptions:
    browser: str | None = None
    browser_profile: str | None = None
    cookie_file: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.browser and not self.cookie_file

    @property
    def label(self) -> str:
        if self.browser:
            if self.browser_profile:
                return f"{self.browser} ({self.browser_profile})"
            return self.browser
        if self.cookie_file:
            return f"cookies.txt: {self.cookie_file}"
        return "不使用 cookies"

    def to_ydl_opts(self) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        if self.browser:
            opts["cookiesfrombrowser"] = (
                self.browser.lower(),
                self.browser_profile.strip() if self.browser_profile else None,
                None,
                None,
            )
        if self.cookie_file:
            opts["cookiefile"] = str(Path(self.cookie_file).expanduser())
        return opts


@dataclass(frozen=True)
class FormatOption:
    key: str
    selector: str
    label: str
    format_id: str
    resolution: str
    ext: str
    filesize: str
    video_codec: str
    audio_codec: str
    needs_merge: bool
    note: str


@dataclass(frozen=True)
class ImageItem:
    url: str
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    ext: str = "jpg"
    note: str = "平台返回图片"
    http_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoInfo:
    url: str
    webpage_url: str
    title: str
    uploader: str
    channel: str
    thumbnail: str | None
    duration: int | None
    extractor: str
    formats: list[FormatOption]
    preview_url: str | None = None
    cookie_file: str | None = None
    http_headers: dict[str, str] = field(default_factory=dict)
    video_id: str | None = None
    media_type: str = "video"
    images: list[ImageItem] = field(default_factory=list)
    audio_url: str | None = None


@dataclass(frozen=True)
class ParseAttempt:
    cookie_label: str
    success: bool
    message: str


@dataclass(frozen=True)
class ParseResult:
    info: VideoInfo
    cookies: CookieOptions
    attempts: list[ParseAttempt]


@dataclass(frozen=True)
class DownloadResult:
    output_dir: Path
    files: list[Path]
    cookies: CookieOptions = field(default_factory=CookieOptions)


ProgressHook = Callable[[dict[str, Any]], None]


def extract_url_from_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise VideoDownloaderError("请输入视频链接。")

    match = URL_PATTERN.search(cleaned)
    if not match:
        raise VideoDownloaderError("没有识别到 http(s) 链接，请粘贴视频 URL 或平台分享文案。")

    return match.group(0).rstrip(URL_TRAILING_CHARS)


def parse_video(url: str, cookies: CookieOptions | None = None) -> VideoInfo:
    cleaned_url = extract_url_from_text(url)

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "logger": SilentYtdlpLogger(),
    }
    ydl_opts.update((cookies or CookieOptions()).to_ydl_opts())

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
    except Exception as exc:  # yt-dlp exposes several exception classes by site.
        raise build_downloader_error(exc, cleaned_url) from exc

    if not isinstance(info, dict):
        raise VideoDownloaderError("解析结果为空，无法读取视频信息。")

    if info.get("_type") == "playlist":
        raise VideoDownloaderError("当前 MVP 只支持单个视频链接，暂不支持播放列表或批量链接。")

    formats = build_format_options(info)
    if not formats:
        raise VideoDownloaderError("没有找到可下载格式，可能需要登录、cookies，或该视频受限制。")

    return VideoInfo(
        url=cleaned_url,
        webpage_url=info.get("webpage_url") or cleaned_url,
        title=info.get("title") or "未命名视频",
        uploader=info.get("uploader") or info.get("creator") or "未知作者",
        channel=info.get("channel") or info.get("uploader") or "未知频道",
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        extractor=info.get("extractor_key") or info.get("extractor") or "未知站点",
        formats=formats,
        preview_url=best_preview_url(info),
        cookie_file=cookies.cookie_file if cookies else None,
        http_headers=info.get("http_headers") or {},
        video_id=str(info.get("id") or "") or None,
    )


def parse_video_auto(url: str, status_hook: Callable[[str], None] | None = None) -> ParseResult:
    attempts: list[ParseAttempt] = []

    def record(cookies: CookieOptions, success: bool, message: str) -> None:
        attempts.append(ParseAttempt(cookie_label=cookies.label, success=success, message=message))
        if status_hook:
            status_hook(message)

    no_cookies = CookieOptions()
    try:
        record(no_cookies, False, "正在直接解析...")
        info = parse_video(url, cookies=no_cookies)
        attempts[-1] = ParseAttempt(no_cookies.label, True, "直接解析成功")
        return ParseResult(info=info, cookies=no_cookies, attempts=attempts)
    except VideoDownloaderError as first_error:
        attempts[-1] = ParseAttempt(no_cookies.label, False, str(first_error))
        if not should_retry_with_cookies(first_error):
            raise first_error

    last_error: VideoDownloaderError | None = None
    for candidate in browser_cookie_candidates():
        try:
            record(candidate, False, f"正在自动尝试 {candidate.label} cookies...")
            info = parse_video(url, cookies=candidate)
            attempts[-1] = ParseAttempt(candidate.label, True, f"已自动使用 {candidate.label} cookies 解析成功")
            return ParseResult(info=info, cookies=candidate, attempts=attempts)
        except VideoDownloaderError as exc:
            last_error = exc
            attempts[-1] = ParseAttempt(candidate.label, False, str(exc))
            if not should_continue_auto_cookie_attempts(exc):
                break

    labels = "、".join(attempt.cookie_label for attempt in attempts[1:]) or "本机浏览器"
    final_message = (
        f"自动 cookies 未成功。已尝试：{labels}。"
        "请先在常用浏览器打开一次目标平台，再重试；如果仍失败，可以在侧边栏高级设置里指定浏览器或 cookies.txt。"
    )
    if last_error:
        final_message = f"{final_message}\n最后一次错误：{last_error}"
    raise VideoDownloaderError(final_message, code="auto_cookies_failed", raw_message=last_error.raw_message if last_error else None)


def build_format_options(info: dict[str, Any]) -> list[FormatOption]:
    raw_formats = info.get("formats") or []
    recommended = recommended_format_option(raw_formats)
    options: list[FormatOption] = [recommended]

    seen_selectors = {options[0].selector}
    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue

        format_id = str(fmt.get("format_id") or "").strip()
        if not format_id:
            continue

        video_codec = fmt.get("vcodec") or "none"
        audio_codec = fmt.get("acodec") or "none"
        has_video = video_codec != "none"
        has_audio = audio_codec != "none"
        if not has_video and not has_audio:
            continue

        ext = fmt.get("ext") or "未知"
        resolution = format_resolution(fmt, has_video, has_audio)
        filesize = format_bytes(fmt.get("filesize") or fmt.get("filesize_approx"))
        note = format_note(fmt)
        mark_note = "带平台标识" if watermark_penalty_for_format(fmt) else ""
        display_note = " / ".join(part for part in [str(note), mark_note] if part)

        if has_video and not has_audio:
            selector = f"{format_id}+bestaudio/best"
            needs_merge = True
            merge_label = "需要合并音视频"
        else:
            selector = format_id
            needs_merge = False
            merge_label = "单文件"

        if selector in seen_selectors:
            continue
        seen_selectors.add(selector)

        label = " | ".join(
            [
                resolution,
                str(ext),
                filesize,
                f"视频 {short_codec(video_codec)}",
                f"音频 {short_codec(audio_codec)}",
                merge_label,
            ]
        )

        options.append(
            FormatOption(
                key=f"format-{format_id}",
                selector=selector,
                label=label,
                format_id=format_id,
                resolution=resolution,
                ext=str(ext),
                filesize=filesize,
                video_codec=short_codec(video_codec),
                audio_codec=short_codec(audio_codec),
                needs_merge=needs_merge,
                note=display_note,
            )
        )

    recommended, rest = options[0], options[1:]
    rest.sort(key=_sort_format_option)
    return [recommended, *rest]


def recommended_format_option(raw_formats: list[Any]) -> FormatOption:
    selected = select_recommended_format(raw_formats)
    if not selected:
        return FormatOption(
            key="recommended-best",
            selector="bestvideo+bestaudio/best",
            label="推荐：最佳 MP4（自动选择公开可用格式）",
            format_id="bestvideo+bestaudio/best",
            resolution="自动最高",
            ext="mp4",
            filesize="未知",
            video_codec="自动",
            audio_codec="自动",
            needs_merge=True,
            note="推荐",
        )

    format_id = str(selected.get("format_id") or "").strip()
    video_codec = selected.get("vcodec") or "none"
    audio_codec = selected.get("acodec") or "none"
    has_audio = audio_codec != "none"
    selector = format_id if has_audio else f"{format_id}+bestaudio/best"
    ext = str(selected.get("ext") or "mp4")
    resolution = format_resolution(selected, True, has_audio)
    filesize = format_bytes(selected.get("filesize") or selected.get("filesize_approx"))
    source_note = "优先原始资源" if watermark_penalty_for_format(selected) == 0 else "推荐"
    merge_note = "必要时合并音视频" if not has_audio else "单文件"

    return FormatOption(
        key="recommended-best",
        selector=selector,
        label=f"推荐：{source_note} {ext.upper()}（{merge_note}）",
        format_id=format_id or selector,
        resolution=resolution,
        ext=ext,
        filesize=filesize,
        video_codec=short_codec(video_codec),
        audio_codec=short_codec(audio_codec),
        needs_merge=not has_audio,
        note=source_note,
    )


def select_recommended_format(raw_formats: list[Any]) -> dict[str, Any] | None:
    candidates = [
        fmt
        for fmt in raw_formats
        if isinstance(fmt, dict)
        and str(fmt.get("format_id") or "").strip()
        and (fmt.get("vcodec") or "none") != "none"
    ]
    if not candidates:
        return None
    return min(candidates, key=recommended_format_sort_key)


def recommended_format_sort_key(fmt: dict[str, Any]) -> tuple[int, int, int, int, float, float, str]:
    ext = str(fmt.get("ext") or "").lower()
    has_audio = (fmt.get("acodec") or "none") != "none"
    height = as_sort_number(fmt.get("height")) or _extract_height(str(fmt.get("resolution") or fmt.get("format_note") or ""))
    tbr = as_sort_number(fmt.get("tbr") or fmt.get("vbr") or fmt.get("abr"))
    size = as_sort_number(fmt.get("filesize") or fmt.get("filesize_approx"))
    return (
        watermark_penalty_for_format(fmt),
        0 if ext in {"mp4", "m4v"} else 1,
        -int(height),
        0 if has_audio else 1,
        -tbr,
        -size,
        str(fmt.get("format_id") or ""),
    )


def make_direct_video_info(
    *,
    url: str,
    webpage_url: str,
    title: str,
    uploader: str = "未知作者",
    channel: str = "未知频道",
    thumbnail: str | None = None,
    duration: int | None = None,
    ext: str = "mp4",
    filesize: str = "未知",
    preview_url: str | None = None,
    extractor: str = "Browser",
    cookie_file: str | None = None,
    http_headers: dict[str, str] | None = None,
    video_id: str | None = None,
    audio_url: str | None = None,
) -> VideoInfo:
    needs_merge = bool(audio_url)
    label = f"推荐：最佳 {ext.upper()}"
    note = "自动合并音视频" if needs_merge else "推荐"
    return VideoInfo(
        url=url,
        webpage_url=webpage_url,
        title=title or "未命名视频",
        uploader=uploader or "未知作者",
        channel=channel or uploader or "未知频道",
        thumbnail=thumbnail,
        duration=duration,
        extractor=extractor,
        formats=[
            FormatOption(
                key="direct-best",
                selector="best",
                label=label,
                format_id="best",
                resolution="自动最高",
                ext=ext,
                filesize=filesize,
                video_codec="自动",
                audio_codec="自动",
                needs_merge=needs_merge,
                note=note,
            )
        ],
        preview_url=preview_url or url,
        cookie_file=cookie_file,
        http_headers=http_headers or {},
        video_id=video_id,
        audio_url=audio_url,
    )


def make_image_info(
    *,
    url: str,
    webpage_url: str,
    title: str,
    uploader: str = "未知作者",
    channel: str = "未知频道",
    images: list[ImageItem],
    thumbnail: str | None = None,
    extractor: str = "Image",
    http_headers: dict[str, str] | None = None,
    video_id: str | None = None,
) -> VideoInfo:
    normalized_images = [
        replace_image_headers(image, http_headers or {})
        for image in images
        if image.url.startswith(("http://", "https://"))
    ]
    if not normalized_images:
        raise VideoDownloaderError("平台没有返回可确认的图片资源。", code="image_resource_missing")

    return VideoInfo(
        url=url,
        webpage_url=webpage_url,
        title=title or "未命名图片",
        uploader=uploader or "未知作者",
        channel=channel or uploader or "未知频道",
        thumbnail=thumbnail or normalized_images[0].thumbnail_url or normalized_images[0].url,
        duration=None,
        extractor=extractor,
        formats=[],
        preview_url=normalized_images[0].thumbnail_url or normalized_images[0].url,
        http_headers=http_headers or {},
        video_id=video_id,
        media_type="image",
        images=normalized_images,
    )


def replace_image_headers(image: ImageItem, headers: dict[str, str]) -> ImageItem:
    if image.http_headers:
        return image
    return ImageItem(
        url=image.url,
        thumbnail_url=image.thumbnail_url,
        width=image.width,
        height=image.height,
        ext=image.ext,
        note=image.note,
        http_headers=headers,
    )


def download_video(
    url: str,
    selector: str,
    output_dir: str | Path,
    progress_hook: ProgressHook | None = None,
    cookies: CookieOptions | None = None,
    http_headers: dict[str, str] | None = None,
) -> DownloadResult:
    cleaned_url = extract_url_from_text(url)
    directory = Path(output_dir).expanduser().resolve()
    before = snapshot_files(directory)

    def hook(status: dict[str, Any]) -> None:
        if progress_hook:
            progress_hook(status)

    ydl_opts: dict[str, Any] = {
        "format": selector,
        "outtmpl": str(directory / OUTPUT_TEMPLATE),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "noplaylist": True,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": SilentYtdlpLogger(),
    }
    if http_headers:
        ydl_opts["http_headers"] = http_headers
    ydl_opts.update((cookies or CookieOptions()).to_ydl_opts())

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([cleaned_url])
    except DownloadCancelled:
        raise
    except Exception as exc:
        raise build_downloader_error(exc, cleaned_url) from exc

    after = snapshot_files(directory)
    changed = sorted(after - before, key=lambda p: p.stat().st_mtime if p.exists() else 0)
    final_files = [path for path in changed if path.exists() and not path.name.endswith(".part")]
    if not final_files:
        final_files = sorted(
            [path for path in directory.iterdir() if path.is_file() and not path.name.endswith(".part")],
            key=lambda p: p.stat().st_mtime,
        )[-1:]

    return DownloadResult(output_dir=directory, files=final_files, cookies=cookies or CookieOptions())


def download_direct_video(
    info: VideoInfo,
    output_dir: str | Path,
    progress_hook: ProgressHook | None = None,
) -> DownloadResult:
    cleaned_url = extract_url_from_text(info.url)
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    ext = direct_ext(info) or "mp4"
    video_id = info.video_id or "video"
    stem = sanitize_filename(f"{info.title[:200]} [{video_id}]", restricted=False).strip() or video_id
    final_path = unique_path(directory / f"{stem}.{ext}")
    part_path = final_path.with_suffix(final_path.suffix + ".part")

    if info.audio_url:
        return download_direct_video_with_audio(
            info=info,
            video_url=cleaned_url,
            final_path=final_path,
            progress_hook=progress_hook,
        )

    download_direct_file(cleaned_url, part_path, info.http_headers or {}, progress_hook=progress_hook)

    if looks_like_incomplete_mp4_fragment(part_path):
        part_path.unlink(missing_ok=True)
        raise VideoDownloaderError("平台只返回了视频分片，正在尝试重新获取完整资源。", code="incomplete_media_fragment")

    shutil.move(str(part_path), str(final_path))
    if progress_hook:
        progress_hook({"status": "finished"})
    return DownloadResult(output_dir=directory, files=[final_path])


def download_direct_video_with_audio(
    *,
    info: VideoInfo,
    video_url: str,
    final_path: Path,
    progress_hook: ProgressHook | None = None,
) -> DownloadResult:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoDownloaderError("该视频需要合并音视频，请先安装 FFmpeg 后再下载。", code="ffmpeg_missing")

    headers = info.http_headers or {}
    video_part = final_path.with_suffix(final_path.suffix + ".video.part")
    audio_part = final_path.with_suffix(final_path.suffix + ".audio.part")
    merged_part = final_path.with_suffix(final_path.suffix + ".part")
    for path in [video_part, audio_part, merged_part]:
        path.unlink(missing_ok=True)

    try:
        download_direct_file(video_url, video_part, headers, progress_hook=progress_hook)
        download_direct_file(info.audio_url or "", audio_part, headers, progress_hook=progress_hook)
        if looks_like_incomplete_mp4_fragment(video_part):
            raise VideoDownloaderError("平台只返回了视频分片，正在尝试重新获取完整资源。", code="incomplete_media_fragment")
        merge_direct_media(ffmpeg, video_part, audio_part, merged_part)
        shutil.move(str(merged_part), str(final_path))
    except Exception:
        for path in [video_part, audio_part, merged_part]:
            path.unlink(missing_ok=True)
        raise
    finally:
        video_part.unlink(missing_ok=True)
        audio_part.unlink(missing_ok=True)

    if progress_hook:
        progress_hook({"status": "finished"})
    return DownloadResult(output_dir=final_path.parent, files=[final_path])


def download_direct_file(
    url: str,
    part_path: Path,
    headers: dict[str, str],
    progress_hook: ProgressHook | None = None,
) -> None:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=60, context=ssl_context()) as response, part_path.open("wb") as file:
            total = response.length or parse_content_length(response.headers.get("content-length"))
            downloaded = 0
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                if progress_hook:
                    progress_hook(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total,
                            "total_bytes_estimate": total,
                            "speed": None,
                            "eta": None,
                        }
                    )
    except DownloadCancelled:
        part_path.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, OSError) as exc:
        part_path.unlink(missing_ok=True)
        raise build_downloader_error(exc, url) from exc


def merge_direct_media(ffmpeg: str, video_part: Path, audio_part: Path, merged_part: Path) -> None:
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_part),
        "-i",
        str(audio_part),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(merged_part),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0 and merged_part.exists() and merged_part.stat().st_size > 0:
        return

    fallback = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_part),
        "-i",
        str(audio_part),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(merged_part),
    ]
    fallback_result = subprocess.run(fallback, capture_output=True, text=True)
    if fallback_result.returncode != 0 or not merged_part.exists() or merged_part.stat().st_size == 0:
        message = fallback_result.stderr.strip() or result.stderr.strip() or "FFmpeg 合并失败。"
        raise VideoDownloaderError(f"音视频合并失败：{message}", code="ffmpeg_merge_failed", raw_message=message)


def download_images(
    info: VideoInfo,
    output_dir: str | Path,
    progress_hook: ProgressHook | None = None,
) -> DownloadResult:
    if info.media_type != "image" or not info.images:
        raise VideoDownloaderError("当前解析结果没有可下载图片。", code="image_resource_missing")

    directory = Path(output_dir).expanduser().resolve() / sanitize_filename(info.title[:80] or "images", restricted=False)
    directory.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    total = len(info.images)
    for index, image in enumerate(info.images, start=1):
        if progress_hook:
            progress_hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": index - 1,
                    "total_bytes": total,
                    "total_bytes_estimate": total,
                    "speed": None,
                    "eta": None,
                }
            )
        ext = image.ext or image_ext_from_url(image.url) or "jpg"
        stem = sanitize_filename(f"{index:02d}-{info.title[:120]}", restricted=False).strip() or f"{index:02d}"
        final_path = unique_path(directory / f"{stem}.{ext}")
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        headers = image.http_headers or info.http_headers or {}
        request = Request(image.url, headers=headers)
        try:
            with urlopen(request, timeout=60, context=ssl_context()) as response, part_path.open("wb") as file:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    file.write(chunk)
                    if progress_hook:
                        progress_hook(
                            {
                                "status": "downloading",
                                "downloaded_bytes": index - 1,
                                "total_bytes": total,
                                "total_bytes_estimate": total,
                                "speed": None,
                                "eta": None,
                            }
                        )
        except DownloadCancelled:
            part_path.unlink(missing_ok=True)
            raise
        except (HTTPError, URLError, OSError) as exc:
            part_path.unlink(missing_ok=True)
            raise build_downloader_error(exc, image.url) from exc
        shutil.move(str(part_path), str(final_path))
        files.append(final_path)
        if progress_hook:
            progress_hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": index,
                    "total_bytes": total,
                    "total_bytes_estimate": total,
                    "speed": None,
                    "eta": None,
                }
            )

    if progress_hook:
        progress_hook({"status": "finished"})
    return DownloadResult(output_dir=directory, files=files)


def ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def download_video_auto(
    url: str,
    selector: str,
    output_dir: str | Path,
    progress_hook: ProgressHook | None = None,
    preferred_cookies: CookieOptions | None = None,
    status_hook: Callable[[str], None] | None = None,
) -> DownloadResult:
    attempts = [preferred_cookies] if preferred_cookies and not preferred_cookies.is_empty else [CookieOptions()]
    attempts.extend(cookie for cookie in browser_cookie_candidates() if cookie not in attempts)

    last_error: VideoDownloaderError | None = None
    for cookies in attempts:
        if status_hook and not cookies.is_empty:
            status_hook(f"正在使用 {cookies.label} cookies 下载...")
        try:
            return download_video(url, selector, output_dir, progress_hook=progress_hook, cookies=cookies)
        except VideoDownloaderError as exc:
            last_error = exc
            if not should_retry_with_cookies(exc):
                raise exc

    raise VideoDownloaderError(
        f"自动 cookies 下载未成功。最后一次错误：{last_error}",
        code="auto_cookies_failed",
        raw_message=last_error.raw_message if last_error else None,
    )


def snapshot_files(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path.resolve() for path in directory.iterdir() if path.is_file()}


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path


def parse_content_length(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def direct_ext(info: VideoInfo) -> str | None:
    if info.formats:
        ext = info.formats[0].ext.lower()
        if ext and ext != "未知":
            return ext
    lowered = info.url.lower().split("?", 1)[0]
    for ext in ["mp4", "m4v", "webm", "mov"]:
        if lowered.endswith(f".{ext}"):
            return ext
    return None


def looks_like_incomplete_mp4_fragment(path: Path) -> bool:
    try:
        if path.stat().st_size > 64 * 1024:
            return False
        with path.open("rb") as file:
            head = file.read(16)
    except OSError:
        return False
    return len(head) >= 8 and head[4:8] == b"sidx"


def image_ext_from_url(url: str) -> str | None:
    lowered = url.lower().split("?", 1)[0]
    for ext in ["jpg", "jpeg", "png", "webp", "gif", "avif"]:
        if lowered.endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return None


def format_resolution(fmt: dict[str, Any], has_video: bool, has_audio: bool) -> str:
    if not has_video and has_audio:
        abr = fmt.get("abr")
        return f"音频 {int(abr)}kbps" if abr else "仅音频"

    width = fmt.get("width")
    height = fmt.get("height")
    if width and height:
        return f"{width}x{height}"

    height = fmt.get("height")
    if height:
        return f"{height}p"

    return fmt.get("resolution") or fmt.get("format_note") or "未知分辨率"


def format_bytes(value: Any) -> str:
    if not value:
        return "未知"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "未知"

    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.1f} {units[index]}"


def best_preview_url(info: dict[str, Any]) -> str | None:
    url = info.get("url")
    ext = str(info.get("ext") or "").lower()
    protocol = str(info.get("protocol") or "").lower()
    if isinstance(url, str) and (ext in {"mp4", "webm", "mov", "m4v"} or protocol in {"https", "http"}):
        return url

    for fmt in sorted(info.get("formats") or [], key=preview_format_sort_key):
        if not isinstance(fmt, dict):
            continue
        fmt_url = fmt.get("url")
        if not isinstance(fmt_url, str):
            continue
        fmt_ext = str(fmt.get("ext") or "").lower()
        has_video = (fmt.get("vcodec") or "none") != "none"
        has_audio = (fmt.get("acodec") or "none") != "none"
        if fmt_ext in {"mp4", "webm", "mov", "m4v"} and has_video and has_audio:
            return fmt_url
    return None


def preview_format_sort_key(item: Any) -> tuple[int, int]:
    if not isinstance(item, dict):
        return (100, 0)
    return (watermark_penalty_for_format(item), -int(as_sort_number(item.get("height"))))


def short_codec(codec: Any) -> str:
    value = str(codec or "none")
    if value == "none":
        return "无"
    return value.split(".")[0]


def format_note(fmt: dict[str, Any]) -> str:
    return str(fmt.get("format_note") or fmt.get("format") or "")


def watermark_penalty_for_format(fmt: dict[str, Any]) -> int:
    values = [
        fmt.get("url"),
        fmt.get("format_id"),
        fmt.get("format_note"),
        fmt.get("format"),
        fmt.get("protocol"),
    ]
    return watermark_penalty_from_text(*values)


def watermark_penalty_from_text(*values: Any) -> int:
    text = " ".join(str(value or "") for value in values).lower()
    if any(marker in text for marker in NO_WATERMARK_MARKERS):
        return 0
    penalty = 0
    if any(marker in text for marker in WATERMARK_MARKERS):
        penalty += 10
    if re.search(r"(^|[/?#&_.=-])wm($|[/?#&_.=-])", text):
        penalty += 5
    return penalty


def as_sort_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def browser_cookie_candidates() -> list[CookieOptions]:
    home = Path.home()
    system = platform.system()
    candidates: list[CookieOptions] = []
    if system == "Darwin":
        browser_paths = [
            ("chrome", home / "Library/Application Support/Google/Chrome"),
            ("safari", home / "Library/Containers/com.apple.Safari"),
            ("edge", home / "Library/Application Support/Microsoft Edge"),
            ("firefox", home / "Library/Application Support/Firefox/Profiles"),
        ]
    elif system == "Windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        app_data = Path(os.environ.get("APPDATA", ""))
        browser_paths = [
            ("chrome", local_app_data / "Google/Chrome/User Data"),
            ("edge", local_app_data / "Microsoft/Edge/User Data"),
            ("firefox", app_data / "Mozilla/Firefox/Profiles"),
        ]
    else:
        browser_paths = [
            ("chrome", home / ".config/google-chrome"),
            ("edge", home / ".config/microsoft-edge"),
            ("firefox", home / ".mozilla/firefox"),
        ]

    for browser, path in browser_paths:
        if path.exists():
            candidates.append(CookieOptions(browser=browser))
    return candidates


def should_retry_with_cookies(error: VideoDownloaderError) -> bool:
    return error.code in {"cookies_required", "login_required", "douyin_shortlink_home", "cookies_load_failed"}


def should_continue_auto_cookie_attempts(error: VideoDownloaderError) -> bool:
    return error.code in {
        "cookies_required",
        "login_required",
        "douyin_shortlink_home",
        "cookies_load_failed",
        "unsupported_url",
        "network_timeout",
        "unknown",
    }


def build_downloader_error(exc: Exception, source_url: str | None = None) -> VideoDownloaderError:
    message = str(exc).strip() or exc.__class__.__name__
    user_message, code = humanize_error(message, source_url)
    return VideoDownloaderError(user_message, code=code, raw_message=message)


def humanize_error(message: str, source_url: str | None = None) -> tuple[str, str]:
    lower = message.lower()
    source_lower = (source_url or "").lower()

    if "douyin" in source_lower and "unsupported url: https://www.douyin.com" in lower:
        return (
            "已识别到抖音短链，但这个短链当前跳转到了抖音首页，没有指向具体视频。"
            "正在尝试使用本机浏览器 cookies 自动处理；如果仍失败，请重新复制一次抖音分享链接。",
            "douyin_shortlink_home",
        )

    if "http error 404" in lower or "not found" in lower:
        return "平台返回的资源地址已失效，正在重新获取下载地址。", "resource_not_found"
    if "http error 403" in lower or "forbidden" in lower:
        return "平台拒绝了当前下载地址，正在重新获取下载地址。", "resource_forbidden"
    if "unsupported url" in lower or "no suitable extractor" in lower or "not a valid url" in lower:
        return "URL 不支持：yt-dlp 暂时无法解析这个网站或链接。", "unsupported_url"
    if "failed to load cookies" in lower or "cookie load" in lower:
        return "cookies 读取失败。请确认浏览器已关闭或授权可读取 cookies，或检查 cookies.txt 文件路径是否正确。", "cookies_load_failed"
    if "fresh cookies" in lower or "cookies" in lower:
        return "该视频需要新的浏览器 cookies。正在自动尝试本机浏览器 cookies。", "cookies_required"
    if "private video" in lower or "login" in lower or "sign in" in lower:
        return "该视频可能需要登录或 cookies。正在自动尝试本机浏览器 cookies。", "login_required"
    if "not available" in lower or "unavailable" in lower or "video unavailable" in lower:
        return "视频不存在或当前不可用。", "video_unavailable"
    if "geo" in lower or "country" in lower or "region" in lower:
        return "视频可能存在地区限制，当前网络无法访问。", "geo_restricted"
    if "ffmpeg" in lower or "ffprobe" in lower:
        return "FFmpeg 未安装或不可用。需要合并音视频时请先安装 FFmpeg。", "ffmpeg_missing"
    if "timed out" in lower or "timeout" in lower:
        return "网络超时，请稍后重试或检查网络连接。", "network_timeout"
    if "requested format is not available" in lower:
        return "所选格式不可用，请重新解析后选择其他格式。", "format_unavailable"
    if "no space left" in lower:
        return "磁盘空间不足，请更换下载目录或清理空间。", "disk_full"
    if "permission denied" in lower:
        return "下载目录没有写入权限，请选择其他目录。", "permission_denied"

    return f"操作失败：{message}", "unknown"


def _sort_format_option(option: FormatOption) -> tuple[int, int, int, float, str]:
    if option.video_codec != "无":
        media_rank = 0 if option.audio_codec != "无" else 1
    else:
        media_rank = 2

    height = _extract_height(option.resolution)
    size_number = _extract_size_number(option.filesize)
    watermark_rank = watermark_penalty_from_text(option.selector, option.format_id, option.label, option.note)
    return (watermark_rank, media_rank, -height, -size_number, option.ext)


def _extract_height(resolution: str) -> int:
    if "x" in resolution:
        tail = resolution.rsplit("x", 1)[-1]
    else:
        tail = resolution.replace("p", "")
    digits = "".join(ch for ch in tail if ch.isdigit())
    return int(digits) if digits else 0


def _extract_size_number(filesize: str) -> float:
    if filesize == "未知":
        return 0.0
    number = filesize.split(" ", 1)[0]
    try:
        return float(number)
    except ValueError:
        return 0.0
