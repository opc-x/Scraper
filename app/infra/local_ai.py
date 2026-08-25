"""本机 AI CLI 调用 —— 优先指定引擎，失败按 codex → claude → cursor-agent 回落。

按 CLAUDE.md 的分工，打标签/评估这类活儿在本机订阅上跑，不走生产 API。
codex exec 实测比 claude -p 快一倍（14s vs 30s），所以默认走 codex。
三个都失败时抛 LocalAiError，把每个引擎怎么挂的说清楚，禁止吞成 None。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ENGINES = ("codex", "claude", "cursor-agent")


class LocalAiError(RuntimeError):
    """本机三个订阅都没吐出可用 JSON。str(self) 就是给用户看的原因。"""


def _resolve(name: str) -> str | None:
    """launchd 启动时 PATH 很瘦，which 找不到本机订阅 CLI。"""
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates = [
        home / ".local/bin" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
    ]
    nvm = home / ".nvm/versions/node"
    if nvm.is_dir():
        candidates.extend(sorted(nvm.glob(f"*/bin/{name}"), reverse=True))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def available() -> str | None:
    for name in ENGINES:
        if _resolve(name):
            return name
    return None


def engine_order(preferred: str | None) -> list[str]:
    names = list(ENGINES)
    if preferred in names:
        names.remove(preferred)
        names.insert(0, preferred)
    return names


def _cmd(engine: str) -> list[str]:
    exe = _resolve(engine)
    if not exe:
        raise FileNotFoundError(engine)
    if engine == "codex":
        return [exe, "exec", "-"]
    if engine == "cursor-agent":
        # --mode ask 只读、不会调用 shell/write 工具；--trust 跳过工作区信任交互确认
        # （非交互场景没法确认，不传直接报错退出）。
        return [exe, "-p", "--output-format", "text", "--mode", "ask", "--trust"]
    return [exe, "-p"]


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


def diagnose(engine: str, *, timed_out: bool, rc: int | None, stderr: str, parsed: bool) -> str:
    if timed_out:
        return f"{engine} 超时"
    if rc is None:
        return f"{engine} 找不到"
    err = " ".join((stderr or "").split())
    low = err.lower()
    if "stream disconnected" in low:
        return f"{engine} 断流"
    if parsed:
        return f"{engine} 失败 rc={rc}"
    if not err:
        return f"{engine} 没吐出 JSON"
    return f"{engine} 没吐出 JSON（{err[-80:]}）"


def failure_message(missing: list[str], failures: list[str]) -> str:
    if not failures and set(missing) == set(ENGINES):
        return "本机找不到 AI 订阅 CLI：codex、claude、cursor-agent 都不在 PATH"
    parts = []
    if missing:
        parts.append("找不到 " + "、".join(missing))
    parts.extend(failures)
    if not parts:
        return "本机 AI 全失败，原因不明"
    return "本机 AI 全失败：" + "；".join(parts)


def _run_sync_one(engine: str, prompt: str, timeout: int) -> dict | str:
    """成功返回 dict；失败返回一句诊断。"""
    try:
        r = subprocess.run(
            _cmd(engine), input=prompt, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except FileNotFoundError:
        return diagnose(engine, timed_out=False, rc=None, stderr="", parsed=False)
    except subprocess.TimeoutExpired:
        return diagnose(engine, timed_out=True, rc=None, stderr="", parsed=False)
    data = _parse(r.stdout or "")
    if data is not None:
        return data
    return diagnose(engine, timed_out=False, rc=r.returncode, stderr=r.stderr or "", parsed=False)


def run_sync(prompt: str, engine: str | None = None, timeout: int = 180) -> dict:
    """指定引擎先试，失败按顺序回落。三个都挂了抛 LocalAiError。"""
    missing = [name for name in engine_order(engine) if not _resolve(name)]
    failures: list[str] = []
    for eng in engine_order(engine):
        if not _resolve(eng):
            continue
        result = _run_sync_one(eng, prompt, timeout)
        if isinstance(result, dict):
            return result
        logger.warning("引擎 %s 失败：%s", eng, result)
        failures.append(result)
    raise LocalAiError(failure_message(missing, failures))


async def _run_one(engine: str, prompt: str, timeout: int) -> dict | str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *_cmd(engine),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return diagnose(engine, timed_out=False, rc=None, stderr="", parsed=False)
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            pass
        return diagnose(engine, timed_out=True, rc=None, stderr="", parsed=False)
    data = _parse((out or b"").decode("utf-8", "ignore"))
    if data is not None:
        return data
    return diagnose(
        engine, timed_out=False, rc=proc.returncode,
        stderr=(err or b"").decode("utf-8", "ignore"), parsed=False,
    )


async def run(prompt: str, engine: str | None = None, timeout: int = 180) -> dict:
    """指定引擎先试，失败按顺序回落。三个都挂了抛 LocalAiError。"""
    missing = [name for name in engine_order(engine) if not _resolve(name)]
    failures: list[str] = []
    for eng in engine_order(engine):
        if not _resolve(eng):
            continue
        result = await _run_one(eng, prompt, timeout)
        if isinstance(result, dict):
            return result
        logger.warning("引擎 %s 失败：%s", eng, result)
        failures.append(result)
    raise LocalAiError(failure_message(missing, failures))
