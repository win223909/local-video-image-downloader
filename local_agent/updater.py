from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import ssl
import stat
import subprocess
import sys
import time
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import zipfile
from pathlib import PurePosixPath

try:
    import certifi
except Exception:  # pragma: no cover - updater should still work without certifi.
    certifi = None


UPDATE_DIR_NAME = "update"
STATUS_FILE_NAME = "update-status.json"
SERVICE_LABEL = "app.video-downloader.agent"
MANAGED_PATHS = [
    "README.md",
    "requirements.txt",
    "requirements-agent.txt",
    "web",
    "local_agent",
    "video_downloader",
]
DEFAULT_PIP_INDEX_URLS = [
    "https://pypi.org/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://pypi.doubanio.com/simple",
]
DEFAULT_PLAYWRIGHT_HOSTS = [
    "",
    "https://npmmirror.com/mirrors/playwright",
]


def main() -> int:
    args = parse_args()
    app_dir = Path(args.app_dir).expanduser().resolve()
    runtime_dir = app_dir / ".runtime"
    update_dir = runtime_dir / UPDATE_DIR_NAME
    status_file = runtime_dir / STATUS_FILE_NAME
    backup_dir = update_dir / "backup"
    backup_created = False
    restart_requested = False
    previous_health = read_agent_health()
    expected_build = ""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    update_dir.mkdir(parents=True, exist_ok=True)

    def status(state: str, message: str, *, percent: float = 0.0, error: str | None = None, version: str | None = None) -> None:
        write_status(
            status_file,
            {
                "state": state,
                "message": message,
                "percent": max(0.0, min(1.0, percent)),
                "error": error,
                "version": version,
                "updated_at": int(time.time()),
                "pid": os.getpid(),
                "build_id": expected_build,
                "previous_instance": previous_health.get("instance_id"),
            },
        )

    try:
        status("running", "正在获取更新信息...", percent=0.05)
        manifest = fetch_json(args.manifest_url)
        latest_version = str(manifest.get("version") or "").strip()
        agent_url = urljoin(args.manifest_url, str(manifest.get("agent_url") or "").strip())
        expected_sha = str(manifest.get("agent_sha256") or "").strip().lower()
        if not latest_version or not agent_url or not expected_sha:
            raise RuntimeError("更新信息不完整，请稍后再试。")

        status("running", "正在下载更新包...", percent=0.16, version=latest_version)
        zip_path = update_dir / "agent-source.zip"
        download_file(agent_url, zip_path)
        actual_sha = sha256(zip_path)
        if actual_sha.lower() != expected_sha:
            raise RuntimeError("更新包校验失败，请稍后重试或重新下载安装包。")

        status("running", "正在解压更新包...", percent=0.34, version=latest_version)
        staging_dir = update_dir / "staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as archive:
            safe_extract_zip(archive, staging_dir)
        validate_staging_package(staging_dir)
        if package_version(staging_dir) != latest_version:
            raise RuntimeError("更新包版本与更新信息不一致，未修改现有安装。")
        expected_build = build_fingerprint(staging_dir)

        status("running", "正在替换本地助手文件...", percent=0.5, version=latest_version)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        backup_managed_files(app_dir, backup_dir)
        backup_created = True
        replace_managed_files(app_dir, staging_dir)

        status("running", "正在更新 Python 依赖...", percent=0.68, version=latest_version)
        install_requirements(app_dir)

        status("running", "正在检查后台浏览器组件...", percent=0.84, version=latest_version)
        install_playwright_chromium(app_dir)

        status("restarting", "文件已安装，正在验证本地助手重启...", percent=0.95, version=latest_version)
        if args.restart:
            restart_requested = restart_agent(app_dir, previous_health.get("pid"))
        if not restart_requested:
            status("awaiting_restart", "文件已安装，请手动重启本地助手。重启验证前不会标记更新成功。", percent=0.95, version=latest_version)
            return 0
        wait_for_agent(latest_version, expected_build, previous_health)
        shutil.rmtree(backup_dir, ignore_errors=True)
        status("completed", "本地助手已更新，正在重新连接。", percent=1.0, version=latest_version)
        return 0
    except Exception as exc:
        if backup_created and backup_dir.exists():
            try:
                restore_managed_files(app_dir, backup_dir)
            except Exception as rollback_exc:
                exc = RuntimeError(f"{exc}；且无法恢复更新前文件：{rollback_exc}")
            else:
                if args.restart:
                    try:
                        restarted = restart_agent(app_dir, read_agent_health().get("pid") or previous_health.get("pid"))
                        if not restarted:
                            exc = RuntimeError(f"{exc}；更新前文件已恢复，请手动重启助手。")
                    except Exception as restart_exc:
                        exc = RuntimeError(f"{exc}；更新前文件已恢复，但重启失败：{restart_exc}")
        status("failed", "更新失败，请稍后重试或重新下载安装包。", percent=0.0, error=str(exc))
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update local downloader agent.")
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--manifest-url", required=True)
    parser.add_argument("--restart", action="store_true")
    return parser.parse_args()


def write_status(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as output:
            temporary = Path(output.name)
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_fingerprint(app_dir: Path) -> str:
    digest = hashlib.sha256()
    files = [app_dir / name for name in ("requirements.txt", "requirements-agent.txt")]
    for folder, suffixes in (("local_agent", {".py"}), ("video_downloader", {".py"}), ("web", {".js", ".html", ".css"})):
        files.extend(path for path in (app_dir / folder).rglob("*") if path.suffix in suffixes and "downloads" not in path.relative_to(app_dir / folder).parts)
    for path in sorted(files):
        if path.is_file():
            digest.update(path.relative_to(app_dir).as_posix().encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def package_version(app_dir: Path) -> str:
    tree = ast.parse((app_dir / "local_agent/server.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "AGENT_VERSION" for target in node.targets):
            value = ast.literal_eval(node.value)
            return value if isinstance(value, str) else ""
    return ""


def read_agent_health() -> dict:
    try:
        # Never route a loopback readiness probe through an HTTP proxy.
        from urllib.request import ProxyHandler, build_opener
        with build_opener(ProxyHandler({})).open("http://127.0.0.1:17890/api/health", timeout=2) as response:
            data = json.load(response)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def wait_for_agent(version: str, expected_build: str, previous: dict, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = read_agent_health()
        if (health.get("ok") and health.get("version") == version
                and health.get("build_id") == expected_build
                and health.get("instance_id")
                and health["instance_id"] != previous.get("instance_id")):
            return
        time.sleep(0.5)
    raise RuntimeError("新版助手未通过重启验证，正在恢复更新前文件。")


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def reconcile_status(data: dict, version: str, build_id: str, instance_id: str) -> dict:
    result = dict(data)
    if (data.get("state") == "awaiting_restart" and data.get("version") == version
            and data.get("build_id") == build_id and data.get("previous_instance") != instance_id):
        result.update(state="completed", percent=1.0, message="本地助手已重启并通过版本验证。", updated_at=int(time.time()))
    elif data.get("state") in {"running", "restarting", "queued"}:
        pid = data.get("pid")
        try:
            age = time.time() - float(data.get("updated_at") or 0)
        except (TypeError, ValueError):
            age = float("inf")
        if (isinstance(pid, int) and not process_is_alive(pid)) or (not isinstance(pid, int) and age > 60):
            result.update(state="failed", percent=0.0, message="更新进程已退出，未确认更新成功。请重试或检查本地更新日志。", updated_at=int(time.time()))
    return result


def fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "VideoDownloaderAgent-Updater/1.0"})
    with urlopen(request, timeout=30, context=ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "VideoDownloaderAgent-Updater/1.0"})
    with urlopen(request, timeout=90, context=ssl_context()) as response, path.open("wb") as output:
        shutil.copyfileobj(response, output)


def ssl_context() -> ssl.SSLContext:
    if certifi:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_zip(archive: zipfile.ZipFile, staging_dir: Path) -> None:
    """Extract only regular files/directories that remain inside staging_dir."""
    staging_root = staging_dir.resolve()
    members: list[tuple[zipfile.ZipInfo, Path]] = []

    for member in archive.infolist():
        raw_name = member.filename
        normalized_name = raw_name.replace("\\", "/")
        if not normalized_name or normalized_name in {".", "/"}:
            continue
        if normalized_name.startswith("/") or re.match(r"^[A-Za-z]:", normalized_name):
            raise RuntimeError(f"更新包包含非法绝对路径：{raw_name}")

        parts = PurePosixPath(normalized_name).parts
        if ".." in parts:
            raise RuntimeError(f"更新包包含非法上级路径：{raw_name}")
        file_type = stat.S_IFMT(member.external_attr >> 16)
        if file_type == stat.S_IFLNK:
            raise RuntimeError(f"更新包不允许包含符号链接：{raw_name}")

        target = (staging_root / Path(*parts)).resolve()
        try:
            target.relative_to(staging_root)
        except ValueError as exc:
            raise RuntimeError(f"更新包路径逃出临时目录：{raw_name}") from exc
        members.append((member, target))

    # Validate every member before writing the first byte to staging_dir.
    for member, target in members:
        if member.is_dir() or member.filename.endswith(("/", "\\")):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def validate_staging_package(staging_dir: Path) -> None:
    managed_directories = {"web", "local_agent", "video_downloader"}
    missing: list[str] = []
    invalid_types: list[str] = []
    for rel in MANAGED_PATHS:
        path = staging_dir / rel
        if not path.exists():
            missing.append(rel)
        elif rel in managed_directories and not path.is_dir():
            invalid_types.append(f"{rel}（应为目录）")
        elif rel not in managed_directories and not path.is_file():
            invalid_types.append(f"{rel}（应为文件）")

    required_files = (
        staging_dir / "local_agent" / "server.py",
    )
    missing.extend(str(path.relative_to(staging_dir)) for path in required_files if not path.is_file())

    if missing or invalid_types:
        details = []
        if missing:
            details.append(f"缺少：{', '.join(missing)}")
        if invalid_types:
            details.append(f"类型错误：{', '.join(invalid_types)}")
        raise RuntimeError(f"更新包结构不完整，{'；'.join(details)}")


def backup_managed_files(app_dir: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for rel in MANAGED_PATHS:
        source = app_dir / rel
        if not source.exists():
            continue
        target = backup_dir / rel
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def restore_managed_files(app_dir: Path, backup_dir: Path) -> None:
    remove_managed_files(app_dir)
    for rel in MANAGED_PATHS:
        source = backup_dir / rel
        target = app_dir / rel
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def remove_managed_files(app_dir: Path) -> None:
    for rel in MANAGED_PATHS:
        target = app_dir / rel
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def replace_managed_files(app_dir: Path, staging_dir: Path) -> None:
    remove_managed_files(app_dir)

    for rel in MANAGED_PATHS:
        source = staging_dir / rel
        target = app_dir / rel
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def install_requirements(app_dir: Path) -> None:
    requirements = app_dir / "requirements-agent.txt"
    if not requirements.exists():
        return
    for index_url in pip_index_urls():
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--upgrade",
            "-i",
            index_url,
            "-r",
            str(requirements),
        ]
        if run_quiet(cmd):
            return
    raise RuntimeError("Python 依赖更新失败。")


def install_playwright_chromium(app_dir: Path) -> None:
    if not (app_dir / "requirements-agent.txt").exists():
        return
    for host in playwright_hosts():
        env = os.environ.copy()
        if host:
            env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
        if run_quiet([sys.executable, "-m", "playwright", "install", "chromium"], env=env):
            return
    # Browser fallback can be unavailable without blocking core yt-dlp updates.


def pip_index_urls() -> list[str]:
    raw = os.environ.get("PIP_INDEX_URLS", "")
    values = [item.strip() for item in raw.split() if item.strip()]
    if values:
        return values
    first = os.environ.get("PIP_INDEX_URL", "").strip()
    if first:
        return [first, *[item for item in DEFAULT_PIP_INDEX_URLS if item != first]]
    return DEFAULT_PIP_INDEX_URLS


def playwright_hosts() -> list[str]:
    raw = os.environ.get("PLAYWRIGHT_DOWNLOAD_HOSTS", "")
    values = [item.strip() for item in raw.split() if item.strip()]
    if values:
        return values
    first = os.environ.get("PLAYWRIGHT_DOWNLOAD_HOST", "").strip()
    if first:
        return [first, *[item for item in DEFAULT_PLAYWRIGHT_HOSTS if item and item != first]]
    return DEFAULT_PLAYWRIGHT_HOSTS


def run_quiet(cmd: list[str], env: dict[str, str] | None = None) -> bool:
    try:
        completed = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, check=False)
    except OSError:
        return False
    return completed.returncode == 0


def restart_agent(app_dir: Path, previous_pid: int | None = None) -> bool:
    system = platform.system().lower()
    if system == "darwin":
        for label in (SERVICE_LABEL, "xyz.k666.video-downloader-agent"):
            plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            if not plist.is_file():
                continue
            with plist.open("rb") as source:
                config = plistlib.load(source)
            if Path(config.get("WorkingDirectory", "")).resolve() != app_dir.resolve():
                continue
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, check=True, timeout=15,
            )
            return True
    if system == "windows":
        return restart_windows_agent(app_dir, previous_pid)
    return False


def restart_windows_agent(app_dir: Path, previous_pid: int | None = None) -> bool:
    base_dir = app_dir.parent
    run_script = base_dir / "run-agent.ps1"
    creationflags = 0
    for flag_name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        creationflags |= getattr(subprocess, flag_name, 0)
    if run_script.exists() and isinstance(previous_pid, int) and previous_pid > 0:
        command = "\n".join(
            [
                f"$RunScript = {ps_quote(str(run_script))}",
                f"$AppDir = {ps_quote(str(app_dir))}",
                f"$AgentPid = {previous_pid}",
                "Start-Sleep -Seconds 1",
                "try {",
                "  Get-CimInstance Win32_Process |",
                "    Where-Object { $_.ProcessId -eq $AgentPid -and $_.CommandLine -like '*local_agent.server*' } |",
                "    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
                "} catch {}",
                "Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"' + $RunScript + '\"') -WorkingDirectory $AppDir",
            ]
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return True
    return False


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
