# DeerFlow App 扫码绑定服务器地址 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 URL 配置功能基础上，新增扫二维码直接绑定服务器地址的功能，支持配置浮层和错误覆盖层双入口。

**架构:** 仅修改 `pages/index/index.vue` 一个文件，新增 `scanQRCode()` 和 `processScannedUrl()` 两个方法，复用现有的 `/health` 验证和 `saveAndLoad()` 存储逻辑。配置面板增加隐藏的 Debug 调试入口（长按标题3秒触发）。

**依赖:** uni-app 内置 `uni.scanCode()` API，无需额外插件。`manifest.json` 已包含 CAMERA 权限。

---

### Task 1: 新增 scanQRCode 方法 — 调用系统相机扫码

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

- [ ] **Step 1: 在 data() 中新增 `scanning` 状态变量**

  在 `data()` 的 `return` 对象中找到 `retryTimer: null`，在其下方新增 `scanning` 字段：

  ```js
  retryTimer: null,
  scanning: false       // ← 新增
  ```

- [ ] **Step 2: 在 methods 中新增 `scanQRCode()` 方法**

  在 `methods` 中的 `onUrlInput` 方法之前插入 `scanQRCode`：

  ```js
  scanQRCode() {
    var self = this
    if (self.scanning) return
    self.scanning = true

    uni.scanCode({
      scanType: ['qrCode'],
      success: function(res) {
        self.scanning = false
        var result = res.result
        if (!result || result.length === 0) {
          plus.nativeUI.toast('二维码内容无效，请扫描 DeerFlow 服务器地址')
          return
        }
        self.processScannedUrl(result)
      },
      fail: function(err) {
        self.scanning = false
        var msg = err.errMsg || ''
        if (msg.indexOf('cancel') !== -1) {
          return
        }
        if (msg.indexOf('permission') !== -1) {
          plus.nativeUI.toast('需要相机权限才能扫码，请在系统设置中开启')
        } else {
          plus.nativeUI.toast('扫码失败: ' + msg)
        }
      }
    })
  },
  ```

- [ ] **Step 3: 在 methods 中新增 `processScannedUrl(url)` 方法**

  在 `scanQRCode` 方法之后插入 `processScannedUrl`：

  ```js
  processScannedUrl(url) {
    if (url.indexOf(' ') !== -1 || /[\u4e00-\u9fa5]/.test(url)) {
      plus.nativeUI.toast('二维码内容无效，请扫描 DeerFlow 服务器地址')
      return
    }

    if (/^https?:\/\//i.test(url)) {
    } else if (url.indexOf('://') !== -1) {
      plus.nativeUI.toast('不支持的协议类型，请扫描 HTTP 服务器地址')
      return
    } else {
      url = 'http://' + url
    }

    var withProtocol = url
    var publicDomain = false
    try {
      var hostname = url.replace(/^https?:\/\//, '').split('/')[0].split(':')[0]
      if (isPublicDomain(url)) {
        publicDomain = true
      }
    } catch (e) {}

    if (publicDomain) {
      plus.nativeUI.toast('您扫描的是一个公共网站地址，DeerFlow 服务器通常位于内网')
    }

    var self = this
    self.testResult = { type: 'loading', message: '正在验证服务器身份...' }

    uni.request({
      url: url + '/health',
      method: 'GET',
      timeout: 5000,
      success: function(res) {
        if (res.data && res.data.service === 'deer-flow-gateway' && res.data.status === 'healthy') {
          self.inputUrl = url
          self.autoCompleteProtocol()

          if (url !== appConfig.serverUrl) {
            uni.setStorageSync('df_custom_url', url)
          } else {
            uni.removeStorageSync('df_custom_url')
          }

          self.webviewSrc = url
          self.currentUrl = url
          self.showConfigPanel = false
          self.showErrorOverlay = false
          self.showWebView = true
          self.retryCount = 0
          if (self.retryTimer) {
            clearTimeout(self.retryTimer)
            self.retryTimer = null
          }

          plus.nativeUI.toast('扫码绑定成功: ' + url)
        } else {
          self.testResult = { type: 'fail', message: '⛔ 该服务器不是 DeerFlow 网关，禁止使用' }
          if (self.showConfigPanel === false) {
            self.openConfigPanel()
            self.inputUrl = url
          }
        }
      },
      fail: function(err) {
        var msg = err.errMsg || ''
        if (msg.indexOf('timeout') !== -1) {
          self.testResult = { type: 'fail', message: '❌ 连接超时（5秒），请检查地址或网络' }
        } else {
          self.testResult = { type: 'fail', message: '❌ 无法连接，请检查地址或网络' }
        }
        if (self.showConfigPanel === false) {
          self.openConfigPanel()
          self.inputUrl = url
        }
      }
    })
  },
  ```

---

### Task 2: 修改模板 — 错误覆盖层增加扫码按钮

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`（template 部分）

- [ ] **Step 1: 在错误覆盖层的按钮列表最上方插入扫码按钮**

  找到错误覆盖层的这段代码：
  ```html
  <view class="error-actions">
    <view class="btn btn-primary" @click="openConfigPanel">✏️ 修改服务器地址</view>
    <view class="btn btn-secondary" @click="retryLoad">🔄 检查网络并重试</view>
  </view>
  ```

  改为：
  ```html
  <view class="error-actions">
    <view class="btn btn-scan" @click="scanQRCode">📷 扫码自动绑定</view>
    <view class="btn btn-primary" @click="openConfigPanel">✏️ 修改服务器地址</view>
    <view class="btn btn-secondary" @click="retryLoad">🔄 检查网络并重试</view>
  </view>
  ```

---

### Task 3: 修改模板 — 配置浮层增加扫码按钮 + Debug 调试入口

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`（template 部分）

- [ ] **Step 1: 在「测试连接」和测试结果之间插入扫码按钮**

  找到配置浮层中测试结果的代码：
  ```html
  <view class="form-group">
    <view class="btn btn-outline" @click="testConnection">🔌 测试连接</view>
  </view>

  <view v-if="testResult.message" class="test-result" :class="'result-' + testResult.type">
    <view>{{ testResult.message }}</view>
  </view>
  ```

  改为：
  ```html
  <view class="form-group">
    <view class="btn btn-outline" @click="testConnection">🔌 测试连接</view>
  </view>

  <view class="form-group">
    <view class="btn btn-scan" @click="scanQRCode">📷 扫码自动绑定</view>
  </view>

  <view v-if="testResult.message" class="test-result" :class="'result-' + testResult.type">
    <view>{{ testResult.message }}</view>
  </view>

  <!-- Debug 调试入口（长按标题触发） -->
  <view v-if="showDebugPanel" class="debug-section">
    <view class="debug-title">🧪 调试模式 — 模拟扫码测试</view>
    <input class="form-input debug-input" type="text" :value="debugInput" @input="onDebugInput" placeholder="输入模拟扫码内容" />
    <view class="form-group">
      <view class="btn btn-outline-debug" @click="debugScan">▶ 模拟扫码</view>
    </view>
  </view>
  ```

- [ ] **Step 2: 在 data() 中新增 debug 相关变量**

  在 `data()` 的 `scanning: false` 下方新增：
  ```js
  scanning: false,
  showDebugPanel: false,
  debugInput: ''
  ```

- [ ] **Step 3: 修改 `config-title` 增加长按事件**

  找到配置面板标题：
  ```html
  <view class="config-title">服务器设置</view>
  ```

  改为：
  ```html
  <view class="config-title" @longpress="toggleDebug">服务器设置</view>
  ```

- [ ] **Step 4: 在 methods 中新增 debug 相关方法**

  在 `processScannedUrl` 方法之后插入：
  ```js
  toggleDebug() {
    this.showDebugPanel = !this.showDebugPanel
    this.debugInput = ''
  },

  onDebugInput(e) {
    this.debugInput = e.detail.value
  },

  debugScan() {
    var val = this.debugInput
    if (!val || val.length === 0) {
      plus.nativeUI.toast('请输入模拟扫码内容')
      return
    }
    this.processScannedUrl(val)
  },
  ```

---

### Task 4: 新增样式 — 扫码按钮和 Debug 区域样式

**Files:**
- Modify: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`（style 部分）

- [ ] **Step 1: 在样式末尾新增扫码按钮和 Debug 样式**

  在 `.settings-trigger` 样式块之后追加：

  ```css
  .btn-scan {
    text-align: center;
    padding: 14px;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 500;
    background: #e8f5e9;
    color: #2e7d32;
    border: 1.5px solid #a5d6a7;
    box-sizing: border-box;
  }

  .debug-section {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px dashed #e0e0e0;
  }
  .debug-title {
    font-size: 13px;
    font-weight: 500;
    color: #9e9e9e;
    margin-bottom: 10px;
  }
  .debug-input {
    border-color: #e0e0e0;
    background: #fafafa;
  }
  .btn-outline-debug {
    text-align: center;
    padding: 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    background: transparent;
    color: #9e9e9e;
    border: 1.5px dashed #e0e0e0;
    box-sizing: border-box;
  }
  ```

---

### Task 5: 开发环境调试验证

**Files:** 无代码修改

- [ ] **Step 1: 用 HBuilderX 运行到 Android 真机**

  用户操作：
  1. 手机开启开发者模式 + USB 调试
  2. USB 连接电脑
  3. HBuilderX 中：`运行 → 运行到手机或模拟器 → Android`

- [ ] **Step 2: 测试 Debug 模拟扫码功能**

  用户操作：
  1. App 启动后点击 ⚙ 按钮
  2. **长按「服务器设置」标题 3 秒** → 出现 Debug 区域
  3. 在 Debug 输入框中逐条输入以下内容，每次点击「▶ 模拟扫码」

  | # | 输入内容 | 预期行为 |
  |---|---------|---------|
  | 1 | `http://192.168.1.56:2026/` | toast "扫码绑定成功" + WebView 加载 |
  | 2 | `192.168.1.56:2026` | 自动补全 http://，绑定成功 |
  | 3 | `hello` | toast "二维码内容无效" |
  | 4 | `http://192.168.1.56:2026/ 空格` | toast "二维码内容无效" |
  | 5 | `中文地址` | toast "二维码内容无效" |
  | 6 | `ftp://192.168.1.56` | toast "不支持的协议类型" |
  | 7 | 清空后点击「▶ 模拟扫码」 | toast "请输入模拟扫码内容" |

- [ ] **Step 3: 恢复默认值后重测**

  点击「恢复默认地址」→ 回到 ⚙ 点击 → Debug 输入 `http://192.168.1.56:2026/` → 模拟扫码 → 应绑定成功

- [ ] **Step 4: 确认无报错**

  在 HBuilderX 的控制台（Console）中查看：
  - 无明显红色错误日志
  - 所有 toast 提示正常显示
  - 扫码/验证/保存/加载各环节无 JS 异常
