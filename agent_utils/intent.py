"""intent.py — 可配置词表机械意图匹配（顺序敏感、先命中先赢）。

纯函数、stdlib-only：无 IO、无网络、无副作用。
词表 json 的读取由调用方做（如 `data/intent-words.json`），本模块只吃 rules 列表。

规则 schema（dict）：
  id       规则名（透传，便于日志/测试）
  action   命中后的动作名（透传给调用方分发）
  keywords 触发词列表，任一命中（默认 contains 语义）
  exclude  排除词列表，任一命中则本条不命中（可省略）
  match    匹配方式："contains"（默认）/ "exact"（整句strip后全等）/ "prefix"（startswith）

用途：图类入口拆分（2026-10-18 真人素材域拆分）后，旅行 / 真人两域各自入口
读各自词表做机械匹配；无命中 → None（交回主模型），词表改动只改 json 不动代码。
"""
from __future__ import annotations


def _hit(text: str, keywords: list[str], mode: str) -> bool:
    if mode == "exact":
        t = text.strip()
        return any(t == k for k in keywords)
    if mode == "prefix":
        return any(text.startswith(k) for k in keywords)
    return any(k in text for k in keywords)  # contains（默认）


def match_intent(text: str | None, rules: list[dict] | None) -> dict | None:
    """顺序扫描规则表，返回第一条「keywords 命中且 exclude 零命中」的规则（原样 dict）。

    空文本 / 空规则表 → None。规则缺 keywords 跳过。exclude 在 keywords 命中后才判。
    """
    t = text or ""
    if not t:
        return None
    for rule in rules or []:
        kws = rule.get("keywords") or []
        if not kws:
            continue
        if not _hit(t, kws, rule.get("match", "contains")):
            continue
        exc = rule.get("exclude") or []
        if any(e in t for e in exc):
            continue
        return rule
    return None
