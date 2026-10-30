## 1. 仓库与插件清单

- [x] 1.1 在仓库根添加 `plugin.yaml`（name/version/description；`provides_tools` 含 `pm_health` 与 `pm_list_my_groups`；骨架不强制 `capabilities`），用文件存在性与字段断言验证
- [x] 1.2 添加 Python 包入口 `__init__.py`，导出 `register(ctx)`，验证可导入
- [x] 1.3 添加 `schemas.py` 定义上述两 tool 的 function schema（组上下文 tool 名与参数含 `feishu_user_id`），验证 name/description/parameters 非空
- [x] 1.4 确认并按需微调 docs 索引：`README.md` 已链 design-overview / tech-architecture / conventions；P0 范围说明齐全

## 2. 业务中间层（组映射与权限）

- [x] 2.1 实现 `middleware` 包：`resolve_groups`、`authorize`、`GroupBinding`、动作常量（至少 `read_group_context`；预留写类 action 名），模块 docstring 注明非 Hermes host middleware；验证可导入
- [x] 2.2 实现 `InMemoryGroupMiddleware`：预置用户**多组**绑定与角色（夹具「AI 组」「开发组」）；单测「双组用户返回两个 group_id」
- [x] 2.3 空绑定与非法/空身份错误路径；单测覆盖空列表与拒绝空身份
- [x] 2.4 `authorize`：无绑定拒绝、角色无权限拒绝、未知 action 默认拒绝、owner/member 允许 `read_group_context`；各场景单测
- [x] 2.5 确认业务中间层 API 无飞书网络与写副作用；测试无需对外 HTTP

## 3. 错误处理、审计与 Tools

- [x] 3.1 实现统一 JSON 信封与 `safe_handler` 包装：任意异常 → `ok:false` + 稳定 `error.code`；**绝不**向宿主 raise
- [x] 3.2 实现 `ToolAudit`（按 tool：`total`/`success`/`failure`）；每次调用根据返回 JSON 的 `ok` 记账；提供只读 `snapshot()`
- [x] 3.3 实现 `pm_health`：JSON str（ok + 插件名/版本）；经 safe_handler + audit
- [x] 3.4 实现 `pm_list_my_groups`：经 `resolve_groups` + `authorize(read_group_context)`；缺身份/空绑定/成功三类 JSON；经 safe_handler + audit
- [x] 3.5 `register(ctx)` 注册两 tool；假 ctx 探针名称集合正确；注册时共用 audit（`get_audit()`）

## 4. 分模块测试（每模块独立用例）

- [x] 4.1 `tests/test_plugin_manifest.py`：plugin.yaml 字段、provides_tools 名称
- [x] 4.2 `tests/test_middleware_groups.py`：多组绑定、空绑定、坏身份、authorize 允许/拒绝/未知 action、不串用户
- [x] 4.3 `tests/test_tools_health.py`：成功 JSON、结构字段、调用后 audit success
- [x] 4.4 `tests/test_tools_list_groups.py`：缺身份失败、未绑定空列表、已绑定过滤、无权限组不出现、不 raise
- [x] 4.5 `tests/test_handler_safety.py`：注入内部异常仍返回 JSON error、不向调用方抛出、failure 计数 +1
- [x] 4.6 `tests/test_tool_audit.py`：连续成功/失败累计、snapshot 结构、未知 tool 查询行为
- [x] 4.7 `tests/test_register.py`：register 探针收集 pm_health / pm_list_my_groups
- [x] 4.8 `python -m pytest tests/ -q` 全部通过（31 passed）

## 5. 文档收尾与范围反向检查

- [x] 5.1 README：安装 enable、pytest、P0 范围；链到 design-overview / tech-architecture / conventions
- [x] 5.2 docs/README 说明审计为进程内、P1+ 可迁 Backend
- [x] 5.3 无 FastAPI/PG 迁移、无飞书写、无 cron/diff/Wiki、无 SSE 服务端
- [x] 5.4 代码/测试/对外 JSON 使用 **group**，不以 project 为绑定主键
