from __future__ import annotations

import base64
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
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
DOWNLOAD_ROOT = Path(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_ROOT") or DEFAULT_DOWNLOAD_ROOT)
INTERNAL_PREFIX = os.environ.get("VIDEO_DOWNLOADER_INTERNAL_DOWNLOAD_PREFIX") or "/__video_downloader_internal_downloads"
SECRET = os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_SECRET", "")
TOKEN_TTL_SECONDS = int(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
HOST = os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_GATE_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIDEO_DOWNLOADER_DOWNLOAD_GATE_PORT", "17991"))
ACCESS_LOG_PATH = Path(
    os.environ.get("VIDEO_DOWNLOADER_ACCESS_LOG")
    or (DOWNLOAD_ROOT.parent / "logs" / "download_gate.jsonl")
)
STATS_TOKEN = os.environ.get("VIDEO_DOWNLOADER_STATS_TOKEN", "")
STATS_MAX_LINES = int(os.environ.get("VIDEO_DOWNLOADER_STATS_MAX_LINES", "50000"))

INSTALLER_FILES = {
    "macos": "VideoDownloaderAgent-macOS.zip",
    "mac": "VideoDownloaderAgent-macOS.zip",
    "windows": "VideoDownloaderAgent-Windows.zip",
    "win": "VideoDownloaderAgent-Windows.zip",
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_hash(value: str) -> str:
    key = SECRET.encode("utf-8") if SECRET else b"video-downloader-download-gate"
    digest = hmac.new(key, value.encode("utf-8", "ignore"), hashlib.sha256).hexdigest()
    return digest[:16]


def trim(value: str | None, max_length: int = 240) -> str:
    if not value:
        return ""
    return value.replace("\n", " ").replace("\r", " ")[:max_length]


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
        if parsed.path == "/api/download-stats":
            self.handle_download_stats(parsed.query)
            return
        self.record_event("not_found", status=HTTPStatus.NOT_FOUND.value, path=parsed.path)
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
            self.record_event(
                "link_rejected",
                status=HTTPStatus.BAD_REQUEST.value,
                platform=platform,
                reason="invalid_platform",
            )
            self.write_json({"error": "请选择 macOS 或 Windows 安装包。"}, HTTPStatus.BAD_REQUEST)
            return
        if not (DOWNLOAD_ROOT / filename).is_file():
            self.record_event(
                "link_rejected",
                status=HTTPStatus.NOT_FOUND.value,
                platform=platform,
                filename=filename,
                reason="missing_installer",
            )
            self.write_json({"error": "安装包暂时不可用，请稍后再试。"}, HTTPStatus.NOT_FOUND)
            return
        expires = int(time()) + TOKEN_TTL_SECONDS
        signature = sign(filename, expires)
        url = (
            f"/api/download-file?file={quote(filename)}"
            f"&expires={expires}&sig={quote(signature)}"
        )
        self.record_event(
            "link_issued",
            status=HTTPStatus.OK.value,
            platform=platform,
            filename=filename,
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
            self.record_event(
                "download_rejected",
                status=HTTPStatus.NOT_FOUND.value,
                filename=filename,
                reason="unknown_file",
            )
            self.write_json({"error": "下载文件不存在。"}, HTTPStatus.NOT_FOUND)
            return
        if not signature or not valid_signature(filename, expires, signature):
            self.record_event(
                "download_rejected",
                status=HTTPStatus.FORBIDDEN.value,
                filename=filename,
                reason="invalid_or_expired_signature",
            )
            self.write_json({"error": "下载链接已过期，请回到页面重新点击下载。"}, HTTPStatus.FORBIDDEN)
            return
        if not (DOWNLOAD_ROOT / filename).is_file():
            self.record_event(
                "download_rejected",
                status=HTTPStatus.NOT_FOUND.value,
                filename=filename,
                reason="missing_installer",
            )
            self.write_json({"error": "安装包暂时不可用，请稍后再试。"}, HTTPStatus.NOT_FOUND)
            return

        self.record_event(
            "download_granted",
            status=HTTPStatus.OK.value,
            filename=filename,
            head_only=head_only,
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("X-Accel-Redirect", f"{INTERNAL_PREFIX}/{quote(filename)}")
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def handle_download_stats(self, query: str) -> None:
        if not STATS_TOKEN:
            self.record_event("stats_rejected", status=HTTPStatus.NOT_FOUND.value, reason="disabled")
            self.write_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token or not hmac.compare_digest(token, STATS_TOKEN):
            self.record_event("stats_rejected", status=HTTPStatus.FORBIDDEN.value, reason="bad_token")
            self.write_json({"error": "无权查看访问统计。"}, HTTPStatus.FORBIDDEN)
            return

        params = parse_qs(query)
        try:
            days = max(1, min(90, int(params.get("days", ["7"])[0])))
        except ValueError:
            days = 7
        try:
            limit = max(1, min(100, int(params.get("limit", ["20"])[0])))
        except ValueError:
            limit = 20

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = list(read_recent_log_rows(cutoff))
        events = Counter(row.get("event", "") for row in rows)
        statuses = Counter(str(row.get("status", "")) for row in rows)
        platforms = Counter(row.get("platform", "") for row in rows if row.get("platform"))
        countries = Counter(row.get("country", "") for row in rows if row.get("country"))
        files = Counter(row.get("filename", "") for row in rows if row.get("filename"))
        ip_hashes = Counter(row.get("ip_hash", "") for row in rows if row.get("ip_hash"))
        user_agents = Counter(row.get("user_agent", "") for row in rows if row.get("user_agent"))

        payload = {
            "ok": True,
            "days": days,
            "events_count": len(rows),
            "events": dict(events),
            "statuses": dict(statuses),
            "platforms": dict(platforms),
            "countries": dict(countries),
            "files": dict(files),
            "top_ip_hashes": ip_hashes.most_common(limit),
            "top_user_agents": user_agents.most_common(limit),
            "recent": rows[-limit:],
        }
        self.record_event("stats_viewed", status=HTTPStatus.OK.value)
        self.write_json(payload)

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

    def client_ip(self) -> str:
        forwarded = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return self.client_address[0] if self.client_address else ""

    def record_event(self, event: str, **extra: object) -> None:
        ip = self.client_ip()
        record = {
            "ts": now_iso(),
            "event": event,
            "method": self.command,
            "path": urlparse(self.path).path,
            "status": extra.pop("status", None),
            "ip_hash": short_hash(ip) if ip else "",
            "country": trim(self.headers.get("CF-IPCountry"), 8),
            "user_agent": trim(self.headers.get("User-Agent"), 320),
            "referer": trim(self.headers.get("Referer"), 320),
        }
        record.update({key: value for key, value in extra.items() if value not in (None, "")})
        try:
            ACCESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with ACCESS_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError as exc:
            print(f"failed to write access log: {exc}", flush=True)


def read_recent_log_rows(cutoff: datetime):
    if not ACCESS_LOG_PATH.is_file():
        return []
    rows: deque[dict] = deque(maxlen=STATS_MAX_LINES)
    with ACCESS_LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
                row_ts = datetime.fromisoformat(str(row.get("ts", "")).replace("Z", "+00:00"))
            except (ValueError, json.JSONDecodeError, TypeError):
                continue
            if row_ts >= cutoff:
                rows.append(row)
    return rows


def main() -> None:
    if not SECRET:
        raise SystemExit("VIDEO_DOWNLOADER_DOWNLOAD_SECRET is required")
    server = ThreadingHTTPServer((HOST, PORT), DownloadGateHandler)
    print(f"download gate listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
