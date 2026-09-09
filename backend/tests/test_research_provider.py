from datetime import datetime

import httpx
import pytest

from app.research_provider import ResearchProviderError, TavilyResearchProvider


def test_tavily_search_and_extract_are_separate_real_endpoints():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": [{
                "url": "https://example.test/docs", "title": "Docs",
                "content": "official", "score": 0.9,
            }]})
        return httpx.Response(200, json={"results": [{
            "url": "https://example.test/docs", "raw_content": "# Documentation",
        }]})

    client = httpx.Client(base_url="https://api.tavily.test", transport=httpx.MockTransport(handler))
    provider = TavilyResearchProvider(api_key="not-a-real-key", client=client)
    hits = provider.search("query", "requirements", "official sources")
    pages = provider.extract([hits[0].url])

    assert [request.url.path for request in requests] == ["/search", "/extract"]
    assert pages[0].content == "# Documentation"
    assert datetime.fromisoformat(pages[0].retrieved_at).tzinfo is not None


def test_extract_timestamp_is_generated_by_provider_not_response():
    client = httpx.Client(
        base_url="https://api.tavily.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "retrieved_at": "1900-01-01T00:00:00Z",
            "results": [{"url": "https://example.test", "raw_content": "content"}],
        })),
    )
    page = TavilyResearchProvider(api_key="dummy", client=client).extract(["https://example.test"])[0]
    assert not page.retrieved_at.startswith("1900-")


def test_http_error_includes_status_and_body_not_just_generic_message():
    """Vor diesem Fix wurde jeder Tavily-HTTP-Fehler (falscher Key, Kontingent
    aufgebraucht, ungültiges Payload...) zu einem nichtssagenden
    "Tavily-Aufruf /search fehlgeschlagen" ohne jeden Grund dahinter - real
    beobachtet beim Testen gegen den echten Tavily-Endpunkt."""
    client = httpx.Client(
        base_url="https://api.tavily.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(
            401, json={"detail": "Invalid API key"}
        )),
    )
    provider = TavilyResearchProvider(api_key="wrong", client=client)

    with pytest.raises(ResearchProviderError, match="401"):
        provider.search("query", "requirements", "official sources")
