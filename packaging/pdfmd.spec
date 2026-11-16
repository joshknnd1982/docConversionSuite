# PyInstaller spec for Document Conversion Suite: builds DocConversionSuite.exe (GUI) and
# pdfmd-cli.exe (command line) into one folder that shares a single runtime.
#
# Build with:  python packaging/build.py
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is set by PyInstaller)

datas, binaries, hiddenimports = [], [], []
# accessible_output2 ships the NVDA / JAWS / Dolphin / ZoomText client DLLs
# it uses to talk to screen readers.
for pkg in ("accessible_output2", "libloader", "platform_utils", "pillow_heif"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("pdfmd")
hiddenimports += [
    "win32com", "win32com.client", "win32com.client.gencache", "pywintypes",
    "pytesseract", "PIL", "markdown", "markdown.extensions.tables",
    "markdown.extensions.fenced_code", "markdown.extensions.sane_lists",
    "pillow_heif",
]

common = dict(
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy.tests", "pytest"],
    noarchive=False,
)

gui_a = Analysis([str(ROOT / "packaging" / "pdfmd_gui_entry.py")], **common)  # noqa: F821
cli_a = Analysis([str(ROOT / "packaging" / "pdfmd_cli_entry.py")], **common)  # noqa: F821

gui_pyz = PYZ(gui_a.pure)  # noqa: F821
cli_pyz = PYZ(cli_a.pure)  # noqa: F821

version_file = str(ROOT / "packaging" / "build" / "version_info.txt")

gui_exe = EXE(  # noqa: F821
    gui_pyz, gui_a.scripts, [],
    exclude_binaries=True,
    name="DocConversionSuite",
    console=False,
    version=version_file,
    upx=False,
)
cli_exe = EXE(  # noqa: F821
    cli_pyz, cli_a.scripts, [],
    exclude_binaries=True,
    name="pdfmd-cli",
    console=True,
    version=version_file,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    gui_exe, gui_a.binaries, gui_a.datas,
    cli_exe, cli_a.binaries, cli_a.datas,
    upx=False,
    name="DocConversionSuite",
)
