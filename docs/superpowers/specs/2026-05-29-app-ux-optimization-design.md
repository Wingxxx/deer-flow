# DeerFlow App UX Optimization Design

**Date:** 2026-05-29
**Author:** WING
**Status:** ✅ Implemented — matched by `.trae/specs/ux-optimization-stress-test/`

## 1. Problem Statement

1. **白屏问题**：App 打开后 WebView 加载服务器 URL，如果不在局域网或网络不可达，长时间等待后全白屏，无任何提示。
2. **URL 配置简陋**：当前使用 `plus.nativeUI.prompt` 原生对话框输入 URL，无格式校验、无连接测试、无身份验证。
3. **防第三方网站**：用户可能误输入公网地址（如 `www.baidu.com`），WebView 直接加载第三方网站，存在安全和体验问题。

## 2. Solution Overview

双页面架构 + 三层 URL 安全防护：

- **页面一**：错误提示页（替换白屏）
- **页面二**：URL 配置页（升级版原生对话框）
- **三层防护**：格式校验 → 内网提示 → Health API 身份验证

## 3. Architecture

### 3.1 Page Structure

```
pages/index/index.vue (现有页面，改造)
├── <web-view> (条件渲染)
│   ├── 加载成功 → 正常显示
│   └── 加载失败 → 隐藏，显示错误提示页
└── 错误提示页 (原生 UI 覆盖层)
    ├── ⚠️ 图标 + "无法连接服务器"
    ├── 当前 URL 显示
    ├── "✏️ 修改服务器地址" → 弹出 URL 配置对话框
    └── "🔄 检查网络并重试" → 重新加载

URL 配置浮层 (替代现有 plus.nativeUI.prompt，使用 cover-view 自定义弹出层)
├── URL 输入框 (带格式校验 + 内网检测)
├── "🔌 测试连接" 按钮
├── 测试结果反馈区域 (成功/失败/身份验证)
├── "💾 保存并加载" 按钮
└── "↩️ 恢复默认地址" 按钮
```

### 3.2 Data Flow

```
App 启动
  → onShow() 读取本地存储 (df_server_url) 或 config.js 默认值
  → 设置 webviewSrc
  → WebView 开始加载

WebView 加载事件监听:
  ├── 成功 (onLoad 无错误)
  │   → 正常显示，隐藏错误覆盖层
  │
  └── 失败 (onError 或超时)
      → 隐藏 WebView，显示错误提示覆盖层
      → 用户操作:
          ├── "修改服务器地址" → 弹出 URL 配置浮层
          │   → 输入新 URL
          │   → "测试连接" → GET /health 验证
          │   → 通过 → 绿色 ✓ → 启用保存按钮
          │   → 不通过 → 红色 ⚠️ 非 DeerFlow 服务器，禁止保存
          │   → "保存并加载" → 持久化 + 重新加载
          │
          └── "检查网络并重试" → 重新加载 WebView

⚙ 悬浮按钮:
  点击 → 弹出 URL 配置浮层 (与上面同一个)
```

## 4. Component Details

### 4.1 错误提示覆盖层 (Error Overlay)

**触发条件：**
- WebView `onError` 事件触发
- WebView 加载超时（10秒无响应）

**UI 元素：**
- ⚠️ 红色圆形图标
- 标题：「无法连接服务器」
- 描述：「当前网络无法访问指定的服务器地址。请检查网络连接或修改服务器地址。」
- 当前 URL 卡片（灰色背景，显示具体地址）
- 「✏️ 修改服务器地址」蓝色主按钮
- 「🔄 检查网络并重试」次要按钮

**状态管理：**
```js
data() {
  return {
    webviewSrc: '',
    webviewReady: false,     // WebView DOM 是否就绪
    loadError: false,         // 是否加载失败
    showErrorOverlay: false,  // 是否显示错误覆盖层
  }
}
```

### 4.2 URL 配置浮层 (Config Panel)

取代现有的 `plus.nativeUI.prompt`，使用 `cover-view` 构建自定义弹出浮层。

**功能列表：**

| 功能 | 实现方式 |
|---|---|
| URL 输入 | 原生输入框，支持粘贴 |
| 格式校验 | 实时校验：必含 `http://` 或 `https://` 前缀 |
| 协议自动补全 | 如果用户输入 `192.168.1.56:2026`，自动补为 `http://192.168.1.56:2026/` |
| 内网检测 | 解析 hostname，判断是否为公网域名 |
| 连接测试 | 点击按钮 → `GET {serverUrl}/health` |
| 身份验证 | 检查响应 JSON：`service === "deer-flow-gateway"` 且 `status === "healthy"` |
| 保存 | `uni.setStorageSync('df_server_url', url)` |

**三层防护逻辑：**

```
用户输入 URL
  → Layer 1: 格式校验
      ├── 空值 → 禁用保存按钮，提示「请输入服务器地址」
      ├── 无协议 → 自动补全 http://
      └── 非法字符 → 提示「地址格式不正确」

  → Layer 2: 内网提示（非阻断）
      ├── 公网域名（baidu.com, google.com 等）→ 黄色提示
      ├── 内网 IP（192.168.x.x, 10.x.x.x, 127.x.x.x）→ 无提示
      └── 自定义域名 → 无提示

  → Layer 3: 连接测试（点击按钮触发）— 硬性条件，不通过则禁止保存
      ├── HTTP GET {serverUrl}/health
      │   ├── 成功 + JSON 匹配 → 绿色 ✓ → 「保存」按钮启用
      │   ├── 成功 + JSON 不匹配 → 红色 ⚠️ 「非 DeerFlow 服务器，保存已禁用」
      │   └── 网络错误 → 红色 ❌ 「无法连接，请检查地址或网络」
      └── 超时（5秒）→ 红色 ❌ 「连接超时」
```

### 4.3 Health API 身份验证

**请求：**
```
GET {serverUrl}/health
```

**验证逻辑：**
```js
async function verifyDeerFlowServer(url) {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)

    const response = await fetch(url + '/health', {
      signal: controller.signal,
      method: 'GET',
    })
    clearTimeout(timeout)

    if (!response.ok) return { verified: false, reason: 'HTTP ' + response.status }

    const data = await response.json()
    if (data.service === 'deer-flow-gateway' && data.status === 'healthy') {
      return { verified: true }
    } else {
      return { verified: false, reason: '非 DeerFlow 服务器 - 仅允许连接 deer-flow-gateway', data }
    }
  } catch (e) {
    return { verified: false, reason: e.name === 'AbortError' ? '连接超时' : e.message }
  }
}
```

**预期返回：**
```json
{"status":"healthy","service":"deer-flow-gateway"}
```

### 4.4 智能重试

WebView 加载失败后，不立即无限重试。使用指数退避策略：

| 重试次数 | 等待时间 |
|---|---|
| 第1次 | 2秒 |
| 第2次 | 4秒 |
| 第3次 | 8秒 |
| 第4次+ | 15秒（上限） |

每次重试前监听网络状态：
- 使用 `uni.onNetworkStatusChange` 监听网络变化
- 网络从断连恢复时 → 提示用户「网络已恢复，是否重试？」
- 用户手动点击「重试」时重置重试计数

## 5. Testing Strategy

### 5.1 Test Scenarios

| 场景 | 预期行为 |
|---|---|
| 正常启动，服务器可达 | WebView 正常加载，无覆盖层 |
| 启动时网络不可达 | 显示错误覆盖层 |
| 加载过程中断网 | 触发 onError，显示错误覆盖层 |
| 点击「修改服务器地址」 | 弹出 URL 配置浮层 |
| 输入合法 DeerFlow URL + 测试连接 | 绿色 ✓ 验证通过，保存按钮启用 |
| 输入第三方 URL（baidu.com）+ 测试连接 | 红色 ⚠️ 身份验证失败，保存按钮禁用 |
| 输入无法访问的 URL + 测试连接 | 红色 ❌ 无法连接，保存按钮禁用 |
| 点击「检查网络并重试」 | 重新加载 WebView |
| ⚙ 按钮点击 | 弹出 URL 配置浮层 |
| WebView 加载成功 | 隐藏错误覆盖层 |

### 5.2 状态矩阵

| webviewReady | loadError | showErrorOverlay | 用户看到 |
|---|---|---|---|
| false | false | false | 空白/加载中 |
| true | false | false | WebView 内容 |
| true | true | true | 错误覆盖层 |
| false | true | true | 错误覆盖层 |

## 6. Implementation Notes

- 所有新增逻辑在 `pages/index/index.vue` 中实现，无需新增页面路由
- URL 配置浮层使用 `cover-view` 自定义弹出层代替 `plus.nativeUI.prompt`（原生对话框无法承载输入框+按钮+结果反馈的复杂布局）
- Health 验证使用 `uni.request` 而非 `fetch`（uni-app 跨平台兼容性更好）
- 错误覆盖层和配置浮层均使用 `cover-view`（与 WebView 同层渲染）
- 项目配置文件 `config.js` 保持不变（编译时默认值）
- 不新增第三方依赖
