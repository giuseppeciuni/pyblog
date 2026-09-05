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

    check("bulleted list with nesting",
          "<ul><li>Primo punto</li><li>Secondo punto<ul><li>Punto annidato</li></ul>"
          "</li><li>Terzo punto</li></ul>" in content)
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

    check("DrawingML image extracted", '<img src="/media/image1' in content)
    check("legacy VML image extracted", '<img src="/media/vecchia' in content)
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
    test_missing_numbering()
    test_missing_styles()
    test_broken_input()
    print(f"\n{PASSED} passed, {FAILED} failed")
    print(f"(images written to {articles.MEDIA_DIR})")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
