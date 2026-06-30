# 品牌自定义配置

## 设计目标

提供一套**零侵入**的品牌自定义机制，允许在不修改核心源码的情况下替换 DeerFlow 前端中的品牌标识。

## 架构

```
site.config.json (public/)     ← 运行时配置文件，修改后无需重新构建
       ↓
BrandingProvider               ← React Context，挂载时加载配置
       ↓
workspace-header.tsx           ← useBranding() 替换品牌名
welcome.tsx                    ← useBranding() 叠加欢迎语
ads_auth/LoginPage.tsx         ← useBranding() 替换登录页标题
layout.tsx                     ← 服务端读取 site.config.json 生成动态 title
```

## 文件说明

| 文件 | 职责 |
|------|------|
| `types.ts` | `BrandingConfig` 接口定义，所有字段可选 |
| `config.ts` | 运行时加载 `/site.config.json`，含 `_cached` 缓存避免重复请求 |
| `context.tsx` | `BrandingProvider` 组件 + `useBranding()` hook |
| `../../public/site.config.json` | 运行时配置文件，修改后刷新即生效 |

## 配置项

```json
{
  "appName": "自定义应用名",
  "appAbbreviation": "缩写",
  "welcome": {
    "greeting": "欢迎语",
    "description": "欢迎描述"
  },
  "loginPage": {
    "title": "登录页标题"
  }
}
```

- 所有字段可选，缺失时自动降级到 i18n 默认值
- 修改 `site.config.json` 后刷新页面即可生效，**无需重新构建**

## 使用方式

```tsx
import { useBranding } from "../branding/context";

function Component() {
  const { appName = "DeerFlow", appAbbreviation = "DF" } = useBranding();
  return <div>{appName}</div>;
}
```

Provider 已在 `layout.tsx` 中全局包裹，消费端组件直接调用 `useBranding()` 即可。
