# Verification Checklist — App UX Optimization + Stress Testing

## Task 1: 错误提示覆盖层
- [x] 1.1 覆盖层包含 ⚠️ 红色圆形图标 — 代码第7行 `.error-icon`
- [x] 1.2 覆盖层包含「无法连接服务器」标题 — 代码第8行
- [x] 1.3 覆盖层包含描述文本（提示网络连接或修改地址） — 代码第9行
- [x] 1.4 覆盖层包含当前 URL 卡片（灰色背景） — 代码第10-13行 `.url-card`
- [x] 1.5 覆盖层包含「✏️ 修改服务器地址」蓝色主按钮 — 代码第15行 `.btn-primary`
- [x] 1.6 覆盖层包含「🔄 检查网络并重试」次要按钮 — 代码第16行 `.btn-secondary`
- [x] 1.7 覆盖层全屏居中，z-index 高于 WebView — 样式 `.error-overlay` fixed, z-index: 9998
- [x] 1.8 `showErrorOverlay = true` 时覆盖层显示，`false` 时隐藏 — 代码第5行 `v-if="showErrorOverlay"`

## Task 2: URL 配置浮层
- [x] 2.1 点击 ⚙ 按钮弹出配置浮层 — 代码第50行 ⚙ 按钮 @click="openConfigPanel"
- [x] 2.2 浮层有半透明遮罩层，点击遮罩可关闭 — 代码第22行 `.config-mask` 半透明背景，@click="closeConfigPanel"
- [x] 2.3 浮层包含 URL 输入框（可编辑） — 代码第31行 `<input>` @input @blur
- [x] 2.4 浮层包含「🔌 测试连接」按钮 — 代码第36行
- [x] 2.5 浮层包含测试结果反馈区域 — 代码第39-41行 `testResult.message`
- [x] 2.6 浮层包含「💾 保存并加载」按钮（受 disabled 控制） — 代码第44行 `btn-disabled` 条件样式
- [x] 2.7 浮层包含「↩️ 恢复默认地址」按钮 — 代码第45行
- [x] 2.8 浮层包含提示文字区域（显示校验结果/内网检测提示） — 代码第32行 `urlHint`

## Task 3: 格式校验 + 协议自动补全 + 内网检测
- [x] 3.1 空输入时提示「请输入服务器地址」，保存按钮禁用 — 代码第192-197行
- [x] 3.2 输入非法字符（空格/中文）时提示「地址格式不正确」，保存按钮禁用 — 代码第200-213行
- [x] 3.3 输入无协议前缀的地址时自动补全 `http://` — 代码第229-232行 `autoCompleteProtocol()`
- [x] 3.4 输入公网域名时显示黄色内网检测提示 — 代码第216-218行 `isPublicDomain` → `hint-warn` 样式
- [x] 3.5 输入内网 IP 时无内网提示 — 代码第65-85行 `isPublicDomain` 对 192.168/10.x/172.16-31/127 返回 false
- [x] 3.6 输入自定义域名时无内网提示 — 非公网域名列表 + 非内网 IP → urlHint 清空

## Task 4: 服务器身份验证（硬限制）
- [x] 4.1 连接测试向 `{serverUrl}/health` 发送 GET 请求 — 代码第246-248行
- [x] 4.2 请求超时设置为 5 秒 — 代码第249行 `timeout: 5000`
- [x] 4.3 DeerFlow 服务器验证通过 → 绿色 ✓ 显示 → 保存按钮启用 — 代码第251-253行
- [x] 4.4 非 DeerFlow 服务器 → 红色 ⛔ 显示 → 保存按钮禁用 — 代码第254-256行
- [x] 4.5 网络错误 → 红色 ❌ 显示 → 保存按钮禁用 — 代码第259-266行
- [x] 4.6 验证 JSON：`service === "deer-flow-gateway"` 且 `status === "healthy"` — 代码第251行

## Task 5: 智能重试 + 网络监听
- [x] 5.1 点击「检查网络并重试」重新加载 WebView — 代码第308-328行 `retryLoad()`
- [x] 5.2 连续失败按指数退避：2s → 4s → 8s → 15s — 代码第332行 `delays = [2000, 4000, 8000, 15000]`
- [x] 5.3 加载成功后 `retryCount` 重置为 0 — 代码第160行 `onWebViewLoad`
- [x] 5.4 网络恢复后弹出提示 — 代码第137-141行 `uni.onNetworkStatusChange`
- [x] 5.5 加载成功后自动隐藏错误覆盖层 — 代码第158行 `onWebViewLoad` 设置 `showErrorOverlay = false`

## Task 6: WebView 事件监听
- [x] 6.1 WebView 绑定 `@error` 事件 — 代码第3行 `@error="onWebViewError"`
- [x] 6.2 WebView 绑定 `@load` 事件 — 代码第3行 `@load="onWebViewLoad"`
- [x] 6.3 加载错误时 `showErrorOverlay = true` — 代码第171-173行
- [x] 6.4 加载成功时 `showErrorOverlay = false` — 代码第158行
- [x] 6.5 10 秒加载超时检测（超时未成功则显示错误页） — 代码第129-135行
- [x] 6.6 页面隐藏时清除超时定时器 — 代码第143-147行 `onHide`

## Task 7: 暴力测试通过 ⏳（需在真机执行）
- [ ] 7.1 网络断开测试：断开 30 秒 + 恢复 → 错误覆盖层 → 网络恢复提示 → 重试正常
- [ ] 7.2 URL 注入测试：`"; DROP TABLE;--` → 格式校验拦截，不崩溃
- [ ] 7.3 URL 注入测试：`javascript:alert(1)` → 格式校验拦截，不崩溃
- [ ] 7.4 快速切换测试：5 秒内切换 10 次 URL → 不崩溃，最终 URL 正确加载
- [ ] 7.5 /health 异常测试：非 DeerFlow 服务器 → 连接测试成功，身份验证失败，保存禁用
- [ ] 7.6 弱网测试：延迟 3-5 秒 → 连接测试在超时内正常工作

## Task 8: 文档同步 ✅
- [x] 8.1 CLAUDE.md「Server URL — 运行时配置」已更新为 cover-view 浮层交互
- [x] 8.2 CLAUDE.md 已添加三层防护说明（格式校验 → 内网检测 → /health 验证）
- [x] 8.3 CLAUDE.md 已添加错误覆盖层说明
- [x] 8.4 CLAUDE.md 中已无过时的 plus.nativeUI.prompt 描述
- [x] 8.5 设计文档 `2026-05-29-app-ux-optimization-design.md` 已标注实现状态
- [x] 8.6 设计文档内容与实际代码行为一致
