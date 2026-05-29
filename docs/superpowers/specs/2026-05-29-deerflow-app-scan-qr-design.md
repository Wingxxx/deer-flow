# DeerFlow App 扫码绑定服务器地址 - 设计方案（最终版）

## 概述

在现有 URL 配置功能基础上，新增扫二维码直接绑定服务器地址的功能。用户扫码后自动提取 URL、自动 `/health` 验证、自动加载 WebView，实现「一扫即用」的闪电绑定体验。config.js 为唯一 URL 权威来源，不设存储持久化。

## 扫码入口

### 入口 1：错误覆盖层
WebView 加载失败时显示的错误页中，「📷 扫码自动绑定」按钮排在第一位，并显示红色错误详情文字。

```
┌──────────────────────────────┐
│        ⚠️                     │
│    无法连接服务器              │
│  [红色错误详情文字]            │
│  ┌─ 当前地址 ──────────────┐ │
│  │ http://192.168.1.56...  │ │
│  └─────────────────────────┘ │
│                              │
│  [📷 扫码自动绑定]            │
│  [✏️ 修改服务器地址]          │
│  [🔄 检查网络并重试]          │
└──────────────────────────────┘
```

### 入口 2：配置浮层
配置面板中「测试连接」按钮下方增加扫描按钮，失败时显示「📋 查看日志」和「🗑 清空日志」按钮。

```
┌──────────────────────────────┐
│      服务器设置           ✕   │
│  服务器地址                   │
│  ┌────────────────────────┐  │
│  │ http://...             │  │
│  └────────────────────────┘  │
│  [🔌 测试连接]               │
│  [📷 扫码自动绑定]            │
│  ✅ DeerFlow 服务器已验证 ✓   │
│  [📋 查看日志] [🗑 清空日志]  │
│  [💾 保存并加载]              │
│  [↩️ 恢复默认地址]            │
└──────────────────────────────┘
```

## 核心流程：全自动闪电绑定

```
用户点击「📷 扫码自动绑定」
  ↓
uni.scanCode() 调用系统相机扫码（10 秒超时兜底）
  ↓ 成功
提取二维码内容 → 格式校验（非空/非空格/非中文/自动补http://）
  ↓ 通过
内网检测提示（公网域名则toast警告，不阻断）
  ↓
自动 /health 验证 GET {去掉末尾斜杠的 url}/health（5秒超时）
  ├─ 符合任一条件：
  │   - service="deer-flow-gateway" + status="healthy"
  │   - detail.code === "not_authenticated"
  │   - 状态码 401 或 403
  │   → 直接加载 WebView → toast "扫码绑定成功: {url}"
  │   → 不持久化到存储
  └─ 都不匹配
      → 显示错误信息 → 打开配置面板（如有需要）→ 不跳转
```

## 悬浮按钮（⚙）

弃用 Vue DOM 渲染的 `<view>` 按钮（被 WebView 原生层覆盖），改用 `plus.nativeObj.View` 原生绘制层：

- **创建**：`onReady()` / `onShow()` 时调用 `createFloatBtn()`
- **销毁**：点击后 `destroyFloatBtn()` + 配置面板打开时 `showWebView = false`
- **重建**：关闭面板 / 扫码成功 / 保存成功 / 后台切回时 `createFloatBtn()`
- **外观**：50×50 半透明圆形，居中 ⚙ 字符
- **位置**：距顶 80%、距左 82%

## 代码变更

仅修改一个文件：`pages/index/index.vue`

### 新增方法

| 方法 | 说明 |
|------|------|
| `scanQRCode()` | 调用 `uni.scanCode()` 扫码，10 秒超时兜底，成功后调用 `processScannedUrl()` |
| `processScannedUrl(url)` | URL 校验 → 去掉末尾斜杠 → 自动补全协议 → 自动 `/health` 验证 → 自动加载 |
| `writeLog(msg)` | 写入文件日志到 `PRIVATE_DOC/df_scan_log.txt` |
| `viewScanLog()` | 读取日志文件并弹窗显示 |
| `clearScanLog()` | 清空日志文件 |
| `createFloatBtn()` | 创建原生 Native 悬浮按钮 |
| `destroyFloatBtn()` | 销毁原生悬浮按钮 |

### 新增状态

| 变量 | 类型 | 说明 |
|------|------|------|
| `scanning` | Boolean | 扫码进行中标志，10 秒超时自动释放 |
| `webViewError` | String | WebView 加载错误详情 |

### 模板改动

- 错误覆盖层：错误详情文字 + 扫码按钮排首位
- 配置浮层：扫码按钮 + 查看/清空日志按钮
- 删除旧的 Vue 悬浮按钮（`.settings-trigger`）

### /health 验证逻辑

三重识别：

```js
var isValid = false
if (data && data.service === 'deer-flow-gateway' && data.status === 'healthy') isValid = true
if (data && data.detail && data.detail.code === 'not_authenticated') isValid = true
if (statusCode === 401 || statusCode === 403) isValid = true
```

### URL 拼接防双斜杠

```js
url: url.replace(/\/+$/, '') + '/health',
```

## 约束条件

- ❌ 不新增第三方 SDK 或插件
- ❌ 不新增页面（单页面不变）
- ❌ **不使用 `getStorageSync` / `setStorageSync` / `removeStorageSync`**
- ❌ 不设存储持久化，config.js 为唯一 URL 来源
- ❌ 不使用 Vue DOM 渲染悬浮按钮
- ✅ 纯 URL 二维码格式（不支持自定义协议）
- ✅ 扫码后必须通过 `/health` 身份验证才能加载（安全硬限制，含认证错误的兼容）

## 测试矩阵

| # | 场景 | 预期 |
|---|------|------|
| 1 | 扫描有效 DeerFlow URL（末尾有斜杠） | 去掉斜杠后验证通过，加载成功 |
| 2 | 扫描纯 IP（无协议前缀） | 自动补全 http://，绑定成功 |
| 3 | 扫描公网 URL | /health 验证失败，提示非 DeerFlow 服务器 |
| 4 | 扫描无效内容（纯文本） | 提示「二维码内容无效」 |
| 5 | 扫描含空格/中文的 URL | 提示「二维码内容无效」 |
| 6 | 扫描非 http/https 协议 | 提示「二维码内容无效」 |
| 7 | 用户拒绝相机权限 | toast 提示需要相机权限 |
| 8 | 扫码过程中取消/返回 | 无异常，回到原界面 |
| 9 | 扫码验证失败 | 打开配置面板，显示完整错误信息和日志按钮 |
| 10 | 重复点击扫码 | toast "扫码正在进行中..."，不会重复调用 |
