# 飞书项目管理 Robot — 项目背景

## 1. 目标

构建一个挂在飞书上的项目管理 Robot，帮助**组（Team/Group）** Owner / 成员：

- 在飞书里与 Robot 对话，完成**基于 Drive 变更（diff）**的周进展审批
- 管理**组级**飞书 Drive（邀请/撤回成员与权限；组内子目录由组长自治）
- 由 Robot **按组 Drive 根目录做 diff 感知** → 生成 summary → 审批通过后写入飞书 Wiki
- 支持用户对话式将材料上传到**本组织 Drive**（落到组长约定的子路径，而非 Robot 强制单一「项目文件夹」）

核心原则：**FastAPI 为 IM/业务主入口与全部鉴权服务；群绑定组 Drive 下的**项目文件夹**；Hermes 只做生成，不绕过鉴权。**

### 1.1 关键组织模型（与早期「一项目一 Drive」的区别）

```text
组（Group）—— 权限与 Drive 的基本单元
  例：AI 组、开发组
  · 每个组绑定一个 Drive「根文件夹」
  · 组长可在根下自由建子文件夹、约定命名/模板（Robot 不强制子树 schema）
  · 成员/角色挂在组上；周报 cron / diff / 审批 按组进行

飞书群（可选）—— 一群一组（chat_id ↔ group_id）
  · 用于对话上下文与提醒投递，不是 Drive 的划分维度

「项目」若仍出现在口语中
  · 多指组内业务称呼或子文件夹，不是另一套与 Drive 平行的顶级资源树
  · 实现真源以 Group 为准（见 tech-architecture）
```

| 维度 | 旧假设（已废弃） | **当前模型** |
|------|------------------|--------------|
| Drive 根 | 按「项目」各一个 folder | **按「组」各一个 folder** |
| 子目录 | 系统可能约定固定周报路径 | **组长自治**；Robot 递归/范围在组根下做 diff |
| 周报材料来源 | 偏「是否上传了本周文档」标记 | **组 Drive 在统计窗口内的 diff**（增/改/删/元数据） |
| 上传 | 传到「项目 Drive」 | 传到**本组 Drive**（可指定相对路径/子文件夹） |

## 2. 用户侧能力

| 场景 | 说明 |
|------|------|
| 周报审批 | Robot 推送**本周组 Drive diff 汇总**；用户回复 Y/N，可附修改建议 |
| Drive 成员与权限 | 在**组 Drive 根**上邀请/撤回成员，调整读写等权限 |
| Drive 内容协作 | 在本组根下由组长规划的子树中协作；Robot 不取代文件夹治理 |
| 主动上传 | 用户可随时与 Robot 对话，将进展/材料上传到**本组 Drive**（指定或默认子路径） |

## 3. Robot 侧能力

| 场景 | 说明 |
|------|------|
| **Drive diff 总结（核心）** | 对管辖**组根文件夹**做窗口内变更检测（新建/更新/删除/移动等），生成可读 summary |
| 周三上午10点提醒 | 若本周该组 Drive **尚无显著变更**（或策略上需要补材料），提醒组 Owner |
| 周四上午10点再提醒 | 仍无显著变更则再提醒（策略可配置） |
| 周四汇总 + 审批 | **有 diff 可汇**（或策略允许空周说明）：生成 summary → 发给 Owner 审批 |
| 审批落库 | 审批通过后，将 summary 写入飞书 Wiki（通常按组/按周落页） |
| 对话式上传 | 响应用户主动对话，协助把内容写入**组 Drive** 指定位置 |

**Robot 对外两大主功能：**

1. **每周四基于组 Drive diff 自动总结并提起审批**
2. **用户主动对话，上传内容到组 Drive**

## 4. 技术路线（当前阶段）

### 4.1 为何 FastAPI 主入口 + Hermes 记忆

- **IM/事件直达 FastAPI**：权限、状态机、幂等、飞书出站集中，避免「Bot 入口与业务真源分裂」
- **Hermes 仅生成**：summary/话术由 Backend 调用；**无**写飞书/改库 tool
- 定时提醒/汇总以 Backend job 为准；按 **project** 扫 Drive 文件夹 diff

### 4.2 推荐分层（已冻结实现形态）

```
飞书用户
  → 飞书云（IM / Drive / Wiki / 事件）
  → PM Backend FastAPI（验签 / chat→project / authorize / diff / 审批 / job）
       →（仅文案）Hermes.generate
  → PostgreSQL + 飞书 OpenAPI（项目文件夹 ACL re-check）
```

**已冻结要点**（全文见 [tech-architecture-and-api.md](./tech-architecture-and-api.md)）：

| 项 | 决定 |
|----|------|
| **IM 入口（D13）** | 飞书事件 **直达 FastAPI**；Hermes 非主入口 |
| 后端 | 独立 FastAPI + PostgreSQL 为业务真源 |
| 人 | email 业务主键 + open_id 通道键 |
| **组织单元** | **组（Group）**：Drive 根 + 成员 + 周报均按组 |
| 群 | **一群一项目**（`chat_id` ↔ `project_id`）；项目=组 Drive 下文件夹；群成员可跨组 |
| 项目 vs 组 | 组=Drive 根+人员池；项目=周报/diff/绑定锚点 |
| Hermes | **仅生成**；服务与鉴权全在 Backend |
| Drive 子树 | **组长自治**；Robot 在组根下 diff，不强制子目录规范 |
| 周报材料 | **项目文件夹**窗口 diff 为主 |
| 空周（D10） | **周三提醒**；**周四仍出「本周无 Drive 变更」并提审** |
| Diff 深度（D11） | MVP **仅元数据**；正文级 diff 不做 |
| API 输出（D12） | 写/长任务 **SSE**；短只读 JSON |
| Job（D16） | 统一 envelope + kind 专用 payload |
| 权限 | 业务表策略 + 写前飞书 ACL re-check（组根） |
| Hermes | 只做生成；不直写飞书、不替代 authorize |
### 4.3 中间层 / 后端职责（设计意图）

- **权限管理**：谁能看/改哪个**组** Drive、谁能审批周报、谁能改 Wiki（`authorize` + ACL re-check）
- **一对多用户管理**：同一 Robot 服务多组；群内由绑定解析**唯一**组
- **资源绑定**：**组** ↔ Drive **根**文件夹 ↔ Wiki 节点 ↔ Owner/成员 ↔ 可选飞书群
- **Diff 汇总**：按组根拉取/缓存变更清单 → summary（不依赖固定「本周文档」路径）
- **幂等与审计**：写操作 `Idempotency-Key` + `operations` / `audit_events`
- 插件 tools **仅**调后端 HTTP，禁止 shell 绕过门禁直操飞书敏感 API

## 5. 典型周节奏（按组 Drive diff）

| 时间 | 动作 |
|------|------|
| 持续 / 窗口采集 | 后端对各组 Drive 根记录快照或变更事件，供周 diff 使用 |
| 每周三 | 若本周该组 **尚无显著 Drive 变更（空周）**，提醒 Owner 补充材料（**D10**） |
| 每周四 | **无论有无 diff**：生成 summary 并提审——有 diff 则列变更；**空周则正文为「本周无 Drive 变更」仍提审**（D10） |
| Diff 深度 | **MVP 仅元数据**（增删改移/时间/路径等），不做正文 diff（**D11**） |
| 用户回复 Y | 将 summary 写入 Wiki（按组/周模板） |
| 用户回复 N + 建议 | 记录建议，可修订后再提审或下轮处理 |
| 任意时刻 | 对话上传到**组 Drive**、管组成员权限等 |

## 6. 非目标（当前阶段先不做）

- 替换飞书原生项目/任务套件的完整 PM 系统
- 多租户 SaaS 化运营后台（可先做成配置/轻量存储）
- 与外部 PM 工具（Jira 等）深度双向同步
- 复杂自定义审批引擎（先用对话式 Y/N + 建议）

## 7. 仓库定位

本仓库 `feishu-pm-plugin`：

- 产出 **PM Backend（FastAPI）** 为飞书 IM 与业务主入口，并保留可选 **Hermes 插件/适配**（`plugin.yaml` + tools）
- **业务中间层**（权限与一对多映射）与 **session 记忆隔离**边界清晰
- 使用 **OpenSpec** 做规格驱动变更（`openspec/`）
- 文档与约定以 `CLAUDE.md`、`docs/` 为准

### 7.1 文档索引

| 文档 | 内容 |
|------|------|
| [project-background.md](./project-background.md) | 本文：产品目标、周节奏、非目标 |
| [architecture.md](./architecture.md) | 概念分层、**两套权限**、端到端数据流 |
| [tech-architecture-and-api.md](./tech-architecture-and-api.md) | **实现**技术架构、PG 表、幂等、HTTP API、tool 映射 |
| [design-overview.md](./design-overview.md) | **Mentor 评审**：大框架、服务层、SSE、全链路流转 |
| [hermes-plugin-conventions.md](./hermes-plugin-conventions.md) | Hermes 插件安装/enable/doctor 与 `register` 约定 |
| `openspec/` | 行为规格与变更（如 `add-hermes-plugin-skeleton`） |

官方参考：[Hermes Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)

## 8. 成功标准（MVP 方向）

1. 用户可在飞书与 Robot 对话，完成一次「上传进展到 Drive」
2. 周四可自动（或半自动）生成 summary 并请求 Y/N 审批
3. 审批通过后 summary 出现在约定 Wiki 位置
4. 成员邀请/撤回在中间层校验下对指定 Drive 生效
5. 新能力优先进 Backend Service / job；对话侧用 Hermes 记忆与意图扩展，而不是改飞书出站散落各处

## 9. 相关概念速查

| 术语 | 含义 |
|------|------|
| Hermes | 文案生成（**非**入口、**非**鉴权） |
| FastAPI Backend | IM 入口、项目绑定、权限、diff、状态机、幂等、job、飞书出站 |
| 插件 | 本项目主要交付物；`plugin.yaml` + `register(ctx)` 扩展 tools/hooks |
| 业务中间层 | 用户↔项目映射 + `authorize(user, project, action)`；经此访问飞书资源 |
| Host capabilities | 可选 Hermes 插件特权面（与业务 **group** 权限不同，见 architecture） |
| Drive | 项目文件空间；上传与 diff 的来源 |
| Wiki | 审批通过后的正式周报/进展落库处 |
| Owner | 项目负责人，接收提醒与审批请求 |
| action | 业务动作名（如 `read_project_context`、`upload_drive`）；未知默认拒绝 |
