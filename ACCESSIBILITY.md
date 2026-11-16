# Document Conversion Suite: Accessibility Guide

Document Conversion Suite (built on the pdfmd engine) is designed to be fully usable with a screen reader and with the keyboard alone. It also produces accessible documents: math that screen readers can speak, HTML with real structure, and accessible defaults when converting to other formats with pandoc.

This guide has three parts:

1. **For people**: what the accessibility features are and how to use them.
2. **What changed and why**: the audit of the old Tkinter interface, and how each problem was fixed.
3. **For AI models and developers**: a precise, structured description of the accessibility design, the rules any change must follow, and how to test them.

Version: 1.7.1

---

## Part 1: For people

### 1.1 Quick start with a screen reader

1. Start **Document Conversion Suite** from the Start menu. Focus starts in the **Input PDF files** list.
2. Press **Ctrl+O** to add PDF files. A standard Windows Open dialog appears; you can select several files.
3. Press **F5** (or **Ctrl+Enter**) to convert.
4. Your screen reader announces progress at 25, 50 and 75 percent, then the result, for example "Conversion complete. Saved notes.md."
5. If the document contains math, a dialog asks whether to enable MathJax. The answer defaults to **Enable MathJax**, so pressing Enter accepts it.
6. Press **Ctrl+Shift+M** to open the Markdown file, **Ctrl+Shift+H** to open the accessible HTML version, or **Ctrl+Shift+F** to open the output folder.
7. Press **F1** at any time for the full list of keyboard shortcuts.

To convert to Word, EPUB, HTML, LaTeX or any other format, press **Ctrl+P** to open the **Convert Any Document with Pandoc** window.

Scanned PDFs are pictures of text that screen readers can't read. OCR is set to **Auto** by default, so scanned pages are recognised with Tesseract OCR and become real, readable text. If Tesseract isn't installed, the program tells you which file is scanned and offers to install it. Press **Ctrl+T** at any time to install or update Tesseract and to add OCR languages.

### 1.2 Screen readers supported

The program uses native Windows controls, which every Windows screen reader understands. It was built and checked with NVDA in mind and also works with JAWS, Narrator, System Access, Dolphin SuperNova and ZoomText.

Spoken status announcements are sent directly to the running screen reader (NVDA, JAWS, System Access, Dolphin, ZoomText, PC-Talker or ZDSR). If no screen reader is running, nothing is spoken: the program never falls back to its own synthetic voice.

### 1.3 Accessibility features of the program

| Feature | What it means for you |
| --- | --- |
| Native Windows controls | Every list, edit field, combo box, check box, spin box, button, progress bar and tab is a real Windows control with a role, a name and a state your screen reader reads. |
| Every control is labelled | Each control's visible label is also its accessible name. For example, the OCR mode combo box is read as "OCR mode, combo box, Off: native text only". |
| Help text is spoken | Each control has a description that screen readers read after the name (in NVDA this is the "object description"). It explains what the control does and its shortcut. Mouse users see the same text as a tooltip. |
| Everything is in the Tab order | Tab and Shift+Tab reach every control in a logical top-to-bottom order, including the conversion log and the Open Output Folder button. |
| Alt+letter access keys everywhere | Every labelled control has a unique Alt+letter key. They work from anywhere in the window, not only inside the current group. |
| Standard menu bar | File, Profiles, View and Help menus list every command. Shortcuts are shown next to each menu item, so screen readers speak them. Press Alt or F10 to reach the menu bar. |
| Spoken announcements | Start, progress (every 25 percent), completion, errors, cancellation and batch results are announced. Turn this off or on with View > Announce Status with Screen Reader. |
| Speak status on demand | Press **Ctrl+Shift+S** to hear the current status again. The status is also in the status bar (NVDA+End, JAWS Insert+Page Down). |
| Focus is never lost | When a button you are on becomes unavailable (for example Convert when a conversion starts), focus moves to the next sensible control (Stop) instead of disappearing. |
| Readable log | The conversion log is a read-only edit field. Read it with the arrow keys; new messages never move your cursor while you read. |
| Native dialogs | File, folder, password, profile name and message dialogs are standard Windows dialogs. |
| Errors are always reported | Problems open a message dialog (read automatically) and are announced. Failed files in a batch are listed by name. |
| High Contrast and dark mode | The program uses system colours, so Windows High Contrast themes work. View > Theme offers Follow Windows Setting, Light and Dark. |
| Input list shows every file | Each file is listed by name and folder. Press Delete to remove the selected files. |
| Explorer integration | The installer can add **Convert with Document Conversion Suite** to the context menu of PDF files, reached with the Applications key or Shift+F10. |
| Keyboard help | F1 opens all shortcuts in a read-only text field you can read line by line. |

### 1.4 Accessible documents (output)

| Output feature | Details |
| --- | --- |
| Accessible math with MathJax | When a document contains math, the program offers to enable MathJax (the default answer is Yes). MathJax 4 turns every expression into accessible math: screen readers speak it in natural language ("a squared plus b squared equals c squared"), it is available as Nemeth or UEB Braille, and you can explore complex expressions piece by piece with the arrow keys. |
| Math found inside sentences | Math written in normal sentences, such as "E = mc²", "α + β³ = γ" or "xᵢ ≥ 0", is detected and converted to proper math, so it is spoken as math and not as a string of symbols. Prices such as "$5 and $10" are left alone. |
| Accessible HTML copy | An HTML version is saved next to the Markdown file. It declares the document language (so screen readers use the right voice), keeps the heading structure, uses real table header cells, has a "Skip to content" link and a main landmark, and contains MathJax math. |
| Pictures are described | A small AI vision model running on your computer describes photos, charts, graphs, maps and diagrams. With Export images on, the description is the picture's alternative text, read by screen readers. Otherwise the description is written in the text as a block quote starting "Image description", so you meet it while reading. Pictures of text get their recognised text ("Text in image"). Word, EPUB, HTML, PowerPoint and other documents converted with pandoc get alternative text for pictures that have none. |
| Photo albums | Describe a Folder of Photos (Ctrl+D) writes a web page with a heading per photo (press H in your screen reader to move from photo to photo), the photo's title as its alternative text and the full description as its caption, or a Markdown file. |
| Pandoc output | Converting with pandoc uses accessible math for each format: MathJax for HTML and slides, MathML for EPUB, and native equations for Word, OpenDocument and PowerPoint, which Word's own accessibility tools and screen readers can read. The document language is always set. |
| Scanned PDFs become text | Auto OCR (the default) recognises scanned pages with Tesseract, turning image-only PDFs into accessible text. |
| Real headings and tables | The engine detects headings from font sizes and rebuilds tables with header rows, so documents can be navigated by heading and by table. Ruled tables are read from the lines drawn in the PDF, so every row, column and header survives. |
| Tables stay tables | Tables are kept as real tables in Markdown, in the HTML copy (header cells marked as column headers with `scope="col"`), and in every pandoc format that has tables (Word, ODT, EPUB, HTML, LaTeX and others). |

Choose what happens when math is found with **When equations are found** (Alt+Q):

* **Ask me (MathJax recommended)**: the default. A dialog asks each time; Enter accepts. In a batch you can apply your answer to the remaining files.
* **Always enable MathJax**
* **Never enable MathJax**

Check **Also save an accessible HTML copy of every document** (Alt+N) to get an HTML copy even of documents without math.

The HTML pages and Markdown files load MathJax from the jsDelivr content delivery network when you open them, so math rendering needs an internet connection at reading time. The conversion itself stays fully offline.

### 1.5 Keyboard reference: main window

#### Commands

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Add PDF files |
| Ctrl+Shift+O | Choose output file or folder |
| F5 or Ctrl+Enter | Start conversion |
| Shift+F5, or Esc while converting | Stop conversion |
| Ctrl+P | Convert any document with pandoc |
| Ctrl+T | Tesseract OCR: install, update, add languages |
| Ctrl+Shift+F | Open the output folder |
| Ctrl+Shift+M | Open the converted Markdown file |
| Ctrl+Shift+H | Open the accessible HTML file |
| Ctrl+Shift+S | Speak the current status |
| Ctrl+S | Save current settings as a profile |
| Delete (in the input list) | Remove the selected files |
| F1 | Keyboard shortcuts |
| Alt+F4 | Exit |

#### Go to a control (hold Alt)

| Key | Control | Type |
| --- | --- | --- |
| Alt+I | Input PDF files | List |
| Alt+A | Add PDFs | Button |
| Alt+R | Remove Selected | Button |
| Alt+Y | Empty List | Button |
| Alt+O | Output file or folder | Edit field |
| Alt+B | Browse Output | Button |
| Alt+E | Profile | Combo box |
| Alt+M | OCR mode | Combo box |
| Alt+G | OCR language | Editable combo box |
| Alt+X | Export images | Check box |
| Alt+K | Insert page breaks | Check box |
| Alt+3 | Preview first 3 pages only | Check box |
| Alt+T | Remove repeating header and footer text | Check box |
| Alt+U | Promote uppercase lines to headings | Check box |
| Alt+J | Join short orphan lines into paragraphs | Check box |
| Alt+Z | Heading size ratio (percent of body text) | Spin box |
| Alt+W | Orphan line width (characters) | Spin box |
| Alt+Q | When equations are found | Combo box |
| Alt+N | Also save an accessible HTML copy of every document | Check box |
| Alt+C | Convert | Button |
| Alt+S | Stop | Button |
| Alt+D | Open Output Folder | Button |
| Alt+L | Conversion log | Read-only edit field |

An Alt key on a button presses it; on a check box it toggles the box and moves focus to it.

Menu bar keys: Alt+F File, Alt+P Profiles, Alt+V View, Alt+H Help. No control uses those letters. Help > Check for Tesseract Updates opens the Tesseract window and checks right away.

### 1.6 Keyboard reference: Convert Any Document with Pandoc window

The window has four pages in a tab control, in the order you use them: settings first, the files and folders to convert last. **Ctrl+Tab** and **Ctrl+Shift+Tab** move between pages; your screen reader announces the page name. Focus starts on the output format. The Convert, Install Pandoc and Close buttons are always available; Stop appears while a batch runs.

| Key | Action |
| --- | --- |
| F5 or Alt+V | Convert every file and folder in the list (with an empty list, moves to page 4 and the Add Files button) |
| Alt+P | Stop a running batch after the current file (shown only while converting) |
| Esc | Close (settings are kept; asks first while a batch runs) |
| Alt+P | Install Pandoc (shown only when pandoc is missing) |

**Page 1, Format and output:** Alt+F input format, Alt+O output format, Alt+D output folder, Alt+B browse, Alt+X also export every PDF conversion in the main window, Alt+C describe pictures.

**Page 2, Document options:** Alt+S standalone document, Alt+C table of contents, Alt+N number sections, Alt+E embed images and styles, Alt+D depth of contents, Alt+M math rendering, Alt+H code highlighting style, Alt+W line wrapping, Alt+T document title, Alt+L document language, Alt+G shift heading levels.

**Page 3, Citations, templates and filters:** Alt+C process citations, Alt+B bibliography files, Alt+I choose bibliography, Alt+S citation style, Alt+F choose style file, Alt+R reference document, Alt+U choose document, Alt+T template, Alt+M choose template, Alt+L filters, Alt+E choose filter, Alt+N PDF engine, Alt+X extra pandoc arguments.

**Page 4, Files and folders:** Alt+I list of files and folders, Alt+A add files, Alt+F add folder, Alt+R remove selected (Delete works in the list too), Alt+E clear list, Alt+S include subfolders, Alt+T file types to take from folders, Alt+G pandoc log.

The list is a standard multiple-selection list box. Each folder is read as "Folder *name*, *N* files" (or "with subfolders, *N* files"), so you hear how many files it will contribute; the count updates when you change the subfolder or file type settings. Select a range with Shift+arrows; to pick items that aren't next to each other, press Shift+F8, move with the arrows and press Space on each item (Shift+F8 again ends this mode). Then press Delete. Adding, removing and clearing are announced with the new totals. During a batch the status line at the top of the window reads "Converting *n* of *total*: *file name*", and progress is announced every quarter of a batch of eight files or more.

### 1.7 Keyboard reference: Tesseract OCR window

Open it with **Ctrl+T** (File > Tesseract OCR) or Help > Check for Tesseract Updates. Focus starts in the Status field, which says whether Tesseract is installed, its version and location, whether an update is available, and how many OCR languages are installed. Downloads show progress and are announced.

| Key | Control |
| --- | --- |
| Alt+S | Status (read-only text) |
| Alt+U | Check for Updates |
| Alt+I | Install Tesseract, Install Update or Reinstall Tesseract |
| Alt+L | Installed languages list |
| Alt+A | Add language |
| Alt+Q | Quality (fast or best) |
| Alt+D | Download Language |
| Alt+C or Esc | Close |

Installing uses the Windows Package Manager (winget) in a console window your screen reader can read; without winget the official installer is downloaded from GitHub and started.

### 1.7a Keyboard reference: Vision Model window

Open it with **Ctrl+I** (File > Vision Model) or Help > Check for Vision Model Updates. Focus starts in the Status field. Downloads show progress, announce every 25 percent, and can be stopped.

| Key | Control |
| --- | --- |
| Alt+S | Status (read-only text) |
| Alt+D | Describe pictures in documents (check box) |
| Alt+P | Processor: Automatic, NVIDIA GPU with CUDA (shown when an NVIDIA card is found; says whether the CUDA engine is installed), Any GPU with Vulkan, Only a particular graphics processor, CPU only. Choosing CUDA before its engine is installed announces how to download it |
| Alt+M | Model |
| Alt+I | Model information (read-only text) |
| Alt+U | Check for Updates |
| Alt+V | Update Vision Model (or Download Vision Model) |
| Alt+T | Test on a Picture (the description is spoken and added to the log) |
| Alt+R | Remove Downloaded Model |
| Alt+W | Stop Download |
| Alt+L | Log |
| Alt+C or Esc | Close |

### 1.7b Keyboard reference: Describe a Folder of Photos window

Open it with **Ctrl+D** (File > Describe a Folder of Photos). Each photo's description is added to the log as it is written; progress is announced every 25 percent.

| Key | Control |
| --- | --- |
| Alt+F | Photo folder |
| Alt+B | Browse for the folder (the number of photos is announced) |
| Alt+A | Save as: Web page (HTML) or Markdown |
| Alt+O | Output file |
| Alt+H | Choose File |
| Alt+U | Include photos in subfolders |
| Alt+W | Open the page when finished |
| Alt+D or F5 | Describe Photos |
| Alt+S | Stop (after the current photo) |
| Alt+P | Open Page |
| Alt+L | Log |
| Alt+C or Esc | Close |

In the main window, **Alt+4** toggles **Describe pictures with the local AI vision model**. In the pandoc window, **Alt+C** toggles the same option for pandoc conversions.

### 1.8 Accessible installer

The installer is built with Inno Setup and uses only standard Windows controls, so NVDA, JAWS and Narrator read every page. Operate it with Tab, Shift+Tab, Space (check boxes), the arrow keys (radio buttons), **Alt+N** (Next), **Alt+B** (Back) and Enter.

It installs for the current user without an administrator prompt; you can choose to install for all users. Optional tasks: a desktop shortcut and the "Convert with Document Conversion Suite" Explorer menu item. Pandoc 3.13 and Tesseract OCR 5.4 (with 17 OCR languages plus orientation detection) are built in, so every feature works offline right after installing. Nothing opens a console window during setup. The Start menu gets shortcuts for the program, this Accessibility Guide, the Features Guide and a command prompt for `pdfmd-cli`.

### 1.9 Known limitations

* The progress bar is not a Tab stop (Windows progress bars never are). Progress is announced, shown in the status bar, and available with Ctrl+Shift+S.
* For the two spin boxes, Windows attaches the help description to the arrow buttons instead of the edit field, so some screen readers don't read it on focus. Their labels already explain them ("Heading size ratio (percent of body text)", "Orphan line width (characters)").
* MathJax loads from the internet when you open a converted document; without a connection, math shows as LaTeX source. Pandoc's Word, OpenDocument and EPUB output doesn't need MathJax.
* Picture descriptions are written by a small AI model. They are usually right about what a picture shows, but can misread small numbers on charts or miscount items. Check descriptions of important figures. The larger 4B model (Ctrl+I) is more accurate on powerful computers.
* OCR quality depends on the scan. Check OCR output before relying on it.
* Pandoc and Tesseract are built in. A copy you install yourself takes priority, so you can use newer versions. The newest Tesseract Windows build is published by UB Mannheim and can lag behind the newest Tesseract source release.
* Very complex tables (merged cells, nested tables) are kept as faithfully as each format allows. Markdown pipe tables can't merge cells, so merged cells are repeated or left empty.

---

## Part 2: What changed and why

### 2.1 Audit of the original Tkinter interface (pdfmd 1.6.0)

| # | Problem | Effect for screen reader users |
| --- | --- | --- |
| 1 | Tkinter draws its own widgets and implements neither Microsoft Active Accessibility (MSAA) nor UI Automation. | Entries, combo boxes, check boxes, spin boxes and the progress bar had no name, no role or no state. Screen readers saw most of the window as one unlabelled pane. |
| 2 | Labels were separate `ttk.Label` widgets with no programmatic link to their controls. | Even reachable controls were announced without saying what they were for. |
| 3 | The log was a `tk.Text` widget in the disabled state, which cannot take focus. | The log, the only place batch errors appeared, could not be read. |
| 4 | "Open folder" was a label with a mouse-click binding. | Not focusable, no keyboard access. |
| 5 | Help existed only as hover tooltips. | Keyboard and screen reader users never got the help. |
| 6 | No menu bar. | Commands and shortcuts could not be discovered. |
| 7 | No Alt+letter access keys; Esc bound globally with `bind_all`. | No quick navigation; Esc fired inside drop-downs and dialogs. |
| 8 | The status line was a plain label. | Start, completion and errors were silent. |
| 9 | Buttons were disabled while focused. | Focus fell back to the window and the screen reader said nothing. |
| 10 | `tkinter.simpledialog` for password and profile name. | Prompt text and fields often unreadable. |
| 11 | Hard-coded colours, some below the 4.5:1 WCAG contrast ratio. | High Contrast themes ignored; poor contrast for low vision users. |
| 12 | Decorative glyphs in labels ("▶ Convert", "———"). | Read aloud literally ("black right-pointing triangle"). |
| 13 | Several selected files were shown only as "3 files selected". | No way to hear or remove individual files. |
| 14 | Math inside sentences stayed as Unicode symbols, and nothing made math accessible. | Equations were read as strings of symbols, or skipped. |
| 15 | OCR was off by default, and a missing Tesseract only produced a console warning the GUI never showed. | Scanned PDFs came out empty with no explanation. |
| 16 | Table rows were repeated as plain text after multi-block tables; short lines were merged into table rows and headings; ruled tables lost rows and columns. | Tables and headings were broken, so table and heading navigation failed. |

### 2.2 Fixes

| # | Fix |
| --- | --- |
| 1 | The interface was rewritten in wxPython, which wraps native Win32 controls with built-in MSAA/UIA support. |
| 2 | Each label is a static text created immediately before its control, which is how Windows names edit fields, lists, combo boxes and spin boxes. Verified with an MSAA inspection (see 3.6). |
| 3 | The log is a read-only multi-line edit field in the Tab order (Alt+L); new lines don't move the reader's cursor. |
| 4 | Open Output Folder is a real button (Alt+D) and a menu command (Ctrl+Shift+F). |
| 5 | Help text is the control's accessible description and its tooltip. |
| 6 | A standard menu bar exposes every command with shortcuts shown. |
| 7 | Unique Alt+letter keys for every control, handled window-wide; Esc stops a conversion only while one is running and otherwise does nothing. |
| 8 | Status changes are spoken through the screen reader and shown in the status bar. |
| 9 | Focus is moved before a focused control is disabled. |
| 10 | Native `wx.PasswordEntryDialog`, `wx.TextEntryDialog`, `wx.MessageBox` and task dialogs. |
| 11 | System colours; native Windows dark mode; High Contrast respected. |
| 12 | Plain-text labels. |
| 13 | A list box with every file, Delete to remove, Add/Remove/Empty buttons. |
| 14 | MathJax integration, detection of math inside sentences, accessible HTML output, and accessible math defaults for pandoc. |
| 15 | Auto OCR by default; the app finds Tesseract wherever it is installed, explains scanned files and offers to install it; a Tesseract window checks for updates, installs, and adds languages. |
| 16 | Table metadata became real fields that survive every transform; table borders are erased before OCR and wide word gaps kept, so scanned tables are read completely and rebuilt; multi-block tables consume their blocks; orphan merging never touches tables, headings, math, code or lists; ruled tables are read with PyMuPDF's table finder; HTML header cells get `scope="col"`. |

---

## Part 3: For AI models and developers

This part is written so that an AI coding assistant or a new developer can change the program without breaking accessibility. Treat the rules in 3.3 as requirements.

### 3.1 Summary (machine-readable)

```yaml
product: Document Conversion Suite
engine: pdfmd (Python package "pdfmd")
version: 1.8.0
platform: Windows 10/11 (wxPython GUI); engine and CLI are cross-platform
gui_toolkit: wxPython 4.x (native Win32 controls; MSAA/UIA provided by Windows)
screen_reader_speech: accessible_output2 (NVDA, JAWS, System Access, Dolphin, ZoomText, PC-Talker, ZDSR); SAPI fallback deliberately disabled
accessible_math: MathJax 4.1.3 (speech, Braille, explorer) via jsDelivr CDN
math_detection: LaTeX delimiters ($, $$, \(, \[) plus Unicode math inside prose
pandoc: external program, found via PDFMD_PANDOC, ./pandoc/pandoc.exe next to the app, PATH, or default install folders
installer: Inno Setup 6, WizardStyle=modern, per-user by default
bundled: pandoc 3.13 (./pandoc), Tesseract 5.4.0.20240606 + tessdata_fast 4.1.0 for 17 languages and osd (./Tesseract-OCR), llama.cpp b12441 Vulkan llama-server + Huihui-Qwen3-VL-2B-Instruct-abliterated Q4_K_M with mmproj Q8_0 (./vision); fetched and checksum-verified by packaging/fetch_vendor.py
vision_model: llama-server on 127.0.0.1 (random port, random API key), started per batch and stopped afterwards; device auto|cuda|gpu (Vulkan)|cpu|dev:<name>; engines Vulkan (bundled) and CUDA 12.4/13.5 (downloaded, chosen from nvidia-smi driver and compute capability); catalog vision-models.json (online copy on GitHub main) with SHA-256 for every file
tool_priority: env var (PDFMD_PANDOC / PDFMD_TESSERACT) > user/system install > bundled copy
config_file: "%USERPROFILE%\\.pdfmd_gui.json"
files:
  pdfmd/app_gui.py: main window (PdfMdFrame), menus, worker thread, MathJax prompt, pandoc auto-export
  pdfmd/gui_a11y.py: Announcer, DescribedAccessible, describe(), MnemonicHandler
  pdfmd/gui_pandoc.py: PandocDialog (three-page notebook)
  pdfmd/mathjax.py: math detection, Unicode-to-LaTeX, MathJax header, accessible HTML writer
  pdfmd/pandoc_support.py: find pandoc, list formats, build arguments, convert
  pdfmd/tesseract_support.py: find/configure Tesseract, version, languages, update check, install, language downloads
  pdfmd/gui_tesseract.py: TesseractDialog (status, check, install/update, languages)
  pdfmd/extract.py: native/OCR extraction; _with_ruled_tables() reads ruled tables with PyMuPDF
  pdfmd/models.py: Block has real table fields (is_table, table_grid, table_type, table_score)
  pdfmd/cli.py: command line (--mathjax, --html, --to, --pandoc-args, --describe-images, --vision-device, --vision-model, --vision-status, --vision-update, --describe-photos)
  pdfmd/vision.py: find engine/models, devices, catalog and updates, VisionEngine (llama-server), prompts, text detection
  pdfmd/figures.py: find pictures, drawn charts and scanned photo regions in PDFs; describe stage; figure Markdown
  pdfmd/docimages.py: describe pictures in any pandoc document (JSON AST); alt text or block quotes per output format
  pdfmd/album.py: describe a folder of photos into an HTML or Markdown album
  pdfmd/gui_vision.py: VisionDialog (Ctrl+I) and PhotoAlbumDialog (Ctrl+D)
  packaging/pdfmd.spec: PyInstaller (DocConversionSuite.exe + pdfmd-cli.exe)
  packaging/installer.iss: Inno Setup installer
  packaging/build.py: full release build
```

### 3.2 Architecture of the accessible GUI

* **Native controls only.** Lists (`wx.ListBox`), edit fields (`wx.TextCtrl`), `wx.Choice`, `wx.ComboBox`, `wx.CheckBox`, `wx.SpinCtrl` (integer, native), `wx.Button`, `wx.Gauge`, `wx.Notebook`, `wx.StatusBar`. `wx.SpinCtrlDouble` is avoided because it is a generic composite whose edit field loses its label; the heading ratio is an integer percent instead.
* **Rich edit is avoided** for the log: a `TE_RICH2` control lost its accessible name in testing. Plain multi-line read-only edits keep it.
* **Labels.** A `wx.StaticText` created immediately before its control, as a sibling with the same parent. Windows derives the accessible name of edits, lists, combo boxes, spin boxes and progress bars from the preceding static text.
* **Descriptions.** `gui_a11y.describe(ctrl, text)` sets the tooltip, the help text and a `DescribedAccessible` (a `wx.Accessible` subclass that implements only `GetDescription` and `GetHelpText`; everything else falls through to the standard Windows implementation).
* **Access keys.** Group boxes (`wx.StaticBox` parents) make Windows resolve Alt+letter only within the focused group. `gui_a11y.MnemonicHandler` binds `EVT_CHAR_HOOK` on the top-level window and resolves keys across the whole window: label → focus the next focusable control; button → press; check box → toggle and focus. Unused keys are skipped so the menu bar still works.
* **Announcements.** `gui_a11y.Announcer.speak(text, interrupt)`; the main window calls it through `_set_status`. Progress is announced at 25/50/75 percent only.
* **Threading.** Conversion runs on a worker thread. All GUI updates go through `wx.CallAfter`. The MathJax question is asked on the GUI thread and the worker waits for the answer (`_call_on_gui`).
* **Focus management.** `_update_buttons()` moves focus before disabling the focused control.

### 3.3 Rules any change must follow

1. Use native wx controls. Don't draw custom controls or use generic composites where a native control exists.
2. Every interactive control gets a visible `wx.StaticText` label created **immediately before** it with the same parent, or carries its own label (buttons, check boxes).
3. Every control gets a description with `describe()`.
4. Every labelled control gets an Alt+letter key that is **unique among the controls visible at the same time**. Don't use F, P, V or H in the main window (menu bar keys). Update the access key tables in this file and in `SHORTCUTS_TEXT` in `app_gui.py`.
5. Every command is in the menu bar with its shortcut after a tab character in the label (`"&Convert\tF5"`).
6. Creation order is Tab order: create controls in logical reading order.
7. Before disabling or hiding a control, move focus away from it if it has focus.
8. Never block the GUI thread with conversion work; never touch wx objects from a worker thread except through `wx.CallAfter`.
9. Announce the start, end, failure and cancellation of any long operation with `Announcer.speak`; keep progress announcements sparse.
10. Report errors in a message dialog as well as in the log.
11. Don't hard-code colours; respect system colours and High Contrast.
12. Don't put decorative symbols in labels.
13. Accessible output defaults: keep the MathJax offer defaulting to Yes; keep `lang` on HTML; keep header rows in tables; keep descriptive image alternative text; keep pandoc's automatic math choice (MathJax for HTML, MathML for EPUB, native equations for Office formats).
14. Don't speak through SAPI when no screen reader is running.
15. Keep tables intact: store table data in the `Block` fields, never as ad-hoc attributes (they are lost by `dataclasses.replace`); never merge text into a table row; keep header rows; pass Markdown tables to pandoc unchanged.
16. Keep OCR on Auto by default and never let a scanned PDF fail silently: explain it and offer Tesseract.

### 3.4 How to add a new option (example)

```python
# In PdfMdFrame._build_ui, inside the right group box (parent = obox):
lbl = wx.StaticText(obox, label="&Example option:")   # pick an unused letter
self.example_choice = wx.Choice(obox, choices=["One", "Two"])
self._describe(self.example_choice, "What this option does, in one or two sentences.")
sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
sizer.Add(self.example_choice, 0)
# Then: save/load it in _options_from_controls / _apply_options_dict,
# add the key to the tables in ACCESSIBILITY.md and SHORTCUTS_TEXT,
# and run the tests in 3.6.
```

### 3.5 Math pipeline

1. The engine (`equations.py`) wraps standalone equation lines in `$$ ... $$`.
2. `mathjax.count_math()` counts delimited math plus Unicode math inside sentences (`count_unicode_math`).
3. If math is found, the GUI asks (default Yes), or follows the Always/Never setting. The CLI uses `--mathjax ask|yes|no` (ask defaults to yes; without a terminal it acts as yes).
4. `mathjax.apply_mathjax()` runs `wrap_unicode_math()` (Unicode math → `$...$` LaTeX; stray `$` escaped as `\$`), prepends the MathJax loader to the Markdown, and writes the HTML copy with `markdown_to_accessible_html()`.
5. The HTML uses only `\(...\)` and `\[...\]` delimiters, so dollar signs in prose are never treated as math.
6. `pandoc_support.convert()` strips the MathJax loader and wraps Unicode math before calling pandoc, so pandoc writes real equations.

### 3.6 How accessibility was verified

* **MSAA inspection.** A script calls `AccessibleObjectFromWindow` on every child window of the running program and reads `accName`, `accRole`, `accKeyboardShortcut`, `accState` and `accDescription`. Result: every input control reports its label as name, its Alt key as keyboard shortcut and its help as description; disabled buttons report the unavailable state.
* **Keyboard simulation.** `wx.UIActionSimulator` presses Alt+letter keys, Tab, F5 and Ctrl+Tab, and the test checks which control has focus. Result: main window 21 of 21 checks passed (every access key across group boxes, complete Tab order, F5 conversion, MathJax offer, focus kept after conversion). Pandoc window 21 of 21 checks passed (access keys on all three pages, Ctrl+Tab page switching, F5 conversion of a PDF to Word with extra arguments, Unicode math passed to pandoc as TeX). Tesseract window 7 of 7 checks passed (status text without Tesseract, live update check, install button state, access keys). Regression runs after the table and OCR changes passed again.
* **Real conversions with the bundled tools (14 of 14 passed).** An image-only scanned PDF was converted with Auto OCR: all text was recovered and both tables (one ruled) were rebuilt as tables. With the bundled pandoc: Word got 2 real tables and 4 native equations with no MathJax code leaking in; ODT got 2 tables; EPUB got MathML math and both tables; HTML got header cells, `lang` and MathJax math; GitHub Markdown kept pipe tables; and a Word file converted back to Markdown kept its tables.
* **MathJax output.** A converted test document was opened in a browser. The accessibility tree exposed each expression as named math, for example "E equals m c squared", "x sub i is greater than or equal to 0", "alpha plus beta cubed equals gamma"; Nemeth Braille strings were generated; each expression was keyboard focusable.

When you change the GUI, repeat these checks: Tab through every control with a screen reader running, try every Alt key in the tables above, convert a file with math, and confirm announcements.
