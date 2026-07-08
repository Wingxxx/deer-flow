DeerFlow 采用分层、结构化的错误处理体系，涵盖从底层领域逻辑到上层 HTTP API 的完整链路。核心策略包括：

### 1. 结构化错误定义 (Structured Error Definitions)
- **认证模块**：在 `backend/app/gateway/auth/errors.py` 中定义了 `AuthErrorCode`（如 `TOKEN_EXPIRED`, `USER_NOT_FOUND`）和 `TokenError`，并配合 `AuthErrorResponse` Pydantic 模型提供标准化的错误响应载荷，替代了简单的字符串 `detail`。
- **沙箱模块**：在 `backend/packages/harness/deerflow/sandbox/exceptions.py` 中定义了以 `SandboxError` 为基类的异常层次结构（如 `SandboxNotFoundError`, `SandboxCommandError`），支持携带详细的上下文信息（如 `sandbox_id`, `exit_code`）。
- **运行时模块**：在 `backend/packages/harness/deerflow/runtime/runs/manager.py` 中定义了 `ConflictError` 和 `UnsupportedStrategyError`，用于处理并发运行冲突和未支持的策略。

### 2. 中间件级容错与重试 (Middleware-level Resilience)
- **LLM 错误处理**：`LLMErrorHandlingMiddleware` (`llm_error_handling_middleware.py`) 实现了对 LLM 调用的自动重试、退避（Backoff）和熔断（Circuit Breaker）。它能识别 transient（瞬时）、quota（配额）、auth（认证）等错误类型，并在重试耗尽后返回用户友好的 `AIMessage` 而非直接抛出异常。
- **工具错误处理**：`ToolErrorHandlingMiddleware` (`tool_error_handling_middleware.py`) 捕获工具执行过程中的异常，将其转换为带有 `status="error"` 的 `ToolMessage`，确保 Agent 工作流不会因单个工具失败而中断，并能继续利用现有上下文或选择替代方案。
- **安全终止检测**：通过 `SafetyFinishReasonMiddleware` 检测模型返回的 `finish_reason`（如 `content_filter`），防止不安全或截断的内容进入后续流程。

### 3. HTTP 层异常映射 (HTTP Exception Mapping)
- **统一网关拦截**：`AuthMiddleware` 作为全局安全网，对非公开路径进行严格的 JWT 验证，失败时返回标准化的 401 JSON 响应。
- **依赖注入检查**：`deps.py` 中的依赖项获取函数（如 `get_config`, `get_thread_store`）在基础设施不可用时抛出 503 `HTTPException`。
- **路由层映射**：在 `services.py` 和各 Router 中，将领域异常（如 `ConflictError` -> 409, `UnsupportedStrategyError` -> 501）显式映射为对应的 HTTP 状态码。

### 4. 开发者规范 (Developer Conventions)
- **优先使用结构化异常**：在新增业务逻辑时，应优先复用或扩展现有的异常类（如 `SandboxError` 子类），避免裸抛 `Exception` 或 `RuntimeError`。
- **中间件封装**：对于可能失败的异步操作（如 LLM 调用、工具执行），应通过中间件进行包装，实现统一的日志记录、重试和降级逻辑。
- **控制流保护**：在处理异常时，必须显式放行 LangGraph 的控制流异常（如 `GraphBubbleUp`, `GraphInterrupt`），防止误捕获导致工作流状态机紊乱。
- **错误信息脱敏**：在向客户端返回错误详情时，应注意脱敏敏感信息（如内部堆栈、密钥），仅返回必要的调试提示或通用错误码。