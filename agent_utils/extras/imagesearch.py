#!/usr/bin/env python3
"""imagesearch.py — 必应图搜纯检索（murl 直链提取 + UA + 拒链过滤）。

纯 urllib，零第三方依赖。机制层：只返回候选图 URL 列表；
搜索词 / 拒链黑名单等业务语义由调用方传入（域语义留域，不进共享库）。

合并了两段近乎相同的必应图搜实现（2026-10-18）：取首张 vs 取多张。
"""
import re
import urllib.parse
import urllib.request

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def bing_image_search(query: str, n: int = 10, reject: list[str] | None = None,
                      suffix: str = "", ua: str = DEFAULT_UA,
                      timeout: int = 20, fallback_keep: int = 2) -> list[str]:
    """必应图库搜索 → 候选图直链列表（≤ n）。

    query   搜索词（域语义，调用方给）
    suffix  追加词（如「 风景」，域语义，调用方给；缺省空）
    reject  域名黑名单子串列表（如 ["gettyimages"]），命中即弃；None/空 = 不过滤
    n       候选上限
    fallback_keep  非直链（无图片扩展名结尾）最多保留条数——直链优先，
                   非直链仅作兜底（原 model-pic 语义：len<2 才收）
    网络 / 解析失败 → 返回 []（不抛，调用方走兜底链）。
    """
    q = urllib.parse.quote((query or "") + suffix)
    url = "https://www.bing.com/images/search?q=%s&qft=+filterui:photo-photo" % q
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:
        return []
    raw = re.findall(r'murl&quot;:&quot;(.*?)&quot;', html)
    if not raw:
        raw = re.findall(r'"murl":"(.*?)"', html)
    reject = [r.lower() for r in (reject or [])]
    out: list[str] = []
    for u in raw:
        u = u.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")
        if not u.lower().startswith("http"):
            continue
        if any(r in u.lower() for r in reject):
            continue
        if u.lower().endswith(_IMAGE_EXTS):
            out.append(u)
        elif sum(1 for x in out if not x.lower().endswith(_IMAGE_EXTS)) < fallback_keep:
            out.append(u)
        if len(out) >= n:
            break
    return out
