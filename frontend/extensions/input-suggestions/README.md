# 输入建议

## 说明

通过运行时配置 + Context-状态驱动-Registry 桥接模式，实现输入建议按钮的自定义系统。这些按钮显示在聊天输入框上方，用户点击后自动填入提示词模板，用于替代 DeerFlow 内置的"小惊喜/写作/研究"等快捷按钮。

## 目录结构

```
input-suggestions/
├── types.ts      # 配置项类型定义（JSON 可序列化）
├── config.ts     # 运行时配置加载器（fetch + 校验 + 缓存 + icon 解析）
├── context.tsx   # React Context Provider + Hook
└── registry.ts   # 注册表系统（核心，不可变数据层）
```

## 架构概览

```
site.config.json
     │ fetch
     ▼
config.ts ── loadInputSuggestionsConfig() ── 校验 ── 返回 InputSuggestionConfig[]
     │                                          ▲
     │ resolveIcon(iconName) ── iconMap ────────┘
     ▼
context.tsx ── InputSuggestionsProvider ── clear + register ── registry.ts
     │                       │
     │                 useState(InputSuggestion[])
     ▼                       │
useInputSuggestionsReady ─────┘
     │
     ▼
input-box.tsx ── 订阅 Context，自动重渲染
```

## 核心文件说明

### types.ts

定义 `InputSuggestionConfig` 接口（JSON 可序列化，所有字段必填）：

```typescript
interface InputSuggestionConfig {
  id: string;
  label: string;
  prompt: string;
  icon: string;          // lucide-react 图标字符串名，如 "Monitor"
  group: "main" | "create";
}
```

### registry.ts

注册表系统，提供三个核心 API：

| 函数 | 说明 |
|------|------|
| `registerInputSuggestion(s)` | 注册一个输入建议项，相同 id 重复注册自动忽略 |
| `getInputSuggestions()` | 获取当前所有注册的建议项的副本 |
| `clearInputSuggestions()` | 清空所有注册项（用于测试或重置） |

`InputSuggestion` 类型（运行时使用的完整类型，icon 为 LucideIcon 组件）：

```typescript
interface InputSuggestion {
  id: string;
  label: string;
  prompt: string;
  icon: LucideIcon;
  group: "main" | "create";
}
```

### config.ts

运行时配置加载器，替代原有的编译时硬编码注册模式。核心功能：

**1. 静态 iconMap**
- 显式导入当前所有已配置的 lucide-react 图标（支持 tree-shaking）
- 新增图标需同时在此添加导入和映射

**2. 原型链污染防护**
- `BLOCKED_ICON_NAMES` 黑名单：`constructor`、`__proto__`、`prototype`、`toString` 等 8 个
- `resolveIcon()` 自动去 `Icon` 后缀规范化匹配

**3. 运行时校验规则**
- `inputSuggestions` 非数组 → `console.warn` + 返回 `[]`
- 单条缺字段（id/label/prompt/icon/group）→ `console.warn` + 跳过
- `group` 不在 `["main", "create"]` → `console.warn` + 跳过
- `prompt` 为空或纯空格 → `console.warn` + 跳过
- fetch 失败 / HTTP 错误 / JSON 解析错误 → 返回 `[]`（零渲染）

**4. 缓存策略**
- 模块级 `_cached` 单例，避免重复 fetch
- `{ cache: "no-store" }` 确保每次获取最新
- `clearInputSuggestionsCache()` 供测试用

### context.tsx

React Context Provider + Hook 层：

- `InputSuggestionsProvider`：在 useEffect 中 fetch site.config.json → 校验 → 解析 icon → 注册到 registry → 通过 `useState` 触发自动重渲染
- `useInputSuggestionsReady()`：消费端 Hook，订阅 Context 状态变化
- `cancelled` 守卫防止 StrictMode 双挂载或组件卸载后写全局状态

## 配置方式

输入建议通过 `public/site.config.json` 的 `inputSuggestions` 数组配置（**JSON 是唯一且强制的配置源**）：

```json
{
  "inputSuggestions": [
    {
      "id": "product-consult",
      "label": "产品咨询",
      "prompt": "咨询关于[具体问题]",
      "icon": "Monitor",
      "group": "main"
    }
  ]
}
```

**配置缺失时行为**：`inputSuggestions` 不存在、非数组或为空 → 前端不显示任何建议按钮，零渲染。

**添加新图标步骤**：
1. 在 `public/site.config.json` 中添加配置项，`icon` 使用 lucide-react 导出名（去 `Icon` 后缀）
2. 在 `config.ts` 的 `iconMap` 中添加导入和映射
3. 重新构建（`pnpm build`）

## 安全说明

- 所有 icon 名称通过 `resolveIcon()` 解析，自动拦截原型链属性访问
- BLOCKED_ICON_NAMES 防止 `constructor`、`__proto__` 等字符串被用作 key 访问对象原型

## 依赖

- lucide-react（图标组件）
- React 18+（Context + Hooks）

## 当前配置项

**main 组（主功能区）：**
| ID | 标签 | 提示词模板 | 图标 |
|----|------|-----------|------|
| product-consult | 产品咨询 | 咨询关于ADS桌面云的[具体问题] | Monitor |
| tech-support | 技术支持 | 排查[具体技术问题]的原因和解决方案 | Bug |
| deployment | 关联模板 | 使用终端关联模板 skill，处理[关联场景]的终端配置 | GitMerge |

**create 组（创作区）：**
| ID | 标签 | 提示词模板 | 图标 |
|----|------|-----------|------|
| ops-report | 运维报告 | 生成关于[主题]的系统运维分析报告 | FileText |
| config-script | 配置脚本 | 生成[场景]的ADS批量配置脚本 | FileCode |
| knowledge-search | 知识检索 | 从知识库检索[主题]的相关资料并总结 | Search |

