"""
Document Conversion Suite: accessible wxPython GUI for the pdfmd engine.

This GUI is a front end for the offline pdfmd engine, designed to be fully
usable with a screen reader (NVDA, JAWS, Narrator and others) and with the
keyboard alone:

- Uses native Windows controls, so every control has a role, a name and a
  state that screen readers can read.
- Every control has a visible label that is also its accessible name, plus
  an accessible description (spoken by screen readers) with help text.
- Every control is in the tab order and has an Alt+letter access key.
- A standard menu bar exposes every command, with shortcuts shown next to
  each menu item.
- Status changes (start, progress, completion, errors) are announced through
  the running screen reader.
- When a converted document contains math, pdfmd offers to enable MathJax
  so the math can be spoken, read in Braille and explored with the keyboard.
- Photos, charts, graphs, maps and diagrams are described by a small local
  AI vision model (alternative text, or a block-quoted description), and a
  whole folder of photos can be described into an accessible album.

Run as:
    python -m pdfmd.app_gui
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# DPI awareness: crisp text at Windows display scaling above 100%.
# Must run before wx creates any window.
# ---------------------------------------------------------------------------
if platform.system() == "Windows":
    try:
        import ctypes

        try:  # Per-monitor v2 (Windows 10 1703+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import wx  # noqa: E402

# Optional PyMuPDF import for password probing (GUI pre-checks)
try:
    try:  # PyMuPDF >= 1.24.3 prefers this name (no deprecation warning)
        import pymupdf as fitz  # type: ignore
    except ImportError:
        import fitz  # type: ignore
except Exception:  # pragma: no cover - optional
    fitz = None  # type: ignore

# --- Robust imports: package or script mode ---------------------------------
try:
    from pdfmd import __version__
    from pdfmd.models import Options
    from pdfmd.pipeline import pdf_to_markdown
    from pdfmd.utils import os_display_path
    from pdfmd.mathjax import apply_mathjax, count_math
    from pdfmd import pandoc_support as ps
    from pdfmd.gui_a11y import Announcer, MnemonicHandler, describe
    from pdfmd.gui_pandoc import PandocDialog
    from pdfmd import tesseract_support as ts
    from pdfmd.gui_tesseract import TesseractDialog
    from pdfmd import vision
    from pdfmd.gui_vision import PhotoAlbumDialog, VisionDialog
except ImportError:  # `python app_gui.py` from inside the package folder
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pdfmd import __version__
    from pdfmd.models import Options
    from pdfmd.pipeline import pdf_to_markdown
    from pdfmd.utils import os_display_path
    from pdfmd.mathjax import apply_mathjax, count_math
    from pdfmd import pandoc_support as ps
    from pdfmd.gui_a11y import Announcer, MnemonicHandler, describe
    from pdfmd.gui_pandoc import PandocDialog
    from pdfmd import tesseract_support as ts
    from pdfmd.gui_tesseract import TesseractDialog
    from pdfmd import vision
    from pdfmd.gui_vision import PhotoAlbumDialog, VisionDialog
# ---------------------------------------------------------------------------

APP_NAME = "Document Conversion Suite"
APP_TITLE = "Document Conversion Suite"
CONFIG_PATH = Path.home() / ".pdfmd_gui.json"

OCR_MODES: List[Tuple[str, str]] = [
    ("off", "Off: native text only (fastest)"),
    ("auto", "Auto: OCR only scanned pages"),
    ("tesseract", "Tesseract: OCR every page"),
    ("ocrmypdf", "OCRmyPDF: high-fidelity OCR"),
]
OCR_CODES = [code for code, _ in OCR_MODES]

# Common Tesseract language codes (the user can also type a custom code).
OCR_LANGS: List[Tuple[str, str]] = [
    ("eng", "English"),
    ("deu", "German"),
    ("fra", "French"),
    ("spa", "Spanish"),
    ("ita", "Italian"),
    ("por", "Portuguese"),
    ("nld", "Dutch"),
    ("pol", "Polish"),
    ("rus", "Russian"),
    ("chi_sim", "Chinese, Simplified"),
    ("chi_tra", "Chinese, Traditional"),
    ("jpn", "Japanese"),
    ("kor", "Korean"),
    ("ara", "Arabic"),
    ("hin", "Hindi"),
    ("tur", "Turkish"),
    ("vie", "Vietnamese"),
]

MATH_MODES: List[Tuple[str, str]] = [
    ("ask", "Ask me (MathJax recommended)"),
    ("always", "Always enable MathJax"),
    ("never", "Never enable MathJax"),
]
MATH_CODES = [code for code, _ in MATH_MODES]

THEMES = ("System", "Light", "Dark")

DEFAULT_OPTIONS: Dict[str, object] = {
    "ocr_mode": "auto",
    "ocr_lang": "eng",
    "preview": False,
    "export_images": False,
    "page_breaks": False,
    "rm_edges": True,
    "caps_to_headings": True,
    "defrag": True,
    "heading_ratio": 1.15,
    "orphan_len": 45,
    "math_mode": "ask",
    "html_copy": False,
    "describe_images": True,
}

BUILTIN_PROFILES: Dict[str, Dict[str, object]] = {
    "Default": DEFAULT_OPTIONS,
    "Academic article": {
        "ocr_mode": "auto",
        "preview": False,
        "export_images": False,
        "page_breaks": False,
        "rm_edges": True,
        "caps_to_headings": True,
        "defrag": True,
        "heading_ratio": 1.10,
        "orphan_len": 60,
    },
    "Math and science (MathJax)": {
        "ocr_mode": "auto",
        "preview": False,
        "export_images": False,
        "page_breaks": False,
        "rm_edges": True,
        "caps_to_headings": True,
        "defrag": True,
        "heading_ratio": 1.10,
        "orphan_len": 60,
        "math_mode": "always",
        "html_copy": True,
    },
    "Slides / handouts": {
        "ocr_mode": "auto",
        "preview": False,
        "export_images": True,
        "page_breaks": True,
        "rm_edges": False,
        "caps_to_headings": False,
        "defrag": True,
        "heading_ratio": 1.20,
        "orphan_len": 45,
    },
    "Scan-heavy / OCR-first": {
        "ocr_mode": "tesseract",
        "preview": False,
        "export_images": False,
        "page_breaks": False,
        "rm_edges": True,
        "caps_to_headings": False,
        "defrag": True,
        "heading_ratio": 1.15,
        "orphan_len": 45,
    },
}

SHORTCUTS_TEXT = """Document Conversion Suite keyboard shortcuts

Commands
  Ctrl+O              Add PDF files
  Ctrl+Shift+O        Choose output file or folder
  F5 or Ctrl+Enter    Start conversion
  Shift+F5            Stop conversion
  Esc                 Stop conversion (while converting)
  Ctrl+Shift+F        Open the output folder
  Ctrl+Shift+M        Open the converted Markdown file
  Ctrl+Shift+H        Open the accessible HTML file
  Ctrl+Shift+S        Speak the current status
  Ctrl+P              Convert with Pandoc (Word, EPUB, HTML, LaTeX and more)
  Ctrl+T              Tesseract OCR: install, update, add languages
  Ctrl+I              Vision model: processor (GPU or CPU), model, updates
  Ctrl+D              Describe a folder of photos (web page or Markdown)
  Ctrl+S              Save current settings as a profile
  Delete              Remove selected files (in the input list)
  F1                  This help
  Alt+F4              Exit

Go to a control (hold Alt)
  Alt+I   Input PDF files list
  Alt+A   Add PDFs button
  Alt+R   Remove Selected button
  Alt+Y   Empty List button
  Alt+O   Output file or folder
  Alt+B   Browse Output button
  Alt+E   Profile
  Alt+M   OCR mode
  Alt+G   OCR language
  Alt+X   Export images
  Alt+K   Insert page breaks
  Alt+3   Preview first 3 pages only
  Alt+T   Remove repeating header and footer text
  Alt+U   Promote uppercase lines to headings
  Alt+J   Join short orphan lines into paragraphs
  Alt+Z   Heading size ratio
  Alt+W   Orphan line width
  Alt+Q   When equations are found (MathJax)
  Alt+N   Also save an accessible HTML copy
  Alt+4   Describe pictures with the local AI vision model
  Alt+C   Convert button
  Alt+S   Stop button
  Alt+D   Open Output Folder button
  Alt+L   Conversion log

Menus
  Alt+F   File menu
  Alt+P   Profiles menu
  Alt+V   View menu
  Alt+H   Help menu

Convert with Pandoc window (Ctrl+P)
  Ctrl+Tab            Next page of settings
  Ctrl+Shift+Tab      Previous page of settings
  F5 or Alt+V         Convert (with an empty list, goes to page 4)
  Alt+P               Stop a running batch after the current file
  Esc                 Close
  Pages are in the order you use them: settings first, files last.
  Page 1, Format and output: Alt+F input format, Alt+O output format,
    Alt+D output folder, Alt+B browse, Alt+X also export PDF
    conversions, Alt+C describe pictures
  Page 2, Document options: Alt+S standalone, Alt+C table of contents,
    Alt+N number sections, Alt+E embed resources, Alt+D contents depth,
    Alt+M math rendering, Alt+H highlighting, Alt+W wrapping, Alt+T title,
    Alt+L language, Alt+G shift heading levels
  Page 3, Citations, templates and filters: Alt+C citations,
    Alt+B bibliography, Alt+I choose bibliography, Alt+S citation style,
    Alt+F choose style, Alt+R reference document, Alt+U choose document,
    Alt+T template, Alt+M choose template, Alt+L filters, Alt+E choose
    filter, Alt+N PDF engine, Alt+X extra pandoc arguments
  Page 4, Files and folders: Alt+I list of files and folders, Alt+A add
    files, Alt+F add folder, Alt+R remove selected (or Delete), Alt+E
    clear list, Alt+S include subfolders, Alt+T file types to take from
    folders, Alt+G pandoc log. Files and folders can also be dropped on
    the list.
  Alt+P               Install Pandoc (shown when pandoc is missing)

Tesseract OCR window (Ctrl+T)
  Alt+S status, Alt+U check for updates, Alt+I install or update,
  Alt+L installed languages, Alt+A add language, Alt+Q quality,
  Alt+D download language, Alt+C or Esc close

Vision Model window (Ctrl+I)
  Alt+S status, Alt+D describe pictures in documents, Alt+P processor
  (automatic, NVIDIA GPU with CUDA, any GPU with Vulkan, one particular
  graphics processor, or CPU only), Alt+M model, Alt+I model information, Alt+U check for
  updates, Alt+V update (or download) vision model, Alt+T test on a
  picture, Alt+R remove downloaded model, Alt+W stop download, Alt+L log,
  Alt+C or Esc close

Describe a Folder of Photos window (Ctrl+D)
  Alt+F photo folder, Alt+B browse, Alt+A save as (web page or
  Markdown), Alt+O output file, Alt+H choose file, Alt+U include
  subfolders, Alt+W open when finished, Alt+D or F5 describe photos,
  Alt+S stop, Alt+P open page, Alt+L log, Alt+C or Esc close

Picture descriptions
  Photos, charts, graphs, maps and diagrams are described by a small AI
  model that runs on your computer. With Export images on, the description
  becomes the picture's alternative text; otherwise it is written in the
  text as a block quote starting "Image description". Pictures that are
  mostly text get their recognised text instead.

Accessible math
  When a converted document contains math, the suite offers to enable
  MathJax (the answer defaults to Yes). MathJax adds a loader to the
  Markdown file and saves an accessible HTML copy, where screen readers
  speak each expression, it can be read in Braille, and you can explore
  it piece by piece with the arrow keys.
"""


class UserCancelled(Exception):
    """Signal that the user requested cancellation."""


# ---------------------------------------------------------------------------
# Accessibility helpers
# ---------------------------------------------------------------------------


class PdfDropTarget(wx.FileDropTarget):
    def __init__(self, frame: "PdfMdFrame") -> None:
        super().__init__()
        self.frame = frame

    def OnDropFiles(self, x, y, filenames):  # noqa: N802
        self.frame.add_inputs(filenames)
        return True


class ShortcutsDialog(wx.Dialog):
    """Keyboard shortcut reference in a read-only, focusable text field."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title="Keyboard Shortcuts", size=(620, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="&Keyboard shortcuts:")
        self.text = wx.TextCtrl(
            panel, value=SHORTCUTS_TEXT.replace("\n", "\r\n"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        self.text.SetFont(wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE)))
        close = wx.Button(panel, wx.ID_CLOSE, "&Close")
        sizer.Add(lbl, 0, wx.ALL, 8)
        sizer.Add(self.text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(close, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        panel.SetSizer(sizer)
        close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        self.SetEscapeId(wx.ID_CLOSE)
        self.SetAffirmativeId(wx.ID_CLOSE)
        close.SetDefault()
        self.text.SetInsertionPoint(0)
        self.text.SetFocus()
        self.CentreOnParent()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class PdfMdFrame(wx.Frame):
    def __init__(self, config: dict, initial_files: Optional[List[str]] = None) -> None:
        super().__init__(None, title=APP_TITLE, size=(980, 820))
        self.SetMinSize((760, 640))

        self.announcer = Announcer()
        self._accessibles: List[wx.Accessible] = []
        self._worker: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._input_paths: List[str] = []
        self._output_is_auto = True
        self._last_output_path: Optional[str] = None
        self._last_html_path: Optional[str] = None
        self._last_announced_pct = 0
        self._status_text = ""
        self.custom_profiles: Dict[str, dict] = {}
        self.current_profile = "Default"
        self.theme = "System"
        self._profile_menu_ids: Dict[int, str] = {}
        self.pandoc_opts = ps.PandocOptions()
        self.pandoc_auto = False
        self.pandoc_out_dir = ""
        self._last_pandoc_path: Optional[str] = None
        self.pandoc_describe = True
        self.pandoc_subfolders = False
        self.pandoc_folder_types = ""
        self.vision_settings = vision.VisionSettings()
        self.album_folder = ""
        self.album_format = "html"

        self._build_menu()
        self._build_ui()
        self.CreateStatusBar(1)

        self._load_config(config)
        if initial_files:
            self._input_paths = []
            self._output_is_auto = True
            self.out_text.ChangeValue("")
            self.add_inputs(initial_files, announce=False)

        self._refresh_profiles()
        self._update_buttons()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        # Bound after the frame's own key handler so it runs first; keys it
        # doesn't use are passed on.
        MnemonicHandler(self)

        self._set_status("Ready. Press Ctrl+O to add PDF files, then F5 to convert. Press F1 for keyboard help.",
                         announce=False)
        self._log(f"Document Conversion Suite {__version__}. "
                  f"Screen reader announcements: {self.announcer.describe()}.")
        pandoc = ps.find_pandoc()
        self._log("Pandoc: " + (f"{ps.pandoc_version(pandoc) or ''} {'(built in)' if ps.is_bundled(pandoc) else 'at ' + pandoc}"
                                if pandoc else "not installed (Ctrl+P to install)") + ".")
        tess = ts.configure()
        self._log("Tesseract OCR: " + (f"{ts.installed_version(tess) or 'installed'} "
                                       f"{'(built in)' if ts.is_bundled(tess) else 'at ' + tess}" if tess
                  else "not installed. Scanned PDFs need it; press Ctrl+T to install it") + ".")
        self._log_vision_status()
        wx.CallAfter(self.input_list.SetFocus)

    # ------------------------------------------------------------------ helpers
    def _describe(self, ctrl: wx.Window, text: str) -> None:
        """Tooltip for mouse users + accessible description for screen readers."""
        describe(ctrl, text)

    # --------------------------------------------------------------------- menu
    def _build_menu(self) -> None:
        mb = wx.MenuBar()

        # File
        m_file = wx.Menu()
        self.mi_add = m_file.Append(wx.ID_ANY, "&Add PDF Files...\tCtrl+O",
                                    "Choose one or more PDF files to convert")
        self.mi_output = m_file.Append(wx.ID_ANY, "Choose &Output File or Folder...\tCtrl+Shift+O",
                                       "Choose where the Markdown output is saved")
        m_file.AppendSeparator()
        self.mi_convert = m_file.Append(wx.ID_ANY, "&Convert\tF5", "Start converting the input files")
        self.mi_stop = m_file.Append(wx.ID_ANY, "&Stop Conversion\tShift+F5", "Stop the running conversion")
        self.mi_pandoc = m_file.Append(wx.ID_ANY, "Convert Any Document with &Pandoc...\tCtrl+P",
                                       "Convert to Word, EPUB, HTML, LaTeX and every other "
                                       "format pandoc supports")
        self.mi_tesseract = m_file.Append(wx.ID_ANY, "&Tesseract OCR (Install, Update, Languages)...\tCtrl+T",
                                          "Install or update Tesseract OCR and add OCR languages")
        self.mi_vision = m_file.Append(wx.ID_ANY, "&Vision Model (Picture Descriptions)...\tCtrl+I",
                                       "Choose GPU or CPU and the model that describes pictures, "
                                       "and update it")
        self.mi_album = m_file.Append(wx.ID_ANY, "&Describe a Folder of Photos...\tCtrl+D",
                                      "Describe every photo in a folder into a web page or "
                                      "Markdown file")
        m_file.AppendSeparator()
        self.mi_open_folder = m_file.Append(wx.ID_ANY, "Open Output &Folder\tCtrl+Shift+F",
                                            "Open the folder that contains the output")
        self.mi_open_md = m_file.Append(wx.ID_ANY, "Open Converted &Markdown File\tCtrl+Shift+M",
                                        "Open the last converted Markdown file")
        self.mi_open_html = m_file.Append(wx.ID_ANY, "Open Accessible &HTML File\tCtrl+Shift+H",
                                          "Open the last accessible HTML file in your browser")
        m_file.AppendSeparator()
        m_file.Append(wx.ID_EXIT, "E&xit\tAlt+F4", "Close Document Conversion Suite")
        mb.Append(m_file, "&File")

        # Profiles
        m_prof = wx.Menu()
        self.profile_submenu = wx.Menu()
        m_prof.AppendSubMenu(self.profile_submenu, "&Apply Profile",
                             "Apply a saved set of conversion options")
        m_prof.AppendSeparator()
        self.mi_save_profile = m_prof.Append(wx.ID_ANY, "&Save Current Settings as Profile...\tCtrl+S",
                                             "Save the current options as a named profile")
        self.mi_delete_profile = m_prof.Append(wx.ID_ANY, "&Delete Current Profile...",
                                               "Delete the selected custom profile")
        self.mi_reset = m_prof.Append(wx.ID_ANY, "&Reset Options to Defaults",
                                      "Set every option back to its default value")
        mb.Append(m_prof, "&Profiles")

        # View
        m_view = wx.Menu()
        m_theme = wx.Menu()
        self.mi_theme = {
            "System": m_theme.AppendRadioItem(wx.ID_ANY, "Follow &Windows Setting",
                                              "Use the Windows light or dark app mode"),
            "Light": m_theme.AppendRadioItem(wx.ID_ANY, "&Light", "Always use the light theme"),
            "Dark": m_theme.AppendRadioItem(wx.ID_ANY, "&Dark", "Always use the dark theme"),
        }
        m_view.AppendSubMenu(m_theme, "&Theme", "Choose light, dark or the Windows setting")
        self.mi_announce = m_view.AppendCheckItem(
            wx.ID_ANY, "&Announce Status with Screen Reader",
            "Speak conversion progress and results with your screen reader")
        self.mi_announce.Check(True)
        self.mi_speak_status = m_view.Append(wx.ID_ANY, "Speak Current &Status\tCtrl+Shift+S",
                                             "Have your screen reader speak the current status")
        mb.Append(m_view, "&View")

        # Help
        m_help = wx.Menu()
        self.mi_shortcuts = m_help.Append(wx.ID_HELP, "&Keyboard Shortcuts\tF1",
                                          "List every keyboard shortcut")
        self.mi_tess_update = m_help.Append(wx.ID_ANY, "Check for &Tesseract Updates...",
                                            "Check online for a newer Tesseract OCR and install it")
        self.mi_vision_update = m_help.Append(wx.ID_ANY, "Check for &Vision Model Updates...",
                                              "Check online for a newer vision engine or model "
                                              "and install it")
        self.mi_about = m_help.Append(wx.ID_ABOUT, "&About Document Conversion Suite", "Version and license information")
        mb.Append(m_help, "&Help")

        self.SetMenuBar(mb)

        b = self.Bind
        b(wx.EVT_MENU, lambda e: self._choose_inputs(), self.mi_add)
        b(wx.EVT_MENU, lambda e: self._choose_output(), self.mi_output)
        b(wx.EVT_MENU, lambda e: self._on_convert(), self.mi_convert)
        b(wx.EVT_MENU, lambda e: self._on_cancel(), self.mi_stop)
        b(wx.EVT_MENU, lambda e: self._open_output_folder(), self.mi_open_folder)
        b(wx.EVT_MENU, lambda e: self._open_last_file("md"), self.mi_open_md)
        b(wx.EVT_MENU, lambda e: self._open_last_file("html"), self.mi_open_html)
        b(wx.EVT_MENU, lambda e: self._open_pandoc(), self.mi_pandoc)
        b(wx.EVT_MENU, lambda e: self._open_tesseract(), self.mi_tesseract)
        b(wx.EVT_MENU, lambda e: self._open_tesseract(check_now=True), self.mi_tess_update)
        b(wx.EVT_MENU, lambda e: self._open_vision(), self.mi_vision)
        b(wx.EVT_MENU, lambda e: self._open_vision(check_now=True), self.mi_vision_update)
        b(wx.EVT_MENU, lambda e: self._open_album(), self.mi_album)
        b(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        b(wx.EVT_MENU, lambda e: self._save_profile_dialog(), self.mi_save_profile)
        b(wx.EVT_MENU, lambda e: self._delete_profile(), self.mi_delete_profile)
        b(wx.EVT_MENU, lambda e: self._reset_options(), self.mi_reset)
        for name, item in self.mi_theme.items():
            b(wx.EVT_MENU, lambda e, n=name: self._on_theme(n), item)
        b(wx.EVT_MENU, self._on_toggle_announce, self.mi_announce)
        b(wx.EVT_MENU, lambda e: self.announcer.speak(self._status_text, interrupt=True)
          if self.announcer.enabled else None, self.mi_speak_status)
        b(wx.EVT_MENU, lambda e: self._show_shortcuts(), id=wx.ID_HELP)
        b(wx.EVT_MENU, lambda e: self._show_about(), id=wx.ID_ABOUT)

    # ----------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self.panel = panel
        main = wx.BoxSizer(wx.VERTICAL)
        pad = 6

        # ===================== Input and output ==============================
        files_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Input and output")
        fbox = files_sb.GetStaticBox()

        lbl = wx.StaticText(fbox, label="&Input PDF files:")
        self.input_list = wx.ListBox(fbox, style=wx.LB_EXTENDED | wx.LB_NEEDED_SB, size=(-1, 110))
        self._describe(self.input_list,
                       "PDF files to convert. Press Delete to remove the selected files. "
                       "Add files with Ctrl+O or by dragging them here. "
                       "All processing is local; nothing leaves your computer.")
        files_sb.Add(lbl, 0, wx.LEFT | wx.TOP, pad)
        files_sb.Add(self.input_list, 1, wx.EXPAND | wx.ALL, pad)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(fbox, label="&Add PDFs...")
        self._describe(self.add_btn, "Choose one or more PDF files to add to the list. Shortcut: Ctrl+O.")
        self.remove_btn = wx.Button(fbox, label="&Remove Selected")
        self._describe(self.remove_btn, "Remove the selected files from the list. Shortcut: Delete in the list.")
        self.clear_btn = wx.Button(fbox, label="Empt&y List")
        self._describe(self.clear_btn, "Remove all files from the list.")
        for btn in (self.add_btn, self.remove_btn, self.clear_btn):
            row.Add(btn, 0, wx.RIGHT, pad)
        files_sb.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)

        out_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(fbox, label="&Output file or folder:")
        self.out_text = wx.TextCtrl(fbox)
        self._describe(self.out_text,
                       "Where to save the Markdown. For one input this is a .md file; "
                       "for several inputs it is a folder. Filled in automatically.")
        self.browse_out_btn = wx.Button(fbox, label="&Browse Output...")
        self._describe(self.browse_out_btn, "Choose the output file or folder. Shortcut: Ctrl+Shift+O.")
        out_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        out_row.Add(self.out_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        out_row.Add(self.browse_out_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        files_sb.Add(out_row, 0, wx.EXPAND | wx.ALL, pad)
        main.Add(files_sb, 0, wx.EXPAND | wx.ALL, 8)

        # ===================== Conversion options ============================
        opts_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Conversion options")
        obox = opts_sb.GetStaticBox()
        grid = wx.FlexGridSizer(cols=4, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)
        grid.AddGrowableCol(3, 1)

        lbl_profile = wx.StaticText(obox, label="Profil&e:")
        self.profile_choice = wx.Choice(obox)
        self._describe(self.profile_choice,
                       "Apply a saved set of options. Built-in profiles include one for math "
                       "and science documents. Save your own with Ctrl+S.")
        grid.Add(lbl_profile, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.profile_choice, 1, wx.EXPAND)
        grid.Add((0, 0))
        grid.Add((0, 0))

        lbl_ocr = wx.StaticText(obox, label="OCR &mode:")
        self.ocr_choice = wx.Choice(obox, choices=[label for _, label in OCR_MODES])
        self._describe(self.ocr_choice,
                       "Off uses the text stored in the PDF and is fastest. Auto detects scanned "
                       "pages and runs OCR only where needed. Tesseract runs OCR on every page. "
                       "OCRmyPDF gives the highest-fidelity OCR. OCR needs Tesseract installed.")
        lbl_lang = wx.StaticText(obox, label="OCR lan&guage:")
        self.lang_combo = wx.ComboBox(obox, choices=[f"{c} ({n})" for c, n in OCR_LANGS],
                                      style=wx.CB_DROPDOWN)
        self._describe(self.lang_combo,
                       "Tesseract language code used for OCR. Choose from the list or type a code. "
                       "Combine languages with a plus sign, for example eng+fra. "
                       "Also sets the language of the accessible HTML copy.")
        grid.Add(lbl_ocr, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.ocr_choice, 1, wx.EXPAND)
        grid.Add(lbl_lang, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        grid.Add(self.lang_combo, 1, wx.EXPAND)
        opts_sb.Add(grid, 0, wx.EXPAND | wx.ALL, pad)

        checks = wx.GridSizer(cols=2, vgap=pad, hgap=24)
        self.export_images_cb = wx.CheckBox(obox, label="E&xport images")
        self._describe(self.export_images_cb,
                       "Save the images in the PDF to a folder next to the output and link them "
                       "from the Markdown with descriptive alternative text.")
        self.page_breaks_cb = wx.CheckBox(obox, label="Insert page brea&ks")
        self._describe(self.page_breaks_cb, "Insert a horizontal rule between pages.")
        self.preview_cb = wx.CheckBox(obox, label="Preview first &3 pages only")
        self._describe(self.preview_cb, "Convert only the first three pages, for a quick check.")
        self.rm_edges_cb = wx.CheckBox(obox, label="Remove repeating header and footer &text")
        self._describe(self.rm_edges_cb,
                       "Remove running headers, footers and page numbers that repeat on every page.")
        self.caps_cb = wx.CheckBox(obox, label="Promote &uppercase lines to headings")
        self._describe(self.caps_cb, "Treat short lines written in all capitals as headings.")
        self.defrag_cb = wx.CheckBox(obox, label="&Join short orphan lines into paragraphs")
        self._describe(self.defrag_cb,
                       "Merge short isolated lines into the previous paragraph so text reads "
                       "smoothly.")
        self.describe_cb = wx.CheckBox(obox, label="Describe pictures with the local AI vision model (&4)")
        self._describe(self.describe_cb,
                       "Photos, charts, graphs, maps and diagrams are described by a small AI model "
                       "running on this computer. With Export images on, the description becomes "
                       "each picture's alternative text; otherwise it is written as a block quote. "
                       "Choose GPU or CPU, and update the model, with Ctrl+I.")
        for cb in (self.export_images_cb, self.page_breaks_cb, self.preview_cb,
                   self.rm_edges_cb, self.caps_cb, self.defrag_cb, self.describe_cb):
            checks.Add(cb, 0)
        opts_sb.Add(checks, 0, wx.EXPAND | wx.ALL, pad)

        tune = wx.FlexGridSizer(cols=4, vgap=pad, hgap=pad)
        lbl = wx.StaticText(obox, label="Heading si&ze ratio (percent of body text):")
        self.heading_spin = wx.SpinCtrl(obox, min=100, max=250, initial=115,
                                        style=wx.SP_ARROW_KEYS)
        self.heading_spin.SetIncrement(5)
        self._describe(self.heading_spin,
                       "Text at least this many percent of the body text size becomes a heading. "
                       "Lower values create more headings. Default 115.")
        tune.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        tune.Add(self.heading_spin, 0)
        lbl = wx.StaticText(obox, label="Orphan line &width (characters):")
        self.orphan_spin = wx.SpinCtrl(obox, min=10, max=120, initial=45, style=wx.SP_ARROW_KEYS)
        self._describe(self.orphan_spin,
                       "Isolated lines up to this many characters are merged into the previous "
                       "paragraph. Default 45.")
        tune.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 12)
        tune.Add(self.orphan_spin, 0)
        opts_sb.Add(tune, 0, wx.ALL, pad)

        math_row = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        lbl = wx.StaticText(obox, label="When e&quations are found:")
        self.math_choice = wx.Choice(obox, choices=[label for _, label in MATH_MODES])
        self._describe(self.math_choice,
                       "What to do when a converted document contains math. MathJax makes math "
                       "accessible: screen readers speak it, it can be read in Braille, and you "
                       "can explore it with the arrow keys. Enabling it adds a MathJax loader to "
                       "the Markdown file and saves an accessible HTML copy. "
                       "Ask me is the default, and the question defaults to Yes.")
        math_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        math_row.Add(self.math_choice, 0)
        opts_sb.Add(math_row, 0, wx.ALL, pad)
        self.html_cb = wx.CheckBox(obox, label="Also save a&n accessible HTML copy of every document")
        self._describe(self.html_cb,
                       "Save an HTML version next to each Markdown file, with the document "
                       "language, real headings and table header cells. Documents with math "
                       "always get one when MathJax is enabled.")
        opts_sb.Add(self.html_cb, 0, wx.ALL, pad)
        main.Add(opts_sb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ===================== Progress ======================================
        prog_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Progress")
        pbox = prog_sb.GetStaticBox()
        act = wx.BoxSizer(wx.HORIZONTAL)
        self.convert_btn = wx.Button(pbox, label="&Convert")
        self._describe(self.convert_btn, "Start converting the files in the list. Shortcut: F5 or Ctrl+Enter.")
        self.stop_btn = wx.Button(pbox, label="&Stop")
        self._describe(self.stop_btn, "Stop the running conversion. Shortcut: Shift+F5 or Escape.")
        self.open_folder_btn = wx.Button(pbox, label="Open Output Fol&der")
        self._describe(self.open_folder_btn,
                       "Open the folder containing the converted files. Shortcut: Ctrl+Shift+F.")
        for btn in (self.convert_btn, self.stop_btn, self.open_folder_btn):
            act.Add(btn, 0, wx.RIGHT, pad)
        prog_sb.Add(act, 0, wx.ALL, pad)

        g_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(pbox, label="Progress:")
        self.gauge = wx.Gauge(pbox, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        g_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        g_row.Add(self.gauge, 1, wx.ALIGN_CENTER_VERTICAL)
        prog_sb.Add(g_row, 0, wx.EXPAND | wx.ALL, pad)

        lbl = wx.StaticText(pbox, label="Conversion &log:")
        self.log_text = wx.TextCtrl(pbox, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                    size=(-1, 140))
        self._describe(self.log_text,
                       "Messages from the conversion. Read it with the arrow keys.")
        prog_sb.Add(lbl, 0, wx.LEFT | wx.TOP, pad)
        prog_sb.Add(self.log_text, 1, wx.EXPAND | wx.ALL, pad)
        main.Add(prog_sb, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(main)
        self.convert_btn.SetDefault()

        # Events
        self.add_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_inputs())
        self.remove_btn.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected())
        self.clear_btn.Bind(wx.EVT_BUTTON, lambda e: self._clear_inputs())
        self.browse_out_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_output())
        self.convert_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_convert())
        self.stop_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_cancel())
        self.open_folder_btn.Bind(wx.EVT_BUTTON, lambda e: self._open_output_folder())
        self.profile_choice.Bind(wx.EVT_CHOICE, self._on_profile_choice)
        self.input_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.input_list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        self.out_text.Bind(wx.EVT_TEXT, self._on_output_edited)

        drop = PdfDropTarget(self)
        self.input_list.SetDropTarget(drop)
        self.panel.SetDropTarget(PdfDropTarget(self))

    # ------------------------------------------------------------------ config
    def _load_config(self, data: dict) -> None:
        theme = data.get("theme")
        if theme in THEMES:
            self.theme = theme
        self.mi_theme[self.theme].Check(True)

        announce = data.get("announce", True)
        self.announcer.enabled = bool(announce)
        self.mi_announce.Check(bool(announce))

        profiles = data.get("profiles")
        if isinstance(profiles, dict):
            self.custom_profiles = {
                name: opt for name, opt in profiles.items()
                if isinstance(opt, dict) and name not in BUILTIN_PROFILES
            }
        prof = data.get("profile")
        if isinstance(prof, str) and (prof in BUILTIN_PROFILES or prof in self.custom_profiles):
            self.current_profile = prof

        opts = data.get("options")
        self._apply_options_dict(opts if isinstance(opts, dict) else DEFAULT_OPTIONS)

        inputs = data.get("last_inputs")
        if not isinstance(inputs, list):
            last = data.get("last_input")
            inputs = [last] if isinstance(last, str) and last.lower().endswith(".pdf") else []
        inputs = [p for p in inputs if isinstance(p, str) and Path(p).is_file()]
        last_output = data.get("last_output")
        if inputs:
            self.add_inputs(inputs, announce=False)
        if isinstance(last_output, str) and last_output and inputs:
            self.out_text.ChangeValue(last_output)
            self._output_is_auto = bool(data.get("output_is_auto", True))
            self._last_output_path = last_output

        pandoc = data.get("pandoc")
        if isinstance(pandoc, dict):
            self.pandoc_opts = ps.PandocOptions.from_dict(pandoc.get("options", {}))
            self.pandoc_auto = bool(pandoc.get("auto_export", False))
            self.pandoc_out_dir = str(pandoc.get("out_dir", "") or "")
            self.pandoc_describe = bool(pandoc.get("describe_images", True))
            self.pandoc_subfolders = bool(pandoc.get("include_subfolders", False))
            self.pandoc_folder_types = str(pandoc.get("folder_types", "") or "")

        vis = data.get("vision")
        if isinstance(vis, dict):
            self.vision_settings = vision.VisionSettings.from_dict(vis)
        alb = data.get("album")
        if isinstance(alb, dict):
            self.album_folder = str(alb.get("folder", "") or "")
            self.album_format = "markdown" if alb.get("format") == "markdown" else "html"

        size = data.get("window_size")
        if isinstance(size, list) and len(size) == 2:
            try:
                self.SetSize((max(760, int(size[0])), max(640, int(size[1]))))
            except Exception:
                pass

    def _save_config(self) -> None:
        data = {
            "theme": self.theme,
            "announce": self.announcer.enabled,
            "last_inputs": list(self._input_paths),
            "last_output": self.out_text.GetValue().strip(),
            "output_is_auto": self._output_is_auto,
            "options": self._options_from_controls(),
            "profile": self.current_profile,
            "profiles": self.custom_profiles,
            "window_size": list(self.GetSize()) if not self.IsMaximized() else None,
            "pandoc": {
                "options": self.pandoc_opts.to_dict(),
                "auto_export": self.pandoc_auto,
                "out_dir": self.pandoc_out_dir,
                "describe_images": self.pandoc_describe,
                "include_subfolders": self.pandoc_subfolders,
                "folder_types": self.pandoc_folder_types,
            },
            "vision": self.vision_settings.to_dict(),
            "album": {"folder": self.album_folder, "format": self.album_format},
        }
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass  # persistence is best-effort

    # ------------------------------------------------------------------ status
    def _set_status(self, text: str, announce: bool = True, interrupt: bool = False) -> None:
        self._status_text = text
        self.SetStatusText(text)
        if announce:
            self.announcer.speak(text, interrupt=interrupt)

    def _log(self, msg: str) -> None:
        """Thread-safe log appender that never moves the reader's caret."""
        def append() -> None:
            if not self or not self.log_text:
                return
            focused = wx.Window.FindFocus() is self.log_text
            if focused:
                pos = self.log_text.GetInsertionPoint()
                self.log_text.AppendText(str(msg) + "\n")
                self.log_text.SetInsertionPoint(pos)
            else:
                self.log_text.AppendText(str(msg) + "\n")
        wx.CallAfter(append)

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _update_buttons(self) -> None:
        busy = self._busy()
        has_inputs = bool(self._input_paths)
        has_sel = bool(self.input_list.GetSelections())
        has_output = bool(self._last_output_path)

        targets = {
            self.convert_btn: not busy and has_inputs,
            self.stop_btn: busy,
            self.open_folder_btn: has_output,
            self.remove_btn: not busy and has_sel,
            self.clear_btn: not busy and has_inputs,
            self.add_btn: not busy,
            self.browse_out_btn: not busy,
        }
        # Move focus away from a control that is about to be disabled, so
        # keyboard and screen reader users never lose their place.
        focus = wx.Window.FindFocus()
        if focus in targets and not targets[focus]:
            for candidate in (self.stop_btn, self.open_folder_btn, self.convert_btn,
                              self.add_btn, self.input_list):
                if candidate is self.input_list or targets.get(candidate):
                    candidate.SetFocus()
                    break
        for ctrl, enable in targets.items():
            ctrl.Enable(enable)

        self.mi_convert.Enable(not busy)
        self.mi_stop.Enable(busy)
        self.mi_add.Enable(not busy)
        self.mi_output.Enable(not busy)
        self.mi_open_folder.Enable(has_output)
        self.mi_open_md.Enable(has_output and str(self._last_output_path).lower().endswith(".md"))
        self.mi_open_html.Enable(bool(self._last_html_path))

    # ------------------------------------------------------------ input files
    def add_inputs(self, paths, announce: bool = True) -> None:
        if self._busy():
            return
        added = 0
        skipped = 0
        for p in paths:
            p = os_display_path(str(p))
            if not p.lower().endswith(".pdf"):
                skipped += 1
                continue
            if p in self._input_paths:
                continue
            self._input_paths.append(p)
            added += 1
        self._refresh_input_list()
        self._suggest_output()
        self._update_buttons()
        if announce:
            msg = f"{added} file{'s' if added != 1 else ''} added. {len(self._input_paths)} in the list."
            if skipped:
                msg += f" {skipped} non-PDF file{'s' if skipped != 1 else ''} ignored."
            self._set_status(msg)

    def _refresh_input_list(self, select: Optional[int] = None) -> None:
        items = [f"{Path(p).name}  ({Path(p).parent})" for p in self._input_paths]
        self.input_list.Set(items)
        if items:
            idx = 0 if select is None else max(0, min(select, len(items) - 1))
            self.input_list.SetSelection(idx)

    def _choose_inputs(self) -> None:
        if self._busy():
            return
        start_dir = str(Path(self._input_paths[-1]).parent) if self._input_paths else ""
        with wx.FileDialog(self, "Add PDF files", defaultDir=start_dir,
                           wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            paths = dlg.GetPaths()
        self.add_inputs(paths)
        self.input_list.SetFocus()

    def _remove_selected(self) -> None:
        sels = sorted(self.input_list.GetSelections(), reverse=True)
        if not sels or self._busy():
            return
        for i in sels:
            del self._input_paths[i]
        self._refresh_input_list(select=min(sels))
        if self._output_is_auto:
            self.out_text.ChangeValue("")
        self._suggest_output()
        self._update_buttons()
        n = len(sels)
        self._set_status(f"{n} file{'s' if n != 1 else ''} removed. "
                         f"{len(self._input_paths)} in the list.", interrupt=True)
        if not self._input_paths:
            self.add_btn.SetFocus()

    def _clear_inputs(self) -> None:
        if self._busy():
            return
        self._input_paths = []
        self._refresh_input_list()
        if self._output_is_auto:
            self.out_text.ChangeValue("")
        self._update_buttons()
        self.add_btn.SetFocus()
        self._set_status("Input list emptied.", interrupt=True)

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self._remove_selected()
        else:
            event.Skip()

    # ------------------------------------------------------------------ output
    def _on_output_edited(self, event) -> None:
        self._output_is_auto = False
        event.Skip()

    def _suggest_output(self) -> None:
        if not self._input_paths:
            return
        if self.out_text.GetValue().strip() and not self._output_is_auto:
            return
        if len(self._input_paths) == 1:
            value = os_display_path(Path(self._input_paths[0]).with_suffix(".md"))
        else:
            value = os_display_path(Path(self._input_paths[0]).parent)
        self.out_text.ChangeValue(value)
        self._output_is_auto = True

    def _choose_output(self) -> None:
        if self._busy():
            return
        current = self.out_text.GetValue().strip()
        if len(self._input_paths) > 1:
            with wx.DirDialog(self, "Choose output folder", defaultPath=current,
                              style=wx.DD_DEFAULT_STYLE) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                path = dlg.GetPath()
        else:
            base = Path(current) if current else (
                Path(self._input_paths[0]).with_suffix(".md") if self._input_paths else Path("output.md"))
            with wx.FileDialog(self, "Save Markdown as", defaultDir=str(base.parent),
                               defaultFile=base.name,
                               wildcard="Markdown files (*.md)|*.md|All files (*.*)|*.*",
                               style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                path = dlg.GetPath()
        self.out_text.ChangeValue(os_display_path(path))
        self._output_is_auto = False
        self._set_status(f"Output set to {path}")
        self.out_text.SetFocus()

    # ---------------------------------------------------------------- profiles
    def _profile_names(self) -> List[str]:
        return list(BUILTIN_PROFILES.keys()) + sorted(self.custom_profiles.keys())

    def _refresh_profiles(self) -> None:
        names = self._profile_names()
        if self.current_profile not in names:
            self.current_profile = "Default"
        self.profile_choice.Set(names)
        self.profile_choice.SetStringSelection(self.current_profile)

        # Rebuild the Profiles > Apply Profile submenu.
        for item_id in list(self._profile_menu_ids):
            self.Unbind(wx.EVT_MENU, id=item_id)
        for item in list(self.profile_submenu.GetMenuItems()):
            self.profile_submenu.Delete(item)
        self._profile_menu_ids = {}
        for i, name in enumerate(names):
            safe = name.replace("&", "&&")
            label = f"&{i + 1} {safe}" if i < 9 else safe
            item = self.profile_submenu.AppendRadioItem(wx.ID_ANY, label)
            self._profile_menu_ids[item.GetId()] = name
            self.Bind(wx.EVT_MENU, self._on_profile_menu, id=item.GetId())
            if name == self.current_profile:
                item.Check(True)
        is_custom = self.current_profile in self.custom_profiles
        self.mi_delete_profile.Enable(is_custom)

    def _on_profile_menu(self, event) -> None:
        name = self._profile_menu_ids.get(event.GetId())
        if name:
            self._apply_profile(name)

    def _on_profile_choice(self, event) -> None:
        name = self.profile_choice.GetStringSelection()
        if name:
            self._apply_profile(name, announce=False)

    def _apply_profile(self, name: str, announce: bool = True) -> None:
        opts = BUILTIN_PROFILES.get(name) or self.custom_profiles.get(name)
        if opts is None:
            return
        self._apply_options_dict(opts)
        self.current_profile = name
        self._refresh_profiles()
        self._log(f"[profile] Applied profile: {name}")
        self._set_status(f"Profile {name} applied.", announce=announce)

    def _save_profile_dialog(self) -> None:
        with wx.TextEntryDialog(self, "Name for the new profile:", "Save Profile",
                                value="" if self.current_profile in BUILTIN_PROFILES
                                else self.current_profile) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            name = dlg.GetValue().strip()
        if not name:
            return
        if name in BUILTIN_PROFILES:
            wx.MessageBox(f'"{name}" is a built-in profile name. Please choose a different name.',
                          "Cannot Replace Built-in Profile", wx.OK | wx.ICON_INFORMATION, self)
            return
        if name in self.custom_profiles:
            if wx.MessageBox(f'A profile named "{name}" already exists. Replace it?',
                             "Replace Profile?", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                             self) != wx.YES:
                return
        self.custom_profiles[name] = self._options_from_controls()
        self.current_profile = name
        self._refresh_profiles()
        self._save_config()
        self._log(f"[profile] Saved profile: {name}")
        self._set_status(f"Profile {name} saved.")

    def _delete_profile(self) -> None:
        name = self.current_profile
        if name not in self.custom_profiles:
            wx.MessageBox("Built-in profiles cannot be deleted. Select a custom profile first.",
                          "Delete Profile", wx.OK | wx.ICON_INFORMATION, self)
            return
        if wx.MessageBox(f'Delete the profile "{name}"?', "Delete Profile?",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        del self.custom_profiles[name]
        self.current_profile = "Default"
        self._apply_options_dict(DEFAULT_OPTIONS)
        self._refresh_profiles()
        self._save_config()
        self._log(f"[profile] Deleted profile: {name}")
        self._set_status(f"Profile {name} deleted. Default options restored.")

    def _reset_options(self) -> None:
        self._apply_profile("Default", announce=False)
        self._set_status("Options reset to defaults.")

    # ------------------------------------------------------------ options I/O
    def _lang_code(self) -> str:
        raw = self.lang_combo.GetValue().strip()
        code = raw.split(" (")[0].strip() if raw else ""
        return code or "eng"

    def _options_from_controls(self) -> dict:
        return {
            "ocr_mode": OCR_CODES[max(0, self.ocr_choice.GetSelection())],
            "ocr_lang": self._lang_code(),
            "preview": self.preview_cb.GetValue(),
            "export_images": self.export_images_cb.GetValue(),
            "page_breaks": self.page_breaks_cb.GetValue(),
            "rm_edges": self.rm_edges_cb.GetValue(),
            "caps_to_headings": self.caps_cb.GetValue(),
            "defrag": self.defrag_cb.GetValue(),
            "heading_ratio": round(self.heading_spin.GetValue() / 100.0, 2),
            "orphan_len": int(self.orphan_spin.GetValue()),
            "math_mode": MATH_CODES[max(0, self.math_choice.GetSelection())],
            "html_copy": self.html_cb.GetValue(),
            "describe_images": self.describe_cb.GetValue(),
        }

    def _apply_options_dict(self, opts: dict) -> None:
        # Options a profile doesn't mention keep their current value for the
        # OCR language; everything else falls back to the defaults.
        current_lang = self._lang_code() if self.lang_combo.GetValue() else "eng"
        o = {**DEFAULT_OPTIONS, "ocr_lang": current_lang, **opts}

        mode = o.get("ocr_mode")
        self.ocr_choice.SetSelection(OCR_CODES.index(mode) if mode in OCR_CODES else 0)

        lang = str(o.get("ocr_lang") or "eng")
        names = dict(OCR_LANGS)
        self.lang_combo.SetValue(f"{lang} ({names[lang]})" if lang in names else lang)

        self.preview_cb.SetValue(bool(o["preview"]))
        self.export_images_cb.SetValue(bool(o["export_images"]))
        self.page_breaks_cb.SetValue(bool(o["page_breaks"]))
        self.rm_edges_cb.SetValue(bool(o["rm_edges"]))
        self.caps_cb.SetValue(bool(o["caps_to_headings"]))
        self.defrag_cb.SetValue(bool(o["defrag"]))
        try:
            self.heading_spin.SetValue(int(round(float(o["heading_ratio"]) * 100)))
        except Exception:
            self.heading_spin.SetValue(115)
        try:
            self.orphan_spin.SetValue(int(o["orphan_len"]))
        except Exception:
            self.orphan_spin.SetValue(45)
        math_mode = o.get("math_mode")
        self.math_choice.SetSelection(MATH_CODES.index(math_mode) if math_mode in MATH_CODES else 0)
        self.html_cb.SetValue(bool(o.get("html_copy", False)))
        self.describe_cb.SetValue(bool(o.get("describe_images", True)))

    # ---------------------------------------------------------------- convert
    @staticmethod
    def _safe_output_path(in_path: Path, out_dir: Path) -> Path:
        """Return <stem>.md in out_dir, adding _1, _2 ... instead of overwriting."""
        candidate = out_dir / (in_path.stem + ".md")
        n = 1
        while candidate.exists():
            candidate = out_dir / f"{in_path.stem}_{n}.md"
            n += 1
        return candidate

    def _error(self, title: str, message: str) -> None:
        self._set_status(f"{title}.", announce=False)
        wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR, self)

    def _ask_password(self, path: Path) -> Optional[str]:
        """Prompt until the password is right; None if the user cancels."""
        while True:
            with wx.PasswordEntryDialog(
                self,
                f"{path.name} is password protected. Enter its password to convert it.\n\n"
                "The password is used only in memory and is never stored or sent anywhere.",
                "Password Required",
            ) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return None
                pwd = dlg.GetValue()
            if not pwd:
                return None
            try:
                doc = fitz.open(str(path))
                ok = bool(doc.authenticate(pwd))
                doc.close()
            except Exception:
                ok = False
            if ok:
                return pwd
            wx.MessageBox("The password is incorrect. Please try again.", "Incorrect Password",
                          wx.OK | wx.ICON_ERROR, self)

    def _on_convert(self) -> None:
        if self._busy():
            self._set_status("A conversion is already running. Press Escape to stop it.", interrupt=True)
            return

        inputs = [Path(p) for p in self._input_paths]
        if not inputs:
            wx.MessageBox("Add one or more PDF files first. Press Ctrl+O to choose files.",
                          "No Input Files", wx.OK | wx.ICON_WARNING, self)
            self.add_btn.SetFocus()
            return

        for in_path in inputs:
            if not in_path.is_file():
                self._error("Input Not Found", f"This file no longer exists:\n{in_path}")
                return
            if in_path.suffix.lower() != ".pdf":
                self._error("Input Is Not a PDF", f"This file is not a PDF:\n{in_path}")
                return

        outp = self.out_text.GetValue().strip()
        jobs: List[Tuple[Path, Path]] = []
        try:
            if len(inputs) > 1:
                out_dir = Path(outp) if outp else inputs[0].parent
                if out_dir.exists() and not out_dir.is_dir():
                    self._error("Output Must Be a Folder",
                                "When converting several files, the output must be a folder.")
                    self.out_text.SetFocus()
                    return
                out_dir.mkdir(parents=True, exist_ok=True)
                self.out_text.ChangeValue(os_display_path(out_dir))
                for inp in inputs:
                    jobs.append((inp, self._safe_output_path(inp, out_dir)))
            else:
                in_path = inputs[0]
                out_path = Path(outp) if outp else in_path.with_suffix(".md")
                if out_path.is_dir() or outp.endswith(("\\", "/")):
                    out_path = out_path / (in_path.stem + ".md")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if out_path.exists():
                    if wx.MessageBox(f"{out_path.name} already exists. Replace it?",
                                     "Replace Output File?",
                                     wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
                        self._set_status("Conversion not started.", interrupt=True)
                        return
                self.out_text.ChangeValue(os_display_path(out_path))
                jobs.append((in_path, out_path))
        except OSError as e:
            self._error("Cannot Use Output Location", f"The output location cannot be used:\n{e}")
            return

        # Scanned PDFs need Tesseract: offer to install it instead of
        # silently producing an empty document.
        if not self._check_ocr_ready([inp for inp, _ in jobs]):
            return

        # Ask for passwords up front, on the GUI thread.
        passwords: Dict[str, Optional[str]] = {}
        if fitz is not None:
            for inp, _ in jobs:
                try:
                    doc = fitz.open(str(inp))
                    needs = bool(getattr(doc, "needs_pass", False))
                    doc.close()
                except Exception:
                    needs = False
                if needs:
                    pwd = self._ask_password(inp)
                    if pwd is None:
                        self._set_status("Conversion cancelled: a password was not provided.",
                                         interrupt=True)
                        return
                    passwords[str(inp)] = pwd

        o = self._options_from_controls()
        opts = self._engine_options(o)

        self._cancel.clear()
        self._last_pandoc_path = None
        self._last_output_path = None
        self._last_html_path = None
        self._last_announced_pct = 0
        self.log_text.Clear()
        self.gauge.SetValue(0)
        self._save_config()

        n = len(jobs)
        self._set_status(f"Converting {n} files..." if n > 1 else f"Converting {jobs[0][0].name}...",
                         interrupt=True)
        self._worker = threading.Thread(
            target=self._run_pipeline,
            args=(jobs, opts, passwords, o["math_mode"], o["html_copy"]),
            daemon=True,
        )
        self._worker.start()
        self._update_buttons()

    # ----------------------------------------------------- worker (background)
    def _call_on_gui(self, func, *args):
        """Run func on the GUI thread and wait for its result."""
        done = threading.Event()
        box: Dict[str, object] = {}

        def run():
            try:
                box["value"] = func(*args)
            finally:
                done.set()

        wx.CallAfter(run)
        done.wait()
        return box.get("value")

    def _ask_mathjax(self, name: str, n_math: int, remaining: int) -> Tuple[bool, bool]:
        """Return (enable, apply_to_rest). Runs on the GUI thread."""
        expr = "expression" if n_math == 1 else "expressions"
        dlg = wx.RichMessageDialog(
            self,
            f"{name} contains {n_math} math {expr}.\n\n"
            "Enable MathJax so the math is accessible? Screen readers will speak each "
            "expression, it can be read in Braille, and you can explore it with the arrow "
            "keys. A MathJax loader is added to the Markdown file and an accessible HTML "
            "copy is saved next to it.",
            "Math Found",
            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
        )
        dlg.SetYesNoLabels("&Enable MathJax", "&Not Now")
        if remaining > 0:
            dlg.ShowCheckBox("&Use this answer for the other files in this batch")
        answer = dlg.ShowModal() == wx.ID_YES
        apply_rest = remaining > 0 and dlg.IsCheckBoxChecked()
        dlg.Destroy()
        return answer, apply_rest

    def _postprocess_math(self, outp: Path, opts: Options, math_mode: str, html_copy: bool,
                          batch_answer: Dict[str, Optional[bool]], remaining: int) -> None:
        try:
            md = outp.read_text(encoding="utf-8")
        except Exception:
            return
        n_math = count_math(md)
        enable = False
        if n_math:
            self._log(f"Math found: {n_math} expression{'s' if n_math != 1 else ''}.")
            if math_mode == "always":
                enable = True
            elif math_mode == "ask":
                if batch_answer.get("value") is not None:
                    enable = bool(batch_answer["value"])
                else:
                    wx.CallAfter(self._set_status,
                                 f"Math found in {outp.name}. Choose whether to enable MathJax.",
                                 False)
                    enable, apply_rest = self._call_on_gui(self._ask_mathjax, outp.name, n_math,
                                                           remaining)
                    if apply_rest:
                        batch_answer["value"] = enable
        if not enable and not html_copy:
            return
        try:
            html_path = apply_mathjax(outp, ocr_lang=opts.ocr_lang, enable_mathjax=enable,
                                      write_html=True)
        except Exception as e:
            self._log(f"Could not write accessible output for {outp.name}: {e}")
            return
        if enable:
            self._log("MathJax enabled: math will be spoken by screen readers and can be "
                      "explored with the arrow keys.")
        if html_path:
            self._last_html_path = str(html_path)
            self._log(f"Accessible HTML: {os_display_path(html_path)}")

    def _run_pipeline(self, jobs: List[Tuple[Path, Path]], opts: Options,
                      passwords: Dict[str, Optional[str]], math_mode: str,
                      html_copy: bool) -> None:
        total_jobs = len(jobs)
        successes = 0
        failures: List[str] = []
        batch_answer: Dict[str, Optional[bool]] = {"value": None}
        final_status = ""
        error_dialog: Optional[Tuple[str, str]] = None

        vision.hold()
        try:
            for job_idx, (inp, outp) in enumerate(jobs):
                if self._cancel.is_set():
                    raise UserCancelled()

                if total_jobs > 1:
                    self._log("")
                    self._log(f"[{job_idx + 1} of {total_jobs}] {inp.name}")
                    wx.CallAfter(self._set_status,
                                 f"File {job_idx + 1} of {total_jobs}: {inp.name}", False)
                self._log(f"Input:  {os_display_path(inp)}")
                self._log(f"Output: {os_display_path(outp)}")
                self._log(f"OCR mode: {opts.ocr_mode}")

                def progress(done: int, total: int, idx=job_idx) -> None:
                    if self._cancel.is_set():
                        raise UserCancelled()
                    frac = (done / total) if total > 0 else 0.0
                    pct = int((idx + max(0.0, min(1.0, frac))) * 100 / total_jobs)
                    wx.CallAfter(self._on_progress, pct)

                def log_cb(msg: str) -> None:
                    if self._cancel.is_set():
                        raise UserCancelled()
                    self._log(msg)

                try:
                    pdf_to_markdown(str(inp), str(outp), opts, progress_cb=progress,
                                    log_cb=log_cb, pdf_password=passwords.get(str(inp)))
                    successes += 1
                    self._last_output_path = str(outp)
                    self._postprocess_math(outp, opts, math_mode, html_copy, batch_answer,
                                           remaining=total_jobs - job_idx - 1)
                    if self.pandoc_auto:
                        self._pandoc_export(outp, opts.ocr_lang, opts.describe_images)
                except UserCancelled:
                    raise
                except Exception as e:
                    failures.append(inp.name)
                    self._log(f"Error converting {inp.name}: {e}")
                    if total_jobs == 1:
                        error_dialog = ("Conversion Failed",
                                        f"{inp.name} could not be converted:\n\n{e}")

            if total_jobs == 1:
                if failures:
                    final_status = "Conversion failed. See the conversion log for details."
                else:
                    final_status = f"Conversion complete. Saved {jobs[0][1].name}."
                    if self._last_html_path:
                        final_status += " An accessible HTML copy was saved too."
                    if self._last_pandoc_path:
                        final_status += f" Pandoc export saved {Path(self._last_pandoc_path).name}."
            else:
                final_status = f"Batch complete: {successes} of {total_jobs} converted."
                if failures:
                    final_status += f" {len(failures)} failed: {', '.join(failures)}."
                    error_dialog = ("Some Files Failed",
                                    f"{len(failures)} of {total_jobs} files could not be converted:\n\n"
                                    + "\n".join(failures)
                                    + "\n\nSee the conversion log for details.")
            self._log("")
            self._log(final_status)
        except UserCancelled:
            self._log("Cancelled by user.")
            final_status = f"Conversion stopped. {successes} of {total_jobs} files converted."
        finally:
            passwords.clear()
            # Free the vision model's memory between batches (important on
            # computers with 8 GB of memory), unless another window uses it.
            vision.release()
            wx.CallAfter(self._on_finished, final_status, error_dialog,
                         100 if not self._cancel.is_set() else None)

    # ------------------------------------------------------- GUI-thread hooks
    def _on_progress(self, pct: int) -> None:
        pct = max(0, min(100, pct))
        self.gauge.SetValue(pct)
        self.SetStatusText(f"{self._status_text}  {pct}%")
        # Announce every 25% so screen reader users know it is working,
        # without flooding them with speech.
        step = (pct // 25) * 25
        if 0 < step < 100 and step > self._last_announced_pct:
            self._last_announced_pct = step
            self.announcer.speak(f"{step} percent")

    def _on_finished(self, status: str, error_dialog, final_pct: Optional[int]) -> None:
        if not self:
            return
        self._worker = None
        if final_pct is not None:
            self.gauge.SetValue(final_pct)
        self._cancel.clear()
        self._update_buttons()
        if status:
            self._set_status(status, interrupt=True)
        if error_dialog:
            wx.MessageBox(error_dialog[1], error_dialog[0], wx.OK | wx.ICON_ERROR, self)

    def _on_cancel(self) -> None:
        if not self._busy():
            return
        self._cancel.set()
        self._set_status("Stopping after the current step...", interrupt=True)
        self._log("Stop requested; finishing the current step...")

    # ---------------------------------------------------------------- opening
    def _open_path(self, path: Path) -> None:
        try:
            if platform.system() == "Windows":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self._error("Could Not Open", f"Could not open:\n{path}\n\n{e}")

    # ----------------------------------------------------------------- pandoc
    def _engine_options(self, o: dict) -> Options:
        return Options(
            ocr_mode=o["ocr_mode"],
            ocr_lang=o["ocr_lang"],
            preview_only=o["preview"],
            caps_to_headings=o["caps_to_headings"],
            defragment_short=o["defrag"],
            heading_size_ratio=o["heading_ratio"],
            orphan_max_len=o["orphan_len"],
            remove_headers_footers=o["rm_edges"],
            insert_page_breaks=o["page_breaks"],
            export_images=o["export_images"],
            describe_images=bool(o.get("describe_images", True)),
            vision_device=self.vision_settings.device,
            vision_model=self.vision_settings.model_id,
        )

    def _open_pandoc(self) -> None:
        """Open the pandoc converter, pre-filled with the last converted file."""
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        o = self._options_from_controls()
        engine_opts = self._engine_options(o)

        def pdf_converter(src: Path, dest_md: Path, describe: Optional[bool] = None) -> None:
            # Runs on the pandoc dialog's worker thread.
            from dataclasses import replace

            eo = engine_opts if describe is None else replace(engine_opts, describe_images=describe)
            pdf_to_markdown(str(src), str(dest_md), eo)

        initial: List[str] = []
        if self._last_output_path and Path(self._last_output_path).is_file():
            initial.append(self._last_output_path)
        else:
            initial.extend(self._input_paths)
        vs = vision.VisionSettings(enabled=self.pandoc_describe, device=self.vision_settings.device,
                                   model_id=self.vision_settings.model_id, lang=o["ocr_lang"])
        dlg = PandocDialog(self, self.pandoc_opts, self.pandoc_auto, initial, o["ocr_lang"],
                           pdf_converter, announcer=self.announcer, out_dir=self.pandoc_out_dir,
                           vision_settings=vs, include_subfolders=self.pandoc_subfolders,
                           folder_types=self.pandoc_folder_types)
        dlg.ShowModal()
        self.pandoc_opts = dlg.opts
        self.pandoc_auto = dlg.auto_export
        self.pandoc_out_dir = dlg.out_dir_value
        self.pandoc_describe = dlg.describe_images
        self.pandoc_subfolders = dlg.include_subfolders
        self.pandoc_folder_types = dlg.folder_types
        dlg.Destroy()
        self._save_config()
        if self.pandoc_auto:
            self._set_status(
                f"PDF conversions will also be exported to "
                f"{ps.format_label(self.pandoc_opts.to_format)}.", announce=False)

    def _pandoc_export(self, md_path: Path, ocr_lang: str, describe: bool = True) -> None:
        """Worker thread: export a converted Markdown file with pandoc."""
        pandoc = ps.find_pandoc()
        if not pandoc:
            self._log("Pandoc export skipped: pandoc is not installed. "
                      "Use File > Convert with Pandoc to install it.")
            return
        o = self.pandoc_opts
        dest_dir = Path(self.pandoc_out_dir) if self.pandoc_out_dir else md_path.parent
        dest = dest_dir / (md_path.stem + ps.output_extension(o.to_format))
        if dest == md_path:
            dest = dest_dir / (md_path.stem + "_pandoc" + ps.output_extension(o.to_format))
        try:
            vs = vision.VisionSettings(enabled=describe, device=self.vision_settings.device,
                                       model_id=self.vision_settings.model_id, lang=ocr_lang)
            ps.convert(md_path, dest, o, ocr_lang=ocr_lang, log_cb=self._log, pandoc=pandoc,
                       vision=vs)
            self._last_pandoc_path = str(dest)
            self._log(f"Pandoc export: {os_display_path(dest)}")
        except Exception as e:  # noqa: BLE001
            self._log(f"Pandoc export failed for {md_path.name}: {e}")

    # -------------------------------------------------------------- tesseract
    def _open_tesseract(self, check_now: bool = False) -> None:
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        dlg = TesseractDialog(self, announcer=self.announcer, check_now=check_now)
        dlg.ShowModal()
        dlg.Destroy()
        tess = ts.configure()
        self._log("Tesseract OCR: " + (f"{ts.installed_version(tess) or 'installed'} at {tess}."
                                       if tess else "not installed."))

    # ----------------------------------------------------------------- vision
    def _log_vision_status(self) -> None:
        rt = vision.find_runtime()
        model = vision.resolve_model(self.vision_settings.model_id)
        if rt and model:
            where = "built in" if model.source == "bundled" else "downloaded"
            cuda = vision.find_cuda_runtime()
            engines = "Vulkan" + (" and CUDA" if cuda else "")
            self._log(f"Vision model: {model.name} ({where}), llama.cpp {rt.build} ({engines}). "
                      "Pictures are described on this computer; press Ctrl+I to choose CUDA, "
                      "Vulkan or CPU, or to update it.")
        else:
            self._log("Vision model: not installed; pictures are not described. Press Ctrl+I "
                      "to download it.")

    def _open_vision(self, check_now: bool = False) -> None:
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        self.vision_settings.enabled = self.describe_cb.GetValue()
        self.vision_settings.lang = self._lang_code()
        dlg = VisionDialog(self, self.vision_settings, announcer=self.announcer, check_now=check_now)
        dlg.ShowModal()
        self.vision_settings = dlg.settings
        dlg.Destroy()
        self.describe_cb.SetValue(self.vision_settings.enabled)
        self._save_config()
        self._log_vision_status()

    def _open_album(self) -> None:
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        vs = vision.VisionSettings(enabled=True, device=self.vision_settings.device,
                                   model_id=self.vision_settings.model_id, lang=self._lang_code())
        if not vision.available(vs):
            if wx.MessageBox("The vision model is not installed yet. Open the Vision Model window "
                             "to download it?", "Vision Model Needed",
                             wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
                self._open_vision()
            if not vision.available(vs):
                return
        dlg = PhotoAlbumDialog(self, vs, announcer=self.announcer, folder=self.album_folder,
                               fmt=self.album_format)
        dlg.ShowModal()
        self.album_folder = dlg.folder_text.GetValue().strip()
        self.album_format = "markdown" if dlg.format_choice.GetSelection() == 1 else "html"
        dlg.Destroy()
        self._save_config()

    def _check_ocr_ready(self, inputs: List[Path]) -> bool:
        """Return False to cancel the conversion."""
        mode = OCR_CODES[max(0, self.ocr_choice.GetSelection())]
        if mode == "off" or ts.configure():
            return True
        scanned: List[str] = []
        if mode == "auto":
            try:
                from pdfmd.extract import _needs_ocr_probe
            except Exception:
                _needs_ocr_probe = None  # type: ignore
            for inp in inputs:
                try:
                    if _needs_ocr_probe and _needs_ocr_probe(str(inp), None):
                        scanned.append(inp.name)
                except Exception:
                    pass
            if not scanned:
                return True
            what = (f"{scanned[0]} looks like a scanned PDF" if len(scanned) == 1
                    else f"{len(scanned)} files look like scanned PDFs")
            msg = (f"{what}: its pages are pictures of text, which screen readers can't read. "
                   "Tesseract OCR is needed to turn it into an accessible document, and it is "
                   "not installed.\n\nInstall Tesseract now? Choose No to convert without OCR "
                   "(scanned pages will be empty).")
        else:
            msg = ("The OCR mode needs Tesseract OCR, which is not installed.\n\n"
                   "Install Tesseract now? Choose No to cancel.")
        answer = wx.MessageBox(msg, "Tesseract OCR Needed",
                               wx.YES_NO | wx.CANCEL | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
        if answer == wx.YES:
            self._open_tesseract(check_now=True)
            if ts.configure():
                return True
            self._set_status("Tesseract is still not installed. Conversion not started.", interrupt=True)
            return False
        if answer == wx.NO and mode == "auto":
            return True
        self._set_status("Conversion not started.", interrupt=True)
        return False

    def _open_output_folder(self) -> None:
        path = self._last_output_path or self.out_text.GetValue().strip()
        if not path:
            return
        folder = Path(path)
        if not folder.is_dir():
            folder = folder.parent
        if not folder.exists():
            self._error("Folder Not Found", f"The output folder does not exist:\n{folder}")
            return
        self._open_path(folder)

    def _open_last_file(self, kind: str) -> None:
        path = self._last_html_path if kind == "html" else self._last_output_path
        if not path or not Path(path).is_file():
            wx.MessageBox("There is no converted file to open yet.", "Nothing to Open",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self._open_path(Path(path))

    # ------------------------------------------------------------ view / help
    def _on_toggle_announce(self, event) -> None:
        self.announcer.enabled = self.mi_announce.IsChecked()
        self.SetStatusText("Screen reader announcements " +
                           ("on." if self.announcer.enabled else "off."))
        self.announcer.speak("Announcements on.", interrupt=True)

    def _on_theme(self, name: str) -> None:
        if name == self.theme:
            return
        self.theme = name
        self._save_config()
        if wx.MessageBox("The new theme is used the next time the program starts. Restart now?",
                         "Restart Document Conversion Suite?", wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
                         self) == wx.YES and not self._busy():
            self._restart()

    def _restart(self) -> None:
        self._save_config()
        if getattr(sys, "frozen", False):
            cmd = [sys.executable] + sys.argv[1:]
        else:
            cmd = [sys.executable, "-m", "pdfmd.app_gui"] + sys.argv[1:]
        try:
            subprocess.Popen(cmd, cwd=os.getcwd())
        except Exception:
            return
        self.Destroy()

    def _show_shortcuts(self) -> None:
        with ShortcutsDialog(self) as dlg:
            dlg.ShowModal()

    def _show_about(self) -> None:
        wx.MessageBox(
            f"Document Conversion Suite {__version__}\n\n"
            "Accessible document converter: PDF to Markdown with OCR, table detection and "
            "accessible math (MathJax), plus conversion between every format pandoc "
            "supports, and picture descriptions by a local AI vision model.\n\n"
            "Built on the pdfmd PDF engine, pandoc (pandoc.org) and llama.cpp. The default "
            "vision model is Qwen3-VL 2B Instruct, abliterated (Apache-2.0).\n\n"
            "All conversion happens on your computer. Nothing is uploaded.\n\n"
            "Licensed under the MIT License. Pandoc is licensed under the GPL.",
            "About Document Conversion Suite", wx.OK | wx.ICON_INFORMATION, self)

    # --------------------------------------------------------------- keyboard
    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE and self._busy():
            self._on_cancel()
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and event.ControlDown() \
                and not event.AltDown() and not event.ShiftDown():
            self._on_convert()
            return
        event.Skip()

    # ------------------------------------------------------------------ close
    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._busy():
            if event.CanVeto() and wx.MessageBox(
                    "A conversion is still running. Stop it and exit?", "Exit Document Conversion Suite?",
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
                event.Veto()
                return
            self._cancel.set()
        self._save_config()
        vision.shutdown()
        self.Destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class PdfMdApp(wx.App):
    def __init__(self, files: Optional[List[str]] = None) -> None:
        self._files = files or []
        super().__init__(redirect=False)

    def OnInit(self) -> bool:  # noqa: N802
        self.SetAppName(APP_NAME)
        # Send wx's internal diagnostics to stderr instead of pop-up windows
        # that would interrupt screen reader users.
        wx.Log.SetActiveTarget(wx.LogStderr())
        config = _read_config()
        theme = config.get("theme", "System")
        if platform.system() == "Windows" and hasattr(self, "MSWEnableDarkMode"):
            try:
                if theme == "Dark":
                    self.MSWEnableDarkMode(wx.App.DarkMode_Always)
                elif theme == "System":
                    self.MSWEnableDarkMode(wx.App.DarkMode_Auto)
            except Exception:
                pass
        frame = PdfMdFrame(config, initial_files=self._files)
        frame.Show()
        self.SetTopWindow(frame)
        return True


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    files = [a for a in args if a.lower().endswith(".pdf") and Path(a).is_file()]
    app = PdfMdApp(files)
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
