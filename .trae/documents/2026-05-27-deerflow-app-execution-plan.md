# DeerFlow 内网 App 入口 — 执行计划

> 基于 `docs/superpowers/plans/2026-05-27-deerflow-internal-app-plan.md` 制定
> **环境**: Windows + HBuilderX | **项目根目录**: `d:\Wing_D\emto\2026\2026.5\uni-app`

---

## 总步数：8 步 | 预计耗时：30-45 分钟（不含云打包等待）

---

## Task 1: 用户手动创建 uni-app 项目

**操作人**: 圣上（AI 提供指引）

1. 打开 HBuilderX
2. `文件 → 新建 → 项目`
3. 选择 `uni-app`，模板选 `默认模板`
4. 项目名：`DeerFlowApp`
5. **保存位置**：`d:\Wing_D\emto\2026\2026.5\uni-app\DeerFlowApp`
6. 确定创建

**验证标志**: 目录 `d:\Wing_D\emto\2026\2026.5\uni-app\DeerFlowApp\` 下出现 `pages/`、`App.vue`、`main.js`、`manifest.json`、`pages.json` 等文件

**注意**: 此步 HBuilderX 会自动生成 appid，**不要修改 appid**，后续云打包依赖它。

---

## Task 2: 写入核心 WebView 页面

**操作人**: AI 奴才

### Step 2.1 — 写入 `pages/index/index.vue`

整个 App 唯一的核心页面，13 行代码：

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

### Step 2.2 — 确认 `pages.json` 配置

确保首页路由指向正确的页面，导航栏标题为 "DeerFlow"。

---

## Task 3: 配置 HTTP 明文访问（最关键）

**操作人**: AI 奴才

### 修改 `manifest.json`

在 HBuilderX 生成的 `manifest.json` 基础上，在 `app-plus` 节点下增加：

- **Android**: `usesCleartextTraffic: true`
- **iOS**: `NSAllowsArbitraryLoads` plistcmds

**不改动**: appid、name、versionName 等 HBuilderX 自动生成的字段

---

## Task 4: 配置 App 图标

**操作人**: 圣上

1. 准备一张 **1024x1024** 像素的 PNG 图标，命名为 `icon.png`
2. 放入 `DeerFlowApp/static/icon.png`
3. 在 HBuilderX 中打开 `manifest.json` → `App 图标配置` → 上传 `icon.png`

---

## Task 5: Android 真机调试

**操作人**: 圣上

1. 手机开 **开发者模式 + USB 调试**
2. USB 连电脑
3. HBuilderX → `运行 → 运行到手机或模拟器 → Android`
4. 确认 App 启动后自动加载 `http://192.168.1.56:2026/`

---

## Task 6: Android 云打包

**操作人**: 圣上

1. HBuilderX → `发行 → 原生App-云打包`
2. 包名：`com.deerflow.app`
3. 证书：**DCloud 默认证书**
4. 等待 3-5 分钟 → 下载 `.apk`

---

## Task 7: iOS 云打包（可选）

**操作人**: 圣上（需 Apple 开发者账号 $99/年）

若无账号则跳过，iOS 用户用微信扫码兜底。

---

## Task 8: 分发部署

**操作人**: 圣上

- .apk 上传到内网 HTTP 服务器 → 生成二维码
- 微信群同时发二维码 + .apk 文件

---

## TDD 策略

本项目是一个纯配置型 WebView 壳 App，无业务逻辑代码：
- Task 2 的 index.vue 共 13 行，测试方案为**真机调试验证**（Task 5）
- Task 3 的 manifest.json 配置错误会导致白屏，验证方法为**真机查看 App 是否正常加载页面**
- 不涉及单元测试框架

## 代码审查要点

| Task | 审查内容 |
|------|----------|
| Task 2 | index.vue 的 `src` 地址是否正确、`@title` 事件绑定是否正确 |
| Task 3 | `manifest.json` JSON 格式是否合法、`usesCleartextTraffic` 是否在正确的层级 |

## 验收标准

1. HBuilderX 项目创建成功，目录结构完整
2. WebView 页面代码写入，`src` 地址正确
3. `manifest.json` HTTP 明文配置正确，JSON 格式合法
4. 真机调试：App 启动后自动加载 DeerFlow，导航栏标题同步
5. Android 云打包成功，.apk 可正常安装
6. 用户安装后连接内网 WiFi，打开 App 即可使用 DeerFlow
