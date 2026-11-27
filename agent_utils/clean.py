"""clean.py — 模型输出清洗（纯函数、stdlib-only）。"""
import re
from datetime import date

from .cjk import chunk_by_sentence, split_sentences
from .text import utf8_bytes


_META_LEAKAGE_PATTERNS = (
    # === 试探条 / 判定结果 ===
    re.compile(r"^.*试探判定结果.*$", re.MULTILINE),
    re.compile(r"^.*没带试探条.*$", re.MULTILINE),
    re.compile(r"^.*没带.*条.*$", re.MULTILINE),
    # === 钩子 / 伏笔 / 演出计划 ===
    re.compile(r"^.*3[-\s～~]?4轮.*钩子.*$", re.MULTILINE),
    re.compile(r"^.*钩子.*3[-\s～~]?4轮.*$", re.MULTILINE),
    re.compile(r"^.*埋.*钩子.*$", re.MULTILINE),
    re.compile(r"^.*钩子.*埋.*$", re.MULTILINE),
    re.compile(r"^.*钩子.*伏笔.*$", re.MULTILINE),
    re.compile(r"^.*伏笔.*试探.*$", re.MULTILINE),
    re.compile(r"^.*递进了下一步.*$", re.MULTILINE),
    re.compile(r"^.*新钩子.*$", re.MULTILINE),
    # === 自我检查 / 元评论 ===
    re.compile(r"^.*长度适中.*$", re.MULTILINE),
    re.compile(r"^.*继续[。.!！]?$", re.MULTILINE),
    re.compile(r"^.*保持戏内.*$", re.MULTILINE),
    re.compile(r"^.*纯戏内演.*$", re.MULTILINE),
    re.compile(r"^.*没有系统腔.*$", re.MULTILINE),
    re.compile(r"^.*按.*性格.*演.*$", re.MULTILINE),
    re.compile(r"^.*规则回响.*$", re.MULTILINE),
    re.compile(r"^.*铁律.*复述.*$", re.MULTILINE),
    re.compile(r"^.*别复述.*$", re.MULTILINE),
    re.compile(r"^.*无试探进行中.*$", re.MULTILINE),
    # === 安全哨 / 系统判定行（免费小模型偶发把安全评审当正文） ===
    re.compile(r"^.*[Uu]ser[ \t]*[Ss]afety[：:]?[ \t]*\w*[ \t]*$", re.MULTILINE),
    re.compile(r"^.*\b[Ss]afety[：:]?[ \t]*(safe|unsafe|ok|normal)[ \t]*$", re.MULTILINE),
    # === <think> 标签（推理模型） ===
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),
    re.compile(r"^</?think>$", re.MULTILINE | re.IGNORECASE),
)


def strip_meta_leakage(text: str | None) -> str:
    """模型输出后清洗：删掉元信息漏吐行。

    保守策略：只删高置信度黑名单行（已经在生产上观察到的漏吐模式），
    不做 NLP 分类。删除后空行也清掉；如果全删空了返回原文（绝不能丢内容）。
    """
    t = (text or "").strip()
    if not t:
        return t
    cleaned = t
    for pat in _META_LEAKAGE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    # 清理多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    # 如果全删空了（说明清洗模式太激进），回退原文
    if not cleaned:
        return t
    return cleaned


def _fill_date_placeholders(text: str, today: str | None = None) -> str:
    """把模型原样吐出的 ``YYYY-MM-DD`` 占位符换成真实日期。"""
    if not text or "YYYY-MM-DD" not in text:
        return text
    return text.replace("YYYY-MM-DD", today or date.today().isoformat())


def _fence_regex():
    """匹配 ``` 代码围栏（跨行非贪婪）。"""
    return re.compile(r"```.*?```", re.DOTALL)


def _natural_share_portion(text: str) -> str:
    """定位「自然分享段」起点之后的正文。

    优先按固定标记词分界；否则取最后一个 `---` 分隔线之后；再兜底整段。
    """
    markers = [
        "现在，把其中愿意分享的部分",
        "把其中愿意分享的部分",
        "想跟你分享",
        "分享给你",
        "我想说",
        "存好了",
        "分享一部分",
        "愿意分享的部分",
    ]
    for m in markers:
        idx = text.find(m)
        if idx >= 0:
            tail = text[idx + len(m):].lstrip("：:，,。. \t\n-")
            if tail:
                return tail

    # 无标记词：取最后一个 --- 分隔之后（模型常在日记后隔行写自然分享）
    splits = re.split(r"(?m)^\s*-{3,}\s*$", text)
    if len(splits) > 1:
        tail = splits[-1].strip(" \t\n-")
        if tail:
            return tail

    return text


def ensure_heading(text: str | None, label: str, max_label_bytes: int = 24) -> str:
    """Prepend `label：\\n\\n` for multi-line text that WeChat might split into
    separate short-chat bubbles — unless the text already carries a heading
    (first non-empty line ends with '：' or ':'), the label is too long, or the
    text is single-line. Idempotent: never double-prepends."""
    text = text or ""
    t = text.strip()
    if not t or "\n" not in t:
        return text
    first = next((ln for ln in t.splitlines() if ln.strip()), "").strip()
    if first.endswith(("：", ":")):
        return text
    if utf8_bytes(label) > max_label_bytes:
        return text
    return f"{label}：\n\n{text}"


def extract_share(text: str, max_len: int = 500, today: str | None = None) -> list[str]:
    """从模型的完整输出中提取「自然分享」片段，返回**数组**（一项一条可发送消息）。

    1. 剥离 markdown 代码围栏（``` ... ```）
    2. 只取「自然分享」段（标记词 / `---` 分隔之后）
    3. 按完整句子边界打包（≤max_len 尽量装满，绝不破句）
    4. 提取不了 → fallback 原样输出原文（内容不丢）
    """
    text = (text or "").strip()
    if not text:
        return [""]

    # 0. 生产侧日期占位符 → 真实日期（不靠模型）。today 为缺省 None 时用本机日期
    #    （date.today()，含时钟副作用）；需要确定性输出时显式传 today。
    text = _fill_date_placeholders(text, today)

    # 1. 剥离代码围栏
    cleaned = _fence_regex().sub("", text)
    cleaned = re.sub(r"`{3,}", "", cleaned)
    cleaned = re.sub(r"\n[ \t]*\n+", "\n\n", cleaned).strip()

    # 2. 定位自然分享段
    share = _natural_share_portion(cleaned)

    # 3. 句子级切分 + 按上限聚段（装满到句末，保留换行）
    sentences = split_sentences(share)
    chunks = chunk_by_sentence(sentences, max_len)
    # 能提取完整句子 → 数组；提取不了 → fallback 原样输出原文
    return chunks or [text]
