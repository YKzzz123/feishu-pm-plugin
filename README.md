# feishu-pm-plugin

飞书「组」维度进展 Robot。  
**目标态**：IM → **FastAPI**；群绑 **项目文件夹**；**Hermes 仅生成**；本目录 P0 骨架 + 可选 thin 插件。

## P0 范围（当前代码）

- Tools：`pm_health`、`pm_list_my_groups`
- 业务中间层：`InMemoryGroupMiddleware`（`resolve_groups` + `authorize`）
- **Handler 永不向宿主抛异常**；统一 JSON 信封
- **Tool 调用审计**（进程内）：每 tool 的 total / success / failure
- **不含**：FastAPI/PG、飞书事件入口、真实飞书写、diff 周报、SSE、job worker（见 `docs/tech-architecture-and-api.md` P1–P5 / D12–D16）

## 文档

| 文档 | 说明 |
|------|------|
| [docs/project-background.md](docs/project-background.md) | 产品背景 |
| [docs/design-overview.md](docs/design-overview.md) | Mentor 框架与服务层 |
| [docs/tech-architecture-and-api.md](docs/tech-architecture-and-api.md) | 实现架构、API、**Job payload** |
| [docs/architecture.md](docs/architecture.md) | 概念分层与一对多记忆隔离 |
| [docs/hermes-plugin-conventions.md](docs/hermes-plugin-conventions.md) | 可选插件约定 |
| `openspec/changes/add-hermes-plugin-skeleton/` | 本阶段 OpenSpec |

## 测试

```bash
pip install -e ".[dev]"   # 或: pip install pytest pyyaml
python -m pytest tests/ -q
```

测试按模块拆分：`test_plugin_manifest`、`test_middleware_groups`、`test_tools_*`、`test_handler_safety`、`test_tool_audit`、`test_register`。

## 安装到 Hermes（可选）

```bash
ln -s "$(pwd)" ~/.hermes/plugins/feishu-pm-plugin
hermes plugins enable feishu-pm-plugin
hermes plugins doctor ~/.hermes/plugins/feishu-pm-plugin
```

## 审计快照（进程内）

```python
from tools import get_audit
print(get_audit().snapshot())
# {"tools": {"pm_health": {"total": 1, "success": 1, "failure": 0}, ...}}
```
