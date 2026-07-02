# 交互式人工介入前端扩展 (Human-Intervention)

## 功能概述

为 AI Agent 的 `ask_clarification` 流程提供交互式 UI 组件。当 Agent 调用澄清工具时，本扩展渲染结构化 Widget（文本输入、选项按钮、确认对话框）替代纯 Markdown 文本，用户点击按钮即可快捷回复。

## 目录结构

```
frontend/extensions/human-intervention/
├── config.ts                  # 注册入口（re-export Provider/Widget/hooks/types）
├── ClarificationProvider.tsx  # React Context — 传播 activeClarificationId / isSubmitting
├── ClarificationWidget.tsx    # 主 Widget 组件（按 input_type 分发到具体 Widget）
├── widgets/
│   ├── TextInputWidget.tsx    # 文本输入 + 提交按钮
│   ├── ChoiceButtonsWidget.tsx # 单选/多选按钮组 (+ allow_custom 时显示「其他…」)
│   └── ConfirmWidget.tsx      # 4 级风险确认（low→auto-accept, medium→单次确认, high→输入短语, critical→短语+倒计时）
├── types.ts                   # TypeScript 接口 + Zod schema
├── schema.ts                  # 版本化解析器（_schema 版本检查 → 降级）
├── hooks.ts                   # useClarificationSubmit — CustomEvent 桥接
└── README.md                  # 本文件
```

## 核心架构

### ClarificationProvider (React Context)

在 `workspace-content.tsx` 中全局挂载，管理：
- `activeClarificationId` — 当前活跃的澄清消息 ID
- `clarificationData` — 结构化澄清数据
- `isSubmitting` — 提交中状态（Widget 按钮 disabled）
- `submitClarification(answer)` — 通过 CustomEvent 桥接提交
- `dismissClarification()` — 取消/跳过

**回执确认（H2）**：`submitClarification` 派发 `clarification:submit` 后启动 3s 超时监听器，等待 hooks.ts 返回 `clarification:ack` 事件。超时未收到 ack 时恢复状态 + console.warn，避免因 sendMessage 静默失败导致状态丢失。

### CustomEvent 桥接

Provider 的 `submitClarification` 不直接调用 sendMessage，而是派发 `clarification:submit` CustomEvent：

```
ClarificationProvider.submitClarification("staging")
  → window.dispatchEvent(new CustomEvent("clarification:submit", { detail: { answer: "staging", clarificationId } }))
  → hooks.ts 的 useEffect 监听器捕获
  → sendMessage(threadId, { text: "staging", files: [] })
  → 成功后派发 "clarification:ack" → Provider 确认送达
  → 失败（3s 超时）→ 恢复状态 + console.warn
```

这种设计解耦了 Widget 组件（扩展目录）与页面逻辑（`src/` 源码），扩展目录组件无需 import sendMessage。

### 双通道提交（Intercom 风格）

- **Widget 按钮**：点击即发送，快捷回复
- **InputBox**：保持可用（不禁用），placeholder 切换为"回复 AI 的提问…"
- 两通道均可提交，无冲突

### 降级渲染

`parseClarificationStructured()` 检查 `_schema` 版本：
- 已知版本 → 渲染交互 Widget
- 未知版本 → 返回 `null`，调用方降级到 MarkdownContent 渲染

## 使用方式

### 挂载 Provider

在 `workspace-content.tsx` 中包裹：

```tsx
import { ClarificationProvider } from "../../../extensions/human-intervention/config";

<ClarificationProvider>
  <MobileSidebarTrigger />
  <WorkspaceSidebar />
  ...
</ClarificationProvider>
```

### 注入提交桥接

在 `page.tsx` 中调用 hook：

```tsx
import { useClarificationSubmit } from "../../../../../extensions/human-intervention/hooks";

useClarificationSubmit(sendMessage, threadId, thread.isLoading);
```

### Widget 条件渲染

在消息列表组件中（如 `message-list.tsx`），检查 `_clarification` 结构数据：

```tsx
import { ClarificationWidget, parseClarificationStructured } from "../../../extensions/human-intervention/config";

const structured = parseClarificationStructured(msg);
if (structured) {
  return <ClarificationWidget structured={structured} />;
}
// 降级到纯 Markdown
return <MarkdownContent content={msg.content} />;
```

## Widget 类型

| Widget | 用途 | 行为 | 关键 props |
|--------|------|------|-----------|
| TextInputWidget | 缺失信息、模糊需求 | 文本框 + 提交按钮，空输入拦截 | — |
| ChoiceButtonsWidget | 方案选择、建议 | 单选/多选按钮组。`allow_custom=true` 时追加「其他…」按钮，展开 textarea 自定义输入 | `allow_custom`, `input_type: multi_choice` |
| ConfirmWidget | 风险确认 | 按 risk_level 分级：low 不渲染、medium 单次确认、high 输入确认短语、critical 短语+5s 倒计时双重保障 | `risk_level`, `confirm_phrase` |

## 依赖

- 后端 `deerflow_extensions/human_intervention/` 对应版本必须匹配
- 无其他外部 npm 依赖

## 验证命令

```bash
# 确认 Provider 挂载
grep -n "ClarificationProvider" src/app/workspace/workspace-content.tsx

# 确认 hook 注入
grep -n "useClarificationSubmit" src/app/workspace/chats/[thread_id]/page.tsx

# 确认扩展文件完整性
ls extensions/human-intervention/{ClarificationProvider,ClarificationWidget,hooks,config,types,schema}.ts
```
