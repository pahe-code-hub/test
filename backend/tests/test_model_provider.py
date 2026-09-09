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
def reset_module_state(monkeypatch):
    """Den Client-Cache zwischen Tests zurücksetzen."""
    mp._client = None
    monkeypatch.setenv("MPA_OPENCLAW_AGENT_ID_UNDERSTANDING", "test-understanding")
    yield
    mp._client = None


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
    fake_client.get_agent.return_value = fake_agent
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
    fake_client.get_agent.assert_called_once()
    assert "<system_instructions>\nsys\n</system_instructions>" in fake_agent.execute.await_args.args[0]


def test_call_model_uses_isolated_sessions_across_calls(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result('{"value": "x"}'))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent
    _patch_client(monkeypatch, fake_client)

    mp.call_model("understanding", "MEDIUM", "sys", "ctx1", _DummySchema)
    mp.call_model("understanding", "MEDIUM", "sys", "ctx2", _DummySchema)

    assert fake_client.get_agent.call_count == 2
    sessions = [call.kwargs["session_name"] for call in fake_client.get_agent.call_args_list]
    assert sessions[0] != sessions[1]
    assert fake_agent.execute.await_count == 2


def test_call_model_uses_configured_gateway_agent(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.execute = AsyncMock(return_value=_execution_result('{"value": "x"}'))

    fake_client = MagicMock()
    fake_client.get_agent.return_value = fake_agent
    _patch_client(monkeypatch, fake_client)
    monkeypatch.setenv("MPA_OPENCLAW_AGENT_ID_UNDERSTANDING", "configured-understanding")

    mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)

    assert fake_client.get_agent.call_args.args[0] == "configured-understanding"


def test_call_model_requires_role_specific_gateway_agent(monkeypatch):
    monkeypatch.delenv("MPA_OPENCLAW_AGENT_ID_UNDERSTANDING")

    with pytest.raises(mp.ModelProviderError, match="MPA_OPENCLAW_AGENT_ID_UNDERSTANDING fehlt"):
        mp.call_model("understanding", "MEDIUM", "sys", "ctx", _DummySchema)


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


def test_agent_build_send_params_rebuilds_payload_for_openai_compat_bridge():
    """Regressionstest für den openclaw-sdk-2.1.0-Patch in model_provider.py.

    `Agent._build_send_params()` liefert im unveränderten SDK das WS-RPC-
    Format (`sessionKey`, `message`, `idempotencyKey`, `timeoutMs`). Die
    OpenAI-kompatible HTTP-Bridge (`POST /v1/responses`) validiert strikt:
    ohne `model` HTTP 400 "Invalid model", ohne `input` "input: Invalid
    input", und mit den WS-RPC-Feldern zusätzlich "Unrecognized keys" (alle
    drei real gegen einen laufenden Gateway verifiziert, siehe
    docs/PHASE2_CHECKPOINT.md). Für diesen Transport muss das Payload daher
    komplett neu gebaut werden. Dieser Test bricht, falls der Patch entfernt
    oder von einer SDK-Aktualisierung überschrieben wird, ohne dass ein
    Ersatz existiert.
    """
    from openclaw_sdk.gateway.openai_compat import OpenAICompatGateway

    fake_client = MagicMock()
    fake_client.gateway = MagicMock(spec=OpenAICompatGateway)
    agent = openclaw.Agent(fake_client, agent_id="mpa-understanding", session_name="s1")

    params = agent._build_send_params("hallo", None, "idem-1")

    assert params == {"model": "openclaw/mpa-understanding", "input": "hallo"}


def test_agent_build_send_params_unchanged_for_raw_websocket_gateway():
    """Der WS-/Local-Gateway-Pfad darf vom HTTP-Bridge-Workaround nicht
    betroffen sein - dort funktioniert das originale `sessionKey`-basierte
    Payload bereits (verifiziert vor Einführung des Workarounds)."""
    fake_client = MagicMock()
    fake_client.gateway = MagicMock()  # kein OpenAICompatGateway
    agent = openclaw.Agent(fake_client, agent_id="mpa-understanding", session_name="s1")

    params = agent._build_send_params("hallo", None, "idem-1")

    assert params["sessionKey"] == "agent:mpa-understanding:s1"
    assert params["message"] == "hallo"
    assert "model" not in params
    assert "input" not in params


def test_call_model_over_openai_compat_bridge_end_to_end(monkeypatch):
    """End-to-End-Test für den kompletten HTTP-Bridge-Workaround in
    call_model() gegen die reale `/v1/responses`-Antwortform (unverändert
    aus einem echten Gateway-Aufruf übernommen, siehe
    docs/PHASE2_CHECKPOINT.md) - nicht nur den Request-Payload wie die
    beiden Tests oben, sondern auch die Antwort-Auswertung inklusive
    Token-Nutzung, die `Agent.execute()` für diesen Transport falsch bzw.
    gar nicht liefert."""
    from openclaw_sdk.gateway.openai_compat import OpenAICompatGateway

    real_responses_api_payload = {
        "id": "resp_548c9ea8-6f6f-43cb-8d1e-d06e5ce66cea",
        "object": "response",
        "status": "completed",
        "model": "openclaw/test-understanding",
        "output": [{
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": '```json\n{"value": "hallo"}\n```'}],
            "status": "completed",
        }],
        "usage": {"input_tokens": 17692, "output_tokens": 8},
    }

    fake_client = MagicMock()
    fake_client.gateway = MagicMock(spec=OpenAICompatGateway)
    fake_client.gateway.call = AsyncMock(return_value=real_responses_api_payload)
    fake_client.get_agent = MagicMock(
        side_effect=lambda agent_id, session_name: openclaw.Agent(
            fake_client, agent_id=agent_id, session_name=session_name
        )
    )
    _patch_client(monkeypatch, fake_client)

    result = mp.call_model(
        role="understanding",
        model_class="MEDIUM",
        system_prompt="sys",
        input_context="ctx",
        output_schema=_DummySchema,
    )

    assert result.parsed.value == "hallo"
    assert result.input_tokens == 17692
    assert result.output_tokens == 8
    assert result.model == "claude-sonnet-5"

    call_args = fake_client.gateway.call.call_args
    sent_params = call_args.args[1]
    assert call_args.args[0] == "chat.send"
    assert sent_params["model"] == "openclaw/test-understanding"
    assert set(sent_params.keys()) == {"model", "input"}


def test_build_gateway_forwards_configured_timeout_to_openai_compat_bridge():
    """Regressionstest für den openclaw-sdk-2.1.0-Patch in model_provider.py.

    `OpenClawClient._build_gateway()` gibt `config.timeout` im
    `openai_base_url`-Pfad im unveränderten SDK nicht an
    `OpenAICompatGateway` weiter - die bleibt bei ihrem Konstruktor-Default
    von 30 Sekunden, egal was `MODEL_CALL_TIMEOUT_SECONDS`/`call_model(...,
    timeout=...)` konfiguriert. Ein echter `research`-Lauf mit extrahiertem
    Seiteninhalt im Kontext überschreitet 30s real und schlägt mit einem
    nichtssagenden `httpx.ReadTimeout` (leere `str()`-Repräsentation) fehl -
    real gegen einen laufenden Gateway verifiziert, siehe
    docs/PHASE3_CHECKPOINT.md. Dieser Test bricht, falls der Patch entfernt
    oder von einer SDK-Aktualisierung überschrieben wird, ohne dass ein
    Ersatz existiert.
    """
    from openclaw_sdk.core.config import ClientConfig

    config = ClientConfig(openai_base_url="http://example.test", api_key="k", timeout=123)
    gateway = openclaw.OpenClawClient._build_gateway(config)

    assert gateway._timeout == 123
