# CLAUDE.md

## 首要要求

1. **全程用中文**与用户沟通（代码标识符、OpenSpec 的 SHALL/MUST 与结构标题保持英文惯例）。
2. 设计或代码结构有变更时，同步更新 `docs/` 中对应文档。
3. **只有用户明确要求「提交」时才 commit**；未经允许不要 push。默认不直接推 `main`。
4. 提交说明用**英文**；不要把本文件或本地密钥一并提交。
5. 不提交：`.env`、密钥、本地 Hermes/飞书 token、临时脚本产出、与当前任务无关的文件。

## 项目概述

飞书「组」维度进展 Robot：用户在飞书与 Robot 对话，审批周报、管理组 Drive 成员/权限与文件；Robot 总结组 Drive **元数据 diff**、按周提醒、周四汇总并提审批，通过后写入 Wiki。

**技术路线（目标态 · D13–D16）**

- **主入口**：**FastAPI（PM Backend）**：验签、**chat→project**、authorize、diff/周报、幂等、飞书出站、job
- **Hermes**：**仅生成** summary/话术；**禁止**绕过后端鉴权；不当 IM 主入口
- **绑定**：**一群一项目**；项目 = 组 Drive 下文件夹（不是绑整个组）
- **本仓库**：可选 thin **插件** `feishu-pm-plugin`（tool → HTTP 回调 Backend）+ 骨架 `middleware/` + 文档/OpenSpec；真实写飞书起可 monorepo `pm-backend/`
- **骨架阶段**：进程内 InMemory 中间层亦可（`add-hermes-plugin-skeleton`）

完整背景：[`docs/project-background.md`](docs/project-background.md)。  
概念架构：[`docs/architecture.md`](docs/architecture.md)。  
**实现架构 + API + Job payload**：[`docs/tech-architecture-and-api.md`](docs/tech-architecture-and-api.md)。  
Mentor 总览：[`docs/design-overview.md`](docs/design-overview.md)。  
Hermes 插件约定：[`docs/hermes-plugin-conventions.md`](docs/hermes-plugin-conventions.md)。

## 仓库结构（目标形态）

```
feishu-pm-plugin/           # 本仓库根；可选 symlink 到 ~/.hermes/plugins/
├── CLAUDE.md
├── docs/
│   ├── project-background.md
│   ├── architecture.md
│   ├── design-overview.md
│   ├── tech-architecture-and-api.md
│   └── hermes-plugin-conventions.md
├── openspec/
├── plugin.yaml
├── __init__.py
├── schemas.py / tools.py   # 可选：HTTP client → PM Backend
├── middleware/             # 骨架 InMemory；≠ Hermes host middleware
├── pm-backend/             # 目标：FastAPI 主入口 + Alembic
└── tests/
```
实际目录以迭代为准；保持「对话侧薄、业务在 Backend」。

## Hermes / 插件约定

- 清单：`plugin.yaml`；入口：`register(ctx)`；tool handler 返回 **JSON str**，`(args, **kwargs)`，不 raise
- **发现 ≠ 启用**：`hermes plugins enable <name>`；校验用 `hermes plugins doctor` / `validate`
- 参考：官方 [Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
- **飞书 IM 主路径进 FastAPI**，不是 Hermes Gateway；Hermes 负责 **session 记忆隔离** + LLM
- **两套权限**：Hermes enable/capabilities ≠ 业务 `authorize(user, project, action)`；详见 architecture
- **禁止** tools/shell 绕过 Backend 直碰飞书敏感 API；写操作须确认/审批 + 幂等键
- 身份：生产用**已验签事件**中的 `open_id`/`chat_id`；email 为业务主键；**一群一项目**

`openspec/config.yaml` 中 `context` 为全局上下文；项目背景变更时请同步改那里的摘要。

### Hermes 侧 OpenSpec skills

生成物在 `.hermes/skills/`。若要用 Hermes 加载，需把该目录加入 `~/.hermes/config.yaml` 的 `skills.external_dirs`（无用户明确要求时不要改用户全局 config）。

## 代码与协作要求

1. 以现有插件/中间层框架为准；**框架级或大重构先方案后改**。
2. 写操作（Drive 权限变更、Wiki 写入、覆盖文件等）须有明确确认或审批态，禁止静默写。
3. 一对多场景下，所有操作必须解析到 **当前飞书用户 → 项目**（群内 `chat_id`→唯一 `project_id`）；防止串项目；Hermes 不得替代鉴权。
4. 优先复用飞书/Lark 官方能力与既有 CLI/SDK；新依赖需说明理由。
5. 改动后补齐或更新对应测试；能跑的测试要跑通。

## 安全

- 密钥只进环境变量或本地未跟踪配置，不进 git
- 日志默认脱敏（token、手机号等）
- 生产写操作与测试租户隔离（若区分环境，按用户指定环境执行）

## 分支与提交

- 功能在分支上开发；用户说「提交」再 commit
- push 前检查远程是否有更新，有则先拉最新的main在当前分支合并与解决冲突后再push
- 每次提交前用中文向用户简述：改了哪些文件、哪些业务内容、对应的主要函数/行为
