from agent_utils.extras.io import write_json_atomic, write_text_atomic


def test_write_json_atomic(tmp_path):
    p = tmp_path / "a.json"
    write_json_atomic(str(p), {"x": "你好"})
    import json
    assert json.loads(p.read_text(encoding="utf-8")) == {"x": "你好"}


def test_write_json_atomic_missing_dir(tmp_path):
    p = tmp_path / "sub" / "b.json"
    write_json_atomic(str(p), {"n": 1})
    assert p.exists()


def test_write_text_atomic(tmp_path):
    p = tmp_path / "a.txt"
    write_text_atomic(str(p), "你好")
    assert p.read_text(encoding="utf-8") == "你好"


def test_write_json_atomic_indent_and_unicode(tmp_path):
    p = tmp_path / "b.json"
    write_json_atomic(str(p), {"k": "中文"}, indent=4)
    raw = p.read_text(encoding="utf-8")
    assert "中文" in raw
    assert '\n    "k"' in raw


def test_write_text_atomic_overwrite(tmp_path):
    p = tmp_path / "a.txt"
    write_text_atomic(str(p), "old")
    write_text_atomic(str(p), "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_write_text_atomic_missing_dir(tmp_path):
    p = tmp_path / "sub" / "a.txt"
    write_text_atomic(str(p), "x")
    assert p.read_text(encoding="utf-8") == "x"
