# 飞书项目管理 Robot — 设计总览

**文档目的**：给 mentor 快速看清大框架、**服务层边界**、系统边界与端到端链路（不含完整 DDL）。  
**状态**：IM→FastAPI（D13）+ **一群一项目=组 Drive 下文件夹（D4/D8/D9）** + Hermes **仅生成（D6/D17）** + Job/SSE；详见 tech-architecture。  
**详细实现合同**：[tech-architecture-and-api.md](./tech-architecture-and-api.md) · 产品背景：[project-background.md](./project-background.md)  

---

## 1. 要解决什么问题

在飞书里做一个**组（Team）维度的进展 Robot**，服务多组、多 Owner：

| 主功能 | 用户感知 |
|--------|----------|
| **① 周四基于 Drive diff 汇总 + 审批** | 周中看组 Drive **有无显著变更**并提醒；周四用 **diff 生成 summary** → Owner Y/N → 通过写 Wiki |
| **② 对话上传到组 Drive** | 用户对话把材料写入**本组 Drive 根下**（路径由组长约定；须确认） |

### 组织前提（评审重点）

```text
Drive 按「组」划分，不是按「项目」各建一套根目录。
  · AI 组 → 一个 Drive 根文件夹
  · 开发组 → 另一个 Drive 根文件夹
  · 组长在根下自建子文件夹与格式；Robot 不强制子树模板
  · 周报 = 对该组根在统计窗口内的 diff（增/改/删/移），而非「是否交了一份固定周报文件」
```

附带：组 Drive 成员邀请/撤回、权限校验、**按组**隔离，避免串组、静默乱写。

**非目标（当前）**：完整自研 PM 套件、SaaS 多租户运营台、Jira 深度同步、重型审批引擎、取代组长对子目录的治理。

---

## 2. 设计原则（给评审看的结论）

1. **FastAPI 做 IM 主入口与业务真源**  
   飞书事件/消息 **直达 Backend**（验签、去重、一对多解析）；写飞书与状态机都在服务端。

2. **Hermes 只做生成，全部服务由后端提供**  
   可选用 session 记忆；**禁止** Agent tool 绕过鉴权写飞书/DB；summary 文案由 Backend 调用 generate 后落库。

3. **独立后端 + PostgreSQL 做系统真源**  
   鉴权、状态机、幂等、审计、**Drive diff**、飞书出站、**job envelope** 集中在 **FastAPI**；可选 thin plugin 仅 HTTP 回调。

4. **两套权限分离**  
   - 宿主：谁能用这个 Bot / 插件是否 enable  
   - 业务：谁 × 哪**组** × 哪动作（`authorize`）+ **写前飞书 ACL 复核（组根）**

5. **写路径双条件**  
   业务允许 ∧（用户确认或周报 Y）∧ 幂等键；禁止静默写 Drive/Wiki/成员。

6. **一群一项目 + 一组一 Drive 根 + 一项目一文件夹**  
   群 `chat_id` → 唯一 `project_id`（群里可以有不同组的人）；项目文件夹必须在所属组 Drive 根下；diff/上传/周报锚定**项目文件夹**。

7. **周报材料 = 项目文件夹 Drive diff，不是单文件上传标记**  
   客户端改该文件夹、对话上传，都只是 diff 的输入。

8. **空周仍闭环（D10）**  
   无显著 diff：周三提醒；周四仍生成「本周无 Drive 变更」并提审，Owner 可 Y/N。

9. **MVP diff = 元数据 only（D11）**  
   对比 token/名称/类型/父路径/modified_time 等；不拉文档正文。

10. **三类「记忆」分存 + 一对多隔离（D14/D15）**  
    对话 transcript / 偏好 MEMORY → **Hermes session_key**；业务状态 → **PG**（`user×group`）。MEMORY **禁止**当 ACL。

11. **后端流式输出用 SSE（D12）**  
    写操作与长任务使用 `text/event-stream`；短只读可用 JSON；飞书事件接口瞬时 ACK。

12. **Job 有统一 payload 合同（D16）**  
    cron/outbox/内部批处理均有 `kind` + envelope + 专用 payload；详见 tech-architecture §5.4。

---

## 3. 总架构图

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            飞书用户（多群 / 多 Owner · 一对多）                 │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTPS（飞书客户端）
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         飞书开放平台（云端）                                   │
│              IM · Drive · Wiki · 通讯录 · 事件订阅                            │
└───────────────┬────────────────────────────────────────────▲────────────────┘
                │ ① 事件/消息：Webhook（或后端 WS 适配）进 **FastAPI**          │ ⑤ OpenAPI
                ▼                                                              │
┌───────────────────────────────────────────────────────────┐                  │
│  PM Backend（FastAPI · **主入口**）                         │                  │
│  · 验签 / 去重 / allowlist / 排队（按 chat 或 session）      │                  │
│  · open_id→user · chat→project · authorize                   │                  │
│  · Services · 状态机 · 幂等 · job envelope · 审计            │                  │
│  · DialogueOrchestrator ──需要 LLM──► Hermes               │                  │
│  · Feishu Egress（Drive/Wiki/IM，写前 ACL）─────────────────┼──────────────────┘
└─────────────┬──────────────────────────┬──────────────────┘
              │ ② session 记忆+意图         │ ④ SQL
              ▼                            ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ Hermes（**仅生成**）          │  │ PostgreSQL                  │
│ summary/话术；可选 session   │  │ 人/组/**项目**/绑定/周报/幂等 │
│ **无**写 tool 绕过鉴权        │  │ **不含**完整多轮对话          │
│                              │  └─────────────────────────────┘
└─────────────────────────────┘

旁路：Scheduler → /internal/cron/* 或 outbox_jobs（payload 见 tech §5.4）
```

### 3.1 进程边界

| 进程 | 职责 |
|------|------|
| **PM Backend** | **IM 入口**、业务规则、权限、状态、幂等、diff、调飞书、job（**服务层在此**） |
| **Hermes** | **仅生成**（summary/话术）；由 Backend 传入已鉴权上下文；无飞书写权 |
| PostgreSQL | 持久化业务真源（非 transcript） |
| （可选）Worker / thin plugin | 消费 outbox；Hermes tool→HTTP 回调 |

### 3.2 信任边界（评审要点）

```text
不可信：LLM 生成的「我是 Owner」、email、是否已确认、MEMORY 中的权限断言
半可信：飞书事件中的 open_id、chat_id、message_id（**经 Backend 验签**）
可信：  DB 中 user/成员/周报状态；飞书 ACL API 返回结果
```

---

## 4. 服务层设计（PM Backend）

服务层是 **业务用例编排的中枢**：API 只做 HTTP/DTO/鉴权头；**Services** 组合 domain 规则、仓储与飞书适配器；**不**在 handler/插件里写状态机。

### 4.1 层内结构与依赖方向

```text
api/                路由 · **飞书事件入口** · REST · **SSE（D12）** · internal jobs
  ↓ 只调 service 方法（可 async 迭代 progress）
services/           用例级 + **DialogueOrchestrator**
  ↓
domain/             纯规则：Role→action、周报状态迁移、diff、**job kind**、错误码
middleware/         authorize(user, group, action) 业务门禁
  ↓
adapters/
  db/               repositories（users/groups/members/cycles/ops…）
  feishu/           事件验签 · Drive · Wiki · IM · Contact · ACL
  hermes/           run_turn(session_key, …) · 记忆框架
core/               config · 幂等 · **job envelope** · logging · SSE · outbox
```

**依赖规则（评审约束）**

| 允许 | 禁止 |
|------|------|
| `api → services → domain/middleware → adapters` | service 互相循环依赖（跨域编排放 Application/Facade 或显式编排 service） |
| service 开短事务 + 明确出站顺序 | API 路由里直接打飞书或改状态机 |
| 飞书进线只进 api；Hermes/cron 只打 HTTP 或内部 service | Hermes/插件绕过 service 写飞书 |

### 4.2 服务目录（按用例）

| Service | 职责 | 主要入站 | 出站 |
|---------|------|----------|------|
| **IdentityService** | open_id→user；Contact 补全 email；upsert users | 几乎所有请求前置 | Contact API、users 表 |
| **ProjectContextService** | chat→**project**；list mine；建项目文件夹；绑群 | `/context/resolve`、`/projects/*`、bindings | projects、bindings、members |
| **AuthorizationService** | `authorize(user, project, action)`；未知 Deny | 各写/读门禁 | project_members（+可选组继承） |
| **MemberService** | 项目成员邀请/撤回；同步**项目文件夹**协作者 | members API | DB + Drive ACL |
| **DriveUploadService** | preview；commit 写**项目文件夹**子树 | upload preview/commit | Drive 写、operations |
| **DriveDiffService** | 项目文件夹元数据 snapshot/diff（D11） | cron、只读 diff API | Drive 读、snapshots |
| **WeeklyCycleService** | 按 **project** 周状态机；可调 Hermes 生成文案；decision 写 Wiki | cron、decision API | cycles、Wiki、IM |
| **RemindService** | 空周提醒；按 project remind_log | cron remind | IM、remind_log |
| **GenerationService** | 封装 Hermes.generate；失败模板回退；**不鉴权替代** | weekly summarize 内 | hermes adapter |
| **OperationService** | 幂等键登记/重放；operation 状态；审计挂接 | 所有写路径前置/收尾 | operations、audit_events |
| **FeishuGateway**（adapter 门面，非业务） | token、限流退避、统一错误映射 | 仅 adapters 内 | 飞书 OpenAPI |

> 命名可随代码微调；**边界**以表为准：diff 与 weekly 分开，避免「一个上帝 WeeklyService」兼做全盘飞书 IO。

### 4.3 跨服务协作（写路径模板）

所有**写飞书或改周期**的用例遵循同一骨架（由 OperationService 托底）：

```text
1. IdentityService.resolve(open_id)
2. ProjectContextService.resolve(chat_id | project_code)
3. AuthorizationService.authorize(user, project, action)
4. OperationService.begin(idempotency_key, request_hash)
     · 已 succeeded 且同 hash → 直接 return 重放
5. （产品）确认位 / 周报 decision 已满足
6. Feishu ACL re-check（**项目文件夹**或目标父目录）
7. 领域动作（upload / member / wiki / …）
8. 更新 DB 真源（members / weekly_cycles / …）
9. OperationService.succeed + audit
   失败：Feishu 未写或可重试 → fail；飞书已写本地失败 → compensating + outbox
```

**读路径**可跳过 4–9 中的写步骤，但仍建议走 Identity + Context + Authorize（如 `read_group_context`）。

### 4.4 各主功能在服务层的切分

#### （1）对话上传 — DriveUploadService

```text
preview(group, actor, title, relative_path, content, hash)
  → 校验成员与路径合法性（相对组根、防 .. 跳出）
  → 存草稿 → preview_token；路径相对项目文件夹
  → 不调飞书写

commit(...)
  → 写路径模板 + 项目文件夹 ACL
  → Drive 写入；diff 自然纳入
```

#### （2）元数据 Diff — DriveDiffService（D11）

```text
capture_snapshot(group) → manifest_json（token, name, type, parent, mtime…）
diff(group, window) →
  compare(snapshot_a, snapshot_b) 或 list_now vs baseline
  → { added, modified, deleted, moved }
  → 应用 diff_exclude_globs
  → 返回结构供 Weekly / 只读 API
```

**不做**：打开文档正文、语义摘要（P5+）。

#### （3）周提醒 — RemindService（D10 周三）

```text
remind_wed_activity(year_week):
  for group in active:
    if DriveDiffService.has_significant_diff(group, window): skip
    if remind_log hit: skip
    IM Owner「本周组 Drive 尚无变更，请补充」
    write remind_log(wed_activity)
```

单组 try/except 隔离，不影响其他组。

#### （4）周四汇总提审 — WeeklyCycleService + DriveDiffService（D10/D11）

```text
summarize_and_request_approval(year_week):
  for group in active:          # 含空周，全量
    d = DriveDiffService.diff(...)
    if d.non_empty:
      text = template_from_metadata_diff(d)
      activity = has_diff → summarized
    else:
      text = "本周无 Drive 变更" + window + optional wed_reminded
      activity = none → summarized（空周模板）
    cycle.summary_text / diff_summary_json / pending_approval
    IM Owner Y/N（cycle_id）
```

Summary **只在 Backend 服务层生成**（规则模板；若未来加内部 LLM 也挂在此服务，不经用户会话 Agent）。

#### （5）审批落 Wiki — WeeklyCycleService

```text
decision(group, year_week, actor, approve|reject, comment, idem_key)
  → authorize approve_weekly
  → 状态机校验 pending_approval
  → reject: 写 comment，不写 Wiki
  → approve: ACL → Wiki 写 summary_text → approved + wiki_page_*
```

#### （6）成员 — MemberService

```text
invite/remove:
  → authorize manage_members
  → 可选 Drive 组根协作者 add/remove
  → upsert/delete group_members
  → 已是成员 / 已不在 → 成功 no-op（幂等友好）
```

### 4.5 与 API / 插件 / Cron 的映射

| 入站 | 主要 Service |
|------|----------------|
| `GET /me` | IdentityService |
| `GET /groups/mine` · `GET /context/resolve` | GroupContextService + AuthorizationService |
| `POST /groups` · bindings | GroupContextService |
| `…/members` | MemberService |
| `…/drive/uploads/*` | DriveUploadService |
| `GET …/drive/diff` | DriveDiffService |
| `POST /internal/cron/drive/capture-snapshots` | DriveDiffService |
| `POST /internal/cron/weekly/remind` | RemindService |
| `POST /internal/cron/weekly/summarize-and-request-approval` | WeeklyCycleService |
| `POST …/weekly/…/decision` | WeeklyCycleService |
| 写路径统一 | OperationService 横切 |

可选 Hermes tools 与上表 HTTP 1:1，**无额外业务分支**；**写/长任务响应走 SSE**，消费流后最终 `result` 交编排/LLM。主路径是 **事件 → Backend**，不是 Gateway 插件。

### 4.6 输出：SSE（服务层 / API 协作，D12）

```text
Service（可 yield Progress 或回调 on_progress）
    → API 层写成 SSE：
         event: meta | progress | delta | ping | result | error
    → 插件 SSE client 读到 result/error 为止
    → handler 返回给 Hermes 的仍是「最终信封」JSON 字符串
```

| 事件 | 用途 |
|------|------|
| `meta` | request_id / operation_id / idempotent_replay |
| `progress` | stage + message（authorize → acl → drive_write → …） |
| `delta` | 可选文本增量（如 summary 拼接） |
| `ping` | 保活 |
| `result` | 成功终态，data 与原 JSON 信封一致 |
| `error` | 失败终态，error.code 与业务码表一致 |

**短只读**（health/me/resolve/mine）：默认一次 JSON；不强制 SSE。  
**Cron 批处理**：进程内可直接调 Service；若 HTTP 暴露且需观察进度 → 同样 SSE。  

完整帧格式与示例见 [tech-architecture-and-api.md §6.1.1](./tech-architecture-and-api.md)。

### 4.7 事务、幂等与一致性（服务层约定）

| 主题 | 约定 |
|------|------|
| DB 事务 | 单服务方法内短事务；**不**跨长耗时飞书调用持有行锁 |
| 出站顺序 | 先 `operations=running`，再飞书，再提交业务行 + `succeeded` |
| 幂等 | 写 API 强制 Idempotency-Key；Service 入口先问 OperationService；SSE 重放可短流直接 `result` |
| 空周/有 diff | 同一 `WeeklyCycleService` 出口，避免两套审批实现 |
| 可观测 | 每用例 `request_id`；流上 progress + audit（actor, group, action, operation_id） |
| SSE 与事务 | progress 可在事务外发；**仅 result 后**保证 DB 真源与飞书侧最终一致声明 |
### 4.8 服务层不做的事

- 解析自然语言、抽 route/slots（Backend 编排 + Hermes 记忆/LLM）
- 保存多轮聊天 transcript
- 规定组内子文件夹模板
- 用 MEMORY.md 做权限
- MVP 正文级 Drive diff（D11）
- 把 SSE 帧拼进 LLM 多轮协议（插件只交最终 JSON str）

### 4.9 目录落位（与仓库）

```text
pm-backend/app/
  api/           # FastAPI routers
  services/      # 本节各 *Service
  domain/        # 状态机、action 枚举、错误
  middleware/    # authorize
  adapters/db/
  adapters/feishu/
  core/          # 幂等、config、log
```

插件侧仅 `tools.py` HTTP client，**无**平行服务层。

---

## 5. 核心数据对象（逻辑，非全字段）

```text
users                 人（email 业务主键，open_id 通道键）
groups                组 + drive_root_folder_token + Wiki + Owner
group_chat_bindings   chat_id ──唯一──► group_id          ← 一群一组
group_members         (user, group, role)                 ← 权限策略
drive_snapshots       组根清单快照（可选，支撑 diff）
weekly_cycles         每组每周：diff 活动态 / summary / 审批 / Wiki
operations            写操作幂等与出站痕迹
audit_events          审计
remind_log            提醒防双发
```

**不进业务库**：完整多轮对话（Hermes session）、文件/Wiki 正文（飞书云）、密钥（环境变量）。  
**不建模为顶级并行实体**：组内子文件夹 schema（留给组长）。

---

## 6. 权限模型（框架）

```text
                    ┌─ A. Hermes：plugins enable / allowlist
用户发消息 ─────────┤
                    └─ B. 业务：
                         open_id → user
                         chat_id → group（群）或显式 group_code（DM）
                         authorize(user, group, action)
                         写飞书前：组根（或目标节点）ACL re-check
```

| role（示意） | 能力 |
|--------------|------|
| owner（组长） | 读、上传、管成员、周报审批、（审批后）写 Wiki |
| member | 读、上传到组 Drive |
| viewer | 只读上下文 |

未知 action → Deny。  
**authorize Allow ≠ 已确认写操作**；确认/周报 Y 是第二道门。

权限**管理**入口：组员 invite/remove（可选同步**组根**协作者）+ 群↔组绑定；对账对比云端 ACL 与 `group_members`。

---

## 7. 全链路流转

### 7.1 公共入口链路（每条用户消息）

```text
[U1] 用户在飞书客户端发消息（群 @Bot 或私聊）
[U2] 飞书云接收 → Webhook/**直达 FastAPI** `/feishu/event`（验签去重）
[U3] Gateway：验签、message_id 去重、allowlist、@ 策略、入队
[U4] 解析 user/group；需要 LLM 则 Hermes `session_key=feishu:{chat}:{open_id}` 隔离记忆
[U5] 组装上下文 → LLM：理解意图，决定是否调 tool、调哪个
[U6] Backend：authorize + Service（写/长任务可 **SSE** 自观察）；Hermes 仅意图时不经写
[U7] Backend 组织回复 → 飞书 IM 出站；LLM 话术可选由 Hermes 生成
[U8] Gateway 调飞书 IM API 把回复发给用户
```

失败策略（框架）：WS 重连；事件去重；LLM provider fallback；意图不清则追问**不**调写 API；飞书 429/5xx 有限退避，403 不重试。

---

### 7.2 链路 A — 只读：我有哪些组 / 本群上下文

```text
用户：「我在哪些组？」 / 「当前是哪个组？」
  → LLM → pm_list_my_groups 或 pm_resolve_context
  → Backend：open_id→user
       · mine：group_members 列表
       · resolve：chat_id→bindings→唯一 group + role
  → 无写飞书；JSON → 话术回复
```

群未绑定 → 提示管理员绑定到**组**，不猜测。

---

### 7.3 链路 B — 主功能②：对话上传到**组 Drive**

```text
用户：「把材料传到本组某子路径」+ 正文
  → preview（relative_path 可选）→ 确认 → commit + 幂等键
  → authorize + 组根/父目录 ACL → 写入组根子树
  → 不单独作为「本周有进展」的唯一标记；进入之后的 Drive diff
```

任一步 Deny / 未确认 → **不出站写**。

---

### 7.4 链路 C — 周三空周提醒（D10）

```text
Hermes Cron 周三 10:00
  → POST /internal/cron/weekly/remind  kind=wed_activity
  → 对 active 组：元数据 diff 仍为空？
       是 → IM 催 Owner 补材料 + remind_log
       否 → 跳过活动提醒
  → 单组失败隔离
```

---

### 7.5 链路 D — 周四 **全量提审**（有 diff 列变更 / 空周「无变更」）

```text
Hermes Cron 周四
  → （可选）capture-snapshots
  → summarize-and-request-approval  【每组都跑，含空周】
  → 元数据 diff only（D11）
       有 diff → summary = 变更清单模板
       无 diff → summary =「本周无 Drive 变更」+ 窗口说明（D10）
  → 一律 pending_approval → IM 请 Owner Y/N
  → 用户会话模型不直接写 Wiki
```

---

### 7.6 链路 E — Owner 审批 → Wiki

```text
Owner Y/N → pm_weekly_decision + 幂等键
  N → rejected，不写 Wiki
  Y → authorize + ACL → Wiki 写入 **diff 型 summary** → approved
```

---

### 7.7 链路 F — 组成员邀请 / 撤回

```text
组长邀请 email → 确认 → manage_members
  → 可选同步**组 Drive 根**协作者 → group_members + audit
```

---

### 7.8 链路 G — 组与群绑定

```text
创建组 → groups（必填 drive_root_folder_token）+ owner
绑群 → group_chat_bindings（一群一组）
子目录 → 组长在飞书侧自治，不进系统强制 schema
```

---

### 7.9 链路 H — 身份首次出现

```text
open_id 未入库
  → Contact API：open_id → email
  → upsert users
  → 无 email / 解析失败：拒绝写操作；只读可提示联系管理员
```

---

### 7.10 链路 I — 幂等与补偿（写路径共性）

```text
写请求携带 Idempotency-Key
  → 同 key + 同 body hash + 已成功 → 原样重放结果
  → 同 key + 不同 body → 冲突错误
  → 处理中 → 进行中 / 轮询 operation
  → 飞书成功、本地失败 → compensating + outbox（阶段后期）
```

---

## 8. 记忆与隔离（框架 · D14/D15）

| 类型 | 存储 | 隔离键 | 用途 |
|------|------|--------|------|
| 会话 transcript | Hermes（可选） | `session_key` | 多轮上下文；**非权限** |
| 生成草稿 | Hermes 输出 | request_id | 须经 Backend 采纳 |
| 业务状态 | PostgreSQL | **`user × project`**（项目属 group） | 绑定、成员、周报、diff、操作 |
| Job | outbox_jobs | job_id + kind | 按 **project_ids** 批处理 |

**一对多**：群绑项目（跨组成员可同群）；diff/周报按**项目文件夹**；授权 `authorize(user,project,action)`。  
Hermes **不能**代替 Backend 做绑定/diff/审批。

---

## 9. 分阶段落地（评审时间线）

| 阶段 | 交付 | 说明 |
|------|------|------|
| P0 | 骨架 | pytest |
| P1 | projects + chat 绑定 + 事件入口 + resolve | 一群一项目 |
| P2 | project 鉴权 + tree/diff API + Hermes 仅生成 | 无绕过 |
| P3 | 上传 + 成员 + 幂等 | 主功能 ② |
| P4 | 周报 job + 审批 + Wiki | 主功能 ① |
| P5 | 对账补偿 | 生产硬化 |

---

## 10. 风险与对策（给 mentor 的诚实清单）

| 风险 | 对策 |
|------|------|
| Bot 应用身份过宽，模型幻觉导致误写 | Agent 只路由；写集中后端；确认 + ACL + 幂等 |
| 业务库与飞书 ACL 漂移 | 写前 re-check；后续对账 job |
| 群未绑定 / 单群多组诉求 | 明确报错；产品上拆群或演进显式选组 |
| Cron 重复触发 | `remind_log` 唯一约束；组级失败隔离 |
| Session / MEMORY 串用户或串组 | 强制 `session_key`；业务真源只认 PG；MEMORY 不写 ACL |
| 密钥与租户 | env / 密钥管理；测试与生产隔离 |

---

## 11. 文档与仓库索引

| 文档 | 内容 |
|------|------|
| **本文** | Mentor 大框架 + **服务层** + 全链路 |
| [project-background.md](./project-background.md) | 产品目标与周节奏 |
| [architecture.md](./architecture.md) | 概念分层与两套权限 |
| [tech-architecture-and-api.md](./tech-architecture-and-api.md) | 表结构、HTTP API、tool 映射 |
| [hermes-plugin-conventions.md](./hermes-plugin-conventions.md) | 插件安装与 handler 约定 |
| `openspec/` | 规格驱动变更（如 skeleton） |

---

## 12. 一页纸结论

```text
飞书 IM/事件
    → FastAPI（验签 · 一对多 · 鉴权 · Drive diff · 状态机 · 幂等 · job · 审计）
        ↔ Hermes（按 session_key 的记忆框架 + 意图/话术）
        → PostgreSQL（人/组/成员/快照/周报/操作/outbox）
        → 飞书 OpenAPI（组根 Drive / Wiki / IM，写前 ACL）

组织：一组 = Drive 根；一项目 = 根下文件夹；一群 = 绑一个项目（成员可跨组）
Hermes：只生成文案；绑定/读/diff/summary 落库/审批/鉴权全在 Backend

两大闭环：
  上传：preview → 确认 → commit → 写入**项目文件夹**
  周报：Wed 提醒 → Thu **项目**元数据 diff（或空周文案）→ 提审 → Y/N → Wiki
```

**技术选型冻结**：IM→FastAPI；**一群一项目（文件夹）**；Hermes **仅生成**；PG 真源；元数据 diff；空周仍提审；SSE；Job envelope。
