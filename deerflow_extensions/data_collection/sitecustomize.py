"""sitecustomize.py - Python auto-loads this file when starting."""

import sys

EXTENSION_PATH = "/app/deerflow_extensions"
if EXTENSION_PATH not in sys.path:
    sys.path.insert(0, EXTENSION_PATH)

DEERFLOW_PATH = "/app/backend/packages/harness"
if DEERFLOW_PATH not in sys.path:
    sys.path.insert(0, DEERFLOW_PATH)

try:
    from deerflow_extensions.data_collection.startup import install_data_collection

    install_data_collection()
    print("[DataCollection] LangGraph startup injection via sitecustomize")
except ImportError as e:
    print(f"[DataCollection] Startup injection skipped: {e}")
except Exception as e:
    print(f"[DataCollection] Startup injection failed: {e}")
