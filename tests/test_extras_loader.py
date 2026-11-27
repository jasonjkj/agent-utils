from agent_utils.extras.loader import load_module


def test_load_module(tmp_path):
    f = tmp_path / "my_engine.py"
    f.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    mod = load_module(str(f))
    assert mod.hello() == "hi"


def test_load_module_nonexistent_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_module(str(tmp_path / "nope.py"))


def test_load_module_default_name_is_basename(tmp_path):
    f = tmp_path / "my_engine.py"
    f.write_text("VALUE = 1\n", encoding="utf-8")
    assert load_module(str(f)).__name__ == "my_engine"


def test_load_module_explicit_name(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("VALUE = 2\n", encoding="utf-8")
    assert load_module(str(f), mod_name="custom_name").__name__ == "custom_name"


def test_load_module_does_not_pollute_sys_modules(tmp_path):
    import sys
    f = tmp_path / "unique_mod_xyz.py"
    f.write_text("X = 1\n", encoding="utf-8")
    load_module(str(f))
    assert "unique_mod_xyz" not in sys.modules
