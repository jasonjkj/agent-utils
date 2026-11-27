#!/usr/bin/env python3
"""loader.py — 纯路径加载器：按显式文件路径加载 Python 模块。

只按约定把模块取出来，不登记函数、不拥有契约；调哪个公开函数由调用方决定。
"""
import importlib.util
import os
import types


def load_module(path: str, mod_name: str | None = None) -> types.ModuleType:
    """Load a Python module from an explicit file path (unique module name to
    avoid sys.modules pollution). Raises FileNotFoundError if the file is
    missing (importlib raises it)."""
    mod_name = mod_name or os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
