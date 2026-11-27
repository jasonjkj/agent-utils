import threading
import http.server

from agent_utils.extras.http import http_get


def _serve(body: bytes):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def test_http_get_ok():
    srv = _serve("你好".encode("utf-8"))
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        assert http_get(url) == "你好"
    finally:
        srv.shutdown()


def test_http_get_failure_returns_none():
    assert http_get("http://127.0.0.1:1/nope", timeout=2) is None


def test_http_get_non_utf8_bytes_ignored():
    srv = _serve(b"\xff\xfehello")
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        assert http_get(url) == "hello"
    finally:
        srv.shutdown()


def test_http_get_empty_body_returns_empty_string():
    srv = _serve(b"")
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        assert http_get(url) == ""
    finally:
        srv.shutdown()
