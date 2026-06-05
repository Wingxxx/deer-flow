# WebView Cookie 持久化 — 设计规格说明书

**日期**: 2026-06-03  
**状态**: 已实施 ✅  
**署名**: WING

---

## 1. 问题陈述

### 1.1 现象

DeerFlowApp（uni-app WebView 壳层）每次冷启动后，访问 DeerFlow 服务器（`http://192.168.1.56:2026/`）都需要**重新登录**。同一台设备上使用桌面浏览器打开相同 URL，关闭浏览器再打开仍保持登录状态。

### 1.2 根因

DeerFlow 后端使用 HTTP Session Cookie 认证。服务器通过 `Set-Cookie: sessionid=<value>` 下发会话标识。该 Cookie 为**会话 Cookie**（无 `Expires`/`Max-Age` 属性），生存期绑定于浏览器进程生命周期。

在 uni-app `<web-view>` 组件环境中：

| 平台 | WebView 类型 | Cookie 行为 |
|------|-------------|-------------|
| Android | 系统 WebView | 有 `Expires/Max-Age` 的 Cookie 由 `CookieManager` 自动持久化；**会话 Cookie**（无过期属性）在 WebView 进程销毁时丢失 |
| iOS | WKWebView | 默认不持久化跨启动 Cookie；Apple ITP（智能防跟踪）对无用户交互的 Cookie 7 天后自动清除 |

App 冷启动（进程被杀死后重新打开）时，WebView 实例重建，会话 Cookie 丢失 → 服务器不认识该请求 → 要求重新登录。

### 1.3 成功标准

1. App 冷启动后，WebView 直接显示已登录状态（无需用户交互）
2. 登录态在 App 正常使用期间持续有效（不意外退出）
3. Cookie 恢复失败时优雅回退（显示登录页，不阻塞 App）
4. 切换服务器地址时旧 Cookie 不影响新连接
5. 双平台（Android / iOS）行为一致

---

## 2. 技术架构

### 2.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    DeerFlowApp (uni-app)                     │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              pages/index/index.vue                    │  │
│  │                                                       │  │
│  │  onShow() ──► restoreCookies() ──► set webviewSrc     │  │
│  │                                   (Cookie已就位)       │  │
│  │                                                       │  │
│  │  onWebViewLoad() ──► captureCookies()                 │  │
│  │                    ──► startCookieSync() (每5s)        │  │
│  │                                                       │  │
│  │  onHide() ──► stopCookieSync() ──► saveCookies()      │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                Cookie 存储层                            │  │
│  │  File: PRIVATE_DOC/df_cookies.txt                     │  │
│  │  Format: raw cookie string (; 分隔)                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────┐  ┌────────────────────────────────┐   │
│  │ Android:         │  │ iOS:                           │   │
│  │ CookieManager    │  │ evalJS('document.cookie')      │   │
│  │ .setCookie()     │  │ + __df_cookie 全局变量监控      │   │
│  │ .getCookie()     │  │ + location.reload() 触发       │   │
│  │ .flush()         │  │   重新加载使 Cookie 生效        │   │
│  └──────────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 壳层框架 | uni-app (Vue 3) | HBuilderX 编译 |
| 原生桥接 | `plus.android.importClass` | Android 端访问原生 CookieManager |
| JS 桥接 | `wv.evalJS()` | 双平台通用，用于注入/读取 Cookie |
| 文件存储 | `plus.io.PRIVATE_DOC` | 与扫码日志共用同一存储域 |
| 定时同步 | `setInterval` (5s) | 低开销轮询 Cookie 变化 |

### 2.3 系统边界

**本方案涉及（壳层）**：
- `pages/index/index.vue`：所有 Cookie 管理逻辑
- `PRIVATE_DOC/df_cookies.txt`：Cookie 持久化文件

**本方案不涉及**：
- DeerFlow 后端代码（零改动）
- `config.js`（零改动，继续作为唯一 URL 来源）
- `manifest.json`（零改动）
- 第三方 npm 包或原生插件（零引入）
- `uni.getStorageSync`（继续保持零存储策略——Cookie 文件存储作为特例）

---

## 3. 详细设计

### 3.1 Cookie 文件格式

**文件路径**: `_doc/df_cookies.txt`（通过 `plus.io.PRIVATE_DOC` 解析）

**存储格式**: 原始的 Cookie 字符串，保持 `CookieManager.getCookie()` 的返回格式

```
sessionid=abc123def456; csrftoken=xyz789; theme=dark
```

**约束**:
- 单文件，纯文本，UTF-8 编码
- 无结构化（JSON/XML）包装——保持与原生 CookieManager 的直接兼容
- 文件大小上限：预估 < 8KB（单个域名 Cookie 通常 < 4KB）
- 不设过期——过期由服务器端 Session 决定，恢复无效 Cookie 时用户自然重登录

### 3.2 Android 端实现

#### 3.2.1 Cookie 恢复（onShow → 加载 URL 之前）

```
流程:
  1. readCookieFile() → cookies string
  2. if cookies 存在:
     a. CookieManager.getInstance().setAcceptCookie(true)
     b. CookieManager.getInstance().setCookie(domain, cookies)
     c. CookieManager.getInstance().flush()     ← 关键：立即刷入磁盘
  3. 设置 webviewSrc → WebView 加载
```

**关键约束**:
- `flush()` 必须调用——否则修改仅在内存中，App 被杀后丢失
- `domain` 必须精确匹配（`http://192.168.1.56:2026` 而非无端口形式）
- 需在 WebView 调用 `loadUrl()` 之前完成

#### 3.2.2 Cookie 捕获（onWebViewLoad / 定时器）

```
CookieManager.getInstance().getCookie(domain)
→ 返回 "key1=val1; key2=val2" 或 null
→ 写入 df_cookies.txt
```

#### 3.2.3 防重复写入

每次捕获到新 Cookie 时与 `this.cookieStore` 比较：
- 相同：跳过（减少 I/O）
- 不同：更新 `this.cookieStore` + 写入文件

### 3.3 iOS 端实现

WKWebView 不暴露原生 CookieManager 接口。只能通过 `evalJS()` 在 WebView 页面上下文中操作 `document.cookie`。

#### 3.3.1 Cookie 恢复策略（首次加载）

```
限制: 无法在 loadUrl() 之前注入 Cookie
方案: 两阶段加载
  1. 正常加载 URL → WebView onload 触发
  2. 在 onWebViewLoad 中 evalJS('document.cookie = "..."')
  3. 500ms 后 evalJS('location.reload()') 重新加载使用 Cookie
```

**注意**: 这会导致页面短暂闪烁（未登录 → 注入 → 刷新 → 已登录）。通过以下方式缓解：
- 仅在首次加载（`cookieInjected === false`）时触发
- 后续页面内导航不会触发 reload
- 可在加载画面阶段完成注入后再显示 WebView

#### 3.3.2 Cookie 捕获

在 WebView 中注入 Cookie 监控 JS：

```javascript
// 注入到 WebView 的脚本
var __df_cookie = document.cookie;
Object.defineProperty(document, 'cookie', {
    get: function() { return __df_cookie; },
    set: function(val) {
        // 处理单个 cookie 设置（document.cookie = "key=val" 只设置一个）
        var name = val.split('=')[0].trim();
        var existing = __df_cookie;
        var parts = existing.split(';').map(function(p) {
            var n = p.trim().split('=')[0];
            if (n === name) return val;  // 替换同名 cookie
            return p;
        });
        __df_cookie = parts.join('; ');
        return val;
    }
});
// 建立时立即暴露
__df_cookie;
```

原生端每 5 秒调用 `wv.evalJS('__df_cookie')` 获取当前 Cookie 字符串。

**⚠️ 已知限制**: `evalJS()` 在 iOS 端**没有返回值**。替代方案：
1. **文档标题通道**：让 JS 将 `__df_cookie` 写入 `document.title`，原生端监听 `onTitleUpdate` 事件
2. **URL 拦截**：让 JS 通过 `location.hash = '#cookie=' + encodeURIComponent(__df_cookie)` 回传（会触发页面内导航事件）
3. **降级方案**：iOS 端放弃定时捕获，仅在每次 `onWebViewLoad` 时通过标题通道捕获一次

**选定方案**: 方案 1（文档标题通道）。在注入的 JS 中添加：
```javascript
// 每 5 秒同步到 title
setInterval(function() {
    document.title = document.title.replace(/__DF_CK=.*/, '') + '__DF_CK=' + encodeURIComponent(__df_cookie);
}, 5000);
```
原生端通过 `wv.titleUpdate` 或监听 `currentWebview().getTitle()` 轮询。

### 3.4 Cookie 同步时机

| 事件 | 操作 | 说明 |
|------|------|------|
| `onShow` (App 回到前台) | 恢复 Cookie → 加载 WebView | URL 加载前完成（Android） |
| `onWebViewLoad` (页面加载) | 捕获 Cookie + 注入 iOS Cookie | 确保登录后的 Cookie 被持久化 |
| `startCookieSync` (定时器) | 每 5s 轮询 Cookie 变化 | 捕获 SPA 内部跳转产生的 Cookie |
| `onHide` (App 进入后台) | 停止轮询 + 最后一次捕获 | 防后台耗电 |
| 扫码/手动切换 URL | 清空 `cookieStore` | 旧 Cookie 不污染新地址 |
| `retryLoad` | 不清 Cookie | 重试同一地址不需要重新登录 |

### 3.5 URL 切换时的 Cookie 隔离

当用户扫码切换服务器地址时：
1. 新地址经过 `/health` 验证通过
2. 清空 `this.cookieStore`（内存）
3. 删除 `df_cookies.txt`（文件）
4. 加载新 URL（无 Cookie，需重新登录）
5. 新登录后重新捕获并保存

**设计理由**: 不同 DeerFlow 服务器的 Session Cookie 不互通。保留旧 Cookie 除了增加文件大小外无意义。

---

## 4. 错误处理与边界

### 4.1 文件操作异常

| 场景 | 行为 | 不影响 |
|------|------|--------|
| 文件不存在 | `readCookieFile` 回调空字符串 | ✓ |
| 文件损坏/乱码 | 回调控空字符串，不解析 | ✓ |
| 文件写入失败 | `saveCookieFile` 静默失败（try-catch） | ✓ 功能降级但不阻塞 |
| 并发读写 | 文件操作全同步回调，无并发冲突 | ✓ |

### 4.2 原生 API 异常

| 场景 | 行为 | 不影响 |
|------|------|--------|
| `CookieManager` 类加载失败 | try-catch 捕获，静默跳过 | ✓（iOS 不走此路径） |
| `CookieManager.getInstance()` 返回 null | `if (cm)` 保护 | ✓ |
| `setCookie` 设置失败 | 后续 WebView 无 Cookie → 显示登录页 | ✓（正常行为） |
| `flush()` 抛异常 | try-catch 捕获 | ✓ 内存中仍有效 |

### 4.3 iOS 特有异常

| 场景 | 行为 | 不影响 |
|------|------|--------|
| `evalJS` 在页面加载前调用 | 注入 `injectFix` 的 retry 机制自动重试 | ✓ |
| 注入的 Cookie 被 ITP 拦截 | 注入后 location.reload 可触发新的 Cookie 设置 | ⚠️ 可能有延迟 |
| `document.title` 通道被页面覆盖 | 正则替换 `__DF_CK=` 标记 | ✓ |

### 4.4 安全性考量

- **Cookie 明文存储**: `PRIVATE_DOC` 为 App 私有目录，其他 App 不可读，内网场景风险可控
- **HttpOnly Cookie**: Android 端 `CookieManager.getCookie()` 可获取 HttpOnly Cookie；iOS 端 `document.cookie` 不可获取 HttpOnly Cookie。这意味着 iOS 端可能无法捕获某些安全 Cookie，登录后可能仍无法持久化。**应对**: 如果发现 iOS 端持久化失败，建议服务器端在设置 Session Cookie 时去掉 `HttpOnly` 标志（内网场景下风险可接受）
- **无加密**: 不引入额外加密层（方案边界决策）

---

## 5. 暴力测试方案（Brute-Force Testing）

### 5.1 Cookie 文件破坏性测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-01 | 空文件 | 写入空字符串到 `df_cookies.txt` → 冷启动 App | App 正常加载，显示登录页 |
| CT-02 | 二进制乱码 | 写入随机二进制数据（`\x00\xFF\xFE...`）→ 冷启动 | 回退到无 Cookie 状态 |
| CT-03 | 超大文件 | 写入 10MB 随机字符 → 冷启动 | 读取失败 → 回退；不影响 UI 渲染 |
| CT-04 | JSON 格式 | 写入 `{"session":"abc"}` → 冷启动 | 不被解析，`setCookie` 忽略无效格式 |
| CT-05 | 特殊字符 | 写入含引号、分号、中文、Unicode 的 Cookie → 冷启动 | Android 端 `setCookie` 处理；iOS 端 escape 后注入 |
| CT-06 | 同时包含 `Secure` 标记 | 写入 `sessionid=xxx; Secure; HttpOnly` → 冷启动 (HTTP 环境) | 浏览器自动忽略 Secure Cookie（不生效，但不崩溃） |
| CT-07 | 50+ 个 Cookie | 生成 `key1=val1; key2=val2; ... key50=val50` → 冷启动 | Android 端完整设置；WebView 正常加载 |

### 5.2 并发/时序测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-08 | 快速切换前台/后台 | 连续 10 次 `Home → App` 切换，间隔 < 1s | 最后一次 `onHide` 的捕获完成；无内存泄漏 |
| CT-09 | App 启动时立即退出 | 冷启动 → 看到品牌画面 → 立即退出 → 再次启动 | Cookie 文件不被损坏 |
| CT-10 | 写入中途杀进程 | 在 `saveCookieFile` 执行中强制杀 App | 文件可能截断 → 下次读取回退（无崩溃） |
| CT-11 | 捕获 + 恢复同时发生 | 定时器捕获与 `readCookieFile` 回调节奏冲突 | JS 单线程 + 文件 API 回调队列确保无竞态 |
| CT-12 | 扫码后立即冷启动 | 扫码切换 URL → 不等页面加载 → 杀进程 → 重启 | 旧 Cookie 文件已清空 → 新地址无 Cookie → 显示登录页 |

### 5.3 网络异常测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-13 | 离线启动 + 有 Cookie | 开启飞行模式 → 冷启动 App | `/health` 失败 → 错误覆盖层；Cookie 恢复不阻塞 |
| CT-14 | 离线恢复 Cookie 后恢复网络 | 飞行模式启动 → 点击重试 → 关闭飞行模式 | Cookie 已就位 → /health 通过 → WebView 显示已登录 |
| CT-15 | Cookie 过期场景 | 保存过期 Cookie（服务器 Session 已过期）→ 冷启动 | WebView 加载 → 服务器返回 302 到登录页（正常行为） |
| CT-16 | /health 返回 401 | `/health` 返回 401 但 Cookie 有效 | 健康检查验证通过（401 视为有效），WebView 正常加载 |

### 5.4 iOS 专有测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-17 | evalJS 在页面加载前调用 | 极低端设备上 `injectFix` 重试 5 次均失败 | `cookieInjected` 不被设置，下次 `onWebViewLoad` 再试 |
| CT-18 | HttpOnly Cookie 无法通过 JS 读取 | 服务器设置 HttpOnly Cookie → iOS 端 `document.cookie` 为空 | 不报错；用户需重新登录（已知限制，记录文档） |
| CT-19 | ITP 7 天清除 | 登录后放置 7 天不打开 App → 重新打开 | Cookie 可能已被 ITP 清除 → 需重新登录（已知限制） |
| CT-20 | location.reload 循环 | iOS 端注入 Cookie → reload → 页面又触发 onWebViewLoad → 再注入 → reload | 仅首次注入时 `cookieInjected` 标记防止死循环 |

### 5.5 Android 专有测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-21 | CookieManager 在 plus 环境不可用 | 模拟 `plus.android.importClass` 抛异常 | try-catch 捕获，静默跳过 |
| CT-22 | WebView 没有 children | `pw.children()` 返回空数组 | `wv = pw` 使用 parent 自身 |
| CT-23 | 多域名 Cookie | DeerFlow 页面中嵌入了其他域名的资源 Cookie | `getCookie(domain)` 只返回指定域名 Cookie；文件只存目标域名 |

### 5.6 长时间运行测试

| 编号 | 测试场景 | 操作步骤 | 预期结果 |
|------|---------|---------|---------|
| CT-24 | 24 小时后台运行 | App 在后台运行 24 小时 | 定时器在 `onHide` 时已停止，后台无 CPU 消耗 |
| CT-25 | 500 次冷启动循环 | 自动化脚本：启动 → 检查登录 → 杀进程 → 重启 | Cookie 在 500 次循环中始终有效（除非服务器 Session 过期） |
| CT-26 | 大文件写入 1000 次 | 注入 1000 次 Cookie 变化 | 文件 I/O 稳定，不产生内存泄漏 |

---

## 6. 实现计划（实施步骤）

### Step 1: `data()` 新增状态字段

在现有 `data()` 末尾加入：
```javascript
cookieStore: '',
cookieSyncTimer: null,
cookieInjected: false
```

### Step 2: 新增 Cookie 工具方法

在 `methods` 中添加：
- `saveCookieFile(cookies)` — 写入 `_doc/df_cookies.txt`
- `readCookieFile(callback)` — 读取 Cookie 文件，回调控用
- `captureCookies()` — 从 CookieManager (Android) 或 evalJS (iOS) 获取当前 Cookie
- `startCookieSync()` — 启动 5s 定时器
- `stopCookieSync()` — 清除定时器

### Step 3: 修改 `onShow()`

在 `this.webviewSrc = configUrl` 之前插入 Cookie 恢复逻辑（仅 Android 端）。

### Step 4: 修改 `onWebViewLoad(e)`

在现有逻辑末尾追加：
1. Android 端：调用 `captureCookies()`
2. iOS 端：首次加载时执行 `evalJS` 注入 + 500ms 后 `location.reload()`
3. 两平台均调用 `startCookieSync()`

### Step 5: 修改 `onHide()`

在 `destroyFloatBtn()` 之前：
1. `stopCookieSync()`
2. `captureCookies()`（最后一次保存）

### Step 6: 修改 `injectFix()`

在 injectedFn 中加入 Cookie 监控脚本（iOS 专用），通过 `__df_cookie` 全局变量暴露。

### Step 7: URL 切换时清空 Cookie

在 `processScannedUrl()` 的成功分支中，切换 `webviewSrc` 之前：
1. `this.cookieStore = ''`
2. 删除 `df_cookies.txt`

---

## 7. 文档同步计划

### 7.1 实现后需更新的文档

| 文档路径 | 更新内容 |
|---------|---------|
| `docs/superpowers/specs/2026-06-03-webview-cookie-persistence-spec.md` | 本文件，实施后标记状态为「已实施」 |
| `docs/superpowers/bug-fix-log.md` | 新增 Bug 8（Cookie 丢失）、Bug 9（iOS evalJS 无返回值） |

### 7.2 CLAUDE.md 更新

在 `CLAUDE.md` 中追加：

```markdown
## Cookie 持久化机制（2026-06-03 新增）

### 文件位置
- Cookie 持久化文件：`PRIVATE_DOC/df_cookies.txt`（纯文本，; 分隔）
- 逻辑代码：`pages/index/index.vue` — `methods` 中的 Cookie 管理方法

### 双平台差异
- **Android**：使用 `plus.android.importClass('android.webkit.CookieManager')`，在 `onShow` 中 URL 加载前恢复
- **iOS**：使用 `evalJS('document.cookie')` + `__df_cookie` 全局变量监控，在 `onWebViewLoad` 后注入/捕获

### 已知限制
- iOS 端无法读取 HttpOnly Cookie（`document.cookie` 限制）
- iOS 端首次启动会有一个「加载 → 注入 → 刷新」的短暂闪烁
- Cookie 文件读取失败时静默回退，不阻塞 App

### 暴力测试参考
详见 `docs/superpowers/specs/2026-06-03-webview-cookie-persistence-spec.md` 第 5 章
```

---

## 8. 回滚方案

1. **还原**：`git checkout -- DeerFlowApp/DeerFlowApp/pages/index/index.vue`
2. **清理**：删除 `PRIVATE_DOC/df_cookies.txt`（如存在）
3. **验证**：App 回到原行为——每次冷启动需重新登录
4. **文档**：回滚 CLAUDE.md 中的 Cookie 持久化章节

---

## 9. 决策记录

| 决策 | 选项 | 选择理由 |
|------|------|---------|
| 存储方式 | 文件 vs. uni.storage | 文件操作与现有扫码日志一致；保持零存储策略精神 |
| 同步间隔 | 5s vs. 1s vs. 10s | 5s 平衡实时性和性能；1s 太耗电，10s 可能丢失 SPA 内快速变化 |
| iOS Cookie 注入 | 文档标题通道 vs. URL hash | 标题通道不影响页面导航；不会触发额外 onWebViewLoad |
| HttpOnly Cookie | 建议服务器去掉 vs. 接受限制 | 内网场景建议去 HttpOnly 以兼容 iOS；但本方案不做强制要求 |
| Cookie 文件格式 | 纯文本 vs. JSON | 纯文本与原生 CookieManager 直接兼容，无需序列化/反序列化 |
