"""
File Text Extraction Service
Extracts plain text from PDF, DOCX, and TXT files uploaded by users.
"""
import io
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)


async def extract_text_from_upload(file: UploadFile) -> str:
    """
    Extract plain text from an uploaded file.
    Supports: .pdf, .docx, .txt
    Raises ValueError for unsupported file types.
    """
    filename = file.filename or ""
    content = await file.read()

    if filename.lower().endswith(".pdf"):
        return _extract_from_pdf(content)
    elif filename.lower().endswith(".docx"):
        return _extract_from_docx(content)
    elif filename.lower().endswith(".txt"):
        return content.decode("utf-8", errors="replace")
    else:
        raise ValueError(
            f"Unsupported file type: '{filename}'. Please upload a PDF, DOCX, or TXT file."
        )


def _extract_from_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF
    text_parts = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
    result = "\n\n".join(text_parts)
    if not result.strip():
        raise ValueError("Could not extract any text from PDF. It may be scanned/image-based.")
    return result


def _extract_from_docx(content: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    from docx import Document
    doc = Document(io.BytesIO(content))
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    result = "\n".join(paragraphs)
    if not result.strip():
        raise ValueError("Could not extract any text from DOCX file.")
    return result
