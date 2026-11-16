"""Tesseract OCR management for Document Conversion Suite.

Scanned PDFs contain pictures of text, which screen readers can't read.
Tesseract OCR recognises that text, so the suite can turn an inaccessible
scanned PDF into an accessible document.

This module:

* finds Tesseract (``PDFMD_TESSERACT``, the Windows registry, the standard
  install folders, PATH, then the copy bundled with the suite) and points
  pytesseract and the engine at it, even when it isn't on PATH;
* reports the installed version and languages;
* checks for the latest Windows build (UB Mannheim, the build recommended by
  the Tesseract project for Windows) on GitHub;
* installs or updates Tesseract, with the Windows Package Manager (winget)
  when available, or by downloading the official installer;
* adds OCR languages by downloading trained data from the Tesseract
  project's tessdata repositories into a per-user folder.

Network access happens only when the user asks to check, install or add a
language.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

GITHUB_LATEST = "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
WINGET_ID = "UB-Mannheim.TesseractOCR"
TESSDATA_URLS = {
    "fast": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{code}.traineddata",
    "best": "https://github.com/tesseract-ocr/tessdata_best/raw/main/{code}.traineddata",
}
_USER_AGENT = "DocConversionSuite (Tesseract updater)"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Languages offered for download (Tesseract code, name). Any other code can
# be typed in the language field of the main window once installed.
LANGUAGES: List[Tuple[str, str]] = [
    ("afr", "Afrikaans"), ("amh", "Amharic"), ("ara", "Arabic"), ("asm", "Assamese"),
    ("aze", "Azerbaijani"), ("bel", "Belarusian"), ("ben", "Bengali"), ("bod", "Tibetan"),
    ("bos", "Bosnian"), ("bul", "Bulgarian"), ("cat", "Catalan"), ("ceb", "Cebuano"),
    ("ces", "Czech"), ("chi_sim", "Chinese, Simplified"), ("chi_tra", "Chinese, Traditional"),
    ("chr", "Cherokee"), ("cym", "Welsh"), ("dan", "Danish"), ("deu", "German"),
    ("ell", "Greek"), ("eng", "English"), ("enm", "English, Middle"), ("epo", "Esperanto"),
    ("est", "Estonian"), ("eus", "Basque"), ("fas", "Persian"), ("fin", "Finnish"),
    ("fra", "French"), ("frk", "German Fraktur"), ("gle", "Irish"), ("glg", "Galician"),
    ("grc", "Greek, Ancient"), ("guj", "Gujarati"), ("hat", "Haitian Creole"), ("heb", "Hebrew"),
    ("hin", "Hindi"), ("hrv", "Croatian"), ("hun", "Hungarian"), ("iku", "Inuktitut"),
    ("ind", "Indonesian"), ("isl", "Icelandic"), ("ita", "Italian"), ("jav", "Javanese"),
    ("jpn", "Japanese"), ("kan", "Kannada"), ("kat", "Georgian"), ("kaz", "Kazakh"),
    ("khm", "Khmer"), ("kir", "Kyrgyz"), ("kor", "Korean"), ("lao", "Lao"), ("lat", "Latin"),
    ("lav", "Latvian"), ("lit", "Lithuanian"), ("mal", "Malayalam"), ("mar", "Marathi"),
    ("mkd", "Macedonian"), ("mlt", "Maltese"), ("msa", "Malay"), ("mya", "Burmese"),
    ("nep", "Nepali"), ("nld", "Dutch"), ("nor", "Norwegian"), ("ori", "Odia"),
    ("pan", "Punjabi"), ("pol", "Polish"), ("por", "Portuguese"), ("pus", "Pashto"),
    ("ron", "Romanian"), ("rus", "Russian"), ("san", "Sanskrit"), ("sin", "Sinhala"),
    ("slk", "Slovak"), ("slv", "Slovenian"), ("spa", "Spanish"), ("sqi", "Albanian"),
    ("srp", "Serbian"), ("swa", "Swahili"), ("swe", "Swedish"), ("syr", "Syriac"),
    ("tam", "Tamil"), ("tel", "Telugu"), ("tgk", "Tajik"), ("tgl", "Tagalog"), ("tha", "Thai"),
    ("tir", "Tigrinya"), ("tur", "Turkish"), ("uig", "Uyghur"), ("ukr", "Ukrainian"),
    ("urd", "Urdu"), ("uzb", "Uzbek"), ("vie", "Vietnamese"), ("yid", "Yiddish"),
    ("equ", "Math and equation detection"), ("osd", "Orientation and script detection"),
]
LANGUAGE_NAMES = dict(LANGUAGES)

Progress = Optional[Callable[[int, int], None]]


# ---------------------------------------------------------------------------
# Finding Tesseract
# ---------------------------------------------------------------------------


def _registry_install_dir() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except Exception:
        return None
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Tesseract-OCR", 0,
                                    winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "InstallDir")
                    if value:
                        return str(value)
            except OSError:
                continue
    return None


def find_tesseract() -> Optional[str]:
    """Full path of tesseract(.exe), or None if it isn't installed."""
    env = os.environ.get("PDFMD_TESSERACT")
    if env and Path(env).is_file():
        return env
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    candidates: List[Path] = []
    reg = _registry_install_dir()
    if reg:
        candidates.append(Path(reg) / exe)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA") and str(Path(os.environ["LOCALAPPDATA"]) / "Programs"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Tesseract-OCR" / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    found = shutil.which("tesseract")
    if found:
        return found
    # Fall back to the copy bundled with Document Conversion Suite. A
    # Tesseract the user installs or updates (Ctrl+T) takes priority.
    bundled = bundled_tesseract()
    return str(bundled) if bundled else None


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_tesseract() -> Optional[Path]:
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    for base in (_app_dir(), _app_dir() / "packaging" / "vendor"):
        cand = base / "Tesseract-OCR" / exe
        if cand.is_file():
            return cand
    return None


def is_bundled(path: Optional[str]) -> bool:
    b = bundled_tesseract()
    return bool(path and b and Path(path).resolve() == b.resolve())


def user_tessdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "DocConversionSuite" / "tessdata"


def install_tessdata_dir(tesseract: Optional[str] = None) -> Optional[Path]:
    tesseract = tesseract or find_tesseract()
    if not tesseract:
        return None
    d = Path(tesseract).resolve().parent / "tessdata"
    return d if d.is_dir() else None


def configure(tesseract: Optional[str] = None) -> Optional[str]:
    """Make the engine, pytesseract and OCRmyPDF use the installed Tesseract.

    Adds its folder to PATH for this process, sets pytesseract's command, and
    uses the per-user language folder if languages were added there.
    Returns the Tesseract path or None.
    """
    tesseract = tesseract or find_tesseract()
    if not tesseract:
        return None
    folder = str(Path(tesseract).parent)
    path = os.environ.get("PATH", "")
    if folder.lower() not in [p.lower() for p in path.split(os.pathsep)]:
        os.environ["PATH"] = folder + os.pathsep + path
    try:
        import pytesseract  # type: ignore

        pytesseract.pytesseract.tesseract_cmd = tesseract
    except Exception:
        pass
    user_dir = user_tessdata_dir()
    if any(user_dir.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(user_dir)
    return tesseract


# ---------------------------------------------------------------------------
# Version and languages
# ---------------------------------------------------------------------------


def _run(args: List[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, creationflags=_NO_WINDOW)


def installed_version(tesseract: Optional[str] = None) -> Optional[str]:
    tesseract = tesseract or find_tesseract()
    if not tesseract:
        return None
    try:
        proc = _run([tesseract, "--version"])
        text = (proc.stdout or proc.stderr).decode("utf-8", "replace")
        m = re.search(r"tesseract\s+v?(\d+(?:\.\d+)+(?:[-.][\w.]+)?)", text, re.I)
        return m.group(1) if m else None
    except Exception:
        return None


def list_languages(tesseract: Optional[str] = None) -> List[str]:
    tesseract = tesseract or find_tesseract()
    if not tesseract:
        return []
    try:
        proc = _run([tesseract, "--list-langs"])
        text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        langs = [ln.strip() for ln in text.splitlines()
                 if ln.strip() and not ln.lower().startswith("list of available")]
        return sorted(set(langs))
    except Exception:
        return []


def version_tuple(v: Optional[str]) -> Tuple[int, ...]:
    if not v:
        return ()
    nums = re.findall(r"\d+", v.lstrip("v"))
    return tuple(int(n) for n in nums[:4])


def is_newer(latest: Optional[str], installed: Optional[str]) -> bool:
    return bool(latest) and version_tuple(latest) > version_tuple(installed)


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


@dataclass
class Release:
    version: str
    url: str
    name: str
    size: int
    page: str


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 (fixed https URLs)


def latest_release() -> Release:
    """Latest Windows 64-bit Tesseract installer from UB Mannheim on GitHub."""
    with _get(GITHUB_LATEST) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = str(data.get("tag_name", "")).lstrip("v")
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if "w64-setup" in name and name.lower().endswith(".exe"):
            return Release(tag, asset["browser_download_url"], name,
                           int(asset.get("size", 0)), data.get("html_url", ""))
    raise RuntimeError("No Windows installer found in the latest Tesseract release.")


def winget_available() -> bool:
    return sys.platform == "win32" and shutil.which("winget") is not None


def winget_command(update: bool) -> List[str]:
    verb = "upgrade" if update else "install"
    return ["winget", verb, "--id", WINGET_ID, "--exact", "--source", "winget"]


def download(url: str, dest: Path, progress: Progress = None,
             cancelled: Optional[Callable[[], bool]] = None) -> Path:
    """Download url to dest, reporting (bytes_done, bytes_total)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _get(url, timeout=60) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise RuntimeError("Download cancelled.")
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError("The download was empty.")
    os.replace(tmp, dest)
    return dest


def download_installer(release: Release, progress: Progress = None,
                       cancelled: Optional[Callable[[], bool]] = None) -> Path:
    dest = Path(tempfile.gettempdir()) / "DocConversionSuite" / release.name
    path = download(release.url, dest, progress, cancelled)
    if release.size and path.stat().st_size != release.size:
        path.unlink(missing_ok=True)
        raise RuntimeError("The downloaded installer has the wrong size; please try again.")
    return path


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def prepare_user_tessdata(tesseract: Optional[str] = None) -> Path:
    """Create the per-user language folder, seeded with the installed data.

    Tesseract reads languages from one folder. Program Files usually isn't
    writable, so added languages go to a per-user folder that also holds a
    copy of the installed languages and configuration files.
    """
    user_dir = user_tessdata_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    src = install_tessdata_dir(tesseract)
    if src and not any(user_dir.glob("*.traineddata")):
        for item in src.iterdir():
            target = user_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif item.suffix in (".traineddata", ".txt", ".config") or item.name == "pdf.ttf":
                shutil.copy2(item, target)
    return user_dir


def add_language(code: str, quality: str = "fast", tesseract: Optional[str] = None,
                 progress: Progress = None) -> Path:
    """Download one language's trained data into the per-user folder."""
    if not re.fullmatch(r"[a-z_]{3,12}", code):
        raise ValueError(f"Not a Tesseract language code: {code!r}")
    user_dir = prepare_user_tessdata(tesseract)
    url = TESSDATA_URLS.get(quality, TESSDATA_URLS["fast"]).format(code=code)
    dest = download(url, user_dir / f"{code}.traineddata", progress)
    os.environ["TESSDATA_PREFIX"] = str(user_dir)
    return dest


def language_label(code: str) -> str:
    name = LANGUAGE_NAMES.get(code)
    return f"{name} ({code})" if name else code


__all__ = [
    "LANGUAGES",
    "Release",
    "find_tesseract",
    "configure",
    "installed_version",
    "list_languages",
    "latest_release",
    "is_newer",
    "winget_available",
    "winget_command",
    "download_installer",
    "add_language",
    "language_label",
    "user_tessdata_dir",
]
