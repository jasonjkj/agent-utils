"""markdown.py — markdown → 纯文本 / 块切分（纯函数、stdlib-only）。"""
import re
from collections.abc import Callable


_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_RULE_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_FENCE_RE = re.compile(r"^```([^\n`]*)\s*$")

# 微信渲染只认空行（\n\n）为换行；单 \n 收成空格。出口统一归一化。
_WEIXIN_NEWLINE_NORMALIZE_ENABLED = True


def md_to_text(text: str | None) -> str:
    """企业微信 text 消息只支持纯文本，不支持 markdown，出口统一剥 md。

    剥掉常见 md 标记：代码块/行内代码/粗体/斜体/删除线/链接/图片/标题/引用/分隔线。
    保留列表符号（- / 1.）与表格竖线——纯文本下仍可读。
    """
    if not text:
        return ""
    # 代码块围栏 ```lang ... ``` → 保留内容、去围栏
    text = re.sub(r"```[^\n]*\n?([\s\S]*?)```", r"\1", text)
    # 图片 ![alt](url) → alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 链接 [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # 行内代码 `x` → x
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    # 粗体 **x** → x（先双星再单星，避免残留）
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    # 斜体 *x* → x
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    # 删除线 ~~x~~ → x
    text = re.sub(r"~~([^~\n]+)~~", r"\1", text)
    # 标题 #/##/### 行首标记
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    # 引用 > 行首标记
    text = re.sub(r"^>\s?", "", text, flags=re.M)
    # 分隔线（纯 --- 行）→ 空行
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.M)
    # 收尾：清理剥 md 后产生的多余空行（连续 3 行以上 → 2 行）
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _walk_markdown_lines(content: str):
    """Yield ``(rstripped line, is_fence, in_code_block)`` per line; ``in_code_block`` is the state *before* a fence toggles it."""
    in_code_block = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        is_fence = bool(_FENCE_RE.match(line.strip()))
        yield line, is_fence, in_code_block
        if is_fence:
            in_code_block = not in_code_block


def normalize_markdown_blocks(content: str | None) -> str:
    """rstrip lines and collapse blank runs to one, leaving fenced code untouched."""
    content = content or ""
    result: list[str] = []
    blank_run = 0
    for line, is_fence, in_code_block in _walk_markdown_lines(content):
        if not is_fence and not in_code_block and not line.strip():
            blank_run += 1
            if blank_run <= 1:
                result.append("")
            continue
        if is_fence or not in_code_block:
            blank_run = 0
        result.append(line)
    return "\n".join(result).strip()


def normalize_newlines_for_weixin(text: str, target: str = "weixin") -> str:
    """Collapse chain: lone \\n -> \\n\\n (WeChat renders blank line only), so
    single-line-break prose becomes visible paragraphs. Idempotent: existing
    \\n\\n / multi-blank runs are untouched. target="legacy" folds blank runs back
    to single \\n for plain-text/CLI consumers."""
    if not _WEIXIN_NEWLINE_NORMALIZE_ENABLED:
        return text
    if not text:
        return text
    if target == "legacy":
        return re.sub(r"\n\n+", "\n", text)
    return re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text)


def split_markdown_blocks(content: str | None) -> list[str]:
    content = content or ""
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append("\n".join(current).strip())
            current.clear()
    for line, is_fence, in_code_block in _walk_markdown_lines(content):
        if is_fence and not in_code_block:  # opening fence starts a fresh block
            flush()
        if is_fence or in_code_block or line.strip():
            current.append(line)
        else:
            flush()
        if is_fence and in_code_block:  # closing fence ends the block
            flush()
    flush()
    return [block for block in blocks if block]


def _looks_like_chatty_line_for_weixin(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped and len(stripped) <= 48 and not line.startswith((" ", "\t")) and not stripped.startswith((">", "-", "*", "【", "#", "|"))
        and not _TABLE_RULE_RE.match(stripped) and not re.match(r"^\*\*[^*]+\*\*$", stripped) and not re.match(r"^\d+\.\s", stripped))


def should_split_short_chat_block_for_weixin(block: str) -> bool:
    """Split only chat-like multiline blocks (2-6 chatty lines, first line not a heading) into separate bubbles."""
    lines = [line for line in block.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 6:
        return False
    first = lines[0].strip()
    if _HEADER_RE.match(first) or (len(first) <= 24 and first.endswith((":", "："))):
        return False
    return all(_looks_like_chatty_line_for_weixin(line) for line in lines)


def _truncate_block(block: str, max_length: int) -> str:
    return block[:max_length]


def _greedy_pack_blocks(blocks: list[str], max_length: int, overflow: Callable[[str], str]) -> list[str]:
    """Greedily join adjacent blocks with \\n\\n while result <= max_length; flush when
    next block would exceed; a single block larger than max_length is passed to
    `overflow(block)` and its result appended."""
    out: list[str] = []
    cur = ""
    for block in blocks:
        candidate = block if not cur else cur + "\n\n" + block
        if len(candidate) <= max_length:
            cur = candidate
            continue
        if cur:
            out.append(cur)
            cur = ""
        if len(block) > max_length:
            out.append(overflow(block))
        else:
            cur = block
    if cur:
        out.append(cur)
    return out


def pack_markdown_blocks_for_weixin(content: str | None, max_length: int) -> list[str]:
    if not content:
        return []
    if len(content) <= max_length:
        return [content]

    def overflow(block: str) -> str:
        return _truncate_block(block, max_length)

    # Block extraction stays weixin-local (anchored _FENCE_RE + per-line rstrip); packing is shared.
    return _greedy_pack_blocks(split_markdown_blocks(content), max_length, overflow=overflow)
