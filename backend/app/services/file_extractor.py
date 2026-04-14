"""
File Extractor Service
Extracts plain text from PDF, DOCX, and TXT files uploaded by users.
"""

import io
import logging

from fastapi import UploadFile

logger = logging.getLogger(__name__)


async def extract_text_from_upload(file: UploadFile) -> str:
    """
    Extract text from an uploaded file.
    Supports: PDF (.pdf), DOCX (.docx), plain text (.txt)
    Raises ValueError for unsupported formats.
    """
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        return _extract_pdf(content)
    elif filename.endswith(".docx"):
        return _extract_docx(content)
    elif filename.endswith(".txt"):
        return content.decode("utf-8", errors="replace")
    else:
        raise ValueError(
            f"Unsupported file type: '{file.filename}'. Please upload a PDF, DOCX, or TXT file."
        )


def _extract_pdf(content: bytes) -> str:
    import fitz  # noqa: PLC0415 — lazy import to avoid startup cost

    doc = fitz.open(stream=content, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def _extract_docx(content: bytes) -> str:
    import docx  # noqa: PLC0415

    doc = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
