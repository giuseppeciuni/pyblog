#!/usr/bin/env python3
"""
Checks on the code placed at a point chosen on the page.

    python3 tests/test_code_anchor_point.py

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


SELECTOR = "div.post-content > p:nth-of-type(2)"


def code_text(**other_value):
    snippet = {"id": "punto-1", "name": "Banner", "enabled": True, "scope": "articles",
               "position": "anchor", "anchor_selector": SELECTOR, "anchor_where": "after",
               "anchor_label": "Dopo · Paragrafo 2 del testo", "anchor_page": "article",
               "consent": "necessary", "code": '<div class="banner">B</div>'}
    snippet.update(other_value)
    return snippet


def templates_found(page_html):
    return re.findall(r'<template data-pb-anchor="([^"]*)" data-pb-where="([a-z]+)"([^>]*)>(.*?)</template>',
                      page_html, re.DOTALL)


def test_page():
    print("\nla pagina porta il codice col suo punto")
    article_list = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = [code_text()]
    page_html = build.generate_article_page(article_list[0], "it", article_list)
    found_items = templates_found(page_html)
    check("un modello col selettore escapato e il lato", len(found_items) == 1
          and found_items[0][0] == "div.post-content &gt; p:nth-of-type(2)" and found_items[0][1] == "after",
          str(found_items))
    check("il codice dentro è intatto", found_items and found_items[0][3] == '<div class="banner">B</div>')
    check("senza consenso da chiedere non aspetta niente", found_items and "data-pb-consent" not in found_items[0][2])
    check("sta in fondo alla pagina, non nel testo",
          page_html.find("data-pb-anchor") > page_html.find("</main>"))
    home = build.generate_homepage(article_list, "it")
    check("la home non lo ha (pagine: solo articoli)", "data-pb-anchor" not in home)

    CONFIG["consent"] = {"enabled": True, "version": 1}
    CONFIG["custom_code"] = [code_text(consent="marketing")]
    page_html = build.generate_article_page(article_list[0], "it", article_list)
    found_items = templates_found(page_html)
    check("con il banner acceso, la pubblicità aspetta il consenso nel suo modello",
          found_items and 'data-pb-consent="marketing"' in found_items[0][2], str(found_items))
    check("e la pagina chiede il consenso alla pubblicità", '"marketing"' in page_html)

    CONFIG["custom_code"] = [code_text(anchor_where="before")]
    check("il lato prima", templates_found(build.generate_article_page(article_list[0], "it", article_list))[0][1] == "before")
    CONFIG["custom_code"] = [code_text(anchor_where="dentro")]
    check("un lato sconosciuto diventa dopo",
          templates_found(build.generate_article_page(article_list[0], "it", article_list))[0][1] == "after")


def test_refusals():
    print("\ncosa non passa")
    article_list = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    for selector, reason in (("", "vuoto"), ('x"><script>alert(1)</script>', "con un tag"),
                              ("a\nb", "con un a capo"), ("p" * 500, "troppo lungo"), (5, "non testo")):
        CONFIG["custom_code"] = [code_text(anchor_selector=selector)]
        page_html = build.generate_article_page(article_list[0], "it", article_list)
        check(f"un selettore {reason} non produce niente", "data-pb-anchor" not in page_html)
    CONFIG["custom_code"] = [code_text(enabled=False)]
    check("spento non esce", "data-pb-anchor" not in build.generate_article_page(article_list[0], "it", article_list))
    CONFIG["custom_code"] = [code_text(anchor_selector='p[title="x"]')]
    page_html = build.generate_article_page(article_list[0], "it", article_list)
    check("le virgolette restano dentro l'attributo", 'data-pb-anchor="p[title=&quot;x&quot;]"' in page_html)


def test_article_code():
    print("\ncodice scritto nell'articolo")
    article_list = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = []
    art = dict(article_list[0], custom_code=[code_text(id="art-1", code="<em>solo qui</em>")])
    page_html = build.generate_article_page(art, "it", article_list)
    check("anche il codice di un articolo va al suo punto",
          any(m[3] == "<em>solo qui</em>" for m in templates_found(page_html)))


def test_page_without_code():
    print("\nla pagina su cui si sceglie il punto")
    article_list = [a for a in load_articles() if a.get("status") == "published"]
    CONFIG["consent"] = {"enabled": False}
    CONFIG["custom_code"] = [code_text(), code_text(id="h", position="head", scope="all", code="<script>traccia()</script>")]
    build.CODE_SWITCH.off = True
    try:
        page_html = build.generate_article_page(article_list[0], "it", article_list)
    finally:
        build.CODE_SWITCH.off = False
    check("è generata senza nessun codice esterno",
          "data-pb-anchor" not in page_html and "traccia()" not in page_html)
    check("e subito dopo i codici tornano",
          "traccia()" in build.generate_article_page(article_list[0], "it", article_list))
    check("la rotta è tra quelle dell'amministrazione, che chiedono l'accesso",
          "/pick-point" in server.ADMIN_GET_ROUTES)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    check("nginx la porta a Python", "|pick-point|" in nginx)


def test_card():
    print("\nla scheda nelle impostazioni")
    card = server.custom_code_card(code_text(), 0, "it")
    check("la posizione «punto sulla pagina» è scelta", 'value="anchor" selected' in card)
    check("il riquadro del punto è visibile e dice quale",
          'class="code-point">' in card and "Dopo · Paragrafo 2 del testo" in card)
    check("il riassunto della scheda chiusa dice il punto",
          "Dopo · Paragrafo 2 del testo · Solo gli articoli" in server.snippet_summary(code_text(), "it"))
    other = server.custom_code_card(code_text(position="head"), 0, "it")
    check("con un'altra posizione il riquadro è nascosto ma il punto resta",
          'class="code-point" hidden>' in other and SELECTOR.replace(">", "&gt;") in other)


def main():
    saved_page = copy.deepcopy(CONFIG)
    try:
        test_page()
        test_refusals()
        test_article_code()
        test_page_without_code()
        test_card()
    finally:
        CONFIG.clear()
        CONFIG.update(saved_page)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
