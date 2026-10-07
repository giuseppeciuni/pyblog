#!/usr/bin/env python3
"""
Checks on the biography and the projects of the homepage.

    python3 tests/test_biografia_progetti.py

Both are off until the author turns them on, and each can sit in the
sidebar, above the articles or below them. The pages are parsed by position
in the HTML, and the configuration is put back as it was at the end.
"""
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.config import CONFIG, CONFIG_DEFAULT  # noqa: E402

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


def articolo(numero):
    return {"title": f"Articolo {numero}", "slug": f"articolo-{numero}",
            "content": "<p>Testo dell'articolo.</p>", "status": "published",
            "date": f"2026-01-{numero:02d}", "tags": "Prova"}


ARTICOLI = [articolo(n) for n in range(1, 4)]
BIO = "<p>Sono Maria, ingegnera del software. " + "Scrivo di sistemi distribuiti. " * 20 + "</p>"


def imposta(bio_posizione="top", progetti_posizione="bottom", bio_attiva=True,
            progetti_attivi=True):
    CONFIG["language"] = "it"
    CONFIG["biography"] = {"enabled": bio_attiva, "position": bio_posizione,
                           "photo": "/media/io.jpg", "content": BIO,
                           "content_en": "<p>I am Maria, a software engineer.</p>"}
    CONFIG["projects"] = {"enabled": progetti_attivi, "position": progetti_posizione, "items": [
        {"name": "Alfa", "description": "Il <b>primo</b>", "description_en": "The first",
         "url": "https://example.org/alfa", "image": "/media/alfa.png", "visible": True},
        {"name": "Nascosto", "description": "No", "url": "", "image": "", "visible": False},
        {"name": "Beta", "description": "Il secondo", "url": "javascript:alert(1)",
         "image": "", "visible": True},
        {"name": "", "description": "Senza nome", "visible": True},
    ]}


def test_predefiniti():
    print("\nvalori predefiniti")
    check("biografia spenta", CONFIG_DEFAULT["biography"]["enabled"] is False)
    check("progetti spenti", CONFIG_DEFAULT["projects"]["enabled"] is False)
    titoli = [card["title"] for card in CONFIG_DEFAULT["home_cards"]]
    check("niente card Biografia e Progetti tra quelle di partenza",
          "Biografia" not in titoli and "Progetti" not in titoli, str(titoli))
    CONFIG["biography"] = copy.deepcopy(CONFIG_DEFAULT["biography"])
    CONFIG["projects"] = copy.deepcopy(CONFIG_DEFAULT["projects"])
    home = build.generate_homepage(ARTICOLI, "it")
    check("spente, la home non le mostra",
          "box-biografia" not in home and "home-sezione" not in home and "box-progetti" not in home)


def test_impostazioni_sporche():
    print("\nimpostazioni salvate male")
    bio = build.biography_settings({"biography": {"enabled": "si", "position": "altrove",
                                                  "content": 3}})
    check("un valore non booleano non accende, una posizione ignota torna predefinita",
          bio["enabled"] is False and bio["position"] == "sidebar" and bio["content"] == "")
    progetti = build.projects_settings({"projects": {"items": ["x", {"name": 5}]}})
    check("le voci che non sono progetti si scartano, i testi si ripuliscono",
          len(progetti["items"]) == 1 and progetti["items"][0]["name"] == "")
    check("una lista che non è una lista non fa danni",
          build.projects_settings({"projects": {"items": "x"}})["items"] == [])


def test_posizioni():
    print("\nposizioni nella home")
    imposta("top", "bottom")
    home = build.generate_homepage(ARTICOLI, "it")
    i_bio = home.find("home-biografia")
    i_art = home.find('id="articles"')
    i_pro = home.find("home-progetti")
    check("biografia sopra gli articoli, progetti sotto", 0 < i_bio < i_art < i_pro)
    check("la biografia porta alla sua pagina",
          'href="/pagine/biografia.html"' in home)

    imposta("bottom", "top")
    home = build.generate_homepage(ARTICOLI, "it")
    check("e al contrario", 0 < home.find("home-progetti") < home.find('id="articles"')
          < home.find("home-biografia"))

    imposta("sidebar", "sidebar")
    home = build.generate_homepage(ARTICOLI, "it")
    barra = home[home.find("<aside"):]
    check("nella barra laterale, fuori dalla colonna",
          "box-biografia" in barra and "box-progetti" in barra and "home-sezione" not in home)
    check("in barra: presentazione, biografia, progetti, esplora, nell'ordine",
          barra.find("box-intro") < barra.find("box-biografia") < barra.find("box-progetti")
          < barra.find("box-segui"))

    imposta("top", "top")
    pagina_due = build.generate_homepage(ARTICOLI, "it", page=2, totale_pagine=2)
    check("dalla seconda pagina in poi non si ripetono",
          "home-biografia" not in pagina_due and "home-progetti" not in pagina_due)


def test_progetti():
    print("\nprogetti")
    imposta("top", "top")
    home = build.generate_homepage(ARTICOLI, "it")
    sezione = home[home.find("home-progetti"):home.find('id="articles"')]
    check("il nascosto e quello senza nome restano fuori",
          "Nascosto" not in sezione and "Senza nome" not in sezione)
    check("nell'ordine della lista", sezione.find("Alfa") < sezione.find("Beta"))
    check("un link javascript: non diventa un link",
          "javascript:" not in home and ">Beta</h3>" in sezione.replace("\n", ""), sezione[:400])
    check("il testo viene escapato", "Il &lt;b&gt;primo&lt;/b&gt;" in sezione)
    check("l'immagine c'è solo dove è stata messa", sezione.count("progetto-immagine") == 1)
    inglese = build.generate_homepage(ARTICOLI, "en")
    check("in inglese la descrizione tradotta, e Beta senza traduzione in italiano",
          "The first" in inglese and "Il secondo" in inglese)
    check("in inglese il titolo della sezione è Projects", ">Projects</h2>" in inglese)


def test_pagina_biografia():
    print("\npagina della biografia")
    imposta()
    pagina = build.generate_biography_page("it", ARTICOLI)
    check("ha tutto il testo, non l'estratto", BIO in pagina)
    check("ha la foto e il canonical giusto",
          'class="bio-pagina-foto" src="/media/io.jpg"' in pagina
          and 'rel="canonical" href="' + CONFIG["base_url"] + '/pagine/biografia.html"' in pagina)
    inglese = build.generate_biography_page("en", ARTICOLI)
    check("la versione inglese usa la traduzione", "I am Maria" in inglese and BIO not in inglese)
    CONFIG["biography"]["content_en"] = ""
    check("senza traduzione mostra la biografia in italiano",
          BIO in build.generate_biography_page("en", ARTICOLI))
    sitemap = build.generate_sitemap(ARTICOLI)
    check("la sitemap la elenca in entrambe le lingue",
          sitemap.count("/pagine/biografia.html") == 2)
    CONFIG["biography"]["content"] = "<p><br></p>"
    check("senza testo non va online", not build.biography_published())
    check("e la sitemap non la elenca",
          "/pagine/biografia.html" not in build.generate_sitemap(ARTICOLI))


def test_menu_titoli_anteprime():
    print("\nmenu, titoli e anteprime social")
    imposta()
    CONFIG["base_url"] = "https://esempio.it"
    CONFIG["site_title"] = "Il mio sito"
    home = build.generate_homepage(ARTICOLI, "it")
    check("con la biografia online il menu ha Chi sono",
          '<a href="/pagine/biografia.html">Chi sono</a>' in home.split("</nav>")[0])
    check("in inglese porta alla pagina inglese",
          '<a href="/en/pagine/biografia.html">About me</a>'
          in build.generate_homepage(ARTICOLI, "en").split("</nav>")[0])
    CONFIG["biography"]["enabled"] = False
    check("spenta, il menu non la elenca",
          "Chi sono" not in build.generate_homepage(ARTICOLI, "it").split("</nav>")[0])

    articolo_copertina = dict(articolo(1), image="media/copertina.png")
    pagina = build.generate_article_page(articolo_copertina, "it", ARTICOLI)
    check("l'immagine dell'anteprima social ha l'indirizzo completo",
          '<meta property="og:image" content="https://esempio.it/media/copertina.png">' in pagina,
          pagina.split("og:image")[1][:120])
    check("anche nei dati per i motori di ricerca",
          '"image": "https://esempio.it/media/copertina.png"' in pagina)
    esterna = dict(articolo(1), image="https://altrove.org/foto.png")
    check("un indirizzo gia' completo resta com'e'",
          'og:image" content="https://altrove.org/foto.png"'
          in build.generate_article_page(esterna, "it", ARTICOLI))
    check("il titolo della pagina finisce con il nome del sito",
          "<title>Articolo 1 &middot; Il mio sito</title>" in pagina)

    CONFIG["site_title"] = ""
    CONFIG["subtitle"] = "Note tecniche"
    pagina = build.generate_article_page(articolo_copertina, "it", ARTICOLI)
    check("senza nome del sito il titolo non finisce con un punto",
          "<title>Articolo 1</title>" in pagina, pagina.split("<title>")[1][:60])
    check("e non c'e' un nome vuoto per le anteprime", "og:site_name" not in pagina)
    check("la home usa il solo sottotitolo",
          "<title>Note tecniche</title>" in build.generate_homepage(ARTICOLI, "it"))


def test_lavora_con_me():
    print("\nlavora con me")
    imposta()
    CONFIG["work_with_me"] = {"enabled": True, "url": "/pagine/lavora-con-me.html",
                              "label": "", "label_en": "Hire me", "text": "Parliamone <ora>",
                              "text_en": ""}
    home = build.generate_homepage(ARTICOLI, "it")
    menu = home.split("</nav>")[0]
    check("il menu chiude con il pulsante, con la scritta predefinita",
          '<a class="nav-lavoro" href="/pagine/lavora-con-me.html">Lavora con me</a>' in menu
          and menu.index("nav-lavoro") > menu.index("Chi sono"), menu[-400:])
    pagina = build.generate_article_page(articolo(1), "it", ARTICOLI)
    invito = pagina.split('<aside class="invito-lavoro">')[1].split("</aside>")[0]
    check("a fine articolo c'e' l'invito, con la frase scelta e senza far passare HTML",
          "Parliamone &lt;ora&gt;" in invito and 'href="/pagine/lavora-con-me.html"' in invito
          and pagina.index("invito-lavoro") > pagina.index('class="post-content"'))
    inglese = build.generate_homepage(ARTICOLI, "en").split("</nav>")[0]
    check("in inglese porta alla pagina inglese, con la sua scritta",
          '<a class="nav-lavoro" href="/en/pagine/lavora-con-me.html">Hire me</a>' in inglese)
    CONFIG["work_with_me"]["url"] = "mailto:io@esempio.it"
    check("un indirizzo email resta com'e' in tutte le lingue",
          'href="mailto:io@esempio.it"' in build.generate_homepage(ARTICOLI, "en"))
    CONFIG["work_with_me"]["url"] = "javascript:alert(1)"
    check("un indirizzo non valido non mostra nulla",
          "nav-lavoro" not in build.generate_homepage(ARTICOLI, "it"))
    CONFIG["work_with_me"] = {"enabled": False, "url": "/pagine/x.html"}
    check("spento, niente pulsante e niente invito",
          "nav-lavoro" not in build.generate_homepage(ARTICOLI, "it")
          and "invito-lavoro" not in build.generate_article_page(articolo(1), "it", ARTICOLI))
    CONFIG["work_with_me"] = "sporco"
    check("un valore sporco vale spento", build.work_link("it") is None)


def test_card_omonima():
    print("\ncard con lo stesso nome")
    imposta()
    CONFIG["home_cards_enabled"] = True
    CONFIG["home_cards"] = [{"active": True, "title": "Biografia", "content": "<p>Vecchia</p>"},
                            {"active": True, "title": "Contatti", "content": "<p>Scrivimi</p>"}]
    titoli = [card["title"] for card in build.published_home_cards()]
    check("con la biografia accesa, la vecchia card Biografia non scrive sopra la sua pagina",
          titoli == ["Contatti"], str(titoli))
    CONFIG["biography"]["enabled"] = False
    titoli = [card["title"] for card in build.published_home_cards()]
    check("con la biografia spenta, la card torna", titoli == ["Biografia", "Contatti"], str(titoli))


def test_impostazioni_admin():
    print("\npagina delle impostazioni")
    pagina = server.config_page("TOKEN")
    check("le due sezioni ci sono",
          'id="sezione-biografia"' in pagina and 'id="sezione-progetti"' in pagina)
    check("una scheda per progetto, più quella vuota del modello",
          pagina.count('class="gruppo progetto-config"') == 4 + 1)
    check("la nota della lista vuota è nascosta quando ci sono progetti",
          'id="progetti-vuoto-nota" hidden' in pagina)
    check("il testo della biografia arriva all'editor", "Sono Maria" in pagina)


def main():
    salvata = copy.deepcopy(CONFIG)
    try:
        test_predefiniti()
        test_impostazioni_sporche()
        test_posizioni()
        test_progetti()
        test_pagina_biografia()
        test_menu_titoli_anteprime()
        test_lavora_con_me()
        test_card_omonima()
    finally:
        CONFIG.clear()
        CONFIG.update(salvata)
    # The Settings page reads config.json from disk: it is checked with the
    # configuration on disk patched for the length of the test.
    originale = server.load_config
    server.load_config = lambda: dict(CONFIG, **{"biography": {
        "enabled": True, "position": "top", "photo": "", "content": "<p>Sono Maria.</p>",
        "content_en": ""}, "projects": {"enabled": True, "position": "top", "items": [
            {"name": n, "visible": True} for n in ("A", "B", "C", "D")]}})
    try:
        test_impostazioni_admin()
    finally:
        server.load_config = originale
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
