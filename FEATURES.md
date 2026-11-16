# Document Conversion Suite: Features Guide

Document Conversion Suite is an accessible, privacy-first document converter for Windows. It turns PDFs (including scanned PDFs) into clean Markdown with the pdfmd engine, makes math accessible with MathJax, writes accessible HTML, and converts between every format pandoc supports, with all of pandoc's options available.

Version 1.7.1. For accessibility details and the full keyboard reference, see [ACCESSIBILITY.md](ACCESSIBILITY.md).

## Contents

1. [At a glance](#1-at-a-glance)
2. [PDF conversion engine](#2-pdf-conversion-engine)
3. [Accessible math](#3-accessible-math)
4. [Accessible HTML output](#4-accessible-html-output)
5. [Pandoc: every format, every option](#5-pandoc-every-format-every-option)
6. [The main window](#6-the-main-window)
7. [The pandoc window](#7-the-pandoc-window)
8. [Profiles and settings](#8-profiles-and-settings)
9. [Command line (pdfmd-cli)](#9-command-line-pdfmd-cli)
10. [Python API](#10-python-api)
11. [Installer and Windows integration](#11-installer-and-windows-integration)
12. [Privacy and security](#12-privacy-and-security)
13. [Requirements](#13-requirements)
14. [Files and locations](#14-files-and-locations)

---

## 1. At a glance

| Area | Highlights |
| --- | --- |
| PDF to Markdown | Paragraphs, headings, lists, bold and italic, links, tables, math, header and footer removal, hyphenation repair |
| Scanned PDFs | Auto OCR by default with Tesseract or OCRmyPDF, 100+ languages, combined languages (eng+fra); install, update and add languages from inside the app |
| Tables | Ruled, aligned and multi-block tables rebuilt with header rows, kept intact in Markdown, HTML and every pandoc format |
| Accessible math | Offers MathJax when math is found (default Yes): spoken math, Braille, keyboard exploration |
| Accessible HTML | Language-tagged, structured HTML copy with MathJax math |
| Pandoc | Convert from about 50 input formats to about 70 output formats: Word, EPUB, HTML, LaTeX, PDF, ODT, PowerPoint, reStructuredText, AsciiDoc, Typst, JATS, DocBook and more |
| Pandoc options | Standalone, table of contents, numbering, math rendering, highlighting, wrapping, title, language, heading shift, citations (citeproc, bibliographies, CSL), reference documents, templates, Lua filters, PDF engines, and any other pandoc argument |
| Accessible GUI | Native controls, labels, spoken descriptions, Tab order, menu bar, Alt keys, screen reader announcements |
| Batch | Convert many files at once, with safe output naming |
| Privacy | Everything runs on your computer |

## 2. PDF conversion engine

The pdfmd engine converts PDFs to Markdown in four stages: extract, transform, render, and optionally export images.

### Text and structure

* **Paragraph reconstruction**: joins lines that were wrapped in the PDF.
* **Heading detection**: text larger than the body text (by the heading size ratio) becomes a heading; optionally, short ALL-CAPS lines become headings.
* **Lists**: bullets (•, ○, -) and numbered or lettered items (1., a.) become Markdown lists.
* **Hyphenation repair**: "hy-\nphen" becomes "hyphen".
* **Links**: plain URLs become links.
* **Inline formatting**: bold and italic are kept.
* **Header and footer removal**: running headers, footers and page numbers that repeat on every page are removed.
* **Orphan joining**: short isolated lines are merged into the previous paragraph.
* **Page breaks**: optional horizontal rule between pages.
* **Multi-column awareness**: reduces mixing of text from neighbouring columns.

### Tables

* **Ruled tables**: tables drawn with lines are read with PyMuPDF's table finder, so every row, column, header row and multi-line cell is kept.
* **Text tables**: detects bordered text tables (`|`, `¦`), whitespace-aligned columns, tab-separated blocks and tables split across several blocks (one block per row).
* Writes Markdown pipe tables with a header row and column alignment; pipe characters in cells are escaped.
* Conservative rules avoid turning prose or lists into tables.
* **Tables stay intact through every conversion**: short lines are never merged into table rows; the accessible HTML copy has real header cells marked `scope="col"`; pandoc receives the tables unchanged and writes real tables in Word, ODT, EPUB, HTML, LaTeX, reStructuredText, AsciiDoc, Typst and other formats. When the target format can't express a complex table (for example GitHub Markdown and merged cells), pandoc falls back to an HTML table instead of losing the structure.

### Math

* Detects equation lines and writes them as display math (`$$ ... $$`).
* Converts Unicode math to LaTeX: Greek letters (α → `\alpha`), superscripts and subscripts (x² → `x^2`, x₁₀ → `x_{10}`), operators and relations (≤, ≥, ≠, ≈, ∫, ∑, √, ∞, →, ∈ and more).
* Keeps LaTeX that is already in the PDF.
* New in 1.7.0: math written inside ordinary sentences is detected too (see section 3).

### Scanned PDFs (OCR)

| OCR mode | What it does |
| --- | --- |
| Off | Uses the text stored in the PDF. Fastest. |
| Auto (default) | Detects scanned pages (little text, large images) and runs OCR only on those, so inaccessible image-only PDFs become text. |
| Tesseract | Runs Tesseract OCR on every page. |
| OCRmyPDF | Uses OCRmyPDF for the highest-fidelity OCR. |

* OCR language: any Tesseract language code, or several joined with `+` (for example `eng+fra`). The list offers 17 common languages; you can type any other installed code.
* **Tesseract OCR 5.4 is built in**, with 17 languages (ara, chi_sim, chi_tra, deu, eng, fra, hin, ita, jpn, kor, nld, pol, por, rus, spa, tur, vie) and orientation detection.
* **Scanned tables**: table borders are erased from the page image before OCR so Tesseract reads every row, and wide gaps between words are kept so the table is rebuilt with its columns.
* If a PDF is scanned and Tesseract isn't available (for example when running from source), the app says which file is scanned and offers to install Tesseract, instead of producing an empty document.
* The app finds Tesseract even when it isn't on the PATH (standard install folders and the Windows registry).

### Tesseract OCR manager (Ctrl+T)

File > Tesseract OCR (Ctrl+T), or Help > Check for Tesseract Updates:

* Shows the Tesseract in use (the built-in copy or one you installed), its version and location, and its OCR languages.
* **Check for Updates** looks up the latest Windows build (UB Mannheim, the build the Tesseract project recommends for Windows).
* **Install Tesseract / Install Update / Reinstall** installs a system copy with the Windows Package Manager (winget), or downloads the official installer from GitHub and starts it. A system copy takes priority over the built-in one, so updates take effect immediately.
* **Add language**: download any of about 100 languages (plus math/equation and orientation detection data) in fast or best quality. Added languages are stored per user, so no administrator rights are needed.
* OCRmyPDF (for that OCR mode) is installed separately with `pip install ocrmypdf`.

### Images

* **Export images**: saves the images in the PDF as PNG files in a `<name>_assets` folder next to the output and links them at the end of the Markdown, grouped by page, with alternative text such as "Image 1 from page 3".
* Colour spaces (CMYK and others) are converted automatically.

### Other engine features

* **Preview**: convert only the first three pages for a quick check.
* **Password-protected PDFs**: you are asked for the password; it is used only in memory and never saved or logged. Supports RC4 and AES encryption.
* **Batch conversion**: several PDFs at once into one folder; existing files are never overwritten silently (`_1`, `_2` suffixes are added).

## 3. Accessible math

When a converted document contains math, the suite can enable **MathJax 4**, which makes every expression accessible:

* **Speech**: screen readers speak the math in natural language, for example "x sub i is greater than or equal to 0".
* **Braille**: Nemeth or UEB Braille for refreshable Braille displays.
* **Exploration**: move through a complex expression piece by piece with the arrow keys.
* **Settings menu**: right-click an expression, or press Shift+F10 on it, for MathJax accessibility settings.

How it works:

1. After conversion, the suite counts math expressions: LaTeX-delimited math, plus Unicode math inside sentences such as "E = mc²", "a² + b² = c²", "α + β³ = γ", "H₂O" or "x ∈ ℝ".
2. Depending on the **When equations are found** setting:
   * **Ask me** (default): a dialog asks whether to enable MathJax. The default answer is **Enable MathJax**. In a batch you can apply the answer to the remaining files.
   * **Always enable MathJax**
   * **Never enable MathJax**
3. When MathJax is enabled:
   * Unicode math in sentences is converted to LaTeX and wrapped as inline math.
   * Dollar signs that are not math (prices) are escaped so they are not mistaken for math.
   * A MathJax loader is added to the top of the Markdown file, so Markdown viewers that allow HTML render accessible math.
   * An accessible HTML copy is written next to the Markdown file.

Prices ("$5 and $10"), version numbers and code are not treated as math.

On the command line, use `--mathjax ask|yes|no`.

## 4. Accessible HTML output

The HTML copy (`<name>.html`, next to the Markdown file) is written when MathJax is enabled, or for every document when **Also save an accessible HTML copy of every document** is checked (`--html` on the command line). It has:

* `lang` set from the OCR language (and `dir="rtl"` for right-to-left languages such as Arabic or Hebrew), so screen readers use the right voice;
* a page title from the first heading;
* real headings, lists, links and code blocks;
* tables with real header cells;
* a "Skip to content" link and a `main` landmark;
* MathJax math with speech, Braille and exploration;
* a short note explaining how to explore math;
* responsive, readable styling that follows light and dark mode, with visible focus outlines.

## 5. Pandoc: every format, every option

[Pandoc](https://pandoc.org) is the universal document converter. The suite uses it to convert to and from every format pandoc supports, and exposes pandoc's options in an accessible window.

### Formats

The format lists come from the installed pandoc (`pandoc --list-input-formats` and `--list-output-formats`), so every format your pandoc version supports is offered, with friendly names.

**Input formats include:** Markdown (pandoc, CommonMark, GitHub, MultiMarkdown, PHP Markdown Extra, strict), Djot, Word (.docx), OpenDocument (.odt), EPUB, HTML, LaTeX, reStructuredText, AsciiDoc, Org mode, MediaWiki, DokuWiki, Textile, Typst, Jupyter notebooks, JATS, DocBook, TEI, FictionBook, RTF, PowerPoint (.pptx), Excel (.xlsx), CSV, TSV, OPML, man pages, Muse, Creole, Haddock, Jira, txt2tags, TikiWiki, TWiki, Vimwiki, BibTeX, BibLaTeX, CSL JSON, EndNote XML, RIS, BITS, POD, mdoc and pandoc's JSON and native formats. **PDF** is also accepted: the suite converts it with the pdfmd engine first.

**Output formats include:** HTML (4 and 5), Word (.docx), OpenDocument (.odt and flat XML), EPUB (2 and 3), PowerPoint (.pptx), RTF, PDF (through a LaTeX, Typst, ConTeXt or HTML-to-PDF engine), LaTeX, Beamer slides, ConTeXt, Typst, all Markdown flavours, Djot, plain text, reStructuredText, AsciiDoc, Org mode, MediaWiki, DokuWiki, Textile, Jira, XWiki, ZimWiki, Vimwiki, Vim help, reveal.js, Slidy, Slideous, S5 and DZSlides slide shows, chunked HTML, JATS (all variants), DocBook 4 and 5, TEI, InDesign ICML, FictionBook, OPML, Jupyter notebooks, man, ms, Texinfo, Haddock, Muse, Markua, BibTeX, BibLaTeX, CSL JSON, ANSI terminal text, and pandoc's JSON, native and XML formats.

### Options in the pandoc window

| Option | Pandoc equivalent |
| --- | --- |
| Input format (or detect from extension) | `--from` |
| Output format | `--to` |
| Standalone document | `--standalone` |
| Table of contents, depth | `--toc`, `--toc-depth` |
| Number sections | `--number-sections` |
| Embed images and styles in one HTML file | `--embed-resources` |
| Math rendering: Automatic, MathJax, MathML, KaTeX, WebTeX, GladTeX, plain text | `--mathjax`, `--mathml`, `--katex`, `--webtex`, `--gladtex` |
| Code highlighting style (from your pandoc's styles) | `--highlight-style` |
| Line wrapping: automatic, none, preserve | `--wrap` |
| Document title | `--metadata title=...` |
| Document language | `--metadata lang=...` |
| Shift heading levels | `--shift-heading-level-by` |
| Process citations | `--citeproc` |
| Bibliography files (several allowed) | `--bibliography` |
| Citation style (CSL) | `--csl` |
| Reference document (Word, ODT, PowerPoint styles) | `--reference-doc` |
| Template | `--template` |
| Lua filters or filter programs (several allowed) | `--lua-filter`, `--filter` |
| PDF engine (pdflatex, xelatex, lualatex, tectonic, latexmk, typst, context, wkhtmltopdf, weasyprint, pagedjs-cli, prince, groff, pdfroff) | `--pdf-engine` |
| Extra pandoc arguments | Anything else, typed as on the command line, for example `--columns=100 -V geometry:margin=1in --metadata author="Ada Lovelace"` |

The **Extra pandoc arguments** field gives access to every pandoc option, including ones added in future pandoc versions.

### Accessible defaults

* **Automatic math rendering** chooses MathJax 4 for HTML and slides, MathML for EPUB, and native equations for Word, ODT and PowerPoint.
* The document language is always set (from your setting or the OCR language).
* Standalone documents get a page title from the file name if you don't give one.
* Unicode math in Markdown input is converted to TeX first, so pandoc writes real equations.
* Media from Word, ODT, EPUB, PowerPoint and notebook input is extracted next to the output.

### Getting pandoc

**Pandoc 3.13 is built in** (a separate GPL program, included unmodified with its license and source link in `docs\THIRD-PARTY-NOTICES.txt`). The suite uses, in this order: the `PDFMD_PANDOC` environment variable, a pandoc on the PATH or in the standard install folders (so you can use a newer version), then the built-in copy. When running from source without pandoc, the pandoc window offers **Install Pandoc** (Alt+P).

## 6. The main window

| Group | Controls |
| --- | --- |
| Input and output | Input PDF files list, Add PDFs, Remove Selected, Empty List, Output file or folder, Browse Output |
| Conversion options | Profile, OCR mode, OCR language, Export images, Insert page breaks, Preview first 3 pages only, Remove repeating header and footer text, Promote uppercase lines to headings, Join short orphan lines into paragraphs, Heading size ratio, Orphan line width, When equations are found, Also save an accessible HTML copy |
| Progress | Convert, Stop, Open Output Folder, progress bar, Conversion log |

Other features:

* **Menus**: File (add files, choose output, convert, stop, convert with pandoc, Tesseract OCR, open folder, open Markdown, open HTML, exit), Profiles (apply, save, delete, reset), View (theme, announcements, speak status), Help (keyboard shortcuts, check for Tesseract updates, about).
* **Drag and drop** PDFs onto the window or the list.
* **Open PDFs from Explorer** with "Convert with Document Conversion Suite", or pass PDF paths on the command line of `DocConversionSuite.exe`.
* **Automatic output name**: one PDF goes to `<name>.md` next to it; several go to the first PDF's folder. Type or browse to change it.
* **Overwrite protection**: asks before replacing an existing file; batch output never overwrites.
* **Stop** a running conversion at any time (Stop button, Shift+F5 or Esc).
* **Also export with pandoc**: each converted PDF can also be converted automatically to your chosen pandoc format (set in the pandoc window).
* **Themes**: follow Windows, light or dark (native Windows dark mode).
* **Status**: spoken announcements, status bar, Ctrl+Shift+S to repeat.

## 7. The pandoc window

Open it with **File > Convert Any Document with Pandoc** (Ctrl+P). It has three pages:

1. **Files and format**: input files (any format, including PDF), input format, output format, output folder, the option to also export every PDF conversion from the main window, and the pandoc log.
2. **Document options**: standalone, table of contents and depth, section numbering, embedded resources, math rendering, code highlighting, line wrapping, title, language, heading shift.
3. **Citations, templates and filters**: citeproc, bibliography files, CSL style, reference document, template, filters, PDF engine, extra pandoc arguments.

Output files are named after the input with the right extension; existing files are never overwritten (`_1`, `_2` are added). Settings are remembered.

## 8. Profiles and settings

Built-in profiles:

| Profile | Purpose |
| --- | --- |
| Default | General documents |
| Academic article | Papers: auto OCR, finer heading detection, longer orphan joining |
| Math and science (MathJax) | Always enables MathJax and saves an accessible HTML copy |
| Slides / handouts | Exports images, inserts page breaks, keeps headers |
| Scan-heavy / OCR-first | Tesseract OCR on every page |

Save your own with Profiles > Save Current Settings as Profile (Ctrl+S); delete or reset from the same menu. The program remembers the theme, announcement setting, input files, output path, options, profiles, window size and pandoc settings.

## 9. Command line (pdfmd-cli)

`pdfmd-cli.exe` is installed next to the program (Start menu: **Command Prompt for pdfmd-cli**). With Python, the same tool is `pdfmd` or `python -m pdfmd`.

```text
pdfmd-cli [options] INPUT_PDF [INPUT_PDF ...]
```

| Option | Meaning |
| --- | --- |
| `-o, --output OUTPUT` | Output .md file (one input) or folder (several inputs) |
| `--ocr {off,auto,tesseract,ocrmypdf}` | OCR mode (default auto) |
| `--lang LANG` | Tesseract language code(s), for example `eng+fra` |
| `--export-images` | Export images to an `_assets` folder |
| `--page-breaks` | Insert page break markers |
| `--preview-only` | Only the first few pages |
| `--mathjax {ask,yes,no}` | Accessible math when math is found (default ask; answer defaults to yes) |
| `--html` | Also write an accessible HTML copy |
| `--to FORMAT` | Also convert with pandoc to any pandoc output format |
| `--pandoc-args ARGS` | Extra pandoc options in one quoted argument |
| `--no-progress` | No progress bar |
| `-q, --quiet` | Only errors |
| `-v, --verbose` | More detail (`-vv` for debug) |
| `--stats` | Print words, headings, tables and lists |
| `--no-color` | No coloured output |
| `--version` | Print the version |

Examples:

```text
pdfmd-cli report.pdf
pdfmd-cli scan.pdf --ocr auto --lang eng+deu
pdfmd-cli calculus.pdf --mathjax yes --html
pdfmd-cli thesis.pdf --to docx --pandoc-args "--toc --citeproc --bibliography refs.bib"
pdfmd-cli *.pdf -o converted --to epub3
```

## 10. Python API

```python
from pdfmd import Options, pdf_to_markdown
from pdfmd.mathjax import count_math, apply_mathjax
from pdfmd import pandoc_support as ps

pdf_to_markdown("paper.pdf", "paper.md", Options(ocr_mode="auto", ocr_lang="eng"))
if count_math(open("paper.md", encoding="utf-8").read()):
    apply_mathjax("paper.md", ocr_lang="eng")          # MathJax + accessible HTML
ps.convert("paper.md", "paper.docx", ps.PandocOptions(to_format="docx", toc=True))
```

See [doc/API.md](doc/API.md) for the engine API.

## 11. Installer and Windows integration

* Accessible Inno Setup wizard (standard controls, keyboard operable, screen reader friendly).
* Installs for the current user without an administrator prompt; optional all-users install.
* Start menu: Document Conversion Suite, Accessibility Guide, Features Guide, Command Prompt for pdfmd-cli, Uninstall.
* Built in: pandoc 3.13, Tesseract OCR 5.4 and 17 OCR languages; nothing else to install.
* Optional: desktop shortcut; "Convert with Document Conversion Suite" for PDF files in Explorer.
* Licenses of bundled programs: `docs\THIRD-PARTY-NOTICES.txt`.
* Documentation installed in the `docs` folder as Markdown and accessible HTML.
* Clean uninstall from Settings > Apps.

## 12. Privacy and security

* No uploads, no telemetry, no cloud processing: every conversion runs on your computer.
* PDF passwords are used only in memory, never logged, saved or passed on a command line.
* Only reading converted HTML or Markdown with MathJax contacts the jsDelivr CDN, to load MathJax. Checking for Tesseract updates, installing Tesseract or pandoc, and downloading OCR languages contact GitHub (or winget's sources), and only when you ask.

## 13. Requirements

* Windows 10 or 11, 64-bit (installer). The engine and command line also run on macOS and Linux with Python 3.8+.
* Included in the installer: Tesseract OCR and pandoc. Optional: OCRmyPDF for the OCRmyPDF mode; a PDF engine (for example a LaTeX distribution, Typst or WeasyPrint) for pandoc PDF output.
* A screen reader is optional; announcements go to NVDA, JAWS, System Access, Dolphin, ZoomText, PC-Talker or ZDSR when one is running.

## 14. Files and locations

| What | Where |
| --- | --- |
| Program | `%LOCALAPPDATA%\Programs\Document Conversion Suite` (per-user) or `C:\Program Files\Document Conversion Suite` (all users) |
| GUI | `DocConversionSuite.exe` |
| Built-in pandoc | `pandoc\` in the program folder |
| Built-in Tesseract and languages | `Tesseract-OCR\` in the program folder |
| Command line | `pdfmd-cli.exe` |
| Documentation | `docs\` in the program folder |
| Settings | `%USERPROFILE%\.pdfmd_gui.json` |
| Added OCR languages | `%LOCALAPPDATA%\DocConversionSuite\tessdata` |
| Markdown output | Next to the PDF by default |
| Accessible HTML | Next to the Markdown file, same name, `.html` |
| Exported images | `<name>_assets` folder next to the Markdown file |
