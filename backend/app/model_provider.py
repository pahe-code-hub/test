"""
Provider-Abstraktion `call_model` (Masterplan Abschnitt 20), implementiert
über den OpenClaw-Gateway (ADR-011) - NICHT mehr direkt über einen
Modellanbieter-Client. Agenten dürfen laut Abschnitt 20 nicht hart an
einen einzigen Modellanbieter gekoppelt sein; OpenClaw sitzt vor dem
Modellanbieter (`AgentConfig.llm_provider`/`llm_model`), ersetzt ihn nicht.

Pro Rolle wird ein im Gateway vorkonfigurierter Agent adressiert; jeder Aufruf
nutzt eine isolierte Session und erhält den versionierten System-Prompt.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Type, TypeVar

import openclaw_sdk as openclaw
from pydantic import BaseModel

from app.config import (
    MODEL_CLASS_MAP,
    MODEL_PROVIDER,
    MODEL_PRICING_USD_PER_MTOK,
    MODEL_CALL_TIMEOUT_SECONDS,
    MODEL_CALL_MAX_PROVIDER_RETRIES,
    OPENCLAW_GATEWAY_WS_URL,
    OPENCLAW_OPENAI_BASE_URL,
    OPENCLAW_API_KEY,
)

T = TypeVar("T", bound=BaseModel)


class ModelProviderError(Exception):
    """Technischer Fehlschlag eines Modellaufrufs (Gateway nicht erreichbar,
    Timeout, Auth-Fehler, ungültige Modellklasse, Antwort nicht ins Schema
    parsebar). Wird von den Routern in `agent_runs.status = FAILED`
    übersetzt (Review 1 §1.6) - keine inhaltliche Entscheidung, sondern
    ein Betriebsfehler."""


@dataclass
class ModelCallResult:
    parsed: BaseModel
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model)
    if not pricing:
        return 0.0
    return (input_tokens / 1_000_000) * pricing["input"] + (
        output_tokens / 1_000_000
    ) * pricing["output"]


# --- OpenClaw-Client/Agent-Lifecycle ----------------------------------------
#
# Ein Client über die Lebensdauer des Prozesses; jeder Lauf erhält eine eigene
# Gateway-Session, damit kein Gesprächskontext zwischen Runs durchsickert. FastAPI-Router
# sind synchron (Abschnitt 27 baut auf der bestehenden, getesteten
# Sync-Signatur von call_model auf) - die async openclaw-sdk-Aufrufe
# laufen daher in einem dedizierten Hintergrund-Event-Loop, den dieses
# Modul einmalig startet.

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_init_lock = threading.Lock()  # schützt nur das einmalige Starten des Hintergrund-Loops

_client: openclaw.OpenClawClient | None = None
_init_lock: asyncio.Lock | None = None  # asyncio.Lock, NICHT threading.Lock - siehe unten


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is None:
        with _loop_init_lock:
            if _loop is None:  # doppelt geprüft - zwei Threads könnten gleichzeitig hier ankommen
                _loop = asyncio.new_event_loop()
                _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
                _loop_thread.start()
    return _loop


def _run_async(coro):
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=MODEL_CALL_TIMEOUT_SECONDS + 5)


def _get_init_lock() -> asyncio.Lock:
    # Muss auf demselben Loop erzeugt werden, auf dem er verwendet wird -
    # daher lazy statt als Modul-Konstante.
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def _get_client() -> "openclaw.OpenClawClient":
    global _client
    if _client is not None:
        return _client
    async with _get_init_lock():
        if _client is None:  # doppelt geprüft, siehe _get_loop
            connect_kwargs = {}
            if OPENCLAW_GATEWAY_WS_URL:
                connect_kwargs["gateway_ws_url"] = OPENCLAW_GATEWAY_WS_URL
            if OPENCLAW_OPENAI_BASE_URL:
                connect_kwargs["openai_base_url"] = OPENCLAW_OPENAI_BASE_URL
            if OPENCLAW_API_KEY:
                connect_kwargs["api_key"] = OPENCLAW_API_KEY
            connect_kwargs["timeout"] = int(MODEL_CALL_TIMEOUT_SECONDS)
            connect_kwargs["max_retries"] = MODEL_CALL_MAX_PROVIDER_RETRIES
            _client = await openclaw.OpenClawClient.connect(**connect_kwargs)
    return _client


# --- Workaround für openclaw-sdk 2.1.0: fehlendes `model`-Feld -------------
#
# `Agent._build_send_params()` baut das `chat.send`-Payload ohne `model`-Feld
# (verifiziert im SDK-Quellcode, nicht vermutet). Der rohe WebSocket-Gateway-
# Pfad (`ProtocolGateway`/`LocalGateway`) toleriert das, weil er das Modell
# serverseitig aus dem in `sessionKey` enthaltenen `agent_id` auflöst. Die
# OpenAI-kompatible HTTP-Bridge (`POST /v1/responses`, per ADR-011-Ergänzung
# der einzige Weg, der ohne Geräte-Pairing/Ed25519-Signatur auskommt) verlangt
# dagegen zwingend ein `model`-Feld im Request-Body und lehnt sonst mit
# HTTP 400 ab. Dieser Patch ergänzt es, sofern nicht bereits gesetzt, im
# vom SDK selbst dokumentierten Format `openclaw/<agentId>`. Nur einmal pro
# Prozess anwenden (Re-Import-sicher).
if not getattr(openclaw.Agent, "_mpa_model_field_patch_applied", False):
    _original_build_send_params = openclaw.Agent._build_send_params

    def _build_send_params_with_model(self, query, options, idempotency_key):
        params = _original_build_send_params(self, query, options, idempotency_key)
        params.setdefault("model", f"openclaw/{self.agent_id}")
        return params

    openclaw.Agent._build_send_params = _build_send_params_with_model
    openclaw.Agent._mpa_model_field_patch_applied = True


async def _get_agent(role: str, model_class: str, system_prompt: str) -> "openclaw.Agent":
    """Erzeugt einen Session-isolierten Proxy auf einen existierenden Agenten.

    `OpenClawClient.get_agent()` ist im SDK eine rein lokale Factory und wirft
    keinen AgentNotFoundError. Die frühere catch/create-Logik wurde deshalb nie
    ausgeführt. Zudem ignoriert `create_agent(AgentConfig)` in SDK 2.1 die
    llm-/system_prompt-Felder beim Gateway-RPC. Agenten werden folglich im
    Gateway konfiguriert; der Prompt wird pro Lauf explizit mitgesendet.
    """
    if model_class not in MODEL_CLASS_MAP:
        raise ModelProviderError(f"Unbekannte Modellklasse: {model_class!r}")

    env_name = f"MPA_OPENCLAW_AGENT_ID_{role.upper()}"
    agent_id = os.environ.get(env_name, "").strip()
    if not agent_id:
        raise ModelProviderError(
            f"OpenClaw-Agent für Rolle {role!r} ist nicht konfiguriert; "
            f"Umgebungsvariable {env_name} fehlt"
        )

    client = await _get_client()
    session_name = f"masterplan-{role}-{uuid.uuid4().hex}"
    return client.get_agent(agent_id, session_name=session_name)


# --- Strukturierte Ausgabe ---------------------------------------------------
#
# Eigene, schlanke Reimplementierung statt Agent.execute_structured():
# execute_structured() liefert nur das validierte Objekt zurück, nicht
# das zugehörige ExecutionResult (Token-Nutzung, Latenz) - beides wird
# aber für agent_runs/Kostenkontrolle (Abschnitt 32) benötigt. Das
# Vorgehen (Schema-Suffix an den Prompt anhängen, JSON aus der Antwort
# extrahieren) folgt exakt openclaw_sdk.output.structured.StructuredOutput,
# nur mit zusätzlichem Zugriff auf ExecutionResult.

_JSON_BLOCK_RE = re.compile(r"```json\s*([\s\S]*?)```")
_BARE_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _schema_prompt(schema: Type[T]) -> str:
    return (
        "\n\nAntworte ausschließlich mit validem JSON nach diesem Schema:\n"
        f"```json\n{json.dumps(schema.model_json_schema(), indent=2)}\n```"
    )


def _parse_json_response(text: str, schema: Type[T]) -> T:
    match = _JSON_BLOCK_RE.search(text)
    json_str = match.group(1).strip() if match else None
    if json_str is None:
        bare = _BARE_JSON_RE.search(text)
        if bare:
            json_str = bare.group(0)
    if json_str is None:
        raise ModelProviderError(f"Keine JSON-Antwort erkennbar: {text[:200]!r}")
    try:
        return schema.model_validate(json.loads(json_str))
    except Exception as exc:  # ungültiges JSON oder Schema-Verletzung
        raise ModelProviderError(f"Antwort entspricht nicht dem Schema {schema.__name__}: {exc}") from exc


async def _call_model_async(
    role: str,
    model_class: str,
    system_prompt: str,
    input_context: str,
    output_schema: Type[T],
    timeout: float,
) -> ModelCallResult:
    agent = await _get_agent(role, model_class, system_prompt)
    query = (
        "<system_instructions>\n"
        + system_prompt
        + "\n</system_instructions>\n\n"
        + input_context
        + _schema_prompt(output_schema)
    )

    try:
        result: openclaw.ExecutionResult = await agent.execute(
            query, options=openclaw.ExecutionOptions(timeout_seconds=int(timeout))
        )
    except (openclaw.GatewayError, openclaw.APIConnectionError, openclaw.APITimeoutError,
            openclaw.AgentExecutionError, openclaw.RateLimitError, openclaw.AuthenticationError) as exc:
        raise ModelProviderError(f"{role}: OpenClaw-Gateway-Fehler: {exc}") from exc

    if not result.success:
        raise ModelProviderError(f"{role}: Agentenlauf nicht erfolgreich: {result.error_message}")

    parsed = _parse_json_response(result.content, output_schema)
    model = MODEL_CLASS_MAP[model_class]

    return ModelCallResult(
        parsed=parsed,
        provider=MODEL_PROVIDER,
        model=model,
        input_tokens=result.token_usage.input,
        output_tokens=result.token_usage.output,
        estimated_cost_usd=_estimate_cost_usd(model, result.token_usage.input, result.token_usage.output),
    )


def call_model(
    role: str,
    model_class: str,
    system_prompt: str,
    input_context: str,
    output_schema: Type[T],
    timeout: float = MODEL_CALL_TIMEOUT_SECONDS,
    max_provider_retries: int = MODEL_CALL_MAX_PROVIDER_RETRIES,  # an OpenClawClient.connect() gereicht, nicht pro Aufruf
) -> ModelCallResult:
    """Synchrone Fassade über die async openclaw-sdk-Aufrufe (siehe Modul-
    Docstring) - Signatur unverändert gegenüber der Anthropic-Direktanbindung
    aus der ersten Phase-1-Implementierung, damit `routers/projects.py`
    und alle bestehenden Tests unverändert bleiben (der Austausch ist
    ausschließlich eine Änderung *hinter* dieser Funktion, ADR-011).
    Nicht global gesperrt - siehe Docstring von `_get_agent` zur
    Parallelitätsanforderung ab Phase 3."""
    return _run_async(
        _call_model_async(role, model_class, system_prompt, input_context, output_schema, timeout)
    )
