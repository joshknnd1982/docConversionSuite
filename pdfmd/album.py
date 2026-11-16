"""Describe a folder of photos with the local vision model.

Every picture in a folder (optionally with its subfolders) is described by
the vision model: a short title and a few sentences about who and what is in
it, the place, the time of day or season, and the mood. The results are
written to one accessible HTML page or Markdown file, in the order the photos
were taken, so people can review vacation photos and family memories with a
screen reader, or quickly find a photo.

The photos are linked, not copied, so the page stays small; keep it in or
near the photo folder. Descriptions are cached in a small file next to the
output, so describing the folder again only describes new or changed photos.
Nothing leaves the computer.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

from . import vision

Logger = Optional[Callable[[str], None]]
Progress = Optional[Callable[[int, int], None]]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".png", ".gif", ".bmp", ".tif", ".tiff",
                    ".webp", ".heic", ".heif", ".avif", ".jfif"}
FORMATS = [("html", "Web page (HTML)"), ("markdown", "Markdown")]


@dataclass
class Photo:
    path: Path
    taken: Optional[_dt.datetime] = None
    camera: str = ""
    width: int = 0
    height: int = 0
    title: str = ""
    description: str = ""
    error: str = ""
    extra: Dict[str, str] = field(default_factory=dict)


def find_photos(folder: Path, recursive: bool = False) -> List[Path]:
    it = folder.rglob("*") if recursive else folder.glob("*")
    out = [p for p in it if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
           and not p.name.startswith(".")]
    return sorted(out, key=lambda p: str(p).lower())


def _exif(path: Path) -> Photo:
    photo = Photo(path)
    try:
        img = vision.open_image(path)
        photo.width, photo.height = img.size
    except Exception as e:  # noqa: BLE001
        photo.error = f"could not be opened ({e})"
        return photo
    try:
        Image, _ = vision._pil()
        with Image.open(str(path)) as raw:
            exif = raw.getexif()
            sub = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
            stamp = sub.get(36867) or sub.get(36868) or exif.get(306)  # DateTimeOriginal, Digitized, DateTime
            if stamp:
                photo.taken = _dt.datetime.strptime(str(stamp).strip()[:19], "%Y:%m:%d %H:%M:%S")
            make, model = str(exif.get(271) or "").strip(), str(exif.get(272) or "").strip()
            photo.camera = model if model.lower().startswith(make.lower()) else f"{make} {model}".strip()
    except Exception:
        pass
    return photo


def _cache_path(out_path: Path) -> Path:
    return out_path.with_name(out_path.name + ".descriptions.json")


def _cache_key(path: Path, model_id: str) -> str:
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}|{model_id}"


def describe_folder(
    folder: Path,
    out_path: Path,
    fmt: str = "html",
    settings: Optional[vision.VisionSettings] = None,
    recursive: bool = False,
    progress_cb: Progress = None,
    log_cb: Logger = None,
    cancel: Optional[threading.Event] = None,
) -> Path:
    """Describe every photo in folder and write the album to out_path."""
    folder = Path(folder)
    out_path = Path(out_path)
    settings = settings or vision.VisionSettings()
    log = log_cb or (lambda m: None)
    paths = find_photos(folder, recursive)
    if not paths:
        raise vision.VisionError(f"No pictures were found in {folder}.")
    log(f"[album] {len(paths)} picture{'s' if len(paths) != 1 else ''} found in {folder}.")

    engine = vision.get_engine(settings, log_cb=log)
    model_id = engine.model.id
    cache_file = _cache_path(out_path)
    try:
        cache: Dict[str, dict] = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        cache = {}

    photos: List[Photo] = []
    for n, path in enumerate(paths, start=1):
        if cancel is not None and cancel.is_set():
            raise vision.Cancelled()
        photo = _exif(path)
        photos.append(photo)
        if photo.error:
            log(f"[album] {n} of {len(paths)}: {path.name} {photo.error}.")
            continue
        try:
            key = _cache_key(path, model_id)
        except OSError:
            key = ""
        if key and key in cache:
            photo.title = cache[key].get("title", "")
            photo.description = cache[key].get("description", "")
            log(f"[album] {n} of {len(paths)}: {path.name} (already described).")
        else:
            try:
                d = engine.describe(path, "photo", settings.lang)
                photo.title, photo.description = d.title, d.text
                if key:
                    cache[key] = {"title": d.title, "description": d.text}
                    _save_cache(cache_file, cache)
                log(f"[album] {n} of {len(paths)}: {path.name} ({d.seconds:.1f} s): "
                    f"{d.title + '. ' if d.title else ''}{d.text}")
            except Exception as e:  # noqa: BLE001
                photo.error = f"could not be described ({e})"
                log(f"[album] {n} of {len(paths)}: {path.name} {photo.error}.")
        if progress_cb:
            progress_cb(n, len(paths))

    photos.sort(key=lambda p: (p.taken is None, p.taken or _dt.datetime.min, str(p.path).lower()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    title = f"Photos in {folder.name or folder}"
    lang = _lang_tag(settings.lang)
    if fmt == "markdown":
        text = render_markdown(photos, out_path, title, engine.model.name)
    else:
        text = render_html(photos, out_path, title, engine.model.name, lang)
    out_path.write_text(text, encoding="utf-8")
    log(f"[album] Saved {out_path}")
    return out_path


def _save_cache(path: Path, cache: dict) -> None:
    try:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def _lang_tag(code: str) -> str:
    try:
        from .mathjax import language_tag

        return language_tag(code)
    except Exception:
        return "en"


def _rel_url(target: Path, out_path: Path) -> str:
    try:
        rel = os.path.relpath(target, out_path.parent)
    except ValueError:  # different drive on Windows
        return target.resolve().as_uri()
    return quote(rel.replace(os.sep, "/"))


def _when(photo: Photo) -> str:
    if not photo.taken:
        return ""
    t = photo.taken
    return f"{t.strftime('%A')} {t.day} {t.strftime('%B %Y')}, {t.strftime('%H:%M')}"


def _heading(photo: Photo, n: int) -> str:
    return photo.title or photo.path.stem or f"Photo {n}"


def render_markdown(photos: List[Photo], out_path: Path, title: str, model: str) -> str:
    lines = [f"# {title}", "",
             f"{len(photos)} photos, described on this computer by {model}. "
             "Descriptions are written by an AI model and may contain mistakes.", ""]
    for n, p in enumerate(photos, start=1):
        lines += [f"## {n}. {_md(_heading(p, n))}", ""]
        # The description follows as text, so the picture's alternative
        # text is the title (screen readers would otherwise read it twice).
        alt = (p.title or f"Photo {n}").replace("[", "(").replace("]", ")")
        if not p.error or p.width:
            lines += [f"![{alt}]({_rel_url(p.path, out_path)})", ""]
        if p.description:
            lines += [_md(p.description), ""]
        elif p.error:
            lines += [f"*This picture {p.error}.*", ""]
        meta = [f"File: {_md(p.path.name)}"]
        if _when(p):
            meta.append(f"Taken: {_when(p)}")
        if p.camera:
            meta.append(f"Camera: {_md(p.camera)}")
        lines += ["- " + m for m in meta] + [""]
    return "\n".join(lines).rstrip() + "\n"


def _md(text: str) -> str:
    return re.sub(r"([\\`*_#<>|])", r"\\\1", text or "")


_CSS = """
:root { color-scheme: light dark; --muted: #555; --card: #f6f6f6; }
@media (prefers-color-scheme: dark) { :root { --muted: #bbb; --card: #222; } }
body { max-width: 60em; margin: 0 auto; padding: 1.5em 1em 3em;
       font-family: system-ui, "Segoe UI", Arial, sans-serif; font-size: 1.1rem; line-height: 1.6; }
a { color: LinkText; }
.skip-link { position: absolute; left: -10000px; }
.skip-link:focus { position: static; }
nav ol { columns: 2 18em; }
article { background: var(--card); border-radius: 10px; padding: 1em 1.2em; margin: 1.5em 0; }
article h2 { margin-top: 0; }
figure { margin: 0; }
img { max-width: 100%; height: auto; border-radius: 6px; display: block; }
.meta { color: var(--muted); font-size: 0.95rem; list-style: none; padding: 0; }
.note { color: var(--muted); }
""".strip()


def render_html(photos: List[Photo], out_path: Path, title: str, model: str,
                lang: str = "en") -> str:
    e = html.escape
    toc = []
    body = []
    for n, p in enumerate(photos, start=1):
        head = _heading(p, n)
        anchor = f"photo-{n}"
        toc.append(f'<li><a href="#{anchor}">{e(head)}</a></li>')
        alt = p.title or f"Photo {n}"   # the description is the caption
        parts = [f'<article id="{anchor}" aria-labelledby="{anchor}-h">',
                 f'<h2 id="{anchor}-h">{n}. {e(head)}</h2>', "<figure>"]
        if not p.error or p.width:
            parts.append(f'<img src="{e(_rel_url(p.path, out_path))}" alt="{e(alt)}" '
                         f'loading="lazy">')
        if p.description:
            parts.append(f"<figcaption><p>{e(p.description)}</p></figcaption>")
        elif p.error:
            parts.append(f"<figcaption><p>This picture {e(p.error)}.</p></figcaption>")
        parts.append("</figure>")
        meta = [f"<li>File: {e(p.path.name)}</li>"]
        if _when(p):
            meta.append(f'<li>Taken: <time datetime="{p.taken.isoformat()}">{e(_when(p))}</time></li>')
        if p.camera:
            meta.append(f"<li>Camera: {e(p.camera)}</li>")
        parts.append('<ul class="meta">' + "".join(meta) + "</ul>")
        parts.append("</article>")
        body.append("\n".join(parts))
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{e(lang)}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="generator" content="Document Conversion Suite">\n'
        f"<title>{e(title)}</title>\n<style>\n{_CSS}\n</style>\n</head>\n<body>\n"
        '<a class="skip-link" href="#photos">Skip to the photos</a>\n'
        f"<header><h1>{e(title)}</h1>\n"
        f'<p class="note">{len(photos)} photos, described on this computer by {e(model)}. '
        "Each photo has a heading, so screen reader users can move from photo to photo "
        "with the H key. Descriptions are written by an AI model and may contain "
        "mistakes.</p></header>\n"
        '<nav aria-label="Photos"><h2>Contents</h2><ol>\n' + "\n".join(toc) + "\n</ol></nav>\n"
        '<main id="photos">\n' + "\n".join(body) + "\n</main>\n</body>\n</html>\n"
    )


def default_output(folder: Path, fmt: str) -> Path:
    ext = ".md" if fmt == "markdown" else ".html"
    return Path(folder) / f"Photo descriptions{ext}"


__all__ = ["IMAGE_EXTENSIONS", "FORMATS", "find_photos", "describe_folder",
           "render_html", "render_markdown", "default_output"]
