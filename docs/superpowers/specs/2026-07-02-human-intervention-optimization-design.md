# 人工介入功能优化设计方案

> 对标文档：`docs/plans/human-intervention-design-standards.md`
> 设计准则：最少惊扰 / 渐进式披露 / 选择优于输入
> 架构原则：零侵入扩展，所有改动限扩展目录
> 审查记录：13 轮 grill-me（OpenAI/Anthropic/LangChain/Slack/Adaptive Cards 标准对标）

---

## 一、背景与目标

### 1.1 当前状态

DeerFlow 人工介入扩展（`deerflow_extensions/human_intervention/` + `frontend/extensions/human-intervention/`）为 AI Agent 的 `ask_clarification` 流程提供交互式 UI：

| 已实现 | 缺失（对标业界标准） |
|--------|---------------------|
| ✅ 纯选择模式（button group） | ❌ 选择+输入组合模式（Slack Block Kit 对标） |
| ✅ 纯输入模式（textarea） | ❌ 渐进式多轮澄清（Nielsen Norman Progressive Disclosure） |
| ✅ 基础确认对话框（✓/✗） | ❌ 风险分级确认（语义确认替代倒计时） |
| ✅ Clarification Gate（async） | ❌ Sync 路径 Gate 覆盖 |
| ✅ 结构化 _clarification 数据 | ❌ multi_choice 后端从未生成 |
| ✅ 三层防御体系 | ❌ Kill Switch 声明但未执行 |
| ❌ — | ❌ 澄清策略（max_per_turn/cooldown/timeout）声明但未执行 |

### 1.2 目标

1. 补齐设计标准文档（`human-intervention-design-standards.md`）第五章指出的三条最务实增强路径
2. 修复结构性安全缺口（Kill Switch、Sync Gate、Rate Limiter）
3. 全部改动**零新增侵入点**，维持 Level 1/2 扩展模式

---

## 二、方案总览

### 2.1 优先级矩阵

| 优先级 | 编号 | 优化项 | 改动量 | 新增侵入点 |
|--------|------|--------|--------|-----------|
| 🔴 P0 | ⑤ | Kill Switch 生效 | `startup.py` +3行 | 0 |
| 🔴 P0 | ⑦ | Sync 路径 Gate 覆盖 | `clarification_middleware_ext.py` +20行 | 0 |
| 🔴 P0 | ⑥ | 澄清策略执行 | 新文件 `rate_limiter.py` + middleware 集成 | 0 |
| 🟡 P1 | ③ | 风险确认增强（语义确认） | `ConfirmWidget.tsx` + `clarification_middleware_ext.py` | 0 |
| 🟡 P1 | ② | 渐进式多轮澄清 | `patch.py` Prompt 注入 + middleware 去重 | 0 |
| 🟡 P1 | ① | 选择+输入组合模式 | `ChoiceButtonsWidget.tsx` + `clarification_middleware_ext.py` | 0 |
| 🟢 P2 | ⑨ | multi_choice 补全 | `_infer_widget_hints` +1行映射 | 0 |
| 🟢 P2 | ④ | Schema 统一（双字段过渡） | `contracts/` + `_build_clarification_structured` | 0 |
| 🟢 P2 | ⑧ | data_collection 依赖封装 | `clarification_middleware_ext.py` 内部方法 | 0 |

### 2.2 边界防御补丁（grill-me 新增）

| 编号 | 补丁 | 改动 |
|------|------|------|
| 🔧H1 | 选项硬截断（max 50） | `_normalize_options` |
| 🔧H2 | CustomEvent 回执确认 | `ClarificationProvider.tsx` + `hooks.ts` |
| 🔧H3 | 倒计时清理（visibilitychange + unmount） | `ConfirmWidget.tsx`（如保留计时器场景） |
| 🔧H4 | key 去重（`${option}-${index}` fallback） | `ChoiceButtonsWidget.tsx` |

---

## 三、详细设计

---

### 🔴 P0-⑤：Kill Switch 生效

**问题**：`extension_manifest.json` 定义了 `kill_switch.file_marker: ".deer-flow/extensions/human_intervention.disabled"`，但 `startup.py` 从未检查。

**方案**：

- 文件：`deerflow_extensions/human_intervention/startup.py`
- 在 `install_human_intervention()` 开头增加：

```python
import os

def install_human_intervention():
    global _installed
    if _installed:
        return

    # Kill switch check
    project_root = _resolve_project_root()
    if project_root:
        marker = os.path.join(project_root, ".deer-flow", "extensions", "human_intervention.disabled")
        if os.path.exists(marker):
            _logger.info("[HumanIntervention] Kill switch active, skipping install")
            return

    # ... existing install logic
```

- 需要从 `boot.py` 复用 `_resolve_project_root()` 逻辑（或改为从环境变量 `DEERFLOW_PROJECT_ROOT` 读取）
- **降级**：文件不存在 → 正常安装；路径解析失败 → 记录 warn 日志，继续安装（Fail-Open，宁可安装不可用的扩展，也不因路径问题永久禁用）

**验证**：
```bash
touch .deer-flow/extensions/human_intervention.disabled
# 重启服务，检查日志应显示 "Kill switch active, skipping install"
rm .deer-flow/extensions/human_intervention.disabled
# 重启服务，扩展恢复正常
```

---

### 🔴 P0-⑦：Sync 路径 Gate 覆盖

**问题**：`HumanInterventionClarificationMiddleware` 只 override 了 `awrap_model_call`（async），未 override `wrap_model_call`（sync）。sync 路径上的 LLM 响应完全绕过 Clarification Gate。

**方案**：

- 文件：`deerflow_extensions/human_intervention/clarification_middleware_ext.py`
- 提取公共检测逻辑为 `_apply_clarification_gate(response)` 方法（纯 CPU 文本解析，无 I/O）
- 新增 `wrap_model_call(self, request, handler)` override，调用同一逻辑

```python
def _apply_clarification_gate(self, response):
    """Shared gate logic for sync and async paths."""
    try:
        if not response or not response.result:
            return response
        ai_msg = response.result[0]
        if not isinstance(ai_msg, AIMessage):
            return response

        existing_tcs = getattr(ai_msg, 'tool_calls', None) or []
        if any(tc.get('name') == 'ask_clarification' for tc in existing_tcs):
            # Still clear content if it contains duplicate question text
            text = getattr(ai_msg, 'content', '') or ''
            if isinstance(text, str) and self._detect_inline_clarification(text):
                ai_msg.content = ''
            return response

        text = getattr(ai_msg, 'content', '') or ''
        q_result = self._detect_inline_clarification(text)
        if not q_result:
            return response

        question, options = q_result
        new_tc = {
            'name': 'ask_clarification',
            'args': {
                'question': question,
                'clarification_type': 'missing_info',
                'options': options or [],
            },
            'id': f'clarification-gate-{hash(question) & 0xFFFFFFFF:x}',
            'type': 'tool_call',
        }
        ai_msg.tool_calls = (existing_tcs or []) + [new_tc]
        ai_msg.content = ''
    except Exception:
        logger.exception('[Clarification Gate] Error in gate logic')
    return response

def wrap_model_call(self, request, handler):
    """Sync version — mirrors awrap_model_call."""
    response = handler(request)
    return self._apply_clarification_gate(response)

async def awrap_model_call(self, request, handler):
    """Async version — existing logic, refactored to use _apply_clarification_gate."""
    response = await handler(request)
    return self._apply_clarification_gate(response)
```

**降级**：任何异常 → 透传原始 response。Fail-Closed：宁可漏一次澄清，也不误拦截正常回复。

---

### 🔴 P0-⑥：澄清策略执行

**问题**：`extension_manifest.json` 定义了 `clarification_policy`（max_per_turn: 3, cooldown_seconds: 30, timeout_minutes: 5），但无代码执行。

**方案**：

- 新文件：`deerflow_extensions/human_intervention/rate_limiter.py`

```python
"""In-memory clarification rate limiter."""

import time
import threading
import logging

logger = logging.getLogger(__name__)

class ClarificationRateLimiter:
    """Thread-safe in-memory rate limiter for clarification requests."""

    def __init__(self, max_per_turn: int = 3, cooldown_seconds: float = 30.0):
        self.max_per_turn = max_per_turn
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        # thread_id → {"count": int, "last_ts": float}
        self._state: dict[str, dict] = {}

    def allow(self, thread_id: str) -> bool:
        """Check if a new clarification is allowed for this thread."""
        with self._lock:
            now = time.time()
            entry = self._state.get(thread_id)
            if entry is None:
                self._state[thread_id] = {"count": 1, "last_ts": now}
                return True
            # Cooldown check
            if now - entry["last_ts"] < self.cooldown_seconds:
                return False
            # Max per turn check
            if entry["count"] >= self.max_per_turn:
                # Reset count if cooldown has passed
                if now - entry["last_ts"] >= self.cooldown_seconds * 2:
                    entry["count"] = 1
                    entry["last_ts"] = now
                    return True
                return False
            entry["count"] += 1
            entry["last_ts"] = now
            return True

    def cleanup_thread(self, thread_id: str):
        """Remove state for a completed/archived thread."""
        with self._lock:
            self._state.pop(thread_id, None)
```

- 集成点：`clarification_middleware_ext.py`

在 `__init__` 中读取 manifest policy 并初始化 limiter；在 `awrap_model_call`/`wrap_model_call` 中 Gate 检测到内联问题后、注入 tool_call **之前**检查 limiter。超限时：
  - **不注入 ask_clarification**（避免中断）
  - **不清空 AIMessage.content**（保留 LLM 原始文本，用户仍可阅读）
  - 记录 warn 日志

**降级**：limiter 初始化失败或状态异常 → 允许所有（Fail-Open，不影响正常功能）。

**存储**：纯进程内 `dict + threading.Lock`，不引入 Redis/DB 等外部依赖。

**前端 timeout**：`ClarificationWidget` 挂载时启动 `setTimeout(5 * 60 * 1000)`，到期自动 dismiss。`useEffect` cleanup 清除计时器。`visibilitychange` 事件暂停计时器。

---

### 🟡 P1-③：风险确认增强（语义确认）

**grill-me 推翻原"倒计时"方案**。理由：
- 倒计时惩罚正常用户（违反"选择优于输入"效率原则）
- Slack/Adaptive Cards 危险操作用 `confirm` dialog + 文本二次确认，而非计时器
- 倒计时提供虚假安全感（用户可能在计时期间分心）

**修正方案——语义确认分级**：

| risk_level | 视觉 | 确认方式 |
|------------|------|---------|
| `low` | 蓝色 info 框 | LLM 直接执行，无需确认 |
| `medium` | 黄色 warning 框 | 单次点击确认（现有 ConfirmWidget） |
| `high` | 红色 danger 框 | **输入确认短语**（如输入 "DELETE" 确认删除） |
| `critical` | 红色 pulse 框 | **确认短语 + 倒计时 5s 双重保障**（仅极端场景） |

**后端改动**：

- `_build_clarification_structured()` 增加 `risk_level` 字段读取（从 `args` 或从 `clarification_type === "risk_confirmation"` 推断默认 `medium`）
- `_infer_widget_hints()` 增加 `risk_level` 到 widget_hints

**前端改动**：

- `ConfirmWidget.tsx` 按 `risk_level` 渲染不同 UI
- `high` 等级：增加 `<input>` 须输入确认短语（如"DELETE"），按钮 disabled 直到文本匹配
- `critical` 等级：确认短语 + 5s 倒计时（仅此场景用计时器，且必须双重条件）
- `WidgetHints` 类型增加 `risk_level?: "low" | "medium" | "high" | "critical"`

**降级**：`risk_level` 缺失 → 默认 `medium`（常规确认行为）；确认短语匹配失败 → 按钮保持 disabled。

---

### 🟡 P1-②：渐进式多轮澄清

**grill-me 发现**：当前 Prompt 只有形式约束（"必须走 ask_clarification"），缺策略引导。LLM 仍可能一次抛出多个问题。

**修正方案——双层保障**：

**Layer 1：策略化 Prompt 注入**

- 文件：`deerflow_extensions/human_intervention/patch.py`
- `_CLARIFICATION_OVERRIDE_SECTION` 增加渐进式策略指令：

```python
_CLARIFICATION_OVERRIDE_SECTION = """
<clarification_skill_override>
**渐进式澄清原则：**
1. 每次只提 1 个问题（questions_per_turn=1），禁止批量列出多个无关问题
2. 优先问能最大程度缩小后续决策空间的问题
   - 例如：先问"部署到哪个环境？"再问"staging 的哪个分支？"
   - 不要先问"偏好什么颜色？"——这不会缩小任何决策空间
3. 如果用户的上轮回答已消除歧义，下一轮问题必须更聚焦
4. options 最多 5 个；超过 5 个启用 allow_custom: true
5. 如果用户的回答已足够完成任务，不要再追问
</clarification_skill_override>
"""
```

**Layer 2：中间件相似问题去重**

- `clarification_middleware_ext.py` 维护最近 N 轮（N=5）的 question 关键词集合
- `_has_recent_similar_question(question)` → 计算当前 question 的关键词（长度≥2的中文词组）与历史集合的交集比率，≥ 70% 视为重复 → 跳过本次 Gate 注入（不清空 content，保留原始文本）

**降级**：去重逻辑异常 → 允许所有（Fail-Open）。

---

### 🟡 P1-①：选择+输入组合模式

**对标**：Slack Block Kit `static_select` + `plain_text_input` 同块共存；OpenAI `anyOf [enum, string]`

**后端改动**：

- `_build_clarification_structured()` 读取 `allow_custom` 参数
- `_infer_widget_hints()` 当 `allow_custom=True` 时设置 `allow_custom: true`
- `_normalize_options()` 硬截断上限 50（grill-me H1）

**LLM 用法**：
```python
ask_clarification(
    question="选择部署环境",
    options=["staging", "production", "development"],
    allow_custom=True
)
```

**前端改动**：

- `ChoiceButtonsWidget.tsx`：
  - 如果 `widget_hints.allow_custom === true`，选项列表末尾渲染「其他/自定义…」按钮
  - 点击展开 `<textarea>` + 独立的"提交自定义"按钮
  - 展开时输入框使用 `position: sticky; bottom: 0`（移动端友好）
  - key 去重：`key={option || \`option-${index}\`}`（grill-me H4）
- `WidgetHints` 类型增加 `allow_custom?: boolean`

**降级**：`allow_custom` 不传 → 行为与现在完全一致（纯按钮选择）。

---

### 🟢 P2-⑨：multi_choice 补全

**问题**：`_infer_widget_hints()` 有 options 时只映射 `single_choice`，从不映射 `multi_choice`。

**后端改动**：

- `_infer_widget_hints()` 检查 `multi_select: true` → 映射 `multi_choice`
- `ask_clarification` 参数增加 `multi_select: bool = False`

**LLM 用法**：
```python
ask_clarification(
    question="选择需要启用的功能",
    options=["邮件通知", "短信通知", "Webhook", "企业微信"],
    multi_select=True
)
```

**前端**：`ClarificationWidget.tsx` L96-98 已有 `multi_choice` case，无需改动。

---

### 🟢 P2-④：Schema 统一（双字段过渡）

**问题**：contract JSON `widget_hint`（单数）vs 代码 `widget_hints`（复数）

**修正**：

- 契约 `clarification_structured_v1.json`：单数字段改复数，同步 enum 补 `multi_choice`
- `_build_clarification_structured()`：**双字段输出过渡期**——同时写 `widget_hint`（旧）和 `widget_hints`（新），前端优先读 `widget_hints` 降级 `widget_hint`
- 补上必填字段：`type: "clarification"`、`id: tool_call_id`
- 契约移除代码未实现的 `required: ["policy"]`

**过渡期结束后（v2）**：移除 `widget_hint` 旧字段。

---

### 🟢 P2-⑧：data_collection 依赖封装

**grill-me 结论**：当前 `try/except import` 已做到三层保护，事件钩子过度设计。不做架构变更，仅封装为内部方法提升可读性。

```python
def _emit_clarification_event(self, structured: dict):
    """Emit clarification event for monitoring/collection. Best-effort."""
    try:
        from deerflow_extensions.data_collection.collector import get_collector
        collector = get_collector()
        collector.record("clarification_triggered", {
            "clarification_type": structured.get("clarification_type"),
            "question": structured.get("question", ""),
            "options_count": len(structured.get("options", [])),
        })
    except Exception:
        pass  # Silent fallback
```

---

### 🔧 边界防御补丁

#### H1：选项硬截断

- `_normalize_options()` 增加 `max_options: int = 50`
- 超长时截断 + 末尾追加 `"…及其他 N 项"` 提示
- 记录 warn 日志（标明被截断的 thread_id）

#### H2：CustomEvent 回执确认

- `ClarificationProvider.submitClarification()` 派发后 3 秒内未收到 `clarification:ack` → 恢复状态 + toast 错误提示
- `hooks.ts` 监听器收到事件后派发 `clarification:ack`
- `threadId` guard：仅在 threadId 可用时注册监听器

#### H3：倒计时清理

- 仅 `critical` 风险等级使用倒计时
- `useEffect` cleanup 清除 `setInterval`/`setTimeout`
- `document.visibilitychange` 暂停/恢复倒计时

#### H4：key 去重

- `ChoiceButtonsWidget` 的 `key` 改为 `${option || 'option'}-${index}`，防空串和重复值

---

## 四、侵入点审计

### 4.1 现有侵入点（不变）

| 编号 | 文件 | 行号 | 内容 |
|------|------|------|------|
| C1 | `frontend/src/app/workspace/workspace-content.tsx` | L10, L35, L44 | ClarificationProvider 导入与包裹 |
| C2 | `frontend/src/app/workspace/chats/[thread_id]/page.tsx` | L7, L123 | useClarificationSubmit hook 导入与调用 |
| C3 | `frontend/src/components/workspace/messages/message-list.tsx` | L43, L322-339 | ClarificationWidget 导入与条件渲染 |

### 4.2 新增侵入点

**零。** 全部 9 项优化 + 4 项边界补丁均在扩展目录内完成。

### 4.3 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `deerflow_extensions/human_intervention/startup.py` | 修改 | Kill Switch 检查 |
| `deerflow_extensions/human_intervention/clarification_middleware_ext.py` | 修改 | Sync Gate + rate_limiter 集成 + 去重 + multi_choice + allow_custom + 选项截断 + 事件封装 |
| `deerflow_extensions/human_intervention/patch.py` | 修改 | 策略化 Prompt 注入 |
| `deerflow_extensions/human_intervention/rate_limiter.py` | **新建** | 澄清速率限制器 |
| `deerflow_extensions/human_intervention/contracts/clarification_structured_v1.json` | 修改 | Schema 双字段统一 |
| `frontend/extensions/human-intervention/ClarificationProvider.tsx` | 修改 | 回执确认 |
| `frontend/extensions/human-intervention/ClarificationWidget.tsx` | 修改 | 无需改动（已支持 multi_choice） |
| `frontend/extensions/human-intervention/widgets/ChoiceButtonsWidget.tsx` | 修改 | allow_custom + key 去重 |
| `frontend/extensions/human-intervention/widgets/ConfirmWidget.tsx` | 修改 | risk_level 分级 + 语义确认 |
| `frontend/extensions/human-intervention/hooks.ts` | 修改 | 回执确认 + threadId guard |
| `frontend/extensions/human-intervention/types.ts` | 修改 | risk_level + allow_custom |

---

## 五、降级与废弃

### 5.1 降级路径总表

| 组件 | 异常场景 | 降级行为 |
|------|---------|---------|
| Kill Switch 检查 | 路径解析失败 | 继续安装（warn 日志） |
| Sync Gate | 任何异常 | 透传原始 response |
| Rate Limiter | 初始化失败/状态损坏 | 允许所有（Fail-Open） |
| 去重逻辑 | 任何异常 | 允许所有 |
| 语义确认 | 确认短语匹配失败 | 按钮保持 disabled |
| CustomEvent | 无 ack / threadId 缺失 | 恢复状态 + toast 提示 |
| Schema 版本 | 前端收到未知版本 | 尽力降级 + Markdown 渲染 |
| data_collection | ImportError / record 失败 | 静默跳过 |

### 5.2 废弃成本

每项优化未来删除时：
- 回滚对应扩展文件
- 删除 `rate_limiter.py`（唯一新文件）
- **无需修改 C1/C2/C3 任何侵入点**
- 预估时间：≤ 5 分钟 / 项

### 5.3 上游兼容性

当 DeerFlow 官方实现原生交互式人工介入时：
- **后端探测**：`hasattr(ClarificationMiddleware, 'native_clarification_ui')` → 跳过 patch
- **前端探测**：检查消息 `additional_kwargs.interactive_ui` → 跳过 Widget 渲染
- **Kill Switch**：`touch .deer-flow/extensions/human_intervention.disabled` 一键禁用

---

## 六、验证计划

### 6.1 单元测试覆盖

| 测试对象 | 测试场景 |
|---------|---------|
| `_detect_inline_clarification` | 中文问号/英文问号/无问号/无关键词/多问句取最后一句/选项含问号过滤 |
| `_normalize_options` | 空数组/null/超长（>50）/含特殊字符/含 emoji/含重复值 |
| `ClarificationRateLimiter` | 正常允许/cooldown 拒绝/max_per_turn 拒绝/cooldown 过期恢复/cleanup |
| `_has_recent_similar_question` | 完全匹配/关键词交集 ≥70%/完全不匹配 |
| `ConfirmWidget` | medium 直接确认/high 确认短语匹配/high 确认短语不匹配/critical 双重保障 |

### 6.2 Browser-Use 自动化 E2E 测试（≥20 案例）

> 工具：browser-use MCP（项目唯一浏览器自动化工具）
> 目标：覆盖全部 9 项优化的端到端用户交互链路
> 前置条件：`bash scripts/start-deerflow.sh` 启动全栈服务

#### 6.2.1 Kill Switch & 降级（案例 1-3）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 1 | **Kill Switch 禁用扩展** | ① `touch .deer-flow/extensions/human_intervention.disabled`<br>② 重启服务<br>③ 发送触发澄清的 prompt（如"帮我选一个部署方案"） | LLM 回复为纯文本 Markdown，无交互 Widget 渲染；日志含 "Kill switch active" |
| 2 | **移除 Kill Switch 恢复** | ① `rm .deer-flow/extensions/human_intervention.disabled`<br>② 重启服务<br>③ 发送同一 prompt | Widget 正常渲染，按钮可点击提交 |
| 3 | **Schema 未知版本降级** | ① Mock 后端返回 `_schema: "deerflow/clarification/v99"`<br>② 前端收到消息 | Widget 不渲染，降级为 MarkdownContent 纯文本 |

#### 6.2.2 选择+输入组合模式（案例 4-7）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 4 | **allow_custom 按钮组渲染** | ① 发送 prompt 触发 `allow_custom: true` 的澄清<br>② 观察 Widget | 选项按钮组 + 末尾「其他/自定义…」按钮 |
| 5 | **点击自定义展开输入框** | ① 点击「其他/自定义…」按钮 | `<textarea>` 展开，提交按钮出现 |
| 6 | **自定义文本提交** | ① 在展开的 textarea 输入 "我的自定义方案"<br>② 点击提交 | 消息成功发送，Agent 继续执行；消息内容为 "我的自定义方案" |
| 7 | **allow_custom=false 无自定义按钮** | ① 发送 prompt 触发 `allow_custom: false` 的澄清 | 仅选项按钮组，无「其他…」按钮 |

#### 6.2.3 风险确认增强（案例 8-12）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 8 | **medium 风险直接确认** | ① 触发 `risk_level=medium` 的澄清<br>② 点击 ✅ 确认 | 黄色 warning 框，确认后 Agent 继续 |
| 9 | **high 风险需输入确认短语** | ① 触发 `risk_level=high, confirm_phrase="DELETE"` 澄清<br>② 不输入直接点确认 | 确认按钮 disabled |
| 10 | **high 风险正确输入后确认** | ① 输入 "DELETE"<br>② 点击确认 | 按钮 enabled，确认后 Agent 继续 |
| 11 | **high 风险错误输入** | ① 输入 "delete"（大小写不符）<br>② 点击确认 | 确认按钮 disabled（严格匹配） |
| 12 | **critical 双重保障** | ① 触发 `risk_level=critical` 澄清<br>② 观察 UI | 红色 pulse 框 + 5s 倒计时 + 确认短语输入，倒计时结束前确认 disabled |

#### 6.2.4 渐进式多轮澄清（案例 13-16）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 13 | **单轮单问题** | ① 发送复杂 prompt（如"帮我部署并配置监控"）<br>② 观察 LLM 回复 | 仅 1 个澄清 Widget，非批量多个 |
| 14 | **多轮逐步缩小** | ① 第 1 轮选择 "production"<br>② 观察第 2 轮问题 | 第 2 轮问题聚焦于 production 的子选项（如"哪个 region？"） |
| 15 | **相似问题去重** | ① 连续发送两次相同 prompt<br>② 观察第 2 轮 | 第 2 轮不重复渲染相同/高度相似问题 |
| 16 | **已回答不再追问** | ① 在澄清中提供足够信息<br>② 观察下一轮 | Agent 直接执行任务，不追加无意义澄清 |

#### 6.2.5 速率限制与边界（案例 17-22）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 17 | **max_per_turn 限流** | ① 30s 内触发 4 次澄清<br>② 观察第 4 次 | 第 4 次降级为纯文本（不清空 content），无 Widget |
| 18 | **cooldown 阻断** | ① 提交一次澄清后 20s 内再触发 | 第二次降级纯文本（30s cooldown 内） |
| 19 | **cooldown 过期恢复** | ① 提交澄清后等待 35s<br>② 再次触发 | Widget 正常渲染（cooldown 已过） |
| 20 | **timeout 自动 dismiss** | ① Widget 渲染后等待 5 分钟（或配置较短 timeout）<br>② 观察 | Widget 自动消失，Agent 继续执行（发送默认跳过消息） |
| 21 | **选项超长截断（>50）** | ① Mock 后端返回 60 个 options<br>② 观察 Widget | 仅渲染前 50 个 + "…及其他 10 项" 提示 |
| 22 | **CustomEvent 回执确认** | ① 模拟 sendMessage 失败（网络断开）<br>② 点击确认按钮 | 3s 后恢复 Widget 状态 + toast 错误提示 |

#### 6.2.6 综合场景（案例 23-25）

| # | 测试案例 | 操作步骤 | 验证点 |
|---|---------|---------|--------|
| 23 | **全链路：选择+自定义→确认→执行** | ① 选择预设选项<br>② 切换到自定义输入<br>③ 提交<br>④ 观察 Agent 行为 | Agent 收到答案后正确继续执行，无卡死 |
| 24 | **页面导航后 Widget 状态** | ① Widget 渲染中<br>② 切换到另一个 thread<br>③ 再切回原 thread | Widget 状态保持（或正确降级为已回复状态） |
| 25 | **多 Tab 并发澄清** | ① 两个 Tab 同时打开同一 thread<br>② Tab A 提交澄清<br>③ 观察 Tab B | Tab B 的 Widget 自动 dismiss（已回复） |

> **总计：25 个 browser-use E2E 测试案例。**

### 6.3 集成测试

| 场景 | 预期 |
|------|------|
| Kill Switch marker 文件存在 | 扩展不加载 |
| Sync 路径内联提问 | Gate 注入 ask_clarification |
| 30s 内连续 4 次澄清 | 第 4 次降级纯文本 |
| allow_custom 选择 | 按钮组 +「其他…」正常渲染 |
| risk_level=high 确认 | 输入框 disabled 直到匹配确认短语 |

---

## 七、grill-me 记录

| 路线 | 轮数 | 对标标准 | 关键发现 |
|------|------|---------|---------|
| A: 设计合规 | 4 | OpenAI/Anthropic/LangChain/Slack/NNG | 倒计时确认不适合、Prompt 缺策略引导、组合模式是空壳 |
| B: 零侵入架构 | 4 | DeerFlow 三层扩展模式 | 全部 Level 1/2、事件钩子过度设计、废弃成本 ≤5min/项 |
| C: 边界极端 | 5 | 最少惊扰/Fail-Closed/认知负荷 | Kill Switch 未执行、Sync Gate 结构性盲区、CustomEvent 竞态 |

**总计：13 轮，覆盖 9 项优化 × 3 维度审查。**

---

## 八、文档同步计划

> 每项优化落地后必须同步更新以下文档，确保代码与文档 100% 一致。

### 8.1 同步矩阵

| 优化项 | 需同步文档 | 同步内容 |
|--------|-----------|---------|
| ⑤ Kill Switch | `extension_manifest.json`、`startup.py` 注释 | kill_switch 字段验证说明 |
| ⑦ Sync Gate | `clarification_middleware_ext.py` docstring、`README.md` | 三层防御体系更新（新增 sync 路径说明） |
| ⑥ Rate Limiter | `rate_limiter.py` docstring、`README.md`、`extension_manifest.json` | 策略执行模块说明、policy 字段验证 |
| ③ 风险确认 | `README.md`（前后端）、`contracts/clarification_structured_v1.json` | risk_level 分级说明、ConfirmWidget 语义确认文档 |
| ② 渐进式澄清 | `patch.py` 注释、`README.md` | 策略化 Prompt 内容、去重逻辑说明 |
| ① 组合模式 | `README.md`（前后端）、`types.ts` 注释 | allow_custom 参数文档、ComboWidget 行为说明 |
| ⑨ multi_choice | `README.md`、`contracts/clarification_structured_v1.json` | multi_select 参数文档 |
| ④ Schema 统一 | `contracts/clarification_structured_v1.json` | 双字段过渡期说明、迁移计划 |
| ⑧ 依赖封装 | `clarification_middleware_ext.py` 注释 | `_emit_clarification_event()` 方法文档 |

### 8.2 核心文档清单

| 文档 | 路径 | 同步时机 | 责任人 |
|------|------|---------|--------|
| **后端扩展 README** | `deerflow_extensions/human_intervention/README.md` | 每项后端改动完成后 | WING |
| **前端扩展 README** | `frontend/extensions/human-intervention/README.md` | 每项前端改动完成后 | WING |
| **后端契约 Schema** | `deerflow_extensions/human_intervention/contracts/clarification_structured_v1.json` | Schema 变更时 | WING |
| **扩展 manifest** | `deerflow_extensions/human_intervention/extension_manifest.json` | kill_switch/policy 变更时 | WING |
| **根 CLAUDE.md** | `CLAUDE.md`（项目根） | 功能发布后更新插件条目 | WING |
| **后端 CLAUDE.md** | `backend/CLAUDE.md` | 后端架构级变更时 | WING |
| **前端 CLAUDE.md** | `frontend/CLAUDE.md` | 前端架构级变更时 | WING |
| **变更记录** | `docs/changelog/code_change_summary/` | 任何核心源码改动时 | WING |
| **补丁记录** | `docs/patches/` | Level 2/3 侵入点变更时 | WING |

### 8.3 同步检查清单

实施完成后逐项核查：

- [ ] 后端 README 的「功能概述」章节是否覆盖所有新增能力
- [ ] 后端 README 的「Widget 类型映射」表是否包含 multi_choice / risk_level
- [ ] 前端 README 的「Widget 类型」表是否包含 risk_level 分级行为
- [ ] 前端 README 的「使用方式」代码示例是否与实现一致
- [ ] `extension_manifest.json` 的 `clarification_policy` 字段是否与 `rate_limiter.py` 默认值一致
- [ ] 契约 JSON 的 `widget_hints` enum 是否包含 `multi_choice`
- [ ] `CLAUDE.md` 中 human_intervention 插件条目是否反映最新能力
- [ ] `docs/changelog/` 是否记录了所有核心源码改动
- [ ] 前后端 README 的「降级策略」表是否覆盖新增降级路径
- [ ] 前后端 README 的「验证命令」是否可正常执行

### 8.4 自动化文档验证

```bash
# 验证后端 README 覆盖所有优化项
grep -c "kill.switch\|rate.limiter\|risk_level\|allow_custom\|multi_select\|渐进式" \
  deerflow_extensions/human_intervention/README.md
# 预期：≥ 6 次命中

# 验证前端 README 覆盖所有 Widget 类型
grep -c "risk_level\|allow_custom\|multi_choice\|ComboWidget" \
  frontend/extensions/human-intervention/README.md
# 预期：≥ 4 次命中

# 确认契约 JSON 字段与代码一致
python3 -c "
import json
with open('deerflow_extensions/human_intervention/contracts/clarification_structured_v1.json') as f:
    c = json.load(f)
assert 'widget_hints' in str(c), 'Missing widget_hints in contract'
print('OK: Contract aligned')
"

# 确认 CLAUDE.md 插件条目最新
grep -A2 'human_intervention' CLAUDE.md | head -5
```

---

## 九、参考

- `docs/plans/human-intervention-design-standards.md` — 人工介入设计参考标准
- `docs/methodology/零侵入扩展方法论.md` — 零侵入扩展原则
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Anthropic Tool Use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- LangGraph HITL: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/
- Slack Block Kit: https://api.slack.com/block-kit
- Nielsen Norman — Progressive Disclosure & Recognition over Recall

---

> **署名：WING**
> **日期：2026-07-02**
