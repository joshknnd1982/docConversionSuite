"""Picture descriptions for every document pandoc reads.

Word, ODT, EPUB, PowerPoint, HTML, Markdown, LaTeX and the other pandoc
input formats are read into pandoc's document tree (JSON). Every picture
without useful alternative text is described by the local vision model:

* if the output format can hold pictures (Word, EPUB, HTML, ODT,
  PowerPoint, PDF, Markdown, LaTeX and most others), the description
  becomes the picture's alternative text;
* if it can't (plain text, man pages, spreadsheets and other text-only
  formats), each picture is replaced by a block quote with its description.

Alternative text an author already wrote is kept. Pictures that are mostly
text get the recognised text instead of a description. Remote pictures
(http/https) are not downloaded.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote

Logger = Optional[Callable[[str], None]]

# Output formats that can't show pictures.
TEXT_ONLY_OUTPUTS = {
    "plain", "ansi", "man", "mdoc", "ms", "texinfo", "csv", "tsv", "xlsx", "bibtex",
    "biblatex", "csljson", "opml", "vimdoc", "haddock", "pod", "native", "json",
}

BLOCK_TYPES = {"Plain", "Para", "LineBlock", "CodeBlock", "RawBlock", "BlockQuote",
               "OrderedList", "BulletList", "DefinitionList", "Header", "HorizontalRule",
               "Table", "Figure", "Div"}

_GENERIC_ALT = re.compile(
    r"^(|image|img|picture|pic|figure|fig|photo|graphic|graph|chart|diagram|screenshot|"
    r"untitled|placeholder|alt|a picture containing.*)\s*[-_ ]?\d*\.?$", re.I)

DESCRIPTION_LABEL = "Image description"
OCR_LABEL = "Text in image"


def is_text_only(fmt: str) -> bool:
    return re.split(r"[+-]", fmt or "", maxsplit=1)[0] in TEXT_ONLY_OUTPUTS


# ---------------------------------------------------------------------------
# Pandoc AST helpers
# ---------------------------------------------------------------------------


def stringify(node) -> str:
    out: List[str] = []

    def go(n):
        if isinstance(n, dict):
            t = n.get("t")
            if t == "Str":
                out.append(n.get("c", ""))
            elif t in ("Space", "SoftBreak", "LineBreak"):
                out.append(" ")
            elif t in ("Code", "Math"):
                out.append(str(n.get("c", ["", ""])[-1]))
            else:
                go(n.get("c"))
        elif isinstance(n, list):
            for x in n:
                go(x)

    go(node)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def to_inlines(text: str) -> List[dict]:
    out: List[dict] = []
    for i, word in enumerate(text.split()):
        if i:
            out.append({"t": "Space"})
        out.append({"t": "Str", "c": word})
    return out


def quote_block(label: str, text: str) -> dict:
    para = [{"t": "Strong", "c": to_inlines(label + ":")}, {"t": "Space"}] + to_inlines(text)
    return {"t": "BlockQuote", "c": [{"t": "Para", "c": para}]}


def needs_description(alt: str, src: str) -> bool:
    a = (alt or "").strip()
    if _GENERIC_ALT.match(a):
        return True
    name = Path(unquote(src.split("?")[0])).name
    if a and (a == name or a == Path(name).stem or re.match(r"^[\w\-. ]+\.(png|jpe?g|gif|bmp|svg|emf|wmf|tiff?|webp)$", a, re.I)):
        return True
    return len(a) < 4


def _is_block_list(node) -> bool:
    return (isinstance(node, list) and node and
            all(isinstance(x, dict) and x.get("t") in BLOCK_TYPES for x in node))


def iter_images(node):
    """Yield every Image node (dict) in the tree."""
    if isinstance(node, dict):
        if node.get("t") == "Image":
            yield node
        c = node.get("c")
        if c is not None:
            yield from iter_images(c)
        for k in ("blocks",):
            if k in node:
                yield from iter_images(node[k])
    elif isinstance(node, list):
        for x in node:
            yield from iter_images(x)


def _image_parts(img: dict) -> Tuple[list, str]:
    attr, inlines, target = img["c"]
    return inlines, target[0]


# ---------------------------------------------------------------------------
# Loading pictures
# ---------------------------------------------------------------------------


def load_image_bytes(src: str, base_dirs: List[Path]) -> Optional[bytes]:
    """Bytes of a picture that is embedded or stored locally (PNG for SVG)."""
    if src.startswith("data:"):
        m = re.match(r"data:([^;,]+)?(;base64)?,(.*)", src, re.S)
        if not m:
            return None
        payload = m.group(3)
        data = base64.b64decode(payload) if m.group(2) else unquote(payload).encode("utf-8")
        return _svg_to_png(data) if (m.group(1) or "").endswith("svg+xml") else data
    if re.match(r"^[a-z][a-z0-9+.-]*://", src, re.I) and not src.lower().startswith("file://"):
        return None  # remote: never fetched
    if src.lower().startswith("file:"):
        from urllib.request import url2pathname

        path_str = url2pathname(re.sub(r"^file:(//)?", "", src, flags=re.I))
    else:
        path_str = unquote(src)
    p0 = Path(path_str)
    candidates = [p0] if p0.is_absolute() else [d / path_str for d in base_dirs] + [p0]
    for p in candidates:
        try:
            if p.is_file():
                data = p.read_bytes()
                return _svg_to_png(data) if p.suffix.lower() in (".svg", ".svgz") else data
        except OSError:
            continue
    return None


def _svg_to_png(data: bytes) -> Optional[bytes]:
    try:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            import fitz  # type: ignore
        doc = fitz.open(stream=data, filetype="svg")
        page = doc.load_page(0)
        zoom = max(1.0, min(4.0, 1024 / max(page.rect.width, page.rect.height, 1)))
        png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
        doc.close()
        return png
    except Exception:
        return None


def ocr_text(data: bytes, lang: str) -> str:
    try:
        import pytesseract  # type: ignore

        from . import tesseract_support as ts
        from .vision import open_image

        if not ts.configure():
            return ""
        text = pytesseract.image_to_string(open_image(data), lang=lang or "eng")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


# ---------------------------------------------------------------------------
# Describing
# ---------------------------------------------------------------------------


def describe_ast(ast: dict, to_format: str, base_dirs: List[Path], settings,
                 log_cb: Logger = None) -> int:
    """Describe the pictures in a pandoc JSON document in place.

    Returns the number of pictures described.
    """
    from . import vision

    log = log_cb or (lambda m: None)
    images = list(iter_images(ast.get("blocks", [])))
    todo = []
    for img in images:
        inlines, src = _image_parts(img)
        if needs_description(stringify(inlines), src):
            todo.append(img)
    results: Dict[str, Tuple[str, str]] = {}   # src -> (label, text)
    if not todo:
        if images:
            log(f"[vision] {len(images)} picture(s) already have alternative text.")
        if images and is_text_only(to_format):
            ast["blocks"] = _captions_for_text_output(ast.get("blocks", []), results)
        return 0
    log(f"[vision] {len(todo)} picture(s) without alternative text found.")
    engine = vision.get_engine(settings, log_cb=log)

    for n, img in enumerate(todo, start=1):
        _, src = _image_parts(img)
        if src in results:
            continue
        data = load_image_bytes(src, base_dirs)
        if data is None:
            log(f"[vision] Picture {n}: {Path(src).name or src[:40]} could not be read; skipped.")
            continue
        try:
            vision.open_image(data)
        except Exception:
            log(f"[vision] Picture {n}: this picture format can't be read; skipped.")
            continue
        can_ocr = vision.text_profile(data, settings.lang) is not None
        if can_ocr and vision.is_mostly_text(data, settings.lang):
            text = ocr_text(data, settings.lang)
            if text:
                results[src] = (OCR_LABEL, text)
                log(f"[vision] Picture {n} of {len(todo)} is text; recognised text used.")
            continue
        try:
            d = engine.describe(data, "document", settings.lang, ask_text=not can_ocr)
        except Exception as e:  # noqa: BLE001
            log(f"[vision] Picture {n} of {len(todo)} could not be described: {e}")
            continue
        if d.kind == "picture":
            results[src] = (DESCRIPTION_LABEL, d.text)
            log(f"[vision] Picture {n} of {len(todo)} ({d.seconds:.1f} s): {d.text}")
        elif d.kind == "text":
            text = ocr_text(data, settings.lang)
            if text:
                results[src] = (OCR_LABEL, text)
        else:
            results[src] = ("", "")  # decorative: empty alternative text

    if not is_text_only(to_format):
        for img in todo:
            _, src = _image_parts(img)
            if src in results:
                img["c"][1] = to_inlines(results[src][1])
        _clear_generic_captions(ast.get("blocks", []), results)
    else:
        ast["blocks"] = _captions_for_text_output(ast.get("blocks", []), results)
    return sum(1 for label, _ in results.values() if label == DESCRIPTION_LABEL)


def _take_images(inlines: list, results: Dict[str, Tuple[str, str]]) -> Tuple[list, List[dict]]:
    """Remove described pictures from inlines; return (inlines, quotes)."""
    quotes: List[dict] = []
    out = []
    for x in inlines:
        if isinstance(x, dict) and x.get("t") == "Image":
            src = x["c"][2][0]
            if src in results:
                label, text = results[src]
                if text:
                    quotes.append(quote_block(label, text))
                continue
            alt = stringify(x["c"][1])
            if alt:
                quotes.append(quote_block(DESCRIPTION_LABEL, alt))
            continue
        if isinstance(x, dict) and isinstance(x.get("c"), list) and x.get("t") in (
                "Emph", "Strong", "Underline", "Strikeout", "Superscript", "Subscript",
                "SmallCaps", "Quoted", "Cite", "Link", "Span"):
            c = list(x["c"])
            idx = {"Quoted": 1, "Cite": 1, "Link": 1, "Span": 1}.get(x["t"])
            if idx is None:
                inner, q = _take_images(c, results)
                x = {**x, "c": inner}
            else:
                inner, q = _take_images(c[idx], results)
                c[idx] = inner
                x = {**x, "c": c}
            quotes.extend(q)
        out.append(x)
    return out, quotes


def _captions_for_text_output(blocks: list, results: Dict[str, Tuple[str, str]]) -> list:
    out: List[dict] = []
    for b in blocks:
        t = b.get("t")
        if t in ("Para", "Plain"):
            inlines, quotes = _take_images(b.get("c", []), results)
            if stringify(inlines):
                out.append({**b, "c": inlines})
            out.extend(quotes)
            continue
        if t == "Figure":
            attr, caption, body = b["c"]
            cap = stringify(caption)
            if needs_description(cap, ""):
                cap = ""  # "image1", "Figure" and the like say nothing
            quotes: List[dict] = []
            for img in iter_images(body):
                src = img["c"][2][0]
                label, text = results.get(src, (DESCRIPTION_LABEL, stringify(img["c"][1])))
                if text:
                    quotes.append(quote_block(label, text))
            if cap:
                out.append({"t": "Para", "c": to_inlines(cap)})
            out.extend(quotes)
            continue
        out.append(_walk_nested(b, results))
    return out


def _clear_generic_captions(node, results) -> None:
    """Remove captions like "image1" from figures whose picture was described."""
    if isinstance(node, dict):
        if node.get("t") == "Figure":
            attr, caption, body = node["c"]
            srcs = [img["c"][2][0] for img in iter_images(body)]
            if any(src in results for src in srcs) and needs_description(stringify(caption), ""):
                node["c"][1] = [None, []]
        for v in node.values():
            if isinstance(v, (list, dict)):
                _clear_generic_captions(v, results)
    elif isinstance(node, list):
        for x in node:
            _clear_generic_captions(x, results)


def relocate_sources(node, old_prefix: str, new_prefix: str) -> None:
    """Rewrite picture paths that start with old_prefix."""
    for img in iter_images(node):
        src = img["c"][2][0]
        if src.startswith(old_prefix):
            img["c"][2][0] = new_prefix + src[len(old_prefix):].lstrip("/\\")


def _walk_nested(node, results):
    """Apply _captions_for_text_output to block lists nested in a block."""
    if isinstance(node, dict):
        return {k: (_walk_nested(v, results) if k == "c" else v) for k, v in node.items()}
    if isinstance(node, list):
        if _is_block_list(node):
            return _captions_for_text_output(node, results)
        return [_walk_nested(x, results) for x in node]
    return node


__all__ = ["TEXT_ONLY_OUTPUTS", "is_text_only", "describe_ast", "needs_description",
           "load_image_bytes", "DESCRIPTION_LABEL", "OCR_LABEL"]
