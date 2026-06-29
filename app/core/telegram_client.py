import logging

from sqlalchemy import text
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.db.connection import engine
from app.db.schema import Base

logger = logging.getLogger(__name__)

_clients: dict[int, TelegramClient] = {}


_table_ready = False

def _ensure_table():
    global _table_ready
    if not engine or _table_ready:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(
                """CREATE TABLE IF NOT EXISTS telegram_accounts (
                    id SERIAL PRIMARY KEY,
                    label VARCHAR(64) NOT NULL,
                    phone VARCHAR(32) NOT NULL UNIQUE,
                    api_id VARCHAR(32) NOT NULL,
                    api_hash VARCHAR(64) NOT NULL,
                    session_str TEXT NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )"""
            ))
        _table_ready = True
    except Exception as e:
        logger.warning("Failed to ensure telegram_accounts table: %s", e)


def list_accounts() -> list[dict]:
    if not engine:
        return []
    _ensure_table()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, label, phone, api_id, api_hash, session_str, is_active, created_at FROM telegram_accounts ORDER BY id"
        ))
        return [
            {"id": r[0], "label": r[1], "phone": r[2], "api_id": r[3], "api_hash": r[4],
             "has_session": bool(r[5]), "is_active": r[6], "created_at": str(r[7])}
            for r in rows
        ]


def get_account(account_id: int) -> dict | None:
    if not engine:
        return None
    _ensure_table()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, label, phone, api_id, api_hash, session_str, is_active FROM telegram_accounts WHERE id = :id"
        ), {"id": account_id}).fetchone()
        if not row:
            return None
        return {"id": row[0], "label": row[1], "phone": row[2], "api_id": row[3],
                "api_hash": row[4], "session_str": row[5], "is_active": row[6]}


def create_account(label: str, phone: str, api_id: str, api_hash: str) -> int:
    if not engine:
        raise RuntimeError("Database not configured")
    _ensure_table()
    with engine.begin() as conn:
        result = conn.execute(text(
            "INSERT INTO telegram_accounts (label, phone, api_id, api_hash, session_str, is_active) VALUES (:l, :p, :ai, :ah, '', true) RETURNING id"
        ), {"l": label, "p": phone, "ai": api_id, "ah": api_hash})
        return result.fetchone()[0]


def update_account(account_id: int, **kwargs):
    if not engine:
        return
    _ensure_table()
    sets = []
    params = {"id": account_id}
    for k in ("label", "phone", "api_id", "api_hash", "session_str", "is_active"):
        if k in kwargs:
            sets.append(f"{k} = :{k}")
            params[k] = kwargs[k]
    if not sets:
        return
    sets.append("updated_at = NOW()")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE telegram_accounts SET {', '.join(sets)} WHERE id = :id"), params)


def delete_account(account_id: int):
    if not engine:
        return
    _ensure_table()
    if account_id in _clients:
        # will be cleaned up lazily
        del _clients[account_id]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM telegram_accounts WHERE id = :id"), {"id": account_id})


async def get_telegram_client(account_id: int | None = None) -> TelegramClient | None:
    if account_id is None:
        accounts = list_accounts()
        active = [a for a in accounts if a["is_active"] and a["has_session"]]
        if not active:
            return None
        account_id = active[0]["id"]

    if account_id in _clients:
        client = _clients[account_id]
        if client.is_connected():
            return client

    acct = get_account(account_id)
    if not acct or not acct["session_str"]:
        return None

    client = TelegramClient(StringSession(acct["session_str"]), int(acct["api_id"]), acct["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        return None

    _clients[account_id] = client
    return client


async def close_all_clients():
    for client in _clients.values():
        try:
            await client.disconnect()
        except Exception:
            pass
    _clients.clear()
