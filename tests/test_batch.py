"""Tests for planning batch pandoc conversions of files and folders.

Run with:  python -m pytest tests
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmd import pandoc_support as ps  # noqa: E402


def _tree(root: Path) -> Path:
    files = ["a.docx", "b.md", "c.html", "~$a.docx", ".hidden.md", "photo.jpg",
             "sub/d.odt", "sub/deeper/e.rst", "b_assets/x.md", ".git/f.md"]
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return root


def test_parse_type_filter():
    assert ps.parse_type_filter("") is None
    assert ps.parse_type_filter("docx; *.md, .HTML") == {".docx", ".md", ".html"}


def test_folder_files_skips_unsupported_hidden_and_lock_files(tmp_path):
    root = _tree(tmp_path)
    names = [p.name for p in ps.folder_files(root)]
    assert names == ["a.docx", "b.md", "c.html"]


def test_folder_files_recursive_skips_hidden_and_assets_folders(tmp_path):
    root = _tree(tmp_path)
    names = sorted(p.name for p in ps.folder_files(root, recursive=True))
    assert names == ["a.docx", "b.md", "c.html", "d.odt", "e.rst"]


def test_folder_files_type_filter(tmp_path):
    root = _tree(tmp_path)
    found = ps.folder_files(root, recursive=True, types={".md", ".rst"})
    assert sorted(p.name for p in found) == ["b.md", "e.rst"]


def test_plan_folder_next_to_inputs_skips_output_format(tmp_path):
    root = _tree(tmp_path)
    log = []
    jobs = ps.plan_batch([root], "html", recursive=True, log_cb=log.append)
    pairs = {j.source.name: j.dest for j in jobs}
    assert set(pairs) == {"a.docx", "b.md", "d.odt", "e.rst"}  # c.html skipped
    assert pairs["d.odt"] == root / "sub" / "d.html"
    assert any("already in the output format" in m for m in log)


def test_plan_folder_into_output_keeps_layout(tmp_path):
    root = _tree(tmp_path / "in")
    out = tmp_path / "out"
    jobs = ps.plan_batch([root], "docx", out_dir=out, recursive=True)
    pairs = {j.source.name: j.dest for j in jobs}
    assert pairs["e.rst"] == out / "sub" / "deeper" / "e.docx"
    assert pairs["b.md"] == out / "b.docx"
    assert "a.docx" not in pairs


def test_plan_explicit_file_is_always_converted_and_never_twice(tmp_path):
    root = _tree(tmp_path)
    jobs = ps.plan_batch([root / "c.html", root, root / "c.html"], "html")
    sources = [j.source.name for j in jobs]
    assert sources.count("c.html") == 1
    # same name as its input: a new name is chosen, the input is never overwritten
    c = next(j for j in jobs if j.source.name == "c.html")
    assert c.dest == root / "c_1.html"


def test_plan_never_gives_two_inputs_one_output(tmp_path):
    (tmp_path / "r.md").write_text("x")
    (tmp_path / "r.docx").write_text("x")
    (tmp_path / "r.txt").write_text("existing")
    out = tmp_path / "o"
    out.mkdir()
    (out / "r.txt").write_text("existing")
    jobs = ps.plan_batch([tmp_path / "r.md", tmp_path / "r.docx"], "plain", out_dir=out)
    dests = [j.dest.name for j in jobs]
    assert dests == ["r_1.txt", "r_2.txt"]


def test_plan_single_file(tmp_path):
    f = tmp_path / "one.docx"
    f.write_text("x")
    jobs = ps.plan_batch([f], "epub")
    assert [(j.source, j.dest) for j in jobs] == [(f, tmp_path / "one.epub")]


def test_plan_missing_path_is_logged(tmp_path):
    log = []
    assert ps.plan_batch([tmp_path / "gone.md"], "html", log_cb=log.append) == []
    assert log and "Not found" in log[0]
