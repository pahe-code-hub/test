"""Retrieval-Abstraktion und Tavily Search+Extract (ADR-003)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.config import TAVILY_API_KEY, TAVILY_BASE_URL, RESEARCH_TIMEOUT_SECONDS


class ResearchProviderError(Exception):
    """Technischer Search-/Extract-Fehler ohne Preisgabe von Secrets."""


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    score: float | None = None


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    content: str
    retrieved_at: str


class ResearchProvider(Protocol):
    def search(self, query: str, requirements: str, source_policy: str) -> list[SearchHit]: ...
    def extract(self, urls: list[str]) -> list[ExtractedPage]: ...


class TavilyResearchProvider:
    """Tavily Search und Extract; Tavily Research/Deep Research wird nie genutzt."""

    provider_name = "tavily"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._api_key = api_key or TAVILY_API_KEY
        if not self._api_key:
            raise ResearchProviderError("TAVILY_API_KEY ist nicht konfiguriert")
        self._client = client or httpx.Client(
            base_url=TAVILY_BASE_URL,
            timeout=RESEARCH_TIMEOUT_SECONDS,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            # Status + Response-Body (kein Secret darin - der API-Key steckt
            # nur im Request-Header, nie in Tavilys Antwort) machen den
            # Fehler diagnostizierbar; ohne das war jeder Tavily-Fehler
            # (falscher Key, Kontingent aufgebraucht, ungültiges Payload...)
            # nur als nichtssagendes "fehlgeschlagen" sichtbar.
            body = exc.response.text[:300]
            raise ResearchProviderError(
                f"Tavily-Aufruf {path} fehlgeschlagen: HTTP {exc.response.status_code}: {body}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchProviderError(f"Tavily-Aufruf {path} fehlgeschlagen: {exc}") from exc
        if not isinstance(data, dict):
            raise ResearchProviderError(f"Tavily-Aufruf {path} lieferte kein Objekt")
        return data

    def search(self, query: str, requirements: str, source_policy: str) -> list[SearchHit]:
        combined_query = f"{query}\nAnforderungen: {requirements}\nQuellenpolicy: {source_policy}"
        data = self._post("/search", {
            "query": combined_query,
            "search_depth": "basic",
            "max_results": 10,
            "include_raw_content": False,
        })
        return [
            SearchHit(
                url=item["url"],
                title=item.get("title") or item["url"],
                snippet=item.get("content") or "",
                score=item.get("score"),
            )
            for item in data.get("results", [])
            if isinstance(item, dict) and isinstance(item.get("url"), str)
        ]

    def extract(self, urls: list[str]) -> list[ExtractedPage]:
        if not urls:
            return []
        data = self._post("/extract", {
            "urls": urls,
            "extract_depth": "basic",
            "format": "markdown",
        })
        # Der Zeitpunkt wird unmittelbar nach dem echten Extract-Response
        # erfasst und niemals aus einem Modelloutput übernommen.
        retrieved_at = datetime.now(timezone.utc).isoformat()
        return [
            ExtractedPage(url=item["url"], content=item.get("raw_content") or "", retrieved_at=retrieved_at)
            for item in data.get("results", [])
            if isinstance(item, dict) and isinstance(item.get("url"), str)
            and isinstance(item.get("raw_content"), str) and item.get("raw_content")
        ]
