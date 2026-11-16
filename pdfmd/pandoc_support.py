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

import copy
import functools
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import pandoc_options as po
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
    "asciidoc_legacy": "AsciiDoc (legacy)",
    "bbcode": "BBCode forum markup",
    "bbcode_fluxbb": "BBCode (FluxBB)",
    "bbcode_hubzilla": "BBCode (Hubzilla)",
    "bbcode_phpbb": "BBCode (phpBB)",
    "bbcode_steam": "BBCode (Steam)",
    "bbcode_xenforo": "BBCode (XenForo)",
    "fodt": "Flat OpenDocument text (.fodt)",
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
# Batch conversion: files and folders
# ---------------------------------------------------------------------------


def supported_input_extensions() -> List[str]:
    """Extensions taken from folders by default: PDF and everything pandoc reads."""
    return sorted(set(INPUT_EXTENSIONS) | {".pdf"})


def parse_type_filter(text: str) -> Optional[set]:
    """Turn "docx; *.md, .html" into {".docx", ".md", ".html"}. Empty means all."""
    exts = set()
    for part in re.split(r"[;,\s]+", text or ""):
        part = part.strip().lower().lstrip("*")
        if not part or part == ".":
            continue
        exts.add(part if part.startswith(".") else "." + part)
    return exts or None


def _skip_name(name: str) -> bool:
    # Hidden files, Office lock files (~$report.docx) and editor backups.
    return name.startswith((".", "~$")) or name.endswith("~")


def folder_files(folder: str | Path, recursive: bool = False,
                 types: Optional[set] = None) -> List[Path]:
    """Files in ``folder`` that can be converted, sorted, optionally with subfolders.

    ``types`` is a set of extensions such as {".docx", ".md"}; None means
    every supported input. Hidden files and folders, Office lock files and
    pdfmd's ``_assets`` image folders are skipped.
    """
    folder = Path(folder)
    wanted = types if types is not None else set(supported_input_extensions())
    found: List[Path] = []
    if not folder.is_dir():
        return found
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs
                         if recursive and not d.startswith(".") and not d.endswith("_assets"))
        for name in sorted(files, key=str.lower):
            if _skip_name(name):
                continue
            p = Path(root) / name
            if p.suffix.lower() in wanted:
                found.append(p)
    return found


@dataclass
class BatchJob:
    source: Path
    dest: Path


def plan_batch(items: Sequence[str | Path], to_format: str, out_dir: str | Path = "",
               recursive: bool = False, types: Optional[set] = None,
               log_cb: Logger = None) -> List[BatchJob]:
    """Turn a list of files and folders into (source, destination) pairs.

    * A file is converted whatever its type.
    * A folder contributes every supported file in it (and its subfolders when
      ``recursive``), limited to ``types`` when given. Files already in the
      output format are skipped, so converting a folder twice doesn't convert
      the first run's results.
    * Without ``out_dir`` each output is saved next to its input. With it,
      files from a folder keep their subfolder layout under ``out_dir``.
    * A file listed twice (on its own and inside a folder) is converted once.
    * Existing files are never overwritten, and two inputs never share an
      output name (``_1``, ``_2`` are added).
    """
    ext = output_extension(to_format)
    out = Path(out_dir) if out_dir else None
    jobs: List[BatchJob] = []
    seen: set = set()
    claimed: set = set()

    def key(p: Path) -> str:
        try:
            return os.path.normcase(str(p.resolve()))
        except OSError:
            return os.path.normcase(str(p.absolute()))

    def add(src: Path, rel_dir: Optional[Path]) -> None:
        k = key(src)
        if k in seen:
            return
        seen.add(k)
        if out is None:
            dest_dir = src.parent
        else:
            dest_dir = out / rel_dir if rel_dir is not None else out
        dest = dest_dir / (src.stem + ext)
        n = 1
        while dest.exists() or key(dest) == k or key(dest) in claimed:
            dest = dest_dir / f"{src.stem}_{n}{ext}"
            n += 1
        claimed.add(key(dest))
        jobs.append(BatchJob(src, dest))

    for item in items:
        p = Path(item)
        if p.is_dir():
            files = folder_files(p, recursive, types)
            skipped = [f for f in files if f.suffix.lower() == ext.lower()]
            if skipped and log_cb:
                log_cb(f"Skipped {len(skipped)} file{'s' if len(skipped) != 1 else ''} in "
                       f"{p.name} already in the output format ({ext}).")
            for f in files:
                if f.suffix.lower() != ext.lower():
                    add(f, f.parent.relative_to(p))
        elif p.is_file():
            add(p, None)
        elif log_cb:
            log_cb(f"Not found, skipped: {p}")
    return jobs


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


@dataclass
class PandocOptions:
    """Pandoc settings.

    Options that existed before 1.9.0 have their own attribute, so old
    settings and profiles keep loading. Every newer option from
    ``pandoc_options.OPTIONS`` is stored in ``values`` (only when it differs
    from pandoc's default). ``in_extensions`` / ``out_extensions`` hold the
    format extensions turned on or off, per format: {"docx": {"styles": True}}.
    """

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
    values: Dict[str, Any] = field(default_factory=dict)
    in_extensions: Dict[str, Dict[str, bool]] = field(default_factory=dict)
    out_extensions: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return copy.deepcopy(dict(self.__dict__))

    @classmethod
    def from_dict(cls, data: dict) -> "PandocOptions":
        obj = cls()
        for k, v in (data or {}).items():
            if hasattr(obj, k) and isinstance(v, type(getattr(obj, k))):
                setattr(obj, k, copy.deepcopy(v))
        # Keep only well-formed extension settings.
        for name in ("in_extensions", "out_extensions"):
            clean = {}
            for fmt, changes in getattr(obj, name).items():
                if isinstance(fmt, str) and isinstance(changes, dict):
                    clean[fmt] = {str(e): bool(on) for e, on in changes.items()}
            setattr(obj, name, clean)
        return obj

    def citation_method(self) -> str:
        """"", "citeproc", "natbib" or "biblatex"."""
        method = str(self.values.get("citation_method", "") or "")
        if not method and self.citeproc:
            method = "citeproc"
        if not method and self.bibliography.strip():
            method = "citeproc"   # a bibliography means "format my citations"
        return method


_UNSET = object()


@functools.lru_cache(maxsize=8)
def _help_flags(pandoc: str) -> Optional[frozenset]:
    try:
        proc = _run([pandoc, "--help"])
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    flags = po.parse_help_flags(proc.stdout.decode("utf-8", "replace"))
    return frozenset(flags) if flags else None


def supported_flags(pandoc: Optional[str] = None) -> Optional[frozenset]:
    """Long option names the pandoc program lists in ``--help`` (None if unknown)."""
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        return None
    return _help_flags(str(pandoc))


@functools.lru_cache(maxsize=64)
def _extensions(pandoc: str, fmt: str) -> Tuple[Tuple[str, bool], ...]:
    try:
        proc = _run([pandoc, f"--list-extensions={fmt}"])
    except Exception:
        return ()
    if proc.returncode != 0:
        return ()
    return tuple(po.parse_extensions(proc.stdout.decode("utf-8", "replace")))


def list_extensions(fmt: str, pandoc: Optional[str] = None) -> List[Tuple[str, bool]]:
    """Extensions of a format and whether pandoc turns each on by default."""
    pandoc = pandoc or find_pandoc()
    if not pandoc or not fmt:
        return []
    return list(_extensions(str(pandoc), po.base_format(fmt)))


def _print(pandoc: Optional[str], args: List[str]) -> bytes:
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        raise RuntimeError("Pandoc is not installed.")
    proc = _run([pandoc] + args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()
                           or f"pandoc exited with code {proc.returncode}")
    return proc.stdout


def default_template(fmt: str, pandoc: Optional[str] = None) -> str:
    """Pandoc's built-in template for an output format."""
    return _print(pandoc, ["--print-default-template", po.base_format(fmt)]).decode("utf-8")


def default_data_file(name: str, pandoc: Optional[str] = None) -> bytes:
    """A pandoc data file, for example "reference.docx"."""
    return _print(pandoc, ["--print-default-data-file", name])


def highlight_style_theme(style: str, pandoc: Optional[str] = None) -> str:
    """A highlighting style as an editable JSON theme."""
    return _print(pandoc, ["--print-highlight-style", style]).decode("utf-8")


def build_args(
    pandoc: str,
    input_path: Optional[Path],
    output_path: Path,
    opts: PandocOptions,
    from_format: Optional[str],
    ocr_lang: Optional[str] = None,
    include_reader: bool = True,
    flags: Any = _UNSET,
    resource_dirs: Optional[Sequence[Path]] = None,
    page_title: Optional[str] = None,
) -> List[str]:
    """The pandoc command line that converts ``input_path`` to ``output_path``.

    ``include_reader`` False leaves out the options used when reading a source
    document (for the second pass of a conversion that reads pandoc JSON).
    ``flags`` is the set from ``supported_flags``; options the running pandoc
    doesn't have are left out. The input file itself is not added.
    """
    if flags is _UNSET:
        flags = supported_flags(pandoc)

    def has(name: str) -> bool:
        return flags is None or name in flags

    to = opts.to_format or "html"
    base_to = po.base_format(to)
    if to == base_to:
        to += po.extension_suffix(opts.out_extensions.get(base_to))
    args: List[str] = [pandoc]
    if from_format:
        fr = from_format
        base_from = po.base_format(from_format)
        if include_reader and fr == base_from:
            fr += po.extension_suffix(opts.in_extensions.get(base_from))
        args += ["--from", fr]
    args += ["--to", to, "--output", str(output_path)]

    if opts.standalone and base_to not in BINARY_OUTPUTS:
        args.append("--standalone")
    if opts.toc:
        args += ["--toc", f"--toc-depth={max(1, min(6, int(opts.toc_depth)))}"]
    if opts.embed_resources and base_to in HTML_LIKE:
        args.append("--embed-resources")
        if "--standalone" not in args:
            args.append("--standalone")
    if opts.shift_heading_level:
        args.append(f"--shift-heading-level-by={int(opts.shift_heading_level)}")

    method = opts.citation_method()
    if method == "citeproc":
        args.append("--citeproc")
    elif method in ("natbib", "biblatex") and base_to in po.LATEX_LIKE:
        args.append(f"--{method}")
    for bib in po.split_list(opts.bibliography):
        args += ["--bibliography", bib]

    hs = (opts.highlight_style or "").strip()
    if hs:
        if has("syntax-highlighting"):
            args.append(f"--syntax-highlighting={hs}")
        elif hs == "none":
            args.append("--no-highlight")
        elif hs != "idiomatic":
            args += ["--highlight-style", hs]
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
    # pandoc 3.8+ has --math-method (the single-method flags are deprecated).
    method_flag = flags is not None and "math-method" in flags
    if math == "mathjax":
        args.append(f"--math-method=mathjax:{MATHJAX_URL}" if method_flag
                    else f"--mathjax={MATHJAX_URL}")
    elif math in ("mathml", "katex", "webtex", "gladtex"):
        args.append(f"--math-method={math}" if method_flag else f"--{math}")

    # Metadata: language and a page title so standalone output is labeled.
    lang = opts.lang.strip() or language_tag(ocr_lang)
    args += ["--metadata", f"lang={lang}"]
    if opts.title.strip():
        args += ["--metadata", f"title={opts.title.strip()}"]
    elif page_title:
        args += ["--metadata", f"pagetitle={page_title}"]
    elif input_path is not None:
        args += ["--metadata", f"pagetitle={input_path.stem}"]

    if include_reader and opts.extract_media and base_to not in BINARY_OUTPUTS \
            and input_path is not None \
            and po.base_format(from_format) in ("docx", "odt", "epub", "pptx", "ipynb"):
        args += ["--extract-media", str(output_path.parent / (output_path.stem + "_media"))]

    dirs = po.split_list(str(opts.values.get("resource_path", "")))
    if resource_dirs:
        dirs += [str(d) for d in resource_dirs]
    elif input_path is not None:
        dirs.append(str(input_path.parent))
    if dirs:
        args += ["--resource-path", os.pathsep.join(dirs + ["."])]

    for flt in po.split_list(opts.lua_filters):
        args += ["--lua-filter" if flt.lower().endswith(".lua") else "--filter", flt]

    generic = po.generic_args(opts, to, from_format, flags,
                              reader=None if include_reader else False)
    # A defaults file goes first, so the options after it take priority.
    defaults = [a for a in generic if a.startswith("--defaults=")]
    generic = [a for a in generic if not a.startswith("--defaults=")]
    args[1:1] = defaults
    args += generic

    if opts.extra_args.strip():
        args += split_args(opts.extra_args)
    return args


def reader_args(opts: PandocOptions, from_format: Optional[str],
                flags: Optional[frozenset] = None) -> List[str]:
    """Options for reading a source document into pandoc JSON."""
    args = po.generic_args(opts, opts.to_format or "html", from_format, flags, reader=True)
    # Reader options in the extra arguments (for example --track-changes=all)
    # must reach the reading pass too.
    extra = split_args(opts.extra_args) if opts.extra_args.strip() else []
    k = 0
    while k < len(extra):
        a = extra[k]
        name = a.split("=", 1)[0]
        if name in _WRITER_ONLY:
            k += 1 if "=" in a else 2
            continue
        args.append(a)
        k += 1
    return args


def command_preview(opts: PandocOptions, input_name: str = "document.docx",
                    pandoc: Optional[str] = None) -> str:
    """The pandoc command line for one example file, for showing to the user."""
    pandoc = pandoc or find_pandoc() or "pandoc"
    src = Path(input_name)
    fmt = opts.from_format or detect_input_format(src) or None
    dest = src.with_suffix(output_extension(opts.to_format or "html"))
    args = build_args(pandoc, src, dest, opts, fmt, flags=supported_flags(pandoc))
    args[0] = "pandoc"
    args.append(str(src))
    return " ".join(shlex.quote(a) for a in args)


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


def _need_pandoc(pandoc: Optional[str]) -> str:
    pandoc = pandoc or find_pandoc()
    if not pandoc:
        raise RuntimeError(
            "Pandoc is not installed. Install it from https://pandoc.org/installing.html "
            "or with: winget install --id JohnMacFarlane.Pandoc -e")
    return pandoc


def _prepare_input(input_path: Path, from_format: Optional[str]
                   ) -> Tuple[Optional[str], Optional[str]]:
    """The input format, and Markdown text to send instead of the file (or None)."""
    if (from_format or "").startswith(("markdown", "gfm", "commonmark")) or \
            input_path.suffix.lower() in (".md", ".markdown"):
        text = input_path.read_text(encoding="utf-8", errors="replace")
        # pdfmd's MathJax loader is only for Markdown viewers; pandoc handles
        # math itself. Unicode math in sentences ("E = mc²") is turned into
        # TeX so pandoc writes real equations (native Word/ODT equations,
        # MathML in EPUB, MathJax in HTML) that assistive technology reads.
        prepared = wrap_unicode_math(_remove_mathjax_header(text))
        if prepared != text:
            return from_format or "markdown", prepared
    return from_format, None


def _log_command(args: List[str], log_cb: Logger) -> None:
    if log_cb:
        shown = [Path(a).name if i == 0 else a for i, a in enumerate(args)]
        log_cb("[pandoc] " + " ".join(shlex.quote(a) for a in shown))


def _run_checked(args: List[str], log_cb: Logger, input_text: Optional[str] = None,
                 cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    proc = _run(args, input_text=input_text, cwd=cwd)
    err = proc.stderr.decode("utf-8", "replace").strip()
    if err and log_cb:
        for line in err.splitlines():
            log_cb(f"[pandoc] {line}")
    if proc.returncode != 0:
        raise RuntimeError(err or f"pandoc exited with code {proc.returncode}")
    return proc


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
    pandoc = _need_pandoc(pandoc)
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from_format = opts.from_format or detect_input_format(input_path) or None
    from_format, stdin_text = _prepare_input(input_path, from_format)

    if vision is not None and getattr(vision, "enabled", False):
        from . import vision as _vision

        if _vision.available(vision):
            return join_convert([input_path], output_path, opts, ocr_lang, log_cb, pandoc,
                                vision, _single=(from_format, stdin_text))
        if log_cb:
            log_cb("[vision] Picture descriptions skipped: "
                   + _vision.unavailable_reason(vision) + ".")

    args = build_args(pandoc, input_path, output_path, opts, from_format, ocr_lang)
    if stdin_text is None:
        args.append(str(input_path))
    _log_command(args, log_cb)
    _run_checked(args, log_cb, input_text=stdin_text, cwd=str(input_path.parent))
    if log_cb:
        log_cb(f"[pandoc] Saved → {output_path}")
    return output_path


def _read_ast(pandoc: str, input_path: Path, opts: PandocOptions, from_format: Optional[str],
              stdin_text: Optional[str], media: Optional[Path], flags) -> dict:
    """Read one document into pandoc's JSON format."""
    import json

    read = [pandoc]
    if from_format:
        base_from = po.base_format(from_format)
        fr = from_format
        if fr == base_from:
            fr += po.extension_suffix(opts.in_extensions.get(base_from))
        read += ["--from", fr]
    read += ["--to", "json"]
    if media is not None:
        read += ["--extract-media", str(media)]
    read += ["--resource-path", os.pathsep.join([str(input_path.parent), "."])]
    read += reader_args(opts, from_format, flags)
    if stdin_text is None:
        read.append(str(input_path))
    proc = _run_checked(read, None, input_text=stdin_text, cwd=str(input_path.parent))
    return json.loads(proc.stdout.decode("utf-8"))


def _unique_header_ids(blocks: list, seen: Dict[str, int]) -> None:
    """Give repeated heading ids a number (-2, -3) so links stay unambiguous."""
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("t") == "Header":
            attr = b["c"][1]
            ident = attr[0]
            if ident:
                n = seen.get(ident, 0) + 1
                seen[ident] = n
                if n > 1:
                    attr[0] = f"{ident}-{n}"
        elif b.get("t") in ("Div", "BlockQuote", "Figure"):
            inner = b.get("c")
            if isinstance(inner, list) and inner and isinstance(inner[-1], list):
                _unique_header_ids(inner[-1], seen)


def join_convert(
    inputs: Sequence[str | Path],
    output_path: str | Path,
    opts: PandocOptions,
    ocr_lang: Optional[str] = None,
    log_cb: Logger = None,
    pandoc: Optional[str] = None,
    vision=None,
    _single: Optional[Tuple[Optional[str], Optional[str]]] = None,
) -> Path:
    """Convert several documents (of any formats) into one output file.

    Each input is read into pandoc's JSON format, the documents are joined
    in order (the document information of the first one is kept), pictures
    are described when ``vision`` is on, and pandoc writes the result.
    """
    import json
    import tempfile

    from . import docimages

    pandoc = _need_pandoc(pandoc)
    flags = supported_flags(pandoc)
    inputs = [Path(p) for p in inputs]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    to = opts.to_format or "html"
    base_to = po.base_format(to)
    single = len(inputs) == 1

    with tempfile.TemporaryDirectory(prefix="pdfmd-pandoc-") as tmp:
        tmpdir = Path(tmp)
        blocks: list = []
        meta: Optional[dict] = None
        api = None
        base_dirs: List[Path] = []
        seen_ids: Dict[str, int] = {}
        for i, inp in enumerate(inputs, 1):
            if _single is not None:
                from_format, stdin_text = _single
            else:
                from_format = opts.from_format or detect_input_format(inp) or None
                from_format, stdin_text = _prepare_input(inp, from_format)
            base_from = po.base_format(from_format) or \
                {".rtf": "rtf", ".fb2": "fb2"}.get(inp.suffix.lower(), "")
            media: Optional[Path] = None
            tmp_name = "media" if single else f"media{i}"
            if base_from in CONTAINER_INPUTS:
                # Pictures inside Word, ODT, EPUB, PowerPoint and notebooks
                # are extracted: next to the output for text outputs (which
                # link to them), or to a temporary folder for binary outputs
                # (which embed them).
                if opts.extract_media and base_to not in BINARY_OUTPUTS:
                    media = output_path.parent / (output_path.stem + "_media")
                    if not single:
                        media = media / str(i)
                else:
                    media = tmpdir / tmp_name
            if not single and log_cb:
                log_cb(f"[pandoc] Reading {i} of {len(inputs)}: {inp.name}")
            ast = _read_ast(pandoc, inp, opts, from_format, stdin_text, media, flags)
            if media is not None and media.parent == tmpdir and media.is_dir():
                # Refer to temporary pictures by a short relative path so no
                # temporary folder name ends up inside the document.
                docimages.relocate_sources(ast.get("blocks", []), str(media), tmp_name + "/")
            base_dirs.append(inp.parent)
            if media is not None:
                base_dirs.append(media)
            if not single:
                _unique_header_ids(ast.get("blocks", []), seen_ids)
            blocks += ast.get("blocks", [])
            if meta is None:
                meta = ast.get("meta", {})
                api = ast.get("pandoc-api-version")
        doc = {"pandoc-api-version": api, "meta": meta or {}, "blocks": blocks}

        if vision is not None and getattr(vision, "enabled", False):
            vs = vision
            if not getattr(vs, "lang", ""):
                vs.lang = ocr_lang or "eng"
            try:
                n = docimages.describe_ast(doc, to, base_dirs + [tmpdir], vs, log_cb=log_cb)
                if log_cb and n:
                    log_cb(f"[vision] Described {n} picture{'s' if n != 1 else ''}.")
            except Exception as e:  # noqa: BLE001  (never fail a conversion over pictures)
                if log_cb:
                    log_cb(f"[vision] Picture descriptions skipped: {e}")

        doc_json = tmpdir / "document.json"
        doc_json.write_text(json.dumps(doc), encoding="utf-8")
        dirs = [tmpdir] + list(dict.fromkeys(p.parent for p in inputs))
        args = build_args(pandoc, inputs[0] if single else None, output_path, opts, "json",
                          ocr_lang, include_reader=False, flags=flags, resource_dirs=dirs,
                          page_title=None if single else output_path.stem)
        args.append(str(doc_json))
        _log_command(args, log_cb)
        _run_checked(args, log_cb, cwd=str(inputs[0].parent))
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
    "supported_flags",
    "list_input_formats",
    "list_output_formats",
    "list_highlight_styles",
    "list_extensions",
    "default_template",
    "default_data_file",
    "highlight_style_theme",
    "format_label",
    "output_extension",
    "detect_input_format",
    "build_args",
    "reader_args",
    "command_preview",
    "convert",
    "join_convert",
    "install_command",
]
