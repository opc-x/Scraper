"""分析出洞，优化出可采纳条目。模型深挖以后接。"""

from __future__ import annotations

import re

_DIGIT = re.compile(r"\d")


def _bare_bullets(markdown: str) -> list[str]:
    return [
        line.strip(" -*\t")
        for line in markdown.splitlines()
        if line.strip().startswith(("-", "*", "·"))
    ]


def draft_analysis(markdown: str, *, sop_steps: list[dict]) -> list[dict]:
    items: list[dict] = []
    for step in sop_steps:
        title = str(step.get("title") or "").strip()
        body = str(step.get("body") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "quote": "",
                "body": body or f"按「{title}」过一遍原稿。",
            }
        )
    for line in _bare_bullets(markdown):
        if len(items) >= 8:
            break
        if line and not _DIGIT.search(line):
            items.append(
                {
                    "title": "缺数字",
                    "quote": line[:80],
                    "body": f"这条没有结果数字：{line[:80]}",
                }
            )
    if not items:
        items.append(
            {
                "title": "原稿太短",
                "quote": "",
                "body": "先补经历条目再分析。",
            }
        )
    return items


_SKIP_TITLE = {"性别", "年龄", "姓名", "电话", "邮箱", "微信", "手机"}


def draft_report_title(findings: list[dict]) -> str:
    holes = [f for f in findings if str(f.get("title") or "") in {"缺数字", "补数字"} and f.get("quote")]
    holes = [
        f
        for f in holes
        if str(f.get("quote") or "").split("：")[0].split(":")[0].strip() not in _SKIP_TITLE
    ] or holes
    if holes:
        head = str(holes[0].get("quote") or "").split("：")[0].split(":")[0].strip()[:12]
        if len(holes) > 1:
            return f"{head}等 {len(holes)} 处没数字" if head else f"{len(holes)} 处没数字"
        return f"{head}没数字" if head else "条目缺数字"
    for raw in findings:
        title = str(raw.get("title") or "").strip()
        if title and title not in {"骨架", "收口"}:
            return title[:24]
    if findings:
        return str(findings[0].get("title") or "分析报告")[:24]
    return "分析报告"


def draft_suggestions(
    markdown: str,
    *,
    model: str,
    findings: list[dict] | None = None,
    brief: str = "",
) -> list[dict]:
    items: list[dict] = []
    note = (brief or "").strip()
    if note:
        items.append(
            {
                "title": "按你写的改",
                "quote": note[:80],
                "body": note[:400],
                "model": model,
            }
        )
    for raw in findings or []:
        if len(items) >= 6:
            break
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title[:80],
                "quote": str(raw.get("quote") or "")[:80],
                "body": str(raw.get("body") or title)[:400],
                "model": model,
            }
        )
    if items:
        return items
    for line in _bare_bullets(markdown):
        if len(items) >= 5:
            break
        if line and not _DIGIT.search(line):
            items.append(
                {
                    "title": "补数字",
                    "quote": line[:80],
                    "body": f"这条没有结果数字，补上量或结果：{line[:80]}",
                    "model": model,
                }
            )
    if not items:
        items.append(
            {
                "title": "收一版",
                "quote": "",
                "body": "原稿条目都有数字，先压空话、再核对岗位关键词。",
                "model": model,
            }
        )
    return items
