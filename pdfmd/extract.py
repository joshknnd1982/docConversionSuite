"""Text extraction layer for pdfmd.

This module provides a single public function `extract_pages()` that returns a
list of `PageText` objects for the given PDF. It supports three modes:

- Native (PyMuPDF): fast, faithful when the PDF contains real text.
- OCR via Tesseract (optional): render each page → run pytesseract.
- OCR via OCRmyPDF (optional): pre-process the whole PDF with `ocrmypdf`, then
  run the native extractor on the OCR'ed PDF. Useful for scanned PDFs while
  preserving layout and selectable text.

The chosen path is controlled by `Options.ocr_mode`:
  "off" | "auto" | "tesseract" | "ocrmypdf".
When set to "auto", a quick probe examines the first few pages and switches to
OCR if the doc appears scanned.

The module also contains helper functions for OCR probing, Tesseract/ocrmypdf
availability checks, and a small wrapper around temporary files.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional

try:
    try:  # PyMuPDF >= 1.24.3 prefers this name (no deprecation warning)
        import pymupdf as fitz  # type: ignore
    except ImportError:
        import fitz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fitz = None  # type: ignore

try:
    import pytesseract  # type: ignore
    _HAS_TESS = True
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore
    _HAS_TESS = False

try:
    from PIL import Image  # type: ignore
    _HAS_PIL = True
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    _HAS_PIL = False

from .models import PageText, Options
from .utils import log


# ---------------------- Secure PDF open helpers -----------------------


def _open_pdf_with_password(pdf_path: str, pdf_password: Optional[str]):
    """Open a PDF with optional password using PyMuPDF.

    This helper centralizes password handling so that:

    * We never log or persist the password.
    * We raise clear, consistent errors for CLI / GUI to react to.
    * We avoid keeping the password around longer than needed.
    """
    if fitz is None:  # pragma: no cover - guarded earlier
        raise RuntimeError("PyMuPDF (fitz) is not installed. Install with: pip install pymupdf")

    # Open the document first; PyMuPDF will tell us if a password is needed.
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:  # pragma: no cover - passthrough, handled by caller
        raise e

    # If the document is encrypted and still needs a password, authenticate.
    needs_pass = bool(getattr(doc, "needs_pass", False))
    if needs_pass:
        if not pdf_password:
            doc.close()
            # Message is intentionally simple so other layers can pattern match.
            raise RuntimeError("Password required to open this PDF.")
        try:
            ok = bool(doc.authenticate(pdf_password))
        except Exception:
            doc.close()
            raise RuntimeError("Incorrect PDF password or cannot decrypt.")
        if not ok:
            doc.close()
            raise RuntimeError("Incorrect PDF password or cannot decrypt.")

    return doc


def _prepare_ocr_input(pdf_path: str, pdf_password: Optional[str], tmpdir: str) -> str:
    """Return the path that OCRmyPDF should read from.

    For unencrypted PDFs this is simply *pdf_path*.

    For password-protected PDFs, we do not pass the password to external
    commands (which could expose it via process listings). Instead we:

    1. Open and decrypt the PDF in-process using PyMuPDF.
    2. Write a temporary, decrypted copy inside *tmpdir*.
    3. Return the path to that temporary copy for OCRmyPDF to process.

    The temporary file lives only in the OS temp directory and is deleted
    together with *tmpdir* once processing completes.
    """
    # First try opening the document; this will also validate the password if needed.
    doc = _open_pdf_with_password(pdf_path, pdf_password)
    try:
        needs_pass = bool(getattr(doc, "needs_pass", False))
        # If no password was required (unencrypted or already openable), we can
        # safely let OCRmyPDF read the original file directly.
        if not needs_pass:
            return pdf_path

        # The document required a password and has now been authenticated.
        # Create a decrypted temporary copy for OCR.
        tmp_plain = os.path.join(tmpdir, "decrypted_input.pdf")
        out_doc = fitz.open()  # new empty document
        try:
            out_doc.insert_pdf(doc)
            out_doc.save(tmp_plain)
        finally:
            out_doc.close()
        return tmp_plain
    finally:
        doc.close()


# --------------------------- Public entry point ---------------------------

DefProgress = Optional[Callable[[int, int], None]]


def extract_pages(
    pdf_path: str,
    options: Options,
    progress_cb: DefProgress = None,
    pdf_password: Optional[str] = None,
) -> List[PageText]:
    """Extract pages as PageText according to OCR mode and preview flag.

    progress_cb, if provided, is called as (done_pages, total_pages).
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is not installed. Install with: pip install pymupdf")

    mode = (options.ocr_mode or "off").lower()

    if mode == "off":
        return _extract_native(pdf_path, options, progress_cb, pdf_password)

    if mode == "auto":
        if _needs_ocr_probe(pdf_path, pdf_password):
            log("[extract] Auto: scanned PDF detected.")
            if _HAS_TESS and _HAS_PIL and _tesseract_available():
                log("[extract] Using Tesseract OCR...")
                return _extract_tesseract(pdf_path, options, progress_cb, pdf_password)
            elif _which("ocrmypdf") and _tesseract_available():
                log("[extract] Using OCRmyPDF...")
                return _extract_ocrmypdf_then_native(pdf_path, options, progress_cb, pdf_password)
            else:
                log("[extract] WARNING: Scanned PDF detected but no OCR available!")
                log("[extract] Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki")
                log("[extract] Then run: pip install pytesseract pillow")
                log("[extract] Falling back to native extraction (may produce poor results).")
                return _extract_native(pdf_path, options, progress_cb, pdf_password)
        # Otherwise, native path
        return _extract_native(pdf_path, options, progress_cb, pdf_password)

    if mode == "tesseract":
        if not (_HAS_TESS and _HAS_PIL):
            raise RuntimeError(
                "OCR mode 'tesseract' selected but pytesseract/Pillow are not available.\n"
                "Install with: pip install pytesseract pillow\n"
                "And install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        if not _tesseract_available():
            raise RuntimeError(
                "OCR mode 'tesseract' selected but Tesseract binary is not available on PATH.\n"
                "Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        return _extract_tesseract(pdf_path, options, progress_cb, pdf_password)

    if mode == "ocrmypdf":
        if not _tesseract_available():
            raise RuntimeError(
                "OCR mode 'ocrmypdf' selected but Tesseract is not available on PATH.\n"
                "Install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        if not _which("ocrmypdf"):
            raise RuntimeError(
                "OCR mode 'ocrmypdf' selected but ocrmypdf is not installed.\n"
                "Install with: pip install ocrmypdf"
            )
        return _extract_ocrmypdf_then_native(pdf_path, options, progress_cb, pdf_password)

    raise ValueError(f"Unknown ocr_mode: {mode!r}")


# ------------------------ Native PyMuPDF extraction ----------------------


def _extract_native(
    pdf_path: str,
    options: Options,
    progress_cb: DefProgress,
    pdf_password: Optional[str] = None,
) -> List[PageText]:
    """Extract text using PyMuPDF's native text extraction."""
    doc = _open_pdf_with_password(pdf_path, pdf_password)
    try:
        total = doc.page_count

        if total == 0:
            raise ValueError("PDF has no pages")

        limit = total if not options.preview_only else min(3, total)
        out: List[PageText] = []

        for i in range(limit):
            page = doc.load_page(i)
            info = page.get_text("dict")
            info = _with_ruled_tables(page, info)
            out.append(PageText.from_pymupdf(info))

            if progress_cb:
                progress_cb(i + 1, total)

        return out
    finally:
        doc.close()


# ------------------------ Ruled tables (PyMuPDF) -------------------------


def _clean_cell(value: Optional[str]) -> str:
    """Table cells can't contain line breaks in Markdown; join them."""
    if not value:
        return ""
    return " ".join(part.strip() for part in str(value).splitlines() if part.strip())


def _with_ruled_tables(page, info: dict) -> dict:
    """Replace text inside ruled tables with whole-table blocks.

    PyMuPDF's table finder reads tables from the lines drawn in the PDF, so
    it keeps every row and column of bordered tables (including the header
    row and multi-line cells) that text-only heuristics tend to break up.
    The text of those cells is removed from the normal text blocks and one
    ``pdfmd_table`` block is inserted where the table starts. Pages without
    ruled tables, or older PyMuPDF versions, are returned unchanged.
    """
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return info
    try:
        import contextlib

        # PyMuPDF prints a hint about an optional add-on package; keep it out
        # of the user's console and log.
        with contextlib.redirect_stdout(io.StringIO()):
            found = finder()
        tables = list(getattr(found, "tables", []) or [])
    except Exception:
        return info
    if not tables:
        return info

    table_items = []
    for tab in tables:
        try:
            rows = tab.extract() or []
        except Exception:
            continue
        grid = [[_clean_cell(c) for c in row] for row in rows]
        grid = [row for row in grid if any(row)]
        # Header row drawn above the table's frame.
        header = getattr(tab, "header", None)
        if header is not None and getattr(header, "external", False):
            names = [_clean_cell(n) for n in (getattr(header, "names", None) or [])]
            if any(names):
                grid.insert(0, names)
        if len(grid) < 2 or max(len(r) for r in grid) < 2:
            continue  # a framed paragraph, not a table
        non_empty = sum(1 for r in grid for c in r if c)
        if non_empty < 4:
            continue
        x0, y0, x1, y1 = tab.bbox
        table_items.append(((x0 - 1, y0 - 1, x1 + 1, y1 + 1), grid))
    if not table_items:
        return info

    def inside(bbox) -> Optional[int]:
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        for k, (tb, _) in enumerate(table_items):
            if tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3]:
                return k
        return None

    new_blocks = []
    placed = set()
    sizes: dict = {}
    for b in info.get("blocks", []) or []:
        if "lines" not in b:
            new_blocks.append(b)
            continue
        kept_lines = []
        hit = None
        for ln in b.get("lines", []) or []:
            k = inside(ln.get("bbox", (0, 0, 0, 0)))
            if k is None:
                kept_lines.append(ln)
                continue
            hit = k
            for sp in ln.get("spans", []) or []:
                if sp.get("size"):
                    sizes.setdefault(k, float(sp["size"]))
        if hit is not None and hit not in placed:
            # Text before the table in this block stays before it.
            before = [ln for ln in kept_lines if ln.get("bbox", (0, 0, 0, 0))[1] < table_items[hit][0][1]]
            after = [ln for ln in kept_lines if ln not in before]
            if before:
                new_blocks.append({**b, "lines": before})
            new_blocks.append({"type": "pdfmd_table", "grid": table_items[hit][1],
                               "bbox": table_items[hit][0], "size": sizes.get(hit, 0.0)})
            placed.add(hit)
            if after:
                new_blocks.append({**b, "lines": after})
            continue
        if kept_lines:
            new_blocks.append({**b, "lines": kept_lines})
    # Tables whose cells held no extractable text lines are added at the end.
    for k, (bbox, grid) in enumerate(table_items):
        if k not in placed:
            new_blocks.append({"type": "pdfmd_table", "grid": grid, "bbox": bbox, "size": 0.0})
    return {**info, "blocks": new_blocks}


# ------------------------ Tesseract-based OCR path -----------------------


def _extract_tesseract(
    pdf_path: str,
    options: Options,
    progress_cb: DefProgress,
    pdf_password: Optional[str] = None,
) -> List[PageText]:
    """Render each page to an image, feed into Tesseract, build PageText."""
    if not (_HAS_TESS and _HAS_PIL):  # pragma: no cover - guarded earlier
        raise RuntimeError("Tesseract/Pillow not available")

    doc = _open_pdf_with_password(pdf_path, pdf_password)
    try:
        total = doc.page_count

        if total == 0:
            raise ValueError("PDF has no pages")

        limit = total if not options.preview_only else min(3, total)
        out: List[PageText] = []

        # Use 200 DPI for preview mode to save memory/time, 300 for full quality
        dpi = 200 if options.preview_only else 300

        for i in range(limit):
            page = doc.load_page(i)

            # Render at higher DPI for better OCR
            pix = page.get_pixmap(dpi=dpi)
            if not hasattr(pix, "tobytes"):
                raise RuntimeError("Unexpected: pixmap missing tobytes()")

            png_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(png_bytes))

            # Let pytesseract detect layout at word/line level
            data = pytesseract.image_to_data(
                img,
                lang=options.ocr_lang or "eng",
                output_type=pytesseract.Output.DICT,
            )
            out.append(PageText.from_tesseract_data(data))

            if progress_cb:
                progress_cb(i + 1, total)

        return out
    finally:
        doc.close()


# ------------------------ OCRmyPDF + native path -------------------------


def _extract_ocrmypdf_then_native(
    pdf_path: str,
    options: Options,
    progress_cb: DefProgress,
    pdf_password: Optional[str] = None,
) -> List[PageText]:
    """Run OCRmyPDF on a temp copy, then extract using _extract_native.

    This allows combining OCR with PyMuPDF's excellent layout-preserving
    extraction on the OCR'ed output.
    """
    ocrmypdf_bin = _which("ocrmypdf")
    if not ocrmypdf_bin:
        raise RuntimeError("ocrmypdf not found on PATH")

    # Create a temporary directory to hold the OCR'ed PDF
    with tempfile.TemporaryDirectory(prefix="pdfmd_") as tmp:
        out_pdf = os.path.join(tmp, "ocr.pdf")

        # Decide which file OCRmyPDF should read from (may create a decrypted temp copy).
        input_for_ocr = _prepare_ocr_input(pdf_path, pdf_password, tmp)

        # Build command: --force-ocr ensures OCR even if text exists
        # Removed --skip-text as it conflicts with --force-ocr
        lang = options.ocr_lang or "eng"
        cmd = [ocrmypdf_bin, "--force-ocr", "-l", lang, input_for_ocr, out_pdf]

        try:
            log("[extract] Running OCRmyPDF (this may take a while)...")
            # Set timeout to 10 minutes (600 seconds) to prevent hanging
            # Capture output for progress logging
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600,
            )
            # Log summary (avoid spamming full output)
            if result.stdout:
                log("[extract] ocrmypdf output (truncated):")
                log("[extract] " + result.stdout.decode(errors="ignore").splitlines()[0])
            if result.stderr:
                first_err_line = result.stderr.decode(errors="ignore").splitlines()[0]
                log("[extract] ocrmypdf stderr (first line):")
                log("[extract] " + first_err_line)
        except subprocess.TimeoutExpired:
            log("[extract] ERROR: ocrmypdf timed out after 10 minutes.")
            raise
        except subprocess.CalledProcessError as e:
            log(f"[extract] ERROR: ocrmypdf failed with return code {e.returncode}.")
            if e.stdout:
                log("[extract] stdout (truncated):")
                log("[extract] " + e.stdout.decode(errors="ignore").splitlines()[0])
            if e.stderr:
                log("[extract] stderr (truncated):")
                log("[extract] " + e.stderr.decode(errors="ignore").splitlines()[0])
            raise

        # Now that we have OCR'ed PDF, run native extraction on it
        # The OCR output is never password protected.
        return _extract_native(out_pdf, options, progress_cb, None)


# ----------------------- OCR probe and helpers ----------------------------


def _needs_ocr_probe(
    pdf_path: str,
    pdf_password: Optional[str] = None,
    pages_to_check: int = 3,
) -> bool:
    """Heuristic: determine if PDF is likely scanned and needs OCR.

    We consider a PDF "scanned" if:
      1. Very little extractable text (< ~100 chars) on first pages
      2. Presence of large images covering most of the page area
      3. Low text density relative to page size
    """
    try:
        doc = _open_pdf_with_password(pdf_path, pdf_password)
    except Exception:
        return False

    try:
        if doc.page_count == 0:
            return False

        total = min(pages_to_check, doc.page_count)
        text_chars = 0
        scanned_indicators = 0

        for i in range(total):
            page = doc.load_page(i)
            text = page.get_text("text").strip()
            text_chars += len(text)

            # Get page dimensions
            rect = page.rect
            page_area = rect.width * rect.height

            # Check for images
            images = page.get_images(full=True)
            if images:
                for img_info in images:
                    try:
                        xref = img_info[0]
                        pix = fitz.Pixmap(doc, xref)
                        img_area = pix.width * pix.height
                        pix = None  # free resources
                        # If image covers a large portion of the page, count it
                        if img_area > 0.3 * page_area:
                            scanned_indicators += 1
                    except Exception:
                        continue

        # Very low text and presence of large images suggests scanned
        if text_chars < 100 and scanned_indicators > 0:
            return True

        # Also treat very low text density as scanned
        avg_text_per_page = text_chars / max(total, 1)
        if avg_text_per_page < 50 and scanned_indicators > 0:
            return True

        return False
    finally:
        doc.close()


def _tesseract_available() -> bool:
    """Check if Tesseract is available on PATH.

    We prefer using pytesseract for detection because it is already imported
    when OCR is needed, but we also verify the underlying binary is callable.
    """
    if pytesseract is None:
        return False

    # Find Tesseract even when it isn't on PATH (standard install folders,
    # registry), and point pytesseract at it.
    try:
        from .tesseract_support import configure

        cmd = configure() or "tesseract"
    except Exception:
        cmd = getattr(getattr(pytesseract, "pytesseract", None), "tesseract_cmd", "tesseract")

    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=5,
            # No console window flashing up from the desktop app.
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return result.returncode == 0
    except Exception:
        return False


def _which(cmd: str) -> Optional[str]:
    """Portable `which` implementation.

    Uses shutil.which when available, falls back to a simple PATH scan.
    """
    path = shutil.which(cmd)
    if path:
        return path

    # Fallback scan
    exts = [""]  # On Windows PATHEXT is used by shutil.which; we emulate minimal behaviour.
    if os.name == "nt":
        pathext = os.environ.get("PATHEXT", "")
        exts.extend(ext.strip() for ext in pathext.split(os.pathsep) if ext.strip())

    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(p, cmd)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

        # On Windows, try with each extension
        if os.name == "nt":
            base = candidate
            for e in exts:
                cand2 = base + e
                if os.path.isfile(cand2) and os.access(cand2, os.X_OK):
                    return cand2

    return None


__all__ = [
    "extract_pages",
]