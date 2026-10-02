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

RADICE = pathlib.Path(__file__).resolve().parent.parent
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


def regola(testo, selettore):
    """
    The declarations of the first rule with this EXACT selector.

    Anchored at the start of a line: without that, looking for "img" also
    matches ".card-page img", and the check reads the wrong rule.
    """
    trovata = re.search(r"(?m)^" + re.escape(selettore) + r"\s*\{([^}]*)\}", testo)
    if trovata is None:
        return None
    return " ".join(trovata.group(1).split())


def test_copertina_in_evidenza():
    """The cover thumbnail must be immune to the size of the uploaded file."""
    # The highlighted block became the lead row of the list in the two-column
    # layout: every row, the lead included, uses this thumbnail.
    print("\nminiatura delle righe degli articoli (style.css)")
    css = (RADICE / "static" / "style.css").read_text(encoding="utf-8")
    dichiarazioni = regola(css, ".art-thumb-img, .art-tile")
    check("la regola esiste", dichiarazioni is not None)
    if dichiarazioni is None:
        return

    check("la larghezza e' dichiarata, non lasciata al flex-basis",
          re.search(r"(^|[^-])width:", dichiarazioni) is not None, dichiarazioni)
    check("min-width:0 disattiva la dimensione minima automatica",
          "min-width:0" in dichiarazioni.replace(" ", ""), dichiarazioni)
    check("il tetto non e' affidato a max-width, che la regola globale vince",
          "max-width" not in dichiarazioni, dichiarazioni)
    check("il ritaglio e' impostato", "object-fit:cover" in dichiarazioni.replace(" ", ""))

    globale = regola(css, "img")
    check("la regola globale sulle immagini e' ancora !important "
          "(e' il motivo per cui non si usa max-width qui)",
          globale is not None and "!important" in globale, str(globale))


def test_anteprima_editor():
    """The editor thumbnail has the same trap on the vertical axis."""
    print("\nminiatura della copertina nell'editor (admin.css)")
    css = (RADICE / "static" / "admin.css").read_text(encoding="utf-8")
    dichiarazioni = regola(css, ".copertina-anteprima")
    check("la regola esiste", dichiarazioni is not None)
    if dichiarazioni is None:
        return
    compatto = dichiarazioni.replace(" ", "")
    check("min-width:0 presente", "min-width:0" in compatto, dichiarazioni)
    check("min-height:0 presente", "min-height:0" in compatto, dichiarazioni)
    check("ha un tetto di larghezza", "max-width" in compatto, dichiarazioni)


def test_immagini_flex_hanno_una_larghezza():
    """
    Every image that is a flex item must declare a width.

    This is the general form of the bug above: without one, the automatic
    minimum size is the size of the file, and a large upload breaks the
    layout of whatever sits next to it.
    """
    print("\nogni immagine dentro un contenitore flex ha una larghezza")
    css = (RADICE / "static" / "style.css").read_text(encoding="utf-8")
    # The images this project places inside a flex row or column.
    for selettore in (".art-thumb-img, .art-tile", ".author-box-photo", ".profilo-foto"):
        dichiarazioni = regola(css, selettore)
        if dichiarazioni is None:
            check(f"{selettore}: la regola esiste", False)
            continue
        ha_larghezza = re.search(r"(^|[^-])width:", dichiarazioni) is not None
        check(f"{selettore}: dichiara una larghezza", ha_larghezza, dichiarazioni)


def main():
    test_copertina_in_evidenza()
    test_anteprima_editor()
    test_immagini_flex_hanno_una_larghezza()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
