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

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.articles import load_article, save_article  # noqa: E402
from core.build import absolute_image_sources, build, media_url  # noqa: E402

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


def leggi(path_value):
    return (ROOT_DIR / path_value).read_text(encoding="utf-8")


def classes_of(testo):
    """Every class attribute of a fragment, in order."""
    return re.findall(r'class="([a-z0-9 -]+)"', testo)


def test_card_parity():
    """The generator and site.js must build the same article row."""
    print("\nparita' fra le due versioni della riga di un articolo")
    home = leggi("output/index.html")
    # Up to the end of the articles section: a closing </div> alone would stop
    # inside the first row, which has divs of its own.
    lista = re.search(r'id="list-box-articles">(.*?)</section>', home, re.S)
    check("la lista degli articoli esiste", lista is not None)
    if lista is None:
        return
    # The first row is the lead one; the rows built by a search are ordinary
    # rows, so the comparison takes an ordinary one.
    line = re.search(r'<article class="art-row">.*?</article>', lista.group(1), re.S)
    check("c'e' almeno una riga normale", line is not None)
    if line is None:
        return
    server_classes = set(classes_of(line.group(0)))

    js = leggi("static/site.js")
    function = re.search(r"function rowHtml\(.*?\n  \}", js, re.S)
    check("site.js ha un solo costruttore di righe", function is not None)
    if function is None:
        return
    tag_builder = re.search(r"function tagsHtml\(.*?\n  \}", js, re.S)
    js_source = function.group(0)
    if tag_builder is not None:
        js_source = js_source + tag_builder.group(0)
    js_classes = set(classes_of(js_source))
    # These two come from the caller: the opening of the article, or the
    # snippet around the searched term.
    js_classes.add("art-excerpt")
    js_classes.add("art-snippet")
    # An article without a cover gets the tile: the server row shows one or
    # the other, site.js knows both.
    server_classes.discard("art-tile")
    server_classes.discard("art-thumb-img")
    check("site.js sa fare sia la miniatura sia il riquadro",
          "art-thumb-img" in js_classes and "art-tile" in js_classes)

    missing = server_classes - js_classes
    check("site.js costruisce ogni parte che il generatore scrive",
          len(missing) == 0, "mancano in site.js: " + str(sorted(missing)))
    check("i tag compaiono anche nei risultati di ricerca",
          "art-tags" in js_classes and "art-tag" in js_classes, str(sorted(js_classes)))

    # Order matters as much as presence: the thumbnail comes before the body,
    # and inside the body the tags come before the title.
    corpo = function.group(0)
    check("la miniatura viene prima del corpo della riga",
          corpo.index("art-thumb") < corpo.index("art-body"), corpo[:200])
    check("i tag vengono prima del titolo",
          corpo.index("tagsHtml(a)") < corpo.index("art-title"), corpo[:400])


def test_search_index():
    """The index must carry everything the browser needs to rebuild a row."""
    print("\nindice di ricerca")
    indice = json.loads(leggi("output/search-index.json"))
    check("l'indice non e' vuoto", len(indice) > 0)
    if len(indice) == 0:
        return
    js = leggi("static/site.js")
    source = ""
    for nome in ("rowHtml", "tagsHtml", "articleDate", "articleTitle",
                 "articleReading", "articleExcerpt"):
        found_one = re.search(r"function " + nome + r"\(.*?\n  \}", js, re.S)
        check(f"site.js ha {nome}", found_one is not None)
        if found_one is not None:
            source = source + found_one.group(0)
    # Every a.<field> the row builder reads must exist in the index.
    used_fields = set(re.findall(r"\ba\.([a-z_]+)", source))
    index_fields = set(indice[0].keys())
    missing = used_fields - index_fields
    check("ogni campo letto dal costruttore e' nell'indice",
          len(missing) == 0, "mancano: " + str(sorted(missing)))
    check("l'anteprima arriva gia' pronta dal server",
          all("excerpt" in item and "reading" in item for item in indice))


def test_cover_in_article():
    """The cover goes under the title and the date, never above them."""
    print("\ncopertina dentro l'articolo")
    article_list = sorted((ROOT_DIR / "output" / "posts").glob("*.html"))
    with_cover = []
    for path_value in article_list:
        testo = path_value.read_text(encoding="utf-8")
        if "article-cover" in testo:
            with_cover.append((path_value.name, testo))
    check("almeno un articolo ha la copertina in pagina", len(with_cover) > 0,
          "nessuno degli articoli di prova ha il campo image valorizzato")
    for nome, testo in with_cover:
        corpo = testo[testo.index("<h1>"):testo.index("</article>")]
        positions = {etichetta: corpo.index(etichetta)
                     for etichetta in ("<h1>", 'class="meta"', "article-cover")}
        check(f"{nome}: la copertina sta dopo titolo e data",
              positions["<h1>"] < positions['class="meta"'] < positions["article-cover"],
              str(positions))
        check(f"{nome}: la copertina e' ingrandibile", "data-zoom" in testo)


def test_zoom_closes_everywhere():
    """
    A click anywhere in the overlay must close it, the picture included.

    Excluding the picture meant that on a phone, where it fills nearly the
    whole screen, almost every tap landed on it and did nothing.
    """
    print("\nchiusura dell'ingrandimento")
    js = leggi("static/site.js")
    opening = re.search(r"function apriZoom\(.*?\n\}", js, re.S)
    check("la funzione esiste", opening is not None)
    if opening is None:
        return
    corpo = opening.group(0)
    check("un clic sullo sfondo chiude",
          "sfondo.addEventListener('click', chiudiZoom)" in corpo, corpo[-400:])
    check("nessuna eccezione per l'immagine",
          "evento.target !== grande" not in corpo, corpo[-400:])
    check("Esc chiude", "'Escape'" in corpo)
    check("il pulsante resta come scorciatoia",
          "chiudi.addEventListener('click', chiudiZoom)" in corpo)

    css = leggi("static/style.css")
    regola = re.search(r"\.zoom-picture img \{([^}]*)\}", css)
    check("l'immagine mostra il cursore di chiusura",
          regola is not None and "zoom-out" in regola.group(1), str(regola))


def test_zoom_only_in_articles():
    """
    The homepage cover must NOT be clickable to zoom.

    There it sits inside the link to the article, and a click has to mean
    "open the article": giving one region of a card a different action is a
    trap, and on a touch screen nothing hints at the difference.
    """
    print("\nlo zoom sta solo dentro gli articoli")
    for page_html in ("output/index.html", "output/en/index.html",
                   "output/archivio.html", "output/tag/ai.html"):
        testo = leggi(page_html)
        check(f"{page_html}: nessuno zoom", "data-zoom" not in testo)


def test_image_addresses():
    """
    Una copertina scritta "media/foto.png" funziona sulla homepage italiana e
    da nessun'altra parte: la home inglese sta sotto /en/, quindi il browser
    cerca /en/media/foto.png e non trova niente. Sembra un problema di
    traduzione e non lo e'. Da qui in poi un indirizzo cosi' viene letto come
    se partisse dalla radice del sito.
    """
    print("\nindirizzi delle immagini")
    check("una copertina relativa diventa assoluta",
          media_url("media/foto.png") == "/media/foto.png", media_url("media/foto.png"))
    check("il ./ davanti non sopravvive",
          media_url("./media/foto.png") == "/media/foto.png", media_url("./media/foto.png"))
    check("una gia' assoluta resta com'e'",
          media_url("/media/foto.png") == "/media/foto.png")
    check("un indirizzo di un altro sito non viene toccato",
          media_url("https://cdn.tld/a.png") == "https://cdn.tld/a.png")
    check("nemmeno uno senza protocollo",
          media_url("//cdn.tld/a.png") == "//cdn.tld/a.png")
    check("nemmeno un'immagine dentro la pagina",
          media_url("data:image/png;base64,AAA") == "data:image/png;base64,AAA")
    check("il campo vuoto resta vuoto", media_url("") == "")

    contenuto = '<p><img src="media/dentro.png"></p><p><img src="https://cdn.tld/b.png"></p>'
    fixed = absolute_image_sources(contenuto)
    check("l'immagine dentro l'articolo viene sistemata",
          'src="/media/dentro.png"' in fixed, fixed)
    check("e quella esterna no",
          'src="https://cdn.tld/b.png"' in fixed, fixed)


def main():
    # Give an article a cover so the checks have something to look at, then
    # put it back exactly as it was.
    slug = "come-un-llm-genera-testo"
    article = load_article(slug)
    if article is None:
        print("articolo di prova assente: salto")
        return
    originale = article.get("image", "")
    if originale == "":
        article["image"] = "/media/copertina-di-prova.png"
        save_article(article)
        build()
    try:
        test_card_parity()
        test_search_index()
        test_cover_in_article()
        test_zoom_closes_everywhere()
        test_zoom_only_in_articles()
        test_image_addresses()
    finally:
        if originale == "":
            article = load_article(slug)
            article["image"] = ""
            save_article(article)
            build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
