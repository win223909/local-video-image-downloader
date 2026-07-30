from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def find_executable(name: str) -> str | None:
    """Return an executable path if it is available on PATH."""
    return shutil.which(name)


def ffmpeg_status() -> dict[str, str | bool | None]:
    ffmpeg_path = find_executable("ffmpeg")
    ffprobe_path = find_executable("ffprobe")
    return {
        "ffmpeg": ffmpeg_path,
        "ffprobe": ffprobe_path,
        "available": bool(ffmpeg_path and ffprobe_path),
    }


def ensure_writable_directory(path: str | Path) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    probe = directory / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise OSError(f"目录不可写：{directory}") from exc

    return directory


def choose_download_folder(initial_dir: str | Path | None = None) -> Path | None:
    system = platform.system()
    start_dir = Path(initial_dir).expanduser() if initial_dir else Path.home()
    if not start_dir.exists():
        start_dir = Path.home()

    if system == "Darwin":
        return _choose_folder_macos(start_dir)
    if system == "Windows":
        return _choose_folder_windows(start_dir)
    return _choose_folder_linux(start_dir)


def choose_video_file(initial_dir: str | Path | None = None) -> Path | None:
    system = platform.system()
    start_dir = Path(initial_dir).expanduser() if initial_dir else Path.home()
    if not start_dir.exists():
        start_dir = Path.home()

    if system == "Darwin":
        return _choose_video_file_macos(start_dir)
    if system == "Windows":
        return _choose_video_file_windows(start_dir)
    return _choose_video_file_linux(start_dir)


def _choose_folder_macos(start_dir: Path) -> Path | None:
    script = f'''
set startPath to "{_applescript_escape(str(start_dir.resolve()))}"
set startFolder to missing value
try
  set startFolder to POSIX file startPath as alias
end try
if startFolder is missing value then
  set chosenFolder to choose folder with prompt "选择保存文件夹"
else
  set chosenFolder to choose folder with prompt "选择保存文件夹" default location startFolder
end if
POSIX path of chosenFolder
'''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError("无法打开文件夹选择窗口，请手动输入保存目录。") from exc
    if result.returncode != 0:
        if "User canceled" in result.stderr or "用户已取消" in result.stderr:
            return None
        raise OSError("无法打开文件夹选择窗口，请手动输入保存目录。")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _choose_video_file_macos(start_dir: Path) -> Path | None:
    script = f'''
set startPath to "{_applescript_escape(str(start_dir.resolve()))}"
set startFolder to missing value
try
  set startFolder to POSIX file startPath as alias
end try
try
  if startFolder is missing value then
    set chosenFile to choose file with prompt "选择要转换的视频文件"
  else
    set chosenFile to choose file with prompt "选择要转换的视频文件" default location startFolder
  end if
on error number -128
  return ""
end try
POSIX path of chosenFile
'''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError("无法打开视频选择窗口，请稍后再试。") from exc
    if result.returncode != 0:
        raise OSError("无法打开视频选择窗口，请稍后再试。")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _choose_folder_windows(start_dir: Path) -> Path | None:
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "选择保存文件夹"
$dialog.SelectedPath = '{_powershell_single_quote(str(start_dir.resolve()))}'
$dialog.ShowNewFolderButton = $true
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.SelectedPath
  exit 0
}}
exit 2
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError("无法打开文件夹选择窗口，请手动输入保存目录。") from exc
    if result.returncode == 2:
        return None
    if result.returncode != 0:
        raise OSError("无法打开文件夹选择窗口，请手动输入保存目录。")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _choose_video_file_windows(start_dir: Path) -> Path | None:
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "选择要转换的视频文件"
$dialog.InitialDirectory = '{_powershell_single_quote(str(start_dir.resolve()))}'
$dialog.Filter = "视频文件|*.mp4;*.m4v;*.mov;*.mkv;*.webm|所有文件|*.*"
$dialog.Multiselect = $false
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.FileName
  exit 0
}}
exit 2
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OSError("无法打开视频选择窗口，请稍后再试。") from exc
    if result.returncode == 2:
        return None
    if result.returncode != 0:
        raise OSError("无法打开视频选择窗口，请稍后再试。")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _choose_folder_linux(start_dir: Path) -> Path | None:
    commands = [
        ["zenity", "--file-selection", "--directory", f"--filename={start_dir.resolve()}"],
        ["kdialog", "--getexistingdirectory", str(start_dir.resolve())],
    ]
    for command in commands:
        if not shutil.which(command[0]):
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise OSError("无法打开文件夹选择窗口，请手动输入保存目录。") from exc
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
        if result.returncode in {1, 5}:
            return None
    raise OSError("当前系统缺少文件夹选择组件，请手动输入保存目录。")


def _choose_video_file_linux(start_dir: Path) -> Path | None:
    command = [
        "zenity",
        "--file-selection",
        f"--filename={start_dir.resolve()}/",
        "--file-filter=视频文件 | *.mp4 *.m4v *.mov *.mkv *.webm",
        "--file-filter=所有文件 | *",
    ]
    if not shutil.which(command[0]):
        raise OSError("当前系统缺少视频选择组件，请稍后再试。")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise OSError("无法打开视频选择窗口，请稍后再试。") from exc
    if result.returncode in {1, 5}:
        return None
    if result.returncode != 0:
        raise OSError("无法打开视频选择窗口，请稍后再试。")
    selected = result.stdout.strip()
    return Path(selected) if selected else None


def _applescript_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _powershell_single_quote(value: str) -> str:
    return value.replace("'", "''")


def open_folder(path: str | Path) -> None:
    directory = Path(path).expanduser().resolve()
    system = platform.system()

    if system == "Darwin":
        subprocess.Popen(["open", str(directory)])
    elif system == "Windows":
        os.startfile(str(directory))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(directory)])
