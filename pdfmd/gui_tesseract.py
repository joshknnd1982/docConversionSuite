"""Accessible Tesseract OCR manager for Document Conversion Suite.

Opened from File > Tesseract OCR (Ctrl+T) or Help > Check for Tesseract
Updates. Shows the installed version and languages, checks for updates,
installs or updates Tesseract, and downloads more OCR languages.

All controls are native, labelled, described and have Alt+letter keys.
Long operations run in the background and are announced.
"""
from __future__ import annotations

import subprocess
import threading
from typing import List, Optional

import wx

from . import tesseract_support as ts
from .gui_a11y import Announcer, MnemonicHandler, describe


class TesseractDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, announcer: Optional[Announcer] = None,
                 check_now: bool = False) -> None:
        super().__init__(parent, title="Tesseract OCR", size=(700, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.announcer = announcer or Announcer()
        self.release: Optional[ts.Release] = None
        self.release_error: Optional[str] = None
        self._busy = False
        self._build()
        MnemonicHandler(self)
        self.SetEscapeId(wx.ID_CLOSE)
        self.refresh()
        self.CentreOnParent()
        wx.CallAfter(self.status.SetFocus)
        if check_now:
            wx.CallAfter(self._check_updates)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        pad = 6
        s = wx.BoxSizer(wx.VERTICAL)

        s.Add(wx.StaticText(self, label="&Status:"), 0, wx.LEFT | wx.TOP, 8)
        self.status = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 120))
        describe(self.status, "Tesseract version, location, available update and languages. "
                              "Read it with the arrow keys.")
        s.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.check_btn = wx.Button(self, label="Check for &Updates")
        describe(self.check_btn, "Look online for the latest Windows build of Tesseract.")
        self.install_btn = wx.Button(self, label="&Install Tesseract")
        describe(self.install_btn,
                 "Install or update Tesseract. Uses the Windows Package Manager when available, "
                 "otherwise downloads the official installer from GitHub and starts it.")
        row.Add(self.check_btn, 0, wx.RIGHT, pad)
        row.Add(self.install_btn, 0)
        s.Add(row, 0, wx.LEFT | wx.RIGHT, 8)

        s.Add(wx.StaticText(self, label="Installed &languages:"), 0, wx.LEFT | wx.TOP, 8)
        self.lang_list = wx.ListBox(self, size=(-1, 120))
        describe(self.lang_list, "OCR languages Tesseract can read now.")
        s.Add(self.lang_list, 1, wx.EXPAND | wx.ALL, 8)

        grid = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)
        grid.Add(wx.StaticText(self, label="&Add language:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.add_choice = wx.Choice(self)
        describe(self.add_choice, "A language to download for OCR. Already installed languages "
                                  "are not listed.")
        grid.Add(self.add_choice, 1, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="&Quality:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.quality = wx.Choice(self, choices=["Fast (smaller download, recommended)",
                                                "Best (most accurate, larger and slower)"])
        self.quality.SetSelection(0)
        describe(self.quality, "Which trained data to download for the language.")
        grid.Add(self.quality, 1, wx.EXPAND)
        s.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.download_btn = wx.Button(self, label="&Download Language")
        describe(self.download_btn, "Download the selected language so OCR can read it.")
        row2.Add(self.download_btn, 0)
        s.Add(row2, 0, wx.ALL, 8)

        s.Add(wx.StaticText(self, label="Progress:"), 0, wx.LEFT, 8)
        self.gauge = wx.Gauge(self, range=100)
        s.Add(self.gauge, 0, wx.EXPAND | wx.ALL, 8)

        self.close_btn = wx.Button(self, wx.ID_CLOSE, "&Close")
        describe(self.close_btn, "Close this window. Shortcut: Escape.")
        s.Add(self.close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(s)

        self.check_btn.Bind(wx.EVT_BUTTON, lambda e: self._check_updates())
        self.install_btn.Bind(wx.EVT_BUTTON, lambda e: self._install())
        self.download_btn.Bind(wx.EVT_BUTTON, lambda e: self._download_language())
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self._close())
        self.Bind(wx.EVT_CLOSE, lambda e: self._close())

    # ---------------------------------------------------------------- status
    def refresh(self) -> None:
        exe = ts.configure()
        version = ts.installed_version(exe) if exe else None
        langs = ts.list_languages(exe) if exe else []
        lines: List[str] = []
        if exe:
            lines.append(f"Tesseract {version or '(unknown version)'} is installed.")
            lines.append(f"Location: {exe}")
        else:
            lines.append("Tesseract is not installed. Scanned PDFs can't be read until it is. "
                         "Press Install Tesseract (Alt+I).")
        if self.release:
            if not exe:
                lines.append(f"Available to install: Tesseract {self.release.version}.")
            elif ts.is_newer(self.release.version, version):
                lines.append(f"Update available: Tesseract {self.release.version}. "
                             "Press Install Update (Alt+I).")
            else:
                lines.append(f"You have the latest Windows build ({self.release.version}).")
        elif self.release_error:
            lines.append(f"Could not check for updates: {self.release_error}")
        if exe:
            lines.append(f"{len(langs)} OCR languages installed. Languages you add are stored in "
                         f"{ts.user_tessdata_dir()}.")
        self.status.SetValue("\r\n".join(lines))

        self.lang_list.Set([ts.language_label(c) for c in langs] or ["No languages found"])
        self.available = [c for c, _ in ts.LANGUAGES if c not in langs]
        self.add_choice.Set([ts.language_label(c) for c in self.available])
        if self.available:
            self.add_choice.SetSelection(0)

        if not exe:
            label = "&Install Tesseract"
        elif self.release and ts.is_newer(self.release.version, version):
            label = f"&Install Update (Tesseract {self.release.version})"
        else:
            label = "Re&install Tesseract"
        self.install_btn.SetLabel(label)
        self._enable(not self._busy)
        self.download_btn.Enable(bool(exe) and bool(self.available) and not self._busy)
        self.Layout()
        self.installed_version = version
        self.exe = exe

    def _enable(self, on: bool) -> None:
        focus = wx.Window.FindFocus()
        for b in (self.check_btn, self.install_btn, self.download_btn):
            if not on and focus is b:
                self.status.SetFocus()
            b.Enable(on)

    def _say(self, text: str) -> None:
        self.announcer.speak(text, interrupt=True)

    # ---------------------------------------------------------------- actions
    def _check_updates(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._enable(False)
        self._say("Checking for Tesseract updates.")

        def work():
            try:
                rel, err = ts.latest_release(), None
            except Exception as e:  # noqa: BLE001
                rel, err = None, str(e)
            wx.CallAfter(self._checked, rel, err)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, rel, err) -> None:
        if not self:
            return
        self._busy = False
        self.release, self.release_error = rel, err
        self.refresh()
        if err:
            self._say("Could not check for updates.")
        elif not self.exe:
            self._say(f"Tesseract {rel.version} is available to install.")
        elif ts.is_newer(rel.version, self.installed_version):
            self._say(f"Update available: Tesseract {rel.version}.")
        else:
            self._say("You have the latest Tesseract.")
        self.status.SetFocus()

    def _install(self) -> None:
        if self._busy:
            return
        update = bool(self.exe)
        if ts.winget_available():
            msg = ("A console window will open and install Tesseract OCR with the Windows "
                   "Package Manager (winget). Windows may ask for permission. Continue?")
            if wx.MessageBox(msg, "Install Tesseract", wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
                             self) != wx.YES:
                return
            cmd = ts.winget_command(update=update)
            try:
                subprocess.call(["cmd", "/c"] + cmd + ["&", "echo.", "&", "echo", "Press", "any", "key",
                                                       "to", "return.", "&", "pause", ">nul"],
                                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            except Exception as e:  # noqa: BLE001
                wx.MessageBox(f"Could not start winget:\n{e}", "Install Tesseract",
                              wx.OK | wx.ICON_ERROR, self)
            self._after_install()
            return
        # No winget: download the official installer and run it.
        self._busy = True
        self._enable(False)
        self._say("Downloading the Tesseract installer.")

        def work():
            try:
                rel = self.release or ts.latest_release()
                path = ts.download_installer(rel, progress=self._progress)
                wx.CallAfter(self._run_installer, path)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._failed, "Could not download Tesseract", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done: int, total: int) -> None:
        if total:
            wx.CallAfter(self.gauge.SetValue, int(done * 100 / total))

    def _run_installer(self, path) -> None:
        self._busy = False
        self._say("Download complete. Starting the Tesseract installer.")
        try:
            subprocess.call([str(path)])
        except OSError as e:
            # Installer needs elevation: let Windows show the permission prompt.
            try:
                import os
                os.startfile(str(path))  # type: ignore[attr-defined]
                wx.MessageBox("Finish the Tesseract installer, then press OK.", "Install Tesseract",
                              wx.OK | wx.ICON_INFORMATION, self)
            except Exception:
                self._failed("Could not start the installer", str(e))
                return
        self._after_install()

    def _after_install(self) -> None:
        self._busy = False
        self.gauge.SetValue(0)
        self.refresh()
        if self.exe:
            self._say(f"Tesseract {self.installed_version or ''} is ready.")
        else:
            self._say("Tesseract was not found. If you just installed it, restart the program.")
        self.status.SetFocus()

    def _download_language(self) -> None:
        sel = self.add_choice.GetSelection()
        if self._busy or sel < 0 or not self.available:
            return
        code = self.available[sel]
        quality = "best" if self.quality.GetSelection() == 1 else "fast"
        self._busy = True
        self._enable(False)
        self._say(f"Downloading {ts.language_label(code)}.")

        def work():
            try:
                ts.add_language(code, quality, self.exe, progress=self._progress)
                wx.CallAfter(self._language_done, code)
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._failed, "Could not download the language", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _language_done(self, code: str) -> None:
        self._busy = False
        self.gauge.SetValue(0)
        self.refresh()
        self._say(f"{ts.language_label(code)} added. Type {code} in OCR language to use it.")
        self.add_choice.SetFocus()

    def _failed(self, title: str, err: str) -> None:
        if not self:
            return
        self._busy = False
        self.gauge.SetValue(0)
        self.refresh()
        wx.MessageBox(f"{title}:\n\n{err}", title, wx.OK | wx.ICON_ERROR, self)

    def _close(self) -> None:
        if self._busy:
            self._say("Please wait for the current download to finish.")
            return
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Destroy()
