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
from openclaw_sdk.gateway.openai_compat import OpenAICompatGateway as _OpenAICompatGateway
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


# --- Workaround für openclaw-sdk 2.1.0: `chat.send`-Payload passt nicht ----
# --- zur OpenAI-kompatiblen HTTP-Bridge -------------------------------------
#
# `Agent._build_send_params()` baut das `chat.send`-Payload im WS-RPC-Format
# des Gateways (`sessionKey`, `message`, `idempotencyKey`, `timeoutMs`) - so
# verifiziert im SDK-Quellcode. Der rohe WebSocket-Pfad (`ProtocolGateway`/
# `LocalGateway`) kommt damit klar. `OpenAICompatGateway.call()` leitet
# `params` aber unverändert als JSON-Body an `POST /v1/responses` weiter,
# ohne jede Feldnamen-Übersetzung - und dieser REST-Endpunkt (der einzige Weg
# ohne Geräte-Pairing/Ed25519-Signatur, das für die aktuelle OpenClaw-CLI-
# Version keinen Erzeugungsbefehl hat) validiert das Payload strikt: er
# erwartet ausschließlich `model`/`input` und lehnt jedes unbekannte Feld ab
# (real verifiziert: erst "input: Invalid input" nach reinem Ergänzen von
# `model`, dann "Unrecognized keys: sessionKey, message, idempotencyKey,
# timeoutMs" nach zusätzlichem Ergänzen von `input` - siehe
# PHASE2_CHECKPOINT.md). Für die HTTP-Bridge muss das Payload deshalb neu
# gebaut werden, nicht nur ergänzt. Der rohe WS-Pfad bleibt unverändert.
#
# Einschränkung: `options.attachments` wird über die HTTP-Bridge nicht
# unterstützt (in Phase 1/2 ungenutzt, da alle Rollen reinen Text senden) -
# ein Aufruf mit Anhängen schlägt bewusst hart fehl statt sie still zu
# verwerfen. Nur einmal pro Prozess anwenden (Re-Import-sicher).
if not getattr(openclaw.Agent, "_mpa_model_field_patch_applied", False):
    _original_build_send_params = openclaw.Agent._build_send_params

    def _build_send_params_with_model(self, query, options, idempotency_key):
        gateway = getattr(self._client, "gateway", None)
        if isinstance(gateway, _OpenAICompatGateway):
            if options and options.attachments:
                raise ModelProviderError(
                    f"{self.agent_id}: Anhänge werden über die OpenAI-kompatible "
                    "HTTP-Bridge (openclaw-sdk-Workaround) nicht unterstützt"
                )
            return {"model": f"openclaw/{self.agent_id}", "input": query}
        return _original_build_send_params(self, query, options, idempotency_key)

    openclaw.Agent._build_send_params = _build_send_params_with_model
    openclaw.Agent._mpa_model_field_patch_applied = True


# --- Workaround für openclaw-sdk 2.1.0 (Fortsetzung): ignorierter Timeout --
#
# `OpenClawClient._build_gateway()` gibt beim `openai_base_url`-Pfad `config.
# timeout` nicht an `OpenAICompatGateway` weiter - die bleibt bei ihrem
# Konstruktor-Default von 30 Sekunden, unabhängig von
# `MODEL_CALL_TIMEOUT_SECONDS`/dem an `OpenClawClient.connect(timeout=...)`
# übergebenen Wert (verifiziert im SDK-Quellcode: `OpenAICompatGateway(config.
# openai_base_url, api_key=config.api_key)` - kein `timeout`-Kwarg). Ein
# echter `research`-Lauf mit extrahiertem Seiteninhalt im Kontext überschreitet
# 30s real (verifiziert: `httpx.ReadTimeout` mit leerer `str()`-Repräsentation
# erzeugt die sonst unerklärliche Fehlermeldung "HTTP request failed for
# chat.send: " ohne jeden Grund dahinter - siehe PHASE3_CHECKPOINT.md). Patch
# ergänzt den fehlenden `timeout`-Parameter, sofern die Zielklasse
# `OpenAICompatGateway` ist; der WS-/Local-Pfad ist unberührt (deren
# `retry_policy`-Weitergabe war nie betroffen).
if not getattr(openclaw.OpenClawClient, "_mpa_gateway_timeout_patch_applied", False):
    _original_build_gateway = openclaw.OpenClawClient._build_gateway

    def _build_gateway_with_timeout(config):
        gateway = _original_build_gateway(config)
        if isinstance(gateway, _OpenAICompatGateway):
            gateway._timeout = config.timeout
        return gateway

    openclaw.OpenClawClient._build_gateway = staticmethod(_build_gateway_with_timeout)
    openclaw.OpenClawClient._mpa_gateway_timeout_patch_applied = True


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


# --- Workaround für openclaw-sdk 2.1.0 (Fortsetzung): kaputte HTTP-Antwort- -
# --- Auswertung in Agent._execute_impl() ------------------------------------
#
# `Agent.execute()` ruft intern `_execute_impl()` auf. Deren HTTP-Zweig
# ("HTTP-only path: result comes back in the send response", Zeile ~950 in
# openclaw_sdk.core.agent) sucht den Antworttext nur unter den Top-Level-
# Schlüsseln `content`/`text`/`message` und wertet `usage` überhaupt nicht
# aus. `POST /v1/responses` liefert den Text aber verschachtelt unter
# `output[].content[].text` (OpenAI-Responses-API-Form) - das Ergebnis ist
# ein leerer String und `token_usage=None`, real verifiziert (siehe
# PHASE2_CHECKPOINT.md). Diesen internen Zweig zu patchen wäre invasiver als
# die vorherigen zwei Patches (er verarbeitet auch den WS-Event-Strom in
# derselben Funktion); stattdessen umgeht `call_model` `Agent.execute()` für
# die HTTP-Bridge komplett und wertet die reale `/v1/responses`-Antwort
# selbst aus. Der rohe WS-/Local-Gateway-Pfad bleibt bei `agent.execute()`.
async def _call_via_openai_compat_bridge(
    agent: "openclaw.Agent", query: str, timeout: float
) -> tuple[str, int, int]:
    params = agent._build_send_params(query, None, uuid.uuid4().hex)
    raw = await agent._client.gateway.call("chat.send", params, timeout=timeout)

    status = raw.get("status")
    if status not in (None, "completed"):
        raise ModelProviderError(
            f"{agent.agent_id}: Agentenlauf nicht erfolgreich (status={status!r})"
        )

    text_parts: list[str] = []
    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text_parts.append(block.get("text", ""))
    content = "".join(text_parts)

    usage = raw.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return content, input_tokens, output_tokens


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

    is_openai_compat = isinstance(getattr(agent._client, "gateway", None), _OpenAICompatGateway)

    try:
        if is_openai_compat:
            content, input_tokens, output_tokens = await _call_via_openai_compat_bridge(
                agent, query, timeout
            )
        else:
            result: openclaw.ExecutionResult = await agent.execute(
                query, options=openclaw.ExecutionOptions(timeout_seconds=int(timeout))
            )
            if not result.success:
                raise ModelProviderError(
                    f"{role}: Agentenlauf nicht erfolgreich: {result.error_message}"
                )
            content = result.content
            input_tokens = result.token_usage.input
            output_tokens = result.token_usage.output
    except (openclaw.GatewayError, openclaw.APIConnectionError, openclaw.APITimeoutError,
            openclaw.AgentExecutionError, openclaw.RateLimitError, openclaw.AuthenticationError) as exc:
        # `str(exc)` allein zeigt nur die generische Nachricht (z. B. "Gateway
        # returned HTTP 400 for chat.send") - die eigentliche Fehlerursache
        # steckt in `exc.details` (u. a. bei GatewayError der geparste
        # Response-Body), wird von OpenClawError.__str__ aber nicht mit
        # ausgegeben. Ohne das hier anzuhängen, ist jeder Gateway-Fehler
        # praktisch nicht diagnostizierbar.
        details = getattr(exc, "details", None)
        raise ModelProviderError(
            f"{role}: OpenClaw-Gateway-Fehler: {exc}" + (f" | details={details}" if details else "")
        ) from exc

    parsed = _parse_json_response(content, output_schema)
    model = MODEL_CLASS_MAP[model_class]

    return ModelCallResult(
        parsed=parsed,
        provider=MODEL_PROVIDER,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimate_cost_usd(model, input_tokens, output_tokens),
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
