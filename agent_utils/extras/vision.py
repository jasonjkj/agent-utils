#!/usr/bin/env python3
"""vision.py — 多模态读图 / 读视频机制（降采样 → base64 → POST → 取文本）。

纯 stdlib（urllib + ffmpeg subprocess），零第三方依赖。**机制层**：
endpoint / model / api_key / 参数全部由调用方传入——配置与密钥留在调用方，
本库不持有、不读取任何 key 与环境变量。

原实现依赖 requests，此处按 stdlib-only 约束以 urllib 重写（2026-10-18）。
"""
import base64
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

from .imgio import downscale_to_b64

_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm")


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True, capture_output=True)


def video_frames(video: str, n: int = 3) -> list[str]:
    """ffmpeg 均匀抽 n 帧 → 临时 jpg 路径列表（调用方负责删除）。"""
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video],
        check=True, capture_output=True, text=True).stdout.strip()
    dur = float(dur)
    frames = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        try:
            _ffmpeg(["-ss", str(t), "-i", video, "-frames:v", "1", "-q:v", "4", tmp.name])
            frames.append(tmp.name)
        except Exception:
            os.unlink(tmp.name)
            continue
    return frames


def vision_describe(path: str, prompt: str, *, endpoint: str, model: str,
                    api_key: str, max_side: int = 512, quality: int = 6,
                    max_tokens: int = 400, temperature: float = 0.2,
                    thinking: dict | None = None, system: str = "",
                    timeout: int = 60, frames: int = 3) -> str:
    """读图 / 读视频，返回 assistant 文本。

    path 为视频扩展名时抽 frames 帧上传，否则单图降采样上传。
    失败（网络 / HTTP 非 200 / 结构异常）抛异常——fail-open 还是 fail-closed 由调用方定
    （门控 / 守卫类调用方应选 fail-closed：拿不到判断依据时按不通过处理）。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    is_video = os.path.splitext(path)[1].lower() in _VIDEO_EXTS

    tmp_frames: list[str] = []
    try:
        items = []
        if is_video:
            tmp_frames = video_frames(path, frames)
            sources = tmp_frames
        else:
            sources = [path]
        for src in sources:
            items.append({"type": "image_url",
                          "image_url": {"url": downscale_to_b64(src, max_side, quality)}})
        items.append({"type": "text", "text": prompt})

        payload = {
            "model": model,
            "temperature": temperature,
            "thinking": thinking if thinking is not None else {"type": "disabled"},
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": items},
            ],
        }
        req = urllib.request.Request(
            endpoint, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % api_key})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="replace")
            except Exception:
                pass
            raise RuntimeError("vision HTTP %s: %s" % (e.code, body[:300])) from e
        return (resp["choices"][0]["message"].get("content") or "").strip()
    finally:
        for p in tmp_frames:
            try:
                os.unlink(p)
            except OSError:
                pass
