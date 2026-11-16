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

import copy
import json
import os
import platform
import subprocess
import sys
import tempfile
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
    from pdfmd.gui_pandoc import PandocOptionsDialog
    from pdfmd.gui_pdf_settings import (DEFAULT_OPTIONS, OCR_CODES, PdfSettingsDialog,
                                        merged_options)
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
    from pdfmd.gui_pandoc import PandocOptionsDialog
    from pdfmd.gui_pdf_settings import (DEFAULT_OPTIONS, OCR_CODES, PdfSettingsDialog,
                                        merged_options)
    from pdfmd import tesseract_support as ts
    from pdfmd.gui_tesseract import TesseractDialog
    from pdfmd import vision
    from pdfmd.gui_vision import PhotoAlbumDialog, VisionDialog
# ---------------------------------------------------------------------------

APP_NAME = "Document Conversion Suite"
APP_TITLE = "Document Conversion Suite"
CONFIG_PATH = Path.home() / ".pdfmd_gui.json"

THEMES = ("System", "Light", "Dark")

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
  Ctrl+O              Add files (PDF, Word, EPUB, HTML, Markdown and every
                      format pandoc reads)
  Ctrl+Shift+A        Add a folder
  Ctrl+Shift+O        Choose output file or folder
  F5 or Ctrl+Enter    Convert
  Shift+F5            Stop converting
  Esc                 Stop converting (while converting)
  Ctrl+Shift+P        PDF Settings (OCR, images, headings, math)
  Ctrl+P              Pandoc Options (every pandoc setting)
  Ctrl+Shift+F        Show the output folder
  Ctrl+Shift+M        Open the converted file
  Ctrl+Shift+H        Open the accessible HTML file
  Ctrl+Shift+S        Speak the current status
  Ctrl+T              Tesseract OCR: install, update, add languages
  Ctrl+I              Vision model: processor (GPU or CPU), model, updates
  Ctrl+D              Describe a folder of photos (web page or Markdown)
  Ctrl+S              Save current PDF settings as a profile
  Delete              Remove selected files (in the input list)
  F1                  This help
  Alt+F4              Exit

Go to a control (hold Alt)
  Files to convert
    Alt+I   Input files and folders list
    Alt+A   Add Files button
    Alt+D   Add Folder button
    Alt+R   Remove Selected Files button
    Alt+E   Clear List button
    Alt+B   Include subfolders of added folders (shown when the list has
            a folder)
    Alt+Y   File types to take from folders (shown when the list has a
            folder)
  Convert to
    Alt+T   Convert to (Markdown, Word, EPUB, HTML, PDF and every other
            format)
    Alt+J   Join all files into one document (not for Markdown)
    Alt+K   Keep the Markdown file too (PDFs to other formats)
    Alt+4   Describe pictures with the local AI vision model
    Alt+G   PDF Settings button
    Alt+N   Pandoc Options button
  Save to
    Alt+O   Output file or folder
    Alt+U   Choose Output button
  Progress
    Alt+C   Convert button
    Alt+S   Stop button
    Alt+W   Show Output Folder button
    Alt+L   Conversion log

Menus
  Alt+F   File menu
  Alt+P   Profiles menu
  Alt+V   View menu
  Alt+H   Help menu

PDF Settings window (Ctrl+Shift+P)
  Alt+E profile, Alt+M OCR mode, Alt+G OCR language, Alt+X export
  images, Alt+K insert page breaks, Alt+3 preview first 3 pages only,
  Alt+T remove repeating header and footer text, Alt+U promote uppercase
  lines to headings, Alt+J join short orphan lines, Alt+Z heading size
  ratio, Alt+W orphan line width, Alt+Q when equations are found, Alt+N
  save an accessible HTML copy, Alt+R reset to defaults, Enter OK,
  Esc Cancel

Pandoc Options window (Ctrl+P)
  Ctrl+Tab            Next page of settings
  Ctrl+Shift+Tab      Previous page of settings
  Alt+V               Show advanced options
  Alt+F               Reset to defaults
  Alt+P               Install Pandoc (shown when pandoc is missing)
  F1                  Every access key on every page
  Enter               OK
  Esc                 Cancel
  Only the options for the chosen output format are shown. Every control
  has its own Alt key, spoken by your screen reader with its name.

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
  model that runs on your computer, in PDFs and in every other document.
  Formats that keep pictures (Word, EPUB, HTML, PowerPoint...) get the
  description as alternative text; text-only formats get it as a block
  quote starting "Image description". Pictures that are mostly text get
  their recognised text instead.

Accessible math
  When a PDF converted to Markdown contains math, the suite offers to
  enable MathJax (the answer defaults to Yes). MathJax adds a loader to
  the Markdown file and saves an accessible HTML copy, where screen
  readers speak each expression, it can be read in Braille, and you can
  explore it piece by piece with the arrow keys. Other output formats get
  accessible math automatically: MathJax in web pages, MathML in EPUB and
  native equations in Word, OpenDocument and PowerPoint.
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
        self.pandoc_show_advanced = False
        self.pdf_options: Dict[str, object] = dict(DEFAULT_OPTIONS)
        # "" converts to Markdown (pdfmd's accessible Markdown for PDFs);
        # anything else is a pandoc output format.
        self.target_format = ""
        self.out_formats = ps.list_output_formats(ps.find_pandoc())
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

        self._set_status("Ready. Press Ctrl+O to add files, choose what to convert them to, "
                         "then press F5. Press F1 for keyboard help.", announce=False)
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
        self.mi_add = m_file.Append(wx.ID_ANY, "&Add Files...\tCtrl+O",
                                    "Choose one or more documents to convert: PDF, Word, EPUB, "
                                    "HTML, Markdown or any format pandoc reads")
        self.mi_add_dir = m_file.Append(wx.ID_ANY, "Add Fo&lder...\tCtrl+Shift+A",
                                        "Choose a folder; every document in it is converted")
        self.mi_output = m_file.Append(wx.ID_ANY, "Choose &Output...\tCtrl+Shift+O",
                                       "Choose where the converted files are saved")
        m_file.AppendSeparator()
        self.mi_convert = m_file.Append(wx.ID_ANY, "&Convert\tF5", "Start converting the input files")
        self.mi_stop = m_file.Append(wx.ID_ANY, "&Stop Converting\tShift+F5", "Stop the running conversion")
        m_file.AppendSeparator()
        self.mi_pdf_settings = m_file.Append(wx.ID_ANY, "PDF Settin&gs...\tCtrl+Shift+P",
                                             "How PDFs are read: OCR, images, headings and math")
        self.mi_pandoc = m_file.Append(wx.ID_ANY, "&Pandoc Options...\tCtrl+P",
                                       "Every pandoc setting for Word, EPUB, HTML, LaTeX, PDF and "
                                       "every other format")
        self.mi_tesseract = m_file.Append(wx.ID_ANY, "&Tesseract OCR (Install, Update, Languages)...\tCtrl+T",
                                          "Install or update Tesseract OCR and add OCR languages")
        self.mi_vision = m_file.Append(wx.ID_ANY, "&Vision Model (Picture Descriptions)...\tCtrl+I",
                                       "Choose GPU or CPU and the model that describes pictures, "
                                       "and update it")
        self.mi_album = m_file.Append(wx.ID_ANY, "&Describe a Folder of Photos...\tCtrl+D",
                                      "Describe every photo in a folder into a web page or "
                                      "Markdown file")
        m_file.AppendSeparator()
        self.mi_open_folder = m_file.Append(wx.ID_ANY, "Show Output &Folder\tCtrl+Shift+F",
                                            "Open the folder that contains the output")
        self.mi_open_md = m_file.Append(wx.ID_ANY, "Open Converted Fil&e\tCtrl+Shift+M",
                                        "Open the last converted file")
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
                                             "Save the current PDF settings as a named profile")
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
        b(wx.EVT_MENU, lambda e: self._choose_folder(), self.mi_add_dir)
        b(wx.EVT_MENU, lambda e: self._open_pdf_settings(), self.mi_pdf_settings)
        b(wx.EVT_MENU, lambda e: self._choose_output(), self.mi_output)
        b(wx.EVT_MENU, lambda e: self._on_convert(), self.mi_convert)
        b(wx.EVT_MENU, lambda e: self._on_cancel(), self.mi_stop)
        b(wx.EVT_MENU, lambda e: self._open_output_folder(), self.mi_open_folder)
        b(wx.EVT_MENU, lambda e: self._open_last_file("output"), self.mi_open_md)
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

        # ===================== Files to convert ==============================
        files_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Files to convert")
        fbox = files_sb.GetStaticBox()

        lbl = wx.StaticText(fbox, label="&Input files and folders:")
        self.input_list = wx.ListBox(fbox, style=wx.LB_EXTENDED | wx.LB_NEEDED_SB, size=(-1, 110))
        self._describe(self.input_list,
                       "Documents and folders to convert: PDF, Word, EPUB, HTML, Markdown, "
                       "OpenDocument, PowerPoint and every other format pandoc reads. Add them "
                       "with Ctrl+O or Ctrl+Shift+A, or drag them here. Press Delete to remove "
                       "the selected items. All processing is local; nothing leaves your computer.")
        files_sb.Add(lbl, 0, wx.LEFT | wx.TOP, pad)
        files_sb.Add(self.input_list, 1, wx.EXPAND | wx.ALL, pad)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(fbox, label="&Add Files...")
        self._describe(self.add_btn, "Choose one or more documents to add to the list. Hold "
                                     "Control or Shift to select several. Shortcut: Ctrl+O.")
        self.add_dir_btn = wx.Button(fbox, label="Add Fol&der...")
        self._describe(self.add_dir_btn,
                       "Choose a folder. Every document in it is converted. Shortcut: Ctrl+Shift+A.")
        self.remove_btn = wx.Button(fbox, label="&Remove Selected Files")
        self._describe(self.remove_btn, "Remove the selected files and folders from the list. "
                                        "Shortcut: Delete in the list.")
        self.clear_btn = wx.Button(fbox, label="Cl&ear List")
        self._describe(self.clear_btn, "Remove every file and folder from the list.")
        for btn in (self.add_btn, self.add_dir_btn, self.remove_btn, self.clear_btn):
            row.Add(btn, 0, wx.RIGHT, pad)
        files_sb.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)

        self.subdirs_cb = wx.CheckBox(fbox, label="Include su&bfolders of added folders")
        self._describe(self.subdirs_cb,
                       "When checked, documents in the subfolders of each added folder are "
                       "converted too. With an output folder, the subfolder layout is kept.")
        files_sb.Add(self.subdirs_cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)
        trow = wx.BoxSizer(wx.HORIZONTAL)
        self.types_lbl = wx.StaticText(fbox, label="File t&ypes to take from folders:")
        self.types_text = wx.TextCtrl(fbox)
        self._describe(self.types_text,
                       "Extensions to convert from added folders, separated by semicolons, for "
                       "example pdf; docx; md. Leave empty to take every document. Files already "
                       "in the output format are skipped. Files added one by one are always "
                       "converted.")
        trow.Add(self.types_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        trow.Add(self.types_text, 1, wx.ALIGN_CENTER_VERTICAL)
        files_sb.Add(trow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)
        main.Add(files_sb, 1, wx.EXPAND | wx.ALL, 8)

        # ===================== Convert to ====================================
        conv_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Convert to")
        cbox = conv_sb.GetStaticBox()
        crow = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(cbox, label="Convert &to:")
        self.target_choice = wx.Choice(
            cbox, choices=["Markdown (recommended)"]
            + [ps.format_label(f) for f in self.out_formats])
        self._describe(self.target_choice,
                       "The format to make. Markdown is the most accessible plain-text format; "
                       "PDFs become Markdown with pdfmd's table, math and OCR support. Choose "
                       "Word, EPUB, HTML, PDF, PowerPoint, LaTeX or any other format to convert "
                       "with pandoc; its settings are in Pandoc Options (Ctrl+P).")
        crow.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        crow.Add(self.target_choice, 1, wx.ALIGN_CENTER_VERTICAL)
        conv_sb.Add(crow, 0, wx.EXPAND | wx.ALL, pad)

        self.join_cb = wx.CheckBox(cbox, label="&Join all files into one document")
        self._describe(self.join_cb,
                       "Make one document from every file in the list, in the order of the "
                       "list, instead of one document per file. The files can be in different "
                       "formats. The output is then a single file.")
        self.keep_md_cb = wx.CheckBox(cbox, label="&Keep the Markdown file too")
        self._describe(self.keep_md_cb,
                       "PDFs are first turned into Markdown, then into the chosen format. When "
                       "checked, that Markdown file is saved too, next to the output.")
        self.describe_cb = wx.CheckBox(cbox, label="Describe pictures with the local AI vision model (&4)")
        self._describe(self.describe_cb,
                       "Photos, charts, graphs, maps and diagrams without alternative text are "
                       "described by a small AI model running on this computer, in PDFs and in "
                       "every other document. Formats that keep pictures get the description as "
                       "alternative text; text-only formats get it as a block quote. Choose GPU "
                       "or CPU, and update the model, with Ctrl+I.")
        for cb in (self.join_cb, self.keep_md_cb, self.describe_cb):
            conv_sb.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)
        brow = wx.BoxSizer(wx.HORIZONTAL)
        self.pdf_settings_btn = wx.Button(cbox, label="PDF Settin&gs...")
        self._describe(self.pdf_settings_btn,
                       "How PDFs are read: OCR mode and language, images, headers and footers, "
                       "headings, and accessible math. Shortcut: Ctrl+Shift+P.")
        self.pandoc_btn = wx.Button(cbox, label="Pandoc Optio&ns...")
        self._describe(self.pandoc_btn,
                       "Every pandoc setting for the chosen format: table of contents, "
                       "numbering, citations, templates, styles, e-book covers, slides, PDF "
                       "engines, filters and more. Shortcut: Ctrl+P.")
        brow.Add(self.pdf_settings_btn, 0, wx.RIGHT, pad)
        brow.Add(self.pandoc_btn, 0)
        conv_sb.Add(brow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)
        main.Add(conv_sb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ===================== Save to =======================================
        save_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Save to")
        sbox = save_sb.GetStaticBox()
        out_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(sbox, label="&Output file or folder:")
        self.out_text = wx.TextCtrl(sbox)
        self._describe(self.out_text,
                       "Where to save. For one file (or joined files) this is a file name; for "
                       "several files it is a folder. Leave empty to save each file next to its "
                       "original. Filled in automatically.")
        self.browse_out_btn = wx.Button(sbox, label="Choose O&utput...")
        self._describe(self.browse_out_btn, "Choose the output file or folder. Shortcut: Ctrl+Shift+O.")
        out_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        out_row.Add(self.out_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, pad)
        out_row.Add(self.browse_out_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        save_sb.Add(out_row, 0, wx.EXPAND | wx.ALL, pad)
        main.Add(save_sb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # ===================== Progress ======================================
        prog_sb = wx.StaticBoxSizer(wx.VERTICAL, panel, "Progress")
        pbox = prog_sb.GetStaticBox()
        act = wx.BoxSizer(wx.HORIZONTAL)
        self.convert_btn = wx.Button(pbox, label="&Convert")
        self._describe(self.convert_btn, "Convert the files in the list. Shortcut: F5 or Ctrl+Enter.")
        self.stop_btn = wx.Button(pbox, label="&Stop")
        self._describe(self.stop_btn, "Stop converting. Shortcut: Shift+F5 or Escape.")
        self.open_folder_btn = wx.Button(pbox, label="Sho&w Output Folder")
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
                                    size=(-1, 120))
        self._describe(self.log_text,
                       "Messages from the conversion. Read it with the arrow keys.")
        prog_sb.Add(lbl, 0, wx.LEFT | wx.TOP, pad)
        prog_sb.Add(self.log_text, 1, wx.EXPAND | wx.ALL, pad)
        main.Add(prog_sb, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(main)
        self.convert_btn.SetDefault()

        # Events
        self.add_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_inputs())
        self.add_dir_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_folder())
        self.remove_btn.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected())
        self.clear_btn.Bind(wx.EVT_BUTTON, lambda e: self._clear_inputs())
        self.subdirs_cb.Bind(wx.EVT_CHECKBOX, lambda e: self._refresh_input_list(
            select=self.input_list.GetSelections()[0] if self.input_list.GetSelections() else None))
        self.types_text.Bind(wx.EVT_KILL_FOCUS, self._on_types_done)
        self.target_choice.Bind(wx.EVT_CHOICE, lambda e: self._on_target_changed())
        self.join_cb.Bind(wx.EVT_CHECKBOX, lambda e: self._on_join_changed())
        self.pdf_settings_btn.Bind(wx.EVT_BUTTON, lambda e: self._open_pdf_settings())
        self.pandoc_btn.Bind(wx.EVT_BUTTON, lambda e: self._open_pandoc())
        self.browse_out_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_output())
        self.convert_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_convert())
        self.stop_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_cancel())
        self.open_folder_btn.Bind(wx.EVT_BUTTON, lambda e: self._open_output_folder())
        self.input_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.input_list.Bind(wx.EVT_LISTBOX, lambda e: self._update_buttons())
        self.out_text.Bind(wx.EVT_TEXT, self._on_output_edited)

        drop = PdfDropTarget(self)
        self.input_list.SetDropTarget(drop)
        self.panel.SetDropTarget(PdfDropTarget(self))
        self._update_visibility()

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

        pandoc = data.get("pandoc")
        old_auto_export = False
        if isinstance(pandoc, dict):
            self.pandoc_opts = ps.PandocOptions.from_dict(pandoc.get("options", {}))
            self.pandoc_show_advanced = bool(pandoc.get("show_advanced", False))
            old_auto_export = bool(pandoc.get("auto_export", False))
            # Batch settings that lived in the pandoc window before 1.9.0.
            self.subdirs_cb.SetValue(bool(data.get("include_subfolders",
                                                   pandoc.get("include_subfolders", False))))
            self.types_text.ChangeValue(str(data.get("folder_types",
                                                     pandoc.get("folder_types", "")) or ""))

        target = data.get("convert_to")
        if isinstance(target, str):
            self._set_target(target)
        elif old_auto_export:
            # 1.8 "Also export every PDF conversion": same files as before.
            self._set_target(self.pandoc_opts.to_format)
            self.keep_md_cb.SetValue(True)
            self._log("Your 1.8 setting \"also export to "
                      f"{ps.format_label(self.pandoc_opts.to_format)}\" is now Convert to, with "
                      "Keep the Markdown file too checked.")
        self.keep_md_cb.SetValue(bool(data.get("keep_markdown", self.keep_md_cb.GetValue())))
        self.join_cb.SetValue(bool(data.get("join_files", False)))

        inputs = data.get("last_inputs")
        if not isinstance(inputs, list):
            last = data.get("last_input")
            inputs = [last] if isinstance(last, str) else []
        inputs = [p for p in inputs if isinstance(p, str) and Path(p).exists()]
        last_output = data.get("last_output")
        if inputs:
            self.add_inputs(inputs, announce=False)
        if isinstance(last_output, str) and last_output and inputs:
            self.out_text.ChangeValue(last_output)
            self._output_is_auto = bool(data.get("output_is_auto", True))
            self._last_output_path = last_output
            self._suggest_output()

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
        self._update_visibility()

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
            "convert_to": self.target_format,
            "join_files": self.join_cb.GetValue(),
            "keep_markdown": self.keep_md_cb.GetValue(),
            "include_subfolders": self.subdirs_cb.GetValue(),
            "folder_types": self.types_text.GetValue().strip(),
            "pandoc": {
                "options": self.pandoc_opts.to_dict(),
                "show_advanced": self.pandoc_show_advanced,
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
            self.add_dir_btn: not busy,
            self.browse_out_btn: not busy,
            self.target_choice: not busy,
            self.join_cb: not busy,
            self.keep_md_cb: not busy,
            self.subdirs_cb: not busy,
            self.types_text: not busy,
            self.pdf_settings_btn: not busy,
            self.pandoc_btn: not busy,
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
        self.mi_add_dir.Enable(not busy)
        self.mi_output.Enable(not busy)
        self.mi_pdf_settings.Enable(not busy)
        self.mi_pandoc.Enable(not busy)
        self.mi_open_folder.Enable(has_output)
        self.mi_open_md.Enable(has_output)
        self.mi_open_html.Enable(bool(self._last_html_path))

    # -------------------------------------------------------- what is shown
    def _has_folders(self) -> bool:
        return any(Path(p).is_dir() for p in self._input_paths)

    def _may_have_pdfs(self) -> bool:
        return any(Path(p).is_dir() or p.lower().endswith(".pdf") for p in self._input_paths)

    def _update_visibility(self) -> None:
        """Show only the controls that do something for the current choices."""
        md = self.target_format == ""
        wanted = {
            self.join_cb: not md,
            self.keep_md_cb: not md and self._may_have_pdfs(),
            self.subdirs_cb: self._has_folders(),
            self.types_lbl: self._has_folders(),
            self.types_text: self._has_folders(),
        }
        focus = wx.Window.FindFocus()
        if focus in wanted and not wanted[focus]:
            self.target_choice.SetFocus()
        changed = False
        for w, show in wanted.items():
            if w.IsShown() != show:
                w.Show(show)
                changed = True
        if changed:
            self.panel.Layout()

    def _target_ext(self) -> str:
        return ".md" if not self.target_format else ps.output_extension(self.target_format)

    def _set_target(self, fmt: str) -> None:
        if fmt and fmt not in self.out_formats:
            return
        self.target_format = fmt
        self.target_choice.SetSelection(0 if not fmt else self.out_formats.index(fmt) + 1)
        if fmt:
            self.pandoc_opts.to_format = fmt

    def _on_target_changed(self) -> None:
        sel = self.target_choice.GetSelection()
        self._set_target("" if sel <= 0 else self.out_formats[sel - 1])
        self._update_visibility()
        self._suggest_output()
        if self.target_format == "pdf":
            self._log("PDF output needs a PDF engine such as a LaTeX distribution, Typst or "
                      "WeasyPrint, installed separately. Choose it in Pandoc Options, PDF page.")

    def _on_join_changed(self) -> None:
        self._suggest_output()
        if self.join_cb.GetValue():
            self._set_status("All files will be joined into one document, in the order of the "
                             "list.", interrupt=True)

    # ------------------------------------------------------------ input files
    def add_inputs(self, paths, announce: bool = True) -> None:
        if self._busy():
            return
        supported = set(ps.supported_input_extensions())
        added = 0
        skipped = 0
        for p in paths:
            p = os_display_path(str(p))
            path = Path(p)
            if not path.is_dir() and path.suffix.lower() not in supported:
                skipped += 1
                continue
            if p in self._input_paths:
                continue
            self._input_paths.append(p)
            added += 1
        self._refresh_input_list(select=len(self._input_paths) - 1 if added else None)
        self._update_visibility()
        self._suggest_output()
        self._update_buttons()
        if announce:
            msg = f"{added} item{'s' if added != 1 else ''} added. {len(self._input_paths)} in the list."
            if skipped:
                msg += (f" {skipped} file{'s' if skipped != 1 else ''} ignored: not a document "
                        "this program can read.")
            self._set_status(msg)

    def _label(self, path: str) -> str:
        p = Path(path)
        if not p.is_dir():
            return f"{p.name}  ({p.parent})"
        recursive = self.subdirs_cb.GetValue()
        n = len(ps.folder_files(p, recursive, ps.parse_type_filter(self.types_text.GetValue())))
        scope = " with subfolders" if recursive else ""
        return f"Folder {p.name}{scope}, {n} file{'s' if n != 1 else ''}  ({p})"

    def _refresh_input_list(self, select: Optional[int] = None) -> None:
        items = [self._label(p) for p in self._input_paths]
        self.input_list.Set(items)
        if items:
            idx = 0 if select is None else max(0, min(select, len(items) - 1))
            self.input_list.SetSelection(idx)

    def _on_types_done(self, event) -> None:
        event.Skip()
        if self._has_folders():
            wx.CallAfter(self._refresh_input_list)

    def _choose_inputs(self) -> None:
        if self._busy():
            return
        start_dir = str(Path(self._input_paths[-1]).parent) if self._input_paths else ""
        exts = ";".join("*" + e for e in ps.supported_input_extensions())
        with wx.FileDialog(self, "Add files", defaultDir=start_dir,
                           wildcard=f"Documents ({exts})|{exts}|PDF files (*.pdf)|*.pdf|"
                                    "All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            paths = dlg.GetPaths()
        self.add_inputs(paths)
        self.input_list.SetFocus()

    def _choose_folder(self) -> None:
        if self._busy():
            return
        start_dir = str(Path(self._input_paths[-1]).parent) if self._input_paths else ""
        with wx.DirDialog(self, "Add a folder of documents", defaultPath=start_dir,
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self.add_inputs([path])
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
        self._update_visibility()
        self._update_buttons()
        n = len(sels)
        self._set_status(f"{n} item{'s' if n != 1 else ''} removed. "
                         f"{len(self._input_paths)} in the list.", interrupt=True)
        if not self._input_paths:
            self.add_btn.SetFocus()

    def _clear_inputs(self) -> None:
        if self._busy() or not self._input_paths:
            return
        n = len(self._input_paths)
        if n > 1 and wx.MessageBox(f"Remove all {n} items from the list?", "Clear List",
                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._input_paths = []
        self._refresh_input_list()
        if self._output_is_auto:
            self.out_text.ChangeValue("")
        self._update_visibility()
        self._update_buttons()
        self.add_btn.SetFocus()
        self._set_status("The list is empty.", interrupt=True)

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self._remove_selected()
        else:
            event.Skip()

    # ------------------------------------------------------------------ output
    def _on_output_edited(self, event) -> None:
        self._output_is_auto = False
        event.Skip()

    def _single_output(self) -> bool:
        """True when the output is one file: one input file, or joined files."""
        if self.join_cb.GetValue() and self.target_format:
            return True
        return len(self._input_paths) == 1 and Path(self._input_paths[0]).is_file()

    def _joined_name(self) -> Path:
        first = Path(self._input_paths[0])
        base = first.parent if first.is_file() else first
        return base / (first.stem + "_joined" + self._target_ext())

    def _suggest_output(self) -> None:
        if not self._input_paths:
            return
        current = self.out_text.GetValue().strip()
        if current and not self._output_is_auto:
            # Keep the user's choice, but follow the chosen format.
            p = Path(current)
            if p.suffix and self._single_output() and not p.is_dir():
                new = p.with_suffix(self._target_ext())
                if new != p:
                    self.out_text.ChangeValue(os_display_path(new))
            return
        if self.join_cb.GetValue() and self.target_format:
            value = os_display_path(self._joined_name())
        elif self._single_output():
            value = os_display_path(Path(self._input_paths[0]).with_suffix(self._target_ext()))
        else:
            value = ""   # next to each original
        self.out_text.ChangeValue(value)
        self._output_is_auto = True

    def _choose_output(self) -> None:
        if self._busy():
            return
        current = self.out_text.GetValue().strip()
        if not self._single_output():
            with wx.DirDialog(self, "Choose output folder", defaultPath=current,
                              style=wx.DD_DEFAULT_STYLE) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                path = dlg.GetPath()
        else:
            ext = self._target_ext()
            if current:
                base = Path(current)
            elif self.join_cb.GetValue() and self.target_format:
                base = self._joined_name()
            elif self._input_paths:
                base = Path(self._input_paths[0]).with_suffix(ext)
            else:
                base = Path("output" + ext)
            name = ps.FORMAT_NAMES.get(self.target_format, "Markdown") if self.target_format \
                else "Markdown"
            with wx.FileDialog(self, "Save as", defaultDir=str(base.parent),
                               defaultFile=base.name,
                               wildcard=f"{name} (*{ext})|*{ext}|All files (*.*)|*.*",
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

    def _profile_options(self, name: str) -> Optional[dict]:
        return BUILTIN_PROFILES.get(name) or self.custom_profiles.get(name)

    def _refresh_profiles(self) -> None:
        names = self._profile_names()
        if self.current_profile not in names:
            self.current_profile = "Default"

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

    def _apply_profile(self, name: str, announce: bool = True) -> None:
        opts = self._profile_options(name)
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
        return str(self.pdf_options.get("ocr_lang") or "eng")

    def _options_from_controls(self) -> dict:
        return {**self.pdf_options, "describe_images": self.describe_cb.GetValue()}

    def _apply_options_dict(self, opts: dict) -> None:
        # Options a profile doesn't mention keep their current value for the
        # OCR language; everything else falls back to the defaults.
        self.pdf_options = merged_options(opts, self._lang_code())
        self.describe_cb.SetValue(bool(self.pdf_options.get("describe_images", True)))

    # ---------------------------------------------------------------- convert
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

    def _confirm_replace(self, path: Path) -> bool:
        if not path.exists():
            return True
        if wx.MessageBox(f"{path.name} already exists. Replace it?", "Replace Output File?",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
            return True
        self._set_status("Conversion not started.", interrupt=True)
        return False

    def _plan_jobs(self) -> Optional[List[dict]]:
        """Turn the list into conversion jobs, asking where needed. None cancels."""
        fmt = self.target_format
        ext = self._target_ext()
        recursive = self.subdirs_cb.GetValue()
        types = ps.parse_type_filter(self.types_text.GetValue())
        outp = self.out_text.GetValue().strip()
        plan_fmt = fmt or "markdown"

        for p in self._input_paths:
            if not Path(p).exists():
                self._error("Input Not Found", f"This file or folder no longer exists:\n{p}")
                return None

        if self.join_cb.GetValue() and fmt:
            sources = [j.source for j in ps.plan_batch(self._input_paths, plan_fmt, "",
                                                       recursive, types, log_cb=self._log)]
            if not sources:
                return []
            out = Path(outp) if outp else self._joined_name()
            if out.is_dir() or outp.endswith(("\\", "/")):
                out = out / self._joined_name().name
            if not out.suffix:
                out = out.with_suffix(ext)
            if any(out == s for s in sources):
                self._error("Output Would Replace an Input",
                            f"{out.name} is one of the files to convert. Choose another name.")
                return None
            if not self._confirm_replace(out):
                return None
            out.parent.mkdir(parents=True, exist_ok=True)
            self.out_text.ChangeValue(os_display_path(out))
            return [{"kind": "join", "sources": sources, "dest": out}]

        if self._single_output():
            src = Path(self._input_paths[0])
            out = Path(outp) if outp else src.with_suffix(ext)
            if out.is_dir() or outp.endswith(("\\", "/")):
                out = out / (src.stem + ext)
            if out == src:
                self._error("Output Would Replace the Input",
                            f"{src.name} is already in this format. Choose another output name "
                            "or format.")
                return None
            if not self._confirm_replace(out):
                return None
            out.parent.mkdir(parents=True, exist_ok=True)
            self.out_text.ChangeValue(os_display_path(out))
            pairs = [(src, out)]
        else:
            out_dir = Path(outp) if outp else None
            if out_dir is not None and out_dir.exists() and not out_dir.is_dir():
                self._error("Output Must Be a Folder",
                            "When converting several files, the output must be a folder, or "
                            "empty to save each file next to its original.")
                self.out_text.SetFocus()
                return None
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
            pairs = [(j.source, j.dest) for j in ps.plan_batch(
                self._input_paths, plan_fmt, out_dir or "", recursive, types, log_cb=self._log)]

        jobs = []
        for src, dest in pairs:
            is_pdf = src.suffix.lower() == ".pdf"
            if not fmt:
                kind = "pdfmd" if is_pdf else "pandoc"
            else:
                kind = "pdf_pandoc" if is_pdf else "pandoc"
            jobs.append({"kind": kind, "sources": [src], "dest": dest})
        return jobs

    def _on_convert(self) -> None:
        if self._busy():
            self._set_status("A conversion is already running. Press Escape to stop it.", interrupt=True)
            return
        if not self._input_paths:
            wx.MessageBox("Add one or more files first. Press Ctrl+O to choose files, or "
                          "Ctrl+Shift+A to choose a folder.",
                          "No Input Files", wx.OK | wx.ICON_WARNING, self)
            self.add_btn.SetFocus()
            return

        try:
            jobs = self._plan_jobs()
        except OSError as e:
            self._error("Cannot Use Output Location", f"The output location cannot be used:\n{e}")
            return
        if jobs is None:
            return
        if not jobs:
            self._set_status("Nothing to convert: the folders have no documents of the chosen "
                             "types, or every file is already in the output format.",
                             interrupt=True)
            return

        needs_pandoc = any(j["kind"] != "pdfmd" for j in jobs)
        if needs_pandoc and not ps.find_pandoc():
            if wx.MessageBox("Converting these files needs pandoc, which is not installed. "
                             "Open Pandoc Options to install it?", "Pandoc Needed",
                             wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
                self._open_pandoc()
            if not ps.find_pandoc():
                self._set_status("Conversion not started: pandoc is not installed.", interrupt=True)
                return

        pdfs = [s for j in jobs for s in j["sources"] if s.suffix.lower() == ".pdf"]
        # Scanned PDFs need Tesseract: offer to install it instead of
        # silently producing an empty document.
        if pdfs and not self._check_ocr_ready(pdfs):
            return

        # Ask for passwords up front, on the GUI thread.
        passwords: Dict[str, Optional[str]] = {}
        if fitz is not None:
            for inp in pdfs:
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
        popts = copy.deepcopy(self.pandoc_opts)
        popts.to_format = self.target_format or "markdown"
        vs = vision.VisionSettings(enabled=self.describe_cb.GetValue(),
                                   device=self.vision_settings.device,
                                   model_id=self.vision_settings.model_id, lang=o["ocr_lang"])

        self._cancel.clear()
        self._last_output_path = None
        self._last_html_path = None
        self._last_announced_pct = 0
        self.log_text.Clear()
        self.gauge.SetValue(0)
        self._save_config()

        n = sum(len(j["sources"]) for j in jobs)
        what = ps.format_label(self.target_format) if self.target_format else "Markdown"
        if jobs[0]["kind"] == "join":
            msg = f"Joining {n} files into one {what} document..."
        elif n > 1:
            msg = f"Converting {n} files to {what}..."
        else:
            msg = f"Converting {jobs[0]['sources'][0].name} to {what}..."
        self._set_status(msg, interrupt=True)
        self._worker = threading.Thread(
            target=self._run_pipeline,
            args=(jobs, opts, popts, vs, passwords, o["math_mode"], o["html_copy"],
                  self.keep_md_cb.GetValue()),
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

    @staticmethod
    def _unique(path: Path) -> Path:
        candidate, n = path, 1
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
            n += 1
        return candidate

    def _pdf_to_md(self, src: Path, md: Path, opts: Options, passwords: Dict[str, Optional[str]],
                   progress, log_cb) -> None:
        self._log(f"Reading {src.name} with pdfmd (OCR mode: {opts.ocr_mode})...")
        pdf_to_markdown(str(src), str(md), opts, progress_cb=progress, log_cb=log_cb,
                        pdf_password=passwords.get(str(src)))

    def _run_pipeline(self, jobs: List[dict], opts: Options, popts: "ps.PandocOptions", vs,
                      passwords: Dict[str, Optional[str]], math_mode: str,
                      html_copy: bool, keep_md: bool) -> None:
        total_jobs = len(jobs)
        successes = 0
        failures: List[str] = []
        batch_answer: Dict[str, Optional[bool]] = {"value": None}
        final_status = ""
        error_dialog: Optional[Tuple[str, str]] = None
        pandoc = ps.find_pandoc()
        binary_out = popts.to_format in ps.BINARY_OUTPUTS

        vision.hold()
        try:
            for job_idx, job in enumerate(jobs):
                if self._cancel.is_set():
                    raise UserCancelled()
                kind, sources, outp = job["kind"], job["sources"], job["dest"]
                name = sources[0].name if len(sources) == 1 else f"{len(sources)} files"

                if total_jobs > 1:
                    self._log("")
                    self._log(f"[{job_idx + 1} of {total_jobs}] {name}")
                    wx.CallAfter(self._set_status,
                                 f"File {job_idx + 1} of {total_jobs}: {name}", False)
                if len(sources) == 1:
                    self._log(f"Input:  {os_display_path(sources[0])}")
                self._log(f"Output: {os_display_path(outp)}")

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
                    with tempfile.TemporaryDirectory(prefix="pdfmd-") as tmp:
                        if kind == "pdfmd":
                            self._pdf_to_md(sources[0], outp, opts, passwords, progress, log_cb)
                        elif kind == "pandoc":
                            ps.convert(sources[0], outp, popts, ocr_lang=opts.ocr_lang,
                                       log_cb=log_cb, pandoc=pandoc, vision=vs)
                        else:
                            # PDFs become Markdown first: kept next to the output when
                            # asked (or when exported images must stay linked from a
                            # text format), otherwise in a temporary folder.
                            inputs: List[Path] = []
                            for src in sources:
                                if src.suffix.lower() != ".pdf":
                                    inputs.append(src)
                                    continue
                                if keep_md or (opts.export_images and not binary_out):
                                    md = self._unique(outp.parent / (src.stem + ".md"))
                                else:
                                    md = Path(tmp) / f"{len(inputs) + 1}_{src.stem}.md"
                                self._pdf_to_md(src, md, opts, passwords, progress, log_cb)
                                if keep_md:
                                    self._log(f"Markdown kept: {os_display_path(md)}")
                                inputs.append(md)
                            wx.CallAfter(self._set_status,
                                         f"Converting to {ps.format_label(popts.to_format)}...",
                                         False)
                            if kind == "join":
                                ps.join_convert(inputs, outp, popts, ocr_lang=opts.ocr_lang,
                                                log_cb=log_cb, pandoc=pandoc, vision=vs)
                            else:
                                ps.convert(inputs[0], outp, popts, ocr_lang=opts.ocr_lang,
                                           log_cb=log_cb, pandoc=pandoc, vision=vs)
                            for md in inputs:
                                if md.suffix == ".md" and md.parent == outp.parent and not keep_md \
                                        and md not in sources:
                                    md.unlink(missing_ok=True)   # assets folder stays linked
                    successes += 1
                    self._last_output_path = str(outp)
                    if outp.suffix.lower() in (".html", ".htm"):
                        self._last_html_path = str(outp)
                    if outp.suffix.lower() == ".md":
                        self._postprocess_math(outp, opts, math_mode, html_copy, batch_answer,
                                               remaining=total_jobs - job_idx - 1)
                    wx.CallAfter(self._on_progress, int((job_idx + 1) * 100 / total_jobs))
                except UserCancelled:
                    raise
                except Exception as e:
                    failures.append(name)
                    self._log(f"Error converting {name}: {e}")
                    if total_jobs == 1:
                        error_dialog = ("Conversion Failed",
                                        f"{name} could not be converted:\n\n{e}")

            if total_jobs == 1:
                if failures:
                    final_status = "Conversion failed. See the conversion log for details."
                else:
                    final_status = f"Conversion complete. Saved {jobs[0]['dest'].name}."
                    if self._last_html_path and jobs[0]["dest"].suffix.lower() == ".md":
                        final_status += " An accessible HTML copy was saved too."
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
        """Pandoc Options: every pandoc setting for the chosen output format."""
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        if self.target_format:
            self.pandoc_opts.to_format = self.target_format
        before = self.pandoc_opts.to_format
        sample = next((Path(p).name for p in self._input_paths
                       if Path(p).is_file() and not p.lower().endswith(".pdf")), "")
        dlg = PandocOptionsDialog(self, self.pandoc_opts, announcer=self.announcer,
                                  show_advanced=self.pandoc_show_advanced, sample_input=sample)
        if dlg.ShowModal() == wx.ID_OK:
            self.pandoc_opts = dlg.opts
            self.pandoc_show_advanced = dlg.show_advanced
            # Choosing an output format there converts to it here.
            if self.pandoc_opts.to_format != before or self.target_format:
                self._set_target(self.pandoc_opts.to_format)
                self._update_visibility()
                self._suggest_output()
            self._save_config()
            self._set_status("Pandoc options saved. Converting to "
                             f"{ps.format_label(self.target_format) if self.target_format else 'Markdown'}.",
                             interrupt=True)
        dlg.Destroy()
        self.out_formats = ps.list_output_formats(ps.find_pandoc())

    def _open_pdf_settings(self) -> None:
        """PDF Settings: how PDFs are read."""
        if self._busy():
            self._set_status("Wait for the current conversion to finish.", interrupt=True)
            return
        dlg = PdfSettingsDialog(self, self._options_from_controls(), self._profile_names(),
                                self.current_profile, self._profile_options,
                                announcer=self.announcer)
        if dlg.ShowModal() == wx.ID_OK:
            self.pdf_options = {**dlg.options, "describe_images": self.describe_cb.GetValue()}
            if dlg.profile != self.current_profile:
                self.current_profile = dlg.profile
                self._refresh_profiles()
            self._save_config()
            self._set_status("PDF settings saved.", interrupt=True)
        dlg.Destroy()

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
        mode = str(self.pdf_options.get("ocr_mode", "auto"))
        if mode not in OCR_CODES:
            mode = "auto"
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
    files = [a for a in args if Path(a).exists()]
    app = PdfMdApp(files)
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
