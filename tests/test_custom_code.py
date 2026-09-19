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

    dopo_body = home.split("<body>")[1]
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
    save_article(articolo)
    build()

    try:
        test_ambito_delle_pagine()
        test_posizione_nella_pagina()
        test_codice_inserito_intatto()
        test_id_mancante_o_morto()
        test_regole_di_ambito()
        test_le_spunte_sopravvivono_al_salvataggio()
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
