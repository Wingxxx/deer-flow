# Tasks

## 任务总览
1. **UI 改造**：index.vue 增加错误覆盖层 + 配置浮层（cover-view）
2. **逻辑改造**：替换 plus.nativeUI.prompt 为 cover-view 配置浮层，实现三层防护
3. **服务器身份验证**：实现 GET /health 验证逻辑，硬限制保存
4. **智能重试**：指数退避 + 网络恢复监听
5. **暴力测试**：模拟极端场景验证稳定性
6. **文档同步**：更新 CLAUDE.md + 设计文档

---

### Task 1: 实现错误提示覆盖层（Error Overlay） ✅

**描述**: 在 `index.vue` template 中增加 cover-view 错误覆盖层，替换白屏。

**步骤**:
1. 在 `<template>` 中添加 cover-view 错误覆盖层结构：
   - ⚠️ 红色圆形图标（纯 CSS 实现）
   - 「无法连接服务器」标题
   - 描述文本「当前网络无法访问指定的服务器地址。请检查网络连接或修改服务器地址。」
   - 当前 URL 卡片（灰色背景圆角卡片）
   - 「✏️ 修改服务器地址」蓝色主按钮
   - 「🔄 检查网络并重试」次要按钮
2. 新增 data 属性：`showErrorOverlay`（Boolean，默认 false）
3. 新增 data 属性：`currentUrl`（String，当前正在加载的 URL）
4. 条件渲染：`v-if="showErrorOverlay"` 控制覆盖层显示
5. 样式定义：覆盖层全屏居中，z-index 高于 WebView

**验收标志**: 设置 `showErrorOverlay = true` 时，覆盖层占满全屏显示，按钮可点击

---

### Task 2: 实现 URL 配置浮层（Config Panel） ✅

**描述**: 替换现有的 `plus.nativeUI.prompt`，使用 cover-view 构建自定义配置浮层。

**步骤**:
1. 在 `<template>` 中添加 cover-view 配置浮层结构：
   - 半透明遮罩层（点击遮罩关闭浮层）
   - 白色浮层卡片
   - 「服务器设置」标题 + 关闭按钮
   - URL 输入框
   - 提示文字区域（格式校验结果、内网检测提示）
   - 「🔌 测试连接」按钮
   - 测试结果反馈区域（动态显示成功/失败/验证状态）
   - 「💾 保存并加载」蓝色主按钮（受 disabled 控制）
   - 「↩️ 恢复默认地址」次要按钮
2. 新增 data 属性：`showConfigPanel`（Boolean）、`inputUrl`（String）、`testResult`（Object）、`saveDisabled`（Boolean）、`urlHint`（String）
3. 新增方法：`openConfigPanel()`（打开浮层）、`closeConfigPanel()`（关闭浮层）、`onUrlInput(e)`（实时校验）、`restoreDefaultUrl()`（恢复默认）
4. 样式定义：浮层居中，遮罩半透明，iOS 风格圆角

**验收标志**: 点击 ⚙ 按钮弹出浮层，URL 输入框可编辑，输入时实时显示校验提示

---

### Task 3: 实现格式校验 + 协议自动补全 + 内网检测 ✅

**描述**: 在 `onUrlInput` 方法中实现三层防护的前两层。

**步骤**:
1. 格式校验逻辑：
   - 空值 → `urlHint = '请输入服务器地址'`, `saveDisabled = true`
   - 非法字符（空格、中文等）→ `urlHint = '地址格式不正确'`, `saveDisabled = true`
   - 合法但无协议前缀 → 自动补全 `http://`
2. 内网检测逻辑：
   - 解析输入的 URL 的 hostname
   - 公网域名列表：常见公共域名标记（如 baidu.com, google.com, github.com 等）
   - 内网 IP 段：`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`, `127.x.x.x`
   - 公网域名 → `urlHint = '您输入的似乎是一个公共网站地址。DeerFlow 服务器通常位于内网'`
   - 内网 IP 或自定义域名 → 清空 urlHint
3. 协议自动补全触发时机：输入框失去焦点 或 点击「测试连接」时

**验收标志**: 输入 `baidu.com` 显示协议自动补全 + 内网检测提示；输入 `192.168.1.56:2026` 自动补全协议 + 无内网提示；输入含空格的 URL 显示格式错误

---

### Task 4: 实现服务器身份验证（硬限制） ✅

**描述**: 通过 `/health` 端点验证目标是否为 DeerFlow 服务器。

**步骤**:
1. 新增方法 `testConnection()`：
   - uni.request 请求 `{url}/health`，5秒超时
   - 验证 JSON: `service === "deer-flow-gateway"` 且 `status === "healthy"`
   - 通过 → `saveDisabled = false`
   - 失败 → `saveDisabled = true`
2. 测试结果渲染：根据 `testResult.type` 显示不同样式（success/fail/loading）
3. 硬限制：`saveDisabled = true` 时「保存并加载」按钮灰色不可点击

**验收标志**: 输入 DeerFlow 地址 + 测试连接 → 绿色 ✓ 保存按钮启用；输入 baidu.com + 测试连接 → 红色 ⛔ 保存按钮禁用

---

### Task 5: 实现智能重试 + 网络监听 ✅

**描述**: 错误页的「检查网络并重试」按钮带指数退避 + 网络状态监听。

**步骤**:
1. 新增 data 属性：`retryCount`（Number，默认 0）
2. 新增方法 `retryLoad()`：
   - 重置 `showErrorOverlay = false`
   - 触发 WebView 重新加载
   - 若再次失败，按指数退避间隔（2s, 4s, 8s, 15s）自动重试
   - `retryCount` 递增，到达上限后停止自动重试
3. WebView `@load` 成功时：
   - `showErrorOverlay = false`
   - `retryCount = 0`
4. 网络监听：
   - 在 `onShow` 中注册 `uni.onNetworkStatusChange`
   - 网络从断连→连接时，如果当前正在显示错误页，弹出 `plus.nativeUI.toast('网络已恢复')`

**验收标志**: 点击「检查网络并重试」后 WebView 重新加载；连续失败按指数退避等待；网络恢复后提示

---

### Task 6: WebView 事件监听改造 ✅

**描述**: 监听 WebView 的 onError 事件和加载超时，控制错误覆盖层显示。

**步骤**:
1. WebView 增加 `@error="onWebViewError"` 事件绑定
2. 新增方法 `onWebViewError(e)`：
   - `showErrorOverlay = true`
   - `currentUrl = this.webviewSrc`
3. 新增方法 `onWebViewLoad(e)`：
   - `showErrorOverlay = false`
   - `retryCount = 0`
4. 加载超时检测：`onShow` 中设置 10 秒定时器，如果 WebView 未成功加载则显示错误页
5. 清理定时器：页面隐藏时清除

**验收标志**: WebView 加载失败时自动显示错误覆盖层；加载成功后自动隐藏

---

### Task 7: 执行暴力测试 🧪

**描述**: 在真实设备或 HBuilderX 调试中执行极端场景验证。

**步骤**:
1. **网络断开测试**：
   - 打开 App 正常加载 → 关闭 WiFi/数据 → 等待 30 秒 → 恢复网络
   - 验证：白屏？→ 错误覆盖层 → 网络恢复提示 → 点击重试后正常加载
2. **URL 注入测试**：
   - 输入 `http://192.168.1.56:2026/"; DROP TABLE;--`
   - 验证：格式校验拦截，不崩溃
   - 输入 `javascript:alert(1)`
   - 验证：格式校验拦截（协议不合法）
3. **快速切换测试**：
   - 连续 10 次快速修改 URL 并保存
   - 验证：App 不崩溃，WebView 正常加载最后一次保存的 URL
4. **/health 异常测试**：
   - 输入可访问的非 DeerFlow 服务器地址（如百度）
   - 验证：连接测试成功，但身份验证失败，保存按钮禁用
5. **弱网模拟**：
   - 通过代理工具限制带宽（如 Clumsy 或 Charles 限速）
   - 验证：连接测试在 5 秒超时内正常工作

**验收标志**: 所有暴力测试场景通过（需在真机 HBuilderX 调试中执行）

---

### Task 8: 文档同步 ✅

**描述**: 更新 CLAUDE.md 和设计文档，反映新的交互逻辑。

**步骤**:
1. 更新 `CLAUDE.md`：
   - 修改「Server URL — 运行时配置」章节
   - 描述新的 cover-view 配置浮层交互
   - 添加三层防护说明（格式校验 → 内网检测 → /health 身份验证）
   - 添加错误覆盖层说明
2. 更新 `docs/superpowers/specs/2026-05-29-app-ux-optimization-design.md`：
   - 在文档头部添加实现状态

**验收标志**: CLAUDE.md 和设计文档内容与实际代码行为一致

---

## Task Dependencies
- Task 7（暴力测试）依赖 Task 1-6 全部完成 — **需主子在真机执行**
- Task 8（文档同步）依赖 Task 1-6 全部完成
- Task 1-6 无顺序依赖关系，已并行在一轮完成
