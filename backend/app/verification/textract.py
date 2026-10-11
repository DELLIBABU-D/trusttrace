"""Text extraction from uploaded files.

PDFs: PyMuPDF text layer. Pages with almost no text (scans) are rendered and OCR'd with Tesseract when it is installed.
Images (JPG/PNG): Tesseract OCR.
Full text is returned to the caller only; it is never logged or stored.
"""
from __future__ import annotations

import io
import logging
import shutil
from dataclasses import dataclass, field

log = logging.getLogger("trusttrace.verification")
MIN_PAGE_CHARS = 40  # below this a PDF page is treated as scanned


@dataclass
class ExtractedText:
    text: str = ""
    pages: int = 0
    method: str = ""
    status: str = "ok"  # ok | low_text | failed
    error: str = ""
    page_texts: list[str] = field(default_factory=list)


def pymupdf():
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24
    except ImportError:
        try:
            import fitz  # older PyMuPDF
        except ImportError:
            return None
    return fitz


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    import os
    cmd = os.environ.get("TT_TESSERACT_CMD")
    if cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        return os.path.isfile(cmd)
    if shutil.which("tesseract"):
        return True
    # Default Windows install location of the UB Mannheim build
    win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(win):
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = win
        return True
    return False


def _ocr_image_bytes(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) < 1400:  # small photos OCR better when enlarged
        scale = 1400 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return pytesseract.image_to_string(img, config="--psm 6")


def extract(data: bytes, content_type: str) -> ExtractedText:
    try:
        if content_type == "application/pdf":
            return _pdf(data)
        if content_type in ("image/jpeg", "image/png"):
            if not ocr_available():
                return ExtractedText(method="ocr_tesseract", status="failed",
                                     error="This is an image and OCR (Tesseract) is not installed on the server, so it could not be read.")
            text = _ocr_image_bytes(data)
            return ExtractedText(text=text, pages=1, method="ocr_tesseract", status="ok" if len(text.strip()) >= MIN_PAGE_CHARS else "low_text",
                                 page_texts=[text])
        return ExtractedText(status="failed", error=f"Unsupported file type {content_type}.")
    except Exception as exc:  # noqa: BLE001 - corrupt files must not crash the pipeline
        log.warning("text extraction failed: %s", type(exc).__name__)
        return ExtractedText(status="failed", error=f"The file could not be read ({type(exc).__name__}).")


MAX_PDF_PAGES = 15        # certificates, marksheets and resumes are short; longer files are refused
MAX_OCR_PAGES = 5         # scanned pages are slow to OCR
MAX_PAGE_AREA = 4 * 595 * 842  # points²: about four A4 pages; larger pages are not rendered for OCR


def _pdf(data: bytes) -> ExtractedText:
    fitz = pymupdf()
    if fitz is None:
        return ExtractedText(method="pymupdf_text", status="failed", error="PyMuPDF is not installed on the server (pip install pymupdf).")
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.needs_pass:
            return ExtractedText(pages=doc.page_count, method="pymupdf_text", status="failed", error="The PDF is password-protected.")
        if doc.page_count > MAX_PDF_PAGES:
            return ExtractedText(pages=doc.page_count, method="pymupdf_text", status="failed",
                                 error=f"The PDF has {doc.page_count} pages; at most {MAX_PDF_PAGES} are processed. Upload just the relevant pages.")
        pages: list[str] = []
        used_ocr = False
        can_ocr = ocr_available()
        ocr_pages = 0
        for page in doc:
            text = page.get_text("text") or ""
            if (len(text.strip()) < MIN_PAGE_CHARS and can_ocr and ocr_pages < MAX_OCR_PAGES
                    and page.rect.width * page.rect.height <= MAX_PAGE_AREA):
                ocr_pages += 1
                pix = page.get_pixmap(dpi=200)
                text = _ocr_image_bytes(pix.tobytes("png"))
                used_ocr = True
            pages.append(text)
        full = "\n".join(pages)
        method = "pymupdf_text+ocr" if used_ocr else "pymupdf_text"
        if len(full.strip()) < MIN_PAGE_CHARS:
            err = "" if can_ocr else "The PDF looks scanned and OCR (Tesseract) is not installed, so its text could not be read."
            return ExtractedText(text=full, pages=len(pages), method=method, status="low_text", error=err, page_texts=pages)
        return ExtractedText(text=full, pages=len(pages), method=method, status="ok", page_texts=pages)
    finally:
        doc.close()


def render_first_page_png(data: bytes, content_type: str) -> bytes | None:
    """Image used for face detection on an ID document (first PDF page, or the image itself)."""
    if content_type in ("image/jpeg", "image/png"):
        return data
    fitz = pymupdf()
    if fitz is None or content_type != "application/pdf":
        return None
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if not doc.page_count or doc[0].rect.width * doc[0].rect.height > MAX_PAGE_AREA:
            return None
        return doc[0].get_pixmap(dpi=200).tobytes("png")
    finally:
        doc.close()
