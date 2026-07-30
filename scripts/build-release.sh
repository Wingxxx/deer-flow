#!/usr/bin/env bash
#
# build-release.sh — 一键编译 DeerFlow 部署产物（2026-05-07 新版架构）
#
# 用法：
#   ./scripts/build-release.sh              # 完整构建（前端 + 后端 PyInstaller）
#   ./scripts/build-release.sh --skip-backend  # 仅构建前端，后端到服务器上编译
#
#   # 在服务器上编译后端：
#   # 1. rsync -avz --progress backend/ user@server:/usr/xccloud/deerflow/backend/
#   # 2. ssh 到服务器，执行:
#   #    cd /usr/xccloud/deerflow && bash backend/scripts/build-backend-on-server.sh
#
# 执行后在当前目录生成 release/ 目录，
# 包含所有需要部署到服务器的产物。
#
# 产物清单：
#   - frontend/                 (Next.js 生产构建，standalone 模式，无 node_modules)
#   - backend-bin/              (PyInstaller 编译产物：二进制 + _internal/，无 .py 源码)
#   - skills/                   (Agent skills)
#   - mcp-agent-mcp/            (可选 ADS MCP)
#   - deepRag/                  (DeepRAG 知识库检索服务：二进制 + 前端 + 配置)
#   - scripts/                  (服务管理：deerflow.sh + wait-for-port.sh + wait-for-deeprag.sh)
#   - nginx/                    (Nginx 配置：server.conf + deeprag.conf)
#   - config.yaml               (主配置，直接拷贝项目根目录 config.yaml)
#   - config.example.yaml       (配置模板)
#   - extensions_config.json    (MCP 配置，直接拷贝项目根目录 extensions_config.json)
#   - extensions_config.example.json  (MCP 配置模板)
#   - .env.example              (环境变量模板)
#   - README.md                 (部署使用说明)
#
# 产物输出到：$(pwd)/release/
#

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RELEASE_DIR="${RELEASE_DIR:-$(pwd)/release}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

SKIP_BACKEND=false
PREPARE_SERVER_BUILD=false
for arg in "$@"; do
    case "$arg" in
        --skip-backend) SKIP_BACKEND=true ;;
        --prepare-server-build) SKIP_BACKEND=true; PREPARE_SERVER_BUILD=true ;;
        *) echo "未知参数: $arg"; exit 1 ;;
    esac
done

echo "=========================================="
echo "  DeerFlow Release Builder"
echo "  新版架构（Gateway 内嵌 Agent 运行时）"
echo "=========================================="
echo ""
echo "  仓库目录: $REPO_ROOT"
echo "  输出目录: $RELEASE_DIR"
echo "  时间戳: $TIMESTAMP"
echo ""

# ── 清理旧产物 ──────────────────────────────────────────────────────────────

if [ -d "$RELEASE_DIR" ]; then
    echo "[1/10] 清理旧产物..."
    rm -rf "$RELEASE_DIR"
fi

# ── 创建目录结构 ────────────────────────────────────────────────────────────

echo "[2/11] 创建目录结构..."
mkdir -p "$RELEASE_DIR"/{frontend,backend-bin,skills,scripts,nginx,mcp-agent-mcp}
mkdir -p "$RELEASE_DIR/deepRag"/{bin,frontend,Knowledge-Base,Knowledge-Base-Chunks,Knowledge-Base-File-Summary}

# ── 编译前端 ────────────────────────────────────────────────────────────────

echo "[3/10] 编译前端 (Next.js, standalone 模式)..."
cd "$REPO_ROOT/frontend"

if [ ! -d "node_modules" ]; then
    echo "  安装前端依赖..."
    pnpm install --frozen-lockfile
fi

NEXT_CONFIG_BUILD_OUTPUT=standalone SKIP_ENV_VALIDATION=1 pnpm build

# ── 泛化依赖完整性修复 ──────────────────────────────────────────────────
# 替代之前按包修补（@swc/helpers、@next/env）的零散逻辑。
# 根因：pnpm 严格模式下，Next.js standalone trace (@vercel/nft) 会遗漏
# 部分包的追踪，导致运行时 MODULE_NOT_FOUND。
# 修复方式：构建后自动扫描 next 声明的运行时依赖，缺失的从 pnpm store 补齐。
#
echo "  验证 standalone 依赖完整性..."
FULL_NM="$REPO_ROOT/frontend/node_modules"
STANDALONE_NM="$REPO_ROOT/frontend/.next/standalone/node_modules"
STANDALONE_NEXT_PKG="$STANDALONE_NM/next/package.json"

FIXED_COUNT=0
if [ -f "$STANDALONE_NEXT_PKG" ]; then
  while IFS= read -r pkg_name; do
    # 跳过 next 自身及其 peerDependency（如 react、react-dom）
    case "$pkg_name" in
      next|react|react-dom) continue ;;
    esac
    if node -e "require.resolve('$pkg_name',{paths:['$STANDALONE_NM']})" 2>/dev/null; then
      continue
    fi
    # 在 pnpm store 中查找该包并复制到 standalone
    STORE_PATH=$(find "$FULL_NM/.pnpm" -maxdepth 4 -path "*/node_modules/$pkg_name" -type d 2>/dev/null | head -1)
    if [ -n "$STORE_PATH" ] && [ -d "$STORE_PATH" ]; then
      TARGET="$STANDALONE_NM/$pkg_name"
      mkdir -p "$(dirname "$TARGET")"
      cp -r "$STORE_PATH" "$TARGET"
      echo "  ✓ 已修复缺失依赖: $pkg_name"
      FIXED_COUNT=$((FIXED_COUNT + 1))
    else
      echo "  ⚠ 在 pnpm store 中找不到 $pkg_name，跳过"
    fi
  done < <(node -e "
    const p = require('$STANDALONE_NEXT_PKG');
    const deps = {...(p.dependencies||{}), ...(p.optionalDependencies||{})};
    Object.keys(deps).forEach(k => console.log(k));
  ")
fi

if [ "$FIXED_COUNT" -gt 0 ]; then
  echo "  ✓ 共修复 $FIXED_COUNT 个缺失依赖"
else
  echo "  ✓ 所有依赖完整，无需修复"
fi

echo "  复制前端构建产物（standalone 模式 = 无源码 + 无 node_modules）..."
cp -r .next "$RELEASE_DIR/frontend/"
# standalone 模式：将静态资源复制到 server.js 同级目录下
cp -r .next/static "$RELEASE_DIR/frontend/.next/standalone/.next/static/"
cp -r public "$RELEASE_DIR/frontend/"
# standalone 模式需要 next.config.js（运行时读取 rewrites 等路由配置）
cp next.config.js "$RELEASE_DIR/frontend/"
# 运行时必需的 src/env.js（next.config.js import 它）
mkdir -p "$RELEASE_DIR/frontend/src"
cp src/env.js "$RELEASE_DIR/frontend/src/env.js"

cd "$REPO_ROOT"

# ── 编译后端（PyInstaller → 二进制）────────────────────────────────────────

if [ "$SKIP_BACKEND" = false ]; then
    # ── 全量编译（本地 PyInstaller）───────────────────────────────────
    echo "[4/10] 编译后端 (PyInstaller → 二进制、无源码)..."
    cd "$REPO_ROOT/backend"

    echo "  安装后端依赖 (uv sync)..."
    rm -rf .venv
    uv sync

    echo "  安装 PyInstaller 到项目 .venv..."
    uv pip install pyinstaller --quiet

    echo "  编译 Gateway 二进制（耗时 5-15 分钟）..."
    .venv/bin/python -m PyInstaller --onedir --noconfirm \
        --name deerflow-gateway \
        --paths . \
        --paths packages/harness \
        --paths ../deerflow_extensions \
        --add-data "../deerflow_extensions:deerflow_extensions" \
        \
        --hidden-import=app \
        --hidden-import=app.gateway \
        --hidden-import=app.gateway.app \
        --hidden-import=app.gateway.deps \
        --hidden-import=app.gateway.config \
        --hidden-import=app.gateway.authz \
        --hidden-import=app.gateway.services \
        --hidden-import=app.gateway.auth_middleware \
        --hidden-import=app.gateway.csrf_middleware \
        --hidden-import=app.gateway.internal_auth \
        --hidden-import=app.gateway.langgraph_auth \
        --hidden-import=app.gateway.path_utils \
        --hidden-import=app.gateway.utils \
        --hidden-import=app.gateway.routers \
        --hidden-import=app.gateway.routers.agents \
        --hidden-import=app.gateway.routers.artifacts \
        --hidden-import=app.gateway.routers.assistants_compat \
        --hidden-import=app.gateway.routers.auth \
        --hidden-import=app.gateway.routers.channels \
        --hidden-import=app.gateway.routers.feedback \
        --hidden-import=app.gateway.routers.mcp \
        --hidden-import=app.gateway.routers.memory \
        --hidden-import=app.gateway.routers.models \
        --hidden-import=app.gateway.routers.runs \
        --hidden-import=app.gateway.routers.skills \
        --hidden-import=app.gateway.routers.suggestions \
        --hidden-import=app.gateway.routers.thread_runs \
        --hidden-import=app.gateway.routers.threads \
        --hidden-import=app.gateway.routers.uploads \
        --hidden-import=app.gateway.auth \
        --hidden-import=app.gateway.auth.repositories \
        --hidden-import=app.gateway.auth.repositories.base \
        --hidden-import=app.gateway.auth.repositories.sqlite \
        --hidden-import=app.channels \
        --hidden-import=app.channels.service \
        --hidden-import=app.channels.manager \
        --hidden-import=app.channels.base \
        --hidden-import=app.channels.commands \
        --hidden-import=app.channels.message_bus \
        --hidden-import=app.channels.store \
        --hidden-import=app.channels.dingtalk \
        --hidden-import=app.channels.discord \
        --hidden-import=app.channels.feishu \
        --hidden-import=app.channels.slack \
        --hidden-import=app.channels.telegram \
        --hidden-import=app.channels.wechat \
        --hidden-import=app.channels.wecom \
        \
        --hidden-import=langchain_openai \
        --hidden-import=langchain_anthropic \
        --hidden-import=langchain_deepseek \
        --hidden-import=langchain_google_genai \
        \
        --hidden-import=deerflow.models.patched_openai \
        --hidden-import=deerflow.models.patched_deepseek \
        --hidden-import=deerflow.models.patched_minimax \
        --hidden-import=deerflow.models.vllm_provider \
        --hidden-import=deerflow.models.mindie_provider \
        --hidden-import=deerflow.models.claude_provider \
        --hidden-import=deerflow.models.openai_codex_provider \
        \
        --hidden-import=deerflow.sandbox.local \
        --hidden-import=deerflow.sandbox.tools \
        --hidden-import=deerflow.community.aio_sandbox \
        \
        --hidden-import=deerflow.community.ddg_search \
        --hidden-import=deerflow.community.serper \
        --hidden-import=deerflow.community.tavily \
        --hidden-import=deerflow.community.infoquest \
        --hidden-import=deerflow.community.exa \
        --hidden-import=deerflow.community.firecrawl \
        --hidden-import=deerflow.community.jina_ai \
        --hidden-import=deerflow.community.image_search \
        \
        --hidden-import=deerflow.tools.builtins \
        --hidden-import=deerflow.tools.builtins.tool_search \
        --hidden-import=deerflow.tools.skill_manage_tool \
        --hidden-import=deerflow.tools.builtins.invoke_acp_agent_tool \
        \
        --hidden-import=deerflow.guardrails.builtin \
        --hidden-import=deerflow.skills.storage.local_skill_storage \
        \
        --hidden-import=deerflow.runtime \
        --hidden-import=deerflow.runtime.converters \
        --hidden-import=deerflow.runtime.journal \
        --hidden-import=deerflow.runtime.serialization \
        --hidden-import=deerflow.runtime.user_context \
        --hidden-import=deerflow.runtime.checkpointer \
        --hidden-import=deerflow.runtime.checkpointer.async_provider \
        --hidden-import=deerflow.runtime.checkpointer.provider \
        --hidden-import=deerflow.runtime.events \
        --hidden-import=deerflow.runtime.events.store \
        --hidden-import=deerflow.runtime.events.store.base \
        --hidden-import=deerflow.runtime.events.store.db \
        --hidden-import=deerflow.runtime.events.store.jsonl \
        --hidden-import=deerflow.runtime.events.store.memory \
        --hidden-import=deerflow.runtime.runs \
        --hidden-import=deerflow.runtime.runs.manager \
        --hidden-import=deerflow.runtime.runs.schemas \
        --hidden-import=deerflow.runtime.runs.worker \
        --hidden-import=deerflow.runtime.runs.store \
        --hidden-import=deerflow.runtime.runs.store.base \
        --hidden-import=deerflow.runtime.runs.store.memory \
        --hidden-import=deerflow.runtime.store \
        --hidden-import=deerflow.runtime.store.async_provider \
        --hidden-import=deerflow.runtime.store.provider \
        --hidden-import=deerflow.runtime.store._sqlite_utils \
        --hidden-import=deerflow.runtime.stream_bridge \
        --hidden-import=deerflow.runtime.stream_bridge.async_provider \
        --hidden-import=deerflow.runtime.stream_bridge.base \
        --hidden-import=deerflow.runtime.stream_bridge.memory \
        \
        --hidden-import=deerflow.persistence \
        --hidden-import=deerflow.persistence.base \
        --hidden-import=deerflow.persistence.engine \
        --hidden-import=deerflow.persistence.feedback \
        --hidden-import=deerflow.persistence.feedback.model \
        --hidden-import=deerflow.persistence.feedback.sql \
        --hidden-import=deerflow.persistence.models \
        --hidden-import=deerflow.persistence.models.run_event \
        --hidden-import=deerflow.persistence.run \
        --hidden-import=deerflow.persistence.run.model \
        --hidden-import=deerflow.persistence.run.sql \
        --hidden-import=deerflow.persistence.thread_meta \
        --hidden-import=deerflow.persistence.thread_meta.base \
        --hidden-import=deerflow.persistence.thread_meta.memory \
        --hidden-import=deerflow.persistence.thread_meta.model \
        --hidden-import=deerflow.persistence.thread_meta.sql \
        --hidden-import=deerflow.persistence.user \
        --hidden-import=deerflow.persistence.user.model \
        \
        --hidden-import=langchain \
        --hidden-import=langchain_core \
        --hidden-import=langgraph \
        --hidden-import=langgraph.runtime \
        \
        --collect-all=langchain \
        --collect-all=langchain_core \
        --collect-all=langgraph \
        --collect-submodules=deerflow \
        --collect-all=funasr \
        --collect-all=modelscope \
        --collect-all=torch \
        --collect-all=transformers \
        --collect-all=soundfile \
        --collect-all=huggingface_hub \
        \
        --hidden-import=deerflow_extensions.voice_transcription \
        --hidden-import=deerflow_extensions.voice_transcription.startup \
        --hidden-import=deerflow_extensions.voice_transcription.router \
        --hidden-import=deerflow_extensions.voice_transcription.transcriber \
        \
        --exclude-module=tests \
        --exclude-module=docs \
        --exclude-module=tkinter \
        --exclude-module=matplotlib \
        \
        deerflow_entry.py 2>&1

    echo "  复制编译产物到 release/backend-bin/..."
    mkdir -p "$RELEASE_DIR/backend-bin"
    cp -r "$REPO_ROOT/backend/dist/deerflow-gateway" "$RELEASE_DIR/backend-bin/"
    # 清理编译中间文件
    rm -rf "$REPO_ROOT/backend/dist" "$REPO_ROOT/backend/build" "$REPO_ROOT/backend/deerflow-gateway.spec"

elif [ "$PREPARE_SERVER_BUILD" = true ]; then
    # ── 准备服务器编译：从本地缓存拷贝 Wheel ──────────────────────────
    echo "[4/10] 准备服务器编译依赖 (Wheel + 源码)..."
    cd "$REPO_ROOT/backend"

    echo "  安装后端依赖 (uv sync)..."
    rm -rf .venv
    uv sync

    echo "  导出依赖清单..."
    uv pip freeze | grep -v "^-e" > /tmp/requirements-server-$$.txt

    # 本地 Wheel 缓存：backend/wheels/（已 gitignore）
    LOCAL_WHEEL_DIR="$REPO_ROOT/backend/wheels"
    WHEEL_CACHE_COUNT=$(find "$LOCAL_WHEEL_DIR" -name '*.whl' 2>/dev/null | wc -l)

    if [ "$WHEEL_CACHE_COUNT" -eq 0 ]; then
        echo "  本地 Wheel 缓存为空，下载到 backend/wheels/..."
        mkdir -p "$LOCAL_WHEEL_DIR"
        uv pip install pip --quiet
        .venv/bin/pip download -r /tmp/requirements-server-$$.txt \
            --dest "$LOCAL_WHEEL_DIR" \
            --quiet
        echo "  清理 pip..."
        uv pip uninstall pip --quiet 2>/dev/null || true
    else
        echo "  ✓ 使用本地缓存 backend/wheels/（$WHEEL_CACHE_COUNT 个 Wheel）"
    fi

    # 拷贝到 release/source/
    echo "  拷贝 Wheel 到 release/source/wheels/..."
    mkdir -p "$RELEASE_DIR/source/wheels"
    cp "$LOCAL_WHEEL_DIR"/*.whl "$RELEASE_DIR/source/wheels/"
    cp /tmp/requirements-server-$$.txt "$RELEASE_DIR/source/requirements.txt"
    # 同时写一份到 backend/，rsync 到服务器 source/ 时会一起携带
    cp /tmp/requirements-server-$$.txt "$REPO_ROOT/backend/requirements.txt"
    rm -f /tmp/requirements-server-$$.txt

    WHEEL_COUNT=$(find "$RELEASE_DIR/source/wheels" -name '*.whl' 2>/dev/null | wc -l)
    echo "  ✓ 已就绪 $WHEEL_COUNT 个 Wheel 文件"

    echo "  拷贝服务器编译脚本到 source/scripts/..."
    mkdir -p "$RELEASE_DIR/source/scripts"
    cp "$REPO_ROOT/backend/scripts/build-backend-on-server.sh" "$RELEASE_DIR/source/scripts/"
    chmod +x "$RELEASE_DIR/source/scripts/build-backend-on-server.sh"

    echo "  创建空占位目录 (backend-bin)..."
    mkdir -p "$RELEASE_DIR/backend-bin"
    echo "  ✓ 服务器编译依赖准备完成"
    echo ""
    echo "  提醒: 部署后服务器上执行以下命令编译:"
    echo "    cd <服务器部署路径>/source && bash scripts/build-backend-on-server.sh"
    echo "    rm -rf <服务器部署路径>/backend-bin && cp -r dist/deerflow-gateway <服务器部署路径>/backend-bin/"

else
    # ── 跳过后端（纯前端）─────────────────────────────────────────────
    echo "[4/10] ⏩ 跳过后端编译 (--skip-backend)"
    echo "  提醒: 在服务器上执行 backend/scripts/build-backend-on-server.sh 编译后端"
    echo "        然后将 backend-bin/ 传回 release/ 目录"
    mkdir -p "$RELEASE_DIR/backend-bin"
fi

cd "$REPO_ROOT"

# ── 复制 SenseVoice 模型（离线推理用，第一次下载后永不重复下载）───────────

echo "[4.5/10] 复制 SenseVoice 模型..."
if [ -d "$REPO_ROOT/models/sensevoice" ]; then
    mkdir -p "$RELEASE_DIR/models/sensevoice"
    cp -r "$REPO_ROOT/models/sensevoice/"* "$RELEASE_DIR/models/sensevoice/"
    echo "  ✓ SenseVoice 模型已复制 ($(du -sh "$REPO_ROOT/models/sensevoice" | cut -f1))"
else
    echo "  ⚠️  models/sensevoice 不存在，跳过（首次运行将自动下载）"
fi

# ── 复制 Skills ─────────────────────────────────────────────────────────────

echo "[5/10] 复制 Skills..."
rsync -av --no-g --no-o \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    skills/ "$RELEASE_DIR/skills/" || true

# ── 复制脚本 ───────────────────────────────────────────────────────────────

echo "[6/11] 复制启动脚本..."
cp scripts/server-release.sh "$RELEASE_DIR/scripts/deerflow.sh"
cp scripts/wait-for-port.sh "$RELEASE_DIR/scripts/"
cp scripts/wait-for-deeprag.sh "$RELEASE_DIR/scripts/"
chmod +x "$RELEASE_DIR/scripts/"*.sh

# ── 适配并复制 Nginx 配置 ───────────────────────────────────────────────────

echo "[7/11] 生成 Nginx 配置..."
cp "$REPO_ROOT/docker/nginx/server.conf" "$RELEASE_DIR/nginx/server.conf"
cp "$REPO_ROOT/docker/nginx/deeprag.conf" "$RELEASE_DIR/nginx/deeprag.conf"

# ── 复制 DeepRAG 服务 ───────────────────────────────────────────────────────

echo "[8/11] 复制 DeepRAG 服务..."
if [ -d "$REPO_ROOT/deepRag/bin/deep-rag-backend" ]; then
    cp -r "$REPO_ROOT/deepRag/bin/deep-rag-backend" "$RELEASE_DIR/deepRag/bin/"
    echo "  ✓ deep-rag-backend 二进制已复制"
else
    echo "  ⚠️  DeepRAG 二进制不存在（deepRag/bin/deep-rag-backend/），请先编译"
fi
if [ -d "$REPO_ROOT/deepRag/frontend" ]; then
    cp -r "$REPO_ROOT/deepRag/frontend/"* "$RELEASE_DIR/deepRag/frontend/"
    echo "  ✓ DeepRAG 前端已复制"
else
    echo "  ⚠️  DeepRAG 前端不存在（deepRag/frontend/），跳过"
fi
cp "$REPO_ROOT/deepRag/.env.example" "$RELEASE_DIR/deepRag/.env.example"
echo "  ✓ DeepRAG .env.example 已复制"
# 复制知识库文件（含目录结构）
if [ -d "$REPO_ROOT/deepRag/Knowledge-Base" ] && [ "$(ls -A "$REPO_ROOT/deepRag/Knowledge-Base" 2>/dev/null)" ]; then
    cp -r "$REPO_ROOT/deepRag/Knowledge-Base/"* "$RELEASE_DIR/deepRag/Knowledge-Base/"
    echo "  ✓ DeepRAG 知识库文件已复制"
else
    touch "$RELEASE_DIR/deepRag/Knowledge-Base/.gitkeep"
    echo "  ✓ DeepRAG 知识库空目录已创建（无源文件）"
fi
if [ -d "$REPO_ROOT/deepRag/Knowledge-Base-Chunks" ] && [ "$(ls -A "$REPO_ROOT/deepRag/Knowledge-Base-Chunks" 2>/dev/null)" ]; then
    cp -r "$REPO_ROOT/deepRag/Knowledge-Base-Chunks/"* "$RELEASE_DIR/deepRag/Knowledge-Base-Chunks/"
    echo "  ✓ DeepRAG 知识库 Chunks 已复制"
else
    touch "$RELEASE_DIR/deepRag/Knowledge-Base-Chunks/.gitkeep"
fi
if [ -d "$REPO_ROOT/deepRag/Knowledge-Base-File-Summary" ] && [ "$(ls -A "$REPO_ROOT/deepRag/Knowledge-Base-File-Summary" 2>/dev/null)" ]; then
    cp -r "$REPO_ROOT/deepRag/Knowledge-Base-File-Summary/"* "$RELEASE_DIR/deepRag/Knowledge-Base-File-Summary/"
    echo "  ✓ DeepRAG 知识库 File Summary 已复制"
else
    touch "$RELEASE_DIR/deepRag/Knowledge-Base-File-Summary/.gitkeep"
fi

# ── 复制配置文件 ────────────────────────────────────────────────────────────

echo "[9/11] 复制配置文件..."

# 复制主配置
cp "$REPO_ROOT/config.yaml" "$RELEASE_DIR/config.yaml"
cp "$REPO_ROOT/config.example.yaml" "$RELEASE_DIR/config.example.yaml"
# 修正 skills.path 为相对路径
if grep -q '^skills:$' "$RELEASE_DIR/config.yaml"; then
    sed -i '/^skills:$/a\  path: ./skills' "$RELEASE_DIR/config.yaml"
else
    echo -e "\nskills:\n  path: ./skills" >> "$RELEASE_DIR/config.yaml"
fi
echo "  ✓ config.yaml 已复制（skills.path 已设为 ./skills）"

# 复制 MCP 配置
cp "$REPO_ROOT/extensions_config.json" "$RELEASE_DIR/extensions_config.json"
# 修正 ADS 路径和 URL（保留端口）
sed -i 's|/app/ads-mcp/|mcp-agent-mcp/|g' "$RELEASE_DIR/extensions_config.json"
sed -E -i 's|https?://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(:[0-9]+)|http://127.0.0.1\1|g' "$RELEASE_DIR/extensions_config.json"
# 精确修正 deeprag URL（替代脆弱 sed 全局替换，确保 /mcp/ 路径正确）
if command -v jq > /dev/null 2>&1; then
    jq '.mcpServers.deeprag.url = "http://127.0.0.1:86/mcp/"' "$RELEASE_DIR/extensions_config.json" > /tmp/deeprag_extensions_config.json && mv /tmp/deeprag_extensions_config.json "$RELEASE_DIR/extensions_config.json"
fi
# ADS_API_BASE_URL 在 release 下无用（config.json 优先级更高），删除避免混淆
sed -i '/ADS_API_BASE_URL/d' "$RELEASE_DIR/extensions_config.json"
cp "$REPO_ROOT/extensions_config.example.json" "$RELEASE_DIR/extensions_config.example.json"
echo "  ✓ extensions_config.json 已复制（URL 已修正为 127.0.0.1，含 example 模板）"

# 复制 .env.example（不拷贝 .env，避免泄露敏感信息）
cp "$REPO_ROOT/.env.example" "$RELEASE_DIR/.env.example"
echo "  ✓ .env.example 已复制（部署后请根据模板创建 .env）"

# ── ADS MCP（可选组件）───────────────────────────────────────────────────────

echo "[10/11] ADS MCP..."
ADS_MCP_DIR="${REPO_ROOT}/mcp-agent-mcp"
if [ -d "$ADS_MCP_DIR" ]; then
    echo "  检测到 ADS MCP..."
    if [ ! -d "$ADS_MCP_DIR/dist" ]; then
        echo "  ⚠️  ADS MCP 未构建（缺少 dist/）"
        echo "  ⚠️  请先执行：cd $ADS_MCP_DIR && npm install && npm run build"
        echo "  ⚠️  跳过 ADS MCP..."
    else
        echo "  复制 ADS MCP..."
        rsync -av --no-g --no-o \
            --exclude='__pycache__' \
            --exclude='.git' \
            "$ADS_MCP_DIR/" "$RELEASE_DIR/mcp-agent-mcp/" || true
        # 修正 ADS 服务器地址为 127.0.0.1，清理 token
        ADS_CONFIG="$RELEASE_DIR/mcp-agent-mcp/.mcp-server/config.json"
        if [ -f "$ADS_CONFIG" ]; then
            sed -i 's|http://[0-9.]*:[0-9]*|http://127.0.0.1:80|g' "$ADS_CONFIG"
            sed -i 's|"value": *"[^"]*"|"value": ""|g' "$ADS_CONFIG"
            sed -i 's|"password": *"[^"]*"|"password": ""|g' "$ADS_CONFIG"
            echo "  ✓ ADS config 已清理（url=127.0.0.1:80, token/password 已清除）"
        fi
        echo "  ✓ ADS MCP 复制完成"
    fi
else
    echo "  ⏩ 未检测到 ADS MCP（deer-flow/mcp-agent-mcp/ 不存在），跳过"
fi

# ── 复制使用文档 ────────────────────────────────────────────────────────────

echo "[11/11] 生成 README.md（部署使用说明）..."
if [ -f "$REPO_ROOT/docs/operations/USE_GUIDE.md" ]; then
    cp "$REPO_ROOT/docs/operations/USE_GUIDE.md" "$RELEASE_DIR/README.md"
    echo "  ✓ README.md 已生成"
else
    echo "  ⚠️  docs/operations/USE_GUIDE.md 不存在，跳过"
fi

# ── 完成 ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  ✓ Release 构建完成！"
echo "=========================================="
echo ""
echo "  产物目录: $RELEASE_DIR"
echo ""
echo "  目录大小:"
du -sh "$RELEASE_DIR"/*
echo ""
echo "  下一步："
echo "  1. 上传到服务器："
echo "     rsync -avz --progress -e 'ssh -p 2222' $RELEASE_DIR/ user@192.168.1.56:/usr/xccloud/deerflow/"
echo ""
echo "  2. 在服务器上配置并启动："
echo "     cd /usr/xccloud/deerflow"
echo "     cp config.example.yaml config.yaml"
echo "     vim config.yaml  # 编辑 API keys + 添加 supports_thinking: true"
echo "     vim extensions_config.json  # 修改 ADS MCP 路径（如需要）"
echo "     ./scripts/serve.sh --prod"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  部署常见问题（详见 docs/operations/DEPLOYMENT_KNOWN_ISSUES.md）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  1. Pro / Ultra 模式不可选"
echo "     → config.yaml 中模型配置需加 supports_thinking: true"
echo ""
echo "  2. ADS MCP 路径错误的 ENOENT"
echo "     → extensions_config.json 中的 args 指向 /app/ads-mcp/"
echo "     → 必须改为服务器实际路径或相对路径 ../mcp-agent-mcp/"
echo ""
echo "  3. 前端启动失败（Module not found: @/...）"
echo "     → 检查 release/frontend/ 是否缺少 package.json 或 node_modules"
echo "     → 脚本已自动执行 pnpm install --prod"
echo ""
echo "  4. 后端 PyInstaller 编译"
echo "     → cd backend && bash build-backend.sh"
echo "     → 产物: dist/deerflow-gateway/（ELF 二进制，无 .py 源码）"
echo ""
