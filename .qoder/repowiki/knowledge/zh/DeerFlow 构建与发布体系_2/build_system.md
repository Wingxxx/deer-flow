## 1. 核心构建系统

DeerFlow 采用 **Monorepo** 架构，后端基于 Python (uv)，前端基于 Node.js (pnpm)。构建体系高度依赖容器化（Docker）和自动化脚本。

### 1.1 依赖管理
- **后端 (Python)**: 使用 `uv` 进行极速依赖解析与环境管理。项目采用 **Workspace** 模式，将核心逻辑封装在 `backend/packages/harness` (`deerflow-harness`) 中，主应用 `backend/` 依赖该 workspace 包。
- **前端 (TypeScript/Next.js)**: 使用 `pnpm` 管理依赖，通过 `corepack` 锁定 pnpm 版本（10.26.2），确保环境一致性。

### 1.2 本地开发构建
- **统一入口**: 根目录 `Makefile` 提供了 `make install`, `make dev`, `make start` 等命令，自动协调前后端的依赖安装与服务启动。
- **热重载**: 开发模式下，后端通过 `uvicorn --reload` 实现代码变更即时生效，前端通过 `next dev` 提供 HMR。

## 2. 容器化与生产部署

### 2.1 Docker 多阶段构建
- **后端镜像**: 采用三阶段构建（Builder -> Dev -> Runtime）。Builder 阶段编译原生扩展；Runtime 阶段剔除编译工具链以减小体积。支持通过 `UV_EXTRAS` 参数按需安装 PostgreSQL 等可选依赖。
- **前端镜像**: 区分 `dev` 和 `prod` 目标。Prod 目标执行 `pnpm build` 生成静态产物，并使用 `node:alpine` 作为运行时基础。

### 2.2 编排与发布
- **Docker Compose**: `docker/docker-compose.yaml` 定义了完整的生产环境栈，包括 Nginx 反向代理、Frontend、Gateway（后端）以及可选的 Sandbox Provisioner。
- **CI/CD**: GitHub Actions (`container.yaml`) 监听 Tag 推送，自动构建并推送前后端镜像至 GHCR，同时生成 Artifact Attestation 以确保供应链安全。

## 3. 离线/二进制发布方案

针对无法连接外网或需要极简部署的场景，项目提供了基于 **PyInstaller** 的二进制打包方案：
- **脚本**: `scripts/build-release.sh`
- **流程**: 
  1. 前端执行 `standalone` 模式构建，剥离 `node_modules`。
  2. 后端通过 PyInstaller 将 Gateway 及其所有隐式依赖（LangGraph, LangChain 等）打包为单一目录的二进制文件。
  3. 产物统一归档至 `release/` 目录，包含 Nginx 配置、Skills 及启动脚本。

## 4. 开发者规范

- **依赖同步**: 修改 `pyproject.toml` 或 `package.json` 后，必须运行 `make install` 或对应的 `uv sync` / `pnpm install`。
- **测试门禁**: CI 流程中包含严格的单元测试（Backend/Frontend）和 E2E 测试。提交 PR 前建议运行 `make test`。
- **配置管理**: 生产环境通过 `.env` 文件和 `config.yaml` 注入配置，严禁将敏感信息硬编码在源码中。