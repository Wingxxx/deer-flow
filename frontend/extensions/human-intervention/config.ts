/**
 * Human-Intervention Extension 人工介入扩展
 *
 * 提供结构化问答 UI 组件，用于处理 AI Agent 在运行中发出的澄清请求。
 * 当 Agent 调用 ask_clarification 工具时，系统会在消息的
 * additional_kwargs._clarification 中注入结构化数据，本扩展负责渲染
 * 对应的交互式小部件（文本输入、单选、多选、确认）。
 *
 * 使用方式：
 * 1. 在 workspace-content.tsx 中包裹 <ClarificationProvider>
 * 2. 在 message-list.tsx 中导入 ClarificationWidget 替换原有 clarification 渲染
 */

export const HUMAN_INTERVENTION_EXTENSION = {
  name: "human-intervention",
  version: 1,
  description: "结构化问答 UI 组件 - 处理 AI Agent 的澄清请求",
} as const;

export { ClarificationProvider } from "./ClarificationProvider";
export { ClarificationWidget } from "./ClarificationWidget";
export { parseClarificationStructured } from "./schema";
export { useClarificationSubmit } from "./hooks";
export type {
  ClarificationStructured,
  ClarificationType,
  WidgetInputType,
  WidgetHints,
  ClarificationContextValue,
} from "./types";
