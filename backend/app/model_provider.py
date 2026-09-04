"""
Provider-Abstraktion `call_model` (Masterplan Abschnitt 20).

Signatur: call_model(role, model_class, system_prompt, input_context,
output_schema, timeout, max_provider_retries) - v0.2 ergänzt Timeout
und Provider-Retries (Review 2 §2.7) gegenüber v0.1.

Agenten dürfen laut Abschnitt 20 nicht hart an einen einzigen
Modellanbieter gekoppelt sein. Für Phase 1 gibt es genau einen
Provider (Anthropic) - die Kapselung hier ist die vorgesehene
Austauschstelle für einen späteren zweiten Provider, nicht schon
eine Multi-Provider-Implementierung.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

from app.config import (
    MODEL_CLASS_MAP,
    MODEL_PRICING_USD_PER_MTOK,
    MODEL_CALL_TIMEOUT_SECONDS,
    MODEL_CALL_MAX_PROVIDER_RETRIES,
)

T = TypeVar("T", bound=BaseModel)


class ModelProviderError(Exception):
    """Technischer Fehlschlag eines Modellaufrufs (Timeout, Rate-Limit nach
    Ausschöpfung der Provider-Retries, Serverfehler, ungültige Modellklasse).
    Wird von den Routern in `agent_runs.status = FAILED` übersetzt
    (Review 1 §1.6) - keine inhaltliche Entscheidung, sondern ein
    Betriebsfehler."""


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


def call_model(
    role: str,
    model_class: str,
    system_prompt: str,
    input_context: str,
    output_schema: Type[T],
    timeout: float = MODEL_CALL_TIMEOUT_SECONDS,
    max_provider_retries: int = MODEL_CALL_MAX_PROVIDER_RETRIES,
) -> ModelCallResult:
    """Führt einen strukturierten Modellaufruf aus und liefert ein bereits
    gegen `output_schema` validiertes Pydantic-Objekt zurück.

    Wirft `ModelProviderError` bei jedem technischen Fehlschlag - der
    Aufrufer (Router) ist dafür verantwortlich, daraus einen
    `agent_runs`-Eintrag mit status=FAILED zu machen, nicht diese
    Funktion selbst (Trennung: Provider-Abstraktion kennt keinen
    Projekt-State).
    """
    model = MODEL_CLASS_MAP.get(model_class)
    if not model:
        raise ModelProviderError(f"Unbekannte Modellklasse: {model_class!r}")

    client = anthropic.Anthropic(timeout=timeout, max_retries=max_provider_retries)

    try:
        response = client.messages.parse(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": input_context}],
            output_format=output_schema,
        )
    except anthropic.APIError as exc:  # covers status errors, connection errors, timeouts
        raise ModelProviderError(f"{role}: Anthropic-API-Fehler: {exc}") from exc

    usage = response.usage
    return ModelCallResult(
        parsed=response.parsed_output,
        provider="anthropic",
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        estimated_cost_usd=_estimate_cost_usd(model, usage.input_tokens, usage.output_tokens),
    )
