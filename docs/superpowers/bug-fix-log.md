# DeerFlow App Bug Fix Log

> 记录 App 开发过程中发现并修复的问题，供后续维护参考。

---

## Bug 1: 定时器误触发错误覆盖层

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
填写正确的 URL 后，App 正常运行一段时间，但**每隔约 10 秒自动弹出错误提示页**，要求修改 URL。点击「保存并加载」可以回到正常界面，但过一会又重复出现。

### 根因分析
`onShow()` 方法中有一处**多余的 10 秒定时器**逻辑：

```js
// ❌ Bug 代码
onShow() {
  this.loadSuccess = false   // 每次回到前台都重置
  setTimeout(function() {    // 每次都启动10秒定时器
    if (!this.loadSuccess) {  // 10秒后检查是否加载成功
      this.showErrorOverlay = true
    }
  }, 10000)
}
```

`onShow()` 在以下场景都会触发：
1. App 首次启动
2. App 从后台切回前台
3. 页面从导航栈中重新显示

**触发链路**：
1. App 首次启动 → `onShow()` → `loadSuccess=false` + 10秒定时器
2. WebView 加载成功 → `@load` 事件 → `loadSuccess=true` ✅
3. 用户切到其他 App 再回来 → `onShow()` **再次调用**
4. `loadSuccess=false` 再次被重置 → 10秒定时器重新启动
5. 但 WebView 已经加载好了，**不会重新触发 `@load` 事件**
6. 10秒后 `loadSuccess` 仍然是 `false` → 定时器误以为加载失败 → 弹出错误覆盖层

### 修复方案
**彻底移除定时器**，错误覆盖层只由 WebView 原生的 `@error` 事件驱动：

```js
// ✅ 修复后
onShow() {
  // URL 变化时才重置状态
  if (targetUrl !== this.webviewSrc) {
    this.webviewSrc = targetUrl
    // ... 不设 loadSuccess，不启动定时器
  }
  // 无定时器！
},
onWebViewLoad() {
  this.showErrorOverlay = false  // 加载成功就隐藏错误页
},
onWebViewError() {
  this.showErrorOverlay = true   // 加载失败才显示错误页
}
```

### 经验教训
- WebView 的 `@load` 和 `@error` 原生事件已经足够覆盖「成功/失败」两种状态，无需额外定时器
- `onShow()` 是高频回调，不适合在其中设置一次性定时器
- 错误状态应由**事件驱动**而非**定时轮询**

---

## Bug 2: config.js 修改后不生效（本地存储覆盖）

**发现日期**: 2026-05-29
**状态**: 已修复 ✅
**涉及文件**: `DeerFlowApp/DeerFlowApp/pages/index/index.vue`

### 现象
修改 `config.js` 中的 `serverUrl` 端口（如从 `2026` 改为 `20261`）后，重装 App 或重新运行，依然访问旧端口。

### 根因分析
存储逻辑有 3 个问题：

**问题 1：无条件覆盖**
```js
// ❌ Bug 代码
onShow() {
  var saved = uni.getStorageSync('df_server_url')
  this.webviewSrc = saved || appConfig.serverUrl  // saved 永远优先
}
saveAndLoad() {
  uni.setStorageSync('df_server_url', url)   // 每次都存，包括默认值
}
```

之前通过 ⚙ 保存过 URL（端口 `2026`）后，`df_server_url` 就永久存在了。此后不管 `config.js` 怎么改，`saved || configUrl` 都返回已保存的值，**config.js 的修改被彻底忽略**。

**问题 2：键名语义不清**
- `df_server_url` 同时存储「默认值」和「自定义值」，无法区分
- 无法判断当前 URL 是来自 `config.js` 还是用户自定义

**问题 3：恢复默认不清除存储**
```js
restoreDefaultUrl() {
  this.inputUrl = appConfig.serverUrl  // 只改了输入框，没删存储
  // 下次启动依然读取旧的存储值
}
```

### 修复方案
**分离默认值与自定义值**，config.js 永远作为权威基准：

```js
// ✅ 修复后
onShow() {
  var configUrl = appConfig.serverUrl        // 编译时默认值（权威基准）
  var customUrl = uni.getStorageSync('df_custom_url')  // 用户自定义值
  var targetUrl = customUrl || configUrl     // 有自定义用自定义，否则用默认

  // 更新逻辑...
}

saveAndLoad() {
  // 只有与 config.js 不同时才存自定义值
  if (url !== appConfig.serverUrl) {
    uni.setStorageSync('df_custom_url', url)
  } else {
    uni.removeStorageSync('df_custom_url')  // 和默认一样则清除
  }
}

restoreDefaultUrl() {
  uni.removeStorageSync('df_custom_url')    // 清除自定义记录
  this.inputUrl = appConfig.serverUrl       // 显示默认值
}
```

### 各场景验证

| 场景 | 行为 |
|---|---|
| `config.js`=`2026`，用户从未自定义 | 读取 `config.js` 的 `2026` |
| 改 `config.js` 为 `20261`，从未自定义 | 读取新的 `20261` |
| 用户自定义为 `8080` | 存 `df_custom_url=8080`，读 `8080` |
| 用户改回默认值并保存 | 清除自定义记录，下次读 `config.js` |
| 点「恢复默认地址」 | 清除自定义记录，显示 `config.js` 的值 |
| 旧版升级（存在 `df_server_url`） | 自动清理旧键名 |

### 经验教训
- 本地存储和配置文件应明确区分「默认值」和「用户自定义值」
- config.js 应始终作为编译时的权威默认值
- 「恢复默认」操作必须清除存储中的自定义值，而非仅修改 UI
- 存储键名应语义清晰，避免歧义

---

## 通用教训

1. **事件驱动优于定时轮询**：WebView 的生命周期事件已经足够覆盖所有状态变化
2. **存储分层**：编译配置（config.js）vs 运行时配置（Storage）应有清晰优先级
3. **幂等设计**：onShow 等高频回调应设计为幂等的，重复调用不产生副作用
4. **升级兼容**：存储键名变更时需清理旧键名，避免遗留数据影响新版本
