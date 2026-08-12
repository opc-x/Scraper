import json
import logging
import time

from sqlalchemy import text

from app.db.connection import engine
from app.db.schema import Base

logger = logging.getLogger(__name__)

# 板块：每个板块对应一个下游消费方 app
BOARDS = {
    "job": {"name": "求职", "desc": "JobSniper Web 消费"},
    "briefing": {"name": "晨报", "desc": "signore 消费"},
}

CHANNEL_SCHEMA = {
    "boss": {
        "name": "BOSS直聘",
        "board": "job",
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
        "board": "job",
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
        "board": "job",
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
    "x": {
        "name": "X (Twitter)",
        "board": "job",
        "description": "全局搜索帖子，AI 圈/远程/海外招聘信号",
        "fields": [
            {
                "key": "cookie",
                "label": "Cookie（可选，兜底用）",
                "type": "textarea",
                "placeholder": "一般不用填，运行 scripts/x_login.py 交互登录即可",
                "help": "登录态默认走 scripts/x_login.py 人工登录后持久化的浏览器 profile；这里只是备用兜底入口",
                "required": False,
            },
            {
                "key": "llm_api_key",
                "label": "AI 解析 Key（DeepSeek）",
                "type": "password",
                "placeholder": "sk-...",
                "help": "DeepSeek 开放平台 API Key，用于从帖子中提取职位信息",
                "required": True,
            },
        ],
    },
    "liepin": {
        "name": "猎聘",
        "board": "job",
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
        "board": "job",
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


_table_ensured = False


def _ensure_table():
    global _table_ensured
    if engine and not _table_ensured:
        Base.metadata.create_all(engine, checkfirst=True)
        _table_ensured = True


def _default_config() -> dict:
    cfg = {}
    for ch_id, schema in CHANNEL_SCHEMA.items():
        ch = {"enabled": False}
        for field in schema["fields"]:
            ch[field["key"]] = field.get("default", "")
        cfg[ch_id] = ch
    return cfg


_config_cache = {"data": None, "ts": 0.0}
_CACHE_TTL = 60.0  # 秒；配置只在保存/重置时才失效，长 TTL 基本消灭远端 Turso 往返


def _invalidate_cache():
    _config_cache["data"] = None


def load_config() -> dict:
    now = time.monotonic()
    if _config_cache["data"] is not None and now - _config_cache["ts"] < _CACHE_TTL:
        return _config_cache["data"]

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
                    defaults[ch]["enabled"] = bool(row[1])
                    config_data = row[2]
                    if isinstance(config_data, str):
                        config_data = json.loads(config_data) if config_data else {}
                    if isinstance(config_data, dict):
                        defaults[ch].update(config_data)
    except Exception as e:
        logger.warning("Failed to load config from DB: %s", e)

    _config_cache["data"] = defaults
    _config_cache["ts"] = now
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
                        VALUES (:ch, :enabled, :cfg, CURRENT_TIMESTAMP)
                        ON CONFLICT (channel) DO UPDATE
                        SET enabled = :enabled, config_data = :cfg, updated_at = CURRENT_TIMESTAMP
                    """),
                    {"ch": ch_id, "enabled": enabled, "cfg": _json_dumps(config_data)},
                )
        _invalidate_cache()
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
                    VALUES (:ch, :enabled, :cfg, CURRENT_TIMESTAMP)
                    ON CONFLICT (channel) DO UPDATE
                    SET enabled = :enabled, config_data = :cfg, updated_at = CURRENT_TIMESTAMP
                """),
                {"ch": channel, "enabled": enabled, "cfg": _json_dumps(config_data)},
            )
        _invalidate_cache()
    except Exception as e:
        logger.error("Failed to save channel config to DB: %s", e)


def get_channel_config(channel: str) -> dict:
    cfg = load_config()
    return cfg.get(channel, {})


def _json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)
