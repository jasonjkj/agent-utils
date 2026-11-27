import threading
import json
import http.server

from agent_utils.extras.notify import render, send_text


def test_render_known_type():
    out = render("health", "标题", "正文", now="2026-10-13 08:00:00")
    assert "【健康体检】标题" in out
    assert "🕐 时间：2026-10-13 08:00:00" in out
    assert "📌 类型：health" in out
    assert "正文" in out


def test_render_unknown_type():
    out = render("nope", "标题", "正文", now="2026-10-13 08:00:00")
    assert "【未知】标题" in out


def _serve(errcode: int, errmsg: str):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n:
                self.rfile.read(n)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"errcode": errcode, "errmsg": errmsg}).encode())

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_send_text_ok():
    srv = _serve(0, "ok")
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        ok, detail = send_text(url, "你好")
        assert ok is True and detail == "ok"
    finally:
        srv.shutdown()


def test_send_text_errcode():
    srv = _serve(93000, "bad")
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        ok, detail = send_text(url, "你好")
        assert ok is False and "93000" in detail
    finally:
        srv.shutdown()


def test_send_text_empty_returns_false():
    assert send_text("http://x", "   ") == (False, "空内容")


def test_send_text_none_returns_false():
    assert send_text("http://x", None) == (False, "空内容")


def test_send_text_network_fail_returns_false():
    ok, detail = send_text("http://127.0.0.1:1/", "你好", timeout=2)
    assert ok is False and detail


def _capture_server(errcode: int = 0):
    captured: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            captured["payload"] = self.rfile.read(n) if n else b""
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"errcode": errcode, "errmsg": "ok"}).encode())

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, captured


def test_send_text_truncates_long_ascii_to_byte_limit():
    srv, captured = _capture_server()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        ok, _ = send_text(url, "a" * 3000)
        assert ok is True
        content = json.loads(captured["payload"].decode("utf-8"))["text"]["content"]
        assert len(content.encode("utf-8")) <= 1900
        assert content.endswith("…（超长已截断）")
    finally:
        srv.shutdown()


def test_send_text_truncates_cjk_within_byte_budget():
    srv, captured = _capture_server()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        ok, _ = send_text(url, "中" * 1000)
        assert ok is True
        content = json.loads(captured["payload"].decode("utf-8"))["text"]["content"]
        assert len(content.encode("utf-8")) <= 1900
        assert content.endswith("…（超长已截断）")
    finally:
        srv.shutdown()


def test_render_separators_and_all_types():
    out = render("error", "T", "B", now="2026-10-15 00:00:00")
    assert out.startswith("【报错异常】T")
    assert "────────────" in out
    for ntype, zh in [("system", "系统维护"), ("model", "模型状态"), ("memory", "记忆维护")]:
        assert f"【{zh}】" in render(ntype, "T", "B", now="x")


def test_send_text_strips_markdown_before_send():
    srv, captured = _capture_server()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        send_text(url, "# 标题\n**正文**")
        content = json.loads(captured["payload"].decode("utf-8"))["text"]["content"]
        assert content == "标题\n正文"
    finally:
        srv.shutdown()
