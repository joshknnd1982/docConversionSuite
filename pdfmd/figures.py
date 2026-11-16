"""Pictures and charts in PDFs, described by the local vision model.

Finding figures (during extraction):

* Embedded pictures (photos, scanned charts, maps, logos) are found with
  PyMuPDF's image list. Tiny pictures (icons, bullets), pictures repeated on
  most pages (logos in a header) and pictures covered by a text layer (pages
  of a searchable scan) are left alone.
* Charts drawn with vector graphics (most charts exported from Excel,
  matplotlib, R and the like) are found by clustering the page's drawings.
  Their axis labels and legends would otherwise come out as stray lines of
  text, so they are kept with the figure and only put back if the figure
  isn't described.
* On scanned pages, regions that Tesseract finds no text in (photos,
  illustrations) become figures too.

Each figure is rendered exactly as it appears on the page and placed in the
text flow where it appears.

Describing figures (``describe_figures``):

Pictures that are mostly text are left to OCR. The rest are described by the
vision model. With "Export images" on, the description becomes the image's
alternative text; otherwise the description is written as a block quote,
because the output has no picture to attach alternative text to.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

try:
    try:
        import pymupdf as fitz  # type: ignore
    except ImportError:
        import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

from .models import Block, Figure, Options, PageText

Logger = Optional[Callable[[str], None]]

MAX_RENDER_SIDE = 1280          # pixels; the engine scales down further
MIN_SIDE_PT = 36                # smaller pictures are icons or bullets
MIN_AREA_FRACTION = 0.01        # of the page


# ---------------------------------------------------------------------------
# Finding figures in native PDF pages
# ---------------------------------------------------------------------------


def repeated_images(doc, page_count: int) -> Set[int]:
    """Images (xrefs) shown on most pages: logos and page decorations."""
    if page_count < 3:
        return set()
    counts: Counter = Counter()
    for pno in range(page_count):
        try:
            for img in doc.load_page(pno).get_images(full=False):
                counts[img[0]] += 1
        except Exception:
            continue
    return {x for x, n in counts.items() if n >= 3 and n >= 0.5 * page_count}


def _words_in(rect, info: dict) -> int:
    n = 0
    for b in info.get("blocks", []) or []:
        for ln in b.get("lines", []) or []:
            x0, y0, x1, y1 = ln.get("bbox", (0, 0, 0, 0))
            if rect.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)):
                n += sum(len(sp.get("text", "").split()) for sp in ln.get("spans", []) or [])
    return n


def _chart_like(drawings: List[dict]) -> bool:
    """True if a cluster of drawings looks like a chart or diagram.

    Tables and forms are only straight horizontal and vertical strokes;
    charts and diagrams have curves, slanted lines, or areas filled with
    several colours.
    """
    if len(drawings) < 4:
        return False
    fills = set()
    curves = slanted = 0
    for d in drawings:
        fill = d.get("fill")
        if fill and not all(c > 0.93 for c in fill):
            fills.add(tuple(round(c, 2) for c in fill))
        for item in d.get("items", []) or []:
            op = item[0]
            if op == "c":
                curves += 1
            elif op == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) > 1 and abs(p1.y - p2.y) > 1:
                    slanted += 1
    return curves >= 2 or slanted >= 2 or len(fills) >= 2 or (len(fills) == 1 and len(drawings) >= 8)


def _with_tick_labels(rect, info: dict, reach: float = 28.0):
    """Grow a drawn chart's area over short labels just outside it.

    Axis tick labels ("2021", "50 %") are usually drawn just outside the
    chart's lines. Titles and captions (longer lines) stay in the text.
    """
    grown = fitz.Rect(rect)
    zone = fitz.Rect(rect) + (-reach, -reach, reach, reach)
    for b in info.get("blocks", []) or []:
        for ln in b.get("lines", []) or []:
            box = fitz.Rect(ln.get("bbox", (0, 0, 0, 0)))
            text = "".join(sp.get("text", "") for sp in ln.get("spans", []) or []).strip()
            if not text or len(text) > 14 or len(text.split()) > 2:
                continue
            if zone.contains(box) and not rect.contains(box):
                grown |= box
    return grown + (-2, -2, 2, 2)


def _render(page, rect) -> bytes:
    zoom = max(1.0, min(4.0, MAX_RENDER_SIDE / max(rect.width, rect.height, 1)))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
    return pix.tobytes("png")


def _context(rect, info: dict) -> str:
    """Text right above or below the figure (often its caption)."""
    near: List[str] = []
    for b in info.get("blocks", []) or []:
        for ln in b.get("lines", []) or []:
            x0, y0, x1, y1 = ln.get("bbox", (0, 0, 0, 0))
            if x1 < rect.x0 or x0 > rect.x1:
                continue
            if 0 <= y0 - rect.y1 <= 36 or 0 <= rect.y0 - y1 <= 24:
                text = "".join(sp.get("text", "") for sp in ln.get("spans", []) or []).strip()
                if text:
                    near.append(text)
    return " ".join(near)[:300]


def _merge(cands: List[list]) -> List[list]:
    """Merge overlapping candidates (tiled pictures, charts with pictures)."""
    merged = True
    while merged:
        merged = False
        out: List[list] = []
        for c in cands:
            for o in out:
                grown = fitz.Rect(o[0]) + (-2, -2, 2, 2)
                if grown.intersects(c[0]):
                    o[0] = fitz.Rect(o[0]) | c[0]
                    o[1] = "vector" if "vector" in (o[1], c[1]) else "raster"
                    o[2] = o[2] or c[2]
                    merged = True
                    break
            else:
                out.append(list(c))
        cands = out
    return cands


def add_figures(page, info: dict, pno: int, repeated: Set[int]) -> dict:
    """Add ``pdfmd_figure`` blocks for the pictures and charts on a page."""
    if fitz is None:
        return info
    page_rect = page.rect
    parea = max(1.0, page_rect.get_area())
    cands: List[list] = []

    try:
        images = page.get_image_info(xrefs=True)
    except Exception:
        images = []
    for im in images:
        r = fitz.Rect(im.get("bbox")) & page_rect
        if r.is_empty or r.width < MIN_SIDE_PT or r.height < MIN_SIDE_PT:
            continue
        if r.get_area() < MIN_AREA_FRACTION * parea:
            continue
        xref = int(im.get("xref") or 0)
        if xref and xref in repeated:
            continue
        if _words_in(r, info) > 40:
            continue  # text drawn over it: a background or a searchable scan
        cands.append([r, "raster", xref])

    tables = [fitz.Rect(b["bbox"]) for b in info.get("blocks", []) or []
              if b.get("type") == "pdfmd_table" and b.get("bbox")]
    try:
        clusters = page.cluster_drawings()
        drawings = page.get_drawings() if clusters else []
    except Exception:
        clusters, drawings = [], []
    for r in clusters:
        r = fitz.Rect(r) & page_rect
        if r.is_empty or r.width < 72 or r.height < 54:
            continue
        if not (0.03 * parea <= r.get_area() <= 0.9 * parea):
            continue
        if any((r & t).get_area() > 0.5 * r.get_area() for t in tables):
            continue
        grown = r + (-1, -1, 1, 1)
        inside = [d for d in drawings if grown.contains(fitz.Rect(d.get("rect")))]
        if not _chart_like(inside):
            continue
        if _words_in(r, info) > 120:
            continue  # a framed text box, not a chart
        cands.append([_with_tick_labels(r, info), "vector", 0])

    if not cands:
        return info
    cands = _merge(cands)

    blocks = list(info.get("blocks", []) or [])
    figure_blocks = []
    for r, kind, xref in cands:
        labels = []
        if kind == "vector":
            # Axis labels and legends belong to the chart.
            kept = []
            for b in blocks:
                if "lines" not in b:
                    kept.append(b)
                    continue
                inner, outer = [], []
                for ln in b.get("lines", []) or []:
                    x0, y0, x1, y1 = ln.get("bbox", (0, 0, 0, 0))
                    (inner if r.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)) else outer).append(ln)
                if inner:
                    labels.append({**b, "lines": inner})
                if outer:
                    kept.append({**b, "lines": outer})
                elif not inner:
                    kept.append(b)
            blocks = kept
        try:
            png = _render(page, r)
        except Exception:
            continue
        fig = Figure(page=pno, bbox=tuple(r), kind=kind, xref=xref, png=png,
                     context=_context(r, info), native_words=_words_in(r, info))
        figure_blocks.append({"type": "pdfmd_figure", "bbox": tuple(r), "figure": fig,
                              "labels": labels})

    # Place each figure before the first block that starts below its top.
    for fb in sorted(figure_blocks, key=lambda f: f["bbox"][1]):
        top, x0, x1 = fb["bbox"][1], fb["bbox"][0], fb["bbox"][2]
        pos = None
        for i, b in enumerate(blocks):
            bb = b.get("bbox")
            if not bb or b.get("type") == "pdfmd_figure":
                continue
            if bb[1] >= top - 1 and bb[2] > x0 and bb[0] < x1:
                pos = i
                break
        if pos is None:
            for i, b in enumerate(blocks):
                bb = b.get("bbox")
                if bb and b.get("type") != "pdfmd_figure" and bb[1] >= top - 1:
                    pos = i
                    break
        if pos is None:
            blocks.append(fb)
        else:
            blocks.insert(pos, fb)
    return {**info, "blocks": blocks}


# ---------------------------------------------------------------------------
# Pictures on scanned pages
# ---------------------------------------------------------------------------


def scanned_picture_regions(data: Dict[str, list], width: int, height: int) -> List[tuple]:
    """Regions of a scanned page that Tesseract found no words in.

    Tesseract's layout analysis lists every block, including picture
    blocks, which contain no words.
    """
    n = len(data.get("level", []))
    words_by_block: Counter = Counter()
    sure_words: Counter = Counter()    # words read with confidence: real text
    blocks = {}
    for i in range(n):
        lvl = int(data["level"][i])
        bno = int(data["block_num"][i])
        if lvl == 2:
            blocks[bno] = (int(data["left"][i]), int(data["top"][i]),
                           int(data["width"][i]), int(data["height"][i]))
        elif lvl == 5 and (data["text"][i] or "").strip():
            words_by_block[bno] += 1
            try:
                conf = float(data.get("conf", [0] * n)[i])
            except (TypeError, ValueError):
                conf = 0.0
            if conf >= 60 and len(re.sub(r"\W", "", str(data["text"][i]))) >= 2:
                sure_words[bno] += 1
    page_area = float(max(1, width * height))
    regions = []
    for bno, (x, y, w, h) in blocks.items():
        # Pictures have no words, or only a few misreadings of the picture
        # (low confidence). Large text such as a title or a stamp is text.
        if words_by_block.get(bno, 0) > 3 or sure_words.get(bno, 0) > 0:
            continue
        if w < 0.12 * width or h < 0.08 * height:
            continue
        if not (0.03 <= (w * h) / page_area <= 0.9):
            continue
        regions.append((x, y, x + w, y + h))
    return regions


def add_scanned_figures(page_text: PageText, data: Dict[str, list], image, pno: int) -> PageText:
    """Insert figures for picture regions of a scanned page image (PIL)."""
    import io

    w, h = image.size
    regions = scanned_picture_regions(data, w, h)
    if not regions:
        return page_text
    # Top of each text block, in the order PageText.from_tesseract_data built them.
    tops: Dict[int, int] = {}
    order: List[int] = []
    for i in range(len(data.get("text", []))):
        if not (data["text"][i] or "").strip():
            continue
        bno = int(data["block_num"][i])
        top = int(data["top"][i])
        if bno not in tops:
            order.append(bno)
            tops[bno] = top
        else:
            tops[bno] = min(tops[bno], top)
    order.sort(key=lambda b: (b, tops[b]))
    block_tops = [tops[b] for b in order]
    blocks = list(page_text.blocks)
    for (x0, y0, x1, y1) in sorted(regions, key=lambda r: r[1], reverse=True):
        crop = image.crop((x0, y0, x1, y1))
        if max(crop.size) > MAX_RENDER_SIDE:
            f = MAX_RENDER_SIDE / float(max(crop.size))
            crop = crop.resize((int(crop.size[0] * f), int(crop.size[1] * f)))
        buf = io.BytesIO()
        crop.convert("RGB").save(buf, format="PNG")
        fig = Figure(page=pno, bbox=(x0, y0, x1, y1), kind="raster", png=buf.getvalue())
        pos = len(blocks)
        for i, top in enumerate(block_tops[: len(blocks)]):
            if top >= y0:
                pos = i
                break
        blocks.insert(pos, Block(figure=fig))
        block_tops.insert(pos, y0)
    return PageText(blocks=blocks)


# ---------------------------------------------------------------------------
# Describing figures
# ---------------------------------------------------------------------------


def iter_figures(pages: List[PageText]):
    for page in pages:
        for blk in page.blocks:
            if blk.figure is not None:
                yield blk.figure


def describe_figures(
    pages: List[PageText],
    options: Options,
    output_md: str,
    log_cb: Logger = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> int:
    """Describe every figure; export them when images are exported.

    Returns the number of figures described. ``log_cb`` may raise to cancel.
    """
    from . import vision

    figs = list(iter_figures(pages))
    if not figs:
        return 0
    log = log_cb or (lambda m: None)
    settings = vision.VisionSettings(enabled=True, device=options.vision_device,
                                     model_id=options.vision_model, lang=options.ocr_lang)
    assets_dir: Optional[Path] = None
    if options.export_images:
        out = Path(output_md)
        assets_dir = out.with_name(out.stem + "_assets")
        assets_dir.mkdir(parents=True, exist_ok=True)

    log(f"[vision] {len(figs)} picture{'s' if len(figs) != 1 else ''} or chart"
        f"{'s' if len(figs) != 1 else ''} found.")
    engine = None
    try:
        engine = vision.get_engine(settings, log_cb=log)
    except vision.VisionError as e:
        log(f"[vision] Picture descriptions skipped: {e}")

    described = 0
    can_ocr = _can_ocr()
    per_page: Counter = Counter()
    for n, fig in enumerate(figs, start=1):
        per_page[fig.page] += 1
        if assets_dir is not None:
            name = f"figure_{fig.page + 1:03d}_{per_page[fig.page]:02d}.png"
            try:
                (assets_dir / name).write_bytes(fig.png)
                fig.asset = assets_dir.name + "/" + name
            except Exception as e:  # noqa: BLE001
                log(f"[vision] Could not save {name}: {e}")
        if engine is None:
            fig.status = "skipped"
            continue
        where = f"page {fig.page + 1}"
        if fig.kind == "raster" and vision.is_mostly_text(fig.png, options.ocr_lang):
            _use_ocr(fig, options.ocr_lang)
            log(f"[vision] Picture {n} of {len(figs)} ({where}) is mostly text; "
                + ("its text was recognised." if fig.status == "ocr" else "skipped."))
            continue
        try:
            d = engine.describe(fig.png, "document", options.ocr_lang, fig.context,
                                ask_text=fig.kind == "raster" and not can_ocr)
        except Exception as e:  # noqa: BLE001
            fig.status = "failed"
            log(f"[vision] Picture {n} of {len(figs)} ({where}) could not be described: {e}")
            continue
        if d.kind == "picture":
            fig.alt, fig.status = d.text, "described"
            described += 1
            log(f"[vision] Picture {n} of {len(figs)} ({where}, {d.seconds:.1f} s): {d.text}")
        elif d.kind == "text" and fig.kind == "raster":
            _use_ocr(fig, options.ocr_lang)
            log(f"[vision] Picture {n} of {len(figs)} ({where}) is text; "
                + ("its text was recognised." if fig.status == "ocr" else "skipped."))
        else:
            fig.status = d.kind
            log(f"[vision] Picture {n} of {len(figs)} ({where}) is {d.kind}; no description needed.")
        if progress_cb:
            progress_cb(n, len(figs))
    return described


def _can_ocr() -> bool:
    try:
        import pytesseract  # type: ignore  # noqa: F401

        from . import tesseract_support as ts

        return bool(ts.configure())
    except Exception:
        return False


def _use_ocr(fig: Figure, lang: str) -> None:
    """A picture of text: give it its recognised text, if Tesseract can read it."""
    from .docimages import ocr_text

    text = ocr_text(fig.png, lang)
    if text:
        fig.alt, fig.status = text, "ocr"
    else:
        fig.status = "text"


# ---------------------------------------------------------------------------
# Markdown for figures
# ---------------------------------------------------------------------------

CAPTION_LABEL = "Image description"
OCR_LABEL = "Text in image"


def alt_text(text: str) -> str:
    """Text that is safe inside Markdown image brackets."""
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.replace("\\", "\\\\").replace("[", "(").replace("]", ")")


def caption_block(text: str, label: str = CAPTION_LABEL) -> str:
    """A block-quoted description for outputs without the picture."""
    t = re.sub(r"\s+", " ", text or "").strip()
    for ch in ("\\", "*", "_", "`"):
        t = t.replace(ch, "\\" + ch)
    return f"> **{label}:** {t}"


def figure_markdown(fig: Figure) -> List[str]:
    """Markdown lines for a figure, without its label text."""
    if fig.status in ("described", "ocr"):
        if fig.asset:
            return [f"![{alt_text(fig.alt)}]({fig.asset})", ""]
        return [caption_block(fig.alt, CAPTION_LABEL if fig.status == "described" else OCR_LABEL), ""]
    if fig.asset:
        alt = "" if fig.status == "decorative" else f"Image from page {fig.page + 1}"
        return [f"![{alt}]({fig.asset})", ""]
    return []


__all__ = [
    "repeated_images", "add_figures", "add_scanned_figures", "scanned_picture_regions",
    "describe_figures", "figure_markdown", "alt_text", "caption_block", "CAPTION_LABEL",
]
