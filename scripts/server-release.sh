#!/usr/bin/env bash
#
# server-release.sh — DeerFlow release 服务管理脚本
#
# 用法：
#   ./scripts/deerflow.sh                    # 启动服务（DeepRAG → Gateway → Frontend）
#   ./scripts/deerflow.sh --stop             # 停止全部服务
#   ./scripts/deerflow.sh --skip-deeprag     # 仅启动 DeerFlow（跳过 DeepRAG）
#
# 说明：
#   启动后按顺序运行 DeepRAG → Gateway → Frontend。
#   带 PID 文件防重、文件锁防并发、三层健康检测。
#   日志输出到 release/logs/ 目录下。
#
# 前置要求：
#   1. 在 release/ 目录下创建 .env 文件，至少配置以下变量：
#      - ADS_BASE_URL=https://your-ads-server   # ADS 认证服务器地址（必填）
#      - DEEPSEEK_API_KEY=xxx                    # 或其他模型 API Key
#      - ADS_MCP_CONFIG_PATH=path/to/config.json # ADS MCP 配置路径（可选）
#   2. backend-bin/deerflow-gateway 二进制文件（ELF 可执行文件）
#   3. frontend/ 目录为 Next.js standalone 构建产物
#   4. deepRag/bin/deep-rag-backend/ 二进制文件（可选，--skip-deeprag 可跳过）
#
# 注意：.env 中的值不要加反引号 `...`，否则 shell 会将其当作命令执行
#
# 目录结构说明：
#   backend-bin/ 是 dist/deerflow-gateway/ 的整体复制
#   即 backend-bin/deerflow-gateway/ 目录（内含二进制 + _internal/）
#   路径写法为 ./backend-bin/deerflow-gateway

set -e

SELF="$(basename "$0")"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ACTION="start"
SKIP_DEEPRAG=false

for arg in "$@"; do
    case "$arg" in
        --stop)        ACTION="stop" ;;
        --skip-deeprag) SKIP_DEEPRAG=true ;;
        *)
            echo "用法: $0 [--stop] [--skip-deeprag]"
            exit 1
            ;;
    esac
done

mkdir -p logs .deer-flow

DEEPRAG_PIDFILE=".deer-flow/deeprag.pid"
DEEPRAG_BIN="./deepRag/bin/deep-rag-backend/deep-rag-backend"

# ── DeepRAG 进程检测 ───────────────────────────────────────────────────────

is_deeprag_alive() {
    [ -f "$DEEPRAG_PIDFILE" ] || return 1
    local pid
    pid=$(cat "$DEEPRAG_PIDFILE" 2>/dev/null)
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    grep -q "deep-rag-backend" "/proc/$pid/cmdline" 2>/dev/null
}

# ── 停止 DeepRAG ──────────────────────────────────────────────────────────

stop_deeprag() {
    if [ ! -f "$DEEPRAG_PIDFILE" ]; then
        # 无 PID 文件时尝试按进程名杀
        pkill -f "deep-rag-backend" 2>/dev/null || true
        return
    fi
    local pid
    pid=$(cat "$DEEPRAG_PIDFILE" 2>/dev/null)
    if [ -z "$pid" ]; then
        rm -f "$DEEPRAG_PIDFILE"
        return
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "  DeepRAG 进程已不存在（PID $pid），清理 PID 文件"
        rm -f "$DEEPRAG_PIDFILE"
        return
    fi
    echo "  正在停止 DeepRAG（PID $pid）..."
    kill "$pid" 2>/dev/null || true
    # 等待优雅退出（最长 15s）
    for _ in $(seq 1 15); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "  DeepRAG 未响应 SIGTERM，发送 SIGKILL..."
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$DEEPRAG_PIDFILE"
    echo "  ✓ DeepRAG 已停止"
}

# ── 清理端口 ──────────────────────────────────────────────────────────────

cleanup_port() {
    local port="$1"
    local pid
    pid=$(ss -tlnp 2>/dev/null | grep ":$port " | sed 's/.*pid=\([0-9]*\).*/\1/')
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
}

# ── 启动 DeepRAG ──────────────────────────────────────────────────────────

start_deeprag() {
    if [ "$SKIP_DEEPRAG" = true ]; then
        echo "⏩ --skip-deeprag 指定，跳过 DeepRAG 启动"
        if curl -sf --max-time 2 http://127.0.0.1:5172/ > /dev/null 2>&1; then
            echo "  DeepRAG 端口 5172 在监听，Gateway 可正常连接 MCP"
        else
            echo "  ⚠️  DeepRAG 未运行（端口 5172 未监听），MCP 功能不可用"
        fi
        return
    fi

    # 防重检测：PID 文件 + /proc 校验
    if is_deeprag_alive; then
        echo "DeepRAG 已在运行（PID $(cat "$DEEPRAG_PIDFILE")），跳过启动"
        return
    fi

    # PID 文件存在但进程已死 -> 清理
    rm -f "$DEEPRAG_PIDFILE"

    # 预检：二进制存在且可执行
    if [ ! -f "$DEEPRAG_BIN" ]; then
        echo "⚠️  DeepRAG 二进制不存在: $DEEPRAG_BIN，跳过启动（--skip-deeprag 可显式跳过）"
        return
    fi
    if [ ! -x "$DEEPRAG_BIN" ]; then
        echo "  DeepRAG 二进制不可执行，设置权限..."
        chmod +x "$DEEPRAG_BIN"
    fi

    echo "启动 DeepRAG..."
    cd deepRag
    "./bin/deep-rag-backend/deep-rag-backend" > ../logs/deeprag.log 2>&1 &
    local pid=$!
    cd ..
    echo "$pid" > "$DEEPRAG_PIDFILE"

    echo "  等待 DeepRAG 就绪（TCP :5172 + :8172 + HTTP health check，最长 120s）..."
    if "$SCRIPTS_DIR/wait-for-deeprag.sh" 120; then
        echo "✓ DeepRAG 已就绪 (API: localhost:5172, MCP: localhost:8172)"
    else
        echo "⚠️  DeepRAG 启动超时（120s），继续启动 Gateway（MCP 功能可能不可用）"
        echo "  查看日志: tail -30 logs/deeprag.log"
        echo "  如需跳过 DeepRAG 可使用 --skip-deeprag 参数"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
#  停止
# ═══════════════════════════════════════════════════════════════════════════

if [ "$ACTION" = "stop" ]; then
    echo "正在停止 DeerFlow 服务..."

    # 1. 停止 DeerFlow（Gateway + Frontend）
    pkill -f "deerflow-gateway" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    pkill -f "server\.js" 2>/dev/null || true
    sleep 1

    # 2. 强制释放端口
    for port in 8001 3000; do
        cleanup_port "$port"
    done
    sleep 1
    for port in 8001 3000; do
        cleanup_port "$port"
    done

    echo "✓ DeerFlow 已停止"
    echo ""
    echo "DeepRAG 未停止（如需手动停止）:"
    echo "  pkill -f deep-rag-backend"
    echo "  # 或按 PID 停止:"
    echo "  cat .deer-flow/deeprag.pid 2>/dev/null | xargs kill"
    echo ""
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════════════════════════════════

echo "清理残留进程..."
pkill -f "deerflow-gateway" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "server\.js" 2>/dev/null || true
pkill -f "deep-rag-backend" 2>/dev/null || true
for port in 8001 3000 5172 8172; do
    cleanup_port "$port"
done
sleep 2

echo "=========================================="
echo "  DeerFlow 启动中"
echo "=========================================="
echo ""

# ── 0. Node.js PATH 兜底（Gateway MCP 与 Frontend 共用）────────────────────
# 部署机在登录前自启（systemd/cron @reboot 等）时，nvm 安装的 node 尚未注入 PATH，
# 而 Gateway 的 MCP（stdio, command=node）与 Frontend standalone 均依赖 node。
# 此处解析一次 node 并注入 PATH，使 Gateway 的 MCP 子进程也能继承。
# 解析失败仅告警不阻断：与现状一致，服务可起但 MCP 工具不可用。
NODE_BIN="$(command -v node 2>/dev/null || true)"
if [ -z "$NODE_BIN" ]; then
    echo "  ⚠️  PATH 中未找到 node，尝试硬编码路径 /root/.nvm/versions/node/v22.22.3/bin/node"
    NODE_BIN="/root/.nvm/versions/node/v22.22.3/bin/node"
fi
if [ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ]; then
    export PATH="$(dirname "$NODE_BIN"):$PATH"
    echo "  ✓ node: $NODE_BIN"
else
    echo "  ⚠️  node 不可用（${NODE_BIN:-未找到}），MCP 服务与 Frontend 将无法使用"
fi

# ── 1. 启动 DeepRAG ────────────────────────────────────────────────────────
start_deeprag

# ── 2. 启动 Gateway ────────────────────────────────────────────────────────
echo ""
echo "启动 Gateway (端口 8001)..."
DEER_FLOW_CONFIG_PATH="$(pwd)/config.yaml"
env DEER_FLOW_CONFIG_PATH="$DEER_FLOW_CONFIG_PATH" \
    ./backend-bin/deerflow-gateway \
    > logs/gateway.log 2>&1 &

"$SCRIPTS_DIR/wait-for-port.sh" 8001 120 "Gateway" || {
    echo "✗ Gateway 启动失败，查看日志: tail -30 logs/gateway.log"
    exit 1
}
echo "✓ Gateway 已就绪 (localhost:8001)"

# ── 3. 启动 Frontend ───────────────────────────────────────────────────────
echo ""
echo "启动 Frontend (端口 3000)..."
# 必须显式 HOSTNAME=0.0.0.0：server.js 默认读取环境变量 HOSTNAME（Linux shell 恒为主机名），
# 不设置会绑定到主机名解析地址（如 127.0.1.1），导致 nginx 127.0.0.1:3000 反代 502
# NODE_BIN 已在前部解析并注入 PATH（见 "Node.js PATH 兜底" 段）
if [ ! -x "$NODE_BIN" ]; then
    echo "✗ node 不可用（$NODE_BIN），无法启动 Frontend"
    exit 1
fi
cd frontend && HOSTNAME=0.0.0.0 PORT=3000 "$NODE_BIN" .next/standalone/server.js \
    > ../logs/frontend.log 2>&1 &
cd ..

"$SCRIPTS_DIR/wait-for-port.sh" 3000 120 "Frontend" || {
    echo "✗ Frontend 启动失败，查看日志: tail -30 logs/frontend.log"
    exit 1
}
echo "✓ Frontend 已就绪 (localhost:3000)"

echo ""
echo "=========================================="
echo "  ✓ DeerFlow 运行中"
echo "=========================================="
echo ""
echo "  DeepRAG API: localhost:5172"
echo "  DeepRAG MCP: localhost:8172"
echo "  Gateway:     localhost:8001"
echo "  Frontend:    localhost:3000"
echo ""
echo "  访问: http://<服务器IP>:3000/"
echo "  API:  http://<服务器IP>:8001/"
echo ""
echo "  停止: ./scripts/${SELF} --stop"
echo "  日志: logs/gateway.log, logs/frontend.log, logs/deeprag.log"
echo ""
