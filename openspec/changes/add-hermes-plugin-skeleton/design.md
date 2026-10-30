## Context

仓库：有完整产品/架构文档与 OpenSpec，**无**插件实现代码。宿主：本机 Hermes。  
插件约定：`docs/hermes-plugin-conventions.md`；概念架构：`docs/architecture.md`；**实现合同**：`docs/tech-architecture-and-api.md`（全局决策 D1–D12）；mentor 框架与服务层：`docs/design-overview.md`。  
官方：[Hermes Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)。  
加载：`~/.hermes/plugins/<name>/` + **`hermes plugins enable`**。

本 change 仅落实 **P0 骨架**；行为以 delta specs `hermes-plugin-skeleton`、`group-middleware` 为准。

> **编号**：下文 **S*** 仅表示本骨架 change 内决策，**不要**与 tech 文档全局 **D1–D12**（FastAPI、Group Drive、diff、SSE 等）混淆。

## Goals / Non-Goals

**Goals:**

- 可安装 Hermes 插件包结构，与官方 `register_tool` / JSON str handler 对齐。
- 插件与**业务中间层**边界清晰：tools 只编排，映射与鉴权在 `middleware/`。
- InMemory 跑通「身份 → **多组**」解析与动作允许/拒绝；pytest 可验。
- 文档与全局真源一致：**组（Group）** 为绑定单元；两套权限说清。
- 为后续写路径预留 action **名**（矩阵暂 Deny），不实现写出。

**Non-Goals（显式不对齐实现、留给后续 change）：**

| 全局能力 | 归属 |
|----------|------|
| 独立 FastAPI + PostgreSQL（全局 D1/D2） | P1+ |
| 组 Drive 根、成员双写、ACL re-check（D5/D8） | P2+ |
| Drive 上传 preview/commit | P3 |
| 元数据 diff 周报、空周 D10、cron、Wiki（D7/D10/D11） | P4 |
| **SSE 服务端流（D12）** | 写路径/长任务 change；本骨架 handler 仍返回**一次** JSON 字符串 |
| 真实飞书 OpenAPI、IM 发送 | 后续 |
| Hermes `ctx.register_middleware` 管道 | 不用 |
| 修改用户全局 `~/.hermes/config.yaml` | 仅文档化安装步骤 |

## Decisions（Skeleton S*）

### S1. 仓库根即插件包

- 根目录：`plugin.yaml`、`__init__.py`、`schemas.py`、`tools.py`、`middleware/`、`tests/`。  
- 可 `ln -s` 到 `~/.hermes/plugins/feishu-pm-plugin`。  
- 备选 `src/` 打包形态：本阶段不做。

### S2. 业务中间层为库内包，非独立进程

- `middleware/`：接口 + `InMemoryGroupMiddleware`；tools 注入实例。  
- **不是** `ctx.register_middleware`。  
- **P1+**：可用 HTTP client 替换 InMemory，**保持** `resolve_groups` / `authorize` 调用语义。  
- 本 change **不**引入 FastAPI（与全局 D1 不冲突，属分阶段）。

### S3. 飞书用户 → **组**解析（一对多）

- **骨架输入**：tool 参数 `feishu_user_id: str`（便于单测）。  
- **目标态输入**：Gateway/插件注入可信 `open_id`（及群 `chat_id`）；禁止仅靠 LLM 自报身份做写操作唯一源（全局身份模型：email 业务主键 + open_id 通道键）。  
- **API**：
  - `GroupBinding`：`group_id`、`role`（`owner` | `member` | `viewer`）
  - `resolve_groups(user_id) -> list[GroupBinding]`
  - `authorize(user_id, group_id, action) -> Allow | Deny`
- **一对多**：同一用户可属多组；写类 tool（未来）必须显式 `group_id` 或群绑定解析出的唯一组，**禁止**默认列表第一项静默写。  
- **群场景（目标态，非本 change 实现）**：一群一组 `chat_id → group_id`；骨架 tools 不解析 chat。  
- **隔离**：不向骨架 tools 暴露无身份全量组列表。

### S4. 两套权限

| 层 | 机制 | 用途 |
|----|------|------|
| 宿主 | enable / 可选 capabilities | 插件是否加载 |
| 业务 | `middleware.authorize` | 用户 × **组** × action |

骨架不声明 host `capabilities`。  
**authorize Allow ≠ 用户已确认写操作**。

### S5. 动作枚举（骨架）

- 允许：`read_group_context`（`owner` 与 `member`；`viewer` 若夹具需要可允许只读）。  
- 未知 action → **Deny**。  
- 名称预留、矩阵暂 Deny：`upload_drive`、`manage_members`、`approve_weekly`、`write_wiki`、`request_weekly_summary` 等。

### S6. Tool 集合与 handler 契约

| Tool | 行为 |
|------|------|
| `pm_health` | 插件名/版本/ok；不经组鉴权 |
| `pm_list_my_groups` | 要 `feishu_user_id`；`resolve_groups` + `authorize(..., read_group_context)` 过滤 |

- Schema / handler 分离。  
- `register(ctx)` → `ctx.register_tool(...)`（以当前 Hermes 为准）。  
- Handler：`(args: dict, **kwargs) -> str`，**JSON 字符串**，错误也 JSON。  
- **永不向宿主抛异常（S6a）**：所有 handler 经统一包装；未捕获异常 → `ok:false` + `error.code=INTERNAL`（或等价），并计入失败审计。  
- **调用审计（S6b）**：进程内 `ToolAudit` 按 tool 名累计 `total` / `success` / `failure`；成功 = 返回 JSON 且 `ok is true`。骨架可用内存；P1+ 可改为落 DB/operations。测试与只读快照可查。  
- **与全局 D12**：本 change **不**实现 SSE；P1+ 写/长任务后端 SSE，插件仍把最终信封收成 JSON str 交 LLM。
### S7. Hermes 边界

| 组件 | 职责 |
|------|------|
| Hermes | 飞书通道、session、LLM、cron、插件 enable |
| 插件（本 change） | manifest、tool、调 InMemory 中间层、JSON str |
| 业务中间层 | 绑定 + authorize；（后）可变为 Backend HTTP 门面 |

### S8. 安装、状态与校验

- symlink/copy → enable → list / doctor。  
- 禁止写插件源码树；状态用官方 plugin storage（骨架可暂不落盘）。  
- `pytest`；可选 `hermes plugins doctor . --ci`。

### S9. 文档

- 必链：`project-background.md`、`architecture.md`、`design-overview.md`、`tech-architecture-and-api.md`、`hermes-plugin-conventions.md`。  
- apply 时若实现细节与 docs 路径不一致，以代码为准微调 docs 索引句，不改产品 D 决策。

### S10. 数据流（骨架）

```text
加载：发现 → enable → register → tools 入表
只读：IM → Gateway → Session → LLM → pm_list_my_groups
     → resolve_groups / authorize → JSON str → 话术
写路径：非本 change（目标态：SSE + Backend + 确认 + ACL + 幂等）
```

## Risks / Trade-offs

- **[Risk] `feishu_user_id` 可被 LLM 填错** → 骨架 fixture only；docs 标明非生产身份源。  
- **[Risk] register_tool 签名随 Hermes 版本变** → doctor + 源码对齐。  
- **[Trade-off] InMemory 非持久** → P0 可接受；P1 换实现保契约。  
- **[Risk] middleware 与 host middleware 名混** → 文档称「业务中间层」。  
- **[Trade-off] 不同步实现 SSE** → 避免 P0 过重；D12 在后续 change 强制。

## Migration Plan

1. pytest 通过；可选 doctor。  
2. 无生产数据。回滚 = disable / 删插件目录。  
3. 下一 change 引入 Backend 时：tools 改为 HTTP；InMemory 可测替身保留。

## Open Questions

- （无阻塞项）身份、一群一组、SSE、diff 均已在全局 docs 冻结；本 change 仅消费其 **Non-Goal 边界**。
