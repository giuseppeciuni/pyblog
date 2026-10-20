#!/usr/bin/env python3
"""
Checks on the stylesheets.

    python3 tests/test_stylesheets.py

There is no browser here to render anything, so these do not check how a page
looks. They check the handful of CSS invariants that, when broken, produced a
bug you can only see by looking - and that therefore came back more than once.

The one that started this file: the cover of the highlighted article was sized
with "flex: 0 0 20%" and a max-width. Both were wrong.

  - A flex item whose width is not declared takes its automatic minimum size
    (min-width:auto) from its CONTENT, and for an image that is the intrinsic
    width of the file. An 800px cover therefore claimed 800px, refused to
    shrink, and pushed the article text out of the block.
  - The max-width meant to cap it never applied, because the global
    "img { max-width:100% !important }" rule overrides it.
"""
import pathlib
import re
import sys

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED = PASSED + 1
        print(f"  ok    {description}")
    else:
        FAILED = FAILED + 1
        print(f"  FAIL  {description}")
        if detail != "":
            print(f"        {detail}")


def regola(testo, selector):
    """
    The declarations of the first rule with this EXACT selector.

    Anchored at the start of a line: without that, looking for "img" also
    matches ".card-page img", and the check reads the wrong rule.
    """
    found_one = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", testo)
    if found_one is None:
        return None
    return " ".join(found_one.group(1).split())


def test_featured_cover():
    """The cover thumbnail must be immune to the size of the uploaded file."""
    # The highlighted block became the lead row of the list in the two-column
    # layout: every row, the lead included, uses this thumbnail.
    print("\nminiatura delle righe degli articoli (style.css)")
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    declarations = regola(css, ".art-thumb-img, .art-tile")
    check("la regola esiste", declarations is not None)
    if declarations is None:
        return

    check("la larghezza e' dichiarata, non lasciata al flex-basis",
          re.search(r"(^|[^-])width:", declarations) is not None, declarations)
    check("min-width:0 disattiva la dimensione minima automatica",
          "min-width:0" in declarations.replace(" ", ""), declarations)
    check("il tetto non e' affidato a max-width, che la regola globale vince",
          "max-width" not in declarations, declarations)
    check("il ritaglio e' impostato", "object-fit:cover" in declarations.replace(" ", ""))

    global_value = regola(css, "img")
    check("la regola globale sulle immagini e' ancora !important "
          "(e' il motivo per cui non si usa max-width qui)",
          global_value is not None and "!important" in global_value, str(global_value))


def test_editor_preview():
    """The editor thumbnail has the same trap on the vertical axis."""
    print("\nminiatura della copertina nell'editor (admin.css)")
    css = (ROOT_DIR / "static" / "admin.css").read_text(encoding="utf-8")
    declarations = regola(css, ".copertina-anteprima")
    check("la regola esiste", declarations is not None)
    if declarations is None:
        return
    compact = declarations.replace(" ", "")
    check("min-width:0 presente", "min-width:0" in compact, declarations)
    check("min-height:0 presente", "min-height:0" in compact, declarations)
    check("ha un tetto di larghezza", "max-width" in compact, declarations)


def test_flex_images_have_a_width():
    """
    Every image that is a flex item must declare a width.

    This is the general form of the bug above: without one, the automatic
    minimum size is the size of the file, and a large upload breaks the
    layout of whatever sits next to it.
    """
    print("\nogni immagine dentro un contenitore flex ha una larghezza")
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    # The images this project places inside a flex row or column.
    for selector in (".art-thumb-img, .art-tile", ".author-box-photo", ".profilo-foto"):
        declarations = regola(css, selector)
        if declarations is None:
            check(f"{selector}: la regola esiste", False)
            continue
        has_width = re.search(r"(^|[^-])width:", declarations) is not None
        check(f"{selector}: dichiara una larghezza", has_width, declarations)


def main():
    test_featured_cover()
    test_editor_preview()
    test_flex_images_have_a_width()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
