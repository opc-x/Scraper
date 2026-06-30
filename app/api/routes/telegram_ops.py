"""
Telegram 全能操作 API — 多账号支持，给前端和 LLM agent 调用

所有操作接口支持 account_id 参数指定账号，不传则用第一个活跃账号。
GET /api/telegram/docs 获取结构化文档，LLM 可动态检索后调用。
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.telegram_client import get_telegram_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram-ops"])


API_DOCS = [
    {
        "method": "GET",
        "path": "/api/telegram/docs",
        "description": "获取所有 Telegram API 接口的结构化文档，LLM 应首先调用此接口了解可用能力",
        "params": [],
    },
    {
        "method": "GET",
        "path": "/api/telegram/accounts",
        "description": "列出所有 Telegram 账号（支持多账号）",
        "params": [],
    },
    {
        "method": "POST",
        "path": "/api/telegram/accounts",
        "description": "添加新 Telegram 账号",
        "params": [
            {"name": "label", "type": "string", "required": True, "description": "账号备注名"},
            {"name": "phone", "type": "string", "required": True, "description": "手机号（带区号）"},
            {"name": "api_id", "type": "string", "required": True, "description": "Telegram API ID"},
            {"name": "api_hash", "type": "string", "required": True, "description": "Telegram API Hash"},
        ],
    },
    {
        "method": "PUT",
        "path": "/api/telegram/accounts/{account_id}",
        "description": "更新账号信息",
        "params": [
            {"name": "account_id", "type": "int", "required": True, "description": "账号ID（路径参数）"},
            {"name": "label", "type": "string", "required": False, "description": "备注名"},
            {"name": "is_active", "type": "bool", "required": False, "description": "是否启用"},
        ],
    },
    {
        "method": "DELETE",
        "path": "/api/telegram/accounts/{account_id}",
        "description": "删除账号",
        "params": [
            {"name": "account_id", "type": "int", "required": True, "description": "账号ID（路径参数）"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/accounts/{account_id}/status",
        "description": "检查指定账号的登录状态",
        "params": [
            {"name": "account_id", "type": "int", "required": True, "description": "账号ID"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/accounts/{account_id}/send-code",
        "description": "向指定账号发送登录验证码",
        "params": [
            {"name": "account_id", "type": "int", "required": True, "description": "账号ID"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/accounts/{account_id}/verify-code",
        "description": "验证登录码完成登录",
        "params": [
            {"name": "account_id", "type": "int", "required": True, "description": "账号ID"},
            {"name": "code", "type": "string", "required": True, "description": "验证码"},
            {"name": "password", "type": "string", "required": False, "description": "两步验证密码"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/search/global",
        "description": "全局搜索账号/群/频道/Bot，按关键词搜索整个 Telegram",
        "params": [
            {"name": "q", "type": "string", "required": True, "description": "搜索关键词"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID，不传用默认"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/search/messages",
        "description": "搜索所有对话中的消息（跨群+私聊+频道）",
        "params": [
            {"name": "q", "type": "string", "required": True, "description": "搜索关键词"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回条数，默认 50"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/messages",
        "description": "读取指定群/频道/用户的消息（公开频道不用加入也能读）",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或数字ID或手机号"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回条数，默认 50"},
            {"name": "q", "type": "string", "required": False, "description": "过滤关键词"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/user",
        "description": "获取用户/频道/群的详细信息",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "用户名/数字ID/手机号"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/dialogs",
        "description": "列出指定账号的所有对话（群、频道、私聊）",
        "params": [
            {"name": "limit", "type": "int", "required": False, "description": "最大返回数，默认 50"},
            {"name": "type", "type": "string", "required": False, "description": "过滤：group/channel/user/all"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/join",
        "description": "加入公开群/频道",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或邀请链接"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "POST",
        "path": "/api/telegram/leave",
        "description": "离开群/频道",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道用户名或数字ID"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
    {
        "method": "GET",
        "path": "/api/telegram/participants",
        "description": "获取群/频道的成员列表",
        "params": [
            {"name": "target", "type": "string", "required": True, "description": "群/频道"},
            {"name": "limit", "type": "int", "required": False, "description": "最大返回数，默认 100"},
            {"name": "q", "type": "string", "required": False, "description": "按名字搜成员"},
            {"name": "account_id", "type": "int", "required": False, "description": "指定账号ID"},
        ],
    },
]


@router.get("/docs")
async def get_docs():
    return {"apis": API_DOCS, "note": "所有操作接口支持 account_id 参数，不传则用第一个活跃账号"}


# ── 工具函数 ────────────────────────────

async def _require_client(account_id: int | None = None):
    client = await get_telegram_client(account_id)
    if not client:
        raise HTTPException(401, "Telegram 未登录或账号不存在")
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
async def search_global(
    q: str = Query(..., description="搜索关键词"),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
    from telethon.tl.functions.contacts import SearchRequest
    result = await client(SearchRequest(q=q, limit=20))

    users = [
        {"type": "user", "id": u.id, "username": u.username,
         "first_name": u.first_name, "last_name": u.last_name,
         "phone": getattr(u, "phone", None), "bot": u.bot}
        for u in result.users
    ]
    chats = [
        {"type": "channel" if getattr(c, "broadcast", False) else "group",
         "id": c.id, "title": c.title, "username": getattr(c, "username", None),
         "participants_count": getattr(c, "participants_count", None)}
        for c in result.chats
    ]
    return {"users": users, "chats": chats, "total": len(users) + len(chats)}


# ── 全局搜索消息 ────────────────────────────

@router.get("/search/messages")
async def search_messages(
    q: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
    messages = []
    async for msg in client.iter_messages(None, search=q, limit=limit):
        chat = await msg.get_chat()
        messages.append({
            "id": msg.id, "text": msg.text or "", "date": _serialize_date(msg.date),
            "chat": {"id": chat.id if chat else None,
                     "title": getattr(chat, "title", None) or getattr(chat, "first_name", None),
                     "username": getattr(chat, "username", None)},
            "sender_id": msg.sender_id,
        })
    return {"messages": messages, "total": len(messages)}


# ── 读取指定实体的消息 ────────────────────────────

@router.get("/messages")
async def get_messages(
    target: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    q: str = Query(None),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
    entity = await client.get_entity(_resolve_entity_id(target))
    kwargs = {"limit": limit}
    if q:
        kwargs["search"] = q

    def _extract_sender(msg) -> dict:
        """同步从已加载的 msg.sender 提取信息，避免额外网络请求"""
        s = getattr(msg, "sender", None)
        if s is None:
            sid = msg.sender_id
            return {"id": sid, "name": None, "username": None} if sid else {}
        if hasattr(s, "first_name"):
            name = " ".join(filter(None, [s.first_name or "", s.last_name or ""]))
            return {"id": s.id, "name": name or None, "username": s.username, "type": "user",
                    "deleted": getattr(s, "deleted", False)}
        title = getattr(s, "title", None)
        return {"id": s.id, "name": title, "username": getattr(s, "username", None), "type": "channel"}

    def _extract_media(msg) -> str | None:
        if msg.sticker: return "🎭 贴纸"
        if msg.photo: return "📷 图片"
        if msg.video: return "🎥 视频"
        if msg.audio: return "🎵 音频"
        if msg.document: return "📄 文件"
        if msg.geo: return "📍 位置"
        if msg.contact: return f"👤 联系人 {getattr(msg.contact,'first_name','')} {getattr(msg.contact,'phone_number','')}"
        if not msg.text: return "📎 媒体"
        return None

    def _extract_fwd(msg) -> dict | None:
        fwd = getattr(msg, "fwd_from", None)
        if not fwd: return None
        name = None
        username = None
        if fwd.from_name:
            name = fwd.from_name
        peer = getattr(fwd, "from_id", None)
        if peer and hasattr(peer, "channel_id"):
            name = name or f"频道#{peer.channel_id}"
        return {"name": name, "date": _serialize_date(fwd.date)} if name else None

    def _extract_web_preview(msg) -> dict | None:
        wp = getattr(msg.media, "webpage", None) if msg.media else None
        if not wp or not hasattr(wp, "url"): return None
        return {
            "url": wp.url,
            "site_name": getattr(wp, "site_name", None),
            "title": getattr(wp, "title", None),
            "description": getattr(wp, "description", None),
        }

    messages = []
    async for msg in client.iter_messages(entity, **kwargs):
        messages.append({
            "id": msg.id,
            "text": msg.text or "",
            "media_type": _extract_media(msg),
            "fwd_from": _extract_fwd(msg),
            "web_preview": _extract_web_preview(msg),
            "date": _serialize_date(msg.date),
            "sender": _extract_sender(msg),
        })
    return {"target": target, "messages": messages, "total": len(messages)}


# ── 用户/频道/群详情 ────────────────────────────

@router.get("/user")
async def get_user_info(
    target: str = Query(...),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
    entity = await client.get_entity(_resolve_entity_id(target))
    info = {"id": entity.id}
    if hasattr(entity, "first_name"):
        info.update({"type": "user", "first_name": entity.first_name, "last_name": entity.last_name,
                     "username": entity.username, "phone": getattr(entity, "phone", None),
                     "bot": getattr(entity, "bot", False)})
    elif hasattr(entity, "title"):
        info.update({"type": "channel" if getattr(entity, "broadcast", False) else "group",
                     "title": entity.title, "username": getattr(entity, "username", None),
                     "participants_count": getattr(entity, "participants_count", None)})
    if hasattr(entity, "about"):
        info["about"] = entity.about
    return info


# ── 我的对话列表 ────────────────────────────

@router.get("/dialogs")
async def list_dialogs(
    limit: int = Query(50, ge=1, le=200),
    type: str = Query("all"),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
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
            "id": d.id, "type": dtype, "name": d.name,
            "username": getattr(d.entity, "username", None),
            "unread_count": d.unread_count,
            "last_message": d.message.text[:100] if d.message and d.message.text else None,
            "last_date": _serialize_date(d.date),
        })
    return {"dialogs": dialogs, "total": len(dialogs)}


# ── 加入/离开群 ────────────────────────────

class TargetRequest(BaseModel):
    target: str
    account_id: int | None = None


@router.post("/join")
async def join_channel(req: TargetRequest):
    client = await _require_client(req.account_id)
    try:
        from telethon.tl.functions.channels import JoinChannelRequest
        entity = await client.get_entity(req.target)
        await client(JoinChannelRequest(entity))
        name = getattr(entity, "title", None) or req.target
        return {"ok": True, "message": f"已加入 {name}"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/leave")
async def leave_channel(req: TargetRequest):
    client = await _require_client(req.account_id)
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
    target: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    q: str = Query(None),
    account_id: int | None = Query(None),
):
    client = await _require_client(account_id)
    entity = await client.get_entity(_resolve_entity_id(target))
    kwargs = {"limit": limit}
    if q:
        kwargs["search"] = q
    participants = []
    async for p in client.iter_participants(entity, **kwargs):
        participants.append({
            "id": p.id, "username": p.username,
            "first_name": p.first_name, "last_name": p.last_name, "bot": p.bot,
        })
    return {"target": target, "participants": participants, "total": len(participants)}


# ── AI 消息分类过滤 ────────────────────────────

import re
import json
import httpx

_JUNK_RE = re.compile(
    r"(加我|加群|广告|优惠|打折|兼职|刷单|日结|内部资料|培训|课程|代理|招代理"
    r"|点击链接|免费领|限时|秒杀|抢购|转发此消息|@所有人)",
    re.IGNORECASE,
)

_CLASSIFY_PROMPT = """你是消息价值分类器。判断每条消息对求职者是否有价值。

有价值（keep=true）：招聘/求职/内推/职位/面试/Offer/薪资/HR联系/简历/行业资讯/技术干货/人脉资源
无价值（keep=false）：闲聊/表情/广告/培训推广/刷单/水消息/纯表情或链接

对每条消息返回：
- id: 原始消息id（整数）
- keep: true/false
- tag: 一个标签（招聘|内推|资讯|资源|闲聊|广告|其他）
- reason: ≤10字说明原因

只返回 JSON 数组，不要其他内容。"""


class ClassifyRequest(BaseModel):
    target: str
    account_id: int | None = None
    limit: int = 100


@router.post("/classify")
async def classify_messages(req: ClassifyRequest):
    from app.core.channel_config import get_channel_config

    client = await _require_client(req.account_id)
    entity = await client.get_entity(_resolve_entity_id(req.target))

    # ── 1. 拉消息 ──
    raw = []
    async for msg in client.iter_messages(entity, limit=min(req.limit, 200)):
        s = getattr(msg, "sender", None)
        sender = {}
        if s is not None:
            if hasattr(s, "first_name"):
                name = " ".join(filter(None, [s.first_name or "", s.last_name or ""]))
                sender = {"id": s.id, "name": name or None, "username": s.username,
                          "type": "user", "deleted": getattr(s, "deleted", False)}
            else:
                sender = {"id": s.id, "name": getattr(s, "title", None),
                          "username": getattr(s, "username", None), "type": "channel"}
        raw.append({"id": msg.id, "text": msg.text or "", "date": _serialize_date(msg.date), "sender": sender})

    # ── 2. 规则预筛（快速丢掉明显垃圾）──
    def rule_keep(m: dict) -> bool:
        t = m["text"]
        if len(t) < 10: return False
        if _JUNK_RE.search(t): return False
        return True

    passable = [m for m in raw if rule_keep(m)]
    rule_dropped = len(raw) - len(passable)

    # ── 3. LLM 批分类 ──
    cfg = get_channel_config("telegram")
    api_key = cfg.get("llm_api_key", "")
    classifications: dict[int, dict] = {}

    if api_key and passable:
        BATCH = 40
        for i in range(0, len(passable), BATCH):
            batch = passable[i:i + BATCH]
            payload = [{"id": m["id"], "text": m["text"][:300]} for m in batch]
            try:
                async with httpx.AsyncClient(timeout=60) as http:
                    resp = await http.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "system", "content": _CLASSIFY_PROMPT},
                                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                            ],
                            "temperature": 0,
                        },
                    )
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                    items = json.loads(content)
                    for item in items:
                        classifications[item["id"]] = item
            except Exception as e:
                logger.warning("LLM classify batch %d failed: %s", i, e)

    # ── 4. 合并结果 ──
    result = []
    for m in raw:
        cls = classifications.get(m["id"])
        if cls:
            m["keep"] = cls.get("keep", True)
            m["tag"] = cls.get("tag", "其他")
            m["reason"] = cls.get("reason", "")
        elif rule_keep(m):
            m["keep"] = True
            m["tag"] = "未分类"
            m["reason"] = "规则通过，未经LLM"
        else:
            m["keep"] = False
            m["tag"] = "垃圾"
            m["reason"] = "规则过滤"
        result.append(m)

    kept = sum(1 for m in result if m["keep"])
    return {
        "total": len(raw),
        "rule_dropped": rule_dropped,
        "llm_classified": len(classifications),
        "kept": kept,
        "messages": result,
    }
