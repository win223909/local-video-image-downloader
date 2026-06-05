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
UPDATE_PACKAGE_FILE = "agent-source.zip"


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
        if parsed.path == f"/downloads/{UPDATE_PACKAGE_FILE}":
            self.handle_update_package(head_only=False)
            return
        self.record_event("not_found", status=HTTPStatus.NOT_FOUND.value, path=parsed.path)
        self.write_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/download-file":
            self.handle_download_file(parsed.query, head_only=True)
            return
        if parsed.path == f"/downloads/{UPDATE_PACKAGE_FILE}":
            self.handle_update_package(head_only=True)
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

    def handle_update_package(self, head_only: bool = False) -> None:
        filename = UPDATE_PACKAGE_FILE
        if not (DOWNLOAD_ROOT / filename).is_file():
            self.record_event(
                "update_package_rejected",
                status=HTTPStatus.NOT_FOUND.value,
                filename=filename,
                reason="missing_update_package",
            )
            self.write_json({"error": "更新包暂时不可用，请稍后再试。"}, HTTPStatus.NOT_FOUND)
            return

        self.record_event(
            "update_package_granted",
            status=HTTPStatus.OK.value,
            filename=filename,
            head_only=head_only,
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("X-Accel-Redirect", f"{INTERNAL_PREFIX}/{quote(filename)}")
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "public, max-age=300")
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
        payload = build_stats_payload(rows, days=days, limit=limit)
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


def event_is_head(row: dict) -> bool:
    return bool(row.get("head_only")) or str(row.get("method", "")).upper() == "HEAD"


def event_day(row: dict) -> str:
    return str(row.get("ts", ""))[:10]


def safe_recent(rows: list[dict], limit: int) -> list[dict]:
    allowed = {
        "ts",
        "event",
        "method",
        "path",
        "status",
        "ip_hash",
        "country",
        "user_agent",
        "referer",
        "platform",
        "filename",
        "reason",
        "head_only",
    }
    return [{key: row.get(key) for key in allowed if key in row} for row in rows[-limit:]]


def build_stats_payload(rows: list[dict], *, days: int, limit: int) -> dict:
    events = Counter(row.get("event", "") for row in rows)
    statuses = Counter(str(row.get("status", "")) for row in rows)
    platforms = Counter(row.get("platform", "") for row in rows if row.get("platform"))
    countries = Counter(row.get("country", "") for row in rows if row.get("country"))
    files = Counter(row.get("filename", "") for row in rows if row.get("filename"))
    ip_hashes = Counter(row.get("ip_hash", "") for row in rows if row.get("ip_hash"))
    user_agents = Counter(row.get("user_agent", "") for row in rows if row.get("user_agent"))

    installer_downloads = [
        row
        for row in rows
        if row.get("event") == "download_granted" and not event_is_head(row)
    ]
    installer_checks = [
        row for row in rows if row.get("event") == "download_granted" and event_is_head(row)
    ]
    update_downloads = [
        row
        for row in rows
        if row.get("event") == "update_package_granted" and not event_is_head(row)
    ]
    update_checks = [
        row for row in rows if row.get("event") == "update_package_granted" and event_is_head(row)
    ]
    blocked_events = [
        row
        for row in rows
        if str(row.get("status", "")).startswith(("4", "5"))
        or str(row.get("event", "")).endswith("_rejected")
    ]

    today = datetime.now(timezone.utc).date()
    day_map = {
        (today - timedelta(days=offset)).isoformat(): {
            "date": (today - timedelta(days=offset)).isoformat(),
            "link_issued": 0,
            "installer_downloads": 0,
            "installer_checks": 0,
            "update_downloads": 0,
            "blocked": 0,
        }
        for offset in range(days - 1, -1, -1)
    }
    for row in rows:
        day = event_day(row)
        if day not in day_map:
            continue
        event = row.get("event")
        if event == "link_issued":
            day_map[day]["link_issued"] += 1
        elif event == "download_granted":
            if event_is_head(row):
                day_map[day]["installer_checks"] += 1
            else:
                day_map[day]["installer_downloads"] += 1
        elif event == "update_package_granted" and not event_is_head(row):
            day_map[day]["update_downloads"] += 1
        if str(row.get("status", "")).startswith(("4", "5")) or str(event).endswith("_rejected"):
            day_map[day]["blocked"] += 1

    downloader_identities = {
        (row.get("ip_hash"), row.get("user_agent"))
        for row in installer_downloads + update_downloads
        if row.get("ip_hash") or row.get("user_agent")
    }
    visitor_identities = {
        (row.get("ip_hash"), row.get("user_agent"))
        for row in rows
        if row.get("event") not in {"stats_viewed", "stats_rejected"} and (row.get("ip_hash") or row.get("user_agent"))
    }

    real_download_rows = installer_downloads + update_downloads
    real_download_rows.sort(key=lambda row: str(row.get("ts", "")))

    summary = {
        "link_issued": events.get("link_issued", 0),
        "installer_downloads": len(installer_downloads),
        "installer_checks": len(installer_checks),
        "update_downloads": len(update_downloads),
        "update_checks": len(update_checks),
        "blocked_requests": len(blocked_events),
        "estimated_visitors": len(visitor_identities),
        "estimated_downloaders": len(downloader_identities),
    }

    return {
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
        "recent": safe_recent(rows, limit),
        "summary": summary,
        "by_day": list(day_map.values()),
        "downloads": {
            "by_file": Counter(row.get("filename", "") for row in real_download_rows if row.get("filename")).most_common(limit),
            "by_country": Counter(row.get("country", "") for row in real_download_rows if row.get("country")).most_common(limit),
            "by_user_agent": Counter(row.get("user_agent", "") for row in real_download_rows if row.get("user_agent")).most_common(limit),
            "recent": safe_recent(real_download_rows, limit),
        },
    }


def main() -> None:
    if not SECRET:
        raise SystemExit("VIDEO_DOWNLOADER_DOWNLOAD_SECRET is required")
    server = ThreadingHTTPServer((HOST, PORT), DownloadGateHandler)
    print(f"download gate listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
