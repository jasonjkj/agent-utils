"""extras/retrieval.py — 只读检索（普通函数集合，非 agent 接口）。

只读检索的两个裸能力 + 配套解析：
- `web_search`：多 provider 搜索注册表（bing/baidu/google/duckduckgo/tavily）
- `web_fetch`：抓取网页正文（协议/白名单/逐跳重定向校验 + HTML 净化）

圆桌协议链路（[RETRIEVE]/[FETCH] 标记解析、资料池、回贴块编排、read_file）不收。
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse

import httpx


class RetrievalError(Exception):
    pass


_MAX_RESULTS = 5
# 统一浏览器请求头（升级项 2）：裸 UA 触发百度反爬，真实 UA + Accept-Language 基础卫生
_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
# HTML → 文本净化（逃生口）：容忍截断造成的未闭合 script/style（非贪婪到闭合或结尾）
_HTML_SCRIPT_STYLE_RE = re.compile(r"(?is)<(?:script|style)\b[^>]*>.*?(?:</(?:script|style)>|$)")
_HTML_TAG_RE = re.compile(r"(?s)<[^>]+>")
_HTML_WS_RE = re.compile(r"[ \t\r\f\v]+")
_HTML_HINT_RE = re.compile(r"(?i)<\s*(?:html|head|body|div|script|style|p|h[1-6])\b")


def _is_html(content: str) -> bool:
    return _HTML_HINT_RE.search(content) is not None


def _html_to_text(content: str) -> str:
    text = _HTML_SCRIPT_STYLE_RE.sub(" ", content)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _HTML_WS_RE.sub(" ", text).strip()


async def web_fetch(url: str, cfg: dict, _transport=None) -> str:
    """仅 GET、限 http/https、超时、大小上限、可选域名白名单、逐跳校验重定向。

    M4 加固：重定向逐跳校验（follow_redirects=False + 手动循环）——每跳都重新
    校验协议与域名白名单，白名单内站点 302 到白名单外域名一律拒绝；响应体
    流式读取、边读边截，fetch_max_bytes 同时管住内存与输出。
    """
    whitelist = cfg.get("domain_whitelist") or []
    timeout = cfg.get("fetch_timeout_seconds", 10)
    max_bytes = cfg.get("fetch_max_bytes", 100000)
    max_redirects = cfg.get("fetch_max_redirects", 5)
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                 transport=_transport) as client:
        for _ in range(max_redirects + 1):
            parsed = urllib.parse.urlparse(current)
            if parsed.scheme not in ("http", "https"):
                raise RetrievalError(f"协议不允许: {parsed.scheme}")
            if whitelist and parsed.netloc not in whitelist:
                raise RetrievalError(f"域名不在白名单: {parsed.netloc}")
            async with client.stream("GET", current) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        raise RetrievalError("重定向缺少 Location")
                    current = urllib.parse.urljoin(current, location)
                    continue
                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    if total >= max_bytes:
                        break
                    take = chunk[:max_bytes - total]
                    chunks.append(take)
                    total += len(take)
                # 中途 break 后依赖 async with 退出自动 aclose，连接不悬挂
                text = b"".join(chunks).decode("utf-8", errors="ignore")
                if _is_html(text):
                    text = _html_to_text(text)
                return text
    raise RetrievalError("重定向次数超限")


async def _baidu_search(query: str, cfg: dict, _transport=None) -> list[dict]:
    """百度网页搜索。解析结果页标题/链接（反爬偶发，fallback 链兜底）。"""
    params = {"wd": query}
    async with httpx.AsyncClient(timeout=cfg.get("fetch_timeout_seconds", 10),
                                 headers=_BROWSER_HEADERS,
                                 follow_redirects=True, transport=_transport) as client:
        resp = await client.get("https://www.baidu.com/s", params=params)
    html = resp.text
    results: list[dict] = []
    for m in re.finditer(
            r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if title:
            results.append({"title": title, "url": m.group(1),
                            "snippet": ""})
        if len(results) >= _MAX_RESULTS:
            break
    return results


async def _google_search(query: str, cfg: dict, _transport=None) -> list[dict]:
    params = {"q": query}
    async with httpx.AsyncClient(timeout=cfg.get("fetch_timeout_seconds", 10),
                                 headers=_BROWSER_HEADERS,
                                 follow_redirects=True, transport=_transport) as client:
        resp = await client.get("https://www.google.com/search", params=params)
    html = resp.text
    results: list[dict] = []
    for m in re.finditer(r'href="(https?://[^"]+)".*?<h3[^>]*>(.*?)</h3>', html, re.S):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if title:
            results.append({"title": title, "url": m.group(1), "snippet": ""})
        if len(results) >= _MAX_RESULTS:
            break
    return results


async def _duckduckgo_search(query: str, cfg: dict, _transport=None) -> list[dict]:
    params = {"q": query, "kl": "cn-zh"}
    async with httpx.AsyncClient(timeout=cfg.get("fetch_timeout_seconds", 10),
                                 headers=_BROWSER_HEADERS,
                                 follow_redirects=True, transport=_transport) as client:
        resp = await client.get("https://html.duckduckgo.com/html/", params=params)
    html = resp.text
    results: list[dict] = []
    for m in re.finditer(
            r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'result__snippet[^>]*>(.*?)</a>', html, re.S):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip() or query
        snippet = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        results.append({"title": title, "url": m.group(1), "snippet": snippet})
        if len(results) >= _MAX_RESULTS:
            break
    return results


async def _bing_search(query: str, cfg: dict, _transport=None) -> list[dict]:
    """必应国内站（cn.bing.com）——免费、国内可达、稳定；解析 b_algo 结果块。

    升级项 2 默认主引擎：Chrome UA 下实测稳定返回结果页，b_algo 结构可解析
    标题/URL/摘要。摘要截断沿用调用方 _SNIPPET_MAX。
    """
    params = {"q": query}
    async with httpx.AsyncClient(timeout=cfg.get("fetch_timeout_seconds", 10),
                                 headers=_BROWSER_HEADERS,
                                 follow_redirects=True, transport=_transport) as client:
        resp = await client.get("https://cn.bing.com/search", params=params)
    html = resp.text
    results: list[dict] = []
    # 先按 b_algo 结果块切分，块内再抽 URL/标题/摘要——比单条大正则稳
    for block in re.findall(r'<li class="b_algo".*?</li>', html, re.S):
        m = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not title:
            continue
        p = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        snippet = re.sub(r"<[^>]+>", "", p.group(1)).strip() if p else ""
        results.append({"title": title, "url": m.group(1), "snippet": snippet})
        if len(results) >= _MAX_RESULTS:
            break
    return results


async def _tavily_search(query: str, cfg: dict, _transport=None) -> list[dict]:
    """Tavily 搜索 API（升级项 3）。POST api.tavily.com/search，key 只走环境变量。

    配置门控：env 无 TAVILY_API_KEY（未设或为空）→ RetrievalError，即无 key 不启用；
    免费档 basic search 1 credit/次（1000 credits/月），成本受控。snippet 原样透传，
    截断沿用调用方 _SNIPPET_MAX（与 bing/baidu 适配器一致）。
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RetrievalError("未配置 TAVILY_API_KEY")
    payload = {"api_key": api_key, "query": query, "max_results": _MAX_RESULTS,
               "search_depth": "basic"}
    timeout = cfg.get("fetch_timeout_seconds", 10)
    async with httpx.AsyncClient(timeout=timeout, transport=_transport) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
    resp.raise_for_status()
    data = resp.json()
    results: list[dict] = []
    for item in (data.get("results") or [])[:_MAX_RESULTS]:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        results.append({"title": title, "url": item.get("url", ""),
                        "snippet": item.get("content", "")})
    return results


SEARCH_ADAPTERS = {
    "baidu": _baidu_search,
    "bing": _bing_search,
    "google": _google_search,
    "duckduckgo": _duckduckgo_search,
    "tavily": _tavily_search,
}


async def web_search(query: str, engine: str, cfg: dict, _transport=None) -> list[dict]:
    adapter = SEARCH_ADAPTERS.get(engine)
    if adapter is None:
        raise RetrievalError(f"未知搜索引擎: {engine}")
    return await adapter(query, cfg, _transport=_transport)
