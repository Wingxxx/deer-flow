"""单元测试：mcp_instructions 扩展（fetcher 握手 + startup 注入）。

纯 pytest + asyncio.run 包装，不引入 pytest-asyncio。所有外部依赖
（create_session / 配置 / OAuth）均 mock，不 spawn 真实 MCP 进程。
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import types
from unittest import mock

import pytest

from deerflow_extensions.mcp_instructions import fetcher, startup
from deerflow_extensions.mcp_instructions.fetcher import fetch_all_instructions


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeResult:
    def __init__(self, instructions=None):
        self.instructions = instructions


class FakeSession:
    """假 MCP session：initialize 可控（正常 / 挂起 / 抛错）。"""

    def __init__(self, result=None, initialize_error=None, hang=False):
        self._result = result
        self._error = initialize_error
        self._hang = hang
        self.initialize_calls = 0

    async def initialize(self):
        self.initialize_calls += 1
        if self._hang:
            await asyncio.sleep(3600)
        if self._error:
            raise self._error
        return self._result


class FakeCM:
    """假 create_session 返回值：跟踪 __aexit__ 是否执行（孤儿进程防护）。"""

    def __init__(self, session=None, enter_error=None):
        self.session = session or FakeSession()
        self.enter_error = enter_error
        self.exited = 0

    async def __aenter__(self):
        if self.enter_error:
            raise self.enter_error
        return self.session

    async def __aexit__(self, *args):
        self.exited += 1
        return False


def _patch_fetcher_env(monkeypatch, servers, cms, oauth_error=False, oauth_headers=None):
    """统一 patch fetcher 的外部依赖，返回 {name: FakeCM} 映射。"""
    from deerflow.config.extensions_config import ExtensionsConfig
    from deerflow.mcp import client as mcp_client
    from deerflow.mcp import oauth as mcp_oauth
    import langchain_mcp_adapters.sessions as lc_sessions

    monkeypatch.setattr(ExtensionsConfig, "from_file", staticmethod(lambda: object()))
    monkeypatch.setattr(mcp_client, "build_servers_config", lambda cfg: servers)

    async def fake_oauth(cfg):
        if oauth_error:
            raise RuntimeError("oauth down")
        return oauth_headers or {}

    monkeypatch.setattr(mcp_oauth, "get_initial_oauth_headers", fake_oauth)
    cm_map = {}

    def fake_create_session(conn):
        name = conn.get("_test_name")
        cm = cms[name]
        cm_map[name] = cm
        return cm

    monkeypatch.setattr(lc_sessions, "create_session", fake_create_session)
    return cm_map


@pytest.fixture(autouse=True)
def _clean_startup_state():
    """每个测试前保存/恢复 startup 模块全局状态，避免测试间污染。"""
    saved = {
        "_registry": dict(startup._registry),
        "_registry_mtime": startup._registry_mtime,
        "_last_attempt": startup._last_attempt,
        "_fetch_in_progress": startup._fetch_in_progress,
        "_installed": startup._installed,
    }
    startup._registry.clear()
    startup._registry_mtime = None
    startup._last_attempt = 0.0
    startup._fetch_in_progress = False
    startup._installed = False
    yield
    startup._registry.clear()
    startup._registry.update(saved["_registry"])
    startup._registry_mtime = saved["_registry_mtime"]
    startup._last_attempt = saved["_last_attempt"]
    startup._fetch_in_progress = saved["_fetch_in_progress"]
    startup._installed = saved["_installed"]


# ---------------------------------------------------------------------------
# fetcher：获取容错 / str 白名单 / 超时清理
# ---------------------------------------------------------------------------

class TestFetcher:
    def test_partial_failure_keeps_others(self, monkeypatch):
        """部分 server 失败 → 其余保留、整体不炸。"""
        servers = {
            "ok": {"_test_name": "ok", "transport": "stdio"},
            "bad": {"_test_name": "bad", "transport": "stdio"},
        }
        cms = {
            "ok": FakeCM(session=FakeSession(result=FakeResult(instructions="规则A"))),
            "bad": FakeCM(enter_error=RuntimeError("spawn failed")),
        }
        _patch_fetcher_env(monkeypatch, servers, cms)

        result = asyncio.run(fetch_all_instructions())
        assert result == {"ok": "规则A"}
        assert cms["ok"].exited == 1  # 成功 server 也完成清理

    def test_instructions_none_or_non_str_skipped(self, monkeypatch):
        """instructions=None / 非 str → 跳过。"""
        servers = {
            "none": {"_test_name": "none", "transport": "stdio"},
            "int": {"_test_name": "int", "transport": "stdio"},
        }
        cms = {
            "none": FakeCM(session=FakeSession(result=FakeResult(instructions=None))),
            "int": FakeCM(session=FakeSession(result=FakeResult(instructions=123))),
        }
        _patch_fetcher_env(monkeypatch, servers, cms)

        assert asyncio.run(fetch_all_instructions()) == {}
        assert cms["none"].exited == 1 and cms["int"].exited == 1

    def test_oauth_failure_degrades_to_no_headers(self, monkeypatch):
        """OAuth 刷新失败 → 降级为无头请求，不阻断抓取。"""
        servers = {"s1": {"_test_name": "s1", "transport": "stdio"}}
        cms = {"s1": FakeCM(session=FakeSession(result=FakeResult(instructions="X")))}
        _patch_fetcher_env(monkeypatch, servers, cms, oauth_error=True)

        assert asyncio.run(fetch_all_instructions()) == {"s1": "X"}

    def test_handshake_timeout_still_cleans_up(self, monkeypatch):
        """initialize 挂起 → wait_for 超时后 __aexit__ 仍执行（无孤儿进程）。"""
        servers = {"slow": {"_test_name": "slow", "transport": "stdio"}}
        cm = FakeCM(session=FakeSession(result=FakeResult(instructions="X"), hang=True))
        _patch_fetcher_env(monkeypatch, servers, {"slow": cm})
        monkeypatch.setattr("deerflow_extensions.mcp_instructions.fetcher._HANDSHAKE_TIMEOUT", 0.05)

        result = asyncio.run(fetch_all_instructions())
        assert result == {}
        assert cm.exited == 1  # 超时后清理仍执行

    def test_concurrent_fetch_wall_time_bounded(self, monkeypatch):
        """并发握手：慢 server 不拖累整体返回（gather 并行）。"""
        servers = {f"s{i}": {"_test_name": f"s{i}", "transport": "stdio"} for i in range(3)}
        cms = {}
        for i, name in enumerate(servers):
            hang = i == 2  # 最后一个 server 挂起 0.2s
            session = FakeSession(result=FakeResult(instructions=f"规则{i}"), hang=hang)

            async def initialize(self=session):
                if self._hang:
                    await asyncio.sleep(0.2)
                self.initialize_calls += 1
                return self._result

            session.initialize = initialize
            cms[name] = FakeCM(session=session)
        _patch_fetcher_env(monkeypatch, servers, cms)
        monkeypatch.setattr("deerflow_extensions.mcp_instructions.fetcher._HANDSHAKE_TIMEOUT", 10)

        start = time.monotonic()
        result = asyncio.run(fetch_all_instructions())
        elapsed = time.monotonic() - start
        # 串行会是 0.6s+，并发应显著更短
        assert elapsed < 0.45
        assert len(result) == 3

    def test_concurrent_fetch_respects_max_concurrency(self, monkeypatch):
        """并发握手受 Semaphore 上限约束：active 峰值 ≤ _MAX_CONCURRENCY
        （防 stdio 服务器无上限 spawn 子进程风暴）。"""
        servers = {f"s{i}": {"_test_name": f"s{i}", "transport": "stdio"} for i in range(20)}
        cms = {}
        gauge = {"active": 0, "peak": 0}

        class GaugeSession(FakeSession):
            async def initialize(self):
                gauge["active"] += 1
                gauge["peak"] = max(gauge["peak"], gauge["active"])
                try:
                    await asyncio.sleep(0.05)
                    return self._result
                finally:
                    gauge["active"] -= 1

        for name in servers:
            cms[name] = FakeCM(session=GaugeSession(result=FakeResult(instructions="x")))
        _patch_fetcher_env(monkeypatch, servers, cms)

        result = asyncio.run(fetch_all_instructions())
        assert len(result) == 20
        assert gauge["peak"] <= fetcher._MAX_CONCURRENCY

    def test_fetch_truncates_huge_instructions(self, monkeypatch):
        """超大 instructions（1MB）→ 抓取侧即截断到 _PER_SERVER_LIMIT，
        registry 不全文驻留（内存防护，渲染预算只是第二道闸）。"""
        servers = {"big": {"_test_name": "big", "transport": "stdio"}}
        huge = "长" * (1024 * 1024)
        cms = {"big": FakeCM(session=FakeSession(result=FakeResult(instructions=huge)))}
        _patch_fetcher_env(monkeypatch, servers, cms)

        result = asyncio.run(fetch_all_instructions())
        assert len(result["big"]) == fetcher._PER_SERVER_LIMIT


# ---------------------------------------------------------------------------
# startup：渲染 / wrapper / 非阻塞 / 风暴 / 幂等 / 版本检测
# ---------------------------------------------------------------------------

class TestStartup:
    def test_render_empty(self):
        assert startup._render_section({}) == ""

    def test_render_sorted_and_budgeted(self, monkeypatch):
        """多 server 确定性排序 + 预算（含 header 开销）控制。"""
        monkeypatch.setattr(startup, "_TOTAL_BUDGET", 200)
        monkeypatch.setattr(startup, "_PER_SERVER_LIMIT", 1000)
        section = startup._render_section({"b": "B" * 50, "a": "A" * 50})
        assert section.startswith("<mcp-instructions>")
        assert section.index("### MCP 服务器指令 - a") < section.index("### MCP 服务器指令 - b")
        # 预算约束：内容总量不超 budget + 包装开销
        assert len(section) <= 200 + len("<mcp-instructions>\n\n</mcp-instructions>")

    def test_render_per_server_truncation(self, monkeypatch):
        monkeypatch.setattr(startup, "_PER_SERVER_LIMIT", 5)
        monkeypatch.setattr(startup, "_TOTAL_BUDGET", 1000)
        section = startup._render_section({"s": "1234567890"})
        assert "12345" in section and "67890" not in section

    def test_render_budget_exhausted_no_empty_header(self, monkeypatch):
        """预算不足以容纳 header → 不再追加空块（负预算守卫）。"""
        monkeypatch.setattr(startup, "_TOTAL_BUDGET", 5)
        monkeypatch.setattr(startup, "_PER_SERVER_LIMIT", 1000)
        section = startup._render_section({"s": "x" * 10})
        assert section == ""  # header 都放不下 → 整体为空

    def test_wrapper_appends_block(self, monkeypatch):
        """registry 有数据 → 原 section 保留 + 追加 <mcp-instructions> 块。"""
        monkeypatch.setattr(startup, "_maybe_spawn_refresh", lambda: None)
        startup._registry.update({"mcp-agent-mcp": "实体规则"})

        def original(*, deferred_names=frozenset()):
            return "<available-deferred-tools>\nfoo\n</available-deferred-tools>"

        wrapper = startup._wrap_deferred_section(original)
        out = wrapper(deferred_names=frozenset())
        assert "<available-deferred-tools>" in out
        assert "<mcp-instructions>" in out
        assert "实体规则" in out

    def test_wrapper_empty_registry_passthrough(self, monkeypatch):
        """registry 空 → 原样返回，不阻塞、不抛错。"""
        monkeypatch.setattr(startup, "_maybe_spawn_refresh", lambda: None)
        startup._registry.clear()

        def original(*, deferred_names=frozenset()):
            return "<available-deferred-tools>"

        wrapper = startup._wrap_deferred_section(original)
        assert wrapper() == "<available-deferred-tools>"

    def test_empty_registry_spawns_background(self, monkeypatch):
        """空 registry：_maybe_spawn_refresh 立即返回（不阻塞），后台线程填充。"""
        calls = []
        monkeypatch.setattr(startup, "_sync_refresh", lambda: calls.append(time.monotonic()))
        startup._registry.clear()

        start = time.monotonic()
        startup._maybe_spawn_refresh()
        assert time.monotonic() - start < 0.1  # 非阻塞
        time.sleep(0.1)
        assert len(calls) == 1

    def test_no_refresh_storm_on_failure(self, monkeypatch):
        """失败也推进 cooldown → 连续调用只 spawn ≤1 个线程。"""
        calls = []
        monkeypatch.setattr(startup, "_sync_refresh", lambda: calls.append(1))
        monkeypatch.setattr(startup, "_REFRESH_COOLDOWN", 300.0)
        startup._registry.clear()

        for _ in range(3):
            startup._maybe_spawn_refresh()
        time.sleep(0.15)
        assert len(calls) <= 1

    def test_mtime_change_triggers_background_refresh(self, monkeypatch, tmp_path):
        """config mtime 变化 → 后台刷新（mock 临时文件，不触碰真实配置）。"""
        from deerflow.config.extensions_config import ExtensionsConfig

        cfg = tmp_path / "extensions_config.json"
        cfg.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(ExtensionsConfig, "resolve_config_path", staticmethod(lambda: cfg))
        calls = []
        monkeypatch.setattr(startup, "_sync_refresh", lambda: calls.append(1))
        startup._registry.update({"s1": "x"})  # 已有数据
        startup._registry_mtime = None          # mtime 与 config 不同 → 触发

        startup._maybe_spawn_refresh()
        time.sleep(0.1)
        assert len(calls) == 1

    # ---- install 幂等 / reload / 版本检测（假模块树，不触发重型导入） ----

    def _install_env(self, monkeypatch, version="0.2.2", enabled=True):
        """构造假 deerflow 模块树，patch install 的外部依赖。"""
        pkg = types.ModuleType("deerflow.agents.lead_agent")
        prompt_mod = types.ModuleType("deerflow.agents.lead_agent.prompt")
        pkg.prompt = prompt_mod
        monkeypatch.setitem(sys.modules, "deerflow.agents.lead_agent", pkg)
        monkeypatch.setitem(sys.modules, "deerflow.agents.lead_agent.prompt", prompt_mod)

        tools_pkg = types.ModuleType("deerflow.tools.builtins")
        ts_mod = types.ModuleType("deerflow.tools.builtins.tool_search")
        tools_pkg.tool_search = ts_mod
        monkeypatch.setitem(sys.modules, "deerflow.tools.builtins", tools_pkg)
        monkeypatch.setitem(sys.modules, "deerflow.tools.builtins.tool_search", ts_mod)

        def orig(*, deferred_names=frozenset()):
            return "<available-deferred-tools>"

        prompt_mod.get_deferred_tools_prompt_section = orig
        ts_mod.get_deferred_tools_prompt_section = orig

        monkeypatch.setattr("importlib.metadata.version", lambda name: version)
        monkeypatch.setattr(startup, "_ENABLED", enabled)
        monkeypatch.setattr(startup, "_maybe_spawn_refresh", lambda: None)
        return prompt_mod, ts_mod

    def test_install_patches_both_targets(self, monkeypatch):
        prompt_mod, ts_mod = self._install_env(monkeypatch)
        startup.install_mcp_instructions()

        assert getattr(prompt_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)
        assert getattr(ts_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)

    def test_install_idempotent(self, monkeypatch):
        prompt_mod, ts_mod = self._install_env(monkeypatch)
        startup.install_mcp_instructions()
        first_prompt = prompt_mod.get_deferred_tools_prompt_section
        startup.install_mcp_instructions()  # _installed 守卫 → 直接返回
        assert prompt_mod.get_deferred_tools_prompt_section is first_prompt

    def test_install_no_wrapper_stacking_on_reload(self, monkeypatch):
        """模拟 reload：_installed 复位后再次 install → 不叠层（marker 检测）。"""
        prompt_mod, ts_mod = self._install_env(monkeypatch)
        startup.install_mcp_instructions()
        first_prompt = prompt_mod.get_deferred_tools_prompt_section

        startup._installed = False  # 模拟 importlib.reload 重置
        startup.install_mcp_instructions()
        assert prompt_mod.get_deferred_tools_prompt_section is first_prompt  # 同一 wrapper

    def test_install_disabled_on_upstream_0_3(self, monkeypatch):
        """langchain-mcp-adapters ≥0.3 → 停用（原生注入工具描述，防双重注入）。"""
        prompt_mod, ts_mod = self._install_env(monkeypatch, version="0.3.2")
        startup.install_mcp_instructions()

        assert not hasattr(prompt_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)
        assert not hasattr(ts_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)

    def test_install_disabled_by_env(self, monkeypatch):
        prompt_mod, ts_mod = self._install_env(monkeypatch, enabled=False)
        startup.install_mcp_instructions()

        assert not hasattr(prompt_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)
        assert not hasattr(ts_mod.get_deferred_tools_prompt_section, startup._WRAPPER_MARK)
