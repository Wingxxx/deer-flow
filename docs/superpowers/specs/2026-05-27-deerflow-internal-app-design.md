# DeerFlow 内网 App 入口 - 设计方案

## 概述

创建一个极简的 uni-app 项目，唯一的页面是一个 WebView，加载 `http://192.168.1.56:2026/`，打包为 iOS/Android App，让用户通过独立 App 图标访问内网的 DeerFlow。

## 技术栈

- **框架**: uni-app（Vue 3）
- **开发工具**: HBuilderX（App 开发版）
- **打包方式**: HBuilderX 云打包
- **证书**: Android 用 DCloud 默认证书，iOS 需 Apple 开发者账号

## 核心设计

### 项目结构

```
DeerFlowApp/
├── pages/
│   └── index/
│       └── index.vue          # 唯一页面：WebView 容器
├── static/
│   └── icon.png               # App 图标 (1024x1024)
├── App.vue                    # 应用入口（默认模板不改）
├── main.js                    # Vue 初始化（默认模板不改）
├── manifest.json              # 应用配置（HTTP 明文 + 图标 + 包名）
├── pages.json                 # 页面路由配置
└── uni.scss                   # 全局样式（默认模板不改）
```

### 核心页面

`pages/index/index.vue` 是唯一需要手写的页面：

- 使用 `<web-view>` 组件加载 `http://192.168.1.56:2026/`
- `@title` 事件将网页标题同步到原生导航栏
- 无任何业务逻辑，纯容器

### HTTP 明文配置

由于内网使用纯 HTTP，Android 9+ 和 iOS 默认禁止明文加载，需在 `manifest.json` 中配置：

- **Android**: `app-plus.distribute.android.manifestPlugins.usesCleartextTraffic = true`
- **iOS**: `app-plus.distribute.ios.plistcmds` 添加 `NSAllowsArbitraryLoads`

### 图标

一张 1024x1024 PNG 图标，HBuilderX 可视化配置后自动生成各平台所需尺寸。

## 打包策略

| 平台 | 方式 | 证书 |
|------|------|------|
| Android | HBuilderX 云打包 → .apk | DCloud 默认证书 |
| iOS | HBuilderX 云打包 → .ipa | Apple 开发者账号（$99/年） |

## 分发策略

- **Android**: .apk 文件通过微信分享或内网 HTTP 服务器提供扫码下载
- **iOS**: TestFlight 分发
- 与微信扫码方案互补使用

## 约束条件

- ❌ 无业务逻辑代码
- ❌ 无第三方 SDK 依赖
- ❌ 无权限申请（相机、定位、存储等）
- ❌ 无额外页面，单页面 App
- ✅ DeerFlow 前端更新后 App 自动加载最新内容，无需重新打包

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 云打包等待时间（3-5 分钟） | 打包期间可并行其他工作 |
| iOS 证书/描述文件管理复杂 | 初期只发 Android 版，iOS 用户用微信扫码兜底 |
| 内网 HTTP 被系统拦截 | 已规划 `usesCleartextTraffic` 和 `NSAllowsArbitraryLoads` 配置 |
