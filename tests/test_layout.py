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


def articolo(numero, con_copertina=True, titoli=0):
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
        "image": "/media/prova.png" if con_copertina else "",
        "status": "published", "custom_code_ids": [],
        "date": f"2026-0{1 + numero % 8}-1{numero % 9}T09:00:00+00:00",
        "date_modified": "2026-01-01T09:00:00+00:00",
        "title_en": f"Test article {numero}", "description_en": "", "preview_en": "",
        "content_en": "<p>English text.</p>", "translation_authorized": True,
        "translation_confirmed": True,
    }


ARTICOLI = sorted([articolo(n, con_copertina=(n % 3 != 0), titoli=(4 if n == 1 else 0))
                   for n in range(1, 15)], key=lambda a: a["date"], reverse=True)


def h1(pagina):
    return re.findall(r"<h1[^>]*>(.*?)</h1>", pagina, re.DOTALL)


def test_un_solo_h1():
    print("\nun solo titolo principale per pagina")
    home = build.generate_homepage(ARTICOLI, "it", 1, 2)
    check("home: un h1, ed e' il nome del sito",
          len(h1(home)) == 1 and CONFIG["site_title"] in h1(home)[0], str(h1(home)))
    pagina = build.generate_article_page(ARTICOLI[0], "it", ARTICOLI)
    check("articolo: un h1, ed e' il titolo dell'articolo",
          len(h1(pagina)) == 1 and ARTICOLI[0]["title"] in h1(pagina)[0], str(h1(pagina)))
    check("articolo: il nome del sito non e' un titolo",
          '<p class="site-title">' in pagina)
    tag = build.generate_tag_page("Prova", ARTICOLI, "it", ARTICOLI)
    check("pagina tag: un h1 col nome del tag", len(h1(tag)) == 1 and "Prova" in h1(tag)[0])
    archivio = build.generate_archive_page(ARTICOLI, "it")
    check("archivio: un h1", len(h1(archivio)) == 1)


def test_due_colonne():
    print("\ndue colonne")
    home = build.generate_homepage(ARTICOLI, "it", 1, 2)
    check("c'e' la colonna principale", 'class="colonna-principale" id="content"' in home)
    check("c'e' la barra laterale", '<aside class="barra-laterale"' in home)
    check("la colonna viene prima della barra (sul telefono la barra va sotto)",
          home.index("colonna-principale") < home.index("barra-laterale"))
    check("la barra degli argomenti ha i conteggi",
          re.search(r'class="argomento" href="/tag/prova.html">Prova <span class="argomento-conteggio">14</span>', home)
          is not None)
    check("il menu del telefono ha il suo pulsante", 'class="menu-toggle"' in home
          and 'aria-controls="site-nav"' in home)
    pagina = build.generate_article_page(ARTICOLI[0], "it", ARTICOLI)
    check("anche l'articolo ha la barra", '<aside class="barra-laterale"' in pagina)
    check("l'articolo tiene l'id del salto al contenuto", '<article id="content" class="post">' in pagina)


def test_righe_e_anteprime():
    print("\nrighe degli articoli")
    home = build.generate_homepage(ARTICOLI, "it", 1, 2)
    righe = re.findall(r'<article class="art-row[^"]*">.*?</article>', home, re.DOTALL)
    check("dieci articoli nella prima pagina", len(righe) == 10, str(len(righe)))
    check("il primo e' l'articolo in evidenza", 'class="art-row art-lead"' in righe[0])
    check("solo il primo", sum('art-lead' in riga for riga in righe) == 1)
    check("chi non ha copertina ha il riquadro col primo tag",
          any('<span class="art-tile">Prova</span>' in riga for riga in righe))
    estratto = re.search(r'<p class="art-excerpt">(.*?)</p>', righe[1]).group(1)
    check("l'anteprima finisce con i puntini", estratto.endswith("…"), estratto)
    # The filler words are all "parola": the last one before the dots must be
    # a whole one, not "par" or "parol".
    check("e non spezza le parole", estratto[:-1].split()[-1] == "parola", estratto[-30:])
    for testo, atteso in (("<p>Uno due tre. Quattro</p>", "Uno due tre…"),
                          ("<p>Davvero? Sì, certo</p>", "Davvero…"),
                          ("<p>Primo, secondo; terzo</p>", "Primo…")):
        parole = len(atteso.split())
        ottenuto = build.excerpt_words(testo, parole)
        check(f"il taglio dopo la punteggiatura non lascia «.…» ({ottenuto})",
              ottenuto == atteso, ottenuto)
    check("i grassetti non lasciano spazi", "un grassetto e un esponente E=mc2" in estratto,
          estratto)
    check("i titoletti non entrano nell'anteprima",
          all("Sezione 1" not in riga for riga in righe))
    seconda = build.generate_homepage(ARTICOLI, "it", 2, 2)
    check("nessun articolo in evidenza dalla seconda pagina", "art-lead" not in seconda)


def test_paginazione():
    print("\npaginazione numerata")
    home = build.generate_homepage(ARTICOLI, "it", 1, 2)
    check("la pagina attuale e' segnata",
          '<span class="paginazione-numero" aria-current="page">1</span>' in home)
    check("la seconda e' un link", '<a class="paginazione-numero" href="/pagina/2.html">2</a>' in home)
    check("i numeri saltati diventano puntini",
          build.pages_to_show(5, 10) == [1, None, 4, 5, 6, None, 10])
    check("niente puntini quando non servono", build.pages_to_show(1, 3) == [1, 2, 3])


def test_indice_nell_articolo():
    print("\nindice dell'articolo")
    lungo = next(a for a in ARTICOLI if a["slug"] == "articolo-di-prova-1")
    pagina = build.generate_article_page(lungo, "it", ARTICOLI)
    check("nella barra, ultimo riquadro", '<nav class="box box-indice"' in pagina)
    check("piegato in cima al testo per il telefono", '<details class="toc-telefono">' in pagina)
    corto = next(a for a in ARTICOLI if a["slug"] == "articolo-di-prova-2")
    pagina = build.generate_article_page(corto, "it", ARTICOLI)
    check("un articolo corto non ha indice", "box-indice" not in pagina and "toc-telefono" not in pagina)
    check("i correlati sono righe come in home", 'class="related-articles"' in pagina
          and '<article class="art-row">' in pagina)


def test_posizione_della_presentazione():
    print("\npresentazione della home")
    vecchia = CONFIG.get("home_intro_position")
    try:
        CONFIG["home_intro_position"] = "sidebar"
        home = build.generate_homepage(ARTICOLI, "it", 1, 2)
        barra = home.split('<aside class="barra-laterale"', 1)[1]
        check("di serie sta nella barra", '<section class="home-intro">' in barra)
        CONFIG["home_intro_position"] = "top"
        home = build.generate_homepage(ARTICOLI, "it", 1, 2)
        colonna = home.split('<aside class="barra-laterale"', 1)[0]
        check("oppure sopra gli articoli", '<section class="home-intro">' in colonna)
        seconda = build.generate_homepage(ARTICOLI, "it", 2, 2)
        check("e mai dalla seconda pagina", '<section class="home-intro">' not in seconda)
    finally:
        CONFIG["home_intro_position"] = vecchia


def test_spazi_per_i_codici():
    print("\nspazi per annunci e widget")
    vecchi = copy.deepcopy(CONFIG.get("custom_code", []))
    CONFIG["custom_code"] = [
        {"id": "a", "enabled": True, "position": "home_feed", "scope": "all", "code": "<!-- TRA-GLI-ARTICOLI -->"},
        {"id": "b", "enabled": True, "position": "sidebar", "scope": "all", "code": "<!-- NELLA-BARRA -->"},
        {"id": "c", "enabled": True, "position": "article_start", "scope": "articles", "code": "<!-- INIZIO-TESTO -->"},
        {"id": "d", "enabled": True, "position": "article_middle", "scope": "articles", "code": "<!-- META-TESTO -->"},
    ]
    try:
        home = build.generate_homepage(ARTICOLI, "it", 1, 2)
        righe = home.split("TRA-GLI-ARTICOLI")
        check("tra gli articoli: dopo il terzo",
          len(righe) == 2 and righe[0].count('<article class="art-row') == 3, str(len(righe)))
        check("nella barra laterale", "NELLA-BARRA" in home.split('<aside class="barra-laterale"', 1)[1])
        pagina = build.generate_article_page(ARTICOLI[0], "it", ARTICOLI)
        check("a inizio testo: dopo il titolo, prima del testo",
              pagina.index("<h1>") < pagina.index("INIZIO-TESTO") < pagina.index('class="post-content"'))
        contenuto = pagina.split('class="post-content">', 1)[1]
        check("a meta' testo: dentro il testo", "META-TESTO" in contenuto)
    finally:
        CONFIG["custom_code"] = vecchi


def test_meta_testo_tra_due_paragrafi():
    print("\nil codice a meta' testo")
    testo = "<p>uno</p><h2>titolo</h2><p>due</p><p>tre</p><ul><li>a</li></ul><p>quattro</p>"
    risultato = build.insert_in_middle(testo, "<!--X-->")
    check("finisce dopo un paragrafo", re.search(r"</p><!--X-->", risultato) is not None, risultato)
    check("mai tra un titolo e il suo paragrafo", "</h2><!--X-->" not in risultato)
    check("mai alla fine", not risultato.endswith("<!--X-->"))
    check("un testo troppo corto lo riceve in fondo",
          build.insert_in_middle("<p>solo</p>", "<!--X-->") == "<p>solo</p><!--X-->")


def test_testi_nella_lingua_della_pagina():
    print("\ntesti dell'interfaccia in inglese")
    home = build.generate_homepage(ARTICOLI, "en", 1, 2)
    check("il pulsante del tema", 'aria-label="Switch theme"' in home)
    check("la ricerca", 'aria-label="Search"' in home)
    check("il menu", "Menu</button>" in home or "Menu\n      </button>" in home)


def test_versione_dei_file():
    print("\nversione di CSS e JavaScript nell'indirizzo")
    home = build.generate_homepage(ARTICOLI, "it", 1, 2)
    check("style.css ha la sua versione", re.search(r'href="/style\.css\?v=[0-9a-f]{10}"', home) is not None)
    check("site.js ha la sua versione", re.search(r'src="/site\.js\?v=[0-9a-f]{10}"', home) is not None)


def test_liste_di_controllo():
    print("\nliste di controllo")
    css = (pathlib.Path(__file__).resolve().parent.parent / "static" / "style.css").read_text(encoding="utf-8")
    check("niente piu' ±0 e ±1", 'content:"±0"' not in css and 'content:"±1"' not in css)
    check("le caselle seguono il markup di Quill 1.3.7",
          'ul[data-checked="false"] > li::before { content:"\\2610"; }' in css
          and 'ul[data-checked="true"] > li::before { content:"\\2611"; }' in css)


def main():
    test_un_solo_h1()
    test_due_colonne()
    test_righe_e_anteprime()
    test_paginazione()
    test_indice_nell_articolo()
    test_posizione_della_presentazione()
    test_spazi_per_i_codici()
    test_meta_testo_tra_due_paragrafi()
    test_testi_nella_lingua_della_pagina()
    test_versione_dei_file()
    test_liste_di_controllo()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
