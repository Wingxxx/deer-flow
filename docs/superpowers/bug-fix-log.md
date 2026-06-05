# DeerFlow App Bug Fix Log

> 记录 App 开发过程中发现并修复的问题，供后续维护参考。

---

## Bug 1: 定时器误触发错误覆盖层

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
填写正确的 URL 后，App 正常运行一段时间，但**每隔约 10 秒自动弹出错误提示页**，要求修改 URL。点击「保存并加载」可以回到正常界面，但过一会又重复出现。

### 根因分析
`onShow()` 方法中有一处**多余的 10 秒定时器**逻辑：

```js
// ❌ Bug 代码
onShow() {
  this.loadSuccess = false   // 每次回到前台都重置
  setTimeout(function() {    // 每次都启动10秒定时器
    if (!this.loadSuccess) {  // 10秒后检查是否加载成功
      this.showErrorOverlay = true
    }
  }, 10000)
}
```

`onShow()` 在以下场景都会触发：
1. App 首次启动
2. App 从后台切回前台
3. 页面从导航栈中重新显示

**触发链路**：
1. App 首次启动 → `onShow()` → `loadSuccess=false` + 10秒定时器
2. WebView 加载成功 → `@load` 事件 → `loadSuccess=true` ✅
3. 用户切到其他 App 再回来 → `onShow()` **再次调用**
4. `loadSuccess=false` 再次被重置 → 10秒定时器重新启动
5. 但 WebView 已经加载好了，**不会重新触发 `@load` 事件**
6. 10秒后 `loadSuccess` 仍然是 `false` → 定时器误以为加载失败 → 弹出错误覆盖层

### 修复方案
**彻底移除定时器**，错误覆盖层只由 WebView 原生的 `@error` 事件驱动：

```js
// ✅ 修复后
onShow() {
  // URL 变化时才重置状态
  if (targetUrl !== this.webviewSrc) {
    this.webviewSrc = targetUrl
    // ... 不设 loadSuccess，不启动定时器
  }
  // 无定时器！
},
onWebViewLoad() {
  this.showErrorOverlay = false  // 加载成功就隐藏错误页
},
onWebViewError() {
  this.showErrorOverlay = true   // 加载失败才显示错误页
}
```

### 经验教训
- WebView 的 `@load` 和 `@error` 原生事件已经足够覆盖「成功/失败」两种状态，无需额外定时器
- `onShow()` 是高频回调，不适合在其中设置一次性定时器
- 错误状态应由**事件驱动**而非**定时轮询**

---

## Bug 2: config.js 修改后不生效（本地存储覆盖）

**发现日期**: 2026-05-29
**状态**: 已修复 → 最终方案: 彻底删除所有存储逻辑 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
修改 `config.js` 中的 `serverUrl` 后，App 依然访问旧地址。

### 根因分析
最初的问题是 `df_server_url` 存储永远覆盖 config.js。第一次修复为 `df_custom_url` 分离存储（v2 修复），但在后续迭代中**主子明确要求 config.js 为唯一权威来源**，禁止任何存储逻辑。

### 最终方案（2026-05-29）
**彻底删除所有 `getStorageSync` / `setStorageSync` / `removeStorageSync` 调用**：
- `onShow()` 只读 config.js，不再读存储
- 扫码成功直接加载 WebView，不持久化
- 手动保存直接加载 WebView，不持久化
- 恢复默认只回退输入框为 config.js，不操作存储
- 清理旧 `df_server_url` 兼容代码也一并删除

config.js 永为权威基准，扫码/手动输入的 URL 只在当前会话生效，重启 App 后回到 config.js。

---

## Bug 3: 扫码验证失败时错误信息被覆盖

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
扫码后 `/health` 验证失败，报错信息一闪而过，用户只能看到面板打开但看不到详细的错误内容。

### 根因分析
`processScannedUrl()` 中验证失败时，`self.testResult = { fail: ... }` 在 `self.openConfigPanel()` **之前**执行。而 `openConfigPanel()` 会清空 `testResult`，导致错误信息丢失。

```js
// ❌ Bug 代码
self.testResult = { type: 'fail', message: '...' }  // 先设
self.openConfigPanel()                                 // 后清 → 丢了！
```

### 修复
交换顺序，先开面板再设 testResult：
```js
// ✅ 修复后
if (self.showConfigPanel === false) {
  self.openConfigPanel()
  self.inputUrl = url
}
self.testResult = { type: 'fail', message: '...' }   // 面板开完再设
```

---

## Bug 4: 扫码相机无法自动识别二维码

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
相机打开后能看到二维码，但不会自动识别。用户手动取消后，尝试从相册导入也返回 `cancel`。

### 根因分析
`uni.scanCode()` 在某些设备上扫码灵敏度偏低，相机预览持续但不触发 success。

### 修复历程
1. 尝试换成 `plus.barcode.scan()`（更底层的原生 API）→ 模拟器上完全崩溃
2. 换回 `uni.scanCode()` → 保留日志 + 超时兜底 + 重复点击保护等改进

### 最终方案
回退到 `uni.scanCode()`，保留以下改进：
- 10 秒超时自动释放 `scanning` 标志，防止按钮卡死
- 重复点击时 toast "扫码正在进行中..."
- 失败时记录完整错误对象到日志文件
- 成功/失败都写入文件日志

---

## Bug 5: 悬浮按钮在模拟器上不可见/点不着

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
真机上 ⚙ 悬浮按钮可见可用，但模拟器上完全看不见。

### 根因分析
`<web-view>` 是 uni-app 原生组件，渲染在独立的 Native 层，**完全覆盖 Vue DOM 层**。无论 CSS `z-index` 多高，Vue 渲染的按钮都在 WebView 之下。

### 修复方案
1. **废弃 Vue DOM 按钮**：删除模板中的 `.settings-trigger` 和对应 CSS
2. **改用原生绘制层**：`plus.nativeObj.View` 创建原生圆形按钮，渲染在所有 Native 组件之上
3. **Destroy/Create 策略**：点击按钮时 `destroyFloatBtn()` 彻底销毁，关闭面板时 `createFloatBtn()` 重新创建
4. **配置面板打开时隐藏 WebView**：`openConfigPanel()` 设置 `showWebView = false`，让 Vue DOM 露出来
5. **生命周期管理**：`onReady()` 创建、`onHide()` 销毁、`onShow()` 重建

---

## Bug 6: /health 端点需登录认证导致验证失败

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
扫码后 `/health` 返回 `{"detail": {"code": "not_authenticated", "message": "Authentication required"}}`，原代码只认 `service === "deer-flow-gateway"`，不认认证错误，报「非 DeerFlow 服务器」。

### 修复方案
放宽验证条件，满足其一即视为有效：
```js
var isValid = false
if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') {
  isValid = true  // 标准健康检查
}
if (res.data && res.data.detail && res.data.detail.code === 'not_authenticated') {
  isValid = true  // 需要登录——一定是 DeerFlow
}
if (statusCode === 401 || statusCode === 403) {
  isValid = true  // 未认证/被拒绝——有 /health 端点
}
```

---

## Bug 7: URL 末尾斜杠导致 /health 请求 404

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
扫码结果 `http://192.168.1.56:2026/`（末尾带 `/`）拼 `/health` 后变为 `http://192.168.1.56:2026//health`（双斜杠）。内网 curl 测试可正常处理，但**手机上通过外网访问**时双斜杠被路由截断，返回 `{"detail":"Not Found"}`。

### 修复
```js
// ✅ 修复后
url: url.replace(/\/+$/, '') + '/health',
```

正则 `\/+$` 去掉 URL 末尾所有斜杠，保障三种格式都正确：
```
http://192.168.1.56:2026/   →  http://192.168.1.56:2026/health  ✅
http://192.168.1.56:2026//  →  http://192.168.1.56:2026/health  ✅
http://192.168.1.56:2026    →  http://192.168.1.56:2026/health  ✅
```

`processScannedUrl()` 和 `testConnection()` 两处都做了修复。

---

## 新增功能记录

### 文件日志系统
- 位置: `writeLog()` 方法
- 文件: 手机 `PRIVATE_DOC` 目录下的 `df_scan_log.txt`
- 记录内容: 扫码开始/成功/失败 + 设备信息 + 完整错误对象 + `/health` 响应状态码和数据 + WebView 加载错误详情
- 查看方式: 配置面板失败时显示「📋 查看日志」按钮 + 「🗑 清空日志」按钮

### WebView 错误详情显示
- 错误页新增 `error-detail` 区域，WebView 加载失败时显示完整的错误对象（红色小字）
- `webViewError` 变量存储错误详情，加载成功或重试时自动清空

### /health 响应日志
- 每次 /health 请求都会记录状态码和响应数据到日志文件，方便调试

---

---

## Bug 8: 冷启动后 WebView Session Cookie 丢失需要重新登录

**发现日期**: 2026-06-03
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
App 冷启动（进程被杀死后重新打开）后，WebView 加载 DeerFlow 页面需要重新登录。同一地址在桌面浏览器中关闭再打开仍保持登录状态。

### 根因分析
DeerFlow 后端使用 Session Cookie（无 `Expires`/`Max-Age` 属性）认证。App 冷启动时 WebView 实例重建，会话 Cookie 丢失，服务器视为新会话。

| 平台 | 原因 |
|------|------|
| Android | 系统 WebView 进程回收，会话 Cookie 丢失 |
| iOS | WKWebView 默认不持久化跨启动 Cookie；ITP 7 天自动清除 |

### 修复方案
Cookie 持久化三层架构：

```
onShow ──→ readCookieFile() ──→ CookieManager.setCookie() + flush() ──→ WebView loadUrl
                                                                           │
onWebViewLoad ──→ captureCookies() ──→ saveCookieFile()                  │
                                                                           │
定时器(5s) ──→ captureCookies() ──→ saveCookieFile() (捕获 SPA 内 Cookie 变化)
                                                                           │
onHide ──→ stopCookieSync() + 最后一次 captureCookies()
```

#### Android 端
使用 `plus.android.importClass('android.webkit.CookieManager')` 原生 API：
- `onShow()` 中在 WebView 加载 URL 之前恢复 Cookie
- `CookieManager.setCookie(domain, cookies)` + `flush()` 刷入磁盘
- `onWebViewLoad` 和定时器中通过 `getCookie(domain)` 捕获

#### iOS 端
WKWebView 不暴露原生 CookieManager，改用 JS 桥接：
- `onWebViewLoad` 中通过 `evalJS('document.cookie = "..."')` 注入已保存 Cookie
- 500ms 后 `location.reload()` 使 Cookie 生效（仅首次）
- `cookieInjected` 标记防死循环
- 注入的 JS 通过 `Object.defineProperty` 覆写 `document.cookie` 叠加监控层，保留原始 getter/setter
- 标题通道：`window.__df_ck` 每 5s 同步到 `document.title`

#### 文件存储
Cookie 持久化到 `PRIVATE_DOC/df_cookies.txt`，纯文本格式，与扫码日志同存储域。

#### URL 切换隔离
扫码切换服务器地址时清空 `cookieStore` 和 `df_cookies.txt`，防止旧 Cookie 污染新地址。

### 详细设计文档
`docs/superpowers/specs/2026-06-03-webview-cookie-persistence-spec.md`

### 已知限制
- iOS 端无法读取 HttpOnly Cookie（`document.cookie` 限制），如发现持久化失败需服务器端去掉 HttpOnly 标志
- iOS 端首次启动会有一个「加载 → 注入 → 刷新」的短暂闪烁
- Apple ITP 可能在 7 天后自动清除 Cookie

---

## Bug 9: iOS 端 evalJS 无返回值

**发现日期**: 2026-06-03
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
iOS WKWebView 的 `evalJS()` 方法无法返回 JavaScript 执行结果，导致无法通过 `evalJS('document.cookie')` 获取 Cookie 值。

### 根因分析
`plus.webview.WebviewObject.evalJS()` 在 iOS 端是单向调用——注入脚本但不返回结果。这是 WKWebView 的安全设计。

### 修复方案
**文档标题通道**：在注入的监控脚本中，每 5 秒将 `window.__df_ck` 写入 `document.title`：
```javascript
D.title = D.title.replace(/__DF_CK=[^;]*;?/g, '') + '__DF_CK=' + encodeURIComponent(ck)
```
原生端通过 `pw.getTitle()` 正则匹配 `__DF_CK=` 标记获取 Cookie。

---

## 通用教训

1. **事件驱动优于定时轮询**：WebView 的生命周期事件已经足够覆盖所有状态变化
2. **config.js 永为权威基准**：不设存储逻辑，编译时配置是唯一来源
3. **原生 vs Vue 渲染**：`<web-view>` 是原生组件盖在 Vue DOM 之上，Vue 按钮会被遮住，必须用 `plus.nativeObj.View`
4. **Destroy/Create 优于 Hide/Show**：Native 组件的 hide/show 状态不可靠，destroy/create 更稳定
5. **双斜杠问题**：URL 拼接前必须先去除末尾斜杠，内网正常不等于外网正常
6. **/health 验证放宽**：认证错误/拒绝访问也算 DeerFlow 服务器的特征
7. **幂等设计**：onShow 等高频回调应设计为幂等的，重复调用不产生副作用
