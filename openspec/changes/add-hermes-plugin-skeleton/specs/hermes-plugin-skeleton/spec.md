## Purpose

定义 feishu-pm-plugin 作为 Hermes 插件的可安装、可注册与最小只读 tool 行为，为后续「组」维度项目管理能力提供稳定扩展入口。

## ADDED Requirements

### Requirement: Plugin manifest and registration entry exist

系统 MUST 在仓库中提供 Hermes 可识别的插件清单与 Python 注册入口。清单 MUST 声明插件名称、版本与所提供的 tools。注册入口 MUST 暴露 `register` 可调用对象，以便宿主在加载时完成 tool 注册。

#### Scenario: Manifest declares plugin identity and tools
- **WHEN** 加载或检查本仓库的插件清单
- **THEN** 清单 MUST 包含稳定的插件名称、版本，以及本变更提供的 tool 名称列表（至少包含 `pm_health` 与 `pm_list_my_groups`）

#### Scenario: Registration entry is importable
- **WHEN** 在正确的插件包路径下导入注册入口并调用 `register`
- **THEN** 调用 MUST 成功完成，且本变更定义的 tools MUST 对宿主可见（或由测试用的注册探针确认已提交注册）

### Requirement: Health check tool is available

系统 MUST 提供只读健康检查 tool。该 tool MUST 返回插件已加载的明确成功标识，且 MUST NOT 修改任何飞书资源或本地持久化业务状态。

#### Scenario: Health check succeeds after registration
- **WHEN** 插件完成注册后调用健康检查 tool
- **THEN** 结果 MUST 表示成功，并包含可识别的插件名称或等价标识

#### Scenario: Health check does not write external systems
- **WHEN** 调用健康检查 tool
- **THEN** 系统 MUST NOT 对 Drive、Wiki、IM 或其他飞书写接口产生调用，也 MUST NOT 要求用户确认

### Requirement: Current user group context tool is available

系统 MUST 提供只读 tool（`pm_list_my_groups`），用于根据调用上下文中的飞书用户身份解析其可访问的**组（Group）**列表（或明确的空/未绑定结果）。该 tool MUST 通过业务中间层完成身份→组解析，MUST NOT 在 tool 内硬编码组列表作为唯一数据源。

#### Scenario: Bound user receives group list via middleware
- **WHEN** 调用方提供已在中间层绑定的飞书用户身份并调用组上下文 tool
- **THEN** 返回 MUST 包含该用户被授权可见的组标识集合，且解析路径 MUST 经过中间层

#### Scenario: Unbound user receives explicit empty or unbound result
- **WHEN** 调用方提供未绑定任何组的飞书用户身份并调用组上下文 tool
- **THEN** 返回 MUST 明确表示无组或未绑定，MUST NOT 虚构组数据

#### Scenario: Missing caller identity is rejected
- **WHEN** 调用组上下文 tool 时缺少可用的飞书用户身份
- **THEN** 系统 MUST 失败并返回可诊断的错误信息，MUST NOT 回落到全局默认组

### Requirement: Skeleton tools remain read-only toward Feishu

本能力在骨架阶段提供的 tools MUST 仅为只读探测与查询。任何会修改飞书 Drive、Wiki、成员权限或发送业务审批消息的行为 MUST NOT 由本能力直接执行；此类写操作若在未来提供，MUST 在独立能力中定义并包含确认或审批行为，且（目标态）经后端与幂等/SSE 合同，而非本骨架直接实现。

#### Scenario: Skeleton tool set has no Feishu mutating action
- **WHEN** 仅启用本骨架能力所注册的 tools
- **THEN** 调用这些 tools MUST NOT 产生飞书资源变更

### Requirement: Tool handlers return JSON strings

本能力注册的 tool handler MUST 接受 `(args: dict, **kwargs)` 形态（以宿主约定为准），MUST 返回 JSON 文本字符串；业务或校验失败时 MUST 仍返回可解析的错误 JSON，MUST NOT 以未捕获异常作为对宿主的唯一失败信号。

#### Scenario: Health handler returns parseable JSON success
- **WHEN** 调用 `pm_health`
- **THEN** 返回值 MUST 可被 JSON 解析且表示成功

#### Scenario: Group list handler returns parseable JSON on error paths
- **WHEN** 调用 `pm_list_my_groups` 且缺少身份或结果为空
- **THEN** 返回值 MUST 可被 JSON 解析，并区分错误与空绑定（不得静默成功编造数据）

### Requirement: Tool handlers never raise to the host

本能力注册的每一个 tool handler MUST 将可预见与不可预见的失败收敛为 JSON 字符串结果。handler MUST NOT 让异常传播到 Hermes 宿主（即对宿主调用面表现为「总是返回 str」）。内部可记录日志；对外 MUST 使用稳定的 `ok` / `error.code` 字段（或等价结构）。

#### Scenario: Unexpected internal failure still returns JSON error
- **WHEN** handler 执行路径中发生未预期异常（测试可用注入/桩模拟）
- **THEN** 返回值 MUST 仍为可解析 JSON，且 MUST 表示失败（例如 `ok: false`），MUST NOT 向调用方抛出异常

#### Scenario: Validation failure does not raise
- **WHEN** 参数缺失或类型不合法
- **THEN** handler MUST 返回错误 JSON，MUST NOT raise

### Requirement: Tool invocation audit counters are recorded

系统 MUST 为每个已注册 tool 维护可查询的调用审计计数，至少包括：总调用次数、成功次数、失败次数。成功与失败 MUST 以 handler 返回 JSON 中的业务成功语义区分（例如 `ok: true` 为成功）。审计存储 MAY 为进程内实现（骨架阶段）；MUST 不依赖飞书网络。

#### Scenario: Successful tool call increments success counter
- **WHEN** 调用某 tool 且返回表示成功的 JSON
- **THEN** 该 tool 的总次数与成功次数 MUST 各增加 1

#### Scenario: Failed tool call increments failure counter
- **WHEN** 调用某 tool 且返回表示失败的 JSON（含校验失败）
- **THEN** 该 tool 的总次数与失败次数 MUST 各增加 1，成功次数 MUST NOT 因该次调用增加

#### Scenario: Audit is queryable without raising
- **WHEN** 查询审计快照（经测试 API 或内部只读接口）
- **THEN** 结果 MUST 包含各 tool 的 counts，MUST NOT 抛出未处理异常
