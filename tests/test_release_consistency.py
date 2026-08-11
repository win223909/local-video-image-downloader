import shutil
from pathlib import Path

import pytest

from scripts.verify_release_consistency import (
    app_js_cache_version,
    parse_sha256sums,
    verify,
    version_from_url,
)


def test_parse_sha256sums_ignores_comments_and_blank_lines() -> None:
    checksum = "a" * 64

    assert parse_sha256sums(f"# comment\n\n{checksum}  file.zip\n") == {"file.zip": checksum}


def test_version_from_url_reads_query_version() -> None:
    assert version_from_url("https://example.test/agent.zip?v=0.1.52") == "0.1.52"
    assert version_from_url("https://example.test/agent.zip") is None


def test_app_js_cache_version_reads_current_index() -> None:
    root = Path(__file__).resolve().parents[1]
    index = (root / "web" / "index.html").read_text(encoding="utf-8")

    assert app_js_cache_version(index) == "0.1.52"


def test_current_release_consistency_passes() -> None:
    assert verify(Path(__file__).resolve().parents[1])


def test_app_js_cache_version_mismatch_fails_validation(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    required_files = (
        "local_agent/server.py",
        "web/app.js",
        "web/index.html",
        "web/downloads/update.json",
        "web/downloads/SHA256SUMS.txt",
        "web/downloads/VideoDownloaderAgent-macOS.zip",
        "web/downloads/VideoDownloaderAgent-Windows.zip",
        "web/downloads/agent-source.zip",
    )
    for relative in required_files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)

    index_path = tmp_path / "web" / "index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "app.js?v=0.1.52", "app.js?v=0.1.51"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="app.js cache version"):
        verify(tmp_path)
