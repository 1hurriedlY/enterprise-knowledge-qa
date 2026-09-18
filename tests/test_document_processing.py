from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from app.routers.files import _delete_uploaded_file, _save_upload
from app.services.parsing import DocumentParseError, chunk_text, clean_text, parse_document


def test_cleaning_and_heading_first_chunking() -> None:
    text = clean_text("# 退款政策\n\n## 退款流程\n  第一步：提交申请。\n\n\n第二步：等待审核。")

    chunks = chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0].heading_path == "退款政策 > 退款流程"
    assert chunks[0].content == "第一步：提交申请。\n\n第二步：等待审核。"


def test_long_chunks_keep_overlap() -> None:
    text = "# 规则\n" + "甲" * 560

    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) == 2
    assert chunks[0].heading_path == "规则"
    assert chunks[0].content[-50:] == chunks[1].content[:50]


def test_txt_requires_utf8_and_pdf_errors_are_safe(tmp_path: Path) -> None:
    invalid_text = tmp_path / "invalid.txt"
    invalid_text.write_bytes(b"\xff\xfe")
    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_bytes(b"not a PDF")

    with pytest.raises(DocumentParseError, match="UTF-8"):
        parse_document(invalid_text, ".txt")
    with pytest.raises(DocumentParseError, match="PDF 正文无法解析"):
        parse_document(invalid_pdf, ".pdf")


@pytest.mark.asyncio
async def test_streamed_upload_enforces_limit_and_cleans_partial_file(tmp_path: Path) -> None:
    too_large = UploadFile(filename="too-large.txt", file=BytesIO(b"x" * 11))
    target = tmp_path / "too-large.txt"

    with pytest.raises(ValueError, match="10 MB"):
        await _save_upload(too_large, target, max_bytes=10)

    assert not target.exists()


def test_delete_only_allows_file_under_upload_root(tmp_path: Path) -> None:
    stored = tmp_path / "uploads" / "document.txt"
    stored.parent.mkdir()
    stored.write_text("source", encoding="utf-8")
    settings = SimpleNamespace(upload_dir=stored.parent)

    _delete_uploaded_file(str(stored), settings)

    assert not stored.exists()
