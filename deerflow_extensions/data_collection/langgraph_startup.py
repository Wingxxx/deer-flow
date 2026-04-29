"""LangGraph startup injection - auto-run by PYTHONSTARTUP.

当 Python 解释器启动时自动执行此脚本，
完成 DataCollectionMiddleware 的注入。
"""

import sys
import os

EXTENSION_PATH = "/app/deerflow_extensions"
if EXTENSION_PATH not in sys.path:
    sys.path.insert(0, EXTENSION_PATH)

DEERFLOW_PATH = "/app/backend/packages/harness"
if DEERFLOW_PATH not in sys.path:
    sys.path.insert(0, DEERFLOW_PATH)

try:
    from deerflow_extensions.data_collection.startup import install_data_collection

    install_data_collection()
    print("[DataCollection] LangGraph startup injection completed")
except ImportError as e:
    print(f"[DataCollection] Startup injection skipped: {e}")
except Exception as e:
    print(f"[DataCollection] Startup injection failed: {e}")
