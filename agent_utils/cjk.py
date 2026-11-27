"""cjk.py — 中文断句 / 分段 / 引号工具。

纯函数、stdlib-only：无 IO、无网络、无副作用。
"""
import re


# ===== 微信发送安全拆分 =====
# 微信单条硬限 2048 字节 UTF-8 ≈ 680 汉字；安全线 500 字/条（留余量）。


def split_sentences(text: str | None) -> list[str]:
    """按句末标点切成完整句子数组（保留标点与句内换行）。末尾残句剔除。"""
    text = text or ""
    parts = re.split(r"(?<=[。！？!?…])", text)
    sentences = [p.strip(" \t") for p in parts if p.strip()]
    sentences = [s.strip("\n") for s in sentences if s.strip()]
    if sentences and not re.search(r"[。！？!?…]$", sentences[-1].rstrip()):
        sentences = sentences[:-1]
    return sentences


def chunk_by_sentence(sentences: list[str] | None, max_len: int = 500) -> list[str]:
    """把完整句子聚成 ≤max_len 的段：尽量装满，逼近上限时在上一句句末切开。

    段内保留换行（气泡内排版）；不是一句一段——只有超长才多段。"""
    sentences = sentences or []
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if not cur:
            cur = s
            continue
        candidate = cur + "\n" + s
        if len(candidate) <= max_len:
            cur = candidate
        else:
            chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def split_for_weixin(text: str | None, max_len: int = 500) -> list[str]:
    """微信发送安全拆分入口：超长文本拆成 ≤max_len 的多条，绝不破句、不毁段落。

    - 短文本（≤max_len）→ 单条列表：[text]
    - 长文本 → 先按空行（\\n\\n）切段落、按段落整体聚块，段落间空行原样保留；
      单独一段仍超限 → 退回段内按句末标点聚段（绝不破句）
    - 无完整句子可提时（全是残句/无标点）→ 硬切兜底（在字数阈值处切），
      总比被微信 2048 截断好
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    paras = [p for p in text.split("\n\n") if p.strip()] or [text]
    chunks: list[str] = []
    cur = ""
    for para in paras:
        if len(para) <= max_len:
            candidate = para if not cur else cur + "\n\n" + para
            if len(candidate) <= max_len:
                cur = candidate
                continue
            chunks.append(cur)
            cur = para
            continue
        # 单段落本身超限：段落间结构无涉，段内退回句末标点聚段（绝不破句）
        if cur:
            chunks.append(cur)
            cur = ""
        sentences = split_sentences(para)
        sub = chunk_by_sentence(sentences, max_len) if sentences else []
        if sub:
            chunks.extend(sub)
            continue
        # 兜底硬切（在 max_len 处就近找逗号/空格断，找不到就硬切）
        buf = para
        while buf:
            if len(buf) <= max_len:
                chunks.append(buf)
                break
            window = buf[: max_len + 50]
            cut = -1
            for mark in ("。", "！", "？", "；", "…", "，", "、", "\n", " "):
                cut = max(cut, window.rfind(mark))
            # 就近断点可能落在 max_len 之后（搜索窗口 max_len+50）：钳到 <=max_len 兑现契约
            if cut < max_len // 3 or cut >= max_len:
                cut = max_len - 1
            # 注：断点两侧空白被 strip/lstrip 丢弃，空格分隔的纯 ASCII 长串无法逐字节回拼；
            # 对 CJK 无影响（无词间空格）。
            chunks.append(buf[: cut + 1].strip())
            buf = buf[cut + 1:].lstrip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


# ===== 引号感知断句单元 / 中文自然折行 =====
# 断句标点：句尾级（强）/ 句中级（弱）
_STRONG_END = "。！？；…"
_WEAK_END = "，、—,;"
_QUOTE_OPEN = {'"', "“", "「", "『"}
_QUOTE_CLOSE = {'"', "”", "」", "』"}


def split_zh_units(text: str) -> list[str]:
    """把一段中文按「断句单元」切分：引号内的强句尾（。！？；…）保持引号整体同段。

    返回的单元列表字符串拼接回 text（相邻单元在原串中是紧邻的）。规则：
    - 引号内遇句尾标点 → 不切段，继续吸纳直到碰到闭引号（一句话带引号整体）。
    - 引号外遇句尾标点 → 单元结束（含该标点）。
    - 引号外遇弱标点（，、…）→ 同样可作后备断点。
    """
    if not text:
        return []
    units = []
    buf = []
    in_quote = False
    quote_open_char = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # 先判闭引号（ASCII " 同属开/闭集合，须先走闭合）：
        # 仅在已开引号且此字符为匹配闭口时闭合
        if ch in _QUOTE_CLOSE and quote_open_char is not None:
            paired = (quote_open_char == "「" and ch == "」"
                      or quote_open_char == "『" and ch == "』"
                      or quote_open_char == "“" and ch == "”"
                      or quote_open_char == '"' and ch == '"')
            if paired:
                buf.append(ch)
                quote_open_char = None
                in_quote = False
                i += 1
                continue
        if ch in _QUOTE_OPEN:
            if quote_open_char is None:
                in_quote = True
                quote_open_char = ch
                buf.append(ch)
                i += 1
                continue
            # 已在引号内，遇不相配的开括记号 → 视为内部字面量（保持现状）
            buf.append(ch)
            i += 1
            continue
        if in_quote:
            # 引号内：句尾标点吸收不切（一句话连引号整体）
            buf.append(ch)
            i += 1
            continue
        # 引号外
        buf.append(ch)
        if ch in _STRONG_END or ch in _WEAK_END:
            units.append("".join(buf))
            buf = []
        i += 1
    if buf:
        units.append("".join(buf))
    return units


def soft_break_zh(text: str, width: int = 42) -> str:
    """长段自然断行（报卡/定场/进场共用观感）。

    对话感知：引号内句尾点会被整体吸纳——闭合引号永不甩行首。
    段落空行分隔（\\n\\n）：微信 iLink 气泡不渲染单换行 \\n，只有空行 \\n\\n 才显示为换行。
    防空洞段：≤4 字的节拍碎行（…/……/嗯。/好了。）空格并入上一行。
    """
    text = (text or "").strip()
    if not text:
        return ""
    out = []
    for para in text.splitlines():
        line = para.strip()
        if not line:
            continue
        if len(line) <= width:
            out.append(line)
            continue
        units = split_zh_units(line)
        # 把 unit 贪心装行：能装下就装，装不下开新行
        cur = ""
        for u in units:
            if not u:
                continue
            if not cur:
                cur = u
            elif len(cur) + len(u) <= width:
                cur += u
            else:
                if cur:
                    out.append(cur)
                cur = u
        if cur:
            out.append(cur)
    # 尾部防御：任何行首悬挂明确闭合引号（」』” —” 不参与，因 ASCII “ 开闭兼用，
    # 行首 " 可能是合法开场引号）则吸收进上一行（绝对红线）。
    _AMBIGUOUS = '"'
    final = []
    for ln in out:
        while ln and ln[0] in (_QUOTE_CLOSE - {_AMBIGUOUS}) and final:
            final[-1] += ln[0]
            ln = ln[1:]
        # 节拍碎行并入：≤4 字短行（省略号/应答词）空格接上一行，防空行聚段孤立成空洞段
        if final and ln and len(ln) <= 4:
            final[-1] += " " + ln
            continue
        final.append(ln)
    # 段落空行分隔：iLink 只渲染空行（\n\n）为换行，单 \n 吃成空格
    return "\n\n".join(final)


def unify_quotes(text: str | None) -> str:
    """台词引号统一为「」：中文弯引号（“”“‘’）一律转成「」。

    ASCII 双引号（"）开闭兼用有歧义，保持原样由模型处理。
    书名号《》、括注（）、直角引号『』不受影响。
    """
    t = (text or "")
    out = []
    for ch in t:
        if ch in ("“", "‘"):
            out.append("「")
        elif ch in ("”", "’"):
            out.append("」")
        else:
            out.append(ch)
    return "".join(out)


def split_quoted(text: str | None) -> list[tuple[str, bool]]:
    """按中英引号切段：[(段文本, 是否引号内), ...]。引号段替换时跳过。

    引号成对匹配：「」/“”/英文 " / 英文 '——开引号必须遇到自己的闭引号才结束，
    中文闭引号（」”）绝不会被当成开引号。
    """
    text = text or ""
    OPEN2CLOSE = {"「": "」", "“": "”", "\"": "\"", "'": "'"}
    parts = []
    buf, in_quote, close_char = [], False, ""
    for ch in text:
        if not in_quote and ch in OPEN2CLOSE:
            if buf:
                parts.append(("".join(buf), False))
                buf = []
            in_quote, close_char = True, OPEN2CLOSE[ch]
            buf.append(ch)
        elif in_quote and ch == close_char:
            buf.append(ch)
            parts.append(("".join(buf), True))
            buf, in_quote, close_char = [], False, ""
        else:
            buf.append(ch)
    if buf:
        parts.append(("".join(buf), in_quote))
    return parts


def compress_one_line(body: str, max_len: int = 48) -> str:
    """设定要点：压成一行；过长只留首句/前段，防大段灌进定场。"""
    body = re.sub(r"\s+", " ", (body or "").strip())
    if not body:
        return ""
    if len(body) <= max_len:
        return body
    cut = re.split(r"[。！？；\n]", body, maxsplit=1)[0].strip()
    body = (cut or body[:max_len]).strip(" ，,、")
    if len(body) > max_len:
        body = body[:max_len].rstrip(" ，,、")
    return body


# ===== 中文数量解析 =====
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def parse_count(text: str | None) -> int:
    """解析数量：「3张 / 两张 / 几张 / 几个」。未指明 → 1；「几」→ 3；上限 9。

    中文数量解析，供图类入口共用（2026-10-18 新增）。
    """
    text = text or ""
    m = re.search(r"(\d+)\s*[张个条段]", text)
    if m:
        return max(1, min(9, int(m.group(1))))
    m = re.search(r"([一两二三四五六七八九十])\s*[张个条段]", text)
    if m:
        return max(1, min(9, _CN_NUM.get(m.group(1), 1)))
    if "几" in text:
        return 3
    return 1
