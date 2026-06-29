from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent.parent / "channels.yaml"

CHANNEL_SCHEMA = {
    "boss": {
        "name": "BOSS直聘",
        "description": "综合流量王，直聊快，互联网/新消费/中小企业",
        "fields": [
            {
                "key": "cookie",
                "label": "Cookie",
                "type": "textarea",
                "placeholder": "从浏览器复制 Cookie 粘贴到这里...",
                "help": "zhipin.com 登录 → F12 → Application → Cookies → 全部复制",
                "required": True,
            },
        ],
    },
    "telegram": {
        "name": "Telegram",
        "description": "内推/猎头/远程/海外/crypto 独占渠道",
        "fields": [
            {
                "key": "api_id",
                "label": "API ID",
                "type": "text",
                "placeholder": "12345678",
                "help": "https://my.telegram.org → API development tools → App api_id",
                "required": True,
            },
            {
                "key": "api_hash",
                "label": "API Hash",
                "type": "password",
                "placeholder": "0123456789abcdef...",
                "help": "同上页面获取的 App api_hash",
                "required": True,
            },
            {
                "key": "phone",
                "label": "手机号",
                "type": "text",
                "placeholder": "+8613800138000",
                "help": "Telegram 注册手机号（带国际区号），首次需验证码登录",
                "required": True,
            },
            {
                "key": "group_ids",
                "label": "监听群组",
                "type": "textarea",
                "placeholder": "每行一个：群用户名(如 python_cn) 或数字 ID(如 -1001234567890)",
                "help": "你已加入的群/频道，用户名或数字 ID 都行",
                "required": True,
            },
            {
                "key": "llm_provider",
                "label": "LLM 提供商",
                "type": "select",
                "options": ["deepseek", "openai", "anthropic"],
                "default": "deepseek",
                "help": "用于从群消息中提取结构化职位信息",
            },
            {
                "key": "llm_api_key",
                "label": "LLM API Key",
                "type": "password",
                "placeholder": "sk-...",
                "help": "对应提供商的 API Key",
                "required": True,
            },
            {
                "key": "llm_base_url",
                "label": "LLM Base URL",
                "type": "text",
                "placeholder": "留空则使用默认地址",
                "help": "自定义 API 地址（可选）",
            },
        ],
    },
    "liepin": {
        "name": "猎聘",
        "description": "3年+中高端，猎头资源",
        "fields": [
            {
                "key": "cookie",
                "label": "Cookie",
                "type": "textarea",
                "placeholder": "从浏览器复制 Cookie 粘贴到这里...",
                "help": "liepin.com 登录 → F12 → Application → Cookies → 全部复制",
                "required": True,
            },
        ],
    },
    "zhilian": {
        "name": "智联招聘",
        "description": "国企央企/金融地产，传统行业",
        "fields": [
            {
                "key": "cookie",
                "label": "Cookie",
                "type": "textarea",
                "placeholder": "从浏览器复制 Cookie 粘贴到这里...",
                "help": "zhaopin.com 登录 → F12 → Application → Cookies → 全部复制",
                "required": True,
            },
        ],
    },
}


def _default_config() -> dict:
    cfg = {}
    for ch_id, schema in CHANNEL_SCHEMA.items():
        ch = {"enabled": False}
        for field in schema["fields"]:
            ch[field["key"]] = field.get("default", "")
        cfg[ch_id] = ch
    return cfg


def load_config() -> dict:
    defaults = _default_config()
    if not CONFIG_PATH.exists():
        save_config(defaults)
        return defaults
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for ch_id, ch_defaults in defaults.items():
        if ch_id not in data:
            data[ch_id] = ch_defaults
        else:
            for k, v in ch_defaults.items():
                if k not in data[ch_id]:
                    data[ch_id][k] = v
    return data


def save_config(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_channel_config(channel: str) -> dict:
    cfg = load_config()
    return cfg.get(channel, {})
