"""把上传的简历转成 Markdown，方便本机模型按同一份底稿读。"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {".pdf", ".doc", ".docx", ".md", ".markdown"}


class ResumeConvertError(ValueError):
    pass


def ext_of(name: str) -> str:
    return Path(name).suffix.lower()


def title_from_name(name: str) -> str:
    stem = Path(name).stem.strip() or "未命名简历"
    return stem[:80]


def to_markdown(filename: str, data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ResumeConvertError("文件超过 8MB")
    ext = ext_of(filename)
    if ext not in ALLOWED:
        raise ResumeConvertError("只收 PDF / Word / .md")
    if ext == ".doc":
        raise ResumeConvertError("旧版 .doc 不收，另存 .docx 或 .md")
    if ext in {".md", ".markdown"}:
        return _decode_text(data)
    if ext == ".docx":
        return _docx_to_markdown(data)
    return _pdf_to_markdown(data)


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ResumeConvertError("文本编码读不出来")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ResumeConvertError("文件是空的")
    return text


def _docx_to_markdown(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ResumeConvertError("Word 文件坏了") from exc
    root = ET.fromstring(xml)
    lines: list[str] = []
    for para in root.iter(f"{W_NS}p"):
        texts = [node.text or "" for node in para.iter(f"{W_NS}t")]
        line = "".join(texts).strip()
        if line:
            lines.append(line)
    if not lines:
        raise ResumeConvertError("Word 里没有可读文字")
    return "\n\n".join(lines)


def _pdf_to_markdown(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise ResumeConvertError("不是有效的 PDF")
    chunks = [data]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = match.group(1)
        try:
            chunks.append(zlib.decompress(raw))
        except zlib.error:
            continue
    blob = b"\n".join(chunks)
    texts: list[str] = []
    for match in re.finditer(rb"\((?:\\.|[^\\)])*\)\s*Tj", blob):
        texts.append(_pdf_literal(match.group(0)))
    for match in re.finditer(rb"\[(.*?)\]\s*TJ", blob, re.S):
        parts = re.findall(rb"\((?:\\.|[^\\)])*\)", match.group(1))
        piece = "".join(_pdf_literal(p + b" Tj") for p in parts)
        if piece.strip():
            texts.append(piece)
    cleaned = [t.strip() for t in texts if t.strip()]
    if not cleaned:
        raise ResumeConvertError("这个 PDF 抽不出字，另存 .md 再传")
    return "\n\n".join(cleaned)


def _pdf_literal(op: bytes) -> str:
    inner = op[1 : op.rfind(b")")]
    inner = inner.replace(br"\(", b"(").replace(br"\)", b")").replace(br"\\", b"\\")
    inner = inner.replace(br"\n", b"\n").replace(br"\r", b"\r").replace(br"\t", b"\t")
    return inner.decode("latin-1", errors="replace")
