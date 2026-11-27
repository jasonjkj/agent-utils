"""text.py — 文本字节级工具（UTF-8 边界安全切分，供微信等按字节截断场景复用）。

纯函数、stdlib-only：无 IO、无网络、无副作用。
"""
from __future__ import annotations

import re

_SENT_END = "。！？!?…"
_WEAK_BREAK = "，、；,;— \n"
_QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”", "（": "）", '"': '"', "'": "'"}
_MEDIA_LINE = re.compile(r"^[ \t]*MEDIA:")
_BLANK_PARA = re.compile(r"\n[ \t]*\n+")


def utf8_bytes(s: str | None) -> int:
    return len((s or "").encode("utf-8"))


def _normalize(text: str | None) -> str:
    """CRLF/CR → LF，剥首尾空白。纯函数。"""
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return s.strip()


def _is_media_para(para: str) -> bool:
    """整段每行都是 MEDIA: 行 → True（该段整体不可切）。"""
    lines = [ln for ln in para.split("\n") if ln.strip()]
    return bool(lines) and all(_MEDIA_LINE.match(ln) for ln in lines)


def _sentences_quote_aware(block: str) -> list[str]:
    """按引号外句末标点切句；引号内不切，未闭合引号吸收到块尾。无损。"""
    out = []
    start = 0
    stack: list[str] = []
    for i, ch in enumerate(block):
        if stack:
            if ch == stack[-1]:
                stack.pop()
            continue
        closer = _QUOTE_PAIRS.get(ch)
        if closer:
            stack.append(closer)
            continue
        if ch in _SENT_END:
            out.append(block[start:i + 1])
            start = i + 1
    if start < len(block):
        out.append(block[start:])
    return [x for x in out if x]


def _weak_cut(cur: str, soft: int) -> int:
    """在 cur 的 [soft*0.6, soft] 字节窗口里找最后一个弱断点字符位置。"""
    low = int(soft * 0.6)
    best = 0
    used = 0
    for i, ch in enumerate(cur):
        used += utf8_bytes(ch)
        if used > soft:
            break
        if used >= low and ch in _WEAK_BREAK:
            best = i + 1
    return best


def _hard_cut(block: str, soft: int, hard: int) -> list[str]:
    """无标点超长块兜底：按 soft 装箱，优先弱断点；每片 ≤ soft（末块可 ≤hard）。"""
    out: list[str] = []
    cur = ""
    for ch in block:
        if utf8_bytes(cur + ch) <= soft:
            cur += ch
            continue
        cut = _weak_cut(cur, soft)
        if cut:
            out.append(cur[:cut])
            cur = cur[cut:] + ch
        else:
            out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    if len(out) >= 2 and utf8_bytes(out[-1]) <= soft:
        merged = out[-2] + out[-1]
        if utf8_bytes(merged) <= hard:
            out[-2:] = [merged]
    return [p for p in out if p]


def _atoms(text: str, soft: int, hard: int) -> list[tuple[str, str, bool]]:
    """→ [(文本, 与前一同段原子拼接用的分隔符, 是否 MEDIA 原子)]。"""
    s = _normalize(text)
    if not s:
        return []
    paras = [p for p in _BLANK_PARA.split(s) if p.strip()]
    atoms: list[tuple[str, str, bool]] = []
    first = True
    for para in paras:
        para = para.strip()
        if not para:
            continue
        sep = "" if first else "\n\n"
        first = False
        if _is_media_para(para) or utf8_bytes(para) <= soft:
            atoms.append((para, sep, _is_media_para(para)))
            continue
        for sent in _sentences_quote_aware(para):
            if utf8_bytes(sent) > hard:
                for piece in _hard_cut(sent, soft, hard):
                    atoms.append((piece, sep, False))
                    sep = ""
            else:
                atoms.append((sent, sep, False))
                sep = ""
    return atoms


def _pack(atoms: list[tuple[str, str, bool]], soft: int, hard: int) -> list[str]:
    """装箱：能装进 soft 就并入当前片；MEDIA 原子只要 ≤hard 就跟前片。"""
    out: list[str] = []
    cur = ""
    for text, sep, is_media in atoms:
        add = (sep if cur else "") + text
        if not cur:
            cur = text
            continue
        if is_media:
            if utf8_bytes(cur + add) <= hard:
                cur += add
            else:
                out.append(cur)
                cur = text
        elif utf8_bytes(cur + add) <= soft:
            cur += add
        else:
            out.append(cur)
            cur = text
    if cur:
        out.append(cur)
    return out


def split_by_bytes(text: str | None, *, limit: int = 1800,
                   hard_limit: int = 2048) -> list[str]:
    """分段投递装箱的通用纯函数（零渠道知识、零 IO、零日志）。

    - limit：装箱目标字节；hard_limit：单条绝对上限（UTF-8 边界安全）
    - 原子大于 limit 但 ≤ hard_limit 时单独成片（允许片落在 (limit, hard_limit]）
    - hard_limit < limit 时以 hard_limit 为准（不抛异常）
    - None / "" / 纯空白 → []
    """
    try:
        soft = max(1, int(limit))
        hard = max(1, int(hard_limit))
        if hard < soft:
            soft = hard
        atoms = _atoms(text, soft, hard)
        if not atoms:
            return []
        return _pack(atoms, soft, hard)
    except Exception:
        s = _normalize(text)
        return [s] if s else []
