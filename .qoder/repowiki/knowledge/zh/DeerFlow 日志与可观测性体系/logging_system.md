## 1. 核心架构与框架
DeerFlow 采用 **Python 标准库 `logging`** 作为基础日志框架，并结合 **LangSmith/Langfuse** 实现分布式追踪（Tracing）和结构化事件记录。系统通过配置驱动的方式管理日志级别，并支持在运行时动态调整。

- **日志框架**: `logging` (Python Standard Library)
- **追踪/可观测性**: LangSmith, Langfuse (通过 `langchain_core.tracers` 和 `langfuse.langchain` 集成)
- **配置管理**: 基于 `config.yaml` 的 `log_level` 字段控制应用层日志粒度。

## 2. 关键文件与模块
- **初始化与入口**: `backend/app/gateway/app.py`
  - 负责全局 `logging.basicConfig` 的初始化，默认格式为 `%(asctime)s - %(name)s - %(levelname)s - %(message)s`。
  - 在应用生命周期（Lifespan）启动时调用 `apply_logging_level` 同步配置。
- **配置逻辑**: `backend/packages/harness/deerflow/config/app_config.py`
  - 定义 `logging_level_from_config` 映射逻辑。
  - 实现 `apply_logging_level`，精准控制 `deerflow` 和 `app` 命名空间的日志级别，同时智能调整 Root Handler 的阈值。
- **扩展引导**: `deerflow_extensions/boot.py`
  - 统一引导加载器，使用独立的 `Boot` Logger 记录扩展模块（如数据采集、认证）的加载状态。
- **追踪工厂**: `backend/packages/harness/deerflow/tracing/factory.py`
  - 根据环境变量动态构建 LangSmith 或 Langfuse 的回调处理器（Callbacks）。

## 3. 架构约定与设计决策
### 3.1 日志级别隔离策略
系统遵循**“最小干扰”**原则：
- **作用域限制**: `apply_logging_level` 仅修改 `deerflow` 和 `app` 前缀的 Logger 级别。
- **第三方库保护**: 明确不修改 Root Logger 的全局级别，防止 uvicorn、sqlalchemy 等底层库产生过量日志。
- **Handler 阈值保护**: 仅当配置级别低于当前 Handler 级别时才降低 Handler 阈值，绝不主动提高阈值，确保不会意外屏蔽已有的重要警告。

### 3.2 结构化追踪元数据
在 `backend/packages/harness/deerflow/tracing/metadata.py` 中定义了 Langfuse 的元数据注入规范：
- **Session 关联**: 使用 `langfuse_session_id` 将 LangGraph 的 Thread ID 映射为追踪会话。
- **用户标识**: 使用 `langfuse_user_id` 关联具体用户（无认证模式下使用 `DEFAULT_USER_ID`）。
- **标签体系**: 自动注入 `env:<environment>` 和 `model:<model_name>` 标签，便于在追踪平台进行多维过滤。

### 3.3 扩展系统日志
零侵入扩展系统（`deerflow_extensions`）拥有独立的日志命名空间（如 `Boot`），并在加载失败时通过 `logger.warning` 记录异常，确保主网关启动不受非核心扩展影响。

## 4. 开发者规范
1. **Logger 获取**: 必须使用 `logging.getLogger(__name__)` 获取 logger 实例，严禁直接使用 `print` 输出业务日志。
2. **级别选择**:
   - `INFO`: 用于关键生命周期事件（如服务启动、通道连接、配置重载）。
   - `WARNING`: 用于非致命错误、降级处理（如文件上传跳过、扩展加载失败）。
   - `ERROR/EXCEPTION`: 用于导致请求失败或功能中断的异常。
3. **敏感信息脱敏**: 在记录日志时，严禁明文打印 API Key、Secret 或用户凭证。追踪系统中的元数据注入需经过 `build_langfuse_trace_metadata` 统一处理。
4. **配置变更**: 修改 `config.yaml` 中的 `log_level` 后，系统会在下次请求或重启时自动生效（取决于具体组件的热加载支持）。
