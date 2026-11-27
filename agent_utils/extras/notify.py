#!/usr/bin/env python3
"""notify.py — 通知渲染 + 企业微信 webhook 发送。

渲染统一通知格式；发送只做「机械发送」：webhook HTTP 封装 + 错误码识别，
发送前统一剥 markdown（企业微信 text 消息只支持纯文本）。webhook URL 由调用方传入。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime

from ..markdown import md_to_text
from ..text import utf8_bytes

DEFAULT_TIMEOUT = 10
# 企业微信 text 消息 content 上限约 2000 字节（utf-8），超长直接截断
MAX_CONTENT_BYTES = 1900
_TRUNCATE_MARKER = "…（超长已截断）"

TYPES_ZH = {
    "health": "健康体检",
    "error": "报错异常",
    "system": "系统维护",
    "model": "模型状态",
    "memory": "记忆维护",
    "unknown": "未知",
}

_SEP = "────────────"


def render(ntype: str, title: str, body: str, now: str | None = None) -> str:
    """统一通知格式渲染（标题 / 时间 / 类型 / 正文）。"""
    if now is None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    zh = TYPES_ZH.get(ntype, TYPES_ZH["unknown"])
    return (
        f"【{zh}】{title}\n"
        f"{_SEP}\n"
        f"🕐 时间：{now}\n"
        f"📌 类型：{ntype}\n"
        f"{_SEP}\n"
        f"{body}\n"
        f"{_SEP}"
    )


def send_text(url: str, text: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    """发一条纯文本到企业微信 webhook。

    返回 (ok, detail)：
      - ok=True  已送达
      - ok=False 未送达（空内容 / 网络失败 / 企业微信返回非 0 errcode）
    """
    content = md_to_text(text).strip()
    if not content:
        return False, "空内容"
    # 按字节截断（UTF-8 边界安全）：CJK 3 字节/字，字符数截断会超企业微信上限
    if utf8_bytes(content) > MAX_CONTENT_BYTES:
        budget = MAX_CONTENT_BYTES - utf8_bytes(_TRUNCATE_MARKER)
        truncated = content.encode("utf-8")[:budget]
        content = truncated.decode("utf-8", errors="ignore") + _TRUNCATE_MARKER

    payload = json.dumps(
        {"msgtype": "text", "text": {"content": content}}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:120]

    errcode = body.get("errcode", -1)
    if errcode == 0:
        return True, "ok"
    return False, f"errcode={errcode} {body.get('errmsg', '')}"
