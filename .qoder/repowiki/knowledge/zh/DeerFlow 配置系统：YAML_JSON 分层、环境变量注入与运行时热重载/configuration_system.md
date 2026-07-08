## 1. 核心架构与加载机制

DeerFlow 采用**分层配置策略**，将静态应用配置、扩展配置与环境变量解耦，并通过 Pydantic 模型进行强类型校验。

*   **主配置文件 (`config.yaml`)**：基于 YAML 格式，承载核心业务逻辑配置（如 LLM 模型定义、工具链、沙箱环境、数据库后端等）。系统通过 `AppConfig.from_file()` 加载，并支持通过 `DEER_FLOW_CONFIG_PATH` 或 `DEER_FLOW_PROJECT_ROOT` 指定路径。
*   **扩展配置文件 (`extensions_config.json`)**：基于 JSON 格式，专门用于管理 MCP (Model Context Protocol) 服务器和 Skills 的状态。这种分离使得动态扩展（如新增 MCP 服务）无需触碰核心 YAML 结构。
*   **前端环境变量 (`.env`)**：Next.js 前端使用 `@t3-oss/env-nextjs` 结合 Zod 进行 schema 校验，区分服务端 (`server`) 与客户端 (`NEXT_PUBLIC_`) 变量。

## 2. 关键特性

### 2.1 环境变量注入与解析
系统实现了递归的环境变量解析器 `resolve_env_variables`。在 `config.yaml` 中，任何以 `$` 开头的字符串（如 `$OPENAI_API_KEY`）都会在加载时被替换为宿主机的环境变量值。若变量未定义且非空，系统将抛出异常（Extensions Config 中未定义的变量则默认为空字符串以避免启动失败）。

### 2.2 运行时热重载 (Hot Reload)
后端配置单例 (`get_app_config()`) 具备自动感知文件变更的能力：
*   **签名校验**：通过计算配置文件的 SHA-256 摘要和监控 `mtime`，系统在每次获取配置时判断文件是否被修改。
*   **自动重载**：一旦检测到变更，会自动触发 `reload_app_config()`，重新解析 YAML 并更新内存中的单例，同时重置相关的 Checkpointer 和 Store 实例以确保状态一致性。
*   **版本管理**：引入 `config_version` 字段。启动时会对比用户 `config.yaml` 与 `config.example.yaml` 的版本号，若版本过低则发出警告，提示运行 `make config-upgrade`。

### 2.3 路径管理与隔离
`Paths` 类统一管理文件系统路径，支持多租户隔离：
*   **基础目录**：优先读取 `DEER_FLOW_HOME`，否则默认为项目根目录下的 `.deer-flow`。
*   **用户隔离**：支持按 `user_id` 划分存储桶（如 `users/{user_id}/threads/`），防止跨用户数据泄露。
*   **沙箱映射**：定义了虚拟路径前缀 `/mnt/user-data`，并在 Docker/本地沙箱执行时自动处理 Host 路径到 Container 路径的映射与权限设置（chmod 0o777）。

## 3. 开发者规范

1.  **敏感信息处理**：严禁在 `config.yaml` 或 `extensions_config.json` 中硬编码 API Key。必须使用 `$VAR_NAME` 语法引用环境变量，并在 `.env` 文件中维护。
2.  **配置变更流程**：修改 `config.example.yaml` 后，务必同步增加 `config_version`。新增配置项应在 `AppConfig` Pydantic 模型中定义默认值，以保证向后兼容。
3.  **前端变量同步**：在 `frontend/src/env.js` 中添加新变量时，必须同步更新 `frontend/.env.example`，并确保客户端变量带有 `NEXT_PUBLIC_` 前缀。
4.  **路径安全**：在处理用户上传或沙箱文件路径时，必须使用 `Paths.resolve_virtual_path()` 等方法，严防路径遍历攻击（Path Traversal）。