"""test_extras_imagesearch.py — 必应图搜纯检索（全 mock，零真网）。"""
from unittest import mock

from agent_utils.extras import imagesearch


def _html(murls, quoted=True):
    if quoted:
        return "".join('murl&quot;:&quot;%s&quot;' % m for m in murls)
    return "".join('"murl":"%s"' % m for m in murls)


class _Resp:
    def __init__(self, text):
        self._b = text.encode("utf-8")

    def read(self):
        return self._b


def _patch_html(monkeypatch, html):
    monkeypatch.setattr(imagesearch.urllib.request, "urlopen",
                        lambda req, timeout=20: _Resp(html))


class TestBingImageSearch:
    def test_extracts_murl_quoted(self, monkeypatch):
        _patch_html(monkeypatch, _html(["http://a.com/1.jpg", "http://b.com/2.png"]))
        out = imagesearch.bing_image_search("西湖")
        assert out == ["http://a.com/1.jpg", "http://b.com/2.png"]

    def test_extracts_murl_unquoted_fallback(self, monkeypatch):
        _patch_html(monkeypatch, _html(["http://a.com/1.jpg"], quoted=False))
        assert imagesearch.bing_image_search("西湖") == ["http://a.com/1.jpg"]

    def test_unescapes_url(self, monkeypatch):
        _patch_html(monkeypatch, _html([r"http:\/\/a.com\/x.jpg?a=1\u0026b=2&amp;c=3"]))
        out = imagesearch.bing_image_search("x")
        assert out == ["http://a.com/x.jpg?a=1&b=2&c=3"]

    def test_reject_list_filtered(self, monkeypatch):
        _patch_html(monkeypatch, _html([
            "http://gettyimages.com/1.jpg", "http://ok.com/2.jpg"]))
        out = imagesearch.bing_image_search("x", reject=["gettyimages"])
        assert out == ["http://ok.com/2.jpg"]

    def test_non_http_dropped(self, monkeypatch):
        _patch_html(monkeypatch, _html(["ftp://x/1.jpg", "http://ok.com/2.jpg"]))
        assert imagesearch.bing_image_search("x") == ["http://ok.com/2.jpg"]

    def test_non_direct_link_capped_by_fallback_keep(self, monkeypatch):
        _patch_html(monkeypatch, _html([
            "http://a.com/page1", "http://b.com/page2", "http://c.com/page3",
            "http://d.com/4.jpg"]))
        out = imagesearch.bing_image_search("x", n=10, fallback_keep=2)
        assert out == ["http://a.com/page1", "http://b.com/page2", "http://d.com/4.jpg"]

    def test_n_cap(self, monkeypatch):
        _patch_html(monkeypatch, _html(["http://a.com/%d.jpg" % i for i in range(10)]))
        assert len(imagesearch.bing_image_search("x", n=3)) == 3

    def test_suffix_appended(self, monkeypatch):
        seen = {}

        def fake_urlopen(req, timeout=20):
            seen["url"] = req.full_url
            return _Resp("")

        monkeypatch.setattr(imagesearch.urllib.request, "urlopen", fake_urlopen)
        imagesearch.bing_image_search("西湖", suffix=" 风景")
        assert "%20" in seen["url"]  # 「 风景」已拼进 query

    def test_network_failure_returns_empty(self, monkeypatch):
        def boom(req, timeout=20):
            raise OSError("no net")

        monkeypatch.setattr(imagesearch.urllib.request, "urlopen", boom)
        assert imagesearch.bing_image_search("x") == []

    def test_no_match_returns_empty(self, monkeypatch):
        _patch_html(monkeypatch, "<html>nothing</html>")
        assert imagesearch.bing_image_search("x") == []
