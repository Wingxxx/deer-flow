# DeerFlowApp

**DeerFlowApp** — 一个极简的 uni-app (Vue 3) 壳工程，将 DeerFlow 服务器包装为全屏 WebView，通过 HBuilderX 云打包为 iOS/Android 原生 App。

不含业务逻辑、原生插件、第三方 SDK 依赖。

## 项目结构

```
DeerFlowApp/DeerFlowApp/        # HBuilderX uni-app 项目源码
├── config.js                   # 服务器 URL 默认地址（编译时）
├── pages/index/index.vue       # WebView + 错误覆盖层 + URL 配置面板
├── App.vue                     # 应用生命周期（onLaunch/onShow/onHide）
├── main.js                     # Vue 3 应用入口
├── pages.json                  # 路由配置
├── manifest.json               # App 配置（名称、HTTP 明文、云打包设置）
├── uni.scss                    # Uni-app SCSS 变量（默认主题）
├── uni.promisify.adaptor.js    # uni API Promise 适配
└── index.html                  # H5 平台入口
```

## 快速开始

### 前置条件
- [HBuilderX](https://www.dcloud.io/hbuilderx.html)（App 开发版）
- Android：开启开发者模式 + USB 调试的手机
- iOS（可选）：Apple Developer 账号（$99/年）

### 真机运行
1. 用 HBuilderX 打开 `DeerFlowApp/DeerFlowApp` 目录
2. 手机 USB 连接电脑
3. 点击 `运行 → 运行到手机或模拟器 → Android/iOS`

### 打包发布
- **Android**：HBuilderX → `发布 → 原生App云打包` → Android (.apk)
- **iOS**：HBuilderX → `发布 → 原生App云打包` → iOS (.ipa)，需 `.p12` 证书 + `.mobileprovision` 描述文件

## 配置说明

### 服务器地址
编辑 `DeerFlowApp/DeerFlowApp/config.js` 设置默认地址：

```js
export default {
  serverUrl: 'http://192.168.1.56:2026/'
}
```

### 运行时修改
App 内点击右下角 ⚙ 悬浮按钮，支持：
- **格式校验** — 自动补全协议、拦截非法字符
- **内网检测** — 公网域名时提醒
- **身份验证** — 通过 `GET /health` 验证服务器身份，非 DeerFlow 服务器禁止保存
- **保存并加载** — 持久化到本地存储
- **恢复默认地址** — 还原 `config.js` 中的默认值

### 错误处理
WebView 加载失败时自动显示错误覆盖层，支持重试（指数退避：2s → 4s → 8s → 15s）和修改地址。

## 技术要点
- 基于 **uni-app (Vue 3)**，HBuilderX 项目，无 npm/CLI
- 使用 `<web-view>` 组件嵌入 DeerFlow 前端页面
- 服务器更新后 App 自动反映，无需重新打包
- 支持 HTTP 明文（内网场景），Android 和 iOS 均已配置
- WebView 页面标题自动同步到原生导航栏

## 分支说明
- `uni-app` — 本分支，uni-app 壳工程源码
- `main` — DeerFlow 服务端主分支
