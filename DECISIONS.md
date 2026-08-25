# DECISIONS.md — 关键决策与理由

> 记录"为什么这么做"，与代码事实（PROJECT.md）和教训（LESSONS.md）分工明确。

## D1 选型：基于 glm2api（XxxXTeam/glm2api，GPLv3）做本地加固

- **备选对比**：WebAI2API（foxhui）等多个开源项目，详见 PROJECT.md §2 调研结论。
- **决定**：采用 glm2api。
- **理由**：已适配 GLM-5.3 网页端私有 API 与 DSML 工具格式，支持多账号 token 池、
  游客模式兜底、并发控制；上游活跃（2026-08 仍在发版适配 5.3）。
- **代价/约束**：GPLv3 许可证 → 本项目的全部修改与衍生内容必须同许可证开源（见 D8）。

## D2 凭据：真实账号 refresh_token，不用游客模式

- **决定**：`token.txt` 放 1 个真实账号的 refresh_token（自动轮换写回）；
  游客模式仅兜底。
- **理由**：游客模式配额太小，跑 agent 任务（多轮工具调用）根本不够；真实账号
  GLM-5.3 试用配额（约 200 积分/天）对日常编码够用。
- **接受的风险**：逆向网页 API 违反智谱用户协议，存在限流/封号可能。
  缓解：并发锁 3、仅 127.0.0.1、单账号、避免 24h 高强度跑（PROJECT.md §8）。

## D3 端口：8100（不用上游默认的 8000）

- **理由**：8000 被用户的 Personal OS 服务（uvicorn）占用，严禁改动或杀该进程。

## D4 会话模型：无状态请求-响应，不维持上游会话

- **决定**：每次请求新建 conversation，请求结束自动删除（`GLM_DELETE_CONVERSATION=true`）。
- **理由**：上游网页端会话有"其他对话生成中"锁，维持会话容易互相阻塞；
  无状态设计下每次把完整历史重发，简单可靠。用户曾问"要不要实时监控 Session"——
  不需要，问题从来不在缺少监控（PROJECT.md §7）。

## D5 错误容错策略：all-tools 服务端执行失败 ≠ 回答失败（2026-08-25）

- **决定**：识别 `role=tool` 且 `model=all-tools`（或 show_type 以 `mc_tool_result`
  开头）的 part，忽略其 error 状态，工具调用照常透传给客户端本地执行。
- **理由**：网页版 all-tools 层执行外来工具（bash 等）必然失败，是"别人的失败"；
  真正该 502 的只有回答 part 本身的错误。背景与验证见 PROJECT.md §7、LESSONS.md L5。

## D6 参数类型校正：按 schema 解码字符串化参数（2026-08-25）

- **决定**：`coerce_tool_arguments()` 在透传前把字符串化的 array/object/number/boolean
  按工具 schema 解码为真结构；无 schema 时行为不变。
- **理由**：OpenCode 等严格校验客户端（zod）对类型零容忍；同时 DSML prompt 加规则
  从源头减少畸形输出。见 LESSONS.md L7。

## D7 上游同步策略：本地加固与上游更新并存

- **决定**：本地修改直接改 glm2api 源码（原版备份 `tool_parser.py.bak-20260825`），
  本地全部修改另存 patch 于 `.local/glm2api-local-changes-20260825.patch`（不入库）。
- **理由**：上游迭代快（频繁适配新模型），直接 vendor 会导致升级困难；保留 patch
  可以随时对比/重放本地加固。
- **注意**：开源准备时 `glm2api/.git` 已移至 `.local/glm2api-upstream-git`
  （见 D8）；日后想同步上游：重新 clone 官方仓库，对比 patch 与 `git log` 决定合并方式。

## D8 开源形态：顶层仓库 = 项目根（文档 + glm2api/ 代码子目录），GPLv3

- **决定**：GitHub 仓库结构 = 根目录文档（README/PROJECT/LESSONS/DECISIONS）+
  `glm2api/` 代码子目录；LICENSE 采用 GPLv3（与上游一致，因本项目是其衍生作品）。
- **敏感文件永不入库**：`token.txt`（真实账号凭据）、`.env`、`log/`（含完整对话
  原始数据）、`回复.md`（用户真实会话抓取）、`.local/`（上游 git 备份 + patch）、
  `*.bak*`。由根 `.gitignore` 强制。
- **理由**：token 一旦泄露等于账号拱手送人；对话日志涉及用户隐私；
  扁平化（把 glm2api/ 提为仓库根）会破坏正在运行的服务路径，不值得此刻折腾。

## D9 Codex 接入：走 CC Switch，不改默认 provider

- **决定**：`~/.codex/config.toml` 只新增 `[model_providers.glmweb]` 段 +
  `cc-switch-model-catalog.json` 加 `glm-5.3` 条目，用 CC Switch 切换；
  严禁改动用户现有 `[model_providers.custom]` 与当前生效的 model_provider/model。
- **理由**：用户明确要求，且保留随时切回官方模型的能力。

## D10 项目知识体系：PROJECT / DECISIONS / LESSONS / AGENTS 四文档分工

- **决定**：项目事实与时间线 → PROJECT.md；决策理由 → 本文件；踩坑与已验证教训 →
  LESSONS.md；工作规则与快速事实 → AGENTS.md。
- **理由**：跨会话可交接（用户明确要求"不怕跨会话沟通"）；开源后也是项目的
  自带文档。

## D11 自动续话：代理检测"截断且只剩思考"，同上游会话补发"请继续"（2026-08-25）

- **决定**：每轮 finish 后跑 `degraded_answer()`（无可见正文、无工具调用、纯思考且戛然而止），
  命中则 `_open_continuation_stream` 在**同一上游会话**内补发一条固定短 user 消息，续文拼进
  同一 SSE 流；上限 `GLM_AUTO_CONTINUE_MAX`（默认 2），`GLM_AUTO_CONTINUE=false` 关闭；
  `intervene`（人工介入）永不续话。
- **理由**：上游会话在请求结束前不删除，模型自己的半段思考留在网页会话历史里，补一句
  "继续"模型就会接着说——这是不改上游、最接近真 API 的修法。续话提示固定且短，不携带
  大段历史，风控指纹增量极小；次数上限防止死循环与配额空耗。
- **备选与否决**：客户端侧（OpenCode/Codex）做自动续话被否——要改多个客户端；代理是唯一
  汇聚点，一处修改所有客户端受益。
## D12 断线自动重试 与 风控介入不重试（2026-08-25 晚）

- **决定**：网络类断线（UpstreamAPIError / OSError / http.client 异常）自动重试，
  `GLM_STREAM_RETRY_MAX` 默认 1；未输出任何内容 → 整体重发原始请求（新会话，旧会话
  标记废弃并清理）；已输出一部分 → 同会话续话（客户端已看到前半段，只能接着说）。
  `status=intervene`（风控内容审查拒绝）**永不重试**，改为正常收尾并附介入文案。
- **理由**：日志证据（14:37:11）证明那次 502 是 output_sensitive/REJECT 内容审查——
  重试同一内容只会再次被拒并加重风控压力；而真正的传输断线"再试一次说不定就好了"，
  对用户价值大。续话提示语天然适配"已输出一半"场景，避免客户端收到重复答案。
  重试次数默认 1，保守防死循环与配额空耗。
- **备选与否决**：客户端侧重试被否（要改多个客户端，代理是唯一汇聚点）；"断线一律
  整体重发"被否（已流式发出的 token 收不回来，整体重发会产生重复内容）。
