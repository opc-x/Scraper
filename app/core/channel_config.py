import logging

from sqlalchemy import text

from app.db.connection import engine
from app.db.schema import Base

logger = logging.getLogger(__name__)

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
                "required": False,
            },
            {
                "key": "dm_users",
                "label": "监听私聊",
                "type": "textarea",
                "placeholder": "每行一个：用户名(如 hr_xiaoli) 或手机号(如 +8613800138000)",
                "help": "猎头/HR 的 Telegram 用户名或手机号，自动读取对话消息",
                "required": False,
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


def _ensure_table():
    if engine:
        Base.metadata.create_all(engine, checkfirst=True)


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
    if not engine:
        return defaults

    _ensure_table()

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT channel, enabled, config_data FROM channel_configs"))
            for row in rows:
                ch = row[0]
                if ch in defaults:
                    defaults[ch]["enabled"] = row[1]
                    if row[2] and isinstance(row[2], dict):
                        defaults[ch].update(row[2])
    except Exception as e:
        logger.warning("Failed to load config from DB: %s", e)

    return defaults


def save_config(data: dict):
    if not engine:
        return

    _ensure_table()

    try:
        with engine.begin() as conn:
            for ch_id, ch_cfg in data.items():
                enabled = ch_cfg.pop("enabled", False) if "enabled" in ch_cfg else False
                config_data = {k: v for k, v in ch_cfg.items()}
                ch_cfg["enabled"] = enabled

                conn.execute(
                    text("""
                        INSERT INTO channel_configs (channel, enabled, config_data, updated_at)
                        VALUES (:ch, :enabled, :cfg, NOW())
                        ON CONFLICT (channel) DO UPDATE
                        SET enabled = :enabled, config_data = :cfg, updated_at = NOW()
                    """),
                    {"ch": ch_id, "enabled": enabled, "cfg": _json_dumps(config_data)},
                )
    except Exception as e:
        logger.error("Failed to save config to DB: %s", e)


def save_channel_config(channel: str, cfg: dict):
    if not engine:
        return

    _ensure_table()

    enabled = cfg.pop("enabled", False) if "enabled" in cfg else False
    config_data = {k: v for k, v in cfg.items()}
    cfg["enabled"] = enabled

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO channel_configs (channel, enabled, config_data, updated_at)
                    VALUES (:ch, :enabled, :cfg, NOW())
                    ON CONFLICT (channel) DO UPDATE
                    SET enabled = :enabled, config_data = :cfg, updated_at = NOW()
                """),
                {"ch": channel, "enabled": enabled, "cfg": _json_dumps(config_data)},
            )
    except Exception as e:
        logger.error("Failed to save channel config to DB: %s", e)


def get_channel_config(channel: str) -> dict:
    cfg = load_config()
    return cfg.get(channel, {})


def _json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)
