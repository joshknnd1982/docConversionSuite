"""Accessibility helpers shared by pdfmd's wxPython windows.

* ``Announcer``          speaks status messages through the running screen reader.
* ``describe``           gives a control a tooltip and an accessible description.
* ``MnemonicHandler``    makes every Alt+letter access key work anywhere in a
                         window (Windows only handles them inside the group
                         box that has focus).
"""
from __future__ import annotations

import re
from typing import List, Optional

import wx


class Announcer:
    """Speak short messages through the running screen reader.

    Uses accessible_output2 when available. Only real screen readers are
    used (NVDA, JAWS, System Access, Dolphin, ZoomText, ...); it never falls
    back to SAPI, so people who don't use a screen reader hear nothing.
    """

    def __init__(self) -> None:
        self.enabled = True
        self._out = None
        try:
            from accessible_output2.outputs import auto  # type: ignore

            out = auto.Auto()
            out.outputs = [
                o for o in out.outputs if type(o).__name__ not in ("SAPI5", "SAPI4")
            ]
            self._out = out
        except Exception:
            self._out = None

    def describe(self) -> str:
        """Name of the screen reader announcements go to, for the log."""
        if self._out is None:
            return "not available (speech library missing)"
        try:
            out = self._out.get_first_available_output()
        except Exception:
            out = None
        if out is None:
            return "no running screen reader detected"
        names = {"NVDA": "NVDA", "Jaws": "JAWS", "SystemAccess": "System Access",
                 "Dolphin": "Dolphin", "PCTalker": "PC-Talker", "ZDSR": "ZDSR"}
        cls = type(out).__name__
        return names.get(cls, cls)

    def speak(self, text: str, interrupt: bool = False) -> None:
        if not self.enabled or self._out is None or not text:
            return
        try:
            self._out.speak(text, interrupt=interrupt)
        except Exception:
            pass


class DescribedAccessible(wx.Accessible):
    """Adds an accessible description (help text) to a native control.

    Name, role, value and state still come from the native control, because
    methods that aren't implemented here fall back to the standard Windows
    implementation.
    """

    def __init__(self, win: wx.Window, description: str) -> None:
        super().__init__(win)
        self._description = description

    def GetDescription(self, childId):  # noqa: N802 (wx naming)
        if childId == 0:
            return (wx.ACC_OK, self._description)
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetHelpText(self, childId):  # noqa: N802
        if childId == 0:
            return (wx.ACC_OK, self._description)
        return (wx.ACC_NOT_IMPLEMENTED, "")


_keep_alive: List[wx.Accessible] = []


def describe(ctrl: wx.Window, text: str) -> None:
    """Tooltip for mouse users + accessible description for screen readers."""
    ctrl.SetToolTip(text)
    ctrl.SetHelpText(text)
    try:
        acc = DescribedAccessible(ctrl, text)
        ctrl.SetAccessible(acc)
        _keep_alive.append(acc)
    except Exception:
        pass


_MNEMONIC = re.compile(r"&([^&])")


def mnemonic_of(label: str) -> Optional[str]:
    m = _MNEMONIC.search(label.replace("&&", ""))
    return m.group(1).upper() if m else None


class MnemonicHandler:
    """Window-wide Alt+letter access keys.

    Windows resolves access keys only among the controls of the group box
    that currently has focus, so Alt+M would do nothing while you are in a
    different group. This handler looks at every label, button and check box
    in the window:

    * a label's access key moves focus to the control that follows it,
    * a button's access key presses the button,
    * a check box's access key toggles it and moves focus to it.

    Keys that no control uses are passed on, so the menu bar (Alt+F etc.)
    keeps working.
    """

    def __init__(self, top: wx.TopLevelWindow) -> None:
        self.top = top
        top.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    @staticmethod
    def _walk(win: wx.Window, out: List[wx.Window]) -> None:
        for child in win.GetChildren():
            if isinstance(child, wx.TopLevelWindow):
                continue
            out.append(child)
            MnemonicHandler._walk(child, out)

    def _usable(self, w: wx.Window) -> bool:
        return w.IsShownOnScreen() and w.IsEnabled()

    def handle(self, key: str) -> bool:
        flat: List[wx.Window] = []
        self._walk(self.top, flat)
        for i, w in enumerate(flat):
            if not isinstance(w, (wx.StaticText, wx.Button, wx.CheckBox, wx.RadioButton)):
                continue
            if mnemonic_of(w.GetLabel()) != key or not w.IsShownOnScreen():
                continue
            if isinstance(w, wx.StaticText):
                for target in flat[i + 1:]:
                    if isinstance(target, (wx.StaticText, wx.StaticBox)):
                        continue
                    if self._usable(target) and target.AcceptsFocus():
                        target.SetFocus()
                        if isinstance(target, wx.TextCtrl) and not target.IsMultiLine():
                            target.SelectAll()
                        return True
                    if self._usable(target) and target.GetChildren():
                        # Composite control (e.g. combo box with an edit child)
                        target.SetFocus()
                        return True
                return False
            if not self._usable(w):
                return True  # the key belongs to a disabled control: swallow it
            if isinstance(w, wx.Button):
                w.SetFocus()
                evt = wx.CommandEvent(wx.wxEVT_BUTTON, w.GetId())
                evt.SetEventObject(w)
                w.GetEventHandler().ProcessEvent(evt)
                return True
            if isinstance(w, wx.CheckBox):
                w.SetFocus()
                w.SetValue(not w.GetValue())
                evt = wx.CommandEvent(wx.wxEVT_CHECKBOX, w.GetId())
                evt.SetEventObject(w)
                evt.SetInt(int(w.GetValue()))
                w.GetEventHandler().ProcessEvent(evt)
                return True
            if isinstance(w, wx.RadioButton):
                w.SetFocus()
                w.SetValue(True)
                return True
        return False

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.AltDown() and not event.ControlDown() and not event.ShiftDown():
            code = event.GetKeyCode()
            if 0 < code < 256:
                ch = chr(code).upper()
                if ch.isalnum() and self.handle(ch):
                    return
        event.Skip()
