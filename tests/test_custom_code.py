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

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from core.articles import load_article, save_article  # noqa: E402
from core.build import build, snippet_applies  # noqa: E402
from core.config import OUTPUT_DIR  # noqa: E402
from core.config import CONFIG_FILE, POSTS_DIR, load_config, save_config  # noqa: E402

PASSED = 0
FAILED = 0

# One snippet per scope, each in a different position, plus one switched off.
SNIPPET_DI_PROVA = [
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
CODICE_PROPRIO = [
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

CON_SPUNTA = "come-un-llm-genera-testo"
SENZA_SPUNTA = "note-sui-sistemi-distribuiti"


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
    percorso_intero = RADICE / percorso
    if not percorso_intero.exists():
        return ""
    return percorso_intero.read_text(encoding="utf-8")


def contiene(percorso, marcatore):
    return marcatore in leggi(percorso)


def test_ambito_delle_pagine():
    """Each scope must reach exactly the pages it promises, and no others."""
    print("\nambito: dove finisce ogni pezzo di codice")

    home = "output/index.html"
    scelto = f"output/posts/{CON_SPUNTA}.html"
    altro = f"output/posts/{SENZA_SPUNTA}.html"

    # The homepage takes all three scopes: that is what they have in common.
    check("la home riceve il codice 'solo home'", contiene(home, "MARCA-SOLO-HOME"))
    check("la home riceve il codice 'tutti gli articoli'",
          contiene(home, "MARCA-TUTTI-ARTICOLI"))
    check("la home riceve il codice 'articoli scelti'", contiene(home, "MARCA-OPTIN"))

    # An article never takes the homepage-only one.
    check("l'articolo scelto non riceve il 'solo home'",
          not contiene(scelto, "MARCA-SOLO-HOME"))
    check("l'altro articolo non riceve il 'solo home'",
          not contiene(altro, "MARCA-SOLO-HOME"))

    # "Every article" means every article.
    check("l'articolo scelto riceve il 'tutti gli articoli'",
          contiene(scelto, "MARCA-TUTTI-ARTICOLI"))
    check("l'altro articolo riceve il 'tutti gli articoli'",
          contiene(altro, "MARCA-TUTTI-ARTICOLI"))

    # The point of the whole feature: opt-in reaches ONLY the ticked article.
    check("l'articolo con la spunta riceve il codice scelto",
          contiene(scelto, "MARCA-OPTIN"))
    check("l'articolo SENZA la spunta non lo riceve",
          not contiene(altro, "MARCA-OPTIN"),
          "una spunta su un articolo ha invaso gli altri")

    # Switched off means off, wherever it was pointed.
    for nome, percorso in (("home", home), ("articolo", scelto)):
        check(f"il codice disattivato non esce nella {nome}",
              not contiene(percorso, "MARCA-SPENTA"))

    # "Solo gli articoli" is the mirror of "solo home": it must skip the home.
    check("la home NON riceve il 'solo articoli'",
          not contiene(home, "MARCA-SOLO-ARTICOLI"),
          "un codice riservato agli articoli e' finito in homepage")
    check("l'articolo scelto riceve il 'solo articoli'",
          contiene(scelto, "MARCA-SOLO-ARTICOLI"))
    check("l'altro articolo riceve il 'solo articoli'",
          contiene(altro, "MARCA-SOLO-ARTICOLI"))

    # "Solo gli articoli scelti": nemmeno la home, e solo quello spuntato.
    check("la home NON riceve il 'solo articoli scelti'",
          not contiene(home, "MARCA-SOLO-SCELTI"))
    check("l'articolo con la spunta riceve il 'solo articoli scelti'",
          contiene(scelto, "MARCA-SOLO-SCELTI"))
    check("l'articolo senza la spunta non lo riceve",
          not contiene(altro, "MARCA-SOLO-SCELTI"))

    # "Tutto il sito" means every page we generate, the odd ones included.
    for nome, percorso in (("home", home), ("articolo", scelto),
                           ("tag", "output/tag/ai.html"),
                           ("archivio", "output/archivio.html"),
                           ("404", "output/404.html")):
        check(f"'tutto il sito' arriva anche su {nome}",
              contiene(percorso, "MARCA-OVUNQUE"),
              f"{percorso} non ha ricevuto il codice di tutto il sito")

    # Tag, archive and 404 are outside every scope but "the whole site".
    for percorso in ("output/tag/ai.html", "output/archivio.html", "output/404.html"):
        pulita = True
        for marcatore in ("MARCA-SOLO-HOME", "MARCA-TUTTI-ARTICOLI", "MARCA-OPTIN",
                          "MARCA-SOLO-ARTICOLI", "MARCA-SOLO-SCELTI"):
            if contiene(percorso, marcatore):
                pulita = False
        check(f"{percorso}: nessun altro codice personalizzato", pulita)


def test_posizione_nella_pagina():
    """Each position must land where the dropdown says it does."""
    print("\nposizione: dove finisce dentro la pagina")
    home = leggi("output/index.html")

    testa = home.split("</head>")[0]
    check("'nell'head' sta davvero nell'head", "MARCA-SOLO-HOME" in testa)

    dopo_body = home.split("<body", 1)[1].split(">", 1)[1]
    prima_header = dopo_body.split("<header")[0]
    check("'inizio body' sta fra <body> e l'header",
          "MARCA-TUTTI-ARTICOLI" in prima_header)

    coda = home.split("</footer>")[-1]
    check("'fondo pagina' sta dopo il footer", "MARCA-OPTIN" in coda)
    check("'fondo pagina' sta dentro il body", "MARCA-OPTIN" in home.split("</body>")[0])

    # The three visible positions all exist on an article page, so one page
    # is enough to check them. We compare offsets rather than splitting: the
    # question here is the ORDER of the landmarks, and that is what reads.
    scelto = leggi(f"output/posts/{CON_SPUNTA}.html")

    def prima_di(marcatore, punto_di_riferimento):
        dove = scelto.find(marcatore)
        riferimento = scelto.find(punto_di_riferimento)
        return dove != -1 and riferimento != -1 and dove < riferimento

    def dopo(marcatore, punto_di_riferimento):
        dove = scelto.find(marcatore)
        riferimento = scelto.find(punto_di_riferimento)
        return dove != -1 and riferimento != -1 and dove > riferimento

    check("'sotto l'intestazione' sta dopo la fine dell'header",
          dopo("MARCA-SOLO-ARTICOLI", "</header>"))
    check("'sotto l'intestazione' sta prima dell'articolo",
          prima_di("MARCA-SOLO-ARTICOLI", '<article id="content"'))

    check("'fondo del testo' sta dentro l'articolo",
          dopo("MARCA-SOLO-SCELTI", '<article id="content"')
          and prima_di("MARCA-SOLO-SCELTI", "</article>"))

    check("'prima del footer' sta dopo la fine dell'articolo",
          dopo("MARCA-OVUNQUE", "</article>"))
    check("'prima del footer' sta prima del footer",
          prima_di("MARCA-OVUNQUE", "<footer"))

    # "Nel menu" must sit INSIDE the nav, among the links: after RSS and before
    # the language switcher. On every page, English ones included, because the
    # header is shared.
    for percorso in ("output/index.html", f"output/posts/{CON_SPUNTA}.html",
                     "output/404.html", "output/en/index.html"):
        pagina = leggi(percorso)
        menu = pagina.split('<nav class="site-nav"', 1)[-1].split("</nav>", 1)[0]
        check(f"{percorso}: 'nel menu' sta dentro il <nav>", "MARCA-MENU" in menu)
        check(f"{percorso}: 'nel menu' sta dopo RSS e prima della lingua",
              menu.find(">RSS</a>") < menu.find("MARCA-MENU") < menu.find("nav-lingua"))
    check("'nel menu' esce una volta sola per pagina",
          leggi("output/index.html").count("MARCA-MENU") == 1)


def test_codice_inserito_intatto():
    """The code is injected verbatim: escaping it would defeat the point."""
    print("\nil codice arriva intatto")
    home = leggi("output/index.html")
    check("il commento non e' stato trasformato in testo",
          "&lt;!-- MARCA-SOLO-HOME" not in home,
          "il codice e' stato escapato invece che inserito")


def test_id_mancante_o_morto():
    """A snippet id an article keeps after the snippet is gone is inert."""
    print("\nid che non esistono piu'")
    vivo = {"id": "prova-scelti", "enabled": True, "scope": "home_optin"}
    check("un id spuntato attiva lo snippet",
          snippet_applies(vivo, "article", ("prova-scelti",)))
    check("un id di uno snippet cancellato non attiva nulla",
          not snippet_applies(vivo, "article", ("sparito-da-tempo",)))
    check("una lista di id vuota non attiva nulla",
          not snippet_applies(vivo, "article", ()))

    # A snippet with no scope at all falls back to the narrowest one.
    senza = {"id": "x", "enabled": True}
    check("senza ambito si comporta come 'solo home'",
          snippet_applies(senza, "home", ()) and not snippet_applies(senza, "article", ()))
    check("uno snippet spento non esce mai",
          not snippet_applies({"id": "x", "scope": "home"}, "home", ()))


def test_regole_di_ambito():
    """The scope rule on its own, without building a whole site for it."""
    print("\nla regola dell'ambito, voce per voce")

    def vale(scope, page_kind, ids=()):
        return snippet_applies(
            {"id": "x", "enabled": True, "scope": scope}, page_kind, ids)

    atteso = {
        # scope            home   articolo  altre pagine
        "home":           (True,  False,    False),
        "articles":       (False, True,     False),
        "home_articles":  (True,  True,     False),
        "all":            (True,  True,     True),
    }
    for scope, (in_home, in_articolo, altrove) in atteso.items():
        check(f"'{scope}': home={in_home}",
              vale(scope, "home") is in_home)
        check(f"'{scope}': articolo={in_articolo}",
              vale(scope, "article") is in_articolo)
        check(f"'{scope}': altre pagine={altrove}",
              vale(scope, "other") is altrove)

    # The two opt-in scopes differ only on the homepage.
    check("'optin' non esce in home", not vale("optin", "home"))
    check("'home_optin' esce in home", vale("home_optin", "home"))
    for scope in ("optin", "home_optin"):
        check(f"'{scope}' esce sull'articolo spuntato",
              vale(scope, "article", ("x",)))
        check(f"'{scope}' non esce su un articolo qualsiasi",
              not vale(scope, "article", ("un-altro",)))

    # An ambito written by hand and misspelled must not make the snippet
    # disappear without a trace: it falls back to the default, "solo home".
    check("un ambito sconosciuto si comporta come 'solo home'",
          vale("ambito-inventato", "home")
          and not vale("ambito-inventato", "article"))


def test_le_spunte_sopravvivono_al_salvataggio():
    """Saving an article must not lose which snippets it had ticked."""
    print("\nle spunte restano sull'articolo")
    articolo = load_article(CON_SPUNTA)
    check("l'articolo ricorda la spunta",
          "prova-scelti" in articolo.get("custom_code_ids", []))

    # A save with the field absent (an older client) must not wipe it silently
    # into something invalid: it becomes an empty list, never None.
    copia = dict(articolo)
    del copia["custom_code_ids"]
    save_article(copia)
    ricaricato = load_article(CON_SPUNTA)
    check("senza il campo, la lista e' vuota e non rotta",
          ricaricato.get("custom_code_ids") == [])

    # Put the ticks back and check they survive a normal round trip.
    ricaricato["custom_code_ids"] = ["prova-scelti"]
    save_article(ricaricato)
    check("dopo un salvataggio normale la spunta c'e' ancora",
          load_article(CON_SPUNTA).get("custom_code_ids") == ["prova-scelti"])


def test_spento_su_un_articolo():
    """An article can say no to a snippet that goes on every article."""
    print("\nun articolo spegne un codice di serie")
    check("l'articolo che lo spegne non lo riceve",
          not contiene(f"output/posts/{CON_SPUNTA}.html", "MARCA-SPEGNIBILE"))
    check("la sua versione tradotta nemmeno",
          not contiene(f"output/en/posts/{CON_SPUNTA}.html", "MARCA-SPEGNIBILE"))
    check("gli altri articoli lo ricevono ancora",
          contiene(f"output/posts/{SENZA_SPUNTA}.html", "MARCA-SPEGNIBILE"),
          "spegnerlo su un articolo l'ha spento dappertutto")

    ovunque = {"id": "x", "enabled": True, "scope": "all"}
    check("la regola: spento sull'articolo che lo dice",
          not snippet_applies(ovunque, "article", (), ("x",)))
    check("la regola: le altre pagine non ne sanno niente",
          snippet_applies(ovunque, "home", (), ("x",))
          and snippet_applies(ovunque, "other", (), ("x",)))
    check("la regola: spegnere vince anche sulla spunta",
          not snippet_applies({"id": "x", "enabled": True, "scope": "optin"},
                              "article", ("x",), ("x",)))


def test_codice_proprio():
    """The code written inside an article goes there and nowhere else."""
    print("\ncodice scritto dentro un articolo")
    pagina = leggi(f"output/posts/{CON_SPUNTA}.html")
    check("l'articolo riceve il suo codice in cima", "MARCA-MIO-INIZIO" in pagina)
    check("l'articolo riceve il suo codice a metà", "MARCA-MIO-META" in pagina)
    check("il codice proprio spento non esce", "MARCA-NON-DEVE-USCIRE" not in pagina)
    check("la versione tradotta riceve lo stesso codice",
          contiene(f"output/en/posts/{CON_SPUNTA}.html", "MARCA-MIO-INIZIO"))

    for nome, percorso in (("home", "output/index.html"),
                           ("altro articolo", f"output/posts/{SENZA_SPUNTA}.html"),
                           ("archivio", "output/archivio.html"),
                           ("tag", "output/tag/ai.html")):
        altrove = leggi(percorso)
        check(f"non esce su {nome}",
              "MARCA-MIO-INIZIO" not in altrove and "MARCA-MIO-META" not in altrove)

    # "At the start": after the title, before the text. "Half way": inside
    # the text, with paragraphs on both sides.
    inizio = pagina.find("MARCA-MIO-INIZIO")
    testo = pagina.find('<div class="post-content">')
    check("'all'inizio' sta dopo il titolo e prima del testo",
          pagina.find("<h1") < inizio < testo)
    meta = pagina.find("MARCA-MIO-META")
    check("'a metà' sta dentro il testo",
          testo < meta < pagina.find("</article>"))
    check("'a metà' ha testo prima e dopo",
          "</p>" in pagina[testo:meta] and "<p" in pagina[meta:pagina.find("</article>")])


def test_salvataggio_dei_codici_propri():
    """The article keeps its own code and its switched-off snippets."""
    print("\nil salvataggio conserva i codici dell'articolo")
    articolo = load_article(CON_SPUNTA)
    propri = articolo.get("custom_code", [])
    check("i codici propri sono salvati, nell'ordine",
          [s.get("id") for s in propri] == ["art-inizio", "art-meta", "art-spento"])
    check("con posizione e consenso",
          propri[1].get("position") == "article_middle" and propri[1].get("consent") == "marketing")
    check("il codice spento resta spento", propri[2].get("enabled") is False)
    check("gli spegnimenti sono salvati",
          articolo.get("custom_code_off_ids") == ["prova-spegnibile"])

    # What a hand-edited file or an old client can send: something that is
    # not a card, a card without an id, a second card with an id taken.
    copia = dict(articolo)
    copia["custom_code"] = propri + ["rotto", {"code": "<!-- senza id -->"},
                                     {"id": "art-inizio", "code": "<!-- doppio -->"}]
    save_article(copia)
    salvati = load_article(CON_SPUNTA)["custom_code"]
    ids = [s["id"] for s in salvati]
    check("le voci che non sono codici vengono scartate", len(salvati) == len(propri) + 2)
    check("ogni codice ha un id, e nessuno è ripetuto",
          all(ids) and len(set(ids)) == len(ids), str(ids))
    check("gli id nuovi sono quelli dell'articolo",
          all(i.startswith("art-") for i in ids[len(propri):]), str(ids))
    check("i codici esistenti tengono il loro id", ids[:len(propri)] == ["art-inizio", "art-meta", "art-spento"])

    copia["custom_code"] = propri
    save_article(copia)


def test_consenso():
    """With the banner on, the code that needs consent waits for it."""
    print("\nconsenso: il codice aspetta la scelta del visitatore")
    config = load_config()
    config["consent"] = {"enabled": True, "text": "", "text_en": "",
                         "privacy_url": "https://example.org/privacy", "version": 3}
    config["analytics_id"] = "G-PROVA12345"
    config["custom_code"] = SNIPPET_DI_PROVA + [
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
    solo_home = home.find("MARCA-SOLO-HOME")
    check("il codice necessario parte subito",
          solo_home != -1 and "<template" not in home[solo_home - 40:solo_home])
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
          in leggi(f"output/posts/{CON_SPUNTA}.html"))

    ads = OUTPUT_DIR / "ads.txt"
    check("ads.txt viene pubblicato",
          ads.exists() and ads.read_text(encoding="utf-8") == config["ads_txt"] + "\n")

    # Banner on, but nothing that needs it: no banner at all.
    config["analytics_id"] = ""
    config["custom_code"] = SNIPPET_DI_PROVA
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
    articolo = load_article(CON_SPUNTA)
    if articolo is None:
        print("articolo di prova assente: salto")
        return

    # We are about to rewrite config.json and one article, so we remember
    # exactly how we found them - including config.json not existing at all,
    # which is the normal state of a fresh checkout. The article is kept as
    # its raw text: saving it again would bump date_modified, and a test has
    # no business changing when an article was last edited.
    config_originale = None
    if CONFIG_FILE.exists():
        config_originale = CONFIG_FILE.read_text(encoding="utf-8")
    file_articolo = POSTS_DIR / f"{CON_SPUNTA}.json"
    articolo_originale = file_articolo.read_text(encoding="utf-8")

    config = load_config()
    config["custom_code"] = SNIPPET_DI_PROVA
    save_config(config)
    articolo["custom_code_ids"] = ["prova-scelti", "prova-solo-scelti"]
    articolo["custom_code_off_ids"] = ["prova-spegnibile"]
    articolo["custom_code"] = CODICE_PROPRIO
    save_article(articolo)
    build()

    try:
        test_ambito_delle_pagine()
        test_posizione_nella_pagina()
        test_codice_inserito_intatto()
        test_id_mancante_o_morto()
        test_regole_di_ambito()
        test_le_spunte_sopravvivono_al_salvataggio()
        test_spento_su_un_articolo()
        test_codice_proprio()
        test_salvataggio_dei_codici_propri()
        # Last: it rebuilds the site with other settings.
        test_consenso()
    finally:
        file_articolo.write_text(articolo_originale, encoding="utf-8")
        if config_originale is None:
            CONFIG_FILE.unlink(missing_ok=True)
        else:
            CONFIG_FILE.write_text(config_originale, encoding="utf-8")
        build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
