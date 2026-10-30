## Purpose

定义飞书身份到**组（Group）**空间的一对多映射与动作级权限校验契约，确保插件业务在隔离的组范围内经中间层访问能力（骨架阶段为 fixture/InMemory；目标态可替换为 PM Backend，契约保持）。

## ADDED Requirements

### Requirement: Resolve Feishu identity to group bindings

中间层 MUST 提供将飞书用户身份解析为**组**绑定列表的能力。每个绑定 MUST 至少包含稳定的**组**标识；在数据可用时 MUST 包含该用户在组中的角色信息。同一用户 MUST 被允许绑定零个、一个或多个组。

#### Scenario: User bound to multiple groups
- **WHEN** 查询一个已绑定两个不同组的飞书用户身份
- **THEN** 中间层 MUST 返回包含这两个组标识的绑定集合，且 MUST NOT 丢弃其中任一绑定

#### Scenario: User bound to zero groups
- **WHEN** 查询一个未配置任何组绑定的飞书用户身份
- **THEN** 中间层 MUST 返回空绑定集合，MUST NOT 抛出未处理异常，MUST NOT 返回其他用户的组

#### Scenario: Unknown identity format is rejected
- **WHEN** 传入空身份或无法识别的身份值
- **THEN** 中间层 MUST 拒绝该请求并返回可诊断的错误

### Requirement: Authorize actions within a group scope

中间层 MUST 提供针对「用户 + **组** + 动作」的权限校验。校验结果 MUST 明确允许或拒绝。当用户对目标组无绑定时，中间层 MUST 拒绝该动作。本阶段动作枚举至少 MUST 覆盖只读探测类动作 `read_group_context`；对尚未实现的写飞书动作或未知动作，中间层 MUST 返回拒绝，而不是默认放行。

#### Scenario: Member is allowed a granted read action
- **WHEN** 某用户对组 G 存在绑定，且其角色被授予动作 `read_group_context`
- **THEN** 对该用户、组 G、动作 `read_group_context` 的校验 MUST 返回允许

#### Scenario: Action denied when user not bound to group
- **WHEN** 某用户未绑定组 G，却校验其对 G 的任一动作
- **THEN** 中间层 MUST 返回拒绝

#### Scenario: Action denied when role lacks permission
- **WHEN** 某用户已绑定组 G，但其角色未授予所请求动作
- **THEN** 中间层 MUST 返回拒绝

#### Scenario: Unknown action is not allowed by default
- **WHEN** 校验一个中间层未定义的动作名
- **THEN** 中间层 MUST 返回拒绝（或等价的明确失败），MUST NOT 默认允许

### Requirement: Prevent cross-group data leakage in resolution APIs

中间层面向插件的查询 API MUST 仅返回调用方身份有权可见的**组**数据。MUST NOT 提供「无身份即可列出全部组」的默认入口给插件业务 tools。管理类全量列表若存在，MUST 与普通用户解析路径分离，且默认不向骨架 tools 开放。

#### Scenario: Group context query is scoped to caller
- **WHEN** 用户 A 与用户 B 分别绑定不同组，插件以用户 A 的身份请求组上下文
- **THEN** 结果 MUST 仅包含用户 A 的组，MUST NOT 包含仅属于用户 B 的组

### Requirement: Fixture or in-memory backend is acceptable for skeleton stage

在骨架阶段，中间层 MUST 允许使用 fixture 或内存实现满足上述行为契约，以便无飞书网络依赖地测试。切换到真实后端/飞书存储实现时，MUST 保持同一对外行为契约（解析绑定、校验动作、调用方隔离），MUST NOT 要求插件 tools 改写调用语义。

#### Scenario: In-memory backend satisfies bind and auth checks
- **WHEN** 使用内存/fixture 后端预置用户与组绑定及角色权限并执行解析与鉴权
- **THEN** 行为 MUST 与本规格场景一致

### Requirement: Mutating Feishu operations require explicit future authorization path

中间层 MUST NOT 在骨架阶段静默执行任何飞书资源写操作。未来支持的写操作（如组 Drive 成员变更、Wiki 写入）MUST 在独立变更中扩展动作模型，并 MUST 在业务层结合确认或审批流，且（目标态）经 PM Backend 幂等与 ACL；权限校验通过 alone MUST NOT 被视为已对用户完成确认。

#### Scenario: Skeleton middleware has no silent Feishu write
- **WHEN** 仅使用骨架阶段中间层 API
- **THEN** 这些 API MUST NOT 直接变更飞书 Drive、Wiki 或成员权限
