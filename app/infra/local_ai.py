"""本机 AI CLI 调用 —— codex 优先，claude 兜底。

按 CLAUDE.md 的分工，打标签/评估这类活儿在本机订阅上跑，不走生产 API。
codex exec 实测比 claude -p 快一倍（14s vs 30s），所以默认走 codex。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

def available() -> str | None:
    for name in ("codex", "claude"):
        if shutil.which(name):
            return name
    return None


def _cmd(engine: str) -> list[str]:
    # codex exec - 从 stdin 读 prompt；claude -p 同理
    return ["codex", "exec", "-"] if engine == "codex" else ["claude", "-p"]


def _parse(text: str) -> dict | None:
    if not text:
        return None
    # CLI 会夹带前后缀；扫描全部起始花括号，取结束位置最靠后的完整对象。
    decoder = json.JSONDecoder()
    best: tuple[int, dict] | None = None
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, length = decoder.raw_decode(text[start:])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict) and (best is None or start + length > best[0]):
            best = (start + length, value)
    return best[1] if best else None


def _engines(preferred: str | None) -> list[str]:
    order = [preferred] if preferred else ["codex", "claude"]
    return [e for e in order if shutil.which(e)]


def run_sync(prompt: str, engine: str | None = None, timeout: int = 180) -> dict | None:
    """codex 优先，失败自动回落 claude。

    codex 时不时会 `stream disconnected before completion` 直接 returncode=1，
    这种时候不该整批跳过，换个引擎重试一次就行。
    """
    last_err = ""
    for eng in _engines(engine):
        try:
            r = subprocess.run(_cmd(eng), input=prompt, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_err = f"{eng} 超时"
            continue
        data = _parse(r.stdout or "")
        if data is not None:
            return data
        last_err = f"{eng} rc={r.returncode} {(r.stderr or '')[-160:]}"
        logger.warning("引擎 %s 无可用输出：%s", eng, last_err)
    if last_err:
        logger.warning("所有引擎都失败：%s", last_err)
    return None


async def run(prompt: str, engine: str | None = None, timeout: int = 180) -> dict | None:
    engine = engine or available()
    if not engine:
        return None
    proc = await asyncio.create_subprocess_exec(
        *_cmd(engine),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return None
    return _parse((out or b"").decode("utf-8", "ignore"))
