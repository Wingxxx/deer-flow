## 1. 核心构建系统
DeerFlow 采用 **Monorepo** 架构，后端基于 Python (uv + PyInstaller)，前端基于 Node.js (pnpm + Next.js)。构建流程通过根目录 `Makefile` 统一编排，支持本地开发、Docker 容器化部署以及生产环境二进制打包。

### 依赖管理
- **后端**: 使用 `uv` 进行极速依赖解析与环境管理。核心逻辑封装在 `backend/packages/harness` (deerflow-harness) 中，主应用通过 workspace 引用该包。
- **前端**: 使用 `pnpm` 管理依赖，配合 `corepack` 锁定 pnpm 版本，确保跨环境一致性。

## 2. 关键构建文件
- **`Makefile`**: 顶层入口，提供 `make install`, `make dev`, `make up` (Docker) 等标准化指令。
- **`scripts/build-release.sh`**: 生产发布脚本。执行前端 Standalone 构建，并利用 `PyInstaller` 将后端 Gateway 编译为无源码的二进制产物 (`deerflow-gateway`)。
- **`docker/docker-compose.yaml`**: 定义 Nginx、Frontend、Gateway 及可选 Provisioner 的生产/开发编排。
- **`.github/workflows/container.yaml`**: CI 流水线，监听 Tag 推送并自动构建多阶段 Docker 镜像至 GHCR。

## 3. 架构与约定
- **多阶段 Docker 构建**: 
  - 后端: `builder` (编译原生扩展) -> `dev` (含工具链) -> `runtime` (精简镜像)。
  - 前端: `base` -> `builder` (Next.js build) -> `prod` (仅包含 `.next/standalone`)。
- **零侵入扩展**: 通过 `deerflow_extensions` 目录实现功能插件化，构建时通过 `--add-data` 注入 PyInstaller 产物。
- **沙箱供应**: 支持 Docker-in-Docker (DooD) 模式，通过挂载宿主 Docker Socket 实现动态沙箱容器创建。

## 4. 开发者规范
- **环境初始化**: 新成员应执行 `make setup` 运行交互式向导，或 `make install` 安装全量依赖。
- **代码质量**: 提交前需通过 `ruff` (Python) 和 `eslint/prettier` (TS) 检查。CI 包含单元测试与 E2E 测试门禁。
- **发布流程**: 使用 `scripts/build-release.sh` 生成 `release/` 目录，产物包含二进制后端、静态前端及配置模板，严禁直接上传源码到生产服务器。