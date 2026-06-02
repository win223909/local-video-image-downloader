from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import zipfile

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
            archive.extractall(staging_dir)

        status("running", "正在替换本地助手文件...", percent=0.5, version=latest_version)
        replace_managed_files(app_dir, staging_dir)

        status("running", "正在更新 Python 依赖...", percent=0.68, version=latest_version)
        install_requirements(app_dir)

        status("running", "正在检查后台浏览器组件...", percent=0.84, version=latest_version)
        install_playwright_chromium(app_dir)

        status("restarting", "更新完成，正在重启本地助手...", percent=0.95, version=latest_version)
        if args.restart:
            restart_agent(app_dir)
        status("completed", "本地助手已更新，正在重新连接。", percent=1.0, version=latest_version)
        return 0
    except Exception as exc:
        status("failed", "更新失败，请稍后重试或重新下载安装包。", percent=0.0, error=str(exc))
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update local downloader agent.")
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--manifest-url", required=True)
    parser.add_argument("--restart", action="store_true")
    return parser.parse_args()


def write_status(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def replace_managed_files(app_dir: Path, staging_dir: Path) -> None:
    for rel in MANAGED_PATHS:
        target = app_dir / rel
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

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


def restart_agent(app_dir: Path) -> None:
    system = platform.system().lower()
    if system == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
        if plist.exists():
            subprocess.Popen(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{SERVICE_LABEL}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
    if system == "windows":
        restart_windows_agent(app_dir)


def restart_windows_agent(app_dir: Path) -> None:
    base_dir = app_dir.parent
    run_script = base_dir / "run-agent.ps1"
    creationflags = 0
    for flag_name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        creationflags |= getattr(subprocess, flag_name, 0)
    if run_script.exists():
        command = "\n".join(
            [
                f"$RunScript = {ps_quote(str(run_script))}",
                f"$AppDir = {ps_quote(str(app_dir))}",
                "Start-Sleep -Seconds 1",
                "try {",
                "  Get-CimInstance Win32_Process |",
                "    Where-Object { $_.ProcessId -ne $PID -and ($_.CommandLine -like '*local_agent.server*' -or $_.CommandLine -like '*run-agent.ps1*') } |",
                "    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
                "} catch {}",
                "Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', $RunScript) -WorkingDirectory $AppDir",
            ]
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return

    subprocess.Popen(
        [sys.executable, "-m", "local_agent.server"],
        cwd=str(app_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
