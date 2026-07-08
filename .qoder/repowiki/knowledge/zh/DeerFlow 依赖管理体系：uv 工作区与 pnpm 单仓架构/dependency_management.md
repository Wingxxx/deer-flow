DeerFlow 采用前后端分离的现代化依赖管理策略，后端基于 Python `uv` 构建高性能工作区，前端基于 `pnpm` 实现确定性安装。

### 1. 后端：uv 工作区模式 (Workspace)
- **包管理器**：使用 `uv` 替代传统的 `pip/poetry`，通过 `pyproject.toml` 和 `uv.lock` 实现极速解析与确定性锁定。
- **工作区架构**：在 `backend/pyproject.toml` 中定义了 `[tool.uv.workspace]`，将核心逻辑封装为 `packages/harness`（即 `deerflow-harness`）。
- **内部依赖引用**：主应用 `deer-flow` 通过 `{ workspace = true }` 引用 `deerflow-harness`，实现了核心运行时与网关层的解耦。这种结构允许 `harness` 作为独立库被测试或复用，同时保持版本同步。
- **源配置**：明确指定 `index-url = "https://pypi.org/simple"`，确保从官方源获取依赖，避免私有源配置混乱。

### 2. 前端：pnpm 严格模式
- **包管理器**：使用 `pnpm@10.26.2`，通过 `package.json` 中的 `packageManager` 字段锁定版本。
- **锁定文件**：`pnpm-lock.yaml` 记录了完整的依赖树，确保跨环境部署的一致性。
- **配置优化**：
  - `.npmrc` 中配置了 `public-hoist-pattern[]`，将 `eslint` 和 `prettier` 提升至根节点，解决 monorepo 或复杂插件系统中工具链找不到依赖的问题。
  - `pnpm-workspace.yaml` 目前配置为空数组，表明当前前端为单体应用结构，但保留了向多包工作区演进的能力。
  - 忽略特定原生依赖（如 `sharp`, `esbuild`）的构建脚本，以加速安装过程并避免不必要的编译错误。

### 3. 开发者规范
- **后端更新**：修改 `pyproject.toml` 后必须运行 `uv lock` 更新锁文件，并通过 `uv sync` 同步虚拟环境。
- **前端更新**：严禁手动修改 `pnpm-lock.yaml`，所有依赖变更应通过 `pnpm add/remove` 执行。
- **版本一致性**：CI/CD 流程应严格校验 `uv.lock` 和 `pnpm-lock.yaml` 的完整性，防止“在我机器上能跑”的环境差异问题。