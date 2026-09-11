import re
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.rag.errors import EmptyDocumentError, TextlessPdfError, UnsupportedDocumentError
from app.rag.models import ExtractedDocument, ExtractedSection
from app.rag.text import normalize_text

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
TEXT_MIME_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
PDF_MIME_TYPES = {"application/pdf", "application/x-pdf"}
FORBIDDEN_MARKERS = (
    "cadre ai | candidate take-home challenge",
    "ai engineer & fde technical take-home",
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _validate_not_forbidden(text: str) -> None:
    lowered = text.casefold()
    if any(marker in lowered for marker in FORBIDDEN_MARKERS):
        raise UnsupportedDocumentError("Challenge or development instructions cannot be indexed")


def _validate_text(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        raise EmptyDocumentError("Document contains no usable text")
    _validate_not_forbidden(normalized)
    return normalized


def _decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise UnsupportedDocumentError("Text document contains binary data")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Text documents must use UTF-8 encoding") from exc


def _extract_markdown(filename: str, data: bytes) -> ExtractedDocument:
    text = _validate_text(_decode_text(data))
    title = Path(filename).stem
    sections: list[ExtractedSection] = []
    current_heading = "Document"
    current_lines: list[str] = []

    def flush() -> None:
        content = normalize_text("\n".join(current_lines))
        if content:
            sections.append(ExtractedSection(location=current_heading, text=content))

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            current_lines = []
            current_heading = normalize_text(match.group(2))
            if not sections and current_heading:
                title = current_heading
        else:
            current_lines.append(line)
    flush()
    if not sections:
        sections.append(ExtractedSection(location="Document", text=text))
    return ExtractedDocument(title=title, sections=tuple(sections))


def _extract_text(filename: str, data: bytes) -> ExtractedDocument:
    text = _validate_text(_decode_text(data))
    return ExtractedDocument(
        title=Path(filename).stem,
        sections=(ExtractedSection(location="Document", text=text),),
    )


def _extract_pdf(filename: str, data: bytes) -> ExtractedDocument:
    if not data.startswith(b"%PDF-"):
        raise UnsupportedDocumentError("PDF signature does not match its extension")
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise UnsupportedDocumentError("PDF could not be parsed") from exc

    sections: list[ExtractedSection] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = normalize_text(page.extract_text() or "")
        if page_text:
            sections.append(ExtractedSection(location=f"Page {page_number}", text=page_text))
    if not sections:
        raise TextlessPdfError("PDF contains no extractable text; OCR is not supported")

    combined = "\n".join(section.text for section in sections)
    _validate_not_forbidden(combined)
    title = normalize_text(str(reader.metadata.title or "")) if reader.metadata else ""
    return ExtractedDocument(title=title or Path(filename).stem, sections=tuple(sections))


def extract_file(filename: str, content_type: str | None, data: bytes) -> ExtractedDocument:
    extension = Path(filename).suffix.casefold()
    mime = (content_type or "").split(";", maxsplit=1)[0].strip().casefold()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedDocumentError("Only Markdown, TXT, and PDF files are supported")
    if extension == ".pdf":
        if mime and mime not in PDF_MIME_TYPES:
            raise UnsupportedDocumentError("Declared MIME type does not match PDF content")
        return _extract_pdf(filename, data)
    if mime and mime not in TEXT_MIME_TYPES and mime != "application/octet-stream":
        raise UnsupportedDocumentError("Declared MIME type does not match text content")
    if extension == ".md":
        return _extract_markdown(filename, data)
    return _extract_text(filename, data)


def extract_html(url: str, data: bytes) -> ExtractedDocument:
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Web page must use UTF-8 compatible text") from exc
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        element.decompose()

    title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else url
    sections: list[ExtractedSection] = []
    current_heading = "Page"
    current_parts: list[str] = []

    def flush() -> None:
        text = normalize_text("\n".join(current_parts))
        if text:
            sections.append(ExtractedSection(location=current_heading, text=text))

    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = normalize_text(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name and element.name.startswith("h"):
            flush()
            current_parts = []
            current_heading = text
        else:
            current_parts.append(text)
    flush()
    if not sections:
        fallback = _validate_text(soup.get_text("\n", strip=True))
        sections.append(ExtractedSection(location="Page", text=fallback))
    _validate_not_forbidden("\n".join(section.text for section in sections))
    return ExtractedDocument(title=title, sections=tuple(sections))


def extract_web_content(
    url: str,
    content_type: str,
    data: bytes,
) -> ExtractedDocument:
    mime = content_type.split(";", maxsplit=1)[0].strip().casefold()
    if mime in {"text/html", "application/xhtml+xml"}:
        return extract_html(url, data)
    if mime in TEXT_MIME_TYPES:
        return _extract_text(Path(url).name or "web-source.txt", data)
    if mime in PDF_MIME_TYPES:
        return _extract_pdf(Path(url).name or "web-source.pdf", data)
    raise UnsupportedDocumentError(f"Unsupported response content type: {mime or 'missing'}")
