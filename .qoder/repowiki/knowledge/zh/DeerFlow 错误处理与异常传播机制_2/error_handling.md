DeerFlow 采用分层、结构化的错误处理策略，涵盖 API 网关层、LangGraph 智能体运行时以及底层沙箱环境。系统通过自定义异常类、中间件拦截和结构化响应模型，确保错误能够被精确分类、安全隔离并以用户友好的方式呈现。

### 1. 核心架构与模式

*   **API 网关层 (FastAPI)**：采用 `HTTPException` 进行标准 HTTP 状态码映射，并结合 `AuthMiddleware` 实现“默认拒绝”（Fail-closed）的安全策略。认证错误通过 `AuthErrorCode` 枚举提供细粒度的错误代码。
*   **智能体运行时 (LangGraph Middleware)**：利用 LangGraph 的 `AgentMiddleware` 机制，在模型调用 (`wrap_model_call`) 和工具执行 (`wrap_tool_call`) 层面实现自动重试、熔断器（Circuit Breaker）和错误降级。
*   **领域异常体系**：在沙箱（Sandbox）、持久化（Persistence）和技能管理（Skills）等模块中定义了继承自 `Exception` 或 `ValueError` 的专用异常类，支持携带结构化详情（如 `sandbox_id`, `exit_code`）。

### 2. 关键组件与文件

| 模块 | 关键文件 | 职责描述 |
| :--- | :--- | :--- |
| **认证与授权** | `backend/app/gateway/auth/errors.py` | 定义 `AuthErrorCode` 和 `TokenError`，统一认证失败原因。 |
| | `backend/app/gateway/auth_middleware.py` | 全局鉴权中间件，拦截未认证请求并返回标准化 401 响应。 |
| | `backend/app/gateway/authz.py` | 基于装饰器的权限校验，抛出 401/403/404 异常。 |
| **LLM 容错** | `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py` | 实现 LLM 调用的指数退避重试、熔断器逻辑及用户友好的降级消息。 |
| **工具容错** | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py` | 捕获工具执行异常，将其转换为 `ToolMessage(status="error")`，防止智能体崩溃。 |
| **沙箱安全** | `backend/packages/harness/deerflow/sandbox/exceptions.py` | 定义 `SandboxError` 及其子类（如 `SandboxNotFoundError`），支持结构化错误详情。 |
| **护栏机制** | `backend/packages/harness/deerflow/guardrails/middleware.py` | 在工具执行前进行策略评估，支持“故障即拒绝”（Fail-closed）模式。 |

### 3. 详细处理策略

#### A. 认证与授权错误
*   **结构化响应**：认证失败不再仅返回字符串，而是返回包含 `code` 和 `message` 的 JSON 对象（如 `{"code": "token_expired", "message": "..."}`）。
*   **全局守卫**：`AuthMiddleware` 在处理非公开路径时，若检测到无效或缺失的 JWT，会直接中断请求并返回 401。
*   **权限隔离**：`require_permission` 装饰器在权限不足时抛出 403，在资源所有权校验失败时抛出 404，防止信息泄露。

#### B. LLM 调用容错与熔断
*   **智能重试**：`LLMErrorHandlingMiddleware` 能识别 transient（瞬时）、busy（繁忙）等错误类型，并进行最多 3 次的指数退避重试。
*   **熔断器**：当连续失败达到阈值时，触发熔断器进入 `open` 状态，快速返回错误提示，保护系统免受雪崩效应影响。
*   **错误分类**：通过关键词匹配（如 `insufficient_quota`, `authentication`）将错误分为配额不足、认证失败等类别，并生成针对性的用户提示。

#### C. 工具执行与护栏
*   **异常转换**：工具执行中的任何未捕获异常都会被 `ToolErrorHandlingMiddleware` 捕获，并转化为带有 `status="error"` 的 `ToolMessage`。这使得智能体可以感知到工具失败并尝试其他路径，而不是直接终止运行。
*   **护栏拦截**：`GuardrailMiddleware` 在工具执行前进行评估。若评估器自身出错且配置为 `fail_closed=True`，则默认拒绝该工具调用。

### 4. 开发者规范

1.  **优先使用领域异常**：在业务逻辑中应抛出如 `SandboxNotFoundError` 等语义明确的异常，而非通用的 `Exception`。
2.  **保留控制流信号**：在编写中间件或包装器时，必须显式捕获并重新抛出 `langgraph.errors.GraphBubbleUp`，以确保 LangGraph 的中断/恢复机制正常工作。
3.  **避免裸异常捕获**：除非是为了记录日志并转换为降级消息（如在 Middleware 中），否则不应静默吞掉异常。
4.  **结构化错误详情**：定义新异常时，建议参考 `SandboxError` 的模式，支持传入 `details` 字典以便于日志追踪和问题排查。