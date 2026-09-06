#!/usr/bin/env python3
"""
Checks on the generated public pages.

    python3 tests/test_public_pages.py

The one that matters most here is the parity between the two renderers of an
article card. The generator writes the cards of the homepage, and site.js
rewrites them from the search index the moment someone types in the search
box. They are two pieces of code producing the same markup, so they drift:
the first time thumbnails were added to the cards, a search silently stripped
every one of them off the page.
"""
import json
import pathlib
import re
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from core.articles import load_article, save_article  # noqa: E402
from core.build import build  # noqa: E402

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


def leggi(percorso):
    return (RADICE / percorso).read_text(encoding="utf-8")


def classi_di(testo):
    """Every class attribute of a fragment, in order."""
    return re.findall(r'class="([a-z0-9 -]+)"', testo)


def test_parita_delle_card():
    """The generator and site.js must build the same card."""
    print("\nparita' fra le due versioni della card")
    home = leggi("output/index.html")
    lista = re.search(r'id="lista-articoli">(.*?)\n    </div>\n', home, re.S)
    check("la lista degli articoli esiste", lista is not None)
    if lista is None:
        return
    card = re.search(r'<a class="article-card".*?</a>', lista.group(1), re.S)
    check("c'e' almeno una card", card is not None)
    if card is None:
        return
    classi_server = set(classi_di(card.group(0)))

    js = leggi("static/site.js")
    funzione = re.search(r"function cardHtml\(.*?\n  \}", js, re.S)
    check("site.js ha un solo costruttore di card", funzione is not None)
    if funzione is None:
        return
    classi_js = set(classi_di(funzione.group(0)))
    # These two come from the caller: the plain list passes an excerpt, the
    # search results pass a snippet.
    classi_js.add("card-excerpt")
    classi_js.add("card-snippet")

    mancanti = classi_server - classi_js
    check("site.js costruisce ogni parte che il generatore scrive",
          len(mancanti) == 0, "mancano in site.js: " + str(sorted(mancanti)))

    # Position matters as much as presence: the thumbnail goes between the
    # opening link and the text block, on both sides.
    ritorno = re.search(r"return '<a class=\"article-card\".*?';", funzione.group(0), re.S)
    check("la miniatura e' concatenata prima del corpo della card",
          ritorno is not None
          and ritorno.group(0).index("copertina") < ritorno.group(0).index("card-corpo"),
          str(ritorno.group(0)) if ritorno else "")


def test_indice_di_ricerca():
    """The index must carry everything the browser needs to rebuild a card."""
    print("\nindice di ricerca")
    indice = json.loads(leggi("output/search-index.json"))
    check("l'indice non e' vuoto", len(indice) > 0)
    if len(indice) == 0:
        return
    js = leggi("static/site.js")
    funzione = re.search(r"function cardHtml\(.*?\n  \}", js, re.S).group(0)
    # Every a.<field> the card builder reads must exist in the index.
    campi_usati = set(re.findall(r"\ba\.([a-z_]+)", funzione))
    campi_indice = set(indice[0].keys())
    mancanti = campi_usati - campi_indice
    check("ogni campo letto dal costruttore e' nell'indice",
          len(mancanti) == 0, "mancano: " + str(sorted(mancanti)))


def test_copertina_nell_articolo():
    """The cover goes under the title and the date, never above them."""
    print("\ncopertina dentro l'articolo")
    articoli = sorted((RADICE / "output" / "posts").glob("*.html"))
    con_copertina = []
    for percorso in articoli:
        testo = percorso.read_text(encoding="utf-8")
        if "articolo-copertina" in testo:
            con_copertina.append((percorso.name, testo))
    check("almeno un articolo ha la copertina in pagina", len(con_copertina) > 0,
          "nessuno degli articoli di prova ha il campo image valorizzato")
    for nome, testo in con_copertina:
        corpo = testo[testo.index("<h1>"):testo.index("</article>")]
        posizioni = {etichetta: corpo.index(etichetta)
                     for etichetta in ("<h1>", 'class="meta"', "articolo-copertina")}
        check(f"{nome}: la copertina sta dopo titolo e data",
              posizioni["<h1>"] < posizioni['class="meta"'] < posizioni["articolo-copertina"],
              str(posizioni))
        check(f"{nome}: la copertina e' ingrandibile", "data-zoom" in testo)


def test_zoom_solo_negli_articoli():
    """
    The homepage cover must NOT be clickable to zoom.

    There it sits inside the link to the article, and a click has to mean
    "open the article": giving one region of a card a different action is a
    trap, and on a touch screen nothing hints at the difference.
    """
    print("\nlo zoom sta solo dentro gli articoli")
    for pagina in ("output/index.html", "output/en/index.html",
                   "output/archivio.html", "output/tag/ai.html"):
        testo = leggi(pagina)
        check(f"{pagina}: nessuno zoom", "data-zoom" not in testo)


def main():
    # Give an article a cover so the checks have something to look at, then
    # put it back exactly as it was.
    slug = "come-un-llm-genera-testo"
    articolo = load_article(slug)
    if articolo is None:
        print("articolo di prova assente: salto")
        return
    originale = articolo.get("image", "")
    if originale == "":
        articolo["image"] = "/media/copertina-di-prova.png"
        save_article(articolo)
        build()
    try:
        test_parita_delle_card()
        test_indice_di_ricerca()
        test_copertina_nell_articolo()
        test_zoom_solo_negli_articoli()
    finally:
        if originale == "":
            articolo = load_article(slug)
            articolo["image"] = ""
            save_article(articolo)
            build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
