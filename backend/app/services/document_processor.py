"""Document content extraction: stored object -> normalized DocumentContent.

Each reader is strict: a corrupted or malformed file raises ProcessingError
and the document is marked FAILED with the message — there is no partial
"success". Large fields are capped so a pathological file cannot bloat the
database; the full file remains in storage for audit.

Phase 1: readers operate on a byte stream from the configured
``ObjectStorage`` backend (local filesystem or S3-compatible object store) —
never on a hard-coded local path. Scanned content is first-class: a text
PDF page with (almost) no extractable text is OCR'd, image uploads are
OCR'd outright, and when OCR is unavailable or reads nothing the document
FAILS with the real reason instead of silently "processing" to nothing.
"""

from __future__ import annotations

import csv
import io

from ..core.config import get_settings
from .entity_extraction import DocumentContent


class ProcessingError(Exception):
    """Extraction failed; the message is user-safe (no paths, no tracebacks)."""


def _resolve_stream(storage_key: str | None) -> io.BytesIO:
    """Open the document's stored object through the configured backend."""
    from ..core.storage import StorageError, get_storage

    if not storage_key:
        raise ProcessingError("Document has no stored file.")
    try:
        return get_storage().open(storage_key)
    except StorageError as exc:
        raise ProcessingError(str(exc)) from exc


def extract_content(document) -> DocumentContent:
    """Read a Document's stored object into a normalized, capped structure.

    `document` is a Document ORM row (only its id/file_type/storage_path are
    used). Raises ProcessingError on any unreadable/corrupt input.
    """
    settings = get_settings()
    max_chars = settings.extraction_max_chars
    stream = _resolve_stream(document.storage_path)
    ftype = (document.file_type or "").lower()

    try:
        if ftype == "pdf":
            return _read_pdf(document.id, stream, max_chars)
        if ftype in ("txt", "text"):
            return _read_txt(document.id, stream, max_chars)
        if ftype == "csv":
            return _read_csv(document.id, stream, max_chars)
        if ftype in ("png", "jpg", "jpeg", "tif", "tiff"):
            return _read_image(document.id, stream, max_chars)
        raise ProcessingError(f"Unsupported file type for processing: {ftype!r}")
    finally:
        stream.close()


# A page with fewer non-whitespace characters than this is treated as a
# scan (or blank) and handed to OCR when OCR is enabled.
_MIN_PAGE_TEXT_CHARS = 12


def _ocr_page(stream: io.BytesIO, page_no: int, dpi: int) -> str:
    """OCR one PDF page via the PDF rasterizer + tesseract.

    Raises ProcessingError when OCR is unavailable or fails — never
    returns nothing silently.
    """
    from ..pipeline import ocr as pipeline_ocr

    if not pipeline_ocr.capabilities()["available"]:
        raise ProcessingError(
            f"PDF page {page_no} is a scan and OCR is unavailable on this "
            "server (tesseract is not installed). Install 'tesseract-ocr' "
            "to process scanned documents.")
    img = _render_pdf_page(stream, page_no, dpi)
    if img is None:
        raise ProcessingError(
            f"PDF page {page_no} is a scan and page rendering is "
            "unavailable (PyMuPDF is not installed). Install 'pymupdf' "
            "to OCR scanned PDF pages.")
    result = pipeline_ocr.ocr_bytes(img, label=f"pdf-page-{page_no}")
    if not result.ok:
        raise ProcessingError(f"OCR of PDF page {page_no} failed: {result.error}")
    return result.text


def _render_pdf_page(stream: io.BytesIO, page_no: int, dpi: int) -> bytes | None:
    """Rasterize one PDF page to PNG bytes (None when the rasterizer is
    unavailable).

    PyMuPDF's ``fitz.open`` takes the document as a *bytes* payload via the
    ``stream=`` keyword (a file-like positional is rejected), so the object
    is read to bytes first.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        stream.seek(0)
        doc = fitz.open(stream=stream.read())
        try:
            page = doc.load_page(page_no - 1)
            return page.get_pixmap(dpi=dpi).tobytes("png")
        finally:
            doc.close()
    except Exception:  # noqa: BLE001 — caller decides how to fail
        return None


def _read_pdf(doc_id: int, stream: io.BytesIO, max_chars: int) -> DocumentContent:
    settings = get_settings()
    try:
        from pypdf import PdfReader

        stream.seek(0)
        reader = PdfReader(stream)
        pages: list[dict] = []
        total = 0
        ocr_pages = 0
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001 — page-level failure
                raise ProcessingError(f"PDF page {i} could not be parsed: {exc.__class__.__name__}") from exc

            # Phase 1: a page with (almost) no text layer is a scan —
            # OCR it. Never let a scanned page silently become nothing.
            ocr_meta = None
            if len(text.strip()) < _MIN_PAGE_TEXT_CHARS:
                if settings.ocr_enabled:
                    ocr_text = _ocr_page(stream, i, settings.ocr_dpi)
                    ocr_pages += 1
                    if len(ocr_text.strip()) >= len(text.strip()):
                        text = ocr_text
                        from ..pipeline import ocr as _ocr
                        ocr_meta = {"engine": "tesseract",
                                    "languages": _ocr.preferred_languages()}
                elif not text.strip():
                    raise ProcessingError(
                        f"PDF page {i} is a scan and OCR is disabled "
                        "(OCR_ENABLED=false) — no text could be extracted.")

            pages.append({"page": i, "chars": len(text),
                          "text_head": text[:400], "text": text[:8000],
                          **({"ocr": ocr_meta} if ocr_meta else {})})
            total += len(text)
            if total > max_chars * 2:
                break
        if not pages:
            raise ProcessingError("PDF contains no pages.")
        if not any(p["chars"] > 0 for p in pages):
            raise ProcessingError(
                "No text could be extracted from this PDF — the pages are "
                "scans and OCR found no readable text (blank or too low "
                "quality).")
        return DocumentContent(
            document_id=doc_id, kind="pdf",
            raw_text="\n\n".join(p["text"] for p in pages)[:max_chars],
            pages=pages,
            ocr_pages=ocr_pages,
        )
    except ProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001 — corrupt / encrypted / invalid PDF
        raise ProcessingError(f"PDF could not be parsed: {exc.__class__.__name__}") from exc


def _read_image(doc_id: int, stream: io.BytesIO, max_chars: int) -> DocumentContent:
    """OCR an image upload (phase 1). Fails honestly when OCR is missing
    or reads nothing."""
    from ..pipeline import ocr as pipeline_ocr

    caps = pipeline_ocr.capabilities()
    if not caps["available"]:
        raise ProcessingError(
            "This file is a scanned image and OCR is unavailable on this "
            "server (tesseract is not installed). Install 'tesseract-ocr' "
            "to process scanned documents.")
    data = stream.read()
    result = pipeline_ocr.ocr_bytes(data, label=f"document-{doc_id}")
    if not result.ok:
        raise ProcessingError(f"OCR failed on the uploaded image: {result.error}")
    if not result.text.strip():
        raise ProcessingError(
            "OCR could not find readable text in this image (blank or too "
            "low quality).")
    pages = [{"page": 1, "chars": len(result.text), "text_head": result.text[:400],
              "text": result.text[:8000],
              "ocr": {"engine": "tesseract",
                      "languages": result.languages,
                      "confidence": result.mean_confidence}}]
    return DocumentContent(
        document_id=doc_id, kind="image",
        raw_text=result.text[:max_chars],
        pages=pages,
        ocr_pages=1,
    )


def _read_txt(doc_id: int, stream: io.BytesIO, max_chars: int) -> DocumentContent:
    try:
        raw = stream.read(max_chars * 2)
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProcessingError("Text file is not valid UTF-8.") from exc
    lines = [(i, line.rstrip("\n")) for i, line in enumerate(text.splitlines(), start=1)]
    return DocumentContent(
        document_id=doc_id, kind="txt", raw_text=text[:max_chars], lines=lines,
    )


def _read_csv(doc_id: int, stream: io.BytesIO, max_chars: int) -> DocumentContent:
    settings = get_settings()
    try:
        raw = stream.read(max_chars * 4)
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProcessingError("CSV file is not valid UTF-8.") from exc

    try:
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames or []
        if not columns or not any((c or "").strip() for c in columns):
            raise ProcessingError("CSV has no header row.")
        rows: list[tuple[int, dict]] = []
        truncated = False
        for i, row in enumerate(reader, start=1):
            if i > settings.extraction_max_rows:
                truncated = True
                break
            clean = {k: (v or "")[:500] for k, v in row.items() if k is not None}
            rows.append((i, clean))
    except csv.Error as exc:
        raise ProcessingError(f"Malformed CSV: {exc}") from exc

    stats: dict = {"rows": len(rows), "columns": len(columns)}
    if truncated:
        stats["warning"] = (f"Only the first {settings.extraction_max_rows} rows were processed.")
    return DocumentContent(
        document_id=doc_id, kind="csv", raw_text=text[:max_chars],
        csv_columns=list(columns), csv_rows=rows,
    )
