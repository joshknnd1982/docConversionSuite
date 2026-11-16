"""Build the Document Conversion Suite Windows release (executables + installer).

Usage (from the repository root, on Windows):

    python -m pip install -r requirements.txt pyinstaller
    python packaging/build.py

Steps:
1. Render README.md, ACCESSIBILITY.md and FEATURES.md to accessible HTML
   (installed next to the Markdown files and linked from the Start menu).
2. Write the Windows version resource for the executables.
3. Run PyInstaller (packaging/pdfmd.spec) -> dist/DocConversionSuite/ with DocConversionSuite.exe
   (GUI) and pdfmd-cli.exe (command line).
4. Copy the bundled pandoc, Tesseract OCR and the vision model (llama.cpp
   engine + default model; packaging/fetch_vendor.py downloads and verifies
   them if they aren't there yet).
5. Run Inno Setup (packaging/installer.iss) -> dist/installer/
   DocConversionSuite-<version>-setup.exe.

Inno Setup 6 must be installed. Set ISCC to the full path of ISCC.exe if
it isn't in a standard location.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
BUILD = PKG / "build"
DIST = ROOT / "dist"

sys.path.insert(0, str(ROOT))
from pdfmd import __version__  # noqa: E402
from pdfmd.mathjax import markdown_to_accessible_html  # noqa: E402


def find_iscc() -> str:
    env = os.environ.get("ISCC")
    candidates = [env] if env else []
    for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs",
                 os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        candidates.append(str(Path(base) / "Inno Setup 6" / "ISCC.exe"))
    for c in candidates:
        if c and Path(c).is_file():
            return c
    found = shutil.which("iscc")
    if found:
        return found
    sys.exit("Inno Setup 6 (ISCC.exe) not found. Install it or set ISCC.")


def render_docs() -> Path:
    out = BUILD / "docs"
    out.mkdir(parents=True, exist_ok=True)
    for name, title in (("README.md", "Document Conversion Suite Read Me"),
                        ("ACCESSIBILITY.md", "Document Conversion Suite Accessibility Guide"),
                        ("FEATURES.md", "Document Conversion Suite Features Guide")):
        md = (ROOT / name).read_text(encoding="utf-8")
        html = markdown_to_accessible_html(md, title=title, lang="en", with_mathjax=False)
        (out / name.replace(".md", ".html")).write_text(html, encoding="utf-8")
        print(f"  rendered {name}")
    return out


def write_version_info() -> None:
    parts = [int(p) for p in __version__.split(".")[:3]] + [0]
    while len(parts) < 4:
        parts.append(0)
    v = tuple(parts[:4])
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Josh Kennedy'),
      StringStruct('FileDescription', 'Document Conversion Suite'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'DocConversionSuite'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'DocConversionSuite.exe'),
      StringStruct('ProductName', 'Document Conversion Suite'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "version_info.txt").write_text(text, encoding="utf-8")


def main() -> None:
    print(f"Building Document Conversion Suite {__version__}")
    for d in (DIST / "DocConversionSuite", BUILD / "pyinstaller"):
        shutil.rmtree(d, ignore_errors=True)

    print("1. Rendering documentation")
    docs = render_docs()
    print("2. Writing version resource")
    write_version_info()

    print("3. Running PyInstaller")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
         str(PKG / "pdfmd.spec")],
        check=True, cwd=ROOT,
    )

    print("4. Adding bundled pandoc, Tesseract OCR and the vision model")
    vendor = PKG / "vendor"
    missing = [name for name, exe in (("pandoc", "pandoc/pandoc.exe"),
                                      ("tesseract", "Tesseract-OCR/tesseract.exe"),
                                      ("vision", "vision/runtime/llama-server.exe"))
               if not (vendor / exe).is_file()]
    if missing:
        subprocess.run([sys.executable, str(PKG / "fetch_vendor.py"), *missing], check=True, cwd=ROOT)
    app_dir = DIST / "DocConversionSuite"
    for name in ("pandoc", "Tesseract-OCR", "vision"):
        shutil.copytree(vendor / name, app_dir / name, dirs_exist_ok=True)
    shutil.copy2(ROOT / "vision-models.json", app_dir / "vision-models.json")
    shutil.copy2(PKG / "THIRD-PARTY-NOTICES.txt", app_dir / "THIRD-PARTY-NOTICES.txt")

    print("5. Running Inno Setup")
    (DIST / "installer").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [find_iscc(), f"/DAppVersion={__version__}", f"/DSourceDir={DIST / 'DocConversionSuite'}",
         f"/DDocsDir={docs}", f"/DOutputDir={DIST / 'installer'}", str(PKG / "installer.iss")],
        check=True, cwd=PKG,
    )
    setup = DIST / "installer" / f"DocConversionSuite-{__version__}-setup.exe"
    print(f"Done: {setup} ({setup.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
