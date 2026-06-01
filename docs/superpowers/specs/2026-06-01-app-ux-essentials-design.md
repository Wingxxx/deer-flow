# DeerFlowApp UX Essentials 优化设计

**日期**：2026-06-01
**状态**：设计稿
**负责人**：WING

## 1. 概述

DeerFlowApp 是一个极简 uni-app (Vue 3) 外壳，通过全屏 WebView 包裹 DeerFlow 服务器。本文档从用户视角出发，只补充「一个正经 App 必须有」的基本体验要素，不做视觉翻新或功能扩展。

## 2. 优化项

### 2.1 启动加载状态（Loading Splash）

**现状**：App 冷启动后立即显示 WebView，如果 WebView 加载缓慢用户看到的是白屏。如果网络不通或地址错误，需等待 WebView 超时才出现错误覆盖层。

**设计**：
- App 启动后（`onShow`/`onReady` 阶段）不立即显示 WebView
- 取而代之显示一个加载画面：
  - 纯白背景，居中
  - 一个纯 CSS 绘制的旋转圆圈（24px × 24px，`#007AFF` 蓝色）
  - 下方文字：「正在连接 DeerFlow 服务器...」（14px, `#86868B` 灰色）
  - 轻量淡入动画（`opacity 0 -> 1, 0.2s`）
- 后端并行执行：
  1. `uni.getNetworkType()` 检查网络
  2. 对当前 `serverUrl` 发起 `GET /health` 请求（5 秒超时）
- 结果处理：
  - **网络 + `/health` 均正常** → 加载画面淡出，WebView 淡入（`opacity 0.25s`）
  - **网络不通** → 加载画面直接过渡到错误覆盖层，错误信息显示「📶 设备未连接网络」
  - **网络通但 `/health` 失败** → 加载画面过渡到错误覆盖层，显示「🔌 无法连接服务器」

**实现位置**：`pages/index/index.vue`
- `data` 新增：`isLoading: true`
- `template` 新增条件渲染段（`v-if="isLoading"`）
- `onShow`/`onReady` 中改为先执行网络检查 + `/health`，再决定显示 WebView 还是错误覆盖层

**样式要点**：
- 加载画面使用 `position: fixed; top:0; left:0; right:0; bottom:0` 填满屏幕
- 旋转圆圈使用 CSS `@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }` + `border`/`border-top-color` 实现
- WebView 容器添加 `transition: opacity 0.25s`

### 2.2 完全隐藏原生导航栏

**现状**：App 顶部有 HBuilderX 原生导航栏，显示标题「DeerFlow」。当 WebView 页面设置了 `<title>`，`@title` 事件会将标题同步为网页标题。

**设计**：
- 隐藏整个原生导航栏，WebView 从屏幕顶部状态栏下方开始渲染
- 移除 `@title` 事件监听（不再需要同步标题）
- 处理刘海屏安全区域：WebView 容器添加 `padding-top: env(safe-area-inset-top)`，使内容不被状态栏遮挡

**实现位置**：
- `pages.json`：`pages[0].style` 中添加 `"navigationStyle": "custom"`
- `index.vue`：`<web-view>` 容器添加安全区域 padding
- `index.vue`：删除 `onTitle` 方法及 `@title` 绑定

### 2.3 App Icon 配置

**现状**：`static/logo.png` 是一个占位图标，云打包后 App 图标为 HBuilderX 默认图标或占位图。

**设计**：
- 主子自行准备 App 图标文件放入 `static/` 目录
- 在 `manifest.json` 的 `app-plus.distribute.android` 和 `app-plus.distribute.ios` 中配置图标路径
- Android 需要至少 `-hdpi`、`-xhdpi`、`-xxhdpi` 三种尺寸
- iOS 需要 `1024x1024`（App Store 标准）

**图标要求**（由主子提供）：
- Android：放入 `static/icons/android/` 目录
  - `icon-hdpi.png`（72×72）
  - `icon-xhdpi.png`（96×96）
  - `icon-xxhdpi.png`（144×144）
  - `icon-xxxhdpi.png`（192×192）
- iOS：放入 `static/icons/ios/` 目录
  - `icon-1024.png`（1024×1024）

### 2.4 禁止 WebView 双指缩放

**现状**：用户在 WebView 页面可以用双指缩放，可能导致 DeerFlow 界面布局错乱。

**设计**：
- 在 `injectFix` 函数注入的 CSS 中增加限制缩放的规则
- 核心方案：注入 `<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">`
- 并在每次 WebView 页面加载完成后重新注入（`@load` 事件触发 `injectFix`）

**实现位置**：`pages/index/index.vue` → `injectFix` 函数
- 注入 CSS 增加 `touch-action: pan-y` 限制横向滚动和缩放
- 使用 `evalJS` 注入 viewport meta 标签

## 3. 不变的限制

- 零存储策略不变：不使用 `getStorageSync` / `setStorageSync`
- config.js 唯一来源不变
- `/health` 身份验证硬限制不变
- 原生悬浮按钮 `plus.nativeObj.View` 不变
- 不引入任何新依赖或 npm 包

## 4. 影响范围

| 文件 | 改动 |
|------|------|
| `pages/index/index.vue` | 新增加载画面模板、逻辑；隐藏导航栏适配；删除 `@title`；禁止缩放注入 |
| `pages.json` | 添加 `navigationStyle: "custom"` |
| `manifest.json` | 配置图标路径 |
| `config.js` | 无改动 |
