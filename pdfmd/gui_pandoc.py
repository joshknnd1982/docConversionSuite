"""Pandoc Options window (Ctrl+P): every pandoc setting, and nothing else.

Files are chosen and converted in the main window; this window only holds
the settings used when a file is converted to a format other than pdfmd's
Markdown. Its controls are built from ``pandoc_options.OPTIONS``, so every
pandoc option has a labelled control with help text and an Alt+letter key.

Layout: pages in a tab control (Ctrl+Tab / Ctrl+Shift+Tab move between
them). Only the options that matter for the chosen output format are shown,
and pages with nothing to show are left out. Rarely used options appear when
"Show advanced options" is checked. The bottom row (always visible) has Show
advanced options (Alt+V), Reset to Defaults (Alt+F), Install Pandoc (Alt+P,
only when pandoc is missing), OK and Cancel. F1 lists every access key.
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import wx

from . import pandoc_options as po
from . import pandoc_support as ps
from .gui_a11y import Announcer, MnemonicHandler, describe, mnemonic_of

PDF_ENGINES = ["", "pdflatex", "xelatex", "lualatex", "tectonic", "latexmk", "typst",
               "context", "wkhtmltopdf", "weasyprint", "pagedjs-cli", "prince", "groff",
               "pdfroff"]

RESERVED_KEYS = "VFP"   # Show advanced options, Reset to Defaults, Install Pandoc
LABEL_WIDTH = 260

# Controls that are not pandoc options themselves, placed around the table's
# options: (page, after this option key or "" for the top or "*" for the end).
EXTRAS: List[Tuple[str, str, str]] = [
    ("format", "", "out_format"),
    ("format", "", "in_format"),
    ("format", "template", "save_template"),
    ("format", "*", "out_ext"),
    ("format", "*", "in_ext"),
    ("math", "highlight_style", "save_highlight"),
    ("office", "reference_doc", "save_reference"),
    ("command", "*", "preview"),
]
EXTRA_LABELS = {
    "out_format": "Output format",
    "in_format": "Input format",
    "save_template": "Save Default Template...",
    "out_ext": "Output format extensions",
    "in_ext": "Input format extensions",
    "save_highlight": "Save Highlight Style...",
    "save_reference": "Save Default Reference Document...",
    "preview": "Command that will run",
}
EXTRA_HELP = {
    "out_format": "The format to create. Changing it shows the options for that format. "
                  "The main window's Convert to choice is set to the same format.",
    "in_format": "The format of the input files. Detect works for most files and is needed "
                 "when a batch mixes several input types. Choose a format to change its "
                 "extensions.",
    "save_template": "Save pandoc's built-in template for the output format to a file, so "
                     "you can edit it and choose it as the template.",
    "out_ext": "Optional features of the output format. Press Space to turn one on or off. "
               "Each item says whether pandoc turns it on by default.",
    "in_ext": "Optional features of the input format. Press Space to turn one on or off. "
              "Each item says whether pandoc turns it on by default.",
    "save_highlight": "Save the chosen highlighting style as a theme file you can edit, "
                      "then use it by typing its file name in Code highlighting.",
    "save_reference": "Save pandoc's own reference document for Word, OpenDocument or "
                      "PowerPoint. Change its styles in Word or LibreOffice, then use it as "
                      "the reference document.",
    "preview": "The pandoc command for an example file with these settings. Read it with the "
               "arrow keys; it changes as you change options.",
}


def _choices_for(spec: po.OptionSpec, highlight_styles: List[str],
                 flags: Optional[frozenset]) -> List[Tuple[str, str]]:
    if spec.key == "math":
        return list(ps.MATH_METHODS)
    return list(spec.choices)


class _Row:
    """The controls of one option (label, control, button) and how to read them."""

    def __init__(self, spec: Optional[po.OptionSpec], key: str) -> None:
        self.spec = spec
        self.key = key
        self.windows: List[wx.Window] = []
        self.get: Callable[[], Any] = lambda: None
        self.set: Callable[[Any], None] = lambda v: None


class PandocOptionsDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        opts: ps.PandocOptions,
        announcer: Optional[Announcer] = None,
        show_advanced: bool = False,
        sample_input: str = "",
    ) -> None:
        super().__init__(parent, title="Pandoc Options", size=(860, 720),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.opts = copy.deepcopy(opts)
        self.announcer = announcer or Announcer()
        self.show_advanced = show_advanced
        self.sample_input = sample_input
        self.pandoc = ps.find_pandoc()
        self._load_pandoc_info()
        self.rows: Dict[str, _Row] = {}
        self.pages: List[Tuple[str, str, wx.ScrolledWindow]] = []
        self._preview_timer: Optional[wx.CallLater] = None
        self._ext_format: Dict[str, str] = {"out_ext": "", "in_ext": ""}
        self._ext_defaults: Dict[str, Dict[str, bool]] = {"out_ext": {}, "in_ext": {}}

        self._build()
        self._load(self.opts)
        MnemonicHandler(self)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.SetEscapeId(wx.ID_CANCEL)
        self.SetAffirmativeId(wx.ID_OK)
        self.CentreOnParent()
        wx.CallAfter(self.rows["out_format"].windows[1].SetFocus)

    def _load_pandoc_info(self) -> None:
        self.flags = ps.supported_flags(self.pandoc) if self.pandoc else None
        self.in_formats = ps.list_input_formats(self.pandoc)
        self.out_formats = ps.list_output_formats(self.pandoc)
        self.highlight_styles = ps.list_highlight_styles(self.pandoc)

    # ---------------------------------------------------------------- layout
    def _page_items(self, page: str) -> List[Tuple[str, Optional[po.OptionSpec]]]:
        """(key, spec) for every control on a page, in Tab order."""
        items: List[Tuple[str, Optional[po.OptionSpec]]] = []
        items += [(k, None) for p, after, k in EXTRAS if p == page and after == ""]
        for spec in po.OPTIONS:
            if spec.page != page:
                continue
            items.append((spec.key, spec))
            items += [(k, None) for p, after, k in EXTRAS if p == page and after == spec.key]
        items += [(k, None) for p, after, k in EXTRAS if p == page and after == "*"]
        return items

    def _page_labels(self, page: str) -> List[str]:
        labels: List[str] = []
        for key, spec in self._page_items(page):
            if spec is None:
                labels.append(EXTRA_LABELS[key])
            elif spec.kind == po.CHOICE and spec.radio:
                labels.append(spec.label)
                labels += [lab for _, lab in spec.choices]
            elif spec.kind == po.FILTERS:
                labels += [spec.label, "Add Lua Filter...", "Add Filter Program...",
                           "Remove Filter", "Move Up", "Move Down"]
            else:
                labels.append(spec.label)
                if spec.button:
                    labels.append(spec.button)
        return labels

    def _build(self) -> None:
        outer = wx.BoxSizer(wx.VERTICAL)
        self.status = wx.StaticText(self, label="")
        outer.Add(self.status, 0, wx.ALL, 8)

        self.book = wx.Notebook(self)
        describe(self.book,
                 "Pages of pandoc settings. Press Ctrl+Tab for the next page and Ctrl+Shift+Tab "
                 "for the previous one. Only options for the chosen output format are shown. "
                 "Press F1 for every access key.")
        for page, title in po.PAGES:
            panel = wx.ScrolledWindow(self.book, style=wx.TAB_TRAVERSAL | wx.VSCROLL)
            panel.SetScrollRate(0, 12)
            sizer = wx.BoxSizer(wx.VERTICAL)
            keyed = iter(po.assign_access_keys(self._page_labels(page), RESERVED_KEYS))
            for key, spec in self._page_items(page):
                row = _Row(spec, key)
                if spec is None:
                    self._build_extra(panel, sizer, row, keyed)
                else:
                    self._build_option(panel, sizer, row, keyed)
                self.rows[key] = row
            panel.SetSizer(sizer)
            self.pages.append((page, title, panel))
            self.book.AddPage(panel, title)
        outer.Add(self.book, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.advanced_cb = wx.CheckBox(self, label="Show ad&vanced options")
        describe(self.advanced_cb,
                 "Also show options most people never need, such as include files, data "
                 "folders, web request headers and debugging messages.")
        self.reset_btn = wx.Button(self, label="Reset to De&faults")
        describe(self.reset_btn, "Set every pandoc option back to its default value.")
        self.install_btn = wx.Button(self, label="Install &Pandoc...")
        describe(self.install_btn, "Install pandoc with the Windows Package Manager (winget).")
        ok = wx.Button(self, wx.ID_OK, "OK")
        describe(ok, "Keep these settings and close the window. Shortcut: Enter.")
        cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        describe(cancel, "Close the window without changing the settings. Shortcut: Escape.")
        bottom.Add(self.advanced_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)
        bottom.Add(self.reset_btn, 0, wx.RIGHT, 6)
        bottom.Add(self.install_btn, 0, wx.RIGHT, 6)
        bottom.AddStretchSpacer()
        bottom.Add(ok, 0, wx.RIGHT, 6)
        bottom.Add(cancel, 0)
        outer.Add(bottom, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        ok.SetDefault()

        self.advanced_cb.Bind(wx.EVT_CHECKBOX, lambda e: self._refresh(keep_focus=True))
        self.reset_btn.Bind(wx.EVT_BUTTON, lambda e: self._reset())
        self.install_btn.Bind(wx.EVT_BUTTON, lambda e: self._install_pandoc())
        ok.Bind(wx.EVT_BUTTON, self._on_ok)
        for evt in (wx.EVT_TEXT, wx.EVT_CHECKBOX, wx.EVT_CHOICE, wx.EVT_COMBOBOX,
                    wx.EVT_SPINCTRL, wx.EVT_RADIOBUTTON, wx.EVT_LIST_ITEM_CHECKED,
                    wx.EVT_LIST_ITEM_UNCHECKED):
            self.Bind(evt, self._on_any_change)

    @staticmethod
    def _label(panel, label: str) -> wx.StaticText:
        # Created immediately before its control, so it names the control
        # for screen readers and its Alt key moves to it.
        return wx.StaticText(panel, label=label, size=(LABEL_WIDTH, -1))

    @staticmethod
    def _line(sizer, lab: wx.StaticText, ctrl: wx.Window,
              button: Optional[wx.Button] = None, tall: bool = False) -> None:
        line = wx.BoxSizer(wx.HORIZONTAL)
        line.Add(lab, 0, wx.TOP if tall else wx.ALIGN_CENTER_VERTICAL, 3 if tall else 0)
        line.Add(ctrl, 1, wx.EXPAND | wx.RIGHT, 6)
        if button is not None:
            line.Add(button, 0, 0 if tall else wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(line, 0, wx.EXPAND | wx.ALL, 5)

    def _build_option(self, panel, sizer, row: _Row, keyed) -> None:
        spec = row.spec
        assert spec is not None
        kind = spec.kind
        if kind == po.SWITCH:
            cb = wx.CheckBox(panel, label=next(keyed))
            describe(cb, spec.help)
            sizer.Add(cb, 0, wx.ALL, 5)
            row.windows = [cb]
            row.get = cb.GetValue
            row.set = lambda v, c=cb: c.SetValue(bool(v))
            return
        if kind == po.CHOICE and spec.radio:
            lab = wx.StaticText(panel, label=next(keyed))
            sizer.Add(lab, 0, wx.LEFT | wx.TOP, 5)
            radios = []
            for i, (_, _text) in enumerate(spec.choices):
                rb = wx.RadioButton(panel, label=next(keyed), style=wx.RB_GROUP if i == 0 else 0)
                describe(rb, spec.help)
                sizer.Add(rb, 0, wx.LEFT | wx.TOP, 4 if i else 2)
                radios.append(rb)
            row.windows = [lab] + radios
            values = [v for v, _ in spec.choices]

            def get_radio(rs=radios, vs=values):
                return next((v for r, v in zip(rs, vs) if r.GetValue()), vs[0])

            def set_radio(v, rs=radios, vs=values):
                rs[vs.index(v) if v in vs else 0].SetValue(True)

            row.get, row.set = get_radio, set_radio
            return
        if kind == po.FILTERS:
            self._build_filters(panel, sizer, row, keyed)
            return

        lab = self._label(panel, next(keyed))
        button = None
        if kind == po.NUMBER:
            ctrl = wx.SpinCtrl(panel, min=spec.minimum, max=spec.maximum,
                               initial=int(spec.default or 0))
            row.get = ctrl.GetValue
            row.set = lambda v, c=ctrl, d=spec.default: c.SetValue(int(v if v is not None else d))
        elif kind == po.CHOICE:
            pairs = _choices_for(spec, self.highlight_styles, self.flags)
            ctrl = wx.Choice(panel, choices=[t for _, t in pairs])
            values = [v for v, _ in pairs]
            row.get = lambda c=ctrl, vs=values: vs[max(0, c.GetSelection())]
            row.set = lambda v, c=ctrl, vs=values: c.SetSelection(vs.index(v) if v in vs else 0)
        elif kind == po.COMBO:
            if spec.key == "highlight_style":
                items = ["default", "none"]
                if self.flags is None or "syntax-highlighting" in self.flags:
                    items.append("idiomatic")
                items += self.highlight_styles
                blank = "default"
            else:
                items = ["Default"] + PDF_ENGINES[1:]
                blank = "Default"
            ctrl = wx.ComboBox(panel, choices=items, style=wx.CB_DROPDOWN)

            def get_combo(c=ctrl, b=blank):
                v = c.GetValue().strip()
                return "" if v.lower() == b.lower() else v

            row.get = get_combo
            row.set = lambda v, c=ctrl, b=blank: c.SetValue(v or b)
        elif kind in (po.PAIRS, po.LINES):
            ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 64))
            row.get = ctrl.GetValue
            row.set = lambda v, c=ctrl: c.ChangeValue(str(v or ""))
        else:   # TEXT, FILE, SAVEFILE, FILES, FOLDER
            ctrl = wx.TextCtrl(panel)
            row.get = lambda c=ctrl: c.GetValue().strip()
            row.set = lambda v, c=ctrl: c.ChangeValue(str(v or ""))
            if spec.button:
                button = wx.Button(panel, label=next(keyed))
                describe(button, "Choose with a file dialog.")
                button.Bind(wx.EVT_BUTTON, lambda e, s=spec, c=ctrl: self._choose(s, c))
        describe(ctrl, spec.help)
        self._line(sizer, lab, ctrl, button, tall=kind in (po.PAIRS, po.LINES))
        row.windows = [lab, ctrl] + ([button] if button else [])

    def _build_filters(self, panel, sizer, row: _Row, keyed) -> None:
        spec = row.spec
        lab = wx.StaticText(panel, label=next(keyed))
        lst = wx.ListBox(panel, style=wx.LB_SINGLE, size=(-1, 140))
        describe(lst, spec.help + " Select a filter, then use the buttons to remove or move it.")
        sizer.Add(lab, 0, wx.LEFT | wx.TOP, 5)
        sizer.Add(lst, 0, wx.EXPAND | wx.ALL, 5)
        line = wx.BoxSizer(wx.HORIZONTAL)
        buttons = []
        helps = ["Add a Lua filter file (.lua).",
                 "Add a filter program, for example pandoc-crossref.exe.",
                 "Remove the selected filter from the list.",
                 "Run the selected filter earlier.",
                 "Run the selected filter later."]
        for help_text in helps:
            b = wx.Button(panel, label=next(keyed))
            describe(b, help_text)
            line.Add(b, 0, wx.RIGHT, 6)
            buttons.append(b)
        sizer.Add(line, 0, wx.ALL, 5)
        add_lua, add_prog, remove, up, down = buttons

        def items() -> List[str]:
            return [lst.GetString(i) for i in range(lst.GetCount())]

        def changed(select: int) -> None:
            if 0 <= select < lst.GetCount():
                lst.SetSelection(select)
            self._on_any_change(None)

        def add(lua: bool) -> None:
            wildcard = ("Lua filters (*.lua)|*.lua|All files (*.*)|*.*" if lua
                        else "Programs (*.exe;*.py;*.cmd;*.bat)|*.exe;*.py;*.cmd;*.bat|"
                             "All files (*.*)|*.*")
            with wx.FileDialog(self, "Choose a filter", wildcard=wildcard,
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                for p in dlg.GetPaths():
                    lst.Append(p)
            changed(lst.GetCount() - 1)
            lst.SetFocus()

        def move(delta: int) -> None:
            i = lst.GetSelection()
            j = i + delta
            if i == wx.NOT_FOUND or not 0 <= j < lst.GetCount():
                return
            vals = items()
            vals[i], vals[j] = vals[j], vals[i]
            lst.Set(vals)
            changed(j)
            self._say(f"Moved to position {j + 1} of {len(vals)}.")

        def remove_sel() -> None:
            i = lst.GetSelection()
            if i == wx.NOT_FOUND:
                return
            lst.Delete(i)
            changed(min(i, lst.GetCount() - 1))
            if lst.GetCount() == 0:
                add_lua.SetFocus()

        add_lua.Bind(wx.EVT_BUTTON, lambda e: add(True))
        add_prog.Bind(wx.EVT_BUTTON, lambda e: add(False))
        remove.Bind(wx.EVT_BUTTON, lambda e: remove_sel())
        up.Bind(wx.EVT_BUTTON, lambda e: move(-1))
        down.Bind(wx.EVT_BUTTON, lambda e: move(1))
        lst.Bind(wx.EVT_KEY_DOWN, lambda e: remove_sel() if e.GetKeyCode() == wx.WXK_DELETE
                 else e.Skip())
        row.windows = [lab, lst] + buttons
        row.get = lambda: ";".join(items())
        row.set = lambda v: lst.Set(po.split_list(v))

    def _build_extra(self, panel, sizer, row: _Row, keyed) -> None:
        key = row.key
        label = next(keyed)
        help_text = EXTRA_HELP[key]
        if key in ("out_format", "in_format"):
            lab = self._label(panel, label)
            if key == "out_format":
                ctrl = wx.Choice(panel, choices=[ps.format_label(f) for f in self.out_formats])
                ctrl.Bind(wx.EVT_CHOICE, lambda e: (self._refresh(keep_focus=True), e.Skip()))
            else:
                ctrl = wx.Choice(panel, choices=["Detect from file extension"]
                                 + [ps.format_label(f) for f in self.in_formats])
                ctrl.Bind(wx.EVT_CHOICE, lambda e: (self._fill_extensions("in_ext"), e.Skip()))
            describe(ctrl, help_text)
            self._line(sizer, lab, ctrl)
            row.windows = [lab, ctrl]
            return
        if key in ("save_template", "save_highlight", "save_reference"):
            b = wx.Button(panel, label=label)
            describe(b, help_text)
            sizer.Add(b, 0, wx.ALL, 5)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key: self._save_default(k))
            row.windows = [b]
            return
        if key in ("out_ext", "in_ext"):
            lab = wx.StaticText(panel, label=label)
            lc = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(-1, 150))
            lc.EnableCheckBoxes(True)
            lc.InsertColumn(0, "Extension", width=260)
            lc.InsertColumn(1, "Pandoc's default", width=160)
            describe(lc, help_text)
            sizer.Add(lab, 0, wx.LEFT | wx.TOP, 5)
            sizer.Add(lc, 0, wx.EXPAND | wx.ALL, 5)
            row.windows = [lab, lc]
            return
        if key == "preview":
            lab = wx.StaticText(panel, label=label)
            ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
                               size=(-1, 90))
            describe(ctrl, help_text)
            sizer.Add(lab, 0, wx.LEFT | wx.TOP, 5)
            sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 5)
            row.windows = [lab, ctrl]
            self.preview = ctrl

    # ----------------------------------------------------------------- values
    def _out_format(self) -> str:
        c = self.rows["out_format"].windows[1]
        return self.out_formats[max(0, c.GetSelection())] if self.out_formats else "html"

    def _in_format(self) -> str:
        sel = self.rows["in_format"].windows[1].GetSelection()
        return self.in_formats[sel - 1] if sel > 0 else ""

    def _load(self, o: ps.PandocOptions) -> None:
        out_c = self.rows["out_format"].windows[1]
        fmt = o.to_format if o.to_format in self.out_formats else (
            "html" if "html" in self.out_formats else self.out_formats[0])
        out_c.SetSelection(self.out_formats.index(fmt))
        in_c = self.rows["in_format"].windows[1]
        in_c.SetSelection(self.in_formats.index(o.from_format) + 1
                          if o.from_format in self.in_formats else 0)
        for spec in po.OPTIONS:
            row = self.rows[spec.key]
            if spec.key == "citation_method":
                row.set(o.citation_method())
            else:
                row.set(po.get_value(o, spec))
        self.advanced_cb.SetValue(self.show_advanced)
        self._ext_format = {"out_ext": "", "in_ext": ""}
        self._refresh()

    def collect(self) -> ps.PandocOptions:
        """The settings shown in the window, as PandocOptions."""
        o = copy.deepcopy(self.opts)
        o.to_format = self._out_format()
        o.from_format = self._in_format()
        for spec in po.OPTIONS:
            po.set_value(o, spec, self.rows[spec.key].get())
        o.citeproc = o.values.get("citation_method", "") == "citeproc"
        o.in_extensions = copy.deepcopy(self.opts.in_extensions)
        o.out_extensions = copy.deepcopy(self.opts.out_extensions)
        for key, store in (("out_ext", o.out_extensions), ("in_ext", o.in_extensions)):
            fmt = self._ext_format.get(key)
            if fmt:
                changes = self._extension_changes(key)
                if changes:
                    store[fmt] = changes
                else:
                    store.pop(fmt, None)
        return o

    def _extension_changes(self, key: str) -> Dict[str, bool]:
        lc: wx.ListCtrl = self.rows[key].windows[1]
        defaults = self._ext_defaults[key]
        changes = {}
        for i in range(lc.GetItemCount()):
            name = lc.GetItemText(i)
            on = lc.IsItemChecked(i)
            if on != defaults.get(name, False):
                changes[name] = on
        return changes

    def _fill_extensions(self, key: str) -> None:
        """Show the extensions of the chosen input or output format."""
        store = self.opts.out_extensions if key == "out_ext" else self.opts.in_extensions
        old = self._ext_format.get(key)
        if old:   # remember the changes made for the previous format
            changes = self._extension_changes(key)
            if changes:
                store[old] = changes
            else:
                store.pop(old, None)
        fmt = po.base_format(self._out_format() if key == "out_ext" else self._in_format())
        lc: wx.ListCtrl = self.rows[key].windows[1]
        exts = ps.list_extensions(fmt, self.pandoc) if fmt else []
        lc.DeleteAllItems()
        self._ext_defaults[key] = dict(exts)
        changes = store.get(fmt, {})
        for i, (name, default) in enumerate(exts):
            lc.InsertItem(i, name)
            lc.SetItem(i, 1, "on by default" if default else "off by default")
            lc.CheckItem(i, changes.get(name, default))
        self._ext_format[key] = fmt
        show = bool(exts)
        for w in self.rows[key].windows:
            w.Show(show)
        self._schedule_preview()

    # ------------------------------------------------------------ visibility
    def _refresh(self, keep_focus: bool = False) -> None:
        """Show the options for the chosen output format; hide the rest."""
        self.show_advanced = self.advanced_cb.GetValue()
        to = self._out_format()
        frm = self._in_format() or None
        visible_keys = set()
        for page, _ in po.PAGES:
            for spec in po.visible_specs(page, to, frm, self.show_advanced, self.flags):
                visible_keys.add(spec.key)
        save_ok = {
            "save_template": "template" in visible_keys,
            "save_highlight": "highlight_style" in visible_keys,
            "save_reference": po.base_format(to) in ("docx", "odt", "pptx"),
        }
        page_has: Dict[str, bool] = {}
        for key, row in self.rows.items():
            if row.spec is not None:
                show = key in visible_keys
                page = row.spec.page
            else:
                show = save_ok.get(key, True)
                page = next(p for p, _, k in EXTRAS if k == key)
                if key in ("out_ext", "in_ext"):
                    show = False   # _fill_extensions shows them when there are any
            for w in row.windows:
                w.Show(show)
            page_has[page] = page_has.get(page, False) or show
        self._fill_extensions("out_ext")
        self._fill_extensions("in_ext")

        # Pages with nothing to show are left out of the tab control.
        current = self.book.GetCurrentPage()
        wanted = [(p, t, panel) for p, t, panel in self.pages if page_has.get(p)]
        for _, _, panel in self.pages:
            if not any(panel is w for _, _, w in wanted):
                panel.Hide()
        shown = [self.book.GetPage(i) for i in range(self.book.GetPageCount())]
        if shown != [panel for _, _, panel in wanted]:
            self.book.Freeze()
            while self.book.GetPageCount():
                self.book.RemovePage(0)
            for _, title, panel in wanted:
                self.book.AddPage(panel, title)
            for i in range(self.book.GetPageCount()):
                if self.book.GetPage(i) is current:
                    self.book.ChangeSelection(i)
            self.book.Thaw()
        for _, _, panel in wanted:
            panel.Layout()
            panel.FitInside()
        self._update_state()
        self.Layout()
        self._schedule_preview()

    def _update_state(self) -> None:
        if self.pandoc:
            ver = ps.pandoc_version(self.pandoc) or ""
            where = " (built in)" if ps.is_bundled(self.pandoc) else ""
            n = len([s for s in po.OPTIONS if self._row_visible(s.key)])
            self.status.SetLabel(f"Pandoc {ver}{where}. {n} options shown for "
                                 f"{ps.format_label(self._out_format())}.")
        else:
            self.status.SetLabel("Pandoc is not installed. Press Install Pandoc to install it.")
        if self.install_btn.HasFocus() and self.pandoc:
            self.advanced_cb.SetFocus()
        self.install_btn.Show(not self.pandoc)

    def _row_visible(self, key: str) -> bool:
        row = self.rows.get(key)
        return bool(row and row.windows and row.windows[0].IsShown())

    # ---------------------------------------------------------------- preview
    def _on_any_change(self, event) -> None:
        if event is not None:
            event.Skip()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_timer is not None and self._preview_timer.IsRunning():
            self._preview_timer.Restart(200)
        else:
            self._preview_timer = wx.CallLater(200, self._update_preview)

    def _update_preview(self) -> None:
        if not self or not hasattr(self, "preview"):
            return
        o = self.collect()
        name = self.sample_input or "document.md"
        try:
            text = ps.command_preview(o, Path(name).name, self.pandoc)
        except Exception as e:  # noqa: BLE001
            text = f"(cannot show the command: {e})"
        if self.preview.GetValue() != text:
            self.preview.ChangeValue(text)

    # ------------------------------------------------------------------ tools
    def _choose(self, spec: po.OptionSpec, txt: wx.TextCtrl) -> None:
        current = po.split_list(txt.GetValue()) if spec.kind == po.FILES else [txt.GetValue()]
        start = str(Path(current[-1]).parent) if current and current[-1] else ""
        if spec.kind == po.FOLDER:
            with wx.DirDialog(self, spec.label, defaultPath=txt.GetValue() or start) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    txt.SetValue(dlg.GetPath())
        else:
            style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT if spec.kind == po.SAVEFILE \
                else wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
            if spec.kind == po.FILES:
                style |= wx.FD_MULTIPLE
            with wx.FileDialog(self, spec.label, defaultDir=start, wildcard=spec.wildcard,
                               style=style) as dlg:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                if spec.kind == po.FILES:
                    paths = [p for p in current if p] + list(dlg.GetPaths())
                    txt.SetValue("; ".join(dict.fromkeys(paths)))
                else:
                    txt.SetValue(dlg.GetPath())
        txt.SetFocus()

    def _save_default(self, which: str) -> None:
        to = po.base_format(self._out_format())
        try:
            if which == "save_template":
                fmt = "latex" if to == "pdf" else to
                data = ps.default_template(fmt, self.pandoc).encode("utf-8")
                name, wildcard, use_key = f"default.{fmt}", "All files (*.*)|*.*", "template"
            elif which == "save_reference":
                data = ps.default_data_file(f"reference.{to}", self.pandoc)
                name = f"reference.{to}"
                wildcard = f"{to.upper()} files (*.{to})|*.{to}"
                use_key = "reference_doc"
            else:
                style = self.rows["highlight_style"].get() or "pygments"
                if style in ("none", "idiomatic") or style.lower().endswith(".theme"):
                    style = "pygments"
                data = ps.highlight_style_theme(style, self.pandoc).encode("utf-8")
                name, wildcard, use_key = (f"{style}.theme",
                                           "Theme files (*.theme)|*.theme", "highlight_style")
        except Exception as e:  # noqa: BLE001
            wx.MessageBox(f"Pandoc could not provide the file:\n{e}", "Save Default File",
                          wx.OK | wx.ICON_ERROR, self)
            return
        with wx.FileDialog(self, "Save As", defaultFile=name, wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        try:
            Path(path).write_bytes(data)
        except OSError as e:
            wx.MessageBox(f"Could not save the file:\n{e}", "Save Default File",
                          wx.OK | wx.ICON_ERROR, self)
            return
        if wx.MessageBox(f"Saved {Path(path).name}. Use it for this conversion from now on?",
                         "Use the Saved File?",
                         wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
            self.rows[use_key].set(path)
            self._say(f"{Path(path).name} will be used.")
            self._schedule_preview()

    def _reset(self) -> None:
        if wx.MessageBox("Set every pandoc option back to its default value?",
                         "Reset to Defaults", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                         self) != wx.YES:
            return
        to = self._out_format()
        self.opts = ps.PandocOptions(to_format=to)
        self._load(self.opts)
        self._say("Every pandoc option is back to its default value.")

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
            wx.MessageBox(f"Could not start winget:\n{e}", "Install Pandoc",
                          wx.OK | wx.ICON_ERROR, self)
            return
        # winget updates PATH for new processes only; look in the usual places.
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(
            Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc")
        self.pandoc = ps.find_pandoc() or shutil.which("pandoc")
        if self.pandoc:
            self._say("Pandoc installed. Close and reopen this window to see every format.")
        else:
            self._say("Pandoc was not found after installing. Try restarting Document "
                      "Conversion Suite.")
        self.advanced_cb.SetFocus()
        self._update_state()
        self.Layout()

    # ------------------------------------------------------------------- keys
    def access_key_text(self) -> str:
        """Every page's Alt keys, for F1 and the documentation."""
        lines = ["Pandoc Options window access keys", "",
                 "Always available: Alt+V Show advanced options, Alt+F Reset to Defaults, "
                 "Alt+P Install Pandoc (when pandoc is missing), Enter OK, Escape Cancel, "
                 "Ctrl+Tab next page, Ctrl+Shift+Tab previous page.", ""]
        for page, title in po.PAGES:
            keyed = po.assign_access_keys(self._page_labels(page), RESERVED_KEYS)
            parts = [f"Alt+{mnemonic_of(k)} {k.replace('&', '')}" for k in keyed]
            lines.append(f"{title} page: " + "; ".join(parts) + ".")
            lines.append("")
        return "\n".join(lines)

    def _show_keys(self) -> None:
        dlg = wx.Dialog(self, title="Pandoc Options Keys", size=(700, 520),
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        s = wx.BoxSizer(wx.VERTICAL)
        txt = wx.TextCtrl(dlg, value=self.access_key_text(),
                          style=wx.TE_MULTILINE | wx.TE_READONLY)
        describe(txt, "Every access key in the Pandoc Options window. Read it with the arrow keys.")
        close = wx.Button(dlg, wx.ID_CLOSE, "&Close")
        close.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE))
        dlg.SetEscapeId(wx.ID_CLOSE)
        s.Add(txt, 1, wx.EXPAND | wx.ALL, 8)
        s.Add(close, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        dlg.SetSizer(s)
        txt.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_F1 and not event.HasAnyModifiers():
            self._show_keys()
            return
        event.Skip()

    def _say(self, text: str) -> None:
        self.announcer.speak(text, interrupt=True)

    def _on_ok(self, event) -> None:
        self.opts = self.collect()
        self.show_advanced = self.advanced_cb.GetValue()
        self.EndModal(wx.ID_OK)


__all__ = ["PandocOptionsDialog", "PDF_ENGINES"]
