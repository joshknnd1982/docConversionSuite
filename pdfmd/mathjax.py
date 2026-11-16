"""Accessible math output for pdfmd.

pdfmd writes math as LaTeX inside Markdown (``$...$`` for inline math and
``$$ ... $$`` for display math). LaTeX source is hard to follow with a screen
reader, so when a converted document contains math this module can:

* add a small MathJax loader to the top of the Markdown file, so Markdown
  viewers that allow HTML render the math as accessible math, and
* write an accessible HTML version of the document next to the Markdown
  file.

MathJax 4 turns every expression into accessible math: screen readers speak
it in natural language, it can be read in Braille, and users can explore
complex expressions piece by piece with the arrow keys (the MathJax
"explorer"). The HTML page also declares the document language, keeps the
heading structure, and uses real table header cells.

Note: the generated files load MathJax from the jsDelivr CDN when they are
opened in a browser. The conversion itself stays fully offline.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import List, Optional, Tuple

MATHJAX_VERSION = "4.1.3"
MATHJAX_URL = f"https://cdn.jsdelivr.net/npm/mathjax@{MATHJAX_VERSION}/tex-mml-chtml.js"

# Marker that makes add_mathjax_to_markdown() idempotent.
_MD_MARKER = "<!-- pdfmd:mathjax -->"

# MathJax configuration. The a11y extensions (speech, Braille, explorer) are
# on by default in MathJax 4's combined components; we only declare the TeX
# delimiters. The Markdown header must accept $...$ because that is what the
# Markdown contains.
_MATHJAX_CONFIG = (
    "window.MathJax = {"
    "tex: {inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], "
    "displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], "
    "processEscapes: true}"
    "};"
)

# The HTML page converts every expression to \(...\) or \[...\], so plain
# dollar signs (prices) in the text are never treated as math there.
_MATHJAX_CONFIG_HTML = (
    "window.MathJax = {"
    "tex: {inlineMath: [['\\\\(', '\\\\)']], "
    "displayMath: [['\\\\[', '\\\\]']]}"
    "};"
)

# ---------------------------------------------------------------------------
# Math detection
# ---------------------------------------------------------------------------

# Order matters: display forms first so their $ signs aren't taken as inline.
_DISPLAY_DOLLAR = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
_DISPLAY_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_INLINE_PAREN = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
# Inline $...$: no whitespace just inside the delimiters and no digit right
# after the closing $, so prices like "$5 and $10" are not mistaken for math.
_INLINE_DOLLAR = re.compile(r"(?<![\\$\w])\$(?=\S)([^$\n]+?)(?<=\S)(?<!\\)\$(?![\d$])")

_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.DOTALL | re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`\n]+`")


def _strip_code(md: str) -> str:
    """Blank out code so math-looking text inside code is ignored."""
    md = _FENCE.sub(lambda m: " " * len(m.group(0)), md)
    return _INLINE_CODE.sub(lambda m: " " * len(m.group(0)), md)


def count_delimited_math(md: str) -> int:
    """Number of math expressions already wrapped in LaTeX delimiters."""
    text = _strip_code(md)
    total = 0
    for rx in (_DISPLAY_DOLLAR, _DISPLAY_BRACKET, _INLINE_PAREN):
        total += len(rx.findall(text))
        text = rx.sub(" ", text)
    total += len(_INLINE_DOLLAR.findall(text))
    return total


def count_math(md: str) -> int:
    """Return the number of math expressions in Markdown text.

    Counts LaTeX-delimited math and Unicode math written inside ordinary
    sentences (for example "E = mc²" or "α + β³ = γ").
    """
    return count_delimited_math(md) + count_unicode_math(md)


# ---------------------------------------------------------------------------
# Unicode math inside prose → LaTeX
# ---------------------------------------------------------------------------
#
# The engine wraps standalone equation lines in $$ ... $$, but math inside a
# sentence ("Einstein's relation E = mc² links ...") stays as Unicode text,
# which MathJax cannot see. When MathJax is enabled we find those
# expressions, convert them to LaTeX and wrap them in $...$ so that they are
# rendered and spoken as math too.

from .equations import (  # noqa: E402  (kept next to the code that uses it)
    _GREEK_MAP,
    _SUBSCRIPT_MAP,
    _SUPERSCRIPT_MAP,
    _UNICODE_MATH_MAP,
)

_SUP = {**_SUPERSCRIPT_MAP, "ⁿ": "n", "ⁱ": "i"}
_SUB = {
    **_SUBSCRIPT_MAP,
    "ᵢ": "i", "ⱼ": "j", "ₙ": "n", "ₐ": "a", "ₑ": "e", "ₒ": "o", "ₓ": "x",
    "ₖ": "k", "ₘ": "m", "ₚ": "p", "ₛ": "s", "ₜ": "t", "ₗ": "l", "ₕ": "h",
}
_SYM = {
    **_GREEK_MAP,
    **_UNICODE_MATH_MAP,
    "…": r"\ldots", "−": "-", "⋅": r"\cdot", "∙": r"\cdot", "∘": r"\circ",
    "∅": r"\emptyset", "∀": r"\forall", "∃": r"\exists", "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}", "ℤ": r"\mathbb{Z}", "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}",
}
# Characters that on their own mark a token as math. Arrows, the middle dot
# and "not" are left out because ordinary prose uses them too.
_STRONG = (set(_SUP) | set(_SUB) | set(_SYM)) - {"·", "→", "←", "¬", "…", "−"}
_ASCII_MATH = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()[]{}+-=/<>^|.,'!")
_OPERATOR_TOKENS = {"=", "+", "-", "−", "<", ">", "/", "×", "÷", "±", "·", "⋅", "→", "≤", "≥",
                    "≠", "≈", "≡", "∈", "⇒", "⇔", "…", "*"}
_RELATIONS = {"=", "<", ">", "≤", "≥", "≠", "≈", "≡", "∈", "⇒", "⇔", "→"}
_TRAILING_PUNCT = ".,;:!?"


def unicode_math_to_latex(expr: str) -> str:
    """Convert a Unicode math expression to LaTeX ("α + β³" → "\\alpha + \\beta^3")."""
    out: List[str] = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in _SUP or ch in _SUB:
            table, mark = (_SUP, "^") if ch in _SUP else (_SUB, "_")
            run: List[str] = []
            while i < n and expr[i] in table:
                run.append(table[expr[i]])
                i += 1
            text = "".join(run)
            out.append(f"{mark}{{{text}}}" if len(text) > 1 else mark + text)
            continue
        if ch in _SYM:
            cmd = _SYM[ch]
            out.append(cmd)
            # "\alpha" followed by a letter would become "\alphax".
            if cmd.startswith("\\") and cmd[-1].isalpha() and i + 1 < n and expr[i + 1].isalpha():
                out.append(" ")
            i += 1
            continue
        out.append(" " if ch in "   " else ch)  # odd spaces → plain space
        i += 1
    return "".join(out)


def _classify(token: str) -> Tuple[bool, bool]:
    """Return (is_math_token, is_strong) for a whitespace-delimited token."""
    core = token.rstrip(_TRAILING_PUNCT) or token
    if any(c in core for c in "$\\`*_#|"):
        return False, False
    if core in _OPERATOR_TOKENS:
        return True, core not in {"-", "/", "*", "…", "·", "→"}
    if not all(c in _ASCII_MATH or c in _SUP or c in _SUB or c in _SYM for c in core):
        return False, False
    if any(c in _STRONG for c in core):
        return len(core) <= 24, True
    if re.fullmatch(r"[A-Za-z]", core):
        return True, False
    if re.fullmatch(r"\d+(?:\.\d+)?", core):
        return True, False
    if len(core) <= 10 and any(c in "+-=/<>^" for c in core) and re.search(r"[A-Za-z0-9]", core):
        return True, False
    return False, False


def _math_runs(line: str) -> List[Tuple[int, int]]:
    """Find (start, end) character ranges of Unicode math inside a line."""
    tokens = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", line)]
    runs: List[Tuple[int, int]] = []
    i = 0
    while i < len(tokens):
        if not _classify(tokens[i][2])[0]:
            i += 1
            continue
        j = i
        group = []
        while j < len(tokens) and _classify(tokens[j][2])[0]:
            group.append(tokens[j])
            core = tokens[j][2]
            j += 1
            # Punctuation after a token ends the expression ("x², then").
            if core.rstrip(_TRAILING_PUNCT) != core:
                break
        i = j

        # Trim lone letters at either end that aren't attached to an operator
        # ("a" in "a² + b² = c² a circle").
        def is_letter(tok: str) -> bool:
            return bool(re.fullmatch(r"[A-Za-z]", tok.rstrip(_TRAILING_PUNCT)))

        while len(group) > 1 and is_letter(group[-1][2]) and group[-2][2] not in _OPERATOR_TOKENS:
            group.pop()
        while len(group) > 1 and is_letter(group[0][2]) and group[1][2] not in _OPERATOR_TOKENS:
            group.pop(0)
        if not group:
            continue

        words = [g[2].rstrip(_TRAILING_PUNCT) or g[2] for g in group]
        strong = any(_classify(g[2])[1] for g in group)
        has_relation = any(w in _RELATIONS for w in words)
        if not (strong or (has_relation and len(group) >= 3)):
            continue
        # A lone operator or number is never worth wrapping.
        if len(group) == 1 and not any(c in _STRONG for c in words[0]):
            continue
        start = group[0][0]
        last = group[-1][2]
        end = group[-1][0] + len(last.rstrip(_TRAILING_PUNCT) or last)
        runs.append((start, end))
    return runs


def _iter_prose_lines(md: str):
    """Yield (index, line, is_prose) skipping code, HTML and existing math."""
    in_fence = False
    in_display = False
    for idx, line in enumerate(md.split("\n")):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            yield idx, line, False
            continue
        if stripped == "$$" or (stripped.startswith("$$") and stripped.count("$$") == 1):
            in_display = not in_display
            yield idx, line, False
            continue
        prose = not (in_fence or in_display or stripped.startswith("<") or "`" in line)
        yield idx, line, prose


# Math that is already delimited inside a line; left untouched.
_EXISTING_MATH = re.compile(
    r"\$\$.+?\$\$|\\\(.+?\\\)|\\\[.+?\\\]|" + _INLINE_DOLLAR.pattern
)


def _prose_segments(line: str) -> List[Tuple[int, int]]:
    """(start, end) ranges of a line that are not already math."""
    segs: List[Tuple[int, int]] = []
    pos = 0
    for m in _EXISTING_MATH.finditer(line):
        segs.append((pos, m.start()))
        pos = m.end()
    segs.append((pos, len(line)))
    return [(a, b) for a, b in segs if b > a]


def _line_runs(line: str) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    for a, b in _prose_segments(line):
        runs.extend((a + s, a + e) for s, e in _math_runs(line[a:b]))
    return runs


def count_unicode_math(md: str) -> int:
    """Number of Unicode math expressions written inside ordinary text."""
    return sum(len(_line_runs(line)) for _, line, prose in _iter_prose_lines(md) if prose)


_STRAY_DOLLAR = re.compile(r"(?<!\\)\$")


def wrap_unicode_math(md: str, escape_dollars: bool = True) -> str:
    """Prepare Markdown for MathJax.

    * Wraps Unicode math inside prose as $...$ LaTeX so MathJax renders it.
    * With ``escape_dollars``, escapes dollar signs that are not math
      ("costs $5 and $10" → "costs \\$5 and \\$10"), so MathJax doesn't
      read the text between two prices as an equation. ``\\$`` displays as
      a plain dollar sign in Markdown and in MathJax.
    """
    lines = md.split("\n")
    for idx, line, prose in _iter_prose_lines(md):
        if not prose:
            continue
        parts: List[str] = []
        pos = 0
        for a, b in _prose_segments(line):
            parts.append(line[pos:a])  # existing math, untouched
            seg = line[a:b]
            out: List[str] = []
            last = 0
            for s, e in _math_runs(seg):
                text = seg[last:s]
                out.append(_STRAY_DOLLAR.sub(r"\\$", text) if escape_dollars else text)
                out.append("$" + unicode_math_to_latex(seg[s:e]) + "$")
                last = e
            tail = seg[last:]
            out.append(_STRAY_DOLLAR.sub(r"\\$", tail) if escape_dollars else tail)
            parts.append("".join(out))
            pos = b
        parts.append(line[pos:])
        lines[idx] = "".join(parts)
    return "\n".join(lines)


def has_mathjax(md: str) -> bool:
    return _MD_MARKER in md


# ---------------------------------------------------------------------------
# Markdown header
# ---------------------------------------------------------------------------


def mathjax_markdown_header() -> str:
    return (
        f"{_MD_MARKER}\n"
        "<!-- MathJax makes the math in this file accessible (speech, Braille and "
        "keyboard exploration) in Markdown viewers that allow HTML. -->\n"
        f"<script>{_MATHJAX_CONFIG}</script>\n"
        f'<script defer src="{MATHJAX_URL}"></script>\n\n'
    )


def add_mathjax_to_markdown(md: str) -> str:
    """Return *md* with the MathJax loader prepended (only once)."""
    if has_mathjax(md):
        return md
    return mathjax_markdown_header() + md


def _remove_mathjax_header(md: str) -> str:
    if not has_mathjax(md):
        return md
    head = mathjax_markdown_header()
    if md.startswith(head):
        return md[len(head):]
    return md.replace(_MD_MARKER, "", 1)


# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------

_TESS_TO_BCP47 = {
    "eng": "en", "deu": "de", "fra": "fr", "spa": "es", "ita": "it",
    "por": "pt", "nld": "nl", "pol": "pl", "rus": "ru", "chi_sim": "zh-Hans",
    "chi_tra": "zh-Hant", "jpn": "ja", "kor": "ko", "ara": "ar", "hin": "hi",
    "tur": "tr", "vie": "vi", "ukr": "uk", "ces": "cs", "swe": "sv",
    "dan": "da", "nor": "no", "fin": "fi", "ell": "el", "heb": "he",
    "hun": "hu", "ron": "ro", "fas": "fa", "tha": "th", "ind": "id",
}
_RTL = {"ar", "he", "fa", "ur"}


def language_tag(ocr_lang: Optional[str]) -> str:
    """Map a Tesseract language code ('eng', 'eng+fra') to a BCP 47 tag."""
    first = (ocr_lang or "eng").split("+")[0].strip().lower()
    return _TESS_TO_BCP47.get(first, "en")


# ---------------------------------------------------------------------------
# HTML conversion
# ---------------------------------------------------------------------------


def _protect_math(md: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Replace math with placeholders so Markdown doesn't mangle it.

    Returns the new text and a list of (kind, tex) where kind is
    'display' or 'inline'.
    """
    found: List[Tuple[str, str]] = []

    # Keep code spans/fences untouched by working only outside them.
    pieces: List[str] = []
    pos = 0
    code_spans = [m.span() for m in _FENCE.finditer(md)]
    for start, end in code_spans:
        pieces.append(("text", md[pos:start]))  # type: ignore[arg-type]
        pieces.append(("code", md[start:end]))  # type: ignore[arg-type]
        pos = end
    pieces.append(("text", md[pos:]))  # type: ignore[arg-type]

    def sub(rx: "re.Pattern[str]", kind: str, text: str) -> str:
        def repl(m: "re.Match[str]") -> str:
            found.append((kind, m.group(1).strip()))
            token = f"PDFMDMATH{len(found) - 1}X"
            return f"\n\n{token}\n\n" if kind == "display" else token
        return rx.sub(repl, text)

    out: List[str] = []
    for kind, text in pieces:  # type: ignore[misc]
        if kind == "code":
            out.append(text)
            continue
        # Protect inline code spans from math matching.
        codes: List[str] = []

        def keep_code(m: "re.Match[str]") -> str:
            codes.append(m.group(0))
            return f"PDFMDCODE{len(codes) - 1}X"

        text = _INLINE_CODE.sub(keep_code, text)
        text = sub(_DISPLAY_DOLLAR, "display", text)
        text = sub(_DISPLAY_BRACKET, "display", text)
        text = sub(_INLINE_PAREN, "inline", text)
        text = sub(_INLINE_DOLLAR, "inline", text)
        for i, c in enumerate(codes):
            text = text.replace(f"PDFMDCODE{i}X", c)
        out.append(text)
    return "".join(out), found


def _restore_math(body: str, found: List[Tuple[str, str]]) -> str:
    for i, (kind, tex) in enumerate(found):
        token = f"PDFMDMATH{i}X"
        esc = html.escape(tex, quote=False)
        if kind == "display":
            block = f'<div class="math-display">\\[{esc}\\]</div>'
            # Markdown wraps a lone token in <p>; replace the whole paragraph.
            body = body.replace(f"<p>{token}</p>", block)
            body = body.replace(token, block)
        else:
            body = body.replace(token, f"\\({esc}\\)")
    return body


def _fallback_markdown(md: str) -> str:
    """Very small Markdown converter used if python-markdown is missing."""
    out: List[str] = []
    for para in re.split(r"\n\s*\n", md.strip()):
        p = para.strip()
        if not p:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", p)
        if m and "\n" not in p:
            n = len(m.group(1))
            out.append(f"<h{n}>{html.escape(m.group(2))}</h{n}>")
        else:
            out.append("<p>" + html.escape(p).replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def _markdown_to_html_body(md: str) -> str:
    try:
        import markdown  # type: ignore
    except Exception:
        return _fallback_markdown(md)
    return markdown.markdown(
        md,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html",
    )


def _first_heading(md: str) -> Optional[str]:
    for line in md.splitlines():
        m = re.match(r"^#{1,2}\s+(.+?)\s*#*\s*$", line)
        if m:
            return re.sub(r"[*_`$\\]", "", m.group(1)).strip() or None
    return None


_CSS = """
:root { color-scheme: light dark; }
body { max-width: 52em; margin: 0 auto; padding: 1.5em 1em 3em;
       font-family: system-ui, "Segoe UI", Arial, sans-serif; font-size: 1.1rem;
       line-height: 1.6; }
a { color: LinkText; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid; padding: 0.3em 0.6em; text-align: left; }
th { font-weight: bold; }
img { max-width: 100%; height: auto; }
pre { overflow-x: auto; padding: 0.75em; border: 1px solid; }
.math-display { overflow-x: auto; margin: 1em 0; }
.skip-link { position: absolute; left: -10000px; }
.skip-link:focus { position: static; }
mjx-container:focus { outline: 3px solid Highlight; outline-offset: 2px; }
""".strip()


def markdown_to_accessible_html(
    md: str,
    title: Optional[str] = None,
    lang: str = "en",
    with_mathjax: bool = True,
) -> str:
    """Convert pdfmd Markdown to a standalone, accessible HTML page."""
    md = _remove_mathjax_header(md)
    protected, found = _protect_math(md)
    # The page only uses \(...\) and \[...\] for math, so escaped dollar
    # signs can be shown as plain text again.
    body = _markdown_to_html_body(protected).replace("\\$", "$")
    # Column headers: say so explicitly, so screen readers announce each
    # cell's header when moving through a table.
    body = re.sub(r"<th(?=[ >])(?![^>]*scope=)", '<th scope="col"', body)
    body = _restore_math(body, found)

    title = title or _first_heading(md) or "Converted document"
    direction = ' dir="rtl"' if lang.split("-")[0] in _RTL else ""

    head_scripts = ""
    if with_mathjax and found:
        head_scripts = (
            f"<script>{_MATHJAX_CONFIG_HTML}</script>\n"
            f'<script defer src="{MATHJAX_URL}"></script>\n'
        )
        note = (
            '<p class="math-help">This document contains math. Screen readers '
            "read each expression aloud. To explore an expression, move to it "
            "with Tab or your screen reader, then use the arrow keys. "
            "Right-click an expression, or press Shift+F10 on it, for MathJax "
            "accessibility settings.</p>\n"
        )
        # Place the note after the first top-level heading, or at the top.
        m = re.search(r"</h1>\s*", body)
        body = body[: m.end()] + note + body[m.end():] if m else note + body

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{html.escape(lang)}"{direction}>\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="generator" content="pdfmd">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>\n{_CSS}\n</style>\n"
        f"{head_scripts}"
        "</head>\n"
        "<body>\n"
        '<a class="skip-link" href="#content">Skip to content</a>\n'
        '<main id="content">\n'
        f"{body}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def apply_mathjax(
    md_path: "str | Path",
    ocr_lang: Optional[str] = None,
    enable_mathjax: bool = True,
    write_html: bool = True,
) -> Optional[Path]:
    """Post-process a converted Markdown file for accessible math.

    * ``enable_mathjax``: add the MathJax loader to the Markdown file, and
      load MathJax in the HTML copy.
    * ``write_html``: write an accessible HTML copy next to the Markdown
      file (same name, ``.html`` extension).

    Returns the HTML path, or None if no HTML file was written.
    """
    md_path = Path(md_path)
    md = md_path.read_text(encoding="utf-8")

    if enable_mathjax and not has_mathjax(md):
        md = add_mathjax_to_markdown(wrap_unicode_math(md))
        md_path.write_text(md, encoding="utf-8")

    if not write_html:
        return None
    html_path = md_path.with_suffix(".html")
    title = _first_heading(_remove_mathjax_header(md)) or md_path.stem
    page = markdown_to_accessible_html(
        md, title=title, lang=language_tag(ocr_lang), with_mathjax=enable_mathjax
    )
    html_path.write_text(page, encoding="utf-8")
    return html_path


__all__ = [
    "MATHJAX_VERSION",
    "MATHJAX_URL",
    "count_math",
    "count_delimited_math",
    "count_unicode_math",
    "wrap_unicode_math",
    "unicode_math_to_latex",
    "has_mathjax",
    "add_mathjax_to_markdown",
    "markdown_to_accessible_html",
    "language_tag",
    "apply_mathjax",
]
