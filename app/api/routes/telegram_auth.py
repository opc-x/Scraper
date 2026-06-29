import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.telegram_client import (
    create_account, delete_account, get_account, list_accounts, update_account,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

_pending: dict[int, dict] = {}


# ── 账号 CRUD ────────────────────────────

class AccountCreate(BaseModel):
    label: str
    phone: str
    api_id: str
    api_hash: str


class AccountUpdate(BaseModel):
    label: str | None = None
    phone: str | None = None
    api_id: str | None = None
    api_hash: str | None = None
    is_active: bool | None = None


@router.get("/accounts")
async def get_accounts():
    accounts = list_accounts()
    return {"accounts": accounts, "total": len(accounts)}


@router.post("/accounts")
async def add_account(req: AccountCreate):
    try:
        aid = create_account(req.label, req.phone, req.api_id, req.api_hash)
        return {"ok": True, "id": aid, "message": f"账号 {req.label} 已添加"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/accounts/{account_id}")
async def edit_account(account_id: int, req: AccountUpdate):
    acct = get_account(account_id)
    if not acct:
        raise HTTPException(404, "账号不存在")
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if kwargs:
        update_account(account_id, **kwargs)
    return {"ok": True, "message": "已更新"}


@router.delete("/accounts/{account_id}")
async def remove_account(account_id: int):
    acct = get_account(account_id)
    if not acct:
        raise HTTPException(404, "账号不存在")
    delete_account(account_id)
    return {"ok": True, "message": "已删除"}


# ── 账号登录状态 ────────────────────────────

@router.get("/accounts/{account_id}/status")
async def account_status(account_id: int):
    acct = get_account(account_id)
    if not acct:
        raise HTTPException(404, "账号不存在")

    if not acct["session_str"]:
        return {"status": "not_logged_in", "message": "需要验证码登录", "account_id": account_id}

    try:
        client = TelegramClient(StringSession(acct["session_str"]), int(acct["api_id"]), acct["api_hash"])
        await client.connect()
        authorized = await client.is_user_authorized()
        await client.disconnect()
        if authorized:
            return {"status": "logged_in", "message": "已登录", "account_id": account_id}
        return {"status": "session_expired", "message": "Session 已过期", "account_id": account_id}
    except Exception as e:
        return {"status": "error", "message": str(e), "account_id": account_id}


# ── 发送验证码 ────────────────────────────

@router.post("/accounts/{account_id}/send-code")
async def send_code(account_id: int):
    acct = get_account(account_id)
    if not acct:
        raise HTTPException(404, "账号不存在")

    try:
        if account_id in _pending and _pending[account_id].get("client"):
            await _pending[account_id]["client"].disconnect()

        client = TelegramClient(StringSession(), int(acct["api_id"]), acct["api_hash"])
        await client.connect()
        result = await client.send_code_request(acct["phone"])
        _pending[account_id] = {"client": client, "phone_hash": result.phone_code_hash}

        return {"ok": True, "message": f"验证码已发送到 {acct['phone']}"}
    except Exception as e:
        logger.error("Send code failed for account %d: %s", account_id, e)
        raise HTTPException(500, str(e))


# ── 验证码登录 ────────────────────────────

class VerifyCodeRequest(BaseModel):
    code: str
    password: str = ""


@router.post("/accounts/{account_id}/verify-code")
async def verify_code(account_id: int, req: VerifyCodeRequest):
    if account_id not in _pending:
        raise HTTPException(400, "请先发送验证码")

    pending = _pending[account_id]
    client = pending["client"]
    acct = get_account(account_id)

    try:
        await client.sign_in(
            phone=acct["phone"],
            code=req.code,
            phone_code_hash=pending["phone_hash"],
        )
    except Exception as e:
        err_msg = str(e)
        if "Two-steps verification" in err_msg or "password" in err_msg.lower():
            if not req.password:
                return {"ok": False, "need_2fa": True, "message": "需要两步验证密码"}
            try:
                await client.sign_in(password=req.password)
            except Exception as e2:
                raise HTTPException(400, f"两步验证失败: {e2}")
        else:
            raise HTTPException(400, f"验证失败: {e}")

    session_str = client.session.save()
    update_account(account_id, session_str=session_str)

    await client.disconnect()
    del _pending[account_id]

    return {"ok": True, "message": "登录成功"}


# ── 兼容旧接口（重定向到第一个账号） ────────────────────────────

@router.get("/status")
async def legacy_status():
    accounts = list_accounts()
    if not accounts:
        return {"status": "no_accounts", "message": "没有 Telegram 账号，请先添加"}
    active = [a for a in accounts if a["is_active"] and a["has_session"]]
    if active:
        return {"status": "logged_in", "message": f"已登录 {len(active)} 个账号"}
    return {"status": "not_logged_in", "message": "没有已登录的账号"}
