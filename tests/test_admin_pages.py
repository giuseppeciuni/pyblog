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
HOSTILE_TITLE = 'Titolo con "virgolette", un\'apostrofe e <b>tag</b> & simboli'

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


class CollectorHandler(html.parser.HTMLParser):
    """Collects every event-handler attribute the HTML parser really sees."""

    def __init__(self):
        super().__init__()
        self.handler = []
        self.stray_attributes = []
        self.tags_seen = []

    def handle_starttag(self, tag, attrs):
        self.tags_seen.append(tag)
        for name, value in attrs:
            if name.startswith("on"):
                self.handler.append((name, value))
            elif value is None and ("(" in name or ")" in name or '"' in name):
                # An attribute NAME that looks like code is what a value
                # escaping its own quotes leaves behind.
                self.stray_attributes.append(name)

    handle_startendtag = handle_starttag


def handler_problems(text):
    """Return the list of broken event handlers in a page."""
    parser = CollectorHandler()
    parser.feed(text)
    problems = []
    for name, value in parser.handler:
        if value is None:
            problems.append(f"{name} senza valore")
            continue
        if value.count("(") != value.count(")"):
            problems.append(f'{name}="{value}" parentesi sbilanciate')
        elif not value.rstrip().endswith((")", ";")):
            problems.append(f'{name}="{value}" troncato')
    for stray in parser.stray_attributes:
        problems.append(f"attributo spurio {stray!r}")
    return problems, len(parser.handler)


def admin_pages():
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


def test_handlers_intact():
    """Every inline handler must survive the HTML parser whole."""
    print("\nevent handler")
    for language in ("it", "en"):
        config.CONFIG["admin_language"] = language
        for name, text in admin_pages().items():
            problems, how_many = handler_problems(text)
            check(f"{language} / {name}: {how_many} handler intatti",
                  len(problems) == 0, "; ".join(problems[:3]))
    config.CONFIG["admin_language"] = "it"


def test_dashboard_topics():
    """
    The dashboard buttons must carry the real slug and title as arguments.

    Escaping them correctly is not enough: the values also have to arrive
    unchanged once the HTML parser has decoded the attribute.
    """
    print("\nargomenti dei pulsanti della dashboard")
    parser = CollectorHandler()
    parser.feed(server.admin_page(load_articles(), "TOKEN"))

    publish = [v for n, v in parser.handler if v and v.startswith("changeStatus(")]
    delete_entry = [v for n, v in parser.handler if v and v.startswith("deleteArticle(")]
    check("ogni articolo ha il pulsante di stato", len(publish) == len(load_articles()))
    check("ogni articolo ha il pulsante elimina", len(delete_entry) == len(load_articles()))

    expected_slug = '"titolo-ostile"'
    check("lo slug arriva come stringa JavaScript valida",
          any(expected_slug in v for v in publish), str(publish))
    check("changeStatus riceve tre argomenti",
          all(v.count(",") == 2 for v in publish), str(publish))
    check("il titolo ostile arriva intero, non troncato",
          any("un\'apostrofe e" in v and "simboli" in v for v in delete_entry), str(delete_entry))
    check("le virgolette del titolo restano dentro la stringa JavaScript",
          any('\\"virgolette\\"' in v for v in delete_entry), str(delete_entry))

    # The title carries a <b> tag. Inside the handler it is just text - the
    # confirmation dialog writes it with textContent - but in the page itself
    # it must never become an element. That is what to check: not the string
    # passed to JavaScript, but whether the HTML parser built a tag out of it.
    check("il titolo non produce un elemento <b> nella pagina",
          "b" not in parser.tags_seen, str([t for t in parser.tags_seen if t == "b"]))
    check("il titolo compare escapato nel testo visibile",
          "&lt;b&gt;tag&lt;/b&gt;" in server.admin_page(load_articles(), "TOKEN"))


def test_json_iniettato():
    """The JSON blocks handed to the browser must be valid JSON."""
    import json
    import re
    print("\nblocchi JSON iniettati")
    for language in ("it", "en"):
        config.CONFIG["admin_language"] = language
        for name, text in admin_pages().items():
            ok = True
            for label in ("PB_I18N", "PB_CSRF", "PB_PAGE"):
                found = re.search(r"window\." + label + r" = (.*?);\n", text, re.S)
                if found is None:
                    ok = False
                    continue
                try:
                    json.loads(found.group(1).replace("<\\/", "</"))
                except ValueError:
                    ok = False
            check(f"{language} / {name}: i tre blocchi sono JSON valido", ok)
    config.CONFIG["admin_language"] = "it"


def test_no_placeholder_left():
    """A template placeholder left behind means a missing value."""
    import re
    print("\nsegnaposto dei template")
    for language in ("it", "en"):
        config.CONFIG["admin_language"] = language
        for name, text in admin_pages().items():
            remaining = set(re.findall(r"\$\{?[a-z_]{3,}\}?", text))
            check(f"{language} / {name}: nessun $segnaposto", len(remaining) == 0, str(remaining))
    config.CONFIG["admin_language"] = "it"


def test_exported_i18n_keys():
    """
    Every key admin.js asks t() for must travel in window.PB_I18N.

    t() returns the key itself when it is missing, so a forgotten one does
    not raise: the button simply shows "js_image_resized_local" to the
    author, in both languages, and nothing in the build complains. That is
    exactly how one of these reached production once.
    """
    import re
    print("\nchiavi di traduzione usate dal JavaScript")
    source = (config.STATIC_DIR / "admin.js").read_text(encoding="utf-8")
    # The call is written t('chiave'); the prefixes below are the families
    # that exist, which also keeps out the createElement('div') lookalikes.
    used = set()
    for key in re.findall(r"\bt\('([a-z0-9_]+)'\)", source):
        if key.startswith(("js_", "admin_", "seo_", "err_", "img_", "consent_")):
            used.add(key)
    exported = set(server.JS_TRANSLATION_KEYS)
    exported.add("js_home_intro_placeholder_it")
    exported.add("js_home_intro_placeholder_en")
    missing = sorted(used - exported)
    check(f"tutte esportate ({len(used)} chiavi usate)",
          len(missing) == 0, "mancanti: " + ", ".join(missing))


def main():
    created = save_article({
        "title": HOSTILE_TITLE, "slug": "titolo-ostile",
        "content": "<p>Contenuto di prova.</p>", "status": "draft", "tags": "Test"})
    try:
        test_handlers_intact()
        test_dashboard_topics()
        test_json_iniettato()
        test_no_placeholder_left()
        test_exported_i18n_keys()
    finally:
        delete_article(created)

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
