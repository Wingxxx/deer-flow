## 1. 核心系统与框架
DeerFlow 采用 **Python 标准库 `logging`** 作为基础日志框架，未引入第三方结构化日志库（如 `structlog` 或 `loguru`）。其可观测性体系由 **应用日志**、**配置驱动的热重载** 以及 **分布式追踪（Tracing）** 三部分组成。

- **日志框架**：基于 `logging` 模块，通过 `logging.basicConfig` 进行全局初始化，并在应用生命周期中动态调整特定命名空间（`deerflow`, `app`）的日志级别。
- **追踪系统**：集成 **LangSmith** 和 **Langfuse** 作为主要的分布式追踪后端，用于记录 Agent 的执行轨迹、Token 消耗及延迟指标。
- **审计与事件**：在关键中间件（如循环检测、安全终止）中使用 `extra` 字段注入结构化上下文，并通过 LangGraph 的回调机制实现执行流的可视化。

## 2. 关键文件与包
- **配置与初始化**：
  - `backend/packages/harness/deerflow/config/app_config.py`：定义 `log_level` 配置项，提供 `apply_logging_level` 函数，负责将配置映射到 `logging` 级别并应用到指定 Logger。
  - `backend/app/gateway/app.py`：FastAPI 应用的入口，在 `lifespan` 启动阶段调用 `apply_logging_level`，确保日志级别随 `config.yaml` 热更新。
- **调试支持**：
  - `backend/debug.py`：为本地开发提供独立的日志路由，将输出重定向至 `debug.log` 文件，避免干扰交互式终端。
- **追踪集成**：
  - `backend/packages/harness/deerflow/tracing/factory.py`：根据环境变量动态构建 LangSmith/Langfuse 的 Callback Handler。
  - `backend/packages/harness/deerflow/config/tracing_config.py`：管理追踪相关的环境变量（如 `LANGSMITH_API_KEY`, `LANGFUSE_PUBLIC_KEY`）。
- **结构化日志实践**：
  - `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py`：展示了如何在 `logger.error/warning` 中使用 `extra` 字典传递 `thread_id`、`call_hash` 等诊断信息。

## 3. 架构设计与约定
### 3.1 日志级别隔离策略
系统采用了**精细化控制**的日志级别策略：
- **作用域限制**：`apply_logging_level` 仅修改 `deerflow` 和 `app` 两个根命名空间下的 Logger 级别，**不触碰 Root Logger**。这确保了第三方库（如 `uvicorn`, `sqlalchemy`）的日志 verbosity 不受应用配置影响，保持环境整洁。
- **Handler 降级原则**：当配置要求更详细的日志（如从 `INFO` 切换到 `DEBUG`）时，系统会同步降低 Root Handler 的阈值以允许消息透出；但当配置要求减少日志时，**不会提高** Handler 阈值，从而保护了可能针对第三方库设置的过滤规则。

### 3.2 配置热重载
- 应用在启动时会读取 `config.yaml` 中的 `log_level` 字段。
- 通过 `get_app_config()` 的单例缓存与文件签名校验机制，系统在检测到配置文件变更时会自动触发 `reload_app_config`，进而调用 `apply_logging_level` 实现**运行时日志级别切换**，无需重启服务。

### 3.3 可观测性分层
1. **基础日志层**：使用标准的 `%(asctime)s - %(name)s - %(levelname)s - %(message)s` 格式，便于在容器化环境（Docker/K8s）中通过 stdout/stderr 收集。
2. **结构化诊断层**：在复杂逻辑（如防循环、安全拦截）中，通过 `extra={...}` 携带业务上下文。虽然底层是文本日志，但这种约定为后续接入 ELK 或 Datadog 等支持 JSON 解析的系统预留了对接能力。
3. **分布式追踪层**：通过 LangChain 的 Tracer 接口，将 Agent 的每一步思考、工具调用和模型响应上报至 LangSmith/Langfuse，形成完整的执行链路图。

## 4. 开发者规范
- **Logger 获取**：始终使用 `logger = logging.getLogger(__name__)` 获取 logger 实例，以确保日志来源可追溯。
- **结构化字段**：在记录关键业务事件（如错误、警告）时，应优先使用 `extra` 参数传递结构化数据，而非将其硬编码在消息字符串中。
- **敏感信息脱敏**：严禁在日志中记录 API Key、用户凭证或完整的 PII（个人身份信息）。在记录 MCP 配置或 Auth Token 时需进行掩码处理。
- **追踪配置**：启用 LangSmith 或 Langfuse 时，需确保对应的环境变量已在 `.env` 或部署环境中正确设置，否则追踪初始化将静默失败或抛出 `RuntimeError`。