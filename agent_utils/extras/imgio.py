#!/usr/bin/env python3
"""imgio.py — 图片字节 / 尺寸 / 下载 / 降采样工具。

纯 stdlib（subprocess 调 ffmpeg / ffprobe），零第三方依赖。机制层：
不含任何业务阈值语义之外的规则（MIN_DIM 等闸门值由调用方传参）。

把三处重复的图片处理代码合并成一个模块（2026-10-18）：
  验真 / 读宽高 / 最小边闸门 / 下载（带 magic-byte 校验）
  与 base64 编码 / 降采样 / 目标尺寸计算
"""
import base64
import os
import subprocess
import tempfile

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def looks_like_image(head: bytes) -> bool:
    """magic-byte 校验：JPEG / PNG / WEBP / GIF / BMP 头。head 取文件前 12 字节即可。"""
    head = head or b""
    return (head[:3] == b"\xff\xd8\xff"
            or head[:8] == b"\x89PNG\r\n\x1a\n"
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
            or head[:6] in (b"GIF87a", b"GIF89a")
            or head[:2] == b"BM")


def is_real_image(path: str) -> bool:
    """读文件头做 magic-byte 校验（防盗链 / HTML 错误页存成 .jpg）。读失败 → False。"""
    try:
        with open(path, "rb") as f:
            return looks_like_image(f.read(12))
    except OSError:
        return False


def quick_dims(path: str) -> tuple[int, int] | None:
    """轻量读宽高（PNG IHDR / JPEG SOF），解析失败返回 None（不拦截语义由调用方定）。"""
    try:
        with open(path, "rb") as f:
            data = f.read(65536)
    except OSError:
        return None
    # PNG 头判定用完整 8 字节签名（源 model-pic.py 的 `data[:3] == b"\x89PNG"` 是
    # 3 字节切片比 4 字节字面量的死比较，PNG 分支永远 False——此处修正，JPEG 分支逐字保留）。
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            seg = int.from_bytes(data[i + 2:i + 4], "big")
            if seg < 2:
                break
            i += 2 + seg
    return None


def min_dim_ok(path: str, min_dim: int = 100) -> bool:
    """最小边闸门：能解析尺寸且最小边 < min_dim → False；解析不了 → True（放行，不拦）。"""
    d = quick_dims(path)
    return d is None or min(d) >= min_dim


def download_image(url: str, dst: str, min_bytes: int = 40000,
                   ua: str = UA, timeout: int = 15, check_magic: bool = True) -> bool:
    """下载图片到 dst：大小闸门（< min_bytes 拒）+ 可选 magic-byte 校验。失败 False 不留残件。"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        data = urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        return False
    if len(data) < min_bytes:
        return False
    if check_magic and not looks_like_image(data[:12]):
        return False
    with open(dst, "wb") as f:
        f.write(data)
    return True


def downscale_to_b64(src: str, side: int, quality: int = 4) -> str:
    """ffmpeg 等比降采样（长边 ≤ side）→ base64 data-url；失败抛异常（调用方兜住）。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
             "-vf", "scale='min(%d,iw)':-2" % side, "-q:v", str(quality), tmp.name],
            check=True, capture_output=True)
        with open(tmp.name, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    finally:
        os.unlink(tmp.name)


def downscale_bytes(img_bytes: bytes, size: tuple[int, int] = (720, 1280)) -> bytes:
    """bytes 降采样到目标尺寸（ffmpeg 等比缩放 + 居中补边）。失败回退原 bytes，绝不阻塞。"""
    w, h = size
    tmp_in = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_in.close()
    tmp_out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_out.close()
    try:
        with open(tmp_in.name, "wb") as f:
            f.write(img_bytes)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", tmp_in.name,
             "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease,"
                    "pad=%d:%d:(ow-iw)/2:(oh-ih)/2" % (w, h, w, h),
             "-q:v", "4", tmp_out.name],
            check=True, capture_output=True)
        with open(tmp_out.name, "rb") as f:
            return f.read()
    except Exception:
        return img_bytes
    finally:
        for p in (tmp_in.name, tmp_out.name):
            try:
                os.unlink(p)
            except OSError:
                pass


def aspect_size(path: str, long_edge: int = 2560) -> str:
    """读图宽高（ffprobe），按比例锁长边生成 "WxH"；读取失败回退 "1920x2560"。"""
    try:
        cap = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10)
        w, h = (int(x) for x in cap.stdout.strip().split(","))
    except Exception:
        return "1920x2560"
    if w >= h:
        scale = long_edge / float(w)
        return "%dx%d" % (int(w * scale), int(h * scale))
    scale = long_edge / float(h)
    return "%dx%d" % (int(w * scale), int(h * scale))
