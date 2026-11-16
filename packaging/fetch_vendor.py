"""Download and verify the third-party programs bundled with the installer.

Document Conversion Suite ships three separate programs next to its own
executables:

* pandoc (GPL-2.0-or-later), from the official GitHub release,
* Tesseract OCR (Apache-2.0), the UB Mannheim Windows build, plus trained
  OCR data for 17 common languages from the Tesseract project's
  tessdata_fast repository, and
* the picture-description engine: llama.cpp's llama-server (MIT), Vulkan
  build for Windows x64, with the default vision model from
  vision-models.json (Apache-2.0 weights, GGUF).

Every file is checked against a published checksum before it is used:
pandoc's SHA-256 from its GitHub release, the Tesseract installer's SHA-256
from the Windows Package Manager manifest, each language file's git blob
hash from the tessdata_fast repository, and the llama.cpp release and model
files' SHA-256 from vision-models.json (taken from the GitHub release and
Hugging Face file listings).

Usage:  python packaging/fetch_vendor.py
Output: packaging/vendor/pandoc/, packaging/vendor/Tesseract-OCR/ and
        packaging/vendor/vision/
Needs 7-Zip (7z.exe) to unpack the Tesseract installer.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
CACHE = VENDOR / "downloads"

PANDOC_VERSION = "3.13"
PANDOC_URL = (f"https://github.com/jgm/pandoc/releases/download/{PANDOC_VERSION}/"
              f"pandoc-{PANDOC_VERSION}-windows-x86_64.zip")
PANDOC_SHA256 = "23e1f2e978a3df80db8bf65c9c59534f41a23140480cfb4f783a882ab7dc6a4e"

TESSERACT_VERSION = "5.4.0.20240606"
TESSERACT_URL = (f"https://github.com/UB-Mannheim/tesseract/releases/download/v{TESSERACT_VERSION}/"
                 f"tesseract-ocr-w64-setup-{TESSERACT_VERSION}.exe")
TESSERACT_SHA256 = "c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9"

TESSDATA_REF = "4.1.0"
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/{ref}/{name}"
# Language files and their git blob SHA-1 at tag 4.1.0 of tessdata_fast.
LANGS = ["eng", "osd", "deu", "fra", "spa", "ita", "por", "nld", "pol", "rus",
         "chi_sim", "chi_tra", "jpn", "kor", "ara", "hin", "tur", "vie"]
TESSDATA_BLOBS = {
    "eng.traineddata": "bbef4675053b5b468cdb477053e28b1c698ba08e",
    "osd.traineddata": "527457ca8f8fe1fda7c2f88bce3c0e4be12be9d0",
    "deu.traineddata": "97ed7b2b60f2771c07040660ef0f6daf596dc7bf",
    "fra.traineddata": "d9e2b2160be0d1ca3b8f1bf2730fae476ef3b4a6",
    "spa.traineddata": "72e901f13ca52cfe34cf239a368b9ed3c0ddaf26",
    "ita.traineddata": "edbffbe0e51892b240630b5eeabededa7e7c9c4f",
    "por.traineddata": "e9f373e95c66b4bf557c263721ef31f78e5bc301",
    "nld.traineddata": "53ce95a9c2488a9a0228939944a184157373d0ae",
    "pol.traineddata": "2382f568f0ce0c4c0a7f4380a291255514e5e97f",
    "rus.traineddata": "b146cb2263acbc6383f8e92ea0ce759537687bb8",
    "chi_sim.traineddata": "388bac276d033d06e5ed5ba7a7ad14ae58f97dab",
    "chi_tra.traineddata": "1955cd8b8d076b898616e9c2c1ace65b43105356",
    "jpn.traineddata": "c4178f89991bde90b7fdc647e3e1901868423bd0",
    "kor.traineddata": "60986d44497689f3abace0b148199476d93292e1",
    "ara.traineddata": "c8d129c67821c1592cac46836686b057ecc203dc",
    "hin.traineddata": "a8f0aaec09378115b12a2c6287c57695d082aea2",
    "tur.traineddata": "1f0b331ef29f50ceb7c44da58e38c7ec42314d0a",
    "vie.traineddata": "e54a5912fb634c581c4a45ae9f37cbc021ec7140",
}

UA = {"User-Agent": "DocConversionSuite build"}


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers=UA)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh, 1024 * 1024)
    os.replace(tmp, dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 (git object id)


def verify(path: Path, expected: str, kind: str = "sha256") -> None:
    actual = sha256(path) if kind == "sha256" else git_blob_sha1(path)
    if actual.lower() != expected.lower():
        path.unlink(missing_ok=True)
        sys.exit(f"Checksum mismatch for {path.name}: expected {expected}, got {actual}")
    print(f"  verified {path.name} ({kind})")


def find_7z() -> str:
    for c in (shutil.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if c and Path(c).is_file():
            return c
    sys.exit("7-Zip (7z.exe) is needed to unpack the Tesseract installer.")


def tessdata_blob_hashes() -> dict:
    """Git blob hashes of the language files, from the GitHub API."""
    import json
    url = f"https://api.github.com/repos/tesseract-ocr/tessdata_fast/contents?ref={TESSDATA_REF}"
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        items = json.loads(resp.read().decode("utf-8"))
    return {it["name"]: it["sha"] for it in items if it["name"].endswith(".traineddata")}


def build_pandoc() -> None:
    print("pandoc")
    z = fetch(PANDOC_URL, CACHE / Path(PANDOC_URL).name)
    verify(z, PANDOC_SHA256)
    out = VENDOR / "pandoc"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if info.is_dir() or not name:
                continue
            with zf.open(info) as src, open(out / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
    print(f"  -> {out} ({len(list(out.iterdir()))} files)")


def build_tesseract() -> None:
    print("Tesseract OCR")
    exe = fetch(TESSERACT_URL, CACHE / Path(TESSERACT_URL).name)
    verify(exe, TESSERACT_SHA256)
    work = VENDOR / "tesseract-unpacked"
    shutil.rmtree(work, ignore_errors=True)
    subprocess.run([find_7z(), "x", "-y", f"-o{work}", str(exe)], check=True,
                   stdout=subprocess.DEVNULL)
    out = VENDOR / "Tesseract-OCR"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for item in work.iterdir():
        if item.name.startswith("$") or item.name.lower() in ("uninstall.exe",):
            continue  # NSIS plug-ins and installer leftovers
        target = out / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    shutil.rmtree(work, ignore_errors=True)
    if not (out / "tesseract.exe").is_file():
        sys.exit("tesseract.exe not found after unpacking the installer.")
    # Keep only what OCR needs at run time: tesseract.exe, its DLLs, the
    # language data and the documentation/licence. Training tools, their
    # manual pages and the Java viewer are left out.
    for item in out.iterdir():
        if item.is_file() and item.name.lower() != "tesseract.exe" and item.suffix.lower() in (".exe", ".html"):
            item.unlink()
    for jar in (out / "tessdata").glob("*.jar"):
        jar.unlink()

    tessdata = out / "tessdata"
    tessdata.mkdir(exist_ok=True)
    blobs = TESSDATA_BLOBS or tessdata_blob_hashes()
    for lang in LANGS:
        name = f"{lang}.traineddata"
        cached = CACHE / "tessdata_fast" / name
        fetch(TESSDATA_URL.format(ref=TESSDATA_REF, name=name), cached)
        verify(cached, blobs[name], kind="git-blob")
        shutil.copy2(cached, tessdata / name)
    print(f"  -> {out}")


def build_vision() -> None:
    """llama.cpp engine + the recommended vision model, as vision/ in the app."""
    import json

    print("Vision model")
    catalog = json.loads((ROOT.parent / "vision-models.json").read_text(encoding="utf-8"))
    rt = catalog["runtime"]
    asset = rt["assets"]["windows-x64"]
    z = fetch(rt["url_base"] + asset["file"], CACHE / "llama" / asset["file"])
    verify(z, asset["sha256"])
    out = VENDOR / "vision"
    runtime = out / "runtime"
    shutil.rmtree(runtime, ignore_errors=True)
    runtime.mkdir(parents=True)
    keep_exe = {"llama-server.exe"}
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if info.is_dir() or not name:
                continue
            # Only the server and its libraries; the other llama.cpp tools
            # are not needed.
            if name.lower().endswith(".exe") and name.lower() not in keep_exe:
                continue
            if name.lower().endswith("-impl.dll") and not name.lower().startswith("llama-server"):
                continue
            with zf.open(info) as src, open(runtime / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
    rec = catalog["recommended"]
    entry = next(m for m in catalog["models"] if m["id"] == rec)
    mdir = out / "models" / rec
    shutil.rmtree(out / "models", ignore_errors=True)
    mdir.mkdir(parents=True)
    for role in ("model", "mmproj"):
        f = entry["files"][role]
        cached = fetch(f["url"], CACHE / "models" / f["file"])
        verify(cached, f["sha256"])
        shutil.copy2(cached, mdir / f["file"])
    manifest = {
        "runtime_build": rt["build"],
        "models": {rec: {"name": entry["name"], "revision": entry["revision"],
                         "license": entry.get("license", ""), "base": entry.get("base", ""),
                         "files": {"model": entry["files"]["model"]["file"],
                                   "mmproj": entry["files"]["mmproj"]["file"]},
                         "server_args": entry.get("server_args") or []}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copy2(ROOT.parent / "vision-models.json", out / "vision-models.json")
    print(f"  -> {out}")


def main() -> None:
    VENDOR.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    if not only or "pandoc" in only:
        build_pandoc()
    if not only or "tesseract" in only:
        build_tesseract()
    if not only or "vision" in only:
        build_vision()
    print("Vendor programs ready.")


if __name__ == "__main__":
    main()
