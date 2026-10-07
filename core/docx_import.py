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
  - a <br> inside a block is deleted by Quill, which glues the two lines
    into one ("ciao mamma.Si sono qui!"): the lines of a paragraph of Word
    become blocks of their own, the way Quill itself writes a new line;
  - a picture shares its line with whatever text is in its paragraph, so a
    picture followed by its caption gets a paragraph to itself;
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
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"

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

# An image at least this wide fills the column of the article (680-720
# pixels) instead of being held at its Word size.
MAX_IMAGE_WIDTH = 680

# English Metric Units per pixel at 96 dpi: Word measures drawings in EMU,
# the page in twentieths of a point, and old VML pictures in points.
EMU_PER_PIXEL = 9525
EMU_PER_TWIP = 635
EMU_PER_POINT = 12700

# A picture that takes this share of the text width in Word went from margin
# to margin there, and goes from margin to margin in the article too.
FULL_WIDTH_SHARE = 0.9

# A picture no taller than this is an icon or a symbol, and stays in the
# line of text wherever it is. A bigger one that opens or closes a line gets
# a paragraph to itself (see _line_blocks).
INLINE_PICTURE_MAX = 48 * EMU_PER_PIXEL

# A floating picture whose top is lower than this under the top of the
# paragraph it is anchored to (half a centimetre, about one line of text)
# has text of that paragraph above it: it goes after the paragraph. One
# anchored higher goes before it.
FLOAT_BELOW_OFFSET = 180000

# Marks left in the inline HTML of a paragraph while it is being rendered:
# the places where the paragraph has to be cut into separate blocks. One is
# a line break; the other pair goes around a picture that needs a line of
# its own. A NUL cannot come from the document (XML forbids it) and
# html.escape never writes one, so a mark is never mistaken for text.
LINE_BREAK = "\x00br\x00"
PICTURE_OPEN = "\x00pic\x00"
PICTURE_CLOSE = "\x00/pic\x00"
CUT_PATTERN = re.compile("(" + re.escape(LINE_BREAK) + "|" + re.escape(PICTURE_OPEN)
                         + ".*?" + re.escape(PICTURE_CLOSE) + ")", re.DOTALL)

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


def _is_blank(html_value):
    """Tell whether a piece of inline HTML shows nothing: no text, no picture."""
    return _plain(html_value) == "" and "<img" not in html_value


def _without_marks(inline_html, line_break):
    """
    Inline HTML with its cut marks resolved in place, for what has to stay
    one line: a footnote takes a space for a line break. The pictures stay
    where they are.
    """
    return (inline_html.replace(LINE_BREAK, line_break)
            .replace(PICTURE_OPEN, "").replace(PICTURE_CLOSE, ""))


def _wrap_around_marks(inline_html, opening, closing):
    """
    Put a tag around a piece of inline HTML, leaving the cut marks outside
    it: a link that runs over a line break becomes one link per line, and a
    linked picture keeps its link when it moves to a line of its own.
    """
    pieces = []
    for part in CUT_PATTERN.split(inline_html):
        if part == LINE_BREAK or part.strip() == "":
            pieces.append(part)
        elif part.startswith(PICTURE_OPEN):
            picture = part[len(PICTURE_OPEN):-len(PICTURE_CLOSE)]
            pieces.append(PICTURE_OPEN + opening + picture + closing + PICTURE_CLOSE)
        else:
            pieces.append(opening + part + closing)
    return "".join(pieces)


# One piece of a link followed by another piece of the same link: the first
# closes where the second opens, with nothing between them.
SPLIT_LINK_PATTERN = re.compile(r'(<a href="[^"]*">)((?:(?!</?a[ >]).)*)</a>\1', re.DOTALL)


def _join_links(inline_html):
    """
    Put back together a link written in pieces. A link is closed and opened
    again around every mark (see _wrap_around_marks); where the mark did not
    cut the line after all - a picture in the middle of a linked sentence -
    the pieces are side by side, and are one link again.
    """
    while True:
        joined = SPLIT_LINK_PATTERN.sub(r"\1\2", inline_html)
        if joined == inline_html:
            return joined
        inline_html = joined


def _cut_lines(inline_html):
    """
    Cut the inline HTML of a paragraph at its marks. The result is a list of
    lines, one for every line break, and each line is a list of ("text",
    html) and ("picture", html) pieces in reading order.
    """
    lines = [[]]
    for part in CUT_PATTERN.split(inline_html):
        if part == "":
            continue
        if part == LINE_BREAK:
            lines.append([])
        elif part.startswith(PICTURE_OPEN):
            lines[-1].append(("picture", part[len(PICTURE_OPEN):-len(PICTURE_CLOSE)]))
        else:
            lines[-1].append(("text", part))
    return lines


def _line_blocks(line):
    """
    The blocks one line becomes: its text, and the pictures that open or
    close it on a line of their own - a picture and its caption, a sentence
    and the chart it announces. A picture with text on both sides is in the
    middle of a sentence, and stays there. Pictures with only spaces between
    them stay together, side by side as they were.
    """
    written = [index for index, (kind, value) in enumerate(line)
               if kind == "text" and not _is_blank(value)]
    blocks = []
    for index, (kind, value) in enumerate(line):
        if kind == "picture" and len(written) > 0 and written[0] < index < written[-1]:
            kind = "text"
        elif kind == "text" and _is_blank(value):
            # Spaces between two pictures are not a line of text: they stay
            # as the gap between the pictures.
            if len(blocks) > 0:
                blocks[-1][1] = blocks[-1][1] + " "
            continue
        if len(blocks) > 0 and blocks[-1][0] == kind:
            blocks[-1][1] = blocks[-1][1] + value
        else:
            blocks.append([kind, value])
    return [(kind, _join_links(value.strip())) for kind, value in blocks]


def _cell_html(inline_html):
    """
    The inline HTML of a paragraph for a table cell. A table is outside
    Quill's reach, so a line can end with a real <br> there: at every line
    break, and around the picture that would get a paragraph of its own
    anywhere else.
    """
    rows = []
    for line in _cut_lines(inline_html):
        blocks = _line_blocks(line)
        if len(blocks) == 0:
            rows.append("")
        for _, value in blocks:
            rows.append(value)
    while len(rows) > 0 and rows[0] == "":
        rows.pop(0)
    while len(rows) > 0 and rows[-1] == "":
        rows.pop()
    return "<br>".join(rows)


def _to_emu(text):
    """A whole number of EMU out of an attribute or an element, or None."""
    try:
        return int((text or "").strip())
    except ValueError:
        return None


def _style_length(style, name):
    """
    A length out of the style of a VML shape ("width:170.1pt;height:147pt"),
    in EMU, or None. Word and LibreOffice write these in points; inches are
    read too, anything else is left alone.
    """
    match = re.search(r"(?:^|;)\s*" + re.escape(name) + r"\s*:\s*(-?[\d.]+)(pt|in)\b",
                      style or "")
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if match.group(2) == "in":
        value = value * 72
    return round(value * EMU_PER_POINT)


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
        # Floating pictures and text boxes met inside the paragraph being
        # rendered, each with its placement (see float_placement) and its
        # entries: they are emitted before or after it, as blocks of their own.
        self.floats = []
        # The width of the text on the page, in EMU, once the body is known.
        self.text_width = None

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
                # a space keeps the words on either side apart. A line break
                # is a mark of its own, outside the formatting tags, so the
                # paragraph can be cut there.
                if child.get(W + "type") in (None, "textWrapping"):
                    flush()
                    if not hidden:
                        self.emit(LINE_BREAK)
                else:
                    buffer.append(" ")
            elif name == "cr":
                flush()
                if not hidden:
                    self.emit(LINE_BREAK)
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
                return _wrap_around_marks(
                    inner, '<a href="' + html.escape(target) + '">', "</a>")
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
        A drawing, a VML picture or an AlternateContent: pictures, text
        boxes, or both.

        A picture that sits in the line of text, the way Word's "in line
        with text" does, is returned as an <img>. A floating picture and a
        text box have no place in the line: they become blocks of their own,
        before or after the paragraph they are anchored to, and nothing is
        returned for them. Inside a list item a floating picture stays in
        the item: a block between two items would end the list there.
        """
        if _local(element.tag) == "AlternateContent":
            element = self.choose_alternative(element)
            if element is None:
                return ""
        parts = self.drawing_parts(element)
        if len(parts) == 0:
            return ""
        placement = self.float_placement(element)
        in_line = placement is None or bool(context.get("in_list_item"))
        if placement is None:
            # A text box in the line of text has no position of its own: its
            # paragraphs follow the one it is in.
            placement = {"where": "after", "offset": 0, "align": ""}

        inline = []
        entries = []
        # The pictures of one drawing - a group of two side by side - share
        # a paragraph, as they shared the drawing.
        pictures = []
        for kind, value in parts:
            if kind == "image" and in_line:
                inline.append(value)
            elif kind == "image":
                pictures.append(_without_marks(value, ""))
            else:
                if len(pictures) > 0:
                    entries.append({"kind": "para", "html": " ".join(pictures),
                                    "align": placement["align"]})
                    pictures = []
                entries.extend(value)
        if len(pictures) > 0:
            entries.append({"kind": "para", "html": " ".join(pictures),
                            "align": placement["align"]})
        if len(entries) > 0:
            self.floats.append(dict(placement, entries=entries))
        return "".join(inline)

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

    def drawing_parts(self, element):
        """
        What a drawing holds, in the order it is written: ("image", html)
        for every picture and ("box", entries) for every text box.

        A picture inside a text box belongs to the box, whose own paragraphs
        render it. Looking for pictures at any depth is what used to show a
        picture with a caption twice, the second time glued to the text of
        the paragraph and with the size of the frame around it.
        """
        found = []

        def walk(node, picture, shape, scale, grouped):
            for child in node:
                tag = child.tag
                if tag == W + "txbxContent":
                    found.append(("box", child, None, 1.0, False))
                elif tag == A + "blip":
                    found.append(("blip", child, picture, scale, grouped))
                elif tag == V + "imagedata":
                    found.append(("vml", child, shape, scale, grouped))
                elif tag == PIC + "pic":
                    walk(child, child, shape, scale, grouped)
                elif _local(tag) in ("wgp", "grpSp", "wpc"):
                    walk(child, picture, shape, scale * self.group_scale(child), True)
                elif isinstance(tag, str) and tag.startswith(V) and child.get("style"):
                    walk(child, picture, child, scale, grouped)
                else:
                    walk(child, picture, shape, scale, grouped)

        walk(element, None, None, 1.0, False)

        # The frame of the drawing itself: its size on the page and the
        # alternative text the author typed. They describe the picture only
        # when the picture is all the drawing holds, not one shape of a group.
        frame = None
        for node in element.iter():
            if node.tag in (WP + "inline", WP + "anchor"):
                frame = node
                break

        parts = []
        for kind, node, owner, scale, grouped in found:
            if kind == "box":
                entries = self.render_box(node)
                if len(entries) > 0:
                    parts.append(("box", entries))
                continue
            if kind == "blip":
                rel_id = node.get(R + "embed") or node.get(R + "link")
                alt, width, height = self.picture_description(owner, scale)
                if frame is not None and not grouped:
                    alt, width, height = self.frame_description(frame, alt, width, height)
            else:
                rel_id = node.get(R + "id")
                alt, width, height = "", None, None
                if owner is not None:
                    alt = owner.get("alt") or ""
                    width = _style_length(owner.get("style"), "width")
                    height = _style_length(owner.get("style"), "height")
            image = self.image_html(rel_id, alt.strip(), width, height)
            if image != "":
                parts.append(("image", image))
        return parts

    def group_scale(self, group):
        """
        How much a group of shapes was stretched after it was made. The
        shapes inside keep the measures they had; the group says how wide it
        is now (a:ext) and how wide it was then (a:chExt).
        """
        for child in group:
            if _local(child.tag) != "grpSpPr":
                continue
            transform = child.find(A + "xfrm")
            if transform is None:
                return 1.0
            now = transform.find(A + "ext")
            then = transform.find(A + "chExt")
            if now is None or then is None:
                return 1.0
            width_now = _to_emu(now.get("cx"))
            width_then = _to_emu(then.get("cx"))
            if not width_now or not width_then or width_now < 0 or width_then < 0:
                return 1.0
            return width_now / width_then
        return 1.0

    def picture_description(self, picture, scale):
        """
        The alternative text and the size (in EMU) a pic:pic says of itself.
        Inside a group this is all there is to know about the picture.
        """
        alt = ""
        width = None
        height = None
        if picture is None:
            return alt, width, height
        properties = picture.find(PIC + "nvPicPr/" + PIC + "cNvPr")
        if properties is not None:
            alt = properties.get("descr") or properties.get("title") or ""
        size = picture.find(PIC + "spPr/" + A + "xfrm/" + A + "ext")
        if size is not None:
            own_width = _to_emu(size.get("cx"))
            own_height = _to_emu(size.get("cy"))
            if own_width:
                width = round(own_width * scale)
            if own_height:
                height = round(own_height * scale)
        return alt, width, height

    def frame_description(self, frame, alt, width, height):
        """
        The alternative text and the size of a picture that stands alone in
        its drawing. Word keeps the text the author typed in wp:docPr, and
        the size the picture has on the page in wp:extent: both win over
        what the picture says of itself.
        """
        properties = frame.find(WP + "docPr")
        if properties is not None:
            alt = properties.get("descr") or properties.get("title") or alt
        extent = frame.find(WP + "extent")
        if extent is not None:
            width = _to_emu(extent.get("cx")) or width
            height = _to_emu(extent.get("cy")) or height
        return alt, width, height

    def float_placement(self, element):
        """
        Where a floating drawing goes, or None for a drawing that sits in
        the line of text: "where" is "before" or "after" the paragraph,
        "offset" is how far its top is from the top of that paragraph (in
        EMU), "align" its alignment class.

        Word anchors a floating picture to a paragraph and says how far down
        from the top of that paragraph it starts. Anchored at the top, the
        text of the paragraph runs beside it or under it: the picture comes
        first. Anchored lower, some of that text is above it: the picture
        comes after. It is an approximation - a web page has no picture with
        text flowing around it at a given height - but it keeps the picture
        next to the text it was next to, and out of the middle of a sentence.
        """
        for node in element.iter():
            if node.tag == WP + "inline":
                return None
            if node.tag == WP + "anchor":
                return self.anchor_placement(node)
            if isinstance(node.tag, str) and node.tag.startswith(V) and node.get("style"):
                return self.vml_placement(node.get("style"))
        return None

    def anchor_placement(self, anchor):
        """The placement of a DrawingML wp:anchor. See float_placement."""
        offset = 0
        below = False
        vertical = anchor.find(WP + "positionV")
        # A position measured from the page or from the margin says nothing
        # about the paragraph: the picture is taken as anchored at its top.
        if vertical is not None and vertical.get("relativeFrom") in ("paragraph", "line"):
            offset = _to_emu(vertical.findtext(WP + "posOffset")) or 0
            below = (vertical.findtext(WP + "align") or "").strip() == "bottom"
        side = ""
        horizontal = anchor.find(WP + "positionH")
        if horizontal is not None:
            side = (horizontal.findtext(WP + "align") or "").strip()
        return self.placement(offset, below, side)

    def vml_placement(self, style):
        """The placement of an old VML shape, read from its CSS-like style."""
        if re.search(r"(?:^|;)\s*position\s*:\s*absolute", style) is None:
            return None
        offset = 0
        below = False
        relative = re.search(r"mso-position-vertical-relative\s*:\s*([a-z-]+)", style)
        if relative is None or relative.group(1) in ("text", "line", "paragraph"):
            offset = _style_length(style, "margin-top") or 0
            vertical = re.search(r"mso-position-vertical\s*:\s*([a-z]+)", style)
            below = vertical is not None and vertical.group(1) == "bottom"
        side = ""
        horizontal = re.search(r"mso-position-horizontal\s*:\s*([a-z]+)", style)
        if horizontal is not None:
            side = horizontal.group(1)
        return self.placement(offset, below, side)

    def placement(self, offset, below, side):
        """Before or after the paragraph, and the class of the alignment."""
        where = "before"
        if below or offset > FLOAT_BELOW_OFFSET:
            where = "after"
        alignment = ""
        if side == "center":
            alignment = " class=\"ql-align-center\""
        elif side == "right":
            alignment = " class=\"ql-align-right\""
        return {"where": where, "offset": offset, "align": alignment}

    def render_box(self, box):
        """The blocks inside a text box, rendered without disturbing the paragraph around it."""
        saved = (self.paragraph_pieces, self.floats, self.fields)
        self.paragraph_pieces = []
        self.floats = []
        self.fields = []
        try:
            entries = self.render_blocks(box)
        finally:
            self.paragraph_pieces, self.floats, self.fields = saved
        return entries

    def image_html(self, rel_id, alt, width, height):
        """
        The <img> of one picture, saved in the media folder on the way, or
        an empty string (plus a warning) when the picture cannot be used, so
        one bad picture never stops the import. width and height are the
        size the picture has on the page of the document, in EMU, when the
        document says it.

        Anything bigger than an icon is wrapped in the marks that can give
        it a paragraph of its own, away from the text of its line.
        """
        if rel_id is None:
            return ""
        if rel_id not in self.saved_images:
            self.saved_images[rel_id] = self.save_image(rel_id)
        url = self.saved_images[rel_id]
        if url == "":
            return ""
        tag = '<img src="' + html.escape(url) + '"'
        if alt != "":
            tag = tag + ' alt="' + html.escape(alt) + '"'
        tag = tag + self.width_attribute(width) + ' loading="lazy">'
        size = height
        if size is None:
            size = width
        if size is not None and 0 < size <= INLINE_PICTURE_MAX:
            return tag
        return PICTURE_OPEN + tag + PICTURE_CLOSE

    def width_attribute(self, width):
        """
        The width attribute of a picture, from the width it has in Word.

        The size on the page is kept in pixels, so a small picture stays
        small on a wide screen and a big one still shrinks on a phone (the
        stylesheet never lets a picture be wider than its column). A picture
        that went from margin to margin in the document goes from margin to
        margin in the article: its width is 100%, whatever the two columns
        measure.
        """
        if width is None or width <= 0:
            return ""
        pixels = round(width / EMU_PER_PIXEL)
        if pixels < 1:
            return ""
        full = pixels >= MAX_IMAGE_WIDTH
        if self.text_width is not None and width >= FULL_WIDTH_SHARE * self.text_width:
            full = True
        if full:
            return ' width="100%"'
        return ' width="' + str(pixels) + '"'

    def page_text_width(self, body):
        """
        The width of the text on the page, in EMU: the page less its two
        margins, divided by the number of columns. None when the document
        does not say, and then pictures are only measured in pixels.
        """
        section = body.find(W + "sectPr")
        if section is None:
            return None
        size = section.find(W + "pgSz")
        if size is None:
            return None
        margins = section.find(W + "pgMar")
        try:
            width = int(size.get(W + "w", ""))
            if margins is not None:
                width = width - int(margins.get(W + "left", "0")) \
                    - int(margins.get(W + "right", "0"))
            columns = 1
            layout = section.find(W + "cols")
            if layout is not None:
                columns = max(1, int(layout.get(W + "num", "1")))
        except ValueError:
            return None
        if width <= 0:
            return None
        return width * EMU_PER_TWIP / columns

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
        Render one w:p into a list of entries for the assembler.

        One paragraph of Word can be several blocks of the article: a line
        break starts a new one, a picture with text around it gets one to
        itself, and the floating pictures and text boxes anchored to the
        paragraph go before or after it.

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
        # A heading numbered by its style is still a heading, not a list item.
        list_info = None
        if not heading_like:
            list_info = self.paragraph_list_info(paragraph, style_id)

        fields_open_before = len(self.fields) > 0
        saved_pieces = self.paragraph_pieces
        saved_floats = self.floats
        self.paragraph_pieces = []
        self.floats = []
        render_context = dict(context, in_heading=heading_like, code_block=code_like,
                              in_list_item=list_info is not None)
        self.render_inline(paragraph, inherited, render_context)
        inner = "".join(self.paragraph_pieces).strip()
        floats = self.floats
        self.paragraph_pieces = saved_pieces
        self.floats = saved_floats
        fields_open_after = len(self.fields) > 0
        if fields_open_after:
            self.end_line_in_field()

        if kind is not None and kind[0] == "toc":
            self.warn("warn_docx_toc_skipped")
            entries = [{"kind": "skip"}]
        elif (fields_open_before or fields_open_after) and inner == "":
            # A paragraph whose whole text went into a field that spans
            # several paragraphs: Word's table of contents. Nothing to show.
            entries = [{"kind": "skip"}]
        else:
            entries = self.classify(paragraph, kind, inner, code_like, inherited,
                                    list_info, context)
        return self.with_floats(entries, floats)

    def end_line_in_field(self):
        """
        A paragraph has ended inside a field that is still open: a
        bibliography, a list of figures. The field collects the text of all
        its paragraphs and hands it over where it closes; the mark keeps
        each paragraph on a line of its own there, instead of one long line.
        """
        field = self.fields[-1]
        if field["phase"] == "result" and len(field["parts"]) > 0 \
                and field["parts"][-1] != LINE_BREAK:
            field["parts"].append(LINE_BREAK)

    def with_floats(self, entries, floats):
        """
        Put the floating pictures and text boxes of a paragraph before it or
        after it, from the highest to the lowest.

        They all go on the side of the highest one. The floats of one
        paragraph belong together - a picture and the caption Word puts in a
        text box under it, two pictures side by side - and the caption sits
        lower than the picture by definition: placed each by its own height,
        the picture would end up before the paragraph and its caption after
        it. A paragraph that held nothing else leaves no empty line behind.
        """
        if len(floats) == 0:
            return entries
        ordered = sorted(floats, key=lambda item: item["offset"])
        blocks = []
        for item in ordered:
            blocks.extend(item["entries"])
        if all(entry["kind"] in ("empty", "skip") for entry in entries):
            return blocks
        if ordered[0]["where"] == "before":
            return blocks + entries
        return entries + blocks

    def classify(self, paragraph, kind, inner, code_like, inherited, list_info, context):
        """
        Turn a rendered paragraph into the entries the assembler needs.

        This is where the marks left in the text are resolved, and each kind
        of block does it its own way. A paragraph and a quotation are cut:
        Quill has no line break inside a block, so every line becomes a block
        like the one it came from. A title, a heading and a list item cannot
        be cut without becoming two headings or two items: the line break
        turns into a space. A table cell is outside Quill's reach, and keeps
        a real <br>.
        """
        alignment = self.paragraph_alignment_class(paragraph)
        name = ""
        if kind is not None:
            name = kind[0]

        if context.get("in_cell"):
            return [self.cell_entry(paragraph, _cell_html(inner), code_like,
                                    inherited, list_info)]

        lines = _cut_lines(inner)
        if name in ("title", "subtitle", "heading"):
            return self.heading_entries(kind, lines, alignment)

        if list_info is not None:
            texts = []
            for line in lines:
                text = "".join(value for _, value in line).strip()
                if not _is_blank(text):
                    texts.append(text)
            if len(texts) == 0:
                return [{"kind": "skip"}]
            return [{"kind": "item", "level": list_info[0], "list": list_info[1],
                     "html": " ".join(texts)}]

        if code_like:
            return [{"kind": "code", "text": self.paragraph_code_text(paragraph, inherited)}]

        entries = []
        for line in lines:
            blocks = _line_blocks(line)
            if len(blocks) == 0:
                # Two line breaks in a row: the empty line between them.
                entries.append({"kind": "empty"})
            for block_kind, value in blocks:
                if block_kind == "text" and name == "quote":
                    entries.append({"kind": "quote", "html": value})
                else:
                    entries.append({"kind": "para", "html": value, "align": alignment})
        # A line break at the very start or end of a paragraph shows nothing.
        while len(entries) > 0 and entries[0]["kind"] == "empty":
            entries.pop(0)
        while len(entries) > 0 and entries[-1]["kind"] == "empty":
            entries.pop()
        if len(entries) == 0:
            return [{"kind": "empty"}]
        return entries

    def heading_entries(self, kind, lines, alignment):
        """
        A title, a subtitle or a heading is one line, whatever Word did
        inside it: a line break becomes a space. A picture is not part of a
        heading: it goes before or after it, on the side it was.
        """
        texts = []
        before = []
        after = []
        for line in lines:
            for block_kind, value in _line_blocks(line):
                if block_kind == "text":
                    texts.append(value)
                    continue
                picture = {"kind": "para", "html": value, "align": alignment}
                if len(texts) == 0:
                    before.append(picture)
                else:
                    after.append(picture)
        text = " ".join(texts)
        if text == "":
            if len(before) == 0:
                return [{"kind": "empty"}]
            return before
        if kind[0] == "title":
            entry = {"kind": "title", "text": _plain(text), "html": text}
        elif kind[0] == "subtitle":
            entry = {"kind": "subtitle", "text": _plain(text), "html": text,
                     "align": alignment}
        else:
            entry = {"kind": "heading", "level": kind[1], "html": text, "align": alignment}
        return before + [entry] + after

    def cell_entry(self, paragraph, inner, code_like, inherited, list_info):
        """One paragraph of a table cell: a cell holds lines, not blocks."""
        if list_info is not None:
            if _is_blank(inner):
                return {"kind": "skip"}
            return {"kind": "item", "level": list_info[0], "list": list_info[1], "html": inner}
        if code_like:
            return {"kind": "code", "text": self.paragraph_code_text(paragraph, inherited)}
        if _is_blank(inner):
            return {"kind": "empty"}
        return {"kind": "para", "html": inner, "align": ""}

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
        context = {"in_header_cell": header, "in_cell": True}

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
                entries.extend(self.table_entries(element))
            # sectPr (page setup), bookmarks and the rest carry no content.
        return entries

    def table_entries(self, table):
        """
        The entries a w:tbl becomes: one table, or - for a table that is
        only there to lay out the page - the blocks inside its cells, read
        row by row.
        """
        if self.is_layout_table(table):
            entries = []
            for row in self.own_rows(table):
                for cell in self.own_cells(row):
                    entries.extend(self.render_blocks(cell))
            if len(entries) > 0:
                self.warn("warn_docx_layout_table")
            return entries
        table_html = self.render_table(table)
        if table_html == "":
            return []
        return [{"kind": "table", "html": table_html}]

    def is_layout_table(self, table):
        """
        Tell whether a table is Word's page furniture rather than data.

        Word has no other way to put a picture beside a text or to keep a
        caption with its picture, so authors use a table for it, usually
        with its borders hidden. The editor's tables always have a header
        row: rendered as one, such a table shows its picture and its text in
        bold on a grey band, in a smaller size. A single row is a strip of
        blocks side by side and a single column is a stack of them, never a
        grid of data: those are taken apart, and their content becomes the
        ordinary text and pictures it is. The same rule decides what a
        table pasted from Word becomes in the editor (isLayoutTable, in
        admin.js); a grid with more rows and columns is always kept.
        """
        rows = self.own_rows(table)
        if len(rows) <= 1:
            return True
        for row in rows:
            if len(self.own_cells(row)) > 1:
                return False
        return True

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
                saved = (self.paragraph_pieces, self.fields, self.floats)
                self.paragraph_pieces = []
                self.fields = []
                self.floats = []
                style_id = self.paragraph_style_id(paragraph)
                self.render_inline(paragraph, self.style_format(style_id), {})
                # A note is one item of a list: a line break is a space.
                text = _without_marks("".join(self.paragraph_pieces), " ").strip()
                self.paragraph_pieces, self.fields, self.floats = saved
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
                if entry["kind"] == "para" and _plain(entry["html"]) == "":
                    # A picture above the title - a logo, a cover - does not
                    # make the heading under it any less the title.
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
        self.text_width = self.page_text_width(body)
        entries = self.render_blocks(body)
        entries.extend(self.unclosed_fields())
        return self.assemble(entries)

    def unclosed_fields(self):
        """
        The text held by the fields that were opened and never closed.

        A field collects everything after its start mark until its end mark
        says what to do with it. A document with no end mark - damaged, or
        written by a converter - used to lose all the text from that point
        to the last page, without a word. That text is the rest of the
        document: it is given back as ordinary paragraphs, with a warning.
        A table of contents left open stays out, as a closed one does.
        """
        recovered = []
        for field in self.fields:
            words = field["instr"].strip().split()
            if len(words) > 0 and words[0].upper() == "TOC":
                continue
            for line in _cut_lines("".join(field["parts"])):
                for _, value in _line_blocks(line):
                    recovered.append({"kind": "para", "html": value, "align": ""})
        self.fields = []
        if len(recovered) > 0:
            self.warn("warn_docx_field_unclosed")
        return recovered


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
    if key == "warn_docx_field_unclosed":
        return "a field was never closed: the text after it was kept as ordinary paragraphs"
    if key == "warn_docx_layout_table":
        return "a table used for layout was taken apart: its content is now ordinary text"
    if key == "warn_docx_numbering_missing":
        return "list numbering could not be read: bulleted lists were used"
    if key == "warn_docx_toc_skipped":
        return "Word's table of contents was left out: the site builds its own"
    if key == "warn_docx_equation":
        return "an equation could not be imported"
    if key == "warn_docx_title_from_filename":
        return "the document has no title of its own: the file name was used"
    return key
