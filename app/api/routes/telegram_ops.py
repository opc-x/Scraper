"""
Telegram 全能操作 API — 给前端和 LLM agent 调用

所有接口通过 GET /api/telegram/docs 获取结构化文档，
LLM 可以动态检索接口定义，按需调用。
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.telegram_client import get_telegram_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram-ops"])


# ── 接口文档（给 LLM 查） ────────────────────────────

API_DOCS = [
    {
        "method": "GET",
        "path": "/api/telegram/docs",
        "description": "获取所有 Telegram API 接口的结构化文档，LLM 应首先调用此接口了解可用能力",
        "params": [],
    },
    {
        "method": "GET",
        "path": "/api/telegram/search/global",
        "description": "全局搜索账号/群/频道/Bot，按关键词搜索整个 Telegram",
        "params": [{"name": "q", "type": "string", "required": True, "description": "搜索关键词"}],
    },
    {
        "method": "GET",
        "path": "/api/telegram/search/messages",
        "description": "搜索所有对话中的消息（跨群+私聊+频道），按关键词全局搜索聊天记录",
        "params": [
            {"name": "q", "type": "string", "required": True, "description": "搜索关键词"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回条数，默认 50"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/messages",
        "description": "读取指定群/频道/用户的消息（公开频道不用加入也能读）",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名 或 数字ID 或 手机号"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回条数，默认 50"},
            {"name": "q", "type": "string", "required": False, "description": "过滤关键词（可选）"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/user",
        "description": "获取用户/频道/群的详细信息（头像、简介、成员数等）",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "用户名/数字ID/手机号"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/dialogs",
        "description": "列出我的所有对话（群、频道、私聊），类似 Telegram 左侧列表",
        "params": [
            {"name": "limit", "type": "int", "required": False, "description": "最大返回数，默认 50"},
            {"name": "type", "type": "string", "required": False, "description": "过滤类型：group/channel/user/all，默认 all"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/join",
        "description": "加入公开群/频道",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或邀请链接"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/leave",
        "description": "离开群/频道",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或数字ID"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/participants",
        "description": "获取群/频道的成员列表",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或数字ID"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回数，默认 100"},
            {"name": "q", "type": "string", "required": False, "description": "按名字搜成员（可选）"},
        ],
    },
]


@router.get("/docs")
async def get_docs():
    return {"apis": API_DOCS, "note": "所有接口需要先完成 Telegram 登录（/api/telegram/status）"}


# ── 工具函数 ────────────────────────────

async def _require_client():
    client = await get_telegram_client()
    if not client:
        raise HTTPException(401, "Telegram 未登录，请先在渠道配置中完成登录")
    return client


def _resolve_entity_id(ref: str):
    try:
        return int(ref) if ref.lstrip("-").isdigit() else ref
    except ValueError:
        return ref


def _serialize_date(dt):
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt) if dt else None


# ── 全局搜索账号/群/频道 ────────────────────────────

@router.get("/search/global")
async def search_global(q: str = Query(..., description="搜索关键词")):
    client = await _require_client()

    from telethon.tl.functions.contacts import SearchRequest
    result = await client(SearchRequest(q=q, limit=20))

    users = []
    for u in result.users:
        users.append({
            "type": "user",
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": getattr(u, "phone", None),
            "bot": u.bot,
        })

    chats = []
    for c in result.chats:
        chats.append({
            "type": "channel" if getattr(c, "broadcast", False) else "group",
            "id": c.id,
            "title": c.title,
            "username": getattr(c, "username", None),
            "participants_count": getattr(c, "participants_count", None),
        })

    return {"users": users, "chats": chats, "total": len(users) + len(chats)}


# ── 全局搜索消息 ────────────────────────────

@router.get("/search/messages")
async def search_messages(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200),
):
    client = await _require_client()

    messages = []
    async for msg in client.iter_messages(None, search=q, limit=limit):
        chat = await msg.get_chat()
        messages.append({
            "id": msg.id,
            "text": msg.text or "",
            "date": _serialize_date(msg.date),
            "chat": {
                "id": chat.id if chat else None,
                "title": getattr(chat, "title", None) or getattr(chat, "first_name", None),
                "username": getattr(chat, "username", None),
            },
            "sender_id": msg.sender_id,
        })

    return {"messages": messages, "total": len(messages)}


# ── 读取指定实体的消息 ────────────────────────────

@router.get("/messages")
async def get_messages(
    target: str = Query(..., description="群/频道/用户"),
    limit: int = Query(50, ge=1, le=200),
    q: str = Query(None, description="过滤关键词"),
):
    client = await _require_client()
    entity = await client.get_entity(_resolve_entity_id(target))

    messages = []
    kwargs = {"limit": limit}
    if q:
        kwargs["search"] = q

    async for msg in client.iter_messages(entity, **kwargs):
        messages.append({
            "id": msg.id,
            "text": msg.text or "",
            "date": _serialize_date(msg.date),
            "sender_id": msg.sender_id,
            "reply_to": msg.reply_to_msg_id if msg.reply_to else None,
        })

    return {"target": target, "messages": messages, "total": len(messages)}


# ── 用户/频道/群详情 ────────────────────────────

@router.get("/user")
async def get_user_info(target: str = Query(..., description="用户名/ID/手机号")):
    client = await _require_client()
    entity = await client.get_entity(_resolve_entity_id(target))

    info = {"id": entity.id}

    if hasattr(entity, "first_name"):
        info.update({
            "type": "user",
            "first_name": entity.first_name,
            "last_name": entity.last_name,
            "username": entity.username,
            "phone": getattr(entity, "phone", None),
            "bot": getattr(entity, "bot", False),
        })
    elif hasattr(entity, "title"):
        info.update({
            "type": "channel" if getattr(entity, "broadcast", False) else "group",
            "title": entity.title,
            "username": getattr(entity, "username", None),
            "participants_count": getattr(entity, "participants_count", None),
        })

    full = await client.get_entity(entity.id)
    if hasattr(full, "about"):
        info["about"] = full.about

    return info


# ── 我的对话列表 ────────────────────────────

@router.get("/dialogs")
async def list_dialogs(
    limit: int = Query(50, ge=1, le=200),
    type: str = Query("all", description="group/channel/user/all"),
):
    client = await _require_client()

    dialogs = []
    async for d in client.iter_dialogs(limit=limit):
        dtype = "user"
        if d.is_group:
            dtype = "group"
        elif d.is_channel:
            dtype = "channel"

        if type != "all" and dtype != type:
            continue

        dialogs.append({
            "id": d.id,
            "type": dtype,
            "name": d.name,
            "username": getattr(d.entity, "username", None),
            "unread_count": d.unread_count,
            "last_message": d.message.text[:100] if d.message and d.message.text else None,
            "last_date": _serialize_date(d.date),
        })

    return {"dialogs": dialogs, "total": len(dialogs)}


# ── 加入公开群/频道 ────────────────────────────

class JoinRequest(BaseModel):
    target: str


@router.post("/join")
async def join_channel(req: JoinRequest):
    client = await _require_client()
    try:
        from telethon.tl.functions.channels import JoinChannelRequest
        entity = await client.get_entity(req.target)
        await client(JoinChannelRequest(entity))
        name = getattr(entity, "title", None) or getattr(entity, "username", req.target)
        return {"ok": True, "message": f"已加入 {name}"}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── 离开群/频道 ────────────────────────────

class LeaveRequest(BaseModel):
    target: str


@router.post("/leave")
async def leave_channel(req: LeaveRequest):
    client = await _require_client()
    try:
        from telethon.tl.functions.channels import LeaveChannelRequest
        entity = await client.get_entity(_resolve_entity_id(req.target))
        await client(LeaveChannelRequest(entity))
        name = getattr(entity, "title", None) or req.target
        return {"ok": True, "message": f"已离开 {name}"}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── 群/频道成员列表 ────────────────────────────

@router.get("/participants")
async def get_participants(
    target: str = Query(..., description="群/频道"),
    limit: int = Query(100, ge=1, le=500),
    q: str = Query(None, description="搜成员名"),
):
    client = await _require_client()
    entity = await client.get_entity(_resolve_entity_id(target))

    participants = []
    kwargs = {"limit": limit}
    if q:
        kwargs["search"] = q

    async for p in client.iter_participants(entity, **kwargs):
        participants.append({
            "id": p.id,
            "username": p.username,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "bot": p.bot,
        })

    return {"target": target, "participants": participants, "total": len(participants)}
