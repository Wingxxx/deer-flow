## 1. 核心架构与加载机制
DeerFlow 采用**多文件分层 + 环境变量注入**的配置体系，将静态应用参数、扩展插件状态与敏感凭据分离管理。

*   **主配置 (`config.yaml`)**：基于 Pydantic 的 `AppConfig` 模型，承载 LLM 模型定义、工具链、沙箱策略、记忆系统及数据库后端等核心逻辑。支持通过 `$VAR_NAME` 语法在 YAML 中引用环境变量。
*   **扩展配置 (`extensions_config.json`)**：以 JSON 格式管理 MCP 服务器连接信息及 Skills 的启用状态，实现插件化功能的动态编排。
*   **环境配置 (`.env`)**：存储 API Keys、Base URLs 及渠道（如企业微信、钉钉）的敏感凭据。前端提供 `/api/env-settings` 接口，支持在线修改并自动同步至 `.env` 和 `config.yaml`。
*   **路径解析优先级**：
    1. 显式传入的路径参数。
    2. 环境变量 `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH`。
    3. 项目根目录下的默认文件名。
    4. 向后兼容的旧版路径（如 `backend/config.yaml`）。

## 2. 关键组件与文件
*   **`backend/packages/harness/deerflow/config/app_config.py`**：配置系统的核心引擎。负责 YAML 解析、版本校验、环境变量递归替换以及 `AppConfig` 单例的生命周期管理。
*   **`backend/packages/harness/deerflow/config/extensions_config.py`**：处理 `extensions_config.json` 的加载与 MCP/Skills 状态映射。
*   **`deerflow_extensions/env_settings/router.py`**：提供 RESTful API，允许用户在前端界面动态更新厂商 Key 和渠道凭据，并触发配置文件的原子写入。
*   **`config.example.yaml`**：包含详尽注释的模板文件，定义了所有支持的配置项及其默认值。

## 3. 设计约定与规则
*   **版本控制与升级**：`config.yaml` 包含 `config_version` 字段。启动时若检测到本地版本低于 `config.example.yaml`，系统会发出警告并建议运行 `make config-upgrade` 进行合并。
*   **敏感信息保护**：严禁在 `config.yaml` 或 `extensions_config.json` 中硬编码明文密钥。必须使用 `$ENV_VAR` 占位符，由系统在加载时从 `.env` 或宿主环境中提取。
*   **运行时热重载**：`get_app_config()` 具备文件监控能力，当检测到 `config.yaml` 的修改时间（mtime）变化时，会自动重新加载配置并刷新相关的单例对象（如 Checkpointer）。
*   **上下文隔离**：支持通过 `push_current_app_config` / `pop_current_app_config` 在特定执行上下文中临时覆盖全局配置，常用于测试或多租户场景。
*   **路径安全**：`Paths` 类统一管理数据目录（如 `.deer-flow`），并对 Thread ID 和 User ID 进行严格的正则校验，防止路径遍历攻击。

## 4. 开发者指南
*   **新增配置项**：首先在 `config.example.yaml` 中添加示例，然后在 `deerflow.config` 对应的 Pydantic 模型中定义字段。
*   **访问配置**：优先通过依赖注入或函数参数传递 `AppConfig` 实例；若需快速访问，可使用 `get_app_config()` 获取全局单例。
*   **环境变更**：修改 `.env` 后，若涉及 Gateway 或 Channel 服务，通常需要通过 API 触发重启或调用 `reload_app_config()` 以确保变更生效。