## 1. 核心系统与工具

DeerFlow 采用现代化的双栈依赖管理方案，针对后端 Python 和前端 TypeScript/JavaScript 分别使用了高性能的包管理器：

- **后端 (Python)**: 使用 **[uv](https://github.com/astral-sh/uv)** 作为统一的包管理和项目构建工具。`uv` 替代了传统的 `pip`、`poetry` 或 `virtualenv`，提供了极速的依赖解析和环境管理能力。
- **前端 (TypeScript/React)**: 使用 **[pnpm](https://pnpm.io/)** 进行依赖管理。通过 `packageManager` 字段锁定版本为 `pnpm@10.26.2`，确保团队环境一致性。

## 2. 关键文件与配置

### 后端 (backend/)
- **`pyproject.toml`**: 项目的核心清单文件。定义了项目名称 `deer-flow`、版本、Python 版本要求 (`>=3.12`) 以及直接依赖（如 `fastapi`, `langgraph-sdk`）。
- **`uv.lock`**: 自动生成的确定性锁文件。记录了所有直接和间接依赖的精确版本、哈希值及来源，确保跨环境构建的可重复性。
- **`.python-version`**: 指定项目所需的 Python 版本为 `3.12`，由 `uv` 自动识别并管理对应的解释器。
- **`packages/harness/pyproject.toml`**: 内部库 `deerflow-harness` 的清单文件。它被定义为 workspace 成员，包含核心的 LangGraph 代理逻辑和模型集成依赖。

### 前端 (frontend/)
- **`package.json`**: 定义前端依赖（如 `next`, `react`, `@langchain/langgraph-sdk`）及脚本。
- **`pnpm-lock.yaml`**: pnpm 的锁文件，采用 `lockfileVersion: '9.0'`，详细记录了依赖树和 peer dependencies 的解析结果。
- **`.npmrc`**: pnpm 配置文件。设置了 `public-hoist-pattern[]` 将 `eslint` 和 `prettier` 提升到根目录，以解决某些工具对 `node_modules` 结构的预期问题。

## 3. 架构与约定

### Python Workspace 架构
后端采用了 **uv Workspaces** 模式：
- **根项目 (`deer-flow`)**: 主要负责 API 网关、渠道集成（Slack, Discord, Feishu 等）和扩展逻辑。
- **子包 (`deerflow-harness`)**: 位于 `backend/packages/harness`，是一个独立的 Python 包。它封装了 Agent 的核心执行引擎、沙箱交互和模型抽象。
- **依赖引用**: 根项目通过 `[tool.uv.sources]` 中的 `{ workspace = true }` 引用 `deerflow-harness`，实现了本地开发时的热更新和模块化隔离。

### 依赖源与版本策略
- **公共源**: 后端明确配置 `[tool.uv.index-url] = "https://pypi.org/simple"`，所有依赖均从官方 PyPI 获取。
- **版本约束**: 
  - Python 依赖多采用语义化版本范围（如 `fastapi>=0.115.0`），在 `uv.lock` 中固定为具体版本。
  - 前端依赖在 `package.json` 中使用 `^` 前缀（如 `^19.0.0`），允许次版本更新，但通过 `pnpm-lock.yaml` 锁定实际安装版本。

## 4. 开发者规范

1. **环境初始化**:
   - 后端: 运行 `uv sync` 即可根据 `uv.lock` 创建虚拟环境并安装所有依赖（包括 workspace 成员）。
   - 前端: 运行 `pnpm install` 安装依赖。
2. **添加依赖**:
   - 后端: 使用 `uv add <package>` 自动更新 `pyproject.toml` 和 `uv.lock`。
   - 前端: 使用 `pnpm add <package>`。
3. **内部开发**: 修改 `backend/packages/harness` 中的代码时，无需重新安装包，`uv` 会自动以可编辑模式（editable mode）链接该包。
4. **锁文件管理**: 严禁手动修改 `uv.lock` 或 `pnpm-lock.yaml`。所有变更应通过包管理器命令触发，并提交到版本控制系统以保证团队协作的一致性。