from agent_utils.text import utf8_bytes, split_by_bytes


def test_utf8_bytes():
    assert utf8_bytes("") == 0
    assert utf8_bytes("你好abc") == 9  # 3+3+1+1+1


def test_split_by_bytes_no_cut():
    assert split_by_bytes("你好世界", limit=100) == ["你好世界"]


def test_split_by_bytes_at_limit():
    assert split_by_bytes("你好", limit=6) == ["你好"]


def test_split_by_bytes_never_splits_a_char():
    parts = split_by_bytes("你好" * 800, limit=2000)
    assert all(utf8_bytes(p) <= 2000 for p in parts)
    assert len(parts) > 1
    assert "".join(parts) == "你好" * 800


def test_utf8_bytes_none():
    assert utf8_bytes(None) == 0


def test_split_by_bytes_none():
    assert split_by_bytes(None) == []


def test_utf8_bytes_mixed_ascii_cjk():
    assert utf8_bytes("a你") == 4


def test_split_by_bytes_empty():
    assert split_by_bytes("") == []


def test_split_by_bytes_default_limit_keeps_short_text_whole():
    assert split_by_bytes("a" * 1799) == ["a" * 1799]


def test_split_by_bytes_default_limit_splits_over_1800():
    assert split_by_bytes("a" * 2500) == ["a" * 1800, "a" * 700]


# ── 语义分段（0.4.0）──

import re as _re


def _nospace(s):
    return _re.sub(r"\s+", "", s)


def test_split_by_bytes_none_and_blank():
    assert split_by_bytes(None) == []
    assert split_by_bytes("") == []
    assert split_by_bytes("   \n ") == []


def test_split_by_bytes_short_text_unchanged():
    assert split_by_bytes("你好世界") == ["你好世界"]


def test_split_by_bytes_paragraph_boundary_preferred():
    a, b = "a" * 1000, "b" * 1000
    out = split_by_bytes(a + "\n\n" + b)
    assert out == [a, b]


def test_split_by_bytes_sentence_boundary_when_paragraph_too_long():
    text = "甲乙丙丁戊己庚辛壬癸。" * 100
    out = split_by_bytes(text)
    assert len(out) > 1
    assert all(p.endswith("。") for p in out)


def test_split_by_bytes_never_exceeds_hard_limit():
    out = split_by_bytes("字" * 2000)
    assert all(len(p.encode()) <= 2048 for p in out)


def test_split_by_bytes_no_punctuation_over_hard_limit():
    out = split_by_bytes("啊" * 1000)
    assert [len(p.encode()) for p in out] == [1800, 1200]
    assert _nospace("".join(out)) == "啊" * 1000


def test_split_by_bytes_quote_span_not_broken():
    text = "「" + "很长的台词。" * 110 + "」"
    out = split_by_bytes(text)
    assert len(out) == 1
    assert out[0].startswith("「") and out[0].endswith("」")


def test_split_by_bytes_media_line_intact():
    out = split_by_bytes("a" * 1900 + "\n\nMEDIA:/tmp/a.png")
    assert any("MEDIA:/tmp/a.png" in p for p in out)


def test_split_by_bytes_media_only_text():
    assert split_by_bytes("MEDIA:/tmp/a.png") == ["MEDIA:/tmp/a.png"]
    assert split_by_bytes("MEDIA:/a.png\nMEDIA:/b.png") == ["MEDIA:/a.png\nMEDIA:/b.png"]


def test_split_by_bytes_trailing_blank_line():
    assert split_by_bytes("短文本\n\n\n") == ["短文本"]


def test_split_by_bytes_exact_1800_and_1801():
    assert split_by_bytes("a" * 1800) == ["a" * 1800]
    assert split_by_bytes("a" * 1801) == ["a" * 1801]
    assert split_by_bytes("a" * 2049) == ["a" * 1800, "a" * 249]


def test_split_by_bytes_single_atom_between_limit_and_hard_limit_kept_whole():
    text = "长" * 632 + "。"
    assert split_by_bytes(text) == [text]


def test_split_by_bytes_limit_gt_hard_limit_clamped():
    out = split_by_bytes("字" * 800, limit=4096, hard_limit=2048)
    assert all(len(p.encode()) <= 2048 for p in out)


def test_split_by_bytes_pieces_join_to_original():
    text = "第一段。" * 500 + "\n\n" + "a" * 1000 + "\n\nMEDIA:/tmp/x.png"
    out = split_by_bytes(text)
    assert _nospace("".join(out)) == _nospace(text)
