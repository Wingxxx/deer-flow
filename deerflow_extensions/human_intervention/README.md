# 交互式人工介入扩展 (Human Intervention)

## 功能概述

为 AI Agent 的 `ask_clarification` 流程增加交互式 UI 组件（按钮选项、文本输入框、确认对话框），替代纯 Markdown 文本渲染。用户可通过点击按钮快速回复 AI 的澄清请求，也可在输入框中自由输入。

## 目录结构

```
deerflow_extensions/human_intervention/
├── extension_manifest.json                     # 扩展声明（版本、依赖、kill switch）
├── clarification_middleware_ext.py              # HumanInterventionClarificationMiddleware 子类
├── patch.py                                     # _build_middlewares 补丁注入
├── startup.py                                   # install_human_intervention() 入口
├── contracts/
│   └── clarification_structured_v1.json         # _clarification 结构化数据 Schema
└── README.md                                    # 本文件
```

## 核心设计

### 子类化模式

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
  "question": "需要部署到哪个环境？",
  "clarification_type": "approach_choice",
  "context": "项目当前有三个可用环境",
  "options": ["staging", "production", "development"],
  "widget_hints": {
    "input_type": "single_choice",
    "required": true
  }
}
```

完整 Schema 定义见 `contracts/clarification_structured_v1.json`。

### Widget 类型映射

| `input_type` | 对应 `clarification_type` | 前端行为 |
|---|---|---|
| `text` | `missing_info`, `ambiguous_requirement` | 文本输入框 + 提交按钮 |
| `single_choice` | `approach_choice`, `suggestion` | 选项按钮组 (+ "其他…" 自由输入) |
| `multi_choice` | `approach_choice` (多选) | 复选框组 + 提交按钮 |
| `confirmation` | `risk_confirmation` | 红色警告框 + ✅ 确认 / ❌ 取消 |

## 启动流程

1. **boot.py 注册**：在 `_EXTENSIONS` 列表中新增 `("human_intervention", False)` 条目
2. **startup.py**：`install_human_intervention()` 调用 `patch._inject_human_intervention_middleware()`
3. **patch.py**：通过 `@wraps` 包装 `_build_middlewares`，用 `isinstance` 替换 `ClarificationMiddleware` 实例
4. **运行时**：每次 `_build_middlewares` 被调用时，自动注入增强版中间件

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
| Kill switch 文件存在 | `touch .deer-flow/extensions/human_intervention.disabled` |

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
```
