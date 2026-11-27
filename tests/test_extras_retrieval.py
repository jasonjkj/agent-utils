import asyncio
import json

import httpx
import pytest

from agent_utils.extras.retrieval import RetrievalError, web_fetch, web_search


# ---- web_fetch ----


def test_web_fetch_html_to_text():
    html_doc = (
        "<html><head><script>var x=1</script></head>"
        "<body><h1>标题</h1><p>正文 <b>粗</b></p></body></html>"
    )

    def handler(request):
        return httpx.Response(200, text=html_doc, headers={"Content-Type": "text/html"})

    async def run():
        return await web_fetch("http://example.com/page", {}, _transport=httpx.MockTransport(handler))

    text = asyncio.run(run())
    assert "标题" in text
    assert "正文 粗" in text
    assert "var x=1" not in text
    assert "<" not in text


def test_web_fetch_rejects_bad_protocol():
    with pytest.raises(RetrievalError):
        asyncio.run(web_fetch("ftp://example.com/x", {}))


def test_web_fetch_domain_whitelist():
    with pytest.raises(RetrievalError):
        asyncio.run(web_fetch("http://evil.com/x", {"domain_whitelist": ["example.com"]}))


def test_web_fetch_follows_redirect_within_whitelist():
    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "http://example.com/b"})
        return httpx.Response(200, text="final body")

    async def run():
        return await web_fetch(
            "http://example.com/a",
            {"domain_whitelist": ["example.com"]},
            _transport=httpx.MockTransport(handler),
        )

    assert asyncio.run(run()) == "final body"


def test_web_fetch_rejects_redirect_outside_whitelist():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://evil.com/b"})

    async def run():
        return await web_fetch(
            "http://example.com/a",
            {"domain_whitelist": ["example.com"]},
            _transport=httpx.MockTransport(handler),
        )

    with pytest.raises(RetrievalError):
        asyncio.run(run())


def test_web_fetch_respects_max_bytes():
    def handler(request):
        return httpx.Response(200, text="x" * 1000)

    async def run():
        return await web_fetch(
            "http://example.com/a", {"fetch_max_bytes": 100}, _transport=httpx.MockTransport(handler)
        )

    assert len(asyncio.run(run())) == 100


# ---- web_search ----


def test_web_search_unknown_engine():
    with pytest.raises(RetrievalError):
        asyncio.run(web_search("q", "nope", {}))


def test_web_search_bing():
    html = (
        '<li class="b_algo"><a href="http://x/1">标题一</a><p>摘要一</p></li>'
        '<li class="b_algo"><a href="http://x/2">标题二</a><p>摘要二</p></li>'
    )

    def handler(request):
        assert "bing.com" in str(request.url)
        return httpx.Response(200, text=html)

    async def run():
        return await web_search("测试", "bing", {}, _transport=httpx.MockTransport(handler))

    results = asyncio.run(run())
    assert results[0]["title"] == "标题一"
    assert results[0]["url"] == "http://x/1"
    assert results[1]["title"] == "标题二"


def test_web_search_baidu():
    html = '<h3><a href="http://x/1">B标题</a></h3>'

    def handler(request):
        return httpx.Response(200, text=html)

    async def run():
        return await web_search("q", "baidu", {}, _transport=httpx.MockTransport(handler))

    results = asyncio.run(run())
    assert results[0]["title"] == "B标题"


def test_web_search_google():
    html = '<a href="http://x/1"><h3>G标题</h3></a>'

    def handler(request):
        return httpx.Response(200, text=html)

    async def run():
        return await web_search("q", "google", {}, _transport=httpx.MockTransport(handler))

    results = asyncio.run(run())
    assert results[0]["title"] == "G标题"


def test_web_search_duckduckgo():
    html = (
        '<a class="result__a" href="http://x/1">D标题</a>'
        '<a class="result__snippet">D摘要</a>'
    )

    def handler(request):
        return httpx.Response(200, text=html)

    async def run():
        return await web_search("q", "duckduckgo", {}, _transport=httpx.MockTransport(handler))

    results = asyncio.run(run())
    assert results[0]["title"] == "D标题"
    assert results[0]["snippet"] == "D摘要"


def test_web_search_tavily_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RetrievalError):
        asyncio.run(web_search("q", "tavily", {}))


def test_web_search_tavily_with_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    payload = json.dumps({"results": [{"title": "T", "url": "http://t", "content": "c"}]})

    def handler(request):
        return httpx.Response(200, content=payload.encode("utf-8"))

    async def run():
        return await web_search("q", "tavily", {}, _transport=httpx.MockTransport(handler))

    results = asyncio.run(run())
    assert results[0]["title"] == "T"


def test_search_adapters_registry():
    from agent_utils.extras.retrieval import SEARCH_ADAPTERS
    assert set(SEARCH_ADAPTERS) == {"baidu", "bing", "google", "duckduckgo", "tavily"}


def test_web_fetch_plain_text_passthrough():
    def handler(request):
        return httpx.Response(200, text="plain body no tags")

    async def run():
        return await web_fetch("http://example.com/a", {}, _transport=httpx.MockTransport(handler))

    assert asyncio.run(run()) == "plain body no tags"


def test_web_fetch_redirect_limit_exceeded():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://example.com/loop"})

    async def run():
        return await web_fetch(
            "http://example.com/loop", {"fetch_max_redirects": 2}, _transport=httpx.MockTransport(handler)
        )

    with pytest.raises(RetrievalError):
        asyncio.run(run())


def test_web_fetch_redirect_missing_location():
    def handler(request):
        return httpx.Response(302)

    async def run():
        return await web_fetch("http://example.com/a", {}, _transport=httpx.MockTransport(handler))

    with pytest.raises(RetrievalError):
        asyncio.run(run())


def test_tavily_empty_key_raises(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    with pytest.raises(RetrievalError):
        asyncio.run(web_search("q", "tavily", {}))
