# GLM Web → OpenAI 兼容本地 API（glm2api 加固版）

把**智谱清言网页版（chatglm.cn）的私有接口**转成 **OpenAI Chat Completions 兼容 API**，
跑在本机，让 [Cherry Studio](https://cherry-ai.com)、[Codex](https://github.com/openai/codex)、
[OpenCode](https://opencode.ai) 等工具直接用 `glm-5.3` 等网页版模型。

本项目基于 [glm2api](https://github.com/XxxXTeam/glm2api)（GPLv3）做了**本地加固**
（工具调用容错、参数类型校正、本地化启停脚本），完整背景见
[PROJECT.md](PROJECT.md)，踩坑记录见 [LESSONS.md](LESSONS.md)。

> ⚠️ **免责声明（请先读）**
>
> 本项目通过调用网页版私有接口工作，**不属于智谱官方 API，违反智谱清言用户协议的
> 可能性很高**，账号存在被限流或封禁的风险。本项目仅供**个人学习研究**，
> 请自行承担使用后果，并控制调用频率（本项目默认并发已锁到 3）。
> 我们不建议也不鼓励把本服务暴露到公网。

## 特性

- OpenAI 兼容端点：`/v1/chat/completions`、`/v1/responses`、`/v1/images/generations`、`/v1/models`、`/health`
- 多账号 token 池（`token.txt` 每行一个 refresh_token，自动轮换）+ 游客模式兜底
- 并发控制 / 排队 / 上游"忙"自动重试，适合多客户端共用
- 网页版无原生 Function Calling，本项目用 DSML 格式转换实现工具调用往返
- **加固补丁**（相对上游，2026-08-25，见 [PROJECT.md §6/§7](PROJECT.md)）：
  - 解析器：CDATA 数组、双重编码 JSON、幻觉闭合标签三类畸形输出恢复
  - 上游 moe_47/moe_5 双后端兼容；网页版 `all-tools` 层服务端执行失败的 error part
    自动容错（不再误报 502），工具调用透传给客户端本地执行
  - 按 schema 自动解码被字符串化的 array/object 工具参数（适配 OpenCode 等严格校验客户端）
- 每次请求新建上游会话、结束即删，不依赖也不污染网页端聊天记录

## 架构

```
Cherry Studio / Codex / OpenCode ...
        │  OpenAI 协议 (http://127.0.0.1:8100/v1)
        ▼
   glm2api 本地代理（本项目，8100 端口）
        │  网页版私有协议（cookie/refresh_token 鉴权）
        ▼
   chatglm.cn 网页版 GLM-5.3 / 4.7 ...
```

## 快速开始

前置：[uv](https://docs.astral.sh/uv/)（或 Python 3.14+）、一个 chatglm.cn 账号。

```bash
cd glm2api
cp .env.example .env          # 按需修改（默认监听 127.0.0.1:8100）
# 获取 token：浏览器登录 chatglm.cn → F12 → Application → Local Storage
#           → 找 chatglm_refresh_token → 填入 .env 的 GLM_REFRESH_TOKEN
./start.sh                    # 启动（脱离会话常驻）
curl http://127.0.0.1:8100/health
./stop.sh                     # 停止
```

没有 token 也能跑：`.env` 里 `GLM_USE_GUEST_REFRESH_TOKEN=true` 启用游客模式
（配额很小，仅够试用）。

## 客户端接入

**OpenCode**（`~/.config/opencode/opencode.json`）：

```json
{
  "provider": {
    "glmweb": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "GLM Web (chatglm.cn)",
      "options": { "baseURL": "http://127.0.0.1:8100/v1", "apiKey": "任意" },
      "models": { "glm-5.3": { "name": "GLM-5.3 (Web)" } }
    }
  }
}
```

**Codex CLI**（`~/.codex/config.toml`，可配合 [CC Switch](https://github.com/farion1231/cc-switch) 切换）：

```toml
[model_providers.glmweb]
name = "GLM Web (chatglm.cn)"
base_url = "http://127.0.0.1:8100/v1"
wire_api = "responses"
```

**Cherry Studio**：设置 → 模型服务 → 添加 OpenAI 兼容服务，
Base URL 填 `http://127.0.0.1:8100/v1`，API Key 任意，模型 ID 填 `glm-5.3`。

## 文档导航

| 文档 | 内容 |
|---|---|
| [PROJECT.md](PROJECT.md) | 项目全景：动机、选型、部署、使用指南、两轮故障排查时间线、风险 |
| [LESSONS.md](LESSONS.md) | 踩坑记录：8 条已验证教训 + 通用排查方法 |
| [DECISIONS.md](DECISIONS.md) | 关键决策与理由（选型/凭据/容错策略/开源形态等） |
| [glm2api/README.md](glm2api/README.md) | 上游项目原始文档 |

## 已知风险

- **合规风险**：见顶部免责声明；保持低并发、单账号、本机使用。
- **上游不稳定**：网页版私有接口随时可能变更（模型输出形态、后端路由都会变），
  出问题优先查 `/tmp/glm2api.log` 原文（`.env` 开 `DEBUG_DUMP_ALL=true`），
  排查方法见 [LESSONS.md](LESSONS.md)。
- **无官方 SLA**：免费通道，首 token 延迟与限流策略不受控。

## License

[GPLv3](LICENSE) — 本项目是 [glm2api](https://github.com/XxxXTeam/glm2api) 的衍生作品，
遵循上游许可证。Copyright (C) 2026 XxxXTeam (upstream) 及本仓库贡献者。
