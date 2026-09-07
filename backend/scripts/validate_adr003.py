"""Reproduzierbare reale ADR-003-Validation; gibt niemals API-Schlüssel aus."""
from __future__ import annotations

import json
import time

from app.research_provider import TavilyResearchProvider, ResearchProviderError


TASKS = [
    ("general_software", "existing appointment scheduling software for small teams"),
    ("github_open_source", "GitHub open source document management OCR active maintained license"),
    ("framework", "FastAPI Server-Sent Events official documentation library"),
    ("vendor_docs", "Anthropic structured outputs official documentation"),
    ("current_best_practice", "OWASP LLM prompt injection prevention best practices 2026"),
]


def main() -> int:
    try:
        provider = TavilyResearchProvider()
    except ResearchProviderError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2

    reports = []
    for category, query in TASKS:
        started = time.monotonic()
        hits = provider.search(query, query, "official documentation and official repositories first")
        pages = provider.extract([hit.url for hit in hits[:5]])
        reports.append({
            "category": category,
            "query": query,
            "search_results": len(hits),
            "extracted_results": len(pages),
            "average_search_score": (
                sum(hit.score for hit in hits if hit.score is not None)
                / max(1, sum(hit.score is not None for hit in hits))
            ),
            "sources": [{
                "url": page.url,
                "content_characters": len(page.content),
                "retrieved_at": page.retrieved_at,
            } for page in pages],
            "estimated_credits": 2,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "human_scores_1_to_5": {
                "relevance": None, "source_quality": None, "freshness": None,
                "completeness": None, "extraction_quality": None,
            },
        })
    print(json.dumps({"status": "EXECUTED_NEEDS_HUMAN_SCORING", "tasks": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
