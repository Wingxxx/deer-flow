"""Per-server MCP tool loading isolation (zero core-source intrusion).

Replaces the module attributes ``deerflow.mcp.tools.get_mcp_tools``,
``deerflow.mcp.get_mcp_tools`` (package re-export), and the
``cache.initialize_mcp_tools`` pair with a patched copy of the upstream
call skeleton in which every configured MCP server is loaded independently —
one failing server no longer kills all the others.

Version sentinel (AND semantics: EVERY channel must pass, otherwise the
patch is skipped with a warning — rather no patch than a broken one):
  1. bytecode (``__code__.co_names`` / ``co_consts``) of ``get_mcp_tools``
  2. existence + minimum positional-arg count of the helper symbols
  3. third-party ``MultiServerMCPClient.get_tools`` ``server_name`` keyword-only
``inspect.getsource`` is NEVER the primary channel — PyInstaller frozen
builds have no source files and would raise OSError; it is only an optional
dev-mode double-check (get-source failure degrades to pass, parameter-name
mismatch blocks).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import sys
import threading
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)  # 扩展生命周期日志（哨兵/apply/unpatch，不混入上游 logger）

_APPLIED = False
_original_get_mcp_tools: Any = None
_original_pkg_get_mcp_tools: Any = None
_original_initialize_mcp_tools: Any = None
_original_pkg_initialize_mcp_tools: Any = None
_last_load_failed = False  # 最近一次加载是否有 per-server 失败（缓存防线用）
_apply_lock = threading.Lock()

# ---- 上游特征基线（实测 backend/packages/harness/deerflow/mcp/tools.py @ 2026-08-19）----
_EXPECTED_CO_NAMES = frozenset(
    {
        "ExtensionsConfig",
        "build_servers_config",
        "get_initial_oauth_headers",
        "build_oauth_tool_interceptor",
        "resolve_variable",
        "_make_session_pool_tool",
        "make_sync_tool_wrapper",
        "get_tools",
    }
)
_EXPECTED_CO_CONSTS = frozenset(
    {
        "Failed to load MCP tools: ",
        "Successfully loaded ",
    }
)
# 辅助符号 → 最小位置参数个数（按 _patched 骨架的调用方式校验，不硬编码完整签名）
_HELPER_MIN_ARGS = {
    "get_initial_oauth_headers": 1,
    "build_oauth_tool_interceptor": 1,
    "resolve_variable": 1,
    "build_servers_config": 1,
    "_make_session_pool_tool": 4,
    "make_sync_tool_wrapper": 2,
}


# ---- 版本哨兵：AND 语义三通道 + getsource dev 增强 ----


def _timeout_from_env() -> float:
    """解析 MCP_RESILIENCE_PER_SERVER_TIMEOUT；非法/非正数回退 30。"""
    raw = os.environ.get("MCP_RESILIENCE_PER_SERVER_TIMEOUT", "30")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        logger.warning("[MCPResilience] invalid MCP_RESILIENCE_PER_SERVER_TIMEOUT=%r, fallback 30", raw)
        return 30.0
    if parsed <= 0:
        logger.warning("[MCPResilience] MCP_RESILIENCE_PER_SERVER_TIMEOUT=%r must be positive, fallback 30", raw)
        return 30.0
    return parsed


def _check_bytecode(fn: Any) -> bool:
    """通道 1：get_mcp_tools 字节码特征（frozen 兼容主通道）。"""
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    string_consts = {c for c in code.co_consts if isinstance(c, str)}
    return _EXPECTED_CO_NAMES <= set(code.co_names) and _EXPECTED_CO_CONSTS <= string_consts


def _check_helpers(mod: Any) -> str | None:
    """通道 2：辅助符号存在性 + 最小位置参数个数。None=通过，否则原因。"""
    for helper, min_args in _HELPER_MIN_ARGS.items():
        h = getattr(mod, helper, None)
        if h is None or not callable(h):
            return f"helper symbol {helper} missing"
        try:
            sig = inspect.signature(h)
        except (ValueError, TypeError):
            continue  # C 扩展/内置 → 降级为仅存在性
        n_pos = sum(
            1
            for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        )
        if n_pos < min_args:
            return f"helper {helper} signature changed: expected >= {min_args} positional args, got {n_pos}"
    return None


def _check_library_signature(client_cls: Any) -> str | None:
    """通道 3：第三方 get_tools 的 server_name 必须为 keyword-only（库升级 →
    TypeError 会被 per-server except 吞掉导致全部失败，必须前置拦截）。"""
    try:
        sig = inspect.signature(client_cls.get_tools)
    except (ValueError, TypeError) as e:
        return f"MultiServerMCPClient.get_tools signature unavailable: {e}"
    server_param = sig.parameters.get("server_name")
    if server_param is None or server_param.kind != inspect.Parameter.KEYWORD_ONLY:
        return "MultiServerMCPClient.get_tools lost server_name keyword-only param"
    return None


def _getsource_enhancement(mod: Any) -> bool:
    """dev 增强：非 frozen 且可获取源码时，校验 _make_session_pool_tool 参数名。

    获取失败（OSError/TypeError，如 frozen 无源码）→ 降级通过、不阻断（消除
    dev/frozen 两套行为差异）；获取成功但参数名不符 → 阻断（dev 环境信息充分，
    拦截更严）。
    """
    if getattr(sys, "frozen", False):
        return True
    try:
        source = inspect.getsource(mod._make_session_pool_tool)
    except (OSError, TypeError):
        return True
    compact = "".join(source.split())
    return (
        "def_make_session_pool_tool(" in compact
        and "server_name:str," in compact
        and "connection:dict" in compact
    )


def _verify_patch_target() -> str | None:
    """Return None if the upstream target matches expectations, else the
    human-readable reason for skipping the patch. AND semantics."""
    try:
        import deerflow.mcp.tools as _mcp_tools
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as e:
        return f"deerflow/langchain_mcp_adapters import failed: {e}"

    fn = getattr(_mcp_tools, "get_mcp_tools", None)
    if fn is None or not callable(fn):
        return "deerflow.mcp.tools.get_mcp_tools missing or not callable"

    # 通道 1：字节码特征（frozen 兼容主通道）
    if not _check_bytecode(fn):
        return "bytecode co_names/co_consts mismatch"

    # 通道 2：辅助符号存在性 + 最小参数个数
    reason = _check_helpers(_mcp_tools)
    if reason is not None:
        return reason

    # dev 增强（放在符号检测后：符号已过时 getsource 是追加校验）
    if not _getsource_enhancement(_mcp_tools):
        return "getsource sanity check failed"

    # 通道 3：第三方库签名
    reason = _check_library_signature(MultiServerMCPClient)
    if reason is not None:
        return reason

    return None


def unpatch_all() -> None:
    """Restore all four attributes and reset state. Idempotent."""
    global _APPLIED, _original_get_mcp_tools, _original_pkg_get_mcp_tools
    global _original_initialize_mcp_tools, _original_pkg_initialize_mcp_tools
    global _last_load_failed

    if not _APPLIED:
        return

    import deerflow.mcp as _mcp_pkg
    import deerflow.mcp.cache as _cache
    import deerflow.mcp.tools as _mcp_tools

    if _original_get_mcp_tools is not None:
        _mcp_tools.get_mcp_tools = _original_get_mcp_tools
    if _original_pkg_get_mcp_tools is not None:
        _mcp_pkg.get_mcp_tools = _original_pkg_get_mcp_tools
    if _original_initialize_mcp_tools is not None:
        _cache.initialize_mcp_tools = _original_initialize_mcp_tools
    if _original_pkg_initialize_mcp_tools is not None:
        _mcp_pkg.initialize_mcp_tools = _original_pkg_initialize_mcp_tools

    _original_get_mcp_tools = None
    _original_pkg_get_mcp_tools = None
    _original_initialize_mcp_tools = None
    _original_pkg_initialize_mcp_tools = None
    _last_load_failed = False
    _APPLIED = False
    logger.info("[MCPResilience] patch unapplied")


async def _patched_get_mcp_tools() -> list[BaseTool]:
    """Patched copy of upstream ``get_mcp_tools`` — per-server isolation.

    Only the call skeleton is copied; helper implementations are referenced
    from the upstream module at call time (never duplicated here), so the
    version sentinel only needs to cover the skeleton's own surface.

    Failure semantics (vs upstream): a failing server is logged per-server
    (ERROR detail + url/cmd) and skipped; the remaining servers still load.
    ``_last_load_failed`` is set whenever at least one server failed — the
    cache-defense wrapper in ``_patched_initialize`` uses it to reset the
    ``cache._cache_initialized`` flag when EVERY server failed (empty result),
    so a transient total failure is retried instead of cached forever.
    """
    global _last_load_failed
    import deerflow.mcp.tools as _mcp_tools  # 运行时解析模块属性：boot 替换/测试 patch 均生效

    mcp_logger = logging.getLogger("deerflow.mcp.tools")  # 复用上游 logger，行前缀一致

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        mcp_logger.warning(
            "langchain-mcp-adapters not installed. Install it to enable MCP tools: pip install langchain-mcp-adapters"
        )
        _last_load_failed = False  # 缺库不是 per-server 失败，不触发缓存防线
        return []

    # 与上游一致：始终从磁盘读取最新配置（Gateway API 跨进程修改立即可见）
    extensions_config = _mcp_tools.ExtensionsConfig.from_file()
    servers_config = _mcp_tools.build_servers_config(extensions_config)

    if not servers_config:
        mcp_logger.info("No enabled MCP servers configured")
        _last_load_failed = False
        return []

    try:
        mcp_logger.info(f"Initializing MCP client with {len(servers_config)} server(s)")

        # OAuth 头注入（仅 sse/http，client 构造前执行，与循环无冲突）
        initial_oauth_headers = await _mcp_tools.get_initial_oauth_headers(extensions_config)
        for server_name, auth_header in initial_oauth_headers.items():
            if server_name not in servers_config:
                continue
            if servers_config[server_name].get("transport") in ("sse", "http"):
                existing_headers = dict(servers_config[server_name].get("headers", {}))
                existing_headers["Authorization"] = auth_header
                servers_config[server_name]["headers"] = existing_headers

        tool_interceptors: list[Any] = []
        oauth_interceptor = _mcp_tools.build_oauth_tool_interceptor(extensions_config)
        if oauth_interceptor is not None:
            tool_interceptors.append(oauth_interceptor)

        # 自定义拦截器（extensions_config.json 的 mcpInterceptors）
        raw_interceptor_paths = (extensions_config.model_extra or {}).get("mcpInterceptors")
        if isinstance(raw_interceptor_paths, str):
            raw_interceptor_paths = [raw_interceptor_paths]
        elif not isinstance(raw_interceptor_paths, list):
            if raw_interceptor_paths is not None:
                mcp_logger.warning(
                    f"mcpInterceptors must be a list of strings, got {type(raw_interceptor_paths).__name__}; skipping"
                )
            raw_interceptor_paths = []
        for interceptor_path in raw_interceptor_paths:
            try:
                builder = _mcp_tools.resolve_variable(interceptor_path)
                interceptor = builder()
                if callable(interceptor):
                    tool_interceptors.append(interceptor)
                    mcp_logger.info(f"Loaded MCP interceptor: {interceptor_path}")
                elif interceptor is not None:
                    mcp_logger.warning(
                        f"Builder {interceptor_path} returned non-callable {type(interceptor).__name__}; skipping"
                    )
            except Exception as e:
                mcp_logger.warning(
                    f"Failed to load MCP interceptor {interceptor_path}: {e}",
                    exc_info=True,
                )

        client = MultiServerMCPClient(
            servers_config,
            tool_interceptors=tool_interceptors,
            tool_name_prefix=True,
        )

        # ── 改造点：全量加载 → per-server 并发加载 + 异常隔离 ──
        async def _load_one(server_name: str) -> tuple[str, list[BaseTool] | None]:
            timeout = _timeout_from_env()  # 每次调用解析：测试可 patch，env 热改生效
            cfg = servers_config[server_name]
            url = cfg.get("url", "-")
            cmd = cfg.get("command", "-")
            try:
                server_tools = await asyncio.wait_for(
                    client.get_tools(server_name=server_name), timeout=timeout
                )
                mcp_logger.info(
                    "[MCPResilience] %s loaded %d tool(s) (%s)",
                    server_name, len(server_tools), cfg.get("transport", "?"),
                )
                return server_name, server_tools
            except asyncio.TimeoutError:
                # 超时计入失败（wait_for 抛 TimeoutError）
                mcp_logger.error(
                    "[MCPResilience] %s failed: TimeoutError(after %ss) [url=%s cmd=%s]",
                    server_name, timeout, url, cmd,
                )
                return server_name, None
            except Exception as e:
                # CancelledError 是 BaseException 不被吞，外层取消正确传播
                mcp_logger.error(
                    "[MCPResilience] %s failed: %s (%s) [url=%s cmd=%s]",
                    server_name, type(e).__name__, e, url, cmd,
                )
                return server_name, None

        # gather 保序：结果顺序与 servers_config 顺序一致（与上游工具顺序契约相同）
        results = await asyncio.gather(*(_load_one(name) for name in servers_config))
        tools: list[BaseTool] = [t for _, ts in results for t in (ts or [])]
        failed_count = sum(1 for _, ts in results if ts is None)
        _last_load_failed = failed_count > 0
        if failed_count:
            mcp_logger.warning(
                "[MCPResilience] %d/%d server(s) failed to load", failed_count, len(servers_config)
            )
        if tools:
            # 全失败不打印成功行（消除"0 tools loaded"误导行）
            mcp_logger.info(f"[MCPResilience] Successfully loaded {len(tools)} tool(s) from MCP servers")

        # ── 以下与上游一致（引用上游实现，不复制）──
        # stdio 工具 session pool 包装；HTTP/SSE 裸返回（TaskGroup 清理限制，见 #3203）
        wrapped_tools: list[BaseTool] = []
        for tool in tools:
            tool_server: str | None = None
            for name in servers_config:
                if tool.name.startswith(f"{name}_"):
                    tool_server = name
                    break
            if tool_server is not None:
                transport = servers_config[tool_server].get("transport", "stdio")
                if transport == "stdio":
                    wrapped_tools.append(
                        _mcp_tools._make_session_pool_tool(
                            tool, tool_server, servers_config[tool_server], tool_interceptors
                        )
                    )
                else:
                    wrapped_tools.append(tool)
            else:
                wrapped_tools.append(tool)

        # sync 调用包装（deerflow client 同步流式调用）
        for tool in wrapped_tools:
            if getattr(tool, "func", None) is None and getattr(tool, "coroutine", None) is not None:
                tool.func = _mcp_tools.make_sync_tool_wrapper(tool.coroutine, tool.name)

        return wrapped_tools

    except Exception as e:
        # 整体异常（client 构造/OAuth/拦截器加载等）保持上游语义
        _last_load_failed = True
        mcp_logger.error(f"Failed to load MCP tools: {e}", exc_info=True)
        return []


# ---- 生命周期 ----


def ensure_applied() -> None:
    """Idempotent: apply when not yet applied (LangGraph dev/Studio path)."""
    if not _APPLIED:
        apply_all()


async def _patched_initialize(*args: Any, **kwargs: Any) -> Any:
    """cache.initialize_mcp_tools 包装：先 ensure_applied 再执行原版。

    全失败结果（空 + _last_load_failed）→ 复位 cache._cache_initialized
    （L3 修复点 cache.py:75 无条件缓存）允许下次重试。unpatch 后误调
    （_original 为 None）→ 直接返回 None，不执行原版。
    """
    if _original_initialize_mcp_tools is None:
        return None  # 未 apply（unpatch 后误调）→ 不执行
    ensure_applied()
    result = await _original_initialize_mcp_tools(*args, **kwargs)
    if not result and _last_load_failed:
        import deerflow.mcp.cache as _cache_mod

        if getattr(_cache_mod, "_cache_initialized", False):
            _cache_mod._cache_initialized = False
            _cache_mod._config_mtime = None  # 同步清 mtime（cache.py mtime 语义避免误读）
            logger.warning("[MCPResilience] all MCP servers failed; cache flag reset for retry")
    return result


def _patch_lazy_install() -> None:
    """包装 cache.initialize_mcp_tools 为"先 ensure_applied 再原版"（幂等）。

    覆盖 LangGraph dev/Studio 等独立进程（不经过 gateway boot）；gateway 路径
    ensure_applied 是 no-op。包装用 *args/**kwargs 透传，只调 orig，无递归。
    同时替换包级 re-export（deerflow/mcp/__init__.py:5 绑定副本，若存在）。
    """
    global _original_initialize_mcp_tools, _original_pkg_initialize_mcp_tools
    import deerflow.mcp as _mcp_pkg
    import deerflow.mcp.cache as _cache

    if _original_initialize_mcp_tools is None:
        _original_initialize_mcp_tools = _cache.initialize_mcp_tools
    _cache.initialize_mcp_tools = _patched_initialize

    if getattr(_mcp_pkg, "initialize_mcp_tools", None) is not None:
        if _original_pkg_initialize_mcp_tools is None:
            _original_pkg_initialize_mcp_tools = _mcp_pkg.initialize_mcp_tools
        _mcp_pkg.initialize_mcp_tools = _patched_initialize


def apply_all() -> None:
    """Apply the patch after re-verifying the version sentinel. Idempotent."""
    global _APPLIED, _original_get_mcp_tools, _original_pkg_get_mcp_tools

    if _APPLIED:
        return
    with _apply_lock:
        if _APPLIED:
            return  # 双重检查：并发 boot 线程只允许一个真正执行 apply

        reason = _verify_patch_target()
        if reason is not None:
            logger.warning("[MCPResilience] patch skipped: %s", reason)
            return

        import deerflow.mcp as _mcp_pkg
        import deerflow.mcp.tools as _mcp_tools

        # 仅当原始引用未保存时保存（防 apply→unpatch→apply 回环保存到补丁版）
        if _original_get_mcp_tools is None:
            _original_get_mcp_tools = _mcp_tools.get_mcp_tools
            _original_pkg_get_mcp_tools = _mcp_pkg.get_mcp_tools

        _mcp_tools.get_mcp_tools = _patched_get_mcp_tools
        # 包级 re-export（deerflow/mcp/__init__.py:9 `from .tools import ...` 绑定副本）一并替换
        _mcp_pkg.get_mcp_tools = _patched_get_mcp_tools

        _patch_lazy_install()

        _APPLIED = True
        logger.info("[MCPResilience] patch applied (sentinel OK)")
