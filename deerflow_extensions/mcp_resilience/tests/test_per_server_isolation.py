"""Unit tests for the per-server MCP isolation patch.

Mock strategy: ``_patched_get_mcp_tools`` resolves upstream symbols via
``deerflow.mcp.tools`` module attributes at call time, so functional tests
(1-7) patch those module attributes directly. Sentinel tests (8-14)
exercise the real ``apply_all`` / ``unpatch_all`` decisions; an autouse
fixture unpatchs after every test so other tests in this process are
unaffected.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from deerflow_extensions.mcp_resilience import patch_manager as pm

# pytest-asyncio 1.3.0 strict：8 条 async 用例各自显式 @pytest.mark.asyncio（模块级标记会给 13 条 sync 用例施加 PytestWarning 噪音）


# ---- helpers ----


def _mock_tool(name: str, with_coroutine: bool = True) -> BaseTool:
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    tool.description = "mock tool"
    tool.args_schema = None
    tool.func = None
    tool.coroutine = AsyncMock(return_value="ok") if with_coroutine else None
    tool.metadata = {}
    return tool


def _make_fake_get_tools(servers: dict, fail_names: frozenset[str] = frozenset()):
    """Return an async get_tools(*, server_name) dispatcher for the mock client.

    stdio servers get tools with a coroutine (so the sync-wrapper loop sees
    them); http/sse servers get bare tools (no coroutine, never wrapped).
    """

    async def fake_get_tools(*, server_name: str | None = None):
        if server_name in fail_names:
            raise ConnectionRefusedError("connection refused")
        assert server_name in servers, f"unexpected server_name={server_name!r}"
        with_coro = servers[server_name].get("transport", "stdio") == "stdio"
        return [_mock_tool(f"{server_name}_tool_{i}", with_coroutine=with_coro) for i in range(2)]

    return fake_get_tools


@contextmanager
def _patched_env(servers: dict, fail_names: frozenset[str] = frozenset()):
    """Context manager patching the upstream module surface used by the patched fn.

    Yields ``(client_cls, wrap)`` — the mocked MultiServerMCPClient class and
    the ``_make_session_pool_tool`` spy (records stdio wrapping calls).
    """
    cfg = MagicMock()
    cfg.model_extra = {}

    with ExitStack() as stack:
        ext_cls = stack.enter_context(patch("deerflow.mcp.tools.ExtensionsConfig"))
        stack.enter_context(
            patch("deerflow.mcp.tools.build_servers_config", return_value=servers)
        )
        stack.enter_context(
            patch(
                "deerflow.mcp.tools.get_initial_oauth_headers",
                new=AsyncMock(return_value={}),
            )
        )
        stack.enter_context(
            patch("deerflow.mcp.tools.build_oauth_tool_interceptor", return_value=None)
        )
        wrap = stack.enter_context(
            patch(
                "deerflow.mcp.tools._make_session_pool_tool",
                side_effect=lambda tool, server, conn, interceptors=None: tool,
            )
        )
        client_cls = stack.enter_context(
            patch("langchain_mcp_adapters.client.MultiServerMCPClient")
        )
        ext_cls.from_file.return_value = cfg
        client_cls.return_value.get_tools = _make_fake_get_tools(servers, fail_names)
        yield client_cls, wrap


@pytest.fixture(autouse=True)
def _unpatch_after_each():
    yield
    pm.unpatch_all()


# ---- 功能用例 1-7 ----


@pytest.mark.asyncio
async def test_one_good_one_bad(caplog):
    servers = {
        "good": {"transport": "stdio", "command": "node", "args": ["srv.js"]},
        "bad": {"transport": "http", "url": "http://127.0.0.1:1/mcp"},
    }
    with _patched_env(servers, fail_names={"bad"}) as (client_cls, wrap):
        tools = await pm._patched_get_mcp_tools()

    names = [t.name for t in tools]
    assert "good_tool_0" in names and "good_tool_1" in names
    assert not any(n.startswith("bad_") for n in names)
    # stdio 工具被 sync 循环包装（func 非 None）；bad 的失败计入明细
    assert all(getattr(t, "func", None) is not None for t in tools)
    assert pm._last_load_failed is True
    assert any("bad failed: ConnectionRefusedError" in r.message for r in caplog.records)
    assert any("[MCPResilience] 1/2 server(s) failed to load" in r.message for r in caplog.records)
    assert not any("Failed to load MCP tools" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_all_fail_returns_empty(caplog):
    servers = {
        "bad1": {"transport": "http", "url": "http://127.0.0.1:1/a"},
        "bad2": {"transport": "http", "url": "http://127.0.0.1:1/b"},
    }
    with _patched_env(servers, fail_names={"bad1", "bad2"}):
        tools = await pm._patched_get_mcp_tools()

    assert tools == []
    assert pm._last_load_failed is True
    assert any("[MCPResilience] 2/2 server(s) failed to load" in r.message for r in caplog.records)
    # 全失败不打印成功行（if tools 守卫，消除误导行）
    assert not any("Successfully loaded" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_config_early_exit(caplog):
    caplog.set_level(logging.INFO)  # caplog 默认只捕获 WARNING+，早退 INFO 行需显式提升
    with _patched_env({}) as (client_cls, wrap):
        tools = await pm._patched_get_mcp_tools()

    assert tools == []
    assert pm._last_load_failed is False
    client_cls.assert_not_called()  # 空配置早退，不创建 client
    assert any("No enabled MCP servers configured" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stdio_wrapped_http_bare():
    servers = {
        "good": {"transport": "stdio", "command": "node", "args": ["srv.js"]},
        "http_ok": {"transport": "http", "url": "http://127.0.0.1:9999/mcp"},
    }
    with _patched_env(servers) as (client_cls, wrap):
        tools = await pm._patched_get_mcp_tools()

    # _make_session_pool_tool 仅对 stdio 工具调用（good 2 个工具）
    assert wrap.call_count == 2
    assert {c.args[1] for c in wrap.call_args_list} == {"good"}
    # 两个 server 的工具都收集到
    names = [t.name for t in tools]
    assert any(n.startswith("good_") for n in names)
    assert any(n.startswith("http_ok_") for n in names)


@pytest.mark.asyncio
async def test_timeout_counts_as_failure(caplog):
    servers = {
        "fast": {"transport": "stdio", "command": "node", "args": ["a.js"]},
        "slow": {"transport": "http", "url": "http://127.0.0.1:1/slow"},
    }

    async def slow_get_tools(*, server_name: str | None = None):
        if server_name == "slow":
            await asyncio.sleep(30)
        return [_mock_tool(f"{server_name}_tool_0")]

    with _patched_env(servers) as (client_cls, wrap), patch.object(
        pm, "_timeout_from_env", return_value=0.05
    ):
        client_cls.return_value.get_tools = slow_get_tools
        tools = await pm._patched_get_mcp_tools()

    assert [t.name for t in tools] == ["fast_tool_0"]
    assert pm._last_load_failed is True
    assert any("[MCPResilience] slow failed: TimeoutError" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_cancellation_propagates():
    """CancelledError 是 BaseException 不被 _load_one 吞掉，正确传播。"""
    servers = {"s1": {"transport": "http", "url": "http://a/mcp"}}

    async def slow_get_tools(*, server_name: str | None = None):
        await asyncio.sleep(30)
        return [_mock_tool("x")]

    with _patched_env(servers) as (client_cls, wrap):
        client_cls.return_value.get_tools = slow_get_tools
        task = asyncio.create_task(pm._patched_get_mcp_tools())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_order_preserved():
    servers = {
        "alpha": {"transport": "http", "url": "http://a/mcp"},
        "beta": {"transport": "http", "url": "http://b/mcp"},
        "gamma": {"transport": "http", "url": "http://c/mcp"},
    }
    with _patched_env(servers):
        tools = await pm._patched_get_mcp_tools()

    # gather 保序：结果顺序与 servers_config 顺序一致（与上游工具顺序契约相同）
    assert [t.name for t in tools] == [
        "alpha_tool_0", "alpha_tool_1",
        "beta_tool_0", "beta_tool_1",
        "gamma_tool_0", "gamma_tool_1",
    ]


# ---- 哨兵用例 8-14（真实 apply_all/unpatch_all 决策） ----


def test_sentinel_bytecode_mismatch(caplog):
    import deerflow.mcp.tools as mcp_tools

    orig = mcp_tools.get_mcp_tools

    def fake_get_mcp_tools():
        return []

    with patch.object(mcp_tools, "get_mcp_tools", fake_get_mcp_tools):
        pm.apply_all()
        # 哨兵拦截：fake 必须留在原位（patch 上下文内断言，退出后会被还原）
        assert mcp_tools.get_mcp_tools is fake_get_mcp_tools

    assert mcp_tools.get_mcp_tools is orig  # patch 上下文退出，还原为原版
    assert pm._APPLIED is False
    assert any("bytecode" in r.message and "mismatch" in r.message for r in caplog.records)
    assert orig is not fake_get_mcp_tools  # 原版完好


def test_check_bytecode_unit():
    import deerflow.mcp.tools as mcp_tools

    assert pm._check_bytecode(mcp_tools.get_mcp_tools) is True  # 真实函数命中基线
    assert pm._check_bytecode(lambda: []) is False  # 无特征


def test_sentinel_helper_signature_changed(caplog):
    import deerflow.mcp.tools as mcp_tools

    orig = mcp_tools.get_mcp_tools
    with patch.object(mcp_tools, "_make_session_pool_tool", lambda tool: None):  # 1 参 < 4
        pm.apply_all()

    assert mcp_tools.get_mcp_tools is orig
    assert any("signature changed" in r.message for r in caplog.records)


def test_sentinel_missing_helper(caplog):
    import deerflow.mcp.tools as mcp_tools

    orig = mcp_tools.get_mcp_tools
    with patch.object(mcp_tools, "make_sync_tool_wrapper", None):
        pm.apply_all()

    assert mcp_tools.get_mcp_tools is orig
    assert any("missing" in r.message for r in caplog.records)


def test_frozen_bytecode_channel(caplog):
    """frozen 下 inspect.getsource 抛 OSError，字节码通道仍通过。"""
    import deerflow.mcp.tools as mcp_tools

    with patch.object(sys, "frozen", True, create=True), patch.object(
        pm.inspect, "getsource", side_effect=OSError("no source")
    ):
        pm.apply_all()

    assert mcp_tools.get_mcp_tools is pm._patched_get_mcp_tools


def test_getsource_oserror_degrades_to_pass(caplog):
    """非 frozen + getsource 抛 OSError → 降级通过（无 dev/frozen 两套行为差异）。"""
    import deerflow.mcp.tools as mcp_tools

    with patch.object(pm.inspect, "getsource", side_effect=OSError("no source")):
        pm.apply_all()

    assert mcp_tools.get_mcp_tools is pm._patched_get_mcp_tools


def test_library_signature_missing_keyword_only(caplog):
    """第三方 get_tools 失去 server_name keyword-only → 跳过 patch。"""
    import deerflow.mcp.tools as mcp_tools
    from langchain_mcp_adapters.client import MultiServerMCPClient

    orig = mcp_tools.get_mcp_tools

    def fake_get_tools(self, server_name=None):  # 普通位置参数
        return []

    with patch.object(MultiServerMCPClient, "get_tools", fake_get_tools):
        pm.apply_all()

    assert mcp_tools.get_mcp_tools is orig
    assert any("keyword-only" in r.message for r in caplog.records)


# ---- 生命周期用例 15-19 ----


def test_apply_twice_idempotent():
    import deerflow.mcp.tools as mcp_tools

    pm.apply_all()
    first = mcp_tools.get_mcp_tools
    pm.apply_all()

    assert mcp_tools.get_mcp_tools is first is pm._patched_get_mcp_tools


def test_patch_applies_all_four_attributes():
    import deerflow.mcp as mcp_pkg
    import deerflow.mcp.cache as cache
    import deerflow.mcp.tools as mcp_tools

    pm.apply_all()

    assert mcp_tools.get_mcp_tools is pm._patched_get_mcp_tools
    assert mcp_pkg.get_mcp_tools is pm._patched_get_mcp_tools  # __init__.py:9 绑定副本
    assert cache.initialize_mcp_tools is pm._patched_initialize  # 迟到安装兜底
    assert mcp_pkg.initialize_mcp_tools is pm._patched_initialize  # __init__.py:5 绑定副本


def test_unpatch_restores_all_four():
    import deerflow.mcp as mcp_pkg
    import deerflow.mcp.cache as cache
    import deerflow.mcp.tools as mcp_tools

    pm.apply_all()
    orig_tools = pm._original_get_mcp_tools
    orig_pkg = pm._original_pkg_get_mcp_tools
    orig_init = pm._original_initialize_mcp_tools
    orig_pkg_init = pm._original_pkg_initialize_mcp_tools
    assert mcp_tools.get_mcp_tools is pm._patched_get_mcp_tools

    pm.unpatch_all()

    assert mcp_tools.get_mcp_tools is orig_tools
    assert mcp_pkg.get_mcp_tools is orig_pkg
    assert cache.initialize_mcp_tools is orig_init
    assert mcp_pkg.initialize_mcp_tools is orig_pkg_init
    assert pm._APPLIED is False
    assert pm._original_get_mcp_tools is None
    assert pm._last_load_failed is False


def test_ensure_applied_idempotent():
    import deerflow.mcp.tools as mcp_tools

    pm.apply_all()
    first = mcp_tools.get_mcp_tools
    pm.ensure_applied()  # 已 apply → no-op

    assert mcp_tools.get_mcp_tools is first is pm._patched_get_mcp_tools


@pytest.mark.asyncio
async def test_patched_initialize_passes_through_and_resets_cache():
    """包装版透传原版结果；空结果 + 有失败 → 复位 cache._cache_initialized。"""
    # 时序关键：patch.object 必须在 apply_all 之前——apply_all 保存的 original 恰是已 patch 的 mock，_patched_initialize 透传调用它
    import deerflow.mcp.cache as cache

    try:
        # 1) 非空结果 → 透传，不复位
        mock_init = AsyncMock(return_value=["t1"])
        with patch.object(cache, "initialize_mcp_tools", mock_init):
            pm.apply_all()
            assert await pm._patched_initialize() == ["t1"]
            mock_init.assert_awaited_once()
            cache._cache_initialized = True
            pm._last_load_failed = True
            assert await pm._patched_initialize() == ["t1"]
            assert cache._cache_initialized is True  # 非空 → 不复位
        pm.unpatch_all()

        # 2) 空结果 + 有失败 → 复位缓存标志
        mock_init = AsyncMock(return_value=[])
        with patch.object(cache, "initialize_mcp_tools", mock_init):
            pm.apply_all()
            cache._cache_initialized = True
            pm._last_load_failed = True
            assert await pm._patched_initialize() == []
            assert cache._cache_initialized is False
            mock_init.assert_awaited_once()
        pm.unpatch_all()
    finally:
        cache._cache_initialized = False  # 防污染同进程其他用例


# ---- 配置用例 20-21（同步，无需 asyncio 标记） ----


def test_timeout_env_invalid_falls_back():
    with patch.dict(os.environ, {"MCP_RESILIENCE_PER_SERVER_TIMEOUT": "abc"}):
        assert pm._timeout_from_env() == 30.0


def test_timeout_env_nonpositive_falls_back():
    for bad in ("0", "-5"):
        with patch.dict(os.environ, {"MCP_RESILIENCE_PER_SERVER_TIMEOUT": bad}):
            assert pm._timeout_from_env() == 30.0
