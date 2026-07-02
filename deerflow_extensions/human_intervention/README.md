# 交互式人工介入扩展 (Human Intervention)

## 功能概述

为 AI Agent 的 `ask_clarification` 流程增加交互式 UI 组件（按钮选项、文本输入框、确认对话框），替代纯 Markdown 文本渲染。用户可通过点击按钮快速回复 AI 的澄清请求，也可在输入框中自由输入。

实现三层防御体系确保所有需要用户选择/补充的场景都能触发人工介入交互：
- **Layer 1: Prompt 引导** — 系统提示词注入渐进式澄清覆盖指令（每次只问 1 个问题，聚焦决策空间）
- **Layer 2: Clarification Gate** — awrap_model_call 拦截 LLM 响应，检测内联提问并自动注入 ask_clarification 工具调用
- **Layer 3: 中间件中断** — wrap_tool_call 拦截 ask_clarification 并中断执行，附加结构化 _clarification 数据

## 目录结构

```
deerflow_extensions/human_intervention/
├── extension_manifest.json                     # 扩展声明（版本、依赖、kill switch）
├── clarification_middleware_ext.py              # HumanInterventionClarificationMiddleware 子类
├── patch.py                                     # _build_middlewares 补丁注入
├── rate_limiter.py                              # ClarificationRateLimiter 进程内限流
├── startup.py                                   # install_human_intervention() 入口
├── contracts/
│   └── clarification_structured_v1.json         # _clarification 结构化数据 Schema
└── README.md                                    # 本文件
```

## 子类化模式

`HumanInterventionClarificationMiddleware(ClarificationMiddleware)` 继承自上游的 `ClarificationMiddleware`，覆写 `_handle_clarification`：

```python
class HumanInterventionClarificationMiddleware(ClarificationMiddleware):
    def _handle_clarification(self, request):
        try:
            result = super()._handle_clarification(request)
            # 注入结构化 _clarification 数据
            structured = self._build_clarification_structured(args)
            msg.additional_kwargs["_clarification"] = structured
            return result
        except Exception:
            return super()._handle_clarification(request)  # 优雅降级
```

优势：
- 上游方法签名变更时，`super()` 自动继承新签名
- `isinstance(mw, HumanInterventionClarificationMiddleware)` 守卫幂等注入
- try/except 降级：即使结构化失败，原始 clarification 逻辑不受影响

### 结构化 Schema

`ToolMessage.additional_kwargs["_clarification"]` 包含版本化数据：

```json
{
  "_schema": "deerflow/clarification/v1",
  "type": "clarification",
  "id": "call_abc123",
  "question": "需要部署到哪个环境？",
  "clarification_type": "approach_choice",
  "context": "项目当前有三个可用环境",
  "options": ["staging", "production", "development"],
  "widget_hints": {
    "input_type": "single_choice",
    "required": true,
    "risk_level": "medium"
  },
  "widget_hint": "single_choice"
}
```

完整 Schema 定义见 `contracts/clarification_structured_v1.json`。

### Widget 类型映射

| `input_type` | 对应 `clarification_type` | 前端行为 | 额外 hint 字段 |
|---|---|---|---|
| `text` | `missing_info`, `ambiguous_requirement` | 文本输入框 + 提交按钮 | `multi_line` |
| `single_choice` | `approach_choice`, `suggestion` | 选项按钮组 (+ `allow_custom` 时显示「其他…」) | `allow_custom` |
| `multi_choice` | `approach_choice` (多选) | 复选框组 + 提交按钮 | `allow_custom` |
| `confirmation` | `risk_confirmation` | 按 risk_level 分级渲染（low→不渲染, medium→单次确认, high→输入确认短语, critical→短语+倒计时） | `risk_level`, `confirm_phrase` |

## Clarification Gate（核心）

### 三层防御体系

```
Layer 1: Prompt 引导（尽力而为）
  -- SYSTEM_PROMPT_TEMPLATE 注入 clarification_skill_override
  -- skills_section 注入 clarification_constraint

Layer 2: Clarification Gate（确定性拦截）* 核心层
  -- awrap_model_call 拦截 LLM 响应
  -- 检测 AI 文本是否包含内联提问
  -- 检测到 -> 自动注入 ask_clarification 工具调用
  -- 已有 ask_clarification 调用 -> 透传

Layer 3: 中间件中断处理
  -- wrap_tool_call 拦截 ask_clarification
  -- _handle_clarification -> Command(goto=END) -> 中断执行
  -- 附加结构化 _clarification 数据
```

### Sync/Async Gate

注入 `_apply_clarification_gate` 公共方法，同时支持 `wrap_model_call`（同步）和 `awrap_model_call`（异步），两者行为 100% 一致。

### 数据流

```
LLM 生成响应（AIMessage）
    |
    |- tool_calls 包含 ask_clarification？ -> YES -> wrap_tool_call 处理 -> 中断
    |
    |- tool_calls 不包含，但 AI 文本含内联提问？
    |       |
    |       |- Rate limiter 检查（max_per_turn=3, cooldown=30s）
    |       |     → 超限：保留 content，跳过注入，warn 日志
    |       |
    |       |- 去重检查（关键词交集 ≥70%）
    |       |     → 重复：保留 content，跳过注入，info 日志
    |       |
    |       |- 通过 → 注入 ask_clarification 到 tool_calls
    |       |       清空 AI 文本 content
    |       |       -> wrap_tool_call 处理 -> 中断
    |       |
    |       |- NO -> 正常透传
```

### 内联提问检测算法

检测位置：`clarification_middleware_ext.py` 中的 `_detect_inline_clarification()` 方法

检测规则（全部满足才触发）：
1. **问号检测**：文本中必须包含以 `？` 或 `?` 结尾的句子
2. **关键词检测**：文本中必须包含澄清关键词（`请问`、`您想`、`是否`、`请选择` 等）
3. **问题提取**：取最后一个问号句作为 `question` 参数
4. **选项提取**：如文本含 `1. xxx\n2. xxx` 或 `- xxx\n- xxx` 结构化列表，提取为 `options`

## 防误报策略

- 两个条件（问号 + 关键词）同时满足才触发，单条件不触发
- `你好`、`今天的日期` 等单纯问候/指令不含关键词，不会误触发
- 任何异常回退到安全路径（`try/except` 包裹，异常不中断正常响应）
- 已有 `ask_clarification` 工具调用的响应不再重复注入
- 选项过滤：如提取出的选项中有任何一项含 `？`/`？`，说明 AI 是在用"选项"形式写描述性文字而非提供可选候选项（例如"或者您有特殊需求？"），则整组选项清空降级为文本输入框
- 选项硬截断（H1）：超过 50 项时截断 + 追加"…及其他 N 项"，避免 LLM 生成海量选项

## Kill Switch

通过文件标记禁用扩展，**不重启即可生效**（启动时检查）：

```bash
touch .deer-flow/extensions/human_intervention.disabled
# 重启后日志含 "Kill switch active"
rm .deer-flow/extensions/human_intervention.disabled # 恢复
```

实现方式：`install_human_intervention()` 调用 `boot._resolve_project_root()` 检测标记文件，Fail-Open（异常时继续安装）。

## Rate Limiter

`ClarificationRateLimiter`（`rate_limiter.py`）提供进程内线程安全限流：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_per_turn` | 3 | 每个 thread 每轮最多触发次数 |
| `cooldown_seconds` | 30 | 连续触发的最小间隔 |

- 配置来源：`extension_manifest.json` 的 `clarification_policy` 字段
- 纯内存 `dict + threading.Lock`，重启即重置
- Fail-Open：初始化失败 limiter=None，检查时跳过

## 选项硬截断

`_normalize_options` 在规范化选项时施加 `max_options=50` 硬边界。超出时 warn 日志 + 截断 + 追加摘要项（"…及其他 N 项"）。

## 启动流程

1. **boot.py 注册**：在 `_EXTENSIONS` 列表中新增 `("human_intervention", False)` 条目
2. **startup.py**：`install_human_intervention()` 依次调用：
   - Kill Switch 检查：检测 `.deer-flow/extensions/human_intervention.disabled` 标记
   - `_inject_clarification_into_system_prompt()` — Layer 1 渐进式 Prompt 引导
   - `_inject_clarification_into_skills_section()` — Layer 1 Prompt 引导
   - `_inject_human_intervention_middleware()` — Layer 2/3 中间件（含 Clarification Gate + Rate Limiter）
3. **patch.py**：通过 `@wraps` 包装 `_build_middlewares`，用 `isinstance` 替换 `ClarificationMiddleware` 实例
4. **运行时**：每次 `_build_middlewares` 被调用时，自动注入增强版中间件；Clarification Gate 在每次模型调用时生效

## 依赖

- DeerFlow >= 2.0, < 3.0
- 前端 `frontend/extensions/human-intervention/` 对应版本必须匹配
- 无其他外部依赖

## 降级策略

| 场景 | 行为 |
|---|---|
| 结构化注入异常 | `try/except` 降级到纯文本 clarification |
| 前端收到未知 schema 版本 | 降级到 MarkdownContent 渲染 |
| upstream 原生支持澄清 UI | 检测到上游方法/字段后自禁用 |
| Kill switch 文件存在 | `touch .deer-flow/extensions/human_intervention.disabled` 后重启跳过安装 |
| Rate limiter 初始化失败 | limiter=None，检查时跳过（Fail-Open） |
| data_collection 异常 | `_emit_clarification_event` try/except 静默降级 |
| 选项截断 | warn 日志 + 截断至 50 项 + 摘要项 |

## 验证命令

```bash
# 检查中间件注入
python3 -c "from deerflow_extensions.human_intervention.startup import install_human_intervention; install_human_intervention(); print('OK')"

# 检查 MRO
python3 -c "
from deerflow_extensions.human_intervention.clarification_middleware_ext import HumanInterventionClarificationMiddleware
print(HumanInterventionClarificationMiddleware.__mro__)
"

# 确认扩展已注册
grep "human_intervention" deerflow_extensions/boot.py

# 检查 Kill Switch 功能
python3 -c "import os; os.path.exists('.deer-flow/extensions/human_intervention.disabled') and print('disabled mode')"

# 验证 Rate Limiter 加载（日志应含 'Rate limiter initialized'）
python3 -c "
from deerflow_extensions.human_intervention.clarification_middleware_ext import HumanInterventionClarificationMiddleware
import logging
logging.basicConfig(level=logging.INFO)
mw = HumanInterventionClarificationMiddleware()
print('Rate limiter:', 'OK' if mw._limiter else 'disabled')
"
```
