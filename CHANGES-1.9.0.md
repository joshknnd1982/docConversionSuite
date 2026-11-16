# Document Conversion Suite 1.9.0: what changed

Version 1.9.0 makes the app **one place to convert any document to any format**, gives **every pandoc option its own labelled control**, and makes the buttons and settings easier to understand.

## Contents

1. [One window for every format](#1-one-window-for-every-format)
2. [Every pandoc option](#2-every-pandoc-option)
3. [Clearer buttons and settings](#3-clearer-buttons-and-settings)
4. [PDF Settings window](#4-pdf-settings-window)
5. [Command line](#5-command-line)
6. [Installer](#6-installer)
7. [Settings from 1.8](#7-settings-from-18)
8. [How it was tested](#8-how-it-was-tested)
9. [Known limitations](#9-known-limitations)
10. [Files added and changed](#10-files-added-and-changed)

---

## 1. One window for every format

Before 1.9.0 the main window only accepted PDFs and only made Markdown. Converting anything else meant opening a second window with its own file list, its own Convert button, and an "Also export every PDF conversion in the main window" check box. Now:

* The main window's list takes **any document pandoc reads, plus PDFs, plus whole folders** (Add Files, Ctrl+O; Add Folder, Ctrl+Shift+A; or drag and drop).
* **Convert to** (Alt+T) lists Markdown (recommended) and every pandoc output format by name: Word, EPUB, HTML, PDF, PowerPoint, OpenDocument, LaTeX, Typst, reStructuredText, AsciiDoc, slides, JATS, DocBook and the rest.
* Each file goes the right way: PDFs to Markdown with pdfmd (OCR, tables, math, the MathJax offer, unchanged); PDFs to other formats through pdfmd's accessible Markdown and then pandoc; every other document straight through pandoc.
* **Join all files into one document** (Alt+J) makes one document from every file in the list, in order, even when they are in different formats. Repeated heading ids are numbered (`introduction`, `introduction-2`) so links and screen reader heading lists stay unambiguous.
* **Keep the Markdown file too** (Alt+K) keeps the Markdown made from each PDF when converting to another format.
* **Folder options** from the old pandoc window moved here: Include subfolders of added folders (Alt+B) and File types to take from folders (Alt+Y).
* **Picture descriptions** (Alt+4) now apply to every input format from the main window.

## 2. Every pandoc option

* **One table, `pdfmd/pandoc_options.py`**, describes every option of pandoc 3.13 once: its flag, the kind of control, a label, help text, which page it is on, and which output (or input) formats it applies to. The Pandoc Options window, the pandoc command line, saved settings and the `--pandoc-option` command-line flag all use it. A test checks that every option in `pandoc --help` is offered, apart from deprecated flags, aliases and ones the app sets itself.
* **New options with their own controls** (previously only reachable by typing extra arguments): format extensions for the input and output format, metadata, metadata file, template variables (also as JSON), include in header / before body / after body, data folder, defaults file, lists of figures and tables, section number offset, top-level division, figure and table caption position, syntax definitions, LaTeX listings, indented code classes, tab stop, preserve tabs, natbib and biblatex, journal abbreviations, line width, line endings, picture resolution, reference links and location, Markdown heading style, list tables, ASCII only, strip comments, CSS, section divs, e-mail obfuscation, id and title prefix, q tags, incremental lists, slide level, link images, tracked changes, EPUB cover, title page, metadata, fonts, split level and subfolder, chunk template, PDF engine options, Typst inputs, resource path, default image extension, abbreviations, file scope, notebook output, request headers, certificate check, sandbox, verbose, quiet, fail if warnings, trace and log file.
* **Only what matters is shown**: options that do nothing for the chosen output format are hidden, and pages with nothing to show are left out. **Show advanced options** (Alt+V) reveals options most people never need.
* **Command that will run**: a read-only field shows the exact pandoc command for your settings.
* **Save Default Template / Reference Document / Highlight Style** save pandoc's own files to customise, and offer to use them right away.
* **Filters** are an ordered list with Add Lua Filter, Add Filter Program, Remove, Move Up and Move Down, because the order matters to pandoc.
* **Works with older pandoc**: the window reads `pandoc --help` and hides options your pandoc doesn't have. Pandoc 3.8+ gets `--syntax-highlighting` and `--math-method` (the old `--highlight-style`, `--mathjax` and `--mathml` print deprecation warnings in 3.13); older versions get the old flags.
* Friendly names were added for the formats pandoc 3.13 added: BBCode variants, flat OpenDocument, legacy AsciiDoc.

## 3. Clearer buttons and settings

* **Settings are check boxes, actions are buttons.** "How citations are handled" is now four radio buttons instead of a check box plus a hidden rule.
* **The same words everywhere**: Clear List (was "Empty List" in one window and "Clear List" in the other), Remove Selected Files, Choose Output (was "Browse Output"), Show Output Folder (button and menu).
* **No confusing cross-window check box**: "Also export every PDF conversion in the main window to this format" is replaced by Convert to plus Keep the Markdown file too.
* **Controls that do nothing are hidden**, not just disabled: folder settings appear when the list has a folder; Join and Keep Markdown appear when they apply.
* **Clear List asks first** when the list has more than one item.
* **One main action per window**: Convert in the main window; OK and Cancel in the settings windows.

## 4. PDF Settings window

The PDF options (profile, OCR mode and language, export images, page breaks, preview, header and footer removal, uppercase headings, orphan joining, heading size ratio, orphan line width, equations, accessible HTML copy) moved from the main window to **PDF Settings** (Ctrl+Shift+P, or Alt+G in the main window), with the same Alt keys as before. Defaults are unchanged: OCR on Auto, and the MathJax offer defaults to Yes.

## 5. Command line

* `--from FORMAT`, `--join`, `--toc`, `--toc-depth`, `--number-sections`, `--template`, `--reference-doc`, `--bibliography` (repeatable), `--csl`, `--citeproc`, `--metadata KEY=VALUE` and `--variable KEY=VALUE` (repeatable).
* `--pandoc-option NAME=VALUE` sets any option in the table by name or pandoc flag, for example `--pandoc-option epub-cover-image=cover.jpg`. Values are checked before anything is converted.
* `--list-pandoc-options` lists every option by page with its values.
* `--pandoc-args` still works for anything typed by hand.

## 6. Installer

* The Explorer command **Convert with Document Conversion Suite** now appears on Word, OpenDocument, RTF, EPUB, HTML, Markdown, PowerPoint, LaTeX, reStructuredText, AsciiDoc, Org, Jupyter, Typst and FictionBook files and on folders, not only on PDFs.

## 7. Settings from 1.8

* Old settings and profiles load unchanged.
* If "Also export every PDF conversion" was on, Convert to is set to that format and Keep the Markdown file too is checked, so the same files are made. A line in the log says so.
* The pandoc window's subfolder and file type choices move to the main window.

## 8. How it was tested

* `python -m pytest`: 152 tests.
  * `tests/test_pandoc_options.py`: the command line each option produces (every option in the table), defaults adding nothing, options for other formats left out, version gating, extensions, citations, the defaults file, old settings loading, command-line parsing, every pandoc option offered, joining Markdown and Word files into one HTML file, and **converting a sample to every one of pandoc's output formats** (PDF skipped: it needs a separately installed engine).
  * `tests/test_gui_access_keys.py`: builds the main window, PDF Settings and Pandoc Options (twelve output formats, with and without advanced options) and checks that every visible interactive control has a description, every list, edit field and combo box has a label created right before it, and Alt keys are unique among the controls visible together (and avoid the menu bar keys in the main window).
  * The existing batch and vision tests.
* End-to-end runs of the main window's conversion code: a PDF to Word with the Markdown kept, a Word file to EPUB, and a PDF, a Markdown file and a Word file joined into one HTML file.
* Settings saved by 1.8.0 were loaded into the new window.

## 9. Known limitations

* **Screen reader check of the new windows**: the automated tests check labels, descriptions and keys, but speech with NVDA and JAWS should be confirmed by hand, especially the check-box lists of format extensions (native Windows list views, which screen readers announce as checked or not checked).
* **PDF output** needs a PDF engine (a LaTeX distribution, Typst, WeasyPrint and others) installed separately; the app says so when you choose PDF.
* **Joined documents** keep the document information (title, author) of the first file.
* Footnote and link targets that point to another joined file are not rewritten.

## 10. Files added and changed

| File | Change |
| --- | --- |
| `pdfmd/pandoc_options.py` | New: the option table, access key assignment, extension and help parsing |
| `pdfmd/pandoc_support.py` | Table-driven `build_args`, `supported_flags`, `list_extensions`, `join_convert`, `command_preview`, default template / reference document / highlight style, `--math-method` and `--syntax-highlighting` |
| `pdfmd/gui_pandoc.py` | Rewritten as `PandocOptionsDialog`: settings only, built from the table |
| `pdfmd/gui_pdf_settings.py` | New: `PdfSettingsDialog` and the PDF option constants |
| `pdfmd/app_gui.py` | Main window: any input, folders, Convert to, Join, Keep Markdown, new menus and shortcuts, routing of each file, settings migration |
| `pdfmd/cli.py` | New pandoc flags, `--join`, `--pandoc-option`, `--list-pandoc-options` |
| `packaging/installer.iss` | Explorer command for documents and folders |
| `tests/test_pandoc_options.py`, `tests/test_gui_access_keys.py` | New tests |
| `CLAUDE.md` | New: rules for AI assistants changing this app |
| `README.md`, `ACCESSIBILITY.md`, `FEATURES.md` | Updated for 1.9.0 |
