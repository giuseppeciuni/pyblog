#!/usr/bin/env python3
"""
Checks on the generated administration pages.

    python3 tests/test_admin_pages.py

These exist because of a bug that a substring search could never have caught.
The dashboard rendered

    onclick="changeStatus(this, "un-articolo", "published")"

which CONTAINS exactly the text you would grep for, and is still broken: the
attribute is delimited by double quotes and json.dumps writes double quotes,
so the HTML parser ends the attribute at the first one and the handler is cut
in half. "Publish" and "Delete" silently did nothing.

So these tests parse the pages instead of searching them, and they run against
an article whose title is full of the characters that break naive escaping.
"""
import html
import html.parser
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import config, server  # noqa: E402
from core.articles import (delete_article, load_article,  # noqa: E402
                           load_articles, save_article)

# A title carrying every character that has ever broken an escaping scheme:
# double quotes end an HTML attribute, the apostrophe ends a JavaScript
# string, and the tag would inject markup.
TITOLO_OSTILE = 'Titolo con "virgolette", un\'apostrofe e <b>tag</b> & simboli'

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


class RaccoglitoreHandler(html.parser.HTMLParser):
    """Collects every event-handler attribute the HTML parser really sees."""

    def __init__(self):
        super().__init__()
        self.handler = []
        self.attributi_spuri = []
        self.tag_visti = []

    def handle_starttag(self, tag, attrs):
        self.tag_visti.append(tag)
        for nome, valore in attrs:
            if nome.startswith("on"):
                self.handler.append((nome, valore))
            elif valore is None and ("(" in nome or ")" in nome or '"' in nome):
                # An attribute NAME that looks like code is what a value
                # escaping its own quotes leaves behind.
                self.attributi_spuri.append(nome)

    handle_startendtag = handle_starttag


def problemi_handler(testo):
    """Return the list of broken event handlers in a page."""
    parser = RaccoglitoreHandler()
    parser.feed(testo)
    problemi = []
    for nome, valore in parser.handler:
        if valore is None:
            problemi.append(f"{nome} senza valore")
            continue
        if valore.count("(") != valore.count(")"):
            problemi.append(f'{nome}="{valore}" parentesi sbilanciate')
        elif not valore.rstrip().endswith((")", ";")):
            problemi.append(f'{nome}="{valore}" troncato')
    for spurio in parser.attributi_spuri:
        problemi.append(f"attributo spurio {spurio!r}")
    return problemi, len(parser.handler)


def pagine_admin():
    """Every administration page, rendered."""
    return {
        "dashboard": server.admin_page(load_articles(), "TOKEN"),
        "editor": server.editor_page(load_article("titolo-ostile"), "TOKEN"),
        "editor nuovo": server.editor_page(None, "TOKEN"),
        "impostazioni": server.config_page("TOKEN"),
        "login": server.login_page("Password errata."),
        "crea password": server.set_password_page(""),
        "cambio password": server.change_password_page("TOKEN"),
    }


def test_handler_intatti():
    """Every inline handler must survive the HTML parser whole."""
    print("\nevent handler")
    for lingua in ("it", "en"):
        config.CONFIG["admin_language"] = lingua
        for nome, testo in pagine_admin().items():
            problemi, quanti = problemi_handler(testo)
            check(f"{lingua} / {nome}: {quanti} handler intatti",
                  len(problemi) == 0, "; ".join(problemi[:3]))
    config.CONFIG["admin_language"] = "it"


def test_argomenti_dashboard():
    """
    The dashboard buttons must carry the real slug and title as arguments.

    Escaping them correctly is not enough: the values also have to arrive
    unchanged once the HTML parser has decoded the attribute.
    """
    print("\nargomenti dei pulsanti della dashboard")
    parser = RaccoglitoreHandler()
    parser.feed(server.admin_page(load_articles(), "TOKEN"))

    pubblica = [v for n, v in parser.handler if v and v.startswith("changeStatus(")]
    elimina = [v for n, v in parser.handler if v and v.startswith("deleteArticle(")]
    check("ogni articolo ha il pulsante di stato", len(pubblica) == len(load_articles()))
    check("ogni articolo ha il pulsante elimina", len(elimina) == len(load_articles()))

    atteso_slug = '"titolo-ostile"'
    check("lo slug arriva come stringa JavaScript valida",
          any(atteso_slug in v for v in pubblica), str(pubblica))
    check("changeStatus riceve tre argomenti",
          all(v.count(",") == 2 for v in pubblica), str(pubblica))
    check("il titolo ostile arriva intero, non troncato",
          any("un\'apostrofe e" in v and "simboli" in v for v in elimina), str(elimina))
    check("le virgolette del titolo restano dentro la stringa JavaScript",
          any('\\"virgolette\\"' in v for v in elimina), str(elimina))

    # The title carries a <b> tag. Inside the handler it is just text - the
    # confirmation dialog writes it with textContent - but in the page itself
    # it must never become an element. That is what to check: not the string
    # passed to JavaScript, but whether the HTML parser built a tag out of it.
    check("il titolo non produce un elemento <b> nella pagina",
          "b" not in parser.tag_visti, str([t for t in parser.tag_visti if t == "b"]))
    check("il titolo compare escapato nel testo visibile",
          "&lt;b&gt;tag&lt;/b&gt;" in server.admin_page(load_articles(), "TOKEN"))


def test_json_iniettato():
    """The JSON blocks handed to the browser must be valid JSON."""
    import json
    import re
    print("\nblocchi JSON iniettati")
    for lingua in ("it", "en"):
        config.CONFIG["admin_language"] = lingua
        for nome, testo in pagine_admin().items():
            ok = True
            for etichetta in ("PB_I18N", "PB_CSRF", "PB_PAGE"):
                trovato = re.search(r"window\." + etichetta + r" = (.*?);\n", testo, re.S)
                if trovato is None:
                    ok = False
                    continue
                try:
                    json.loads(trovato.group(1).replace("<\\/", "</"))
                except ValueError:
                    ok = False
            check(f"{lingua} / {nome}: i tre blocchi sono JSON valido", ok)
    config.CONFIG["admin_language"] = "it"


def test_nessun_segnaposto_rimasto():
    """A template placeholder left behind means a missing value."""
    import re
    print("\nsegnaposto dei template")
    for lingua in ("it", "en"):
        config.CONFIG["admin_language"] = lingua
        for nome, testo in pagine_admin().items():
            rimasti = set(re.findall(r"\$\{?[a-z_]{3,}\}?", testo))
            check(f"{lingua} / {nome}: nessun $segnaposto", len(rimasti) == 0, str(rimasti))
    config.CONFIG["admin_language"] = "it"


def test_chiavi_i18n_esportate():
    """
    Every key admin.js asks t() for must travel in window.PB_I18N.

    t() returns the key itself when it is missing, so a forgotten one does
    not raise: the button simply shows "js_image_resized_local" to the
    author, in both languages, and nothing in the build complains. That is
    exactly how one of these reached production once.
    """
    import re
    print("\nchiavi di traduzione usate dal JavaScript")
    sorgente = (config.STATIC_DIR / "admin.js").read_text(encoding="utf-8")
    # The call is written t('chiave'); the prefixes below are the families
    # that exist, which also keeps out the createElement('div') lookalikes.
    usate = set()
    for chiave in re.findall(r"\bt\('([a-z0-9_]+)'\)", sorgente):
        if chiave.startswith(("js_", "admin_", "seo_", "err_", "img_", "consenso_")):
            usate.add(chiave)
    esportate = set(server.JS_TRANSLATION_KEYS)
    esportate.add("js_home_intro_placeholder_it")
    esportate.add("js_home_intro_placeholder_en")
    mancanti = sorted(usate - esportate)
    check(f"tutte esportate ({len(usate)} chiavi usate)",
          len(mancanti) == 0, "mancanti: " + ", ".join(mancanti))


def main():
    creato = save_article({
        "title": TITOLO_OSTILE, "slug": "titolo-ostile",
        "content": "<p>Contenuto di prova.</p>", "status": "draft", "tags": "Test"})
    try:
        test_handler_intatti()
        test_argomenti_dashboard()
        test_json_iniettato()
        test_nessun_segnaposto_rimasto()
        test_chiavi_i18n_esportate()
    finally:
        delete_article(creato)

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
