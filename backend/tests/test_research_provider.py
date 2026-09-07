from datetime import datetime

import httpx

from app.research_provider import TavilyResearchProvider


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
