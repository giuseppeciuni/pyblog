#!/usr/bin/env python3
"""
Build the .docx fixtures used to test core/docx_import.py.

A .docx is a ZIP of XML parts, so we can write one by hand with zipfile: no
Word, no library, and the fixture is readable in the diff. The main document
deliberately contains one of everything the importer claims to support, plus
a few of the things it is supposed to survive.

    python3 test_docx/make_test_docx.py
"""
import pathlib
import struct
import zlib
import zipfile

HERE = pathlib.Path(__file__).resolve().parent

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R_NS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
A_NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
V_NS = 'xmlns:v="urn:schemas-microsoft-com:vml"'

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="wmf" ContentType="image/x-wmf"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

# Heading styles in both the English and the Italian naming Word uses, a
# character style carrying bold, and one carrying italic.
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W_NS}>
  <w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Titolo3"><w:name w:val="Titolo 3"/><w:basedOn w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="MioSottotitolo"><w:name w:val="Mio sottotitolo"/><w:basedOn w:val="Heading2"/></w:style>
  <w:style w:type="paragraph" w:styleId="ParagrafoGrassetto"><w:name w:val="Paragrafo grassetto"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="Strong"><w:name w:val="Strong"/><w:rPr><w:b/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="Emphasis"><w:name w:val="Emphasis"/><w:rPr><w:i/></w:rPr></w:style>
</w:styles>"""

# numId 1 is bulleted, numId 2 is numbered; level 1 of numId 1 is bulleted too.
NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {W_NS}>
  <w:abstractNum w:abstractNumId="10">
    <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
    <w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="20">
    <w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="20"/></w:num>
</w:numbering>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId10" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rId11" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/pagina" TargetMode="External"/>
  <Relationship Id="rId12" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="javascript:alert(1)" TargetMode="External"/>
  <Relationship Id="rId13" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/disegno.wmf"/>
  <Relationship Id="rId14" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/vecchia.png"/>
</Relationships>"""


def paragraph(runs, style=None, alignment=None, num_id=None, level=0):
    """Build a <w:p> with optional style, alignment and list membership."""
    properties = []
    if style is not None:
        properties.append(f'<w:pStyle w:val="{style}"/>')
    if alignment is not None:
        properties.append(f'<w:jc w:val="{alignment}"/>')
    if num_id is not None:
        properties.append(f'<w:numPr><w:ilvl w:val="{level}"/>'
                          f'<w:numId w:val="{num_id}"/></w:numPr>')
    if properties:
        prefix = "<w:pPr>" + "".join(properties) + "</w:pPr>"
    else:
        prefix = ""
    return "<w:p>" + prefix + runs + "</w:p>"


def run(text, bold=None, italic=None, underline=None, strike=None, style=None):
    """Build a <w:r>. A bold value of False writes the explicit w:val="0"."""
    properties = []
    if style is not None:
        properties.append(f'<w:rStyle w:val="{style}"/>')
    for name, value in (("b", bold), ("i", italic), ("strike", strike)):
        if value is True:
            properties.append(f"<w:{name}/>")
        elif value is False:
            properties.append(f'<w:{name} w:val="0"/>')
    if underline is True:
        properties.append('<w:u w:val="single"/>')
    elif underline is False:
        properties.append('<w:u w:val="none"/>')
    if properties:
        prefix = "<w:rPr>" + "".join(properties) + "</w:rPr>"
    else:
        prefix = ""
    return ("<w:r>" + prefix + '<w:t xml:space="preserve">' + text + "</w:t></w:r>")


def drawing(rel_id):
    """A DrawingML image reference, the modern form Word writes."""
    return (f'<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            f'<a:graphic {A_NS}><a:graphicData>'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:blipFill><a:blip r:embed="{rel_id}"/></pic:blipFill></pic:pic>'
            f"</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>")


def picture(rel_id):
    """A VML image reference, the legacy form still found in old documents."""
    return (f'<w:r><w:pict><v:shape {V_NS}><v:imagedata r:id="{rel_id}"/>'
            f"</v:shape></w:pict></w:r>")


def table(rows, nested=False):
    """Build a <w:tbl> from a list of lists of cell texts."""
    out = ["<w:tbl>"]
    for cells in rows:
        out.append("<w:tr>")
        for cell in cells:
            out.append("<w:tc>" + paragraph(run(cell)) + "</w:tc>")
        if nested:
            inner = table([["dentro A", "dentro B"], ["dentro C", "dentro D"]])
            out.append("<w:tc>" + inner + paragraph(run("dopo")) + "</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def realistic_table(rows):
    """
    A table shaped the way Word actually writes one.

    The minimal <w:tbl><w:tr><w:tc> of the fixture above is not what comes
    out of Word: there are table, row and cell property elements, a column
    grid, and - in documents that have been through review or that use
    content controls - the rows sit inside a w:sdt rather than directly under
    the table. A parser that only looks at direct children loses those.
    """
    columns = max(len(cells) for cells in rows)
    out = ["<w:tbl>"]
    out.append('<w:tblPr><w:tblStyle w:val="GridTable"/>'
               '<w:tblW w:w="0" w:type="auto"/>'
               '<w:tblBorders><w:top w:val="single" w:sz="4"/></w:tblBorders>'
               "</w:tblPr>")
    out.append("<w:tblGrid>" + '<w:gridCol w:w="3000"/>' * columns + "</w:tblGrid>")
    for index, cells in enumerate(rows):
        riga = ["<w:tr><w:trPr><w:cantSplit/></w:trPr>"]
        for cell in cells:
            riga.append('<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/>'
                        "<w:vAlign w:val=\"center\"/></w:tcPr>"
                        + paragraph(run(cell), style="Normal") + "</w:tc>")
        riga.append("</w:tr>")
        riga_xml = "".join(riga)
        # The second row is wrapped in a content control, as Word does.
        if index == 1:
            riga_xml = ("<w:sdt><w:sdtPr/><w:sdtContent>" + riga_xml
                        + "</w:sdtContent></w:sdt>")
        out.append(riga_xml)
    out.append("</w:tbl>")
    return "".join(out)


BODY = "".join([
    paragraph(run("Guida completa all'import da Word"), style="Heading1"),
    paragraph(run("Questo paragrafo ha del ") + run("grassetto diretto", bold=True)
              + run(", del ") + run("corsivo", italic=True)
              + run(", del ") + run("sottolineato", underline=True)
              + run(" e del ") + run("barrato", strike=True) + run(".")),
    paragraph(run("Grassetto ereditato dallo stile di carattere", style="Strong")),
    paragraph(run("Corsivo ereditato dallo stile di carattere", style="Emphasis")),
    paragraph(run("Tutto il paragrafo eredita il grassetto dallo stile"),
              style="ParagrafoGrassetto"),
    paragraph(run("Questo pezzo annulla il grassetto dello stile", bold=False),
              style="ParagrafoGrassetto"),
    paragraph(run("Paragrafo centrato"), alignment="center"),
    paragraph(run("Paragrafo giustificato"), alignment="both"),
    paragraph(run("Sezione con stile inglese"), style="Heading2"),
    paragraph(run("Sezione con stile italiano"), style="Titolo3"),
    paragraph(run("Sezione con stile derivato da Heading2"), style="MioSottotitolo"),
    paragraph(run("Primo punto"), num_id=1),
    paragraph(run("Secondo punto"), num_id=1),
    paragraph(run("Punto annidato"), num_id=1, level=1),
    paragraph(run("Terzo punto"), num_id=1),
    paragraph(run("Primo passo"), num_id=2),
    paragraph(run("Secondo passo"), num_id=2),
    paragraph(run("Un ") + '<w:hyperlink r:id="rId11">' + run("collegamento buono")
              + "</w:hyperlink>" + run(" e un ")
              + '<w:hyperlink r:id="rId12">' + run("collegamento pericoloso")
              + "</w:hyperlink>" + run(".")),
    table([["Comando", "Effetto"], ["build", "rigenera"], ["serve", "avvia"]]),
    paragraph(run("Una tabella come la scrive davvero Word"), style="Heading2"),
    realistic_table([["Parametro", "Valore", "Note"],
                     ["porta", "8000", "predefinita"],
                     ["host", "127.0.0.1", "solo locale"]]),
    paragraph(drawing("rId10")),
    paragraph(picture("rId14")),
    paragraph(drawing("rId13")),
    paragraph("<w:ins>" + run("Testo inserito con revisioni attive.") + "</w:ins>"),
    paragraph("<w:del>" + "<w:r><w:delText>Testo cancellato.</w:delText></w:r>" + "</w:del>"),
    paragraph(run("Riga uno") + "<w:r><w:br/></w:r>" + run("riga due")),
    # Text that must be neutralised: in the document it is legal XML, but
    # once converted it must not be able to inject markup into the page.
    paragraph(run("Testo con &lt;script&gt;alert(1)&lt;/script&gt; e &amp; da neutralizzare")),
    paragraph(""),
    # Two rows: a table with a single row is page layout, and is taken apart.
    table([["Esterna A", "Esterna B"], ["Esterna C", "Esterna D"]], nested=True),
    "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/></w:sectPr>",
])

DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS} {R_NS}>
  <w:body>{BODY}</w:body>
</w:document>"""


# ---------------------------------------------------------------------------
# A document shaped the way Word really writes one
# ---------------------------------------------------------------------------
# The fixture above has one of every construct the importer understands, in
# its simplest form. A real file is fussier, and every item below is something
# a real document carried that the importer used to get wrong: the title in
# the "Title" style rather than in a Heading 1, a table of contents, lists
# whose numbering lives in the style, links written as fields, footnotes, a
# text box, hidden text, merged cells, code in a monospaced font.

WORD_NS = (W_NS + " " + R_NS + " " + A_NS + " " + V_NS + " "
           'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
           'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
           'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
           'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"')

# The Italian style ids Word writes, with the English names it keeps.
WORD_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W_NS}>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normale"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Titolo"><w:name w:val="Title"/><w:basedOn w:val="Normale"/></w:style>
  <w:style w:type="paragraph" w:styleId="Sottotitolo"><w:name w:val="Subtitle"/><w:basedOn w:val="Normale"/><w:rPr><w:i/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Titolo1"><w:name w:val="heading 1"/><w:basedOn w:val="Normale"/><w:pPr><w:numPr><w:numId w:val="9"/></w:numPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Titolo2"><w:name w:val="heading 2"/><w:basedOn w:val="Normale"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Puntoelenco"><w:name w:val="List Bullet"/><w:basedOn w:val="Normale"/><w:pPr><w:numPr><w:numId w:val="7"/></w:numPr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Numeroelenco"><w:name w:val="List Number"/><w:basedOn w:val="Normale"/><w:pPr><w:numPr><w:numId w:val="8"/></w:numPr></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Citazione"><w:name w:val="Quote"/><w:basedOn w:val="Normale"/><w:rPr><w:i/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="PreformattatoHTML"><w:name w:val="HTML Preformatted"/><w:basedOn w:val="Normale"/></w:style>
  <w:style w:type="paragraph" w:styleId="Sommario1"><w:name w:val="toc 1"/><w:basedOn w:val="Normale"/></w:style>
  <w:style w:type="character" w:styleId="Collegamentoipertestuale"><w:name w:val="Hyperlink"/><w:rPr><w:u w:val="single"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="Rimandonotaapidipagina"><w:name w:val="footnote reference"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="CodiceHTML"><w:name w:val="HTML Code"/><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/></w:rPr></w:style>
</w:styles>"""

# numId 7 and 8 are the ones the list styles point to; 9 numbers the
# headings ("1.", "2."), which must stay headings; 6 has no visible marker.
WORD_NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {W_NS}>
  <w:abstractNum w:abstractNumId="3"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>
  <w:abstractNum w:abstractNumId="4"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
  <w:abstractNum w:abstractNumId="5"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
  <w:abstractNum w:abstractNumId="6"><w:lvl w:ilvl="0"><w:numFmt w:val="none"/></w:lvl></w:abstractNum>
  <w:num w:numId="7"><w:abstractNumId w:val="3"/></w:num>
  <w:num w:numId="8"><w:abstractNumId w:val="4"/></w:num>
  <w:num w:numId="9"><w:abstractNumId w:val="5"/></w:num>
  <w:num w:numId="6"><w:abstractNumId w:val="6"/></w:num>
</w:numbering>"""

WORD_FOOTNOTES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes {W_NS}>
  <w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>
  <w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>
  <w:footnote w:id="1"><w:p><w:r><w:rPr><w:rStyle w:val="Rimandonotaapidipagina"/></w:rPr><w:footnoteRef/></w:r><w:r><w:t xml:space="preserve"> Testo della nota a piè di pagina.</w:t></w:r></w:p></w:footnote>
</w:footnotes>"""

WORD_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
  <Relationship Id="rId20" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/grafico.png"/>
  <Relationship Id="rId30" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/normale" TargetMode="External"/>
</Relationships>"""


def field(instruction, display_runs):
    """A complex field: begin, instruction, separator, what Word shows, end."""
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve">' + instruction + '</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            + display_runs + '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def raw_run(text, properties):
    """A run with the given w:rPr content."""
    return ('<w:r><w:rPr>' + properties + '</w:rPr><w:t xml:space="preserve">'
            + text + '</w:t></w:r>')


WORD_IMAGE = (
    '<w:r><w:drawing><wp:inline>'
    '<wp:extent cx="1905000" cy="1428750"/>'
    '<wp:docPr id="1" name="Immagine 1" descr="Grafico delle vendite 2025"/>'
    '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:blipFill><a:blip r:embed="rId20"/></pic:blipFill></pic:pic>'
    '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')

# The same text box twice, as Word writes it: DrawingML for new readers and
# VML for old ones. Reading both would put the text in the article twice.
WORD_TEXT_BOX = (
    '<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor>'
    '<wp:extent cx="2000000" cy="600000"/><wp:docPr id="2" name="Casella di testo 2"/>'
    '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
    '<wps:wsp><wps:txbx><w:txbxContent><w:p><w:r><w:t>Testo dentro una casella di testo.</w:t></w:r></w:p>'
    '</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>'
    '<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent><w:p><w:r><w:t>Testo dentro una casella di testo.</w:t></w:r></w:p>'
    '</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback></mc:AlternateContent></w:r>')

# Word's table of contents: a TOC field that opens in the first entry and
# closes in a paragraph of its own, each entry a link to a bookmark followed
# by a PAGEREF field with the page number. Word 2007 and later wrap the whole
# thing in a content control; older documents have the bare field.
def toc_paragraphs():
    return (paragraph(run("Sommario"), style="Sommario1")
            + paragraph('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                        '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
                        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                        '<w:hyperlink w:anchor="_Toc1">' + run("Introduzione")
                        + field(" PAGEREF _Toc1 \\h ", run("1")) + "</w:hyperlink>")
            + paragraph('<w:hyperlink w:anchor="_Toc2">' + run("Conclusioni")
                        + field(" PAGEREF _Toc2 \\h ", run("2")) + "</w:hyperlink>")
            + paragraph('<w:r><w:fldChar w:fldCharType="end"/></w:r>'))


WORD_TOC = ('<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/>'
            '<w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtContent>'
            + toc_paragraphs() + "</w:sdtContent></w:sdt>")


def merged_table():
    """A table with one cell merged across two columns and one down two rows."""
    def cell(content, properties=""):
        return "<w:tc><w:tcPr>" + properties + "</w:tcPr>" + content + "</w:tc>"
    return ("<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>"
            "<w:tr>" + cell(paragraph(run("Nome")))
            + cell(paragraph(run("Dettagli")), '<w:gridSpan w:val="2"/>') + "</w:tr>"
            "<w:tr>" + cell(paragraph(run("Alfa")), '<w:vMerge w:val="restart"/>')
            + cell(paragraph(run("prima riga")) + paragraph(run("seconda riga")))
            + cell(paragraph(run("3"))) + "</w:tr>"
            "<w:tr>" + cell(paragraph(""), "<w:vMerge/>")
            + cell(paragraph(run("b"))) + cell(paragraph(run("4"))) + "</w:tr>"
            "</w:tbl>")


WORD_BODY = "".join([
    paragraph(run("Guida pratica ai sistemi distribuiti"), style="Titolo"),
    paragraph(run("Appunti per chi parte da zero"), style="Sottotitolo"),
    WORD_TOC,
    paragraph(run("Un paragrafo con E=mc") + raw_run("2", '<w:vertAlign w:val="superscript"/>')
              + run(", H") + raw_run("2", '<w:vertAlign w:val="subscript"/>') + run("O e una nota")
              + '<w:r><w:rPr><w:rStyle w:val="Rimandonotaapidipagina"/></w:rPr>'
                '<w:footnoteReference w:id="1"/></w:r>'
              + run(". Prima") + raw_run("TESTO NASCOSTO", "<w:vanish/>") + run(" e dopo.")),
    paragraph('<w:bookmarkStart w:id="0" w:name="_Toc1"/>' + run("Introduzione")
              + '<w:bookmarkEnd w:id="0"/>', style="Titolo1"),
    paragraph(run("Link con campo semplice: ")
              + '<w:fldSimple w:instr=" HYPERLINK &quot;https://example.com/semplice&quot; ">'
                '<w:r><w:t>sito di esempio</w:t></w:r></w:fldSimple>' + run(".")),
    paragraph(run("Link con campo complesso: ")
              + field(' HYPERLINK "https://example.com/complesso" ',
                      run("altro sito", style="Collegamentoipertestuale")) + run(".")),
    paragraph(run("Link normale: ") + '<w:hyperlink r:id="rId30">'
              + run("terzo sito", style="Collegamentoipertestuale") + "</w:hyperlink>"),
    paragraph(run("Il comando ") + run("pyblog build", style="CodiceHTML") + run(" rigenera il sito.")),
    paragraph(run("Primo punto con stile elenco"), style="Puntoelenco"),
    paragraph(run("Secondo punto con stile elenco"), style="Puntoelenco"),
    paragraph(run("Passo numerato uno"), style="Numeroelenco"),
    paragraph(run("Passo numerato due"), style="Numeroelenco"),
    paragraph(run("Paragrafo in una numerazione senza segni"), num_id=6),
    paragraph(run("Una citazione con lo stile Citazione."), style="Citazione"),
    paragraph(run("def ciao():"), style="PreformattatoHTML"),
    paragraph(run("    return 42"), style="PreformattatoHTML"),
    paragraph(WORD_IMAGE),
    paragraph(WORD_TEXT_BOX + run("Paragrafo che contiene una casella di testo.")),
    paragraph(run("Prima della pagina nuova") + '<w:r><w:br w:type="page"/></w:r>'
              + run("dopo la pagina nuova")),
    '<w:customXml w:element="blocco">' + paragraph(run("Paragrafo dentro customXml.")) + "</w:customXml>",
    paragraph(run("Testo ") + '<w:customXml w:element="nome">' + run("dentro customXml")
              + "</w:customXml>" + run(" in linea.")),
    paragraph(""),
    paragraph(""),
    paragraph(""),
    merged_table(),
    paragraph(run("Conclusioni"), style="Titolo1"),
    paragraph(run("Dettaglio finale"), style="Titolo2"),
    paragraph(run("Fine.")),
    "<w:sectPr/>",
])

WORD_DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {WORD_NS}><w:body>{WORD_BODY}</w:body></w:document>"""

# The bare TOC field of an older document, with no content control around it
# and entries in a style of their own: nothing of it may reach the article.
BARE_TOC_BODY = "".join([
    paragraph(run("Documento con sommario"), style="Heading1"),
    toc_paragraphs().replace("Sommario1", "TOC1"),
    paragraph(run("Introduzione"), style="Heading2"),
    paragraph(run("Il testo vero comincia qui.")),
    "<w:sectPr/>",
])

# A Heading 1 in the middle of the text is a section, not the title.
MIDDLE_HEADING_BODY = "".join([
    paragraph(run("Il documento comincia con un paragrafo normale.")),
    paragraph(run("Una sezione"), style="Heading1"),
    paragraph(run("Testo della sezione.")),
    "<w:sectPr/>",
])


# ---------------------------------------------------------------------------
# Lines, pictures and tables used to lay out the page
# ---------------------------------------------------------------------------
# What a document looks like when its author pressed Shift+Enter instead of
# Enter, dragged a picture next to a paragraph, gave it a caption or put
# picture and text in a table to keep them together. None of it has a direct
# translation in the editor: Quill deletes a <br> inside a block, a picture
# shares its line with the text of its paragraph, and the editor's tables
# always have a header row. Every item below used to come out wrong.

LINE = "<w:r><w:br/></w:r>"

PICTURE_URI = "http://schemas.openxmlformats.org/drawingml/2006/picture"
SHAPE_URI = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
GROUP_URI = "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"


def picture_shape(width, height, description=""):
    """The pic:pic of a picture, with the size it has on the page (in EMU)."""
    return ('<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="grafico.png" descr="'
            + description + '"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rId20"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')


def anchor(width, height, offset, side=None, name="Immagine"):
    """
    The opening of a wp:anchor, the frame of a floating drawing: offset is
    how far under the top of its paragraph it starts, in EMU.
    """
    horizontal = "<wp:posOffset>0</wp:posOffset>"
    if side is not None:
        horizontal = "<wp:align>" + side + "</wp:align>"
    return ('<wp:anchor distT="0" distB="0" distL="114300" distR="114300" simplePos="0" '
            'relativeHeight="251658240" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
            '<wp:simplePos x="0" y="0"/>'
            '<wp:positionH relativeFrom="column">' + horizontal + "</wp:positionH>"
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{offset}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="{width}" cy="{height}"/><wp:wrapSquare wrapText="bothSides"/>'
            f'<wp:docPr id="1" name="{name}"/>')


def word_picture(description, width=1905000, height=1428750, floating=None, side=None):
    """
    A picture as Word writes it: in the line of text, or - when floating is
    a number - anchored to its paragraph, that many EMU under the top of it.
    """
    graphic = ('<a:graphic><a:graphicData uri="' + PICTURE_URI + '">'
               + picture_shape(width, height) + "</a:graphicData></a:graphic>")
    if floating is None:
        frame = (f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{width}" cy="{height}"/>'
                 f'<wp:docPr id="1" name="Immagine" descr="{description}"/>' + graphic + "</wp:inline>")
    else:
        frame = (anchor(width, height, floating, side).replace(
                    'name="Immagine"/>', f'name="Immagine" descr="{description}"/>')
                 + graphic + "</wp:anchor>")
    return "<w:r><w:rPr><w:noProof/></w:rPr><w:drawing>" + frame + "</w:drawing></w:r>"


def text_box(content, offset=0, width=1905000, height=400000):
    """
    A floating text box holding whole paragraphs, written twice as Word
    does: DrawingML for new readers, VML for old ones.
    """
    box = "<w:txbxContent>" + content + "</w:txbxContent>"
    return ('<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing>'
            + anchor(width, height, offset, name="Casella di testo")
            + '<a:graphic><a:graphicData uri="' + SHAPE_URI + '">'
            "<wps:wsp><wps:spPr/><wps:txbx>" + box + "</wps:txbx><wps:bodyPr/></wps:wsp>"
            "</a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>"
            '<mc:Fallback><w:pict><v:shape style="position:absolute;margin-left:0;'
            f'margin-top:{offset / 12700:.1f}pt;width:{width / 12700:.1f}pt;height:{height / 12700:.1f}pt">'
            "<v:textbox>" + box + "</v:textbox></v:shape></w:pict></mc:Fallback>"
            "</mc:AlternateContent></w:r>")


def picture_group(shapes, width, width_when_made, height=1428750):
    """
    Pictures grouped into one floating drawing. The group has been stretched
    since it was made: its shapes still carry the measures they had then.
    """
    return ("<w:r><w:drawing>" + anchor(width, height, 0, name="Gruppo")
            + '<a:graphic><a:graphicData uri="' + GROUP_URI + '">'
            '<wpg:wgp xmlns:wpg="' + GROUP_URI + '"><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm>'
            f'<a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/>'
            f'<a:chOff x="0" y="0"/><a:chExt cx="{width_when_made}" cy="{height}"/>'
            "</a:xfrm></wpg:grpSpPr>" + shapes + "</wpg:wgp>"
            "</a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>")


def grouped_text_box(content):
    """A text box that is one shape of a group: it has no frame of its own."""
    return ("<wps:wsp><wps:spPr/><wps:txbx><w:txbxContent>" + content
            + "</w:txbxContent></wps:txbx><wps:bodyPr/></wps:wsp>")


# A floating picture the way Word 2003 and many converters write one: VML,
# with its position and size in a CSS-like style.
OLD_FLOATING_PICTURE = (
    '<w:r><w:pict><v:shape type="#_x0000_t75" alt="Vecchio stile" '
    'style="position:absolute;margin-left:0;margin-top:0;width:150pt;height:112.5pt;'
    'mso-position-horizontal:center;mso-position-vertical-relative:text">'
    '<v:imagedata r:id="rId20"/></v:shape></w:pict></w:r>')

# A field left open at the end of its paragraph and closed two paragraphs
# later: the bibliography Word and the reference managers write.
FIELD_OPEN = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText xml:space="preserve"> BIBLIOGRAPHY </w:instrText></w:r>'
              '<w:r><w:fldChar w:fldCharType="separate"/></w:r>')
FIELD_CLOSE = '<w:r><w:fldChar w:fldCharType="end"/></w:r>'


def layout_table(rows):
    """
    A table used to lay out the page: its cells hold whole paragraphs (given
    as XML) and its borders are hidden.
    """
    out = ['<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
           '<w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
           '<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders></w:tblPr>']
    for cells in rows:
        out.append("<w:tr>" + "".join("<w:tc><w:tcPr/>" + cell + "</w:tc>" for cell in cells)
                   + "</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def link(runs):
    """A hyperlink to the address of rId30."""
    return '<w:hyperlink r:id="rId30">' + runs + "</w:hyperlink>"


LINES_BODY = "".join([
    paragraph(run("Righe, immagini") + LINE + run("e tabelle"), style="Titolo"),

    # --- Line breaks ---
    paragraph("<w:r><w:t>ciao mamma.</w:t><w:br/><w:t>Si sono qui!</w:t></w:r>"),
    paragraph("<w:r><w:rPr><w:b/></w:rPr><w:t>Grassetto prima</w:t><w:br/>"
              "<w:t>grassetto dopo</w:t></w:r>"),
    paragraph(run("Centrato sopra") + LINE + run("centrato sotto"), alignment="center"),
    paragraph(run("Un ") + link(run("collegamento su") + LINE + run("due righe"))
              + run(" e basta.")),
    paragraph(run("Prima riga") + LINE + LINE + run("terza riga, dopo una vuota") + LINE),
    paragraph(run("Sezione su") + LINE + run("due righe"), style="Titolo1"),
    paragraph(run("Voce su") + LINE + run("due righe"), style="Puntoelenco"),
    paragraph(run("Citazione, prima riga") + LINE + run("citazione, seconda riga"),
              style="Citazione"),
    paragraph(FIELD_OPEN + run("Rossi, Primo libro, 2020.")),
    paragraph(run("Bianchi, Secondo libro, 2021.")),
    paragraph(run("Verdi, Terzo libro, 2022.") + FIELD_CLOSE),

    # --- Pictures in the line of text ---
    paragraph(word_picture("Con didascalia") + LINE + run("Didascalia in grassetto", bold=True)
              + LINE + run("Testo normale dopo la didascalia."), alignment="center"),
    paragraph(word_picture("Prima del testo") + run("Testo subito dopo l'immagine.")),
    paragraph(run("Testo subito prima dell'immagine.") + word_picture("Dopo il testo")),
    paragraph(run("Questa figura ") + word_picture("In mezzo")
              + run(" sta in mezzo alla frase.")),
    paragraph(word_picture("Icona", width=152400, height=152400)
              + run(" Nota: un'icona resta nella riga.")),
    paragraph(link(word_picture("Con collegamento") + run("Testo del collegamento"))),
    paragraph(word_picture("Da margine a margine", width=6120130, height=3000000)),
    paragraph(word_picture("Nel titolo") + run("Sezione con immagine"), style="Titolo1"),

    # --- Floating pictures and text boxes ---
    paragraph(word_picture("Flottante in cima", floating=0, side="center")
              + run("Paragrafo con un'immagine flottante in cima.")),
    paragraph(word_picture("Flottante in basso", floating=900000)
              + run("Paragrafo con un'immagine flottante in basso.")),
    # The caption Word adds to a floating picture: a text box under it,
    # anchored to the same paragraph and written before the picture.
    paragraph(text_box(paragraph(run("Figura 1 - didascalia in una casella", bold=True),
                                 alignment="center"), offset=1500000)
              + word_picture("Con didascalia in casella", floating=0)
              + run("Paragrafo a cui sono ancorate immagine e didascalia.")),
    # The caption LibreOffice adds: a frame around the picture and its text,
    # wider than the picture.
    paragraph(text_box(paragraph(word_picture("Dentro la cornice")
                                 + run("Figura 2: didascalia nella cornice")),
                       width=2857500, height=1900000)
              + run("Paragrafo a cui e' ancorata la cornice.")),
    paragraph(word_picture("Sola nel paragrafo", floating=0)),
    paragraph(run("Dopo il paragrafo che aveva solo un'immagine flottante.")),
    paragraph(run("Voce con immagine flottante") + word_picture("Nella voce", floating=0),
              style="Numeroelenco"),
    paragraph(run("Voce seguente"), style="Numeroelenco"),
    paragraph(picture_group(picture_shape(1905000, 1428750, "Sinistra")
                            + picture_shape(1905000, 1428750, "Destra"),
                            width=5715000, width_when_made=3810000)
              + run("Paragrafo con due immagini raggruppate.")),
    # A picture grouped with its caption, so the two move together: the
    # group is as wide as the caption, the picture is narrower.
    paragraph(picture_group(picture_shape(1905000, 1428750, "Raggruppata con la didascalia")
                            + grouped_text_box(paragraph(run("Figura 3 - didascalia nel gruppo"))),
                            width=3810000, width_when_made=3810000, height=1900000)
              + run("Paragrafo con immagine e didascalia raggruppate.")),
    paragraph(OLD_FLOATING_PICTURE + run("Paragrafo con un'immagine flottante vecchio stile.")),

    # --- Tables that lay out the page, and one that is a table ---
    layout_table([[paragraph(word_picture("In tabella"), alignment="center")
                   + paragraph(run("Didascalia in tabella", bold=True), alignment="center")
                   + paragraph(run("Testo normale nella stessa cella."))]]),
    layout_table([[paragraph(word_picture("Colonna sinistra")),
                   paragraph(run("Testo della colonna destra."))]]),
    layout_table([[paragraph(run("Riquadro a una colonna."))],
                  [table([["Dato A", "Dato B"], ["1", "2"]])]]),
    # A grid stays a table even with its borders hidden. Its cells hold
    # lines: a line break and a picture end theirs with a <br>.
    layout_table([[paragraph(run("Chiave")), paragraph(run("Valore"))],
                  [paragraph(run("riga uno") + LINE + run("riga due")),
                   paragraph(word_picture("In cella", floating=0) + run("testo della cella"))],
                  [paragraph(word_picture("Con didascalia in cella")
                             + run("Didascalia in cella")),
                   paragraph(run("ultima cella"))]]),

    paragraph(run("Fine") + '<w:r><w:footnoteReference w:id="1"/></w:r>' + run(".")),
    # A4 with 2 cm margins: the text is 17 cm wide, 6120130 EMU.
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1417" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>',
])

LINES_DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {WORD_NS}><w:body>{LINES_BODY}</w:body></w:document>"""

LINES_FOOTNOTES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes {W_NS}>
  <w:footnote w:id="1"><w:p><w:r><w:t>Nota su</w:t><w:br/><w:t>due righe.</w:t></w:r></w:p></w:footnote>
</w:footnotes>"""

# A field that is opened and never closed, as a damaged document or a
# converter can leave one: the text after it is the rest of the document.
UNCLOSED_FIELD_BODY = "".join([
    paragraph(run("Documento con un campo rotto"), style="Heading1"),
    paragraph(run("Prima del campo.")),
    paragraph(run("Oggi e' il ") + FIELD_OPEN.replace(" BIBLIOGRAPHY ", " DATE ")
              + run("7 ottobre")),
    paragraph(run("Paragrafo dopo il campo mai chiuso.")),
    paragraph(run("Ultimo paragrafo.")),
    "<w:sectPr/>",
])

# A picture above the first Heading 1 - a cover, a logo - and the heading is
# still the title of the document.
COVER_BODY = "".join([
    paragraph(drawing("rId10")),
    paragraph(run("Titolo sotto la copertina"), style="Heading1"),
    paragraph(run("Il testo comincia qui.")),
    "<w:sectPr/>",
])


def tiny_png(width=8, height=8, colour=(0x2a, 0x6f, 0xd0)):
    """A real, valid PNG built by hand, so the importer's magic-byte check passes."""
    rows = b""
    for _ in range(height):
        rows += b"\x00" + bytes(colour) * width

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b""))


def write_docx(path_value, parts):
    """Write the parts as a ZIP archive, which is all a .docx is."""
    with zipfile.ZipFile(path_value, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            archive.writestr(name, data)


def build_all():
    """Write every fixture into this folder."""
    full = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": DOCUMENT,
        "word/_rels/document.xml.rels": DOCUMENT_RELS,
        "word/styles.xml": STYLES,
        "word/numbering.xml": NUMBERING,
        "word/media/image1.png": tiny_png(),
        "word/media/vecchia.png": tiny_png(colour=(0xd0, 0x50, 0x2a)),
        # A WMF: a real Word document can embed one, and no browser shows it.
        "word/media/disegno.wmf": b"\xd7\xcd\xc6\x9a" + b"\x00" * 64,
    }
    write_docx(HERE / "documento-completo.docx", full)

    # The same document with no numbering part: the importer must fall back to
    # bulleted lists instead of failing.
    no_numbering = dict(full)
    del no_numbering["word/numbering.xml"]
    write_docx(HERE / "senza-numerazione.docx", no_numbering)

    # A document with no styles part at all, as some converters produce.
    no_styles = dict(full)
    del no_styles["word/styles.xml"]
    write_docx(HERE / "senza-stili.docx", no_styles)

    # A valid ZIP that is not a Word document.
    write_docx(HERE / "non-e-word.docx", {"hello.txt": "I am not a document"})

    # A file whose XML is broken halfway through.
    broken = dict(full)
    broken["word/document.xml"] = DOCUMENT[:len(DOCUMENT) // 2]
    write_docx(HERE / "xml-rotto.docx", broken)

    # Not a ZIP at all.
    (HERE / "non-e-zip.docx").write_bytes(b"Questo e' solo testo, non un archivio.")

    # The document shaped the way Word really writes one.
    write_docx(HERE / "documento-word.docx", {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": WORD_DOCUMENT,
        "word/_rels/document.xml.rels": WORD_RELS,
        "word/styles.xml": WORD_STYLES,
        "word/numbering.xml": WORD_NUMBERING,
        "word/footnotes.xml": WORD_FOOTNOTES,
        "word/media/grafico.png": tiny_png(width=40, height=30),
    })

    # Line breaks, pictures with their captions, tables that lay out the page.
    write_docx(HERE / "documento-righe.docx", {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": LINES_DOCUMENT,
        "word/_rels/document.xml.rels": WORD_RELS,
        "word/styles.xml": WORD_STYLES,
        "word/numbering.xml": WORD_NUMBERING,
        "word/footnotes.xml": LINES_FOOTNOTES,
        "word/media/grafico.png": tiny_png(width=40, height=30),
    })

    # A field with no end mark.
    unclosed = dict(full)
    unclosed["word/document.xml"] = DOCUMENT.replace(BODY, UNCLOSED_FIELD_BODY)
    write_docx(HERE / "campo-non-chiuso.docx", unclosed)

    # A picture above the Heading 1 that is the title.
    cover = dict(full)
    cover["word/document.xml"] = DOCUMENT.replace(BODY, COVER_BODY)
    write_docx(HERE / "copertina.docx", cover)

    # The table of contents of an older document, as a bare field.
    bare_toc = dict(full)
    bare_toc["word/document.xml"] = DOCUMENT.replace(BODY, BARE_TOC_BODY)
    write_docx(HERE / "sommario-campo.docx", bare_toc)

    # A Heading 1 that is not at the start: it must stay in the text.
    middle = dict(full)
    middle["word/document.xml"] = DOCUMENT.replace(BODY, MIDDLE_HEADING_BODY)
    write_docx(HERE / "titolo-a-meta.docx", middle)

    # A document with no title and no text worth importing.
    empty = dict(full)
    empty["word/document.xml"] = DOCUMENT.replace(BODY, paragraph(run("   ")))
    write_docx(HERE / "vuoto.docx", empty)

    for path_value in sorted(HERE.glob("*.docx")):
        print(f"  {path_value.name:28s} {path_value.stat().st_size:>7} bytes")


if __name__ == "__main__":
    print("Writing the .docx fixtures:")
    build_all()
