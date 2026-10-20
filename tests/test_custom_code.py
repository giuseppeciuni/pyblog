#!/usr/bin/env python3
"""
Checks on the custom code injected into the public pages.

    python3 tests/test_custom_code.py

The thing worth testing here is the scope, not the injection: getting a
snippet into a page is one string concatenation, but deciding WHICH pages it
belongs to is a rule with six scopes and six positions, and a mistake there
is silent. A tracking pixel that quietly lands on every article instead of the
three you picked looks exactly like one that works.

The snippets below are HTML comments with unmistakable markers, so a match
cannot be a coincidence: nothing else in the site says MARCA-SOLO-HOME.
"""
import json
import pathlib
import sys

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.articles import HISTORY_DIR, load_article, save_article  # noqa: E402
from core.build import build, snippet_applies  # noqa: E402
from core.config import OUTPUT_DIR  # noqa: E402
from core.config import CONFIG_FILE, POSTS_DIR, load_config, save_config  # noqa: E402

PASSED = 0
FAILED = 0

# One snippet per scope, each in a different position, plus one switched off.
TEST_SNIPPET = [
    {"id": "prova-home", "name": "Solo home", "enabled": True,
     "position": "head", "scope": "home",
     "code": "<!-- MARCA-SOLO-HOME -->"},
    {"id": "prova-ovunque", "name": "Ovunque", "enabled": True,
     "position": "body_start", "scope": "home_articles",
     "code": "<!-- MARCA-TUTTI-ARTICOLI -->"},
    {"id": "prova-scelti", "name": "Scelti", "enabled": True,
     "position": "body_end", "scope": "home_optin",
     "code": "<!-- MARCA-OPTIN -->"},
    {"id": "prova-spento", "name": "Spento", "enabled": False,
     "position": "head", "scope": "home_articles",
     "code": "<!-- MARCA-SPENTA -->"},
    # The scopes that leave the homepage out, and the whole-site one. Each
    # sits in one of the three visible positions, so the same fixture covers
    # both halves of the feature.
    {"id": "prova-solo-articoli", "name": "Solo articoli", "enabled": True,
     "position": "after_header", "scope": "articles",
     "code": "<!-- MARCA-SOLO-ARTICOLI -->"},
    {"id": "prova-solo-scelti", "name": "Solo scelti", "enabled": True,
     "position": "article_end", "scope": "optin",
     "code": "<!-- MARCA-SOLO-SCELTI -->"},
    {"id": "prova-ovunque-davvero", "name": "Tutto il sito", "enabled": True,
     "position": "before_footer", "scope": "all",
     "code": "<!-- MARCA-OVUNQUE -->"},
    # The header menu: a link, because that is what goes there.
    {"id": "prova-menu", "name": "Voce di menu", "enabled": True,
     "position": "nav", "scope": "all",
     "code": '<a href="#" data-vaitony-apri>MARCA-MENU</a>'},
    # On every article, except the one that switches it off for itself.
    {"id": "prova-spegnibile", "name": "Spegnibile", "enabled": True,
     "position": "body_end", "scope": "articles",
     "code": "<!-- MARCA-SPEGNIBILE -->"},
]

# The code written inside the ticked article: one piece at the top of the
# text, one half way down, one switched off. The markers share no prefix, so
# finding one can never be finding another.
OWN_CODE = [
    {"id": "art-inizio", "name": "Annuncio in cima", "enabled": True,
     "position": "article_start", "consent": "necessary",
     "code": "<!-- MARCA-MIO-INIZIO -->"},
    {"id": "art-meta", "name": "Annuncio a metà", "enabled": True,
     "position": "article_middle", "consent": "marketing",
     "code": "<!-- MARCA-MIO-META -->"},
    {"id": "art-spento", "name": "Spento", "enabled": False,
     "position": "article_end", "consent": "necessary",
     "code": "<!-- MARCA-NON-DEVE-USCIRE -->"},
]

TICKED = "come-un-llm-genera-testo"
UNTICKED = "note-sui-sistemi-distribuiti"


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
    full_path = ROOT_DIR / path_value
    if not full_path.exists():
        return ""
    return full_path.read_text(encoding="utf-8")


def contains(path_value, marker):
    return marker in leggi(path_value)


def test_page_scope():
    """Each scope must reach exactly the pages it promises, and no others."""
    print("\nambito: dove finisce ogni pezzo di codice")

    home = "output/index.html"
    chosen = f"output/posts/{TICKED}.html"
    altro = f"output/posts/{UNTICKED}.html"

    # The homepage takes all three scopes: that is what they have in common.
    check("la home riceve il codice 'solo home'", contains(home, "MARCA-SOLO-HOME"))
    check("la home riceve il codice 'tutti gli articoli'",
          contains(home, "MARCA-TUTTI-ARTICOLI"))
    check("la home riceve il codice 'articoli scelti'", contains(home, "MARCA-OPTIN"))

    # An article never takes the homepage-only one.
    check("l'articolo scelto non riceve il 'solo home'",
          not contains(chosen, "MARCA-SOLO-HOME"))
    check("l'altro articolo non riceve il 'solo home'",
          not contains(altro, "MARCA-SOLO-HOME"))

    # "Every article" means every article.
    check("l'articolo scelto riceve il 'tutti gli articoli'",
          contains(chosen, "MARCA-TUTTI-ARTICOLI"))
    check("l'altro articolo riceve il 'tutti gli articoli'",
          contains(altro, "MARCA-TUTTI-ARTICOLI"))

    # The point of the whole feature: opt-in reaches ONLY the ticked article.
    check("l'articolo con la spunta riceve il codice scelto",
          contains(chosen, "MARCA-OPTIN"))
    check("l'articolo SENZA la spunta non lo riceve",
          not contains(altro, "MARCA-OPTIN"),
          "una spunta su un articolo ha invaso gli altri")

    # Switched off means off, wherever it was pointed.
    for nome, path_value in (("home", home), ("articolo", chosen)):
        check(f"il codice disattivato non esce nella {nome}",
              not contains(path_value, "MARCA-SPENTA"))

    # "Solo gli articoli" is the mirror of "solo home": it must skip the home.
    check("la home NON riceve il 'solo articoli'",
          not contains(home, "MARCA-SOLO-ARTICOLI"),
          "un codice riservato agli articoli e' finito in homepage")
    check("l'articolo scelto riceve il 'solo articoli'",
          contains(chosen, "MARCA-SOLO-ARTICOLI"))
    check("l'altro articolo riceve il 'solo articoli'",
          contains(altro, "MARCA-SOLO-ARTICOLI"))

    # "Solo gli articoli scelti": nemmeno la home, e solo quello spuntato.
    check("la home NON riceve il 'solo articoli scelti'",
          not contains(home, "MARCA-SOLO-SCELTI"))
    check("l'articolo con la spunta riceve il 'solo articoli scelti'",
          contains(chosen, "MARCA-SOLO-SCELTI"))
    check("l'articolo senza la spunta non lo riceve",
          not contains(altro, "MARCA-SOLO-SCELTI"))

    # "Tutto il sito" means every page we generate, the odd ones included.
    for nome, path_value in (("home", home), ("articolo", chosen),
                           ("tag", "output/tag/ai.html"),
                           ("archivio", "output/archivio.html"),
                           ("404", "output/404.html")):
        check(f"'tutto il sito' arriva anche su {nome}",
              contains(path_value, "MARCA-OVUNQUE"),
              f"{path_value} non ha ricevuto il codice di tutto il sito")

    # Tag, archive and 404 are outside every scope but "the whole site".
    for path_value in ("output/tag/ai.html", "output/archivio.html", "output/404.html"):
        clean_page = True
        for marker in ("MARCA-SOLO-HOME", "MARCA-TUTTI-ARTICOLI", "MARCA-OPTIN",
                          "MARCA-SOLO-ARTICOLI", "MARCA-SOLO-SCELTI"):
            if contains(path_value, marker):
                clean_page = False
        check(f"{path_value}: nessun altro codice personalizzato", clean_page)


def test_position_on_page():
    """Each position must land where the dropdown says it does."""
    print("\nposizione: dove finisce dentro la pagina")
    home = leggi("output/index.html")

    head = home.split("</head>")[0]
    check("'nell'head' sta davvero nell'head", "MARCA-SOLO-HOME" in head)

    after_body = home.split("<body", 1)[1].split(">", 1)[1]
    before_header = after_body.split("<header")[0]
    check("'inizio body' sta fra <body> e l'header",
          "MARCA-TUTTI-ARTICOLI" in before_header)

    queue = home.split("</footer>")[-1]
    check("'fondo pagina' sta dopo il footer", "MARCA-OPTIN" in queue)
    check("'fondo pagina' sta dentro il body", "MARCA-OPTIN" in home.split("</body>")[0])

    # The three visible positions all exist on an article page, so one page
    # is enough to check them. We compare offsets rather than splitting: the
    # question here is the ORDER of the landmarks, and that is what reads.
    chosen = leggi(f"output/posts/{TICKED}.html")

    def before_of(marker, landmark):
        where = chosen.find(marker)
        reference = chosen.find(landmark)
        return where != -1 and reference != -1 and where < reference

    def after_value(marker, landmark):
        where = chosen.find(marker)
        reference = chosen.find(landmark)
        return where != -1 and reference != -1 and where > reference

    check("'sotto l'intestazione' sta dopo la fine dell'header",
          after_value("MARCA-SOLO-ARTICOLI", "</header>"))
    check("'sotto l'intestazione' sta prima dell'articolo",
          before_of("MARCA-SOLO-ARTICOLI", '<article id="content"'))

    check("'fondo del testo' sta dentro l'articolo",
          after_value("MARCA-SOLO-SCELTI", '<article id="content"')
          and before_of("MARCA-SOLO-SCELTI", "</article>"))

    check("'prima del footer' sta dopo la fine dell'articolo",
          after_value("MARCA-OVUNQUE", "</article>"))
    check("'prima del footer' sta prima del footer",
          before_of("MARCA-OVUNQUE", "<footer"))

    # "Nel menu" must sit INSIDE the nav, among the links: after RSS and before
    # the language switcher. On every page, English ones included, because the
    # header is shared.
    for path_value in ("output/index.html", f"output/posts/{TICKED}.html",
                     "output/404.html", "output/en/index.html"):
        page_html = leggi(path_value)
        menu = page_html.split('<nav class="site-nav"', 1)[-1].split("</nav>", 1)[0]
        check(f"{path_value}: 'nel menu' sta dentro il <nav>", "MARCA-MENU" in menu)
        check(f"{path_value}: 'nel menu' sta dopo RSS e prima della lingua",
              menu.find(">RSS</a>") < menu.find("MARCA-MENU") < menu.find("nav-lingua"))
    check("'nel menu' esce una volta sola per pagina",
          leggi("output/index.html").count("MARCA-MENU") == 1)


def test_inserted_code_intact():
    """The code is injected verbatim: escaping it would defeat the point."""
    print("\nil codice arriva intatto")
    home = leggi("output/index.html")
    check("il commento non e' stato trasformato in testo",
          "&lt;!-- MARCA-SOLO-HOME" not in home,
          "il codice e' stato escapato invece che inserito")


def test_missing_or_dead_id():
    """A snippet id an article keeps after the snippet is gone is inert."""
    print("\nid che non esistono piu'")
    alive = {"id": "prova-scelti", "enabled": True, "scope": "home_optin"}
    check("un id spuntato attiva lo snippet",
          snippet_applies(alive, "article", ("prova-scelti",)))
    check("un id di uno snippet cancellato non attiva nulla",
          not snippet_applies(alive, "article", ("sparito-da-tempo",)))
    check("una lista di id vuota non attiva nulla",
          not snippet_applies(alive, "article", ()))

    # A snippet with no scope at all falls back to the narrowest one.
    without = {"id": "x", "enabled": True}
    check("senza ambito si comporta come 'solo home'",
          snippet_applies(without, "home", ()) and not snippet_applies(without, "article", ()))
    check("uno snippet spento non esce mai",
          not snippet_applies({"id": "x", "scope": "home"}, "home", ()))


def test_scope_rules():
    """The scope rule on its own, without building a whole site for it."""
    print("\nla regola dell'ambito, voce per voce")

    def holds(scope, page_kind, ids=()):
        return snippet_applies(
            {"id": "x", "enabled": True, "scope": scope}, page_kind, ids)

    expected_value = {
        # scope            home   articolo  altre pagine
        "home":           (True,  False,    False),
        "articles":       (False, True,     False),
        "home_articles":  (True,  True,     False),
        "all":            (True,  True,     True),
    }
    for scope, (in_home, in_article, elsewhere) in expected_value.items():
        check(f"'{scope}': home={in_home}",
              holds(scope, "home") is in_home)
        check(f"'{scope}': articolo={in_article}",
              holds(scope, "article") is in_article)
        check(f"'{scope}': altre pagine={elsewhere}",
              holds(scope, "other") is elsewhere)

    # The two opt-in scopes differ only on the homepage.
    check("'optin' non esce in home", not holds("optin", "home"))
    check("'home_optin' esce in home", holds("home_optin", "home"))
    for scope in ("optin", "home_optin"):
        check(f"'{scope}' esce sull'articolo spuntato",
              holds(scope, "article", ("x",)))
        check(f"'{scope}' non esce su un articolo qualsiasi",
              not holds(scope, "article", ("un-altro",)))

    # An ambito written by hand and misspelled must not make the snippet
    # disappear without a trace: it falls back to the default, "solo home".
    check("un ambito sconosciuto si comporta come 'solo home'",
          holds("ambito-inventato", "home")
          and not holds("ambito-inventato", "article"))


def test_ticks_survive_saving():
    """Saving an article must not lose which snippets it had ticked."""
    print("\nle spunte restano sull'articolo")
    article = load_article(TICKED)
    check("l'articolo ricorda la spunta",
          "prova-scelti" in article.get("custom_code_ids", []))

    # A save with the field absent (an older client) must not wipe it silently
    # into something invalid: it becomes an empty list, never None.
    copy_value = dict(article)
    del copy_value["custom_code_ids"]
    save_article(copy_value)
    reloaded = load_article(TICKED)
    check("senza il campo, la lista e' vuota e non rotta",
          reloaded.get("custom_code_ids") == [])

    # Put the ticks back and check they survive a normal round trip.
    reloaded["custom_code_ids"] = ["prova-scelti"]
    save_article(reloaded)
    check("dopo un salvataggio normale la spunta c'e' ancora",
          load_article(TICKED).get("custom_code_ids") == ["prova-scelti"])


def test_off_on_one_article():
    """An article can say no to a snippet that goes on every article."""
    print("\nun articolo spegne un codice di serie")
    check("l'articolo che lo spegne non lo riceve",
          not contains(f"output/posts/{TICKED}.html", "MARCA-SPEGNIBILE"))
    check("la sua versione tradotta nemmeno",
          not contains(f"output/en/posts/{TICKED}.html", "MARCA-SPEGNIBILE"))
    check("gli altri articoli lo ricevono ancora",
          contains(f"output/posts/{UNTICKED}.html", "MARCA-SPEGNIBILE"),
          "spegnerlo su un articolo l'ha spento dappertutto")

    everywhere = {"id": "x", "enabled": True, "scope": "all"}
    check("la regola: spento sull'articolo che lo dice",
          not snippet_applies(everywhere, "article", (), ("x",)))
    check("la regola: le altre pagine non ne sanno niente",
          snippet_applies(everywhere, "home", (), ("x",))
          and snippet_applies(everywhere, "other", (), ("x",)))
    check("la regola: spegnere vince anche sulla spunta",
          not snippet_applies({"id": "x", "enabled": True, "scope": "optin"},
                              "article", ("x",), ("x",)))


def test_own_code():
    """The code written inside an article goes there and nowhere else."""
    print("\ncodice scritto dentro un articolo")
    page_html = leggi(f"output/posts/{TICKED}.html")
    check("l'articolo riceve il suo codice in cima", "MARCA-MIO-INIZIO" in page_html)
    check("l'articolo riceve il suo codice a metà", "MARCA-MIO-META" in page_html)
    check("il codice proprio spento non esce", "MARCA-NON-DEVE-USCIRE" not in page_html)
    check("la versione tradotta riceve lo stesso codice",
          contains(f"output/en/posts/{TICKED}.html", "MARCA-MIO-INIZIO"))

    for nome, path_value in (("home", "output/index.html"),
                           ("altro articolo", f"output/posts/{UNTICKED}.html"),
                           ("archivio", "output/archivio.html"),
                           ("tag", "output/tag/ai.html")):
        elsewhere = leggi(path_value)
        check(f"non esce su {nome}",
              "MARCA-MIO-INIZIO" not in elsewhere and "MARCA-MIO-META" not in elsewhere)

    # "At the start": after the title, before the text. "Half way": inside
    # the text, with paragraphs on both sides.
    start = page_html.find("MARCA-MIO-INIZIO")
    testo = page_html.find('<div class="post-content">')
    check("'all'inizio' sta dopo il titolo e prima del testo",
          page_html.find("<h1") < start < testo)
    meta = page_html.find("MARCA-MIO-META")
    check("'a metà' sta dentro il testo",
          testo < meta < page_html.find("</article>"))
    check("'a metà' ha testo prima e dopo",
          "</p>" in page_html[testo:meta] and "<p" in page_html[meta:page_html.find("</article>")])


def test_saving_own_code():
    """The article keeps its own code and its switched-off snippets."""
    print("\nil salvataggio conserva i codici dell'articolo")
    article = load_article(TICKED)
    own = article.get("custom_code", [])
    check("i codici propri sono salvati, nell'ordine",
          [s.get("id") for s in own] == ["art-inizio", "art-meta", "art-spento"])
    check("con posizione e consenso",
          own[1].get("position") == "article_middle" and own[1].get("consent") == "marketing")
    check("il codice spento resta spento", own[2].get("enabled") is False)
    check("gli spegnimenti sono salvati",
          article.get("custom_code_off_ids") == ["prova-spegnibile"])

    # What a hand-edited file or an old client can send: something that is
    # not a card, a card without an id, a second card with an id taken.
    copy_value = dict(article)
    copy_value["custom_code"] = own + ["rotto", {"code": "<!-- senza id -->"},
                                     {"id": "art-inizio", "code": "<!-- doppio -->"}]
    save_article(copy_value)
    saved_items = load_article(TICKED)["custom_code"]
    ids = [s["id"] for s in saved_items]
    check("le voci che non sono codici vengono scartate", len(saved_items) == len(own) + 2)
    check("ogni codice ha un id, e nessuno è ripetuto",
          all(ids) and len(set(ids)) == len(ids), str(ids))
    check("gli id nuovi sono quelli dell'articolo",
          all(i.startswith("art-") for i in ids[len(own):]), str(ids))
    check("i codici esistenti tengono il loro id", ids[:len(own)] == ["art-inizio", "art-meta", "art-spento"])

    copy_value["custom_code"] = own
    save_article(copy_value)


def test_consent():
    """With the banner on, the code that needs consent waits for it."""
    print("\nconsenso: il codice aspetta la scelta del visitatore")
    config = load_config()
    config["consent"] = {"enabled": True, "text": "", "text_en": "",
                         "privacy_url": "https://example.org/privacy", "version": 3}
    config["analytics_id"] = "G-PROVA12345"
    config["custom_code"] = TEST_SNIPPET + [
        {"id": "prova-statistiche", "name": "Statistiche", "enabled": True,
         "position": "head", "scope": "all", "consent": "statistics",
         "code": "<!-- MARCA-STATISTICHE -->"},
        {"id": "prova-pubblicita", "name": "Pubblicità", "enabled": True,
         "position": "sidebar", "scope": "all", "consent": "marketing",
         "code": "<!-- MARCA-PUBBLICITA -->"},
    ]
    config["ads_txt"] = "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0"
    save_config(config)
    build()

    home = leggi("output/index.html")
    check("le statistiche arrivano trattenute",
          '<template data-pb-consenso="statistics"><!-- MARCA-STATISTICHE --></template>' in home)
    check("la pubblicità arriva trattenuta",
          '<template data-pb-consenso="marketing"><!-- MARCA-PUBBLICITA --></template>' in home)
    home_only = home.find("MARCA-SOLO-HOME")
    check("il codice necessario parte subito",
          home_only != -1 and "<template" not in home[home_only - 40:home_only])
    check("Google Analytics aspetta anche lui",
          '<template data-pb-consenso="statistics"><script async '
          'src="https://www.googletagmanager.com/gtag/js?id=G-PROVA12345"' in home)
    check("i valori di Consent Mode vengono prima di ogni tag di Google",
          -1 < home.find("gtag('consent', 'default'") < home.find("gtag/js?id=G-PROVA12345"))
    check("il banner è nella pagina", 'id="pb-consenso"' in home)
    check("chiede le due categorie usate",
          'data-categoria="statistics"' in home and 'data-categoria="marketing"' in home)
    check("site.js riceve versione e categorie",
          '"consent": {"version": 3, "categories": ["statistics", "marketing"]}' in home)
    check("il banner porta all'informativa", 'href="https://example.org/privacy"' in home)
    check("il piè di pagina permette di cambiare idea", 'data-consenso="apri"' in home)
    check("in inglese il banner è in inglese",
          "Cookies and privacy" in leggi("output/en/index.html"))
    check("il codice proprio dell'articolo aspetta il suo consenso",
          '<template data-pb-consenso="marketing"><!-- MARCA-MIO-META --></template>'
          in leggi(f"output/posts/{TICKED}.html"))

    ads = OUTPUT_DIR / "ads.txt"
    check("ads.txt viene pubblicato",
          ads.exists() and ads.read_text(encoding="utf-8") == config["ads_txt"] + "\n")

    # Banner on, but nothing that needs it: no banner at all.
    config["analytics_id"] = ""
    config["custom_code"] = TEST_SNIPPET
    save_config(config)
    build()
    home = leggi("output/index.html")
    check("senza codici da trattenere il banner non esce", 'id="pb-consenso"' not in home)
    check("e il piè di pagina non offre preferenze", 'data-consenso="apri"' not in home)

    # Banner off: everything runs as written, and ads.txt goes away.
    config["consent"]["enabled"] = False
    config["analytics_id"] = "G-PROVA12345"
    config["ads_txt"] = ""
    save_config(config)
    build()
    home = leggi("output/index.html")
    check("a banner spento niente viene trattenuto", "data-pb-consenso" not in home)
    check("a banner spento Analytics parte subito",
          '<script async src="https://www.googletagmanager.com/gtag/js?id=G-PROVA12345">' in home)
    check("a banner spento nessun Consent Mode", "gtag('consent', 'default'" not in home)
    check("ads.txt vuoto non viene pubblicato", not ads.exists())


def main():
    article = load_article(TICKED)
    if article is None:
        print("articolo di prova assente: salto")
        return

    # We are about to rewrite config.json and one article, so we remember
    # exactly how we found them - including config.json not existing at all,
    # which is the normal state of a fresh checkout. The article is kept as
    # its raw text: saving it again would bump date_modified, and a test has
    # no business changing when an article was last edited.
    original_config = None
    if CONFIG_FILE.exists():
        original_config = CONFIG_FILE.read_text(encoding="utf-8")
    article_file = POSTS_DIR / f"{TICKED}.json"
    original_article = article_file.read_text(encoding="utf-8")
    # Saving the article also keeps its previous version in the history:
    # the versions this test makes are removed with the rest.
    versions_before = set(HISTORY_DIR.glob("*/*.json")) if HISTORY_DIR.exists() else set()

    config = load_config()
    config["custom_code"] = TEST_SNIPPET
    save_config(config)
    article["custom_code_ids"] = ["prova-scelti", "prova-solo-scelti"]
    article["custom_code_off_ids"] = ["prova-spegnibile"]
    article["custom_code"] = OWN_CODE
    save_article(article)
    build()

    try:
        test_page_scope()
        test_position_on_page()
        test_inserted_code_intact()
        test_missing_or_dead_id()
        test_scope_rules()
        test_ticks_survive_saving()
        test_off_on_one_article()
        test_own_code()
        test_saving_own_code()
        # Last: it rebuilds the site with other settings.
        test_consent()
    finally:
        article_file.write_text(original_article, encoding="utf-8")
        if HISTORY_DIR.exists():
            for version in set(HISTORY_DIR.glob("*/*.json")) - versions_before:
                version.unlink()
            for folder in sorted(HISTORY_DIR.glob("*"), reverse=True):
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
            if not any(HISTORY_DIR.iterdir()):
                HISTORY_DIR.rmdir()
        if original_config is None:
            CONFIG_FILE.unlink(missing_ok=True)
        else:
            CONFIG_FILE.write_text(original_config, encoding="utf-8")
        build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
