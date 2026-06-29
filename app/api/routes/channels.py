from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["channels"])

CHANNELS = [
    {
        "id": "boss",
        "name": "BOSS直聘",
        "status": "active",
        "description": "综合流量王，直聊快，互联网/新消费/中小企业",
    },
    {
        "id": "liepin",
        "name": "猎聘",
        "status": "planned",
        "description": "3年+中高端，猎头资源",
    },
    {
        "id": "zhilian",
        "name": "智联招聘",
        "status": "planned",
        "description": "国企央企/金融地产，传统行业",
    },
]


@router.get("/channels")
async def list_channels():
    return {"channels": CHANNELS}
