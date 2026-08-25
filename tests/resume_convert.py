import io
import zipfile

from app.core.resume_convert import ResumeConvertError, to_markdown


def test_md_passthrough():
    text = to_markdown("me.md", "# 李\n\nJava".encode())
    assert text.startswith("# 李")
    assert "Java" in text


def test_docx_extracts_paragraphs():
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Java 负责人</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>13 年</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    text = to_markdown("cv.docx", buf.getvalue())
    assert "Java 负责人" in text
    assert "13 年" in text


def test_old_doc_rejected():
    try:
        to_markdown("cv.doc", b"\xd0\xcf")
    except ResumeConvertError as exc:
        assert ".doc" in str(exc)
    else:
        raise AssertionError("should reject .doc")


def test_pdf_extracts_tj_text():
    pdf = b"%PDF-1.4\nBT /F1 12 Tf 10 100 Td (Hello Resume) Tj ET\n"
    text = to_markdown("cv.pdf", pdf)
    assert "Hello Resume" in text
