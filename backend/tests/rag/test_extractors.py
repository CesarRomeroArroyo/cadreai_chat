from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.rag.errors import EmptyDocumentError, TextlessPdfError, UnsupportedDocumentError
from app.rag.extractors import extract_file, extract_html


def test_extracts_markdown_sections_and_title() -> None:
    document = extract_file(
        "services.md",
        "text/markdown",
        b"# Cadre Services\nStrategy and engineering.\n## Security\nData controls.",
    )

    assert document.title == "Cadre Services"
    assert [section.location for section in document.sections] == [
        "Cadre Services",
        "Security",
    ]


def test_rejects_empty_and_binary_text() -> None:
    with pytest.raises(EmptyDocumentError):
        extract_file("empty.txt", "text/plain", b"  \n")
    with pytest.raises(UnsupportedDocumentError):
        extract_file("binary.txt", "text/plain", b"hello\x00world")


def test_rejects_challenge_content_even_when_renamed() -> None:
    with pytest.raises(UnsupportedDocumentError, match="Challenge"):
        extract_file(
            "approved.pdf.txt",
            "text/plain",
            b"Cadre AI | Candidate Take-Home Challenge",
        )


def test_reports_pdf_without_extractable_text() -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)

    with pytest.raises(TextlessPdfError):
        extract_file("scan.pdf", "application/pdf", output.getvalue())


def test_extracts_structured_html_without_scripts_or_navigation() -> None:
    document = extract_html(
        "https://cadreai.com/services",
        b"<html><head><title>Services</title></head><body><nav>Ignore</nav>"
        b"<h1>AI Strategy</h1><p>Find valuable workflows.</p>"
        b"<script>Ignore this too</script></body></html>",
    )

    assert document.title == "Services"
    assert document.sections[0].location == "AI Strategy"
    assert document.sections[0].text == "Find valuable workflows."
