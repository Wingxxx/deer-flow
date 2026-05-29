# DeerFlow 内网 App 入口 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个极简的 uni-app 项目，唯一的页面是一个 WebView 加载 `http://192.168.1.56:2026/`，打包为 iOS/Android App。

**架构:** 单页面 WebView 容器 App，无任何业务逻辑。用户通过 HBuilderX 可视化创建项目后，替换核心代码文件即可。

**技术栈:** uni-app（Vue 3）+ HBuilderX 云打包

---

### Task 1: 在 HBuilderX 中创建 uni-app 项目

**说明:** 此步骤由用户在 HBuilderX 中手动操作，AI 提供操作指引。

- [ ] **Step 1: 打开 HBuilderX 并新建项目**

  用户在 HBuilderX 中操作：
  1. 点击 `文件 → 新建 → 项目`
  2. 选择 `uni-app` 类型（注意不是 uni-app CLI）
  3. 输入项目名：`DeerFlowApp`
  4. 模板选择：`默认模板`
  5. 确定创建

- [ ] **Step 2: 确认项目目录创建成功**

  项目创建后，在文件系统中确认以下结构已存在：
  ```
  /home/wing/wing/emto/2026/2026.5/uni-app/DeerFlowApp/
  ```

---

### Task 2: 写入核心 WebView 页面

**说明:** 这是整个 App 唯一需要手写的页面文件

**Files:**
- Modify: `DeerFlowApp/pages/index/index.vue`（替换整个文件）

- [ ] **Step 1: 写入 index.vue**

  将以下内容写入 `DeerFlowApp/pages/index/index.vue`：

  ```vue
  <template>
    <web-view src="http://192.168.1.56:2026/" @title="onTitle"></web-view>
  </template>

  <script>
  export default {
    methods: {
      onTitle(e) {
        uni.setNavigationBarTitle({ title: e.title });
      }
    }
  }
  </script>
  ```

- [ ] **Step 2: 验证 pages.json 首页配置**

  读取 `DeerFlowApp/pages.json`，确认内容正确。如果不存在，创建并写入以下内容：

  ```json
  {
    "pages": [
      {
        "path": "pages/index/index",
        "style": {
          "navigationBarTitleText": "DeerFlow"
        }
      }
    ],
    "globalStyle": {
      "navigationBarTextStyle": "black",
      "navigationBarTitleText": "DeerFlow",
      "navigationBarBackgroundColor": "#ffffff",
      "backgroundColor": "#ffffff"
    }
  }
  ```

---

### Task 3: 配置 HTTP 明文访问（最关键步骤）

**说明:** Android 9+ 和 iOS 默认禁止 HTTP 明文加载。不做此配置 App 打开会白屏。

**Files:**
- Modify: `DeerFlowApp/manifest.json`

- [ ] **Step 1: 读取现有 manifest.json**

  读取 HBuilderX 生成的 `DeerFlowApp/manifest.json`，了解其默认结构。

- [ ] **Step 2: 写入完整的 manifest.json**

  将以下内容写入 `DeerFlowApp/manifest.json`：

  ```json
  {
    "name": "DeerFlow",
    "appid": "__UNI__XXXXXXX",
    "description": "DeerFlow 内网入口",
    "versionName": "1.0.0",
    "versionCode": "100",
    "app-plus": {
      "distribute": {
        "android": {
          "manifestPlugins": {
            "usesCleartextTraffic": true
          }
        },
        "ios": {
          "plistcmds": [
            "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true"
          ]
        }
      }
    },
    "quickapp": {},
    "vueVersion": "3"
  }
  ```

  > **注意:** `appid` 字段保留 HBuilderX 生成的原始值，不要修改。上述配置合并到现有 manifest.json 中，不要删除 HBuilderX 自动生成的其他字段。

- [ ] **Step 3: 验证 JSON 格式**

  用验证工具确认 `manifest.json` 的 JSON 格式正确。

---

### Task 4: 配置 App 图标

**说明:** 用户准备图标并配置

- [ ] **Step 1: 准备图标文件**

  用户准备一张 **1024x1024 像素** 的 PNG 图标（DeerFlow 风格），保存为 `DeerFlowApp/static/icon.png`。

- [ ] **Step 2: HBuilderX 中配置图标**

  用户在 HBuilderX 中操作：
  1. 打开 `manifest.json` → 点击 `App 图标配置`
  2. 上传 `static/icon.png`
  3. HBuilderX 自动生成所有平台适配尺寸

---

### Task 5: 真机调试验证

**说明:** 在真机上验证 WebView 能正常加载 DeerFlow

- [ ] **Step 1: Android 真机调试**

  用户操作：
  1. 手机开启 **开发者模式** 和 **USB 调试**
  2. USB 连接电脑
  3. HBuilderX 中点击 `运行 → 运行到手机或模拟器 → Android`
  4. 等待安装调试基座
  5. 确认 App 启动后自动加载 DeerFlow

- [ ] **Step 2: 验证核心功能**

  - App 启动后显示 DeerFlow 页面（非白屏）
  - 页面交互正常（登录、对话等）
  - 导航栏标题随页面切换同步更新

---

### Task 6: Android 云打包

**Files:** 无代码修改，纯打包操作

- [ ] **Step 1: 执行 Android 云打包**

  用户操作：
  1. HBuilderX 中：`发行 → 原生App-云打包`
  2. 包名：`com.deerflow.app`
  3. Android 打包类型：`Android（apk）`
  4. 证书：使用 **DCloud 默认证书**
  5. 点击 **打包**
  6. 等待云端编译完成（3-5 分钟）

- [ ] **Step 2: 下载并验证 .apk**

  下载生成的 `.apk` 文件，在真机上安装测试，确认一切正常。

---

### Task 7: iOS 云打包（可选）

**说明:** 需要有效的 Apple 开发者账号（$99/年）。如不具备条件，跳过此步骤，用户用微信扫码兜底。

**Files:** 无代码修改，纯打包操作

- [ ] **Step 1: 准备 iOS 证书**

  用户从 Apple Developer Center 下载：
  - `.p12` 证书文件（含私钥）
  - `.mobileprovision` 描述文件

- [ ] **Step 2: 执行 iOS 云打包**

  用户操作：
  1. HBuilderX 中：`发行 → 原生App-云打包`
  2. 选择 **iOS 打包**
  3. 上传 `.p12` 证书和 `.mobileprovision` 描述文件
  4. 点击 **打包**
  5. 下载生成的 `.ipa`

---

### Task 8: 分发部署

- [ ] **Step 1: Android 分发**

  两种方式：
  - **扫码安装**：将 `.apk` 上传到内网 HTTP 服务器，生成二维码
  - **文件分享**：通过微信文件传输发送 `.apk`

- [ ] **Step 2: 微信群配合推广**

  在微信群同时发送：
  1. DeerFlow 网页访问二维码（微信扫码直接可用）
  2. `.apk` 安装包文件（想装 App 的用户使用）
  3. 简短使用说明（需连接内网 WiFi）
