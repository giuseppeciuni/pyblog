#!/usr/bin/env python3
"""
Tests for core/docx_import.py.

They run against the fixtures written by make_test_docx.py (which this script
regenerates first, so the two can never drift apart).

    python3 test_docx/test_import.py

No test framework: this project has no dependencies, and a list of assertions
with a counter is enough to tell whether the importer still does its job.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import make_test_docx  # noqa: E402  (the fixtures must exist before the tests)
from core import articles  # noqa: E402
from core.docx_import import (convert_docx, convert_docx_file,  # noqa: E402
                              looks_like_docx)

# Importing a document saves its images through save_uploaded_file, which
# writes into output/media. A test run must not litter the real site, so we
# point the media folder at a scratch directory next to the fixtures.
articles.MEDIA_DIR = HERE / "_media_di_prova"

PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    """Record one assertion and print its outcome."""
    global PASSED, FAILED
    if condition:
        PASSED = PASSED + 1
        print(f"  ok    {description}")
    else:
        FAILED = FAILED + 1
        print(f"  FAIL  {description}")
        if detail != "":
            print(f"        {detail}")


def warning_keys(result):
    """The set of warning keys a conversion produced."""
    return {w["key"] for w in result["warnings"]}


def test_full_document():
    """The document that contains one of everything we claim to support."""
    print("\ndocumento-completo.docx")
    result = convert_docx_file(HERE / "documento-completo.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    content = result["content"]

    check("the first Heading 1 becomes the title",
          result["title"] == "Guida completa all'import da Word", repr(result["title"]))
    check("the title is removed from the body", "<h1" not in content)

    check("direct bold", "<strong>grassetto diretto</strong>" in content)
    check("direct italic", "<em>corsivo</em>" in content)
    check("direct underline", "<u>sottolineato</u>" in content)
    check("direct strikethrough", "<s>barrato</s>" in content)

    check("bold inherited from a character style",
          "<strong>Grassetto ereditato dallo stile di carattere</strong>" in content)
    check("italic inherited from a character style",
          "<em>Corsivo ereditato dallo stile di carattere</em>" in content)
    check("bold inherited from a paragraph style",
          "<strong>Tutto il paragrafo eredita il grassetto dallo stile</strong>" in content)
    check('w:b w:val="0" cancels the style bold',
          "<p>Questo pezzo annulla il grassetto dello stile</p>" in content)

    check("centre alignment", '<p class="ql-align-center">Paragrafo centrato</p>' in content)
    check("justified alignment", '<p class="ql-align-justify">Paragrafo giustificato</p>' in content)

    check("English heading style", "<h2>Sezione con stile inglese</h2>" in content)
    check("Italian heading style", "<h3>Sezione con stile italiano</h3>" in content)
    check("style derived from a heading", "<h2>Sezione con stile derivato da Heading2</h2>" in content)

    # Flat, the way Quill writes lists: a <ul> nested in an <li> makes Quill
    # throw the whole list away when the editor loads it.
    check("bulleted list with nesting, in Quill's flat form",
          "<ul><li>Primo punto</li><li>Secondo punto</li>"
          '<li class="ql-indent-1">Punto annidato</li><li>Terzo punto</li></ul>' in content)
    check("no list is nested inside another", "<li>Secondo punto<ul>" not in content)
    check("no line breaks between the blocks (Quill turns them into empty lines)",
          "\n" not in content)
    check("numbered list is an ol",
          "<ol><li>Primo passo</li><li>Secondo passo</li></ol>" in content)

    check("allowed hyperlink is kept",
          '<a href="https://example.com/pagina">collegamento buono</a>' in content)
    check("javascript: hyperlink is dropped, text kept",
          "javascript:" not in content and "collegamento pericoloso" in content)
    check("a warning reports the dropped link",
          "warn_docx_link_skipped" in warning_keys(result))

    check("table with a header row",
          '<table class="article-table"><tbody><tr><th>Comando</th><th>Effetto</th></tr>'
          "<tr><td>build</td><td>rigenera</td></tr>" in content)
    # Without this wrapper Quill has no blot for the element, deletes it on
    # the first normalisation, and the imported table disappears while the
    # text and images around it survive.
    check("tables carry the raw-html-block wrapper the editor needs",
          content.count('<div class="raw-html-block" contenteditable="false">'
                        '<table class="article-table">') == 3)
    check("every table is wrapped, none is left bare",
          content.count("<table class=") == content.count('<div class="raw-html-block"'))

    # A table as Word really writes it: property elements before the rows, a
    # column grid, per-row and per-cell properties, and one row inside a
    # content control.
    check("a table with Word's property elements is read",
          "<th>Parametro</th><th>Valore</th><th>Note</th>" in content)
    check("a row wrapped in a content control is not lost",
          "<td>porta</td><td>8000</td><td>predefinita</td>" in content)
    check("the rows after it are still read",
          "<td>host</td><td>127.0.0.1</td><td>solo locale</td>" in content)

    check("nested table is flattened to text",
          "dentro A dentro B dentro C dentro D" in content
          and content.count("<table") == 3)
    check("a warning reports the flattened table",
          "warn_docx_nested_table" in warning_keys(result))

    # The saved files carry the document's name: every Word file calls its
    # first picture image1.png.
    check("DrawingML image extracted", '<img src="/media/documento-completo-image1' in content)
    check("legacy VML image extracted", '<img src="/media/documento-completo-vecchia' in content)
    check("images are lazy loaded", content.count('loading="lazy"') == 2)
    check("WMF image is refused", ".wmf" not in content)
    check("a warning reports the refused image",
          "warn_docx_image_skipped" in warning_keys(result))

    check("tracked insertion is kept", "Testo inserito con revisioni attive." in content)
    check("tracked deletion is dropped", "Testo cancellato" not in content)
    check("line break becomes <br>", "Riga uno<br>riga due" in content)

    check("markup in the text is escaped",
          "&lt;script&gt;alert(1)&lt;/script&gt;" in content
          and "<script>" not in content)
    check("ampersand is escaped", "e &amp; da neutralizzare" in content)


def test_word_document():
    """A document shaped the way Word writes one, with the parts that used to go wrong."""
    print("\ndocumento-word.docx")
    result = convert_docx_file(HERE / "documento-word.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    content = result["content"]
    keys = warning_keys(result)

    check("the Title style becomes the title",
          result["title"] == "Guida pratica ai sistemi distribuiti", repr(result["title"]))
    check("the subtitle is offered as a description",
          result["subtitle"] == "Appunti per chi parte da zero")
    check("the title is not repeated in the text",
          "Guida pratica ai sistemi distribuiti" not in content)
    check("a Heading 1 becomes an h2: the h1 of the page is the title",
          "<h2>Introduzione</h2>" in content and "<h1" not in content)
    check("a Heading 2 becomes an h3", "<h3>Dettaglio finale</h3>" in content)
    check("headings numbered by their style are still headings",
          "<h2>Conclusioni</h2>" in content)
    check("no bold inside the headings", "<h2><strong>" not in content)

    check("Word's table of contents is left out",
          "Sommario" not in content and "Introduzione 1" not in content
          and content.count("Introduzione") == 1)
    check("a warning says the table of contents was left out",
          "warn_docx_toc_skipped" in keys)

    check("superscript", "E=mc<sup>2</sup>" in content)
    check("subscript", "H<sub>2</sub>O" in content)
    check("hidden text is not published", "TESTO NASCOSTO" not in content)
    check("the footnote mark stays where it was", "una nota<sup>[1]</sup>" in content)
    check("the footnote text goes at the end, under its heading",
          content.endswith("<h2>Note</h2><ol><li>Testo della nota a piè di pagina.</li></ol>"))

    check("a link written as a simple field keeps text and address",
          '<a href="https://example.com/semplice">sito di esempio</a>' in content)
    check("a link written as a complex field keeps text and address",
          '<a href="https://example.com/complesso">altro sito</a>' in content)
    check("the Hyperlink style does not add a <u> inside links",
          "<a href=\"https://example.com/normale\">terzo sito</a>" in content
          and "<u>" not in content)
    check("a code font in the middle of a sentence becomes <code>",
          "Il comando <code>pyblog build</code> rigenera il sito." in content)

    check("a list whose numbering is in the style is a list",
          "<ul><li>Primo punto con stile elenco</li><li>Secondo punto con stile elenco</li></ul>"
          in content)
    check("and a numbered one is an ol",
          "<ol><li>Passo numerato uno</li><li>Passo numerato due</li></ol>" in content)
    check("a numbering with no visible mark is a plain paragraph",
          "<p>Paragrafo in una numerazione senza segni</p>" in content)
    check("the Quote style becomes a quotation, without the style's italics",
          "<blockquote>Una citazione con lo stile Citazione.</blockquote>" in content)
    check("consecutive code lines become one block, indentation kept",
          '<pre class="ql-syntax" spellcheck="false">def ciao():\n    return 42</pre>' in content)

    check("the image keeps the alternative text written in Word",
          'alt="Grafico delle vendite 2025"' in content)
    check("and the size it had on the page", 'width="200"' in content)
    check("the image file carries the document's name",
          '<img src="/media/documento-word-grafico' in content)

    check("the text of a text box is kept, once",
          content.count("Testo dentro una casella di testo.") == 1)
    check("a page break does not glue two words together",
          "Prima della pagina nuova dopo la pagina nuova" in content)
    check("paragraphs inside custom XML are kept", "Paragrafo dentro customXml." in content)
    check("text inside inline custom XML is kept",
          "Testo dentro customXml in linea." in content)
    check("three empty paragraphs become one", content.count("<p><br></p>") == 1)

    check("cells merged across columns keep their colspan",
          '<th colspan="2">Dettagli</th>' in content)
    check("cells merged down rows keep their rowspan",
          '<td rowspan="2">Alfa</td>' in content)
    check("the cell covered by the merge is not written",
          "<tr><td>b</td><td>4</td></tr>" in content)
    check("two paragraphs in a cell stay on two lines",
          "<td>prima riga<br>seconda riga</td>" in content)
    check("nothing between the blocks", "</p>\n" not in content and "</h2>\n" not in content)


def test_table_of_contents_as_a_field():
    """An older document's table of contents: a bare field across paragraphs."""
    print("\nsommario-campo.docx")
    result = convert_docx_file(HERE / "sommario-campo.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    content = result["content"]
    check("the entries of the table of contents are gone",
          "Sommario" not in content and "Conclusioni" not in content)
    check("the text after it is all there",
          content == "<h2>Introduzione</h2><p>Il testo vero comincia qui.</p>", content)


def test_heading_in_the_middle():
    """A Heading 1 after the first paragraph is a section, not the title."""
    print("\ntitolo-a-meta.docx")
    result = convert_docx_file(HERE / "titolo-a-meta.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    check("the section heading stays in the text", "<h2>Una sezione</h2>" in result["content"])
    check("the title falls back to the file name", result["title"] == "titolo-a-meta")
    check("and the author is told", "warn_docx_title_from_filename" in warning_keys(result))


def test_missing_numbering():
    """Without numbering.xml every list falls back to bullets, with a warning."""
    print("\nsenza-numerazione.docx")
    result = convert_docx_file(HERE / "senza-numerazione.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    check("lists still render", "<li>Primo punto</li>" in result["content"])
    check("no numbered list is invented", "<ol>" not in result["content"])
    check("a warning explains the fallback",
          "warn_docx_numbering_missing" in warning_keys(result))


def test_missing_styles():
    """Without styles.xml the headings are gone but the text survives."""
    print("\nsenza-stili.docx")
    result = convert_docx_file(HERE / "senza-stili.docx")
    check("conversion succeeds", result["ok"], result.get("error_key", ""))
    if not result["ok"]:
        return
    check("the text is still there", "Paragrafo centrato" in result["content"])
    check("alignment still works",
          'class="ql-align-center"' in result["content"])


def test_broken_input():
    """Every kind of bad input produces a clean error, never a traceback."""
    print("\nmalformed input")
    for name, expected in (("non-e-zip.docx", "err_docx_not_a_zip"),
                           ("non-e-word.docx", "err_docx_no_document"),
                           ("xml-rotto.docx", "err_docx_parse"),
                           ("vuoto.docx", "err_docx_empty")):
        result = convert_docx_file(HERE / name)
        check(f"{name} -> {expected}",
              result["ok"] is False and result["error_key"] == expected,
              str(result))

    check("an empty file is refused",
          convert_docx(b"")["error_key"] == "err_docx_not_a_zip")
    check("random bytes are refused",
          convert_docx(bytes(range(256)))["error_key"] == "err_docx_not_a_zip")
    check("a truncated ZIP is refused",
          convert_docx(b"PK\x03\x04" + b"\x00" * 30)["ok"] is False)
    check("a missing file is refused",
          convert_docx_file(HERE / "non-esiste.docx")["ok"] is False)
    check("looks_like_docx accepts a ZIP signature",
          looks_like_docx(b"PK\x03\x04rest") is True)
    check("looks_like_docx rejects anything else",
          looks_like_docx(b"%PDF-1.4") is False)


def main():
    print("Regenerating the fixtures...")
    make_test_docx.build_all()
    # A clean media folder every run, so the file names in the assertions
    # stay predictable (a second run would otherwise produce image1-1.png).
    if articles.MEDIA_DIR.exists():
        for leftover in articles.MEDIA_DIR.iterdir():
            leftover.unlink()
    test_full_document()
    test_word_document()
    test_table_of_contents_as_a_field()
    test_heading_in_the_middle()
    test_missing_numbering()
    test_missing_styles()
    test_broken_input()
    print(f"\n{PASSED} passed, {FAILED} failed")
    print(f"(images written to {articles.MEDIA_DIR})")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
