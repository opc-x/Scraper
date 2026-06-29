import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.channel_config import get_channel_config, load_config, save_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

_pending_client: TelegramClient | None = None
_pending_phone_hash: str | None = None


class SendCodeRequest(BaseModel):
    pass


class VerifyCodeRequest(BaseModel):
    code: str
    password: str = ""


@router.get("/status")
async def telegram_status():
    cfg = get_channel_config("telegram")
    api_id = cfg.get("api_id", "")
    api_hash = cfg.get("api_hash", "")
    phone = cfg.get("phone", "")
    session_str = cfg.get("_session", "")

    if not api_id or not api_hash or not phone:
        return {"status": "not_configured", "message": "请先填写 API ID、API Hash 和手机号"}

    if not session_str:
        return {"status": "not_logged_in", "message": "需要验证码登录"}

    try:
        client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
        await client.connect()
        authorized = await client.is_user_authorized()
        await client.disconnect()
        if authorized:
            return {"status": "logged_in", "message": "已登录"}
        return {"status": "session_expired", "message": "Session 已过期，需重新登录"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/send-code")
async def send_code(_: SendCodeRequest):
    global _pending_client, _pending_phone_hash

    cfg = get_channel_config("telegram")
    api_id = cfg.get("api_id", "")
    api_hash = cfg.get("api_hash", "")
    phone = cfg.get("phone", "")

    if not api_id or not api_hash or not phone:
        raise HTTPException(400, "请先保存 API ID、API Hash 和手机号")

    try:
        if _pending_client:
            await _pending_client.disconnect()

        _pending_client = TelegramClient(StringSession(), int(api_id), api_hash)
        await _pending_client.connect()

        result = await _pending_client.send_code_request(phone)
        _pending_phone_hash = result.phone_code_hash

        return {"ok": True, "message": f"验证码已发送到 {phone}"}
    except Exception as e:
        logger.error("Send code failed: %s", e)
        raise HTTPException(500, str(e))


@router.post("/verify-code")
async def verify_code(req: VerifyCodeRequest):
    global _pending_client, _pending_phone_hash

    if not _pending_client or not _pending_phone_hash:
        raise HTTPException(400, "请先发送验证码")

    cfg = get_channel_config("telegram")
    phone = cfg.get("phone", "")

    try:
        await _pending_client.sign_in(
            phone=phone,
            code=req.code,
            phone_code_hash=_pending_phone_hash,
        )
    except Exception as e:
        err_msg = str(e)
        if "Two-steps verification" in err_msg or "password" in err_msg.lower():
            if not req.password:
                return {"ok": False, "need_2fa": True, "message": "需要两步验证密码"}
            try:
                await _pending_client.sign_in(password=req.password)
            except Exception as e2:
                raise HTTPException(400, f"两步验证失败: {e2}")
        else:
            raise HTTPException(400, f"验证码错误: {e}")

    session_str = _pending_client.session.save()

    full_cfg = load_config()
    full_cfg["telegram"]["_session"] = session_str
    save_config(full_cfg)

    await _pending_client.disconnect()
    _pending_client = None
    _pending_phone_hash = None

    return {"ok": True, "message": "登录成功"}
