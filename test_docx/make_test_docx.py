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
    table([["Esterna A", "Esterna B"]], nested=True),
    "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/></w:sectPr>",
])

DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W_NS} {R_NS}>
  <w:body>{BODY}</w:body>
</w:document>"""


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

    # A document with no title and no text worth importing.
    empty = dict(full)
    empty["word/document.xml"] = DOCUMENT.replace(BODY, paragraph(run("   ")))
    write_docx(HERE / "vuoto.docx", empty)

    for path_value in sorted(HERE.glob("*.docx")):
        print(f"  {path_value.name:28s} {path_value.stat().st_size:>7} bytes")


if __name__ == "__main__":
    print("Writing the .docx fixtures:")
    build_all()
