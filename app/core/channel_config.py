from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent.parent / "channels.yaml"

_DEFAULT = {
    "boss": {"enabled": True, "cookie": ""},
    "liepin": {"enabled": False, "cookie": ""},
    "zhilian": {"enabled": False, "cookie": ""},
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        save_config(_DEFAULT)
        return _DEFAULT
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for ch, defaults in _DEFAULT.items():
        if ch not in data:
            data[ch] = defaults
    return data


def save_config(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_channel_config(channel: str) -> dict:
    cfg = load_config()
    return cfg.get(channel, {})
