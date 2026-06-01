# DeerFlowApp UX Essentials 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 DeerFlowApp 补充四项基本的用户体验要素：启动加载状态、隐藏导航栏、App Icon 配置、禁止 WebView 缩放。

**Architecture:** 所有改动集中在 `index.vue`（加/改/删模板、脚本和样式）、`pages.json`（一行配置）、`manifest.json`（图标路径配置），不新增文件、不引入依赖。

**Tech Stack:** uni-app (Vue 3) + HBuilderX 云打包

---

### Task 1: pages.json — 隐藏原生导航栏

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages.json:10`

- [ ] **Step 1: 添加 `navigationStyle: "custom"`**

定位到第 10 行的 `"navigationBarTitleText": "DeerFlow"`，在同级对象中添加 `"navigationStyle": "custom"`：

```json
{
  "pages": [
    {
      "path": "pages/index/index",
      "style": {
        "navigationBarTitleText": "DeerFlow",
        "navigationStyle": "custom"
      }
    }
  ],
  ...
```

---

### Task 2: index.vue template — 增加加载画面 + 移除 @title + 安全区域适配

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

- [ ] **Step 1: WebView 容器前增加加载画面模板**

在 `<template>` 中 `<web-view>` 容器的前面，增加加载画面的条件渲染段：

```html
<view v-if="isLoading" class="loading-splash">
  <view class="loading-spinner"></view>
  <view class="loading-text">正在连接 DeerFlow 服务器...</view>
</view>
```

- [ ] **Step 2: 从 `<web-view>` 标签移除 `@title` 事件绑定**

改动前：
```html
<web-view v-show="showWebView" :src="webviewSrc" @title="onTitle" @load="onWebViewLoad" @error="onWebViewError"></web-view>
```

改动后：
```html
<web-view v-show="showWebView" :src="webviewSrc" @load="onWebViewLoad" @error="onWebViewError"></web-view>
```

- [ ] **Step 3: WebView 容器增加安全区域 padding**

给 `.webview-container` 添加 `padding-top` 样式（在 style 中处理），并使用 CSS 变量 `env(safe-area-inset-top)`：

修改 `.webview-container` 样式：

```css
.webview-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  padding-top: constant(safe-area-inset-top);
  padding-top: env(safe-area-inset-top);
}
```

---

### Task 3: index.vue script — 加载逻辑 + 删除 onTitle + 缩放限制注入

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

- [ ] **Step 1: data 中增加 `isLoading` 属性**

```js
data() {
  return {
    webviewSrc: '',
    isLoading: true,       // 新增
    showWebView: true,
    showErrorOverlay: false,
    ...
  }
}
```

- [ ] **Step 2: 修改 `onShow`，改为先显示加载画面，再检查网络和 `/health`**

将原来直接设置 `webviewSrc` 的逻辑替换为启动加载流程：

```js
onShow() {
  var configUrl = appConfig.serverUrl
  if (configUrl !== this.webviewSrc) {
    this.webviewSrc = configUrl
    this.currentUrl = configUrl
    this.showWebView = false
    this.showErrorOverlay = false
    this.isLoading = true
  }

  this.createFloatBtn()
  if (this.showConfigPanel) {
    this.destroyFloatBtn()
  }

  if (!this._networkListenerRegistered) {
    this._networkListenerRegistered = true
    uni.onNetworkStatusChange(function(res) {
      if (res.isConnected && this.showErrorOverlay) {
        plus.nativeUI.toast('网络已恢复，点击重试加载')
      }
    }.bind(this))
  }

  this.checkServerConnection(configUrl)
},
```

- [ ] **Step 3: 新增 `checkServerConnection` 方法**

```js
checkServerConnection(url) {
  var self = this
  var healthUrl = url.replace(/\/+$/, '') + '/health'

  // 并行检查网络 + health
  uni.getNetworkType({
    success: function(netRes) {
      var noNetwork = (netRes.networkType === 'none')
      if (noNetwork) {
        self.isLoading = false
        self.showErrorOverlay = true
        self.showWebView = false
        self.webViewError = '📶 设备未连接网络，请检查 Wi-Fi 或移动数据'
        self.currentUrl = url
        return
      }

      // 有网络，检查 /health
      uni.request({
        url: healthUrl,
        method: 'GET',
        timeout: 5000,
        success: function(res) {
          self.isLoading = false
          var isValid = false
          if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') isValid = true
          if (res.data && res.data.detail && res.data.detail.code === 'not_authenticated') isValid = true
          if (res.statusCode === 401 || res.statusCode === 403) isValid = true

          if (isValid) {
            self.showWebView = true
            self.showErrorOverlay = false
            self.webViewError = ''
          } else {
            self.showWebView = false
            self.showErrorOverlay = true
            self.webViewError = '🔌 无法连接服务器（服务器地址错误或 DeerFlow 服务未启动）'
            self.currentUrl = url
          }
        },
        fail: function(err) {
          self.isLoading = false
          self.showWebView = false
          self.showErrorOverlay = true
          var msg = err.errMsg || ''
          if (msg.indexOf('timeout') !== -1) {
            self.webViewError = '🔌 连接超时（5秒），请检查服务器地址或网络'
          } else {
            self.webViewError = '🔌 无法连接服务器（' + msg + '）'
          }
          self.currentUrl = url
        }
      })
    },
    fail: function() {
      // getNetworkType 失败，直接尝试 health
      self.isLoading = false
      self.showWebView = true
    }
  })
}
```

- [ ] **Step 4: 删除 `onTitle` 方法**

移除整个 `onTitle` 方法：

```js
// 整段删除
onTitle(e) {
  uni.setNavigationBarTitle({ title: e.title })
},
```

- [ ] **Step 5: 在 `injectFix` 中添加缩放限制**

在 `injectFix` 函数的 injectedFn 内，在已有的 CSS 注入内容中增加缩放限制。

找到 `cs.textContent = '*{pointer-events...'` 这一行，修改为：

```js
cs.textContent = '*{pointer-events:auto!important;-webkit-text-size-adjust:none!important}' +
  'html{touch-action:pan-y;-ms-touch-action:pan-y}' +
  'input,textarea,select,button,a{-webkit-user-select:text!important;user-select:text!important;touch-action:manipulation!important}'
```

并在 `injectedFn` 中增加 viewport meta 注入：

在 `var D = document` 之后，`if (D.__ok) return` 之前或之后添加：

```js
var meta = D.querySelector('meta[name=viewport]')
if (meta) {
  meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no'
} else {
  var m = D.createElement('meta')
  m.name = 'viewport'
  m.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no'
  D.head && D.head.appendChild(m)
}
```

---

### Task 4: index.vue style — 添加加载画面样式 + spinner 动画

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

- [ ] **Step 1: 在 style 末尾新增加载画面样式**

```css
.loading-splash {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 9997;
  opacity: 0;
  animation: loadingFadeIn 0.2s ease-out forwards;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid #e5e5ea;
  border-top-color: #007aff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

.loading-text {
  font-size: 14px;
  color: #86868b;
  text-align: center;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes loadingFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

---

### Task 5: CLAUDE.md 和 manifest.json — 文档同步 + 图标配置

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/manifest.json`
- Modify: `CLAUDE.md`

- [ ] **Step 1: manifest.json 配置图标路径**

在 `manifest.json` 的 `app-plus.distribute.android` 中添加 `icons` 字段：

```json
"android": {
  "manifestPlugins": {
    "usesCleartextTraffic": true
  },
  "icons": {
    "hdpi": "static/icons/android/icon-hdpi.png",
    "xhdpi": "static/icons/android/icon-xhdpi.png",
    "xxhdpi": "static/icons/android/icon-xxhdpi.png",
    "xxxhdpi": "static/icons/android/icon-xxxhdpi.png"
  },
  "permissions": [...]
}
```

在 `ios` 中添加：

```json
"ios": {
  "icons": {
    "appstore": "static/icons/ios/icon-1024.png"
  },
  "plistcmds": [...],
  "dSYMs": false
}
```

> **注意：** 图标文件需主子自行放入对应目录，云打包时会读取这些路径。

- [ ] **Step 2: 更新 CLAUDE.md 移除关于 URL 输入框的文档**

`CLAUDE.md` 中 "Server URL — 运行时配置（应用内修改）" 章节和 "交互流程" 表格中提到的「输入 URL（实时格式校验 + 内网检测）」「保存并加载」「恢复默认地址」等描述已与实际代码不符（配置面板无文本输入框，地址仅通过扫码设置），需同步移除这些不存在的功能描述。

---

### 验证

- [ ] **验证：各文件语法正确性**
  无运行测试环境，通过 IDE 诊断检查确保无语法错误。

- [ ] **验证：所有改动的文件内容完整、无残留占位符**
