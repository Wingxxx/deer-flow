import json
import os

from deerflow_extensions.ads_auth.config import ADS_BASE_URL, get_mcp_config_path

_ads_tokens: dict[str, str] = {}


async def save_token(user_id: str, token: str):
    _ads_tokens[user_id] = token


async def get_token(user_id: str) -> str | None:
    return _ads_tokens.get(user_id)


async def remove_token(user_id: str):
    _ads_tokens.pop(user_id, None)


async def sync_to_mcp_config(username: str, password: str):
    config_path = get_mcp_config_path()

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        return

    if "ads" not in config:
        config["ads"] = {}
    if "server" not in config["ads"]:
        config["ads"]["server"] = {}

    config["ads"]["server"]["url"] = ADS_BASE_URL

    # 写入用户登录时使用的凭据
    if "credentials" not in config["ads"]:
        config["ads"]["credentials"] = {}
    if "new" not in config["ads"]["credentials"]:
        config["ads"]["credentials"]["new"] = {}
    config["ads"]["credentials"]["new"]["username"] = username
    config["ads"]["credentials"]["new"]["password"] = password

    tmp = config_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    os.rename(tmp, config_path)
