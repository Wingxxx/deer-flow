#!/usr/bin/env bash
#
# wait-for-deeprag.sh — 等待 DeepRAG 服务就绪
#
# 用法:
#   ./wait-for-deeprag.sh              # 默认超时 120s
#   ./wait-for-deeprag.sh 180          # 自定义超时 180s
#
# 环境变量:
#   DEEPRAG_TIMEOUT=180               # 覆盖默认超时
#
# 检测策略:
#   HTTP health check GET /（后端路由）。不使用 ss 表达式语法，
#   避免旧版 iproute2 上的 SIGSEGV 兼容性问题。
#
# 返回:
#   0 = 服务就绪
#   1 = 超时未就绪

set -e

TIMEOUT="${1:-${DEEPRAG_TIMEOUT:-120}}"
INTERVAL=2
elapsed=0
PROGRESS_INTERVAL=15
next_progress=$PROGRESS_INTERVAL

while [ "$elapsed" -lt "$TIMEOUT" ]; do
    # 进度输出（每 15s）
    if [ "$elapsed" -ge "$next_progress" ]; then
        echo "  [wait-for-deeprag] 等待中... ${elapsed}s / ${TIMEOUT}s"
        next_progress=$((next_progress + PROGRESS_INTERVAL))
    fi

    # HTTP health check（deeprag 后端路由为 GET /）
    if curl -sf --max-time 3 "http://127.0.0.1:5172/" > /dev/null 2>&1; then
        exit 0
    fi

    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

echo "[wait-for-deeprag] DeepRAG 启动超时 (${TIMEOUT}s)"
echo "[wait-for-deeprag] === 诊断信息 ==="
echo "磁盘: $(df -h "$(pwd)" 2>/dev/null | tail -1)"
echo "内存: $(free -h 2>/dev/null | grep Mem || echo 'N/A')"
echo "进程: $(ps aux 2>/dev/null | grep deep-rag-backend | grep -v grep || echo '无')"
echo "端口 5172: $(ss -tlnp 2>/dev/null | grep ':5172 ' || echo '未监听')"
echo "端口 8172: $(ss -tlnp 2>/dev/null | grep ':8172 ' || echo '未监听')"
echo "curl 5172: $(curl -sf --max-time 3 http://127.0.0.1:5172/ 2>&1 || echo '不可达')"
exit 1
