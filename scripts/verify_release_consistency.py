"""Verify release version and checksum consistency without changing files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
ASSET_NAMES = (
    "VideoDownloaderAgent-macOS.zip",
    "VideoDownloaderAgent-Windows.zip",
    "agent-source.zip",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_version(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find {label} in {path.relative_to(ROOT)}")
    return match.group(1)


def parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            raise ValueError(f"Invalid SHA256SUMS entry on line {line_number}")
        filename = parts[1].strip()
        if filename in checksums:
            raise ValueError(f"Duplicate SHA256SUMS entry: {filename}")
        checksums[filename] = parts[0].lower()
    return checksums


def version_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("v")
    return values[0] if values else None


def verify(root: Path = ROOT) -> list[str]:
    server_path = root / "local_agent" / "server.py"
    web_app_path = root / "web" / "app.js"
    web_index_path = root / "web" / "index.html"
    manifest_path = root / "web" / "downloads" / "update.json"
    sums_path = root / "web" / "downloads" / "SHA256SUMS.txt"
    downloads_dir = root / "web" / "downloads"

    agent_version = extract_version(
        server_path,
        r'^\s*AGENT_VERSION\s*=\s*"([^"]+)"\s*$',
        "AGENT_VERSION",
    )
    web_version = extract_version(
        web_app_path,
        r'^\s*const\s+WEB_VERSION\s*=\s*"([^"]+)"\s*;',
        "WEB_VERSION",
    )
    index_version = extract_version(
        web_index_path,
        r'<div id="versionBadge"[^>]*>\s*v([^<\s]+)\s*</div>',
        "version badge fallback",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = str(manifest.get("version") or "")
    agent_url = str(manifest.get("agent_url") or "")
    agent_url_version = version_from_url(agent_url)

    errors: list[str] = []
    versions = {
        "Agent version": agent_version,
        "web fallback version": web_version,
        "HTML fallback version": index_version,
        "update manifest version": manifest_version,
    }
    for label, value in versions.items():
        if value != agent_version:
            errors.append(f"{label} is {value!r}, expected {agent_version!r}")
    if agent_url_version is not None and agent_url_version != agent_version:
        errors.append(f"agent URL version is {agent_url_version!r}, expected {agent_version!r}")

    agent_zip = downloads_dir / "agent-source.zip"
    actual_agent_sha = sha256(agent_zip)
    if str(manifest.get("agent_sha256") or "").lower() != actual_agent_sha:
        errors.append("update manifest agent_sha256 does not match agent-source.zip")

    expected_assets = {name: sha256(downloads_dir / name) for name in ASSET_NAMES}
    checksums = parse_sha256sums(sums_path.read_text(encoding="utf-8"))
    if set(checksums) != set(expected_assets):
        errors.append(
            "SHA256SUMS entries do not match the expected assets: "
            f"expected {sorted(expected_assets)}, got {sorted(checksums)}"
        )
    for name, expected_sha in expected_assets.items():
        if checksums.get(name) != expected_sha:
            errors.append(f"SHA256SUMS mismatch for {name}")

    if errors:
        raise ValueError("Release consistency check failed:\n- " + "\n- ".join(errors))

    return [
        f"Agent version: PASS ({agent_version})",
        f"Web fallback version: PASS ({web_version})",
        f"HTML fallback version: PASS ({index_version})",
        f"Update manifest version: PASS ({manifest_version})",
        f"Agent URL version: PASS ({agent_url_version or 'no query version'})",
        f"agent-source SHA256: PASS ({actual_agent_sha})",
        "SHA256SUMS: PASS",
    ]


def main() -> int:
    try:
        for line in verify():
            print(line)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
