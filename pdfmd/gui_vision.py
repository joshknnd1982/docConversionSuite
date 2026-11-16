"""Accessible windows for the local AI vision model.

* ``VisionDialog`` (File > Vision Model, Ctrl+I): shows the vision engine,
  the installed models and the graphics processors; chooses the processor
  (automatic, graphics processor, a particular graphics processor, or CPU)
  and the model; checks for updates and installs them with one button;
  describes a test picture.
* ``PhotoAlbumDialog`` (File > Describe a Folder of Photos, Ctrl+D):
  describes every photo in a folder and saves an accessible web page or
  Markdown file.

Every control is native, labelled, described and has an Alt+letter key.
Long operations run in the background, are announced through the screen
reader, and can be cancelled.
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import wx

from . import album, vision
from .gui_a11y import Announcer, MnemonicHandler, describe


def _gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


class VisionDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: vision.VisionSettings,
                 announcer: Optional[Announcer] = None, check_now: bool = False) -> None:
        super().__init__(parent, title="Vision Model (Picture Descriptions)", size=(760, 680),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = vision.VisionSettings(**{**settings.__dict__})
        self.announcer = announcer or Announcer()
        self.catalog = vision.builtin_catalog()
        self.catalog_online = False
        self.catalog_error = ""
        self.plan: Optional[vision.UpdatePlan] = None
        self._busy = False
        self._cancel = threading.Event()
        self.devices: List[vision.Device] = []
        self._build()
        MnemonicHandler(self)
        self.SetEscapeId(wx.ID_CLOSE)
        self.refresh(load_devices=True)
        self.CentreOnParent()
        wx.CallAfter(self.status.SetFocus)
        if check_now:
            wx.CallAfter(self._check_updates)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        pad = 6
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.StaticText(self, label="&Status:"), 0, wx.LEFT | wx.TOP, 8)
        self.status = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 170))
        describe(self.status, "The vision engine, the model in use, the graphics processors found "
                              "and any available update. Read it with the arrow keys.")
        s.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)

        self.enable_cb = wx.CheckBox(self, label="&Describe pictures in documents (on by default)")
        describe(self.enable_cb,
                 "When on, photos, charts, graphs, maps and diagrams in converted documents are "
                 "described by the local vision model. Pictures that are mostly text are read "
                 "with OCR instead. Nothing leaves your computer.")
        s.Add(self.enable_cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        grid = wx.FlexGridSizer(cols=2, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)
        grid.Add(wx.StaticText(self, label="&Processor:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.device_choice = wx.Choice(self)
        describe(self.device_choice,
                 "Where the model runs. Automatic uses an NVIDIA card with CUDA when the CUDA "
                 "engine is installed, otherwise a graphics card with Vulkan, otherwise the CPU. "
                 "NVIDIA GPU with CUDA is offered when an NVIDIA card is found and is the fastest "
                 "on those cards. Any GPU with Vulkan works with NVIDIA, AMD and Intel graphics, "
                 "including integrated graphics. You can also pick one particular graphics "
                 "processor, or CPU only, which works on every computer but is slower.")
        grid.Add(self.device_choice, 1, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="&Model:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.model_choice = wx.Choice(self)
        describe(self.model_choice,
                 "The vision model. Models that aren't installed yet are downloaded when you "
                 "press Update Vision Model.")
        grid.Add(self.model_choice, 1, wx.EXPAND)
        s.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        s.Add(wx.StaticText(self, label="Model &information:"), 0, wx.LEFT | wx.TOP, 8)
        self.model_info = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 70))
        describe(self.model_info, "About the selected model: size, memory needed and licence.")
        s.Add(self.model_info, 0, wx.EXPAND | wx.ALL, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.check_btn = wx.Button(self, label="Check for &Updates")
        describe(self.check_btn, "Look online for a newer vision engine or model. Only the small "
                                 "model list is downloaded.")
        self.update_btn = wx.Button(self, label="Update &Vision Model")
        describe(self.update_btn,
                 "Download and install the newest vision engine and the selected model. Every "
                 "file is checked against its published SHA-256 checksum before it is used.")
        self.test_btn = wx.Button(self, label="&Test on a Picture...")
        describe(self.test_btn, "Choose a picture and hear the model describe it.")
        self.remove_btn = wx.Button(self, label="&Remove Downloaded Model")
        describe(self.remove_btn, "Delete the selected model if it was downloaded, to free disk "
                                  "space. The built-in model can't be removed.")
        for b in (self.check_btn, self.update_btn, self.test_btn, self.remove_btn):
            row.Add(b, 0, wx.RIGHT, pad)
        s.Add(row, 0, wx.LEFT | wx.RIGHT, 8)

        s.Add(wx.StaticText(self, label="Progress:"), 0, wx.LEFT | wx.TOP, 8)
        self.gauge = wx.Gauge(self, range=1000)
        s.Add(self.gauge, 0, wx.EXPAND | wx.ALL, 8)
        s.Add(wx.StaticText(self, label="&Log:"), 0, wx.LEFT, 8)
        self.log = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 90))
        describe(self.log, "Messages from downloads and tests.")
        s.Add(self.log, 1, wx.EXPAND | wx.ALL, 8)

        brow = wx.BoxSizer(wx.HORIZONTAL)
        self.stop_btn = wx.Button(self, label="Stop Do&wnload")
        describe(self.stop_btn, "Stop the running download.")
        self.close_btn = wx.Button(self, wx.ID_CLOSE, "&Close")
        describe(self.close_btn, "Save these settings and close this window. Shortcut: Escape.")
        brow.Add(self.stop_btn, 0, wx.RIGHT, pad)
        brow.Add(self.close_btn, 0)
        s.Add(brow, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(s)

        self.check_btn.Bind(wx.EVT_BUTTON, lambda e: self._check_updates())
        self.update_btn.Bind(wx.EVT_BUTTON, lambda e: self._update())
        self.test_btn.Bind(wx.EVT_BUTTON, lambda e: self._test())
        self.remove_btn.Bind(wx.EVT_BUTTON, lambda e: self._remove())
        self.stop_btn.Bind(wx.EVT_BUTTON, lambda e: self._stop())
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self._close())
        self.Bind(wx.EVT_CLOSE, lambda e: self._close())
        self.model_choice.Bind(wx.EVT_CHOICE, lambda e: self._on_model())
        self.device_choice.Bind(wx.EVT_CHOICE, lambda e: self._on_device())

    # ---------------------------------------------------------------- status
    def _device_options(self) -> List[Tuple[str, str]]:
        opts: List[Tuple[str, str]] = []
        nvidia = vision.nvidia_gpus()
        for code, label in vision.DEVICES:
            if code == "cuda":
                if not nvidia:
                    continue  # offered only when an NVIDIA card is detected
                if vision.find_cuda_runtime():
                    label += " (installed)"
                elif vision.cuda_variant():
                    label += " (engine download about 710 MB: press Download Vision Model)"
                else:
                    label += " (needs a newer NVIDIA driver)"
            opts.append((code, label))
        for d in self.devices:
            opts.insert(len(opts) - 1, (f"dev:{d.name}", f"Only {d.label()}"))
        return opts

    def _model_options(self) -> List[Tuple[str, str]]:
        installed = vision.installed_models()
        out: List[Tuple[str, str]] = []
        rec = self.catalog.get("recommended", "")
        for m in self.catalog.get("models", []):
            size = sum(int(f.get("size", 0)) for f in m["files"].values())
            mark = "installed" if m["id"] in installed else f"download {_gb(size)}"
            extra = ", recommended" if m["id"] == rec else ""
            out.append((m["id"], f"{m['name']} ({mark}{extra})"))
        for mid, m in installed.items():
            if mid not in [o[0] for o in out]:
                out.append((mid, f"{m.name} (installed)"))
        return out

    def refresh(self, load_devices: bool = False) -> None:
        if load_devices:
            self.devices = vision.list_devices()
        rt = vision.find_runtime()
        installed = vision.installed_models()
        model = vision.resolve_model(self.settings.model_id)
        lines: List[str] = []
        if rt:
            where = {"bundled": "built in", "user": "updated copy", "path": "on the PATH",
                     "environment": "from PDFMD_LLAMA_SERVER"}.get(rt.source, rt.source)
            lines.append(f"Vision engine: llama.cpp {rt.build or ''} ({where}).".replace("  ", " "))
        else:
            lines.append("The vision engine is not installed. Press Update Vision Model (Alt+V).")
        if model:
            lines.append(f"Model in use: {model.name}, {_gb(model.size)} "
                         f"({'built in' if model.source == 'bundled' else 'downloaded'}).")
        else:
            lines.append("No vision model is installed. Press Update Vision Model (Alt+V).")
        if self.devices:
            lines.append("Graphics processors (Vulkan): "
                         + "; ".join(d.label() for d in self.devices) + ".")
        elif rt:
            lines.append("No graphics processor was found; the CPU is used.")
        nvidia = vision.nvidia_gpus()
        if nvidia:
            cuda = vision.find_cuda_runtime()
            g = nvidia[0]
            if cuda:
                state = "the CUDA engine is installed"
            elif vision.cuda_variant():
                state = ("the CUDA engine is not installed; choose NVIDIA GPU with CUDA and press "
                         "Download Vision Model (Alt+V) to get it")
            else:
                state = "its driver is too old for CUDA; update it from nvidia.com or use Vulkan"
            lines.append(f"NVIDIA card: {g.name}, driver {g.driver}; {state}.")
        if rt and model:
            _, dev, note = vision.choose_engine(self.settings, model)
            lines.append("With the current choice the model runs on: "
                         + (dev.label() if dev else "the CPU") + "." + (f" {note}" if note else ""))
        if self.plan is not None:
            if self.plan.needed:
                lines.append("Update available: " + "; ".join(self.plan.notes)
                             + f". Download size {self.plan.download_bytes / 1e6:.0f} MB. "
                             "Press Update Vision Model (Alt+V).")
            else:
                lines.append("The vision engine and model are up to date.")
        if self.catalog_error:
            lines.append(f"Could not check for updates: {self.catalog_error}")
        lines.append(f"Downloaded models are stored in {vision.user_dir()}.")
        self.status.SetValue("\r\n".join(lines))

        self.enable_cb.SetValue(self.settings.enabled)
        dopts = self._device_options()
        self.device_choice.Set([label for _, label in dopts])
        codes = [c for c, _ in dopts]
        self.device_choice.SetSelection(codes.index(self.settings.device)
                                        if self.settings.device in codes else 0)
        mopts = self._model_options()
        self.model_choice.Set([label for _, label in mopts])
        mcodes = [c for c, _ in mopts]
        current = self.settings.model_id or (model.id if model else self.catalog.get("recommended", ""))
        if current in mcodes:
            self.model_choice.SetSelection(mcodes.index(current))
        elif mcodes:
            self.model_choice.SetSelection(0)
        self._show_model_info()
        self._installed = installed
        self._enable()
        self.Layout()

    def _selected_model(self) -> str:
        mopts = self._model_options()
        sel = self.model_choice.GetSelection()
        return mopts[sel][0] if 0 <= sel < len(mopts) else ""

    def _show_model_info(self) -> None:
        mid = self._selected_model()
        entry = vision.catalog_model(self.catalog, mid)
        if entry:
            size = sum(int(f.get("size", 0)) for f in entry["files"].values())
            text = (f"{entry.get('description', '')}\r\nDownload {_gb(size)}; needs about "
                    f"{entry.get('ram_gb', '?')} GB of memory. Licence: {entry.get('license', '?')}. "
                    f"Based on {entry.get('base', '?')}.")
        else:
            m = vision.installed_models().get(mid)
            text = f"{m.name}, {_gb(m.size)}." if m else ""
        self.model_info.SetValue(text)

    def _enable(self) -> None:
        busy = self._busy
        focus = wx.Window.FindFocus()
        mid = self._selected_model()
        installed = vision.installed_models()
        targets = {
            self.check_btn: not busy,
            self.update_btn: not busy,
            self.test_btn: not busy and vision.available(self.settings),
            self.remove_btn: not busy and mid in installed and installed[mid].source == "user",
            self.stop_btn: busy,
            self.device_choice: not busy,
            self.model_choice: not busy,
        }
        if focus in targets and not targets[focus]:
            (self.stop_btn if busy else self.status).SetFocus()
        for ctrl, on in targets.items():
            ctrl.Enable(on)
        label = "Update &Vision Model"
        cuda_missing = (self.settings.device == "cuda" and bool(vision.cuda_variant())
                        and vision.find_cuda_runtime() is None)
        if not vision.find_runtime() or mid not in installed or cuda_missing:
            label = "Download &Vision Model"
        self.update_btn.SetLabel(label)

    def _say(self, text: str) -> None:
        self.announcer.speak(text, interrupt=True)

    def _log(self, msg: str) -> None:
        def add():
            if self:
                self.log.AppendText(str(msg) + "\n")
        wx.CallAfter(add)

    def _progress(self, done: int, total: int) -> None:
        if total:
            wx.CallAfter(self._set_gauge, int(done * 1000 / total))

    def _set_gauge(self, value: int) -> None:
        if not self:
            return
        old = self.gauge.GetValue()
        self.gauge.SetValue(max(0, min(1000, value)))
        if value // 250 > old // 250 and 0 < value < 1000:
            self._say(f"{value // 10} percent")

    # ---------------------------------------------------------------- events
    def _on_model(self) -> None:
        self.settings.model_id = self._selected_model()
        self.plan = (vision.plan_update(self.catalog, self.settings.model_id, self.settings.device)
                     if self.catalog_online else None)
        self.refresh()

    def _on_device(self) -> None:
        dopts = self._device_options()
        sel = self.device_choice.GetSelection()
        if 0 <= sel < len(dopts):
            self.settings.device = dopts[sel][0]
            vision.shutdown()  # the next description starts on the new processor
        if self.catalog_online:
            self.plan = vision.plan_update(self.catalog, self._selected_model(), self.settings.device)
        self.refresh()
        if self.settings.device == "cuda" and vision.find_cuda_runtime() is None \
                and vision.cuda_variant():
            self._say("The CUDA engine isn't installed yet. Press Download Vision Model, Alt+V, "
                      "to download it, about 710 megabytes.")

    def _check_updates(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._enable()
        self._say("Checking for vision model updates.")

        def work():
            try:
                cat, err = vision.fetch_catalog(), ""
            except Exception as e:  # noqa: BLE001
                cat, err = None, str(e)
            wx.CallAfter(self._checked, cat, err)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, cat, err: str) -> None:
        if not self:
            return
        self._busy = False
        self.catalog_error = err
        if cat:
            self.catalog, self.catalog_online = cat, True
            self.plan = vision.plan_update(cat, self._selected_model(), self.settings.device)
        self.refresh()
        if err:
            self._say("Could not check for updates.")
        elif self.plan and self.plan.needed:
            self._say("Update available. " + ". ".join(self.plan.notes))
        else:
            self._say("The vision model is up to date.")
        self.status.SetFocus()

    def _update(self) -> None:
        if self._busy:
            return
        mid = self._selected_model()
        catalog = self.catalog
        device = self.settings.device
        plan = vision.plan_update(catalog, mid, device)
        if not plan.needed:
            if self.catalog_online:
                self._say("The vision engine and model are already up to date.")
                wx.MessageBox("The vision engine and the selected model are up to date.",
                              "Vision Model", wx.OK | wx.ICON_INFORMATION, self)
                return
            # Check online first, then update.
        msg = ("Download the newest vision engine and model from the internet? "
               "Files come from github.com (llama.cpp and, for CUDA, NVIDIA's CUDA runtime) and "
               "huggingface.co (the model), and each is checked against its published checksum.")
        if plan.needed:
            msg = ("Download and install:\n\n" + "\n".join(plan.notes)
                   + f"\n\nDownload size: {plan.download_bytes / 1e6:.0f} MB.\n\n" + msg)
        if wx.MessageBox(msg, "Update Vision Model", wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
                         self) != wx.YES:
            return
        self._busy = True
        self._cancel.clear()
        self._enable()
        self._say("Updating the vision model.")

        def work():
            try:
                cat = catalog
                try:
                    cat = vision.fetch_catalog()
                except Exception as e:  # noqa: BLE001
                    self._log(f"Could not read the online model list ({e}); using the built-in one.")
                result = vision.run_update(mid, cat, progress=self._progress, cancel=self._cancel,
                                           log_cb=self._log, device=device)
                wx.CallAfter(self._updated, cat, result, "")
            except vision.Cancelled:
                wx.CallAfter(self._updated, None, None, "cancelled")
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._updated, None, None, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _updated(self, cat, result, err: str) -> None:
        if not self:
            return
        self._busy = False
        self.gauge.SetValue(0)
        if cat:
            self.catalog, self.catalog_online = cat, True
            self.plan = vision.plan_update(cat, self._selected_model(), self.settings.device)
        if err == "cancelled":
            self._say("Update stopped.")
            self._log("Update stopped.")
        elif err:
            self._log(f"Update failed: {err}")
            self.refresh()
            wx.MessageBox(f"The vision model could not be updated:\n\n{err}", "Update Vision Model",
                          wx.OK | wx.ICON_ERROR, self)
            return
        else:
            done = "Nothing needed updating." if not result.needed else "Update installed."
            self._log(done)
            self._say(done + " The vision model is ready.")
        self.settings.model_id = self._selected_model()
        self.refresh()
        self.status.SetFocus()

    def _test(self) -> None:
        if self._busy:
            return
        with wx.FileDialog(self, "Choose a picture to describe",
                           wildcard="Pictures|*.jpg;*.jpeg;*.png;*.gif;*.bmp;*.tif;*.tiff;*.webp;*.heic|"
                                    "All files (*.*)|*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self._busy = True
        self._enable()
        self._say("Describing the picture. Loading the model can take a moment.")
        settings = vision.VisionSettings(**{**self.settings.__dict__})

        def work():
            try:
                engine = vision.get_engine(settings, log_cb=self._log)
                d = engine.describe(path, "photo", settings.lang)
                wx.CallAfter(self._tested, path, d, engine.device_label, "")
            except Exception as e:  # noqa: BLE001
                wx.CallAfter(self._tested, path, None, "", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _tested(self, path: str, d, device: str, err: str) -> None:
        if not self:
            return
        self._busy = False
        self._enable()
        if err:
            self._log(f"Could not describe {Path(path).name}: {err}")
            wx.MessageBox(f"The picture could not be described:\n\n{err}", "Test on a Picture",
                          wx.OK | wx.ICON_ERROR, self)
            return
        text = (f"{d.title}. " if d.title else "") + d.text
        self._log(f"{Path(path).name} ({d.seconds:.1f} seconds on {device}): {text}")
        self._say(text)
        self.log.SetFocus()
        self.log.SetInsertionPointEnd()

    def _remove(self) -> None:
        mid = self._selected_model()
        m = vision.installed_models().get(mid)
        if not m or m.source != "user":
            return
        if wx.MessageBox(f"Delete the downloaded model {m.name} ({_gb(m.size)})? You can "
                         "download it again later.", "Remove Downloaded Model",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        vision.remove_user_model(mid)
        self._say(f"{m.name} removed.")
        self.refresh()

    def _stop(self) -> None:
        if self._busy:
            self._cancel.set()
            self._say("Stopping.")

    def _close(self) -> None:
        if self._busy:
            self._say("Please wait, or press Stop first.")
            return
        self.settings.enabled = self.enable_cb.GetValue()
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Destroy()


class PhotoAlbumDialog(wx.Dialog):
    """Describe a folder of photos into an accessible album."""

    def __init__(self, parent: wx.Window, settings: vision.VisionSettings,
                 announcer: Optional[Announcer] = None, folder: str = "",
                 fmt: str = "html") -> None:
        super().__init__(parent, title="Describe a Folder of Photos", size=(760, 620),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = vision.VisionSettings(**{**settings.__dict__})
        self.settings.enabled = True
        self.announcer = announcer or Announcer()
        self._worker: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._out_auto = True
        self.last_output: Optional[Path] = None
        self._last_pct = 0
        self._build()
        MnemonicHandler(self)
        self.SetEscapeId(wx.ID_CLOSE)
        self.format_choice.SetSelection(1 if fmt == "markdown" else 0)
        if folder:
            self.folder_text.SetValue(folder)
            self._suggest_output()
        self._update()
        self.CentreOnParent()
        wx.CallAfter(self.folder_text.SetFocus)

    def _build(self) -> None:
        pad = 6
        s = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(self, label=(
            "Each photo is described by the vision model on this computer: a short title and a "
            "few sentences about who and what is in it, the place, the time of day and the mood. "
            "The descriptions are saved in one page, in the order the photos were taken."))
        intro.Wrap(700)
        s.Add(intro, 0, wx.ALL, 8)

        grid = wx.FlexGridSizer(cols=3, vgap=pad, hgap=pad)
        grid.AddGrowableCol(1, 1)
        grid.Add(wx.StaticText(self, label="Photo &folder:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.folder_text = wx.TextCtrl(self)
        describe(self.folder_text, "The folder with your photos. JPEG, PNG, HEIC, WebP, TIFF, GIF "
                                   "and BMP pictures are described.")
        grid.Add(self.folder_text, 1, wx.EXPAND)
        self.browse_btn = wx.Button(self, label="&Browse...")
        describe(self.browse_btn, "Choose the photo folder.")
        grid.Add(self.browse_btn, 0)

        grid.Add(wx.StaticText(self, label="Save &as:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.format_choice = wx.Choice(self, choices=[label for _, label in album.FORMATS])
        describe(self.format_choice, "Web page: opens in your browser, with a heading for each "
                                     "photo and the photos shown. Markdown: a plain text file that "
                                     "any editor can open.")
        grid.Add(self.format_choice, 1, wx.EXPAND)
        grid.Add((0, 0))

        grid.Add(wx.StaticText(self, label="&Output file:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.out_text = wx.TextCtrl(self)
        describe(self.out_text, "Where the descriptions are saved. Filled in automatically; keep it "
                                "in or near the photo folder so the photos show in the page.")
        grid.Add(self.out_text, 1, wx.EXPAND)
        self.out_btn = wx.Button(self, label="C&hoose File...")
        describe(self.out_btn, "Choose where to save the descriptions.")
        grid.Add(self.out_btn, 0)
        s.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.recursive_cb = wx.CheckBox(self, label="Include photos in s&ubfolders")
        describe(self.recursive_cb, "Also describe the photos in folders inside the photo folder.")
        s.Add(self.recursive_cb, 0, wx.ALL, 8)
        self.open_cb = wx.CheckBox(self, label="Open the page &when finished")
        self.open_cb.SetValue(True)
        describe(self.open_cb, "Open the saved page when all photos are described.")
        s.Add(self.open_cb, 0, wx.LEFT | wx.RIGHT, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(self, label="&Describe Photos")
        describe(self.start_btn, "Start describing the photos. Shortcut: F5. Photos described "
                                 "before are remembered, so running it again is quick.")
        self.stop_btn = wx.Button(self, label="&Stop")
        describe(self.stop_btn, "Stop after the current photo.")
        self.open_btn = wx.Button(self, label="O&pen Page")
        describe(self.open_btn, "Open the saved descriptions.")
        for b in (self.start_btn, self.stop_btn, self.open_btn):
            row.Add(b, 0, wx.RIGHT, pad)
        s.Add(row, 0, wx.ALL, 8)

        s.Add(wx.StaticText(self, label="Progress:"), 0, wx.LEFT, 8)
        self.gauge = wx.Gauge(self, range=100)
        s.Add(self.gauge, 0, wx.EXPAND | wx.ALL, 8)
        s.Add(wx.StaticText(self, label="&Log:"), 0, wx.LEFT, 8)
        self.log = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        describe(self.log, "Each photo's description as it is written. Read it with the arrow keys.")
        s.Add(self.log, 1, wx.EXPAND | wx.ALL, 8)
        self.close_btn = wx.Button(self, wx.ID_CLOSE, "&Close")
        describe(self.close_btn, "Close this window. Shortcut: Escape.")
        s.Add(self.close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(s)
        self.start_btn.SetDefault()

        self.browse_btn.Bind(wx.EVT_BUTTON, lambda e: self._browse())
        self.out_btn.Bind(wx.EVT_BUTTON, lambda e: self._choose_out())
        self.start_btn.Bind(wx.EVT_BUTTON, lambda e: self._start())
        self.stop_btn.Bind(wx.EVT_BUTTON, lambda e: self._stop())
        self.open_btn.Bind(wx.EVT_BUTTON, lambda e: self._open())
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self._close())
        self.Bind(wx.EVT_CLOSE, lambda e: self._close())
        self.format_choice.Bind(wx.EVT_CHOICE, lambda e: self._suggest_output())
        self.folder_text.Bind(wx.EVT_TEXT, lambda e: (self._suggest_output(), self._update()))
        self.out_text.Bind(wx.EVT_TEXT, self._out_edited)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _fmt(self) -> str:
        return album.FORMATS[max(0, self.format_choice.GetSelection())][0]

    def _out_edited(self, event) -> None:
        self._out_auto = False
        event.Skip()

    def _suggest_output(self) -> None:
        folder = self.folder_text.GetValue().strip()
        if not folder or not self._out_auto:
            if not self._out_auto:
                cur = Path(self.out_text.GetValue().strip())
                ext = ".md" if self._fmt() == "markdown" else ".html"
                if cur.suffix.lower() in (".md", ".html") and cur.suffix.lower() != ext:
                    self.out_text.ChangeValue(str(cur.with_suffix(ext)))
            return
        self.out_text.ChangeValue(str(album.default_output(Path(folder), self._fmt())))

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _update(self) -> None:
        busy = self._busy()
        folder_ok = Path(self.folder_text.GetValue().strip() or "\0").is_dir()
        targets = {self.start_btn: not busy and folder_ok, self.stop_btn: busy,
                   self.open_btn: not busy and bool(self.last_output and self.last_output.is_file()),
                   self.browse_btn: not busy, self.out_btn: not busy}
        focus = wx.Window.FindFocus()
        if focus in targets and not targets[focus]:
            (self.stop_btn if busy else self.folder_text).SetFocus()
        for c, on in targets.items():
            c.Enable(on)

    def _browse(self) -> None:
        with wx.DirDialog(self, "Choose the photo folder", defaultPath=self.folder_text.GetValue(),
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            self.folder_text.SetValue(dlg.GetPath())
        n = len(album.find_photos(Path(self.folder_text.GetValue())))
        self._say(f"{n} photo{'s' if n != 1 else ''} in this folder.")
        self.folder_text.SetFocus()

    def _choose_out(self) -> None:
        fmt = self._fmt()
        cur = Path(self.out_text.GetValue().strip() or "Photo descriptions")
        wildcard = ("Markdown files (*.md)|*.md" if fmt == "markdown" else "Web pages (*.html)|*.html")
        with wx.FileDialog(self, "Save descriptions as", defaultDir=str(cur.parent),
                           defaultFile=cur.name, wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            self.out_text.ChangeValue(dlg.GetPath())
        self._out_auto = False
        self.out_text.SetFocus()

    def _say(self, text: str) -> None:
        self.announcer.speak(text, interrupt=True)

    def _log(self, msg: str) -> None:
        def add():
            if self:
                focused = wx.Window.FindFocus() is self.log
                pos = self.log.GetInsertionPoint()
                self.log.AppendText(str(msg) + "\n")
                if focused:
                    self.log.SetInsertionPoint(pos)
        wx.CallAfter(add)

    def _start(self) -> None:
        if self._busy():
            return
        folder = Path(self.folder_text.GetValue().strip())
        if not folder.is_dir():
            wx.MessageBox("Choose a folder of photos first.", "Describe Photos",
                          wx.OK | wx.ICON_WARNING, self)
            return
        photos = album.find_photos(folder, self.recursive_cb.GetValue())
        if not photos:
            wx.MessageBox("No pictures were found in this folder.", "Describe Photos",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if not vision.available(self.settings):
            wx.MessageBox("The vision model is not installed: " + vision.unavailable_reason(self.settings),
                          "Describe Photos", wx.OK | wx.ICON_WARNING, self)
            return
        out = Path(self.out_text.GetValue().strip() or album.default_output(folder, self._fmt()))
        self._cancel.clear()
        self.log.Clear()
        self.gauge.SetValue(0)
        self._last_pct = 0
        self._say(f"Describing {len(photos)} photos. Loading the model can take a moment.")
        self._worker = threading.Thread(target=self._run, args=(folder, out, self._fmt(),
                                                                self.recursive_cb.GetValue()),
                                        daemon=True)
        self._worker.start()
        self._update()

    def _run(self, folder: Path, out: Path, fmt: str, recursive: bool) -> None:
        vision.hold()
        try:
            path = album.describe_folder(folder, out, fmt, self.settings, recursive=recursive,
                                         progress_cb=lambda d, t: wx.CallAfter(self._progress, d, t),
                                         log_cb=self._log, cancel=self._cancel)
            wx.CallAfter(self._done, path, "")
        except vision.Cancelled:
            wx.CallAfter(self._done, None, "cancelled")
        except Exception as e:  # noqa: BLE001
            wx.CallAfter(self._done, None, str(e))
        finally:
            vision.release()  # stops the engine unless another window uses it

    def _progress(self, done: int, total: int) -> None:
        if not self:
            return
        pct = int(done * 100 / total) if total else 0
        self.gauge.SetValue(pct)
        step = (pct // 25) * 25
        if 0 < step < 100 and step > self._last_pct:
            self._last_pct = step
            self.announcer.speak(f"{done} of {total} photos described.")

    def _done(self, path: Optional[Path], err: str) -> None:
        if not self:
            return
        self._worker = None
        if err == "cancelled":
            self._say("Stopped. Photos described so far are remembered.")
        elif err:
            self._say("Could not describe the photos.")
            wx.MessageBox(f"The photos could not be described:\n\n{err}", "Describe Photos",
                          wx.OK | wx.ICON_ERROR, self)
        else:
            self.gauge.SetValue(100)
            self.last_output = path
            self._say(f"Done. Saved {path.name}.")
            if self.open_cb.GetValue():
                self._open()
        self._update()

    def _open(self) -> None:
        if not self.last_output or not self.last_output.is_file():
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(self.last_output))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(self.last_output)])
            else:
                subprocess.Popen(["xdg-open", str(self.last_output)])
        except Exception as e:  # noqa: BLE001
            wx.MessageBox(f"Could not open {self.last_output}:\n{e}", "Open Page",
                          wx.OK | wx.ICON_ERROR, self)

    def _stop(self) -> None:
        if self._busy():
            self._cancel.set()
            self._say("Stopping after the current photo.")

    def _on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_F5 and not event.HasAnyModifiers():
            self._start()
            return
        event.Skip()

    def _close(self) -> None:
        if self._busy():
            if wx.MessageBox("Photos are still being described. Stop and close?", "Close",
                             wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
                return
            self._cancel.set()
        if self.IsModal():
            self.EndModal(wx.ID_CLOSE)
        else:
            self.Destroy()


__all__ = ["VisionDialog", "PhotoAlbumDialog"]
