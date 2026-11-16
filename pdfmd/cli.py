"""Command-line interface for pdfmd.

Fast, local, privacy-first PDF → Markdown converter with table and math-aware
conversion (LaTeX-style equations, Unicode math, and text tables rendered as
Markdown).

Usage (basic):

  pdfmd input.pdf
  pdfmd input.pdf -o notes.md
  pdfmd *.pdf --ocr auto --stats

All processing happens locally. No uploads, no telemetry, no tracking.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from .models import Options
from .pipeline import pdf_to_markdown
from .mathjax import apply_mathjax, count_math


# ---------------------------------------------------------------------------
# Colour handling
# ---------------------------------------------------------------------------


@dataclass
class _Colors:
    ok: str
    warn: str
    err: str
    info: str
    reset: str


def _make_colors(enable: bool) -> _Colors:
    if not enable:
        return _Colors("", "", "", "", "")
    return _Colors(
        ok="\033[32m",      # green
        warn="\033[33m",    # yellow
        err="\033[31m",     # red
        info="\033[36m",    # cyan
        reset="\033[0m",
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    description = (
        "Convert PDF files to clean, Obsidian-ready Markdown with table and "
        "math-aware conversion.\n"
        "Runs fully offline: no uploads, no telemetry, no cloud dependencies."
    )

    epilog = r"""
Examples:

  # Basic conversion (writes input.md next to the PDF)
  pdfmd report.pdf

  # Choose an explicit output file
  pdfmd report.pdf -o report_notes.md

  # Auto-detect scanned pages and OCR as needed
  pdfmd scan.pdf --ocr auto

  # Force Tesseract OCR and export page images
  pdfmd book_scan.pdf --ocr tesseract --export-images

  # Preview only (first few pages) with stats
  pdfmd long_paper.pdf --preview-only --stats

  # Batch convert multiple PDFs into a folder
  pdfmd *.pdf --ocr auto -o out_md/

  # Quiet mode, non-interactive (good for scripts)
  pdfmd confidential.pdf --ocr auto --no-progress --quiet

  # Describe pictures and charts with the local AI vision model on the GPU
  pdfmd report.pdf --export-images --vision-device gpu

  # Any document pandoc reads (Word, EPUB, PowerPoint...), pictures described
  pdfmd slides.pptx --to docx

  # Describe a folder of photos into an accessible web page
  pdfmd --describe-photos "C:\\Photos\\Italy 2026" --album-format html

Picture descriptions:

  • A small open-weights vision model, running on this computer, describes
    photos, charts, graphs, maps and diagrams. With --export-images the
    description is the picture's alternative text; without it the description
    is written as a block quote ("> Image description: ...").
  • --vision-device auto uses a graphics card when one is found, gpu also
    uses integrated graphics, cpu never uses a graphics processor.
  • pdfmd --vision-status shows the engine, model and graphics processors;
    pdfmd --vision-update downloads a newer engine or model.

Tables and math:

  • Text tables are detected and rendered as GitHub-flavoured Markdown tables.
  • Common Unicode math, Greek letters, subscripts and superscripts are
    normalised to LaTeX-style math so expressions like E = mc², x₁₀², α + β³
    survive the round-trip as equations instead of broken text.
  • LaTeX-like math already present in the PDF is preserved and not escaped
    as normal Markdown text.

Security notes:

  • All processing happens on your machine.
  • Passwords are read interactively (no echo), never logged,
    and never sent to other processes via command-line arguments.
  • Output Markdown files are written unencrypted; protect them
    according to your environment's security requirements.
"""

    parser = argparse.ArgumentParser(
        prog="pdfmd",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "inputs",
        metavar="INPUT",
        nargs="*",  # CHANGED: '*' allows zero inputs (was '+')
        help=("Path(s) to input PDF file(s). Other documents (Word, EPUB,\n"
              "PowerPoint, HTML, ...) are converted with pandoc to --to\n"
              "(default: GitHub Markdown), with their pictures described."),
    )

    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT",
        help=(
            "Output path. For a single input this is an .md file.\n"
            "For multiple inputs this is treated as an output directory."
        ),
    )

    parser.add_argument(
        "--ocr",
        choices=["off", "auto", "tesseract", "ocrmypdf"],
        default="auto",
        help=(
            "OCR mode (default: auto):\n"
            "  off        - use native text only\n"
            "  auto       - detect scanned pages and OCR as needed\n"
            "  tesseract  - force page-by-page Tesseract OCR\n"
            "  ocrmypdf   - use OCRmyPDF for high-fidelity layout"
        ),
    )

    parser.add_argument(
        "--lang",
        default="eng",
        help=(
            "Tesseract language code(s) for OCR (default: eng).\n"
            "Use a Tesseract language code, e.g. 'deu' for German,\n"
            "'fra' for French, 'jpn' for Japanese.\n"
            "Combine with '+' for multiple: 'eng+fra'.\n"
            "Only used when --ocr is not 'off'."
        ),
    )

    parser.add_argument(
        "--export-images",
        action="store_true",
        help="Export images to an _assets/ folder and append Markdown references.",
    )

    parser.add_argument(
        "--describe-images",
        choices=["auto", "off"],
        default="auto",
        help=(
            "Describe pictures and charts with the local AI vision model\n"
            "(default: auto = when the model is installed). Exported images get\n"
            "the description as alternative text; otherwise it is written as a\n"
            "block quote."
        ),
    )

    parser.add_argument(
        "--vision-device",
        default="auto",
        metavar="DEVICE",
        help=(
            "Processor for the vision model (default: auto):\n"
            "  auto   - CUDA on an NVIDIA card if the CUDA engine is installed,\n"
            "           otherwise a graphics card with Vulkan, otherwise the CPU\n"
            "  cuda   - the NVIDIA card with CUDA (download the CUDA engine with\n"
            "           --vision-update --vision-device cuda)\n"
            "  vulkan - any graphics processor with Vulkan (NVIDIA, AMD, Intel,\n"
            "           including integrated graphics); 'gpu' means the same\n"
            "  cpu    - never use a graphics processor\n"
            "  a device name from --vision-status, e.g. Vulkan1 - that GPU"
        ),
    )

    parser.add_argument(
        "--vision-model",
        metavar="ID",
        default="",
        help="Vision model to use (see --vision-status). Default: the recommended model.",
    )

    parser.add_argument(
        "--vision-status",
        action="store_true",
        help="Show the vision engine, models and graphics processors, then exit.",
    )

    parser.add_argument(
        "--vision-update",
        action="store_true",
        help=(
            "Download a newer vision engine or model (or the --vision-model\n"
            "chosen), checked against published SHA-256 checksums, then exit."
        ),
    )

    parser.add_argument(
        "--describe-photos",
        metavar="FOLDER",
        help=(
            "Describe every photo in FOLDER with the vision model and write\n"
            "an accessible album (-o sets the file; default: 'Photo\n"
            "descriptions.html' in the folder)."
        ),
    )

    parser.add_argument(
        "--album-format",
        choices=["html", "markdown"],
        default="html",
        help="Album file format for --describe-photos (default: html).",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="With --describe-photos, also describe photos in subfolders.",
    )

    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert '---' page break markers between pages in the output.",
    )

    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Only process the first few pages (useful for quick inspection).",
    )

    parser.add_argument(
        "--mathjax",
        choices=["ask", "yes", "no"],
        default="ask",
        help=(
            "Accessible math (default: ask). When a document contains math,\n"
            "MathJax makes it readable by screen readers (speech, Braille,\n"
            "keyboard exploration). It adds a MathJax loader to the Markdown\n"
            "file and writes an accessible HTML copy next to it.\n"
            "  ask  - ask after each file that contains math (answer defaults\n"
            "         to yes; without a terminal this behaves like 'yes')\n"
            "  yes  - always enable MathJax when math is found\n"
            "  no   - never enable MathJax"
        ),
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help=(
            "Also write an accessible HTML copy of every converted file\n"
            "(document language, headings, table headers, and MathJax math\n"
            "when enabled)."
        ),
    )

    parser.add_argument(
        "--to",
        metavar="FORMAT",
        help=(
            "Also convert the Markdown with pandoc to FORMAT, for example\n"
            "docx, epub, html, latex, odt, pptx, rst, typst or pdf. Any pandoc\n"
            "output format works (see `pandoc --list-output-formats`).\n"
            "Requires pandoc. Math becomes native equations (Word/ODT),\n"
            "MathML (EPUB) or MathJax (HTML)."
        ),
    )

    parser.add_argument(
        "--pandoc-args",
        metavar="ARGS",
        default="",
        help=(
            "Extra pandoc options, quoted as one argument, for example\n"
            "--pandoc-args \"--toc --citeproc --bibliography refs.bib\"."
        ),
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the terminal progress bar.",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-error messages; only show errors.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity. Use -v for more logs, -vv for debug-level detail.",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help=(
            "After conversion, print basic stats "
            "(words, headings, tables, lists)."
        ),
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable coloured output.",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )

    return parser


# ---------------------------------------------------------------------------
# Options helper
# ---------------------------------------------------------------------------


def _make_options(args: argparse.Namespace) -> Options:
    opts = Options()

    # Extraction / OCR
    opts.ocr_mode = args.ocr
    opts.ocr_lang = args.lang or "eng"
    opts.preview_only = bool(args.preview_only)

    # Rendering / output
    opts.insert_page_breaks = bool(args.page_breaks)
    opts.export_images = bool(args.export_images)

    # Picture descriptions (local vision model)
    opts.describe_images = args.describe_images != "off"
    opts.vision_device = _device_code(args.vision_device)
    opts.vision_model = args.vision_model or ""

    # Transform heuristics remain at their defaults; they can be exposed later.
    return opts


# ---------------------------------------------------------------------------
# Progress bar with ETA
# ---------------------------------------------------------------------------


def _make_progress_cb(
    file_label: str,
    colors: _Colors,
    args: argparse.Namespace,
) -> Callable[[int, int], None]:
    start = time.time()

    def progress_cb(done: int, total: int) -> None:
        if args.no_progress or args.quiet:
            return

        # In the pipeline, progress_cb is called with (pct, 100) where pct is 0—100.
        if total == 100 and 0 <= done <= 100:
            pct = int(done)
        else:
            pct = int(done * 100 / total) if total > 0 else 0
        pct = max(0, min(100, pct))

        elapsed = time.time() - start
        eta_str = "ETA: --"
        if pct > 0 and elapsed > 0:
            remaining = elapsed * (100 - pct) / pct
            if remaining < 90:
                eta_str = f"ETA: {int(remaining)}s"
            else:
                eta_str = f"ETA: {int(remaining // 60)}m"

        bar_width = 24
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        line = f"\r{colors.info}[{bar}] {pct:3d}% {eta_str}  {file_label}{colors.reset}"
        sys.stderr.write(line)
        sys.stderr.flush()

        if pct >= 100:
            sys.stderr.write("\n")
            sys.stderr.flush()

    return progress_cb


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


@dataclass
class ConversionStats:
    words: int
    headings: int
    tables: int
    lists: int


def _is_table_header_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and len(s) > 3


def _is_table_sep_line(line: str) -> bool:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    inner = s.strip("|").replace("-", "").replace(":", "").strip()
    return inner == ""


def _compute_stats(md_path: Path) -> ConversionStats:
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return ConversionStats(words=0, headings=0, tables=0, lists=0)

    lines = text.splitlines()

    # Simple word count
    words = len(re.findall(r"\w+", text))

    # Headings: lines starting with '#'
    headings = sum(1 for ln in lines if ln.lstrip().startswith("#"))

    # Lists: lines starting with -, *, +
    lists = sum(
        1
        for ln in lines
        if ln.lstrip().startswith("- ")
        or ln.lstrip().startswith("* ")
        or ln.lstrip().startswith("+ ")
    )

    # Tables: header + separator pairs
    tables = 0
    i = 0
    n = len(lines)
    while i < n - 1:
        if _is_table_header_line(lines[i]) and _is_table_sep_line(lines[i + 1]):
            tables += 1
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                i += 1
            continue
        i += 1

    return ConversionStats(words=words, headings=headings, tables=tables, lists=lists)


def _print_stats(path: Path, stats: ConversionStats, colors: _Colors) -> None:
    sys.stderr.write(
        f"{colors.info}Stats for {path.name}:{colors.reset}\n"
        f"  Words:     {stats.words}\n"
        f"  Headings:  {stats.headings}\n"
        f"  Tables:    {stats.tables}\n"
        f"  Lists:     {stats.lists}\n"
    )
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Core conversion for a single file
# ---------------------------------------------------------------------------


def _run_single(
    inp: Path,
    outp: Path,
    opts: Options,
    args: argparse.Namespace,
    colors: _Colors,
) -> bool:
    """Run conversion for one input/output pair.

    Returns True on success, False on failure.
    """
    if not inp.is_file():
        if not args.quiet:
            sys.stderr.write(
                f"{colors.err}Error:{colors.reset} input file not found: {inp}\n"
            )
        return False

    if not args.quiet:
        sys.stderr.write(
            f"{colors.info}Converting{colors.reset} {inp} "
            f"→ {colors.ok}{outp}{colors.reset}\n"
        )
        sys.stderr.flush()

    # Decide logging callback based on verbosity / quiet
    if args.quiet:
        log_cb: Optional[Callable[[str], None]] = lambda _msg: None  # silence engine logs
    elif args.verbose >= 1:
        def log_cb(msg: str) -> None:
            sys.stderr.write(f"{colors.info}{msg}{colors.reset}\n")
    else:
        log_cb = None

    progress_cb = _make_progress_cb(inp.name, colors, args)

    password: Optional[str] = None  # kept local, never persisted

    def run_once(pdf_password: Optional[str]) -> None:
        pdf_to_markdown(
            str(inp),
            str(outp),
            opts,
            progress_cb=progress_cb,
            log_cb=log_cb,
            pdf_password=pdf_password,
        )

    try:
        # First attempt with no password (or whatever we have)
        run_once(password)
        return True

    except Exception as exc:
        # Look for password / encryption related errors
        lower = str(exc).lower()
        password_keywords = [
            "password required",
            "password is required",
            "incorrect pdf password",
            "wrong password",
            "cannot decrypt",
            "encrypted",
        ]
        needs_password = any(kw in lower for kw in password_keywords)

        if not needs_password:
            if not args.quiet:
                sys.stderr.write(f"{colors.err}Error:{colors.reset} {exc}\n")
                if args.verbose >= 2:
                    traceback.print_exc(file=sys.stderr)
            return False

        # Encrypted PDF, interactive password prompt required.
        if not sys.stdin.isatty():
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Error:{colors.reset} "
                    "PDF is password protected and interactive input is not available.\n"
                )
            return False

        try:
            password = getpass.getpass(
                "PDF is password protected. Enter password (input will be hidden): "
            )
        except Exception as e_input:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Error reading password:{colors.reset} {e_input}\n"
                )
            return False

        if not password:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.warn}No password provided; skipping file.{colors.reset}\n"
                )
            return False

        try:
            run_once(password)
            return True
        except Exception as exc2:
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Error after password attempt:{colors.reset} {exc2}\n"
                )
                if args.verbose >= 2:
                    traceback.print_exc(file=sys.stderr)
            return False

    finally:
        # Best-effort hygiene: drop any reference to the password.
        password = None


# ---------------------------------------------------------------------------
# Accessible math (MathJax) post-processing
# ---------------------------------------------------------------------------


def _accessible_math(
    outp: Path, opts: Options, args: argparse.Namespace, colors: _Colors
) -> None:
    """Offer MathJax when the converted file contains math; write HTML copy."""
    try:
        md = outp.read_text(encoding="utf-8")
    except Exception:
        return

    n_math = count_math(md)
    enable = False
    if n_math and args.mathjax == "yes":
        enable = True
    elif n_math and args.mathjax == "ask":
        if sys.stdin.isatty():
            try:
                answer = input(
                    f"{outp.name} contains {n_math} math expression(s). "
                    "Enable MathJax so screen readers can read the math? [Y/n] "
                )
            except EOFError:
                answer = ""
            enable = answer.strip().lower() not in ("n", "no")
        else:
            enable = True

    if not enable and not args.html:
        return

    try:
        html_path = apply_mathjax(
            outp, ocr_lang=opts.ocr_lang, enable_mathjax=enable, write_html=True
        )
    except Exception as exc:
        if not args.quiet:
            sys.stderr.write(f"{colors.err}Could not write accessible output:{colors.reset} {exc}\n")
        return

    if not args.quiet:
        if enable:
            sys.stderr.write(f"{colors.ok}MathJax enabled{colors.reset} for {outp.name}.\n")
        if html_path:
            sys.stderr.write(f"{colors.ok}Accessible HTML:{colors.reset} {html_path}\n")


def _pandoc_export(outp: Path, opts: Options, args: argparse.Namespace, colors: _Colors) -> bool:
    """Convert the Markdown output with pandoc (``--to``). Returns success."""
    from . import pandoc_support as ps

    popts = ps.PandocOptions(to_format=args.to, extra_args=args.pandoc_args)
    dest = outp.with_suffix(ps.output_extension(args.to))
    if dest == outp:
        dest = outp.with_name(outp.stem + "_pandoc" + outp.suffix)
    def log(msg: str) -> None:
        sys.stderr.write(f"{colors.info}{msg}{colors.reset}\n")

    verbose = args.verbose >= 1 and not args.quiet
    try:
        ps.convert(outp, dest, popts, ocr_lang=opts.ocr_lang, log_cb=log if verbose else None,
                   vision=_vision_settings(opts))
    except Exception as exc:
        sys.stderr.write(f"{colors.err}Pandoc error:{colors.reset} {exc}\n")
        return False
    if not args.quiet:
        sys.stderr.write(f"{colors.ok}Pandoc:{colors.reset} {dest}\n")
    return True


# ---------------------------------------------------------------------------
# Vision model: status, updates, documents and photo albums
# ---------------------------------------------------------------------------


def _device_code(value: Optional[str]) -> str:
    """auto / cuda / vulkan (= gpu) / cpu (any case), or a device name such as Vulkan1."""
    dev = (value or "auto").strip()
    if dev.lower() == "vulkan":
        return "gpu"
    if dev.lower() in ("auto", "cuda", "gpu", "cpu"):
        return dev.lower()
    if dev.lower().startswith("dev:"):
        dev = dev[4:]
    return "dev:" + dev


def _vision_settings(opts: Options):
    from . import vision

    return vision.VisionSettings(enabled=opts.describe_images, device=opts.vision_device,
                                 model_id=opts.vision_model, lang=opts.ocr_lang)


def _vision_status(args: argparse.Namespace, colors: _Colors) -> int:
    from . import vision

    rt = vision.find_runtime()
    print("Vision engine: " + (f"llama.cpp {rt.build or '(unknown build)'} ({rt.source}) at {rt.server}"
                               if rt else "not installed (run pdfmd --vision-update)"))
    models = vision.installed_models()
    rec = vision.resolve_model(args.vision_model or "")
    if models:
        print("Installed models:")
        for m in models.values():
            mark = " (in use)" if rec and rec.id == m.id else ""
            print(f"  {m.id}: {m.name}, {m.size / 1e9:.2f} GB, {m.source}{mark}")
    else:
        print("Installed models: none (run pdfmd --vision-update)")
    gpus = vision.nvidia_gpus()
    cuda = vision.find_cuda_runtime()
    if gpus:
        g = gpus[0]
        if cuda:
            state = f"CUDA engine ({cuda.backend}, llama.cpp {cuda.build}) installed."
        elif vision.cuda_variant():
            state = "CUDA engine not installed (pdfmd --vision-update --vision-device cuda)."
        else:
            state = "driver too old for CUDA; update it from nvidia.com."
        print(f"NVIDIA card: {g.name} (compute capability {g.compute_capability}, "
              f"driver {g.driver}); {state}")
    if rt:
        devs = vision.list_devices(rt) + (vision.list_devices(cuda) if cuda else [])
        print("Graphics processors:" if devs else "Graphics processors: none found (the CPU is used)")
        for d in devs:
            print(f"  {d.name}: {d.label()}")
        if rec:
            s = vision.VisionSettings(device=_device_code(args.vision_device),
                                      model_id=args.vision_model or "")
            _, dev, note = vision.choose_engine(s, rec)
            print(f"With --vision-device {args.vision_device}: " + (dev.label() if dev else "CPU")
                  + (f" ({note})" if note else ""))
    print("Models you can download:")
    for m in vision.builtin_catalog().get("models", []):
        size = sum(int(f.get("size", 0)) for f in m["files"].values()) / 1e9
        print(f"  {m['id']}: {m['name']} ({size:.1f} GB, about {m.get('ram_gb', '?')} GB of memory)")
    return 0


def _vision_update(args: argparse.Namespace, colors: _Colors) -> int:
    from . import vision

    try:
        catalog = vision.fetch_catalog()
    except Exception as exc:
        sys.stderr.write(f"{colors.warn}Could not read the online catalog ({exc}); "
                         f"using the built-in one.{colors.reset}\n")
        catalog = vision.builtin_catalog()
    plan = vision.plan_update(catalog, args.vision_model or "", _device_code(args.vision_device))
    if not plan.needed:
        print("The vision engine and model are up to date.")
        return 0
    for note in plan.notes:
        print(note)
    print(f"Downloading {plan.download_bytes / 1e6:.0f} MB...")
    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 0
        if pct != last[0] and not args.no_progress:
            last[0] = pct
            sys.stderr.write(f"\r  {pct:3d}%")
            sys.stderr.flush()

    try:
        if plan.runtime:
            vision.install_runtime(plan.runtime, plan.runtime_build, progress, log_cb=print)
            sys.stderr.write("\n")
        if plan.model:
            vision.install_model(plan.model, progress, log_cb=print)
            sys.stderr.write("\n")
        if plan.cuda:
            vision.install_cuda_runtime(plan.cuda, plan.cuda_variant, plan.runtime_build, progress,
                                        log_cb=print)
            sys.stderr.write("\n")
    except Exception as exc:
        sys.stderr.write(f"\n{colors.err}Update failed:{colors.reset} {exc}\n")
        return 1
    print(f"{colors.ok}Vision model ready.{colors.reset}")
    return 0


def _describe_photos(args: argparse.Namespace, opts: Options, colors: _Colors) -> int:
    from . import album, vision

    folder = Path(args.describe_photos).expanduser()
    if not folder.is_dir():
        sys.stderr.write(f"{colors.err}Error:{colors.reset} not a folder: {folder}\n")
        return 1
    out = (Path(args.output).expanduser() if args.output
           else album.default_output(folder, args.album_format))
    settings = _vision_settings(opts)
    settings.enabled = True

    def log(msg: str) -> None:
        if not args.quiet:
            sys.stderr.write(f"{msg}\n")

    try:
        path = album.describe_folder(folder, out, args.album_format, settings,
                                     recursive=args.recursive, log_cb=log)
    except Exception as exc:
        sys.stderr.write(f"{colors.err}Error:{colors.reset} {exc}\n")
        return 1
    finally:
        vision.shutdown()
    if not args.quiet:
        sys.stderr.write(f"{colors.ok}Album:{colors.reset} {path}\n")
    return 0


def _convert_document(inp: Path, out_arg: Optional[Path], multiple: bool, opts: Options,
                      args: argparse.Namespace, colors: _Colors) -> bool:
    """A non-PDF input: convert it with pandoc (pictures described)."""
    from . import pandoc_support as ps

    to = args.to or "gfm"
    ext = ps.output_extension(to)
    if out_arg is None:
        dest = inp.with_suffix(ext)
    elif multiple or out_arg.is_dir():
        dest = out_arg / (inp.stem + ext)
    else:
        dest = out_arg
    if dest.resolve() == inp.resolve():
        dest = dest.with_name(dest.stem + "_converted" + dest.suffix)
    if not args.quiet:
        sys.stderr.write(f"{colors.info}Converting{colors.reset} {inp} -> {colors.ok}{dest}{colors.reset}\n")
    verbose = args.verbose >= 1 and not args.quiet

    def log(msg: str) -> None:
        sys.stderr.write(f"{colors.info}{msg}{colors.reset}\n")

    try:
        ps.convert(inp, dest, ps.PandocOptions(to_format=to, extra_args=args.pandoc_args),
                   ocr_lang=opts.ocr_lang, log_cb=log if verbose else None,
                   vision=_vision_settings(opts))
    except Exception as exc:
        sys.stderr.write(f"{colors.err}Error:{colors.reset} {exc}\n")
        return False
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Never crash on characters the console code page can't show (for
    # example dashes on Windows code page 1252).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Version info - CHECK THIS FIRST before requiring inputs
    try:
        from . import __version__ as _VERSION
    except Exception:
        _VERSION = "unknown"

    if args.version:
        print(f"pdfmd {_VERSION}")
        return 0

    # Colour configuration
    enable_color = sys.stderr.isatty() and not args.no_color
    colors = _make_colors(enable_color)

    if args.quiet:
        # Quiet suppresses verbosity
        args.verbose = 0

    opts = _make_options(args)

    if args.vision_status:
        return _vision_status(args, colors)
    if args.vision_update:
        return _vision_update(args, colors)
    if args.describe_photos:
        return _describe_photos(args, opts, colors)

    # NOW check if inputs were provided
    if not args.inputs:
        parser.print_help()
        return 1

    # Prepare inputs
    inputs: List[Path] = [Path(p).expanduser() for p in args.inputs]

    # Interpret output argument
    out_arg = Path(args.output).expanduser() if args.output else None
    multiple = len(inputs) > 1

    if multiple and out_arg is not None and out_arg.exists() and not out_arg.is_dir():
        sys.stderr.write(
            f"{colors.err}Error:{colors.reset} when converting multiple inputs, "
            f"--output must be a directory.\n"
        )
        return 1

    if multiple and out_arg is not None and not out_arg.exists():
        try:
            out_arg.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            sys.stderr.write(
                f"{colors.err}Error creating output directory:{colors.reset} {exc}\n"
            )
            return 1

    successes = 0
    failures = 0

    for inp in inputs:
        if not inp.is_file():
            if not args.quiet:
                sys.stderr.write(
                    f"{colors.err}Error:{colors.reset} input file not found: {inp}\n"
                )
            failures += 1
            continue

        if inp.suffix.lower() != ".pdf":
            if _convert_document(inp, out_arg, multiple, opts, args, colors):
                successes += 1
            else:
                failures += 1
            continue

        if out_arg is None:
            outp = inp.with_suffix(".md")
        else:
            if multiple or out_arg.is_dir():
                outp = out_arg / (inp.stem + ".md")
            else:
                outp = out_arg

        ok = _run_single(inp, outp, opts, args, colors)

        if ok:
            _accessible_math(outp, opts, args, colors)
            if args.to and not _pandoc_export(outp, opts, args, colors):
                failures += 1
            successes += 1
            if args.stats:
                stats = _compute_stats(outp)
                _print_stats(outp, stats, colors)
        else:
            failures += 1

    try:
        from . import vision

        vision.shutdown()
    except Exception:
        pass

    if not args.quiet:
        if failures == 0:
            sys.stderr.write(
                f"{colors.ok}Done.{colors.reset} "
                f"{successes} file(s) converted successfully.\n"
            )
        else:
            sys.stderr.write(
                f"{colors.err}Finished with errors.{colors.reset} "
                f"{successes} succeeded, {failures} failed.\n"
            )
        sys.stderr.flush()

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())