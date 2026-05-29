# DeerFlow 内网 App 入口 - uni-app WebView 壳实施指南

> **本指南写给 uni-app 项目的 AI Agent 阅读**。在新建的 uni-app 项目中，AI Agent 按以下步骤实施即可完成 DeerFlow 内网 App 壳的开发和部署。

---

## 〇、任务概述

**目标**：创建一个极简的 uni-app 项目，唯一的页面是一个 WebView，加载 `http://192.168.1.56:2026/`，打包为 iOS/Android App，让用户通过独立 App 图标访问内网的 DeerFlow。

**技术栈**：uni-app（Vue 3 + HBuilderX 云打包）

**关键约束**：
- 纯内网 HTTP，无 HTTPS
- 需要 Android 和 iOS 双端
- App 不需要任何业务逻辑，只做 WebView 容器
- DeerFlow 页面自带登录和所有交互

---

## 一、开发环境准备

### 1.1 安装 HBuilderX

告知用户前往 https://www.dcloud.io/hbuilderx.html 下载 HBuilderX（App 开发版）。安装后打开。

### 1.2 新建 uni-app 项目

在 HBuilderX 中操作：
1. 点击 `文件 → 新建 → 项目`
2. 选择 `uni-app` 类型
3. 输入项目名：`DeerFlowApp`
4. 模板选择：`默认模板`
5. 确定创建

> **注意**：创建完成后不要用 `vue-cli` 或命令行创建，HBuilderX 可视化创建最方便后续云打包。

---

## 二、核心代码编写

### 2.1 首页 WebView 组件

整个 App 只有一个核心页面，修改 `pages/index/index.vue`：

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

**代码说明**：
- `<web-view>` 组件是 uni-app 提供的原生 WebView 容器，直接加载 DeerFlow 页面
- `@title` 事件监听网页标题变化，自动同步到 App 原生导航栏
- 这 13 行代码就是整个 App 的全部业务逻辑

### 2.2 配置首页为启动页

检查 `pages.json`，确保首页配置正确：

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

## 三、HTTP 明文配置（最关键的一步）

由于 DeerFlow 跑在纯 HTTP 上，Android 9+ 和 iOS 默认禁止 HTTP 明文加载。**不做这一步 App 会白屏**。

### 3.1 Android 配置

打开 `manifest.json`，切换到 **源码视图**，在 `app-plus` → `distribute` → `android` 中添加：

```json
"plus": {
  "distribute": {
    "android": {
      "manifestPlugins": {
        "usesCleartextTraffic": true
      }
    }
  }
}
```

**如果使用可视化界面配置**：
1. 打开 `manifest.json` → 点击 `App 模块配置`
2. 找到 `Android X5 WebView`（不用勾选）
3. 切换到 **源码视图**
4. 找到 `"app-plus"` 节点，将上述 JSON 插入

### 3.2 iOS 配置

在 `manifest.json` 源码视图的 `app-plus` → `distribute` → `ios` 中添加：

```json
"plus": {
  "distribute": {
    "ios": {
      "plistcmds": [
        "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true"
      ]
    }
  }
}
```

### 3.3 完整的 manifest.json 配置

以下是 `manifest.json` 中 `app-plus` 节点的完整内容参考：

```json
{
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
  }
}
```

---

## 四、App 图标配置

### 4.1 准备图标

准备一张 **1024x1024 像素** 的 PNG 图标（鹿角/Deer 主题，或者用 DeerFlow logo）。命名为 `icon.png`。

### 4.2 配置图标

在 `manifest.json` 的可视化界面中：
1. 点击 **App 图标配置**
2. 上传准备好的 `icon.png`
3. HBuilderX 会自动生成所有尺寸的适配图标（Android 的 mipmap 各目录、iOS 的各规格）

---

## 五、真机调试

### 5.1 Android 真机调试

1. 手机开启 **开发者模式** 和 **USB 调试**
2. USB 连接电脑
3. HBuilderX 中点击：`运行 → 运行到手机或模拟器 → Android`
4. 等待 HBuilderX 安装调试基座到手机
5. 手机上确认安装，App 启动后应自动加载 DeerFlow

### 5.2 iOS 真机调试

iOS 真机调试需要：
1. Mac 电脑 + Xcode
2. Apple 开发者账号
3. 如果条件不具备，可以直接跳到云打包阶段，用云打包生成的 `ipa` 通过 TestFlight 分发

---

## 六、云打包

### 6.1 Android 云打包

1. HBuilderX 中：`发行 → 原生App-云打包`
2. 包名格式：`com.deerflow.app`（可自定义）
3. Android 打包类型选择：`Android（apk）`
4. 证书选择：**使用 DCloud 默认证书**（免费，测试用足够）
   - 如果要正式分发，可以生成自己的 keystore 证书
5. 点击 **打包**
6. 等待云端编译完成（通常 3-5 分钟）
7. 下载生成的 `.apk` 文件

### 6.2 iOS 云打包

> ⚠️ **必要条件**：需要有效的 Apple 开发者账号（$99/年）

1. HBuilderX 中：`发行 → 原生App-云打包`
2. 选择 **iOS 打包**
3. 上传从 Apple Developer Center 下载的：
   - `.p12` 证书文件（含私钥）
   - `.mobileprovision` 描述文件
4. 点击 **打包**
5. 下载生成的 `.ipa` 文件

**如果没有 Apple 开发者账号**：
- 可以先只发布 Android 版
- iOS 用户暂时用微信扫码或 Safari 打开

---

## 七、分发安装

### 7.1 Android 分发

两种方式：

**方式一：二维码扫码安装（推荐）**
1. 将 `.apk` 上传到 DeerFlow 服务器静态目录，或内网任意 HTTP 服务器
2. 生成下载链接的二维码：`http://192.168.1.56/apk/DeerFlowApp.apk`
3. 将二维码打印张贴，或发到微信群

**方式二：直接发送文件**
1. 将 `.apk` 直接通过微信文件传输发送给用户
2. 用户手机上点击文件 → 安装（需允许未知来源安装）

### 7.2 iOS 分发

使用 **TestFlight**：
1. 登录 App Store Connect
2. 上传 `.ipa`
3. 添加内部测试员（最多 100 人）
4. 测试员通过 TestFlight App 下载安装

### 7.3 用户首次打开注意事项

用户首次打开 App 时：
1. Android 会提示"允许访问设备上的媒体和文件"——**拒绝即可**（App 不需要此权限）
2. 加载 DeerFlow 需要**连接内网 WiFi**（校园网或单位内网）
3. 如果网络不通，App 会显示"无法加载网页"——检查 WiFi 连接状态

---

## 八、进阶优化（可选）

以下优化项按优先级排列，可根据需要决定是否实施：

### 8.1 加载进度条

给 WebView 添加加载进度提示，改善白屏等待体验。

修改 `pages/index/index.vue`：

```vue
<template>
  <view style="position: relative; height: 100%;">
    <progress 
      v-if="loadingProgress < 100" 
      :percent="loadingProgress" 
      stroke-width="2" 
      activeColor="#4CAF50"
      style="position: fixed; top: 0; left: 0; right: 0; z-index: 999;"
    />
    <web-view 
      src="http://192.168.1.56:2026/" 
      @title="onTitle"
      @progress="onProgress"
    ></web-view>
  </view>
</template>

<script>
export default {
  data() {
    return {
      loadingProgress: 0
    }
  },
  methods: {
    onTitle(e) {
      uni.setNavigationBarTitle({ title: e.title });
    },
    onProgress(e) {
      this.loadingProgress = e.detail.progress;
    }
  }
}
</script>
```

### 8.2 错误页面处理

如果 DeerFlow 服务器不可达，显示友好的错误提示而非白屏。

### 8.3 自定义导航栏

替换 WebView 自带的导航栏为 uni-app 原生导航栏：
- 隐藏 WebView 的导航栏（在 `<web-view>` 上加 `@navigationbar` 事件）
- 用 uni-app 原生导航栏显示标题、返回按钮、刷新按钮

### 8.4 下拉刷新

```json
// pages.json 中对应页面的 style
{
  "path": "pages/index/index",
  "style": {
    "enablePullDownRefresh": true
  }
}
```

配合 WebView 的 `@pullrefresh` 事件实现下拉刷新 DeerFlow 页面。

---

## 九、与微信扫码方案的配合策略

**记住：App 壳和微信扫码不冲突，可以同时使用。**

| 场景 | 用户操作 | 说明 |
|------|---------|------|
| 没有安装 App | 打开微信 → 扫内网二维码 → 微信内置浏览器打开 DeerFlow | **无需任何安装** |
| 已安装 App | 点击手机桌面 DeerFlow 图标 → App 打开 → 自动加载 DeerFlow | **独立入口体验** |
| 桌面端 | 浏览器直接打开 `http://192.168.1.56:2026/` | 原有方式不变 |

**建议初期推荐策略**：
1. 微信群发 DeerFlow 二维码 + 简短使用说明
2. 同时分享 `.apk` 文件到群文件
3. 用户按需选择：扫码即用 vs 安装 App

---

## 十、常见问题

### Q1: App 打开后白屏
- Android：确认 `usesCleartextTraffic` 已配置
- iOS：确认 `NSAllowsArbitraryLoads` 已配置
- 确认手机已连接到内网 WiFi
- 在手机上用 Chrome/Safari 手动打开 `http://192.168.1.56:2026/` 验证可达

### Q2: Android 云打包失败
- 检查项目名称是否含特殊字符
- 检查 `manifest.json` 格式是否正确（JSON 格式错误会导致打包失败）
- 尝试使用 DCloud 默认证书打包

### Q3: iOS 云打包提示证书问题
- 确认 `.p12` 和 `.mobileprovision` 的 App ID 匹配
- 描述文件中需包含云打包设备的 UDID（测试阶段）
- 确认证书未过期

### Q4: 更新 DeerFlow 前端后 App 需要重新打包吗？
**不需要。** App 只是一个壳，每次打开都是从 `http://192.168.1.56:2026/` 实时加载内容。更新 DeerFlow 前端后，App 用户下次打开自动看到最新版本。

### Q5: 包名可以修改吗？
可以，在 `manifest.json` 中修改——但注意 **一旦发布，包名不要轻易修改**，否则用户升级时会识别为两个不同的 App。

---

## 十一、实施检查清单

| # | 事项 | 完成 |
|:-:|------|:---:|
| 1 | HBuilderX 已安装 | ☐ |
| 2 | uni-app 项目已创建 | ☐ |
| 3 | `pages/index/index.vue` WebView 代码已编写 | ☐ |
| 4 | `manifest.json` Android `usesCleartextTraffic` 已配置 | ☐ |
| 5 | `manifest.json` iOS `NSAllowsArbitraryLoads` 已配置 | ☐ |
| 6 | App 图标已配置 | ☐ |
| 7 | 真机调试通过（WebView 正常加载 DeerFlow） | ☐ |
| 8 | Android 云打包成功 | ☐ |
| 9 | iOS 云打包成功（如需要） | ☐ |
| 10 | `.apk` 已分发，用户安装后可正常使用 | ☐ |
