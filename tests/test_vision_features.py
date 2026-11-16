"""Tests for picture descriptions that don't need the vision model.

Run with:  python -m pytest tests
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmd import docimages, vision  # noqa: E402
from pdfmd.figures import add_figures, figure_markdown, scanned_picture_regions  # noqa: E402
from pdfmd.models import Block, Figure, Options, PageText  # noqa: E402
from pdfmd.render import render_document  # noqa: E402

fitz = pytest.importorskip("pymupdf")


# ------------------------------------------------------------- answers


def test_parse_answer_strips_markdown_lists_and_limits_length():
    d = vision.parse_answer("- **Bar chart** of sales. It rose. Then more. And more. And yet more.",
                            "document")
    assert d.kind == "picture"
    assert d.text == "Bar chart of sales. It rose. Then more."


def test_parse_answer_verdicts():
    assert vision.parse_answer("TEXT", "document").kind == "text"
    assert vision.parse_answer("DECORATIVE.", "document").kind == "decorative"
    assert vision.parse_answer("", "document").kind == "text"


def test_clean_text_removes_stock_openings_and_leading_punctuation():
    assert vision.clean_text(", a bar chart, showing x") == "A bar chart, showing x"
    assert vision.clean_text("The image shows a red car.") == "A red car."
    assert vision.clean_text("This is a map of Spain.") == "A map of Spain."


@pytest.mark.parametrize("raw,expected", [
    ("Title: Sunset Over a Calm Lake", "Sunset Over a Calm Lake"),
    ("The title only is: Deep Blue Glow", "Deep Blue Glow"),
    ("The title only, without quotation marks", ""),
    ("Based on the description provided, the image", ""),
    ('"Warm Orb Glow."', "Warm Orb Glow"),
])
def test_clean_title(raw, expected):
    assert vision.clean_title(raw) == expected


def test_settings_round_trip_and_device_names():
    s = vision.VisionSettings.from_dict({"enabled": False, "device": "dev:Vulkan1", "model_id": "m"})
    assert (s.enabled, s.device, s.model_id) == (False, "dev:Vulkan1", "m")
    assert vision.VisionSettings.from_dict({"device": "bogus"}).device == "auto"


def test_integrated_gpu_detection():
    assert vision.Device("Vulkan1", "AMD Radeon 780M Graphics", 16000, 15000).integrated
    assert vision.Device("Vulkan0", "Intel(R) Iris(R) Xe Graphics", 8000, 7000).integrated
    assert not vision.Device("Vulkan0", "NVIDIA GeForce RTX 4060", 8000, 7000).integrated
    assert not vision.Device("MTL0", "Apple M2", 16000, 12000).integrated


def test_auto_skips_integrated_gpu_but_gpu_mode_uses_it():
    igpu = vision.Device("Vulkan0", "Intel(R) UHD Graphics 620", 4000, 3500)
    assert vision._best_gpu([igpu], allow_integrated=False, need_mib=2500) is None
    assert vision._best_gpu([igpu], allow_integrated=True, need_mib=2500) is igpu


def test_catalog_is_complete():
    cat = vision.builtin_catalog()
    assert cat["recommended"] in [m["id"] for m in cat["models"]]
    for m in cat["models"]:
        for role in ("model", "mmproj"):
            f = m["files"][role]
            assert len(f["sha256"]) == 64 and f["url"].startswith("https://") and f["size"] > 0
    assert "windows-x64" in cat["runtime"]["assets"]


# ------------------------------------------------------------- markdown


def test_figure_markdown_alt_text_or_block_quote():
    fig = Figure(page=0, alt="A bar chart of sales [2021-2024].", status="described")
    assert figure_markdown(fig) == ["> **Image description:** A bar chart of sales [2021-2024].", ""]
    fig.asset = "doc_assets/figure_001_01.png"
    assert figure_markdown(fig)[0] == "![A bar chart of sales (2021-2024).](doc_assets/figure_001_01.png)"
    ocr = Figure(page=0, alt="Meeting on *Monday*", status="ocr")
    assert figure_markdown(ocr)[0] == r"> **Text in image:** Meeting on \*Monday\*"
    assert figure_markdown(Figure(status="decorative")) == []


def test_render_keeps_image_lines_and_chart_labels():
    described = Block(figure=Figure(alt="A photo of a lake.", status="described", asset="a/x.png"))
    label = PageText.from_pymupdf({"blocks": [{"lines": [{"spans": [{"text": "Units sold", "size": 9}]}]}]}).blocks
    skipped = Block(figure=Figure(status="skipped", labels=label))
    para = PageText.from_pymupdf({"blocks": [{"lines": [{"spans": [{"text": "We went to a lake.",
                                                                      "size": 11}]}]}]}).blocks[0]
    md = render_document([PageText(blocks=[para, described, skipped])], Options())
    assert "We went to a lake.\n\n![A photo of a lake.](a/x.png)" in md
    assert "Units sold" in md  # labels of an undescribed chart stay in the text


# ------------------------------------------------------------- PDF figures


def _test_pdf() -> "fitz.Document":
    from PIL import Image

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Report", fontsize=20)
    buf = io.BytesIO()
    Image.new("RGB", (400, 250), (30, 120, 200)).save(buf, "PNG")
    page.insert_image(fitz.Rect(72, 100, 372, 287), stream=buf.getvalue())
    x0, y0 = 110, 600
    page.draw_line((x0, y0), (x0 + 300, y0))
    page.draw_line((x0, y0), (x0, y0 - 190))
    for i, (v, c) in enumerate(zip((40, 75, 120, 160), ((0.2, 0.4, 0.8), (0.9, 0.5, 0.1),
                                                         (0.2, 0.7, 0.3), (0.8, 0.2, 0.3)))):
        bx = x0 + 20 + i * 70
        page.draw_rect(fitz.Rect(bx, y0 - v, bx + 45, y0), color=c, fill=c)
        page.insert_text((bx + 8, y0 + 14), str(2021 + i), fontsize=9)
    page.insert_text((72, 660), "Figure 2: Sales by year.", fontsize=9)
    icon = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 0, 0)).save(icon, "PNG")
    page.insert_image(fitz.Rect(72, 700, 84, 712), stream=icon.getvalue())
    return doc


def test_add_figures_finds_photo_and_drawn_chart_but_not_icon():
    doc = _test_pdf()
    page = doc[0]
    info = add_figures(page, page.get_text("dict"), 0, set())
    figs = [b for b in info["blocks"] if b.get("type") == "pdfmd_figure"]
    assert [f["figure"].kind for f in figs] == ["raster", "vector"]
    chart = figs[1]
    # The year labels under the axis belong to the chart...
    assert chart["bbox"][3] > 600 + 10
    labels = " ".join(sp["text"] for b in chart["labels"] for ln in b["lines"] for sp in ln["spans"])
    assert "2021" in labels and "2024" in labels
    # ...and the caption is passed to the model as context, not swallowed.
    assert "Figure 2" in chart["figure"].context
    text = page.get_text("text")
    assert "Figure 2" in text
    # The figure comes before the caption in reading order.
    order = [b.get("type", "text") for b in info["blocks"]]
    assert order.index("pdfmd_figure") < len(order) - 1


def test_scanned_picture_regions():
    data = {"level": [1, 2, 5, 2], "block_num": [0, 1, 1, 2], "left": [0, 50, 60, 100],
            "top": [0, 50, 60, 400], "width": [1000, 900, 50, 600], "height": [1400, 100, 20, 500],
            "text": ["", "", "Hello", ""]}
    assert scanned_picture_regions(data, 1000, 1400) == [(100, 400, 700, 900)]


# ------------------------------------------------------------- pandoc AST


def _img(src, alt=""):
    return {"t": "Image", "c": [["", [], []], docimages.to_inlines(alt), [src, ""]]}


def test_needs_description():
    assert docimages.needs_description("", "a.png")
    assert docimages.needs_description("image1", "a.png")
    assert docimages.needs_description("IMG_2041.JPG", "IMG_2041.JPG")
    assert not docimages.needs_description("Our team at the summit", "a.png")


def test_text_only_outputs_get_block_quotes():
    ast = {"blocks": [
        {"t": "Para", "c": docimages.to_inlines("Look:") + [{"t": "Space"}, _img("a.png")]},
        {"t": "Figure", "c": [["", [], []], [None, [{"t": "Plain", "c": docimages.to_inlines("image1")}]],
                              [{"t": "Plain", "c": [_img("b.png", "A red car parked by a beach")]}]]},
    ]}
    results = {"a.png": (docimages.DESCRIPTION_LABEL, "A lake at sunset.")}
    out = docimages._captions_for_text_output(ast["blocks"], results)
    texts = [docimages.stringify(b) for b in out]
    assert texts == ["Look:", "Image description: A lake at sunset.",
                     "Image description: A red car parked by a beach"]
    assert [b["t"] for b in out] == ["Para", "BlockQuote", "BlockQuote"]


def test_generic_figure_captions_are_cleared():
    fig = {"t": "Figure", "c": [["", [], []], [None, [{"t": "Plain", "c": docimages.to_inlines("image1")}]],
                                [{"t": "Plain", "c": [_img("b.png")]}]]}
    docimages._clear_generic_captions([fig], {"b.png": ("Image description", "A car.")})
    assert fig["c"][1] == [None, []]


def test_remote_pictures_are_never_fetched(tmp_path):
    assert docimages.load_image_bytes("https://example.com/x.png", [tmp_path]) is None
    (tmp_path / "x.png").write_bytes(b"png")
    assert docimages.load_image_bytes("x.png", [tmp_path]) == b"png"


# ------------------------------------------------------------- review fixes


def test_large_confident_text_block_is_not_a_picture():
    data = {"level": [2, 5, 5, 2], "block_num": [1, 1, 1, 2], "left": [100, 110, 300, 100],
            "top": [100, 110, 110, 600], "width": [800, 150, 150, 600], "height": [200, 80, 80, 400],
            "text": ["", "BIG", "STAMP", ""], "conf": [-1, 95, 94, -1]}
    assert scanned_picture_regions(data, 1000, 1400) == [(100, 600, 700, 1000)]


def test_cli_device_names_are_case_insensitive():
    from pdfmd.cli import _device_code

    assert _device_code("CPU") == "cpu"
    assert _device_code("Vulkan1") == "dev:Vulkan1"
    assert _device_code("dev:CUDA0") == "dev:CUDA0"


def test_file_urls_and_document_folder_first(tmp_path):
    (tmp_path / "pic.png").write_bytes(b"x")
    assert docimages.load_image_bytes((tmp_path / "pic.png").as_uri(), []) == b"x"
    assert docimages.load_image_bytes("pic.png", [tmp_path]) == b"x"


def test_hold_and_release_keep_the_engine_for_other_windows(monkeypatch):
    stopped = []
    monkeypatch.setattr(vision, "shutdown", lambda: stopped.append(True))
    vision.hold()
    vision.hold()
    vision.release()
    assert stopped == []          # another window still uses it
    vision.release()
    assert stopped == [True]


# ------------------------------------------------------------- CUDA / Vulkan / CPU


@pytest.mark.parametrize("driver,cc,platform_name,expected", [
    ("581.15", 8.9, "win32", "cuda13"),     # new driver, RTX 40
    ("572.97", 12.0, "win32", "cuda12"),    # RTX 50 on a driver older than 580
    ("581.15", 6.1, "win32", "cuda12"),     # GTX 10 series: CUDA 13 dropped it
    ("516.94", 8.6, "win32", ""),           # driver too old for CUDA 12.4
])
def test_cuda_variant(monkeypatch, driver, cc, platform_name, expected):
    monkeypatch.setattr(vision, "nvidia_gpus", lambda: [vision.NvidiaGpu("GPU", cc, driver, 8000, 7000)])
    monkeypatch.setattr(vision.sys, "platform", platform_name)
    assert vision.cuda_variant() == expected


def test_no_nvidia_means_no_cuda(monkeypatch):
    monkeypatch.setattr(vision, "nvidia_gpus", lambda: [])
    assert vision.cuda_variant() == ""


def test_device_codes_for_cuda_and_vulkan():
    from pdfmd.cli import _device_code

    assert _device_code("CUDA") == "cuda"
    assert _device_code("vulkan") == "gpu"
    assert vision.VisionSettings.from_dict({"device": "vulkan"}).device == "gpu"
    assert vision.VisionSettings.from_dict({"device": "cuda"}).device == "cuda"


def test_catalog_has_cuda_engines_with_checksums():
    cuda = vision.builtin_catalog()["runtime"]["cuda"]
    for variant in ("cuda12", "cuda13"):
        files = cuda[variant]["assets"]["windows-x64"]
        assert len(files) == 2 and all(len(f["sha256"]) == 64 and f["size"] > 0 for f in files)
