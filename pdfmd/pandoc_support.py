"""Pandoc integration for pdfmd.

pdfmd turns PDFs into Markdown. Pandoc (https://pandoc.org) converts between
dozens of document formats. Together they let pdfmd take a PDF (or any
format pandoc reads) and produce Word, EPUB, HTML, LaTeX, ODT, PowerPoint,
reStructuredText, AsciiDoc, Typst, JATS and many other formats, with
pandoc's citations, templates, filters, tables of contents and every other
command-line option.

Pandoc is a separate program (GPL-2.0-or-later). pdfmd looks for it in this
order:

1. the ``PDFMD_PANDOC`` environment variable (full path to pandoc.exe),
2. ``pandoc`` on the PATH,
3. the default Windows install folders,
4. the copy bundled with Document Conversion Suite (``pandoc`` folder next
   to the program).

Accessibility defaults (used when "Math rendering" is Automatic):

* HTML and slide shows: MathJax 4, so math is spoken, readable in Braille
  and explorable with the keyboard; ``lang`` is set on the document.
* EPUB: MathML, which EPUB reading systems pass to screen readers.
* Word, ODT, PowerPoint: pandoc writes native equations (OMML), which
  Word's accessibility features and screen readers understand.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .mathjax import MATHJAX_URL, language_tag, wrap_unicode_math, _remove_mathjax_header

Logger = Optional[Callable[[str], None]]

# Friendly names for formats. Formats pandoc reports that are not listed
# here are still offered, by their pandoc name.
FORMAT_NAMES: Dict[str, str] = {
    "asciidoc": "AsciiDoc",
    "asciidoctor": "AsciiDoctor",
    "beamer": "LaTeX Beamer slides",
    "bibtex": "BibTeX bibliography",
    "biblatex": "BibLaTeX bibliography",
    "bits": "BITS XML",
    "chunkedhtml": "Chunked HTML (zip of linked pages)",
    "commonmark": "CommonMark Markdown",
    "commonmark_x": "CommonMark with extensions",
    "context": "ConTeXt",
    "creole": "Creole wiki",
    "csljson": "CSL JSON bibliography",
    "csv": "CSV table",
    "djot": "Djot",
    "docbook": "DocBook 4",
    "docbook4": "DocBook 4",
    "docbook5": "DocBook 5",
    "docx": "Microsoft Word (.docx)",
    "dokuwiki": "DokuWiki",
    "dzslides": "DZSlides HTML slides",
    "endnotexml": "EndNote XML bibliography",
    "epub": "EPUB e-book",
    "epub2": "EPUB 2 e-book",
    "epub3": "EPUB 3 e-book",
    "fb2": "FictionBook 2",
    "gfm": "GitHub-Flavored Markdown",
    "haddock": "Haddock markup",
    "html": "HTML web page",
    "html4": "HTML 4",
    "html5": "HTML 5",
    "icml": "InDesign ICML",
    "ipynb": "Jupyter notebook",
    "jats": "JATS XML",
    "jats_archiving": "JATS archiving XML",
    "jats_articleauthoring": "JATS article authoring XML",
    "jats_publishing": "JATS publishing XML",
    "jira": "Jira wiki",
    "json": "Pandoc JSON (AST)",
    "latex": "LaTeX",
    "man": "Unix man page",
    "markdown": "Pandoc Markdown",
    "markdown_github": "GitHub Markdown (deprecated)",
    "markdown_mmd": "MultiMarkdown",
    "markdown_phpextra": "PHP Markdown Extra",
    "markdown_strict": "Original (strict) Markdown",
    "markua": "Markua",
    "mediawiki": "MediaWiki",
    "ms": "roff ms",
    "muse": "Emacs Muse",
    "native": "Pandoc native (Haskell)",
    "odt": "OpenDocument text (.odt)",
    "opendocument": "OpenDocument XML",
    "opml": "OPML outline",
    "org": "Emacs Org mode",
    "pdf": "PDF (needs a LaTeX, Typst or HTML-to-PDF engine)",
    "plain": "Plain text",
    "pod": "Perl POD",
    "pptx": "Microsoft PowerPoint (.pptx)",
    "revealjs": "reveal.js HTML slides",
    "ris": "RIS bibliography",
    "rst": "reStructuredText",
    "rtf": "Rich Text Format (.rtf)",
    "s5": "S5 HTML slides",
    "slideous": "Slideous HTML slides",
    "slidy": "Slidy HTML slides",
    "t2t": "txt2tags",
    "tei": "TEI Simple XML",
    "texinfo": "GNU Texinfo",
    "textile": "Textile",
    "tikiwiki": "TikiWiki",
    "tsv": "TSV table",
    "twiki": "TWiki",
    "typst": "Typst",
    "vimdoc": "Vim help",
    "vimwiki": "Vimwiki",
    "xlsx": "Microsoft Excel (.xlsx)",
    "xml": "Pandoc XML (AST)",
    "xwiki": "XWiki",
    "zimwiki": "ZimWiki",
    "ansi": "Terminal text with ANSI styling",
    "mdoc": "mdoc man page",
}

# Fallback lists used when pandoc can't be asked (not installed yet).
DEFAULT_INPUT_FORMATS = [
    "markdown", "commonmark", "commonmark_x", "gfm", "markdown_mmd", "markdown_phpextra",
    "markdown_strict", "djot", "docx", "odt", "epub", "html", "latex", "rst", "asciidoc",
    "org", "mediawiki", "dokuwiki", "textile", "typst", "ipynb", "jats", "docbook", "tei",
    "fb2", "rtf", "pptx", "xlsx", "csv", "tsv", "json", "native", "opml", "man", "muse",
    "creole", "haddock", "jira", "t2t", "tikiwiki", "twiki", "vimwiki", "bibtex", "biblatex",
    "csljson", "endnotexml", "ris", "bits", "pod", "mdoc", "xml",
]
DEFAULT_OUTPUT_FORMATS = [
    "html", "html5", "html4", "docx", "odt", "epub", "epub3", "epub2", "pptx", "rtf", "pdf",
    "latex", "beamer", "context", "typst", "markdown", "commonmark", "commonmark_x", "gfm",
    "markdown_mmd", "markdown_phpextra", "markdown_strict", "djot", "plain", "rst",
    "asciidoc", "asciidoctor", "org", "mediawiki", "dokuwiki", "textile", "jira", "xwiki",
    "zimwiki", "vimwiki", "revealjs", "slidy", "slideous", "s5", "dzslides", "chunkedhtml",
    "jats", "jats_archiving", "jats_articleauthoring", "jats_publishing", "docbook",
    "docbook5", "tei", "icml", "fb2", "opml", "opendocument", "ipynb", "man", "ms", "texinfo",
    "haddock", "muse", "markua", "json", "native", "bibtex", "biblatex", "csljson", "ansi",
    "vimdoc", "xml", "bits",
]

# Output file extensions.
EXTENSIONS: Dict[str, str] = {
    "html": ".html", "html4": ".html", "html5": ".html", "revealjs": ".html",
    "slidy": ".html", "slideous": ".html", "s5": ".html", "dzslides": ".html",
    "chunkedhtml": ".zip", "docx": ".docx", "odt": ".odt", "opendocument": ".fodt",
    "epub": ".epub", "epub2": ".epub", "epub3": ".epub", "pptx": ".pptx", "rtf": ".rtf",
    "pdf": ".pdf", "latex": ".tex", "beamer": ".tex", "context": ".tex", "typst": ".typ",
    "markdown": ".md", "commonmark": ".md", "commonmark_x": ".md", "gfm": ".md",
    "markdown_mmd": ".md", "markdown_phpextra": ".md", "markdown_strict": ".md",
    "markdown_github": ".md", "markua": ".md", "djot": ".dj", "plain": ".txt",
    "ansi": ".txt", "rst": ".rst", "asciidoc": ".adoc", "asciidoctor": ".adoc",
    "asciidoc_legacy": ".adoc", "org": ".org", "mediawiki": ".wiki", "dokuwiki": ".txt",
    "textile": ".textile", "jira": ".txt", "xwiki": ".txt", "zimwiki": ".txt",
    "vimwiki": ".wiki", "vimdoc": ".txt", "jats": ".xml", "jats_archiving": ".xml",
    "jats_articleauthoring": ".xml", "jats_publishing": ".xml", "bits": ".xml",
    "docbook": ".xml", "docbook4": ".xml", "docbook5": ".xml", "tei": ".xml",
    "xml": ".xml", "icml": ".icml", "fb2": ".fb2", "opml": ".opml", "ipynb": ".ipynb",
    "man": ".1", "ms": ".ms", "texinfo": ".texi", "haddock": ".txt", "muse": ".muse",
    "json": ".json", "native": ".native", "bibtex": ".bib", "biblatex": ".bib",
    "csljson": ".json",
}

# Formats pandoc can only write to a file (never to stdout).
BINARY_OUTPUTS = {"docx", "odt", "epub", "epub2", "epub3", "pptx", "pdf", "chunkedhtml"}
HTML_LIKE = {"html", "html4", "html5", "revealjs", "slidy", "slideous", "s5", "dzslides",
             "chunkedhtml"}
EPUB_LIKE = {"epub", "epub2", "epub3"}

MATH_METHODS = [
    ("auto", "Automatic (most accessible for the output format)"),
    ("mathjax", "MathJax (spoken, Braille, keyboard exploration)"),
    ("mathml", "MathML"),
    ("katex", "KaTeX"),
    ("webtex", "WebTeX images"),
    ("gladtex", "GladTeX"),
    ("plain", "Plain text (Unicode)"),
]

WRAP_MODES = ["auto", "none", "preserve"]

INPUT_EXTENSIONS: Dict[str, str] = {
    ".md": "markdown", ".markdown": "markdown", ".txt": "markdown", ".docx": "docx",
    ".odt": "odt", ".epub": "epub", ".html": "html", ".htm": "html", ".xhtml": "html",
    ".tex": "latex", ".latex": "latex", ".rst": "rst", ".adoc": "asciidoc",
    ".asciidoc": "asciidoc", ".org": "org", ".wiki": "mediawiki", ".textile": "textile",
    ".typ": "typst", ".ipynb": "ipynb", ".xml": "docbook", ".dbk": "docbook",
    ".fb2": "fb2", ".rtf": "rtf", ".pptx": "pptx", ".xlsx": "xlsx", ".csv": "csv",
    ".tsv": "tsv", ".json": "json", ".native": "native", ".opml": "opml", ".muse": "muse",
    ".t2t": "t2t", ".bib": "biblatex", ".ris": "ris", ".dj": "djot", ".pod": "pod",
    ".1": "man", ".man": "man",
}

# ---------------------------------------------------------------------------
# Finding pandoc
# ---------------------------------------------------------------------------

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_pandoc() -> Optional[str]:
    """Return the full path of pandoc, or None if it isn't installed."""
    env = os.environ.get("PDFMD_PANDOC")
    if env and Path(env).is_file():
        return env
    exe = "pandoc.exe" if sys.platform == "win32" else "pandoc"
    # A pandoc the user installed takes priority over the bundled copy.
    found = shutil.which("pandoc")
    if found:
        return found
    if sys.platform == "win32":
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"),
                     os.environ.get("ProgramFiles(x86)")):
            if base:
                cand = Path(base) / "Pandoc" / exe
                if cand.is_file():
                    return str(cand)
    bundled = bundled_pandoc()
    return str(bundled) if bundled else None


def bundled_pandoc() -> Optional[Path]:
    """The pandoc shipped with Document Conversion Suite, if present."""
    exe = "pandoc.exe" if sys.platform == "win32" else "pandoc"
    for base in (_app_dir(), _app_dir() / "packaging" / "vendor"):
        cand = base / "pandoc" / exe
        if cand.is_file():
            return cand
    return None


def is_bundled(path: Optional[str]) -> bool:
    b = bundled_pandoc()
    return bool(path and b and Path(path).resolve() == b.resolve())


def _run(args: Sequence[str], input_text: Optional[str] = None,
         cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        creationflags=_NO_WINDOW,
    )


def pandoc_version(pandoc: Optional[str] = None) -> Optional[str]:
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        return None
    try:
        out = _run([pandoc, "--version"]).stdout.decode("utf-8", "replace")
        first = out.splitlines()[0] if out else ""
        m = re.search(r"(\d+(?:\.\d+)+)", first)
        return m.group(1) if m else first.strip() or None
    except Exception:
        return None


def _list(pandoc: Optional[str], flag: str, fallback: List[str]) -> List[str]:
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        return list(fallback)
    try:
        out = _run([pandoc, flag]).stdout.decode("utf-8", "replace")
        items = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return items or list(fallback)
    except Exception:
        return list(fallback)


def list_input_formats(pandoc: Optional[str] = None) -> List[str]:
    return _list(pandoc, "--list-input-formats", DEFAULT_INPUT_FORMATS)


def list_output_formats(pandoc: Optional[str] = None) -> List[str]:
    return _list(pandoc, "--list-output-formats", DEFAULT_OUTPUT_FORMATS)


def list_highlight_styles(pandoc: Optional[str] = None) -> List[str]:
    return _list(pandoc, "--list-highlight-styles",
                 ["pygments", "tango", "espresso", "zenburn", "kate", "monochrome",
                  "breezedark", "haddock"])


def format_label(fmt: str) -> str:
    name = FORMAT_NAMES.get(fmt)
    return f"{name} ({fmt})" if name else fmt


def output_extension(fmt: str) -> str:
    base = re.split(r"[+-]", fmt, maxsplit=1)[0]
    return EXTENSIONS.get(base, "." + base)


def detect_input_format(path: str | Path) -> Optional[str]:
    return INPUT_EXTENSIONS.get(Path(path).suffix.lower())


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@dataclass
class PandocOptions:
    """Pandoc settings. Anything not covered here goes in ``extra_args``."""

    to_format: str = "html"
    from_format: str = ""             # "" = detect from the file extension
    standalone: bool = True
    toc: bool = False
    toc_depth: int = 3
    number_sections: bool = False
    embed_resources: bool = False
    citeproc: bool = False
    bibliography: str = ""
    csl: str = ""
    reference_doc: str = ""
    template: str = ""
    math: str = "auto"
    highlight_style: str = ""
    wrap: str = "auto"
    title: str = ""
    lang: str = ""
    lua_filters: str = ""             # separated by ";"
    extra_args: str = ""              # any other pandoc options
    shift_heading_level: int = 0
    extract_media: bool = True
    pdf_engine: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "PandocOptions":
        obj = cls()
        for k, v in (data or {}).items():
            if hasattr(obj, k) and isinstance(v, type(getattr(obj, k))):
                setattr(obj, k, v)
        return obj


def build_args(
    pandoc: str,
    input_path: Optional[Path],
    output_path: Path,
    opts: PandocOptions,
    from_format: Optional[str],
    ocr_lang: Optional[str] = None,
) -> List[str]:
    to = opts.to_format or "html"
    base_to = re.split(r"[+-]", to, maxsplit=1)[0]
    args: List[str] = [pandoc]
    if from_format:
        args += ["--from", from_format]
    args += ["--to", to, "--output", str(output_path)]

    if opts.standalone and base_to not in BINARY_OUTPUTS:
        args.append("--standalone")
    if opts.toc:
        args += ["--toc", f"--toc-depth={max(1, min(6, int(opts.toc_depth)))}"]
    if opts.number_sections:
        args.append("--number-sections")
    if opts.embed_resources and base_to in HTML_LIKE:
        args += ["--embed-resources", "--standalone"]
    if opts.shift_heading_level:
        args.append(f"--shift-heading-level-by={int(opts.shift_heading_level)}")
    if opts.citeproc or opts.bibliography:
        args.append("--citeproc")
    if opts.bibliography:
        for bib in opts.bibliography.split(";"):
            if bib.strip():
                args += ["--bibliography", bib.strip()]
    if opts.csl:
        args += ["--csl", opts.csl]
    if opts.reference_doc:
        args += ["--reference-doc", opts.reference_doc]
    if opts.template:
        args += ["--template", opts.template]
    if opts.highlight_style:
        args += ["--highlight-style", opts.highlight_style]
    if opts.wrap in WRAP_MODES and opts.wrap != "auto":
        args.append(f"--wrap={opts.wrap}")
    if opts.pdf_engine and base_to == "pdf":
        args += ["--pdf-engine", opts.pdf_engine]

    # Math: accessible defaults per output format.
    math = opts.math or "auto"
    if math == "auto":
        if base_to in HTML_LIKE:
            math = "mathjax"
        elif base_to in EPUB_LIKE:
            math = "mathml"
        else:
            math = ""  # docx/odt/pptx write native equations; others keep TeX
    if math == "mathjax":
        args.append(f"--mathjax={MATHJAX_URL}")
    elif math in ("mathml", "katex", "webtex", "gladtex"):
        args.append(f"--{math}")
    elif math == "plain":
        pass

    # Metadata: language and a page title so standalone output is labeled.
    lang = opts.lang.strip() or language_tag(ocr_lang)
    args += ["--metadata", f"lang={lang}"]
    if opts.title.strip():
        args += ["--metadata", f"title={opts.title.strip()}"]
    elif input_path is not None:
        args += ["--metadata", f"pagetitle={input_path.stem}"]

    if opts.extract_media and base_to not in BINARY_OUTPUTS and input_path is not None \
            and (from_format or "") in ("docx", "odt", "epub", "pptx", "ipynb"):
        args += ["--extract-media", str(output_path.parent / (output_path.stem + "_media"))]

    if input_path is not None:
        args += ["--resource-path", os.pathsep.join([str(input_path.parent), "."])]

    for flt in opts.lua_filters.split(";"):
        flt = flt.strip()
        if flt:
            args += ["--lua-filter" if flt.lower().endswith(".lua") else "--filter", flt]

    if opts.extra_args.strip():
        args += split_args(opts.extra_args)
    return args


def split_args(text: str) -> List[str]:
    """Split a command-line string like a shell, but keep backslashes.

    Quotes group words ("Ada Lovelace") and are removed; backslashes in
    Windows paths are kept.
    """
    lex = shlex.shlex(text, posix=True)
    lex.whitespace_split = True
    lex.escape = ""
    lex.commenters = ""
    return list(lex)


# Input formats that carry their pictures inside the file (pandoc keeps them
# in its media bag, which the JSON document doesn't contain).
CONTAINER_INPUTS = ("docx", "odt", "epub", "epub2", "epub3", "pptx", "ipynb", "rtf", "fb2",
                    "xlsx", "docbook", "docbook4", "docbook5", "jats", "bits")
# Options that belong to the writer pass only.
_WRITER_ONLY = {"-o", "--output", "-t", "--to", "-w", "--write", "-f", "--from", "-r", "--read"}


def convert(
    input_path: str | Path,
    output_path: str | Path,
    opts: PandocOptions,
    ocr_lang: Optional[str] = None,
    log_cb: Logger = None,
    pandoc: Optional[str] = None,
    vision=None,
) -> Path:
    """Convert one file with pandoc. Raises RuntimeError on failure.

    ``vision`` (a ``vision.VisionSettings``) turns on picture descriptions:
    pictures without alternative text are described by the local vision
    model (see docimages.py).
    """
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        raise RuntimeError(
            "Pandoc is not installed. Install it from https://pandoc.org/installing.html "
            "or with: winget install --id JohnMacFarlane.Pandoc -e")
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from_format = opts.from_format or detect_input_format(input_path) or None
    stdin_text: Optional[str] = None
    if (from_format or "").startswith(("markdown", "gfm", "commonmark")) or \
            input_path.suffix.lower() in (".md", ".markdown"):
        text = input_path.read_text(encoding="utf-8", errors="replace")
        # pdfmd's MathJax loader is only for Markdown viewers; pandoc handles
        # math itself. Unicode math in sentences ("E = mc²") is turned into
        # TeX so pandoc writes real equations (native Word/ODT equations,
        # MathML in EPUB, MathJax in HTML) that assistive technology reads.
        prepared = wrap_unicode_math(_remove_mathjax_header(text))
        if prepared != text:
            stdin_text = prepared
            from_format = from_format or "markdown"

    if vision is not None and getattr(vision, "enabled", False):
        from . import vision as _vision

        if _vision.available(vision):
            return _convert_with_descriptions(pandoc, input_path, output_path, opts, from_format,
                                              stdin_text, ocr_lang, log_cb, vision)
        if log_cb:
            log_cb("[vision] Picture descriptions skipped: "
                   + _vision.unavailable_reason(vision) + ".")

    args = build_args(pandoc, input_path, output_path, opts, from_format, ocr_lang)
    if stdin_text is None:
        args.append(str(input_path))
    if log_cb:
        shown = [Path(a).name if i == 0 else a for i, a in enumerate(args)]
        log_cb("[pandoc] " + " ".join(shlex.quote(a) for a in shown))
    proc = _run(args, input_text=stdin_text, cwd=str(input_path.parent))
    err = proc.stderr.decode("utf-8", "replace").strip()
    if err and log_cb:
        for line in err.splitlines():
            log_cb(f"[pandoc] {line}")
    if proc.returncode != 0:
        raise RuntimeError(err or f"pandoc exited with code {proc.returncode}")
    if log_cb:
        log_cb(f"[pandoc] Saved → {output_path}")
    return output_path


def _convert_with_descriptions(pandoc: str, input_path: Path, output_path: Path,
                               opts: PandocOptions, from_format: Optional[str],
                               stdin_text: Optional[str], ocr_lang: Optional[str],
                               log_cb: Logger, vision) -> Path:
    """Read the document as pandoc JSON, describe its pictures, then write it."""
    import json
    import tempfile

    from . import docimages

    to = opts.to_format or "html"
    base_to = re.split(r"[+-]", to, maxsplit=1)[0]
    with tempfile.TemporaryDirectory(prefix="pdfmd-pandoc-") as tmp:
        tmpdir = Path(tmp)
        # Pictures inside Word, ODT, EPUB, PowerPoint and notebooks are
        # extracted: next to the output for text outputs (which link to
        # them), or to a temporary folder for binary outputs (which embed
        # them).
        read = [pandoc]
        if from_format:
            read += ["--from", from_format]
        read += ["--to", "json"]
        base_dirs = [input_path.parent]
        base_from = re.split(r"[+-]", from_format or "", maxsplit=1)[0] or \
            {".rtf": "rtf", ".fb2": "fb2"}.get(input_path.suffix.lower(), "")
        if base_from in CONTAINER_INPUTS:
            if opts.extract_media and base_to not in BINARY_OUTPUTS:
                media = output_path.parent / (output_path.stem + "_media")
            else:
                media = tmpdir / "media"
            read += ["--extract-media", str(media)]
            base_dirs.append(media)
        read += ["--resource-path", os.pathsep.join([str(input_path.parent), "."])]
        # Reader options in the extra arguments (for example
        # --track-changes=all) must reach this pass too.
        extra = split_args(opts.extra_args) if opts.extra_args.strip() else []
        k = 0
        while k < len(extra):
            a = extra[k]
            name = a.split("=", 1)[0]
            if name in _WRITER_ONLY:
                k += 1 if "=" in a else 2
                continue
            read.append(a)
            k += 1
        if stdin_text is None:
            read.append(str(input_path))
        proc = _run(read, input_text=stdin_text, cwd=str(input_path.parent))
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()
                               or f"pandoc exited with code {proc.returncode}")
        ast = json.loads(proc.stdout.decode("utf-8"))

        vs = vision
        if not getattr(vs, "lang", ""):
            vs.lang = ocr_lang or "eng"
        try:
            n = docimages.describe_ast(ast, to, base_dirs, vs, log_cb=log_cb)
            if log_cb and n:
                log_cb(f"[vision] Described {n} picture{'s' if n != 1 else ''}.")
        except Exception as e:  # noqa: BLE001  (never fail a conversion over pictures)
            if log_cb:
                log_cb(f"[vision] Picture descriptions skipped: {e}")

        doc_json = tmpdir / "document.json"
        extra = []
        if (tmpdir / "media").is_dir():
            # Pictures extracted to the temporary folder are embedded in the
            # output; refer to them by a short relative path so no temporary
            # folder name ends up inside the document.
            docimages.relocate_sources(ast.get("blocks", []), str(tmpdir / "media"), "media/")
            extra = ["--resource-path",
                     os.pathsep.join([str(tmpdir), str(input_path.parent), "."])]
        doc_json.write_text(json.dumps(ast), encoding="utf-8")
        args = build_args(pandoc, input_path, output_path, opts, "json", ocr_lang)
        args += extra
        args.append(str(doc_json))
        if log_cb:
            shown = [Path(a).name if i == 0 else a for i, a in enumerate(args)]
            log_cb("[pandoc] " + " ".join(shlex.quote(a) for a in shown))
        proc = _run(args, cwd=str(input_path.parent))
        err = proc.stderr.decode("utf-8", "replace").strip()
        if err and log_cb:
            for line in err.splitlines():
                log_cb(f"[pandoc] {line}")
        if proc.returncode != 0:
            raise RuntimeError(err or f"pandoc exited with code {proc.returncode}")
    if log_cb:
        log_cb(f"[pandoc] Saved → {output_path}")
    return output_path


def install_command() -> Optional[List[str]]:
    """Command that installs pandoc with winget, or None if winget is missing."""
    if sys.platform != "win32" or not shutil.which("winget"):
        return None
    return ["winget", "install", "--id", "JohnMacFarlane.Pandoc", "--exact", "--source", "winget"]


__all__ = [
    "PandocOptions",
    "MATH_METHODS",
    "WRAP_MODES",
    "find_pandoc",
    "pandoc_version",
    "list_input_formats",
    "list_output_formats",
    "list_highlight_styles",
    "format_label",
    "output_extension",
    "detect_input_format",
    "build_args",
    "convert",
    "install_command",
]
