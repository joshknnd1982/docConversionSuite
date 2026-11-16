# CLAUDE.md: rules for working on Document Conversion Suite

These rules are for Claude (and any other AI model or developer) changing this
repository. Follow them in order of priority: **accessibility first, then
correctness, then features, then polish.** When a rule here conflicts with a
habit or a default, the rule here wins.

## 1. What this project is

Document Conversion Suite is an accessible, offline, privacy-first document
converter for Windows, used mainly by blind and low-vision people with NVDA,
JAWS and Narrator. It is a wxPython desktop app plus a command-line tool, built
on the **pdfmd** engine (PDF to Markdown) and on **pandoc** (every other
format), with built-in Tesseract OCR and a local AI vision model for picture
descriptions.

| Area | Files |
| --- | --- |
| Main window (wxPython) | `pdfmd/app_gui.py` |
| Pandoc window (Ctrl+P) | `pdfmd/gui_pandoc.py` |
| Pandoc logic (finding pandoc, formats, building arguments, running it) | `pdfmd/pandoc_support.py` |
| Screen reader helpers (`describe()`, `Announcer`) | `pdfmd/gui_a11y.py` |
| Tesseract window / logic | `pdfmd/gui_tesseract.py`, `pdfmd/tesseract_support.py` |
| Vision model window / logic, photo albums | `pdfmd/gui_vision.py`, `pdfmd/vision.py`, `pdfmd/album.py`, `pdfmd/docimages.py` |
| PDF engine | `pdfmd/pipeline.py`, `extract.py`, `transform.py`, `tables.py`, `equations.py`, `figures.py`, `render.py`, `mathjax.py`, `models.py` |
| Command line | `pdfmd/cli.py` |
| Version number | `pdfmd/__init__.py` (`__version__`) and `pyproject.toml` |
| Build and installer | `packaging/build.py`, `packaging/fetch_vendor.py`, `packaging/pdfmd.spec`, `packaging/installer.iss` |
| User guides | `README.md`, `ACCESSIBILITY.md`, `FEATURES.md`, `CHANGES-<version>.md` |
| Tests | `tests/` (pytest) |

GitHub repository: **https://github.com/joshknnd1982/docConversionSuite**
(remote `origin`). Releases: https://github.com/joshknnd1982/docConversionSuite/releases

## 2. Accessibility rules (never break these)

`ACCESSIBILITY.md` section 3.3 "Rules any change must follow" is part of this
file. Read it before touching any GUI code. In short:

1. Native wx controls only. No custom-drawn controls, no colour-only meaning, no hard-coded colours.
2. Every control has a visible label (a `wx.StaticText` created immediately before it, or its own label) and a `describe()` help text.
3. Every labelled control has an Alt+letter access key that is unique among the controls visible at the same time. In the main window, never use F, P, V or H (menu bar keys).
4. Every command is also in the menu bar, with its shortcut after a tab (`"&Convert\tF5"`).
5. Creation order is Tab order. Create controls in logical reading order.
6. Move focus away before disabling or hiding a focused control.
7. Never block the GUI thread. Touch wx objects from worker threads only through `wx.CallAfter`.
8. Announce the start, end, failure and cancellation of long operations with `Announcer.speak`; keep progress announcements sparse. Errors also go in a message dialog.
9. Keep the accessible output defaults: MathJax offer defaults to Yes, `lang` on HTML, table header rows, descriptive alt text, pandoc's automatic math choice (MathJax for HTML, MathML for EPUB, native equations for Office formats).
10. After any GUI change, update the keyboard tables in `ACCESSIBILITY.md` and `SHORTCUTS_TEXT` in `app_gui.py`.

If a feature can't be made accessible, it doesn't ship.

## 3. Goal 1: every pandoc feature, for input and output

Today the main window only takes PDFs, and the pandoc window exposes a subset
of pandoc's options (the rest only through "Extra pandoc arguments"). The goal
is that **every input format, every output format and every pandoc option is
available through normal, labelled controls**, with "Extra pandoc arguments"
kept only as an expert fallback.

### 3.1 Inputs and outputs

1. The main window accepts **any file pandoc can read, plus PDFs**. Rename "Add PDFs..." / "Add PDF Files..." to "Add Files..." and add "Add Folder...". PDFs go through pdfmd first (OCR, tables, math, pictures); every other format goes straight to pandoc.
2. The main window has an **Output format** choice listing Markdown (pdfmd's default) and every pandoc output format, by friendly name (`FORMAT_NAMES` in `pandoc_support.py`).
3. The list of formats always comes from the **running pandoc** (`pandoc --list-input-formats`, `--list-output-formats`), never from a hard-coded list alone. `FORMAT_NAMES` only supplies friendly names; unknown formats are still offered by their pandoc name.
4. Support pandoc **format extensions** (`+ext` / `-ext`): for the chosen input and output format, list the extensions from `pandoc --list-extensions=FORMAT` as check boxes, each checked or unchecked by pandoc's default.
5. Support **combining several inputs into one output** (pandoc concatenates its inputs) with a check box "Combine all files into one document", off by default. When off, each file is converted separately (current behaviour).
6. Support **URLs as input** (pandoc reads them) through an "Add Web Address..." command. Never fetch a URL the user didn't type.
7. Binary outputs (docx, odt, pptx, epub, pdf, chunkedhtml) are always written to a file, never to the log.

### 3.2 Options

1. Build options from **one data table** in `pandoc_support.py`, not from hand-written controls one by one. Each entry has: the pandoc flag, kind (on/off, number, choice, text, file, several files, key=value list), friendly label, one-sentence help text, default, and the output formats it applies to. Both `build_args()` and the GUI read this table, so adding an option is one table entry plus a test.
2. Cover **every option in `pandoc --help` of the bundled pandoc version** (3.13 at the time of writing; check `packaging/fetch_vendor.py`). Check flag names against that version's `pandoc --help` and the matching manual at https://pandoc.org/MANUAL.html; never invent or guess a flag, and handle renamed or deprecated flags by version. Groups to cover, at minimum:
   * **General**: from/to format, output folder, data directory, defaults file (`--defaults`), resource path, verbose/quiet, fail on warnings, log file, sandbox.
   * **Reader**: shift heading levels, indented code classes, default image extension, file scope, metadata (`-M`), metadata file, preserve tabs, tab stop, track changes (Word input), extract media, abbreviations, strip comments.
   * **Writer (general)**: standalone, template, variables (`-V`), table of contents and depth, wrap, columns, line endings, DPI, strip comments, syntax highlighting style or none, custom syntax definitions, include in header / before body / after body, link images.
   * **Math**: automatic (accessible default), MathJax, MathML, KaTeX, WebTeX, GladTeX, plain.
   * **Citations**: citeproc, bibliography, CSL style, citation abbreviations, natbib, biblatex.
   * **HTML and slides**: embed resources, CSS files, section divs, email obfuscation, id prefix, title prefix, HTML `<q>` tags, ASCII output, incremental lists, slide level, number sections and number offset.
   * **Markdown and text**: reference links, reference location, ATX/Setext headings, list tables, top-level division.
   * **Word, ODT, PowerPoint**: reference document.
   * **EPUB**: cover image, title page, EPUB metadata file, embedded fonts, chapter split level, EPUB subdirectory.
   * **Chunked HTML**: split level, chunk template.
   * **PDF**: PDF engine and PDF engine options, LaTeX listings.
   * **Jupyter**: ipynb output (all, none, best).
   * **Network**: request headers, skip certificate check (off by default, with a warning in its help text).
   * **Tools menu**: show pandoc's default template for a format, show a default data file (for example `reference.docx`) and save it, list highlight styles. These help users make their own reference documents and templates.
3. Show only the options that apply to the chosen output format; options for other formats are hidden, not just disabled. A check box **"Show advanced options"** (off by default) reveals the rarely used ones. Unchecked/empty options add nothing to the pandoc command, so pandoc's own defaults apply.
4. Every option is saved in **profiles** (`PandocOptions.to_dict` / `from_dict`) and old profiles keep loading.
5. Every option is reachable from the **command line** too (`pdfmd --to FORMAT --pandoc-args ...` already passes anything through; add named flags for the common ones).
6. Add a read-only **"Pandoc command"** text field that shows the exact command that will run, so users can learn and check it.
7. pandoc options pass to `subprocess` as an argument list, never through a shell. Keep `shlex` parsing for the extra-arguments field.

### 3.3 Tests for Goal 1

For every option table entry, a test checks the arguments `build_args()`
produces. Add a test that every output format in `--list-output-formats` can
be chosen and converts a small Markdown sample (skip if pandoc is missing).
Run `python -m pytest` before every commit.

## 4. Goal 2: buttons and controls that are not confusing

1. **Settings are check boxes, actions are buttons.** Anything that is on or off is a `wx.CheckBox`. A button only does something right now (Convert, Add Files..., Stop).
2. **Choose one of 2 to 5** uses radio buttons (`wx.RadioBox` or `wx.RadioButton` group with a label). **Choose one of many** uses a `wx.Choice`. Never a button that cycles through values.
3. **Label check boxes positively** with what happens when checked: "Include subfolders", not "Don't skip subfolders". No "Also ..." labels that depend on another window (for example, the pandoc window's "Also export every PDF conversion in the main window to this format" should become an output-format choice in the main window).
4. **Button labels are a verb plus what it acts on**: "Add Files...", "Remove Selected Files", "Convert", "Open Output Folder". Add "..." only when the button opens a dialog.
5. **Use the same word for the same thing everywhere.** Today the main window says "Empty List" and the pandoc window says "Clear List": pick "Clear List" for both. Same for "Browse..." versus "Choose ...": use "Choose Output Folder...".
6. **One main action per window.** The Convert button is the default button (Enter activates it) and is placed last in the Tab order of the window's controls, after all settings.
7. **Group related settings** in labelled `wx.StaticBox` groups, in the order the user decides them: what to convert, what to make, how, where to save, then Convert.
8. **Don't show controls that do nothing for the current choice.** Hide them, and say what is missing in the status line instead of silently disabling a button (for example "Add at least one file to convert.").
9. **Every destructive action asks first** (Clear List with more than one item, overwriting existing output files) and the safe answer is the default.
10. **Help text says what the control does and when to use it**, in plain words, not just the pandoc flag. The flag name may follow in brackets for experts.
11. **Keep the number of buttons small.** If a window has more than six buttons in a row, move rarely used commands to the menu bar.
12. Before changing the layout, list every current control of the window with its label and access key, then write the new list, and check that every access key is still unique and every old feature still exists.

## 5. Goal 3: commit, push and release

Do this at the end of every finished piece of work that the user asked to
release. Do it on the user's Windows computer, from the repository root.

1. **Version.** Bump the version with semantic versioning (new features = minor, for example 1.8.0 to 1.9.0; fixes only = patch). Change it in **all** of: `pdfmd/__init__.py` (`__version__`), `pyproject.toml`, the README version badge and download line, the "Version:" line in `ACCESSIBILITY.md`, and the README "What's new" section.
2. **Change log.** Write `CHANGES-<version>.md` in the style of `CHANGES-1.8.0.md`: what changed, why, how it was tested, known limitations, files changed. Update `FEATURES.md` and `ACCESSIBILITY.md` for every new control or shortcut.
3. **Ignored Markdown files.** `.gitignore` ignores `*.md` except listed files. When adding a new Markdown file, add a `!name.md` line so it is committed (check with `git status`).
4. **Tests.** Run `python -m pytest`. Don't release with failing tests. Also start the app (`python -m pdfmd.app_gui` or `pdfmd-gui`) and check the changed windows open without errors.
5. **Build.** Run:
   ```bash
   python -m pip install -r requirements.txt pyinstaller
   python packaging/build.py
   ```
   It downloads the bundled pandoc, Tesseract and vision model if `packaging/vendor/` is empty, and needs Inno Setup 6. The result is `dist/installer/DocConversionSuite-<version>-setup.exe`. Check that the file exists and is **under 2 GiB** (GitHub's limit per release file; 1.8.0 was about 1.7 GB). If it is too big, stop and tell the user; never split or trim the bundled tools without asking.
6. **Commit.** Commit to `main` (this repository's history is on `main`). Stage files by name, never `git add -A` blindly, and never commit `dist/`, `packaging/build/`, `packaging/vendor/`, `.claude/`, installers, models or other binaries. Commit message title: `Document Conversion Suite <version>: <short summary>`, then a short body. End it with the co-author line Claude Code supplies.
7. **Push and tag.**
   ```bash
   git push origin main
   git tag v<version>
   git push origin v<version>
   ```
   Never force-push, never rewrite pushed history, never move or delete an existing tag or release.
8. **Release.** Create the GitHub release with the installer attached:
   ```bash
   gh release create v<version> "dist/installer/DocConversionSuite-<version>-setup.exe" --title "Document Conversion Suite <version> (<short summary>)" --notes-file <release-notes-file>
   ```
   Release notes follow the 1.8.0 release: a one-paragraph summary, a **Download** section naming the setup file and its size and saying the installer is screen reader accessible, then **What's new**, linking to `CHANGES-<version>.md`. The new release becomes "Latest".
9. **Verify.** Run `gh release view v<version>` and check the installer is listed with the right size. Give the user the release link.
10. If any step fails, stop, report the exact error, and don't skip ahead (for example, never publish a release without the installer, and never tag a commit whose tests failed).

## 6. How to work

1. **Plan before large changes.** For Goal 1 and Goal 2, write the plan (option table design, new layout of each window with every control and access key) and show it to the user before rewriting GUI code.
2. **Small steps.** Change one window or one option group at a time, run the tests after each, and keep the app working between steps.
3. **Don't remove features.** Every current feature, menu command, shortcut and command-line flag keeps working unless the user agrees to remove it. Keep old profile files loading.
4. **Keep it offline and private.** No telemetry, no uploads, no new network access except downloads the user starts (pandoc, Tesseract, vision model updates), checksum-verified as today.
5. **Python 3.8+ compatible**, `black` line length 100, type hints on new functions.
6. **Write for the user.** All labels, help texts, messages and docs are plain, short English that reads well with a screen reader: no decorative symbols or emoji in labels, no jargon without explanation.
7. **Don't guess.** If pandoc's behaviour, a flag, or the user's wish is unclear, check `pandoc --help` and the manual, or ask the user.
