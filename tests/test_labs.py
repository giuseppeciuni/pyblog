#!/usr/bin/env python3
"""
Checks on the labs.

    python3 tests/test_labs.py

A lab is an article that puts another one into practice with code. It opens
with a box linking to the project, the article it refers to points to it,
and the labs have a page of their own and an entry in the menu. Nothing is
written to disk, and the configuration is put back as it was at the end.
"""
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.articles import article_from_data  # noqa: E402
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


def articolo(numero, **extra):
    art = {"title": f"Articolo {numero}", "slug": f"articolo-{numero}",
           "content": "<p>Testo dell'articolo.</p>", "status": "published",
           "date": f"2026-01-{numero:02d}", "tags": "Prova"}
    art.update(extra)
    return art


TEORIA = articolo(1)
LAB = articolo(2, kind="lab", lab_of="articolo-1", stack="Python 3.12, <LiteLLM>",
               repo_url="https://github.com/esempio/lab", title="Lab uno")
LAB_SENZA = articolo(3, kind="lab", repo_url="javascript:alert(1)", title="Lab due")
ARTICOLI = [articolo(4), LAB_SENZA, LAB, TEORIA]


def test_dati():
    print("\ni dati dell'articolo")
    salvato = article_from_data({"title": "T", "kind": "lab", "lab_of": " articolo-1 ",
                                 "repo_url": " https://github.com/x/y ", "stack": " Python "}, "t")
    check("i campi del lab vengono salvati puliti",
          salvato["kind"] == "lab" and salvato["lab_of"] == "articolo-1"
          and salvato["repo_url"] == "https://github.com/x/y" and salvato["stack"] == "Python")
    check("un tipo sconosciuto e' un articolo normale",
          article_from_data({"title": "T", "kind": "altro"}, "t")["kind"] == "")
    check("senza dati non e' un lab", article_from_data({"title": "T"}, "t")["kind"] == "")


def test_pagina_lab():
    print("\nla pagina di un lab")
    build.note_labs(ARTICOLI)
    pagina = build.generate_article_page(LAB, "it", ARTICOLI)
    riquadro = pagina.split('<aside class="lab-box"')[1].split("</aside>")[0]
    check("apre con il link al progetto su GitHub",
          '<a class="lab-codice" href="https://github.com/esempio/lab" rel="noopener">'
          'Il codice su GitHub' in riquadro, riquadro)
    check("dice con cosa e' fatto, senza far passare codice HTML",
          "Fatto con: Python 3.12, &lt;LiteLLM&gt;" in riquadro)
    check("porta all'articolo che mette in pratica",
          'Mette in pratica: <a href="/posts/articolo-1.html">Articolo 1</a>' in riquadro)
    check("il riquadro sta prima del testo",
          pagina.index("lab-box") < pagina.index('class="post-content"'))
    senza = build.generate_article_page(LAB_SENZA, "it", ARTICOLI)
    riquadro = senza.split('<aside class="lab-box"')[1].split("</aside>")[0]
    check("un indirizzo non valido non diventa un link", "<a " not in riquadro, riquadro)

    teoria = build.generate_article_page(TEORIA, "it", ARTICOLI)
    fine = teoria.split('class="lab-box lab-fine"')[1].split("</aside>")[0]
    check("l'articolo di riferimento segnala il suo lab in fondo al testo",
          '<a href="/posts/articolo-2.html">Lab uno</a>' in fine
          and "https://github.com/esempio/lab" in fine
          and teoria.index("lab-fine") > teoria.index('class="post-content"'))
    check("un articolo senza lab non ha riquadri",
          "lab-box" not in build.generate_article_page(ARTICOLI[0], "it", ARTICOLI))


def test_pagina_labs_e_menu():
    print("\nla pagina Labs e il menu")
    build.note_labs(ARTICOLI)
    pagina = build.generate_labs_page(ARTICOLI, "it")
    elenco = pagina.split('<div class="articles-list">')[1].split("</section>")[0]
    check("elenca i lab e solo quelli",
          "articolo-2.html" in elenco and "articolo-3.html" in elenco
          and "articolo-1.html" not in elenco and "articolo-4.html" not in elenco)
    check("ha titolo e indirizzo canonico",
          "<title>Labs" in pagina and 'rel="canonical" href="'
          + CONFIG["base_url"].rstrip("/") + '/labs.html"' in pagina)
    home = build.generate_homepage(ARTICOLI, "it")
    check("con dei lab online il menu ha Labs",
          '<a href="/labs.html">Labs</a>' in home.split("</nav>")[0])
    check("negli elenchi un lab ha la sua etichetta",
          home.count('<p class="art-kicker">Lab</p>') == 2)
    check("in inglese, senza lab tradotti, niente voce e niente pagina",
          "labs.html" not in build.generate_homepage(ARTICOLI, "en").split("</nav>")[0]
          and "/en/labs.html" not in build.generate_sitemap(ARTICOLI))
    check("la sitemap elenca la pagina", "/labs.html</loc>" in build.generate_sitemap(ARTICOLI))
    solo_articoli = [TEORIA, ARTICOLI[0]]
    build.note_labs(solo_articoli)
    check("senza lab il menu non la elenca",
          "labs.html" not in build.generate_homepage(solo_articoli, "it").split("</nav>")[0]
          and "labs.html" not in build.generate_sitemap(solo_articoli))


def test_editor():
    print("\nl'editor")
    originale = server.load_articles
    server.load_articles = lambda: ARTICOLI
    try:
        pagina = server.editor_page(LAB, "csrf")
        normale = server.editor_page(TEORIA, "csrf")
    finally:
        server.load_articles = originale
    check("la spunta e i campi del lab hanno i valori dell'articolo",
          'id="kind_lab" checked' in pagina and '<div id="campi-lab" >' in pagina
          and 'id="repo_url" value="https://github.com/esempio/lab"' in pagina
          and 'id="stack" value="Python 3.12, &lt;LiteLLM&gt;"' in pagina)
    scelta = pagina.split('<select id="lab_of"')[1].split("</select>")[0]
    check("l'articolo di riferimento si sceglie tra gli articoli che non sono lab",
          '<option value="articolo-1" selected>Articolo 1</option>' in scelta
          and "articolo-4" in scelta and "articolo-3" not in scelta
          and 'value="articolo-2"' not in scelta, scelta)
    check("su un articolo normale i campi del lab sono nascosti",
          'id="kind_lab" ' in normale and 'id="kind_lab" checked' not in normale
          and '<div id="campi-lab" hidden>' in normale)
    script = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("il salvataggio manda i campi del lab",
          "kind: document.getElementById('kind_lab').checked ? 'lab' : ''" in script
          and "repo_url: document.getElementById('repo_url').value" in script)


def main():
    salvata = copy.deepcopy(CONFIG)
    try:
        CONFIG["language"] = "it"
        test_dati()
        test_pagina_lab()
        test_pagina_labs_e_menu()
        test_editor()
    finally:
        CONFIG.clear()
        CONFIG.update(salvata)
        build.LABS_ONLINE.clear()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
