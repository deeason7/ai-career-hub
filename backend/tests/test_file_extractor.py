"""Error-handling tests for upload text extraction."""

import pytest

from app.services.file_extractor import _extract_docx, _extract_pdf


def test_extract_pdf_corrupt_raises_valueerror():
    with pytest.raises(ValueError, match="Could not read the PDF"):
        _extract_pdf(b"definitely not a real pdf")


def test_extract_docx_corrupt_raises_valueerror():
    with pytest.raises(ValueError, match="Could not read the DOCX"):
        _extract_docx(b"definitely not a real docx")
