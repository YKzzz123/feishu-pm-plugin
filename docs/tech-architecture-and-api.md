# 技术架构与接口设计

**状态**：已冻结决策 + **项目绑定修正（2026-10-29，D4/D8/D9/D17）**：一群一项目（组 Drive 下文件夹）；Hermes 仅生成  
**范围**：实现向设计；与 `project-background.md`、`architecture.md`、`design-overview.md` 对齐。  
**骨架 change**（`add-hermes-plugin-skeleton`）仍可不含本后端；**第一个真实写飞书 / IM 入口 change** 起按本文落地。

---

## 0. 已冻结决策

| ID | 议题 | 决定 |
|----|------|------|
| D1 | 后端形态 | **独立 FastAPI + PostgreSQL** 为业务真源与主进程能力 |
| D2 | 数据库 | **PostgreSQL** |
| D3 | 人主键 | **email 业务主键** + **open_id 通道键**（并存 union_id 可选） |
| D4 | 群与绑定 | **一群一项目**（`chat_id` ↔ 唯一 `project_id`）。群成员**不必**同属一个组；群只表示「在讨论哪个项目」 |
| D5 | 权限真源 | **业务表 `authorize(user, project, action)`** + **写前飞书 ACL re-check（项目文件夹 token）**；组级角色可映射默认权限，但**门禁锚点是项目** |
| D6 | Agent 边界 | Hermes **只做生成**（summary 文案、回复话术等）；**全部业务服务由 Backend 提供**；**禁止** Agent tool 绕过鉴权直读写飞书/DB |
| D7 | 周报是否「有料」 | **以项目文件夹窗口 Drive diff 为主**；`weekly_cycles` 按 **project** 存 diff/审批态 |
| D8 | Drive 拓扑 | **组 = 一个 Drive 根**；**项目 = 组根下的一个文件夹**（`project.drive_folder_token`）；diff/上传/周报默认落在**项目文件夹子树**，不是整组根 |
| D9 | 组 vs 项目 | **Group**＝组织/盘根/人员池；**Project**＝可绑定群聊的业务单元（一项目一文件夹）。实现上两者都是一等实体 |
| D10 | **空周策略** | 项目窗口内无显著 diff：周三提醒；周四仍「本周无 Drive 变更」并提审 |
| D11 | **Diff 深度（MVP）** | **仅元数据 diff**（项目文件夹子树）；不做正文级 diff |
| D12 | **API 输出形态** | 写/长任务 **SSE**；短读 JSON；飞书事件瞬时 ACK |
| D13 | **IM 入口** | 飞书 IM/事件 **直达 FastAPI** |
| D14 | **一对多** | 多用户 × 多组 × 多项目 × 多会话；业务隔离 `user×project`（项目归属 `group`）；群上下文用 `chat→project`；对话记忆 `session_key` |
| D15 | **会话记忆** | transcript/MEMORY 在 Hermes；**禁止当 ACL**；生成所需的业务事实由 Backend 注入 |
| D16 | **Job 合同** | envelope + kind payload（§5.4）；scope 以 **project_ids** 为主 |
| D17 | **Hermes 调用方式** | Backend **单向**调用「生成」接口（传入已鉴权上下文 + 约束）；Hermes **无**写 tool、**无**私自调飞书；生成结果须经 Backend 校验后再落库/出站 |

其余默认：写操作强制幂等键；DM 须显式 `project_code`；群未绑定项目时只提示绑定不写。

### 0.1 组 / 项目 / 群 / Drive（评审必读）

```text
Group「AI 组」 ──drive_root_token──► 飞书【组根文件夹】
                     │
                     ├── Project「模型评测」── folder_token ──► 子文件夹（一项目一夹）
                     ├── Project「数据采集」── folder_token ──► 子文件夹
                     └── （组内其它资料，不绑定群也可存在）

Group「开发组」──drive_root_token──► 另一组根
                     └── Project「客户端重构」──► 子文件夹

飞书群 oc_aaa  ──project_chat_bindings──► Project「模型评测」
  · 群里可以有不同组的人；绑定的是「讨论的项目」，不是「整个组」
  · 该群 @Robot 的上传/diff/周报 → 只动该项目文件夹子树

周 summary = f( 项目文件夹在窗口内的 Drive metadata diff )
上传       = 写入该项目文件夹下 relative_path
```

### 0.2 入口与记忆（评审必读 · D13–D15）

```text
飞书 IM / 卡片回调 / 事件
        │  直接 HTTPS（Webhook 验签）或后端事件适配
        ▼
   PM Backend (FastAPI)     ← 主入口 · 一对多业务隔离 · 飞书出站
        │
        ├── 纯业务 / 定时 job  ──► PostgreSQL + Feishu OpenAPI
        │
        └── 需要「生成文案」时 ──► Hermes（仅生成）
                                    · session 记忆可选用
                                    · 输入=Backend 已鉴权的上下文包
                                    · 输出=文本/结构化草稿；**不**自带写权限
                                    · 落库/发飞书/改权限 **只回 Backend**
```

---

## 1. 总架构

```text
┌──────────────────────────────────────────────────────────────────┐
│ 飞书用户（多群 / 多 Owner / 一对多）                                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS（客户端 ↔ 飞书云）
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│ 飞书开放平台（IM / Drive / Wiki / 通讯录 / 事件订阅）                 │
└───────┬────────────────────────────────────────────▲─────────────┘
        │ ① 事件/消息：Webhook（首选进后端）            │ ⑤ OpenAPI
        │    或后端自持 WS 长连接适配                   │
        ▼                                              │
┌──────────────────────────────────────────────────────┴───────────┐
│  PM Backend（FastAPI · 主入口 · 业务真源编排）                      │
│  · Feishu Ingress：验签 / message_id 去重 / @ 门槛 / allowlist      │
│  · 一对多：open_id→user · chat_id→project · authorize(user,project,act)│
│  · Services / 状态机 / 幂等 / 审计 / outbox jobs                    │
│  · DialogueOrchestrator：需要 LLM 时调 Hermes；不需要则直接业务回复  │
│  · Feishu Egress：Drive / Wiki / IM / Contact（写前 ACL re-check） │
└───────┬──────────────────────────────┬───────────────────────────┘
        │ ② session 记忆 + 意图/槽位     │ ④ SQL
        ▼                              ▼
┌───────────────────────────┐    ┌─────────────────────────────────┐
│ Hermes（CLI 记忆框架）      │    │ PostgreSQL                       │
│ · 可选 session 记忆        │    │ users/groups/projects/members…  │
│ · **仅生成** summary/话术   │    │ chat绑定/ weekly / operations    │
│ · **无**写 tool 绕过鉴权    │    │ outbox_jobs / audit / remind_log │
└───────────────────────────┘    └─────────────────────────────────┘

旁路（不经用户对话）：
  Scheduler（APScheduler / 系统 cron / 可选 Hermes cron 只当触发器）
    → POST /internal/cron/* 或 入 outbox_jobs
    → Service 执行（可 SSE 观察进度）
```

### 1.1 进程与部署

| 组件 | 进程 | 说明 |
|------|------|------|
| **PM Backend** | 独立（主） | FastAPI：IM 入口、业务、幂等、飞书出站、job 消费 |
| **PostgreSQL** | 独立 | 业务真源（不含完整对话 transcript） |
| **Hermes** | 独立或同机旁路 | **会话记忆框架 + LLM 循环**；由 Backend 按 session 调用，**不是**飞书主入口 |
| feishu-pm-plugin | 可选 | 仅当仍用 Hermes tool 回调 Backend 时保留；**薄 HTTP client**，无业务真源 |
| （可选）Worker | 独立 | 消费 `outbox_jobs`、大 diff、对账（可与 Backend 同进程起步） |

本地开发：`docker compose` 起 PG + API；Hermes 本机 CLI；飞书事件指向 `http://127.0.0.1:8080/v1/feishu/event`（或内网穿透）。

### 1.2 信任边界

```text
不可信：LLM 生成的 email、group_code、是否「已确认」、session 记忆里的「我是 Owner」
半可信：飞书事件里的 open_id、chat_id、message_id（须 Backend 验签后再用）
可信：  后端用 open_id 查库得到的 user_id/email；DB 状态机；飞书 API 返回的 ACL
```

**生产强制：**

- 飞书事件：**验签** + `message_id` 去重后再入编排
- 写操作身份：**仅**来自已验签事件 / 可信回调头中的 `open_id`，再 `open_id → users`
- Hermes / LLM 回调 Backend：携带 `SERVICE_TOKEN` + Backend 已解析的 `actor_user_id` / `group_id`（或等价内部 claim）；**禁止**仅凭模型自报身份写库/写飞书
- Session 记忆与业务表分离：记忆可丢、可错；**授权只认 PG + ACL**

### 1.3 一对多与记忆隔离（D14 / D15）

| 维度 | 隔离键 | 谁负责 | 存哪里 |
|------|--------|--------|--------|
| 业务成员/角色 | `user_id` × `group_id` | FastAPI `authorize` | PG `group_members` |
| 群上下文 | `chat_id` → 唯一 `group_id` | FastAPI bindings | PG `group_chat_bindings` |
| 对话 transcript | **`session_key`** | Hermes（可选） | 非 PG 真源 |
| 偏好 MEMORY | session 策略 | Hermes | **禁止当 ACL** |
| 写操作/周报/diff | **`project_id`** + 周期/幂等键 | FastAPI | PG `operations` / `weekly_cycles` / … |
| 群上下文 | `chat_id` → **`project_id`** | FastAPI bindings | PG `project_chat_bindings` |

**推荐 `session_key`（一对多防串话）：**

```text
session_key = f"feishu:{chat_id}:{open_id}"
# 群内按人隔离；项目维度由 Backend 绑定表提供，不写进记忆当权限
# DM：feishu:dm:{open_id}:project:{project_id|pending}
```

**硬约束：**

1. Backend 调 Hermes 时 **必须**传入稳定 `session_key`，禁止多用户共用默认 session  
2. 用户 A 的 session **不得**读到用户 B 的 transcript / MEMORY  
3. 写路径只认 **chat→project 绑定** 或显式 `project_id`/`project_code`，不认模型口头「当前项目」  
4. list/读只返回 `authorize(user, project, …)` 通过的项目；禁止 Agent 直接枚举未授权项目详情  

---

## 2. 逻辑分层（后端内部）

```text
api/            # FastAPI routes：飞书事件入口、业务 REST、internal cron/jobs、SSE
services/       # 用例：Identity/Group/Authz/Member/DriveUpload/DriveDiff/
                #       Weekly/Remind/Operation/DialogueOrchestrator
domain/         # 状态机、角色→action、错误码、job kind
middleware/     # authorize(user, group, action)  — 业务门禁
adapters/
  feishu/       # 事件验签 · Drive / Wiki / Contact / IM
  hermes/       # 调用 Hermes CLI/运行时：run_turn(session_key, message, context)
  db/           # repositories
core/           # config、幂等、outbox、job envelope、logging
```

依赖方向：`api → services → domain/middleware → adapters`。

- **飞书进线**进 `api`（ingress），不经 Hermes Gateway。  
- **Hermes** 只被 `DialogueOrchestrator`（或 adapter）调用；**不**实现业务状态机。  
- 可选 **feishu-pm-plugin**：仅作为 Hermes 侧 tool → HTTP 回 Backend 的薄客户端。  
**服务层职责、写路径模板、与 job/API 映射**：见 [design-overview.md §4](./design-overview.md)。

## 3. 身份、组、项目与「一群一项目」

### 3.1 身份映射

```text
事件 open_id
  → users.open_id 命中？ → user_id, email
  → 否 → Contact 换 email → upsert users
  email 无法解析 → 拒绝写操作
```

| 字段 | 角色 |
|------|------|
| `users.email` | **业务主键** |
| `users.open_id` | IM/事件关联 |
| `users.union_id` | 可选跨应用 |

### 3.2 概念分层（必读）

| 概念 | 是什么 | 不是什么 |
|------|--------|----------|
| **Group 组** | 组织单元；拥有 **Drive 根**；人员池/默认角色来源 | 不是群聊绑定目标；不是周报 diff 的默认范围 |
| **Project 项目** | 业务讨论与交付单元；**对应组 Drive 根下的一个文件夹** | 不是第二套游离盘；必须归属某个 `group_id` |
| **Chat 群** | 飞书会话；**绑定唯一 project**（一群一项目） | 不要求群成员都来自同一组 |
| **Folder** | 飞书 `folder_token`；项目文件夹 = diff/上传锚点 | 不是 PG 主键（PG 用 project_id，token 为飞书侧引用） |

```text
authorize(actor_user, project_id, action)  ← 业务门禁主键
写飞书前再 ACL re-check(project.drive_folder_token)
```

### 3.3 一群一项目

```text
project_chat_bindings:
  chat_id  PRIMARY KEY / UNIQUE  →  project_id
project.group_id → groups
project.drive_folder_token → 须落在 groups.drive_root 子树内（创建/绑定时校验）
```

- 用户在群里说话 → 解析 **唯一 project**（再带出 group 仅作归属）
- 未绑定 → 提示管理员执行「绑定本群到项目文件夹」API，不猜测
- DM → 显式 `project_code` / `project_id`
- **禁止**用「用户默认第一组」或「第一项目」静默写

### 3.4 角色与 action（锚在项目）

成员可来自：`project_members`（优先）和/或继承 `group_members`（产品可配；**鉴权实现仍归一到 project 上的有效角色**）。

| 有效 role | 允许的 action（初版） |
|-----------|----------------------|
| owner | `read_project_context`, `upload_drive`, `manage_members`, `manage_binding`, `request_weekly_summary`, `approve_weekly`, `write_wiki`（经审批） |
| member | `read_project_context`, `upload_drive` |
| viewer | `read_project_context` |

未知 action → Deny。  
Hermes **不出现在** action 调用链里（无 `hermes.*` 业务 action）。

### 3.5 Hermes 仅生成（D6 / D17）

```text
允许：
  Backend ──已鉴权上下文──► Hermes.generate(kind, input) ──文本/草稿──► Backend
  再由 Backend：校验 → 写 PG / 调飞书 IM·Drive·Wiki

禁止：
  Hermes 自带飞书 token 写盘
  Hermes tool 直接 UPDATE weekly_cycles / 改成员
  前端/Agent 拿用户句就跳过 authorize
```

生成 kind 示例：`weekly_summary_from_diff`、`empty_week_copy`、`im_reply_phrase`（均不包含授权结论）。

## 4. 数据模型（PostgreSQL）

### 4.1 ER 概要

```text
users 1──* group_members *──1 groups
groups 1──* projects
projects 1──* project_members *──1 users
projects 1──1‥0 project_chat_bindings（chat_id UNIQUE）
projects 1──* weekly_cycles
projects 1──* drive_snapshots
projects 1──* remind_log
users / projects 1──* operations → audit_events
outbox_jobs（payload 含 project scope）
```

### 4.2 表定义（实现草案）

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           CITEXT NOT NULL UNIQUE,
  open_id         TEXT UNIQUE,
  union_id        TEXT UNIQUE,
  display_name    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 组：组织 + Drive 根（人员池）
CREATE TABLE groups (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code                     TEXT NOT NULL UNIQUE,
  name                     TEXT NOT NULL,
  drive_root_folder_token  TEXT NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'archived')),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE group_members (
  group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('owner', 'member', 'viewer')),
  source      TEXT NOT NULL DEFAULT 'manual',
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (group_id, user_id)
);

-- 项目：组 Drive 下的一个文件夹；群绑定与周报/diff 锚点
CREATE TABLE projects (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id             UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  code                 TEXT NOT NULL,              -- 组内唯一
  name                 TEXT NOT NULL,
  drive_folder_token   TEXT NOT NULL,              -- 项目文件夹
  drive_folder_path    TEXT,                      -- 可选展示路径
  wiki_node_token      TEXT,
  owner_user_id        UUID REFERENCES users(id),
  diff_exclude_globs   JSONB NOT NULL DEFAULT '[]',
  status               TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'archived')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (group_id, code),
  UNIQUE (drive_folder_token)
);

-- 一群一项目（群成员可跨组）
CREATE TABLE project_chat_bindings (
  chat_id      TEXT PRIMARY KEY,
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  bound_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  bound_by     UUID REFERENCES users(id)
);

CREATE TABLE project_members (
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('owner', 'member', 'viewer')),
  source      TEXT NOT NULL DEFAULT 'manual'
              CHECK (source IN ('manual', 'invite_flow', 'sync', 'group_inherit')),
  feishu_perm TEXT,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, user_id)
);

CREATE TABLE drive_snapshots (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  captured_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  year_week     TEXT,
  root_token    TEXT NOT NULL,           -- 一般为 project.drive_folder_token
  manifest_json JSONB NOT NULL,
  content_hash  TEXT
);
CREATE INDEX drive_snapshots_project_time_idx
  ON drive_snapshots (project_id, captured_at DESC);

CREATE TABLE weekly_cycles (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  year_week         TEXT NOT NULL,
  activity_status   TEXT NOT NULL DEFAULT 'none'
    CHECK (activity_status IN (
      'none', 'has_diff', 'summarized', 'pending_approval',
      'approved', 'rejected'
    )),
  diff_summary_json JSONB,
  summary_text      TEXT,
  window_start      TIMESTAMPTZ,
  window_end        TIMESTAMPTZ,
  approval_status   TEXT NOT NULL DEFAULT 'none'
    CHECK (approval_status IN ('none', 'pending', 'approved', 'rejected')),
  reviewer_user_id  UUID REFERENCES users(id),
  decision_comment  TEXT,
  wiki_page_token   TEXT,
  wiki_page_url     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, year_week)
);

CREATE TABLE operations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key  TEXT NOT NULL UNIQUE,
  kind             TEXT NOT NULL,
  actor_user_id    UUID NOT NULL REFERENCES users(id),
  project_id       UUID REFERENCES projects(id),
  group_id         UUID REFERENCES groups(id),
  request_hash     TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'accepted'
    CHECK (status IN (
      'accepted', 'running', 'succeeded', 'failed', 'compensating'
    )),
  result_json      JSONB,
  error_code       TEXT,
  error_message    TEXT,
  feishu_refs      JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX operations_project_created_idx
  ON operations (project_id, created_at DESC);

CREATE TABLE audit_events (
  id            BIGSERIAL PRIMARY KEY,
  at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_id    TEXT,
  operation_id  UUID REFERENCES operations(id),
  actor_user_id UUID REFERENCES users(id),
  project_id    UUID REFERENCES projects(id),
  group_id      UUID REFERENCES groups(id),
  action        TEXT NOT NULL,
  detail_json   JSONB
);

CREATE TABLE remind_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  year_week   TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN (
                'wed_activity', 'thu_activity', 'thu_approval'
              )),
  sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, year_week, kind)
);

CREATE TABLE outbox_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind         TEXT NOT NULL,
  payload      JSONB NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'processing', 'done', 'dead')),
  attempts     INT NOT NULL DEFAULT 0,
  next_run_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.3 周报状态机（项目 diff + 空周仍提审）

```text
none
  ├─ 项目文件夹有显著元数据 diff → has_diff → summarized → pending_approval → approved|rejected
  └─ 空周 → Wed remind → Thu 仍 summarized（「无变更」）→ pending_approval → …
```

### 4.4 Drive diff 范围

```text
根 = project.drive_folder_token（不是 group.drive_root，除非项目误配成根——创建时校验子树）
MVP：元数据 list → added/modified/deleted/moved → diff_summary_json
summary_text：Backend 可调 Hermes.generate（仅文案）；批准写 Wiki 仍走 Backend
```

## 5. 幂等设计

### 5.1 规则

1. 所有 **写接口** 要求头：`Idempotency-Key: <uuid>`  
2. `request_hash = sha256(canonical_json({kind, actor_user_id, project_id, body}))`  
3. 同 key + 同 hash + `succeeded` → **原样返回首次结果**（`idempotent_replay: true`）  
4. 同 key + 不同 hash → `409 IDEMPOTENCY_KEY_REUSE`  
5. 同 key + `running` → `409 OPERATION_IN_PROGRESS` 或短轮询 `GET /operations/{id}`  

### 5.2 Kind 与自然唯一

| kind | 补充唯一约束 |
|------|----------------|
| `drive.upload` | 可选 content_hash；写入组根下路径；间接进入下周 diff |
| `drive.diff.capture` | 同 group+时间窗快照去重 |
| `members.invite` | 目标已是成员 → success no-op |
| `members.remove` | 已不在 → success no-op |
| `weekly.approve` | cycle 已 approved → 返回已有 wiki |
| `weekly.reject` | 已 rejected → no-op |
| `remind.*` | `remind_log` UNIQUE 防双发 |

### 5.3 飞书出站顺序

```text
INSERT operation(running)
→ Feishu API（资源名/备注可带 operation_id 前缀便于对账）
→ 成功：更新业务表 + operation(succeeded, feishu_refs)
→ 飞书成功本地失败：operation(compensating) + outbox 修复
→ 飞书失败：operation(failed)；可重试类允许同 key 再入（策略：仅 failed+可重试）
```

---

## 5.4 Job 统一合同与每次 payload（D16）

所有 **定时任务、outbox 补偿、内部批处理** 使用同一逻辑模型（可落 `outbox_jobs` 表，或同步 HTTP 触发后立即执行）。

### 5.4.1 通用 envelope

```json
{
  "job_id": "uuid",
  "kind": "weekly.remind",
  "schema_version": 1,
  "created_at": "2026-10-28T02:00:00Z",
  "trigger": "cron" | "api" | "outbox" | "event",
  "request_id": "optional-trace-id",
  "idempotency_key": "optional-for-write-ish-jobs",
  "actor": {
    "type": "system" | "user",
    "user_id": null,
    "service": "pm-backend"
  },
  "scope": {
    "project_ids": null,
    "group_ids": null,
    "year_week": "2026-W44"
  },
  "payload": { }
}
```

| 字段 | 说明 |
|------|------|
| `job_id` | 全局唯一；写入 `outbox_jobs.id` 或运行日志 |
| `kind` | 稳定枚举，见下表；**禁止**自由字符串当业务分支 |
| `schema_version` | payload 兼容版本；破坏性变更 +1 |
| `trigger` | 来源：调度器 / 人工 API / 补偿 / 飞书事件衍生 |
| `actor` | 系统 job 为 `system`；用户触发的内部二次任务可带 `user_id` |
| `scope` | 批范围；`project_ids: null` = 全部 active **项目**（可按 group_ids 过滤） |
| `payload` | **kind 专用体**；envelope 字段不重复塞进 payload |
| `idempotency_key` | 写飞书/改状态的 job 建议带；可与 `kind+scope` 自然键二选一 |

`outbox_jobs.payload` 列建议存 **整份 envelope 的 JSON**（或至少 `{kind, schema_version, payload, scope}`），`kind` 列与 envelope.kind 冗余便于索引。

### 5.4.2 kind 一览与 payload

#### A. 入口与对话（常同步，可选用 job 异步化重试）

| kind | 何时 | payload |
|------|------|---------|
| `im.event.ingest` | 飞书事件入站落队（可选） | 见下 |
| `dialogue.turn` | 需 LLM 的一轮对话 | 见下 |

**`im.event.ingest`**

```json
{
  "feishu_event_id": "…",
  "event_type": "im.message.receive_v1",
  "encrypt_ok": true,
  "message_id": "om_…",
  "chat_id": "oc_…",
  "open_id": "ou_…",
  "chat_type": "group" | "p2p",
  "message_type": "text" | "interactive" | "…",
  "text": "用户原文或抽取文本",
  "raw_event_ref": "optional-object-storage-key-or-omitted"
}
```

说明：`raw` 大包体可只存对象存储引用；验签必须在入队前完成。`message_id` 用于去重。

**`dialogue.turn`**（可选编排；**不含写权限**）

```json
{
  "session_key": "feishu:oc_xxx:ou_yyy",
  "open_id": "ou_…",
  "chat_id": "oc_…",
  "project_id": "uuid-or-null",
  "project_resolve_source": "chat_binding" | "explicit_code" | "unresolved",
  "group_id": "uuid-or-null",
  "user_text": "…",
  "attachment_refs": [],
  "generation_only": true,
  "context_snapshot": {
    "project_code": "model-eval",
    "project_name": "模型评测",
    "group_code": "ai",
    "role": "member",
    "folder_path": "/AI组/模型评测"
  }
}
```

说明：编排结果若需写库/写飞书，**只能**触发 Backend API；Hermes 即使返回 route 也须后端再次 `authorize`。

#### B. 周节奏 / Drive（主功能 1）

| kind | 调度建议 | payload |
|------|----------|---------|
| `drive.snapshot.capture` | 可选每日或周四前 | 见下 |
| `weekly.remind` | 周三（及可选周四） | 见下 |
| `weekly.summarize_request_approval` | 周四 | 见下 |

**`drive.snapshot.capture`**

```json
{
  "project_ids": null,
  "group_ids": null,
  "window": {
    "year_week": "2026-W44",
    "start": "2026-10-27T00:00:00Z",
    "end": "2026-11-03T00:00:00Z"
  },
  "mode": "metadata_only",
  "force": false
}
```

- `mode` 固定 MVP=`metadata_only`（D11）  
- `force=true` 忽略「已有同窗 snapshot」短路径（运维）

**`weekly.remind`**

```json
{
  "remind_kind": "wed_activity" | "thu_activity",
  "year_week": "2026-W44",
  "project_ids": null,
  "group_ids": null,
  "only_if_no_significant_diff": true,
  "dry_run": false
}
```

- `remind_log (project_id, year_week, kind)` 防双发  

**`weekly.summarize_request_approval`**

```json
{
  "year_week": "2026-W44",
  "project_ids": null,
  "group_ids": null,
  "window": {
    "start": "2026-10-27T00:00:00Z",
    "end": "2026-11-03T00:00:00Z"
  },
  "diff_mode": "metadata_only",
  "include_empty_week": true,
  "request_approval": true,
  "notify_channel": "project_bound_chat",
  "use_hermes_for_copy": true,
  "dry_run": false
}
```

- 按 **project** 扫文件夹 diff；`use_hermes_for_copy` 仅影响 summary **文案生成**  
- 单项目失败隔离：`items[].project_id`  

#### C. 用户写路径衍生 / 成员

常同步 API；若异步化则 envelope.actor.type=`user`。

| kind | payload |
|------|---------|
| `drive.upload.commit` | `{ "project_id", "preview_token", "confirm": true, "relative_path?", "content_hash?" }` |
| `members.invite` | `{ "project_id", "email", "role", "sync_feishu_drive": true }` |
| `members.remove` | `{ "project_id", "email", "sync_feishu_drive": true }` |
| `weekly.decision` | `{ "project_id", "year_week", "decision": "approve"\|"reject", "comment": "" }` |
| `project.bind_chat` | `{ "project_id", "chat_id" }` |
| `generation.weekly_summary` | 仅内部：`{ "project_id", "year_week", "diff_summary_json" }` → Hermes 文案，**不写 Wiki** |

写类必须有 `idempotency_key`（HTTP 头或 envelope 字段）。

#### D. 补偿与对账（P5）

| kind | payload |
|------|---------|
| `outbox.compensate_operation` | `{ "operation_id": "uuid", "reason": "local_update_failed_after_feishu_ok" }` |
| `reconcile.drive_acl` | `{ "project_id": "uuid", "direction": "feishu_to_db_report_only", "apply_changes": false }` |
| `reconcile.operation` | `{ "operation_id": "uuid" }` 或 `{ "project_id", "since": "ISO" }` |

默认 `apply_changes=false`：只报告差异，不静默改 Owner。

### 5.4.3 HTTP 触发与 envelope 的关系

| HTTP | 对应 kind | body |
|------|-----------|------|
| `POST /internal/cron/drive/capture-snapshots` | `drive.snapshot.capture` | 同 payload（可无 envelope 包装；服务端补 job_id） |
| `POST /internal/cron/weekly/remind` | `weekly.remind` | 同 payload |
| `POST /internal/cron/weekly/summarize-and-request-approval` | `weekly.summarize_request_approval` | 同 payload |
| `POST /internal/jobs/sync-drive-acl` | `reconcile.drive_acl` | 同 payload |
| `POST /internal/jobs/enqueue` | 任意 | **完整 envelope**（运维/测试） |

同步执行时：仍生成 `job_id` 写入审计/日志；可选不落 `outbox_jobs`。  
异步：`INSERT outbox_jobs(kind, payload=envelope)` → worker 领取。

### 5.4.4 Job 结果（批处理 JSON 或 SSE `result.data`）

```json
{
  "job_id": "…",
  "kind": "weekly.remind",
  "ok": true,
  "started_at": "…",
  "finished_at": "…",
  "summary": { "scanned": 10, "sent": 3, "skipped": 7, "failed": 0 },
  "items": [
    {
      "project_id": "…",
      "ok": true,
      "action": "sent" | "skipped_has_diff" | "skipped_already_logged" | "failed",
      "error": null
    }
  ]
}
```

---

---

## 6. 接口设计（HTTP API）

### 6.1 约定

| 项 | 值 |
|----|-----|
| Base URL | `https://pm-api.internal/v1`（本地 `http://127.0.0.1:8080/v1`） |
| **IM 入口** | 飞书事件 **直达** Backend（D13）；见 §6.1.0 |
| 鉴权 | 内部 API：`Authorization: Bearer <SERVICE_TOKEN>`（Hermes tool 回调 / cron / worker 共享）；飞书事件：平台签名校验 |
| 用户上下文 | 事件内 `open_id`/`chat_id`；内部回调可再带 `X-Feishu-Open-Id` / `X-Actor-User-Id` / `X-Request-Id` |
| 幂等 | 写：`Idempotency-Key` 必填 |
| 时间 | ISO8601 UTC |
| **输出（D12）** | 长任务/写操作：**SSE**；短只读：JSON；飞书事件回调接口本身按飞书要求瞬时 ACK |

---

### 6.1.0 飞书 IM 入口（D13）

#### `POST /v1/feishu/event`

飞书开放平台事件订阅（Webhook）主回调。

| 步骤 | 行为 |
|------|------|
| 1 | URL 校验 / 解密 / **签名验证**；失败 4xx，不入业务 |
| 2 | `message_id` / `event_id` **去重**（短 TTL 缓存或 DB） |
| 3 | 解析 `open_id`、`chat_id`、文本/卡片 action |
| 4 | `IdentityService` + `ProjectContextService`（**一群一项目**） |
| 5a | 结构化命令/卡片 → **直接 Service**（鉴权在 Service 内） |
| 5b | 需生成话术 → Backend 调 Hermes.**generate only**（不赋写权） |
| 6 | 任何写：Backend `authorize(user,project,action)` + 幂等 + 项目文件夹 ACL |
| 7 | Backend 出站 IM；对飞书 HTTP 尽早 ACK |

```text
飞书 POST /feishu/event
  → 验签 & 去重
  → resolve user + chat→project
  → authorize + services（写全在 Backend）
  → (optional) Hermes.generate 文案
  → 飞书发消息 / 写 项目文件夹|Wiki
```

#### `POST /v1/feishu/card`（可选拆分）

若卡片回调与消息事件分域名，合同同级：验签 → 解析 action → **不靠 LLM 改 decision** → `weekly.decision` / upload confirm 等。

#### 与 Hermes 的调用方向

```text
正确：Feishu → FastAPI → Hermes →（tool 可选）→ FastAPI
错误：Feishu → Hermes Gateway → plugin → FastAPI   ← 已废弃为主路径（D13）
```

---

### 6.1.1 输出：SSE 为流式合同（D12）

**原则**：插件 tool 与用户可感知的「进行中」能力，后端**用 SSE 推事件**；不要用一块巨大 JSON 干等 diff/汇总/写飞书整段完成（cron 内部批处理可同进程调用 service，但若经 HTTP 暴露给插件，仍走 SSE）。

#### 传输

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

- 一帧：可选 `id:` / `event:` + `data:`（JSON 单行）+ 空行  
- 客户端（插件）按 `event` 分发；未知 event 可忽略或打日志  
- 心跳：建议每 15s `event: ping`（`data: {}`），防代理断连  
- 结束：`event: result` 或 `event: error` 之后服务端关闭流；**成功与业务失败都在流内结束**，避免仅靠 HTTP 4xx 丢进度（握手阶段鉴权失败仍可用非 SSE 的 401/403 JSON）

#### 标准事件类型

| event | 何时 | data 要点 |
|-------|------|-----------|
| `meta` | 流开始 | `request_id`, `operation_id?`, `idempotent_replay?` |
| `progress` | 过程 | `stage`, `message`, `percent?`, `detail?` |
| `delta` | 可展示增量（可选） | `text` 或结构化片段（如 summary 生成中） |
| `ping` | 心跳 | `{}` 或 `ts` |
| `result` | **成功终态** | 与下方「结果信封」一致：`ok: true`, `data`, … |
| `error` | **失败终态** | `ok: false`, `error: { code, message, details }` |

#### 结果信封（`result` / 短 JSON 共用）

```json
{
  "ok": true,
  "request_id": "…",
  "operation_id": "…",
  "idempotent_replay": false,
  "data": { },
  "error": null
}
```

失败终态（`event: error` 的 data，或短 JSON body）：

```json
{
  "ok": false,
  "request_id": "…",
  "operation_id": "…",
  "idempotent_replay": false,
  "data": null,
  "error": {
    "code": "FORBIDDEN_ACTION",
    "message": "user is not a member of group",
    "details": {}
  }
}
```

#### 流表示例（上传 commit）

```text
event: meta
data: {"request_id":"r1","operation_id":"o1","idempotent_replay":false}

event: progress
data: {"stage":"authorize","message":"checking permission"}

event: progress
data: {"stage":"acl_recheck","message":"checking drive ACL"}

event: progress
data: {"stage":"drive_write","message":"uploading file"}

event: result
data: {"ok":true,"request_id":"r1","operation_id":"o1","idempotent_replay":false,"data":{"file_url":"…"},"error":null}
```

#### 哪些接口用 SSE

| 类别 | 形态 | 说明 |
|------|------|------|
| 写操作（upload commit、member、weekly decision） | **SSE** | progress → result/error；幂等重放可立刻 `meta.idempotent_replay=true` + `result` |
| 周报 summarize / diff capture（若插件或管理端触发） | **SSE** | stage：snapshot → diff → summarize → notify |
| Cron `/internal/cron/*` | **SSE 或 JSON 批结果** | 服务账号批处理可 JSON 汇总；若需观察进度则 SSE |
| 短只读（`/health`、`/me`、`/context/resolve`、`/groups/mine`） | **JSON 即可** | 可选 `Accept: text/event-stream` 时仍可用单帧 `result` 包一层，**不强制** |

#### 调用方消费约定（Hermes tool 回调或内部 client）

```text
caller（Hermes thin tool 或 Backend 内 client）:
  POST/GET 后端（Accept: text/event-stream）
  → 读 SSE
  → 可选把 progress 转用户可见中间态（由 Backend 发 IM，或 Hermes 话术）
  → 取最终 result/error → JSON 字符串交 LLM 或直接结束编排
  → 禁止在未收到 result/error 时瞎编成功
```

幂等：同一 `Idempotency-Key` 重放时，可短流：`meta(idempotent_replay=true)` + 缓存的 `result`。

**常见 error.code：**

| code | HTTP | 含义 |
|------|------|------|
| `UNAUTHORIZED` | 401 | 缺服务 token / 无法解析用户 |
| `FORBIDDEN_ACTION` | 403 | authorize 失败或飞书 ACL 失败 |
| `NOT_FOUND` | 404 | 组/周期不存在 |
| `VALIDATION_ERROR` | 422 | 参数错误 |
| `CONFLICT` | 409 | 状态机冲突 |
| `IDEMPOTENCY_KEY_REUSE` | 409 | 同 key 不同 body |
| `OPERATION_IN_PROGRESS` | 409 | 处理中 |
| `CHAT_NOT_BOUND` | 400 | 群未绑定**组** |
| `FEISHU_ERROR` | 502 | 飞书侧失败（可带 retryable） |
| `INTERNAL` | 500 | 未分类 |

### 6.2 健康与元数据

#### `GET /health`

```json
{ "ok": true, "data": { "status": "up", "db": "ok" }, "error": null }
```

#### `GET /ready`

含 DB ping。

---

### 6.3 身份与上下文（只读）

#### `GET /me`

Headers: 可信 `open_id`（或事件已解析的 actor）。

```json
{
  "ok": true,
  "data": {
    "user_id": "…",
    "email": "a@co.com",
    "open_id": "ou_…",
    "display_name": "Alice"
  },
  "error": null
}
```

#### `GET /context/resolve`

Headers: `open_id` + 可选 `chat_id`；或 query `project_code`。

**Schema（响应 data）**

```json
{
  "source": "chat_binding" | "explicit_code" | "unresolved",
  "project": {
    "id": "uuid",
    "code": "model-eval",
    "name": "模型评测",
    "group_id": "uuid",
    "group_code": "ai",
    "drive_folder_token": "fld_proj",
    "drive_folder_path": "/AI组/模型评测",
    "role": "owner" | "member" | "viewer",
    "wiki_node_token": "…"
  } | null,
  "hint": "CHAT_NOT_BOUND 时的人话提示"
}
```

#### `GET /projects/mine`

当前用户 `authorize(read_project_context)` 通过的项目列表。

```json
{
  "ok": true,
  "data": {
    "projects": [
      {
        "id": "…",
        "code": "model-eval",
        "name": "模型评测",
        "group_code": "ai",
        "role": "member",
        "drive_folder_path": "/AI组/模型评测",
        "bound_chat_id": "oc_…" 
      }
    ],
    "count": 1
  }
}
```

#### `GET /groups/mine`（可选）

仅组人员池视图；**不**替代项目列表。周报/上传仍以 project 为准。

---

### 6.4 组与项目目录（管理）

#### `POST /groups`

```json
{
  "code": "ai",
  "name": "AI 组",
  "drive_root_folder_token": "fld_group_root",
  "owner_email": "lead@co.com"
}
```

#### `POST /groups/{group_id}/projects` — 在组 Drive 下登记项目文件夹

```json
{
  "code": "model-eval",
  "name": "模型评测",
  "drive_folder_token": "fld_proj",
  "drive_folder_path": "/AI组/模型评测",
  "owner_email": "pm@co.com",
  "wiki_node_token": null,
  "create_folder_if_missing": false
}
```

**规则：**

- `drive_folder_token` 必须是该组 `drive_root` 子树内节点（Backend 调飞书校验 parent 链）
- 一项目一 token（UNIQUE）
- 需要 `manage_members` 或组 owner 类权限（实现矩阵定）

#### `GET /groups/{group_id}/projects`

组内项目目录（调用方须对组有可见性）。

---

### 6.5 群 ↔ 项目绑定（一群一项目）

#### `POST /projects/{project_id}/bindings/chat`

```json
{
  "chat_id": "oc_xxx",
  "confirm": true
}
```

**响应 data**

```json
{
  "chat_id": "oc_xxx",
  "project_id": "…",
  "project_code": "model-eval",
  "bound_at": "ISO-8601"
}
```

- `chat_id` 已绑其它项目 → `409 CHAT_ALREADY_BOUND`
- 鉴权：`manage_binding` 或项目 owner
- **不**要求群成员 ⊆ 组成员

#### `DELETE /projects/{project_id}/bindings/chat/{chat_id}`

解绑。

#### `GET /bindings/chat/{chat_id}`

反查当前绑定（只读；无绑定 `404` / `CHAT_NOT_BOUND`）。

---

### 6.6 项目成员

#### `POST /projects/{project_id}/members`

```json
{
  "email": "u@co.com",
  "role": "member",
  "sync_feishu_drive": true
}
```

`sync_feishu_drive=true` → 对 **项目文件夹** 加协作者（非整组根）。

#### `DELETE /projects/{project_id}/members/{email}`

#### `GET /projects/{project_id}/members`

---

### 6.7 Drive：读 / diff / 上传（均锚定 project 文件夹）

#### `GET /projects/{project_id}/drive/tree`（只读清单）

Query: `depth?`（默认有限深）

```json
{
  "ok": true,
  "data": {
    "project_id": "…",
    "root_token": "fld_proj",
    "entries": [
      {
        "token": "…",
        "name": "notes.md",
        "type": "file",
        "parent_token": "fld_proj",
        "modified_time": "ISO-8601"
      }
    ]
  }
}
```

须 `read_project_context`。

#### `GET /projects/{project_id}/drive/diff`

Query: `from`/`to` 或 `year_week`

```json
{
  "ok": true,
  "data": {
    "project_id": "…",
    "window_start": "…",
    "window_end": "…",
    "mode": "metadata_only",
    "diff": {
      "added": [ { "token", "name", "path", "modified_time" } ],
      "modified": [ … ],
      "deleted": [ … ],
      "moved": [ { "token", "from_path", "to_path" } ]
    },
    "significant": true
  }
}
```

#### `POST /projects/{project_id}/drive/snapshots`（可 SSE）

手工/job 触发 capture；body 可空或 `{ "year_week": "2026-W44" }`。

#### `POST /projects/{project_id}/drive/uploads/preview`

```json
{
  "title": "实验记录",
  "relative_path": "2026/W44/",
  "content_markdown": "…",
  "content_hash": "sha256-…"
}
```

- 路径相对 **项目文件夹**
- 不写飞书；返回：

```json
{
  "preview_token": "…",
  "expires_at": "…",
  "resolved_path": "/AI组/模型评测/2026/W44/实验记录"
}
```

#### `POST /projects/{project_id}/drive/uploads/commit`（SSE）

Headers: `Idempotency-Key`

```json
{ "preview_token": "…", "confirm": true }
```

流程：authorize `upload_drive` → 项目文件夹 ACL → 写飞书 → `operations`。

---

### 6.8 周报：diff → summary → 审批 → Wiki

全链路均带 `project_id`；文案生成可调 Hermes，**审批与 Wiki 只走 Backend**。

#### `POST /internal/cron/drive/capture-snapshots`

Body = job payload（`project_ids` 等），见 §5.4。

#### `POST /internal/cron/weekly/remind`

```json
{
  "remind_kind": "wed_activity",
  "year_week": "2026-W44",
  "project_ids": null
}
```

#### `POST /internal/cron/weekly/summarize-and-request-approval`（可 SSE）

```json
{
  "year_week": "2026-W44",
  "project_ids": null,
  "include_empty_week": true,
  "use_hermes_for_copy": true
}
```

**单项目处理步骤（服务内）：**

1. authorize 系统 actor 或跳过（internal token）  
2. metadata diff @ `project.drive_folder_token`  
3. 写 `weekly_cycles.diff_summary_json`  
4. 若 `use_hermes_for_copy`：`Hermes.generate("weekly_summary_from_diff", {diff, project_meta})` → **仅字符串**  
5. 空周模板或生成文案写入 `summary_text`；状态 → `pending_approval`  
6. IM 通知 **项目绑定群** 或 Owner（配置）  
7. **不**在本步写 Wiki  

**响应 items[] schema**

```json
{
  "project_id": "…",
  "ok": true,
  "activity_status": "pending_approval",
  "significant_diff": false,
  "summary_excerpt": "本周无 Drive 变更…",
  "error": null
}
```

#### `GET /projects/{project_id}/weekly/{year_week}`

```json
{
  "ok": true,
  "data": {
    "project_id": "…",
    "year_week": "2026-W44",
    "activity_status": "pending_approval",
    "approval_status": "pending",
    "diff_summary_json": { "added": [], "modified": [], "deleted": [], "moved": [] },
    "summary_text": "…",
    "window_start": "…",
    "window_end": "…",
    "wiki_page_url": null
  }
}
```

#### `POST /projects/{project_id}/weekly/{year_week}/decision`（SSE）

Headers: `Idempotency-Key`；actor 须 `approve_weekly`。

```json
{
  "decision": "approve" | "reject",
  "comment": "可选"
}
```

- `reject` → `rejected`，不写 Wiki  
- `approve` → 再 ACL → 写 Wiki（Backend Feishu adapter）→ `approved` + url  
- **禁止** Hermes 直接 decision  

#### `POST /internal/generation/weekly-summary`（可选，仅服务间）

供 Backend 自测生成；**仍不写 Wiki**。

```json
{
  "project_id": "…",
  "year_week": "2026-W44",
  "diff_summary_json": { },
  "style": "bullet_zh"
}
```

```json
{
  "ok": true,
  "data": { "summary_text": "…", "provider": "hermes" }
}
```

---

### 6.9 操作查询与对账

#### `GET /operations/{operation_id}`

#### `POST /internal/jobs/sync-drive-acl`

```json
{ "project_id": "…", "apply_changes": false }
```

#### `POST /internal/jobs/enqueue`

完整 job envelope（§5.4）。

---

### 6.10 错误码（业务常用）

| code | 含义 |
|------|------|
| `UNAUTHORIZED` | 无服务令牌 / 无法解析用户 |
| `FORBIDDEN_ACTION` | project 上 authorize 失败或 ACL 失败 |
| `NOT_FOUND` | 组/项目/周期不存在 |
| `CHAT_NOT_BOUND` | 群未绑定项目 |
| `CHAT_ALREADY_BOUND` | 群已绑其它项目 |
| `FOLDER_NOT_UNDER_GROUP_ROOT` | 项目文件夹不在组 Drive 根下 |
| `VALIDATION_ERROR` | 参数错 |
| `CONFLICT` / `WEEKLY_INVALID_TRANSITION` | 状态机冲突 |
| `IDEMPOTENCY_KEY_REUSE` | 同 key 不同 body |
| `OPERATION_IN_PROGRESS` | 处理中 |
| `FEISHU_ERROR` | 飞书侧失败 |
| `GENERATION_FAILED` | Hermes 生成失败（可回退模板） |

---

## 7. Hermes：仅生成（D6 / D17）

### 7.1 边界

| Hermes 可以 | Hermes 不可以 |
|-------------|----------------|
| 根据 Backend 传入的 **已鉴权** diff/上下文 **生成** summary 文案 | 自己决定「谁有权批准」 |
| 生成 IM 话术、空周文案 | 持有飞书写 token / 调 Drive·Wiki·成员 API |
| 可选维护 session transcript | 用 MEMORY 当 ACL 或改 `weekly_cycles` |
| 返回纯文本 / 受限 JSON 草稿 | 通过 tool **绕过** Backend `authorize` |

```text
Backend Service
  →（已通过 authorize / 已算完 diff）
  → hermes.generate({ kind, input_snapshot, locale })
  → 得到 text
  → Backend 校验长度/敏感策略 → 写入 weekly_cycles.summary_text 或发出 IM
```

### 7.2 生成请求 schema（Backend → Hermes）

```json
{
  "kind": "weekly_summary_from_diff" | "empty_week_copy" | "im_reply_phrase",
  "request_id": "…",
  "locale": "zh-CN",
  "input": {
    "project": { "code": "model-eval", "name": "模型评测", "group_code": "ai" },
    "year_week": "2026-W44",
    "window": { "start": "…", "end": "…" },
    "diff_summary_json": { "added": [], "modified": [], "deleted": [], "moved": [] },
    "constraints": { "max_chars": 2000, "no_acl_claims": true }
  }
}
```

### 7.3 生成响应 schema

```json
{
  "ok": true,
  "kind": "weekly_summary_from_diff",
  "text": "本周变更：…",
  "warnings": []
}
```

失败由 Backend 捕获 → 可选模板回退；**不影响**已写入的 diff_json。

### 7.4 可选 thin plugin

若仍用 Hermes function calling：tools **只能**打 Backend HTTP，且写接口仍走 Backend 鉴权；**推荐关闭**写类 tool，改由 Backend 事件编排。P0 骨架 `pm_*` 仅用于本地演练，生产以 FastAPI 为准。

## 8. 鉴权与安全

| 层 | 机制 |
|----|------|
| 飞书入站 | 事件 **签名校验** + 去重；encrypt key 仅 Backend |
| 服务间 | `SERVICE_TOKEN` 或 mTLS（Hermes/worker → API；生产建议轮换） |
| 用户 | 事件或可信头中的 `open_id` → DB user；写操作强制 |
| Bot 使用门槛 | Backend allowlist（open_id/email/部门） |
| 飞书出站 | Bot app 身份调 OpenAPI；**仍做 per-user ACL re-check** |
| 一对多 | `authorize(user,project,action)` + chat→project；禁串项目写；Hermes 无写权 |
| 密钥 | `.env` / 密钥管理；不进 git |
| 审计 | 所有写 operation + audit_events；job 带 job_id |
| LLM / Hermes | 无飞书长期 token；无 DB 直访；记忆非 ACL |

---

## 9. 重试与 Fallback

| 层级 | 策略 |
|------|------|
| 飞书 Webhook | 快速 ACK；业务异步；失败可出站补偿 |
| 事件 | message_id / event_id 去重 |
| Hermes/LLM | fallback provider；意图不清则追问，不调写 API；session 级重试不串 key |
| 后端→飞书 | 429/5xx 指数退避 ≤3；403/4xx 业务错误不重试 |
| 幂等写 | 同 Idempotency-Key 重试安全 |
| Cron / job | **单组失败隔离**；`remind_log` / 自然键防双发；见 §5.4 结果 items |
| 补偿 | `compensating` + `outbox_jobs`（payload=envelope） |

---

## 10. 配置项（后端）

```bash
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/feishu_pm
SERVICE_TOKEN=…
FEISHU_APP_ID=…
FEISHU_APP_SECRET=…
FEISHU_VERIFICATION_TOKEN=…
FEISHU_ENCRYPT_KEY=…
FEISHU_DOMAIN=feishu
FEISHU_EVENT_PATH=/v1/feishu/event
# Hermes（对话记忆）
HERMES_MODE=cli_or_http          # 本地 CLI 或侧车 HTTP
HERMES_ENDPOINT=…                # 若 HTTP
HERMES_DEFAULT_PROFILE=default
SESSION_KEY_TEMPLATE=feishu:{chat_id}:{open_id}
HERMES_GENERATION_ONLY=true
# 可选
REDIS_URL=                       # preview_token / 限流 / 事件去重
LOG_LEVEL=INFO
CORS_ORIGINS=                    # 一般不对公网浏览器开放
```

可选插件 / Hermes tool 回调侧：

```bash
PM_API_BASE_URL=http://127.0.0.1:8080/v1
PM_SERVICE_TOKEN=…
```

---

## 11. 仓库与目录建议

```text
feishu-pm-plugin/                 # 可选：Hermes thin tools（回调 Backend）
  plugin.yaml
  __init__.py
  schemas.py
  tools.py                      # HTTP client
  middleware/                   # P0 InMemory 骨架

pm-backend/                     # FastAPI 主入口（可 monorepo 子目录）
  app/
    main.py
    api/                        # feishu event · REST · internal jobs · SSE
    services/                   # + DialogueOrchestrator
    domain/
    middleware/
    adapters/feishu/
    adapters/hermes/            # session_key + 记忆框架调用
    adapters/db/
    core/                       # job envelope · 幂等 · logging
  alembic/
  tests/
  pyproject.toml
  Dockerfile

docker-compose.yml              # postgres + api
docs/
  tech-architecture-and-api.md  # 本文
```

OpenSpec：后续 change 如 `add-pm-fastapi-backend`、`add-drive-upload-flow` 引用本文为设计真源。

---

## 12. 分阶段实现

| Phase | 交付 | 验收 |
|-------|------|------|
| P0 | 插件/中间层骨架（现有 OpenSpec） | pytest |
| P1 | PG：users/groups/**projects**/bindings/members + 飞书事件入口 + context/resolve | 一群一项目 |
| P2 | 项目鉴权 + 绑定 API + 读 tree/diff + Hermes **仅生成** 适配 | Agent 无法绕过鉴权 |
| P3 | 上传 preview/commit + 成员 + 幂等 + 项目文件夹 ACL | 主功能 2 |
| P4 | Job + 项目 diff 周报 + 审批 + Wiki | 主功能 1 |
| P5 | 对账、补偿、可观测、正文 diff | 生产硬化 |

---

## 13. 与文档索引

| 文档 | 关系 |
|------|------|
| `project-background.md` | 产品场景 |
| `architecture.md` | 概念分层与权限哲学 |
| `hermes-plugin-conventions.md` | 宿主插件机制 |
| **本文** | **实现架构 + HTTP/工具合同 + 表结构 + 幂等** |

---

## 14. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-10-27 | 初版：冻结 D1=B、D2=PG、D4 及默认项；完整 API 草案 |
| 2026-10-28 | **组模型**：Drive 按组根；子树组长自治；周报 **diff 驱动**；实体 projects→groups；D7–D9 |
| 2026-10-28 | **D10 空周**：周三提醒 + 周四仍「无变更」提审；**D11 MVP 仅元数据 diff** |
| 2026-10-28 | **D12**：写/长任务 HTTP 输出统一 **SSE**（meta/progress/result/error） |
| 2026-10-28 | **D13–D16**：IM **直连 FastAPI**；一对多 + Hermes **session 记忆隔离**；**Job envelope/payload** 合同（§5.4）；Hermes 降为旁路对话运行时 |
| 2026-10-29 | **D4/D8/D9/D17**：群绑定 **项目**（组 Drive 下文件夹）；Hermes **仅生成**；补齐绑定/读/diff/summary/审批 API schema |
