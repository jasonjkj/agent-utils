#!/usr/bin/env python3
"""io.py — 原子写入工具（tmp 同目录 + os.replace，防 cron 中断留半截文件）。

为什么必须同目录 tmp：os.replace 不跨文件系统（跨设备会 EXDEV 失败），
所以临时文件必须和目标文件在同一目录。

用法：
    from agent_utils.extras.io import write_json_atomic, write_text_atomic
    write_json_atomic(path, data)          # ensure_ascii=False, indent=2
    write_text_atomic(path, text)          # Markdown / 纯文本

append 类（jsonl）不用原子写：追加半截行靠读取侧容错（skip 坏行），
覆盖写才需要原子（半截 JSON 会毒死整个状态文件）。
"""
from __future__ import annotations

import json
import os
import tempfile


def _atomic_write_bytes(path: str, data: bytes) -> None:
    """核心：写临时文件 + fsync + os.replace。失败时 tmp 自动清理，目标文件不动。

    权限：继承目标已有 mode（replace 不保留原 mode）；新文件 0644，
    对齐旧 open("w") 行为（mkstemp 默认 0600 会静默收紧权限）。
    """
    dirname = os.path.dirname(os.path.abspath(path))
    os.makedirs(dirname, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-atomic-", dir=dirname)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp_path, mode)
        # 同目录 → 同文件系统 → os.replace 原子生效
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def write_json_atomic(path: str, data, indent: int = 2) -> None:
    """原子写 JSON（ensure_ascii=False）。中途被 kill 时目标文件保持旧值或不存在。"""
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    _atomic_write_bytes(path, text.encode("utf-8"))


def write_text_atomic(path: str, text: str) -> None:
    """原子写纯文本 / Markdown。"""
    _atomic_write_bytes(path, text.encode("utf-8"))
