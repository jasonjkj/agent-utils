"""test_extras_vision.py — vision 机制（降采样→base64→POST→取文本），全 mock 零真网零真 key。"""
import json
from unittest import mock

import pytest

from agent_utils.extras import vision


@pytest.fixture
def fake_b64(monkeypatch):
    monkeypatch.setattr(vision, "downscale_to_b64",
                        lambda src, side, q: "data:image/jpeg;base64,FAKE-%s" % src)


def _capture_post(monkeypatch, reply_text="OK"):
    seen = {}

    class R:
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": reply_text}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }).encode()

    def fake_urlopen(req, timeout=60):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["payload"] = json.loads(req.data.decode())
        return R()

    monkeypatch.setattr(vision.urllib.request, "urlopen", fake_urlopen)
    return seen


class TestVisionDescribe:
    def test_image_flow(self, tmp_path, monkeypatch, fake_b64):
        img = tmp_path / "a.jpg"
        img.write_bytes(b"\xff\xd8\xffx")
        seen = _capture_post(monkeypatch, "一只猫")
        out = vision.vision_describe(str(img), "这是什么", endpoint="http://ep/v1/chat",
                                     model="m1", api_key="K", max_side=256, quality=5)
        assert out == "一只猫"
        assert seen["url"] == "http://ep/v1/chat"
        assert seen["headers"]["Authorization"] == "Bearer K"
        p = seen["payload"]
        assert p["model"] == "m1"
        assert p["thinking"] == {"type": "disabled"}
        content = p["messages"][1]["content"]
        assert content[0]["type"] == "image_url"
        assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,FAKE-")
        assert content[-1] == {"type": "text", "text": "这是什么"}

    def test_video_flow_extracts_frames(self, tmp_path, monkeypatch, fake_b64):
        vid = tmp_path / "a.mp4"
        vid.write_bytes(b"fake")
        monkeypatch.setattr(vision, "video_frames",
                            lambda v, n: [str(tmp_path / "f1.jpg"), str(tmp_path / "f2.jpg")])
        seen = _capture_post(monkeypatch)
        vision.vision_describe(str(vid), "看看", endpoint="http://ep", model="m",
                               api_key="K", frames=2)
        content = seen["payload"]["messages"][1]["content"]
        imgs = [c for c in content if c["type"] == "image_url"]
        assert len(imgs) == 2

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            vision.vision_describe("/nonexistent/x.jpg", "p", endpoint="e", model="m",
                                   api_key="k")

    def test_http_error_raises_with_body(self, tmp_path, monkeypatch, fake_b64):
        import urllib.error
        img = tmp_path / "a.jpg"
        img.write_bytes(b"\xff\xd8\xffx")

        def boom(req, timeout=60):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, None)

        monkeypatch.setattr(vision.urllib.request, "urlopen", boom)
        with pytest.raises(RuntimeError, match="HTTP 400"):
            vision.vision_describe(str(img), "p", endpoint="http://ep", model="m",
                                   api_key="K")


class TestVideoFrames:
    def test_frames_uniform_and_cleanup_on_error(self, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "ffprobe":
                return mock.Mock(stdout="10.0\n")
            # ffmpeg 抽帧：第二帧模拟失败
            out = cmd[-1]
            if "-ss" in cmd and cmd[cmd.index("-ss") + 1].startswith("7.5"):
                raise RuntimeError("frame fail")
            with open(out, "wb") as f:
                f.write(b"\xff\xd8\xff")
            return mock.Mock(returncode=0)

        monkeypatch.setattr(vision.subprocess, "run", fake_run)
        frames = vision.video_frames(str(tmp_path / "v.mp4"), 2)
        assert len(frames) == 1  # 失败帧被丢弃
