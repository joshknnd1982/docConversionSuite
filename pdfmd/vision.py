"""Local AI picture descriptions for Document Conversion Suite.

A small open-weights vision model describes the pictures in a document
(photos, charts, graphs, maps, diagrams) so people who can't see them get
alternative text, or a caption in a block quote when the output format can't
hold the picture itself. It also describes whole folders of photos.

Everything runs on this computer. The model runs in llama.cpp's
``llama-server`` (MIT licence), started on 127.0.0.1 with a random port and a
random access key, and stopped when it is no longer needed. Nothing is sent
anywhere.

Hardware
--------
Three llama.cpp engines can be used:

* **Vulkan** (bundled): CPU code for every x64 processor generation (SSE4.2
  through AVX-512) plus NVIDIA, AMD and Intel graphics through Vulkan, which
  ships with their drivers. Works on every computer.
* **CUDA** (downloaded on request, about 700 MB with NVIDIA's CUDA
  runtime): the fastest engine on NVIDIA graphics cards. Offered only when an
  NVIDIA card is detected (with ``nvidia-smi``, part of every NVIDIA
  driver). The CUDA 13 build is used with drivers 580 and newer on RTX 20
  series cards and newer; the CUDA 12.4 build otherwise (GTX 900 series and
  newer, driver 528 or newer).
* On macOS the bundled-by-download build uses Metal.

The default model needs about 3 GB of memory, so it runs on 8 GB laptops
with integrated graphics and is much faster on a graphics card.

Processor choices (``VisionSettings.device``):

* ``auto``: an NVIDIA card with CUDA when the CUDA engine is installed;
  otherwise a dedicated graphics card through Vulkan (or Apple silicon) when
  one with enough free memory is found; otherwise the CPU. Integrated
  graphics are not used automatically, because on many laptops they are no
  faster than the CPU.
* ``cuda``: the NVIDIA card with CUDA (falls back to Vulkan, then the CPU).
* ``gpu`` (also ``vulkan``): the best graphics processor through Vulkan,
  including integrated graphics. Falls back to the CPU if none works.
* ``cpu``: never use a graphics processor.
* ``dev:<name>``: one particular graphics processor, by its llama.cpp name
  (for example ``dev:Vulkan1``), for computers with more than one.

Files
-----
The engine and the default model are bundled in the program folder
(``vision/``). Updates and extra models are stored per user, in
``%LOCALAPPDATA%\\DocConversionSuite\\vision`` (Windows),
``~/Library/Application Support/DocConversionSuite/vision`` (macOS) or
``~/.local/share/DocConversionSuite/vision`` (Linux). Every download is
checked against the SHA-256 published in the model catalog before it is used.
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import io
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

Logger = Optional[Callable[[str], None]]
Progress = Optional[Callable[[int, int], None]]

CATALOG_URL = ("https://raw.githubusercontent.com/joshknnd1982/docConversionSuite/main/"
               "vision-models.json")
_USER_AGENT = "DocConversionSuite (vision model updater)"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

DEVICES: List[Tuple[str, str]] = [
    ("auto", "Automatic: CUDA on NVIDIA if installed, otherwise a graphics card with Vulkan, "
             "otherwise CPU"),
    ("cuda", "NVIDIA GPU with CUDA (fastest on NVIDIA cards)"),
    ("gpu", "Any GPU with Vulkan (NVIDIA, AMD, Intel, including integrated graphics)"),
    ("cpu", "CPU only (works on every computer)"),
]
DEVICE_CODES = [c for c, _ in DEVICES]
CUDA_VARIANTS = ("cuda13", "cuda12")

# Built-in copy of vision-models.json, used offline and when the online
# catalog can't be read.
_BUILTIN_CATALOG_FILE = "vision-models.json"


class VisionError(RuntimeError):
    """The vision model could not be started or used."""


class Cancelled(Exception):
    """A download or batch was cancelled."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass
class VisionSettings:
    enabled: bool = True
    device: str = "auto"          # auto | cuda | gpu (Vulkan) | cpu | dev:<name>
    model_id: str = ""            # "" = the recommended installed model
    lang: str = "eng"             # Tesseract-style language code for the output

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "device": self.device, "model_id": self.model_id}

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "VisionSettings":
        s = cls()
        data = data or {}
        if isinstance(data.get("enabled"), bool):
            s.enabled = data["enabled"]
        dev = data.get("device")
        if dev == "vulkan":
            dev = "gpu"
        if dev in DEVICE_CODES or (isinstance(dev, str) and dev.startswith("dev:")):
            s.device = dev
        if isinstance(data.get("model_id"), str):
            s.model_id = data["model_id"]
        return s


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_dir() -> Optional[Path]:
    """The vision folder shipped with the program (or the build's vendor copy)."""
    for base in (_app_dir() / "vision", _app_dir() / "packaging" / "vendor" / "vision"):
        if base.is_dir():
            return base
    return None


def user_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "DocConversionSuite" / "vision"


def _read_manifest(folder: Optional[Path]) -> dict:
    if not folder:
        return {}
    try:
        data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_manifest(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "manifest.json.tmp"
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "manifest.json")


def _server_name() -> str:
    return "llama-server.exe" if sys.platform == "win32" else "llama-server"


def build_number(build: Optional[str]) -> int:
    m = re.search(r"(\d+)", build or "")
    return int(m.group(1)) if m else 0


@dataclass
class Runtime:
    server: Path
    build: str          # e.g. "b12441", "" if unknown
    source: str         # "user", "bundled", "environment", "path"
    backend: str = "vulkan"   # "vulkan" (also Metal/CPU builds), "cuda12" or "cuda13"


def find_cuda_runtime() -> Optional[Runtime]:
    """The installed CUDA engine that suits this computer's NVIDIA driver."""
    runtimes = _read_manifest(user_dir()).get("runtimes") or {}
    want = cuda_variant()
    order = [want] + [v for v in CUDA_VARIANTS if v != want] if want else []
    for variant in order:
        entry = runtimes.get(variant)
        if not isinstance(entry, dict):
            continue
        exe = user_dir() / str(entry.get("dir", "")) / _server_name()
        if entry.get("dir") and exe.is_file():
            return Runtime(exe, entry.get("build", ""), "user", variant)
    return None


def find_runtime(backend: str = "vulkan") -> Optional[Runtime]:
    """The llama-server to use: a user update, the bundled copy, or PATH.

    ``backend="cuda"`` returns the installed CUDA engine, or None.
    """
    if backend.startswith("cuda"):
        return find_cuda_runtime()
    env = os.environ.get("PDFMD_LLAMA_SERVER")
    if env and Path(env).is_file():
        return Runtime(Path(env), "", "environment")
    candidates: List[Runtime] = []
    udir = user_dir()
    manifest = _read_manifest(udir)
    user_build = manifest.get("runtime_build", "")
    exe = udir / str(manifest.get("runtime_dir") or "runtime") / _server_name()
    if exe.is_file():
        candidates.append(Runtime(exe, user_build, "user"))
    bdir = bundled_dir()
    if bdir:
        exe = bdir / "runtime" / _server_name()
        if exe.is_file():
            candidates.append(Runtime(exe, _read_manifest(bdir).get("runtime_build", ""), "bundled"))
    if candidates:
        # The newest engine wins (a user update is newer than the bundled copy).
        return max(candidates, key=lambda r: build_number(r.build))
    found = shutil.which("llama-server")
    return Runtime(Path(found), "", "path") if found else None


@dataclass
class InstalledModel:
    id: str
    name: str
    revision: str
    model: Path
    mmproj: Path
    source: str          # "user" or "bundled"
    server_args: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        try:
            return self.model.stat().st_size + self.mmproj.stat().st_size
        except OSError:
            return 0


def installed_models() -> Dict[str, InstalledModel]:
    """Models whose files are present, user copies first."""
    out: Dict[str, InstalledModel] = {}
    for source, folder in (("user", user_dir()), ("bundled", bundled_dir())):
        if not folder:
            continue
        for mid, entry in (_read_manifest(folder).get("models") or {}).items():
            if mid in out or not isinstance(entry, dict):
                continue
            files = entry.get("files") or {}
            mdir = folder / "models" / str(entry.get("dir") or mid)
            model = mdir / str(files.get("model", ""))
            mmproj = mdir / str(files.get("mmproj", ""))
            if model.is_file() and mmproj.is_file():
                out[mid] = InstalledModel(mid, entry.get("name", mid), entry.get("revision", ""),
                                          model, mmproj, source,
                                          list(entry.get("server_args") or []))
    return out


def resolve_model(model_id: str = "") -> Optional[InstalledModel]:
    models = installed_models()
    if not models:
        return None
    if model_id and model_id in models:
        return models[model_id]
    rec = builtin_catalog().get("recommended", "")
    if rec in models:
        return models[rec]
    return next(iter(models.values()))


def available(settings: Optional[VisionSettings] = None) -> bool:
    """True when the engine and a model are installed."""
    return find_runtime() is not None and resolve_model(settings.model_id if settings else "") is not None


def unavailable_reason(settings: Optional[VisionSettings] = None) -> str:
    if find_runtime() is None:
        return ("the vision engine (llama.cpp) is not installed. Open the Vision Model window "
                "(Ctrl+I) and press Update Vision Model, or run pdfmd --vision-update")
    if resolve_model(settings.model_id if settings else "") is None:
        return ("no vision model is installed. Open the Vision Model window (Ctrl+I) and press "
                "Update Vision Model, or run pdfmd --vision-update")
    return ""


# ---------------------------------------------------------------------------
# Catalog and updates
# ---------------------------------------------------------------------------


def builtin_catalog() -> dict:
    for base in (_app_dir(), _app_dir() / "vision", Path(__file__).resolve().parent.parent):
        p = base / _BUILTIN_CATALOG_FILE
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {"schema": 1, "recommended": "", "runtime": {}, "models": []}


def _opener():
    # Downloads go to the internet through the system proxy settings;
    # requests to the local engine never use a proxy (see _local_opener).
    return urllib.request.build_opener()


def fetch_catalog(timeout: int = 20) -> dict:
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": _USER_AGENT})
    with _opener().open(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URL)
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise VisionError("The online model catalog has an unknown format.")
    # An older online list without CUDA engines: use the built-in ones for
    # the same llama.cpp build.
    builtin = builtin_catalog().get("runtime") or {}
    online = data.setdefault("runtime", {})
    if "cuda" not in online and builtin.get("build") == online.get("build") and builtin.get("cuda"):
        online["cuda"] = builtin["cuda"]
    return data


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def catalog_model(catalog: dict, model_id: str) -> Optional[dict]:
    for m in catalog.get("models") or []:
        if m.get("id") == model_id:
            return m
    return None


@dataclass
class UpdatePlan:
    runtime: Optional[dict] = None       # catalog runtime asset to install, or None
    runtime_build: str = ""
    model: Optional[dict] = None         # catalog model entry to install, or None
    cuda: Optional[List[dict]] = None    # CUDA engine archives to install, or None
    cuda_variant: str = ""
    download_bytes: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def needed(self) -> bool:
        return bool(self.runtime or self.model or self.cuda)


def plan_update(catalog: dict, model_id: str = "", device: str = "") -> UpdatePlan:
    """What "Update Vision Model" would download for this computer.

    With ``device="cuda"`` on a computer with an NVIDIA card, the CUDA engine
    is included (it is only downloaded when you choose CUDA).
    """
    plan = UpdatePlan()
    rt = catalog.get("runtime") or {}
    asset = (rt.get("assets") or {}).get(platform_key())
    current = find_runtime()
    if asset:
        newer = current is None or (current.source in ("user", "bundled") and
                                    build_number(rt.get("build")) > build_number(current.build))
        if newer:
            plan.runtime = dict(asset, url=(rt.get("url_base", "") + asset["file"]))
            plan.runtime_build = rt.get("build", "")
            plan.download_bytes += int(asset.get("size", 0))
            plan.notes.append(f"Vision engine: llama.cpp {rt.get('build')} "
                              + ("(new)" if current is None else f"(installed: {current.build or 'unknown'})"))
    elif current is None:
        plan.notes.append(f"No vision engine is published for {platform_key()}. Install "
                          "llama.cpp (for example with your package manager) so that "
                          "llama-server is on the PATH.")
    target = model_id or catalog.get("recommended", "")
    entry = catalog_model(catalog, target)
    if entry:
        have = installed_models().get(target)
        if have is None or have.revision != entry.get("revision"):
            plan.model = entry
            plan.download_bytes += sum(int(f.get("size", 0)) for f in entry["files"].values())
            plan.notes.append(f"Model: {entry.get('name', target)} "
                              + ("(new)" if have is None else "(newer version)"))
    if device == "cuda":
        variant = cuda_variant()
        spec = ((rt.get("cuda") or {}).get(variant) or {}) if variant else {}
        files = (spec.get("assets") or {}).get(platform_key())
        if files:
            have_cuda = find_cuda_runtime()
            if have_cuda is None or have_cuda.backend != variant or \
                    build_number(rt.get("build")) > build_number(have_cuda.build):
                plan.cuda = [dict(f, url=rt.get("url_base", "") + f["file"]) for f in files]
                plan.cuda_variant = variant
                plan.runtime_build = plan.runtime_build or rt.get("build", "")
                plan.download_bytes += sum(int(f.get("size", 0)) for f in files)
                plan.notes.append(f"NVIDIA CUDA engine: llama.cpp {rt.get('build')} with "
                                  f"{spec.get('label', variant)} "
                                  + ("(new)" if have_cuda is None else "(newer version)"))
        elif not nvidia_gpus():
            plan.notes.append("No NVIDIA graphics card was found, so the CUDA engine isn't needed.")
        elif not variant:
            plan.notes.append("Your NVIDIA driver is too old for CUDA; update it from nvidia.com, "
                              "or use Vulkan.")
    return plan


def _download(url: str, dest: Path, sha256: str, progress: Progress = None,
              cancel: Optional[threading.Event] = None, done_before: int = 0,
              total_all: int = 0) -> None:
    """Download url to dest, verifying the SHA-256 while streaming."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with _opener().open(req, timeout=60) as resp, open(part, "wb") as fh:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel is not None and cancel.is_set():
                fh.close()
                part.unlink(missing_ok=True)
                raise Cancelled()
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                if total_all:
                    progress(done_before + done, total_all)
                else:
                    progress(done, total)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        part.unlink(missing_ok=True)
        raise VisionError(f"{dest.name} failed its checksum check, so it was not installed. "
                          "Please try again.")
    os.replace(part, dest)


def _safe_extract(archive: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    root = out.resolve()

    def ok(name: str) -> bool:
        target = (out / name).resolve()
        return str(target).startswith(str(root))

    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if ok(info.filename):
                    zf.extract(info, out)
    else:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                if ok(member.name) and (member.isfile() or member.isdir() or member.issym()):
                    tf.extract(member, out)  # noqa: S202 (paths checked above)


def install_runtime(asset: dict, build: str, progress: Progress = None,
                    cancel: Optional[threading.Event] = None, log_cb: Logger = None) -> Path:
    """Download and install a llama.cpp engine into the user folder."""
    shutdown()
    udir = user_dir()
    with tempfile.TemporaryDirectory(dir=str(udir.parent) if udir.parent.exists() else None) as tmp:
        archive = Path(tmp) / asset["file"]
        if log_cb:
            log_cb(f"Downloading the vision engine (llama.cpp {build})...")
        _download(asset["url"], archive, asset.get("sha256", ""), progress, cancel)
        unpacked = Path(tmp) / "unpacked"
        _safe_extract(archive, unpacked)
        servers = list(unpacked.rglob(_server_name()))
        if not servers:
            raise VisionError("llama-server was not found in the downloaded engine.")
        src = servers[0].parent
        # Each engine version gets its own folder, so an engine another
        # window is still running is never overwritten.
        dir_name = f"runtime-{build or 'new'}"
        new = udir / dir_name
        if new.exists():
            new = udir / f"{dir_name}-{int(time.time())}"
            dir_name = new.name
        shutil.copytree(src, new)
        if sys.platform != "win32":
            for f in new.iterdir():
                if f.is_file():
                    f.chmod(f.stat().st_mode | 0o755)
    manifest = _read_manifest(udir)
    old_dir = manifest.get("runtime_dir") or "runtime"
    manifest["runtime_build"] = build
    manifest["runtime_dir"] = dir_name
    _write_manifest(udir, manifest)
    if old_dir != dir_name:
        _remove_quietly(udir / old_dir)  # best effort: it may still be in use
    if log_cb:
        log_cb(f"Vision engine llama.cpp {build} installed.")
    return new / _server_name()


def install_cuda_runtime(files: List[dict], variant: str, build: str, progress: Progress = None,
                         cancel: Optional[threading.Event] = None, log_cb: Logger = None) -> Path:
    """Download and install llama.cpp's CUDA engine with NVIDIA's CUDA runtime."""
    shutdown()
    udir = user_dir()
    udir.mkdir(parents=True, exist_ok=True)
    total = sum(int(f.get("size", 0)) for f in files)
    done = 0
    with tempfile.TemporaryDirectory(dir=str(udir)) as tmp:
        unpacked = Path(tmp) / "unpacked"
        for f in files:
            if log_cb:
                log_cb(f"Downloading {f['file']} ({int(f.get('size', 0)) / 1e6:.0f} MB)...")
            archive = Path(tmp) / f["file"]
            _download(f["url"], archive, f.get("sha256", ""), progress, cancel,
                      done_before=done, total_all=total)
            done += int(f.get("size", 0))
            _safe_extract(archive, unpacked / Path(f["file"]).stem)
            archive.unlink(missing_ok=True)
        servers = list(unpacked.rglob(_server_name()))
        if not servers:
            raise VisionError("llama-server was not found in the downloaded CUDA engine.")
        dir_name = f"runtime-{variant}-{build or 'new'}"
        new = udir / dir_name
        if new.exists():
            dir_name = f"{dir_name}-{int(time.time())}"
            new = udir / dir_name
        shutil.copytree(servers[0].parent, new)
        # NVIDIA's runtime libraries (cudart, cublas) go next to the server.
        for lib in unpacked.rglob("*"):
            if lib.is_file() and lib.parent != servers[0].parent and \
                    re.search(r"\.(dll|so(\.\d+)*)$", lib.name, re.I) and not (new / lib.name).exists():
                shutil.copy2(lib, new / lib.name)
        if sys.platform != "win32":
            for f in new.iterdir():
                if f.is_file():
                    f.chmod(f.stat().st_mode | 0o755)
    manifest = _read_manifest(udir)
    runtimes = manifest.setdefault("runtimes", {})
    old_dir = str((runtimes.get(variant) or {}).get("dir") or "")
    runtimes[variant] = {"build": build, "dir": dir_name}
    _write_manifest(udir, manifest)
    if old_dir and old_dir != dir_name:
        _remove_quietly(udir / old_dir)
    _devices_cache.clear()
    if log_cb:
        log_cb(f"NVIDIA CUDA engine (llama.cpp {build}) installed.")
    return new / _server_name()


def _remove_quietly(folder: Path) -> None:
    """Delete a folder that is no longer used, if nothing holds it open."""
    try:
        if folder.is_dir():
            shutil.rmtree(folder)
    except OSError:
        pass  # still in use by another window; cleaned up on a later update


def install_model(entry: dict, progress: Progress = None,
                  cancel: Optional[threading.Event] = None, log_cb: Logger = None) -> InstalledModel:
    """Download a catalog model (model + vision projector) into the user folder."""
    shutdown()
    udir = user_dir()
    mid = entry["id"]
    # One folder per model version, so files another window has open are
    # never overwritten.
    dir_name = f"{mid}-{(entry.get('revision') or 'new')[:8]}"
    staging = udir / "models" / (dir_name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    files = entry["files"]
    total = sum(int(f.get("size", 0)) for f in files.values())
    done = 0
    for role in ("model", "mmproj"):
        f = files[role]
        if log_cb:
            log_cb(f"Downloading {f['file']} ({int(f.get('size', 0)) / 1e6:.0f} MB)...")
        # Reuse an identical file already in the bundled or user folder.
        existing = _find_identical(f)
        if existing:
            staging.mkdir(parents=True, exist_ok=True)
            shutil.copy2(existing, staging / f["file"])
        else:
            _download(f["url"], staging / f["file"], f.get("sha256", ""), progress, cancel,
                      done_before=done, total_all=total)
        done += int(f.get("size", 0))
    mdir = udir / "models" / dir_name
    if mdir.exists():
        dir_name = f"{dir_name}-{int(time.time())}"
        mdir = udir / "models" / dir_name
    os.replace(staging, mdir)
    manifest = _read_manifest(udir)
    models = manifest.setdefault("models", {})
    old = models.get(mid) or {}
    old_dir = str(old.get("dir") or mid) if old else ""
    models[mid] = {"name": entry.get("name", mid), "revision": entry.get("revision", ""),
                   "dir": dir_name,
                   "license": entry.get("license", ""), "base": entry.get("base", ""),
                   "files": {"model": files["model"]["file"], "mmproj": files["mmproj"]["file"]},
                   "server_args": entry.get("server_args") or []}
    _write_manifest(udir, manifest)
    if old_dir and old_dir != dir_name:
        _remove_quietly(udir / "models" / old_dir)
    if log_cb:
        log_cb(f"Vision model {entry.get('name', mid)} installed.")
    return installed_models()[mid]


def _find_identical(f: dict) -> Optional[Path]:
    for folder in (bundled_dir(), user_dir()):
        if not folder:
            continue
        for cand in (folder / "models").rglob(f["file"]) if (folder / "models").is_dir() else []:
            try:
                if cand.stat().st_size == int(f.get("size", -1)) and _sha256(cand) == f.get("sha256"):
                    return cand
            except OSError:
                continue
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_update(model_id: str = "", catalog: Optional[dict] = None, progress: Progress = None,
               cancel: Optional[threading.Event] = None, log_cb: Logger = None,
               device: str = "") -> UpdatePlan:
    """Check the online catalog and install whatever is newer."""
    if catalog is None:
        catalog = fetch_catalog()
    plan = plan_update(catalog, model_id, device)
    if plan.runtime:
        install_runtime(plan.runtime, plan.runtime_build, progress, cancel, log_cb)
    if plan.cuda:
        install_cuda_runtime(plan.cuda, plan.cuda_variant, plan.runtime_build, progress, cancel,
                             log_cb)
    if plan.model:
        install_model(plan.model, progress, cancel, log_cb)
    return plan


def remove_user_model(model_id: str) -> bool:
    """Delete a downloaded model from the user folder. Bundled models stay."""
    shutdown()
    udir = user_dir()
    manifest = _read_manifest(udir)
    models = manifest.get("models") or {}
    if model_id not in models:
        return False
    folder = udir / "models" / str(models[model_id].get("dir") or model_id)
    del models[model_id]
    _write_manifest(udir, manifest)
    _remove_quietly(folder)
    return True


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


@dataclass
class Device:
    name: str           # llama.cpp device id, e.g. "Vulkan0", "MTL0", "CUDA0"
    description: str    # e.g. "NVIDIA GeForce RTX 4070"
    total_mib: int
    free_mib: int

    @property
    def integrated(self) -> bool:
        d = self.description
        if self.name.upper().startswith("MTL"):
            return False  # Apple silicon: unified memory, and fast
        return bool(re.search(
            r"UHD|Iris|Intel\(R\) Graphics|Intel\(R\) HD|Radeon\(TM\) Graphics|Radeon Graphics|"
            r"Radeon \d{3}M|\d{3}M Graphics|Vega \d|Adreno|Mali|Arc\(TM\) 1[34]0V|"
            r"Microsoft Basic|llvmpipe|SwiftShader", d, re.I))

    @property
    def backend(self) -> str:
        n = self.name.upper()
        return ("CUDA" if n.startswith("CUDA") else "Metal" if n.startswith("MTL")
                else "Vulkan" if n.startswith("VULKAN") else re.sub(r"\d+$", "", self.name))

    def label(self) -> str:
        kind = "integrated graphics" if self.integrated else "graphics card"
        return f"{self.description} ({kind}, {self.backend}, {self.free_mib / 1024:.1f} GB free)"


@dataclass
class NvidiaGpu:
    name: str
    compute_capability: float
    driver: str
    total_mib: int
    free_mib: int


_nvidia_cache: Optional[List[NvidiaGpu]] = None


def nvidia_gpus() -> List[NvidiaGpu]:
    """NVIDIA graphics cards, from nvidia-smi (installed with every NVIDIA driver)."""
    global _nvidia_cache
    if _nvidia_cache is not None:
        return _nvidia_cache
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform == "win32":
        cand = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        exe = str(cand) if cand.is_file() else None
    gpus: List[NvidiaGpu] = []
    if exe:
        try:
            out = subprocess.run(
                [exe, "--query-gpu=name,compute_cap,driver_version,memory.total,memory.free",
                 "--format=csv,noheader,nounits"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=20, creationflags=_NO_WINDOW,
            ).stdout.decode("utf-8", "replace")
            for line in out.splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 5:
                    try:
                        gpus.append(NvidiaGpu(parts[0], float(parts[1]), parts[2],
                                              int(float(parts[3])), int(float(parts[4]))))
                    except ValueError:
                        gpus.append(NvidiaGpu(parts[0], 0.0, parts[2], 0, 0))
        except Exception:
            gpus = []
    _nvidia_cache = gpus
    return gpus


def cuda_variant() -> str:
    """"cuda13", "cuda12", or "" if there is no NVIDIA card with a recent driver."""
    gpus = nvidia_gpus()
    if not gpus or sys.platform == "darwin":
        return ""
    best = max(gpus, key=lambda g: g.compute_capability)
    try:
        driver = float(".".join(best.driver.split(".")[:2]))
    except ValueError:
        driver = 0.0
    if driver >= 580 and best.compute_capability >= 7.5:
        return "cuda13"
    if driver >= (528 if sys.platform == "win32" else 525):
        return "cuda12"
    return ""


_devices_cache: Dict[str, List[Device]] = {}


def list_devices(runtime: Optional[Runtime] = None) -> List[Device]:
    runtime = runtime or find_runtime()
    if runtime is None:
        return []
    key = str(runtime.server)
    if key in _devices_cache:
        return _devices_cache[key]
    try:
        proc = subprocess.run([str(runtime.server), "--list-devices"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60, creationflags=_NO_WINDOW,
                              cwd=str(runtime.server.parent))
        text = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return []
    devices = []
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z]+\d+):\s*(.+?)\s*\((\d+)\s*MiB,\s*(\d+)\s*MiB free\)", line)
        if m:
            devices.append(Device(m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    _devices_cache[key] = devices
    return devices


def _best_gpu(devices: List[Device], allow_integrated: bool, need_mib: int) -> Optional[Device]:
    usable = [d for d in devices if allow_integrated or not d.integrated]
    if not allow_integrated:
        usable = [d for d in usable if d.free_mib >= need_mib]
    if not usable:
        return None
    return max(usable, key=lambda d: (not d.integrated, d.free_mib))


def choose_engine(settings: VisionSettings, model: InstalledModel
                  ) -> Tuple[Optional[Runtime], Optional[Device], str]:
    """(engine, GPU or None for the CPU, note) for these settings."""
    vulkan = find_runtime()
    if settings.device in ("cuda", "auto"):
        cuda = find_cuda_runtime() if nvidia_gpus() else None
        if cuda is not None:
            devs = [d for d in list_devices(cuda) if d.name.upper().startswith("CUDA")]
            if devs:
                return cuda, max(devs, key=lambda d: d.free_mib), ""
        if settings.device == "cuda":
            note = ("The NVIDIA CUDA engine is not installed; using Vulkan. Download it in the "
                    "Vision Model window (Ctrl+I) or with pdfmd --vision-update "
                    "--vision-device cuda." if nvidia_gpus() and cuda is None
                    else "CUDA could not be used; using Vulkan.")
            if not nvidia_gpus():
                note = "No NVIDIA graphics card was found; using Vulkan."
            gpu = choose_device(VisionSettings(device="gpu"), model, vulkan)
            return vulkan, gpu, note
    return vulkan, choose_device(settings, model, vulkan), ""


def choose_device(settings: VisionSettings, model: InstalledModel,
                  runtime: Optional[Runtime] = None) -> Optional[Device]:
    """The GPU to use with this (Vulkan) engine, or None for the CPU."""
    if settings.device == "cpu":
        return None
    need = int(model.size / (1024 * 1024) * 1.3) + 600
    devices = list_devices(runtime)
    if settings.device.startswith("dev:"):
        wanted = settings.device[4:].lower()
        for d in devices:
            if d.name.lower() == wanted:
                return d
        return _best_gpu(devices, allow_integrated=True, need_mib=need)
    if settings.device in ("gpu", "cuda"):
        return _best_gpu(devices, allow_integrated=True, need_mib=need)
    return _best_gpu(devices, allow_integrated=False, need_mib=need)


# ---------------------------------------------------------------------------
# The engine (llama-server)
# ---------------------------------------------------------------------------

DOC_PROMPT = """Write alternative text for this picture from a document, for a reader who is blind.
Use one to three plain sentences, under 60 words. Start with what kind of picture it is (for example a photo, bar chart, line graph, pie chart, map, diagram, illustration or logo), then say what it shows.
For a chart or graph, give its title if there is one, what it measures, and the main trend or the values you can clearly read. If the chart has no title or axis labels, do not guess what it measures.
Describe only what is visible. Never invent words, names or numbers. Do not use lists, headings or Markdown."""

TEXT_VERDICT = """
If the picture is only a block of paragraph text, such as a scanned page, reply with the single word TEXT."""

PHOTO_PROMPT = """Describe this photo for someone looking back through their own photos.
In two to four plain sentences, say who or what is in it (describe people by appearance, clothing and what they are doing, but never guess who they are), the place and setting, the time of day, season or weather if you can tell, and the mood. Mention any signs or text you can read.
Describe only what you can see."""

TITLE_SYSTEM = "You give photos short, plain titles of two to six words."

TITLE_PROMPT = """Photo description: {description}

Title for this photo:"""

_LANG_NAMES = {
    "eng": "English", "deu": "German", "fra": "French", "spa": "Spanish", "ita": "Italian",
    "por": "Portuguese", "nld": "Dutch", "pol": "Polish", "rus": "Russian",
    "chi_sim": "Simplified Chinese", "chi_tra": "Traditional Chinese", "jpn": "Japanese",
    "kor": "Korean", "ara": "Arabic", "hin": "Hindi", "tur": "Turkish", "vie": "Vietnamese",
    "ukr": "Ukrainian", "ces": "Czech", "swe": "Swedish", "dan": "Danish", "nor": "Norwegian",
    "fin": "Finnish", "ell": "Greek", "heb": "Hebrew", "hun": "Hungarian", "ron": "Romanian",
    "ind": "Indonesian", "tha": "Thai",
}


def language_name(code: str) -> str:
    first = (code or "eng").split("+")[0].strip()
    return _LANG_NAMES.get(first, "English")


@dataclass
class Description:
    kind: str           # "picture", "text", "decorative"
    text: str = ""
    title: str = ""
    seconds: float = 0.0


def _local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class VisionEngine:
    """One running llama-server with one model."""

    def __init__(self, runtime: Runtime, model: InstalledModel, device: Optional[Device],
                 log_cb: Logger = None) -> None:
        self.runtime = runtime
        self.model = model
        self.device = device
        self.log_cb = log_cb
        self.port = 0
        self.key = secrets.token_hex(16)
        self.proc: Optional[subprocess.Popen] = None
        self.log_path: Optional[Path] = None
        self._lock = threading.Lock()
        self.last_used = time.time()

    @property
    def device_label(self) -> str:
        return self.device.label() if self.device else "the CPU"

    def _args(self) -> List[str]:
        args = [str(self.runtime.server), "-m", str(self.model.model), "--mmproj",
                str(self.model.mmproj), "--host", "127.0.0.1", "--port", str(self.port),
                "--api-key", self.key, "-c", "8192", "-np", "1", "--no-webui",
                "--cache-ram", "0", "--image-max-tokens", "1024"]
        if self.device is None:
            args += ["--device", "none", "-ngl", "0", "--no-mmproj-offload"]
        else:
            args += ["--device", self.device.name, "-ngl", "all"]
        args += list(self.model.server_args)
        return args

    def start(self, timeout: float = 240.0) -> None:
        self.port = _free_port()
        fd, name = tempfile.mkstemp(prefix="pdfmd-vision-", suffix=".log")
        os.close(fd)
        self.log_path = Path(name)
        log = open(self.log_path, "wb")
        try:
            env = dict(os.environ)
            if self.runtime.backend.startswith("cuda"):
                # On cards newer than the CUDA build, the driver compiles the
                # kernels the first time. Keep them all in its cache (the
                # default 256 MB is too small for llama.cpp) so later starts
                # are fast.
                env.setdefault("CUDA_CACHE_MAXSIZE", str(4 * 1024 ** 3 - 1))
            self.proc = subprocess.Popen(self._args(), stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
                                         cwd=str(self.runtime.server.parent), env=env)
        except OSError as e:
            log.close()
            raise VisionError(f"Could not start the vision engine: {e}") from e
        log.close()
        with _running_lock:
            _running.add(self)
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{self.port}/health"
        while time.time() < deadline:
            proc = self.proc
            if proc is None:  # shutdown() was called while the model was loading
                raise VisionError("The vision engine was stopped while loading the model.")
            if proc.poll() is not None:
                raise VisionError("The vision engine stopped while loading the model.\n"
                                  + self.log_tail())
            try:
                with _local_opener().open(url, timeout=5) as resp:  # noqa: S310 (localhost)
                    if resp.status == 200:
                        return
            except Exception:
                pass
            time.sleep(0.4)
        self.stop()
        raise VisionError("The vision engine took too long to load the model.")

    def log_tail(self, lines: int = 12) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace") if self.log_path else ""
        except Exception:
            text = ""
        return "\n".join(text.strip().splitlines()[-lines:])

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        with _running_lock:
            _running.discard(self)
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self.log_path:
            try:
                self.log_path.unlink()
            except Exception:
                pass

    def _chat(self, prompt: str, png: Optional[bytes], max_tokens: int,
              temperature: float = 0.1, system: str = "") -> str:
        content: list = []
        if png is not None:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(png).decode()}})
        content.append({"type": "text", "text": prompt})
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        body = {
            "messages": messages,
            # Every picture is new; reusing a cached prompt only makes the
            # answers less repeatable.
            "cache_prompt": False,
            "temperature": temperature,
            "top_p": 0.8,
            "top_k": 20,
            "repeat_penalty": 1.05,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
        )
        with _local_opener().open(req, timeout=600) as resp:  # noqa: S310 (localhost)
            data = json.loads(resp.read().decode("utf-8"))
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        return str(msg.get("content") or "").strip()

    def describe(self, image, purpose: str = "document", lang: str = "eng",
                 context: str = "", ask_text: bool = False) -> Description:
        """Describe one picture (PIL image, bytes or path).

        ``ask_text``: let the model answer TEXT for pictures of paragraphs
        (used when Tesseract isn't there to tell).
        """
        png = prepare_image(image, max_side=1024 if self.device else 896)
        name = language_name(lang)
        in_lang = f"\nWrite the description in {name}." if name != "English" else ""
        if purpose == "photo":
            system, prompt, max_tokens = "", PHOTO_PROMPT + in_lang, 260
            plain = prompt
        else:
            system = DOC_PROMPT + (TEXT_VERDICT if ask_text else "") + in_lang
            plain = "Write the alternative text for this picture."
            prompt = (f"Caption in the document: \"{context[:300]}\"\n{plain}" if context
                      else plain)
            max_tokens = 160
        t0 = time.time()
        with self._lock:
            if not self.alive():
                raise VisionError("The vision engine is not running.\n" + self.log_tail())
            raw = self._chat(prompt, png, max_tokens, system=system)
            d = parse_answer(raw, purpose, 0.0)
            if not d.text and d.kind == "picture" or not raw.strip():
                # Small models occasionally end the answer at once; ask
                # again, a little more freely and without the caption.
                raw = self._chat(plain, png, max_tokens, temperature=0.4, system=system)
                d = parse_answer(raw, purpose, 0.0)
            if purpose == "photo" and d.text and not d.title:
                # Small models follow one instruction at a time: the title
                # is asked for separately, from the description (fast, no
                # picture needed).
                try:
                    t = self._chat(TITLE_PROMPT.format(description=d.text), None, 24,
                                   system=TITLE_SYSTEM + (f" Write in {name}." if name != "English"
                                                          else ""))
                    d.title = clean_title(t)
                except Exception:
                    pass
            self.last_used = time.time()
        d.seconds = time.time() - t0
        return d


def parse_answer(raw: str, purpose: str, seconds: float = 0.0) -> Description:
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    bare = re.sub(r"[^A-Za-z]", "", text).upper()
    if purpose != "photo" and bare in ("TEXT", "TEXTONLY"):
        return Description("text", seconds=seconds)
    if purpose != "photo" and bare == "DECORATIVE":
        return Description("decorative", seconds=seconds)
    title = ""
    if purpose == "photo":
        m = re.search(r"(?im)^\s*\**\s*title\s*\**\s*[:\-]\s*(.+)$", text)
        if m:
            title = clean_text(m.group(1)).rstrip(".")
        m = re.search(r"(?is)\**\s*description\s*\**\s*[:\-]\s*(.+)", text)
        text = m.group(1) if m else re.sub(r"(?im)^\s*\**\s*title\s*\**\s*[:\-].*$", "", text)
    text = clean_text(text)
    if purpose != "photo":
        text = limit_sentences(text, 3, 80)
    else:
        text = limit_sentences(text, 4, 110)
    if not text:
        return Description("text" if purpose != "photo" else "picture", seconds=seconds)
    return Description("picture", text, title, seconds)


def clean_title(raw: str) -> str:
    """A short photo title, or "" if the model's answer isn't one."""
    t = clean_text((raw or "").strip().splitlines()[0] if (raw or "").strip() else "")
    # "Title: X", "The title is: X", "Here is a title - X"
    m = re.match(r"^[^:]{0,40}\btitle\b[^:]{0,20}[:\-]\s*(.+)$", t, flags=re.I)
    if m:
        t = m.group(1)
    t = t.strip(" .\"'\u201c\u201d")
    if not t or not t[0].isalnum() or len(t.split()) > 10 or len(t) > 80:
        return ""
    if re.search(r"\b(title|description|described|based on|photo with|this photo|quotation)\b",
                 t, re.I):
        return ""
    return t


def limit_sentences(text: str, sentences: int, words: int) -> str:
    """At most this many sentences and about this many words."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    out: List[str] = []
    count = 0
    for part in parts:
        n = len(part.split())
        if out and (len(out) >= sentences or count + n > words):
            break
        out.append(part)
        count += n
    return " ".join(out).strip()


def clean_text(text: str) -> str:
    """One paragraph of plain text, without Markdown or a stock opening."""
    t = re.sub(r"(?m)^\s*(?:[-*+\u2022]|\d+[.)])\s+", "", text or "")   # list markers
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"\s+", " ", t).strip().strip('"').strip()
    t = re.sub(r"^(alt(ernative)? text|description)\s*:\s*", "", t, flags=re.I)
    t = t.lstrip(",;:.-\u2013\u2014 ")
    t = re.sub(r"^(this|the) (image|picture|photo|photograph) (shows|depicts|features|is)\s+", "",
               t, flags=re.I)
    t = re.sub(r"^this is (an? )", r"\1", t, flags=re.I)
    t = re.sub(r"^(an? )?(image|picture|photo) of\s+", "", t, flags=re.I)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    if len(t) > 900:
        cut = t[:900]
        t = cut[: cut.rfind(". ") + 1] or cut
    return t


# ---------------------------------------------------------------------------
# Shared engine
# ---------------------------------------------------------------------------

_engine: Optional[VisionEngine] = None
_engine_key: Optional[Tuple[str, str, str]] = None
_engine_lock = threading.Lock()        # held while an engine is being started
_running: "set" = set()                # every engine process that may be alive
_running_lock = threading.Lock()       # short critical sections only
_holds = 0                             # batches using the shared engine (hold/release)
_holds_lock = threading.Lock()


def get_engine(settings: VisionSettings, log_cb: Logger = None) -> VisionEngine:
    """Start (or reuse) the engine for these settings."""
    global _engine, _engine_key
    runtime = find_runtime()
    if runtime is None:
        raise VisionError("Picture descriptions are off: " + unavailable_reason(settings) + ".")
    model = resolve_model(settings.model_id)
    if model is None:
        raise VisionError("Picture descriptions are off: " + unavailable_reason(settings) + ".")
    with _engine_lock:
        key = (model.id, settings.device)
        if _engine is not None and _engine_key == key and _engine.alive():
            _engine.log_cb = log_cb
            return _engine
        if _engine is not None:
            _engine.stop()
            _engine = None
        chosen, device, note = choose_engine(settings, model)
        runtime = chosen or runtime
        if note and log_cb:
            log_cb(f"[vision] {note}")
        engine = VisionEngine(runtime, model, device, log_cb)
        if log_cb:
            log_cb(f"[vision] Loading {model.name} on {engine.device_label}...")
            if runtime.backend.startswith("cuda"):
                log_cb("[vision] The first start with CUDA can take a minute on the newest "
                       "graphics cards while the NVIDIA driver prepares the engine; later starts "
                       "are fast.")
        t0 = time.time()
        try:
            try:
                engine.start()
            except VisionError as e:
                engine.stop()
                if device is None:
                    raise
                reason = str(e).splitlines()[0]
                engine = None
                if runtime.backend.startswith("cuda"):
                    # CUDA failed (driver, memory): try the GPU through Vulkan.
                    vulkan = find_runtime()
                    gpu = choose_device(VisionSettings(device="gpu"), model, vulkan) if vulkan else None
                    if gpu is not None:
                        if log_cb:
                            log_cb(f"[vision] CUDA could not be used ({reason}); using Vulkan.")
                        engine = VisionEngine(vulkan, model, gpu, log_cb)
                        try:
                            engine.start()
                        except VisionError as e2:
                            engine.stop()
                            engine = None
                            reason = str(e2).splitlines()[0]
                        runtime = vulkan
                if engine is None:
                    cpu_rt = find_runtime() or runtime
                    engine = VisionEngine(cpu_rt, model, None, log_cb)
                    if log_cb:
                        log_cb(f"[vision] The graphics processor could not be used ({reason}); "
                               "using the CPU instead.")
                    engine.start()
            # Stored before anything else can raise (a log callback raises to
            # cancel), so shutdown() always finds it.
            _engine, _engine_key = engine, key
        except BaseException:
            engine.stop()
            raise
        if log_cb:
            log_cb(f"[vision] Ready in {time.time() - t0:.1f} s on {engine.device_label}.")
        return engine


def shutdown() -> None:
    """Stop every engine now (frees its memory), even one still loading.

    Never waits for a model to finish loading, so it is safe on the GUI
    thread. A batch that is using the engine sees an error for the pictures
    that remain; use hold()/release() to share the engine between batches.
    """
    global _engine, _engine_key
    _engine, _engine_key = None, None
    with _running_lock:
        engines = list(_running)
    for e in engines:
        e.stop()


def hold() -> None:
    """A batch starts using the shared engine (see release())."""
    global _holds
    with _holds_lock:
        _holds += 1


def release() -> None:
    """A batch is done; stop the engine when no other batch is using it."""
    global _holds
    with _holds_lock:
        _holds = max(0, _holds - 1)
        idle = _holds == 0
    if idle:
        shutdown()


atexit.register(shutdown)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def _pil():
    from PIL import Image, ImageOps  # type: ignore

    try:  # iPhone and many Android phones save HEIC photos
        import pillow_heif  # type: ignore

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    return Image, ImageOps


def open_image(source):
    """Open bytes, a path or a PIL image as an upright RGB PIL image."""
    Image, ImageOps = _pil()
    if isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    elif isinstance(source, (str, Path)):
        img = Image.open(str(source))
    else:
        img = source
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def prepare_image(source, max_side: int = 1024) -> bytes:
    """PNG bytes, scaled so the longest side is at most max_side pixels."""
    Image, _ = _pil()
    img = open_image(source)
    w, h = img.size
    scale = max_side / float(max(w, h))
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    elif max(w, h) < 224:
        # Very small pictures are enlarged a little so the model can see them.
        f = 224 / float(max(w, h))
        img = img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def text_profile(image, lang: str = "eng") -> Optional[Tuple[int, float]]:
    """(words, fraction of the picture covered by words) using Tesseract.

    Returns None when Tesseract isn't available.
    """
    try:
        import pytesseract  # type: ignore

        from . import tesseract_support as ts

        if not ts.configure():
            return None
        img = open_image(image)
        w, h = img.size
        if max(w, h) > 2000:
            f = 2000 / float(max(w, h))
            img = img.resize((int(w * f), int(h * f)))
            w, h = img.size
        data = pytesseract.image_to_data(img, lang=lang or "eng",
                                         output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    words = 0
    area = 0
    for i, txt in enumerate(data.get("text", [])):
        t = (txt or "").strip()
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1
        if conf < 60 or len(re.sub(r"\W", "", t)) < 2:
            continue
        words += 1
        area += int(data["width"][i]) * int(data["height"][i])
    return words, (area / float(w * h)) if w and h else 0.0


def is_mostly_text(image, lang: str = "eng") -> bool:
    """True for pictures of text (scans, screenshots of paragraphs).

    Charts, maps and diagrams have a few labels: little text spread over a
    large picture. Pictures of text are dense with words.
    """
    prof = text_profile(image, lang)
    if prof is None:
        return False  # can't tell; the model answers TEXT for text pictures
    words, coverage = prof
    return words >= 40 and coverage >= 0.15


__all__ = [
    "DEVICES", "VisionSettings", "VisionEngine", "VisionError", "Cancelled", "Description",
    "find_runtime", "find_cuda_runtime", "nvidia_gpus", "cuda_variant", "choose_engine",
    "install_cuda_runtime", "CUDA_VARIANTS", "installed_models", "resolve_model", "available", "unavailable_reason",
    "builtin_catalog", "fetch_catalog", "plan_update", "run_update", "install_runtime",
    "install_model", "remove_user_model", "list_devices", "choose_device", "get_engine",
    "shutdown", "prepare_image", "open_image", "text_profile", "is_mostly_text",
    "user_dir", "bundled_dir", "platform_key", "language_name",
]
