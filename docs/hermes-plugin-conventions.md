# Hermes 插件约定（feishu-pm-plugin）

对照官方文档：[Developer Guide · Plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)。  
本页只保留与本仓库相关的操作约定；业务权限见 [`architecture.md`](./architecture.md)。

## 1. 最小插件形态

```text
feishu-pm-plugin/          # 也可 symlink 到 ~/.hermes/plugins/feishu-pm-plugin
├── plugin.yaml            # 清单（必需）
├── __init__.py            # register(ctx)（必需）
├── schemas.py             # tool JSON schema（推荐）
├── tools.py               # handlers（推荐）
├── middleware/            # 本项目业务中间层（非 Hermes register_middleware）
├── skills/…/SKILL.md      # 可选
└── pyproject.toml         # 可选 Python 依赖（推荐于写在 yaml 里）
```

## 2. 发现 ≠ 启用

| 步骤 | 命令/动作 |
|------|-----------|
| 安装 | 将仓库链接或复制到 `~/.hermes/plugins/feishu-pm-plugin` |
| 启用 | `hermes plugins enable feishu-pm-plugin`（名称以 `plugin.yaml` 的 `name` 为准） |
| 查看 | `hermes plugins list` |
| 调试发现 | `HERMES_PLUGINS_DEBUG=1 hermes plugins list` |
| 健康检查 | 在插件目录：`hermes plugins doctor . --ci` |
| 清单校验 | `hermes plugins validate . --install-deps` |

常见加载失败：未 enable、缺 `__init__.py`、`register` 抛错、目录嵌套过深、`requires_env` 未满足。

## 3. `plugin.yaml`（骨架建议字段）

```yaml
name: feishu-pm-plugin
version: 0.1.0
description: 飞书项目管理 Robot — Hermes 插件
provides_tools:
  - pm_health
  - pm_list_my_projects
# provides_hooks: []          # 需要时再声明
# requires_env: []            # 接真实飞书后再加
# capabilities: []            # 仅当需要特权面时声明并征得同意
# python_dependencies: []     # 或使用 pyproject.toml
```

需要 host 特权时再声明 `capabilities`（如 `tools.override`、`llm.model_override`），并在代码中 `ctx.has_capability(...)` 探测；未同意则 fail-closed。  
**业务项目权限不要写进 capabilities**——那是 middleware 的 `authorize`。

## 4. `register(ctx)` 与 Tool API

```python
def register(ctx):
    ctx.register_tool(
        name="pm_health",
        toolset="feishu_pm",          # toolset 名可按实现调整
        schema=PM_HEALTH_SCHEMA,      # OpenAI function 风格
        handler=pm_health_handler,
    )
    # ...
```

Handler 约定（官方）：

```python
def pm_health_handler(args: dict, **kwargs) -> str:
    # 始终返回 JSON 字符串；失败也返回 JSON，不要 raise
    # 接受 **kwargs（session_id、task_id 等由宿主注入）
    return json.dumps({"ok": True, "plugin": "feishu-pm-plugin"})
```

其它常用 ctx API（按需）：

- `register_hook` / `register_command` / `register_skill` / `register_cli_command`
- `register_middleware`（宿主管道，与本仓库 `middleware/` 包不同）
- `get_config` / `set_config`、`state.get` / `state.set`
- `dispatch_tool`、`ctx.llm`、`has_plugin`、`has_capability`

## 5. Hooks 何时用（本项目）

骨架阶段**可不注册 hook**。后续可考虑：

| 需求 | Hook |
|------|------|
| 每轮注入「当前用户默认项目」提示 | `pre_llm_call` 返回 `{"context": "..."}` |
| 拦截危险 tool | `pre_tool_call` 返回 block |
| 审计 tool 调用 | `post_tool_call` |
| 飞书网关原生事件 | `gateway_platform_event` |

`pre_llm_call` 注入挂在 user message 侧（利于 prompt cache）；有长度上限。

## 6. 状态与密钥

- **不要**把运行时 DB/缓存写进插件源码目录（升级/覆盖会丢）  
  使用 Hermes 提供的 `plugin_data_dir` / `plugin_db`（见官方文档）
- **不要**直接读改 Hermes/Codex 凭证文件；走官方 credential 请求路径
- 飞书 app secret 等只进环境变量或宿主密钥存储，不进 git

## 7. 与 re_plugin 的差异（刻意）

| | re_plugin（参考） | feishu-pm-plugin（本仓库） |
|--|-------------------|---------------------------|
| 模式 | Hermes tools + 可选 AgentPortal HTTP | 骨架仅 Hermes 插件 |
| 后端 | RE MCP | 业务中间层 →（后）飞书 API |
| 写操作 | dry-run / confirm 两阶段 | 同样原则；骨架阶段无写 tool |

可复用其「schema/tools 分离、handler 包装、写操作确认」思路，不复用 RE 领域模型。

## 8. 本地安装示例

```bash
# 开发链接（示例）
ln -sfn /Users/yukizeng/Desktop/feishu-pm-plugin ~/.hermes/plugins/feishu-pm-plugin
hermes plugins enable feishu-pm-plugin
hermes plugins list
hermes plugins doctor ~/.hermes/plugins/feishu-pm-plugin --ci
```

单测仍在仓库内用 pytest 跑中间层与 handler，不强制每次拉起 gateway。
