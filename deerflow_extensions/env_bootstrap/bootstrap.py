"""
env_bootstrap — 启动时自动探测并注入环境变量。

注入策略:
  - DEER_FLOW_PROJECT_ROOT: 复用 boot._resolve_project_root()
  - ADS_MCP_CONFIG_PATH: os.path.expanduser("~/.config/deer-flow/ads-mcp.json")

幂等: os.environ.setdefault() + dotenv.dotenv_values() 检查。
回滚安全: 所有 I/O 错误静默吞掉，不抛异常。
"""

import logging
import os
from typing import Callable

from dotenv import dotenv_values, find_dotenv, set_key
from filelock import FileLock

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置驱动的变量注册表 — 添加新变量只需追加一行元组
# ---------------------------------------------------------------------------
_BOOTSTRAP_VARS: list[tuple[str, Callable[[], str | None], str]] = []


def _resolve_project_root() -> str | None:
    """探测项目根路径，复用 boot.py 的 _resolve_project_root() 逻辑。

    函数作用域内导入，避免循环导入（boot.py → startup.py → bootstrap.py → boot.py）。
    由于 _boot_one() 调用 install_env_bootstrap() → bootstrap_all() 时
    boot.py 模块已完全加载，此 import 是安全的。
    """
    try:
        from deerflow_extensions.boot import _resolve_project_root as _boot_resolve

        return _boot_resolve()
    except Exception:
        _logger.debug("Cannot import _resolve_project_root from boot, skip")
        return None


def _resolve_ads_config() -> str | None:
    """展开 ADS_MCP_CONFIG_PATH 的 ~ 为真实 HOME 路径。"""
    try:
        return os.path.abspath(os.path.expanduser("~/.config/deer-flow/ads-mcp.json"))
    except Exception:
        _logger.debug("Cannot expand ~ for ADS_MCP_CONFIG_PATH, skip")
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
    """向 .env 文件和 os.environ 写入环境变量（幂等，并发安全）。

    1. 如果 .env 文件中已有此 key → 仅同步 os.environ，不覆盖文件
    2. 获取 FileLock(.env.lock, timeout=5) 互斥锁
    3. set_key 写入 .env 文件
    4. os.environ.setdefault 让当前进程立即可用
    5. 所有异常静默捕获，不阻塞启动
    """
    # .env 中已有此 key 则只同步 os.environ，不覆盖
    try:
        existing = dotenv_values(env_path)
        if key in existing:
            os.environ.setdefault(key, existing[key])
            _logger.debug("%s already in .env, synced to os.environ", key)
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

    # 总是设置 os.environ（让当前进程立即可用）
    os.environ.setdefault(key, value)
    _logger.info("[EnvBootstrap] %s=%s", key, value)


def bootstrap_all() -> dict[str, str | None]:
    """执行所有自举变量的探测和写入。

    Returns:
        dict: {"DEER_FLOW_PROJECT_ROOT": "/path" | None, "ADS_MCP_CONFIG_PATH": "/path" | None}
    """
    result: dict[str, str | None] = {}

    # 定位 .env 文件
    try:
        env_path = find_dotenv()
    except Exception:
        env_path = ""

    for key, _desc in _BOOTSTRAP_VARS:
        # ① os.environ 已有 → 跳过（用户显式设的值，永不覆盖）
        if key in os.environ:
            _logger.debug("%s already in os.environ, skip", key)
            result[key] = os.environ[key]
            continue

        # ② .env 文件已有 → 同步 os.environ，不覆盖文件中的值
        if env_path:
            try:
                existing = dotenv_values(env_path)
                if key in existing:
                    os.environ.setdefault(key, existing[key])
                    _logger.debug("%s already in .env, synced to os.environ", key)
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

        # ④ 幂等写入 .env + os.environ
        if env_path:
            _write_env(env_path, key, value)
        else:
            # 无法定位 .env → 仅设 os.environ
            os.environ.setdefault(key, value)
            _logger.info("[EnvBootstrap] %s=%s (os.environ only, .env not found)", key, value)

        result[key] = value

    return result
