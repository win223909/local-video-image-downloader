from pathlib import Path

from scripts.verify_release_consistency import parse_sha256sums, version_from_url, verify


def test_parse_sha256sums_ignores_comments_and_blank_lines() -> None:
    checksum = "a" * 64

    assert parse_sha256sums(f"# comment\n\n{checksum}  file.zip\n") == {"file.zip": checksum}


def test_version_from_url_reads_query_version() -> None:
    assert version_from_url("https://example.test/agent.zip?v=0.1.52") == "0.1.52"
    assert version_from_url("https://example.test/agent.zip") is None


def test_current_release_consistency_passes() -> None:
    assert verify(Path(__file__).resolve().parents[1])
