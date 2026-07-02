# 人工介入交互设计参考标准

> 基于 OpenAI / Anthropic / LangChain / Slack / Microsoft 等平台的 HITL 与对话式 UI 实践。
> 临时参考文档，供后续人工介入功能设计决策使用。

---

## 一、何时触发人工介入（触发条件）

| 场景 | 判断标准 | 示例 |
|------|---------|------|
| **信息缺失** | Agent 缺少执行任务必需的参数/上下文，且无法从历史或环境中推断 | "帮我优化代码" → 哪段代码？什么方向？ |
| **歧义消解** | 用户意图存在多种合理解读，Agent 无法确定唯一路径 | "部署应用" → 生产？预发布？测试？ |
| **高风险确认** | 操作后果不可逆或影响面大，需用户显式授权 | "删除所有数据"、"发布到生产" |
| **主观偏好** | 决策涉及品味、风格、策略等无法由 Agent 客观判定的维度 | "选什么颜色"、"用 React 还是 Vue" |

**核心原则：最少惊扰（Least Interruption）**
> Only interrupt when the value of the answer exceeds the cost of the interruption.

每次中断打断用户心流。如果 Agent 能用默认值 + 事后确认（如 "我将优化可读性，不同意可调整"），优于事前拦停。

---

## 二、交互模式选择：选择 vs 输入 vs 选择+输入

### 决策树

```
答案空间是否封闭可枚举？
├─ YES → 选项数 ≤ 5？
│   ├─ YES → 【纯选择】按钮组
│   └─ NO  → 【选择+输入】预设高频选项 + "其他/自定义" 入口
└─ NO  → 答案需要自然语言描述？
    ├─ YES → 【纯输入】文本框
    └─ 部分可枚举 → 【选择+输入】常见选项 + 自定义兜底
```

### 三种模式对比

| UI 模式 | 适用条件 | 优势 | 风险 |
|---------|---------|------|------|
| **纯选择** | 选项集合 ≤5、互斥、Agent 100% 确定所有合法值 | 零输入成本、防错 | 漏掉用户需要的选项 |
| **纯输入** | 答案开放、无法枚举、或选项太多（>10） | 完全灵活 | 输入成本高、需二次解析 |
| **选择+输入** | 80% 场景落在 ≤5 个高频选项，但 20% 需要自定义 | 兼顾效率与灵活性 | UI 复杂度增加 |

---

## 三、各平台对标

| 平台 | 选择模式 | 输入模式 | 组合模式 | 关键文档 |
|------|---------|---------|---------|---------|
| **OpenAI** | Function Calling `enum` | `string` 类型参数 | `anyOf [enum, string]` | [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) |
| **Anthropic** | Tool Use `input_schema.enum` | `input_schema.string` | 同 OpenAI | [Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) |
| **LangGraph** | `Command(resume={"choice": "A"})` | `Command(resume="free text")` | 上游代码可自定义 | [Human-in-the-loop](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/) |
| **Slack Block Kit** | `static_select` / `radio_buttons` | `plain_text_input` | 不支持组合（需分块） | [Block Kit Builder](https://api.slack.com/block-kit) |
| **Adaptive Cards** | `Input.ChoiceSet` | `Input.Text` | 分开渲染 | [Adaptive Cards](https://adaptivecards.io/) |
| **CrewAI** | `HumanInput(choices=[...])` | `HumanInput()` | 不支持组合 | [CrewAI Human Input](https://docs.crewai.com/concepts/human-input-on-tools) |
| **AutoGen** | `UserProxyAgent` 多轮对话 | 自由文本回复 | 对话式自然选择 | [AutoGen HITL](https://microsoft.github.io/autogen/docs/topics/human-in-the-loop/) |

---

## 四、三条设计准则

### 准则 1：最少惊扰原则（HITL 安全研究）
> Only interrupt when the value of the answer exceeds the cost of the interruption.

- 来源：LangChain HITL 文档、OpenAI 安全实践
- 宁可事后纠错，不要过度拦停
- 高风险操作是例外

### 准则 2：渐进式披露（Nielsen Norman Group）
> Don't ask all questions upfront. Ask the most constraining question first, then narrow.

- 不要一次抛出 5 个问题
- 先问最关键的那个
- 根据回答决定下一步，类似决策树

### 准则 3：选择优于输入（移动端 UX / 对话式 UI）
> Recognition over recall. Selection minimizes cognitive load and errors.

- 能列举就不要让用户打字
- Claude、ChatGPT 等主流产品一致做法
- 优先展示按钮，仅当无法枚举时降级为输入框

---

## 五、对 DeerFlow 现状的启示

### 当前能力
- `ask_clarification(question, options)` 覆盖纯选择（options 非空）和纯输入（options 为空）
- 前端 `ClarificationWidget` 渲染：options 非空 → 按钮组；空 → 文本输入框

### 当前缺失
- **选择+输入** 组合模式（如 Slack Block Kit 的 `overflow_menu` + `text_input` 分离块）
- **渐进式多轮澄清**（一次只问一个问题，根据回答决定下一个）
- **高风险操作确认模式**（独立的 yes/no confirm 对话框）

### 最务实的增强路径
1. **选择+输入**：`ClarificationWidget` 在 options 非空时渲染按钮组，最末位固定 `[其他/自定义...]` 按钮，点击后展开文本输入框
2. 后端 `ask_clarification` 支持 `allow_custom: true` 参数
3. 与 Adaptive Cards / Slack Block Kit 模式完全对齐，实现成本低

### 废弃兼容性
当前方案已预留 `kill_switch` marker 文件禁用机制（`.deer-flow/extensions/human_intervention.disabled`），未来若上游原生实现，可通过探测式降级 + 配置开关双重机制确保零冲突。

---

## 六、参考资源

| 资源 | 链接 | 关键内容 |
|------|------|---------|
| OpenAI Structured Outputs | https://platform.openai.com/docs/guides/structured-outputs | enum vs string 分类逻辑 |
| Anthropic Tool Use | https://docs.anthropic.com/en/docs/build-with-claude/tool-use | input_schema 设计模式 |
| LangGraph Human-in-the-loop | https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/ | interrupt + Command(resume=) 模式 |
| Slack Block Kit | https://api.slack.com/block-kit | 交互式消息 UI 参考标准 |
| Microsoft Adaptive Cards | https://adaptivecards.io/ | 跨平台交互卡片规范 |
| Nielsen Norman — Recognition vs Recall | https://www.nngroup.com/articles/recall-recognition/ | 认知负荷理论基础 |
| Anthropic — Prompt Engineering for HITL | https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering | 提示词引导 Agent 合理使用澄清工具 |
