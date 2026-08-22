import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.db.connection import SessionLocal
from app.db.schema import TelegramAccount

logger = logging.getLogger(__name__)

_clients: dict[int, TelegramClient] = {}


def list_accounts() -> list[dict]:
    if not SessionLocal:
        return []
    with SessionLocal() as db:
        rows = db.query(TelegramAccount).order_by(TelegramAccount.id).all()
        return [
            {
                "id": r.id,
                "label": r.label,
                "phone": r.phone,
                "api_id": r.api_id,
                "api_hash": r.api_hash,
                "has_session": bool(r.session_str),
                "is_active": r.is_active,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]


def get_account(account_id: int) -> dict | None:
    if not SessionLocal:
        return None
    with SessionLocal() as db:
        row = db.get(TelegramAccount, account_id)
        if not row:
            return None
        return {
            "id": row.id,
            "label": row.label,
            "phone": row.phone,
            "api_id": row.api_id,
            "api_hash": row.api_hash,
            "session_str": row.session_str,
            "is_active": row.is_active,
        }


def create_account(label: str, phone: str, api_id: str, api_hash: str) -> int:
    if not SessionLocal:
        raise RuntimeError("Database not configured")
    with SessionLocal.begin() as db:
        account = TelegramAccount(label=label, phone=phone, api_id=api_id, api_hash=api_hash)
        db.add(account)
        db.flush()
        return account.id


def update_account(account_id: int, **kwargs):
    if not SessionLocal:
        return
    with SessionLocal.begin() as db:
        account = db.get(TelegramAccount, account_id)
        if not account:
            return
        for key in ("label", "phone", "api_id", "api_hash", "session_str", "is_active"):
            if key in kwargs:
                setattr(account, key, kwargs[key])


def delete_account(account_id: int):
    if not SessionLocal:
        return
    if account_id in _clients:
        # will be cleaned up lazily
        del _clients[account_id]
    with SessionLocal.begin() as db:
        account = db.get(TelegramAccount, account_id)
        if account:
            db.delete(account)


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

    client = TelegramClient(
        StringSession(acct["session_str"]), int(acct["api_id"]), acct["api_hash"]
    )
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
