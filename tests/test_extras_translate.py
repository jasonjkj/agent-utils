"""test_extras_translate.py — 通用翻译 API（零真网：全 mock provider/urlopen）。"""
from types import SimpleNamespace
from unittest import mock

from agent_utils.extras import translate as tr


def _urlopen_fake(body: bytes):
    return mock.patch(
        "urllib.request.urlopen",
        return_value=SimpleNamespace(read=lambda: body))


class TestMymemory:
    def test_parse_ok(self):
        body = (b'{"responseStatus":200,'
                b'"responseData":{"translatedText":"West Lake Broken Bridge"}}')
        with _urlopen_fake(body):
            assert tr._mymemory_translate("西湖断桥", "zh-CN", "en", 15) == "West Lake Broken Bridge"

    def test_non_200_returns_none(self):
        body = b'{"responseStatus":403,"responseData":{}}'
        with _urlopen_fake(body):
            assert tr._mymemory_translate("x", "zh-CN", "en", 15) is None

    def test_network_error_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            assert tr._mymemory_translate("x", "zh-CN", "en", 15) is None

    def test_bad_json_returns_none(self):
        with _urlopen_fake(b"not json"):
            assert tr._mymemory_translate("x", "zh-CN", "en", 15) is None


class TestTranslateContract:
    def test_empty_text_returns_none(self):
        assert tr.translate("  ") is None
        assert tr.translate(None) is None

    def test_default_auto_hits_mymemory(self):
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "West Lake"}):
            assert tr.translate("西湖断桥", src="zh-CN", dst="en") == "West Lake"

    def test_explicit_provider(self):
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "West Lake"}):
            assert tr.translate("西湖断桥", provider="mymemory") == "West Lake"

    def test_nonexistent_provider_returns_none(self):
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "West Lake"}):
            assert tr.translate("西湖断桥", provider="nope") is None

    def test_provider_fail_then_auto_falls_through(self):
        # 第一个 provider 失败 → auto 继续试下一个注册源
        def _good(text, src, dst, timeout):
            return "Novosibirsk Opera"

        with mock.patch.dict(tr._PROVIDERS,
                             {"broken": lambda *a: None, "good": _good}, clear=True):
            assert tr.translate("新西伯利亚", src="zh-CN", dst="en") == "Novosibirsk Opera"

    def test_all_fail_returns_none(self):
        with mock.patch.dict(tr._PROVIDERS,
                             {"a": lambda *a: None, "b": lambda *a: None}, clear=True):
            assert tr.translate("x", src="zh-CN", dst="en") is None

    def test_provider_exception_is_isolated(self):
        def _boom(text, src, dst, timeout):
            raise RuntimeError("down")

        with mock.patch.dict(tr._PROVIDERS,
                             {"a": _boom, "b": lambda *a: "ok"}, clear=True):
            assert tr.translate("x", src="zh-CN", dst="en") == "ok"


def _llm_body(content="West Lake Broken Bridge"):
    import json
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


class TestLlm:
    LLM = dict(llm_endpoint="https://example.com/v1", llm_model="m",
               llm_api_key="k")

    def test_llm_ok(self):
        with _urlopen_fake(_llm_body()):
            assert tr.translate("西湖断桥", provider="llm", **self.LLM) == "West Lake Broken Bridge"

    def test_llm_missing_params_returns_none(self):
        with _urlopen_fake(_llm_body()):
            # 缺三件套之一 → llm 不可用 → None（且不该发请求）
            assert tr.translate("西湖断桥", provider="llm",
                                llm_endpoint="x", llm_model="m") is None

    def test_llm_bad_response_returns_none(self):
        with _urlopen_fake(b'{"choices": []}'):
            assert tr.translate("西湖断桥", provider="llm", **self.LLM) is None

    def test_llm_request_error_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            assert tr.translate("西湖断桥", provider="llm", **self.LLM) is None

    def test_auto_falls_back_to_llm(self):
        # mymemory 失败 → auto 续试 llm（三件套齐全）
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: None}):
            with _urlopen_fake(_llm_body()):
                assert tr.translate("西湖断桥", src="zh-CN", dst="en", **self.LLM) == "West Lake Broken Bridge"

    def test_auto_without_llm_params_skips_llm(self):
        # 不给 llm 三件套 → auto 只用 mymemory，不发 llm 请求
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "West Lake"}):
            assert tr.translate("西湖断桥", src="zh-CN", dst="en") == "West Lake"

    def test_internal_hooks_baked_in(self):
        # hook 在内部固化、留扩展口：request 构造 / response 解析是模块内可测函数（暂不对外）
        payload = tr._llm_payload("西湖断桥", "zh-CN", "en", "m")
        assert payload["model"] == "m"
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1] == {"role": "user", "content": "西湖断桥"}
        assert tr._llm_parse({"choices": [{"message": {"content": "  West Lake  "}}]}) == "West Lake"
        assert tr._llm_parse({"choices": []}) is None

    def test_provider_list_first_wins(self):
        # 自定义优先级：列表第一个（llm）成功 → 用它，不到 fallback
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "MyMemory X"}):
            with _urlopen_fake(_llm_body()):
                assert tr.translate("西湖断桥", provider=["llm", "mymemory"], **self.LLM) == "West Lake Broken Bridge"

    def test_provider_list_fallback(self):
        # 主渠道（llm）失败 → fallback 到列表下一个（mymemory）
        with mock.patch.dict(tr._PROVIDERS, {"mymemory": lambda t, s, d, to: "West Lake"}):
            with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
                assert tr.translate("西湖断桥", provider=["llm", "mymemory"], **self.LLM) == "West Lake"
