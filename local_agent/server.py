from __future__ import annotations

from dataclasses import dataclass, field
import io
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from uuid import uuid4

import certifi
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import ssl
import uvicorn

from video_downloader.core import (
    DownloadCancelled,
    DownloadResult,
    FormatOption,
    ImageItem,
    VideoDownloaderError,
    VideoInfo,
    format_bytes,
)
from video_downloader.resolver import ResolvedVideo, download_resolved_video, resolve_video
from video_downloader.system import choose_download_folder, ensure_writable_directory, ffmpeg_status, open_folder


AGENT_VERSION = "0.1.47"
DEFAULT_HOST = os.environ.get("LOCAL_AGENT_HOST", "0.0.0.0")
DEFAULT_PORT = 17890
PAIRING_TTL_SECONDS = 10 * 60
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
TOKEN_FILE = RUNTIME_DIR / "agent-token.json"
SETTINGS_FILE = RUNTIME_DIR / "agent-settings.json"
UPDATE_STATUS_FILE = RUNTIME_DIR / "update-status.json"
INSTALL_SOURCE_FILE = RUNTIME_DIR / "install-source.json"
WEB_DIR = PROJECT_ROOT / "web"
DEFAULT_UPDATE_MANIFEST_URL = "http://127.0.0.1:17890/downloads/update.json"
LOCAL_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class SettingsUpdate(BaseModel):
    download_dir: str


class ResolveRequest(BaseModel):
    text: str


class DownloadRequest(BaseModel):
    format_key: str | None = None


class ConvertRequest(BaseModel):
    file_index: int = 0


class UpdateStartRequest(BaseModel):
    force: bool = False


@dataclass
class AgentSettings:
    download_dir: Path


@dataclass
class AgentTask:
    id: str
    text: str
    preview_key: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    status: str = "queued"
    stage: str = "resolve"
    message: str = "等待处理"
    error: str | None = None
    error_code: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    resolved: ResolvedVideo | None = None
    result: DownloadResult | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False


def allowed_origins() -> list[str]:
    configured = os.environ.get("LOCAL_AGENT_ALLOWED_ORIGINS", "")
    values = [origin.strip() for origin in configured.split(",") if origin.strip()]
    values.extend(install_source_allowed_origins())
    values.extend(LOCAL_ALLOWED_ORIGINS)
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def read_install_source() -> dict[str, Any]:
    try:
        data = json.loads(INSTALL_SOURCE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def install_source_allowed_origins() -> list[str]:
    data = read_install_source()
    raw_origins = data.get("allowed_origins")
    if isinstance(raw_origins, list):
        return [str(origin).strip().rstrip("/") for origin in raw_origins if str(origin).strip()]
    raw_origin = data.get("allowed_origin")
    if isinstance(raw_origin, str) and raw_origin.strip():
        return [raw_origin.strip().rstrip("/")]
    return []


def update_manifest_url() -> str:
    configured = os.environ.get("LOCAL_AGENT_UPDATE_MANIFEST_URL", "").strip()
    if configured:
        return configured
    source_url = read_install_source().get("update_manifest_url")
    if isinstance(source_url, str) and source_url.strip():
        return source_url.strip()
    return DEFAULT_UPDATE_MANIFEST_URL


def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.exists() else Path.home()
    return base / "VideoDownloader"


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix) :].strip()


class AgentState:
    def __init__(self) -> None:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.tasks: dict[str, AgentTask] = {}
        self.pair_code = f"{secrets.randbelow(1_000_000):06d}"
        self.pair_expires_at = time.time() + PAIRING_TTL_SECONDS
        self.token = self._load_token()
        self.settings = self._load_settings()

    def _load_token(self) -> str | None:
        try:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        token = data.get("token")
        return token if isinstance(token, str) and token else None

    def _save_token(self, token: str) -> None:
        TOKEN_FILE.write_text(
            json.dumps({"token": token, "created_at": int(time.time())}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_settings(self) -> AgentSettings:
        default_dir = default_download_dir()
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AgentSettings(download_dir=default_dir)
        raw_dir = data.get("download_dir")
        if isinstance(raw_dir, str) and raw_dir.strip():
            return AgentSettings(download_dir=Path(raw_dir).expanduser())
        return AgentSettings(download_dir=default_dir)

    def save_settings(self) -> None:
        SETTINGS_FILE.write_text(
            json.dumps({"download_dir": str(self.settings.download_dir)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def pair(self, code: str) -> str:
        if time.time() > self.pair_expires_at:
            raise HTTPException(status_code=403, detail="配对码已过期，请重启本地助手。")
        if code.strip() != self.pair_code:
            raise HTTPException(status_code=403, detail="配对码不正确。")
        return self.ensure_token()

    def ensure_token(self) -> str:
        with self.lock:
            if not self.token:
                self.token = secrets.token_urlsafe(32)
                self._save_token(self.token)
            return self.token

    def reset_pair_code(self) -> dict[str, Any]:
        with self.lock:
            self.pair_code = f"{secrets.randbelow(1_000_000):06d}"
            self.pair_expires_at = time.time() + PAIRING_TTL_SECONDS
            return {
                "pair_code": self.pair_code,
                "pairing_expires_in": PAIRING_TTL_SECONDS,
            }

    def is_authenticated(self, authorization: str | None) -> bool:
        token = bearer_token(authorization)
        return bool(token and self.token and secrets.compare_digest(token, self.token))

    def require_auth(self, authorization: str | None) -> None:
        if not self.is_authenticated(authorization):
            raise HTTPException(status_code=401, detail="请先完成本地助手配对。")

    def create_task(self, text: str) -> AgentTask:
        task = AgentTask(id=uuid4().hex, text=text)
        with self.lock:
            self.tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> AgentTask:
        with self.lock:
            task = self.tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在或本地助手已重启。")
        return task

    def latest_result_task(self) -> AgentTask | None:
        with self.lock:
            tasks = [task for task in self.tasks.values() if task.result]
        if not tasks:
            return None
        return max(tasks, key=lambda task: task.updated_at)

    def clear_completed_tasks(self) -> int:
        active_statuses = {"queued", "running", "downloading", "converting"}
        with self.lock:
            before = len(self.tasks)
            self.tasks = {
                task_id: task
                for task_id, task in self.tasks.items()
                if task.status in active_statuses
            }
            return before - len(self.tasks)

    def write_update_status(self, status: dict[str, Any]) -> None:
        with self.lock:
            UPDATE_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_update_status(self) -> dict[str, Any]:
        try:
            data = json.loads(UPDATE_STATUS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"state": "idle", "message": "当前没有更新任务。", "percent": 0.0}
        if not isinstance(data, dict):
            return {"state": "idle", "message": "当前没有更新任务。", "percent": 0.0}
        return data


state = AgentState()
app = FastAPI(title="Local Video Downloader Agent", version=AGENT_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_private_network_access_header(request: FastAPIRequest, call_next):
    origin = request.headers.get("origin")
    if (
        request.method == "OPTIONS"
        and origin in allowed_origins()
        and request.headers.get("access-control-request-private-network") == "true"
    ):
        return PlainTextResponse(
            "OK",
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
                "Access-Control-Allow-Headers": "Accept, Accept-Language, Authorization, Content-Language, Content-Type",
                "Access-Control-Allow-Private-Network": "true",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            },
        )

    response = await call_next(request)
    if origin in allowed_origins():
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    if should_disable_browser_cache(request.url.path):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def require_auth(authorization: str | None = Header(default=None)) -> None:
    state.require_auth(authorization)


@app.get("/api/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return {
        "ok": True,
        "version": AGENT_VERSION,
        "paired": bool(state.token),
        "authenticated": state.is_authenticated(authorization),
        "pairing_expires_in": max(0, int(state.pair_expires_at - time.time())),
        "ffmpeg": ffmpeg_status(),
    }


@app.post("/api/pair")
def pair(request: PairRequest) -> dict[str, str]:
    return {"token": state.pair(request.code)}


@app.get("/api/local-token")
def local_token(request: FastAPIRequest) -> dict[str, str]:
    if not is_same_origin_local_ui_request(request):
        raise HTTPException(status_code=403, detail="只能从本机控制台自动连接。")
    return {"token": state.ensure_token()}


@app.post("/api/device/share", dependencies=[Depends(require_auth)])
def share_device_access(request: FastAPIRequest) -> dict[str, Any]:
    pair = state.reset_pair_code()
    urls = local_access_urls(request)
    recommended_url = next((url for url in urls if "127.0.0.1" not in url and "localhost" not in url), urls[0] if urls else "")
    return {
        **pair,
        "device_name": socket.gethostname(),
        "recommended_url": recommended_url,
        "recommended_qr_svg": qr_svg(recommended_url) if recommended_url else None,
        "local_urls": urls,
        "message": "手机和电脑/NAS 连接同一个网络后，打开下面的地址并输入配对码。",
    }


@app.get("/api/settings", dependencies=[Depends(require_auth)])
def get_settings() -> dict[str, Any]:
    return {"download_dir": str(state.settings.download_dir)}


@app.put("/api/settings", dependencies=[Depends(require_auth)])
def update_settings(update: SettingsUpdate) -> dict[str, Any]:
    try:
        directory = ensure_writable_directory(update.download_dir)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with state.lock:
        state.settings = AgentSettings(download_dir=directory)
        state.save_settings()
    return {"download_dir": str(directory)}


@app.post("/api/settings/select-folder", dependencies=[Depends(require_auth)])
def select_download_folder() -> dict[str, Any]:
    try:
        selected = choose_download_folder(state.settings.download_dir)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if selected is None:
        return {"download_dir": str(state.settings.download_dir), "cancelled": True}
    try:
        directory = ensure_writable_directory(selected)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with state.lock:
        state.settings = AgentSettings(download_dir=directory)
        state.save_settings()
    return {"download_dir": str(directory), "cancelled": False}


@app.post("/api/tasks/resolve", dependencies=[Depends(require_auth)])
def create_resolve_task(request: ResolveRequest) -> dict[str, str]:
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="请先粘贴链接或分享文案。")
    task = state.create_task(request.text)
    threading.Thread(target=run_resolve_task, args=(task.id,), daemon=True).start()
    return {"task_id": task.id}


@app.get("/api/tasks/latest-result", dependencies=[Depends(require_auth)])
def latest_result_task(request: FastAPIRequest) -> dict[str, Any]:
    task = state.latest_result_task()
    return {"task": task_payload(task, request_base_url(request)) if task else None}


@app.delete("/api/tasks/history", dependencies=[Depends(require_auth)])
def clear_task_history() -> dict[str, Any]:
    return {"ok": True, "removed": state.clear_completed_tasks()}


@app.get("/api/tasks/{task_id}", dependencies=[Depends(require_auth)])
def get_task(task_id: str, request: FastAPIRequest) -> dict[str, Any]:
    return task_payload(state.get_task(task_id), request_base_url(request))


@app.post("/api/tasks/{task_id}/download", dependencies=[Depends(require_auth)])
def start_download(task_id: str, request: DownloadRequest) -> dict[str, str]:
    task = state.get_task(task_id)
    if not task.resolved:
        raise HTTPException(status_code=409, detail="请等待解析完成后再下载。")
    if task.status in {"queued", "downloading"} and task.stage == "download":
        raise HTTPException(status_code=409, detail="下载正在进行中。")
    with state.lock:
        task.status = "queued"
        task.stage = "download"
        task.message = "等待下载"
        task.error = None
        task.error_code = None
        task.progress = {}
        task.result = None
        task.cancel_requested = False
        task.updated_at = time.time()
    threading.Thread(target=run_download_task, args=(task.id, request.format_key), daemon=True).start()
    return {"task_id": task.id}


@app.post("/api/tasks/{task_id}/cancel", dependencies=[Depends(require_auth)])
def cancel_download(task_id: str) -> dict[str, Any]:
    task = state.get_task(task_id)
    if task.stage != "download" or task.status not in {"queued", "downloading"}:
        return {"ok": True, "status": task.status}
    with state.lock:
        task.cancel_requested = True
        task.message = "正在停止下载..."
        task.progress = {
            **task.progress,
            "status": "cancel_requested",
            "text": "正在停止下载...",
        }
        task.updated_at = time.time()
    return {"ok": True, "status": task.status}


@app.post("/api/tasks/{task_id}/open-folder", dependencies=[Depends(require_auth)])
def open_task_folder(task_id: str) -> dict[str, Any]:
    task = state.get_task(task_id)
    if not task.result:
        raise HTTPException(status_code=409, detail="下载完成后才能打开文件夹。")
    try:
        open_folder(task.result.output_dir)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="无法打开文件夹，请手动前往保存目录。") from exc
    return {"ok": True, "output_dir": str(task.result.output_dir)}


@app.post("/api/tasks/{task_id}/convert/iphone", dependencies=[Depends(require_auth)])
def start_iphone_conversion(task_id: str, request: ConvertRequest) -> dict[str, Any]:
    task = state.get_task(task_id)
    if not task.result:
        raise HTTPException(status_code=409, detail="下载完成后才能转换。")
    if task.status in {"queued", "downloading", "converting"}:
        raise HTTPException(status_code=409, detail="当前任务正在处理中。")
    with state.lock:
        task.status = "converting"
        task.stage = "convert"
        task.message = "正在转换为 iPhone 相册格式..."
        task.error = None
        task.error_code = None
        task.progress = {"percent": 0, "text": "正在转换为 iPhone 相册格式..."}
        task.cancel_requested = False
        task.updated_at = time.time()
    threading.Thread(target=run_iphone_conversion_task, args=(task.id, request.file_index), daemon=True).start()
    return {"task_id": task.id}


@app.get("/api/tasks/{task_id}/files/{index}/download")
def download_result_file(
    task_id: str,
    index: int,
    authorization: str | None = Header(default=None),
    key: str | None = Query(default=None),
) -> FileResponse:
    task = state.get_task(task_id)
    authorize_media_request(task, authorization, key)
    if not task.result or index < 0 or index >= len(task.result.files):
        raise HTTPException(status_code=404, detail="文件不存在。")
    output_dir = task.result.output_dir.expanduser().resolve()
    file_path = task.result.files[index].expanduser().resolve()
    if output_dir not in [file_path, *file_path.parents]:
        raise HTTPException(status_code=403, detail="文件路径无效。")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return FileResponse(file_path, filename=file_path.name)


@app.get("/api/update/check", dependencies=[Depends(require_auth)])
def check_update() -> dict[str, Any]:
    manifest = fetch_update_manifest()
    latest_version = str(manifest.get("version") or "").strip()
    return {
        "current_version": AGENT_VERSION,
        "latest_version": latest_version,
        "update_available": bool(latest_version and latest_version != AGENT_VERSION),
        "notes": manifest.get("notes") or "",
        "published_at": manifest.get("published_at"),
        "status": safe_update_status(),
    }


@app.get("/api/update/status", dependencies=[Depends(require_auth)])
def update_status() -> dict[str, Any]:
    return safe_update_status()


@app.post("/api/update/start", dependencies=[Depends(require_auth)])
def start_update(request: UpdateStartRequest) -> dict[str, Any]:
    current = safe_update_status()
    if current.get("state") in {"queued", "running", "restarting"}:
        return current

    manifest = fetch_update_manifest()
    latest_version = str(manifest.get("version") or "").strip()
    if not request.force and latest_version == AGENT_VERSION:
        status = {
            "state": "completed",
            "message": "当前已经是最新版本。",
            "percent": 1.0,
            "version": AGENT_VERSION,
            "updated_at": int(time.time()),
        }
        state.write_update_status(status)
        return status

    status = {
        "state": "queued",
        "message": "更新任务已开始。",
        "percent": 0.0,
        "version": latest_version,
        "updated_at": int(time.time()),
    }
    state.write_update_status(status)
    start_update_process()
    return status


@app.get("/api/tasks/{task_id}/preview")
def preview_media(
    task_id: str,
    request: FastAPIRequest,
    authorization: str | None = Header(default=None),
    key: str | None = Query(default=None),
) -> StreamingResponse:
    task = state.get_task(task_id)
    authorize_media_request(task, authorization, key)
    info = task.resolved.info if task.resolved else None
    if not info or not info.preview_url:
        raise HTTPException(status_code=404, detail="没有可预览资源。")
    return proxy_remote_resource(info.preview_url, info.http_headers, request)


@app.get("/api/tasks/{task_id}/images/{index}/preview")
def preview_image(
    task_id: str,
    index: int,
    request: FastAPIRequest,
    authorization: str | None = Header(default=None),
    key: str | None = Query(default=None),
) -> StreamingResponse:
    task = state.get_task(task_id)
    authorize_media_request(task, authorization, key)
    info = task.resolved.info if task.resolved else None
    if not info or info.media_type != "image" or index < 0 or index >= len(info.images):
        raise HTTPException(status_code=404, detail="没有可预览图片。")
    image = info.images[index]
    return proxy_remote_resource(image.thumbnail_url or image.url, image.http_headers or info.http_headers, request)


def authorize_media_request(task: AgentTask, authorization: str | None, key: str | None) -> None:
    if state.is_authenticated(authorization):
        return
    if key and secrets.compare_digest(key, task.preview_key):
        return
    raise HTTPException(status_code=401, detail="请先完成本地助手配对。")


def fetch_update_manifest() -> dict[str, Any]:
    manifest_url = update_manifest_url()
    separator = "&" if "?" in manifest_url else "?"
    request = Request(f"{manifest_url}{separator}t={int(time.time())}", headers={"User-Agent": f"VideoDownloaderAgent/{AGENT_VERSION}"})
    try:
        with urlopen(request, timeout=20, context=ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="暂时无法获取更新信息，请稍后再试。") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="更新信息格式异常，请稍后再试。")
    return data


def safe_update_status() -> dict[str, Any]:
    status = state.read_update_status()
    public_keys = {"state", "message", "percent", "version", "updated_at"}
    return {key: status.get(key) for key in public_keys if key in status}


def start_update_process() -> None:
    log_path = RUNTIME_DIR / "update.log"
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "local_agent.updater",
        "--app-dir",
        str(PROJECT_ROOT),
        "--manifest-url",
        update_manifest_url(),
        "--restart",
    ]
    log_file = log_path.open("ab")
    popen_kwargs: dict[str, Any] = {"cwd": str(PROJECT_ROOT), "stdout": log_file, "stderr": log_file}
    if sys.platform.startswith("win"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        state.write_update_status(
            {
                "state": "failed",
                "message": "更新启动失败，请重新下载安装包。",
                "percent": 0.0,
                "updated_at": int(time.time()),
            }
        )
        raise HTTPException(status_code=500, detail="更新启动失败，请重新下载安装包。") from exc
    finally:
        log_file.close()


def run_resolve_task(task_id: str) -> None:
    task = state.get_task(task_id)
    update_task(task, status="running", stage="resolve", message="正在解析...")

    def status_hook(message: str) -> None:
        update_task(task, message=public_message(message))

    try:
        resolved = resolve_video(task.text, status_hook=status_hook)
    except VideoDownloaderError as exc:
        fail_task(task, exc)
        return
    except Exception as exc:
        fail_task(task, VideoDownloaderError("该内容当前无法无感解析。", code="unknown", raw_message=str(exc)))
        return

    with state.lock:
        task.resolved = resolved
        task.status = "resolved"
        task.stage = "resolve"
        task.message = "解析完成"
        task.updated_at = time.time()


def run_download_task(task_id: str, format_key: str | None) -> None:
    task = state.get_task(task_id)
    resolved = task.resolved
    if not resolved:
        fail_task(task, VideoDownloaderError("请等待解析完成后再下载。", code="not_resolved"))
        return

    def ensure_not_cancelled() -> None:
        if task.cancel_requested:
            raise DownloadCancelled()

    selected = selected_format(resolved.info, format_key)
    if resolved.info.media_type == "video" and not selected:
        fail_task(task, VideoDownloaderError("没有可下载格式，请重新解析。", code="format_unavailable"))
        return

    try:
        output_dir = ensure_writable_directory(state.settings.download_dir)
    except OSError as exc:
        fail_task(task, VideoDownloaderError(str(exc), code="permission_denied"))
        return

    update_task(task, status="downloading", stage="download", message="正在下载...", progress={})

    def progress_hook(raw: dict[str, Any]) -> None:
        ensure_not_cancelled()
        update_task(task, progress=progress_payload(raw, resolved.info.media_type), message=progress_message(raw, resolved.info.media_type))
        ensure_not_cancelled()

    def status_hook(message: str) -> None:
        ensure_not_cancelled()
        update_task(task, message=public_message(message))

    try:
        ensure_not_cancelled()
        result = download_resolved_video(
            resolved=resolved,
            selected=selected,
            output_dir=output_dir,
            progress_hook=progress_hook,
            status_hook=status_hook,
        )
    except DownloadCancelled:
        cancel_task(task)
        return
    except VideoDownloaderError as exc:
        if task.cancel_requested or exc.code == "download_cancelled":
            cancel_task(task)
            return
        fail_task(task, exc)
        return
    except Exception as exc:
        if task.cancel_requested:
            cancel_task(task)
            return
        fail_task(task, VideoDownloaderError("下载失败，请重新解析后再试。", code="unknown", raw_message=str(exc)))
        return

    with state.lock:
        task.result = result
        task.status = "completed"
        task.stage = "download"
        task.message = "下载完成"
        task.progress = {"percent": 1, "text": "下载完成"}
        task.cancel_requested = False
        task.updated_at = time.time()


def run_iphone_conversion_task(task_id: str, file_index: int) -> None:
    task = state.get_task(task_id)
    result = task.result
    if not result:
        fail_task(task, VideoDownloaderError("下载完成后才能转换。", code="not_downloaded"))
        return

    try:
        source_path = safe_result_file(result, file_index)
        if not is_convertible_video_file(source_path):
            fail_task(task, VideoDownloaderError("当前文件不是可转换的视频文件。", code="format_unavailable"))
            return
        output_path = iphone_output_path(source_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            merged_files = append_result_file(result.files, output_path)
            with state.lock:
                task.result = DownloadResult(output_dir=result.output_dir, files=merged_files)
                task.status = "completed"
                task.stage = "download"
                task.message = "已生成 iPhone 相册版"
                task.progress = {"percent": 1, "text": "已生成 iPhone 相册版"}
                task.updated_at = time.time()
            return

        ffmpeg = ffmpeg_status().get("ffmpeg")
        if not ffmpeg:
            fail_task(task, VideoDownloaderError("该功能需要 FFmpeg，请先安装 FFmpeg 后再转换。", code="ffmpeg_missing"))
            return

        update_task(task, status="converting", stage="convert", message="正在转换为 iPhone 相册格式...", progress={"percent": 0, "text": "正在转换为 iPhone 相册格式..."})
        convert_video_for_iphone(Path(str(ffmpeg)), source_path, output_path, task)
        merged_files = append_result_file(result.files, output_path)
    except VideoDownloaderError as exc:
        fail_task(task, exc)
        return
    except Exception as exc:
        fail_task(task, VideoDownloaderError("转换失败，请稍后重试。", code="unknown", raw_message=str(exc)))
        return

    with state.lock:
        task.result = DownloadResult(output_dir=result.output_dir, files=merged_files)
        task.status = "completed"
        task.stage = "download"
        task.message = "已生成 iPhone 相册版"
        task.progress = {"percent": 1, "text": "已生成 iPhone 相册版"}
        task.cancel_requested = False
        task.updated_at = time.time()


def update_task(task: AgentTask, **updates: Any) -> None:
    with state.lock:
        for key, value in updates.items():
            setattr(task, key, value)
        task.updated_at = time.time()


def fail_task(task: AgentTask, error: VideoDownloaderError) -> None:
    with state.lock:
        task.status = "failed"
        task.error = public_error(error)
        task.error_code = error.code
        task.message = task.error
        task.cancel_requested = False
        task.updated_at = time.time()


def cancel_task(task: AgentTask) -> None:
    with state.lock:
        task.status = "cancelled"
        task.stage = "download"
        task.message = "下载已停止"
        task.error = None
        task.error_code = None
        task.progress = {
            **task.progress,
            "status": "cancelled",
            "text": "下载已停止",
        }
        task.cancel_requested = False
        task.updated_at = time.time()


def selected_format(info: VideoInfo, format_key: str | None) -> FormatOption | None:
    if info.media_type != "video":
        return None
    if not info.formats:
        return None
    if not format_key:
        return info.formats[0]
    return next((fmt for fmt in info.formats if fmt.key == format_key), info.formats[0])


def safe_result_file(result: DownloadResult, file_index: int) -> Path:
    if file_index < 0 or file_index >= len(result.files):
        raise VideoDownloaderError("文件不存在。", code="file_not_found")
    output_dir = result.output_dir.expanduser().resolve()
    file_path = result.files[file_index].expanduser().resolve()
    if output_dir not in [file_path, *file_path.parents]:
        raise VideoDownloaderError("文件路径无效。", code="invalid_file_path")
    if not file_path.is_file():
        raise VideoDownloaderError("文件不存在。", code="file_not_found")
    return file_path


def is_convertible_video_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".m4v", ".mov", ".mkv", ".webm"}


def iphone_output_path(source_path: Path) -> Path:
    if "iPhone相册版" in source_path.stem:
        return source_path
    return source_path.with_name(f"{source_path.stem} iPhone相册版.mp4")


def append_result_file(files: list[Path], path: Path) -> list[Path]:
    resolved_path = path.expanduser().resolve()
    result = [file for file in files if file.expanduser().resolve() != resolved_path]
    result.append(resolved_path)
    return result


def convert_video_for_iphone(ffmpeg: Path, source_path: Path, output_path: Path, task: AgentTask) -> None:
    if source_path == output_path:
        return

    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    temp_path.unlink(missing_ok=True)
    duration = media_duration_seconds(source_path)
    command = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        "-progress",
        "pipe:1",
        "-nostats",
        str(temp_path),
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    stderr_text = ""
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            if task.cancel_requested:
                process.terminate()
                raise DownloadCancelled()
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms=") and duration:
                out_time = safe_float(line.split("=", 1)[1]) / 1_000_000
                percent = max(0.02, min(0.98, out_time / duration))
                update_task(task, progress={"percent": percent, "text": "正在转换为 iPhone 相册格式..."}, message="正在转换为 iPhone 相册格式...")
            elif line == "progress=end":
                update_task(task, progress={"percent": 0.99, "text": "正在整理转换文件..."}, message="正在整理转换文件...")
        stderr_text = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
    except DownloadCancelled:
        temp_path.unlink(missing_ok=True)
        raise
    except Exception:
        process.kill()
        temp_path.unlink(missing_ok=True)
        raise

    if return_code != 0 or not temp_path.exists() or temp_path.stat().st_size == 0:
        temp_path.unlink(missing_ok=True)
        message = stderr_text.strip() or "FFmpeg 转换失败。"
        raise VideoDownloaderError(f"转换失败：{message}", code="ffmpeg_convert_failed", raw_message=message)

    temp_path.replace(output_path)


def media_duration_seconds(path: Path) -> float:
    ffprobe = ffmpeg_status().get("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    if result.returncode != 0:
        return 0.0
    return safe_float(result.stdout.strip())


def safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def task_payload(task: AgentTask, base_url: str | None = None) -> dict[str, Any]:
    info = task.resolved.info if task.resolved else None
    result = task.result
    base_url = base_url or agent_base_url()
    return {
        "task_id": task.id,
        "status": task.status,
        "stage": task.stage,
        "message": task.message,
        "error": task.error,
        "error_code": task.error_code,
        "created_at": int(task.created_at),
        "updated_at": int(task.updated_at),
        "progress": task.progress,
        "cancel_requested": task.cancel_requested,
        "info": info_payload(info, task.id, base_url) if info else None,
        "result": result_payload(result, task.id, base_url, task.preview_key) if result else None,
    }


def info_payload(info: VideoInfo, task_id: str, base_url: str) -> dict[str, Any]:
    task = state.get_task(task_id)
    key_suffix = f"?key={task.preview_key}"
    preview_url = f"{base_url}/api/tasks/{task_id}/preview{key_suffix}" if info.preview_url else None
    image_previews = [
        f"{base_url}/api/tasks/{task_id}/images/{index}/preview{key_suffix}"
        for index, _image in enumerate(info.images[:12])
    ]
    return {
        "media_type": info.media_type,
        "title": info.title,
        "uploader": info.uploader or info.channel,
        "channel": info.channel,
        "thumbnail": info.thumbnail,
        "duration": info.duration,
        "extractor": info.extractor,
        "webpage_url": info.webpage_url,
        "preview_url": preview_url,
        "image_count": len(info.images),
        "image_previews": image_previews,
        "formats": [format_payload(fmt) for fmt in info.formats],
    }


def format_payload(fmt: FormatOption) -> dict[str, Any]:
    return {
        "key": fmt.key,
        "label": fmt.label,
        "format_id": fmt.format_id,
        "resolution": fmt.resolution,
        "ext": fmt.ext,
        "filesize": fmt.filesize,
        "video_codec": fmt.video_codec,
        "audio_codec": fmt.audio_codec,
        "needs_merge": fmt.needs_merge,
        "note": fmt.note,
    }


def result_payload(result: DownloadResult, task_id: str, base_url: str, preview_key: str) -> dict[str, Any]:
    files = []
    for index, path in enumerate(result.files):
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "url": f"{base_url}/api/tasks/{task_id}/files/{index}/download?key={preview_key}",
                "can_convert_iphone": is_convertible_video_file(path) and "iPhone相册版" not in path.stem,
                "iphone_ready": is_convertible_video_file(path) and "iPhone相册版" in path.stem,
                "index": index,
            }
        )
    return {
        "output_dir": str(result.output_dir),
        "files": [str(path) for path in result.files],
        "file_items": files,
    }


def progress_payload(raw: dict[str, Any], media_type: str) -> dict[str, Any]:
    status = raw.get("status")
    downloaded = raw.get("downloaded_bytes") or 0
    total = raw.get("total_bytes") or raw.get("total_bytes_estimate") or 0
    percent = float(downloaded) / float(total) if total else (1.0 if status == "finished" else 0.0)
    return {
        "status": status,
        "downloaded": downloaded,
        "total": total,
        "percent": max(0.0, min(1.0, percent)),
        "speed": raw.get("speed"),
        "eta": raw.get("eta"),
        "text": progress_message(raw, media_type),
    }


def progress_message(raw: dict[str, Any], media_type: str) -> str:
    if raw.get("status") == "finished":
        return "下载完成，正在处理文件..."
    downloaded = raw.get("downloaded_bytes") or 0
    total = raw.get("total_bytes") or raw.get("total_bytes_estimate") or 0
    if media_type == "image":
        return f"下载中：第 {int(downloaded)} / {int(total or 0)} 张"
    speed = raw.get("speed")
    eta = raw.get("eta")
    speed_text = f"{format_bytes(speed)}/s" if speed else "未知"
    eta_text = format_seconds(eta)
    return f"下载中：{format_bytes(downloaded)} / {format_bytes(total)}，速度 {speed_text}，剩余 {eta_text}"


def public_message(message: str) -> str:
    blocked_terms = ["cookie", "cookies", "yt-dlp", "extractor", "headers", "Playwright"]
    if any(term.lower() in message.lower() for term in blocked_terms):
        return "正在处理平台验证..."
    return message


def public_error(error: VideoDownloaderError) -> str:
    if error.code == "download_cancelled":
        return "下载已停止"
    if error.code == "not_downloaded":
        return "下载完成后才能转换。"
    if error.code == "ffmpeg_convert_failed":
        return "转换失败，请稍后重试。"
    if error.code == "invalid_file_path":
        return "文件路径无效。"
    if error.code == "file_not_found":
        return "文件不存在。"
    if error.code == "format_unavailable":
        return "当前文件不是可转换的视频文件。"
    if error.code == "ffmpeg_missing":
        return "该功能需要 FFmpeg，请先安装 FFmpeg 后再转换。"
    if error.code in {"cookies_required", "login_required", "cookies_load_failed", "auto_cookies_failed", "platform_verification_required"}:
        return "该内容需要平台验证，当前无法无感解析。"
    raw_text = f"{error.raw_message or ''}\n{str(error)}".lower()
    if "no video formats found" in raw_text:
        if "xiaohongshu" in raw_text or "小红书" in raw_text:
            return "这条小红书内容没有返回可下载的视频流，也没有拿到可确认的图片资源。请重新复制分享链接后再试。"
        return "平台没有返回可下载的视频资源，请换一个公开链接再试。"
    if error.code in {"unsupported_url"}:
        return "暂不支持这个链接，或平台没有返回可解析的内容。"
    if error.code in {"resource_not_found", "resource_forbidden", "browser_download_refresh_failed"}:
        return "平台没有返回可下载的资源，请重新复制链接并解析后再试。"
    if error.code == "image_resource_missing":
        return "平台没有返回可确认的图片资源，请换一个公开链接再试。"
    if error.code == "network_timeout":
        return "网络超时，请稍后重试。"
    if error.code == "disk_full":
        return "磁盘空间不足，请清理空间或更换保存目录。"
    if error.code == "permission_denied":
        return str(error)
    message = public_message(str(error))
    if message == "正在处理平台验证...":
        return "该内容当前无法解析，请重新复制链接后再试。"
    return message


def format_seconds(value: Any) -> str:
    if value is None:
        return "未知"
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return "未知"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def agent_base_url() -> str:
    return f"http://127.0.0.1:{DEFAULT_PORT}"


def request_base_url(request: FastAPIRequest) -> str:
    host = request.headers.get("host") or f"127.0.0.1:{DEFAULT_PORT}"
    return f"{request.url.scheme}://{host}"


def local_access_urls(request: FastAPIRequest | None = None) -> list[str]:
    urls: list[str] = []
    if request:
        current = request_base_url(request).rstrip("/") + "/"
        if not is_loopback_url(current):
            urls.append(current)
    primary_ip = primary_lan_ipv4()
    if primary_ip:
        urls.append(f"http://{primary_ip}:{DEFAULT_PORT}/")
    urls.append(f"http://127.0.0.1:{DEFAULT_PORT}/")
    for ip in local_ipv4_addresses():
        urls.append(f"http://{ip}:{DEFAULT_PORT}/")
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    for _name, ip in interface_ipv4s():
        if is_usable_lan_ip(ip):
            addresses.add(ip)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if is_usable_lan_ip(ip):
                addresses.add(ip)
    except OSError:
        pass
    if not addresses:
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = item[4][0]
                if is_usable_lan_ip(ip):
                    addresses.add(ip)
        except OSError:
            pass
    primary = primary_lan_ipv4()
    ordered = sorted(addresses)
    if primary in ordered:
        ordered.remove(primary)
        ordered.insert(0, primary)
    return ordered


def primary_lan_ipv4() -> str | None:
    if sys.platform == "darwin":
        interface = default_route_interface_macos()
        if interface:
            ip = command_text(["ipconfig", "getifaddr", interface]).strip()
            if is_usable_lan_ip(ip):
                return ip
    if sys.platform.startswith("linux"):
        output = command_text(["ip", "-4", "route", "get", "1.1.1.1"])
        parts = output.split()
        if "src" in parts:
            index = parts.index("src")
            if index + 1 < len(parts) and is_usable_lan_ip(parts[index + 1]):
                return parts[index + 1]
    return socket_default_ipv4()


def socket_default_ipv4() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    return ip if is_usable_lan_ip(ip) else None


def default_route_interface_macos() -> str | None:
    output = command_text(["route", "-n", "get", "default"])
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip()
    return None


def interface_ipv4s() -> list[tuple[str, str]]:
    if sys.platform == "darwin":
        return interface_ipv4s_from_ifconfig(command_text(["ifconfig"]))
    if sys.platform.startswith("linux"):
        output = command_text(["ip", "-o", "-4", "addr", "show", "scope", "global"])
        pairs: list[tuple[str, str]] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                name = parts[1]
                ip = parts[3].split("/", 1)[0]
                if is_likely_physical_interface(name):
                    pairs.append((name, ip))
        return pairs
    return []


def interface_ipv4s_from_ifconfig(output: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    current_name = ""
    current_block: list[str] = []
    for line in output.splitlines():
        if line and not line.startswith(("\t", " ")):
            pairs.extend(interface_ips_from_block(current_name, current_block))
            current_name = line.split(":", 1)[0]
            current_block = [line]
        elif current_name:
            current_block.append(line)
    pairs.extend(interface_ips_from_block(current_name, current_block))
    return pairs


def interface_ips_from_block(name: str, block: list[str]) -> list[tuple[str, str]]:
    if not name or not is_likely_physical_interface(name):
        return []
    text = "\n".join(block)
    if "status: inactive" in text:
        return []
    pairs: list[tuple[str, str]] = []
    for line in block:
        stripped = line.strip()
        if stripped.startswith("inet "):
            ip = stripped.split()[1]
            pairs.append((name, ip))
    return pairs


def is_likely_physical_interface(name: str) -> bool:
    lower = name.lower()
    blocked_prefixes = (
        "lo",
        "utun",
        "awdl",
        "llw",
        "bridge",
        "vmenet",
        "vmnet",
        "vbox",
        "docker",
        "br-",
        "gif",
        "stf",
        "anpi",
        "p2p",
        "tun",
        "tap",
        "wg",
        "zt",
    )
    return not lower.startswith(blocked_prefixes)


def is_usable_lan_ip(value: str | None) -> bool:
    if not value:
        return False
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        ip.version == 4
        and ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
    )


def command_text(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def is_loopback_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def qr_svg(value: str) -> str | None:
    if not value:
        return None
    try:
        import qrcode
        import qrcode.image.svg
    except Exception:
        return None
    image = qrcode.make(
        value,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=3,
    )
    output = io.BytesIO()
    image.save(output)
    return output.getvalue().decode("utf-8")


def is_same_origin_local_ui_request(request: FastAPIRequest) -> bool:
    host = request.headers.get("host", "")
    host_name = host.rsplit(":", 1)[0].strip("[]").lower()
    if host_name not in {"127.0.0.1", "localhost", "::1"}:
        return False

    origin = request.headers.get("origin")
    if origin and not is_local_agent_url(origin):
        return False

    referer = request.headers.get("referer")
    if referer and not is_local_agent_url(referer):
        return False

    fetch_site = request.headers.get("sec-fetch-site")
    return fetch_site in {None, "none", "same-origin"}


def is_local_agent_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"} and parsed.port in {None, DEFAULT_PORT}


def should_disable_browser_cache(path: str) -> bool:
    if path in {"", "/"}:
        return True
    return path.endswith((".html", ".js", ".css"))


def proxy_remote_resource(url: str, headers: dict[str, str], request: FastAPIRequest) -> StreamingResponse:
    request_headers = dict(headers or {})
    range_header = request.headers.get("range")
    if range_header:
        request_headers["Range"] = range_header
    remote_request = Request(url, headers=request_headers)
    try:
        response = urlopen(remote_request, timeout=60, context=ssl_context())
    except (HTTPError, URLError, OSError) as exc:
        raise HTTPException(status_code=502, detail="预览资源暂时不可用。") from exc

    response_headers = {}
    for name in ["content-length", "content-range", "accept-ranges"]:
        value = response.headers.get(name)
        if value:
            response_headers[name] = value
    media_type = response.headers.get("content-type") or "application/octet-stream"

    def iterator():
        with response:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(iterator(), status_code=getattr(response, "status", 200), media_type=media_type, headers=response_headers)


def ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def print_startup_banner() -> None:
    print("")
    print("本地下载助手已启动")
    print(f"本机访问：http://127.0.0.1:{DEFAULT_PORT}")
    lan_urls = [url for url in local_access_urls() if "127.0.0.1" not in url]
    if lan_urls:
        print("手机/NAS 局域网访问：")
        for url in lan_urls:
            print(f"  {url}")
    print(f"本次配对码：{state.pair_code}")
    print("配对码 10 分钟内有效。请在云端管理页输入一次即可。")
    print("")


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="local_web")


def main() -> None:
    print_startup_banner()
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
