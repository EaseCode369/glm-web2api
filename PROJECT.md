# 网页版智谱清言 GLM-5.3 本地 API 项目

> 本文件是项目记忆文件（Project Memory）。任何模型/会话在本目录工作时，请先读完本文件再动手。
> 最后更新：2026-08-25（OpenCode agent 模式故障根因定位 + 工具解析器加固）

---

## 1. 背景与动机（为什么做）

- 目标模型 **GLM-5.3** 的官方付费 API（open.bigmodel.cn）token 价格太贵，日常写代码用不起。
- 网页版智谱清言（chatglm.cn）有免费额度，且已上线 GLM-5.3。
- 思路：登录网页版 → 取其会话凭证（refresh_token）→ 用开源代理把网页版私有 API
  转成 **OpenAI 兼容接口** → 接入本地各客户端。
- 主要消费方是**编码工具**：Codex（桌面/CLI，主力）、OpenCode、Trae Work；
  Cherry Studio 只是顺带接入的聊天客户端。

## 2. 选型过程（调研结论）

| 项目 | 结论 | 原因 |
|---|---|---|
| [WebAI2API](https://github.com/foxhui/WebAI2API) | ❌ 排除 | 基于 Camoufox 真实浏览器模拟，重；支持列表（LMArena/Gemini/豆包/zAI 国际站等）**不含 chatglm.cn**；zAI 是智谱国际站 zai.is，与网页版智谱清言账号体系不同 |
| [HelloGML](https://github.com/Hello-Application-XH/HelloGML) | ⏸ 备选 | Cloudflare Worker 方案，功能全（OpenAI/Claude/Gemini 三协议、多账号、绘图/视频），但主分支 2026-05-08 后停更，`.workers.dev` 大陆访问不稳，工具调用靠 prompt 注入实现。需要云端 7x24 或 Claude 协议时再启用 |
| [glm2api](https://github.com/XxxXTeam/glm2api) | ✅ **采用** | 内置模型列表第一个就是 `glm-5.3`（为当前网页版阵容而做）；`/v1/chat/completions` + `/v1/responses` 双协议（后者正好匹配 Codex 的 `wire_api="responses"`）；本地 Python 服务，零云依赖；refresh_token 自动轮换写回；多账号池 + 游客模式兜底；2026-08-23 仍在更新 |

关键佐证：本机 Codex 早已在用自定义 Provider（`model_providers.custom`，Tailscale 中继，
responses 协议，`cc-switch` 管理模型目录），说明"自定义 provider 接编码工具"这条路在本机
已被验证可行，本次只是新增一个 GLM 源。

## 3. 架构

```
Codex / OpenCode / Cherry Studio / Trae Work
        │  OpenAI 兼容协议 (chat/completions 或 responses)
        ▼
glm2api 本地代理  http://127.0.0.1:8100/v1   (Python, uv 运行, 127.0.0.1 仅本机)
        │  签名 + refresh_token → access_token 自动换取/轮换
        ▼
chatglm.cn 网页版私有 API (GLM-5.3 等 82 个模型)
```

## 4. 部署记录（2026-08-24）

1. `git clone` glm2api 到本目录 `glm2api/`。
2. `.env` 从 `.env.example` 生成，修改：`PORT=8100`（**8000 被 Personal OS 的 uvicorn 占用，勿动**）、
   `GLM_MAX_CONCURRENCY=3`（控风控，示例默认 100 太激进）、`HOST=127.0.0.1`。
3. `uv sync`（纯标准库，无第三方依赖）→ 启动。**启动坑（2026-08-24 实测）**：从临时 shell
   用普通 `nohup &` 启动的进程会随该 shell 会话结束被连带回收（服务无声消失、日志无报错），
   必须用 `start_new_session` 脱离进程组。`start.sh` 已改为经 Python launcher 以
   `start_new_session=True` 拉起 `uv run main.py`（旧版备份 `start.sh.bak-20260824b`），
   并用"新会话再查 /health"验证存活。
4. **已接入真实账号**（2026-08-24 23:30）：从用户 Chrome 登录态中取出
   `chatglm_refresh_token` 写入 `glm2api/token.txt`（chmod 600，一行一个 = 多账号池，
   程序自动轮换写回）。启动日志确认 `账号数=1 游客模式=False`；游客模式降级为纯兜底。

### 验证结果（全部通过）

| 接口 | 结果 |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /v1/models` | 82 个模型，含 `glm-5.3` / `glm-5.3-think` / `glm-5.3-search` / `glm-5.3-think-search` |
| `POST /v1/chat/completions`（glm-5.3, stream） | 流式正常，模型自述"我是智谱清言，基于 GLM-5.2 开发" |
| `POST /v1/responses`（带 tools） | 正确返回 `function_call: get_time {"city":"北京"}` |
| `POST /v1/chat/completions`（glm-5.3-**think**, stream） | 游客模式下 502 `GLM part status error`；**接账号后复测通过**（2026-08-24 23:29，流式完整 + `[DONE]`） |
| `POST /v1/responses`（账号模式复测） | 200，`status: completed`，会话自动清理正常 |

## 5. 使用指南

### 5.1 启停代理

```bash
cd "/Users/eric/Documents/Codex/GLM5.3网页版API/glm2api"
./start.sh    # 启动（幂等，已运行会提示）；日志 /tmp/glm2api.log
./stop.sh     # 停止
```

重启后 Codex/OpenCode/Cherry Studio 无需任何改动（端口不变即可）。
**重启电脑后需手动再 start.sh**（暂未做开机自启）。

### 5.2 连接信息

- Base URL: `http://127.0.0.1:8100/v1`
- API Key: 任意（如 `glm-local`；服务端默认不鉴权）
- 模型名: `glm-5.3`（推荐）、`glm-5.3-think`（思考）、`glm-5.3-search`（联网）、`glm-4.7` 等

### 5.3 客户端接入（已完成项标注 ✅）

- ✅ **Codex**（`~/.codex/config.toml`，备份 `config.toml.bak-20260824-glmweb`）
  已添加：
  ```toml
  [model_providers.glmweb]
  name = "GLM Web (chatglm.cn)"
  base_url = "http://127.0.0.1:8100/v1"
  wire_api = "responses"
  ```
  `~/.codex/cc-switch-model-catalog.json` 已添加 `glm-5.3` 目录条目（备份同后缀 .bak）。
  当前生效模型未动（仍是 custom/qwen3.8-27b）。**用 cc-switch 新建 profile：
  `model_provider = "glmweb"` + `model = "glm-5.3"` 切换即可。**
- ✅ **OpenCode**（`~/.config/opencode/opencode.jsonc`，备份 `.bak-20260824`）
  已添加 provider `glmweb`（`@ai-sdk/openai-compatible` + baseURL），
  模型列表出现 `glmweb/glm-5.3` / `glmweb/glm-5.3-think` / `glmweb/glm-4.7`。
- **Cherry Studio**（手动）：模型供应商 → OpenAI 兼容 → Base URL `http://127.0.0.1:8100/v1`，
  Key 任意，模型 `glm-5.3`。
- **Trae Work**（未接）：先查设置里有无自定义模型端点入口，有则填同一地址；
  没有则不强接——Trae Work 自带免费 GLM 通道（`solo_work_lite`，含 glm-5.2）。

### 5.4 账号 token 的接入与再提取（✅ 已完成，当前 1 个账号）

**现状**（2026-08-24 23:30）：`glm2api/token.txt` 存有一个真实 refresh_token
（chmod 600；一行一个即多账号池，程序自动轮换、过期自动写回新值）。

**需要重新提取 token 时**（日志出现"请登录后继续使用"、或上游持续 401/502）：
1. 用户在 Chrome 登录 chatglm.cn，并把该标签页切到最前面。
2. 前提：Chrome 菜单 `显示 → 开发者 → 允许 Apple 事件中的 JavaScript` 已勾选
   （本机已开启；注意该项**程序化点击无效**，只能人工点一次）。
3. 自动提取（只读这一个值，不碰其他凭据；token 在 cookie 里，不在 localStorage）：
   ```bash
   osascript -e 'tell application "Google Chrome" to execute active tab of front window javascript "(document.cookie.match(/chatglm_refresh_token=([^;]+)/) || [])[1]""'
   ```
   结果写入 `token.txt`（追加为新行可组成多账号池），`chmod 600 token.txt`。
4. `./stop.sh && ./start.sh`，用一条 glm-5.3-think 流式请求复测（这是最容易先挂的场景）。
5. 兜底人工法：F12 → Application → Cookies → chatglm.cn → 复制
   `chatglm_refresh_token` 的值，粘贴进 `token.txt`。

**多账号**：`token.txt` 每行加一个即可，程序在账号间自动轮换；建议 ≤2 个，优先备用号。

## 6. OpenCode agent 模式故障排查（2026-08-25）

**现象**：OpenCode 里小问题正常，一跑真实编码任务（会触发内置 `question` 工具）就报
两层错：① `SchemaError(Expected array, got "<item>{...}..." at ["questions"])`
② `GLM 上游返回错误 | GLM part status error`。曾怀疑风控/请求体积/内容审查——
**均排除**（23 万字符大请求、敏感内容、多工具、多轮 agent 历史等 7 组对照全部成功）。

**真根因（两个独立的解析器 bug，级联成 502）**：

1. **CDATA 数组**：GLM-5.3（上游内部名 `moe_5`）调 `question` 工具时，把数组参数整体包进
   CDATA 当文本：`<|DSML|parameter name="questions"><![CDATA[<item>{...}</item>,<item>...</item>]]></|DSML|parameter>`。
   解析器把 CDATA 当叶子文本返回 → `questions` 变成字符串 → OpenCode schema 校验失败。
   OpenCode 自动重试并把 SchemaError 文本作为 tool_result 发回 → glm2api 注入上游会话 →
   上游把该 part 标记 `status:"error"` → 代理抛 502 `GLM part status error`。
2. **幻觉闭合标签**：模型偶尔在 parameter 里吐出多余的 `</arg_value>`（不存在的标签），
   导致整个 DSML 块 XML 解析失败被静默丢弃 → 客户端收到空响应（`tool_calls=0`、空 delta）。

**修复**（均在 `glm2api/src/glm2api/utils/tool_parser.py`，原版备份 `tool_parser.py.bak-20260825`）：

- `_parse_item_list_text()` + `_coerce_leaf_value()` 增加恢复路径：把 CDATA 文本里的
  `<item>...</item>` 序列解析回数组（skeleton 校验防止误伤含 "item" 的普通文本）。
  ⚠️ 前一版补丁有隐藏 bug：skeleton 检查用 `ITEM_ENTRY_PATTERN.sub("[]", text)` 会产生
  `[],[]` 永远通不过 `fullmatch(r"[\s,;]*")`，恢复路径实际永不触发；已改为 `sub("", text)`。
- 双重编码 JSON 恢复：值形如带引号字符串包的 JSON（`"[\"a\":1]..."`）→ 递归解码回数组。
- `_drop_unmatched_close_tags()`：仅当 `ET.fromstring` 首次失败时，删掉无主的闭合标签
  （如 `</arg_value>`）后重试一次；正常块零开销。

**验证（全部通过，2026-08-25）**：

- 19 项定向检查，样本取自真实故障日志（`/tmp/glm_bad_sample.txt` = CDATA 坏块、
  `/tmp/glm_argvalue_sample.txt` = `</arg_value>` 坏块）：两者均解析为正确的 `list[dict]`
  参数；普通文本、`<item>` 元素、裸 JSON 数组等回归用例不受影响。
- 仓库测试套件：`uv run --with pytest python -m pytest tests/ -q` → 59 passed
  （venv 未装 pytest，用 `--with pytest` 临时注入）。
- 端到端：用 OpenCode 真实 `question` 工具 schema 打 `POST /v1/chat/completions` →
  `finish_reason: tool_calls`，`questions` 为 2 个 dict 的真数组，每问 3 选项。
- 纯对话（无工具）回归正常。

**排查方法备忘**：`.env` 开 `DEBUG_DUMP_ALL=true` 后，`/tmp/glm2api.log` 有完整上游
请求体/响应 SSE 原文，故障时直接 grep 关键字（`CDATA`、`arg_value`、`status`）。
**该开关当前仍处于开启状态**，待观察一两轮稳定后改回 `false` 再重启（日志会很大）。

**遗留观察项**：模型输出形态不稳定（同一工具可能时而是 CDATA、时而裸 JSON、时而带
幻觉标签），解析器现已覆盖已知 4 种形态；若再出现新畸形，优先查日志原文，按同样
思路加恢复路径。

## 7. OpenCode agent 模式故障排查·第二轮：moe_5 agent 后端 + all-tools 容错（2026-08-25 深夜）

**现象**：§6 修复后小问题仍正常，但大 agent 任务（马里奥开发任务）仍间歇性报 502
`GLM 上游返回错误 | GLM part status error`，失败率约 50%。用户在网页版直接抓到了
故障对话（`glm2api/回复.md`，其中 # CONVERSATION 段是被污染的历史全文）。

**真根因（上游双后端随机路由）**：

1. 上游把每个请求随机路由到两个后端：`moe_47`（文本后端）和 `moe_5`（agent 后端）。
   moe_47 把工具调用以 DSML 纯文本返回（解析器正常处理）；moe_5 把工具调用结构化成
   `tool_calls` part（show_type `mc_tool_call`）。
2. 网页版自带**服务端执行层 `all-tools`**：看到结构化 `tool_calls` 后，会尝试在服务端
   执行 OpenCode 传进来的"外来工具"（bash / todowrite / question……），必然失败，
   于是发出 `role:"tool"`、`model:"all-tools"`、`status:"error"` 的 part
   （show_type `mc_tool_result2`，日志 24485 行）。
3. 旧代码 `_raise_for_event_error` 见到任何 part `status=error` 就抛 502 → 整条流作废。
   小问题纯文本回答不触发工具调用 → 不失败；大任务几乎必调工具 → 成败取决于路由骰子。
4. 次要问题：模型/网页解析器把 schema 声明为 array/object 的参数**包成 JSON 字符串**
   （`todos:"[{...}]"`、`questions:"<item>..."`），OpenCode zod 校验报 SchemaError →
   坏调用被每轮重放，污染历史（回复.md 可见：马里奥 prompt 重复 5 次）。

**修复（4 个文件）**：

- `src/glm2api/services/glm_client.py`（类名 `GLMWebClient`）：模块级
  `is_server_side_tool_error_part(part)`（`role=="tool"` 且 `model=="all-tools"`
  或 show_type 以 `mc_tool_result` 开头）；`_extract_event_error` 跳过这类 part；
  `_raise_for_event_error` 新增护栏：整个 event 只含这类错误 part 时 warning+return，
  不再抛 502（`_only_server_side_tool_errors`）。
- `src/glm2api/services/translator.py`：`GLMEventAccumulator` 新增 `tool_schemas` 字段
  （由 `GLMWebClient._tool_schemas_from(filtered_tools)` 提供）；`finalize()` 与
  `build_response()` 合并全部 tool calls 后统一走 `_coerce_tool_call_arguments`。
- `src/glm2api/utils/tool_parser.py`：新增 `coerce_tool_arguments(name, arguments, schema)`
  + `_coerce_to_schema_type()`：把字符串化的 array（含 `<item>` 形式与 JSON 字面量）/
  object / number / boolean 按 schema 解码为真结构；无 schema 时行为不变。
- `src/glm2api/utils/tool_protocol.py`（当前生效的 DSML prompt 在此）：参数规则新增
  "array/object 值必须是原始 JSON 或 `<item>`，禁止多套一层引号"。

**验证（全部通过，2026-08-25）**：

- 真实事故数据（日志 24399 行的 todowrite 字符串化数组）经 `coerce_tool_arguments`
  解码为 6 项 todos 的真数组。
- 测试套件 `uv run --with pytest python -m pytest tests/ -q` → **67 passed**
  （新增：test_tool_parser.py 1 项、新文件 tests/test_glm_client_errors.py、
  test_translator.py 2 项）。
- 服务已用新代码重启（端口 8100）。

**对用户的疑问的回答**：

- **不需要"实时监控对话 Session"**：本架构是无状态请求-响应——每次请求把完整历史
  重发一遍，上游每次新建 conversation、请求结束即自动删除。问题出在错误处理，
  不在缺少监控。
- **不是"项目太大被安全审查识破"**：失败率由 moe_5 路由骰子 × 是否触发工具调用决定。
- 修复后应在 OpenCode **开新会话**重发任务：旧会话历史已污染，每轮重放浪费 token
  且干扰模型。

**证据**：`/tmp/glm2api.log`（三次 502 在 23:55:31 / 00:23:33 / 00:23:54；
all-tools error part 24485 行；todowrite tool_calls part 24399 行；moe_47/moe_5
路由分布可 grep `"model":"moe_`）；用户网页抓取 `glm2api/回复.md`。

## 8. 已知风险与限制

- **ToS 风险**：逆向网页 API 违反智谱清言用户协议，存在限流/封号可能。
  对策：并发保持 3、避免 24h 高强度跑、游客模式兜底。
- **无原生工具调用 + 双后端路由**：网页版 API 不支持原生 Function Calling，glm2api 用
  DSML 格式转换实现，且上游存在 moe_47/moe_5 双后端随机路由（moe_5 的 all-tools 层会
  服务端误执行外来工具，代理已容错，见 §7）。2026-08-25 已加固解析器（详见 §6/§7），
  `question` 等复杂数组工具的往返已打通；若再遇新的解析失败，先查 `/tmp/glm2api.log`
  原文再加恢复路径，或临时换 `glm-4.7` 对比，再不行评估 HelloGML 备选方案。
- **延迟**：上游为网页版免费通道，首 token 较慢（实测一次完整问答约 70s，含游客取号），
  并发排队/上游忙时代理会自动重试（最多 30 次）。
- **代理只在本机**：不在 Tailscale 服务器上，其他设备用不了。

## 9. 关键文件索引

| 路径 | 说明 |
|---|---|
| `glm2api/` | 代理服务源码（勿随意改动；上游更新用 `git pull` + `./stop.sh && ./start.sh`） |
| `glm2api/src/glm2api/utils/tool_parser.py.bak-20260825` | 工具解析器加固前原版（2026-08-25 补丁，见 §6） |
| `glm2api/.env` | 运行配置（端口/并发/token） |
| `glm2api/start.sh` / `stop.sh` | 启停脚本（start.sh 用 start_new_session 脱离会话） |
| `glm2api/token.txt` | 账号 token 池（每行一个 refresh_token，chmod 600，自动轮换写回） |
| `/tmp/glm2api.log` | 运行日志（重启电脑后清空） |
| `~/.codex/config.toml` | Codex 配置（含 `[model_providers.glmweb]`） |
| `~/.codex/cc-switch-model-catalog.json` | Codex 模型目录（含 `glm-5.3` 条目） |
| `~/.config/opencode/opencode.jsonc` | OpenCode 全局配置（含 `glmweb` provider） |
| `glm2api/回复.md` | 2026-08-25 用户在网页版抓取的故障对话（第二轮根因证据，见 §7） |
