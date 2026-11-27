from agent_utils.markdown import (
    md_to_text,
    normalize_markdown_blocks,
    split_markdown_blocks,
    should_split_short_chat_block_for_weixin,
    normalize_newlines_for_weixin,
    pack_markdown_blocks_for_weixin,
)


def test_md_to_text_code_fence():
    assert md_to_text("```python\nprint(1)\n```") == "print(1)"


def test_md_to_text_bold_code_link():
    assert md_to_text("**粗体** 和 `code` 见 [链接](https://x)") == "粗体 和 code 见 链接"


def test_md_to_text_image():
    assert md_to_text("![图](img.png)") == "图"


def test_md_to_text_headings():
    assert md_to_text("# 标题\n\n正文") == "标题\n\n正文"


def test_md_to_text_hr_becomes_empty():
    assert md_to_text("---") == ""


def test_md_to_text_blank_collapse():
    assert md_to_text("a\n\n\n\nb") == "a\n\nb"


def test_md_to_text_empty():
    assert md_to_text("") == ""
    assert md_to_text(None) == ""


def test_normalize_markdown_blocks_collapses_blank_runs():
    assert normalize_markdown_blocks("a\n\n\n\nb") == "a\n\nb"


def test_normalize_markdown_blocks_keeps_fence_intact():
    assert normalize_markdown_blocks("```py\n\nx\n\n```") == "```py\n\nx\n\n```"


def test_split_markdown_blocks_splits_on_blank():
    assert split_markdown_blocks("第1行\n\n第2行") == ["第1行", "第2行"]


def test_split_markdown_blocks_keeps_fence_block():
    assert split_markdown_blocks("a\n\n```py\nx\n```\n\nb") == ["a", "```py\nx\n```", "b"]


def test_should_split_short_chat_block():
    assert should_split_short_chat_block_for_weixin("你好啊\n吃了吗") is True


def test_should_not_split_heading_first():
    assert should_split_short_chat_block_for_weixin("标题：\n内容") is False
    assert should_split_short_chat_block_for_weixin("# 标题\n内容") is False


def test_normalize_newlines_weixin():
    assert normalize_newlines_for_weixin("a\nb") == "a\n\nb"
    assert normalize_newlines_for_weixin("a\n\nb") == "a\n\nb"


def test_normalize_newlines_legacy():
    assert normalize_newlines_for_weixin("a\n\nb", target="legacy") == "a\nb"


def test_pack_blocks_when_fits():
    assert pack_markdown_blocks_for_weixin("aaaa\n\nbbbb", max_length=6) == ["aaaa", "bbbb"]


def test_pack_blocks_truncates_overflow():
    assert pack_markdown_blocks_for_weixin("abcdefgh", max_length=4) == ["abcd"]


def test_normalize_markdown_blocks_none():
    assert normalize_markdown_blocks(None) == ""


def test_split_markdown_blocks_none():
    assert split_markdown_blocks(None) == []


def test_pack_blocks_none_and_empty():
    assert pack_markdown_blocks_for_weixin(None, max_length=100) == []
    assert pack_markdown_blocks_for_weixin("", max_length=100) == []


def test_md_to_text_italic_strike_quote():
    assert md_to_text("*斜* 和 ~~删~~\n>引") == "斜 和 删\n引"


def test_md_to_text_inline_code_and_link():
    assert md_to_text("`code` [文字](http://x)") == "code 文字"


def test_normalize_markdown_blocks_rstrips_and_collapses():
    assert normalize_markdown_blocks("a  \n\n\n\nb   ") == "a\n\nb"


def test_normalize_newlines_weixin_empty():
    assert normalize_newlines_for_weixin("") == ""


def test_normalize_newlines_weixin_idempotent():
    once = normalize_newlines_for_weixin("a\nb\nc")
    assert once == "a\n\nb\n\nc"
    assert normalize_newlines_for_weixin(once) == once


def test_split_markdown_blocks_empty_and_whitespace():
    assert split_markdown_blocks("") == []
    assert split_markdown_blocks("   \n\n  ") == []


def test_split_markdown_blocks_multiple_blank_collapsed():
    assert split_markdown_blocks("a\n\n\n\nb") == ["a", "b"]


def test_should_split_rejects_single_and_long():
    assert should_split_short_chat_block_for_weixin("只有一行") is False
    seven = "\n".join(f"行{i}" for i in range(7))
    assert should_split_short_chat_block_for_weixin(seven) is False


def test_should_split_rejects_markdown_shapes():
    assert should_split_short_chat_block_for_weixin("> 引用\n第二行") is False
    assert should_split_short_chat_block_for_weixin("- 项目\n第二行") is False
    assert should_split_short_chat_block_for_weixin("**加粗**\n第二行") is False


def test_pack_blocks_greedy_packs_adjacent():
    assert pack_markdown_blocks_for_weixin("aa\n\nbb\n\ncc", max_length=7) == ["aa\n\nbb", "cc"]


def test_pack_blocks_overflow_truncated_and_split():
    assert pack_markdown_blocks_for_weixin("x" * 10 + "\n\ny", max_length=4) == ["xxxx", "y"]
