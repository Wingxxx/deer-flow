# DeerFlow 模型蒸馏私有化可行性分析方案

> **WING** 2026-04-28
>
> 基于两份PRD及DeerFlow项目代码深度调研，产出可行性分析方案及优先级排序。

---

## 一、背景与现状

### 1.1 当前架构

DeerFlow 全链路 LLM 推理依赖 **DeepSeek 公有云 API**，经分析代码发现：

| 推理节点 | 文件路径 | 当前模型 |
|---------|---------|---------|
| Lead Agent 主推理 | [agents/lead_agent/agent.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py) | DeepSeek API |
| Tool 调用（MCP选择/参数生成） | 同上（Agent内嵌） | DeepSeek API |
| 结果解析与多轮闭环 | 同上 | DeepSeek API |
| 知识库问答（RAG） | [tools/builtins/ragflow_tool.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/tools/builtins/ragflow_tool.py) | 外部调用，结果由LLM总结 |

### 1.2 核心痛点

1. **数据安全**：企业工单/订单/客户数据全部外发公有云
2. **成本不可控**：Agent多轮思考+工具调用Token消耗极大
3. **稳定性**：公网延迟/限流/超时导致Agent任务中断
4. **业务不收敛**：通用模型不熟悉企业MCP调用规范

### 1.3 DeerFlow 架构优势（对蒸馏方案极为有利）

DeerFlow 采用**类路径动态注入**的模型工厂模式（[models/factory.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/models/factory.py)），天然支持：
- **配置驱动切换模型**：通过`config.yaml`修改`models`列表即可切换
- **多模型共存**：可在配置中同时定义DeepSeek API和本地vLLM模型
- **已有vLLM Provider**：[models/vllm_provider.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/models/vllm_provider.py) 已实现完整vLLM支持
- **已有熔断器**：`circuit_breaker`支持故障自动切换

---

## 二、可行性分析框架

### 2.1 总体可行性判断

| 维度 | 评估 | 说明 |
|------|------|------|
| **技术可行性** | ✅ 高 | DeerFlow架构天然支持模型切换，已有vLLM Provider |
| **数据可行性** | ✅ 高 | 旁路日志采集零侵入，蒸馏训练数据可自动沉淀 |
| **成本可行性** | ✅ 高 | 单卡24G可训练7B模型，推理成本降低90%+ |
| **工程可行性** | ✅ 高 | 全开源栈（LlamaFactory+vLLM），零自研训练代码 |
| **风险可控性** | ✅ 高 | 双引擎热切换，一键回滚公有API |

### 2.2 关键约束

- **业务无侵入**：不改动现有RAG、Agent、MCP、Skill代码
- **增量式迭代**：先数据沉淀 → 离线蒸馏 → 灰度切换
- **开源零造轮**：全线采用工业级开源框架

---

## 三、具体方案选择（按优先级排序）

### 【P0】方案一：黑盒指令蒸馏（企业Agent标准方案）

> **核心思路**：用线上真实业务样本（用户Query+上下文+教师完美输出）驯化小模型，完全复刻教师API的业务行为。

#### 3.1.1 方案描述

| 维度 | 选择 | 理由 |
|------|------|------|
| **蒸馏方式** | 黑盒指令蒸馏（而非Logits蒸馏） | DeepSeek API仅暴露文本输出，无Logits访问权限 |
| **训练框架** | LlamaFactory | 国内企业Agent场景落地标准，原生支持工具调用样本 |
| **学生底座** | Qwen3-7B（首选） | 同源适配度高，7B参数量单卡可训，支持工具调用 |
| **训练方式** | QLoRA（4bit量化） | 单卡24G显存可完整训练，微调成本最低 |
| **推理引擎** | vLLM | DeerFlow已有VllmChatModel Provider，无缝对接 |

#### 3.1.2 技术可行性分析

**✅ DeerFlow 已有支持**：
- [config.example.yaml](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/config.example.yaml) 中已有vLLM配置示例
- [models/vllm_provider.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/models/vllm_provider.py) 已实现完整vLLM推理引擎
- [scripts/wizard/providers.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/scripts/wizard/providers.py) 中vLLM已被列为标准Provider

**✅ 配置示例**（仅需新增一个模型配置）：
```yaml
models:
  # 保留原有DeepSeek API作为教师/兜底
  - name: deepseek-api
    use: langchain_openai:ChatOpenAI
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1

  # 新增本地蒸馏模型
  - name: distilled-local
    use: deerflow.models.vllm_provider:VllmChatModel
    model: Qwen/Qwen3-7B-Distilled
    api_key: $VLLM_API_KEY
    base_url: http://localhost:8000/v1
    max_tokens: 4096
    temperature: 0.1
    supports_thinking: true
```

#### 3.1.3 关键模块代码变更评估

| 模块 | 变更量 | 说明 |
|------|--------|------|
| `config.yaml` | 新增10行 | 新增蒸馏模型配置 |
| `app_config.py` | ✅ 零改动 | 配置加载已支持多模型 |
| `models/factory.py` | ✅ 零改动 | 工厂模式已支持任意模型切换 |
| `models/vllm_provider.py` | ✅ 零改动 | 已有完整vLLM支持 |
| `agents/lead_agent/agent.py` | ✅ 零改动 | Agent通过`create_chat_model()`调用 |
| `extensions_config.json` | ✅ 零改动 | MCP配置与模型解耦 |
| **新增：旁路日志采集模块** | ~50行 | 在Agent调用LLM处新增日志旁路 |
| **新增：蒸馏数据清洗脚本** | ~100行 | JSONL格式转换、数据去重、格式校验 |

#### 3.1.4 训练数据配比（行业最佳实践）

| 样本类型 | 占比 | 来源 | 说明 |
|---------|------|------|------|
| RAG知识库问答 | 60% | RagFlow检索+DeepSeek答案 | 文档问答、结果润色 |
| Agent工具调用 | 30% | DeerFlow CoT+MCP调用日志 | 意图识别、工具选择、参数生成 |
| 合规拒绝样本 | 10% | 风控拦截、异常处理 | 企业业务约束、禁止操作 |

#### 3.1.5 可行性风险

| 风险 | 概率 | 应对 |
|------|------|------|
| 7B模型对复杂Agent推理能力不足 | 中 | 先尝试7B，效果不达标升14B/32B |
| 工具调用格式不一致 | 低 | 训练集中充分覆盖工具调用样本 |
| 训练数据量不足 | 低 | 持续增量采集，每周增量蒸馏 |

---

### 【P1】方案二：旁路日志采集系统

> **蒸馏方案的前置基础设施**，零侵入录制教师模型的标准答案。

#### 3.2.1 方案描述

在DeerFlow现有LLM调用链路中新增旁路日志采集点，不阻塞主业务流程。

#### 3.2.2 采集点设计

| 采集点 | 位置 | 数据内容 |
|--------|------|---------|
| **Agent输入** | `lead_agent/agent.py` 调用`create_chat_model()`前 | user_query, system_prompt, 历史上下文 |
| **RAG上下文** | `ragflow_tool.py` 调用后 | 检索文档片段、相似度分数 |
| **Agent思考** | Agent执行过程中 | CoT思考过程、中间推理 |
| **工具调用** | MCP Tool调用时 | tool_name, tool_params, tool_result |
| **模型输出** | `lead_agent/agent.py` 调用后 | 最终回复、拒绝话术 |

#### 3.2.3 输出格式

```jsonl
{
  "user_query": "帮我查一下终端86的状态",
  "system_prompt": "你是ADS智能运维助手...",
  "rag_context": "",
  "agent_thought": "用户想查询终端状态，需要调用ads_client_show工具",
  "tool_name": "ads_client_show",
  "tool_params": "{\"clientId\": 86}",
  "model_response": "终端86当前状态：在线，IP: 192.168.1.86...",
  "session_id": "session_abc123",
  "create_time": "2026-04-28T10:30:00Z"
}
```

#### 3.2.4 代码变更

**变更文件**：[agents/lead_agent/agent.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py) 约新增20行采样逻辑

```python
# 在LLM调用前后增加旁路日志
from deerflow.data_collection import collect_training_sample

# 采集Agent输入
collect_training_sample({
    "user_query": user_message,
    "system_prompt": system_prompt,
    "rag_context": rag_context,
})
# ... 执行LLM调用 ...
# 采集Agent输出
collect_training_sample({
    "tool_name": tool.name if tool else None,
    "tool_params": tool_params,
    "model_response": response,
    "session_id": session_id,
})
```

#### 3.2.5 部署方式

- 异步写入本地日志文件（`/data/training_logs/`）
- 定时归档至训练数据集目录
- 支持日志轮转（按天/按大小）

---

### 【P1】方案三：双引擎灰度调度系统

> 实现公有API/私有模型可配置切换，支持灰度放量。

#### 3.3.1 方案描述

利用DeerFlow现有`create_chat_model(name)`机制，新增灰度路由逻辑。

#### 3.3.2 架构设计

```
用户请求
     │
     ▼
┌─────────────┐
│ 灰度路由器    │ ←── 配置：local_model_traffic_ratio = 0.3
│ (配置驱动)   │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
本地模型  DeepSeek API
(vLLM)   (公有云兜底)
```

#### 3.3.3 配置设计

```yaml
# config.yaml 新增灰度配置
model_routing:
  teacher_model: deepseek-api          # 教师/兜底模型
  student_model: distilled-local       # 学生/主力模型
  traffic_ratio: 0.0                   # 0.0=纯公有, 0.3=30%本地, 1.0=纯本地
  fallback_on_error: true              # 本地模型失败时自动切回公有
  fallback_on_timeout: true            # 超时自动切回
```

#### 3.3.4 代码变更

| 文件 | 变更量 | 说明 |
|------|--------|------|
| [config/app_config.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/config/app_config.py) | +20行 | 新增灰度配置解析 |
| [models/factory.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/models/factory.py) | +30行 | 新增路由选择逻辑 |
| [agents/lead_agent/agent.py](file:///home/wing/wing/emto/2026/2026.3/DeerFlow/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py) | +5行 | 调用路由而非直接指定模型 |

---

### 【P2】方案四：模型评估与效果验证体系

> 建立对标公有API的量化评估体系。

#### 3.4.1 评估维度

| 维度 | 指标 | 对标基线 |
|------|------|---------|
| **问答准确率** | 知识库问答正确率 | DeepSeek API ≥ 95% |
| **工具调用成功率** | MCP工具选择+参数正确率 | DeepSeek API ≥ 98% |
| **推理延迟** | P95延迟 | 公有API 500ms → 本地 ≤ 300ms |
| **解决率** | 客服问题解决率 | 持平原有基线 |
| **幻觉率** | 错误信息/捏造工具参数 | ≤ 2% |

#### 3.4.2 评估数据集

- 从旁路日志中抽取1000条测试样本
- 覆盖：RAG问答(400) + Agent工具调用(400) + 合规拒绝(200)

#### 3.4.3 A/B测试方案

- **离线评估**：在固定测试集上对比蒸馏模型 vs DeepSeek API
- **在线评估**：灰度流量对比用户满意度、解决率

---

### 【P2】方案五：增量蒸馏与模型持续迭代

> 建立月度增量蒸馏机制，持续优化模型。

#### 3.5.1 迭代周期

```
每周：日志采集 → 数据清洗 → 增量训练 → 评估 → 发布
```

#### 3.5.2 数据增量策略

- 每周新增1000+条真实业务样本
- 保留所有历史训练数据（去重后）
- 新MCP工具上线后，人工标注50条样本加入训练集

---

## 四、方案优先级总览

| 优先级 | 方案 | 投入 | 收益 |
|--------|------|------|------|
| **P0** | **黑盒指令蒸馏**（核心方案） | 1-2周（训练+评估） | 成本降低90%+，数据不出内网 |
| **P1** | **旁路日志采集**（前置依赖） | 1天代码+持续运行 | 蒸馏数据源，零成本 |
| **P1** | **双引擎灰度调度**（安全切换） | 3天开发 | 一键回滚，风险可控 |
| **P2** | **模型评估体系**（质量保障） | 2天开发 | 量化对标，效果可衡量 |
| **P2** | **增量迭代机制**（持续优化） | 1天配置 | 模型持续进化 |

---

## 五、实施路线图

### 阶段1：数据基建（第1-3天）

```
Day 1: 旁路日志采集模块开发 (~50行代码)
Day 2: 蒸馏数据清洗脚本开发 (~100行代码)
Day 3: 数据质量验证，启动线上数据沉淀
```

### 阶段2：蒸馏训练（第4-8天）

```
Day 4-5: 搭建LlamaFactory训练环境
Day 6: 数据格式转换、训练配置调优
Day 7-8: 启动7B模型蒸馏训练（约6-12小时）
         评估模型效果，对比基线
```

### 阶段3：私有化部署（第9-12天）

```
Day 9: vLLM部署本地模型
Day 10: 双引擎灰度调度模块开发
Day 11-12: 全链路回归测试
           RAG问答、Agent多轮、MCP工具调用
```

### 阶段4：灰度上线（第13-15天）

```
Day 13: 10%流量灰度验证
Day 14: 50%流量验证（需Day13通过）
Day 15: 全量切换，下线公有API（可选）
```

---

## 六、核心结论

1. **DeerFlow现有架构已为模型蒸馏做好充分准备** — 类路径注入模式、已有vLLM Provider、配置驱动切换，方案可行且低成本
2. **P0方案黑盒指令蒸馏是唯一正确的技术路线** — 教师模型仅暴露API、无Logits访问权限，指令蒸馏是唯一选择
3. **7B学生模型性价比最高** — 单卡24G训练，vLLM毫秒级推理，预期效果满足客服场景
4. **实施周期15天可完成全流程上线** — 不改动核心业务代码，纯增量添加

---

**WING**
*2026-04-28*
