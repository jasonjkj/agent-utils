from agent_utils.cjk import (
    split_sentences,
    chunk_by_sentence,
    split_for_weixin,
    split_zh_units,
    soft_break_zh,
    unify_quotes,
    split_quoted,
    compress_one_line,
    parse_count,
)


def test_split_sentences_basic():
    assert split_sentences("你好。世界！这是…测试") == ["你好。", "世界！", "这是…"]


def test_split_sentences_trailing_trailing():
    assert split_sentences("第一句。第二句。") == ["第一句。", "第二句。"]


def test_split_sentences_empty():
    assert split_sentences("") == []


def test_split_sentences_ascii_period_not_a_break():
    assert split_sentences("use pkg.json and pkg.toml") == []


def test_chunk_by_sentence_fills_then_breaks():
    assert chunk_by_sentence(["a", "b", "c"], max_len=3) == ["a\nb", "c"]


def test_chunk_by_sentence_single():
    assert chunk_by_sentence(["hello"], max_len=3) == ["hello"]


def test_split_for_weixin_short():
    assert split_for_weixin("你好世界") == ["你好世界"]


def test_split_for_weixin_empty():
    assert split_for_weixin("") == []
    assert split_for_weixin(None) == []


def test_split_for_weixin_preserves_paragraphs():
    text = "第一段。\n\n第二段。" * 40
    chunks = split_for_weixin(text, max_len=100)
    orig_paras = [p for p in text.split("\n\n") if p.strip()]
    reconstructed = []
    for c in chunks:
        reconstructed.extend(c.split("\n\n"))
    assert all(len(c) <= 100 for c in chunks)
    # 段落不被腰斩、顺序不变：每块只由完整段落组成
    assert reconstructed == orig_paras
    assert "".join(chunks).replace("\n\n", "") == text.replace("\n\n", "")


def test_split_for_weixin_hard_cut_fallback():
    text = "这是一个完全没有标点符号也没有换行的超长段落" * 50
    chunks = split_for_weixin(text, max_len=100)
    assert chunks and all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


def test_split_for_weixin_fallback_respects_max_len():
    # 唯一断点在 max_len 之后（逗号在 index 100）：兜底硬切必须仍钳到 <=max_len
    text = "字" * 100 + "，" + "字" * 100
    chunks = split_for_weixin(text, max_len=100)
    assert chunks and all(len(c) <= 100 for c in chunks)


def test_split_zh_units_basic():
    assert split_zh_units("你好。世界！") == ["你好。", "世界！"]


def test_split_zh_units_keeps_quote_whole():
    assert split_zh_units("他说：“你好。”") == ["他说：“你好。”"]


def test_split_zh_units_empty():
    assert split_zh_units("") == []


def test_soft_break_zh_empty_and_short():
    assert soft_break_zh("") == ""
    assert soft_break_zh("你好世界") == "你好世界"


def test_soft_break_zh_breaks_between_units():
    assert soft_break_zh("今天天气不错。我们出去玩吧！", width=8) == "今天天气不错。\n\n我们出去玩吧！"


def test_soft_break_zh_quote_not_split():
    assert soft_break_zh("他说“今天天气真好”，然后我们回家。", width=8) == "他说“今天天气真好”，\n\n然后我们回家。"


def test_soft_break_zh_paragraphs_with_blank_lines():
    assert soft_break_zh("第一段内容。\n\n第二段内容。") == "第一段内容。\n\n第二段内容。"


def test_unify_quotes_curly_to_bracket():
    assert unify_quotes("她说“你好”，他答‘再见’") == "她说「你好」，他答「再见」"


def test_unify_quotes_keeps_ascii_and_book_title():
    assert unify_quotes('说"hi"看《三国》') == '说"hi"看《三国》'


def test_unify_quotes_empty():
    assert unify_quotes(None) == ""


def test_split_quoted_pairs():
    assert split_quoted('他说「你好」') == [("他说", False), ("「你好」", True)]


def test_split_quoted_unclosed():
    assert split_quoted('他说「你好') == [("他说", False), ("「你好", True)]


def test_split_quoted_empty():
    assert split_quoted("") == []


def test_compress_one_line_short():
    assert compress_one_line("你好") == "你好"


def test_compress_one_line_cut_at_first_sentence():
    assert compress_one_line("今天很热。我们明天见", max_len=4) == "今天很热"


def test_compress_one_line_empty():
    assert compress_one_line("   ") == ""


def test_split_sentences_none():
    assert split_sentences(None) == []


def test_chunk_by_sentence_none():
    assert chunk_by_sentence(None) == []


def test_split_quoted_none():
    assert split_quoted(None) == []


def test_split_sentences_keeps_intra_sentence_newline():
    assert split_sentences("第一行\n还在第一句。第二句。") == ["第一行\n还在第一句。", "第二句。"]


def test_chunk_by_sentence_default_max():
    assert chunk_by_sentence(["甲。", "乙。"]) == ["甲。\n乙。"]


def test_chunk_by_sentence_empty_list():
    assert chunk_by_sentence([]) == []


def test_split_for_weixin_whitespace_only():
    assert split_for_weixin("   \n  ") == []


def test_split_for_weixin_strips_outer_whitespace():
    assert split_for_weixin("  你好世界  ") == ["你好世界"]


def test_split_zh_units_weak_punct_outside_quote_breaks():
    assert split_zh_units("甲，乙。") == ["甲，", "乙。"]


def test_split_zh_units_ascii_quote_pair_kept_whole():
    assert split_zh_units('他说"你好。"') == ['他说"你好。"']


def test_soft_break_zh_none_returns_empty():
    assert soft_break_zh(None) == ""


def test_soft_break_zh_short_rhythm_line_merges():
    assert soft_break_zh("第一段完整内容。\n\n嗯。", width=4) == "第一段完整内容。 嗯。"


def test_unify_quotes_single_curly_quotes():
    assert unify_quotes("‘好’") == "「好」"


def test_split_quoted_ascii_double_quotes():
    assert split_quoted('a"b"c') == [("a", False), ('"b"', True), ("c", False)]


def test_split_quoted_single_quotes():
    assert split_quoted("a'b'c") == [("a", False), ("'b'", True), ("c", False)]


def test_compress_one_line_none():
    assert compress_one_line(None) == ""


def test_compress_one_line_truncates_without_sentence_break():
    assert compress_one_line("字" * 100, max_len=10) == "字" * 10


class TestParseCount:
    """parse_count（2026-10-18 自 image-dispatch.py 逐字下沉）。"""

    def test_digit(self):
        assert parse_count("给我3张照片") == 3
        assert parse_count("来 10 张") == 9  # 上限 9

    def test_chinese_num(self):
        assert parse_count("两张") == 2
        assert parse_count("来三个") == 3

    def test_ji_defaults_3(self):
        assert parse_count("找几张素材库的视频") == 3

    def test_default_1(self):
        assert parse_count("给我照片") == 1
        assert parse_count("") == 1
        assert parse_count(None) == 1
