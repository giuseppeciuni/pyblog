#!/usr/bin/env python3
"""
Checks on the code placed at a point chosen on the page.

    python3 tests/test_codice_punto.py

The author clicks a block of the real page; the snippet keeps a CSS selector
and the side. The generated page carries the code inert, naming the block,
and site.js moves it there. These checks cover the generated side: what the
page carries, when, and what it refuses. The configuration is put back.
"""
import copy
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.articles import load_articles  # noqa: E402
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


SELETTORE = "div.post-content > p:nth-of-type(2)"


def codice(**altro):
    snippet = {"id": "punto-1", "name": "Banner", "enabled": True, "scope": "articles",
               "position": "anchor", "anchor_selector": SELETTORE, "anchor_where": "after",
               "anchor_label": "Dopo · Paragrafo 2 del testo", "anchor_page": "article",
               "consent": "necessary", "code": '<div class="banner">B</div>'}
    snippet.update(altro)
    return snippet


def modelli(pagina):
    return re.findall(r'<template data-pb-ancora="([^"]*)" data-pb-dove="([a-z]+)"([^>]*)>(.*?)</template>',
                      pagina, re.DOTALL)


def test_pagina():
    print("\nla pagina porta il codice col suo punto")
    articoli = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = [codice()]
    pagina = build.generate_article_page(articoli[0], "it", articoli)
    trovati = modelli(pagina)
    check("un modello col selettore escapato e il lato", len(trovati) == 1
          and trovati[0][0] == "div.post-content &gt; p:nth-of-type(2)" and trovati[0][1] == "after",
          str(trovati))
    check("il codice dentro è intatto", trovati and trovati[0][3] == '<div class="banner">B</div>')
    check("senza consenso da chiedere non aspetta niente", trovati and "data-pb-consenso" not in trovati[0][2])
    check("sta in fondo alla pagina, non nel testo",
          pagina.find("data-pb-ancora") > pagina.find("</main>"))
    home = build.generate_homepage(articoli, "it")
    check("la home non lo ha (pagine: solo articoli)", "data-pb-ancora" not in home)

    CONFIG["consent"] = {"enabled": True, "version": 1}
    CONFIG["custom_code"] = [codice(consent="marketing")]
    pagina = build.generate_article_page(articoli[0], "it", articoli)
    trovati = modelli(pagina)
    check("con il banner acceso, la pubblicità aspetta il consenso nel suo modello",
          trovati and 'data-pb-consenso="marketing"' in trovati[0][2], str(trovati))
    check("e la pagina chiede il consenso alla pubblicità", '"marketing"' in pagina)

    CONFIG["custom_code"] = [codice(anchor_where="before")]
    check("il lato prima", modelli(build.generate_article_page(articoli[0], "it", articoli))[0][1] == "before")
    CONFIG["custom_code"] = [codice(anchor_where="dentro")]
    check("un lato sconosciuto diventa dopo",
          modelli(build.generate_article_page(articoli[0], "it", articoli))[0][1] == "after")


def test_rifiuti():
    print("\ncosa non passa")
    articoli = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    for selettore, perche in (("", "vuoto"), ('x"><script>alert(1)</script>', "con un tag"),
                              ("a\nb", "con un a capo"), ("p" * 500, "troppo lungo"), (5, "non testo")):
        CONFIG["custom_code"] = [codice(anchor_selector=selettore)]
        pagina = build.generate_article_page(articoli[0], "it", articoli)
        check(f"un selettore {perche} non produce niente", "data-pb-ancora" not in pagina)
    CONFIG["custom_code"] = [codice(enabled=False)]
    check("spento non esce", "data-pb-ancora" not in build.generate_article_page(articoli[0], "it", articoli))
    CONFIG["custom_code"] = [codice(anchor_selector='p[title="x"]')]
    pagina = build.generate_article_page(articoli[0], "it", articoli)
    check("le virgolette restano dentro l'attributo", 'data-pb-ancora="p[title=&quot;x&quot;]"' in pagina)


def test_codice_dell_articolo():
    print("\ncodice scritto nell'articolo")
    articoli = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = []
    art = dict(articoli[0], custom_code=[codice(id="art-1", code="<em>solo qui</em>")])
    pagina = build.generate_article_page(art, "it", articoli)
    check("anche il codice di un articolo va al suo punto",
          any(m[3] == "<em>solo qui</em>" for m in modelli(pagina)))


def test_pagina_senza_codici():
    print("\nla pagina su cui si sceglie il punto")
    articoli = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = [codice(), codice(id="h", position="head", scope="all", code="<script>traccia()</script>")]
    build.CODE_SWITCH.off = True
    try:
        pagina = build.generate_article_page(articoli[0], "it", articoli)
    finally:
        build.CODE_SWITCH.off = False
    check("è generata senza nessun codice esterno",
          "data-pb-ancora" not in pagina and "traccia()" not in pagina)
    check("e subito dopo i codici tornano",
          "traccia()" in build.generate_article_page(articoli[0], "it", articoli))
    check("la rotta è tra quelle dell'amministrazione, che chiedono l'accesso",
          "/scegli-punto" in server.ADMIN_GET_ROUTES)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    check("nginx la porta a Python", "scegli-punto" in nginx)


def test_scheda():
    print("\nla scheda nelle impostazioni")
    scheda = server.custom_code_card(codice(), 0, "it")
    check("la posizione «punto sulla pagina» è scelta", 'value="anchor" selected' in scheda)
    check("il riquadro del punto è visibile e dice quale",
          'class="codice-punto">' in scheda and "Dopo · Paragrafo 2 del testo" in scheda)
    check("il riassunto della scheda chiusa dice il punto",
          "Dopo · Paragrafo 2 del testo · Solo gli articoli" in server.snippet_summary(codice(), "it"))
    altra = server.custom_code_card(codice(position="head"), 0, "it")
    check("con un'altra posizione il riquadro è nascosto ma il punto resta",
          'class="codice-punto" hidden>' in altra and SELETTORE.replace(">", "&gt;") in altra)


def main():
    salvata = copy.deepcopy(CONFIG)
    try:
        test_pagina()
        test_rifiuti()
        test_codice_dell_articolo()
        test_pagina_senza_codici()
        test_scheda()
    finally:
        CONFIG.clear()
        CONFIG.update(salvata)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
