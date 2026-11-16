"""Accessibility checks for the windows: labels, help text and unique Alt keys.

Builds the windows without showing them. Skipped when wxPython is missing.

Run with:  python -m pytest tests
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

wx = pytest.importorskip("wx")

from pdfmd import pandoc_support as ps  # noqa: E402
from pdfmd.gui_a11y import mnemonic_of  # noqa: E402

INTERACTIVE = (wx.Button, wx.CheckBox, wx.RadioButton, wx.Choice, wx.ComboBox, wx.TextCtrl,
               wx.SpinCtrl, wx.ListBox, wx.ListCtrl)
KEYED = (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioButton)


@pytest.fixture(scope="module")
def app():
    a = wx.App(False)
    yield a
    for w in wx.GetTopLevelWindows():
        w.Destroy()


def _visible(win: wx.Window, stop: wx.Window) -> bool:
    w = win
    while w is not None and w is not stop:
        if not w.IsShown():
            return False
        w = w.GetParent()
    return True


def _descendants(win: wx.Window) -> List[wx.Window]:
    out = []
    for child in win.GetChildren():
        if isinstance(child, wx.TopLevelWindow):
            continue
        out.append(child)
        out += _descendants(child)
    return out


def _check_group(windows: List[wx.Window], where: str) -> None:
    keys = {}
    for w in windows:
        if isinstance(w, KEYED):
            k = mnemonic_of(w.GetLabel())
            if k:
                assert k not in keys, f"{where}: Alt+{k} used by '{keys[k]}' and '{w.GetLabel()}'"
                keys[k] = w.GetLabel()
        if isinstance(w, INTERACTIVE) and w.IsEnabled():
            # describe() sets the tooltip and the accessible description together.
            assert w.GetToolTipText(), f"{where}: no description on {type(w).__name__} " \
                                    f"'{getattr(w, 'GetLabel', lambda: '')()}'"


def _check_labels_precede_controls(panel: wx.Window, where: str) -> None:
    kids = _descendants(panel)
    for i, w in enumerate(kids):
        if isinstance(w, (wx.Choice, wx.ComboBox, wx.TextCtrl, wx.SpinCtrl, wx.ListBox,
                          wx.ListCtrl)) and not isinstance(w.GetParent(), (wx.ComboBox,
                                                                            wx.SpinCtrl)):
            prev = next((k for k in reversed(kids[:i])
                         if not isinstance(k.GetParent(), (wx.ComboBox, wx.SpinCtrl))), None)
            assert isinstance(prev, wx.StaticText), \
                f"{where}: {type(w).__name__} has no label created right before it"


MENU_KEYS = {"F", "P", "V", "H"}   # the main window's menu bar


@pytest.mark.parametrize("target", ["", "docx"])
def test_main_window(app, tmp_path, monkeypatch, target):
    from pdfmd import app_gui

    monkeypatch.setattr(app_gui, "CONFIG_PATH", tmp_path / "config.json")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "docs").mkdir()
    frame = app_gui.PdfMdFrame({}, [str(tmp_path / "a.pdf"), str(tmp_path / "docs")])
    try:
        frame._set_target(target)
        frame._update_visibility()
        shown = [w for w in _descendants(frame.panel) if _visible(w, frame.panel)]
        _check_group(shown, f"main window ({target or 'Markdown'})")
        keys = {mnemonic_of(w.GetLabel()) for w in shown if isinstance(w, KEYED)}
        assert not keys & MENU_KEYS, "main window controls must not use menu bar keys"
        # Folder settings are shown because the list has a folder; Join and
        # Keep Markdown only for formats other than Markdown.
        assert frame.subdirs_cb.IsShown()
        assert frame.join_cb.IsShown() == bool(target)
        assert frame.keep_md_cb.IsShown() == bool(target)
    finally:
        frame.Destroy()


def test_pdf_settings_window(app):
    from pdfmd.gui_pdf_settings import DEFAULT_OPTIONS, PdfSettingsDialog

    frame = wx.Frame(None)
    dlg = PdfSettingsDialog(frame, dict(DEFAULT_OPTIONS), ["Default"], "Default",
                            lambda name: dict(DEFAULT_OPTIONS))
    try:
        _check_group([w for w in _descendants(dlg) if w.IsShown()], "PDF Settings")
        assert dlg.collect()["ocr_mode"] == "auto"
    finally:
        dlg.Destroy()
        frame.Destroy()


@pytest.mark.parametrize("fmt", ["html", "docx", "epub", "pdf", "pptx", "markdown", "latex",
                                 "revealjs", "chunkedhtml", "rst", "odt", "typst"])
@pytest.mark.parametrize("advanced", [False, True])
def test_pandoc_options_window(app, fmt, advanced):
    from pdfmd.gui_pandoc import PandocOptionsDialog

    frame = wx.Frame(None)
    dlg = PandocOptionsDialog(frame, ps.PandocOptions(to_format=fmt), show_advanced=advanced)
    try:
        bottom = [w for w in dlg.GetChildren()
                  if w is not dlg.book and not isinstance(w, wx.TopLevelWindow)]
        for i in range(dlg.book.GetPageCount()):
            panel = dlg.book.GetPage(i)
            where = f"{fmt}, page '{dlg.book.GetPageText(i)}'"
            shown = [w for w in _descendants(panel) if _visible(w, panel)]
            assert any(isinstance(w, INTERACTIVE) for w in shown), f"{where} is empty"
            _check_group(shown + [w for w in bottom if w.IsShown()], where)
            _check_labels_precede_controls(panel, where)
    finally:
        dlg.Destroy()
        frame.Destroy()
