"""
env_bootstrap — 启动时自动探测并写入 .env 文件。

写入策略:
  - 只写 .env 文件，不碰 os.environ（由 DeerFlow 的 load_dotenv() 加载到进程）
  - DEER_FLOW_PROJECT_ROOT: 不再写入 .env（内部缓存供 ADS_MCP_CONFIG_PATH 使用）
  - ADS_MCP_CONFIG_PATH: 幂等写入（.env 已有则不覆写）

回滚安全: 所有 I/O 错误静默吞掉，不抛异常。
"""

import json
import logging
import os
import shutil
import sys
import tempfile
from typing import Callable

from dotenv import dotenv_values, find_dotenv, set_key
from filelock import FileLock

_logger = logging.getLogger(__name__)

# 模块级缓存，用于在 bootstrap_all() 的 resolver 之间传递已解析值
# （绕过 os.environ，因为本模块不写入系统环境变量）
_bootstrap_cache: dict[str, str] = {}

# ---------------------------------------------------------------------------
# 配置驱动的变量注册表 — 添加新变量只需追加一行元组
# ---------------------------------------------------------------------------
_BOOTSTRAP_VARS: list[tuple[str, Callable[[], str | None], str]] = []


def _resolve_project_root() -> str | None:
    """探测项目根路径。

    先委托 boot._resolve_project_root()，再对 PyInstaller frozen 模式
    做一层修正：boot.py 返回的是 sys.executable 所在目录（如 backend-bin/），
    真正的项目根在上一级（含 config.yaml）。
    """
    try:
        from deerflow_extensions.boot import _resolve_project_root as _boot_resolve

        result = _boot_resolve()
    except Exception:
        _logger.debug("Cannot import _resolve_project_root from boot, skip")
        return None

    if result is None:
        return None

    # Frozen 模式路径修正：PyInstaller --onedir 会在 result 下产生 _internal/
    # 真正的项目根在上一级（含 config.yaml）。向上遍历查找，最多3级。
    if getattr(sys, "frozen", False) and os.path.isdir(os.path.join(result, "_internal")):
        current = os.path.dirname(result)  # 从父级开始
        for _ in range(3):
            if os.path.isfile(os.path.join(current, "config.yaml")):
                if current != result:
                    _logger.info(
                        "[EnvBootstrap] Frozen root corrected: %s -> %s", result, current,
                    )
                    return current
                break  # 当前目录就是项目根
            parent = os.path.dirname(current)
            if parent == current:  # 到达文件系统根
                break
            current = parent

    return result


def _resolve_ads_config() -> str | None:
    """基于 DEER_FLOW_PROJECT_ROOT 定位 ads-mcp 配置路径。

    ADS MCP 的 config.json 一定位于项目根的 ads-agent-mcp/.ads-mcp/ 下，
    `DEER_FLOW_PROJECT_ROOT` 已在 bootstrap_all() 中先于本 resolver 写入
    `_bootstrap_cache`（见 _BOOTSTRAP_VARS 顺序），不依赖 os.environ。

    Note:
        如果 config.json 文件不存在，仍返回路径并记录 WARNING 日志。
        这是因为 ads_auth 可能在启动后才创建该文件。
    """
    try:
        root = _bootstrap_cache.get("DEER_FLOW_PROJECT_ROOT")
        if not root:
            _logger.debug("DEER_FLOW_PROJECT_ROOT not cached, skip ADS_MCP_CONFIG_PATH")
            return None
        path = os.path.join(root, "ads-agent-mcp", ".ads-mcp", "config.json")
        # 非阻塞存在性校验（文件可能在后续阶段创建）
        if not os.path.isfile(path):
            _logger.warning(
                "[EnvBootstrap] ADS_MCP_CONFIG_PATH=%s but file does not exist. "
                "Ensure ads-agent-mcp is deployed at %s.",
                path, os.path.join(root, "ads-agent-mcp"),
            )
        return path
    except Exception:
        _logger.debug("Cannot resolve ADS_MCP_CONFIG_PATH, skip")
        return None


# 注册自举变量（模块加载时填充）
_BOOTSTRAP_VARS: list[tuple[str, str]] = [
    ("DEER_FLOW_PROJECT_ROOT", "Project root directory"),
    ("ADS_MCP_CONFIG_PATH",    "ADS MCP config file path"),
]

# resolver 名称映射 — 调用时通过 globals() 查找，确保 mock.patch 可拦截
_RESOLVER_NAMES: dict[str, str] = {
    "DEER_FLOW_PROJECT_ROOT": "_resolve_project_root",
    "ADS_MCP_CONFIG_PATH":    "_resolve_ads_config",
}


def _get_resolver(key: str) -> Callable[[], str | None] | None:
    """通过 globals() 动态查找 resolver，使 mock.patch 在调用时生效。"""
    name = _RESOLVER_NAMES.get(key)
    if name:
        return globals().get(name)  # type: ignore[return-value]
    return None


# ---------------------------------------------------------------------------
# 核心: 幂等写入
# ---------------------------------------------------------------------------


def _write_env(env_path: str, key: str, value: str) -> None:
    """向 .env 文件写入环境变量（幂等，并发安全）。

    1. 如果 .env 文件中已有此 key → 直接返回（不覆盖文件）
    2. 获取 FileLock(.env.lock, timeout=5) 互斥锁
    3. set_key 写入 .env 文件
    4. 所有异常静默捕获，不阻塞启动
    """
    # .env 中已有此 key 则跳过
    try:
        existing = dotenv_values(env_path)
        if key in existing:
            _logger.debug("%s already in .env, skip", key)
            return
    except Exception:
        pass  # 无法读取 .env 不是致命错误

    # 获取文件锁，防止多进程并发写
    lock_path = env_path + ".lock"
    try:
        lock = FileLock(lock_path, timeout=5)
        with lock:
            set_key(env_path, key, value, quote_mode="always")
    except Exception as e:
        _logger.warning("Failed to write %s to .env: %s", key, e)
        return

    _logger.info("[EnvBootstrap] %s=%s", key, value)


def bootstrap_all() -> dict[str, str | None]:
    """执行所有自举变量的探测和写入。

    只写 .env 文件，不碰 os.environ。

    Returns:
        dict: {"DEER_FLOW_PROJECT_ROOT": "/path" | None, "ADS_MCP_CONFIG_PATH": "/path" | None}
    """
    _bootstrap_cache.clear()
    result: dict[str, str | None] = {}

    # 定位 .env 文件
    try:
        env_path = find_dotenv()
    except Exception:
        env_path = ""

    for key, _desc in _BOOTSTRAP_VARS:
        # ① os.environ 已有 → 跳过（用户显式设的值，永不覆盖）
        #     DEER_FLOW_PROJECT_ROOT 例外：env_bootstrap 是唯一写入者，
        #     load_dotenv() 在 import 时已将 .env 加载到 os.environ，
        #     如果 step ① 跳过，陈旧值永不被修正。
        if key != "DEER_FLOW_PROJECT_ROOT" and key in os.environ:
            _logger.debug("%s already in os.environ, skip", key)
            result[key] = os.environ[key]
            continue

        # ② .env 文件已有 → 使用该值，不覆盖文件
        #     DEER_FLOW_PROJECT_ROOT 例外：env_bootstrap 是唯一写入者，
        #     始终由 resolver 决定，不依赖 .env 持久化值。
        if env_path and key != "DEER_FLOW_PROJECT_ROOT":
            try:
                existing = dotenv_values(env_path)
                if key in existing:
                    _logger.debug("%s already in .env, use existing", key)
                    result[key] = existing[key]
                    continue
            except Exception:
                pass

        # ③ 调用 resolver 探测值（从 globals() 查找，确保 mock.patch 可拦截）
        resolver = _get_resolver(key)
        if resolver is None:
            _logger.debug("%s has no resolver, skip", key)
            result[key] = None
            continue
        try:
            value = resolver()
        except Exception as e:
            _logger.debug("Resolver for %s failed: %s", key, e)
            value = None

        if value is None:
            _logger.debug("%s could not be resolved, skip", key)
            result[key] = None
            continue

        # ④ 写入 .env 文件
        #     DEER_FLOW_PROJECT_ROOT：不再写入 .env（奥卡姆剃刀剪枝）
        #     ADS_MCP_CONFIG_PATH：幂等写入（_write_env 检查 .env 已有值则不覆写）
        if env_path and key == "ADS_MCP_CONFIG_PATH" and value is not None:
            _write_env(env_path, key, value)

        _logger.info("[EnvBootstrap] %s=%s", key, value)

        # DEER_FLOW_PROJECT_ROOT 供后续 ADS_MCP_CONFIG_PATH 的 resolver 使用
        if key == "DEER_FLOW_PROJECT_ROOT":
            _bootstrap_cache["DEER_FLOW_PROJECT_ROOT"] = value

        result[key] = value

    return result


# ---------------------------------------------------------------------------
# extensions_config.json ADS MCP 路径绝对化
# ---------------------------------------------------------------------------


def _rewrite_extensions_config_ads_paths(project_root: str) -> bool:
    """将 extensions_config.json 中 ADS MCP 的路径改写为绝对路径。

    只改写 args[0] 和 env.ADS_CONFIG_PATH（Node.js 实际解析的路径），
    删除 cwd 字段（路径已绝对化后 cwd 无意义）。

    幂等: 已为绝对路径则跳过。
    并发安全: FileLock + 原子写入（temp file + rename）。
    可回滚: 写入前创建 .bak 备份。

    Args:
        project_root: 已解析的项目根路径（来自 _bootstrap_cache）。

    Returns:
        True 如果文件被改写，False 如果无需修改。
    """
    config_path = os.path.join(project_root, "extensions_config.json")
    if not os.path.isfile(config_path):
        _logger.debug(
            "[EnvBootstrap] extensions_config.json not found at %s, skip", config_path
        )
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        _logger.warning("[EnvBootstrap] Failed to read extensions_config.json: %s", e)
        return False

    ads = config.get("mcpServers", {}).get("ads")
    if not ads:
        _logger.debug("[EnvBootstrap] No 'ads' MCP server entry, skip")
        return False

    lock_path = config_path + ".lock"
    try:
        lock = FileLock(lock_path, timeout=5)
        with lock:
            # 锁内重读，获取最新版本
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            ads = config.setdefault("mcpServers", {}).setdefault("ads", {})

            changes: list[str] = []

            # ── 删除 cwd（路径绝对化后不再需要） ──
            if "cwd" in ads:
                old_cwd = ads.pop("cwd")
                changes.append(f"removed cwd={old_cwd!r}")

            # ── 改写 args[0] ──
            args = ads.get("args", [])
            if args and isinstance(args[0], str) and not os.path.isabs(args[0]):
                old = args[0]
                ads["args"][0] = os.path.normpath(os.path.join(project_root, old))
                changes.append(f"args[0]: {old!r} -> {ads['args'][0]}")

            # ── 改写 env.ADS_CONFIG_PATH ──
            env = ads.setdefault("env", {})
            acp = env.get("ADS_CONFIG_PATH", "")
            if acp and not os.path.isabs(acp):
                env["ADS_CONFIG_PATH"] = os.path.normpath(
                    os.path.join(project_root, acp)
                )
                changes.append(f"env.ADS_CONFIG_PATH: {acp!r} -> {env['ADS_CONFIG_PATH']}")

            if not changes:
                _logger.debug("[EnvBootstrap] All ADS MCP paths already absolute, skip")
                return False

            # 备份原始文件
            try:
                shutil.copy2(config_path, config_path + ".bak")
            except Exception as e:
                _logger.warning("[EnvBootstrap] Failed to create .bak backup: %s", e)

            # 原子写入: temp file + rename
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(config_path), suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(tmp_path, config_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            _logger.info(
                "[EnvBootstrap] Rewrote extensions_config.json ADS paths: %s",
                "; ".join(changes),
            )
            return True
    except Exception as e:
        _logger.warning(
            "[EnvBootstrap] Failed to rewrite extensions_config.json: %s", e
        )
        return False
