# agent-utils

像 lodash 一样的中文 / Agent 工具函数库——**stdlib-only、零运行时依赖**（唯一例外：`extras.retrieval` 依赖 `httpx`）。

核心是一层**纯函数**（无 IO / 无网络 / 无副作用），另带一层 **extras**（有副作用的工具）。谁需要拿谁。

- dist 名 `agent-utils`；import 名 `agent_utils`。
- 这是**纯库，没有 CLI**：只 `import`，没有命令行入口。

## 1. 定位

- 面向 Agent 生态的通用工具层：**中文文本 / CJK 断句 / markdown 化简 / 模型输出清洗**。
- `text` / `cjk` / `markdown` / `clean` 四个核心模块**纯函数、stdlib-only**，可在无网络、无文件系统权限的环境安全 import；所有副作用集中在 `extras.*`。
- 适合这样的场景：你在写一个中文场景的 Agent / 机器人，反复需要「这条回复超过微信单条上限了怎么切」「模型输出里混了 `思考中…` 这类元信息怎么洗」「中文引号不统一怎么归一」——这些是不该在每个项目里重写一遍的东西。

## 2. 安装

从源码可编辑安装（含测试依赖）：

```bash
git clone https://github.com/jasonjkj/agent-utils.git
cd agent-utils
python -m pip install -e ".[dev]"
```

也可以直接从 git 装（钉 tag）：

```bash
python -m pip install "agent-utils @ git+https://github.com/jasonjkj/agent-utils.git@v0.5.0"
```

> 唯一运行时依赖是 `httpx`，仅 `extras.retrieval` 用到；其余模块纯标准库。

## 3. 用法

```python
from agent_utils.cjk import split_for_weixin
from agent_utils.markdown import md_to_text
from agent_utils.extras.io import write_json_atomic

bubbles = split_for_weixin("很长的中文正文……", max_len=500)   # -> ["...", "..."]
plain = md_to_text("# 标题\n\n**正文**")                       # -> "标题\n\n正文"
write_json_atomic("state.json", {"k": "你好"})                 # 原子写，防半截文件
```

- 一律 `from agent_utils.<模块> import <函数>`。
- 四个核心模块可安全用于无网络 / 无文件系统权限的环境；只有 `extras.*` 触达文件 / 网络。

## 4. API / 模块参考

> 签名逐项核对源码。`stdlib` = 仅标准库；`httpx` = 唯一第三方运行时依赖。

### 核心（纯函数，stdlib-only）

**`agent_utils.text`** — 字节级文本工具

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `utf8_bytes` | `(s: str \| None) -> int` | UTF-8 字节数；`None` → `0` |
| `split_by_bytes` | `(text: str \| None, *, limit: int = 1800, hard_limit: int = 2048) -> list[str]` | 空行→句末标点→硬切三层；引号内不断、`MEDIA:` 行不切且随所属段；每片 ≤ hard_limit |

**`agent_utils.cjk`** — 中文断句 / 分段 / 引号

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `split_sentences` | `(text: str \| None) -> list[str]` | 按句末标点（`。！？!?…`）切句，保留标点与句内换行；末尾残句剔除 |
| `chunk_by_sentence` | `(sentences: list[str] \| None, max_len: int = 500) -> list[str]` | 完整句子聚成 ≤`max_len` 的段，句末切开，不破句 |
| `split_for_weixin` | `(text: str \| None, max_len: int = 500) -> list[str]` | 聊天软件安全拆分入口：先按空行切段聚块，超限退句级，再无句则硬切；每片 ≤`max_len` |
| `split_zh_units` | `(text: str) -> list[str]` | 引号感知断句单元：引号内强句尾不切，引号整体同段 |
| `soft_break_zh` | `(text: str, width: int = 42) -> str` | 长段自然折行（`\n\n` 分隔）；闭合引号不甩行首；≤4 字碎行并入上一行 |
| `unify_quotes` | `(text: str \| None) -> str` | 中文弯引号 `“”‘’` → `「」`；ASCII `"` 与《》保持原样 |
| `split_quoted` | `(text: str \| None) -> list[tuple[str, bool]]` | 按中英引号切 `(段文本, 是否引号内)`；未闭合按引号内收尾 |
| `compress_one_line` | `(body: str, max_len: int = 48) -> str` | 压成一行；过长取首句/前段，再按 `max_len` 截断 |
| `parse_count` | `(text: str \| None) -> int` | 中文数量解析：「3张 / 两张 / 几张」；未指明 → 1，「几」→ 3，上限 9 |

**`agent_utils.intent`** — 可配置词表机械意图匹配

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `match_intent` | `(text: str \| None, rules: list[dict] \| None) -> dict \| None` | 顺序扫描规则表（`keywords`/`exclude`/`match`: contains\|exact\|prefix），首条「命中且零排除」规则原样返回；无命中 → `None`（交回主模型）。词表 json 由调用方读取 |

**`agent_utils.markdown`** — markdown 化简 + 块切分

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `md_to_text` | `(text: str \| None) -> str` | 剥 markdown 标记（代码块/图片/链接/行内码/粗体/斜体/删除线/标题/引用/分隔线）；保留列表符号与表格竖线 |
| `normalize_markdown_blocks` | `(content: str \| None) -> str` | 逐行 rstrip + 连续空行折一；fenced code 原样保留 |
| `normalize_newlines_for_weixin` | `(text: str, target: str = "weixin") -> str` | 单 `\n` → `\n\n`（微信只认空行）；`target="legacy"` 反向折回单 `\n`；幂等 |
| `split_markdown_blocks` | `(content: str \| None) -> list[str]` | 按空行切块；fenced code 作为整块 |
| `should_split_short_chat_block_for_weixin` | `(block: str) -> bool` | 仅 2–6 行、首行非标题、全为聊天感的块 → `True` |
| `pack_markdown_blocks_for_weixin` | `(content: str \| None, max_length: int) -> list[str]` | 贪心打包块（`\n\n` 连接，≤`max_length`）；单块超限则截断 |

**`agent_utils.clean`** — 模型输出清洗

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `strip_meta_leakage` | `(text: str \| None) -> str` | 删模型元信息漏吐行（试探/钩子/自检/安全哨/`<think>`）；若全删空则回退原文（绝不丢内容） |
| `ensure_heading` | `(text: str \| None, label: str, max_label_bytes: int = 24) -> str` | 多行且无标题时前置 `label：\n\n`；幂等；label 超字节或单行不动 |
| `extract_share` | `(text: str, max_len: int = 500, today: str \| None = None) -> list[str]` | 剥围栏 → 定位「自然分享」段 → 句级打包；提不出回退 `[原文]`；`today` 填 `YYYY-MM-DD` 占位符 |

### extras（有副作用）

**`agent_utils.extras.io`** — 原子写入（文件，stdlib）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `write_json_atomic` | `(path: str, data, indent: int = 2) -> None` | 原子写 JSON（`ensure_ascii=False`）：同目录 tmp + fsync + `os.replace` |
| `write_text_atomic` | `(path: str, text: str) -> None` | 原子写文本 / Markdown |

**`agent_utils.extras.http`** — 静默 GET（网络，stdlib `urllib`）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `http_get` | `(url: str, timeout: int = 15) -> str \| None` | GET，UTF-8 解码（坏字节忽略）；任何失败静默返回 `None` |

**`agent_utils.extras.loader`** — 按路径加载模块（文件，stdlib）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `load_module` | `(path: str, mod_name: str \| None = None) -> types.ModuleType` | 按显式路径加载；`mod_name` 缺省取 basename；不污染 `sys.modules`；文件缺失抛 `FileNotFoundError` |

**`agent_utils.extras.notify`** — 通知渲染 + 企业微信 webhook（网络，stdlib `urllib`）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `render` | `(ntype: str, title: str, body: str, now: str \| None = None) -> str` | 统一通知格式（标题/时间/类型/正文 + 分隔线）；`ntype` 未知 → 「未知」 |
| `send_text` | `(url: str, text: str, timeout: int = 10) -> tuple[bool, str]` | 剥 md 后 POST 企业微信 webhook；按 UTF-8 字节截断到 ≤1900；返回 `(ok, detail)` |

常量：`TYPES_ZH`（类型→中文名）、`MAX_CONTENT_BYTES = 1900`、`DEFAULT_TIMEOUT = 10`。

**`agent_utils.extras.imagesearch`** — 必应图搜纯检索（网络，stdlib `urllib`）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `bing_image_search` | `(query, n=10, reject=None, suffix="", ua=..., timeout=20, fallback_keep=2) -> list[str]` | 必应图库 murl 直链提取；`reject` 域名黑名单由调用方传（域语义留域）；直链优先、非直链兜底 ≤`fallback_keep`；失败 → `[]` |

**`agent_utils.extras.imgio`** — 图片字节 / 尺寸 / 下载 / 降采样（文件 + ffmpeg subprocess，stdlib）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `looks_like_image` | `(head: bytes) -> bool` | magic-byte 校验（JPEG/PNG/WEBP/GIF/BMP） |
| `is_real_image` | `(path: str) -> bool` | 文件头 magic-byte 校验 |
| `quick_dims` | `(path: str) -> tuple[int, int] \| None` | 轻量读宽高（PNG IHDR / JPEG SOF）；失败 `None` |
| `min_dim_ok` | `(path: str, min_dim: int = 100) -> bool` | 最小边闸门；解析不了 → 放行 |
| `download_image` | `(url, dst, min_bytes=40000, ua=..., timeout=15, check_magic=True) -> bool` | 下载 + 大小闸门 + magic 校验；失败不留残件 |
| `downscale_to_b64` | `(src, side, quality=4) -> str` | ffmpeg 等比降采样 → `data:image/jpeg;base64,...`；失败抛异常 |
| `downscale_bytes` | `(img_bytes, size=(720,1280)) -> bytes` | ffmpeg 缩放 + 居中补边；失败回退原 bytes |
| `aspect_size` | `(path, long_edge=2560) -> str` | ffprobe 读宽高按比例锁长边 → `"WxH"`；失败回退 `"1920x2560"` |

**`agent_utils.extras.vision`** — 多模态读图 / 读视频机制（网络，stdlib `urllib`）

| 函数 | 签名 | 返回 / 行为 |
|---|---|---|
| `vision_describe` | `(path, prompt, *, endpoint, model, api_key, max_side=512, quality=6, max_tokens=400, ...) -> str` | 降采样 → base64 → POST OpenAI 兼容 chat/completions → 取文本；视频抽帧（ffmpeg）。**不持密钥**：endpoint/model/key 全由调用方传；失败抛异常（fail-open/closed 由调用方定） |
| `video_frames` | `(video, n=3) -> list[str]` | ffprobe 取时长 + ffmpeg 均匀抽帧 → 临时 jpg 列表 |

**`agent_utils.extras.translate`** — 通用翻译 API（网络，stdlib `urllib`）

统一契约（**单字段翻译**，不做关联上下文；成功 → 译文 `str`，失败 → `None`，本层静默失败不抛异常）：

| 名称 | 签名 | 说明 |
|---|---|---|
| `translate` | `(text, *, src="zh-CN", dst="en", provider=None, timeout=15, llm_endpoint=None, llm_model=None, llm_api_key=None) -> str \| None` | 翻译单个字符串；`provider` 三态见下；`llm_*` 三件套给大模型翻译用（OpenAI 兼容，密钥外层传、不入库） |
| `_PROVIDERS` | `dict[str, fn]` | provider 注册表（`mymemory` 内置；扩展点：加一个 `(text, src, dst, timeout) -> str\|None` 函数即可） |

`provider` 三态（**指定 / 调优先级 / 主+fallback**）：
- `None` / `"auto"` → 默认顺序：`mymemory`（免费免 key）→ `llm`（三件套齐全才启用）
- `"mymemory"` / `"llm"` → 只用一个（指定即用，不做 fallback）
- `["llm", "mymemory"]` → 按列表顺序试：**列表第一个是主渠道，后续为 fallback**（用户自定义优先级）

内置 provider：
- `mymemory` — MyMemory 免费翻译 API（免 key）
- `llm` — 大模型翻译：**仅支持 OpenAI 兼容 `chat/completions` 请求格式**（`{endpoint}/chat/completions`）；request/response hook 在内部固化（`_llm_payload` 请求构造 / `_llm_parse` 响应解析），**暂不对外、留扩展口**（将来外部化直接从这两个内部函数暴露）

示例：

```python
from agent_utils.extras import translate as tr

tr.translate("西湖断桥", src="zh-CN", dst="en")          # -> "West Lake Broken Bridge"（免费 API）
tr.translate("西湖断桥", provider="llm",                 # 只用大模型
             llm_endpoint="https://x/v1", llm_model="m", llm_api_key="k")
tr.translate("西湖断桥", provider=["llm", "mymemory"],   # LLM 主 + 免费兜底
             llm_endpoint="https://x/v1", llm_model="m", llm_api_key="k")
```

**`agent_utils.extras.retrieval`** — 只读检索（网络，**唯一导入 `httpx` 的模块**）

| 名称 | 签名 | 返回 / 行为 |
|---|---|---|
| `RetrievalError` | `Exception` 子类 | 协议 / 白名单 / 重定向 / 引擎等错误 |
| `web_fetch` | `async (url: str, cfg: dict, _transport=None) -> str` | 仅 GET、限 `http`/`https`、超时、大小上限、可选域名白名单、逐跳校验重定向；返回净化后正文 |
| `web_search` | `async (query: str, engine: str, cfg: dict, _transport=None) -> list[dict]` | 多引擎搜索，返回 `[{"title","url","snippet"}, ...]` |
| `SEARCH_ADAPTERS` | `dict` | 引擎注册表：`baidu` / `bing` / `google` / `duckduckgo` / `tavily` |

`cfg` 键（`web_fetch` / 各 adapter 读）：`fetch_timeout_seconds`（默认 10）、`fetch_max_bytes`（默认 100000）、`fetch_max_redirects`（默认 5）、`domain_whitelist`（可选）。

## 5. 设计取舍

- **纯核与副作用分层**：`text` / `cjk` / `markdown` / `clean` 禁止 `os` / `sys` / `io` / `socket` / `urllib` / `http` / `httpx` 导入。这样纯函数层能在任何环境（沙箱、只读文件系统、进程内联调用）安全 import；需要副作用就去 `extras/`。该约束由测试断言，不是口头约定。
- **密钥不进库**：`extras.vision` / `extras.translate` 的 endpoint / model / key 一律由调用方传入，本库不读配置、不持密钥。
- **失败语义分离**：`http_get` 静默返回 `None`（调用方兜底），`vision_describe` 抛异常（fail-open / fail-closed 由调用方决定），`translate` 返回 `None`（静默降级）。三种语义是刻意的，别互相套。
- **不内嵌业务语义**：`bing_image_search` 的域名黑名单、`match_intent` 的词表都从外部传入。库只提供机制，词表和策略留在调用方。

## 6. 版本与发布

语义化版本 + git tag。任何公共契约变更都要 bump 版本并打新 tag：

1. 改 `pyproject.toml` 的 `version` **和** `agent_utils/__init__.py` 的 `__version__`（两者必须一致）。
2. 跑测试全绿（§7）。
3. 提交后打 tag：`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`。

> 文档 / 测试改动属 doc-only，不动版本、不打 tag。

## 7. env 变量表

**无必填环境变量**——纯库，import 时不读环境。唯一例外：`extras.retrieval` 的 `tavily` 引擎在**调用时**读 `TAVILY_API_KEY`（可选；未设则该引擎抛 `RetrievalError`，其余引擎不受影响）。

| 变量 | 谁用 | 必填 | 说明 |
|---|---|---|---|
| `TAVILY_API_KEY` | `extras.retrieval._tavily_search` | 否 | 仅用 `tavily` 引擎走 API 时才需要 |

## 8. 测试

```bash
python -m pip install -e ".[dev]"
python -m pytest                                            # 全套
python -m pytest tests/test_cjk.py -v                       # 单模块
python -m pytest tests/test_cjk.py -k split_for_weixin -v   # 单用例
```

- 当前基线：**231 passed**（Python 3.13 / pytest 9）。
- 网络函数（`notify.send_text` / `retrieval.*` / live `http_get`）用离线 mock 覆盖，不打真网。

## 9. 已知缺口

- **无 CLI**：只有库接口，没有可执行入口。
- **`extras.retrieval` 是唯一带运行时依赖的模块**（`httpx`）。
- **`extract_share(today=None)`** 会调 `date.today()`（含时钟副作用）；要确定性输出请显式传 `today`。
- **网络函数不可离线硬测**：`send_text` / `web_search` / `web_fetch` / `translate` / live `http_get` 的联网路径只做结构性 / 离线 mock 覆盖。
- **`split_by_bytes` 默认值**已从 2000 收紧到 1800 并新增 `hard_limit`：为「引号内不切断、`MEDIA:` 行整块跟随」留出余量。若要旧行为，显式传 `limit=2000`。

## 变更记录

- **v0.5.0（2026-11-27）** — 首次公开发布。
  - 包名与 dist 名统一为 `agent-utils` / `agent_utils`（此前为内部命名，import 路径全变，属破坏性变更）。
  - 移除内部开发文档（设计稿 / 施工计划 / 接线交接）与内部工具链说明。
  - README 重写为面向外部使用者的版本：补安装方式、设计取舍、已知缺口。
- **v0.1.0（2026-10-14）** — 首版：中文文本 / CJK 断句 / markdown 化简 / 模型输出清洗四层纯核 + extras 副作用层（io / http / loader / notify / retrieval）。
  - 修复：`send_text` 按 UTF-8 字节截断（CJK 不会因字节超限被拒）；`split_for_weixin` 硬切钳到 `<=max_len`；`md_to_text(None)` 统一返回 `""`；四个核心模块全部接受 `None`。
- **v0.2.0（2026-10-18）** — 图 / 素材相关公共件下沉。
  - 新增 `intent.match_intent`（可配置词表机械匹配：contains/exact/prefix + exclude，纯函数）。
  - 新增 `cjk.parse_count`（中文数量「3张/两张/几张」）。
  - 新增 `extras.imagesearch.bing_image_search`（必应图搜 murl 纯检索；不并入 `extras.retrieval`——那是文本搜索且会拖入 `httpx`）。
  - 新增 `extras.imgio`（magic-byte / quick_dims / 最小边闸门 / 下载 / ffmpeg 降采样与 data-url / aspect_size）。修正了 PNG magic-byte 分支恒为假的死比较。
  - 新增 `extras.vision.vision_describe`（多模态读图机制，`urllib` 重写；**不持密钥**）。
- **v0.3.0（2026-10-19）** — 新增通用翻译 API `extras.translate`。
  - 统一契约**单字段翻译** `translate(text, src, dst, provider, timeout, llm_*)`：成功 → 译文，失败 → `None`。
  - 内置免费 `mymemory` + **OpenAI 兼容大模型 provider**（`{endpoint}/chat/completions`；密钥外层传、不入库）。
  - `provider` 三态：默认 `auto`（mymemory → llm）/ 指定单个 / **列表自定义优先级（主渠道 + fallback）**。
  - request/response hook 内部固化，留扩展口；`_PROVIDERS` 注册表可扩展新免费源。
- **v0.4.0（2026-10-22）** — `text.split_by_bytes` 升级为语义优先、字节兜底的分段投装箱函数（默认 1800 / hard 2048；引号内不断、`MEDIA:` 行不切）。

## License

MIT，见 [LICENSE](LICENSE)。
