#!/usr/bin/env python3
"""
Checks on the series of articles.

    python3 tests/test_serie.py

An article can be a part of a series: it then opens with the name of the
series and the list of its parts, leads to the part before and after, and
the series has a page of its own. Nothing is written to disk, and the
configuration is put back as it was at the end.
"""
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.articles import article_from_data, collect_series  # noqa: E402
from core.config import CONFIG  # noqa: E402

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


def articolo(numero, serie="", parte=0, tradotto=False):
    art = {"title": f"Articolo {numero}", "slug": f"articolo-{numero}",
           "content": "<p>Testo dell'articolo.</p>", "status": "published",
           "date": f"2026-01-{numero:02d}", "tags": "Prova",
           "series": serie, "series_number": parte}
    if tradotto:
        art.update({"title_en": f"Article {numero}", "content_en": "<p>Text.</p>",
                    "translation_confirmed": True})
    return art


# Newest first, as the build passes them. Parts 1 and 2 are numbered, the
# third has no number and follows by date; the name is typed in two ways.
ARTICOLI = [
    articolo(5),
    articolo(4, "Inside the machine", 0, tradotto=True),
    articolo(3, "Un'altra serie", 1),
    articolo(2, "Inside the Machine", 1, tradotto=True),
    articolo(1, "Inside the Machine", 2),
]


def test_dati():
    print("\ni dati dell'articolo")
    salvato = article_from_data({"title": "T", "series": "  Inside the Machine ",
                                 "series_number": "3"}, "t")
    check("serie e numero vengono salvati puliti",
          salvato["series"] == "Inside the Machine" and salvato["series_number"] == 3)
    for sporco in ("", "abc", "-2", "0", None):
        check(f"un numero non valido ({sporco!r}) vale nessun numero",
              article_from_data({"title": "T", "series_number": sporco}, "t")["series_number"] == 0)
    check("un articolo senza serie non ne ha una",
          article_from_data({"title": "T"}, "t")["series"] == "")

    serie = collect_series(ARTICOLI)
    check("maiuscole diverse nel nome sono la stessa serie",
          set(serie) == {"inside-the-machine", "un-altra-serie"}, str(list(serie)))
    check("le parti numerate vanno in ordine di numero, le altre dopo per data",
          [a["slug"] for a in serie["inside-the-machine"]["articles"]]
          == ["articolo-2", "articolo-1", "articolo-4"])


def test_articolo():
    print("\nla pagina di una parte")
    pagina = build.generate_article_page(ARTICOLI[4], "it", ARTICOLI)
    riquadro = pagina.split('<nav class="serie-box"')[1].split("</nav>")[0]
    check("apre con il nome della serie e il posto della parte",
          '<a class="serie-nome" href="/serie/inside-the-machine.html">' in riquadro
          and "parte 2 di 3" in riquadro, riquadro[:300])
    check("elenca tutte le parti, con la corrente segnata e senza link",
          riquadro.count("<li") == 3 and '<li aria-current="page">Articolo 1</li>' in riquadro
          and '<a href="/posts/articolo-2.html">Articolo 2</a>' in riquadro)
    check("il riquadro sta prima del testo",
          pagina.index("serie-box") < pagina.index('class="post-content"'))
    fondo = pagina.split('class="article-nav"')[1].split("</nav>")[0]
    check("in fondo porta alla parte precedente e alla successiva della serie",
          "Parte precedente" in fondo and "/posts/articolo-2.html" in fondo
          and "Parte successiva" in fondo and "/posts/articolo-4.html" in fondo, fondo)
    prima = build.generate_article_page(ARTICOLI[3], "it", ARTICOLI)
    fondo = prima.split('class="article-nav"')[1].split("</nav>")[0]
    check("la prima parte non ha una precedente",
          "Parte precedente" not in fondo and "Parte successiva" in fondo)

    fuori = build.generate_article_page(ARTICOLI[0], "it", ARTICOLI)
    check("un articolo fuori dalle serie non ha il riquadro", "serie-box" not in fuori)
    check("e naviga per data come prima", "Meno recente" in fuori)
    sola = build.generate_article_page(ARTICOLI[2], "it", ARTICOLI)
    check("una serie con una sola parte online non mostra nulla", "serie-box" not in sola)

    inglese = build.generate_article_page(ARTICOLI[3], "en", ARTICOLI)
    check("in inglese contano solo le parti tradotte",
          "part 1 of 2" in inglese and '/en/serie/inside-the-machine.html' in inglese
          and "Article 4" in inglese and "Articolo 1" not in inglese)


def test_pagina_serie():
    print("\nla pagina della serie")
    serie = collect_series(ARTICOLI)["inside-the-machine"]
    pagina = build.generate_series_page("inside-the-machine", serie, "it", ARTICOLI)
    elenco = pagina.split('class="articles-list serie-elenco"')[1].split("</ol>")[0]
    check("ha il nome della serie nel titolo e nell'intestazione",
          "<title>Serie: Inside the Machine" in pagina
          and '<h1 class="articles-heading">Inside the Machine</h1>' in pagina)
    check("elenca le parti dalla prima all'ultima",
          elenco.index("articolo-2") < elenco.index("articolo-1") < elenco.index("articolo-4")
          and elenco.count("<li>") == 3)
    check("ha il suo indirizzo canonico",
          'rel="canonical" href="' + CONFIG["base_url"].rstrip("/")
          + '/serie/inside-the-machine.html"' in pagina)
    sitemap = build.generate_sitemap(ARTICOLI)
    check("la sitemap la elenca in tutte e due le lingue",
          "/serie/inside-the-machine.html" in sitemap
          and "/en/serie/inside-the-machine.html" in sitemap)
    check("ma non la serie con una sola parte", "un-altra-serie" not in sitemap)


def test_editor():
    print("\nl'editor")
    originale = server.load_articles
    server.load_articles = lambda: ARTICOLI
    try:
        pagina = server.editor_page(ARTICOLI[4], "csrf")
    finally:
        server.load_articles = originale
    check("i campi hanno la serie e il numero dell'articolo",
          'id="series" value="Inside the Machine"' in pagina
          and 'id="series_number" value="2"' in pagina)
    check("e propone le serie che esistono gia'",
          '<option value="Un&#x27;altra serie">' in pagina
          and pagina.count('<option value="Inside the') == 1)
    script = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("il salvataggio manda serie e numero",
          "series: document.getElementById('series').value" in script
          and "series_number: document.getElementById('series_number').value" in script)


def main():
    salvata = copy.deepcopy(CONFIG)
    try:
        CONFIG["language"] = "it"
        test_dati()
        test_articolo()
        test_pagina_serie()
        test_editor()
    finally:
        CONFIG.clear()
        CONFIG.update(salvata)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
