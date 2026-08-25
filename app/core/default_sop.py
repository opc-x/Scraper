DEFAULT_SOP_NAME = "SOP"
DEFAULT_SOP_DESCRIPTION = "拆履历、补数字、点名挑刺、按洞改，掏不出新洞才收口。"

DEFAULT_SOP_STEPS = [
    {
        "id": "s1",
        "from": "codex",
        "at": "",
        "title": "骨架",
        "body": "把履历拆成可攻击条目，先不抒情。",
    },
    {
        "id": "s2",
        "from": "cursor",
        "at": "codex",
        "title": "补数字",
        "body": "每条要有结果或标「无出处」，不许编。",
    },
    {
        "id": "s3",
        "from": "claude",
        "at": "all",
        "title": "挑刺",
        "body": "点到具体句子：空话、不可证、跟别人撞车的表述。",
    },
    {
        "id": "s4",
        "from": "codex",
        "at": "claude",
        "title": "按洞改",
        "body": "只改被点名的句子，改完丢回去再撕。",
    },
    {
        "id": "s5",
        "from": "claude",
        "at": "",
        "title": "收口",
        "body": "掏不出新洞才签字。终稿只有这一份。",
    },
]
