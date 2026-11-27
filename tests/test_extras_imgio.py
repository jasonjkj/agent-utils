"""test_extras_imgio.py — 图片字节 / 尺寸 / 下载 / 降采样（ffmpeg 类全 mock，零真网）。"""
import struct
import zlib

from unittest import mock

from agent_utils.extras import imgio


def _png_bytes(w=64, h=48):
    """构造最小合法 PNG 头（IHDR 宽高可读）。"""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_payload = struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    chunk = struct.pack(">I", len(ihdr_payload)) + b"IHDR" + ihdr_payload
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_payload))
    return sig + chunk


def _jpeg_bytes(w=32, h=24):
    """构造最小 JPEG：SOI + SOF0（宽高可读）。"""
    sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", h, w) + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xd9"


class TestLooksLikeImage:
    def test_magic_bytes(self):
        assert imgio.looks_like_image(b"\xff\xd8\xff\xe0....")
        assert imgio.looks_like_image(b"\x89PNG\r\n\x1a\n....")
        assert imgio.looks_like_image(b"RIFFxxxxWEBP")
        assert imgio.looks_like_image(b"GIF89a")
        assert imgio.looks_like_image(b"BMxx")

    def test_rejects_html_and_empty(self):
        assert not imgio.looks_like_image(b"<html><body>")
        assert not imgio.looks_like_image(b"")
        assert not imgio.looks_like_image(None)


class TestRealImageAndDims:
    def test_png_dims(self, tmp_path):
        p = tmp_path / "a.png"
        p.write_bytes(_png_bytes(640, 480))
        assert imgio.is_real_image(str(p))
        assert imgio.quick_dims(str(p)) == (640, 480)
        assert imgio.min_dim_ok(str(p), 100)
        assert not imgio.min_dim_ok(str(p), 1000)

    def test_jpeg_dims(self, tmp_path):
        p = tmp_path / "a.jpg"
        p.write_bytes(_jpeg_bytes(320, 200))
        assert imgio.is_real_image(str(p))
        assert imgio.quick_dims(str(p)) == (320, 200)

    def test_unreadable_is_not_real_and_dims_none(self, tmp_path):
        p = tmp_path / "nope.jpg"
        assert not imgio.is_real_image(str(p))
        assert imgio.quick_dims(str(p)) is None
        # 解析不了 → min_dim_ok 放行（不拦语义）
        assert imgio.min_dim_ok(str(p), 100)

    def test_html_not_image(self, tmp_path):
        p = tmp_path / "x.jpg"
        p.write_bytes(b"<html>error</html>" * 100)
        assert not imgio.is_real_image(str(p))


class TestDownloadImage:
    def test_size_gate(self, tmp_path, monkeypatch):
        import urllib.request as ur
        class R:
            def __init__(self, b): self._b = b
            def read(self): return self._b
        monkeypatch.setattr(ur, "urlopen", lambda req, timeout=15: R(b"x" * 100))
        dst = tmp_path / "a.jpg"
        assert not imgio.download_image("http://x/a.jpg", str(dst), min_bytes=40000,
                                        check_magic=False)
        assert not dst.exists()

    def test_magic_gate(self, tmp_path, monkeypatch):
        import urllib.request as ur
        class R:
            def __init__(self, b): self._b = b
            def read(self): return self._b
        monkeypatch.setattr(ur, "urlopen",
                            lambda req, timeout=15: R(b"<html>" + b"x" * 50000))
        dst = tmp_path / "b.jpg"
        assert not imgio.download_image("http://x/b.jpg", str(dst), min_bytes=1000)
        assert not dst.exists()

    def test_success_writes_file(self, tmp_path, monkeypatch):
        import urllib.request as ur
        payload = b"\xff\xd8\xff" + b"x" * 50000
        class R:
            def read(self): return payload
        monkeypatch.setattr(ur, "urlopen", lambda req, timeout=15: R())
        dst = tmp_path / "c.jpg"
        assert imgio.download_image("http://x/c.jpg", str(dst), min_bytes=1000)
        assert dst.read_bytes() == payload

    def test_network_failure_false(self, tmp_path, monkeypatch):
        import urllib.request as ur
        def boom(req, timeout=15):
            raise OSError("no net")
        monkeypatch.setattr(ur, "urlopen", boom)
        assert not imgio.download_image("http://x/d.jpg", str(tmp_path / "d.jpg"))


class TestFfmpegWrappers:
    def test_downscale_to_b64(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kw):
            out = cmd[-1]
            with open(out, "wb") as f:
                f.write(b"\xff\xd8\xff-fake-jpeg")
            return mock.Mock(returncode=0)
        monkeypatch.setattr(imgio.subprocess, "run", fake_run)
        src = tmp_path / "in.jpg"
        src.write_bytes(b"\xff\xd8\xffsrc")
        out = imgio.downscale_to_b64(str(src), 512, 6)
        assert out.startswith("data:image/jpeg;base64,")
        import base64
        assert base64.b64decode(out.split(",", 1)[1]) == b"\xff\xd8\xff-fake-jpeg"

    def test_downscale_bytes_success(self, monkeypatch):
        def fake_run(cmd, **kw):
            with open(cmd[-1], "wb") as f:
                f.write(b"scaled")
            return mock.Mock(returncode=0)
        monkeypatch.setattr(imgio.subprocess, "run", fake_run)
        assert imgio.downscale_bytes(b"orig", (720, 1280)) == b"scaled"

    def test_downscale_bytes_failure_falls_back(self, monkeypatch):
        def boom(cmd, **kw):
            raise RuntimeError("ffmpeg dead")
        monkeypatch.setattr(imgio.subprocess, "run", boom)
        assert imgio.downscale_bytes(b"orig", (720, 1280)) == b"orig"

    def test_aspect_size_portrait(self, monkeypatch):
        monkeypatch.setattr(imgio.subprocess, "run",
                            lambda cmd, **kw: mock.Mock(stdout="720,1280\n"))
        assert imgio.aspect_size("x.jpg", 2560) == "1440x2560"

    def test_aspect_size_landscape(self, monkeypatch):
        monkeypatch.setattr(imgio.subprocess, "run",
                            lambda cmd, **kw: mock.Mock(stdout="2560,1280\n"))
        assert imgio.aspect_size("x.jpg", 2560) == "2560x1280"

    def test_aspect_size_failure_fallback(self, monkeypatch):
        def boom(cmd, **kw):
            raise RuntimeError("no ffprobe")
        monkeypatch.setattr(imgio.subprocess, "run", boom)
        assert imgio.aspect_size("x.jpg") == "1920x2560"
