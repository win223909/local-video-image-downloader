from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import time
from urllib.parse import parse_qs, quote, urlparse


DEFAULT_DOWNLOAD_ROOT = Path(__file__).resolve().parents[1] / "web" / "downloads"
DOWNLOAD_ROOT = Path(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_ROOT") or os.environ.get("K666_DOWNLOAD_ROOT") or DEFAULT_DOWNLOAD_ROOT)
INTERNAL_PREFIX = os.environ.get("VIDEO_DOWNLOADER_INTERNAL_DOWNLOAD_PREFIX") or os.environ.get("K666_INTERNAL_DOWNLOAD_PREFIX") or "/__video_downloader_internal_downloads"
SECRET = os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_SECRET") or os.environ.get("K666_DOWNLOAD_SECRET", "")
TOKEN_TTL_SECONDS = int(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_TOKEN_TTL_SECONDS") or os.environ.get("K666_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
HOST = os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_GATE_HOST") or os.environ.get("K666_DOWNLOAD_GATE_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_GATE_PORT") or os.environ.get("K666_DOWNLOAD_GATE_PORT", "17991"))

INSTALLER_FILES = {
    "macos": "K666VideoDownloaderAgent-macOS.zip",
    "mac": "K666VideoDownloaderAgent-macOS.zip",
    "windows": "K666VideoDownloaderAgent-Windows.zip",
    "win": "K666VideoDownloaderAgent-Windows.zip",
}


def sign(filename: str, expires: int) -> str:
    message = f"{filename}:{expires}".encode("utf-8")
    digest = hmac.new(SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def valid_signature(filename: str, expires: int, signature: str) -> bool:
    if expires < int(time()):
        return False
    expected = sign(filename, expires)
    return hmac.compare_digest(expected, signature)


def json_body(payload: dict, status: HTTPStatus = HTTPStatus.OK) -> tuple[int, bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return status.value, body


class DownloadGateHandler(BaseHTTPRequestHandler):
    server_version = "VideoDownloaderDownloadGate/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json({"ok": True})
            return
        if parsed.path == "/api/download-link":
            self.handle_download_link(parsed.query)
            return
        if parsed.path == "/api/download-file":
            self.handle_download_file(parsed.query)
            return
        self.write_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/download-file":
            self.handle_download_file(parsed.query, head_only=True)
            return
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.end_headers()

    def handle_download_link(self, query: str) -> None:
        params = parse_qs(query)
        platform = (params.get("platform", [""])[0] or "").lower()
        filename = INSTALLER_FILES.get(platform)
        if not filename:
            self.write_json({"error": "请选择 macOS 或 Windows 安装包。"}, HTTPStatus.BAD_REQUEST)
            return
        if not (DOWNLOAD_ROOT / filename).is_file():
            self.write_json({"error": "安装包暂时不可用，请稍后再试。"}, HTTPStatus.NOT_FOUND)
            return
        expires = int(time()) + TOKEN_TTL_SECONDS
        signature = sign(filename, expires)
        url = (
            f"/api/download-file?file={quote(filename)}"
            f"&expires={expires}&sig={quote(signature)}"
        )
        self.write_json({"url": url, "expires_in": TOKEN_TTL_SECONDS})

    def handle_download_file(self, query: str, head_only: bool = False) -> None:
        params = parse_qs(query)
        filename = params.get("file", [""])[0]
        signature = params.get("sig", [""])[0]
        try:
            expires = int(params.get("expires", ["0"])[0])
        except ValueError:
            expires = 0
        if filename not in set(INSTALLER_FILES.values()):
            self.write_json({"error": "下载文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        if not signature or not valid_signature(filename, expires, signature):
            self.write_json({"error": "下载链接已过期，请回到页面重新点击下载。"}, HTTPStatus.FORBIDDEN)
            return
        if not (DOWNLOAD_ROOT / filename).is_file():
            self.write_json({"error": "安装包暂时不可用，请稍后再试。"}, HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("X-Accel-Redirect", f"{INTERNAL_PREFIX}/{quote(filename)}")
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        code, body = json_body(payload, status)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    if not SECRET:
        raise SystemExit("VIDEO_DOWNLOADER_DOWNLOAD_SECRET is required")
    server = ThreadingHTTPServer((HOST, PORT), DownloadGateHandler)
    print(f"download gate listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
