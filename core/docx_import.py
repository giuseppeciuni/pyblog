"""
Import a Word document (.docx) and turn it into HTML the Quill editor can edit.

A .docx is a ZIP archive of XML parts, so no library is needed: zipfile opens
the archive, xml.etree parses the parts. The pieces that matter are

    word/document.xml            the text itself
    word/_rels/document.xml.rels the targets of images and hyperlinks
    word/styles.xml              the styles a run or paragraph inherits from
    word/numbering.xml           whether a list is bulleted or numbered
    word/footnotes.xml           footnotes (and word/endnotes.xml, endnotes)
    word/media/                  the embedded image files

The conversion keeps what a blog article needs - title, headings, emphasis,
superscript, alignment, lists, quotes, code, tables with merged cells,
images with their alternative text, links, footnotes - and drops the rest of
Word's machinery: page breaks, the table of contents (the site builds its
own), field codes, hidden text. Anything it does not recognise degrades to
plain text rather than raising, because a real document from Word,
LibreOffice or Google Docs will always contain something unexpected.

THE SHAPE OF THE OUTPUT MATTERS AS MUCH AS ITS CONTENT. The result is put
into Quill 1.3.7, and Quill only keeps what it can map onto its own model:

  - a list nested inside a list item makes Quill throw the WHOLE list away
    when the HTML is loaded, so lists are written flat, the way Quill writes
    them itself: <li class="ql-indent-1"> for a second-level item;
  - a line break between two blocks becomes an empty paragraph in Quill, so
    the blocks are joined with nothing between them;
  - a table is wrapped in the div.raw-html-block the editor registers a blot
    for, otherwise Quill deletes it.

Nothing in here trusts the document: every piece of text goes through
html.escape, every hyperlink is checked against a scheme allowlist, and every
extracted image is put through the same validation as a manual upload.
"""
import html
import io
import re
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

from core.articles import (requested_slug, save_article, save_uploaded_file,
                           slugify, validate_upload)
from core.config import main_language
from core.i18n import T

# OOXML namespaces. ElementTree spells a namespaced tag "{uri}local", so we
# keep the braces in the constants and write W + "p" for a paragraph.
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"

# Paragraph styles, recognised by style id or by style name, lowercased with
# everything but letters and digits removed. Word writes the English name of
# a built-in style in styles.xml whatever the interface language ("heading
# 1", "Title"), but the style id is localised ("Titolo1", "Titolo"), and
# LibreOffice has names of its own ("Quotations"). Both are checked.
HEADING_STYLE_NAMES = {}
for _level in (1, 2, 3, 4, 5, 6):
    for _prefix in ("heading", "titolo", "titre", "berschrift", "ttulo", "titulo", "kop"):
        HEADING_STYLE_NAMES[_prefix + str(_level)] = _level

TITLE_STYLE_NAMES = {"title", "titolo", "titel", "titre", "ttulo", "titulo"}
SUBTITLE_STYLE_NAMES = {"subtitle", "sottotitolo", "untertitel", "soustitre",
                        "subttulo", "subtitulo"}
QUOTE_STYLE_NAMES = {"quote", "intensequote", "citazione", "citazioneintensa",
                     "quotations", "blockquotation", "blocktext", "zitat",
                     "intensiveszitat", "citation", "citationintense", "cita",
                     "citadestacada"}
CODE_STYLE_NAMES = {"htmlpreformatted", "htmlpreformattato", "preformattedtext",
                    "testopreformattato", "code", "codice", "sourcecode",
                    "sourcetext", "plaintext", "macrotext"}
# The entries of Word's own table of contents: "toc 1" ... "toc 9", and the
# heading Word puts above it. The site builds its own index of the headings.
TOC_STYLE_PATTERN = re.compile(r"(toc|sommario|verzeichnis|tdm)\d")
TOC_HEADING_STYLE_NAMES = {"tocheading", "titolosommario", "inhaltsverzeichnisberschrift",
                           "entte", "ttulodetdc"}

# Fonts that mark a run as code. Matched as substrings of the lowercased name,
# so "Courier New", "Consolas" and "Source Code Pro" all count.
MONOSPACE_FONT_HINTS = ("mono", "courier", "consol", "menlo", "monaco", "code",
                        "typewriter")

# Fonts whose characters are pictures (arrows, ticks, bullets) at private code
# points: copying the character would show a meaningless box.
SYMBOL_FONTS = ("symbol", "wingdings", "webdings", "marlett")

# Schemes a hyperlink may use. Anything else (javascript:, data:, file:) is
# dropped and the link text is kept as plain text.
ALLOWED_LINK_SCHEMES = ("http://", "https://", "mailto:")

# How deep we follow a chain of w:basedOn styles before giving up. A malformed
# document can point a style at itself; this stops the walk instead of looping.
MAX_STYLE_DEPTH = 12

# Word nests tables inside table cells for layout. We render the outer table
# and flatten anything deeper to its text, which keeps the content without
# producing a grid nobody asked for.
MAX_TABLE_DEPTH = 0

# Quill indents list items from 1 to 8 levels.
MAX_LIST_LEVEL = 8

# An image wider than this is left without a width, so it fills the column of
# the article (680-720 pixels) instead of being held at its Word size.
MAX_IMAGE_WIDTH = 680

# English Metric Units per pixel at 96 dpi: Word measures drawings in EMU.
EMU_PER_PIXEL = 9525

# No part of a .docx needs to be bigger than this once unpacked. A ZIP can
# hold a part that expands to gigabytes; it is refused before it is read.
MAX_PART_BYTES = 64 * 1024 * 1024


def _local(tag):
    """The local name of a namespaced tag ("{uri}p" -> "p")."""
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _style_key(name):
    """A style id or name reduced to lowercase letters and digits."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _on_off(element):
    """
    Read a Word on/off property, such as <w:b/> or <w:b w:val="0"/>.

    Word writes the property with no value to switch it ON, and with a value
    of 0/false/off to switch it OFF. Returning None (the element is absent)
    is different from returning False: absent means "inherit from the style",
    False means "the style says bold, this run says no".
    """
    if element is None:
        return None
    value = element.get(W + "val")
    if value is None:
        return True
    if value in ("0", "false", "off"):
        return False
    return True


def _is_monospace(font):
    """Tell whether a font name is a monospaced one, i.e. a code font."""
    if not font:
        return False
    lowered = font.lower()
    for hint in MONOSPACE_FONT_HINTS:
        if hint in lowered:
            return True
    return False


def _plain(html_value):
    """The text of a piece of HTML, without tags and entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", html_value)).strip()


# ---------------------------------------------------------------------------
# PARTS, RELATIONSHIPS, STYLES, NUMBERING
# ---------------------------------------------------------------------------

def _read_part(archive, name):
    """
    Read one part of the archive, or None when it is not there or when it
    would unpack to more than MAX_PART_BYTES.
    """
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        return None
    return archive.read(info)


def _part_too_big(archive, name):
    """Tell whether a part exists but is too large to be read safely."""
    try:
        return archive.getinfo(name).file_size > MAX_PART_BYTES
    except KeyError:
        return False


def _parse_xml(data):
    """Parse an XML part, returning None instead of raising on bad input."""
    if data is None:
        return None
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None


def parse_relationships(archive):
    """
    Read word/_rels/document.xml.rels into {relationship id: {target, external}}.

    Every image and every hyperlink in document.xml is a reference by id; this
    map is what turns "rId7" into "media/image1.png" or into a URL.
    """
    root = _parse_xml(_read_part(archive, "word/_rels/document.xml.rels"))
    relationships = {}
    if root is None:
        return relationships
    for element in root:
        if _local(element.tag) != "Relationship":
            continue
        rel_id = element.get("Id")
        target = element.get("Target", "")
        if rel_id is None or target == "":
            continue
        external = element.get("TargetMode", "") == "External"
        relationships[rel_id] = {"target": target, "external": external}
    return relationships


def _empty_format():
    """Formatting that says nothing: every property inherits."""
    return {"bold": None, "italic": None, "underline": None, "strike": None,
            "valign": None, "position": None, "hidden": None, "font": None}


def _read_run_properties(run_properties):
    """
    Read the character properties we support out of a w:rPr element.

    Every value is None when the element does not say anything about it, so
    the layers (paragraph style, character style, the run itself) can be
    stacked with the more specific one winning.
    """
    result = _empty_format()
    if run_properties is None:
        return result
    result["bold"] = _on_off(run_properties.find(W + "b"))
    result["italic"] = _on_off(run_properties.find(W + "i"))
    strike = _on_off(run_properties.find(W + "strike"))
    double = _on_off(run_properties.find(W + "dstrike"))
    if strike is not None or double is not None:
        result["strike"] = bool(strike) or bool(double)

    underline = run_properties.find(W + "u")
    if underline is not None:
        # "none" is how Word switches an inherited underline back off.
        result["underline"] = underline.get(W + "val", "single") != "none"

    vertical = run_properties.find(W + "vertAlign")
    if vertical is not None:
        value = vertical.get(W + "val", "baseline")
        if value == "superscript":
            result["valign"] = "super"
        elif value == "subscript":
            result["valign"] = "sub"
        else:
            result["valign"] = ""

    # Raised or lowered text. LibreOffice writes a superscript this way when
    # it comes from HTML, and so do some converters: a number of half-points
    # up or down instead of the vertAlign above.
    position = run_properties.find(W + "position")
    if position is not None:
        try:
            result["position"] = int(position.get(W + "val", "0"))
        except ValueError:
            result["position"] = None

    # w:vanish is hidden text; w:webHidden is text hidden in a web view, which
    # is what Word does to the page numbers of its table of contents.
    hidden = _on_off(run_properties.find(W + "vanish"))
    web_hidden = _on_off(run_properties.find(W + "webHidden"))
    if hidden is not None or web_hidden is not None:
        result["hidden"] = bool(hidden) or bool(web_hidden)

    fonts = run_properties.find(W + "rFonts")
    if fonts is not None:
        font = fonts.get(W + "ascii") or fonts.get(W + "hAnsi") or fonts.get(W + "cs")
        if font:
            result["font"] = font
    return result


def _read_numbering_reference(element):
    """(numId, ilvl) of the w:numPr inside a pPr, each None when absent."""
    if element is None:
        return None, None
    number_properties = element.find(W + "numPr")
    if number_properties is None:
        return None, None
    num_id = None
    level = None
    id_element = number_properties.find(W + "numId")
    if id_element is not None:
        num_id = id_element.get(W + "val")
    level_element = number_properties.find(W + "ilvl")
    if level_element is not None:
        level = level_element.get(W + "val")
    return num_id, level


def _read_outline_level(paragraph_properties):
    """The w:outlineLvl of a pPr as a heading level (1-6), or None."""
    if paragraph_properties is None:
        return None
    outline = paragraph_properties.find(W + "outlineLvl")
    if outline is None:
        return None
    try:
        value = int(outline.get(W + "val", "9"))
    except ValueError:
        return None
    if 0 <= value <= 5:
        return value + 1
    return None


def parse_styles(archive):
    """
    Read word/styles.xml into {style id: properties}.

    For each style: what it is based on, its name, the character formatting
    it carries, and - for paragraph styles - the list and outline level it
    gives its paragraphs. Word puts bold on the "Strong" style rather than on
    the run, and numbering on the "List Bullet" style rather than on the
    paragraph, so a document can be full of bold text and lists without a
    single <w:b/> or <w:numPr/> in document.xml.
    """
    root = _parse_xml(_read_part(archive, "word/styles.xml"))
    styles = {}
    if root is None:
        return styles

    for style in root.findall(W + "style"):
        style_id = style.get(W + "styleId")
        if style_id is None:
            continue
        entry = {"based_on": None, "name": ""}

        name_element = style.find(W + "name")
        if name_element is not None:
            entry["name"] = name_element.get(W + "val", "")

        based_on = style.find(W + "basedOn")
        if based_on is not None:
            entry["based_on"] = based_on.get(W + "val")

        entry["format"] = _read_run_properties(style.find(W + "rPr"))
        paragraph_properties = style.find(W + "pPr")
        entry["num_id"], entry["num_level"] = _read_numbering_reference(paragraph_properties)
        entry["outline"] = _read_outline_level(paragraph_properties)
        styles[style_id] = entry
    return styles


def parse_numbering(archive):
    """
    Read word/numbering.xml into {numId: {level: "bullet" | "decimal" | "none"}}.

    A list paragraph only carries a numbering id and a level; the shape of the
    list lives here, in an abstract definition the numId points to, possibly
    with per-level overrides. When the part is missing or unreadable we return
    an empty map and the caller falls back to bulleted lists, which is the
    safe guess: a bullet where a number belonged is a small cosmetic loss,
    while numbers invented where there were none would be wrong.
    """
    root = _parse_xml(_read_part(archive, "word/numbering.xml"))
    if root is None:
        return {}

    def level_format(level):
        number_format = level.find(W + "numFmt")
        if number_format is None:
            return None
        value = number_format.get(W + "val", "bullet")
        if value in ("bullet", "none"):
            return value
        return "decimal"

    # abstractNumId -> {level: format}
    abstract = {}
    for abstract_num in root.findall(W + "abstractNum"):
        abstract_id = abstract_num.get(W + "abstractNumId")
        if abstract_id is None:
            continue
        levels = {}
        for level in abstract_num.findall(W + "lvl"):
            shape = level_format(level)
            if shape is not None:
                levels[level.get(W + "ilvl", "0")] = shape
        abstract[abstract_id] = levels

    # numId -> its abstract definition, with any level overridden on top.
    numbering = {}
    for num in root.findall(W + "num"):
        num_id = num.get(W + "numId")
        if num_id is None:
            continue
        abstract_ref = num.find(W + "abstractNumId")
        levels = {}
        if abstract_ref is not None:
            levels = dict(abstract.get(abstract_ref.get(W + "val"), {}))
        for override in num.findall(W + "lvlOverride"):
            level = override.find(W + "lvl")
            if level is None:
                continue
            shape = level_format(level)
            if shape is not None:
                levels[override.get(W + "ilvl", level.get(W + "ilvl", "0"))] = shape
        numbering[num_id] = levels
    return numbering


def parse_notes(archive, part, tag):
    """
    Read footnotes.xml or endnotes.xml into {id: w:footnote element}.

    The separator "notes" Word keeps in the same part (the line above the
    notes, its continuation) carry a w:type and are not notes at all.
    """
    root = _parse_xml(_read_part(archive, part))
    notes = {}
    if root is None:
        return notes
    for note in root.findall(W + tag):
        if note.get(W + "type") not in (None, "normal"):
            continue
        note_id = note.get(W + "id")
        if note_id is not None:
            notes[note_id] = note
    return notes


# ---------------------------------------------------------------------------
# THE CONVERTER
# ---------------------------------------------------------------------------

class DocxConverter:
    """
    Holds the state of one conversion: the archive, the resolved maps, the
    warnings collected along the way, the footnotes met so far, and the
    fields (Word's {HYPERLINK ...} and friends) currently open.
    """

    def __init__(self, archive, notes_heading="Note", image_prefix=""):
        self.archive = archive
        self.relationships = parse_relationships(archive)
        self.styles = parse_styles(archive)
        self.numbering = parse_numbering(archive)
        self.notes = {"footnote": parse_notes(archive, "word/footnotes.xml", "footnote"),
                      "endnote": parse_notes(archive, "word/endnotes.xml", "endnote")}
        self.notes_heading = notes_heading
        self.image_prefix = image_prefix
        self.warnings = []
        # relationship id -> saved URL, so an image used twice is stored once.
        self.saved_images = {}
        self.title = ""
        self.subtitle = ""
        # Footnotes and endnotes share one numbering, in order of reference.
        self.note_numbers = {}
        self.note_order = []
        # Complex fields still open, innermost last. Each one collects the
        # HTML of its result until its end mark says what to do with it.
        self.fields = []
        # Where the paragraph being rendered writes its pieces.
        self.paragraph_pieces = []
        # Text boxes met inside the paragraph being rendered: their
        # paragraphs are emitted after it, as blocks of their own.
        self.extra_entries = []

    def warn(self, key, **params):
        """
        Record a warning for the author. We store the i18n key and its
        parameters, not a sentence: the caller knows which language to show.
        """
        entry = {"key": key}
        entry.update(params)
        # The same warning about the same thing is not worth repeating.
        if entry not in self.warnings:
            self.warnings.append(entry)

    # --- Styles -------------------------------------------------------------

    def style_chain(self, style_id):
        """The style and the ones it is based on, the most specific first."""
        chain = []
        current = style_id
        while current is not None and current in self.styles and len(chain) < MAX_STYLE_DEPTH:
            entry = self.styles[current]
            if any(entry is seen for seen in chain):
                break
            chain.append(entry)
            current = entry["based_on"]
        return chain

    def style_kind(self, style_id):
        """
        What a paragraph style means for us: ("heading", level), ("title",),
        ("subtitle",), ("quote",), ("code",), ("toc",) or None.

        The style and its ancestors are tried in turn, the most specific
        first: a style based on "Heading 2" is a heading, while a style of
        its own that happens to be called "Mio sottotitolo" is not taken
        for the built-in "Subtitle".
        """
        if style_id is None:
            return None
        candidates = [(style_id, self.styles.get(style_id))]
        for entry in self.style_chain(style_id)[1:]:
            candidates.append((None, entry))
        for raw_id, entry in candidates:
            keys = []
            if raw_id is not None:
                keys.append(_style_key(raw_id))
            if entry is not None:
                keys.append(_style_key(entry["name"]))
            for key in keys:
                if key == "":
                    continue
                if key in HEADING_STYLE_NAMES:
                    return ("heading", HEADING_STYLE_NAMES[key])
                if key in TITLE_STYLE_NAMES:
                    return ("title",)
                if key in SUBTITLE_STYLE_NAMES:
                    return ("subtitle",)
                if TOC_STYLE_PATTERN.fullmatch(key) or key in TOC_HEADING_STYLE_NAMES:
                    return ("toc",)
                if key in QUOTE_STYLE_NAMES:
                    return ("quote",)
                if key in CODE_STYLE_NAMES:
                    return ("code",)
            if entry is not None and entry.get("outline") is not None:
                return ("heading", entry["outline"])
        return None

    def style_format(self, style_id):
        """The character formatting a style really carries, ancestors included."""
        resolved = _empty_format()
        for entry in reversed(self.style_chain(style_id)):
            for key in resolved:
                if entry["format"].get(key) is not None:
                    resolved[key] = entry["format"][key]
        return resolved

    def run_format(self, run, inherited):
        """
        Work out the formatting of a single run.

        Three layers, each overriding the one before: the paragraph style, the
        character style named by w:rStyle, and the run's own w:rPr. An explicit
        <w:b w:val="0"/> in the last layer switches off bold that came from
        the first, which is why the layers carry None ("say nothing") rather
        than False.
        """
        result = dict(inherited)
        properties = run.find(W + "rPr")
        if properties is None:
            return result
        style = properties.find(W + "rStyle")
        if style is not None:
            character_format = self.style_format(style.get(W + "val"))
            for key in result:
                if character_format.get(key) is not None:
                    result[key] = character_format[key]
        direct = _read_run_properties(properties)
        for key in result:
            if direct.get(key) is not None:
                result[key] = direct[key]
        return result

    # --- Inline content -----------------------------------------------------

    def _sink(self):
        """
        The list the next piece of HTML goes into.

        Inside a field, the pieces belong to the field until its end mark
        decides what they become (a link, nothing at all for a table of
        contents). Between a field's start and its separator the runs hold
        the field's instruction, which nobody is meant to read: those pieces
        go into a list that is thrown away.
        """
        if len(self.fields) > 0:
            top = self.fields[-1]
            if top["phase"] == "result":
                return top["parts"]
            return []
        return self.paragraph_pieces

    def emit(self, piece):
        """Add a piece of HTML to whatever is collecting it right now."""
        if piece:
            self._sink().append(piece)

    def wrap(self, text_html, fmt, context):
        """Put the formatting tags around a run of text."""
        if _plain(text_html) == "":
            # Spaces and line breaks need no formatting, and an image must
            # never end up wrapped in <strong>.
            return text_html
        if _is_monospace(fmt.get("font")) and not context.get("code_block"):
            text_html = "<code>" + text_html + "</code>"
        vertical = fmt.get("valign")
        if vertical is None and fmt.get("position") and len(_plain(text_html)) <= 6:
            # A few characters moved up or down are an exponent or an index;
            # a whole sentence moved up is a layout trick, left alone.
            vertical = "super" if fmt["position"] > 0 else "sub"
        if vertical == "super":
            text_html = "<sup>" + text_html + "</sup>"
        elif vertical == "sub":
            text_html = "<sub>" + text_html + "</sub>"
        if fmt.get("strike"):
            text_html = "<s>" + text_html + "</s>"
        # The underline of a link is the style of the link, not of the text.
        if fmt.get("underline") and not context.get("in_link"):
            text_html = "<u>" + text_html + "</u>"
        if fmt.get("italic"):
            text_html = "<em>" + text_html + "</em>"
        # Headings and header cells are bold already: a <strong> inside them
        # is noise that the author would only have to remove by hand.
        if fmt.get("bold") and not context.get("in_heading") and not context.get("in_header_cell"):
            text_html = "<strong>" + text_html + "</strong>"
        return text_html

    def render_inline(self, node, inherited, context):
        """Render the inline children of a paragraph, or of a wrapper inside it."""
        for child in node:
            name = _local(child.tag)
            if name == "r":
                self.render_run(child, inherited, context)
            elif name == "hyperlink":
                self.render_hyperlink(child, inherited, context)
            elif name == "fldSimple":
                self.render_simple_field(child, inherited, context)
            elif name in ("del", "moveFrom"):
                # Tracked deletions and the old place of moved text.
                continue
            elif name == "sdt":
                content = child.find(W + "sdtContent")
                if content is not None:
                    self.render_inline(content, inherited, context)
            elif name in ("ins", "moveTo", "smartTag", "customXml", "sdtContent",
                          "dir", "bdo"):
                self.render_inline(child, inherited, context)
            elif name in ("oMath", "oMathPara"):
                self.warn("warn_docx_equation")
            # pPr, bookmarks, proofing marks and comment anchors carry no text.

    def render_run(self, run, inherited, context):
        """Render one w:r, field marks included."""
        fmt = self.run_format(run, inherited)
        hidden = bool(fmt.get("hidden"))
        buffer = []

        def flush():
            if len(buffer) > 0 and not hidden:
                self.emit(self.wrap("".join(buffer), fmt, context))
            buffer.clear()

        for child in run:
            name = _local(child.tag)
            if name == "t":
                buffer.append(html.escape(child.text or "", quote=False))
            elif name == "tab":
                buffer.append(" ")
            elif name == "br":
                # Page and column breaks belong to paper, not to a web page:
                # a space keeps the words on either side apart.
                if child.get(W + "type") in (None, "textWrapping"):
                    buffer.append("<br>")
                else:
                    buffer.append(" ")
            elif name == "cr":
                buffer.append("<br>")
            elif name == "noBreakHyphen":
                buffer.append("-")
            elif name == "sym":
                font = (child.get(W + "font") or "").lower()
                code = child.get(W + "char") or ""
                if code != "" and not font.startswith(SYMBOL_FONTS):
                    try:
                        buffer.append(html.escape(chr(int(code, 16)), quote=False))
                    except ValueError:
                        pass
            elif name == "fldChar":
                flush()
                self.field_mark(child)
            elif name == "instrText":
                if len(self.fields) > 0 and self.fields[-1]["phase"] == "instr":
                    self.fields[-1]["instr"] = self.fields[-1]["instr"] + (child.text or "")
            elif name in ("footnoteReference", "endnoteReference"):
                flush()
                if not hidden:
                    self.emit(self.note_reference(name, child.get(W + "id")))
            elif name in ("drawing", "pict", "object", "AlternateContent"):
                flush()
                if not hidden:
                    self.emit(self.render_graphic(child, context))
            # softHyphen, delText, comment and footnote markers: nothing shown.
        flush()

    def render_hyperlink(self, element, inherited, context):
        """
        Render a w:hyperlink. The address comes from the relationships, and
        only http, https and mailto survive: a Word document can carry a
        javascript: or file: target, and neither belongs in a published page.
        An internal bookmark link keeps its text and loses the link.
        """
        inner = self.capture(element, inherited, dict(context, in_link=True))
        if inner == "":
            return
        rel_id = element.get(R + "id")
        relationship = None
        if rel_id is not None:
            relationship = self.relationships.get(rel_id)
        if relationship is None:
            self.emit(inner)
            return
        self.emit(self.link(relationship["target"], inner))

    def render_simple_field(self, element, inherited, context):
        """A w:fldSimple: the instruction is an attribute, the result is inside."""
        inner = self.capture(element, inherited, dict(context, in_link=True))
        self.emit(self.finish_field(element.get(W + "instr", ""), inner))

    def capture(self, element, inherited, context):
        """Render the children of an element into a string of their own."""
        holder = {"phase": "result", "parts": [], "instr": "", "capture": True}
        self.fields.append(holder)
        self.render_inline(element, inherited, context)
        # A field opened inside and never closed must not swallow what follows.
        while len(self.fields) > 0 and self.fields[-1] is not holder:
            self.fields.pop()
        if len(self.fields) > 0:
            self.fields.pop()
        return "".join(holder["parts"])

    def link(self, target, inner):
        """An <a> around inner, if the address may be published."""
        target = target.strip()
        lowered = target.lower()
        for scheme in ALLOWED_LINK_SCHEMES:
            if lowered.startswith(scheme):
                return '<a href="' + html.escape(target) + '">' + inner + "</a>"
        self.warn("warn_docx_link_skipped", href=target[:80])
        return inner

    def field_mark(self, element):
        """Handle a w:fldChar: the start, the separator or the end of a field."""
        kind = element.get(W + "fldCharType")
        if kind == "begin":
            self.fields.append({"phase": "instr", "parts": [], "instr": ""})
        elif kind == "separate":
            for field in reversed(self.fields):
                if not field.get("capture"):
                    field["phase"] = "result"
                    break
        elif kind == "end":
            for index in range(len(self.fields) - 1, -1, -1):
                if not self.fields[index].get("capture"):
                    field = self.fields.pop(index)
                    self.emit(self.finish_field(field["instr"], "".join(field["parts"])))
                    break

    def finish_field(self, instruction, inner):
        """
        Decide what a field becomes, from its instruction.

        HYPERLINK is a link like any other. TOC is Word's table of contents,
        which the site replaces with its own. PAGE, PAGEREF and NUMPAGES are
        page numbers, meaningless on a web page. Everything else - a
        reference, a figure number, a date - keeps the text Word showed.
        """
        words = instruction.strip().split()
        if len(words) == 0:
            return inner
        code = words[0].upper()
        if code == "HYPERLINK":
            match = re.match(r'\s*HYPERLINK\s+(\\l\s+)?"([^"]*)"', instruction, re.IGNORECASE)
            if match is not None and match.group(1) is None and inner != "":
                # The "Hyperlink" style underlines the text; the link is
                # underlined by the site's stylesheet already.
                return self.link(match.group(2), re.sub(r"</?u>", "", inner))
            return inner
        if code == "TOC":
            self.warn("warn_docx_toc_skipped")
            return ""
        if code in ("PAGE", "PAGEREF", "NUMPAGES", "SECTIONPAGES"):
            return ""
        return inner

    def note_reference(self, name, note_id):
        """The [n] mark of a footnote or endnote, numbered in reading order."""
        kind = "footnote"
        if name == "endnoteReference":
            kind = "endnote"
        if note_id is None or note_id not in self.notes[kind]:
            return ""
        key = (kind, note_id)
        if key not in self.note_numbers:
            self.note_numbers[key] = len(self.note_order) + 1
            self.note_order.append(key)
        return "<sup>[" + str(self.note_numbers[key]) + "]</sup>"

    # --- Images and text boxes ---------------------------------------------

    def render_graphic(self, element, context):
        """
        A drawing, a VML picture or an AlternateContent: an image, a text box,
        or both. A text box's paragraphs become blocks of their own after the
        current paragraph; an image is returned as an <img>.
        """
        if _local(element.tag) == "AlternateContent":
            element = self.choose_alternative(element)
            if element is None:
                return ""
        for box in list(element.iter(W + "txbxContent")):
            self.extra_entries.extend(self.render_box(box))
        if element.find(".//" + A + "blip") is not None or \
                element.find(".//" + V + "imagedata") is not None:
            return self.render_image(element)
        return ""

    def choose_alternative(self, element):
        """
        Pick one branch of an mc:AlternateContent. Word writes the same shape
        twice, as modern DrawingML in mc:Choice and as old VML in mc:Fallback;
        reading both would duplicate every text box.
        """
        for choice in element.findall(MC + "Choice"):
            if choice.find(".//" + A + "blip") is not None or \
                    choice.find(".//" + W + "txbxContent") is not None:
                return choice
        return element.find(MC + "Fallback")

    def render_box(self, box):
        """The blocks inside a text box, rendered without disturbing the paragraph around it."""
        saved = (self.paragraph_pieces, self.extra_entries, self.fields)
        self.paragraph_pieces = []
        self.extra_entries = []
        self.fields = []
        try:
            entries = self.render_blocks(box)
        finally:
            self.paragraph_pieces, self.extra_entries, self.fields = saved
        return entries

    def find_image_relationship_id(self, element):
        """
        Find the relationship id of an image, in either of the two ways Word
        writes one: the modern DrawingML <a:blip r:embed="..."> and the legacy
        VML <v:imagedata r:id="...">, still produced by older documents and by
        some converters.
        """
        blip = element.find(".//" + A + "blip")
        if blip is not None:
            embed = blip.get(R + "embed")
            if embed is not None:
                return embed
            link = blip.get(R + "link")
            if link is not None:
                return link
        image_data = element.find(".//" + V + "imagedata")
        if image_data is not None:
            rel_id = image_data.get(R + "id")
            if rel_id is not None:
                return rel_id
        return None

    def image_description(self, element):
        """
        The alternative text and the displayed width (in pixels) of an image.

        Word keeps the alternative text the author typed in wp:docPr, and the
        size the picture has on the page in wp:extent, in EMU. A legacy VML
        picture keeps both on v:shape instead.
        """
        alt = ""
        width = None
        properties = element.find(".//" + WP + "docPr")
        if properties is not None:
            alt = properties.get("descr") or properties.get("title") or ""
        extent = element.find(".//" + WP + "extent")
        if extent is not None:
            try:
                width = round(int(extent.get("cx", "0")) / EMU_PER_PIXEL)
            except ValueError:
                width = None
        shape = element.find(".//" + V + "shape")
        if shape is not None:
            if alt == "":
                alt = shape.get("alt") or ""
            match = re.search(r"width:\s*([\d.]+)pt", shape.get("style") or "")
            if width is None and match is not None:
                width = round(float(match.group(1)) * 96 / 72)
        return alt.strip(), width

    def render_image(self, element):
        """
        Extract an embedded image, save it in the media folder and return the
        <img> tag. Returns an empty string (plus a warning) when the image
        cannot be used, so one bad picture never stops the import.
        """
        rel_id = self.find_image_relationship_id(element)
        if rel_id is None:
            return ""
        alt, width = self.image_description(element)

        if rel_id not in self.saved_images:
            self.saved_images[rel_id] = self.save_image(rel_id)
        url = self.saved_images[rel_id]
        if url == "":
            return ""
        tag = '<img src="' + html.escape(url) + '"'
        if alt != "":
            tag = tag + ' alt="' + html.escape(alt) + '"'
        if width is not None and 0 < width < MAX_IMAGE_WIDTH:
            tag = tag + ' width="' + str(width) + '"'
        return tag + ' loading="lazy">'

    def save_image(self, rel_id):
        """Save the image a relationship points to; return its URL or ""."""
        relationship = self.relationships.get(rel_id)
        if relationship is None or relationship["external"]:
            # A linked (not embedded) image lives on the author's disk; the
            # bytes are simply not in the file.
            self.warn("warn_docx_image_missing", name=rel_id)
            return ""

        target = relationship["target"]
        # Targets are relative to word/, and may be written "../media/x.png".
        candidates = [
            "word/" + target.lstrip("/"),
            target.lstrip("/"),
            "word/" + target.replace("../", ""),
        ]
        data = None
        source_name = Path(target).name
        for candidate in candidates:
            if _part_too_big(self.archive, candidate):
                self.warn("warn_docx_image_skipped", name=source_name)
                return ""
            data = _read_part(self.archive, candidate)
            if data is not None:
                break
        if data is None:
            self.warn("warn_docx_image_missing", name=source_name)
            return ""

        # The same checks a manual upload goes through: extension whitelist,
        # magic bytes, SVG sanitising. Word happily embeds WMF and EMF, which
        # no browser can display, and those are refused here.
        check = validate_upload(source_name, data)
        if not check["ok"]:
            self.warn("warn_docx_image_skipped", name=source_name)
            return ""
        # "image1.png" is the name of the first picture of every Word file:
        # prefixed with the document's name, the media folder says where
        # each picture came from.
        saved_name = source_name
        if self.image_prefix != "":
            saved_name = self.image_prefix + "-" + source_name
        return save_uploaded_file(saved_name, check["data"])

    # --- Paragraphs ---------------------------------------------------------

    def paragraph_style_id(self, paragraph):
        """The w:pStyle of a paragraph, or None."""
        properties = paragraph.find(W + "pPr")
        if properties is None:
            return None
        style = properties.find(W + "pStyle")
        if style is None:
            return None
        return style.get(W + "val")

    def paragraph_alignment_class(self, paragraph):
        """
        Map Word's alignment onto the classes the editor and the public
        stylesheet already use, so an imported paragraph looks the same as one
        written in Quill.
        """
        properties = paragraph.find(W + "pPr")
        if properties is None:
            return ""
        alignment = properties.find(W + "jc")
        if alignment is None:
            return ""
        value = alignment.get(W + "val", "")
        if value == "center":
            return " class=\"ql-align-center\""
        if value in ("right", "end"):
            return " class=\"ql-align-right\""
        if value == "both":
            return " class=\"ql-align-justify\""
        return ""

    def paragraph_list_info(self, paragraph, style_id):
        """
        Return (level, "ul" | "ol") for a list paragraph, or None.

        The numbering can sit on the paragraph itself or on its style ("List
        Bullet" carries it); the paragraph wins. numId 0 means "explicitly not
        in a list", and a level whose format is "none" shows no bullet or
        number at all, so it is an ordinary paragraph to us.
        """
        num_id, level = _read_numbering_reference(paragraph.find(W + "pPr"))
        if num_id is None or level is None:
            for entry in self.style_chain(style_id):
                if num_id is None and entry.get("num_id") is not None:
                    num_id = entry["num_id"]
                if level is None and entry.get("num_level") is not None:
                    level = entry["num_level"]
        if num_id is None or num_id == "0":
            return None
        try:
            level_number = int(level or "0")
        except ValueError:
            level_number = 0
        level_number = max(0, min(level_number, MAX_LIST_LEVEL))

        levels = self.numbering.get(num_id)
        if levels is None:
            if len(self.numbering) == 0:
                self.warn("warn_docx_numbering_missing")
            return level_number, "ul"
        shape = levels.get(str(level_number), levels.get("0", "bullet"))
        if shape == "none":
            return None
        if shape == "decimal":
            return level_number, "ol"
        return level_number, "ul"

    def paragraph_is_monospace(self, paragraph, inherited):
        """Tell whether every piece of text in a paragraph is set in a code font."""
        seen = 0
        for run in paragraph.iter(W + "r"):
            text = "".join(t.text or "" for t in run.findall(W + "t"))
            if text.strip() == "":
                continue
            seen = seen + 1
            if not _is_monospace(self.run_format(run, inherited).get("font")):
                return False
        return seen > 0

    def paragraph_code_text(self, paragraph, inherited):
        """The text of a code paragraph, spaces and line breaks preserved."""
        pieces = []

        def walk(node):
            for child in node:
                name = _local(child.tag)
                if name == "r":
                    if self.run_format(child, inherited).get("hidden"):
                        continue
                    for part in child:
                        part_name = _local(part.tag)
                        if part_name == "t":
                            pieces.append(part.text or "")
                        elif part_name == "tab":
                            pieces.append("    ")
                        elif part_name in ("br", "cr"):
                            pieces.append("\n")
                elif name in ("del", "moveFrom", "pPr"):
                    continue
                else:
                    walk(child)

        walk(paragraph)
        return "".join(pieces)

    def render_paragraph(self, paragraph, context=None):
        """
        Render one w:p into a list of entries for the assembler: the paragraph
        itself, followed by the paragraphs of any text box it anchors.

        An entry is a dict with a "kind": title, subtitle, heading, item,
        quote, code, para, empty or skip.
        """
        if context is None:
            context = {}
        style_id = self.paragraph_style_id(paragraph)
        kind = self.style_kind(style_id)
        if kind is None:
            outline = _read_outline_level(paragraph.find(W + "pPr"))
            if outline is not None:
                kind = ("heading", outline)
        inherited = self.style_format(style_id)
        if kind is not None and kind[0] == "quote":
            # A quotation style is usually italic, and the site shows a
            # quotation in italics anyway: only italics the author added by
            # hand inside it are kept.
            inherited = dict(inherited, italic=None)

        heading_like = kind is not None and kind[0] in ("heading", "title", "subtitle")
        code_like = kind is not None and kind[0] == "code"
        if kind is None and self.paragraph_is_monospace(paragraph, inherited):
            code_like = True

        fields_open_before = len(self.fields) > 0
        saved_pieces = self.paragraph_pieces
        saved_extra = self.extra_entries
        self.paragraph_pieces = []
        self.extra_entries = []
        render_context = dict(context, in_heading=heading_like, code_block=code_like)
        self.render_inline(paragraph, inherited, render_context)
        inner = "".join(self.paragraph_pieces).strip()
        extra = self.extra_entries
        self.paragraph_pieces = saved_pieces
        self.extra_entries = saved_extra
        fields_open_after = len(self.fields) > 0

        if kind is not None and kind[0] == "toc":
            self.warn("warn_docx_toc_skipped")
            entry = {"kind": "skip"}
        elif (fields_open_before or fields_open_after) and inner == "":
            # A paragraph whose whole text went into a field that spans
            # several paragraphs: Word's table of contents. Nothing to show.
            entry = {"kind": "skip"}
        else:
            entry = self.classify(paragraph, style_id, kind, inner, code_like, inherited)
        return [entry] + extra

    def classify(self, paragraph, style_id, kind, inner, code_like, inherited):
        """Turn a rendered paragraph into the entry the assembler needs."""
        empty = _plain(inner) == "" and "<img" not in inner
        alignment = self.paragraph_alignment_class(paragraph)

        if kind is not None and kind[0] == "title":
            if empty:
                return {"kind": "empty"}
            return {"kind": "title", "text": _plain(inner), "html": inner}
        if kind is not None and kind[0] == "subtitle":
            if empty:
                return {"kind": "empty"}
            return {"kind": "subtitle", "text": _plain(inner), "html": inner,
                    "align": alignment}
        if kind is not None and kind[0] == "heading":
            if empty:
                return {"kind": "empty"}
            return {"kind": "heading", "level": kind[1], "html": inner, "align": alignment}

        list_info = self.paragraph_list_info(paragraph, style_id)
        if list_info is not None:
            if empty:
                return {"kind": "skip"}
            return {"kind": "item", "level": list_info[0], "list": list_info[1], "html": inner}

        if code_like:
            return {"kind": "code", "text": self.paragraph_code_text(paragraph, inherited)}
        if empty:
            return {"kind": "empty"}
        if kind is not None and kind[0] == "quote":
            return {"kind": "quote", "html": inner}
        return {"kind": "para", "html": inner, "align": alignment}

    # --- Tables -------------------------------------------------------------

    def own_rows(self, table):
        """
        The w:tr elements that belong to THIS table.

        They are usually direct children, but a real Word document wraps them
        in content controls (w:sdt) or tracked-change markers (w:ins) often
        enough that looking only one level down loses whole tables. We walk
        down through anything, stopping at a nested table, whose rows are not
        ours, and at a cell, which cannot contain a row of our own.
        """
        rows = []

        def walk(node):
            for child in node:
                name = _local(child.tag)
                if name in ("tbl", "tc", "del"):
                    continue
                if name == "tr":
                    rows.append(child)
                else:
                    walk(child)

        walk(table)
        return rows

    def own_cells(self, row):
        """The w:tc elements of a row, through the same wrappers."""
        cells = []

        def walk(node):
            for child in node:
                name = _local(child.tag)
                if name in ("tbl", "del"):
                    continue
                if name == "tc":
                    cells.append(child)
                else:
                    walk(child)

        walk(row)
        return cells

    def render_table(self, table, depth=0):
        """
        Render a w:tbl as the same <table class="article-table"> the editor
        produces, with the first row as the header and merged cells kept.

        Word merges cells across columns with w:gridSpan, which is HTML's
        colspan, and down rows with w:vMerge: the first cell says "restart"
        and every cell under it says "continue". Those continuation cells
        are not written: the first one gets a rowspan covering them.

        A table nested inside a cell is flattened to its text: Word uses
        nested tables for page layout, and a grid inside a grid is almost
        never what the author meant to publish.
        """
        if depth > MAX_TABLE_DEPTH:
            self.warn("warn_docx_nested_table")
            return self.flatten_table_text(table)

        rows = []
        for row in self.own_rows(table):
            cells = []
            column = 0
            for cell in self.own_cells(row):
                span = 1
                merge = None
                properties = cell.find(W + "tcPr")
                if properties is not None:
                    grid_span = properties.find(W + "gridSpan")
                    if grid_span is not None:
                        try:
                            span = max(1, int(grid_span.get(W + "val", "1")))
                        except ValueError:
                            span = 1
                    vertical = properties.find(W + "vMerge")
                    if vertical is not None:
                        merge = vertical.get(W + "val") or "continue"
                cells.append({"column": column, "span": span, "merge": merge,
                              "html": self.render_cell(cell, depth, len(rows) == 0)})
                column = column + span
            if len(cells) > 0:
                rows.append(cells)

        if len(rows) == 0:
            return ""

        for row_index, cells in enumerate(rows):
            for cell in cells:
                if cell["merge"] != "restart":
                    continue
                rowspan = 1
                for below in rows[row_index + 1:]:
                    continued = False
                    for other in below:
                        if other["column"] == cell["column"] and other["merge"] == "continue":
                            continued = True
                            break
                    if not continued:
                        break
                    rowspan = rowspan + 1
                cell["rowspan"] = rowspan

        rows_html = []
        for row_index, cells in enumerate(rows):
            tag = "td"
            if row_index == 0:
                tag = "th"
            pieces = []
            for cell in cells:
                if cell["merge"] == "continue":
                    continue
                attributes = ""
                if cell["span"] > 1:
                    attributes = attributes + ' colspan="' + str(cell["span"]) + '"'
                if cell.get("rowspan", 1) > 1:
                    attributes = attributes + ' rowspan="' + str(cell["rowspan"]) + '"'
                pieces.append("<" + tag + attributes + ">" + cell["html"] + "</" + tag + ">")
            rows_html.append("<tr>" + "".join(pieces) + "</tr>")

        table_html = ('<table class="article-table"><tbody>'
                      + "".join(rows_html) + "</tbody></table>")

        # The wrapper is not decoration: it is what makes the table survive.
        #
        # Quill keeps a document model of its own and deletes any element it
        # has no blot for. A bare <table> is one of those, so an imported
        # table used to vanish the moment the editor normalised the content,
        # while the text and images around it (which Quill does understand)
        # came through fine. The editor registers a "rawHTML" blot bound to
        # div.raw-html-block, which is also what its own paste-from-Word path
        # produces, so emitting the same wrapper here makes an imported table
        # indistinguishable from one pasted or drawn in the editor - editable
        # with a double click, and saved unchanged.
        return ('<div class="raw-html-block" contenteditable="false">'
                + table_html + "</div>")

    def render_cell(self, cell, depth, header):
        """
        Render the blocks inside one table cell as inline HTML: the cells of
        the editor's tables hold text, images and line breaks, not blocks.
        Paragraphs are separated by <br>, list items keep a bullet.
        """
        pieces = []
        context = {"in_header_cell": header}

        def walk(node):
            for child in node:
                name = _local(child.tag)
                if name == "p":
                    for entry in self.render_paragraph(child, context):
                        text = self.entry_as_inline(entry)
                        if text != "":
                            pieces.append(text)
                elif name == "tbl":
                    nested = self.render_table(child, depth + 1)
                    if nested != "":
                        pieces.append(nested)
                elif name in ("sdt", "sdtContent", "ins", "moveTo", "customXml"):
                    walk(child)

        walk(cell)
        return "<br>".join(pieces)

    def entry_as_inline(self, entry):
        """An assembler entry flattened to inline HTML, for a table cell."""
        kind = entry["kind"]
        if kind in ("para", "heading", "quote", "subtitle", "title"):
            return entry["html"]
        if kind == "item":
            return "&bull; " + entry["html"]
        if kind == "code":
            return ("<code>" + html.escape(entry["text"], quote=False).replace("\n", "<br>")
                    + "</code>")
        return ""

    def flatten_table_text(self, table):
        """The text of a table, with no markup: used for nested tables."""
        pieces = []
        for text_element in table.iter(W + "t"):
            if text_element.text:
                pieces.append(html.escape(text_element.text, quote=False))
        return " ".join(pieces).strip()

    # --- The document body --------------------------------------------------

    def render_blocks(self, container):
        """Render the block-level children of the body (or of a text box)."""
        entries = []
        for element in self._block_children(container):
            name = _local(element.tag)
            if name == "p":
                entries.extend(self.render_paragraph(element))
            elif name == "tbl":
                table_html = self.render_table(element)
                if table_html != "":
                    entries.append({"kind": "table", "html": table_html})
            # sectPr (page setup), bookmarks and the rest carry no content.
        return entries

    def _block_children(self, container):
        """
        Yield the block-level children, stepping through the wrappers Word
        puts around content: content controls (w:sdt), custom XML and tracked
        insertions or moves all hold real paragraphs. Word's own table of
        contents is a content control too, and is left out whole.
        """
        for element in container:
            name = _local(element.tag)
            if name == "sdt":
                if self.is_table_of_contents(element):
                    self.warn("warn_docx_toc_skipped")
                    continue
                content = element.find(W + "sdtContent")
                if content is not None:
                    for inner in self._block_children(content):
                        yield inner
            elif name in ("customXml", "ins", "moveTo"):
                for inner in self._block_children(element):
                    yield inner
            elif name in ("del", "moveFrom"):
                continue
            else:
                yield element

    def is_table_of_contents(self, sdt):
        """Tell whether a content control holds Word's table of contents."""
        properties = sdt.find(W + "sdtPr")
        if properties is None:
            return False
        gallery = properties.find(".//" + W + "docPartGallery")
        if gallery is None:
            return False
        return "content" in (gallery.get(W + "val") or "").lower()

    def render_notes(self):
        """The footnotes and endnotes, as a numbered list under a heading."""
        if len(self.note_order) == 0:
            return ""
        items = []
        for kind, note_id in self.note_order:
            note = self.notes[kind][note_id]
            texts = []
            for paragraph in note.iter(W + "p"):
                saved = (self.paragraph_pieces, self.fields)
                self.paragraph_pieces = []
                self.fields = []
                style_id = self.paragraph_style_id(paragraph)
                self.render_inline(paragraph, self.style_format(style_id), {})
                text = "".join(self.paragraph_pieces).strip()
                self.paragraph_pieces, self.fields = saved
                if text != "":
                    texts.append(text)
            items.append("<li>" + " ".join(texts) + "</li>")
        return ("<h2>" + html.escape(self.notes_heading) + "</h2>"
                + "<ol>" + "".join(items) + "</ol>")

    def assemble(self, entries):
        """
        Turn the entries into the final HTML.

        This is where the document becomes an article: the title leaves the
        body, the headings move so the highest one is an <h2> (the <h1> of
        the page is the article title), consecutive code lines become one
        block, list items are gathered into Quill's flat lists, and empty
        lines are tidied up.
        """
        entries = [entry for entry in entries if entry["kind"] != "skip"]

        # 1) The title: the "Title" style if the document has one, otherwise
        #    a Heading 1 that opens the document. A Heading 1 further down is
        #    a section, and stays where it is.
        for index, entry in enumerate(entries):
            if entry["kind"] != "title":
                continue
            if self.title == "":
                self.title = entry["text"]
                entries[index] = {"kind": "skip"}
            else:
                # A second "Title" paragraph is used as a big heading.
                entries[index] = {"kind": "heading", "level": 1,
                                  "html": entry["html"], "align": ""}
        if self.title == "":
            for index, entry in enumerate(entries):
                if entry["kind"] == "empty":
                    continue
                if entry["kind"] == "heading" and entry["level"] == 1:
                    self.title = _plain(entry["html"])
                    entries[index] = {"kind": "skip"}
                break
        entries = [entry for entry in entries if entry["kind"] != "skip"]

        # 2) The subtitle is kept as the opening paragraph, and offered to the
        #    editor as a description.
        for index, entry in enumerate(entries):
            if entry["kind"] == "subtitle":
                if self.subtitle == "":
                    self.subtitle = entry["text"]
                entries[index] = {"kind": "para", "html": entry["html"],
                                  "align": entry.get("align", "")}

        # 3) Headings: the highest level used becomes h2.
        levels = [entry["level"] for entry in entries if entry["kind"] == "heading"]
        if len(levels) > 0:
            shift = min(levels) - 2
            for entry in entries:
                if entry["kind"] == "heading":
                    entry["level"] = max(2, min(6, entry["level"] - shift))

        # 4) Empty lines: one at most in a row, none at the start or the end.
        tidy = []
        for entry in entries:
            if entry["kind"] == "empty":
                if len(tidy) == 0 or tidy[-1]["kind"] == "empty":
                    continue
            tidy.append(entry)
        while len(tidy) > 0 and tidy[-1]["kind"] == "empty":
            tidy.pop()

        # 5) Output, gathering the runs of list items and of code lines.
        out = []
        index = 0
        while index < len(tidy):
            entry = tidy[index]
            kind = entry["kind"]
            if kind == "item":
                group = []
                while index < len(tidy) and tidy[index]["kind"] == "item":
                    group.append(tidy[index])
                    index = index + 1
                out.append(render_list(group))
                continue
            if kind == "code":
                lines = []
                while index < len(tidy) and tidy[index]["kind"] == "code":
                    lines.append(tidy[index]["text"])
                    index = index + 1
                out.append('<pre class="ql-syntax" spellcheck="false">'
                           + html.escape("\n".join(lines), quote=False) + "</pre>")
                continue
            if kind == "heading":
                level = str(entry["level"])
                out.append("<h" + level + entry["align"] + ">" + entry["html"]
                           + "</h" + level + ">")
            elif kind == "quote":
                out.append("<blockquote>" + entry["html"] + "</blockquote>")
            elif kind == "table":
                out.append(entry["html"])
            elif kind == "empty":
                # Word marks an empty line with an empty paragraph, and so
                # does Quill: we keep one, with the markup the editor writes.
                out.append("<p><br></p>")
            else:
                out.append("<p" + entry.get("align", "") + ">" + entry["html"] + "</p>")
            index = index + 1

        out.append(self.render_notes())
        # Nothing between the blocks: a line break there becomes an empty
        # paragraph once the editor loads the HTML.
        return "".join(out)

    def convert(self, body):
        """Convert the document body into the article HTML."""
        return self.assemble(self.render_blocks(body))


def render_list(items):
    """
    Turn a run of list paragraphs into lists the way Quill 1.3.7 writes them:
    flat, with the depth of each item in a ql-indent class.

    A nested <ul> inside an <li> looks like the natural translation, and it
    is what this function used to produce, but Quill cannot represent it:
    loading such a list into the editor throws the WHOLE list away, so a
    document with sub-points lost every point the moment it was imported. A
    change of list type starts a new list, which is also how Quill keeps a
    numbered sub-list under a bulleted one.
    """
    pieces = []
    current = None
    for item in items:
        if item["list"] != current:
            if current is not None:
                pieces.append("</" + current + ">")
            current = item["list"]
            pieces.append("<" + current + ">")
        level = item["level"]
        if level > 0:
            pieces.append('<li class="ql-indent-' + str(level) + '">' + item["html"] + "</li>")
        else:
            pieces.append("<li>" + item["html"] + "</li>")
    if current is not None:
        pieces.append("</" + current + ">")
    return "".join(pieces)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINTS
# ---------------------------------------------------------------------------

# The first bytes of every ZIP archive, and therefore of every .docx. A file
# that does not start with these is not worth unpacking.
ZIP_MAGIC = b"PK\x03\x04"


def looks_like_docx(binary_data):
    """Tell whether some bytes could be a .docx, from the ZIP signature."""
    return binary_data[:4] == ZIP_MAGIC


def notes_heading_for_site():
    """The heading of the notes section, in the language the articles are written in."""
    return T("docx_note_titolo", main_language())


def convert_docx(binary_data, fallback_title="Documento importato", notes_heading=None):
    """
    Convert a .docx file into HTML for the editor.

    Return {"ok": True, "title", "subtitle", "content", "warnings"}, or
    {"ok": False, "error_key": ...} when the file cannot be read at all. The
    warnings are i18n keys with parameters, so the caller picks the language.

    fallback_title is used when the document has no title of its own; it is
    the file name, and also the prefix of the saved image files.

    This function never raises on a malformed document: everything it cannot
    make sense of is skipped, and the parts it understood are still returned.
    """
    if notes_heading is None:
        notes_heading = notes_heading_for_site()
    if not looks_like_docx(binary_data):
        return {"ok": False, "error_key": "err_docx_not_a_zip"}

    try:
        archive = zipfile.ZipFile(io.BytesIO(binary_data))
    except (zipfile.BadZipFile, EOFError, ValueError):
        return {"ok": False, "error_key": "err_docx_not_a_zip"}

    try:
        with archive:
            if _part_too_big(archive, "word/document.xml"):
                return {"ok": False, "error_key": "err_docx_too_big"}
            document = _read_part(archive, "word/document.xml")
            if document is None:
                return {"ok": False, "error_key": "err_docx_no_document"}

            root = _parse_xml(document)
            if root is None:
                return {"ok": False, "error_key": "err_docx_parse"}

            body = root.find(W + "body")
            if body is None:
                return {"ok": False, "error_key": "err_docx_no_document"}

            prefix = ""
            if fallback_title:
                prefix = slugify(fallback_title)
            converter = DocxConverter(archive, notes_heading=notes_heading,
                                      image_prefix=prefix)
            content = converter.convert(body)
    except zipfile.BadZipFile:
        return {"ok": False, "error_key": "err_docx_not_a_zip"}
    except Exception as error:
        # A last line of defence. A document we cannot convert must produce a
        # clear message in the editor, never a traceback in the server log.
        return {"ok": False, "error_key": "err_docx_parse", "detail": str(error)}

    if _plain(content) == "" and "<img" not in content:
        return {"ok": False, "error_key": "err_docx_empty"}

    title = converter.title
    if title == "":
        title = fallback_title
        converter.warn("warn_docx_title_from_filename")

    return {"ok": True, "title": title, "subtitle": converter.subtitle,
            "content": content, "warnings": converter.warnings}


def convert_docx_file(path_value):
    """Convert a .docx from disk. The file name is the fallback title."""
    path_value = Path(path_value)
    try:
        data = path_value.read_bytes()
    except OSError as error:
        return {"ok": False, "error_key": "err_docx_unreadable", "detail": str(error)}
    return convert_docx(data, fallback_title=path_value.stem)


def import_docx_path(path_value):
    """
    Import one .docx file, or every .docx of a folder, as draft articles.

    Return (imported_count, messages) where messages is a list of lines
    already formatted for the console: the command line is the only caller,
    and it prints them as they come.
    """
    path_value = Path(path_value)
    if path_value.is_dir():
        files = sorted(path_value.glob("*.docx"))
    elif path_value.is_file():
        files = [path_value]
    else:
        return 0, [f"Error: {path_value} does not exist."]

    # Word writes a lock file next to an open document; it is not a document.
    files = [f for f in files if not f.name.startswith("~$")]

    imported = 0
    messages = []
    for current in files:
        result = convert_docx_file(current)
        if not result["ok"]:
            messages.append(f"  skipped: {current.name} ({result['error_key']})")
            continue
        data = {
            "title": result["title"],
            "description": result.get("subtitle", ""),
            "content": result["content"],
            # An imported document is never published straight away: the
            # conversion is lossy and deserves a look in the editor first.
            "status": "draft",
        }
        # A document whose title matches an existing article lands next to
        # it with a numbered slug: an import never replaces an article.
        slug = save_article(data, new_article=True)
        messages.append(f"  imported: {current.name} -> posts/{slug}.json (draft)")
        if slug != requested_slug(data):
            messages.append(f"    note: {requested_slug(data)} was already taken, saved as {slug}")
        for warning in result["warnings"]:
            messages.append("    warning: " + describe_warning(warning))
        imported = imported + 1
    return imported, messages


def describe_warning(warning):
    """
    A plain English rendering of a warning, for the command line. The web UI
    translates the same keys through the i18n dictionary instead.
    """
    key = warning.get("key", "")
    if key == "warn_docx_image_skipped":
        return f"image skipped ({warning.get('name', '')}): unsupported format"
    if key == "warn_docx_image_missing":
        return f"image not embedded in the document ({warning.get('name', '')})"
    if key == "warn_docx_link_skipped":
        return f"link dropped, address not allowed ({warning.get('href', '')})"
    if key == "warn_docx_nested_table":
        return "a nested table was flattened to text"
    if key == "warn_docx_numbering_missing":
        return "list numbering could not be read: bulleted lists were used"
    if key == "warn_docx_toc_skipped":
        return "Word's table of contents was left out: the site builds its own"
    if key == "warn_docx_equation":
        return "an equation could not be imported"
    if key == "warn_docx_title_from_filename":
        return "the document has no title of its own: the file name was used"
    return key
