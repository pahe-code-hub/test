"""Manueller E2E-Nachweis für call_model gegen einen laufenden Gateway."""
from __future__ import annotations

import json
import time

from pydantic import BaseModel

from app.model_provider import ModelProviderError, call_model


ROLES = ("understanding", "research")


class GatewayVerificationOutput(BaseModel):
    antwort: str


def main() -> int:
    failed = False
    for role in ROLES:
        started = time.monotonic()
        try:
            result = call_model(
                role=role,
                model_class="MEDIUM",
                system_prompt=(
                    "Dies ist ein technischer Gateway-Verifikationstest. "
                    "Antworte ausschließlich mit dem JSON-Feld antwort und "
                    "dem Wert 'gateway-ok'."
                ),
                input_context="Führe den technischen Verifikationstest jetzt aus.",
                output_schema=GatewayVerificationOutput,
            )
        except ModelProviderError as exc:
            failed = True
            print(json.dumps({
                "status": "FAILED",
                "role": role,
                "error": str(exc),
            }, ensure_ascii=False))
            continue

        print(json.dumps({
            "status": "OK",
            "role": role,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "estimated_cost_usd": result.estimated_cost_usd,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "result": result.parsed.model_dump(),
        }, ensure_ascii=False))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
