"""
Unit-Tests für app/model_provider.py selbst (ADR-011) - mocken
openclaw_sdk direkt, nicht call_model. Kein echter Gateway nötig
(siehe ADR-011 Trade-off: ein Ende-zu-Ende-Test gegen einen tatsächlich
laufenden OpenClaw-Gateway steht aus, PHASE1_CHECKPOINT.md).
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

import app.model_provider as mp
import openclaw_sdk as openclaw


class _DummySchema(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def reset_module_state():
    """_client/_agents sind Modul-Globals mit Cache-Semantik (siehe
    model_provider.py) - zwischen Tests zurücksetzen, sonst leckt der
    Mock-Zustand eines Tests in den nächsten."""
    mp._client = None
    mp._agents = {}
    yield
    mp._client = None
    mp._agents = {}


def _execution_result(content: str, success: bool = True, error_message: str | None = None):
    return openclaw.ExecutionResult(
        success=success,
        content=content,
        content_blocks=[],
        files=[],
        tool_calls=[],
        token_usage=openclaw.TokenUsage(input=100, output=40, cache_read=0, cache_write=0, total_tokens=140),
        completed_at=datetime.now(timezone.utc),
        stop_reason="end_turn",
        error_message=error_message,
    )


def _patch_client(monkeypatch, fake_client):
    async def _fake_connect(**kwargs):
        return fake_client

    monkeypatch.setattr(openclaw.OpenClawClient, "connect", _fake_connect)


def test_call_model_happy_path(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(
        return_value=_execution_result('```json\n{"value": "hallo"}\n```')
    )

    fake_client = MagicMock()
    fake_client.get_agent.side_effect = openclaw.AgentNotFoundError("not found")
    fake_client.create_agent = AsyncMock(return_value=fake_agent)
    _patch_client(monkeypatch, fake_client)

    result = mp.call_model(
        role="understanding",
        model_class="MEDIUM",
        system_prompt="sys",
        input_context="ctx",
        output_schema=_DummySchema,
    )

    assert isinstance(result.parsed, _DummySchema)
    assert result.parsed.value == "hallo"
    assert result.input_tokens == 100
    assert result.output_tokens == 40
    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-5"
    assert result.estimated_cost_usd > 0
    fake_client.create_agent.assert_awaited_once()


def test_call_model_reuses_agent_across_calls(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result('{"value": "x"}'))

    fake_client = MagicMock()
    fake_client.get_agent.side_effect = openclaw.AgentNotFoundError("not found")
    fake_client.create_agent = AsyncMock(return_value=fake_agent)
    _patch_client(monkeypatch, fake_client)

    mp.call_model("understanding", "MEDIUM", "sys", "ctx1", _DummySchema)
    mp.call_model("understanding", "MEDIUM", "sys", "ctx2", _DummySchema)

    fake_client.create_agent.assert_awaited_once()  # zweiter Aufruf nutzt den gecachten Agenten
    assert fake_agent.execute.await_count == 2


def test_call_model_existing_agent_is_reused_via_get_agent(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result('{"value": "x"}'))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent  # Agent existiert bereits im Gateway
    fake_client.create_agent = AsyncMock()
    _patch_client(monkeypatch, fake_client)

    mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)

    fake_client.create_agent.assert_not_awaited()


def test_call_model_gateway_error_raises_model_provider_error(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(side_effect=openclaw.GatewayError("gateway down"))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(mp.ModelProviderError):
        mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)


def test_call_model_unsuccessful_result_raises_model_provider_error(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result("", success=False, error_message="boom"))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(mp.ModelProviderError, match="boom"):
        mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)


def test_call_model_unparseable_response_raises_model_provider_error(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result("Das ist kein JSON."))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(mp.ModelProviderError):
        mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)


def test_call_model_unknown_model_class_raises_model_provider_error(monkeypatch):
    fake_client = MagicMock()
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(mp.ModelProviderError):
        mp.call_model("understanding", "EXTREME", "sys", "ctx", _DummySchema)
