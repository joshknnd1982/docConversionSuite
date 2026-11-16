"""Accessible pandoc converter dialog for pdfmd.

Opened from File > Convert with Pandoc (Ctrl+P). Converts PDFs (through
pdfmd) or any format pandoc reads into any format pandoc writes, with
pandoc's options for standalone documents, tables of contents, numbering,
math rendering, citations, templates, reference documents, filters, PDF
engines and free-form extra arguments.

Layout: four pages in a tab control (Ctrl+Tab / Ctrl+Shift+Tab switch
pages), in the order you use them: choose the format, then the document
options, then citations and templates, and last the files and folders to
convert. One file, many files, whole folders (with or without subfolders)
or any mix are converted in one batch with the same settings. Convert,
Stop, Install Pandoc and Close buttons are always at the bottom. Every
control has a label, a description and an Alt+letter key.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, List, Optional

import wx

from . import pandoc_support as ps
from .gui_a11y import Announcer, MnemonicHandler, describe

PDF_ENGINES = ["", "pdflatex", "xelatex", "lualatex", "tectonic", "latexmk", "typst",
               "context", "wkhtmltopdf", "weasyprint", "pagedjs-cli", "prince", "groff",
               "pdfroff"]

FILES_PAGE = 3  # index of the "Files and folders" page


class _ListDropTarget(wx.FileDropTarget):
    """Files and folders dropped on the list are added to it."""

    def __init__(self, dlg: "PandocDialog") -> None:
        super().__init__()
        self.dlg = dlg

    def OnDropFiles(self, x, y, filenames):  # noqa: N802
        self.dlg.add_items(list(filenames), announce=True)
        return True


class PandocDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        opts: ps.PandocOptions,
        auto_export: bool,
        initial_files: List[str],
        ocr_lang: str,
        pdf_converter: Callable[[Path, Path], None],
        announcer: Optional[Announcer] = None,
        out_dir: str = "",
        vision_settings=None,
        include_subfolders: bool = False,
        folder_types: str = "",
    ) -> None:
        super().__init__(parent, title="Convert Any Document with Pandoc", size=(820, 720),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.opts = opts
        self.auto_export = auto_export
        self.ocr_lang = ocr_lang
        self.pdf_converter = pdf_converter
        self.announcer = announcer or Announcer()
        self.items: List[str] = []  # files and folders, in the order added
        self.out_dir_value = out_dir
        self.include_subfolders = include_subfolders
        self.folder_types = folder_types
        self.vision_settings = vision_settings
        self.describe_images = bool(vision_settings.enabled) if vision_settings is not None else False
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.pandoc = ps.find_pandoc()
        self.in_formats = ps.list_input_formats(self.pandoc)
        self.out_formats = ps.list_output_formats(self.pandoc)
        self.highlight_styles = ps.list_highlight_styles(self.pandoc)

        self._build()
        self._load(opts)
        self.add_items(initial_files)
        self.describe_cb.SetValue(self.describe_images)
        if vision_settings is None:
            self.describe_cb.Hide()
        MnemonicHandler(self)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.SetEscapeId(wx.ID_CLOSE)
        self.CentreOnParent()
        # Settings first: start on the output format; the files come last.
        wx.CallAfter(self.out_choice.SetFocus)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        outer = wx.BoxSizer(wx.VERTICAL)
        pad = 6

        self.status = wx.StaticText(self, label="")
        outer.Add(self.status, 0, wx.ALL, 8)

        self.book = wx.Notebook(self)
        describe(self.book,
                 "Pages of pandoc settings, in order: format, document options, citations, then the "
                 "files and folders to convert. Press Ctrl+Tab to move to the next page.")

        # ---------------- Page 1: format and output ----------------
        p1 = wx.Panel(self.book)
        s1 = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)
        grid.Add(wx.StaticText(p1, label="Input &format:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.in_choice = wx.Choice(
            p1, choices=["Detect from file extension"] + [ps.format_label(f) for f in self.in_formats])
        describe(self.in_choice,
                 "The format of the input files. Detect works for most files, and is needed when "
                 "a batch mixes several input types.")
        grid.Add(self.in_choice, 1, wx.EXPAND)
        grid.Add(wx.StaticText(p1, label="&Output format:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.out_choice = wx.Choice(p1, choices=[ps.format_label(f) for f in self.out_formats])
        describe(self.out_choice,
                 "The format to create, for example Microsoft Word, EPUB e-book, HTML, LaTeX, "
                 "OpenDocument, PowerPoint, reStructuredText or plain text.")
        grid.Add(self.out_choice, 1, wx.EXPAND)
        grid.Add(wx.StaticText(p1, label="Output fol&der:"), 0, wx.ALIGN_CENTER_VERTICAL)
        orow = wx.BoxSizer(wx.HORIZONTAL)
        self.out_dir = wx.TextCtrl(p1)
        describe(self.out_dir,
                 "Folder for the converted files. Leave empty to save next to each input. Files "
                 "from an added folder keep their subfolder layout inside this folder.")
        self.browse_btn = wx.Button(p1, label="&Browse...")
        describe(self.browse_btn, "Choose the output folder.")
        orow.Add(self.out_dir, 1, wx.RIGHT, pad)
        orow.Add(self.browse_btn, 0)
        grid.Add(orow, 1, wx.EXPAND)
        s1.Add(grid, 0, wx.EXPAND | wx.ALL, pad)

        self.auto_cb = wx.CheckBox(p1, label="Also e&xport every PDF conversion in the main window to this format")
        describe(self.auto_cb,
                 "When checked, each PDF you convert in the main window is also converted to the "
                 "output format chosen here, with these settings.")
        s1.Add(self.auto_cb, 0, wx.ALL, pad)

        self.describe_cb = wx.CheckBox(p1, label="Describe pi&ctures with the local AI vision model")
        describe(self.describe_cb,
                 "Pictures without alternative text are described by the vision model on this "
                 "computer. Word, EPUB, HTML, PowerPoint and other formats that can hold pictures "
                 "get the description as alternative text; plain text and other text-only "
                 "formats get it as a block quote. Alternative text the author wrote is kept.")
        s1.Add(self.describe_cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, pad)
        p1.SetSizer(s1)
        self.book.AddPage(p1, "Format and output")

        # ---------------- Page 2: document options ----------------
        p2 = wx.Panel(self.book)
        s2 = wx.BoxSizer(wx.VERTICAL)
        self.standalone_cb = wx.CheckBox(p2, label="&Standalone document (complete file with header)")
        describe(self.standalone_cb, "Write a complete document rather than a fragment. Pandoc option --standalone.")
        self.toc_cb = wx.CheckBox(p2, label="Table of &contents")
        describe(self.toc_cb, "Add a table of contents. Pandoc option --toc.")
        self.number_cb = wx.CheckBox(p2, label="&Number sections")
        describe(self.number_cb, "Number the headings. Pandoc option --number-sections.")
        self.embed_cb = wx.CheckBox(p2, label="&Embed images and styles in a single HTML file")
        describe(self.embed_cb, "Make HTML output self-contained. Pandoc option --embed-resources.")
        for cb in (self.standalone_cb, self.toc_cb, self.number_cb, self.embed_cb):
            s2.Add(cb, 0, wx.ALL, pad)

        g2 = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        g2.AddGrowableCol(1, 1)
        g2.Add(wx.StaticText(p2, label="&Depth of contents (heading levels):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.depth_spin = wx.SpinCtrl(p2, min=1, max=6, initial=3)
        describe(self.depth_spin, "How many heading levels the table of contents includes.")
        g2.Add(self.depth_spin, 0)
        g2.Add(wx.StaticText(p2, label="&Math rendering:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.math_choice = wx.Choice(p2, choices=[label for _, label in ps.MATH_METHODS])
        describe(self.math_choice,
                 "How equations are written. Automatic picks the most accessible method: MathJax "
                 "for web pages, MathML for EPUB, and native equations for Word, OpenDocument "
                 "and PowerPoint.")
        g2.Add(self.math_choice, 1, wx.EXPAND)
        g2.Add(wx.StaticText(p2, label="Code &highlighting style:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.hl_choice = wx.Choice(p2, choices=["Default"] + self.highlight_styles)
        describe(self.hl_choice, "Syntax highlighting style for code blocks.")
        g2.Add(self.hl_choice, 1, wx.EXPAND)
        g2.Add(wx.StaticText(p2, label="Line &wrapping:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.wrap_choice = wx.Choice(p2, choices=["Automatic", "None", "Preserve"])
        describe(self.wrap_choice, "How text output wraps lines. Pandoc option --wrap.")
        g2.Add(self.wrap_choice, 1, wx.EXPAND)
        g2.Add(wx.StaticText(p2, label="Document &title:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.title_text = wx.TextCtrl(p2)
        describe(self.title_text, "Optional title. Leave empty to use the file name as the page title.")
        g2.Add(self.title_text, 1, wx.EXPAND)
        g2.Add(wx.StaticText(p2, label="Document &language:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.lang_text = wx.TextCtrl(p2)
        describe(self.lang_text,
                 "Language tag such as en, fr or de-CH. Screen readers use it to pick the right "
                 "voice. Leave empty to use the OCR language.")
        g2.Add(self.lang_text, 1, wx.EXPAND)
        g2.Add(wx.StaticText(p2, label="Shift headin&g levels by:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.shift_spin = wx.SpinCtrl(p2, min=-5, max=5, initial=0)
        describe(self.shift_spin, "Promote or demote all headings. Pandoc option --shift-heading-level-by.")
        g2.Add(self.shift_spin, 0)
        s2.Add(g2, 0, wx.EXPAND | wx.ALL, pad)
        p2.SetSizer(s2)
        self.book.AddPage(p2, "Document options")

        # ---------------- Page 3: citations, templates, filters ----------------
        p3 = wx.Panel(self.book)
        s3 = wx.BoxSizer(wx.VERTICAL)
        self.cite_cb = wx.CheckBox(p3, label="Process &citations (citeproc)")
        describe(self.cite_cb, "Format citations and add a bibliography. Pandoc option --citeproc.")
        s3.Add(self.cite_cb, 0, wx.ALL, pad)
        g3 = wx.FlexGridSizer(cols=3, vgap=pad, hgap=pad)
        g3.AddGrowableCol(1, 1)

        def file_row(label: str, help_text: str, btn_label: str, wildcard: str, multi: bool = False):
            g3.Add(wx.StaticText(p3, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            txt = wx.TextCtrl(p3)
            describe(txt, help_text)
            btn = wx.Button(p3, label=btn_label)
            describe(btn, "Choose the file with a file dialog.")
            g3.Add(txt, 1, wx.EXPAND)
            g3.Add(btn, 0)
            btn.Bind(wx.EVT_BUTTON, lambda e: self._pick_file(txt, wildcard, multi))
            return txt

        self.bib_text = file_row("&Bibliography files:",
                                 "BibTeX, BibLaTeX, CSL JSON or RIS files. Separate several with semicolons.",
                                 "Choose B&ibliography...",
                                 "Bibliographies|*.bib;*.json;*.yaml;*.ris|All files|*.*", True)
        self.csl_text = file_row("Citation &style (CSL):",
                                 "A CSL style file that controls citation formatting.",
                                 "Choose Style &File...", "CSL styles (*.csl)|*.csl|All files|*.*")
        self.ref_text = file_row("&Reference document:",
                                 "A Word, OpenDocument or PowerPoint file whose styles are used for the output.",
                                 "Choose Doc&ument...",
                                 "Office documents|*.docx;*.odt;*.pptx|All files|*.*")
        self.tpl_text = file_row("&Template:", "A custom pandoc template.",
                                 "Choose Te&mplate...", "All files|*.*")
        self.filter_text = file_row("&Lua filters or filter programs:",
                                    "Pandoc filters to run, separated by semicolons. Files ending in .lua "
                                    "run as Lua filters.",
                                    "Choose Filt&er...", "Lua filters (*.lua)|*.lua|All files|*.*", True)
        s3.Add(g3, 0, wx.EXPAND | wx.ALL, pad)

        g4 = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        g4.AddGrowableCol(1, 1)
        g4.Add(wx.StaticText(p3, label="PDF engi&ne (for PDF output):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.engine_combo = wx.ComboBox(p3, choices=["Default"] + PDF_ENGINES[1:], style=wx.CB_DROPDOWN)
        describe(self.engine_combo,
                 "Program pandoc uses to make PDF files, for example xelatex, typst or weasyprint. "
                 "It must be installed separately.")
        g4.Add(self.engine_combo, 1, wx.EXPAND)
        g4.Add(wx.StaticText(p3, label="E&xtra pandoc arguments:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.extra_text = wx.TextCtrl(p3)
        describe(self.extra_text,
                 "Any other pandoc command-line options, exactly as you would type them, for "
                 "example --columns=100 --metadata author=\"Ada Lovelace\". This gives access to "
                 "every pandoc feature.")
        g4.Add(self.extra_text, 1, wx.EXPAND)
        s3.Add(g4, 0, wx.EXPAND | wx.ALL, pad)
        p3.SetSizer(s3)
        self.book.AddPage(p3, "Citations, templates and filters")

        # ---------------- Page 4: files and folders to convert ----------------
        p4 = wx.Panel(self.book)
        s4 = wx.BoxSizer(wx.VERTICAL)
        s4.Add(wx.StaticText(p4, label="&Input files and folders:"), 0, wx.LEFT | wx.TOP, pad)
        self.file_list = wx.ListBox(p4, style=wx.LB_EXTENDED, size=(-1, 140))
        describe(self.file_list,
                 "Files and folders to convert, all with the settings on the other pages. Add one "
                 "file, many files, whole folders, or a mix. PDFs are converted with the pdfmd "
                 "engine first; any format pandoc reads can be added. Shift and the arrow keys "
                 "select a range; Shift+F8, then the arrows and Space, select separate items. "
                 "Press Delete to remove the selected items.")
        self.file_list.SetDropTarget(_ListDropTarget(self))
        s4.Add(self.file_list, 1, wx.EXPAND | wx.ALL, pad)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.add_btn = wx.Button(p4, label="&Add Files...")
        describe(self.add_btn, "Choose one or more files to convert. Hold Control or Shift to "
                               "select several files in the file dialog.")
        self.add_dir_btn = wx.Button(p4, label="Add &Folder...")
        describe(self.add_dir_btn,
                 "Choose a folder. Every file in it that can be converted is converted; you can "
                 "add several folders one after another.")
        self.remove_btn = wx.Button(p4, label="&Remove Selected")
        describe(self.remove_btn, "Remove the selected files and folders from the list.")
        self.clear_btn = wx.Button(p4, label="Cl&ear List")
        describe(self.clear_btn, "Remove every file and folder from the list.")
        for b in (self.add_btn, self.add_dir_btn, self.remove_btn):
            row.Add(b, 0, wx.RIGHT, pad)
        row.Add(self.clear_btn, 0)
        s4.Add(row, 0, wx.LEFT | wx.BOTTOM, pad)

        self.subdirs_cb = wx.CheckBox(p4, label="Include &subfolders of added folders")
        describe(self.subdirs_cb,
                 "When checked, files in the subfolders of each added folder are converted too. "
                 "With an output folder, the subfolder layout is kept.")
        s4.Add(self.subdirs_cb, 0, wx.ALL, pad)
        g5 = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        g5.AddGrowableCol(1, 1)
        g5.Add(wx.StaticText(p4, label="File &types to take from folders:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.types_text = wx.TextCtrl(p4)
        describe(self.types_text,
                 "Extensions to convert from added folders, separated by semicolons, for example "
                 "docx; md; pdf. Leave empty to take every file pandoc or pdfmd can read. Files "
                 "already in the output format are always skipped. Files added one by one are "
                 "always converted.")
        g5.Add(self.types_text, 1, wx.EXPAND)
        s4.Add(g5, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, pad)

        s4.Add(wx.StaticText(p4, label="Pandoc lo&g:"), 0, wx.LEFT | wx.TOP, pad)
        self.log = wx.TextCtrl(p4, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 110))
        describe(self.log, "Messages from pandoc. Read it with the arrow keys.")
        s4.Add(self.log, 1, wx.EXPAND | wx.ALL, pad)
        p4.SetSizer(s4)
        self.book.AddPage(p4, "Files and folders")

        outer.Add(self.book, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        self.convert_btn = wx.Button(self, label="Con&vert")
        describe(self.convert_btn,
                 "Convert every file and folder in the list with these settings. If the list is "
                 "empty, moves to the Files and folders page. Shortcut: F5.")
        self.stop_btn = wx.Button(self, label="Sto&p")
        describe(self.stop_btn, "Stop the batch after the file being converted now.")
        self.install_btn = wx.Button(self, label="Install &Pandoc...")
        describe(self.install_btn, "Install pandoc with the Windows Package Manager (winget).")
        self.close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        describe(self.close_btn, "Close this window and keep the settings. Shortcut: Escape.")
        btns.Add(self.convert_btn, 0, wx.RIGHT, pad)
        btns.Add(self.stop_btn, 0, wx.RIGHT, pad)
        btns.Add(self.install_btn, 0, wx.RIGHT, pad)
        btns.Add(self.close_btn, 0)
        outer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(outer)
        self.convert_btn.SetDefault()

        self.add_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_files())
        self.add_dir_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_folder())
        self.remove_btn.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected())
        self.clear_btn.Bind(wx.EVT_BUTTON, lambda e: self._clear_items())
        self.subdirs_cb.Bind(wx.EVT_CHECKBOX, lambda e: self._refresh_list())
        self.types_text.Bind(wx.EVT_KILL_FOCUS, self._on_types_done)
        self.browse_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_dir())
        self.convert_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_convert())
        self.stop_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_stop())
        self.install_btn.Bind(wx.EVT_BUTTON, lambda e: self._install_pandoc())
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self._close())
        self.Bind(wx.EVT_CLOSE, lambda e: self._close())
        self.file_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self._update_state()

    # ------------------------------------------------------------------ state
    def _update_state(self) -> None:
        busy = self._worker is not None and self._worker.is_alive()
        if busy:
            pass  # the status line shows the batch's progress
        elif self.pandoc:
            if getattr(self, "_ver_for", None) != self.pandoc:
                self._ver_for, self._ver = self.pandoc, ps.pandoc_version(self.pandoc) or ""
            where = " (built in)" if ps.is_bundled(self.pandoc) else ""
            self.status.SetLabel(f"Pandoc {self._ver}{where} is ready.".replace("  ", " "))
        else:
            self.status.SetLabel("Pandoc is not installed. Press Install Pandoc to install it, "
                                 "then convert.")
        focus = wx.Window.FindFocus()
        # Convert stays enabled with an empty list (it then opens the Files
        # and folders page), so it is always reachable with Tab.
        can_convert = bool(self.pandoc) and not busy
        # Stop and Install Pandoc share Alt+P; only one is ever shown.
        self.stop_btn.Show(busy)
        self.install_btn.Show(not self.pandoc and not busy)
        has_items = bool(self.items) and not busy
        lose = [self.convert_btn, self.remove_btn, self.clear_btn, self.add_btn,
                self.add_dir_btn, self.subdirs_cb, self.types_text]
        for w in (self.remove_btn, self.clear_btn):
            w.Enable(has_items)
        for w in (self.add_btn, self.add_dir_btn, self.subdirs_cb, self.types_text):
            w.Enable(not busy)
        self.convert_btn.Enable(can_convert)
        self.Layout()
        # Never leave focus on a control that was just disabled or hidden.
        if busy and focus in lose and not focus.IsEnabled():
            self.stop_btn.SetFocus()
        elif not busy and focus is self.stop_btn:
            (self.convert_btn if can_convert else self.file_list).SetFocus()
        elif focus in (self.remove_btn, self.clear_btn) and not has_items:
            self.add_btn.SetFocus()
        elif focus is self.convert_btn and not can_convert:
            self.file_list.SetFocus()

    def _load(self, o: ps.PandocOptions) -> None:
        fmt = o.to_format if o.to_format in self.out_formats else (
            "html" if "html" in self.out_formats else self.out_formats[0])
        self.out_choice.SetSelection(self.out_formats.index(fmt))
        self.in_choice.SetSelection(self.in_formats.index(o.from_format) + 1
                                    if o.from_format in self.in_formats else 0)
        self.standalone_cb.SetValue(o.standalone)
        self.toc_cb.SetValue(o.toc)
        self.depth_spin.SetValue(o.toc_depth)
        self.number_cb.SetValue(o.number_sections)
        self.embed_cb.SetValue(o.embed_resources)
        codes = [c for c, _ in ps.MATH_METHODS]
        self.math_choice.SetSelection(codes.index(o.math) if o.math in codes else 0)
        self.hl_choice.SetSelection(self.highlight_styles.index(o.highlight_style) + 1
                                    if o.highlight_style in self.highlight_styles else 0)
        self.wrap_choice.SetSelection(ps.WRAP_MODES.index(o.wrap) if o.wrap in ps.WRAP_MODES else 0)
        self.title_text.SetValue(o.title)
        self.lang_text.SetValue(o.lang)
        self.shift_spin.SetValue(o.shift_heading_level)
        self.cite_cb.SetValue(o.citeproc)
        self.bib_text.SetValue(o.bibliography)
        self.csl_text.SetValue(o.csl)
        self.ref_text.SetValue(o.reference_doc)
        self.tpl_text.SetValue(o.template)
        self.filter_text.SetValue(o.lua_filters)
        self.engine_combo.SetValue(o.pdf_engine or "Default")
        self.extra_text.SetValue(o.extra_args)
        self.auto_cb.SetValue(self.auto_export)
        self.out_dir.SetValue(self.out_dir_value)
        self.subdirs_cb.SetValue(self.include_subfolders)
        self.types_text.SetValue(self.folder_types)

    def collect(self) -> ps.PandocOptions:
        o = ps.PandocOptions()
        o.to_format = self.out_formats[max(0, self.out_choice.GetSelection())]
        sel = self.in_choice.GetSelection()
        o.from_format = self.in_formats[sel - 1] if sel > 0 else ""
        o.standalone = self.standalone_cb.GetValue()
        o.toc = self.toc_cb.GetValue()
        o.toc_depth = self.depth_spin.GetValue()
        o.number_sections = self.number_cb.GetValue()
        o.embed_resources = self.embed_cb.GetValue()
        o.math = ps.MATH_METHODS[max(0, self.math_choice.GetSelection())][0]
        hl = self.hl_choice.GetSelection()
        o.highlight_style = self.highlight_styles[hl - 1] if hl > 0 else ""
        o.wrap = ps.WRAP_MODES[max(0, self.wrap_choice.GetSelection())]
        o.title = self.title_text.GetValue().strip()
        o.lang = self.lang_text.GetValue().strip()
        o.shift_heading_level = self.shift_spin.GetValue()
        o.citeproc = self.cite_cb.GetValue()
        o.bibliography = self.bib_text.GetValue().strip()
        o.csl = self.csl_text.GetValue().strip()
        o.reference_doc = self.ref_text.GetValue().strip()
        o.template = self.tpl_text.GetValue().strip()
        o.lua_filters = self.filter_text.GetValue().strip()
        engine = self.engine_combo.GetValue().strip()
        o.pdf_engine = "" if engine.lower() in ("", "default") else engine
        o.extra_args = self.extra_text.GetValue().strip()
        return o

    # ------------------------------------------------- files and folders
    def _types(self) -> Optional[set]:
        return ps.parse_type_filter(self.types_text.GetValue())

    def _label(self, path: str) -> str:
        p = Path(path)
        if not p.is_dir():
            return f"{p.name}  ({p.parent})"
        n = len(ps.folder_files(p, self.subdirs_cb.GetValue(), self._types()))
        scope = " with subfolders" if self.subdirs_cb.GetValue() else ""
        return f"Folder {p.name}{scope}, {n} file{'s' if n != 1 else ''}  ({p})"

    def _refresh_list(self, select: Optional[List[int]] = None) -> None:
        if select is None:
            select = list(self.file_list.GetSelections())
        self.file_list.Set([self._label(p) for p in self.items])
        for i in select:
            if 0 <= i < len(self.items):
                self.file_list.SetSelection(i)
        self._update_state()

    def add_items(self, paths: List[str], announce: bool = False) -> int:
        """Add files and folders to the list. Returns how many were new."""
        if self._worker is not None and self._worker.is_alive():
            if announce:
                self._say("Wait for the conversion to finish before adding more.")
            return 0
        known = {os.path.normcase(os.path.abspath(p)) for p in self.items}
        added = 0
        for p in paths:
            if not p or not (Path(p).is_file() or Path(p).is_dir()):
                continue
            k = os.path.normcase(os.path.abspath(p))
            if k in known:
                continue
            known.add(k)
            self.items.append(p)
            added += 1
        self._refresh_list(select=[len(self.items) - 1] if added else None)
        if announce:
            self._say(f"{added} added. {self._summary()}")
        return added

    # Kept for callers of the earlier, files-only dialog.
    add_files = add_items

    def _summary(self) -> str:
        folders = sum(1 for p in self.items if Path(p).is_dir())
        files = len(self.items) - folders
        parts = []
        if files:
            parts.append(f"{files} file{'s' if files != 1 else ''}")
        if folders:
            parts.append(f"{folders} folder{'s' if folders != 1 else ''}")
        return (" and ".join(parts) + " in the list.") if parts else "The list is empty."

    def _choose_folder(self) -> None:
        start = ""
        if self.items:
            last = Path(self.items[-1])
            start = str(last if last.is_dir() else last.parent)
        with wx.DirDialog(self, "Add a folder to convert", defaultPath=start,
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                self.add_dir_btn.SetFocus()
                return
            path = dlg.GetPath()
        if self.add_items([path]):
            n = len(ps.folder_files(path, self.subdirs_cb.GetValue(), self._types()))
            self._say(f"Folder {Path(path).name} added with {n} file{'s' if n != 1 else ''} to "
                      f"convert. {self._summary()}")
        else:
            self._say(f"Folder {Path(path).name} is already in the list.")
        self.file_list.SetFocus()

    def _clear_items(self) -> None:
        self.items.clear()
        self._refresh_list(select=[])
        self.add_btn.SetFocus()
        self._say("List cleared.")

    def _on_types_done(self, event: wx.FocusEvent) -> None:
        event.Skip()
        if any(Path(p).is_dir() for p in self.items):
            wx.CallAfter(self._refresh_list)

    def _choose_files(self) -> None:
        with wx.FileDialog(self, "Add files to convert",
                           wildcard="All supported files|*.pdf;*.md;*.markdown;*.docx;*.odt;*.epub;"
                                    "*.html;*.htm;*.tex;*.rst;*.adoc;*.org;*.ipynb;*.rtf;*.txt;*.typ;"
                                    "*.xml;*.pptx;*.xlsx;*.csv;*.tsv;*.json;*.wiki;*.textile;*.fb2|"
                                    "All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            paths = dlg.GetPaths()
        added = self.add_items(paths)
        self._say(f"{added} file{'s' if added != 1 else ''} added. {self._summary()}")
        self.file_list.SetFocus()

    def _remove_selected(self) -> None:
        sels = sorted(self.file_list.GetSelections(), reverse=True)
        if not sels:
            self._say("Nothing is selected.")
            return
        for i in sels:
            del self.items[i]
        keep = [min(min(sels), len(self.items) - 1)] if self.items else []
        self._refresh_list(select=keep)
        (self.file_list if self.items else self.add_btn).SetFocus()
        self._say(f"{len(sels)} removed. {self._summary()}")

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
            self._remove_selected()
        else:
            event.Skip()

    def _choose_dir(self) -> None:
        with wx.DirDialog(self, "Choose output folder", defaultPath=self.out_dir.GetValue()) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.out_dir.SetValue(dlg.GetPath())
        self.out_dir.SetFocus()

    def _pick_file(self, txt: wx.TextCtrl, wildcard: str, multi: bool) -> None:
        style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | (wx.FD_MULTIPLE if multi else 0)
        with wx.FileDialog(self, "Choose file", wildcard=wildcard, style=style) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            paths = dlg.GetPaths() if multi else [dlg.GetPath()]
        if multi and txt.GetValue().strip():
            paths = [txt.GetValue().strip()] + paths
        txt.SetValue(";".join(paths))
        txt.SetFocus()

    # --------------------------------------------------------------- convert
    def _say(self, text: str, interrupt: bool = True) -> None:
        self.announcer.speak(text, interrupt=interrupt)

    def _log(self, msg: str) -> None:
        def append():
            if self:
                self.log.AppendText(msg + "\n")
        wx.CallAfter(append)

    def _on_convert(self) -> None:
        if not self.pandoc:
            self._install_pandoc()
            return
        if self._worker and self._worker.is_alive():
            return
        if not self.items:
            # Settings are chosen; now the files. Take the user to them.
            self.book.SetSelection(FILES_PAGE)
            self.add_btn.SetFocus()
            self._say("Add the files or folders to convert, then press Convert or F5.")
            return
        opts = self.collect()
        out_dir = self.out_dir.GetValue().strip()
        self.log.Clear()
        self._stop.clear()
        self.book.SetSelection(FILES_PAGE)  # where the log is
        self._say(f"Converting {self._summary()[:-len(' in the list.')]} "
                  f"to {ps.format_label(opts.to_format)}.")
        vs = None
        if self.vision_settings is not None and self.describe_cb.GetValue():
            from dataclasses import replace

            vs = replace(self.vision_settings, enabled=True, lang=self.ocr_lang)
        self._worker = threading.Thread(
            target=self._run,
            args=(list(self.items), opts, out_dir, vs, self.subdirs_cb.GetValue(), self._types()),
            daemon=True)
        self._worker.start()
        self._update_state()

    def _on_stop(self) -> None:
        if self._worker and self._worker.is_alive() and not self._stop.is_set():
            self._stop.set()
            self.status.SetLabel("Stopping after the file being converted now...")
            self._say("Stopping after the file being converted now.")

    def _progress(self, text: str, speak: bool) -> None:
        def show():
            if self and self._worker is not None:
                self.status.SetLabel(text)
                if speak:
                    self._say(text, interrupt=False)
        wx.CallAfter(show)

    def _run(self, items: List[str], opts: ps.PandocOptions, out_dir: str, vs=None,
             recursive: bool = False, types: Optional[set] = None) -> None:
        ok, failed = 0, []
        jobs = ps.plan_batch(items, opts.to_format, out_dir, recursive, types, log_cb=self._log)
        total = len(jobs)
        if total > 1:
            self._log(f"{total} files to convert.")
        if vs is not None:
            from . import vision

            vision.hold()
        next_quarter = 1
        for i, job in enumerate(jobs, 1):
            if self._stop.is_set():
                self._log(f"Stopped. {total - i + 1} file{'s' if total - i + 1 != 1 else ''} "
                          f"not converted.")
                break
            src, dest = job.source, job.dest
            # Speak progress every quarter of a long batch; always show it.
            speak = total >= 8 and i - 1 >= next_quarter * total / 4
            if speak:
                next_quarter += 1
            self._progress(f"Converting {i} of {total}: {src.name}", speak and i > 1)
            if total > 1:
                self._log(f"--- {i} of {total}: {src}")
            try:
                if src.suffix.lower() == ".pdf":
                    with tempfile.TemporaryDirectory() as tmp:
                        md = Path(tmp) / (src.stem + ".md")
                        self._log(f"Converting {src.name} to Markdown with pdfmd...")
                        if self._converter_takes_flag():
                            self.pdf_converter(src, md, vs is not None)
                        else:  # an older converter without the flag
                            self.pdf_converter(src, md)
                        ps.convert(md, dest, opts, ocr_lang=self.ocr_lang, log_cb=self._log,
                                   pandoc=self.pandoc, vision=vs)
                else:
                    ps.convert(src, dest, opts, ocr_lang=self.ocr_lang, log_cb=self._log,
                               pandoc=self.pandoc, vision=vs)
                ok += 1
                self._last_output = dest
            except Exception as e:  # noqa: BLE001
                failed.append(src.name)
                self._log(f"Error converting {src.name}: {e}")
        if vs is not None:
            vision.release()
        wx.CallAfter(self._finished, ok, failed, total, self._stop.is_set())

    def _converter_takes_flag(self) -> bool:
        import inspect

        try:
            return len(inspect.signature(self.pdf_converter).parameters) >= 3
        except (TypeError, ValueError):
            return False

    def _finished(self, ok: int, failed: List[str], total: int, stopped: bool = False) -> None:
        if not self:
            return
        self._worker = None
        self._update_state()
        if total == 0:
            msg = ("Nothing to convert: the folders in the list have no files of the chosen "
                   "types, or every file is already in the output format.")
        else:
            msg = f"Pandoc {'stopped' if stopped else 'finished'}: {ok} of {total} converted."
        if failed:
            names = ", ".join(failed[:10])
            if len(failed) > 10:
                names += f" and {len(failed) - 10} more"
            msg += f" {len(failed)} failed: {names}."
        self.status.SetLabel(msg)
        self._log(msg)
        self._say(msg)
        if failed:
            wx.MessageBox(msg + "\n\nSee the pandoc log for details.", "Pandoc Conversion",
                          wx.OK | wx.ICON_ERROR, self)

    def _install_pandoc(self) -> None:
        cmd = ps.install_command()
        if not cmd:
            wx.MessageBox("Pandoc can be downloaded from https://pandoc.org/installing.html. "
                          "After installing it, open this window again.",
                          "Install Pandoc", wx.OK | wx.ICON_INFORMATION, self)
            return
        if wx.MessageBox("A console window will open and install pandoc with the "
                         "Windows Package Manager (winget). Pandoc is free software from "
                         "pandoc.org. Continue?", "Install Pandoc",
                         wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        try:
            subprocess.call(["cmd", "/c"] + cmd + ["&", "echo.", "&", "pause"],
                            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as e:  # noqa: BLE001
            wx.MessageBox(f"Could not start winget:\n{e}", "Install Pandoc", wx.OK | wx.ICON_ERROR, self)
            return
        # winget updates PATH for new processes only; look in the usual places.
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(
            Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc")
        self.pandoc = ps.find_pandoc() or shutil.which("pandoc")
        if self.pandoc:
            self.in_formats = ps.list_input_formats(self.pandoc)
            self.out_formats = ps.list_output_formats(self.pandoc)
            self._say("Pandoc installed and ready.")
        else:
            self._say("Pandoc was not found after installing. Try restarting Document Conversion Suite.")
        self._update_state()
        self.convert_btn.SetFocus() if self.convert_btn.IsEnabled() else self.file_list.SetFocus()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_F5 and not event.HasAnyModifiers():
            self._on_convert()
            return
        event.Skip()

    def _close(self) -> None:
        if self._worker and self._worker.is_alive():
            if wx.MessageBox("A conversion is running. Stop it after the current file and "
                             "close this window?", "Convert with Pandoc",
                             wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
                return
        self.opts = self.collect()
        self.auto_export = self.auto_cb.GetValue()
        self.out_dir_value = self.out_dir.GetValue().strip()
        self.describe_images = self.describe_cb.GetValue()
        self.include_subfolders = self.subdirs_cb.GetValue()
        self.folder_types = self.types_text.GetValue().strip()
        self._stop.set()  # a running batch stops after its current file
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Destroy()
