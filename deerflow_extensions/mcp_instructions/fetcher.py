"""Fetch per-server instructions from the MCP initialize handshake.

Concurrency is bounded: up to ``_MAX_CONCURRENCY`` servers handshake in
parallel (Semaphore — stdio servers spawn subprocesses, unbounded would be a
process storm); per-server timeout bounds the total wall time to ~max (not
sum). The timeout wraps only
``session.initialize()``: ``asyncio.wait_for`` cancels the inner task, never
``fetch_one`` itself, so the cleanup can be awaited directly in the same
task (anyio cancel scopes REQUIRE enter/exit in the same task — wrapping
``__aexit__`` in ``asyncio.shield`` spawns a new task and blows up with
"Attempted to exit cancel scope in a different task than it was entered in").
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# 与 startup.py 共享的超时/预算（env 可覆盖，见 README）
_HANDSHAKE_TIMEOUT = float(os.getenv("MCP_INSTRUCTIONS_HANDSHAKE_TIMEOUT", "30"))
# 抓取侧即截断，registry 不驻留超大文本；渲染时仍会按预算再截（第二道闸）。
# 与 startup._PER_SERVER_LIMIT 同读一个 env，各自独立定义（不跨模块耦合）
_PER_SERVER_LIMIT = int(os.getenv("MCP_INSTRUCTIONS_PER_SERVER_LIMIT", "2000"))
# 并发上限：stdio 服务器会 spawn 子进程，无上限并发 = 子进程风暴
_MAX_CONCURRENCY = int(os.getenv("MCP_INSTRUCTIONS_MAX_CONCURRENCY", "4"))


async def fetch_all_instructions() -> dict[str, str]:
    """Return {server_name: instructions} for all enabled MCP servers.

    One failing server never blocks others (per-server try/except + warning,
    mirroring get_mcp_tools' fault-tolerance style). Servers without
    instructions are omitted. Concurrent: total wall time is bounded by the
    slowest server, not the sum.
    """
    from deerflow.config.extensions_config import ExtensionsConfig
    from deerflow.mcp.client import build_servers_config
    from deerflow.mcp.oauth import get_initial_oauth_headers
    from langchain_mcp_adapters.sessions import create_session

    extensions_config = ExtensionsConfig.from_file()
    servers_config = build_servers_config(extensions_config)
    if not servers_config:
        return {}
    try:
        oauth_headers = await get_initial_oauth_headers(extensions_config)
    except Exception:
        oauth_headers = {}

    # 并发上限：Semaphore 限制同时 spawn/握手的服务器数（stdio 子进程风暴防护）
    sem = asyncio.Semaphore(max(1, _MAX_CONCURRENCY))

    async def fetch_one(name: str, connection: dict) -> tuple[str, str] | None:
        async with sem:
            conn = dict(connection)
            if conn.get("transport") in ("sse", "http") and oauth_headers.get(name):
                headers = dict(conn.get("headers") or {})
                headers["Authorization"] = oauth_headers[name]
                conn["headers"] = headers
            cm = create_session(conn)
            try:
                session = await cm.__aenter__()
            except Exception as e:
                logger.warning("[MCPInstructions] connect failed for '%s': %s", name, e)
                return None
            try:
                # 超时只包握手；wait_for 取消的是内部 task，fetch_one 未被取消，
                # 同一 task 内直接 await 清理（shield 会换 task 执行 __aexit__，
                # 违反 anyio cancel scope 同 task 约束 → RuntimeError）
                result = await asyncio.wait_for(session.initialize(), timeout=_HANDSHAKE_TIMEOUT)
            except Exception as e:
                logger.warning("[MCPInstructions] initialize failed for '%s': %s", name, e)
                return None
            finally:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass  # 清理失败不掩盖握手结果
            text = getattr(result, "instructions", None)
            # str 白名单：跳过 mock/异常返回值
            if isinstance(text, str) and text.strip():
                return name, text.strip()[:_PER_SERVER_LIMIT]
            return None

    results = await asyncio.gather(
        *(fetch_one(n, c) for n, c in servers_config.items()),
        return_exceptions=True,
    )
    collected: dict[str, str] = {}
    for r in results:
        if isinstance(r, tuple):
            collected[r[0]] = r[1]
    return collected
