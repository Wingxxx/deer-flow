# App UX Optimization + Stress Testing Spec

## Why
当前 App 在服务器不可达时白屏无反馈，URL 配置体验简陋，且无安全校验防止误输入第三方网站。需要参考业界最佳实践进行全面交互优化，并通过暴力测试保证极端场景下的稳定性。

## What Changes
- **白屏替换**：WebView 加载失败时显示原生错误提示覆盖层（cover-view），不再白屏
- **URL 配置浮层升级**：用 cover-view 自定义浮层替代 plus.nativeUI.prompt，增加格式校验、协议自动补全、内网检测提示
- **服务器身份验证硬限制**：通过 GET /health 端点验证目标是否为 DeerFlow 服务器（检查 `service === "deer-flow-gateway"`），非 DeerFlow 服务器禁止保存
- **智能重试**：错误提示页提供「检查网络并重试」按钮，带指数退避策略
- **暴力测试**：模拟网络断开/恢复、URL 注入、快速切换配置等极端场景
- **文档同步**：更新 CLAUDE.md 和设计文档，反映新交互逻辑

## Impact
- Affected specs: 现有设计文档 `docs/superpowers/specs/2026-05-29-app-ux-optimization-design.md`（需更新实现状态）
- Affected code: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`（唯一改动的源文件）
- Affected docs: `CLAUDE.md`、`.trae/specs/ux-optimization-stress-test/`（新增）

## ADDED Requirements

### Requirement: 错误提示覆盖层
The system SHALL display an error overlay when WebView fails to load.

#### Scenario: 网络不可达时显示错误页
- **WHEN** WebView 触发 onError 事件 或 加载超过 10 秒无响应
- **THEN** 显示 cover-view 覆盖层，包含 ⚠️ 图标、「无法连接服务器」标题、当前 URL 卡片、「修改服务器地址」按钮（蓝色主按钮）、「检查网络并重试」按钮（次要按钮）

#### Scenario: 加载成功后隐藏错误页
- **WHEN** WebView 重新加载成功
- **THEN** 隐藏错误覆盖层，恢复 WebView 显示

### Requirement: URL 配置浮层
The system SHALL provide a cover-view config panel for URL editing.

#### Scenario: 输入格式校验
- **WHEN** 用户输入 URL 时
- **THEN** 系统实时校验格式：
  - 空值 → 保存按钮禁用，提示「请输入服务器地址」
  - 无 http:// 或 https:// 前缀 → 自动补全 http://
  - 非法字符 → 保存按钮禁用，提示「地址格式不正确」

#### Scenario: 内网检测提示
- **WHEN** 用户输入的 URL hostname 为公网域名（如 baidu.com, google.com 等）
- **THEN** 输入框下方显示黄色提示「您输入的似乎是一个公共网站地址。DeerFlow 服务器通常位于内网」
- **AND WHEN** URL 为内网 IP 或自定义域名
- **THEN** 不显示此提示

### Requirement: 服务器身份验证（硬限制）
The system SHALL verify that the target URL is a DeerFlow server via /health endpoint.

#### Scenario: 连接测试——DeerFlow 服务器
- **WHEN** 用户点击「连接测试」按钮
- **THEN** 向 `{serverUrl}/health` 发送 GET 请求
- **AND THEN** 若响应 JSON 包含 `service === "deer-flow-gateway"` 且 `status === "healthy"`
- **THEN** 显示绿色 ✓「DeerFlow 服务器已验证」，保存按钮启用

#### Scenario: 连接测试——非 DeerFlow 服务器
- **WHEN** 用户点击「连接测试」按钮
- **AND WHEN** 请求成功但 JSON 不匹配
- **THEN** 显示红色 ⛔「非 DeerFlow 服务器，禁止使用」，保存按钮保持禁用

#### Scenario: 连接测试——无法连接
- **WHEN** 用户点击「连接测试」按钮
- **AND WHEN** 网络错误或超时（5秒）
- **THEN** 显示红色 ❌ 对应的错误信息，保存按钮保持禁用

### Requirement: 智能重试
The system SHALL support smart retry with exponential backoff.

#### Scenario: 点击重试
- **WHEN** 用户在错误页点击「检查网络并重试」
- **THEN** 重新加载 WebView
- **AND THEN** 若再次失败，按 2s → 4s → 8s → 15s（上限）间隔自动重试

#### Scenario: 网络恢复通知
- **WHEN** 网络从断连恢复
- **THEN** 提示用户「网络已恢复，是否重试？」

### Requirement: 暴力测试
The system SHALL pass stress testing under extreme scenarios.

#### Scenario: 网络断开后恢复
- **WHEN** App 正常加载中突然断开网络 30 秒后恢复
- **THEN** 错误页显示 → 网络恢复后提示 → 用户可重试

#### Scenario: 快速连续切换 URL
- **WHEN** 用户在 5 秒内连续切换 10 次不同 URL
- **THEN** 系统不崩溃，每次切换正常触发连接测试/保存/加载流程

#### Scenario: 输入极端 URL
- **WHEN** 用户输入包含特殊字符的极端 URL（如 `http://192.168.1.56:2026/"; DROP TABLE;--`）
- **THEN** 系统不崩溃，格式校验正常拦截非法字符

#### Scenario: /health 端点异常响应
- **WHEN** /health 返回非 JSON、HTTP 500、或超时
- **THEN** 身份验证正常识别为失败，显示对应错误提示

#### Scenario: 弱网环境
- **WHEN** 网络延迟高达 3-5 秒
- **THEN** 连接测试在 5 秒超时内正常等待并返回结果，不崩溃

## MODIFIED Requirements
### Requirement: ⚙ 悬浮按钮
现有 ⚙ 按钮功能从弹出原生对话框改为弹出 cover-view URL 配置浮层，浮层内容同上述 URL 配置浮层要求。

### Requirement: 文档同步
实施完成后需同步以下文档：
- `CLAUDE.md`：更新「Server URL — 运行时配置」章节，反映新的 URL 配置浮层交互逻辑、三层防护机制
- `docs/superpowers/specs/2026-05-29-app-ux-optimization-design.md`：补充实现状态（如果未实施）

## REMOVED Requirements
### Requirement: plus.nativeUI.prompt URL 配置
**Reason**: 被 cover-view 自定义配置浮层取代，功能更丰富（格式校验、连接测试、身份验证）
**Migration**: 全部迁移至 `showConfigPanel()` 方法中的 cover-view 浮层

### Key Architecture Decisions
1. **所有逻辑在 `index.vue` 中实现**，不新增页面路由——保持单页面架构
2. **错误覆盖层和配置浮层均使用 `cover-view`**——与 WebView 同层渲染，无层级问题
3. **身份验证用 `uni.request` 而非 `fetch`**——uni-app 跨平台兼容性更好
4. **不新增第三方依赖**——全部用 uni-app 内置 API 和 plus 扩展
5. **格式校验在前端实时执行**，无需服务器配合
