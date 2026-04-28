# DeerFlow 蒸馏数据采集体系设计

> **WING** 2026-04-28
>
> 聚焦于DeerFlow全链路数据采集，为未来蒸馏训练储备海量高质量业务数据。
> 不涉及小模型训练、部署、推理。

---

## 一、设计目标与原则

### 1.1 核心目标

在**不改动DeerFlow现有业务逻辑**的前提下，零侵入采集全链路LLM推理数据，沉淀海量高质量业务样本，为未来蒸馏私有化小模型提供充足弹药。

### 1.2 量化目标

| 指标 | 目标 | 说明 |
|------|------|------|
| **日均采集量** | ≥10,000条完整样本 | 每条样本含完整推理链路 |
| **周均沉淀量** | ≥50,000条清洗后样本 | 去重过滤后可用数据 |
| **数据多样性覆盖** | ≥10种MCP工具调用场景 | 覆盖ADS/RAGFlow/DataCenter等 |
| **数据质量** | ≤1% 脏数据 | 缺失字段、格式异常严格控制 |
| **采集性能损耗** | ≤5ms/请求 | 异步旁路，不阻塞主流程 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **零侵入** | 不修改现有Agent执行逻辑、不修改MCP调用流程、不修改中间件行为 |
| **全链路** | 覆盖Agent输入→思考→工具调用→模型输出的完整推理闭环 |
| **可溯源** | 每条样本关联唯一session_id，支持回溯原始会话 |
| **即插即用** | 采集数据直接适配LlamaFactory训练格式，无需二次转换 |
| **增量累积** | 每日增量追加，按月归档，支持持续数据沉淀 |

---

## 二、数据采集全景架构

### 2.1 采集系统部署位置

```
DeerFlow LangGraph Runtime (Python 进程内)
         │
         ├── 用户输入 → [采集点1: Agent输入] → LLM调用 → [采集点2: 模型输出]
         │                                                  │
         │                                     LLM返回tool_calls
         │                                                  │
         ├── [采集点3: 工具调用请求] → MCP Tool执行 → [采集点4: 工具返回结果]
         │                                                  │
         ├── [采集点5: Agent中间状态] → 多轮推理循环 ...
         │
         ├── [采集点6: 最终回复输出] → 用户收到回复
         │
         ▼
    ┌─────────────────────────────────────────────┐
    │        旁路异步写入队列 (asyncio.Queue)        │
    │         ┌──────────────────────┐             │
    │         │  内存缓冲区 500条      │  批量刷盘    │
    │         │  或 5秒间隔触发写入     │ ──────►    │
    │         └──────────────────────┘             │
    └──────────────────────┬──────────────────────┘
                           │
                           ▼
    ┌─────────────────────────────────────────────┐
    │           本地日志文件系统                      │
    │  /data/deerflow/training_logs/               │
    │    ├── raw/          ← 原始日志（保留7天）      │
    │    ├── daily/        ← 按天归档JSONL           │
    │    └── archive/      ← 月度打包(.tar.gz)       │
    └─────────────────────────────────────────────┘
```

### 2.2 采集点总览（共6个标准采集点）

| 采集点 | 位置 | 触发时机 | 采集内容 | 数据量/次 |
|--------|------|---------|---------|----------|
| **P1: Agent输入** | `create_chat_model()` 调用前 | 用户提交消息 | user_query, system_prompt, 历史上下文, session_id | ~2KB |
| **P2: 模型输出** | LLM 流式响应完成后 | LLM返回完整响应 | raw_response, finish_reason, token_usage | ~1-10KB |
| **P3: 工具调用请求** | `ToolErrorHandlingMiddleware.wrap_tool_call()` | LLM决定调用工具 | tool_name, tool_params, call_id | ~1KB |
| **P4: 工具返回结果** | 工具执行完成后 | 工具返回结果 | tool_result, error_info, duration_ms | ~1-50KB |
| **P5: Agent中间状态** | 每轮Agent循环后 | 多轮推理每轮结束 | messages历史快照, step_number | ~2KB |
| **P6: 最终回复** | Agent执行结束 | 最终输出给用户 | final_response, user_satisfaction(可选) | ~1KB |

### 2.3 数据关联机制

```
session_id: "sess_20260428_a1b2c3d4"
    │
    ├── turn_001 (第1轮对话)
    │     ├── P1: agent_input
    │     ├── P2: model_output (含tool_calls)
    │     ├── P3: tool_call_request [tool="ads_client_list", params={}]
    │     ├── P4: tool_call_result [status=success, result={...}]
    │     ├── P2: model_output (基于工具结果生成最终回复)
    │     └── P6: final_response
    │
    └── turn_002 (第2轮对话，用户追问)
          ├── P1: agent_input (含历史上下文)
          ├── P2: model_output
          └── ...
```

---

## 三、详细采集点设计（代码级）

### 3.1 采集点P1: Agent输入

#### 3.1.1 部署位置

在 `lead_agent/agent.py` 的 `make_lead_agent()` 函数中，当Agent被调用时，LangGraph内部会执行`model.ainvoke(messages)`或`agent.astream()`。采集点位于用户消息进入Agent之后、LLM调用之前。

#### 3.1.2 最佳采集方式：利用中间件钩子

**✅ 推荐方案：新增DataCollectMiddleware**

利用DeerFlow已有的中间件链（`AgentMiddleware`），新增一个`DataCollectMiddleware`，通过`before_model`钩子采集输入、`after_model`钩子采集输出。

```python
# agents/middlewares/data_collect_middleware.py
class DataCollectMiddleware(AgentMiddleware):
    """零侵入数据采集中间件，旁路记录全链路推理数据。"""

    def __init__(self, collector: "TrainingDataCollector"):
        self.collector = collector

    def before_model(self, state: ThreadState) -> ThreadState:
        # 采集点P1: Agent输入
        messages = state.get("messages", [])
        if messages:
            self.collector.record_agent_input(
                session_id=state.get("session_id"),
                messages=messages,
                system_prompt=_extract_system_prompt(messages),
                user_query=_extract_last_user_message(messages),
                rag_context=_extract_rag_context(state),
            )
        return state

    def after_model(self, state: ThreadState) -> ThreadState:
        # 采集点P2: 模型输出
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "additional_kwargs"):
                self.collector.record_model_output(
                    session_id=state.get("session_id"),
                    response=last_msg.content if hasattr(last_msg, "content") else str(last_msg),
                    finish_reason=last_msg.additional_kwargs.get("finish_reason"),
                    tool_calls=last_msg.additional_kwargs.get("tool_calls", []),
                    token_usage=state.get("token_usage"),
                )
        return state

    def before_tool(self, state: ThreadState, tool_name: str, tool_input: dict) -> ThreadState:
        # 采集点P3: 工具调用请求
        self.collector.record_tool_call_request(
            session_id=state.get("session_id"),
            tool_name=tool_name,
            tool_params=tool_input,
        )
        return state

    def after_tool(self, state: ThreadState, tool_name: str, tool_output: Any) -> ThreadState:
        # 采集点P4: 工具返回结果
        self.collector.record_tool_call_result(
            session_id=state.get("session_id"),
            tool_name=tool_name,
            tool_result=tool_output,
            duration_ms=...,
        )
        return state
```

#### 3.1.3 采集数据Schema（JSONL格式）

```json
{
  "sample_type": "agent_input",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "create_time": "2026-04-28T10:30:00.000Z",
  "user_query": "帮我查一下今天哪些终端离线了",
  "system_prompt": "你是ADS智能运维助手，负责管理云桌面终端...\n\n可用工具：\n- ads_client_list: 获取终端列表\n- ads_client_show: 获取终端详情\n- ...",
  "history_context": [
    {"role": "user", "content": "早上好"},
    {"role": "assistant", "content": "早上好！我是ADS运维助手，有什么需要帮助的吗？"}
  ],
  "rag_context": "",
  "agent_config": {
    "model_name": "deepseek-api",
    "subagent_enabled": true,
    "thinking_enabled": false
  }
}
```

### 3.2 采集点P2: 模型输出（含工具调用）

#### 3.2.1 部署位置

`after_model`钩子中，当LLM返回响应后立即采集。

#### 3.2.2 采集数据Schema

```json
{
  "sample_type": "model_output",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "step_number": 1,
  "create_time": "2026-04-28T10:30:01.500Z",
  "raw_response": "我来查询终端列表...",
  "response_type": "tool_calls",
  "finish_reason": "tool_calls",
  "tool_calls": [
    {
      "tool_name": "ads_client_list",
      "call_id": "call_xyz123",
      "arguments": {
        "status": "offline"
      }
    }
  ],
  "token_usage": {
    "prompt_tokens": 2845,
    "completion_tokens": 156,
    "total_tokens": 3001
  },
  "thinking_content": "用户想查询离线终端，我需要先调用ads_client_list工具获取终端列表，并传入status=offline参数过滤...",
  "latency_ms": 2340
}
```

### 3.3 采集点P3+P4: 工具调用请求与结果

#### 3.3.1 部署位置

在 `ToolErrorHandlingMiddleware.wrap_tool_call()` 的前后包装。该中间件是DeerFlow中所有工具调用的统一入口。

#### 3.3.2 采集方式

利用`ToolErrorHandlingMiddleware`的`wrap_tool_call`方法，在工具执行前后插入采集逻辑：

```python
# 在 tool_error_handling_middleware.py 中增强
class ToolErrorHandlingMiddleware(AgentMiddleware):

    @override
    def wrap_tool_call(
        self,
        tool_call: ToolCall,
        handler: Callable[[ToolCall], ToolCallResult],
    ) -> ToolCallResult:
        # 采集点P3: 工具调用请求
        data_collector.record_tool_call_request(
            session_id=self._get_session_id(tool_call),
            tool_name=tool_call.name,
            tool_params=tool_call.args,
        )

        start_time = time.monotonic()
        result = handler(tool_call)  # 执行工具
        duration_ms = (time.monotonic() - start_time) * 1000

        # 采集点P4: 工具返回结果
        data_collector.record_tool_call_result(
            session_id=self._get_session_id(tool_call),
            tool_name=tool_call.name,
            tool_params=tool_call.args,
            tool_result=result.content if hasattr(result, 'content') else str(result),
            error=None if result.success else result.error,
            duration_ms=duration_ms,
        )

        return result
```

#### 3.3.3 采集数据Schema

**工具调用请求：**
```json
{
  "sample_type": "tool_call_request",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "step_number": 1,
  "create_time": "2026-04-28T10:30:01.600Z",
  "tool_name": "ads_client_list",
  "tool_params": {
    "status": "offline"
  },
  "call_id": "call_xyz123"
}
```

**工具返回结果：**
```json
{
  "sample_type": "tool_call_result",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "step_number": 1,
  "create_time": "2026-04-28T10:30:01.800Z",
  "tool_name": "ads_client_list",
  "tool_params": {
    "status": "offline"
  },
  "tool_result": {
    "code": 0,
    "message": "success",
    "data": [
      {"clientId": 101, "name": "教室A-终端1", "status": "offline", "lastOnline": "2026-04-28T08:00:00Z"},
      {"clientId": 102, "name": "教室A-终端2", "status": "offline", "lastOnline": "2026-04-28T09:15:00Z"}
    ]
  },
  "error": null,
  "duration_ms": 125,
  "tool_provider": "ads-mcp",
  "tool_type": "mcp"
}
```

### 3.4 采集点P5: Agent中间状态

#### 3.4.1 部署位置

在Agent多轮推理循环中，每轮结束时采集。通过中间件的`after_model`钩子在每轮LLM调用后触发。

#### 3.4.2 采集数据Schema

```json
{
  "sample_type": "agent_intermediate_state",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "step_number": 2,
  "total_steps": 3,
  "create_time": "2026-04-28T10:30:02.300Z",
  "message_count": 8,
  "accumulated_tokens": {
    "prompt_tokens": 4500,
    "completion_tokens": 320,
    "total_tokens": 4820
  },
  "tools_called_so_far": ["ads_client_list"],
  "pending_tool_calls": [], 
  "loop_detection_triggered": false
}
```

### 3.5 采集点P6: 最终回复

#### 3.5.1 部署位置

Agent执行结束，最终响应输出给用户时采集。可通过`ClarificationMiddleware`（中间件链最后一个）的`after_model`钩子捕获最终输出。

#### 3.5.2 采集数据Schema

```json
{
  "sample_type": "final_response",
  "session_id": "sess_a1b2c3d4",
  "turn_id": 1,
  "create_time": "2026-04-28T10:30:03.500Z",
  "final_response": "当前共有2台终端离线：\n1. 教室A-终端1（ID: 101，最后在线: 08:00）\n2. 教室A-终端2（ID: 102，最后在线: 09:15）\n\n是否需要我启动这些终端？",
  "total_duration_ms": 3500,
  "total_llm_calls": 2,
  "total_tool_calls": 1,
  "total_tokens": 5200,
  "subagent_invoked": false,
  "resolution_status": "completed"
}
```

---

## 四、完整样本聚合（蒸馏训练直接可用格式）

### 4.1 单样本聚合逻辑

将上述6个采集点的数据，按照 `session_id + turn_id` 聚合为一条完整蒸馏训练样本：

```
原始多采集点数据                 聚合后蒸馏样本
─────────────────              ─────────────────
P1: agent_input                ┌─────────────────┐
P2: model_output (step1)       │ messages: [      │
P3: tool_call_request           │   system_prompt,│
P4: tool_call_result            │   user_query,   │
P2: model_output (step2)       │   assistant(含   │
P6: final_response              │     tool_calls),│
                               │   tool_result,  │
                               │   final_response│
                               │ ]               │
                               └─────────────────┘
```

### 4.2 最终输出格式（直接适配LlamaFactory）

```jsonl
{"messages": [
  {"role": "system", "content": "你是ADS智能运维助手，负责管理云桌面终端...\n\n可用工具：\n- ads_client_list: 获取终端列表\n- ads_client_show: 获取终端详情\n- ..."},
  {"role": "user", "content": "帮我查一下今天哪些终端离线了"},
  {"role": "assistant", "content": "我来查询终端列表。", "tool_calls": [{"type": "function", "function": {"name": "ads_client_list", "arguments": {"status": "offline"}}}]},
  {"role": "tool", "tool_call_id": "call_xyz123", "content": "{\"code\":0,\"data\":[{\"clientId\":101,\"name\":\"教室A-终端1\",\"status\":\"offline\"},{\"clientId\":102,\"name\":\"教室A-终端2\",\"status\":\"offline\"}]}"},
  {"role": "assistant", "content": "当前共有2台终端离线：\n1. 教室A-终端1（ID: 101，最后在线: 08:00）\n2. 教室A-终端2（ID: 102，最后在线: 09:15）\n\n是否需要我启动这些终端？"}
]}
```

**格式说明**：
- 遵循OpenAI `messages` 格式，与LlamaFactory原生兼容
- 工具调用使用 `tool_calls` 字段，符合函数调用标准
- 工具结果使用 `role: "tool"` + `tool_call_id` 关联
- 无需任何格式转换即可直接投入训练

### 4.3 样本分类与元数据标记

每条聚合后的样本附带分类标签，用于训练时的数据配比和效果分析：

```json
{
  "messages": [...],
  "metadata": {
    "category": "agent_tool_call",       // rag_qa | agent_tool_call | compliance_reject | multi_turn
    "subcategory": "terminal_query",     // terminal_operation | knowledge_query | system_admin
    "tools_involved": ["ads_client_list"],
    "turn_count": 2,
    "tool_call_count": 1,
    "total_tokens": 5200,
    "has_thinking": false,
    "session_id": "sess_a1b2c3d4",
    "create_time": "2026-04-28T10:30:03.500Z",
    "model_name": "deepseek-api",
    "resolution_status": "completed"     // completed | error | interrupted | escalated_to_human
  }
}
```

### 4.4 数据配比目标（行业最佳实践）

基于业界Agent蒸馏数据经验，数据配比参考如下（但采集系统不限制配比，全量保存）：

| 样本类别 | 预期占比 | 最低周产量 | 说明 |
|---------|---------|-----------|------|
| **RAG知识问答** | 40-50% | 20,000条 | 用户查询知识库 → LLM总结回答 |
| **Agent工具调用** | 30-40% | 15,000条 | LLM调用MCP工具执行业务操作 |
| **多轮复杂任务** | 10-15% | 5,000条 | 多步推理+多个工具串联 |
| **合规拒绝/异常处理** | 5-10% | 2,000条 | 拒绝高危操作、错误恢复 |
| **子Agent并行任务** | 3-5% | 1,000条 | Sub-agent并行执行场景 |

---

## 五、数据采集模块实现方案

### 5.1 核心类设计

```python
# deerflow/data_collection/collector.py
"""
蒸馏数据采集核心模块。
零侵入旁路采集DeerFlow全链路推理数据。
"""

import json
import os
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from collections import deque

logger = logging.getLogger(__name__)


class TrainingDataCollector:
    """
    训练数据采集器。
    
    使用方式：
        collector = TrainingDataCollector()
        collector.record_agent_input(...)
        collector.record_model_output(...)
        collector.flush()  # 批量写入磁盘
    """

    def __init__(
        self,
        output_dir: str = "/data/deerflow/training_logs",
        buffer_size: int = 500,           # 内存缓冲区条数
        flush_interval_sec: float = 5.0,  # 最大刷盘间隔
        max_file_size_mb: int = 100,      # 单文件最大100MB
    ):
        self.output_dir = output_dir
        self.buffer_size = buffer_size
        self.flush_interval_sec = flush_interval_sec
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        self._buffer: deque[dict] = deque()
        self._current_file: Optional[str] = None
        self._current_file_size: int = 0
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

        self._ensure_directories()
        self._start_periodic_flush()

    def _ensure_directories(self):
        """确保目录结构存在。"""
        for subdir in ["raw", "daily", "archive"]:
            os.makedirs(os.path.join(self.output_dir, subdir), exist_ok=True)

    def _get_daily_file(self) -> str:
        """获取当前日期的写入文件路径。"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        return os.path.join(self.output_dir, "daily", f"train_data_{today}.jsonl")

    def record_agent_input(
        self,
        session_id: str,
        turn_id: int,
        user_query: str,
        system_prompt: str,
        history_context: list,
        rag_context: str = "",
        agent_config: Optional[dict] = None,
    ):
        """采集点P1: Agent输入。"""
        sample = {
            "sample_type": "agent_input",
            "session_id": session_id,
            "turn_id": turn_id,
            "create_time": datetime.now(timezone.utc).isoformat(),
            "user_query": user_query,
            "system_prompt": system_prompt,
            "history_context": history_context,
            "rag_context": rag_context,
            "agent_config": agent_config or {},
        }
        self._add_to_buffer(sample)

    def record_model_output(
        self,
        session_id: str,
        turn_id: int,
        step_number: int,
        raw_response: str,
        response_type: str,
        finish_reason: Optional[str],
        tool_calls: list,
        token_usage: Optional[dict],
        thinking_content: Optional[str],
        latency_ms: float,
    ):
        """采集点P2: 模型输出。"""
        sample = {
            "sample_type": "model_output",
            "session_id": session_id,
            "turn_id": turn_id,
            "step_number": step_number,
            "create_time": datetime.now(timezone.utc).isoformat(),
            "raw_response": raw_response,
            "response_type": response_type,
            "finish_reason": finish_reason,
            "tool_calls": tool_calls,
            "token_usage": token_usage or {},
            "thinking_content": thinking_content or "",
            "latency_ms": round(latency_ms, 1),
        }
        self._add_to_buffer(sample)

    def record_tool_call_request(
        self,
        session_id: str,
        turn_id: int,
        step_number: int,
        tool_name: str,
        tool_params: dict,
        call_id: str,
    ):
        """采集点P3: 工具调用请求。"""
        sample = {
            "sample_type": "tool_call_request",
            "session_id": session_id,
            "turn_id": turn_id,
            "step_number": step_number,
            "create_time": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "tool_params": tool_params,
            "call_id": call_id,
        }
        self._add_to_buffer(sample)

    def record_tool_call_result(
        self,
        session_id: str,
        turn_id: int,
        step_number: int,
        tool_name: str,
        tool_params: dict,
        tool_result: Any,
        error: Optional[str],
        duration_ms: float,
        tool_provider: str = "",
        tool_type: str = "",
    ):
        """采集点P4: 工具返回结果。"""
        sample = {
            "sample_type": "tool_call_result",
            "session_id": session_id,
            "turn_id": turn_id,
            "step_number": step_number,
            "create_time": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "tool_params": tool_params,
            "tool_result": tool_result,
            "error": error,
            "duration_ms": round(duration_ms, 1),
            "tool_provider": tool_provider,
            "tool_type": tool_type,
        }
        self._add_to_buffer(sample)

    def record_intermediate_state(self, session_id: str, turn_id: int, step_data: dict):
        """采集点P5: Agent中间状态。"""
        sample = {
            "sample_type": "agent_intermediate_state",
            "session_id": session_id,
            "turn_id": turn_id,
            "create_time": datetime.now(timezone.utc).isoformat(),
            **step_data,
        }
        self._add_to_buffer(sample)

    def record_final_response(
        self,
        session_id: str,
        turn_id: int,
        final_response: str,
        total_duration_ms: float,
        total_llm_calls: int,
        total_tool_calls: int,
        total_tokens: int,
        resolution_status: str,
        subagent_invoked: bool = False,
    ):
        """采集点P6: 最终回复。"""
        sample = {
            "sample_type": "final_response",
            "session_id": session_id,
            "turn_id": turn_id,
            "create_time": datetime.now(timezone.utc).isoformat(),
            "final_response": final_response,
            "total_duration_ms": round(total_duration_ms, 1),
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "total_tokens": total_tokens,
            "resolution_status": resolution_status,
            "subagent_invoked": subagent_invoked,
        }
        self._add_to_buffer(sample)

    def _add_to_buffer(self, sample: dict):
        """将样本加入缓冲区，达到阈值自动刷盘。"""
        self._buffer.append(sample)
        if len(self._buffer) >= self.buffer_size:
            asyncio.ensure_future(self.flush())

    async def flush(self):
        """将缓冲区数据批量写入磁盘。"""
        async with self._lock:
            if not self._buffer:
                return
            to_write = list(self._buffer)
            self._buffer.clear()

        file_path = self._get_daily_file()
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                for sample in to_write:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            logger.debug(f"Flushed {len(to_write)} samples to {file_path}")
        except Exception as e:
            logger.error(f"Failed to flush training data: {e}")
            # 失败时重新放回缓冲区头部
            self._buffer.extendleft(reversed(to_write))

    def _start_periodic_flush(self):
        """启动定时刷盘任务。"""
        async def _periodic_flush():
            while True:
                await asyncio.sleep(self.flush_interval_sec)
                await self.flush()
        self._flush_task = asyncio.ensure_future(_periodic_flush())

    async def shutdown(self):
        """关闭采集器，确保所有数据已写入。"""
        if self._flush_task:
            self._flush_task.cancel()
        await self.flush()
```

### 5.2 中间件集成代码

```python
# deerflow/agents/middlewares/data_collect_middleware.py
"""
数据采集中间件。

零侵入集成到DeerFlow中间件链中，自动采集全链路LLM推理数据。
"""

import time
from typing import Any
from deerflow.data_collection.collector import TrainingDataCollector
from deerflow.agents.middlewares.base import AgentMiddleware

# 全局单例采集器（进程级别）
_collector: TrainingDataCollector | None = None


def ensure_collector() -> TrainingDataCollector:
    global _collector
    if _collector is None:
        _collector = TrainingDataCollector()
    return _collector


class DataCollectMiddleware(AgentMiddleware):
    """
    蒸馏数据采集中间件。
    通过before/after钩子零侵入采集Agent全链路数据。
    """

    def __init__(self, collector: TrainingDataCollector | None = None):
        super().__init__()
        self.collector = collector or ensure_collector()
        self._turn_counts: dict[str, int] = {}
        self._step_counts: dict[str, int] = {}
        self._session_start: dict[str, float] = {}
        self._llm_call_counts: dict[str, int] = {}
        self._tool_call_counts: dict[str, int] = {}
        self._accumulated_tokens: dict[str, dict] = {}

    def _get_or_init_session(self, session_id: str):
        """初始化会话追踪数据。"""
        if session_id not in self._turn_counts:
            self._turn_counts[session_id] = 0
            self._session_start[session_id] = time.monotonic()
            self._llm_call_counts[session_id] = 0
            self._tool_call_counts[session_id] = 0
            self._accumulated_tokens[session_id] = {
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0
            }

    def before_model(self, state: dict) -> dict:
        """采集点P1: Agent输入。"""
        session_id = state.get("session_id", "unknown")
        turn_id = state.get("turn_id", 0)
        self._get_or_init_session(session_id)

        messages = state.get("messages", [])
        user_query = ""
        history = []
        system_prompt = ""

        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            elif msg.get("role") == "user":
                user_query = msg.get("content", "")
            else:
                history.append(msg)

        self.collector.record_agent_input(
            session_id=session_id,
            turn_id=turn_id,
            user_query=user_query,
            system_prompt=system_prompt,
            history_context=history[-6:],  # 保留最近3轮历史
            agent_config=state.get("agent_config"),
        )
        return state

    def after_model(self, state: dict) -> dict:
        """采集点P2+P5: 模型输出和中间状态。"""
        session_id = state.get("session_id", "unknown")
        turn_id = state.get("turn_id", 0)
        self._get_or_init_session(session_id)

        messages = state.get("messages", [])
        if not messages:
            return state

        last_msg = messages[-1]
        step_number = self._step_counts.get(session_id, 0)
        self._step_counts[session_id] = step_number + 1
        self._llm_call_counts[session_id] += 1

        # 提取token使用
        token_usage = state.get("token_usage", {})
        if token_usage:
            for k in token_usage:
                self._accumulated_tokens[session_id][k] = (
                    self._accumulated_tokens[session_id].get(k, 0) + token_usage.get(k, 0)
                )

        # 工具调用名单
        tool_calls = last_msg.get("tool_calls", [])
        tools_called_so_far = [
            tc.get("function", {}).get("name", "unknown")
            for tc in getattr(last_msg, "additional_kwargs", {}).get("tool_calls", [])
        ]

        # 记录模型输出
        self.collector.record_model_output(
            session_id=session_id,
            turn_id=turn_id,
            step_number=step_number,
            raw_response=last_msg.get("content", ""),
            response_type="tool_calls" if tool_calls else "text",
            finish_reason=last_msg.get("finish_reason", ""),
            tool_calls=[
                {
                    "tool_name": tc["function"]["name"],
                    "call_id": tc["id"],
                    "arguments": tc["function"]["arguments"],
                }
                for tc in last_msg.get("additional_kwargs", {}).get("tool_calls", [])
            ],
            token_usage=token_usage,
            thinking_content=last_msg.get("thinking_content", ""),
            latency_ms=0,
        )

        # 记录中间状态
        self.collector.record_intermediate_state(
            session_id=session_id,
            turn_id=turn_id,
            step_data={
                "step_number": step_number,
                "total_steps": state.get("max_steps", 25),
                "message_count": len(messages),
                "accumulated_tokens": self._accumulated_tokens[session_id],
                "tools_called_so_far": tools_called_so_far,
                "pending_tool_calls": tool_calls,
                "loop_detection_triggered": state.get("loop_detected", False),
            },
        )
        return state

    def wrap_tool_call(self, tool_call: Any, handler: callable) -> Any:
        """
        采集点P3+P4: 工具调用请求和结果。
        
        包装所有工具调用，记录输入输出。
        """
        session_id = getattr(tool_call, "session_id", "unknown")
        tool_name = tool_call.name
        tool_params = tool_call.args
        call_id = tool_call.id

        self._tool_call_counts[session_id] = (
            self._tool_call_counts.get(session_id, 0) + 1
        )

        # 采集点P3: 工具调用请求
        self.collector.record_tool_call_request(
            session_id=session_id,
            turn_id=0,
            step_number=self._step_counts.get(session_id, 0),
            tool_name=tool_name,
            tool_params=tool_params,
            call_id=call_id,
        )

        start_time = time.monotonic()
        try:
            result = handler(tool_call)
            error = None
            duration_ms = (time.monotonic() - start_time) * 1000
        except Exception as e:
            result = None
            error = str(e)
            duration_ms = (time.monotonic() - start_time) * 1000
            raise
        finally:
            # 采集点P4: 工具返回结果
            self.collector.record_tool_call_result(
                session_id=session_id,
                turn_id=0,
                step_number=self._step_counts.get(session_id, 0),
                tool_name=tool_name,
                tool_params=tool_params,
                tool_result=result.content if hasattr(result, "content") else result,
                error=error,
                duration_ms=duration_ms,
                tool_provider="mcp",
                tool_type="mcp"
            )

        return result

    def after_agent(self, state: dict) -> dict:
        """采集点P6: 最终回复。"""
        session_id = state.get("session_id", "unknown")
        turn_id = state.get("turn_id", 0)

        messages = state.get("messages", [])
        final_response = messages[-1].get("content", "") if messages else ""

        total_duration = (time.monotonic() - self._session_start.get(session_id, time.monotonic())) * 1000

        self.collector.record_final_response(
            session_id=session_id,
            turn_id=turn_id,
            final_response=final_response,
            total_duration_ms=total_duration,
            total_llm_calls=self._llm_call_counts.get(session_id, 0),
            total_tool_calls=self._tool_call_counts.get(session_id, 0),
            total_tokens=self._accumulated_tokens.get(session_id, {}).get("total_tokens", 0),
            resolution_status="completed",
            subagent_invoked=state.get("subagent_invoked", False),
        )

        # 清理会话追踪数据
        for key in ["_turn_counts", "_step_counts", "_session_start",
                     "_llm_call_counts", "_tool_call_counts", "_accumulated_tokens"]:
            getattr(self, key).pop(session_id, None)

        return state
```

### 5.3 在中间件链中的注册位置

```python
# agents/lead_agent/agent.py 中 _build_middlewares() 函数
def _build_middlewares(config, model_name=None, agent_name=None) -> list:
    middlewares = []

    # 现有中间件...
    middlewares.append(ThreadDataMiddleware(...))
    middlewares.append(UploadsMiddleware(...))

    # +++ 新增：数据采集中间件（放在中间件链首位，捕获完整输入输出）+++
    from deerflow.agents.middlewares.data_collect_middleware import DataCollectMiddleware
    middlewares.append(DataCollectMiddleware())

    middlewares.append(SandboxMiddleware(...))
    middlewares.append(DanglingToolCallMiddleware(...))
    middlewares.append(LLMErrorHandlingMiddleware(...))
    # ... 后续中间件

    return middlewares
```

### 5.4 配置开关

```yaml
# config.yaml 新增
data_collection:
  enabled: true                          # 总开关
  output_dir: /data/deerflow/training_logs
  buffer_size: 500                       # 内存缓冲条数
  flush_interval_sec: 5.0               # 刷盘间隔
  max_file_size_mb: 100                 # 单文件最大体积
  collect_agent_input: true             # 采集点P1
  collect_model_output: true            # 采集点P2
  collect_tool_calls: true              # 采集点P3+P4
  collect_intermediate_state: true      # 采集点P5
  collect_final_response: true          # 采集点P6
  auto_aggregate: true                  # 自动聚合成训练格式
```

---

## 六、子Agent数据采集

### 6.1 子Agent采集点

DeerFlow的子Agent（`subagents/executor.py`）同样有独立的LLM调用和工具执行，需要单独采集。

```python
# subagents/executor.py 增强
class SubagentExecutor:
    async def _aexecute(self, ...):
        # 创建子Agent时注入数据采集中间件
        middlewares = build_subagent_runtime_middlewares(lazy_init=True)
        middlewares.append(DataCollectMiddleware())  # 新增

        agent = create_agent(
            model=model,
            tools=self.tools,
            middleware=middlewares,
            ...
        )

        # 子Agent执行时自动采集数据
        async for chunk in agent.astream(state, ...):
            ...
```

### 6.2 子Agent数据Schema

子Agent的数据通过 `parent_session_id` 与主Agent关联：

```json
{
  "sample_type": "subagent_execution",
  "session_id": "sess_a1b2c3d4",
  "parent_session_id": "sess_a1b2c3d4",
  "subagent_name": "data_query_agent",
  "parent_tool_call_id": "call_setup_agent_xyz",
  "messages": [...],
  "final_response": "...",
  "total_duration_ms": 5200,
  "total_llm_calls": 3,
  "total_tool_calls": 2
}
```

---

## 七、数据清洗与聚合流水线

### 7.1 离线清洗脚本

每日定时运行清洗流程，将原始日志转换为蒸馏训练格式：

```python
# scripts/data_pipeline/clean_and_aggregate.py
"""
蒸馏数据清洗聚合流水线。

输入: /data/deerflow/training_logs/raw/*.jsonl
输出: /data/deerflow/training_logs/aggregated/{date}/train_data.jsonl
"""

import json
import os
import glob
from datetime import datetime, timedelta
from collections import defaultdict


class DataCleaner:
    """数据清洗器。"""

    def deduplicate(self, samples: list[dict]) -> list[dict]:
        """基于(user_query + model_response)去重。"""
        seen = set()
        deduped = []
        for s in samples:
            key = f"{s.get('user_query', '')}|{s.get('model_response', '')}"
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        return deduped

    def filter_incomplete(self, samples: list[dict]) -> list[dict]:
        """过滤不完整样本（缺少关键字段）。"""
        required_fields = {"session_id", "user_query", "model_response"}
        return [s for s in samples if required_fields.issubset(s.keys())]

    def filter_short_response(self, samples: list[dict], min_chars: int = 5) -> list[dict]:
        """过滤回复过短的样本（如"好的"、"已处理"等无意义回复）。"""
        return [s for s in samples if len(s.get("model_response", "")) >= min_chars]

    def filter_error_cases(self, samples: list[dict]) -> list[dict]:
        """过滤模型报错或工具调用失败的样本。"""
        return [s for s in samples if not s.get("error")]

    def clean(self, samples: list[dict]) -> list[dict]:
        """执行全量清洗。"""
        samples = self.filter_incomplete(samples)
        samples = self.filter_error_cases(samples)
        samples = self.filter_short_response(samples)
        samples = self.deduplicate(samples)
        return samples


class DataAggregator:
    """数据聚合器：将采集点数据聚合为训练格式。"""

    def aggregate_session(self, raw_samples: list[dict]) -> list[dict]:
        """
        将同一session的所有采集点数据聚合为训练样本。
        
        输入: 同一session_id的原始采集点数据（agent_input, model_output, tool_call...）
        输出: messages格式的训练样本
        """
        # 按session_id分组
        sessions = defaultdict(list)
        for s in raw_samples:
            sessions[s["session_id"]].append(s)

        aggregated = []
        for session_id, samples in sessions.items():
            samples.sort(key=lambda x: x.get("create_time", ""))
            train_sample = self._build_training_sample(samples)
            if train_sample:
                aggregated.append(train_sample)

        return aggregated

    def _build_training_sample(self, samples: list[dict]) -> dict | None:
        """
        将单个session的所有采集点数据转为messages格式。
        """
        messages = []
        metadata = {}

        for sample in samples:
            sample_type = sample.get("sample_type")

            if sample_type == "agent_input":
                # 添加system message
                if sample.get("system_prompt"):
                    messages.append({
                        "role": "system",
                        "content": sample["system_prompt"]
                    })
                # 添加user message
                if sample.get("user_query"):
                    messages.append({
                        "role": "user",
                        "content": sample["user_query"]
                    })
                metadata["session_id"] = sample["session_id"]
                metadata["create_time"] = sample["create_time"]

            elif sample_type == "model_output":
                tool_calls = sample.get("tool_calls", [])
                if tool_calls:
                    # 含工具调用的assistant消息
                    messages.append({
                        "role": "assistant",
                        "content": sample.get("raw_response", ""),
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": tc["tool_name"],
                                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                                }
                            }
                            for tc in tool_calls
                        ]
                    })
                else:
                    # 普通文本回复
                    messages.append({
                        "role": "assistant",
                        "content": sample.get("raw_response", "")
                    })

            elif sample_type == "tool_call_result":
                # 工具返回结果
                messages.append({
                    "role": "tool",
                    "tool_call_id": sample.get("call_id", ""),
                    "content": json.dumps(sample.get("tool_result", ""), ensure_ascii=False)
                })

        if len(messages) < 2:  # 至少有user+assistant
            return None

        return {
            "messages": messages,
            "metadata": metadata
        }


def run_daily_pipeline(date_str: str = None):
    """运行每日数据清洗聚合流水线。"""
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    raw_dir = f"/data/deerflow/training_logs/daily/train_data_{date_str}.jsonl"
    output_dir = f"/data/deerflow/training_logs/aggregated/{date_str}"
    os.makedirs(output_dir, exist_ok=True)

    # 1. 加载原始数据
    raw_samples = []
    if os.path.exists(raw_dir):
        with open(raw_dir, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_samples.append(json.loads(line))

    print(f"[{date_str}] Loaded {len(raw_samples)} raw samples")

    # 2. 清洗
    cleaner = DataCleaner()
    cleaned = cleaner.clean(raw_samples)
    print(f"[{date_str}] After cleaning: {len(cleaned)} samples")

    # 3. 聚合
    aggregator = DataAggregator()
    train_samples = aggregator.aggregate_session(cleaned)
    print(f"[{date_str}] After aggregation: {len(train_samples)} training samples")

    # 4. 写入
    output_path = os.path.join(output_dir, "train_data.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in train_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # 5. 写入统计
    stats = {
        "date": date_str,
        "raw_count": len(raw_samples),
        "cleaned_count": len(cleaned),
        "train_sample_count": len(train_samples),
        "categories": {},
    }
    for s in train_samples:
        cat = s.get("metadata", {}).get("category", "unknown")
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1

    stats_path = os.path.join(output_dir, "stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"[{date_str}] Output: {output_path}")
    print(f"[{date_str}] Stats: {json.dumps(stats, ensure_ascii=False)}")
    return stats


if __name__ == "__main__":
    import sys
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    run_daily_pipeline(date_str)
```

### 7.2 样本质量评分

对聚合后的训练样本自动评分，用于训练时的样本权重：

```python
class SampleQualityScorer:
    """训练样本质量评分器。"""

    def score(self, sample: dict) -> float:
        """
        对训练样本进行质量评分 (0.0 - 1.0)。
        
        评分维度:
        - 完整性 (0.3): 是否包含完整的推理链路
        - 复杂度 (0.2): 是否涉及工具调用或多轮交互
        - 回复质量 (0.3): 回复长度、信息密度
        - 多样性 (0.2): 是否与已有样本重复
        """
        score = 0.0
        messages = sample.get("messages", [])

        # 完整性评分
        roles = {m.get("role") for m in messages}
        if "tool" in roles:
            score += 0.3  # 含工具调用样本价值更高
        elif len(messages) >= 3:
            score += 0.2
        else:
            score += 0.1

        # 复杂度评分
        tool_call_count = sum(
            1 for m in messages if m.get("tool_calls")
        )
        if tool_call_count >= 2:
            score += 0.2
        elif tool_call_count >= 1:
            score += 0.15

        # 回复质量评分
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        if assistant_msgs:
            total_length = sum(len(m.get("content", "")) for m in assistant_msgs)
            if total_length >= 50:
                score += 0.3
            elif total_length >= 20:
                score += 0.2
            else:
                score += 0.1

        return min(score, 1.0)
```

---

## 八、数据存储与生命周期管理

### 8.1 目录结构

```
/data/deerflow/training_logs/
├── raw/                              # 原始日志（保留7天）
│   └── train_data_20260428.jsonl
├── daily/                            # 按天归档JSONL（保留30天）
│   └── train_data_20260428.jsonl
├── aggregated/                       # 聚合后训练格式（永久保留）
│   └── 20260428/
│       ├── train_data.jsonl          # 最终训练数据
│       ├── stats.json                # 每日统计
│       └── quality_scores.jsonl      # 质量评分
├── archive/                          # 月度打包
│   └── 2026_04.tar.gz
└── pipeline.log                      # 清洗流水线日志
```

### 8.2 保留策略

| 层级 | 保留期限 | 清理策略 | 说明 |
|------|---------|---------|------|
| **raw/** | 7天 | cron每日清理 | 原始采集日志，事故排查用 |
| **daily/** | 30天 | cron每日清理 | 按天归档，中间格式 |
| **aggregated/** | 永久 | 手动清理 | 最终训练数据，持续累积 |
| **archive/** | 永久 | 自动打包 | 月度压缩存档 |

### 8.3 数据量预估

| 口径 | 日均量 | 月均量 | 年化量 |
|------|-------|-------|-------|
| **原始采集点** (6个点合计) | ~60,000条 | ~180万条 | ~2,160万条 |
| **清洗后** (去重过滤) | ~50,000条 | ~150万条 | ~1,800万条 |
| **聚合样本** (按session聚合) | ~10,000条 | ~30万条 | ~360万条 |
| **存储空间** | ~200MB/天 | ~6GB/月 | ~72GB/年 |

---

## 九、可观测性与质量监控

### 9.1 数据采集监控指标

| 指标 | 采集方式 | 告警阈值 |
|------|---------|---------|
| 每日采集量 | 统计daily文件行数 | < 1,000条/天告警 |
| 采集延迟 | 日志时间戳差值 | 批量写入延迟 > 30秒 |
| 脏数据率 | 清洗后过滤比例 | > 5% 需排查 |
| 存储使用率 | 磁盘空间监控 | > 80% 告警 |
| 采集器错误率 | collector日志 | > 1% 告警 |

### 9.2 数据质量看板

```python
# scripts/data_pipeline/quality_dashboard.py
def generate_daily_report(date_str: str) -> dict:
    """生成数据质量日报。"""
    stats_path = f"/data/deerflow/training_logs/aggregated/{date_str}/stats.json"
    if not os.path.exists(stats_path):
        return {"error": f"No data for {date_str}"}

    with open(stats_path) as f:
        stats = json.load(f)

    report = {
        "date": date_str,
        "total_raw": stats["raw_count"],
        "total_train": stats["train_sample_count"],
        "categories": stats["categories"],
        "category_distribution": {
            cat: round(count / stats["train_sample_count"] * 100, 1)
            for cat, count in stats["categories"].items()
        },
        "estimated_disk_gb": round(
            stats["train_sample_count"] * 2 / 1024, 2  # 每条约2KB
        ),
    }
    return report
```

---

## 十、实施计划

### 10.1 实施步骤

| 步骤 | 内容 | 工作量 | 产出物 |
|------|------|--------|-------|
| **Step 1** | 新建data_collection模块 | ~150行 | `collector.py` 核心采集类 |
| **Step 2** | 新建DataCollectMiddleware | ~200行 | 中间件集成代码 |
| **Step 3** | 在中间件链中注册 | ~5行 | 修改`_build_middlewares()` |
| **Step 4** | 子Agent采集增强 | ~20行 | 修改`subagents/executor.py` |
| **Step 5** | 新增config.yaml配置 | ~15行 | 配置开关 |
| **Step 6** | 离线清洗聚合脚本 | ~200行 | `clean_and_aggregate.py` |
| **Step 7** | cron定时任务配置 | ~5行 | 每日自动清洗 |
| **Step 8** | 质量监控脚本 | ~80行 | `quality_dashboard.py` |

### 10.2 代码变更汇总

| 文件路径 | 变更类型 | 变更量 | 说明 |
|---------|---------|-------|------|
| `deerflow/data_collection/__init__.py` | **新增** | 1行 | 包入口 |
| `deerflow/data_collection/collector.py` | **新增** | ~150行 | 核心采集器 |
| `deerflow/agents/middlewares/data_collect_middleware.py` | **新增** | ~200行 | 数据采集中间件 |
| `deerflow/agents/lead_agent/agent.py` | 修改 | +5行 | 注册中间件 |
| `deerflow/subagents/executor.py` | 修改 | +5行 | 子Agent采集 |
| `deerflow/config/app_config.py` | 修改 | +10行 | 采集配置解析 |
| `deerflow/config.yaml` | 修改 | +15行 | 配置项 |
| `scripts/data_pipeline/clean_and_aggregate.py` | **新增** | ~200行 | 清洗聚合 |
| `scripts/data_pipeline/quality_dashboard.py` | **新增** | ~80行 | 质量监控 |

**总计新增/修改约665行代码，零改动现有业务逻辑。**

### 10.3 依赖

| 依赖 | 用途 | 备注 |
|------|------|------|
| Python标准库 `json`, `os`, `asyncio`, `logging` | 核心采集 | 无额外依赖 |
| `deerflow.agents.middlewares.AgentMiddleware` | 中间件基类 | 项目已有 |
| `schedule` (可选) | 清洗任务调度 | pip install schedule |
| `python-crontab` (可选) | cron配置 | pip install python-crontab |

---

## 十一、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 数据采集影响Agent性能 | 低 | 中 | 异步写入 + 内存缓冲，采集失败不退主流程 |
| 磁盘写满 | 低 | 高 | 定期清理 + 磁盘告警 + 自动停采保护 |
| 数据泄露（敏感信息外泄） | 中 | 高 | 日志文件权限控制 + 定期审计 + 脱敏处理 |
| 采集数据格式不兼容蒸馏框架 | 低 | 中 | 输出标准OpenAI messages格式，与LlamaFactory原生兼容 |
| 数据量不达标 | 低 | 中 | 持续运行，日均10,000条目标，1个月即可积累30万条 |

---

## 十二、核心结论

1. **DeerFlow中间件架构天然适合数据采集** — 利用现有`AgentMiddleware`钩子系统，零侵入采集全链路数据
2. **6个采集点覆盖完整推理链路** — 输入→思考→工具调用→结果→最终回复，无死角
3. **标准OpenAI messages格式** — 输出即用，无需转换直接喂LlamaFactory
4. **日均10,000+条优质样本** — 1个月可积累30万条，足够支撑7B模型蒸馏训练
5. **纯增量665行代码** — 不改动任何现有业务逻辑，风险可控

---

**WING**
*2026-04-28*
