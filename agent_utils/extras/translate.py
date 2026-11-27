"""translate.py — 通用翻译 API（机制层：免费/大模型、纯 stdlib、多 provider 可扩）。

统一契约（入参出参定死，内部实现可换可扩；只做单字段翻译，不做关联上下文）：
  translate(text: str, *, src: str = "zh-CN", dst: str = "en",
            provider: str | None = None, timeout: int = 15,
            llm_endpoint: str | None = None, llm_model: str | None = None,
            llm_api_key: str | None = None) -> str | None
  成功 → 译文（strip）；失败 → None（调用方兜底；本层静默失败、不抛异常）。

provider 参数（指定 / 调优先级 / 主+fallback）：
  None / "auto"      → 默认顺序逐个试：mymemory（免费免 key）→ llm（仅当 llm_endpoint/model/api_key 三件套齐全）
  "mymemory"/"llm"   → 只用一个（指定即用，不做 fallback）
  ["llm", "mymemory"]→ 按列表顺序试：列表第一个是主渠道，后续为 fallback（用户自定义优先级）

内置 provider：
  mymemory   MyMemory（GET /get，免 key；2026-10-19 实测 zh-CN→en 可用）
  llm        大模型翻译：**仅支持 OpenAI 兼容 chat/completions 请求格式**（endpoint/model/api_key 由调用方传，
             密钥不入库不持有；单字段 text → 译文）。
             request/response hook **在内部固化**（请求体构造 / 响应解析见 _llm_payload / _llm_parse），
             **不对外部开放参数**（当前无此需求，不做过度设计）；留扩展口——将来要外部化直接从这两个内部函数暴露。
扩展点：往 _PROVIDERS 加一个 (text, src, dst, timeout) -> str | None 的函数即可。
"""
import json
import urllib.parse
import urllib.request

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_MYMEMORY_URL = "https://api.mymemory.translated.net/get"

_LLM_SYSTEM_TMPL = "你是翻译。把{src}翻译成{dst}。只输出译文本身，不要解释、不要引号。"


def _mymemory_translate(text, src, dst, timeout):
    """MyMemory：GET /get?q=&langpair=src|dst，免 key。失败 → None。"""
    q = urllib.parse.quote(text)
    url = "%s?q=%s&langpair=%s%%7C%s" % (_MYMEMORY_URL, q, src, dst)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        data = json.loads(urllib.request.urlopen(req, timeout=timeout)
                          .read().decode("utf-8", "ignore"))
    except Exception:
        return None
    if data.get("responseStatus") != 200:
        return None
    out = (data.get("responseData") or {}).get("translatedText") or ""
    return out.strip() or None


def _llm_payload(text, src, dst, model):
    """内部固化：OpenAI 兼容请求体构造（request hook；将来外部化时从这暴露，暂不对外）。"""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM_TMPL.format(src=src, dst=dst)},
            {"role": "user", "content": text},
        ],
        "max_tokens": 128,
        "temperature": 0.2,
    }


def _llm_parse(resp):
    """内部固化：响应解析 + 清洗（response hook；将来外部化时从这暴露，暂不对外）。"""
    try:
        out = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return out.strip() or None


def _llm_translate(text, src, dst, timeout, endpoint, model, api_key):
    """大模型翻译：OpenAI 兼容 chat/completions（hook 内部固化，不对外）。失败 → None。"""
    payload = _llm_payload(text, src, dst, model)
    url = endpoint.rstrip("/") + "/chat/completions"
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % api_key,
                     "User-Agent": _UA})
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout)
                          .read().decode("utf-8", "ignore"))
    except Exception:
        return None
    return _llm_parse(resp)


# provider 注册表（扩展点：加一条 = 多一个翻译源；llm 为动态源，见 translate()）
_PROVIDERS = {
    "mymemory": _mymemory_translate,
}


def translate(text, *, src="zh-CN", dst="en", provider=None, timeout=15,
              llm_endpoint=None, llm_model=None, llm_api_key=None):
    """通用翻译契约：成功 → 译文；失败 → None（调用方兜底）。

    provider：None/"auto"=默认顺序；单个名字=只用它；列表=按列表顺序试（主渠道在前，fallback 在后）。
    """
    if not text or not str(text).strip():
        return None
    text = str(text).strip()
    llm_ready = bool(llm_endpoint and llm_model and llm_api_key)
    if provider in (None, "auto", ""):
        names = list(_PROVIDERS)
        if llm_ready:
            names.append("llm")
    elif isinstance(provider, (list, tuple)):
        names = list(provider)  # 用户自定义优先级：主渠道 → fallback
    else:
        names = [provider]
    for name in names:
        if name == "llm":
            if not llm_ready:
                continue
            fn = lambda t, s, d, to: _llm_translate(  # noqa: E731
                t, s, d, to, llm_endpoint, llm_model, llm_api_key)
        else:
            fn = _PROVIDERS.get(name)
        if fn is None:
            continue
        try:
            out = fn(text, src, dst, timeout)
        except Exception:
            continue
        if out:
            return out
    return None
