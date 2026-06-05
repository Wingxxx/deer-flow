# WebView Cookie 持久化 — 验收清单

## TDD / 实施检查项

### Phase 1: 基础准备
- [ ] 1.1 `data()` 中新增 `cookieStore: ''`、`cookieSyncTimer: null`、`cookieInjected: false`
- [ ] 1.2 新增 `saveCookieFile(cookies)` 方法
- [ ] 1.3 新增 `readCookieFile(callback)` 方法
- [ ] 1.4 新增 `captureCookies()` 方法（Android + iOS 双路径）
- [ ] 1.5 新增 `startCookieSync()` / `stopCookieSync()` 方法

### Phase 2: Android 端集成
- [ ] 2.1 `onShow()` 中在设置 webviewSrc 前调用 Cookie 恢复
- [ ] 2.2 `onWebViewLoad()` 中调用 `captureCookies()`
- [ ] 2.3 `captureCookies()` Android 分支使用 `CookieManager.getInstance().getCookie(domain)`
- [ ] 2.4 Cookie 恢复时调用 `flush()` 确保持久化
- [ ] 2.5 防重复写入（cookieStore 比对）

### Phase 3: iOS 端集成
- [ ] 3.1 `onWebViewLoad()` 中 `#ifdef APP-IOS` 分支注入 Cookie
- [ ] 3.2 注入后 500ms `location.reload()` + `cookieInjected` 防死循环
- [ ] 3.3 `injectFix()` 的 injectedFn 中加入 `__df_cookie` 监控脚本
- [ ] 3.4 文档标题通道：注入的 JS 每 5s 将 `__df_cookie` 同步到 `document.title`
- [ ] 3.5 `captureCookies()` iOS 分支通过标题通道或轮询获取 Cookie

### Phase 4: 生命周期集成
- [ ] 4.1 `onHide()` 中停止轮询 + 最后一次捕获
- [ ] 4.2 `processScannedUrl()` 成功分支清空 Cookie 文件
- [ ] 4.3 `retryLoad` 不清 Cookie（重试同地址）

### Phase 5: 健壮性
- [ ] 5.1 所有原生 API 调用加 try-catch
- [ ] 5.2 文件读取失败回调控空字符串
- [ ] 5.3 iOS evalJS 在页面未就绪时由 injectFix 重试机制兜底

## 暴力测试验收项

### 文件破坏测试
- [ ] CT-01: 空文件冷启动不报错
- [ ] CT-02: 二进制乱码文件冷启动不报错
- [ ] CT-03: 10MB 超大文件冷启动不报错
- [ ] CT-04: JSON 格式文件冷启动不报错
- [ ] CT-05: 特殊字符 Cookie 不崩溃
- [ ] CT-06: Secure 标记在 HTTP 下不崩溃
- [ ] CT-07: 50+ Cookie 设置正常

### 并发/时序测试
- [ ] CT-08: 快速前台/后台切换无泄漏
- [ ] CT-09: 启动即退出不损坏文件
- [ ] CT-10: 写入中途杀进程不崩溃
- [ ] CT-11: 捕获/恢复无竞态
- [ ] CT-12: 扫码后立即冷启动正常

### 网络异常测试
- [ ] CT-13: 离线启动不阻塞
- [ ] CT-14: 离线启动后恢复网络可正常登录
- [ ] CT-15: Cookie 过期正常显示登录页
- [ ] CT-16: /health 返回 401 不受影响

### 平台专有测试
- [ ] CT-17: iOS evalJS 重试机制生效
- [ ] CT-18: iOS HttpOnly Cookie 不崩溃（已知限制）
- [ ] CT-19: iOS ITP 7 天清除后正常显示登录页
- [ ] CT-20: iOS location.reload 无死循环
- [ ] CT-21: Android CookieManager 异常时静默跳过
- [ ] CT-22: Android WebView 无 children 时使用 parent
- [ ] CT-23: Android 多域名 Cookie 不混淆

### 长时间运行
- [ ] CT-24: 24 小时后台无 CPU 泄漏
- [ ] CT-25: 500 次冷启动循环稳定
- [ ] CT-26: 1000 次文件写入稳定

## 安全验收项
- [ ] SA-01: Cookie 文件仅 App 自身可读写（PRIVATE_DOC 保证）
- [ ] SA-02: URL 切换时旧 Cookie 被彻底清空
- [ ] SA-03: 所有原生 API 异常不泄露栈信息到 UI

## 文档验收项
- [ ] DA-01: `docs/superpowers/bug-fix-log.md` 已更新（Bug 8/9）
- [ ] DA-02: `CLAUDE.md` 已追加 Cookie 持久化章节
- [ ] DA-03: 本 spec 文件状态标记为「已实施」
