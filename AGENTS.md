# AGENTS.md

本目录是「网页版智谱清言 GLM-5.3 → 本地 OpenAI 兼容 API」项目。
**先读 [PROJECT.md](PROJECT.md) 再动手**，其中包含背景、选型、部署记录、完整用法与风险。

## 快速事实

- 代理服务：`glm2api/`（本地 Python 代理，上游 chatglm.cn 网页版私有 API）
- 服务地址：`http://127.0.0.1:8100/v1`，API Key 任意，主模型 `glm-5.3`
- 启停：`cd glm2api && ./start.sh` / `./stop.sh`；日志 `/tmp/glm2api.log`
- 当前凭据模式：**真实账号**（`glm2api/token.txt` 1 个 refresh_token，自动轮换写回；游客模式仅作兜底）；token 再提取方法见 PROJECT.md §5.4
- 下游已接入：Codex（`~/.codex/config.toml` 的 `[model_providers.glmweb]`，cc-switch 切换）、
  OpenCode（`~/.config/opencode/opencode.jsonc` 的 `glmweb` provider）
- 2026-08-25 已加固 `glm2api/src/glm2api/utils/tool_parser.py`（CDATA 数组 / 双重编码 JSON /
  幻觉闭合标签三类恢复；原版备份 `tool_parser.py.bak-20260825`），OpenCode `question` 工具
  往返已打通，详见 PROJECT.md §6
- 2026-08-25 第三轮（详见 PROJECT.md §11）：**自动续话**（检测"截断且只剩思考"的退化解，
  同一上游会话补发"请继续"，`GLM_AUTO_CONTINUE` 默认 true / `GLM_AUTO_CONTINUE_MAX` 默认 2，
  改后需重启）+ 截断告警日志 + 思考经 `reasoning_content` 转发 + 风控介入（intervene）正常
  收尾不再 502 + 断线自动重试（`GLM_STREAM_RETRY_MAX` 默认 1，0 关闭）。**OpenCode agent
  任务用非 think 版 `glm-5.3`**（Think 版有截断问题，用户决定不再用）。测试套件当前 81 passed
- 2026-08-25 第二轮修复（详见 PROJECT.md §7）：上游 moe_47/moe_5 双后端随机路由，moe_5 的
  all-tools 层会服务端误执行外来工具并回 `status:error` part → 代理现在识别并忽略这类 part
  （`is_server_side_tool_error_part`），不再抛 502；字符串化的 array/object 工具参数按 schema
  解码（`coerce_tool_arguments`）。测试套件当前 67 passed
- 上游行为排查：`.env` 的 `DEBUG_DUMP_ALL=true`（当前开着）会让 `/tmp/glm2api.log` 记录
  全量原始上游请求/响应；跑仓库测试用 `uv run --with pytest python -m pytest tests/ -q`

## 注意事项（重要）

- **排查任何故障前，先读 [LESSONS.md](LESSONS.md)**（10 条已验证教训，避免重走弯路）；
  重要技术决策及其理由见 [DECISIONS.md](DECISIONS.md)。
- 本目录已是 git 仓库（main 分支）：**token.txt / .env / log/ / 回复.md / .local/ 永不提交**，
  提交前用 `git grep -i "eyJhbGci"` 自查。上游 glm2api 的 .git 备份在 `.local/glm2api-upstream-git`。

- **端口 8000 被用户的 Personal OS 服务（uvicorn）占用，严禁改动或杀该进程。**
- 不要修改 `~/.codex/config.toml` 里现有的 `[model_providers.custom]` 段和当前生效的
  `model_provider` / `model` 值（用户在用），本项目的段是 `[model_providers.glmweb]`。
- 改动 `.env` 或拉取上游更新后必须 `./stop.sh && ./start.sh` 才生效。
- 从临时 shell 启动服务会随会话被回收，必须用 `start.sh`（内部 `start_new_session`）。
- 上游是逆向的网页版 API：保持低并发（`GLM_MAX_CONCURRENCY=3`），避免长时间高强度调用。
