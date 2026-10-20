#!/usr/bin/env python3
"""
Checks on the two-column layout of the public site.

    python3 tests/test_layout.py

The pages are generated in memory from articles built here, with the
configuration changed in memory only: nothing is written to posts/, to
output/ or to config.json.
"""
import copy
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build  # noqa: E402
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


def article(numero, with_cover=True, titoli=0):
    """A published article with a predictable text."""
    testo = ("<p>Primo paragrafo dell'articolo numero " + str(numero)
             + " con un <strong>grassetto</strong> e un esponente E=mc<sup>2</sup>.</p>")
    for indice in range(titoli):
        testo = testo + f"<h2>Sezione {indice + 1}</h2><p>Testo della sezione {indice + 1}.</p>"
    testo = testo + "<p>" + " ".join(["parola"] * 80) + "</p>"
    return {
        "title": f"Articolo di prova {numero}", "slug": f"articolo-di-prova-{numero}",
        "description": "", "preview": "", "content": testo,
        "tags": "Prova, Layout" if numero % 2 else "Prova",
        "image": "/media/prova.png" if with_cover else "",
        "status": "published", "custom_code_ids": [],
        "date": f"2026-0{1 + numero % 8}-1{numero % 9}T09:00:00+00:00",
        "date_modified": "2026-01-01T09:00:00+00:00",
        "title_en": f"Test article {numero}", "description_en": "", "preview_en": "",
        "content_en": "<p>English text.</p>", "translation_authorized": True,
        "translation_confirmed": True,
    }


ARTICLES_FIXTURE = sorted([article(n, with_cover=(n % 3 != 0), titoli=(4 if n == 1 else 0))
                   for n in range(1, 15)], key=lambda a: a["date"], reverse=True)


def h1(page_html):
    return re.findall(r"<h1[^>]*>(.*?)</h1>", page_html, re.DOTALL)


def test_single_h1():
    print("\nun solo titolo principale per pagina")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
    check("home: un h1, ed e' il nome del sito",
          len(h1(home)) == 1 and CONFIG["site_title"] in h1(home)[0], str(h1(home)))
    page_html = build.generate_article_page(ARTICLES_FIXTURE[0], "it", ARTICLES_FIXTURE)
    check("articolo: un h1, ed e' il titolo dell'articolo",
          len(h1(page_html)) == 1 and ARTICLES_FIXTURE[0]["title"] in h1(page_html)[0], str(h1(page_html)))
    check("articolo: il nome del sito non e' un titolo",
          '<p class="site-title">' in page_html)
    tag = build.generate_tag_page("Prova", ARTICLES_FIXTURE, "it", ARTICLES_FIXTURE)
    check("pagina tag: un h1 col nome del tag", len(h1(tag)) == 1 and "Prova" in h1(tag)[0])
    archive = build.generate_archive_page(ARTICLES_FIXTURE, "it")
    check("archivio: un h1", len(h1(archive)) == 1)


def test_two_columns():
    print("\ndue colonne")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
    check("c'e' la colonna principale", 'class="colonna-principale" id="content"' in home)
    check("c'e' la barra laterale", '<aside class="barra-laterale"' in home)
    check("la colonna viene prima della barra (sul telefono la barra va sotto)",
          home.index("colonna-principale") < home.index("barra-laterale"))
    check("la barra degli argomenti ha i conteggi",
          re.search(r'class="argomento" href="/tag/prova.html">Prova <span class="argomento-conteggio">14</span>', home)
          is not None)
    check("il menu del telefono ha il suo pulsante", 'class="menu-toggle"' in home
          and 'aria-controls="site-nav"' in home)
    page_html = build.generate_article_page(ARTICLES_FIXTURE[0], "it", ARTICLES_FIXTURE)
    check("anche l'articolo ha la barra", '<aside class="barra-laterale"' in page_html)
    check("l'articolo tiene l'id del salto al contenuto", '<article id="content" class="post">' in page_html)


def test_lines_and_previews():
    print("\nrighe degli articoli")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
    lines = re.findall(r'<article class="art-row[^"]*">.*?</article>', home, re.DOTALL)
    check("dieci articoli nella prima pagina", len(lines) == 10, str(len(lines)))
    check("il primo e' l'articolo in evidenza", 'class="art-row art-lead"' in lines[0])
    check("solo il primo", sum('art-lead' in line for line in lines) == 1)
    check("chi non ha copertina ha il riquadro col primo tag",
          any('<span class="art-tile">Prova</span>' in line for line in lines))
    estratto = re.search(r'<p class="art-excerpt">(.*?)</p>', lines[1]).group(1)
    check("l'anteprima finisce con i puntini", estratto.endswith("…"), estratto)
    # The filler words are all "parola": the last one before the dots must be
    # a whole one, not "par" or "parol".
    check("e non spezza le parole", estratto[:-1].split()[-1] == "parola", estratto[-30:])
    for testo, expected_value in (("<p>Uno due tre. Quattro</p>", "Uno due tre…"),
                          ("<p>Davvero? Sì, certo</p>", "Davvero…"),
                          ("<p>Primo, secondo; terzo</p>", "Primo…")):
        words = len(expected_value.split())
        obtained = build.excerpt_words(testo, words)
        check(f"il taglio dopo la punteggiatura non lascia «.…» ({obtained})",
              obtained == expected_value, obtained)
    check("i grassetti non lasciano spazi", "un grassetto e un esponente E=mc2" in estratto,
          estratto)
    check("i titoletti non entrano nell'anteprima",
          all("Sezione 1" not in line for line in lines))
    second = build.generate_homepage(ARTICLES_FIXTURE, "it", 2, 2)
    check("nessun articolo in evidenza dalla seconda pagina", "art-lead" not in second)


def test_pagination():
    print("\npaginazione numerata")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
    check("la pagina attuale e' segnata",
          '<span class="paginazione-numero" aria-current="page">1</span>' in home)
    check("la seconda e' un link", '<a class="paginazione-numero" href="/pagina/2.html">2</a>' in home)
    check("i numeri saltati diventano puntini",
          build.pages_to_show(5, 10) == [1, None, 4, 5, 6, None, 10])
    check("niente puntini quando non servono", build.pages_to_show(1, 3) == [1, 2, 3])


def test_table_of_contents_in_article():
    print("\nindice dell'articolo")
    long_value = next(a for a in ARTICLES_FIXTURE if a["slug"] == "articolo-di-prova-1")
    page_html = build.generate_article_page(long_value, "it", ARTICLES_FIXTURE)
    check("nella barra, ultimo riquadro", '<nav class="box box-indice"' in page_html)
    check("piegato in cima al testo per il telefono", '<details class="toc-telefono">' in page_html)
    short_value = next(a for a in ARTICLES_FIXTURE if a["slug"] == "articolo-di-prova-2")
    page_html = build.generate_article_page(short_value, "it", ARTICLES_FIXTURE)
    check("un articolo corto non ha indice", "box-indice" not in page_html and "toc-telefono" not in page_html)
    check("i correlati sono righe come in home", 'class="related-articles"' in page_html
          and '<article class="art-row">' in page_html)


def test_introduction_position():
    print("\npresentazione della home")
    vecchia = CONFIG.get("home_intro_position")
    try:
        CONFIG["home_intro_position"] = "sidebar"
        home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
        barra = home.split('<aside class="barra-laterale"', 1)[1]
        check("di serie sta nella barra", '<section class="home-intro">' in barra)
        CONFIG["home_intro_position"] = "top"
        home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
        column = home.split('<aside class="barra-laterale"', 1)[0]
        check("oppure sopra gli articoli", '<section class="home-intro">' in column)
        second = build.generate_homepage(ARTICLES_FIXTURE, "it", 2, 2)
        check("e mai dalla seconda pagina", '<section class="home-intro">' not in second)
    finally:
        CONFIG["home_intro_position"] = vecchia


def test_slots_for_code():
    print("\nspazi per annunci e widget")
    old_items = copy.deepcopy(CONFIG.get("custom_code", []))
    CONFIG["custom_code"] = [
        {"id": "a", "enabled": True, "position": "home_feed", "scope": "all", "code": "<!-- TRA-GLI-ARTICOLI -->"},
        {"id": "b", "enabled": True, "position": "sidebar", "scope": "all", "code": "<!-- NELLA-BARRA -->"},
        {"id": "c", "enabled": True, "position": "article_start", "scope": "articles", "code": "<!-- INIZIO-TESTO -->"},
        {"id": "d", "enabled": True, "position": "article_middle", "scope": "articles", "code": "<!-- META-TESTO -->"},
    ]
    try:
        home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
        lines = home.split("TRA-GLI-ARTICOLI")
        check("tra gli articoli: dopo il terzo",
          len(lines) == 2 and lines[0].count('<article class="art-row') == 3, str(len(lines)))
        check("nella barra laterale", "NELLA-BARRA" in home.split('<aside class="barra-laterale"', 1)[1])
        page_html = build.generate_article_page(ARTICLES_FIXTURE[0], "it", ARTICLES_FIXTURE)
        check("a inizio testo: dopo il titolo, prima del testo",
              page_html.index("<h1>") < page_html.index("INIZIO-TESTO") < page_html.index('class="post-content"'))
        contenuto = page_html.split('class="post-content">', 1)[1]
        check("a meta' testo: dentro il testo", "META-TESTO" in contenuto)
    finally:
        CONFIG["custom_code"] = old_items


def test_meta_text_between_two_paragraphs():
    print("\nil codice a meta' testo")
    testo = "<p>uno</p><h2>titolo</h2><p>due</p><p>tre</p><ul><li>a</li></ul><p>quattro</p>"
    result = build.insert_in_middle(testo, "<!--X-->")
    check("finisce dopo un paragrafo", re.search(r"</p><!--X-->", result) is not None, result)
    check("mai tra un titolo e il suo paragrafo", "</h2><!--X-->" not in result)
    check("mai alla fine", not result.endswith("<!--X-->"))
    check("un testo troppo corto lo riceve in fondo",
          build.insert_in_middle("<p>solo</p>", "<!--X-->") == "<p>solo</p><!--X-->")


def test_texts_in_page_language():
    print("\ntesti dell'interfaccia in inglese")
    home = build.generate_homepage(ARTICLES_FIXTURE, "en", 1, 2)
    check("il pulsante del tema", 'aria-label="Switch theme"' in home)
    check("la ricerca", 'aria-label="Search"' in home)
    check("il menu", "Menu</button>" in home or "Menu\n      </button>" in home)


def test_file_version():
    print("\nversione di CSS e JavaScript nell'indirizzo")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it", 1, 2)
    check("style.css ha la sua versione", re.search(r'href="/style\.css\?v=[0-9a-f]{10}"', home) is not None)
    check("site.js ha la sua versione", re.search(r'src="/site\.js\?v=[0-9a-f]{10}"', home) is not None)


def test_checklists():
    print("\nliste di controllo")
    css = (pathlib.Path(__file__).resolve().parent.parent / "static" / "style.css").read_text(encoding="utf-8")
    check("niente piu' ±0 e ±1", 'content:"±0"' not in css and 'content:"±1"' not in css)
    check("le caselle seguono il markup di Quill 1.3.7",
          'ul[data-checked="false"] > li::before { content:"\\2610"; }' in css
          and 'ul[data-checked="true"] > li::before { content:"\\2611"; }' in css)


def main():
    test_single_h1()
    test_two_columns()
    test_lines_and_previews()
    test_pagination()
    test_table_of_contents_in_article()
    test_introduction_position()
    test_slots_for_code()
    test_meta_text_between_two_paragraphs()
    test_texts_in_page_language()
    test_file_version()
    test_checklists()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
