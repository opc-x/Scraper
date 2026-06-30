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
                "help": "浏览器登录 zhipin.com → F12 → Application → Cookies → 全选复制",
                "required": True,
            },
        ],
    },
    "telegram": {
        "name": "Telegram",
        "description": "内推/猎头/远程/海外/crypto 独占渠道",
        "fields": [
            {
                "key": "sources",
                "label": "监听来源",
                "type": "textarea",
                "placeholder": "每行一个群/频道用户名或私聊用户名\n例：\npython_jobs\nhr_xiaoli\n-1001234567890",
                "help": "群/频道/私聊 均支持，用户名(不带@)或数字 ID",
                "required": True,
            },
            {
                "key": "llm_api_key",
                "label": "AI 解析 Key（DeepSeek）",
                "type": "password",
                "placeholder": "sk-...",
                "help": "DeepSeek 开放平台 API Key，用于提取职位信息",
                "required": True,
            },
        ],
    },
    "discord": {
        "name": "Discord",
        "description": "海外远程/Web3/AI 圈招聘，全英文为主",
        "fields": [
            {
                "key": "user_token",
                "label": "User Token",
                "type": "password",
                "placeholder": "粘贴 Discord User Token...",
                "help": (
                    "浏览器登录 discord.com → F12 → Network → "
                    "刷新 → Request Headers 的 authorization（账号 Token）"
                ),
                "required": True,
            },
            {
                "key": "sources",
                "label": "监听来源",
                "type": "textarea",
                "placeholder": "每行一个频道 ID 或服务器 ID\n例：\n1234567890123456789",
                "help": "频道 ID：右键频道复制；服务器 ID：右键服务器图标复制，自动展开文字频道",
                "required": True,
            },
            {
                "key": "llm_api_key",
                "label": "AI 解析 Key（DeepSeek）",
                "type": "password",
                "placeholder": "sk-...",
                "help": "DeepSeek 开放平台 API Key，用于提取职位信息",
                "required": True,
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
