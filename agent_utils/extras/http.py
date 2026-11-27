#!/usr/bin/env python3
"""http.py — 共享 HTTP GET 唯一实现（避免各调用点重复复制 http_get）。

纯 urllib，零第三方依赖，失败静默返回 None。
"""
import urllib.request


def http_get(url: str, timeout: int = 15) -> str | None:
    """GET 请求，失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
