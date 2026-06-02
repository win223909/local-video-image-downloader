from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import textwrap
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WEB_DOWNLOADS = ROOT / "web" / "downloads"
AGENT_ZIP = WEB_DOWNLOADS / "agent-source.zip"
UPDATE_MANIFEST = WEB_DOWNLOADS / "update.json"
MAC_INSTALLER_ZIP = WEB_DOWNLOADS / "K666VideoDownloaderAgent-macOS.zip"
WINDOWS_INSTALLER_ZIP = WEB_DOWNLOADS / "K666VideoDownloaderAgent-Windows.zip"
AGENT_URL = "https://download.k666.xyz/downloads/agent-source.zip"
UPDATE_MANIFEST_URL = "https://download.k666.xyz/downloads/update.json"
CONTROL_URL = "http://127.0.0.1:17890/"


SOURCE_FILES = [
    "README.md",
    "requirements.txt",
    "requirements-agent.txt",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
    "web/site.webmanifest",
    "web/robots.txt",
    "web/apple-touch-icon.png",
    "web/favicon-32.png",
]


SOURCE_DIRS = [
    "local_agent",
    "video_downloader",
]


WEB_ASSET_DIRS = [
    "web/assets",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def agent_version() -> str:
    source = (ROOT / "local_agent" / "server.py").read_text(encoding="utf-8")
    match = re.search(r'^AGENT_VERSION\s*=\s*"([^"]+)"', source, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Cannot find AGENT_VERSION in local_agent/server.py")
    return match.group(1)


def write_zip(path: Path, files: list[tuple[Path, str, int | None]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, arcname, mode in files:
            info = zipfile.ZipInfo(arcname, date_time=time.localtime(source.stat().st_mtime)[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            if not arcname.isascii():
                info.flag_bits |= 0x800
            if mode is not None:
                info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, source.read_bytes())


def build_agent_source() -> str:
    entries: list[tuple[Path, str, int | None]] = []
    for rel in SOURCE_FILES:
        entries.append((ROOT / rel, rel, 0o644))
    for rel_dir in SOURCE_DIRS:
        for source in sorted((ROOT / rel_dir).rglob("*.py")):
            entries.append((source, source.relative_to(ROOT).as_posix(), 0o644))
    for rel_dir in WEB_ASSET_DIRS:
        asset_dir = ROOT / rel_dir
        if not asset_dir.exists():
            continue
        for source in sorted(path for path in asset_dir.rglob("*") if path.is_file()):
            entries.append((source, source.relative_to(ROOT).as_posix(), 0o644))
    write_zip(AGENT_ZIP, entries)
    return sha256(AGENT_ZIP)


def write_update_manifest(agent_hash: str) -> None:
    version = agent_version()
    manifest = {
        "version": version,
        "agent_url": f"{AGENT_URL}?v={version}",
        "agent_sha256": agent_hash,
        "published_at": int(time.time()),
        "notes": "更新本地助手和平台解析依赖，保留保存目录、配对状态和本地会话。",
    }
    UPDATE_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mac_installer(agent_hash: str) -> str:
    return textwrap.dedent(
        f"""\
        #!/bin/bash
        set -euo pipefail

        APP_NAME="K666VideoDownloaderAgent"
        BASE="$HOME/Library/Application Support/$APP_NAME"
        APP_DIR="$BASE/app"
        VENV="$BASE/.venv"
        LOG_DIR="$BASE/logs"
        TOOLS_DIR="$BASE/tools"
        FFMPEG_DIR="$TOOLS_DIR/ffmpeg"
        FFMPEG_BIN="$FFMPEG_DIR/bin"
        ZIP_PATH="$BASE/agent-source.zip"
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        BUNDLED_ZIP="$SCRIPT_DIR/_internal/agent-source.zip"
        if [ ! -f "$BUNDLED_ZIP" ]; then
          BUNDLED_ZIP="$SCRIPT_DIR/agent-source.zip"
        fi
        PLIST="$HOME/Library/LaunchAgents/xyz.k666.video-downloader-agent.plist"
        AGENT_URL="{AGENT_URL}"
        CONTROL_URL="{CONTROL_URL}"
        EXPECTED_SHA256="{agent_hash}"
        PYTHON_VERSION="3.12.10"
        PYTHON_MIN_VERSION="3.9"
        PYTHON_PKG_URL="https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg"
        FFMPEG_ZIP_URL="https://evermeet.cx/ffmpeg/getrelease/zip"
        FFPROBE_ZIP_URL="https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
        PIP_INDEX_URLS="${{PIP_INDEX_URLS:-${{PIP_INDEX_URL:-https://pypi.org/simple}} https://mirrors.aliyun.com/pypi/simple https://pypi.tuna.tsinghua.edu.cn/simple https://pypi.doubanio.com/simple}}"
        PLAYWRIGHT_DOWNLOAD_HOSTS="${{PLAYWRIGHT_DOWNLOAD_HOSTS:-${{PLAYWRIGHT_DOWNLOAD_HOST:-}} https://npmmirror.com/mirrors/playwright}}"

        info() {{
          printf "\\n%s\\n" "$1"
        }}

        python_ok() {{
          "$1" - <<'PY' >/dev/null 2>&1
import sys
import venv
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
        }}

        find_python() {{
          for candidate in \\
            "/opt/homebrew/bin/python3" \\
            "/usr/local/bin/python3" \\
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \\
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \\
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \\
            "/usr/bin/python3" \\
            "$(command -v python3 2>/dev/null || true)"
          do
            [ -z "$candidate" ] && continue
            [ ! -x "$candidate" ] && continue
            if python_ok "$candidate"; then
              printf "%s\\n" "$candidate"
              return 0
            fi
          done
          return 1
        }}

        install_python_dependency() {{
          info "未检测到可用的 Python 3.9+，正在尝试自动安装 Python..."
          mkdir -p "$BASE"
          if command -v brew >/dev/null 2>&1; then
            info "正在使用 Homebrew 安装 Python..."
            brew install python@3.12 || brew install python || true
            PYTHON_BIN="$(find_python || true)"
            if [ -n "$PYTHON_BIN" ]; then
              return 0
            fi
          fi

          PKG_PATH="$BASE/python-$PYTHON_VERSION-macos11.pkg"
          info "正在下载 Python 官方安装包..."
          if curl -L --fail "$PYTHON_PKG_URL" -o "$PKG_PATH"; then
            info "正在安装 Python。macOS 可能会要求输入电脑密码，这是系统安装器的正常提示。"
            if sudo installer -pkg "$PKG_PATH" -target /; then
              PYTHON_BIN="$(find_python || true)"
              if [ -n "$PYTHON_BIN" ]; then
                return 0
              fi
            fi
          fi
          return 1
        }}

        install_python_requirements() {{
          if [ ! -x "$VENV/bin/python" ]; then
            info "Python 虚拟环境未创建成功：$VENV/bin/python"
            return 1
          fi
          for index_url in $PIP_INDEX_URLS; do
            [ -z "$index_url" ] && continue
            info "正在安装 Python 依赖：$index_url"
            if "$VENV/bin/python" -m pip install --disable-pip-version-check -i "$index_url" -r "$APP_DIR/requirements-agent.txt"; then
              return 0
            fi
            info "该源安装失败，正在尝试下一个源..."
          done
          return 1
        }}

        create_virtual_environment() {{
          rm -rf "$VENV"
          if ! "$PYTHON_BIN" -m venv "$VENV"; then
            info "Python 虚拟环境创建失败，请重新安装 Python 后再试。"
            return 1
          fi
          if [ ! -x "$VENV/bin/python" ]; then
            info "Python 虚拟环境未创建成功：$VENV/bin/python"
            return 1
          fi
          if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
            "$VENV/bin/python" -m ensurepip --upgrade || true
          fi
          "$VENV/bin/python" -m pip --version >/dev/null 2>&1
        }}

        install_playwright_chromium() {{
          info "正在安装后台浏览器组件..."
          if "$VENV/bin/python" -m playwright install chromium; then
            return 0
          fi
          for host_url in $PLAYWRIGHT_DOWNLOAD_HOSTS; do
            [ -z "$host_url" ] && continue
            info "正在尝试浏览器组件镜像：$host_url"
            if PLAYWRIGHT_DOWNLOAD_HOST="$host_url" "$VENV/bin/python" -m playwright install chromium; then
              return 0
            fi
          done
          return 1
        }}

        local_ffmpeg_bin() {{
          if [ -x "$FFMPEG_BIN/ffmpeg" ] && [ -x "$FFMPEG_BIN/ffprobe" ]; then
            printf "%s\\n" "$FFMPEG_BIN"
            return 0
          fi
          return 1
        }}

        ffmpeg_available() {{
          if local_ffmpeg_bin >/dev/null 2>&1; then
            return 0
          fi
          command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1
        }}

        install_ffmpeg_dependency() {{
          if ffmpeg_available; then
            info "FFmpeg 已可用。"
            return 0
          fi
          info "未检测到 FFmpeg，正在尝试安装本地 FFmpeg 组件..."
          if command -v brew >/dev/null 2>&1; then
            info "正在使用 Homebrew 安装 FFmpeg..."
            brew install ffmpeg || true
            if ffmpeg_available; then
              return 0
            fi
          fi

          mkdir -p "$FFMPEG_BIN"
          FFMPEG_ZIP="$BASE/ffmpeg.zip"
          FFPROBE_ZIP="$BASE/ffprobe.zip"
          TMP_FFMPEG="$BASE/ffmpeg-unzip"
          rm -rf "$TMP_FFMPEG"
          mkdir -p "$TMP_FFMPEG"
          if curl -L --fail "$FFMPEG_ZIP_URL" -o "$FFMPEG_ZIP" && curl -L --fail "$FFPROBE_ZIP_URL" -o "$FFPROBE_ZIP"; then
            unzip -q "$FFMPEG_ZIP" -d "$TMP_FFMPEG"
            unzip -q "$FFPROBE_ZIP" -d "$TMP_FFMPEG"
            FFMPEG_FILE="$(find "$TMP_FFMPEG" -type f -name ffmpeg | head -n 1)"
            FFPROBE_FILE="$(find "$TMP_FFMPEG" -type f -name ffprobe | head -n 1)"
            if [ -n "$FFMPEG_FILE" ] && [ -n "$FFPROBE_FILE" ]; then
              cp "$FFMPEG_FILE" "$FFMPEG_BIN/ffmpeg"
              cp "$FFPROBE_FILE" "$FFMPEG_BIN/ffprobe"
              chmod +x "$FFMPEG_BIN/ffmpeg" "$FFMPEG_BIN/ffprobe"
            fi
            rm -rf "$TMP_FFMPEG"
          fi
          if ffmpeg_available; then
            info "FFmpeg 已准备好。"
            return 0
          fi
          info "FFmpeg 自动安装失败。图片和单文件视频仍可使用，部分高清合并可能失败。"
          return 1
        }}

        wait_for_agent() {{
          for attempt in $(seq 1 45); do
            if curl -fsS "http://127.0.0.1:17890/api/health" >/dev/null 2>&1 && curl -fsS "$CONTROL_URL" | grep -q "视频/图片下载工具"; then
              return 0
            fi
            sleep 1
          done
          return 1
        }}

        finish() {{
          printf "\\n安装窗口可以关闭了。\\n"
          printf "如果浏览器没有自动打开，请访问：%s\\n" "$CONTROL_URL"
          read -r -n 1 -s -p "按任意键关闭..." || true
          printf "\\n"
        }}
        trap finish EXIT

        info "正在安装本地下载助手..."
        if ! command -v curl >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1; then
          info "系统缺少 curl 或 unzip，无法继续安装。"
          exit 1
        fi
        mkdir -p "$BASE" "$LOG_DIR" "$TOOLS_DIR" "$HOME/Library/LaunchAgents"

        PYTHON_BIN="$(find_python || true)"
        if [ -z "$PYTHON_BIN" ]; then
          if ! install_python_dependency; then
            info "Python 3.9+ 无法自动安装。请先安装 Python 3.9 或更新版本后，再运行安装器。"
            info "安装器不会自动跳转网页；如需手动安装，请访问：https://www.python.org/downloads/macos/"
            exit 1
          fi
        fi
        PYTHON_BIN="$(find_python || true)"
        if [ -z "$PYTHON_BIN" ]; then
          info "Python 3.9+ 仍不可用。请手动安装 Python 后重试。"
          info "手动安装地址：https://www.python.org/downloads/macos/"
          exit 1
        fi

        mkdir -p "$BASE" "$APP_DIR" "$LOG_DIR" "$TOOLS_DIR" "$HOME/Library/LaunchAgents"
        if [ -f "$BUNDLED_ZIP" ]; then
          info "正在使用安装包内置组件..."
          cp "$BUNDLED_ZIP" "$ZIP_PATH"
        else
          info "正在下载本地组件..."
          curl -L --fail "$AGENT_URL" -o "$ZIP_PATH"
        fi
        ACTUAL_SHA256="$(shasum -a 256 "$ZIP_PATH" | awk '{{print $1}}')"
        if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
          info "安装包校验失败，请重新下载。"
          exit 1
        fi

        RUNTIME_BACKUP="$BASE/runtime-backup-$(date +%s)"
        if [ -d "$APP_DIR/.runtime" ]; then
          cp -R "$APP_DIR/.runtime" "$RUNTIME_BACKUP"
        fi
        rm -rf "$APP_DIR"
        mkdir -p "$APP_DIR"
        unzip -q "$ZIP_PATH" -d "$APP_DIR"
        if [ -d "$RUNTIME_BACKUP" ]; then
          rm -rf "$APP_DIR/.runtime"
          mv "$RUNTIME_BACKUP" "$APP_DIR/.runtime"
        fi

        info "正在准备 Python 环境..."
        if ! create_virtual_environment; then
          exit 1
        fi
        if ! install_python_requirements; then
          info "Python 依赖安装失败。请检查网络后重试；如果官方源不可用，安装器会自动尝试国内镜像。"
          exit 1
        fi
        if ! install_playwright_chromium; then
          info "后台浏览器组件下载失败。多数平台仍可解析；抖音等需要浏览器辅助的平台可能暂时不可用，可换网络后重新运行安装器。"
        fi

        install_ffmpeg_dependency || true

        TOKEN="$("$VENV/bin/python" - "$APP_DIR" <<'PY'
import json
import secrets
import sys
import time
from pathlib import Path

app_dir = Path(sys.argv[1])
token_file = app_dir / ".runtime" / "agent-token.json"
token_file.parent.mkdir(parents=True, exist_ok=True)
token = ""
if token_file.exists():
    try:
        token = json.loads(token_file.read_text(encoding="utf-8")).get("token", "")
    except Exception:
        token = ""
if not token:
    token = secrets.token_urlsafe(32)
    token_file.write_text(json.dumps({{"token": token, "created_at": int(time.time())}}, ensure_ascii=False, indent=2), encoding="utf-8")
print(token)
PY
        )"

        cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>xyz.k666.video-downloader-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV/bin/python</string>
    <string>-m</string>
    <string>local_agent.server</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$APP_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/agent.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/agent.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
  <key>PATH</key>
    <string>$FFMPEG_BIN:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
PLIST

        info "正在启动本地助手..."
        USER_ID="$(id -u)"
        launchctl bootout "gui/$USER_ID" "$PLIST" >/dev/null 2>&1 || true
        pkill -f "local_agent.server" >/dev/null 2>&1 || true
        launchctl enable "gui/$USER_ID/xyz.k666.video-downloader-agent" >/dev/null 2>&1 || true
        launchctl bootstrap "gui/$USER_ID" "$PLIST"
        launchctl enable "gui/$USER_ID/xyz.k666.video-downloader-agent" >/dev/null 2>&1 || true

        if wait_for_agent; then
          info "本地助手已启动。正在打开本机控制台..."
        else
          info "本地助手启动较慢，请稍后打开本机控制台并点击重新检测。"
        fi
        open "$CONTROL_URL?install=$(date +%s)#agentToken=$TOKEN"
        """
    )

def windows_ps1(agent_hash: str) -> str:
    return textwrap.dedent(
        f"""\
        $ErrorActionPreference = "Stop"

        $Base = Join-Path $env:LOCALAPPDATA "K666VideoDownloaderAgent"
        $AppDir = Join-Path $Base "app"
        $Venv = Join-Path $Base ".venv"
        $Logs = Join-Path $Base "logs"
        $ToolsDir = Join-Path $Base "tools"
        $FfmpegDir = Join-Path $ToolsDir "ffmpeg"
        $ZipPath = Join-Path $Base "agent-source.zip"
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $BundledZip = Join-Path $ScriptDir "agent-source.zip"
        if (-not (Test-Path $BundledZip)) {{
          $BundledZip = Join-Path (Split-Path -Parent $ScriptDir) "_internal\\agent-source.zip"
        }}
        $RunScript = Join-Path $Base "run-agent.ps1"
        $AgentUrl = "{AGENT_URL}"
        $ControlUrl = "{CONTROL_URL}"
        $ExpectedSha256 = "{agent_hash}"
        $PythonVersion = "3.12.10"
        $PythonInstallerUrls = @{{
          "AMD64" = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
          "ARM64" = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-arm64.exe"
          "X86" = "https://www.python.org/ftp/python/3.12.10/python-3.12.10.exe"
        }}
        $FfmpegZipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        if ($env:PIP_INDEX_URLS) {{
          $PipIndexUrls = $env:PIP_INDEX_URLS -split "\\s+" | Where-Object {{ $_ }}
        }} elseif ($env:PIP_INDEX_URL) {{
          $PipIndexUrls = @($env:PIP_INDEX_URL, "https://mirrors.aliyun.com/pypi/simple", "https://pypi.tuna.tsinghua.edu.cn/simple", "https://pypi.doubanio.com/simple")
        }} else {{
          $PipIndexUrls = @("https://pypi.org/simple", "https://mirrors.aliyun.com/pypi/simple", "https://pypi.tuna.tsinghua.edu.cn/simple", "https://pypi.doubanio.com/simple")
        }}
        if ($env:PLAYWRIGHT_DOWNLOAD_HOSTS) {{
          $PlaywrightDownloadHosts = $env:PLAYWRIGHT_DOWNLOAD_HOSTS -split "\\s+" | Where-Object {{ $_ }}
        }} elseif ($env:PLAYWRIGHT_DOWNLOAD_HOST) {{
          $PlaywrightDownloadHosts = @($env:PLAYWRIGHT_DOWNLOAD_HOST, "https://npmmirror.com/mirrors/playwright")
        }} else {{
          $PlaywrightDownloadHosts = @("https://npmmirror.com/mirrors/playwright")
        }}
        $StartupRegPath = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        $StartupRegName = "K666 Video Downloader Agent"

        function Info($Message) {{
          Write-Host ""
          Write-Host $Message
        }}

        function Open-ControlPage([string]$Url) {{
          try {{
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "`"`"", "`"$Url`"" -WindowStyle Hidden | Out-Null
            return $true
          }} catch {{
            Info "Could not open the control page automatically. Please open this URL manually:"
            Info $Url
            return $false
          }}
        }}

        function Get-WindowsArchitecture {{
          $Arch = $env:PROCESSOR_ARCHITEW6432
          if ([string]::IsNullOrWhiteSpace($Arch)) {{
            $Arch = $env:PROCESSOR_ARCHITECTURE
          }}
          if ($Arch -eq "ARM64") {{ return "ARM64" }}
          if ([Environment]::Is64BitOperatingSystem) {{ return "AMD64" }}
          return "X86"
        }}

        function Refresh-ProcessPath {{
          $MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
          $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
          $KnownPythonPaths = @(
            "$env:LOCALAPPDATA\\Programs\\Python\\Python314",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python314\\Scripts",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python313",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python313\\Scripts",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python312",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\Scripts",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python311",
            "$env:LOCALAPPDATA\\Programs\\Python\\Python311\\Scripts",
            "$env:ProgramFiles\\Python314",
            "$env:ProgramFiles\\Python314\\Scripts",
            "$env:ProgramFiles\\Python313",
            "$env:ProgramFiles\\Python313\\Scripts",
            "$env:ProgramFiles\\Python312",
            "$env:ProgramFiles\\Python312\\Scripts",
            "$env:ProgramFiles\\Python311",
            "$env:ProgramFiles\\Python311\\Scripts"
          ) | Where-Object {{ $_ -and (Test-Path $_) }}
          $PathParts = @($MachinePath, $UserPath, ($KnownPythonPaths -join ";"), $env:PATH) | Where-Object {{ $_ }}
          $env:PATH = ($PathParts -join ";")
        }}

        function Download-File([string]$Url, [string]$OutFile) {{
          [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
          Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
        }}

        function Invoke-PythonCandidate([string[]]$Candidate, [string[]]$ArgsList, [switch]$Quiet) {{
          if (-not $Candidate -or $Candidate.Length -lt 1) {{ return $false }}
          $Exe = $Candidate[0]
          $RunArgs = @()
          if ($Candidate.Length -gt 1) {{
            $RunArgs += $Candidate[1..($Candidate.Length - 1)]
          }}
          $RunArgs += $ArgsList
          try {{
            $CommandOutput = & $Exe @RunArgs 2>&1
            $ExitCode = $LASTEXITCODE
          }} catch {{
            if (-not $Quiet) {{ Write-Host $_ }}
            return $false
          }}
          if (-not $Quiet -and $CommandOutput) {{
            $CommandOutput | ForEach-Object {{ Write-Host $_ }}
          }}
          return ($ExitCode -eq 0)
        }}

        function Test-PythonCandidate([string[]]$Candidate) {{
          if (-not $Candidate -or $Candidate.Length -lt 1) {{ return $false }}
          if (-not (Test-Path $Candidate[0]) -and -not (Get-Command $Candidate[0] -ErrorAction SilentlyContinue)) {{ return $false }}
          return (Invoke-PythonCandidate -Candidate $Candidate -ArgsList @("-c", "import sys, venv; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)") -Quiet)
        }}

        function Find-Python {{
          Refresh-ProcessPath
          $Candidates = @(
            ,@("py", "-3.12")
            ,@("py", "-3.11")
            ,@("py", "-3")
            ,@("python")
            ,@("python3")
            ,@("$env:LOCALAPPDATA\\Programs\\Python\\Python314\\python.exe")
            ,@("$env:LOCALAPPDATA\\Programs\\Python\\Python313\\python.exe")
            ,@("$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe")
            ,@("$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe")
            ,@("$env:ProgramFiles\\Python314\\python.exe")
            ,@("$env:ProgramFiles\\Python313\\python.exe")
            ,@("$env:ProgramFiles\\Python312\\python.exe")
            ,@("$env:ProgramFiles\\Python311\\python.exe")
          )
          foreach ($Candidate in $Candidates) {{
            if (Test-PythonCandidate -Candidate $Candidate) {{
              return $Candidate
            }}
          }}
          return $null
        }}

        function Install-PythonDependency {{
          Info "Python 3.11+ was not found. Installing Python first..."
          if (Get-Command winget -ErrorAction SilentlyContinue) {{
            Info "Trying Windows Package Manager: Python 3.12"
            winget install -e --id Python.Python.3.12 --silent --scope user --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {{
              winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
            }}
            $script:Python = @(Find-Python)
            if ($script:Python) {{ return $true }}
          }}

          $Arch = Get-WindowsArchitecture
          $InstallerUrl = $PythonInstallerUrls[$Arch]
          if (-not $InstallerUrl) {{ $InstallerUrl = $PythonInstallerUrls["AMD64"] }}
          $InstallerPath = Join-Path $Base ("python-" + $PythonVersion + "-" + $Arch + ".exe")
          try {{
            Info "Downloading Python installer..."
            Download-File $InstallerUrl $InstallerPath
            Info "Installing Python. This may take a few minutes..."
            $InstallArgs = "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_tcltk=0 Include_test=0 SimpleInstall=1"
            $Process = Start-Process -FilePath $InstallerPath -ArgumentList $InstallArgs -Wait -PassThru
            if ($Process.ExitCode -ne 0) {{
              Info "Python installer exited with code $($Process.ExitCode)."
            }}
          }} catch {{
            Info "Automatic Python download or installation failed."
            Write-Host $_
          }}
          $script:Python = @(Find-Python)
          return [bool]$script:Python
        }}

        function Invoke-BasePython([string[]]$ArgsList) {{
          return (Invoke-PythonCandidate -Candidate $Python -ArgsList $ArgsList)
        }}

        function New-VirtualEnvironment {{
          if (Test-Path $Venv) {{
            Remove-Item $Venv -Recurse -Force -ErrorAction SilentlyContinue
          }}
          if (-not (Invoke-BasePython -ArgsList @("-m", "venv", $Venv))) {{
            Info "Could not create the Python virtual environment. Please repair or reinstall Python 3.11+ and run this installer again."
            return $false
          }}
          $script:VenvPython = Join-Path $Venv "Scripts\\python.exe"
          $script:VenvPythonw = Join-Path $Venv "Scripts\\pythonw.exe"
          if (-not (Test-Path $script:VenvPython)) {{
            Info "The virtual environment was not created correctly: $script:VenvPython"
            Info "Please repair or reinstall Python 3.11+ and run this installer again."
            return $false
          }}
          & $script:VenvPython -m pip --version *> $null
          if ($LASTEXITCODE -ne 0) {{
            & $script:VenvPython -m ensurepip --upgrade
            & $script:VenvPython -m pip --version *> $null
            if ($LASTEXITCODE -ne 0) {{
              Info "pip is not available in the Python virtual environment. Please repair Python and run this installer again."
              return $false
            }}
          }}
          return $true
        }}

        function Install-PythonRequirements {{
          $Requirements = Join-Path $AppDir "requirements-agent.txt"
          if (-not (Test-Path $VenvPython)) {{
            Info "The virtual environment Python file is missing: $VenvPython"
            return $false
          }}
          foreach ($IndexUrl in $PipIndexUrls) {{
            if ([string]::IsNullOrWhiteSpace($IndexUrl)) {{ continue }}
            Info "Installing Python dependencies from: $IndexUrl"
            & $VenvPython -m pip install --disable-pip-version-check -i $IndexUrl -r $Requirements
            if ($LASTEXITCODE -eq 0) {{ return $true }}
            Info "This source failed. Trying the next source..."
          }}
          return $false
        }}

        function Install-PlaywrightChromium {{
          if (-not (Test-Path $VenvPython)) {{
            Info "The virtual environment Python file is missing: $VenvPython"
            return $false
          }}
          Info "Installing browser component..."
          & $VenvPython -m playwright install chromium
          if ($LASTEXITCODE -eq 0) {{ return $true }}
          foreach ($HostUrl in $PlaywrightDownloadHosts) {{
            if ([string]::IsNullOrWhiteSpace($HostUrl)) {{ continue }}
            Info "Trying browser component mirror: $HostUrl"
            $OldHost = $env:PLAYWRIGHT_DOWNLOAD_HOST
            $env:PLAYWRIGHT_DOWNLOAD_HOST = $HostUrl
            & $VenvPython -m playwright install chromium
            if ($OldHost) {{
              $env:PLAYWRIGHT_DOWNLOAD_HOST = $OldHost
            }} else {{
              Remove-Item Env:PLAYWRIGHT_DOWNLOAD_HOST -ErrorAction SilentlyContinue
            }}
            if ($LASTEXITCODE -eq 0) {{ return $true }}
          }}
          return $false
        }}

        function Get-LocalFfmpegBin {{
          $Candidate = Join-Path $FfmpegDir "bin"
          if ((Test-Path (Join-Path $Candidate "ffmpeg.exe")) -and (Test-Path (Join-Path $Candidate "ffprobe.exe"))) {{
            return $Candidate
          }}
          return ""
        }}

        function Find-FFmpeg {{
          $LocalBin = Get-LocalFfmpegBin
          if ($LocalBin) {{ return $LocalBin }}
          if ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) {{
            return "system"
          }}
          return ""
        }}

        function Install-FFmpegDependency {{
          $Existing = Find-FFmpeg
          if ($Existing) {{
            Info "FFmpeg is available."
            return $true
          }}

          Info "FFmpeg was not found. Installing FFmpeg for video merging..."
          if (Get-Command winget -ErrorAction SilentlyContinue) {{
            Info "Trying Windows Package Manager: FFmpeg"
            winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
            Refresh-ProcessPath
            $Existing = Find-FFmpeg
            if ($Existing) {{ return $true }}
          }}

          try {{
            $FfmpegZip = Join-Path $Base "ffmpeg-release-essentials.zip"
            $ExtractDir = Join-Path $ToolsDir "ffmpeg-extract"
            Info "Downloading FFmpeg local package..."
            New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
            Download-File $FfmpegZipUrl $FfmpegZip
            if (Test-Path $ExtractDir) {{ Remove-Item $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue }}
            New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
            Expand-Archive -Path $FfmpegZip -DestinationPath $ExtractDir -Force
            $FfmpegExe = Get-ChildItem -Path $ExtractDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            if ($FfmpegExe) {{
              $PackageRoot = Split-Path -Parent (Split-Path -Parent $FfmpegExe.FullName)
              if (Test-Path $FfmpegDir) {{ Remove-Item $FfmpegDir -Recurse -Force -ErrorAction SilentlyContinue }}
              Move-Item $PackageRoot $FfmpegDir -Force
              Remove-Item $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
            }}
          }} catch {{
            Info "Automatic FFmpeg installation failed. Images and single-file videos can still work."
            Write-Host $_
          }}
          $Existing = Find-FFmpeg
          if ($Existing) {{
            Info "FFmpeg is ready."
            return $true
          }}
          Info "FFmpeg is still unavailable. Some HD video merges may fail until FFmpeg is installed."
          return $false
        }}

        function Wait-AgentReady {{
          for ($Index = 0; $Index -lt 45; $Index++) {{
            try {{
              Invoke-RestMethod -Uri "http://127.0.0.1:17890/api/health" -TimeoutSec 2 | Out-Null
              $HomePage = Invoke-WebRequest -Uri $ControlUrl -UseBasicParsing -TimeoutSec 2
              if ($HomePage.Content -like "*sourceInput*" -or $HomePage.Content -like "*downloadButton*") {{
                return $true
              }}
            }} catch {{}}
            Start-Sleep -Seconds 1
          }}
          return $false
        }}

        Info "Installing local downloader agent..."
        $Python = @(Find-Python)
        if (-not $Python) {{
          if (-not (Install-PythonDependency)) {{
            Info "Python 3.11+ could not be installed automatically."
            Info "Please install Python 3.11 or newer, then run this installer again."
            Start-Process "https://www.python.org/downloads/windows/"
            Read-Host "Press Enter to close"
            exit 1
          }}
        }}
        if (-not $Python) {{
          Info "Python 3 was not found. Please install Python 3.11 or newer, then run this installer again."
          Start-Process "https://www.python.org/downloads/windows/"
          Read-Host "Press Enter to close"
          exit 1
        }}

        New-Item -ItemType Directory -Force -Path $Base, $AppDir, $Logs | Out-Null
        if (Test-Path $BundledZip) {{
          Info "Using bundled agent files..."
          Copy-Item $BundledZip $ZipPath -Force
        }} else {{
          Info "Downloading agent files..."
          Invoke-WebRequest -Uri $AgentUrl -OutFile $ZipPath
        }}
        $ActualSha256 = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash.ToLowerInvariant()
        if ($ActualSha256 -ne $ExpectedSha256) {{
          Info "Package verification failed. Please download the installer again."
          Read-Host "Press Enter to close"
          exit 1
        }}

        $RuntimeBackup = Join-Path $Base ("runtime-backup-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
        $ExistingRuntime = Join-Path $AppDir ".runtime"
        if (Test-Path $ExistingRuntime) {{
          Copy-Item $ExistingRuntime $RuntimeBackup -Recurse -Force
        }}
        if (Test-Path $AppDir) {{ Remove-Item $AppDir -Recurse -Force }}
        New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
        Expand-Archive -Path $ZipPath -DestinationPath $AppDir -Force
        if (Test-Path $RuntimeBackup) {{
          $NewRuntime = Join-Path $AppDir ".runtime"
          if (Test-Path $NewRuntime) {{ Remove-Item $NewRuntime -Recurse -Force }}
          Move-Item $RuntimeBackup $NewRuntime -Force
        }}

        Info "Preparing Python environment..."
        if (-not (New-VirtualEnvironment)) {{
          Read-Host "Press Enter to close"
          exit 1
        }}
        if (-not (Install-PythonRequirements)) {{
          Info "Python dependency installation failed. Please check the network and try again."
          Read-Host "Press Enter to close"
          exit 1
        }}
        if (-not (Install-PlaywrightChromium)) {{
          Info "Browser component installation failed. Many platforms still work; Douyin-like sites may need a later retry."
        }}

        Install-FFmpegDependency | Out-Null

        $RuntimeDir = Join-Path $AppDir ".runtime"
        $TokenFile = Join-Path $RuntimeDir "agent-token.json"
        New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
        $Token = ""
        if (Test-Path $TokenFile) {{
          try {{ $Token = (Get-Content $TokenFile -Raw | ConvertFrom-Json).token }} catch {{ $Token = "" }}
        }}
        if (-not $Token) {{
          $Bytes = New-Object byte[] 32
          [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Bytes)
          $Token = [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
          @{{ token = $Token; created_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }} | ConvertTo-Json | Set-Content -Encoding UTF8 $TokenFile
        }}

        $RunScriptFfmpegLine = ""
        $LocalFfmpegBin = Get-LocalFfmpegBin
        if ($LocalFfmpegBin) {{
          $RunScriptFfmpegLine = '$env:PATH = "' + $LocalFfmpegBin + ';$env:PATH"'
        }}
        @"
        Set-Location "$AppDir"
        $RunScriptFfmpegLine
        & "$VenvPython" -m local_agent.server *> "$Logs\\agent.log"
        "@ | Set-Content -Encoding UTF8 $RunScript

        Info "Setting startup entry..."
        Get-Process | Where-Object {{ $_.Path -eq $VenvPython -or $_.Path -eq $VenvPythonw }} | Stop-Process -Force -ErrorAction SilentlyContinue
        $RunCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunScript`""
        try {{
          New-Item -Path $StartupRegPath -Force | Out-Null
          New-ItemProperty -Path $StartupRegPath -Name $StartupRegName -PropertyType String -Value $RunCommand -Force | Out-Null
          Info "Startup entry was added."
        }} catch {{
          Info "Startup entry could not be added. The agent will still start now."
        }}
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunScript`"" -WorkingDirectory $AppDir

        Info "Starting local agent..."
        if (Wait-AgentReady) {{
          Info "Local agent is ready. Opening control page..."
        }} else {{
          Info "Local agent is starting slowly. If the page is not connected yet, wait a few seconds and retry."
        }}
        $InstallTs = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $ControlPageUrl = "{{0}}?install={{1}}#agentToken={{2}}" -f $ControlUrl, $InstallTs, $Token
        Open-ControlPage $ControlPageUrl | Out-Null
        Read-Host "Install finished. Press Enter to close"
        """
    )


def windows_launcher_bat(script_name: str, title: str, action_name: str) -> str:
    return textwrap.dedent(
        f"""\
        @echo off
        setlocal EnableExtensions
        chcp 65001 >nul 2>nul
        title K666 Video Downloader Agent - {title}

        set "INSTALL_DIR=%~dp0"
        pushd "%INSTALL_DIR%" >nul 2>nul
        if errorlevel 1 (
          echo Cannot enter installer folder: %INSTALL_DIR%
          echo.
          echo If you are using Parallels, C:\\Mac\\Home\\Desktop is the Mac shared desktop.
          echo Please copy this extracted folder to C:\\Users\\your-Windows-name\\Desktop and run this script again.
          echo.
          pause
          exit /b 1
        )

        set "SCRIPT=%CD%\\_internal\\{script_name}"
        if not exist "%SCRIPT%" (
          echo Missing {action_name} component: %SCRIPT%
          echo.
          echo Please right-click the downloaded zip file and choose Extract All first.
          echo Then open the extracted folder and double-click this script again.
          echo Do not run this script directly inside the zip preview window.
          echo.
          pause
          exit /b 1
        )

        echo Starting {action_name}...
        echo.
        powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
        set "EXIT_CODE=%ERRORLEVEL%"

        echo.
        if not "%EXIT_CODE%"=="0" (
          echo {action_name} did not finish. Error code: %EXIT_CODE%
          echo Please take a screenshot of the messages above.
        ) else (
          echo {action_name} script finished.
        )
        echo.
        pause
        popd >nul 2>nul
        exit /b %EXIT_CODE%
        """
    )


def write_windows_text(path: Path, content: str) -> None:
    path.write_text(content.replace("\n", "\r\n"), encoding="utf-8")


def write_windows_ps1(path: Path, content: str) -> None:
    path.write_text(content.replace("\n", "\r\n"), encoding="utf-8-sig")


def mac_cleaner() -> str:
    return textwrap.dedent(
        """\
        #!/bin/bash
        set -u

        APP_NAME="K666VideoDownloaderAgent"
        BASE="$HOME/Library/Application Support/$APP_NAME"
        PLIST="$HOME/Library/LaunchAgents/xyz.k666.video-downloader-agent.plist"
        CONTROL_URL="http://127.0.0.1:17890/"

        info() {
          printf "\\n%s\\n" "$1"
        }

        finish() {
          printf "\\n卸载窗口可以关闭了。\\n"
          read -r -n 1 -s -p "按任意键关闭..." || true
          printf "\\n"
        }
        trap finish EXIT

        info "正在卸载本地下载助手..."
        info "这只会删除本地助手程序、启动项、token、设置和临时缓存，不会删除你已经下载的视频或图片文件。"

        USER_ID="$(id -u)"
        launchctl bootout "gui/$USER_ID" "$PLIST" >/dev/null 2>&1 || true
        launchctl disable "gui/$USER_ID/xyz.k666.video-downloader-agent" >/dev/null 2>&1 || true
        pkill -f "local_agent.server" >/dev/null 2>&1 || true
        rm -f "$PLIST"
        rm -rf "$BASE"

        if curl -fsS "$CONTROL_URL/api/health" >/dev/null 2>&1; then
          info "本地助手仍在运行，请重启电脑后再试。"
        else
          info "本地助手已卸载。需要再次使用时，重新运行安装脚本即可。"
        fi
        """
    )


def mac_updater() -> str:
    return textwrap.dedent(
        f"""\
        #!/bin/bash
        set -euo pipefail

        APP_NAME="K666VideoDownloaderAgent"
        BASE="$HOME/Library/Application Support/$APP_NAME"
        APP_DIR="$BASE/app"
        VENV="$BASE/.venv"
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        UPDATER="$SCRIPT_DIR/_internal/updater.py"
        if [ ! -f "$UPDATER" ]; then
          UPDATER="$APP_DIR/local_agent/updater.py"
        fi
        CONTROL_URL="{CONTROL_URL}"
        MANIFEST_URL="{UPDATE_MANIFEST_URL}"

        info() {{
          printf "\\n%s\\n" "$1"
        }}

        finish() {{
          printf "\\n更新窗口可以关闭了。\\n"
          printf "如果浏览器没有自动打开，请访问：%s\\n" "$CONTROL_URL"
          read -r -n 1 -s -p "按任意键关闭..." || true
          printf "\\n"
        }}
        trap finish EXIT

        info "正在更新本地下载助手..."
        if [ ! -x "$VENV/bin/python" ] || [ ! -d "$APP_DIR" ]; then
          info "未检测到已安装的本地助手，请先运行 01-INSTALL。"
          exit 1
        fi
        if [ ! -f "$UPDATER" ]; then
          info "更新组件缺失，请重新下载安装包。"
          exit 1
        fi

        "$VENV/bin/python" "$UPDATER" --app-dir "$APP_DIR" --manifest-url "$MANIFEST_URL" --restart
        info "更新命令已完成，正在打开本机控制台..."
        open "$CONTROL_URL?updated=$(date +%s)"
        """
    )


def windows_cleaner_ps1() -> str:
    return textwrap.dedent(
        """\
        $ErrorActionPreference = "Continue"

        $Base = Join-Path $env:LOCALAPPDATA "K666VideoDownloaderAgent"
        $TaskName = "K666 Video Downloader Agent"
        $StartupRegPath = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        $StartupRegName = "K666 Video Downloader Agent"

        function Info($Message) {
          Write-Host ""
          Write-Host $Message
        }

        Info "Uninstalling local downloader agent..."
        Info "This removes the local agent, startup task, token, settings and cache. Downloaded files will not be deleted."

        try {
          Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        } catch {}
        try {
          Remove-ItemProperty -Path $StartupRegPath -Name $StartupRegName -ErrorAction SilentlyContinue
        } catch {}

        try {
          Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -like "*local_agent.server*" -or $_.CommandLine -like "*run-agent.ps1*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        } catch {}

        if (Test-Path $Base) {
          Remove-Item $Base -Recurse -Force -ErrorAction SilentlyContinue
        }

        try {
          Invoke-RestMethod -Uri "http://127.0.0.1:17890/api/health" -TimeoutSec 2 | Out-Null
          Info "The local agent is still running. Please restart Windows and try again."
        } catch {
          Info "The local agent has been uninstalled. Run 01-INSTALL again when needed."
        }

        Read-Host "Press Enter to close"
        """
    )


def windows_cleaner_bat() -> str:
    return windows_launcher_bat("uninstall.ps1", "Uninstall", "Uninstall")


def windows_updater_ps1() -> str:
    return textwrap.dedent(
        f"""\
        $ErrorActionPreference = "Stop"

        $Base = Join-Path $env:LOCALAPPDATA "K666VideoDownloaderAgent"
        $AppDir = Join-Path $Base "app"
        $VenvPython = Join-Path $Base ".venv\\Scripts\\python.exe"
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $Updater = Join-Path $ScriptDir "updater.py"
        if (-not (Test-Path $Updater)) {{
          $Updater = Join-Path $AppDir "local_agent\\updater.py"
        }}
        $ControlUrl = "{CONTROL_URL}"
        $ManifestUrl = "{UPDATE_MANIFEST_URL}"

        function Info($Message) {{
          Write-Host ""
          Write-Host $Message
        }}

        function Open-ControlPage([string]$Url) {{
          try {{
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "`"`"", "`"$Url`"" -WindowStyle Hidden | Out-Null
            return $true
          }} catch {{
            Info "Could not open the control page automatically. Please open this URL manually:"
            Info $Url
            return $false
          }}
        }}

        Info "Updating local downloader agent..."
        if (-not (Test-Path $VenvPython) -or -not (Test-Path $AppDir)) {{
          Info "No installed local agent was found. Please run 01-INSTALL first."
          Read-Host "Press Enter to close"
          exit 1
        }}
        if (-not (Test-Path $Updater)) {{
          Info "Update component is missing. Please download the installer again."
          Read-Host "Press Enter to close"
          exit 1
        }}

        & $VenvPython $Updater --app-dir $AppDir --manifest-url $ManifestUrl --restart
        Info "Update command finished. Opening control page..."
        $UpdatedTs = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $ControlPageUrl = "{{0}}?updated={{1}}" -f $ControlUrl, $UpdatedTs
        Open-ControlPage $ControlPageUrl | Out-Null
        Read-Host "Update finished. Press Enter to close"
        """
    )


def windows_updater_bat() -> str:
    return windows_launcher_bat("update.ps1", "Update", "Update")


def build_installers(agent_hash: str) -> None:
    tmp = ROOT / ".runtime" / "installer-build"
    tmp.mkdir(parents=True, exist_ok=True)

    mac_script = tmp / "01-INSTALL.command"
    mac_clean_script = tmp / "02-UNINSTALL.command"
    mac_update_script = tmp / "03-UPDATE.command"
    mac_script.write_text(mac_installer(agent_hash), encoding="utf-8")
    mac_clean_script.write_text(mac_cleaner(), encoding="utf-8")
    mac_update_script.write_text(mac_updater(), encoding="utf-8")
    os.chmod(mac_script, 0o755)
    os.chmod(mac_clean_script, 0o755)
    os.chmod(mac_update_script, 0o755)
    mac_root = "K666VideoDownloaderAgent-macOS"
    write_zip(
        MAC_INSTALLER_ZIP,
        [
            (mac_script, f"{mac_root}/{mac_script.name}", 0o755),
            (mac_clean_script, f"{mac_root}/{mac_clean_script.name}", 0o755),
            (mac_update_script, f"{mac_root}/{mac_update_script.name}", 0o755),
            (ROOT / "local_agent" / "updater.py", f"{mac_root}/_internal/updater.py", 0o644),
            (AGENT_ZIP, f"{mac_root}/_internal/{AGENT_ZIP.name}", 0o644),
        ],
    )

    ps1 = tmp / "install.ps1"
    bat = tmp / "01-INSTALL.bat"
    cleaner_ps1 = tmp / "uninstall.ps1"
    cleaner_bat = tmp / "02-UNINSTALL.bat"
    updater_ps1 = tmp / "update.ps1"
    updater_bat = tmp / "03-UPDATE.bat"
    write_windows_ps1(ps1, windows_ps1(agent_hash))
    write_windows_text(bat, windows_launcher_bat("install.ps1", "Install", "Install"))
    write_windows_ps1(cleaner_ps1, windows_cleaner_ps1())
    write_windows_text(cleaner_bat, windows_cleaner_bat())
    write_windows_ps1(updater_ps1, windows_updater_ps1())
    write_windows_text(updater_bat, windows_updater_bat())
    windows_root = "K666VideoDownloaderAgent-Windows"
    write_zip(
        WINDOWS_INSTALLER_ZIP,
        [
            (bat, f"{windows_root}/{bat.name}", 0o644),
            (cleaner_bat, f"{windows_root}/{cleaner_bat.name}", 0o644),
            (updater_bat, f"{windows_root}/{updater_bat.name}", 0o644),
            (ps1, f"{windows_root}/_internal/{ps1.name}", 0o644),
            (cleaner_ps1, f"{windows_root}/_internal/{cleaner_ps1.name}", 0o644),
            (updater_ps1, f"{windows_root}/_internal/{updater_ps1.name}", 0o644),
            (ROOT / "local_agent" / "updater.py", f"{windows_root}/_internal/updater.py", 0o644),
            (AGENT_ZIP, f"{windows_root}/_internal/{AGENT_ZIP.name}", 0o644),
        ],
    )


def main() -> None:
    agent_hash = build_agent_source()
    write_update_manifest(agent_hash)
    build_installers(agent_hash)
    print(f"agent_source={AGENT_ZIP} sha256={agent_hash}")
    print(f"update_manifest={UPDATE_MANIFEST} version={agent_version()}")
    print(f"mac_installer={MAC_INSTALLER_ZIP} sha256={sha256(MAC_INSTALLER_ZIP)}")
    print(f"windows_installer={WINDOWS_INSTALLER_ZIP} sha256={sha256(WINDOWS_INSTALLER_ZIP)}")


if __name__ == "__main__":
    main()
