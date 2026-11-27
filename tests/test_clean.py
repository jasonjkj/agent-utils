from agent_utils.clean import ensure_heading, extract_share, strip_meta_leakage


def test_ensure_heading_multiline_prepends():
    assert ensure_heading("第一行\n第二行", "天气") == "天气：\n\n第一行\n第二行"


def test_ensure_heading_single_line_unchanged():
    assert ensure_heading("只有一行", "天气") == "只有一行"


def test_ensure_heading_idempotent():
    assert ensure_heading("天气：\n\n内容", "天气") == "天气：\n\n内容"


def test_ensure_heading_long_label_unchanged():
    assert ensure_heading("a\nb", "很长的标题很长的标题很长的标题") == "a\nb"


def test_extract_share_marker_path():
    text = "开头日记\n现在，把其中愿意分享的部分：今天很好。明天更好。"
    assert extract_share(text) == ["今天很好。\n明天更好。"]


def test_extract_share_date_placeholder():
    out = extract_share("分享给你：今天是YYYY-MM-DD。", today="2026-10-13")
    assert out == ["今天是2026-10-13。"]


def test_extract_share_fallback_original():
    text = "```\n你好\n```"
    assert extract_share(text) == [text]


def test_extract_share_empty():
    assert extract_share("") == [""]


def test_ensure_heading_none():
    assert ensure_heading(None, "天气") == ""


def test_strip_meta_leakage_removes_blacklist_lines():
    assert strip_meta_leakage("你好\n试探判定结果：未带此条\n再见") == "你好\n\n再见"


def test_strip_meta_leakage_keeps_body():
    assert strip_meta_leakage("纯戏内正文。") == "纯戏内正文。"


def test_strip_meta_leakage_falls_back_on_empty():
    assert strip_meta_leakage("试探判定结果：未带此条") == "试探判定结果：未带此条"


def test_strip_meta_leakage_empty():
    assert strip_meta_leakage("") == ""
    assert strip_meta_leakage(None) == ""


def test_strip_meta_leakage_thinking_tags():
    assert strip_meta_leakage("正文\n<think>内部推理</think>") == "正文"


def test_ensure_heading_ascii_colon_first_line():
    assert ensure_heading("Title:\nbody", "X") == "Title:\nbody"


def test_extract_share_dash_separator():
    text = "日记内容。\n\n---\n\n今天分享这件事。"
    assert extract_share(text) == ["今天分享这件事。"]


def test_extract_share_respects_max_len():
    text = "分享给你：" + "句。" * 100
    out = extract_share(text, max_len=6)
    assert len(out) > 1
    assert all(len(c) <= 6 for c in out)


def test_strip_meta_leakage_safety_and_continue_lines():
    assert strip_meta_leakage("正文\nSafety: safe\n继续\n结尾") == "正文\n\n结尾"


def test_strip_meta_leakage_think_line_only():
    assert strip_meta_leakage("正文\n</think>\n结尾") == "正文\n\n结尾"
