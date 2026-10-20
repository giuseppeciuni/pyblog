#!/usr/bin/env python3
"""
Checks on the biography and the projects of the homepage.

    python3 tests/test_biography_projects.py

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


def article(number):
    return {"title": f"Articolo {number}", "slug": f"articolo-{number}",
            "content": "<p>Testo dell'articolo.</p>", "status": "published",
            "date": f"2026-01-{number:02d}", "tags": "Prova"}


ARTICLES_FIXTURE = [article(n) for n in range(1, 4)]
BIO = "<p>Sono Maria, ingegnera del software. " + "Scrivo di sistemi distribuiti. " * 20 + "</p>"


def set_value(bio_position="top", projects_position="bottom", bio_enabled=True,
            projects_enabled=True):
    CONFIG["language"] = "it"
    CONFIG["biography"] = {"enabled": bio_enabled, "position": bio_position,
                           "photo": "/media/io.jpg", "content": BIO,
                           "content_en": "<p>I am Maria, a software engineer.</p>"}
    CONFIG["projects"] = {"enabled": projects_enabled, "position": projects_position, "items": [
        {"name": "Alfa", "description": "Il <b>primo</b>", "description_en": "The first",
         "url": "https://example.org/alfa", "image": "/media/alfa.png", "visible": True},
        {"name": "Nascosto", "description": "No", "url": "", "image": "", "visible": False},
        {"name": "Beta", "description": "Il secondo", "url": "javascript:alert(1)",
         "image": "", "visible": True},
        {"name": "", "description": "Senza nome", "visible": True},
    ]}


def test_defaults():
    print("\nvalori predefiniti")
    check("biografia spenta", CONFIG_DEFAULT["biography"]["enabled"] is False)
    check("progetti spenti", CONFIG_DEFAULT["projects"]["enabled"] is False)
    titles = [card["title"] for card in CONFIG_DEFAULT["home_cards"]]
    check("niente card Biografia e Progetti tra quelle di partenza",
          "Biografia" not in titles and "Progetti" not in titles, str(titles))
    CONFIG["biography"] = copy.deepcopy(CONFIG_DEFAULT["biography"])
    CONFIG["projects"] = copy.deepcopy(CONFIG_DEFAULT["projects"])
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    check("spente, la home non le mostra",
          "box-biography" not in home and "home-section" not in home and "box-progetti" not in home)


def test_dirty_settings():
    print("\nimpostazioni salvate male")
    bio = build.biography_settings({"biography": {"enabled": "si", "position": "altrove",
                                                  "content": 3}})
    check("un valore non booleano non accende, una posizione ignota torna predefinita",
          bio["enabled"] is False and bio["position"] == "sidebar" and bio["content"] == "")
    projects = build.projects_settings({"projects": {"items": ["x", {"name": 5}]}})
    check("le voci che non sono progetti si scartano, i testi si ripuliscono",
          len(projects["items"]) == 1 and projects["items"][0]["name"] == "")
    check("una lista che non è una lista non fa danni",
          build.projects_settings({"projects": {"items": "x"}})["items"] == [])


def test_positions():
    print("\nposizioni nella home")
    set_value("top", "bottom")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    i_biography = home.find("home-biography")
    i_article = home.find('id="articles"')
    i_projects = home.find("home-projects")
    check("biografia sopra gli articoli, progetti sotto", 0 < i_biography < i_article < i_projects)
    check("la biografia porta alla sua pagina",
          'href="/pages/biografia.html"' in home)

    set_value("bottom", "top")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    check("e al contrario", 0 < home.find("home-projects") < home.find('id="articles"')
          < home.find("home-biography"))

    set_value("sidebar", "sidebar")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    sidebar_html = home[home.find("<aside"):]
    check("nella barra laterale, fuori dalla colonna",
          "box-biography" in sidebar_html and "box-progetti" in sidebar_html and "home-section" not in home)
    check("in barra: presentazione, biografia, progetti, esplora, nell'ordine",
          sidebar_html.find("box-intro") < sidebar_html.find("box-biography") < sidebar_html.find("box-progetti")
          < sidebar_html.find("box-segui"))

    set_value("top", "top")
    page_two = build.generate_homepage(ARTICLES_FIXTURE, "it", page=2, total_pages=2)
    check("dalla seconda pagina in poi non si ripetono",
          "home-biography" not in page_two and "home-projects" not in page_two)


def test_projects():
    print("\nprogetti")
    set_value("top", "top")
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    section = home[home.find("home-projects"):home.find('id="articles"')]
    check("il nascosto e quello senza nome restano fuori",
          "Nascosto" not in section and "Senza nome" not in section)
    check("nell'ordine della lista", section.find("Alfa") < section.find("Beta"))
    check("un link javascript: non diventa un link",
          "javascript:" not in home and ">Beta</h3>" in section.replace("\n", ""), section[:400])
    check("il testo viene escapato", "Il &lt;b&gt;primo&lt;/b&gt;" in section)
    check("l'immagine c'è solo dove è stata messa", section.count("project-picture") == 1)
    english = build.generate_homepage(ARTICLES_FIXTURE, "en")
    check("in inglese la descrizione tradotta, e Beta senza traduzione in italiano",
          "The first" in english and "Il secondo" in english)
    check("in inglese il titolo della sezione è Projects", ">Projects</h2>" in english)


def test_biography_page():
    print("\npagina della biografia")
    set_value()
    page_html = build.generate_biography_page("it", ARTICLES_FIXTURE)
    check("ha tutto il testo, non l'estratto", BIO in page_html)
    check("ha la foto e il canonical giusto",
          'class="bio-page-photo" src="/media/io.jpg"' in page_html
          and 'rel="canonical" href="' + CONFIG["base_url"] + '/pages/biografia.html"' in page_html)
    english = build.generate_biography_page("en", ARTICLES_FIXTURE)
    check("la versione inglese usa la traduzione", "I am Maria" in english and BIO not in english)
    CONFIG["biography"]["content_en"] = ""
    check("senza traduzione mostra la biografia in italiano",
          BIO in build.generate_biography_page("en", ARTICLES_FIXTURE))
    sitemap = build.generate_sitemap(ARTICLES_FIXTURE)
    check("la sitemap la elenca in entrambe le lingue",
          sitemap.count("/pages/biografia.html") == 2)
    CONFIG["biography"]["content"] = "<p><br></p>"
    check("senza testo non va online", not build.biography_published())
    check("e la sitemap non la elenca",
          "/pages/biografia.html" not in build.generate_sitemap(ARTICLES_FIXTURE))


def test_menu_titles_previews():
    print("\nmenu, titoli e anteprime social")
    set_value()
    CONFIG["base_url"] = "https://esempio.it"
    CONFIG["site_title"] = "Il mio sito"
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    check("con la biografia online il menu ha Chi sono",
          '<a href="/pages/biografia.html">Chi sono</a>' in home.split("</nav>")[0])
    check("in inglese porta alla pagina inglese",
          '<a href="/en/pages/biografia.html">About me</a>'
          in build.generate_homepage(ARTICLES_FIXTURE, "en").split("</nav>")[0])
    CONFIG["biography"]["enabled"] = False
    check("spenta, il menu non la elenca",
          "Chi sono" not in build.generate_homepage(ARTICLES_FIXTURE, "it").split("</nav>")[0])

    cover_article = dict(article(1), image="media/copertina.png")
    page_html = build.generate_article_page(cover_article, "it", ARTICLES_FIXTURE)
    check("l'immagine dell'anteprima social ha l'indirizzo completo",
          '<meta property="og:image" content="https://esempio.it/media/copertina.png">' in page_html,
          page_html.split("og:image")[1][:120])
    check("anche nei dati per i motori di ricerca",
          '"image": "https://esempio.it/media/copertina.png"' in page_html)
    external = dict(article(1), image="https://altrove.org/foto.png")
    check("un indirizzo gia' completo resta com'e'",
          'og:image" content="https://altrove.org/foto.png"'
          in build.generate_article_page(external, "it", ARTICLES_FIXTURE))
    check("il titolo della pagina finisce con il nome del sito",
          "<title>Articolo 1 &middot; Il mio sito</title>" in page_html)

    CONFIG["site_title"] = ""
    CONFIG["subtitle"] = "Note tecniche"
    page_html = build.generate_article_page(cover_article, "it", ARTICLES_FIXTURE)
    check("senza nome del sito il titolo non finisce con un punto",
          "<title>Articolo 1</title>" in page_html, page_html.split("<title>")[1][:60])
    check("e non c'e' un nome vuoto per le anteprime", "og:site_name" not in page_html)
    check("la home usa il solo sottotitolo",
          "<title>Note tecniche</title>" in build.generate_homepage(ARTICLES_FIXTURE, "it"))


def test_work_with_me():
    print("\nlavora con me")
    set_value()
    CONFIG["work_with_me"] = {"enabled": True, "url": "/pages/lavora-con-me.html",
                              "label": "", "label_en": "Hire me", "text": "Parliamone <ora>",
                              "text_en": ""}
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    menu = home.split("</nav>")[0]
    check("il menu chiude con il pulsante, con la scritta predefinita",
          '<a class="nav-work" href="/pages/lavora-con-me.html">Lavora con me</a>' in menu
          and menu.index("nav-work") > menu.index("Chi sono"), menu[-400:])
    page_html = build.generate_article_page(article(1), "it", ARTICLES_FIXTURE)
    invitation = page_html.split('<aside class="invite-work">')[1].split("</aside>")[0]
    check("a fine articolo c'e' l'invito, con la frase scelta e senza far passare HTML",
          "Parliamone &lt;ora&gt;" in invitation and 'href="/pages/lavora-con-me.html"' in invitation
          and page_html.index("invite-work") > page_html.index('class="post-content"'))
    english = build.generate_homepage(ARTICLES_FIXTURE, "en").split("</nav>")[0]
    check("in inglese porta alla pagina inglese, con la sua scritta",
          '<a class="nav-work" href="/en/pages/lavora-con-me.html">Hire me</a>' in english)
    CONFIG["work_with_me"]["url"] = "mailto:io@esempio.it"
    check("un indirizzo email resta com'e' in tutte le lingue",
          'href="mailto:io@esempio.it"' in build.generate_homepage(ARTICLES_FIXTURE, "en"))
    CONFIG["work_with_me"]["url"] = "javascript:alert(1)"
    check("un indirizzo non valido non mostra nulla",
          "nav-work" not in build.generate_homepage(ARTICLES_FIXTURE, "it"))
    CONFIG["work_with_me"] = {"enabled": False, "url": "/pages/x.html"}
    check("spento, niente pulsante e niente invito",
          "nav-work" not in build.generate_homepage(ARTICLES_FIXTURE, "it")
          and "invite-work" not in build.generate_article_page(article(1), "it", ARTICLES_FIXTURE))
    CONFIG["work_with_me"] = "sporco"
    check("un valore sporco vale spento", build.work_link("it") is None)


def test_card_with_same_name():
    print("\ncard con lo stesso nome")
    set_value()
    CONFIG["home_cards_enabled"] = True
    CONFIG["home_cards"] = [{"active": True, "title": "Biografia", "content": "<p>Vecchia</p>"},
                            {"active": True, "title": "Contatti", "content": "<p>Scrivimi</p>"}]
    titles = [card["title"] for card in build.published_home_cards()]
    check("con la biografia accesa, la vecchia card Biografia non scrive sopra la sua pagina",
          titles == ["Contatti"], str(titles))
    CONFIG["biography"]["enabled"] = False
    titles = [card["title"] for card in build.published_home_cards()]
    check("con la biografia spenta, la card torna", titles == ["Biografia", "Contatti"], str(titles))


def test_admin_settings():
    print("\npagina delle impostazioni")
    page_html = server.config_page("TOKEN")
    check("le due sezioni ci sono",
          'id="section-biography"' in page_html and 'id="section-projects"' in page_html)
    check("una scheda per progetto, più quella vuota del modello",
          page_html.count('class="group project-config"') == 4 + 1)
    check("la nota della lista vuota è nascosta quando ci sono progetti",
          'id="projects-empty-note" hidden' in page_html)
    check("il testo della biografia arriva all'editor", "Sono Maria" in page_html)


def main():
    saved_page = copy.deepcopy(CONFIG)
    try:
        test_defaults()
        test_dirty_settings()
        test_positions()
        test_projects()
        test_biography_page()
        test_menu_titles_previews()
        test_work_with_me()
        test_card_with_same_name()
    finally:
        CONFIG.clear()
        CONFIG.update(saved_page)
    # The Settings page reads config.json from disk: it is checked with the
    # configuration on disk patched for the length of the test.
    original = server.load_config
    server.load_config = lambda: dict(CONFIG, **{"biography": {
        "enabled": True, "position": "top", "photo": "", "content": "<p>Sono Maria.</p>",
        "content_en": ""}, "projects": {"enabled": True, "position": "top", "items": [
            {"name": n, "visible": True} for n in ("A", "B", "C", "D")]}})
    try:
        test_admin_settings()
    finally:
        server.load_config = original
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
