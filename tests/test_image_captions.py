#!/usr/bin/env python3
"""
Checks on the alternative text and the caption of pictures.

    python3 tests/test_image_captions.py

In the editor a caption is the paragraph under a picture with the class
image-caption; the site turns the two into <figure> and <figcaption>, and a
picture with no alternative text takes its caption as one. A Word document
brings its captions along when they use the caption style.
"""
import io
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build  # noqa: E402
from core.docx_import import convert_docx  # noqa: E402

PASSED = 0
FAILED = 0
ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


def test_figures():
    print("\nfigures on the page")
    figure = build.captioned_figures
    result = figure('<p class="ql-align-center"><img src="/media/a.png" width="300"></p>'
                    '<p class="ql-align-center image-caption">The <em>graph</em> &amp; its nodes</p><p>after</p>')
    check("a picture and its caption become a figure, aligned like the picture",
          result.startswith('<figure class="ql-align-center"><img ')
          and "<figcaption>The <em>graph</em> &amp; its nodes</figcaption></figure><p>after</p>" in result, result)
    check("a picture with no alternative text takes the caption, as plain text",
          'alt="The graph &amp; its nodes"' in result, result)
    result = figure('<p><img src="/media/a.png" alt="Five nodes"></p><p class="image-caption">Figure 1</p>')
    check("an alternative text already there is kept",
          result == '<figure><img src="/media/a.png" alt="Five nodes"><figcaption>Figure 1</figcaption></figure>',
          result)
    result = figure('<p><video controls src="/media/v.mp4"></video></p><p class="image-caption">A clip</p>')
    check("a video gets its caption too, with no alt", result ==
          '<figure><video controls src="/media/v.mp4"></video><figcaption>A clip</figcaption></figure>', result)
    lonely = '<p class="image-caption">No picture above</p>'
    check("a caption with no picture above stays a paragraph", figure(lonely) == lonely)
    inline = '<p>Text <img src="/media/a.png"> more</p><p class="image-caption">Caption</p>'
    check("a picture inside a sentence is left alone", figure(inline) == inline)
    page = build.add_lazy_loading('<p><img src="/media/a.png"></p><p class="image-caption">X</p>')
    check("the pages get the figures, lazy loading included",
          "<figure>" in page and 'loading="lazy"' in page, page)
    css = (ROOT / "static" / "style.css").read_text()
    check("the site styles the caption", "figcaption, p.image-caption" in css)


def caption_docx():
    """A Word document with a normal paragraph and a centred caption."""
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'),
        # Italian Word: the id of the caption style is localised, its name is not.
        "word/styles.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><w:styles {w}>'
            '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="Didascalia"><w:name w:val="caption"/><w:basedOn w:val="Normal"/></w:style>'
            '</w:styles>'),
        "word/document.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><w:document {w}><w:body>'
            '<w:p><w:r><w:t>Ordinary text.</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:pStyle w:val="Didascalia"/><w:jc w:val="center"/></w:pPr>'
            '<w:r><w:t>Figure 1: the graph</w:t></w:r></w:p>'
            '</w:body></w:document>'),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_word_captions():
    print("\ncaptions from Word")
    result = convert_docx(caption_docx())
    html_value = result.get("content", "")
    check("a paragraph in the caption style becomes a caption, keeping its alignment",
          '<p class="ql-align-center image-caption">Figure 1: the graph</p>' in html_value, html_value)
    check("an ordinary paragraph stays ordinary", "<p>Ordinary text.</p>" in html_value, html_value)


def test_editor():
    print("\nthe editor")
    script = (ROOT / "static" / "admin.js").read_text()
    check("the caption class is registered with Quill before the editors are made",
          "new Parchment.Attributor.Class('imagecaption', 'image'" in script
          and "registerImageCaption();" in script)
    check("both the article and the homepage editors watch their pictures",
          script.count("watchImageDescriptions(") >= 3)
    check("the alternative text goes through Quill, so it is saved and undone with the text",
          "editor.formatText(lines.index, 1, 'alt'" in script)
    for name in ("editor.html", "config.html"):
        template = (ROOT / "templates" / "admin" / name).read_text()
        check(f"{name}: the button and the warning about pictures without a description",
              'id="image-details-button"' in template and 'id="image-alt-status"' in template)


def main():
    test_figures()
    test_word_captions()
    test_editor()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
