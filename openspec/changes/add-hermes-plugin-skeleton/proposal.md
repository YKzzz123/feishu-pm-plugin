## Why

本仓库已有产品/架构文档与 OpenSpec 脚手架，尚无任何可被 Hermes 加载的插件代码，也没有「飞书用户 → **组（Group）**」的业务门禁边界。若不先落下可安装的插件骨架与中间层契约，后续组 Drive 上传、元数据 diff 周报、Wiki 写入会直接散落在工具实现里，导致权限与一对多隔离难以补齐。

用一次**小变更**建立可扩展底座：只读探测 + InMemory 门禁；真实 FastAPI/PG/diff/SSE 留给后续 change（见 `docs/tech-architecture-and-api.md` P1–P5）。

## What Changes

- 新增可被 Hermes 发现的插件清单与入口：`plugin.yaml`、`register(ctx)`。
- 新增最小 tool 集合：健康检查、**解析当前用户所属组**（`pm_list_my_groups`）。
- 新增**业务中间层**模块边界与内存/fixture 实现：飞书身份 → **组**绑定查询、动作级 `authorize`（本变更不接真实飞书 OpenAPI、不启 FastAPI）。
- 约定插件 tools **必须经中间层**解析组范围与权限，禁止在 tool 内硬编码组列表或绕过校验。
- 补充 pytest 与文档索引对齐（`design-overview.md`、`tech-architecture-and-api.md`、architecture、conventions）。
- **不包含**：真实 Drive/Wiki/IM 写、cron、周报 diff/审批、PostgreSQL、HTTP 后端、SSE 服务端流。

## Capabilities

### New Capabilities

- `hermes-plugin-skeleton`：Hermes 插件可安装、可注册 tools；暴露健康检查与「当前用户**组**上下文」只读查询。
- `group-middleware`：一对多场景下身份→**组**映射与动作权限校验契约（fixture/InMemory 后端）。

### Modified Capabilities

- （无：主规格库尚为空）

## Impact

- **代码**：仓库根 Hermes 插件布局（`plugin.yaml`、`__init__.py`、`schemas.py`、`tools.py`、`middleware/`、`tests/`）；不修改 Hermes 核心。
- **运行时**：可 symlink 至 `~/.hermes/plugins/` 后 enable；默认不改用户全局 `config.yaml`。
- **依赖**：Python 3 + Hermes 插件约定；pytest；无飞书生产调用、无 FastAPI 运行时依赖（本 change）。
- **文档**：同步 docs 索引与骨架范围说明；产品真源仍以 `project-background.md` / `design-overview.md` 为准。
- **语义**：实现与规格统一使用 **Group**；口语「项目」若出现，不等价于本变更中的绑定单元。
- **后续**：P1 起中间层可改为 HTTP 客户端调 PM Backend；工具名与 `authorize` 契约保持，存储实现替换。
