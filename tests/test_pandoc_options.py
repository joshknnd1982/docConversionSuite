"""Tests for the pandoc option table and the pandoc command lines built from it.

Run with:  python -m pytest tests
Tests that run pandoc are skipped when pandoc isn't installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmd import pandoc_options as po  # noqa: E402
from pdfmd import pandoc_support as ps  # noqa: E402

PANDOC = ps.find_pandoc()
needs_pandoc = pytest.mark.skipif(not PANDOC, reason="pandoc is not installed")


def _sample(spec: po.OptionSpec):
    """A value that differs from the option's default."""
    if spec.kind == po.SWITCH:
        return not spec.default
    if spec.kind == po.NUMBER:
        return spec.default + 1 if spec.default < spec.maximum else spec.minimum
    if spec.kind == po.CHOICE:
        return [v for v, _ in spec.choices if v not in ("", spec.default)][-1]
    if spec.kind == po.PAIRS:
        return "key=value"
    return "sample.txt"


def _formats(spec: po.OptionSpec):
    to = sorted(spec.outputs)[0] if spec.outputs else "html"
    if to in spec.exclude_outputs:
        to = "markdown"
    fr = sorted(spec.inputs)[0] if spec.inputs else "markdown"
    return to, fr


def test_table_is_well_formed():
    keys = [s.key for s in po.OPTIONS]
    assert len(keys) == len(set(keys)), "option keys must be unique"
    pages = {p for p, _ in po.PAGES}
    for s in po.OPTIONS:
        assert s.kind in po.KINDS, s.key
        assert s.page in pages, s.key
        assert s.label and s.help, s.key
        assert "&" not in s.label, "access keys are assigned by the window"
        assert s.special or s.flag.startswith("--"), s.key
        if s.kind == po.CHOICE:
            assert s.choices or s.special, s.key
        if s.kind in (po.FILE, po.SAVEFILE, po.FILES, po.FOLDER):
            assert s.button, f"{s.key} needs a Choose button label"


@pytest.mark.parametrize("spec", [s for s in po.OPTIONS if not s.special],
                         ids=lambda s: s.key)
def test_every_option_reaches_the_command_line(spec):
    opts = ps.PandocOptions()
    to, fr = _formats(spec)
    opts.to_format = to
    po.set_value(opts, spec, _sample(spec))
    args = ps.build_args("pandoc", Path("in.md"), Path("out.x"), opts, fr, flags=None)
    assert any(a == spec.flag or a.startswith(spec.flag + "=") for a in args), (spec.key, args)


def test_defaults_add_no_options():
    opts = ps.PandocOptions(to_format="html")
    assert po.generic_args(opts, "html", "markdown") == []
    for spec in po.OPTIONS:
        if not spec.special:
            assert po.option_args(spec, spec.default) == [], spec.key


def test_options_for_other_formats_are_left_out():
    opts = ps.PandocOptions(to_format="html")
    opts.values["epub_cover_image"] = "cover.png"
    opts.values["reference_links"] = True
    opts.reference_doc = "styles.docx"
    args = ps.build_args("pandoc", Path("in.md"), Path("out.html"), opts, "markdown", flags=None)
    joined = " ".join(args)
    assert "--epub-cover-image" not in joined
    assert "--reference-links" not in joined
    assert "--reference-doc" not in joined


def test_options_the_running_pandoc_lacks_are_left_out():
    opts = ps.PandocOptions(to_format="docx")
    opts.values["lof"] = True
    opts.highlight_style = "none"
    old = {"standalone", "toc", "metadata", "highlight-style", "no-highlight"}
    args = ps.build_args("pandoc", Path("in.md"), Path("out.docx"), opts, "markdown", flags=old)
    assert "--lof" not in args
    assert "--no-highlight" in args          # pandoc before 3.8
    args = ps.build_args("pandoc", Path("in.md"), Path("out.docx"), opts, "markdown",
                         flags=old | {"lof", "syntax-highlighting"})
    assert "--lof" in args
    assert "--syntax-highlighting=none" in args


def test_switch_that_pandoc_turns_on_by_default_is_turned_off_explicitly():
    spec = po.BY_KEY["epub_title_page"]
    assert po.option_args(spec, False) == ["--epub-title-page=false"]
    assert po.option_args(spec, True) == []


def test_lists_and_pairs_repeat_the_flag():
    assert po.option_args(po.BY_KEY["css"], "a.css; b.css") == ["--css=a.css", "--css=b.css"]
    assert po.option_args(po.BY_KEY["metadata"], "author=Ada\n\ndate=2026") == [
        "--metadata=author=Ada", "--metadata=date=2026"]


def test_reader_options_only_in_the_reading_pass():
    opts = ps.PandocOptions(to_format="html")
    opts.values["track_changes"] = "all"
    write = ps.build_args("pandoc", None, Path("o.html"), opts, "json", include_reader=False,
                          flags=None)
    assert "--track-changes=all" not in write
    assert "--track-changes=all" in ps.reader_args(opts, "docx")
    assert "--track-changes=all" not in ps.reader_args(opts, "odt")


def test_extensions():
    assert po.extension_suffix({"styles": True, "citations": False}) == "-citations+styles"
    opts = ps.PandocOptions(to_format="docx")
    opts.out_extensions["docx"] = {"styles": True}
    opts.in_extensions["markdown"] = {"smart": False}
    args = ps.build_args("pandoc", Path("in.md"), Path("o.docx"), opts, "markdown", flags=None)
    assert args[args.index("--to") + 1] == "docx+styles"
    assert args[args.index("--from") + 1] == "markdown-smart"
    assert po.parse_extensions("+smart -styles\n+raw_tex") == [
        ("smart", True), ("styles", False), ("raw_tex", True)]


def test_citation_methods():
    opts = ps.PandocOptions(to_format="latex", bibliography="refs.bib")
    args = ps.build_args("pandoc", Path("in.md"), Path("o.tex"), opts, "markdown", flags=None)
    assert "--citeproc" in args                      # a bibliography means citeproc
    opts.values["citation_method"] = "natbib"
    args = ps.build_args("pandoc", Path("in.md"), Path("o.tex"), opts, "markdown", flags=None)
    assert "--natbib" in args and "--citeproc" not in args
    old = ps.PandocOptions.from_dict({"citeproc": True})
    assert old.citation_method() == "citeproc"


def test_defaults_file_comes_first():
    opts = ps.PandocOptions(to_format="html")
    opts.values["defaults_file"] = "my.yaml"
    args = ps.build_args("pandoc", Path("in.md"), Path("o.html"), opts, "markdown", flags=None)
    assert args[1] == "--defaults=my.yaml"


def test_old_settings_still_load():
    old = {"to_format": "epub", "toc": True, "toc_depth": 2, "highlight_style": "tango",
           "unknown_option": 5, "values": "not a dict"}
    o = ps.PandocOptions.from_dict(old)
    assert o.to_format == "epub" and o.toc and o.toc_depth == 2
    assert o.values == {}
    o.values["lof"] = True
    o.in_extensions["docx"] = {"styles": True}
    again = ps.PandocOptions.from_dict(o.to_dict())
    assert again.values == {"lof": True}
    assert again.in_extensions == {"docx": {"styles": True}}


def test_access_keys_are_unique():
    labels = ["Title", "Table of contents", "Template", "&Output format", "T", "Choose..."]
    keyed = po.assign_access_keys(labels, reserved="VFP")
    keys = [k.split("&")[1][0].lower() for k in keyed]
    assert len(keys) == len(set(keys))
    assert not set(keys) & set("vfp")
    assert keyed[3] == "&Output format"
    for page, _ in po.PAGES:
        specs = [s for s in po.OPTIONS if s.page == page]
        labels = [s.label for s in specs] + [s.button for s in specs if s.button]
        keyed = po.assign_access_keys(labels, reserved="VFP")
        keys = [k.split("&")[1][0].lower() for k in keyed]
        assert len(keys) == len(set(keys)), page


@needs_pandoc
def test_every_pandoc_option_is_offered():
    flags = ps.supported_flags(PANDOC)
    assert flags
    offered = {s.name for s in po.OPTIONS if s.flag}
    missing = sorted(flags - offered - po.NOT_OFFERED)
    assert not missing, f"pandoc options without a control: {missing}"


@needs_pandoc
def test_join_mixed_formats_into_one_document(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("# Introduction\n\nFirst file.\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# Introduction\n\nSecond file.\n", encoding="utf-8")
    src = tmp_path / "c.md"
    src.write_text("# Word part\n\nThird file.\n", encoding="utf-8")
    c = tmp_path / "c.docx"
    ps.convert(src, c, ps.PandocOptions(to_format="docx"), pandoc=PANDOC)
    out = tmp_path / "all.html"
    ps.join_convert([a, b, c], out, ps.PandocOptions(to_format="html"), pandoc=PANDOC)
    html = out.read_text(encoding="utf-8")
    assert html.index("First file") < html.index("Second file") < html.index("Third file")
    assert 'id="introduction"' in html and 'id="introduction-2"' in html
    assert "<title>all</title>" in html


@needs_pandoc
def test_every_output_format_converts(tmp_path):
    src = tmp_path / "sample.md"
    src.write_text("# Heading\n\nSome *text* and a list:\n\n- one\n- two\n", encoding="utf-8")
    failed = []
    for fmt in ps.list_output_formats(PANDOC):
        if fmt == "pdf":
            continue   # needs a separately installed PDF engine
        out = tmp_path / ("out_" + fmt + ps.output_extension(fmt))
        try:
            ps.convert(src, out, ps.PandocOptions(to_format=fmt), pandoc=PANDOC)
        except RuntimeError as e:
            failed.append(f"{fmt}: {e}")
            continue
        if not out.is_file():
            failed.append(f"{fmt}: no output file")
    assert not failed, failed


@needs_pandoc
def test_tools_print_defaults():
    assert "$body$" in ps.default_template("html", PANDOC)
    assert ps.default_data_file("reference.docx", PANDOC)[:2] == b"PK"
    assert ps.list_extensions("docx", PANDOC)
