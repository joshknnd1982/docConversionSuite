# Document Conversion Suite: Features Guide

Document Conversion Suite is an accessible, privacy-first document converter for Windows. It turns PDFs (including scanned PDFs) into clean Markdown with the pdfmd engine, makes math accessible with MathJax, writes accessible HTML, and converts between every format pandoc supports, with all of pandoc's options available.

Version 1.9.0. For accessibility details and the full keyboard reference, see [ACCESSIBILITY.md](ACCESSIBILITY.md).

## Contents

1. [At a glance](#1-at-a-glance)
2. [PDF conversion engine](#2-pdf-conversion-engine)
3. [Accessible math](#3-accessible-math)
4. [Accessible HTML output](#4-accessible-html-output)
5. [Pandoc: every format, every option](#5-pandoc-every-format-every-option)
6. [The main window](#6-the-main-window)
7. [The Pandoc Options and PDF Settings windows](#7-the-pandoc-options-and-pdf-settings-windows)
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
| Picture descriptions | A local AI vision model (Qwen3-VL 2B, abliterated, in llama.cpp) describes photos, charts, graphs, maps and diagrams in PDFs and every pandoc input format: alternative text, or a block quote for text-only output; GPU or CPU; describe whole photo folders into an album |
| Pandoc | Convert from about 50 input formats to about 70 output formats: Word, EPUB, HTML, LaTeX, PDF, ODT, PowerPoint, reStructuredText, AsciiDoc, Typst, JATS, DocBook and more |
| Pandoc options | Every option of pandoc 3.13 has its own labelled control: format extensions, metadata, variables, table of contents, lists of figures and tables, numbering, captions, math, highlighting, citations (citeproc, natbib, biblatex), wrapping, line endings, reference documents, templates, EPUB covers and fonts, slides, PDF engines, filters, includes, sandbox and more. Only the options for the chosen format are shown |
| Accessible GUI | Native controls, labels, spoken descriptions, Tab order, menu bar, Alt keys, screen reader announcements |
| One window | Add any documents or folders, choose what to convert them to, press F5. Join many files of different formats into one document |
| Batch | Convert many files and whole folders at once, with safe output naming |
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

* **Export images**: saves the images in the PDF as PNG files in a `<name>_assets` folder next to the output. With picture descriptions on (the default), each described picture and drawn chart is saved where it appears in the text, with its description as alternative text. Other images (icons, logos, and every image when descriptions are off) are linked at the end of the Markdown, grouped by page, with alternative text such as "Image 1 from page 3".
* Colour spaces (CMYK and others) are converted automatically.

### Picture descriptions (local AI vision model)

* **What is described**: embedded pictures (photos, scanned charts, maps, illustrations), charts drawn with vector graphics (most charts exported from Excel, matplotlib or R), and photo regions inside scanned pages. Tiny pictures (icons, bullets), logos repeated on most pages and pictures under a text layer are skipped.
* **Pictures of text** (a scanned paragraph, a screenshot of a letter) are read with Tesseract OCR instead, and their text is added ("Text in image").
* **Alternative text or block quote**: with Export images on, the description is the picture's alternative text: `![A bar chart of sales from 2021 to 2024...](report_assets/figure_001_02.png)`. With it off there is no picture in the output, so the description is written in the text: `> **Image description:** A bar chart of sales from 2021 to 2024...`.
* **Charts**: axis labels just outside a drawn chart are included in what the model sees; the chart's caption is given to the model as context; when a chart is described, its stray axis labels are kept out of the text.
* **Every document**: in the pandoc window and on the command line, Word, ODT, EPUB, PowerPoint, Jupyter, HTML, Markdown, LaTeX and other inputs are read with pandoc and every picture without useful alternative text is described. Formats that hold pictures (Word, EPUB, HTML, ODT, PowerPoint, PDF, LaTeX, Markdown...) get alternative text; text-only formats (plain text, man pages, spreadsheets...) get block quotes. Generic captions such as "image1" are removed. Remote pictures are never downloaded.
* **Language**: descriptions are written in the OCR language you chose (for example German for `deu`).
* **Model**: Qwen3-VL 2B Instruct, abliterated by huihui-ai (Apache-2.0), 4-bit GGUF, about 1.6 GB on disk and 3 GB of memory. Also offered: the official Qwen3-VL 2B Instruct, and a larger, more accurate Qwen3-VL 4B abliterated for computers with 16 GB of memory or a graphics card with 6 GB or more.
* **Engine**: llama.cpp's llama-server (Vulkan build), started only while pictures are being described, listening only on 127.0.0.1 with a random port and access key, and stopped afterwards to free memory.
* **Processor**: Automatic; **NVIDIA GPU with CUDA** (offered when an NVIDIA card is detected; the CUDA engine, about 710 MB, is downloaded with one button press and chosen for your driver: CUDA 13 or CUDA 12.4); **Any GPU with Vulkan** (NVIDIA, AMD, Intel, including integrated graphics; built in); one particular graphics processor; or **CPU only**. If CUDA fails, Vulkan is used; if the graphics processor fails, the CPU.
* **Speed** (measured on a Ryzen 7 laptop): about 0.5 to 0.7 seconds per picture on an RTX 5060 with CUDA, 0.6 to 0.8 with Vulkan, 4 seconds on Radeon 780M integrated graphics, 5 to 7 seconds on the CPU alone.

### Describe a folder of photos (Ctrl+D)

* Choose a folder (optionally with subfolders) and **Web page (HTML)** or **Markdown**. Every photo (JPEG, PNG, HEIC from phones, WebP, TIFF, GIF, BMP, AVIF) gets a short title and a description of who and what is in it, the place, the time of day or season and the mood.
* Photos are listed in the order they were taken (from the camera's date), with the date, time and camera model.
* The web page has a heading per photo (screen reader users press H to move between photos), a contents list, the photo with its title as alternative text and the description as its caption, light and dark mode. Photos are linked, not copied.
* Descriptions are remembered in a small file next to the page, so running it again only describes new or changed photos.
* The command line does the same: `pdfmd-cli --describe-photos "C:\Photos\Italy" --album-format html`.

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

### Every pandoc option

Every option in `pandoc --help` (pandoc 3.13) is described once in `pdfmd/pandoc_options.py`, and each one gets a labelled control in the **Pandoc Options** window (Ctrl+P), a place in saved settings, and a `--pandoc-option` name on the command line. The window has these pages:

| Page | Options (pandoc flags) |
| --- | --- |
| Format | Output and input format (`--to`, `--from`), output and input **format extensions** (`+ext`/`-ext`, from `--list-extensions`), standalone (`--standalone`), template (`--template`) with **Save Default Template**, data folder (`--data-dir`), defaults file (`--defaults`) |
| Document | Title and language (`--metadata`), metadata (`--metadata`), metadata file (`--metadata-file`), template variables (`--variable`, `--variable-json`), include in header / before body / after body (`--include-in-header`, `--include-before-body`, `--include-after-body`) |
| Contents and sections | Table of contents and depth (`--toc`, `--toc-depth`), lists of figures and tables (`--lof`, `--lot`), number sections (`--number-sections`, `--number-offset`), top-level division (`--top-level-division`), shift heading levels (`--shift-heading-level-by`), figure and table caption position (`--figure-caption-position`, `--table-caption-position`) |
| Math and code | Math rendering (`--math-method`: automatic, MathJax, MathML, KaTeX, WebTeX, GladTeX, plain), code highlighting (`--syntax-highlighting`) with **Save Highlight Style**, syntax definitions (`--syntax-definition`), LaTeX listings (`--listings`), indented code classes (`--indented-code-classes`), tab stop (`--tab-stop`), preserve tabs (`--preserve-tabs`) |
| Citations | How citations are handled: leave as written, citeproc, natbib or biblatex (`--citeproc`, `--natbib`, `--biblatex`), bibliography files (`--bibliography`), citation style (`--csl`), journal abbreviations (`--citation-abbreviations`) |
| Text layout | Wrapping (`--wrap`), line width (`--columns`), line endings (`--eol`), picture resolution (`--dpi`), reference links and their location (`--reference-links`, `--reference-location`), Markdown heading style (`--markdown-headings`), list tables (`--list-tables`), ASCII only (`--ascii`), strip comments (`--strip-comments`) |
| Web pages and slides | Embed resources (`--embed-resources`), CSS (`--css`), section divs (`--section-divs`), e-mail obfuscation (`--email-obfuscation`), id prefix (`--id-prefix`), title prefix (`--title-prefix`), q tags (`--html-q-tags`), incremental lists (`--incremental`), slide level (`--slide-level`) |
| Word, OpenDocument, PowerPoint | Reference document (`--reference-doc`) with **Save Default Reference Document**, link images (`--link-images`), tracked changes (`--track-changes`) |
| E-books | Cover picture (`--epub-cover-image`), title page (`--epub-title-page`), EPUB metadata (`--epub-metadata`), embedded fonts (`--epub-embed-font`), split level (`--split-level`), chunk template (`--chunk-template`), EPUB subfolder (`--epub-subdirectory`) |
| PDF | PDF engine (`--pdf-engine`: pdflatex, xelatex, lualatex, tectonic, latexmk, typst, context, wkhtmltopdf, weasyprint, pagedjs-cli, prince, groff, pdfroff), engine options (`--pdf-engine-opt`), Typst inputs (`--typst-input`) |
| Input and media | Extract media (`--extract-media`), resource path (`--resource-path`), default image extension (`--default-image-extension`), abbreviations (`--abbreviations`), file scope (`--file-scope`), notebook output (`--ipynb-output`), request headers (`--request-header`), skip certificate check (`--no-check-certificate`), sandbox (`--sandbox`) |
| Filters | An ordered list of Lua filters and filter programs (`--lua-filter`, `--filter`) with Add, Remove, Move Up and Move Down |
| Command line | Extra pandoc arguments, verbose, quiet, fail if warnings, trace, log file (`--verbose`, `--quiet`, `--fail-if-warnings`, `--trace`, `--log`), and the read-only **Command that will run** |

* **Only what matters is shown.** Options that do nothing for the chosen output format are hidden, and pages with nothing to show are left out (Word output has no e-book or slide page). Rarely used options appear with **Show advanced options**.
* **Works with any pandoc version.** The window reads `pandoc --help` and hides options your pandoc doesn't have; newer flags (`--syntax-highlighting`, `--math-method`) are used when available and the older ones otherwise.
* **Extra pandoc arguments** stays as an expert fallback for anything typed by hand.

### Accessible defaults

* **Automatic math rendering** chooses MathJax 4 for HTML and slides, MathML for EPUB, and native equations for Word, ODT and PowerPoint.
* The document language is always set (from your setting or the OCR language).
* Standalone documents get a page title from the file name if you don't give one.
* Unicode math in Markdown input is converted to TeX first, so pandoc writes real equations.
* Media from Word, ODT, EPUB, PowerPoint and notebook input is extracted next to the output.

### Getting pandoc

**Pandoc 3.13 is built in** (a separate GPL program, included unmodified with its license and source link in `docs\THIRD-PARTY-NOTICES.txt`). The suite uses, in this order: the `PDFMD_PANDOC` environment variable, a pandoc on the PATH or in the standard install folders (so you can use a newer version), then the built-in copy. When running from source without pandoc, the pandoc window offers **Install Pandoc** (Alt+P).

## 6. The main window

One window converts everything: add documents or folders, choose what to convert them to, choose where to save, press **Convert** (F5).

| Group | Controls |
| --- | --- |
| Files to convert | Input files and folders list, Add Files, Add Folder, Remove Selected Files, Clear List, Include subfolders of added folders, File types to take from folders |
| Convert to | Convert to (Markdown and every pandoc output format), Join all files into one document, Keep the Markdown file too, Describe pictures with the local AI vision model, PDF Settings, Pandoc Options |
| Save to | Output file or folder, Choose Output |
| Progress | Convert, Stop, Show Output Folder, progress bar, Conversion log |

How each file is converted:

* **PDF to Markdown**: the pdfmd engine, with OCR, tables, math and the MathJax offer, exactly as before.
* **PDF to any other format**: pdfmd makes accessible Markdown, then pandoc converts it with your Pandoc Options. Check **Keep the Markdown file too** to keep that Markdown next to the output.
* **Any other document**: pandoc converts it directly, to Markdown or any other format.
* **Join all files into one document**: every file in the list (in list order, of any formats, PDFs included) becomes one document. Repeated heading ids are numbered so links stay unambiguous.

Other features:

* **Only useful controls are shown**: folder settings appear when the list has a folder; Join and Keep the Markdown file appear when they apply.
* **Menus**: File (add files, add folder, choose output, convert, stop, PDF Settings, Pandoc Options, Tesseract OCR, vision model, describe a folder of photos, show output folder, open converted file, open HTML, exit), Profiles (apply, save, delete, reset), View (theme, announcements, speak status), Help (keyboard shortcuts, check for Tesseract updates, check for vision model updates, about).
* **Drag and drop** files and folders onto the window or the list.
* **Open documents from Explorer** with "Convert with Document Conversion Suite", or pass file and folder paths on the command line of `DocConversionSuite.exe`.
* **Automatic output name**: one file goes to `<name>.<extension>` next to it; several are saved next to each original, or in the output folder you choose (keeping subfolders). Joined files go to `<first name>_joined.<extension>`.
* **Overwrite protection**: asks before replacing an existing file; batch output never overwrites.
* **Stop** a running conversion at any time (Stop button, Shift+F5 or Esc).
* **Themes**: follow Windows, light or dark (native Windows dark mode).
* **Status**: spoken announcements, status bar, Ctrl+Shift+S to repeat.

Settings from version 1.8 carry over. If "Also export every PDF conversion" was on, Convert to is set to that format with Keep the Markdown file too checked, so you get the same files as before.

## 7. The Pandoc Options and PDF Settings windows

**Pandoc Options** (Ctrl+P, or the Pandoc Options button) holds every pandoc setting, on the pages listed in section 5. Changing its output format changes Convert to in the main window. Each control's Alt key is unique on its page; press F1 in the window for the full list. **Save Default Template**, **Save Default Reference Document** and **Save Highlight Style** save pandoc's own files so you can customise them, and offer to use the saved file right away.

**PDF Settings** (Ctrl+Shift+P, or the PDF Settings button) holds how PDFs are read: profile, OCR mode and language, export images, page breaks, preview, header and footer removal, uppercase headings, orphan joining, heading size ratio, orphan line width, what to do when equations are found, and the accessible HTML copy. These were in the main window before 1.9.0 and keep their Alt keys.

## 7a. The Vision Model window

Open it with **File > Vision Model** (Ctrl+I) or **Help > Check for Vision Model Updates**.

* **Status**: the engine version, the model in use, the graphics processors found, where the model will run, and any available update.
* **Describe pictures in documents**: the same setting as the main window's check box.
* **Processor**: Automatic, NVIDIA GPU with CUDA (when an NVIDIA card is found), Any GPU with Vulkan, Only *a particular graphics processor*, or CPU only.
* **Model**: the default model, the official Qwen3-VL 2B, or the larger Qwen3-VL 4B (downloaded when you press Update).
* **Check for Updates**: reads the small online model list ([vision-models.json](vision-models.json)).
* **Update Vision Model** (Download Vision Model when something is missing): installs the newest engine and the selected model with one button press, and the NVIDIA CUDA engine when the processor is NVIDIA GPU with CUDA. Every file is checked against its published SHA-256 checksum. Updates go to `%LOCALAPPDATA%\DocConversionSuite\vision`; the built-in copy stays as a fallback.
* **Test on a Picture**: describes a picture you choose and speaks the result.
* **Remove Downloaded Model**: frees disk space (the built-in model stays).

## 8. Profiles and settings

Built-in profiles:

| Profile | Purpose |
| --- | --- |
| Default | General documents |
| Academic article | Papers: auto OCR, finer heading detection, longer orphan joining |
| Math and science (MathJax) | Always enables MathJax and saves an accessible HTML copy |
| Slides / handouts | Exports images, inserts page breaks, keeps headers |
| Scan-heavy / OCR-first | Tesseract OCR on every page |

Profiles hold PDF settings. Apply one from Profiles > Apply Profile or from the Profile list in PDF Settings; save your own with Profiles > Save Current Settings as Profile (Ctrl+S); delete or reset from the same menu. The program remembers the theme, announcement setting, input files and folders, output path, Convert to, join and folder choices, PDF settings, profiles, window size and every pandoc option.

## 9. Command line (pdfmd-cli)

`pdfmd-cli.exe` is installed next to the program (Start menu: **Command Prompt for pdfmd-cli**). With Python, the same tool is `pdfmd` or `python -m pdfmd`.

```text
pdfmd-cli [options] INPUT [INPUT ...]
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
| `--from FORMAT` | Input format for non-PDF files (default: from the extension) |
| `--join` | Join every input into one `--to` document (`-o` sets the file) |
| `--toc`, `--toc-depth N` | Table of contents |
| `--number-sections` | Number the headings |
| `--template FILE`, `--reference-doc FILE` | Template; Word, ODT or PowerPoint styles |
| `--bibliography FILE` (repeatable), `--csl FILE`, `--citeproc` | Citations |
| `--metadata KEY=VALUE`, `--variable KEY=VALUE` (repeatable) | Document information; template variables |
| `--pandoc-option NAME=VALUE` (repeatable) | Any option from `--list-pandoc-options`, for example `epub-cover-image=cover.jpg` or `lof=true`; checked before converting |
| `--list-pandoc-options` | List every pandoc option by page, with its values |
| `--describe-images {auto,off}` | Describe pictures with the local vision model (default auto: when installed) |
| `--vision-device DEVICE` | `auto`, `cuda` (NVIDIA CUDA), `vulkan` (any GPU; `gpu` means the same), `cpu`, or a device name from `--vision-status` such as `Vulkan1` |
| `--vision-model ID` | Model to use or update (see `--vision-status`) |
| `--vision-status` | Show the engine, installed models and graphics processors |
| `--vision-update` | Download a newer engine or model (checksum-verified) |
| `--describe-photos FOLDER` | Describe every photo in a folder into an album (`-o` sets the file) |
| `--album-format {html,markdown}` | Album format (default html) |
| `--recursive` | Include subfolders with `--describe-photos` |
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
pdfmd-cli report.pdf --export-images --vision-device gpu
pdfmd-cli slides.pptx --to docx
pdfmd-cli book.docx --to epub --pandoc-option epub-cover-image=cover.jpg --toc
pdfmd-cli intro.md chapter1.docx scan.pdf --join --to html -o book.html
pdfmd-cli --list-pandoc-options
pdfmd-cli --describe-photos "C:\Photos\Italy 2026" --album-format markdown
pdfmd-cli --vision-status
pdfmd-cli --vision-update --vision-model huihui-qwen3-vl-4b-abliterated
pdfmd-cli --vision-update --vision-device cuda
pdfmd-cli report.pdf --vision-device cuda
```

Inputs that aren't PDFs are converted with pandoc to `--to` (default GitHub Markdown), with their pictures described.

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
* Built in: pandoc 3.13, Tesseract OCR 5.4 and 17 OCR languages, and the vision model (llama.cpp b12441 with Qwen3-VL 2B Instruct, abliterated); nothing else to install.
* Optional: desktop shortcut; "Convert with Document Conversion Suite" for PDF files in Explorer.
* Licenses of bundled programs: `docs\THIRD-PARTY-NOTICES.txt`.
* Documentation installed in the `docs` folder as Markdown and accessible HTML.
* Clean uninstall from Settings > Apps.

## 12. Privacy and security

* No uploads, no telemetry, no cloud processing: every conversion runs on your computer.
* PDF passwords are used only in memory, never logged, saved or passed on a command line.
* Picture descriptions run on your computer: the vision engine listens only on 127.0.0.1, with a random port and access key, and only while it is describing pictures. Remote pictures in documents are never downloaded.
* Only reading converted HTML or Markdown with MathJax contacts the jsDelivr CDN, to load MathJax. Checking for vision model updates reads vision-models.json from GitHub; updating downloads from github.com (llama.cpp) and huggingface.co (models), only when you ask. Checking for Tesseract updates, installing Tesseract or pandoc, and downloading OCR languages contact GitHub (or winget's sources), and only when you ask.

## 13. Requirements

* Windows 10 or 11, 64-bit (installer). The engine and command line also run on macOS and Linux with Python 3.8+ (`pdfmd --vision-update` downloads the llama.cpp build for your system: Metal on Apple silicon, Vulkan on Linux).
* Picture descriptions: about 3 GB of free memory (8 GB of RAM in total is enough) and 2 GB of disk space; any 64-bit x64 processor; optional graphics processor (NVIDIA, AMD or Intel, through Vulkan, which comes with their drivers; NVIDIA also through CUDA, with driver 528 or newer and about 1.5 GB more disk space).
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
| Built-in vision engine and model | `vision\` in the program folder |
| Updated or downloaded vision models, and the CUDA engine | `%LOCALAPPDATA%\DocConversionSuite\vision` |
| Photo album descriptions cache | `<album file>.descriptions.json` next to the album |
| Markdown output | Next to the PDF by default |
| Accessible HTML | Next to the Markdown file, same name, `.html` |
| Exported images | `<name>_assets` folder next to the Markdown file |
