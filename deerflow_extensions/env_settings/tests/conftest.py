"""测试 fixtures: 提供 mock provider 数据，避免依赖真实 providers.json。"""

from unittest.mock import patch

import pytest

# 测试用厂商数据（与生产 providers.json 结构一致）
TEST_PROVIDERS: dict = {
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "env_prefix": "DEEPSEEK",
        "deeprag_provider_id": "deepseek",
        "deeprag_prefix": "DEEPSEEK",
        "default_base_url": "https://api.deepseek.com",
        "default_models": ["deepseek-v4-pro", "deepseek-v4-flash"],
    },
    "moonshot": {
        "id": "moonshot",
        "name": "Kimi",
        "env_prefix": "MOONSHOT",
        "deeprag_provider_id": "kimi",
        "deeprag_prefix": "KIMI",
        "default_base_url": "https://api.moonshot.cn/v1",
        "default_models": ["kimi-k3", "kimi-k2.6"],
    },
    "volcengine": {
        "id": "volcengine",
        "name": "Doubao",
        "env_prefix": "VOLCENGINE",
        "deeprag_provider_id": "doubao",
        "deeprag_prefix": "DOUBAO",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_models": ["doubao-seed-2-1-pro-260628", "doubao-seed-2-0-lite-260428"],
    },
    "dashscope": {
        "id": "dashscope",
        "name": "Qwen",
        "env_prefix": "DASHSCOPE",
        "deeprag_provider_id": "qwen",
        "deeprag_prefix": "QWEN",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"],
    },
    "minimax": {
        "id": "minimax",
        "name": "MiniMax",
        "env_prefix": "MINIMAX",
        "deeprag_provider_id": "minimax",
        "deeprag_prefix": "MINIMAX",
        "default_base_url": "https://api.minimax.io/v1",
        "default_models": ["MiniMax-M2.7", "MiniMax-M2.5"],
    },
    "zhipuai": {
        "id": "zhipuai",
        "name": "GLM",
        "env_prefix": "ZHIPUAI",
        "deeprag_provider_id": "glm",
        "deeprag_prefix": "GLM",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_models": ["glm-4.7", "glm-4.5", "glm-4.5-air"],
    },
    "siliconflow": {
        "id": "siliconflow",
        "name": "硅基流动",
        "env_prefix": "SILICONFLOW",
        "deeprag_provider_id": "siliconflow",
        "deeprag_prefix": "SILICONFLOW",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "default_models": ["Pro/Qwen/Qwen3.5-397B-A17B", "Pro/deepseek-ai/DeepSeek-V3.2"],
    },
}


@pytest.fixture(autouse=True)
def _patch_get_providers():
    """mock _get_providers：返回固定测试数据，避免依赖真实 providers.json。"""
    with patch(
        "deerflow_extensions.env_settings.router._get_providers",
        return_value=TEST_PROVIDERS,
    ) as mock:
        yield mock
