"""PDF Settings window (Ctrl+Shift+P): how PDFs are read.

These settings only matter for PDF files (pdfmd's engine); other documents
are read by pandoc. They used to fill the main window; moving them here
keeps the main window short: files, what to make, where to save, Convert.

Every control has a label, a description and the same Alt+letter key it had
in the main window before 1.9.0.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import wx

from .gui_a11y import Announcer, MnemonicHandler, describe

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


def lang_label(code: str) -> str:
    names = dict(OCR_LANGS)
    return f"{code} ({names[code]})" if code in names else code


def lang_code(text: str) -> str:
    raw = (text or "").strip()
    return (raw.split(" (")[0].strip() if raw else "") or "eng"


def merged_options(opts: Optional[dict], current_lang: str = "eng") -> dict:
    """A complete options dict: defaults, then ``opts``.

    Options a profile doesn't mention keep the current OCR language;
    everything else falls back to the defaults.
    """
    return {**DEFAULT_OPTIONS, "ocr_lang": current_lang, **(opts or {})}


class PdfSettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, options: dict, profiles: List[str],
                 current_profile: str, profile_options: Callable[[str], Optional[dict]],
                 announcer: Optional[Announcer] = None) -> None:
        super().__init__(parent, title="PDF Settings", size=(720, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.announcer = announcer or Announcer()
        self.profile_options = profile_options
        self.options = merged_options(options, str(options.get("ocr_lang", "eng")))
        self.profile = current_profile
        self._build(profiles)
        self._apply(self.options)
        MnemonicHandler(self)
        self.SetEscapeId(wx.ID_CANCEL)
        self.SetAffirmativeId(wx.ID_OK)
        self.CentreOnParent()
        wx.CallAfter(self.ocr_choice.SetFocus)

    def _build(self, profiles: List[str]) -> None:
        pad = 6
        outer = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label="These settings are used for PDF files. Other "
                                          "documents are read by pandoc.")
        outer.Add(intro, 0, wx.ALL, 10)

        grid = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)

        def labelled(label: str, ctrl_factory, help_text: str):
            lab = wx.StaticText(self, label=label)   # created right before its control
            ctrl = ctrl_factory()
            describe(ctrl, help_text)
            grid.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.profile_choice = labelled(
            "Profil&e:", lambda: wx.Choice(self, choices=profiles),
            "Apply a saved set of PDF settings. Built-in profiles include one for math and "
            "science documents. Save your own with Profiles, Save Current Settings as "
            "Profile (Ctrl+S) in the main window.")
        if self.profile in profiles:
            self.profile_choice.SetStringSelection(self.profile)
        self.ocr_choice = labelled(
            "OCR &mode:", lambda: wx.Choice(self, choices=[t for _, t in OCR_MODES]),
            "Off uses the text stored in the PDF and is fastest. Auto detects scanned pages "
            "and runs OCR only where needed. Tesseract runs OCR on every page. OCRmyPDF gives "
            "the highest-fidelity OCR. OCR needs Tesseract, which is built in.")
        self.lang_combo = labelled(
            "OCR lan&guage:",
            lambda: wx.ComboBox(self, choices=[lang_label(c) for c, _ in OCR_LANGS],
                                style=wx.CB_DROPDOWN),
            "Tesseract language code used for OCR. Choose from the list or type a code. "
            "Combine languages with a plus sign, for example eng+fra. Also sets the language "
            "of the documents made from PDFs.")
        outer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        checks = wx.BoxSizer(wx.VERTICAL)

        def check(label: str, help_text: str) -> wx.CheckBox:
            cb = wx.CheckBox(self, label=label)
            describe(cb, help_text)
            checks.Add(cb, 0, wx.TOP, pad)
            return cb

        self.export_images_cb = check(
            "E&xport images",
            "Save the images in the PDF to a folder next to the output and link them with "
            "descriptive alternative text.")
        self.page_breaks_cb = check("Insert page brea&ks", "Insert a horizontal rule between pages.")
        self.preview_cb = check("Preview first &3 pages only",
                                "Convert only the first three pages, for a quick check.")
        self.rm_edges_cb = check(
            "Remove repeating header and footer &text",
            "Remove running headers, footers and page numbers that repeat on every page.")
        self.caps_cb = check("Promote &uppercase lines to headings",
                             "Treat short lines written in all capitals as headings.")
        self.defrag_cb = check(
            "&Join short orphan lines into paragraphs",
            "Merge short isolated lines into the previous paragraph so text reads smoothly.")
        outer.Add(checks, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        tune = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        lab = wx.StaticText(self, label="Heading si&ze ratio (percent of body text):")
        self.heading_spin = wx.SpinCtrl(self, min=100, max=250, initial=115,
                                        style=wx.SP_ARROW_KEYS)
        self.heading_spin.SetIncrement(5)
        describe(self.heading_spin,
                 "Text at least this many percent of the body text size becomes a heading. "
                 "Lower values create more headings. Default 115.")
        tune.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL)
        tune.Add(self.heading_spin, 0)
        lab = wx.StaticText(self, label="Orphan line &width (characters):")
        self.orphan_spin = wx.SpinCtrl(self, min=10, max=120, initial=45, style=wx.SP_ARROW_KEYS)
        describe(self.orphan_spin,
                 "Isolated lines up to this many characters are merged into the previous "
                 "paragraph. Default 45.")
        tune.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL)
        tune.Add(self.orphan_spin, 0)
        lab = wx.StaticText(self, label="When e&quations are found:")
        self.math_choice = wx.Choice(self, choices=[t for _, t in MATH_MODES])
        describe(self.math_choice,
                 "What to do when a PDF converted to Markdown contains math. MathJax makes math "
                 "accessible: screen readers speak it, it can be read in Braille, and you can "
                 "explore it with the arrow keys. Ask me is the default, and the question "
                 "defaults to Yes. Other output formats always get accessible math.")
        tune.Add(lab, 0, wx.ALIGN_CENTER_VERTICAL)
        tune.Add(self.math_choice, 0)
        outer.Add(tune, 0, wx.ALL, 10)

        self.html_cb = wx.CheckBox(
            self, label="Save a&n accessible HTML copy of each Markdown file")
        describe(self.html_cb,
                 "When converting to Markdown, also save an HTML version with the document "
                 "language, real headings and table header cells. Documents with math always "
                 "get one when MathJax is enabled.")
        outer.Add(self.html_cb, 0, wx.LEFT | wx.RIGHT, 10)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        reset = wx.Button(self, label="&Reset to Defaults")
        describe(reset, "Set every PDF setting back to its default value.")
        ok = wx.Button(self, wx.ID_OK, "OK")
        describe(ok, "Keep these settings. Shortcut: Enter.")
        cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        describe(cancel, "Close without changing the settings. Shortcut: Escape.")
        btns.Add(reset, 0)
        btns.AddStretchSpacer()
        btns.Add(ok, 0, wx.RIGHT, pad)
        btns.Add(cancel, 0)
        outer.AddStretchSpacer()
        outer.Add(btns, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(outer)
        ok.SetDefault()

        self.profile_choice.Bind(wx.EVT_CHOICE, self._on_profile)
        reset.Bind(wx.EVT_BUTTON, lambda e: self._reset())
        ok.Bind(wx.EVT_BUTTON, self._on_ok)

    def _apply(self, o: dict) -> None:
        o = merged_options(o, lang_code(self.lang_combo.GetValue())
                           if self.lang_combo.GetValue() else str(o.get("ocr_lang", "eng")))
        mode = o.get("ocr_mode")
        self.ocr_choice.SetSelection(OCR_CODES.index(mode) if mode in OCR_CODES else 0)
        self.lang_combo.SetValue(lang_label(str(o.get("ocr_lang") or "eng")))
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
        self._describe_images = bool(o.get("describe_images", True))

    def collect(self) -> dict:
        return {
            "ocr_mode": OCR_CODES[max(0, self.ocr_choice.GetSelection())],
            "ocr_lang": lang_code(self.lang_combo.GetValue()),
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
            "describe_images": self._describe_images,
        }

    def _on_profile(self, event) -> None:
        name = self.profile_choice.GetStringSelection()
        opts = self.profile_options(name) if name else None
        if opts is not None:
            self._apply(opts)
            self.profile = name
            self.announcer.speak(f"Profile {name} applied.", interrupt=True)

    def _reset(self) -> None:
        self._apply(DEFAULT_OPTIONS)
        if self.profile_choice.FindString("Default") != wx.NOT_FOUND:
            self.profile_choice.SetStringSelection("Default")
            self.profile = "Default"
        self.announcer.speak("PDF settings reset to defaults.", interrupt=True)

    def _on_ok(self, event) -> None:
        self.options = self.collect()
        self.EndModal(wx.ID_OK)


__all__ = ["PdfSettingsDialog", "OCR_MODES", "OCR_CODES", "OCR_LANGS", "MATH_MODES",
           "MATH_CODES", "DEFAULT_OPTIONS", "lang_label", "lang_code", "merged_options"]
