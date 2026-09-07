import time

import pytest
from fastapi import HTTPException

from local_agent import server


@pytest.fixture
def agent_state(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(server, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(server, "TOKEN_FILE", runtime / "agent-token.json")
    monkeypatch.setattr(server, "SETTINGS_FILE", runtime / "agent-settings.json")
    monkeypatch.setattr(server, "UPDATE_STATUS_FILE", runtime / "update-status.json")
    return server.AgentState()


def test_pairing_success_and_token_authentication(agent_state):
    token = agent_state.pair(agent_state.pair_code)

    assert token
    assert agent_state.is_authenticated(f"Bearer {token}")
    assert not agent_state.is_authenticated("Bearer wrong-token")


def test_pairing_rejects_expired_code(agent_state):
    agent_state.pair_expires_at = time.time() - 1

    with pytest.raises(HTTPException) as error:
        agent_state.pair(agent_state.pair_code)

    assert error.value.status_code == 403


def test_pairing_rate_limit_after_repeated_failures(agent_state):
    wrong_code = agent_state.pair_code + "x"

    for _ in range(server.PAIRING_MAX_ATTEMPTS - 1):
        with pytest.raises(HTTPException) as error:
            agent_state.pair(wrong_code)
        assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        agent_state.pair(wrong_code)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"]

    with pytest.raises(HTTPException) as error:
        agent_state.pair(agent_state.pair_code)
    assert error.value.status_code == 429


def test_update_version_comparison_only_accepts_newer_versions():
    assert server.is_newer_version("0.1.52", "0.1.51")
    assert not server.is_newer_version("0.1.51", "0.1.52")
    assert not server.is_newer_version("0.1.52", "0.1.52")
    assert not server.is_newer_version("invalid", "0.1.51")


def test_update_check_only_reports_a_newer_manifest(monkeypatch):
    monkeypatch.setattr(server, "AGENT_VERSION", "0.1.51")
    monkeypatch.setattr(server, "safe_update_status", lambda: {})

    monkeypatch.setattr(server, "fetch_update_manifest", lambda: {"version": "0.1.47"})
    assert server.check_update()["update_available"] is False

    monkeypatch.setattr(server, "fetch_update_manifest", lambda: {"version": "0.1.52"})
    assert server.check_update()["update_available"] is True
