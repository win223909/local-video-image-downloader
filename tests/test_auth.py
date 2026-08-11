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

