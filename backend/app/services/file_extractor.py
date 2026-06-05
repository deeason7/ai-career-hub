"""Extract plain text from PDF, DOCX, and TXT uploads."""

import io
import logging

from fastapi import UploadFile

logger = logging.getLogger(__name__)


async def extract_text_from_upload(file: UploadFile) -> str:
    """Return plain text extracted from a PDF, DOCX, or TXT upload. Raises ValueError for other types."""
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

    # A malformed file that slipped past the extension check should surface as a
    # clean 422, so any parse failure is re-raised as ValueError (caught upstream).
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        logger.warning("PDF extraction failed: %s", exc)
        raise ValueError(
            "Could not read the PDF. It may be corrupted, password-protected, or not a valid PDF."
        ) from exc


def _extract_docx(content: bytes) -> str:
    import docx  # noqa: PLC0415

    try:
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        logger.warning("DOCX extraction failed: %s", exc)
        raise ValueError(
            "Could not read the DOCX file. It may be corrupted or not a valid Word document."
        ) from exc
