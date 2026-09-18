import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

# pypdf may log malformed-file bytes while parsing. Uploaded document content
# must not escape into service logs merely because a PDF is invalid.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    content: str
    heading_path: str
    chunk_index: int


def parse_document(path: Path, file_type: str) -> str:
    if file_type in {".txt", ".md"}:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentParseError("文件编码必须为 UTF-8") from exc
    if file_type == ".pdf":
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        except Exception as exc:  # pypdf exposes multiple parser exceptions
            raise DocumentParseError("PDF 正文无法解析") from exc
    raise DocumentParseError("不支持的文件类型")


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("\n", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[TextChunk]:
    """Prefer Markdown headings and paragraphs, retaining their heading path."""
    heading_stack: list[tuple[int, str]] = []
    sections: list[tuple[str, str]] = []
    current: list[str] = []

    def flush() -> None:
        content = "\n".join(current).strip()
        if len(content) >= 8:
            sections.append((content, " > ".join(item[1] for item in heading_stack)))
        current.clear()

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush()
            level, title = len(match.group(1)), match.group(2)
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
        else:
            current.append(line)
    flush()
    if not sections and text:
        sections = [(text, "")]

    chunks: list[TextChunk] = []
    for content, heading_path in sections:
        for piece in _split_long_text(content, chunk_size, overlap):
            chunks.append(TextChunk(piece, heading_path, len(chunks)))
    return chunks
