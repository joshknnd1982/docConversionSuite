"""Every pandoc option, described once.

The Pandoc Options window builds its controls from ``OPTIONS`` and
``pandoc_support.build_args`` builds the pandoc command line from it, so
adding a pandoc option means adding one ``OptionSpec`` here (and a test).

Option names and choices follow pandoc 3.13 (``pandoc --help`` and
https://pandoc.org/MANUAL.html). Options the running pandoc doesn't list in
``--help`` are hidden and never passed (see ``supported_flags``), so an older
pandoc the user installed still works.

Values are stored on ``PandocOptions``: options that existed before 1.9.0
keep their own attribute (``toc``, ``template`` ...), so old settings and
profiles load unchanged; newer options live in ``PandocOptions.values``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Groups of output formats
# ---------------------------------------------------------------------------

HTML_LIKE = frozenset({"html", "html4", "html5", "revealjs", "slidy", "slideous", "s5",
                       "dzslides", "chunkedhtml"})
EPUB_LIKE = frozenset({"epub", "epub2", "epub3"})
SLIDES = frozenset({"revealjs", "slidy", "slideous", "s5", "dzslides", "beamer", "pptx"})
LATEX_LIKE = frozenset({"latex", "beamer", "pdf"})
MARKDOWN_LIKE = frozenset({"markdown", "gfm", "commonmark", "commonmark_x", "markdown_mmd",
                           "markdown_phpextra", "markdown_strict", "markdown_github", "markua"})
OFFICE = frozenset({"docx", "odt", "pptx"})
BINARY_OUTPUTS = frozenset({"docx", "odt", "epub", "epub2", "epub3", "pptx", "pdf",
                            "chunkedhtml"})
MARKDOWN_INPUTS = MARKDOWN_LIKE | frozenset({"djot"})

# ---------------------------------------------------------------------------
# Pages of the Pandoc Options window, in order
# ---------------------------------------------------------------------------

PAGES: List[Tuple[str, str]] = [
    ("format", "Format"),
    ("document", "Document"),
    ("sections", "Contents and sections"),
    ("math", "Math and code"),
    ("citations", "Citations"),
    ("layout", "Text layout"),
    ("web", "Web pages and slides"),
    ("office", "Word, OpenDocument, PowerPoint"),
    ("ebook", "E-books"),
    ("pdf", "PDF"),
    ("input", "Input and media"),
    ("filters", "Filters"),
    ("command", "Command line"),
]

# Kinds of option and the control each one gets.
SWITCH = "switch"      # check box
NUMBER = "number"      # spin control
CHOICE = "choice"      # drop-down list (or radio buttons when ``radio``)
COMBO = "combo"        # drop-down list you can also type in
TEXT = "text"          # one-line text field
FILE = "file"          # text field + "Choose ..." button (one file)
SAVEFILE = "savefile"  # text field + "Choose ..." button (a file to write)
FILES = "files"        # text field + "Choose ..." button (several, separated by ;)
FOLDER = "folder"      # text field + "Choose ..." button (a folder)
PAIRS = "pairs"        # multi-line text field, one KEY=VALUE per line
LINES = "lines"        # multi-line text field, one value per line
FILTERS = "filters"    # ordered list of filters with buttons

KINDS = (SWITCH, NUMBER, CHOICE, COMBO, TEXT, FILE, SAVEFILE, FILES, FOLDER, PAIRS, LINES,
         FILTERS)


@dataclass(frozen=True)
class OptionSpec:
    key: str
    flag: str
    kind: str
    label: str
    help: str
    page: str
    default: Any = None
    choices: Tuple[Tuple[str, str], ...] = ()
    outputs: Optional[FrozenSet[str]] = None          # only for these output formats
    exclude_outputs: FrozenSet[str] = frozenset()     # never for these output formats
    inputs: Optional[FrozenSet[str]] = None           # only for these input formats
    reader: bool = False          # used when reading the source document
    advanced: bool = False        # shown only with "Show advanced options"
    negatable: bool = False       # pandoc accepts --flag=false
    special: bool = False         # build_args handles it itself
    radio: bool = False           # CHOICE shown as radio buttons
    minimum: int = 0
    maximum: int = 100
    wildcard: str = "All files (*.*)|*.*"
    button: str = ""              # label of the "Choose..." button

    @property
    def name(self) -> str:
        """The flag without the leading dashes ("toc-depth")."""
        return self.flag.lstrip("-")


def _o(*formats: Iterable[str]) -> FrozenSet[str]:
    out: set = set()
    for f in formats:
        if isinstance(f, str):
            out.add(f)
        else:
            out |= set(f)
    return frozenset(out)


IMAGES = "Pictures (*.png;*.jpg;*.jpeg;*.gif;*.svg;*.webp)|*.png;*.jpg;*.jpeg;*.gif;*.svg;*.webp|All files (*.*)|*.*"
YAML = "YAML files (*.yaml;*.yml)|*.yaml;*.yml|All files (*.*)|*.*"

OPTIONS: List[OptionSpec] = [
    # ------------------------------------------------------------- Format
    OptionSpec("standalone", "--standalone", SWITCH,
               "Standalone document (complete file with header and footer)",
               "Write a complete document rather than a fragment. Word, EPUB, PowerPoint and "
               "other binary formats are always complete. Pandoc option --standalone.",
               "format", default=False, special=True),
    OptionSpec("template", "--template", FILE, "Template",
               "A custom pandoc template for the output. Leave empty for pandoc's built-in "
               "template. Use Save Default Template to get a copy to edit. Pandoc option "
               "--template.", "format", button="Choose Template...",
               exclude_outputs=_o("docx", "pptx")),
    OptionSpec("data_dir", "--data-dir", FOLDER, "Pandoc data folder",
               "A folder where pandoc looks for templates, reference documents, filters and "
               "styles before its built-in ones. Pandoc option --data-dir.", "format",
               advanced=True, button="Choose Data Folder..."),
    OptionSpec("defaults_file", "--defaults", FILE, "Defaults file",
               "A YAML file of pandoc settings, applied before the options in this window. "
               "Pandoc option --defaults.", "format", advanced=True, wildcard=YAML,
               button="Choose Defaults File..."),

    # ------------------------------------------------------------- Document
    OptionSpec("title", "--metadata", TEXT, "Document title",
               "Optional title. Leave empty to use the file name as the page title.",
               "document", default="", special=True),
    OptionSpec("lang", "--metadata", TEXT, "Document language",
               "Language tag such as en, fr or de-CH. Screen readers use it to pick the right "
               "voice. Leave empty to use the OCR language.", "document", default="",
               special=True),
    OptionSpec("metadata", "--metadata", PAIRS, "Metadata (one key=value per line)",
               "Document information such as author=Ada Lovelace or date=2026-11-16, one per "
               "line. Pandoc option --metadata.", "document"),
    OptionSpec("metadata_file", "--metadata-file", FILE, "Metadata file",
               "A YAML or JSON file of document information. Pandoc option --metadata-file.",
               "document", wildcard=YAML, button="Choose Metadata File..."),
    OptionSpec("variables", "--variable", PAIRS, "Template variables (one key=value per line)",
               "Values for the template, for example geometry=margin=2cm or fontsize=12pt, one "
               "per line. Pandoc option --variable.", "document", advanced=True),
    OptionSpec("variables_json", "--variable-json", LINES,
               "Template variables as JSON (one key:JSON per line)",
               "Template variables with structured values, for example "
               "authors:[\"Ada\",\"Grace\"], one per line. Pandoc option --variable-json.",
               "document", advanced=True),
    OptionSpec("include_in_header", "--include-in-header", FILES, "Include in header",
               "Files whose contents are added at the end of the document header, for example "
               "extra CSS or LaTeX packages. Separate several with semicolons. Pandoc option "
               "--include-in-header.", "document", advanced=True,
               button="Choose Header Files..."),
    OptionSpec("include_before_body", "--include-before-body", FILES, "Include before body",
               "Files added at the start of the document body. Pandoc option "
               "--include-before-body.", "document", advanced=True,
               button="Choose Before-Body Files..."),
    OptionSpec("include_after_body", "--include-after-body", FILES, "Include after body",
               "Files added at the end of the document body. Pandoc option "
               "--include-after-body.", "document", advanced=True,
               button="Choose After-Body Files..."),

    # ------------------------------------------------------------- Contents and sections
    OptionSpec("toc", "--toc", SWITCH, "Table of contents",
               "Add a table of contents. Pandoc option --toc.", "sections", default=False,
               special=True),
    OptionSpec("toc_depth", "--toc-depth", NUMBER, "Depth of contents (heading levels)",
               "How many heading levels the table of contents includes.", "sections",
               default=3, minimum=1, maximum=6, special=True),
    OptionSpec("lof", "--lof", SWITCH, "List of figures",
               "Add a list of figures. Works for LaTeX, PDF, ConTeXt and Word output. Pandoc "
               "option --lof.", "sections", default=False, negatable=True,
               outputs=_o(LATEX_LIKE, "context", "docx")),
    OptionSpec("lot", "--lot", SWITCH, "List of tables",
               "Add a list of tables. Works for LaTeX, PDF, ConTeXt and Word output. Pandoc "
               "option --lot.", "sections", default=False, negatable=True,
               outputs=_o(LATEX_LIKE, "context", "docx")),
    OptionSpec("number_sections", "--number-sections", SWITCH, "Number sections",
               "Number the headings, for example 1, 1.1, 1.2. Pandoc option --number-sections.",
               "sections", default=False),
    OptionSpec("number_offset", "--number-offset", TEXT, "Section number offset",
               "Numbers to start the section numbering from, for example 3 or 1,4. Works for "
               "HTML output. Pandoc option --number-offset.", "sections", advanced=True,
               outputs=_o(HTML_LIKE, EPUB_LIKE)),
    OptionSpec("top_level_division", "--top-level-division", CHOICE, "Top-level headings are",
               "What first-level headings become in LaTeX, PDF, ConTeXt, DocBook and TEI "
               "output: sections, chapters or parts. Pandoc option --top-level-division.",
               "sections", default="",
               choices=(("", "Automatic"), ("section", "Sections"), ("chapter", "Chapters"),
                        ("part", "Parts")),
               outputs=_o(LATEX_LIKE, "context", "docbook", "docbook4", "docbook5", "tei")),
    OptionSpec("shift_heading_level", "--shift-heading-level-by", NUMBER,
               "Shift heading levels by",
               "Promote (negative) or demote (positive) every heading. Pandoc option "
               "--shift-heading-level-by.", "sections", default=0, minimum=-5, maximum=5,
               special=True),
    OptionSpec("figure_caption_position", "--figure-caption-position", CHOICE,
               "Figure captions",
               "Whether figure captions go above or below figures. Works for HTML, LaTeX, PDF, "
               "Word, OpenDocument and Typst output. Pandoc option --figure-caption-position.",
               "sections", default="",
               choices=(("", "Default (below)"), ("above", "Above the figure"),
                        ("below", "Below the figure")),
               outputs=_o(HTML_LIKE, EPUB_LIKE, LATEX_LIKE, "docx", "odt", "typst")),
    OptionSpec("table_caption_position", "--table-caption-position", CHOICE,
               "Table captions",
               "Whether table captions go above or below tables. Works for HTML, LaTeX, PDF, "
               "Word, OpenDocument and Typst output. Pandoc option --table-caption-position.",
               "sections", default="",
               choices=(("", "Default (above)"), ("above", "Above the table"),
                        ("below", "Below the table")),
               outputs=_o(HTML_LIKE, EPUB_LIKE, LATEX_LIKE, "docx", "odt", "typst")),

    # ------------------------------------------------------------- Math and code
    OptionSpec("math", "", CHOICE, "Math rendering",
               "How equations are written. Automatic picks the most accessible method: MathJax "
               "for web pages, MathML for EPUB, and native equations for Word, OpenDocument "
               "and PowerPoint.", "math", default="auto", special=True),
    OptionSpec("highlight_style", "--syntax-highlighting", CHOICE, "Code highlighting",
               "How code blocks are coloured. None turns highlighting off; Idiomatic uses the "
               "output format's own method (for example LaTeX listings). Use Save Highlight "
               "Style to get a theme file to edit. Pandoc option --syntax-highlighting.",
               "math", default="", special=True),
    OptionSpec("syntax_definition", "--syntax-definition", FILES, "Extra syntax definitions",
               "KDE syntax definition XML files for languages pandoc doesn't know. Pandoc "
               "option --syntax-definition.", "math", advanced=True,
               wildcard="Syntax definitions (*.xml)|*.xml|All files (*.*)|*.*",
               button="Choose Syntax Files..."),
    OptionSpec("listings", "--listings", SWITCH, "Use the LaTeX listings package for code",
               "Write code blocks with the LaTeX listings package. Pandoc option --listings.",
               "math", default=False, negatable=True, outputs=LATEX_LIKE),
    OptionSpec("indented_code_classes", "--indented-code-classes", TEXT,
               "Classes for indented code blocks",
               "Languages for code blocks written by indenting, for example python. Pandoc "
               "option --indented-code-classes.", "math", advanced=True, reader=True,
               inputs=MARKDOWN_INPUTS),
    OptionSpec("tab_stop", "--tab-stop", NUMBER, "Spaces per tab",
               "How many spaces a tab is worth when reading. Pandoc option --tab-stop.",
               "math", default=4, minimum=1, maximum=16, advanced=True, reader=True),
    OptionSpec("preserve_tabs", "--preserve-tabs", SWITCH, "Keep tabs in code blocks",
               "Keep tab characters in code instead of turning them into spaces. Pandoc option "
               "--preserve-tabs.", "math", default=False, negatable=True, advanced=True,
               reader=True),

    # ------------------------------------------------------------- Citations
    OptionSpec("citation_method", "", CHOICE, "How citations are handled",
               "Leave as written keeps citations like [@smith2020] as they are. Format with "
               "citeproc formats them and adds a bibliography (pandoc option --citeproc). "
               "LaTeX natbib and biblatex leave the formatting to LaTeX.", "citations",
               default="", radio=True, special=True,
               choices=(("", "Leave as written"), ("citeproc", "Format with citeproc"),
                        ("natbib", "LaTeX natbib"), ("biblatex", "LaTeX biblatex"))),
    OptionSpec("bibliography", "--bibliography", FILES, "Bibliography files",
               "BibTeX, BibLaTeX, CSL JSON, CSL YAML or RIS files. Separate several with "
               "semicolons. Choosing one turns on citeproc unless natbib or biblatex is chosen.",
               "citations", default="", special=True,
               wildcard="Bibliographies (*.bib;*.json;*.yaml;*.ris)|*.bib;*.json;*.yaml;*.ris|"
                        "All files (*.*)|*.*",
               button="Choose Bibliography..."),
    OptionSpec("csl", "--csl", FILE, "Citation style (CSL)",
               "A CSL style file that controls how citations look, for example APA or "
               "Chicago. Pandoc option --csl.", "citations", default="",
               wildcard="CSL styles (*.csl)|*.csl|All files (*.*)|*.*",
               button="Choose Style File..."),
    OptionSpec("citation_abbreviations", "--citation-abbreviations", FILE,
               "Journal abbreviations",
               "A CSL JSON file of journal abbreviations. Pandoc option "
               "--citation-abbreviations.", "citations",
               wildcard="JSON files (*.json)|*.json|All files (*.*)|*.*",
               button="Choose Abbreviations File..."),

    # ------------------------------------------------------------- Text layout
    OptionSpec("wrap", "--wrap", CHOICE, "Line wrapping",
               "How text output wraps lines: automatically at the column width, not at all, or "
               "as in the source. Pandoc option --wrap.", "layout", default="auto",
               choices=(("auto", "Automatic"), ("none", "None"), ("preserve", "Preserve")),
               exclude_outputs=BINARY_OUTPUTS),
    OptionSpec("columns", "--columns", NUMBER, "Line width (characters)",
               "Characters per line for wrapping and for tables in text output. Pandoc option "
               "--columns.", "layout", default=72, minimum=10, maximum=1000,
               exclude_outputs=BINARY_OUTPUTS),
    OptionSpec("eol", "--eol", CHOICE, "Line endings",
               "Line endings in text output. Pandoc option --eol.", "layout", default="",
               choices=(("", "This computer's (native)"), ("crlf", "Windows (CRLF)"),
                        ("lf", "Unix and Mac (LF)")),
               exclude_outputs=BINARY_OUTPUTS),
    OptionSpec("dpi", "--dpi", NUMBER, "Picture resolution (dots per inch)",
               "Used to convert picture sizes between pixels and inches or centimetres. "
               "Pandoc option --dpi.", "layout", default=96, minimum=10, maximum=2400),
    OptionSpec("reference_links", "--reference-links", SWITCH, "Use reference-style links",
               "Write links as [text][1] with the addresses collected elsewhere. Pandoc option "
               "--reference-links.", "layout", default=False, negatable=True,
               outputs=_o(MARKDOWN_LIKE, "rst")),
    OptionSpec("reference_location", "--reference-location", CHOICE,
               "Footnotes and references go",
               "Where footnotes and reference links are placed. Pandoc option "
               "--reference-location.", "layout", default="",
               choices=(("", "At the end of the document"), ("block", "After each paragraph"),
                        ("section", "At the end of each section")),
               outputs=_o(MARKDOWN_LIKE, HTML_LIKE, EPUB_LIKE, "muse", "docx")),
    OptionSpec("markdown_headings", "--markdown-headings", CHOICE, "Markdown heading style",
               "ATX headings start with # signs; Setext headings are underlined. Pandoc option "
               "--markdown-headings.", "layout", default="",
               choices=(("", "Default (ATX, # signs)"), ("atx", "ATX (# signs)"),
                        ("setext", "Setext (underlined)")),
               outputs=_o(MARKDOWN_LIKE, "ipynb")),
    OptionSpec("list_tables", "--list-tables", SWITCH, "Write tables as list tables",
               "Write reStructuredText tables as list tables. Pandoc option --list-tables.",
               "layout", default=False, negatable=True, outputs=_o("rst")),
    OptionSpec("ascii", "--ascii", SWITCH, "Use only ASCII characters",
               "Write other characters as entities or escapes. Pandoc option --ascii.",
               "layout", default=False, negatable=True,
               outputs=_o(HTML_LIKE, EPUB_LIKE, MARKDOWN_LIKE, "docbook", "docbook4",
                          "docbook5", "jats", "jats_archiving", "jats_articleauthoring",
                          "jats_publishing", "ms", "man", "latex", "beamer")),
    OptionSpec("strip_comments", "--strip-comments", SWITCH, "Remove HTML comments",
               "Leave out HTML comments found in Markdown, Textile or HTML input. Pandoc "
               "option --strip-comments.", "layout", default=False, negatable=True,
               reader=True, inputs=_o(MARKDOWN_INPUTS, "textile", "html")),

    # ------------------------------------------------------------- Web pages and slides
    OptionSpec("embed_resources", "--embed-resources", SWITCH,
               "Embed pictures, styles and scripts in one HTML file",
               "Make HTML output self-contained, so it works when copied on its own. Pandoc "
               "option --embed-resources.", "web", default=False, special=True,
               outputs=HTML_LIKE),
    OptionSpec("css", "--css", FILES, "Style sheets (CSS)",
               "CSS files or web addresses to link (or embed). Separate several with "
               "semicolons. Pandoc option --css.", "web", outputs=_o(HTML_LIKE, EPUB_LIKE),
               wildcard="Style sheets (*.css)|*.css|All files (*.*)|*.*",
               button="Choose Style Sheets..."),
    OptionSpec("section_divs", "--section-divs", SWITCH, "Wrap sections in section elements",
               "Put each section in an HTML section element. Pandoc option --section-divs.",
               "web", default=False, negatable=True, outputs=_o(HTML_LIKE, EPUB_LIKE)),
    OptionSpec("email_obfuscation", "--email-obfuscation", CHOICE, "Hide e-mail addresses",
               "How mailto links are hidden from spam robots. Pandoc option "
               "--email-obfuscation.", "web", default="",
               choices=(("", "Don't hide them"), ("javascript", "With JavaScript"),
                        ("references", "As character references")),
               outputs=HTML_LIKE),
    OptionSpec("id_prefix", "--id-prefix", TEXT, "Prefix for identifiers",
               "Text added before every generated id and footnote number, so documents can be "
               "combined in one page. Pandoc option --id-prefix.", "web",
               outputs=_o(HTML_LIKE, EPUB_LIKE, MARKDOWN_LIKE, "docbook", "docbook4",
                          "docbook5", "jats", "jats_archiving", "jats_articleauthoring",
                          "jats_publishing")),
    OptionSpec("title_prefix", "--title-prefix", TEXT, "Window title prefix",
               "Text added before the title shown in the browser's title bar. Pandoc option "
               "--title-prefix.", "web", outputs=HTML_LIKE),
    OptionSpec("html_q_tags", "--html-q-tags", SWITCH, "Use q elements for quotations",
               "Write quoted text with HTML q elements. Pandoc option --html-q-tags.", "web",
               default=False, negatable=True, outputs=_o(HTML_LIKE, EPUB_LIKE)),
    OptionSpec("incremental", "--incremental", SWITCH, "Show list items one at a time",
               "In slide shows, lists appear one item at a time. Pandoc option --incremental.",
               "web", default=False, negatable=True, outputs=SLIDES),
    OptionSpec("slide_level", "--slide-level", CHOICE, "Heading level that starts a slide",
               "Which heading level starts a new slide. Automatic picks the highest level "
               "followed directly by content. Pandoc option --slide-level.", "web", default="",
               choices=(("", "Automatic"), ("0", "None (only horizontal rules)"),
                        ("1", "Level 1"), ("2", "Level 2"), ("3", "Level 3"),
                        ("4", "Level 4"), ("5", "Level 5"), ("6", "Level 6")),
               outputs=SLIDES),

    # ------------------------------------------------------------- Office
    OptionSpec("reference_doc", "--reference-doc", FILE, "Reference document",
               "A Word, OpenDocument or PowerPoint file whose styles are used for the output. "
               "Use Save Default Reference Document to get pandoc's own one to restyle. Pandoc "
               "option --reference-doc.", "office", default="", outputs=OFFICE,
               wildcard="Office documents (*.docx;*.odt;*.pptx)|*.docx;*.odt;*.pptx|"
                        "All files (*.*)|*.*",
               button="Choose Reference Document..."),
    OptionSpec("link_images", "--link-images", SWITCH, "Link pictures instead of embedding them",
               "In OpenDocument output, refer to picture files instead of storing them in the "
               "document. Pandoc option --link-images.", "office", default=False,
               negatable=True, outputs=_o("odt")),
    OptionSpec("track_changes", "--track-changes", CHOICE, "Tracked changes in Word files",
               "What to do with tracked changes when reading Word files: accept them, reject "
               "them, or keep all of them marked up. Pandoc option --track-changes.", "office",
               default="",
               choices=(("", "Accept them (default)"), ("accept", "Accept them"),
                        ("reject", "Reject them"), ("all", "Keep all, marked up")),
               reader=True, inputs=_o("docx")),

    # ------------------------------------------------------------- E-books
    OptionSpec("epub_cover_image", "--epub-cover-image", FILE, "Cover picture",
               "A picture for the e-book's cover. Pandoc option --epub-cover-image.", "ebook",
               outputs=EPUB_LIKE, wildcard=IMAGES, button="Choose Cover Picture..."),
    OptionSpec("epub_title_page", "--epub-title-page", SWITCH, "Include a title page",
               "Start the e-book with a title page. Pandoc option --epub-title-page.", "ebook",
               default=True, negatable=True, outputs=EPUB_LIKE),
    OptionSpec("epub_metadata", "--epub-metadata", FILE, "E-book metadata file",
               "An XML file of Dublin Core metadata for the e-book. Pandoc option "
               "--epub-metadata.", "ebook", outputs=EPUB_LIKE,
               wildcard="XML files (*.xml)|*.xml|All files (*.*)|*.*",
               button="Choose Metadata XML..."),
    OptionSpec("epub_embed_font", "--epub-embed-font", FILES, "Fonts to embed",
               "Font files to store in the e-book. Separate several with semicolons. Pandoc "
               "option --epub-embed-font.", "ebook", outputs=EPUB_LIKE,
               wildcard="Fonts (*.ttf;*.otf;*.woff;*.woff2)|*.ttf;*.otf;*.woff;*.woff2|"
                        "All files (*.*)|*.*",
               button="Choose Fonts..."),
    OptionSpec("split_level", "--split-level", NUMBER, "Start a new file at heading level",
               "E-books and chunked HTML are split into one file per section at this heading "
               "level. Pandoc option --split-level.", "ebook", default=1, minimum=1,
               maximum=6, outputs=_o(EPUB_LIKE, "chunkedhtml")),
    OptionSpec("chunk_template", "--chunk-template", TEXT, "Chunk file names",
               "How chunked HTML files are named, for example %s-%i.html. Pandoc option "
               "--chunk-template.", "ebook", outputs=_o("chunkedhtml")),
    OptionSpec("epub_subdirectory", "--epub-subdirectory", TEXT, "Folder inside the e-book",
               "The folder inside the EPUB that holds its content. Pandoc option "
               "--epub-subdirectory.", "ebook", advanced=True, outputs=EPUB_LIKE),

    # ------------------------------------------------------------- PDF
    OptionSpec("pdf_engine", "--pdf-engine", COMBO, "PDF engine",
               "Program pandoc uses to make PDF files, for example xelatex, typst or "
               "weasyprint. It must be installed separately. Pandoc option --pdf-engine.",
               "pdf", default="", special=True, outputs=_o("pdf")),
    OptionSpec("pdf_engine_opt", "--pdf-engine-opt", LINES, "PDF engine options (one per line)",
               "Command-line options passed to the PDF engine. Pandoc option --pdf-engine-opt.",
               "pdf", outputs=_o("pdf")),
    OptionSpec("typst_input", "--typst-input", PAIRS, "Typst inputs (one key=value per line)",
               "Values passed to Typst as sys.inputs. Pandoc option --typst-input.", "pdf",
               outputs=_o("typst", "pdf")),

    # ------------------------------------------------------------- Input and media
    OptionSpec("extract_media", "--extract-media", SWITCH,
               "Save pictures from Word, OpenDocument, EPUB and PowerPoint files",
               "Pictures inside those files are saved to a folder next to the output, so text "
               "formats can link to them. Pandoc option --extract-media.", "input",
               default=True, special=True),
    OptionSpec("resource_path", "--resource-path", TEXT, "Where to look for pictures",
               "Extra folders, separated by semicolons, where pandoc looks for pictures and "
               "other files. The input file's folder is always searched. Pandoc option "
               "--resource-path.", "input", advanced=True, special=True),
    OptionSpec("default_image_extension", "--default-image-extension", TEXT,
               "Default picture extension",
               "Extension added to picture names that have none, for example .png. Pandoc "
               "option --default-image-extension.", "input", advanced=True, reader=True,
               inputs=_o(MARKDOWN_INPUTS, "latex")),
    OptionSpec("abbreviations", "--abbreviations", FILE, "Abbreviations file",
               "A list of abbreviations (like Mr.) that don't end a sentence. Pandoc option "
               "--abbreviations.", "input", advanced=True, reader=True,
               button="Choose Abbreviations..."),
    OptionSpec("file_scope", "--file-scope", SWITCH, "Read each input file on its own",
               "When files are joined, read each one separately so footnotes and links don't "
               "clash. Pandoc option --file-scope.", "input", default=False, negatable=True,
               advanced=True, reader=True),
    OptionSpec("ipynb_output", "--ipynb-output", CHOICE, "Notebook output cells",
               "Which output cells of Jupyter notebooks are kept: the best one for the output "
               "format, all of them, or none. Pandoc option --ipynb-output.", "input",
               default="",
               choices=(("", "The best one (default)"), ("best", "The best one"),
                        ("all", "All of them"), ("none", "None")),
               reader=True, inputs=_o("ipynb")),
    OptionSpec("request_header", "--request-header", PAIRS,
               "Web request headers (one name=value per line)",
               "Headers sent when pandoc downloads pictures or pages from the web, for example "
               "User-Agent=Mozilla. Pandoc option --request-header.", "input", advanced=True),
    OptionSpec("no_check_certificate", "--no-check-certificate", SWITCH,
               "Skip web security certificate checks",
               "Warning: this makes downloads from the web unsafe. Only use it for a trusted "
               "server with a broken certificate. Pandoc option --no-check-certificate.",
               "input", default=False, negatable=True, advanced=True),
    OptionSpec("sandbox", "--sandbox", SWITCH, "Sandbox (no file or web access)",
               "Pandoc may only read the input files and must not use the web or other files. "
               "Use it for documents you don't trust. Pandoc option --sandbox.", "input",
               default=False, negatable=True, advanced=True),

    # ------------------------------------------------------------- Filters
    OptionSpec("lua_filters", "", FILTERS, "Filters, in the order they run",
               "Lua filters (files ending in .lua) and filter programs run on the document in "
               "this order. Pandoc options --lua-filter and --filter.", "filters", default="",
               special=True),

    # ------------------------------------------------------------- Command line
    OptionSpec("extra_args", "", TEXT, "Extra pandoc arguments",
               "Any other pandoc command-line options, exactly as you would type them, for "
               "example --columns=100 --metadata author=\"Ada Lovelace\". For experts; every "
               "option also has a control on the other pages.", "command", default="",
               special=True),
    OptionSpec("verbose", "--verbose", SWITCH, "Detailed messages",
               "Pandoc writes detailed messages to the log. Pandoc option --verbose.",
               "command", default=False, advanced=True),
    OptionSpec("quiet", "--quiet", SWITCH, "Hide warnings",
               "Pandoc doesn't write warnings to the log. Pandoc option --quiet.", "command",
               default=False, advanced=True),
    OptionSpec("fail_if_warnings", "--fail-if-warnings", SWITCH, "Treat warnings as errors",
               "The conversion fails when pandoc warns about something. Pandoc option "
               "--fail-if-warnings.", "command", default=False, negatable=True,
               advanced=True),
    OptionSpec("trace", "--trace", SWITCH, "Trace the reader (for debugging)",
               "Pandoc writes debugging details about reading the input. Pandoc option "
               "--trace.", "command", default=False, negatable=True, advanced=True),
    OptionSpec("log_file", "--log", SAVEFILE, "Save pandoc's messages to a JSON file",
               "Pandoc writes every message, as JSON, to this file. Pandoc option --log.",
               "command", advanced=True,
               wildcard="JSON files (*.json)|*.json|All files (*.*)|*.*",
               button="Choose Log File..."),
]

BY_KEY: Dict[str, OptionSpec] = {s.key: s for s in OPTIONS}

# Flags pandoc 3.13 has that are deliberately not offered as controls:
# deprecated ones and ones for shell completion or debugging the command line.
NOT_OFFERED = {
    "self-contained", "base-header-level", "epub-chapter-level", "no-highlight",
    "highlight-style", "dump-args", "ignore-args", "completion", "bash-completion",
    "math-method", "mathml", "webtex", "mathjax", "katex", "gladtex",  # via "Math rendering"
    "citeproc", "natbib", "biblatex",                                  # via "How citations..."
    "filter", "lua-filter",                                            # via "Filters"
    "from", "read", "to", "write", "output", "version", "help",        # set by the app
    "list-input-formats", "list-output-formats", "list-extensions",    # used by the app
    "list-highlight-languages", "list-highlight-styles", "print-default-template",
    "print-default-data-file", "print-highlight-style",
    "table-of-contents", "list-of-figures", "list-of-tables",          # aliases
}


# ---------------------------------------------------------------------------
# Applying options
# ---------------------------------------------------------------------------


def base_format(fmt: Optional[str]) -> str:
    """"docx+styles" -> "docx"."""
    return re.split(r"[+-]", fmt or "", maxsplit=1)[0]


def applies(spec: OptionSpec, to_format: str, from_format: Optional[str] = None) -> bool:
    """Whether ``spec`` matters for this output (and input) format."""
    to = base_format(to_format)
    if spec.outputs is not None and to not in spec.outputs:
        return False
    if to in spec.exclude_outputs:
        return False
    if spec.inputs is not None and from_format:
        if base_format(from_format) not in spec.inputs:
            return False
    return True


def get_value(opts, spec: OptionSpec) -> Any:
    """The stored value of ``spec`` (its default when unset)."""
    if spec.key != "values" and spec.key in getattr(opts, "__dataclass_fields__", {}):
        return getattr(opts, spec.key)
    return getattr(opts, "values", {}).get(spec.key, spec.default)


def set_value(opts, spec: OptionSpec, value: Any) -> None:
    if spec.key != "values" and spec.key in getattr(opts, "__dataclass_fields__", {}):
        setattr(opts, spec.key, value)
        return
    if _is_default(spec, value):
        opts.values.pop(spec.key, None)
    else:
        opts.values[spec.key] = value


def _is_default(spec: OptionSpec, value: Any) -> bool:
    if value is None:
        return True
    if spec.kind in (TEXT, FILE, SAVEFILE, FILES, FOLDER, PAIRS, LINES, COMBO, FILTERS):
        return not str(value).strip()
    if spec.kind == CHOICE:
        return value in ("", spec.default)
    return value == spec.default


def split_list(text: str) -> List[str]:
    """Split a ";"-separated list of files."""
    return [part.strip() for part in str(text or "").split(";") if part.strip()]


def split_lines(text: str) -> List[str]:
    return [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]


def option_args(spec: OptionSpec, value: Any) -> List[str]:
    """Command-line arguments for one (non-special) option and its value."""
    if _is_default(spec, value):
        return []
    flag = spec.flag
    if spec.kind == SWITCH:
        on = bool(value)
        if on and not spec.default:
            return [flag]
        if spec.negatable:
            return [f"{flag}={'true' if on else 'false'}"]
        return []
    if spec.kind == NUMBER:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return []
        n = max(spec.minimum, min(spec.maximum, n))
        return [] if n == spec.default else [f"{flag}={n}"]
    if spec.kind in (CHOICE, COMBO, TEXT, FILE, SAVEFILE, FOLDER):
        return [f"{flag}={str(value).strip()}"]
    if spec.kind == FILES:
        return [f"{flag}={v}" for v in split_list(value)]
    if spec.kind in (PAIRS, LINES):
        return [f"{flag}={v}" for v in split_lines(value)]
    return []


def generic_args(opts, to_format: str, from_format: Optional[str],
                 flags: Optional[set] = None, reader: Optional[bool] = None) -> List[str]:
    """Arguments for every table option that build_args doesn't handle itself.

    ``reader`` True gives only the options used when reading the source,
    False only the others, None all of them. ``flags`` (from
    ``supported_flags``) leaves out options the running pandoc doesn't have.
    """
    args: List[str] = []
    for spec in OPTIONS:
        if spec.special or not spec.flag:
            continue
        if reader is not None and spec.reader != reader:
            continue
        if flags is not None and spec.name not in flags:
            continue
        if not applies(spec, to_format, from_format):
            continue
        args += option_args(spec, get_value(opts, spec))
    return args


def extension_suffix(changes: Optional[Dict[str, bool]]) -> str:
    """{"styles": True, "citations": False} -> "+styles-citations"."""
    if not changes:
        return ""
    return "".join(("+" if on else "-") + name for name, on in sorted(changes.items()))


# ---------------------------------------------------------------------------
# What the running pandoc supports
# ---------------------------------------------------------------------------

_FLAG_RE = re.compile(r"--([a-z][a-z0-9-]*)")


def parse_help_flags(help_text: str) -> set:
    """Long option names (without dashes) listed in ``pandoc --help``."""
    return set(_FLAG_RE.findall(help_text or ""))


def parse_extensions(text: str) -> List[Tuple[str, bool]]:
    """Parse ``pandoc --list-extensions=FMT``: [("smart", True), ...]."""
    out: List[Tuple[str, bool]] = []
    for tok in (text or "").split():
        if len(tok) > 1 and tok[0] in "+-":
            out.append((tok[1:], tok[0] == "+"))
    return out


def visible_specs(page: str, to_format: str, from_format: Optional[str] = None,
                  advanced: bool = False, flags: Optional[set] = None) -> List[OptionSpec]:
    """The options shown on ``page`` for this output format."""
    out = []
    for spec in OPTIONS:
        if spec.page != page:
            continue
        if spec.advanced and not advanced:
            continue
        if flags is not None and spec.flag and spec.name not in flags \
                and spec.key not in ("highlight_style",):
            continue
        if not applies(spec, to_format, from_format):
            continue
        out.append(spec)
    return out


# ---------------------------------------------------------------------------
# Access keys
# ---------------------------------------------------------------------------


def assign_access_keys(labels: Sequence[str], reserved: Iterable[str] = ()) -> List[str]:
    """Give every label a unique Alt+letter key ("&Title").

    Labels that already contain "&" keep their key. Otherwise the first
    unused letter that starts a word is taken, then any unused letter, then
    a digit added in brackets. ``reserved`` letters are never given out.
    """
    used = {c.lower() for c in reserved}
    for lab in labels:
        m = re.search(r"&([^&])", lab)
        if m:
            used.add(m.group(1).lower())
    out: List[str] = []
    for lab in labels:
        if re.search(r"&[^&]", lab):
            out.append(lab)
            continue
        idx = None
        starts = [i for i, ch in enumerate(lab)
                  if ch.isalnum() and (i == 0 or not lab[i - 1].isalnum())]
        for i in starts + list(range(len(lab))):
            ch = lab[i]
            if ch.isalnum() and ch.isascii() and ch.lower() not in used:
                idx = i
                break
        if idx is None:
            digit = next((d for d in "123456789" if d not in used), None)
            if digit is None:
                out.append(lab)
                continue
            used.add(digit)
            if lab.endswith("..."):
                out.append(f"{lab[:-3]} (&{digit})...")
            else:
                out.append(f"{lab} (&{digit})")
            continue
        used.add(lab[idx].lower())
        out.append(lab[:idx] + "&" + lab[idx:])
    return out


__all__ = [
    "OptionSpec", "OPTIONS", "BY_KEY", "PAGES", "NOT_OFFERED", "applies", "get_value",
    "set_value", "option_args", "generic_args", "extension_suffix", "parse_help_flags",
    "parse_extensions", "visible_specs", "assign_access_keys", "base_format", "split_list",
    "split_lines",
]
