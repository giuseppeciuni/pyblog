"""
Import a Word document (.docx) and turn it into HTML the Quill editor can edit.

A .docx is a ZIP archive of XML parts, so no library is needed: zipfile opens
the archive, xml.etree parses the parts. The pieces that matter are

    word/document.xml            the text itself
    word/_rels/document.xml.rels the targets of images and hyperlinks
    word/styles.xml              the styles a run or paragraph inherits from
    word/numbering.xml           whether a list is bulleted or numbered
    word/media/                  the embedded image files

The conversion is deliberately lossy: it keeps what a blog article needs
(headings, emphasis, alignment, lists, tables, images, links) and drops the
rest of Word's machinery. Anything it does not recognise degrades to plain
text rather than raising, because a real document from LibreOffice, Google
Docs or Word 2007 will always contain something unexpected.

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

from core.articles import save_article, save_uploaded_file, validate_upload

# OOXML namespaces. ElementTree spells a namespaced tag "{uri}local", so we
# keep the braces in the constants and write W + "p" for a paragraph.
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"

# Paragraph styles that mean "heading", in the languages Word ships. The key
# is the style id or style name lowercased with spaces removed; the value is
# the heading level.
HEADING_STYLE_NAMES = {}
for _level in (1, 2, 3, 4):
    for _prefix in ("heading", "titolo", "titre", "berschrift", "ttulo", "kop"):
        HEADING_STYLE_NAMES[_prefix + str(_level)] = _level

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


def _local(tag):
    """The local name of a namespaced tag ("{uri}p" -> "p")."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


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


# ---------------------------------------------------------------------------
# RELATIONSHIPS, STYLES, NUMBERING
# ---------------------------------------------------------------------------

def _read_part(archive, name):
    """Read one part of the archive, or None when it is not there."""
    try:
        return archive.read(name)
    except KeyError:
        return None


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


def parse_styles(archive):
    """
    Read word/styles.xml into {style id: properties}.

    Properties we care about: what the style is based on, its name, and the
    character formatting it carries. Word puts bold on the "Strong" style
    rather than on the run, so a document can be full of bold text without a
    single <w:b/> in document.xml; without this map that bold would be lost.
    """
    root = _parse_xml(_read_part(archive, "word/styles.xml"))
    styles = {}
    if root is None:
        return styles

    for style in root.findall(W + "style"):
        style_id = style.get(W + "styleId")
        if style_id is None:
            continue
        entry = {"based_on": None, "name": "", "bold": None, "italic": None,
                 "underline": None, "strike": None}

        name_element = style.find(W + "name")
        if name_element is not None:
            entry["name"] = name_element.get(W + "val", "")

        based_on = style.find(W + "basedOn")
        if based_on is not None:
            entry["based_on"] = based_on.get(W + "val")

        run_properties = style.find(W + "rPr")
        if run_properties is not None:
            entry.update(_read_run_properties(run_properties))

        styles[style_id] = entry
    return styles


def _read_run_properties(run_properties):
    """Read the four character properties we support out of a w:rPr element."""
    result = {}
    result["bold"] = _on_off(run_properties.find(W + "b"))
    result["italic"] = _on_off(run_properties.find(W + "i"))
    result["strike"] = _on_off(run_properties.find(W + "strike"))

    underline = run_properties.find(W + "u")
    if underline is None:
        result["underline"] = None
    else:
        value = underline.get(W + "val", "single")
        # "none" is how Word switches an inherited underline back off.
        if value == "none":
            result["underline"] = False
        else:
            result["underline"] = True
    return result


def resolve_style_format(style_id, styles):
    """
    Walk the w:basedOn chain and return the formatting a style really carries.

    A style inherits from its parent, so "Strong based on Normal" must pick up
    whatever Normal set. We collect the chain from the root down, so the more
    specific style wins.
    """
    chain = []
    current = style_id
    depth = 0
    while current is not None and current in styles and depth < MAX_STYLE_DEPTH:
        chain.append(styles[current])
        current = styles[current]["based_on"]
        depth = depth + 1

    resolved = {"bold": None, "italic": None, "underline": None, "strike": None}
    for entry in reversed(chain):
        for key in resolved:
            if entry.get(key) is not None:
                resolved[key] = entry[key]
    return resolved


def heading_level_for_style(style_id, styles):
    """
    Return 1..4 when a paragraph style means "heading", otherwise None.

    We look at the style id and at its human name, in both English and the
    localised forms Word writes ("Titolo1" in Italian), and we follow the
    basedOn chain so a style derived from Heading2 is still a heading.
    """
    current = style_id
    depth = 0
    while current is not None and depth < MAX_STYLE_DEPTH:
        candidates = [current]
        entry = styles.get(current)
        if entry is not None and entry["name"] != "":
            candidates.append(entry["name"])
        for candidate in candidates:
            key = re.sub(r"[^a-z0-9]", "", candidate.lower())
            if key in HEADING_STYLE_NAMES:
                return HEADING_STYLE_NAMES[key]
        if entry is None:
            return None
        current = entry["based_on"]
        depth = depth + 1
    return None


def parse_numbering(archive):
    """
    Read word/numbering.xml into {numId: {level: "bullet" | "decimal"}}.

    A list paragraph only carries a numbering id and a level; the shape of the
    list lives here. When the part is missing or unreadable we return an empty
    map and the caller falls back to bulleted lists, which is the safe guess:
    a bullet where a number belonged is a small cosmetic loss, while numbers
    invented where there were none would be wrong.
    """
    root = _parse_xml(_read_part(archive, "word/numbering.xml"))
    if root is None:
        return {}

    # abstractNumId -> {level: format}
    abstract = {}
    for abstract_num in root.findall(W + "abstractNum"):
        abstract_id = abstract_num.get(W + "abstractNumId")
        if abstract_id is None:
            continue
        levels = {}
        for level in abstract_num.findall(W + "lvl"):
            level_index = level.get(W + "ilvl", "0")
            number_format = level.find(W + "numFmt")
            if number_format is None:
                continue
            value = number_format.get(W + "val", "bullet")
            if value == "bullet":
                levels[level_index] = "bullet"
            else:
                levels[level_index] = "decimal"
        abstract[abstract_id] = levels

    # numId -> abstractNumId
    numbering = {}
    for num in root.findall(W + "num"):
        num_id = num.get(W + "numId")
        if num_id is None:
            continue
        abstract_ref = num.find(W + "abstractNumId")
        if abstract_ref is None:
            continue
        abstract_id = abstract_ref.get(W + "val")
        numbering[num_id] = abstract.get(abstract_id, {})
    return numbering


# ---------------------------------------------------------------------------
# THE CONVERTER
# ---------------------------------------------------------------------------

class DocxConverter:
    """
    Holds the state of one conversion: the archive, the resolved maps, the
    warnings collected along the way and the cache of already-saved images.
    """

    def __init__(self, archive):
        self.archive = archive
        self.relationships = parse_relationships(archive)
        self.styles = parse_styles(archive)
        self.numbering = parse_numbering(archive)
        self.warnings = []
        # relationship id -> saved URL, so an image used twice is stored once.
        self.saved_images = {}
        self.title = ""
        self.title_taken = False

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

    # --- Runs -------------------------------------------------------------

    def paragraph_run_format(self, paragraph):
        """The character formatting a paragraph's own style contributes."""
        style_id = None
        properties = paragraph.find(W + "pPr")
        if properties is not None:
            style = properties.find(W + "pStyle")
            if style is not None:
                style_id = style.get(W + "val")
        if style_id is None:
            return {"bold": None, "italic": None, "underline": None, "strike": None}
        return resolve_style_format(style_id, self.styles)

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
            style_id = style.get(W + "val")
            character_format = resolve_style_format(style_id, self.styles)
            for key in result:
                if character_format.get(key) is not None:
                    result[key] = character_format[key]

        direct = _read_run_properties(properties)
        for key in result:
            if direct.get(key) is not None:
                result[key] = direct[key]
        return result

    def render_run(self, run, inherited):
        """Render one w:r into HTML, tags included."""
        pieces = []
        for child in run:
            name = _local(child.tag)
            if name == "t":
                text = child.text
                if text is None:
                    text = ""
                pieces.append(html.escape(text, quote=False))
            elif name == "br":
                pieces.append("<br>")
            elif name == "tab":
                pieces.append(" ")
            elif name in ("drawing", "pict", "object"):
                pieces.append(self.render_image(child))
            elif name == "noBreakHyphen":
                pieces.append("-")
            elif name == "softHyphen":
                pieces.append("")
            # w:delText belongs to deleted revisions and is never rendered;
            # anything else (comments, footnote marks, fields) is skipped.

        text = "".join(pieces)
        if text == "":
            return ""

        # Formatting is only applied to a run that actually shows text: an
        # image must not end up wrapped in <strong>.
        visible = re.sub(r"<[^>]+>", "", text).strip()
        if visible == "":
            return text

        fmt = self.run_format(run, inherited)
        if fmt.get("bold"):
            text = "<strong>" + text + "</strong>"
        if fmt.get("italic"):
            text = "<em>" + text + "</em>"
        if fmt.get("underline"):
            text = "<u>" + text + "</u>"
        if fmt.get("strike"):
            text = "<s>" + text + "</s>"
        return text

    # --- Images -----------------------------------------------------------

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

    def render_image(self, element):
        """
        Extract an embedded image, save it in the media folder and return the
        <img> tag. Returns an empty string (plus a warning) when the image
        cannot be used, so one bad picture never stops the import.
        """
        rel_id = self.find_image_relationship_id(element)
        if rel_id is None:
            return ""
        if rel_id in self.saved_images:
            url = self.saved_images[rel_id]
            if url == "":
                return ""
            return '<img src="' + html.escape(url) + '" loading="lazy">'

        relationship = self.relationships.get(rel_id)
        if relationship is None or relationship["external"]:
            # A linked (not embedded) image lives on the author's disk; the
            # bytes are simply not in the file.
            self.saved_images[rel_id] = ""
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
            data = _read_part(self.archive, candidate)
            if data is not None:
                break
        if data is None:
            self.saved_images[rel_id] = ""
            self.warn("warn_docx_image_missing", name=source_name)
            return ""

        # The same checks a manual upload goes through: extension whitelist,
        # magic bytes, SVG sanitising. Word happily embeds WMF and EMF, which
        # no browser can display, and those are refused here.
        check = validate_upload(source_name, data)
        if not check["ok"]:
            self.saved_images[rel_id] = ""
            self.warn("warn_docx_image_skipped", name=source_name)
            return ""

        url = save_uploaded_file(source_name, check["data"])
        self.saved_images[rel_id] = url
        return '<img src="' + html.escape(url) + '" loading="lazy">'

    # --- Hyperlinks -------------------------------------------------------

    def render_hyperlink(self, element, inherited):
        """
        Render a w:hyperlink. The address comes from the relationships, and
        only http, https and mailto survive: a Word document can carry a
        javascript: or file: target, and neither belongs in a published page.
        An internal bookmark link keeps its text and loses the link.
        """
        inner = []
        for child in element:
            if _local(child.tag) == "r":
                inner.append(self.render_run(child, inherited))
            else:
                inner.append(self.render_block_inline(child, inherited))
        text = "".join(inner)
        if text == "":
            return ""

        rel_id = element.get(R + "id")
        if rel_id is None:
            # An anchor-only link points inside the document; we keep the text.
            return text
        relationship = self.relationships.get(rel_id)
        if relationship is None:
            return text

        target = relationship["target"].strip()
        lowered = target.lower()
        allowed = False
        for scheme in ALLOWED_LINK_SCHEMES:
            if lowered.startswith(scheme):
                allowed = True
                break
        if not allowed:
            self.warn("warn_docx_link_skipped", href=target[:80])
            return text
        return '<a href="' + html.escape(target) + '">' + text + "</a>"

    def render_block_inline(self, element, inherited):
        """
        Render the inline children of a paragraph-level element we do not
        handle specially. Tracked insertions (w:ins) are accepted text; tracked
        deletions (w:del) are not, and never reach this function.
        """
        pieces = []
        for child in element:
            name = _local(child.tag)
            if name == "r":
                pieces.append(self.render_run(child, inherited))
            elif name == "hyperlink":
                pieces.append(self.render_hyperlink(child, inherited))
            elif name == "del":
                continue
            elif name in ("ins", "smartTag", "sdt", "sdtContent", "bookmarkStart",
                          "bookmarkEnd", "proofErr", "commentRangeStart",
                          "commentRangeEnd"):
                pieces.append(self.render_block_inline(child, inherited))
        return "".join(pieces)

    # --- Paragraphs -------------------------------------------------------

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

    def paragraph_list_info(self, paragraph):
        """
        Return (level, "ul" | "ol") for a list paragraph, or None.

        The paragraph names a numbering id and an indent level; numbering.xml
        says whether that level is bulleted or numbered. With no numbering
        part we fall back to a bulleted list.
        """
        properties = paragraph.find(W + "pPr")
        if properties is None:
            return None
        number_properties = properties.find(W + "numPr")
        if number_properties is None:
            return None

        level_element = number_properties.find(W + "ilvl")
        level = "0"
        if level_element is not None:
            level = level_element.get(W + "val", "0")
        try:
            level_number = int(level)
        except ValueError:
            level_number = 0
        if level_number < 0:
            level_number = 0

        id_element = number_properties.find(W + "numId")
        if id_element is None:
            return level_number, "ul"
        num_id = id_element.get(W + "val")
        # numId 0 means "this paragraph is explicitly not in a list".
        if num_id in (None, "0"):
            return None

        levels = self.numbering.get(num_id)
        if levels is None:
            if len(self.numbering) == 0:
                self.warn("warn_docx_numbering_missing")
            return level_number, "ul"
        shape = levels.get(level, levels.get("0", "bullet"))
        if shape == "decimal":
            return level_number, "ol"
        return level_number, "ul"

    def render_paragraph(self, paragraph):
        """
        Render one w:p into a block of HTML, or into a list item description
        the caller will assemble.

        Returns a dict: {"kind": "block", "html": ...} for an ordinary
        paragraph or heading, or {"kind": "item", "level":, "list":, "html":}
        for a paragraph that belongs to a list.
        """
        inherited = self.paragraph_run_format(paragraph)
        inner = self.render_block_inline(paragraph, inherited)

        list_info = self.paragraph_list_info(paragraph)
        if list_info is not None:
            level, list_tag = list_info
            if inner.strip() == "":
                return None
            return {"kind": "item", "level": level, "list": list_tag, "html": inner}

        style_id = None
        properties = paragraph.find(W + "pPr")
        if properties is not None:
            style = properties.find(W + "pStyle")
            if style is not None:
                style_id = style.get(W + "val")
        level = heading_level_for_style(style_id, self.styles)

        alignment = self.paragraph_alignment_class(paragraph)

        if level is not None:
            if inner.strip() == "":
                return None
            # The first Heading 1 becomes the article title, so it must not
            # appear again as an <h1> inside the body.
            if level == 1 and not self.title_taken:
                self.title = re.sub(r"<[^>]+>", "", inner).strip()
                self.title = html.unescape(self.title)
                self.title_taken = True
                return None
            return {"kind": "block",
                    "html": f"<h{level}{alignment}>{inner}</h{level}>"}

        if inner.strip() == "":
            # Word marks an empty line with an empty paragraph, and so does
            # Quill: we keep it, with the same markup the editor writes.
            return {"kind": "block", "html": "<p><br></p>"}
        return {"kind": "block", "html": f"<p{alignment}>{inner}</p>"}

    # --- Tables -----------------------------------------------------------

    def render_table(self, table, depth=0):
        """
        Render a w:tbl as the same <table class="article-table"> the editor
        produces, with the first row as the header.

        A table nested inside a cell is flattened to its text: Word uses
        nested tables for page layout, and a grid inside a grid is almost
        never what the author meant to publish.
        """
        if depth > MAX_TABLE_DEPTH:
            self.warn("warn_docx_nested_table")
            return self.flatten_table_text(table)

        rows_html = []
        row_index = 0
        for row in table.findall(W + "tr"):
            cells_html = []
            for cell in row.findall(W + "tc"):
                content = self.render_cell(cell, depth)
                if row_index == 0:
                    cells_html.append("<th>" + content + "</th>")
                else:
                    cells_html.append("<td>" + content + "</td>")
            if len(cells_html) == 0:
                continue
            rows_html.append("<tr>" + "".join(cells_html) + "</tr>")
            row_index = row_index + 1

        if len(rows_html) == 0:
            return ""
        return ('<table class="article-table"><tbody>'
                + "".join(rows_html) + "</tbody></table>")

    def render_cell(self, cell, depth):
        """Render the blocks inside one table cell, as inline-ish HTML."""
        pieces = []
        for child in cell:
            name = _local(child.tag)
            if name == "p":
                rendered = self.render_paragraph(child)
                if rendered is None:
                    continue
                if rendered["kind"] == "item":
                    pieces.append(rendered["html"])
                else:
                    # Inside a cell we do not want block markup: the editor's
                    # tables hold plain content.
                    text = re.sub(r"</?(p|h[1-6])[^>]*>", "", rendered["html"])
                    if text.strip() != "":
                        pieces.append(text)
            elif name == "tbl":
                nested = self.render_table(child, depth + 1)
                if nested != "":
                    pieces.append(nested)
        return " ".join(piece for piece in pieces if piece.strip() != "")

    def flatten_table_text(self, table):
        """The text of a table, with no markup: used for nested tables."""
        pieces = []
        for text_element in table.iter(W + "t"):
            if text_element.text:
                pieces.append(html.escape(text_element.text, quote=False))
        return " ".join(pieces).strip()

    # --- The document body -------------------------------------------------

    def render_body(self, body):
        """
        Walk the top-level blocks of the document and assemble the HTML.

        List paragraphs arrive one at a time and have to be gathered back into
        <ul>/<ol> elements, which is what the buffer below is for.
        """
        blocks = []
        pending_items = []

        def flush_list():
            if len(pending_items) > 0:
                blocks.append(render_list(pending_items))
                pending_items.clear()

        for element in self._body_children(body):
            name = _local(element.tag)
            if name == "p":
                rendered = self.render_paragraph(element)
                if rendered is None:
                    continue
                if rendered["kind"] == "item":
                    pending_items.append(rendered)
                else:
                    flush_list()
                    blocks.append(rendered["html"])
            elif name == "tbl":
                flush_list()
                table_html = self.render_table(element)
                if table_html != "":
                    blocks.append(table_html)
            # sectPr (page setup), bookmarks and the rest carry no content.

        flush_list()
        return "\n".join(blocks)

    def _body_children(self, body):
        """
        Yield the block-level children of the body, stepping through the
        wrappers Word puts around content: content controls (w:sdt) and
        tracked insertions both hold real paragraphs inside them.
        """
        for element in body:
            name = _local(element.tag)
            if name in ("sdt", "ins"):
                content = element.find(W + "sdtContent")
                if content is None:
                    content = element
                for inner in self._body_children(content):
                    yield inner
            elif name == "del":
                continue
            else:
                yield element


def render_list(items):
    """
    Turn a flat run of list paragraphs into nested <ul>/<ol> markup.

    Word gives every item an indent level; a deeper item belongs inside the
    previous one. We walk the items once, opening a nested list when the level
    goes up and closing lists when it comes back down.
    """
    if len(items) == 0:
        return ""

    def build(index, level):
        """Render the items at this level, returning (html, next index)."""
        tag = items[index]["list"]
        pieces = ["<" + tag + ">"]
        while index < len(items):
            item = items[index]
            if item["level"] < level:
                break
            if item["level"] > level:
                # A deeper item belongs inside the item we just wrote.
                nested, index = build(index, item["level"])
                if len(pieces) > 1:
                    pieces[-1] = pieces[-1][:-len("</li>")] + nested + "</li>"
                else:
                    pieces.append("<li>" + nested + "</li>")
                continue
            if item["list"] != tag:
                # The list changes shape at the same level: close and restart.
                break
            pieces.append("<li>" + item["html"] + "</li>")
            index = index + 1
        pieces.append("</" + tag + ">")
        return "".join(pieces), index

    output = []
    position = 0
    guard = 0
    while position < len(items) and guard < len(items) + 5:
        chunk, position = build(position, items[position]["level"])
        output.append(chunk)
        guard = guard + 1
    return "".join(output)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINTS
# ---------------------------------------------------------------------------

# The first bytes of every ZIP archive, and therefore of every .docx. A file
# that does not start with these is not worth unpacking.
ZIP_MAGIC = b"PK\x03\x04"


def looks_like_docx(binary_data):
    """Tell whether some bytes could be a .docx, from the ZIP signature."""
    return binary_data[:4] == ZIP_MAGIC


def convert_docx(binary_data, fallback_title="Documento importato"):
    """
    Convert a .docx file into HTML for the editor.

    Return {"ok": True, "title": ..., "content": ..., "warnings": [...]}, or
    {"ok": False, "error_key": ...} when the file cannot be read at all. The
    warnings are i18n keys with parameters, so the caller picks the language.

    This function never raises on a malformed document: everything it cannot
    make sense of is skipped, and the parts it understood are still returned.
    """
    if not looks_like_docx(binary_data):
        return {"ok": False, "error_key": "err_docx_not_a_zip"}

    try:
        archive = zipfile.ZipFile(io.BytesIO(binary_data))
    except (zipfile.BadZipFile, EOFError, ValueError):
        return {"ok": False, "error_key": "err_docx_not_a_zip"}

    try:
        with archive:
            document = _read_part(archive, "word/document.xml")
            if document is None:
                return {"ok": False, "error_key": "err_docx_no_document"}

            root = _parse_xml(document)
            if root is None:
                return {"ok": False, "error_key": "err_docx_parse"}

            body = root.find(W + "body")
            if body is None:
                return {"ok": False, "error_key": "err_docx_no_document"}

            converter = DocxConverter(archive)
            content = converter.render_body(body)
    except zipfile.BadZipFile:
        return {"ok": False, "error_key": "err_docx_not_a_zip"}
    except Exception as error:
        # A last line of defence. A document we cannot convert must produce a
        # clear message in the editor, never a traceback in the server log.
        return {"ok": False, "error_key": "err_docx_parse", "detail": str(error)}

    title = converter.title
    if title == "":
        title = fallback_title

    if re.sub(r"<[^>]+>", "", content).strip() == "" and "<img" not in content:
        return {"ok": False, "error_key": "err_docx_empty"}

    return {"ok": True, "title": title, "content": content,
            "warnings": converter.warnings}


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
        slug = save_article({
            "title": result["title"],
            "content": result["content"],
            # An imported document is never published straight away: the
            # conversion is lossy and deserves a look in the editor first.
            "status": "draft",
        })
        messages.append(f"  imported: {current.name} -> posts/{slug}.json (draft)")
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
    return key
