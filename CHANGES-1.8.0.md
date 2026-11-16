# Document Conversion Suite 1.8.0: what changed

Version 1.8.0 adds **picture descriptions by a small open-weights AI vision model that runs on your own computer**. Photos, charts, graphs, maps and diagrams in any document get alternative text, or a block-quoted description when the output can't hold the picture, and whole folders of photos can be described into an accessible album. Nothing is uploaded.

This page lists every change, explains how the model was chosen, and records how it was tested.

## Contents

1. [The chosen vision model](#1-the-chosen-vision-model)
2. [Works on every computer: CPU, NVIDIA CUDA or Vulkan](#2-works-on-every-computer-cpu-nvidia-cuda-or-vulkan)
3. [When pictures are described](#3-when-pictures-are-described)
4. [Alternative text or block quote: it depends on the output](#4-alternative-text-or-block-quote-it-depends-on-the-output)
5. [Every document with pictures](#5-every-document-with-pictures)
6. [Describe a folder of photos](#6-describe-a-folder-of-photos)
7. [Updating the vision model with one button](#7-updating-the-vision-model-with-one-button)
8. [Desktop app changes](#8-desktop-app-changes)
9. [Command line changes](#9-command-line-changes)
10. [Python API changes](#10-python-api-changes)
11. [Installer and packaging](#11-installer-and-packaging)
12. [Privacy and security](#12-privacy-and-security)
13. [How it was tested](#13-how-it-was-tested)
14. [Known limitations](#14-known-limitations)
15. [Files added and changed](#15-files-added-and-changed)

---

## 1. The chosen vision model

**Default model: Qwen3-VL 2B Instruct, abliterated** (Huihui), 4-bit GGUF.

| | |
| --- | --- |
| Base model | [Qwen/Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) by the Qwen team, Alibaba Cloud |
| Abliteration | [huihui-ai/Huihui-Qwen3-VL-2B-Instruct-abliterated](https://huggingface.co/huihui-ai/Huihui-Qwen3-VL-2B-Instruct-abliterated) |
| GGUF files | [mradermacher/Huihui-Qwen3-VL-2B-Instruct-abliterated-GGUF](https://huggingface.co/mradermacher/Huihui-Qwen3-VL-2B-Instruct-abliterated-GGUF), revision `a12463c6` |
| Files | `Huihui-Qwen3-VL-2B-Instruct-abliterated.Q4_K_M.gguf` (1.11 GB, language model) and `...mmproj-Q8_0.gguf` (0.45 GB, vision encoder) |
| Licence | Apache-2.0 (open weights, commercial use allowed) |
| Memory | about 3 GB while describing; freed after each batch |
| Engine | [llama.cpp](https://github.com/ggml-org/llama.cpp) build b12441, `llama-server` (MIT): Vulkan build built in; CUDA builds downloaded with one button for NVIDIA cards |

### Why this model

The requirements were: small and local; open weights; runs on an 8 GB laptop with integrated graphics *and* uses a high-end graphics card when the user wants; accurate on photos **and** on charts, graphs, maps and diagrams; abliterated, so it describes any personal photo without refusing; and it must still be accurate.

| Candidate | Licence | Download | Verdict |
| --- | --- | --- | --- |
| **Qwen3-VL 2B Instruct, abliterated (chosen)** | Apache-2.0 | 1.6 GB | Strong on charts, documents and photos for its size; runs everywhere; the abliterated version describes every photo |
| Qwen3-VL 2B Instruct (official) | Apache-2.0 | 1.6 GB | Same accuracy and speed; may decline some photos. Offered as an alternative |
| Qwen3-VL 4B Instruct, abliterated | Apache-2.0 | 3.0 GB | More accurate, but needs about 6 GB of memory: too heavy for 8 GB laptops as a default. Offered as an option for powerful PCs |
| Qwen3.5 0.8B / 2B | Apache-2.0 | 1.0–2.0 GB | Thinking models by default (slower, need special settings); no clear gain for alt text |
| Gemma 4 E2B | Apache-2.0 | 3.4 GB at Q4 | About twice the size of the 2B Qwen3-VL, too large for the default |
| SmolVLM2 256M–2.2B | Apache-2.0 | 0.3–1.9 GB | Smaller, but noticeably weaker on charts and dense pictures |
| LFM3-VL 2B | LFM Open License | 1.6 GB | Licence restricts commercial use above a revenue threshold |

**Abliteration and accuracy.** Abliteration removes a model's tendency to refuse by changing the language model's refusal direction; the vision encoder (the mmproj file) comes from the same weights as the official model. In a side-by-side test on the same drawn bar chart and three pictures (section 13), both models read the chart identically (sales rising from 40 to 160 thousand units, 2021 to 2024) and described the pictures equally accurately; the official model added one wrong detail ("pixelated, fragmented style") that the abliterated model did not.

**Quantisation.** Q4_K_M keeps the language model at about 1.1 GB with little loss; the vision encoder stays at 8-bit (Q8_0), because the encoder is the part that reads small chart labels.

## 2. Works on every computer: CPU, NVIDIA CUDA or Vulkan

Three llama.cpp engines can run the model:

| Engine | Runs on | How you get it |
| --- | --- | --- |
| **CPU** | Every x64 processor generation (SSE4.2, AVX, AVX2, AVX-512, Zen 4 ...); the best code path is picked at start-up | Built in (part of the Vulkan engine) |
| **Vulkan** | **Any GPU**: NVIDIA, AMD and Intel graphics cards and integrated graphics, through Vulkan, which comes with their normal drivers | Built in |
| **NVIDIA CUDA** | NVIDIA graphics cards; the fastest engine on them | Offered only when an NVIDIA card is detected. One button press downloads llama.cpp's CUDA build with NVIDIA's CUDA runtime (about 710 MB), checksum-verified |

NVIDIA cards are detected with `nvidia-smi`, which is installed with every NVIDIA driver. The CUDA build is chosen automatically: **CUDA 13** for RTX 20 series and newer cards with driver 580 or newer, **CUDA 12.4** otherwise (GTX 900 series and newer, driver 528 or newer on Windows). Older drivers are told to update, and Vulkan is used meanwhile. On macOS (Metal) and Linux (Vulkan, and CUDA on NVIDIA), `pdfmd --vision-update` downloads the right builds.

**Why CUDA is a download and not in the installer:** the CUDA build plus NVIDIA's CUDA runtime is about 710 MB. Together with the built-in model it would make the installer larger than 2 GB, the largest file a GitHub release can hold. Vulkan, which is built in, already runs on NVIDIA cards; CUDA is the optional faster path, one button press away.

**Processor** setting (Vision Model window, Ctrl+I, or `--vision-device`):

| Setting | What happens | Who it's for |
| --- | --- | --- |
| **Automatic** (default) | An NVIDIA card with CUDA when the CUDA engine is installed; otherwise a dedicated graphics card with Vulkan (or Apple silicon) with enough free memory; otherwise the CPU. Integrated graphics are not used automatically, because on many laptops they are no faster than the CPU | Everyone |
| **NVIDIA GPU with CUDA** (`cuda`) | The NVIDIA card through CUDA. Shown only when an NVIDIA card is found; if the CUDA engine isn't installed yet, Vulkan is used until you press Download Vision Model | Desktops and laptops with NVIDIA graphics |
| **Any GPU with Vulkan** (`vulkan` or `gpu`) | The best graphics processor through Vulkan, including integrated graphics | AMD and Intel graphics, laptops with good integrated graphics (Radeon 780M, Intel Arc), and NVIDIA without the CUDA download |
| **Only *device name*** | One particular graphics processor through Vulkan, for computers with more than one | Laptops with both integrated and dedicated graphics |
| **CPU only** (`cpu`) | Never uses a graphics processor | Any computer; also a fallback if graphics drivers misbehave |

If CUDA can't be used, the engine **falls back to Vulkan**, and if the graphics processor can't be used at all (old driver, not enough memory), **to the CPU**, and says so in the log.

Measured on one laptop (Ryzen 7 260, 32 GB, RTX 5060 Laptop GPU with driver 572.97, Radeon 780M), same PDF:

| Processor | Model loading | Per picture |
| --- | --- | --- |
| NVIDIA RTX 5060 with **CUDA** (12.4) | 1.4–1.8 s | 0.5–0.7 s |
| NVIDIA RTX 5060 with **Vulkan** | 2.2–2.7 s | 0.6–0.8 s |
| AMD Radeon 780M (integrated) with Vulkan | 3.9 s | about 4 s |
| **CPU** only (Ryzen 7, 8 cores) | 1.8 s | 5–7 s |

On the very newest cards (here an RTX 50 series card with a driver older than 580, so the CUDA 12.4 build), the **first** CUDA start took about a minute and a quarter while the NVIDIA driver compiled the engine for the card. The app raises the driver's compile cache so this happens only once, and says so in the log; later starts took 1.4–1.8 s.

On an older or low-power 8 GB laptop without a graphics card the CPU is slower than the one above (an estimate, not measured: roughly 10 to 20 seconds per picture). The model uses about 3 GB of memory, leaving room for Windows and the program, and the memory is freed after each batch.

## 3. When pictures are described

Pictures are described when they contain **little or no text**: photos, charts, graphs, maps, diagrams, illustrations.

In PDFs the engine finds:

* **Embedded pictures**, skipping tiny ones (icons, bullets, under about 0.5 inch or 1 % of the page), logos repeated on most pages, and pictures covered by a text layer (pages of a searchable scan).
* **Charts drawn with vector graphics** (most charts from Excel, matplotlib, R): clusters of drawings with curves, slanted lines or several fill colours. Plain ruled tables are left to the table detector. Short axis labels just outside the drawing are included in the picture the model sees, and the chart's caption is given to the model as context. When the chart is described, its stray axis labels are kept out of the text.
* **Photos inside scanned pages**: regions where Tesseract finds no words.

**Pictures of text** (a scanned paragraph, a screenshot of a letter) are recognised with Tesseract (more than 40 words covering at least 15 % of the picture) and get their **recognised text** instead of a description, labelled "Text in image". Without Tesseract, the model itself is asked to answer TEXT for such pictures.

Descriptions are one to three sentences (photos in albums: up to four), start with the kind of picture ("A bar chart showing ..."), and are written in the document's OCR language.

## 4. Alternative text or block quote: it depends on the output

| Output | What you get |
| --- | --- |
| Markdown **with** Export images | `![A bar chart showing sales from 2021 to 2024 ...](report_assets/figure_001_02.png)`, placed where the picture is |
| Markdown **without** Export images | `> **Image description:** A bar chart showing sales from 2021 to 2024 ...`, a block quote where the picture was |
| Accessible HTML copy | `<img alt="...">`, or a `<blockquote>`, following the Markdown |
| Word, ODT, EPUB, HTML, PowerPoint, PDF, LaTeX, Markdown and other formats that hold pictures (pandoc) | The picture with the description as its alternative text (Word's "Alt Text") |
| Plain text, man pages, spreadsheets, CSV and other text-only formats (pandoc) | A block quote with the description in place of the picture |

## 5. Every document with pictures

Pictures are described in **every document pandoc reads**, not only PDFs: Word (.docx), OpenDocument (.odt), EPUB, PowerPoint (.pptx), Jupyter notebooks, HTML, Markdown, LaTeX, reStructuredText and the rest.

* The document is read into pandoc's document tree; pictures with **no alternative text, or useless alternative text** ("image1", "Picture 3", a file name) are described. **Alternative text an author wrote is kept.**
* Generic figure captions such as "image1" are removed once the picture is described.
* SVG pictures are rendered first; embedded (data:) pictures are read directly; **remote pictures (http/https) are never downloaded**.
* Available in the **pandoc window** (Ctrl+P, check box "Describe pictures with the local AI vision model", Alt+C), for PDF conversions that are also exported with pandoc, and on the command line (`pdfmd-cli slides.pptx --to docx`).

## 6. Describe a folder of photos

**File > Describe a Folder of Photos** (Ctrl+D), or `pdfmd-cli --describe-photos FOLDER`.

* Choose a folder (and optionally its subfolders) and **Web page (HTML)** or **Markdown**.
* Every photo (JPEG, PNG, **HEIC from iPhones**, WebP, TIFF, GIF, BMP, AVIF) gets a **short title** and a **description**: who and what is in it (people by appearance and what they are doing, never guessed identities), the place and setting, the time of day, season or weather, the mood, and readable signs.
* Photos are sorted by the date they were taken (from the camera), with date, time and camera model.
* The **web page** has a heading per photo (screen reader users press H to go from photo to photo), a contents list, the photo itself with its title as alternative text and the description as its caption, and light and dark mode. Photos are linked, not copied.
* Descriptions are **remembered** in `<page>.descriptions.json`, so running it again only describes new or changed photos. Stop at any time; finished photos are kept.

## 7. Updating the vision model with one button

* **Vision Model window** (Ctrl+I) > **Update Vision Model** (Alt+V): downloads and installs the newest engine and the selected model with one button press, and the **NVIDIA CUDA engine** when the processor is set to NVIDIA GPU with CUDA. The button reads **Download Vision Model** when something is missing.
* **Check for Updates** (Alt+U) reads [vision-models.json](vision-models.json) from this repository, which lists the tested llama.cpp build and the models, with their download addresses and **SHA-256 checksums**. Publishing a new model or engine is a matter of editing that file.
* Every download is **verified against its SHA-256 before it is used**; a mismatch is deleted and reported.
* Updates go to `%LOCALAPPDATA%\DocConversionSuite\vision`. The built-in copy in the program folder stays as a fallback; the newest engine is used.
* Downloads show progress, are announced every 25 percent, and can be stopped. **Remove Downloaded Model** frees disk space.
* Command line: `pdfmd-cli --vision-update` (optionally `--vision-model ID`; add `--vision-device cuda` to download the CUDA engine).

## 8. Desktop app changes

* New option **Describe pictures with the local AI vision model** (Alt+4), on by default and saved in profiles.
* **File > Vision Model (Picture Descriptions)** (Ctrl+I): status, on/off, processor, model, model information, check for updates, update, test on a picture, remove downloaded model, log.
* **File > Describe a Folder of Photos** (Ctrl+D).
* **Help > Check for Vision Model Updates**.
* The pandoc window has the **Describe pictures** check box (Alt+C).
* The log shows the vision model at start-up and each description as it is written; the model's memory is freed after every batch.
* Keyboard help (F1), About, Accessibility Guide and Features Guide updated. Every new control is a native Windows control with a label, a spoken description and a unique Alt key; long operations are announced and can be cancelled; focus never gets lost when buttons are disabled.

## 9. Command line changes

| Option | Meaning |
| --- | --- |
| `--describe-images {auto,off}` | Describe pictures (default auto: when installed) |
| `--vision-device DEVICE` | `auto`, `cuda` (NVIDIA CUDA), `vulkan` (any GPU; `gpu` means the same), `cpu`, or a device name such as `Vulkan1` |
| `--vision-model ID` | Model to use or update |
| `--vision-status` | Engines (Vulkan, CUDA), installed models, NVIDIA card and driver, graphics processors, and where the model would run |
| `--vision-update` | Download a newer engine or model (checksum-verified); with `--vision-device cuda`, also the NVIDIA CUDA engine |
| `--describe-photos FOLDER` | Describe a folder of photos (`-o` sets the album file) |
| `--album-format {html,markdown}` | Album format |
| `--recursive` | Include subfolders |

Inputs that aren't PDFs are now accepted and converted with pandoc to `--to` (default GitHub Markdown), with their pictures described.

## 10. Python API changes

* `Options.describe_images`, `Options.vision_device`, `Options.vision_model`.
* New modules: `pdfmd.vision` (engine, models, devices, updates, `VisionEngine.describe`), `pdfmd.figures` (pictures and charts in PDFs), `pdfmd.docimages` (pictures in pandoc documents), `pdfmd.album` (photo folders), `pdfmd.gui_vision` (windows).
* `pandoc_support.convert(..., vision=VisionSettings(...))`.
* `models.Figure` and `Block.figure`: figures travel through the pipeline in reading order.
* See [doc/API.md](doc/API.md), section 6.4.

## 11. Installer and packaging

* The installer includes `vision\runtime` (llama-server Vulkan build and its libraries, about 90 MB) and `vision\models\huihui-qwen3-vl-2b-abliterated` (1.55 GB), so picture descriptions work offline right after installing.
* `packaging/fetch_vendor.py vision` downloads the llama.cpp release and the model and **verifies their SHA-256** against `vision-models.json` before building.
* The model files are stored uncompressed in the installer (they don't compress further), which keeps building fast.
* `pillow-heif` added for HEIC photos.
* `vision-models.json` lists the CUDA 12.4 and CUDA 13.5 builds of llama.cpp b12441 with NVIDIA's CUDA runtime for Windows x64, Windows on ARM and Linux, with SHA-256 checksums. The CUDA engine is installed per user, in its own folder (`runtime-cuda12-b12441`), next to the built-in Vulkan engine.
* `THIRD-PARTY-NOTICES.txt` lists llama.cpp (MIT), LLVM OpenMP (Apache-2.0 with LLVM exceptions), the model (Apache-2.0, with its origin) and pillow-heif.

## 12. Privacy and security

* The engine runs as a separate process listening **only on 127.0.0.1**, on a random free port, with a **random access key** for each start, and only while pictures are being described. Requests to it never go through a proxy.
* Documents and photos never leave the computer. Remote pictures referenced by documents are not downloaded.
* Network access happens only when you press Check for Updates or Update Vision Model (github.com and huggingface.co), and every download is checksum-verified.

## 13. How it was tested

* **31 automated tests** (`python -m pytest tests`): answer parsing, length limits, title cleanup, GPU detection, catalog completeness, figure Markdown, rendering, PDF picture and drawn-chart detection (including axis labels and captions), scanned-page photo regions (large confidently-read text such as a stamp is not mistaken for a picture), pandoc block quotes, caption cleanup, remote pictures never fetched, `file://` pictures, case-insensitive device names, sharing the engine between windows, choosing CUDA 12 or CUDA 13 from the driver and card, `cuda`/`vulkan` device names, CUDA entries in the catalog.
* **Independent code review** of the whole change found nine problems, all fixed before release: a model server could keep running after Stop was pressed while the model was loading; closing the app during loading could freeze the window; finishing a photo album could stop the engine a PDF conversion was using (the engine is now shared and stopped only when no window uses it); updates could fail when another window had the old engine or model open (each version now gets its own folder); pictures in RTF and FB2 documents could be dropped and reader options ignored in pandoc conversions; exporting images skipped pictures that weren't described (they are exported again, as before); scanned-page detection could mistake a big title for a picture; an internal error could silently rerun a conversion without descriptions; `--vision-device CPU` (capitals) was misread.
* **PDF with a photo, a drawn bar chart, a picture of text and a tiny icon**: the photo and chart were described, the chart with its years and rising trend; the picture of text got its recognised text; the icon was skipped. Run with CUDA and with Vulkan on the RTX 5060, with Vulkan on the Radeon 780M, and on the CPU alone.
* **CUDA engine download** through the app's own update code: 711 MB downloaded from the llama.cpp GitHub release, checksum-verified and installed in 18 seconds; the CUDA engine found the RTX 5060 as `CUDA0`. Without it, choosing CUDA used Vulkan and offered the download.
* **Scanned PDF** (a page photographed as one image): the text was recognised and the photo inside the scan was found and described in the right place.
* **Word document with pictures without alt text**, converted to Word (alt text written into the document), HTML (`alt` attributes) and plain text (block quotes); generic captions removed.
* **Photo folder** of 8 pictures: titles and descriptions written into an HTML page and a Markdown file in about 15 seconds on the GPU, including loading the model.
* **Abliterated vs official model**, same chart and three pictures on the same GPU: equally accurate (see section 1).
* **Prompts were tuned** for the 2B model: an earlier version invented chart details; the final prompt puts instructions in the system message, gives the caption as context, and forbids guessing what an unlabelled chart measures.
* All windows were opened from the real GUI code; access keys were checked for uniqueness in each window.

## 14. Known limitations

* A 2B model is small: it is reliable about *what* a picture shows, but can misread small numbers on charts or miscount items. Check important figures; the 4B model (Ctrl+I) is more accurate on powerful computers.
* Integrated graphics are not chosen automatically; choose **Any GPU with Vulkan** if yours is fast.
* The CUDA engine is a separate download (about 710 MB) because the installer can't be larger than 2 GB on GitHub. The first CUDA start on the newest cards can take about a minute.
* Photos inside scanned pages are found from Tesseract's layout analysis; pictures that touch text closely may be missed.
* Picture descriptions in the installer are Windows x64 only out of the box; on Windows on ARM, macOS and Linux run `pdfmd --vision-update`.

## 15. Files added and changed

**Added**

* `pdfmd/vision.py` (including NVIDIA detection and the CUDA, Vulkan and CPU engines), `pdfmd/figures.py`, `pdfmd/docimages.py`, `pdfmd/album.py`, `pdfmd/gui_vision.py`
* `vision-models.json` (model and engine catalog with checksums; also read online for updates)
* `tests/test_vision_features.py`
* `CHANGES-1.8.0.md` (this file)

**Changed**

* `pdfmd/models.py` (`Figure`, `Block.figure`, vision options), `pdfmd/extract.py`, `pdfmd/transform.py`, `pdfmd/render.py`, `pdfmd/pipeline.py` (describe stage), `pdfmd/pandoc_support.py`, `pdfmd/cli.py`, `pdfmd/app_gui.py`, `pdfmd/gui_pandoc.py`, `pdfmd/__init__.py` (1.8.0)
* `packaging/fetch_vendor.py`, `packaging/build.py`, `packaging/installer.iss`, `packaging/pdfmd.spec`, `packaging/THIRD-PARTY-NOTICES.txt`
* `README.md`, `FEATURES.md`, `ACCESSIBILITY.md`, `doc/API.md`, `pyproject.toml`, `requirements.txt`, `.gitignore`
