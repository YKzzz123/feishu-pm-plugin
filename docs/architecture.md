# 架构、权限与数据流

本文描述 **feishu-pm-plugin / PM Backend** 的**概念**架构，以及「权限」在 Hermes 与业务层中分别扮演什么角色。骨架阶段（`add-hermes-plugin-skeleton`）只落地可测只读子集；写路径、IM 入口与 HTTP/PG 落地见 [tech-architecture-and-api.md](./tech-architecture-and-api.md)（**已冻结 D13–D16**：IM→FastAPI + PostgreSQL + 一群一项目 + Hermes `session_key` 记忆隔离 + Job envelope/payload）。

## 1. 总览

```text
 飞书用户 (Owner / 成员 · 一对多)
        │  IM 消息 / 卡片回调 / 事件
        ▼
 ┌──────────────────────────────────────────────────────────┐
 │ PM Backend（FastAPI · **主入口**）                          │
 │  · 验签 / 去重 / allowlist                                 │
 │  · authorize(user, project, action)                         │
 │  · 状态机 / operations 幂等 / 审计 / job envelope           │
 │  · 一群一项目 chat_id → project_id                             │
 │  · 写前飞书 ACL re-check → OpenAPI 出站                     │
 │  · 需要对话时 → DialogueOrchestrator                       │
 └───────────────┬──────────────────────────┬───────────────┘
                 │ session 记忆 + 意图         │ SQL
                 ▼                            ▼
 ┌───────────────────────────┐    ┌───────────────────────────┐
 │ Hermes（仅生成文案）         │    │ PostgreSQL                │
 │ 无写权；不替代鉴权           │    │ users/groups/projects/…   │
 │                            │    └───────────────────────────┘
 └───────────────────────────┘
```

**骨架阶段**：业务门禁可用进程内 `middleware/` + InMemory，不强制起 FastAPI。  
**目标态**：飞书进 Backend；Hermes 只管记忆与 LLM；第一个真实写飞书 change 起出站以 Backend 为准。

**一句话**：Backend 负责「消息进、是谁、哪项目、能不能做、diff/审批/写出」；Hermes **只生成**文案，任何服务与鉴权不经过 Agent 旁路。

## 2. 两套「权限」不要混

| 层级 | 名称 | 管什么 | 谁配置/实现 |
|------|------|--------|-------------|
| A. 宿主/对话面 | Hermes enable / 调用面 | 能否跑 LLM、是否加载 thin tools、记忆框架 | Hermes CLI / 可选 `plugin.yaml` |
| B. 业务面 | **Backend authorize（project）** | 飞书用户在某 **project** 上能否执行某 **action**（读上下文、传盘、周报审批、写 Wiki 等） | Backend 鉴权 + PG 项目角色 |

- **A 通过 ≠ B 通过**。能对话 ≠ 能改该项目 Drive/Wiki。  
- **B 通过 ≠ 用户已确认写操作**。写盘仍需确认；写 Wiki 仍需周报审批。  
- **MEMORY / transcript ≠ B**。记忆可错，授权只认 B + 飞书 ACL。

## 3. 业务权限模型

### 3.1 核心概念

| 概念 | 含义 |
|------|------|
| `open_id` | 通道键：飞书事件身份（Backend 验签后使用） |
| `email` | **业务主键**；Contact 解析后写入 `users` |
| `group_id` | 组；拥有 Drive **根**；人员池 |
| `project_id` | 项目；组根下**一个文件夹**；周报/diff/群绑定锚点 |
| `chat_id` | 飞书群；**一群一项目**（成员可跨组） |
| `session_key` | 可选对话隔离；**非**授权依据 |
| `role` | `owner` / `member` / `viewer` |
| `action` | 细粒度动作名 |

### 3.2 主 API

```text
resolve_project(chat_id | project_code) -> Project + effective role
list_my_projects(user) -> [ProjectBinding...]
authorize(user, project_id, action) -> Allow | Deny
```

规则：未绑定 / 角色无 action / 未知 action → **Deny**；resolve 不得串用户；list 不得无身份全站枚举。

### 3.3 动作枚举（读写 / 审批）

本文范围**不含**成员邀请/撤回等人员治理动作；只保留与读、传盘、diff/周报、审批、写 Wiki 相关的 action。

| action | 骨架 | 含义（目标态） |
|--------|------|----------------|
| `read_project_context` | ✅（P0 或近） | 查看项目绑定、元数据、周报状态、diff 只读 |
| `upload_drive` | 预留 | 对话上传到**项目文件夹**（preview→确认→commit） |
| `request_weekly_summary` | 预留 | 触发/请求本周 summary（与 cron 同源服务） |
| `approve_weekly` | 预留 | 周报 Y/N 审批 |
| `write_wiki` | 预留 | **审批通过后**由 Backend 写 Wiki（不经 Agent） |

读类：`read_project_context`。  
写类（须确认或审批 + 幂等）：`upload_drive`、`approve_weekly`（通过后联动 `write_wiki`）。

### 3.4 一对多与「一群一项目」

```text
Group AI ──Drive根──┬─ Project 模型评测 (folder) ←── chat oc_aaa
                    └─ Project 数据采集 (folder) ←── chat oc_bbb

群 oc_aaa 成员可来自不同组；绑定的是「项目文件夹」不是「整个 AI 组」
```

- 群内：`chat_id` → 唯一 `project_id`  
- diff/上传/周报：只动该项目文件夹  
- DM：显式 `project_code`；禁止默认第一项就写  
- Hermes 生成 summary 前，diff 与权限已在 Backend 完成  

## 4. 数据流

### 4.1 飞书消息（目标态主路径）

```text
用户 @Robot
  → 飞书事件 POST /v1/feishu/event
  → Backend 验签、去重、resolve user + chat→project
  → authorize(user, project, action) → Service（读/写/diff/审批）
  → 需要文案时 Backend→Hermes.generate（无写权）
  → 写飞书：项目文件夹 ACL + Idempotency-Key
  → IM 回复
```

### 4.2 骨架只读（当前仓）

```text
（开发态）直接调 tool/handler 或未来事件入口的只读分支
  → resolve + authorize(read_project_context)（P0 夹具仍可能是 group 命名）
  → JSON 信封；safe_handler 不 raise；ToolAudit 计数
```

### 4.3 上传 / 周报（读写与审批）

见 tech/design 全链路；范围限于：

- **读**：项目上下文、Drive tree/diff、周报状态  
- **写盘**：上传 preview → 确认 commit（项目文件夹）  
- **周报**：元数据 diff → summary → 待审 → Y/N → 通过后写 Wiki  

周报以 **项目文件夹元数据 diff** 驱动，空周仍提审（D10/D11）。  
**不在本文展开**：成员邀请/撤回、人员 ACL 运营台等。

### 4.4 Job

Scheduler → `/internal/cron/*` 或 `outbox_jobs`；**每次 job 的 payload** 见 tech §5.4（`weekly.remind`、`weekly.summarize_request_approval`、`drive.snapshot.capture` 等）。  
Job 同样只覆盖 diff/提醒/汇总/审批相关 kind，不含成员治理。

## 5. Hermes 侧约定

| 项 | 约定 |
|----|------|
| 定位 | **仅生成**，非飞书主入口、非鉴权方 |
| Session | 强制 `session_key` 一对多隔离 |
| Tool 返回 | 若用 thin plugin：**JSON 字符串**；错误也 JSON，**不要 raise** |
| 启用 | 可选 `hermes plugins enable`；发现 ≠ 启用 |
| 校验 | `hermes plugins doctor` / `validate` |

业务 `middleware/` ≠ Hermes `ctx.register_middleware`。

## 6. 目录与模块边界（目标）

```text
feishu-pm-plugin/            # 可选 thin tools + P0 骨架
pm-backend/                  # FastAPI 主入口（可 monorepo）
  app/api|services|adapters/feishu|adapters/hermes|…
docs/ openspec/ tests/
```

**禁止** tools/shell 绕过 Backend 写飞书。

## 7. 安全与审计要点

- 事件验签 + 去重；写身份只认可信 open_id  
- 默认拒绝：未知 action、无绑定；写前飞书 ACL  
- 写操作：Allow + 确认/审批 + Idempotency-Key  
- 日志脱敏；`operations` + `audit_events` + `job_id`  
- Session 记忆与 PG 业务态分离  

## 8. 与 OpenSpec / 文档

| 文档/规格 | 内容 |
|-----------|------|
| `docs/project-background.md` | 产品目标与周节奏 |
| 本文 | 概念架构、两套权限、数据流 |
| `docs/tech-architecture-and-api.md` | 实现架构、PG、幂等、HTTP、**job payload**、分阶段 |
| `docs/design-overview.md` | Mentor 总览与服务层 |
| `docs/hermes-plugin-conventions.md` | 可选插件安装与 handler 约定 |
| change `add-hermes-plugin-skeleton` | P0 InMemory 骨架 |
| 能力 `group-middleware` | 组映射与鉴权契约 |
