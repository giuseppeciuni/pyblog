#!/usr/bin/env python3
"""
Checks on the series of articles.

    python3 tests/test_series.py

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


def article(numero, serie="", part=0, tradotto=False):
    art = {"title": f"Articolo {numero}", "slug": f"articolo-{numero}",
           "content": "<p>Testo dell'articolo.</p>", "status": "published",
           "date": f"2026-01-{numero:02d}", "tags": "Prova",
           "series": serie, "series_number": part}
    if tradotto:
        art.update({"title_en": f"Article {numero}", "content_en": "<p>Text.</p>",
                    "translation_confirmed": True})
    return art


# Newest first, as the build passes them. Parts 1 and 2 are numbered, the
# third has no number and follows by date; the name is typed in two ways.
ARTICLES_FIXTURE = [
    article(5),
    article(4, "Inside the machine", 0, tradotto=True),
    article(3, "Un'altra serie", 1),
    article(2, "Inside the Machine", 1, tradotto=True),
    article(1, "Inside the Machine", 2),
]


def test_data():
    print("\ni dati dell'articolo")
    saved = article_from_data({"title": "T", "series": "  Inside the Machine ",
                                 "series_number": "3"}, "t")
    check("serie e numero vengono salvati puliti",
          saved["series"] == "Inside the Machine" and saved["series_number"] == 3)
    for dirty in ("", "abc", "-2", "0", None):
        check(f"un numero non valido ({dirty!r}) vale nessun numero",
              article_from_data({"title": "T", "series_number": dirty}, "t")["series_number"] == 0)
    check("un articolo senza serie non ne ha una",
          article_from_data({"title": "T"}, "t")["series"] == "")

    serie = collect_series(ARTICLES_FIXTURE)
    check("maiuscole diverse nel nome sono la stessa serie",
          set(serie) == {"inside-the-machine", "un-altra-serie"}, str(list(serie)))
    check("le parti numerate vanno in ordine di numero, le altre dopo per data",
          [a["slug"] for a in serie["inside-the-machine"]["articles"]]
          == ["articolo-2", "articolo-1", "articolo-4"])


def test_article():
    print("\nla pagina di una parte")
    page_html = build.generate_article_page(ARTICLES_FIXTURE[4], "it", ARTICLES_FIXTURE)
    box = page_html.split('<nav class="series-box"')[1].split("</nav>")[0]
    check("apre con il nome della serie e il posto della parte",
          '<a class="series-name" href="/series/inside-the-machine.html">' in box
          and "parte 2 di 3" in box, box[:300])
    check("elenca tutte le parti, con la corrente segnata e senza link",
          box.count("<li") == 3 and '<li aria-current="page">Articolo 1</li>' in box
          and '<a href="/posts/articolo-2.html">Articolo 2</a>' in box)
    check("il riquadro sta prima del testo",
          page_html.index("series-box") < page_html.index('class="post-content"'))
    bottom = page_html.split('class="article-nav"')[1].split("</nav>")[0]
    check("in fondo porta alla parte precedente e alla successiva della serie",
          "Parte precedente" in bottom and "/posts/articolo-2.html" in bottom
          and "Parte successiva" in bottom and "/posts/articolo-4.html" in bottom, bottom)
    before = build.generate_article_page(ARTICLES_FIXTURE[3], "it", ARTICLES_FIXTURE)
    bottom = before.split('class="article-nav"')[1].split("</nav>")[0]
    check("la prima parte non ha una precedente",
          "Parte precedente" not in bottom and "Parte successiva" in bottom)

    outside = build.generate_article_page(ARTICLES_FIXTURE[0], "it", ARTICLES_FIXTURE)
    check("un articolo fuori dalle serie non ha il riquadro", "series-box" not in outside)
    check("e naviga per data come prima", "Meno recente" in outside)
    alone = build.generate_article_page(ARTICLES_FIXTURE[2], "it", ARTICLES_FIXTURE)
    check("una serie con una sola parte online non mostra nulla", "series-box" not in alone)

    english = build.generate_article_page(ARTICLES_FIXTURE[3], "en", ARTICLES_FIXTURE)
    check("in inglese contano solo le parti tradotte",
          "part 1 of 2" in english and '/en/series/inside-the-machine.html' in english
          and "Article 4" in english and "Articolo 1" not in english)


def test_series_page():
    print("\nla pagina della serie")
    serie = collect_series(ARTICLES_FIXTURE)["inside-the-machine"]
    page_html = build.generate_series_page("inside-the-machine", serie, "it", ARTICLES_FIXTURE)
    elenco = page_html.split('class="articles-list series-list"')[1].split("</ol>")[0]
    check("ha il nome della serie nel titolo e nell'intestazione",
          "<title>Serie: Inside the Machine" in page_html
          and '<h1 class="articles-heading">Inside the Machine</h1>' in page_html)
    check("elenca le parti dalla prima all'ultima",
          elenco.index("articolo-2") < elenco.index("articolo-1") < elenco.index("articolo-4")
          and elenco.count("<li>") == 3)
    check("ha il suo indirizzo canonico",
          'rel="canonical" href="' + CONFIG["base_url"].rstrip("/")
          + '/series/inside-the-machine.html"' in page_html)
    sitemap = build.generate_sitemap(ARTICLES_FIXTURE)
    check("la sitemap la elenca in tutte e due le lingue",
          "/series/inside-the-machine.html" in sitemap
          and "/en/series/inside-the-machine.html" in sitemap)
    check("ma non la serie con una sola parte", "un-altra-serie" not in sitemap)


def test_editor():
    print("\nl'editor")
    originale = server.load_articles
    server.load_articles = lambda: ARTICLES_FIXTURE
    try:
        page_html = server.editor_page(ARTICLES_FIXTURE[4], "csrf")
    finally:
        server.load_articles = originale
    check("i campi hanno la serie e il numero dell'articolo",
          'id="series" value="Inside the Machine"' in page_html
          and 'id="series_number" value="2"' in page_html)
    check("e propone le serie che esistono gia'",
          '<option value="Un&#x27;altra serie">' in page_html
          and page_html.count('<option value="Inside the') == 1)
    script = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("il salvataggio manda serie e numero",
          "series: document.getElementById('series').value" in script
          and "series_number: document.getElementById('series_number').value" in script)


def main():
    saved_page = copy.deepcopy(CONFIG)
    try:
        CONFIG["language"] = "it"
        test_data()
        test_article()
        test_series_page()
        test_editor()
    finally:
        CONFIG.clear()
        CONFIG.update(saved_page)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
