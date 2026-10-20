#!/usr/bin/env python3
"""
Checks on the layout of the administration area.

    python3 tests/test_admin_layout.py

The side menu, the sections of the Settings and the labels of the fields.
The pages are parsed, not searched: a label is only a label if its "for"
names an id that exists, and a section is only reachable if the menu links
to the name the page answers to.
"""
import html.parser
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import config, server  # noqa: E402
from core.articles import load_articles  # noqa: E402

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


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "source", "track", "wbr"}


class ParsedPage(html.parser.HTMLParser):
    """Collects the elements of a page with the labels that wrap them."""

    def __init__(self):
        super().__init__()
        self.elements = []
        self.opened = []
        self.labels_for = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        inside_label = any(e["tag"] == "label" for e in self.opened)
        element = {"tag": tag, "attrs": attributes, "in_label": inside_label,
                    "antenati": [e["tag"] + "." + e["attrs"].get("class", "")
                                 for e in self.opened]}
        self.elements.append(element)
        if tag == "label" and attributes.get("for"):
            self.labels_for.append(attributes["for"])
        if tag not in VOID_TAGS:
            self.opened.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.opened:
            self.opened.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.opened) - 1, -1, -1):
            if self.opened[i]["tag"] == tag:
                del self.opened[i:]
                return

    def ids(self):
        return [e["attrs"]["id"] for e in self.elements if e["attrs"].get("id")]

    def with_class(self, class_name):
        return [e for e in self.elements
                if class_name in e["attrs"].get("class", "").split()]


def parse_page(text):
    page_html = ParsedPage()
    page_html.feed(text)
    return page_html


def unlabelled_fields(page_html):
    """Every field a person can type into or choose from, without a name."""
    ids = set(page_html.ids())
    missing = []
    for e in page_html.elements:
        if e["tag"] not in ("input", "select", "textarea"):
            continue
        a = e["attrs"]
        if a.get("type") == "hidden":
            continue
        if a.get("id") and a["id"] in page_html.labels_for:
            continue
        if e["in_label"] or a.get("aria-label"):
            continue
        if a.get("aria-labelledby") and a["aria-labelledby"] in ids:
            continue
        missing.append(f'{e["tag"]}#{a.get("id", "")}.{a.get("class", "")}')
    return missing


def broken_references(page_html):
    """Labels, descriptions and controls that point at an id nobody has."""
    ids = set(page_html.ids())
    broken_items = []
    for e in page_html.elements:
        for name in ("aria-describedby", "aria-labelledby", "aria-controls"):
            for value in e["attrs"].get(name, "").split():
                if value not in ids:
                    broken_items.append(f'{name}="{value}"')
    for value in page_html.labels_for:
        if value not in ids:
            broken_items.append(f'for="{value}"')
    return broken_items


def admin_pages():
    """The pages with the menu, and the voice the menu should mark on each."""
    article_list = load_articles()
    existing = article_list[0]
    return {
        "dashboard": (server.admin_page(article_list, "TOKEN"), "/admin"),
        "editor nuovo": (server.editor_page(None, "TOKEN"), "/edit"),
        "editor": (server.editor_page(existing, "TOKEN"), "/admin"),
        "impostazioni": (server.config_page("TOKEN"), "/config"),
        "cambio password": (server.change_password_page("TOKEN"), "/change-password"),
    }


def test_menu():
    """Every admin page has the menu, and it marks where you are."""
    print("\nmenu laterale")
    for language in ("it", "en"):
        config.CONFIG["admin_language"] = language
        for name, (text, expected) in admin_pages().items():
            page_html = parse_page(text)
            menu = [e for e in page_html.elements if e["attrs"].get("id") == "menu-admin"]
            skip_link = [e for e in page_html.elements
                     if e["tag"] == "a" and e["attrs"].get("href") == "#content"]
            main_html = [e for e in page_html.elements
                          if e["tag"] == "main" and e["attrs"].get("id") == "content"]
            check(f"{language} / {name}: un menu, il salto al contenuto e il main",
                  len(menu) == 1 and len(skip_link) == 1 and len(main_html) == 1)
            current_items = [e["attrs"].get("href") for e in page_html.with_class("item")
                        if e["attrs"].get("aria-current") == "page"]
            if expected is None:
                check(f"{language} / {name}: nessuna voce segnata dal server (lo fa admin.js)",
                      current_items == [], str(current_items))
            else:
                check(f"{language} / {name}: segnata solo la voce {expected}",
                      current_items == [expected], str(current_items))
            # The sections are in the panel, not in the menu: the menu
            # stays the same short list on every page.
            below = [e for e in page_html.with_class("item")
                     if "#" in e["attrs"].get("href", "")]
            check(f"{language} / {name}: niente sotto-voci nel menu", len(below) == 0)
    config.CONFIG["admin_language"] = "it"

    page_html = parse_page(server.login_page(""))
    check("il login non ha il menu",
          not any(e["attrs"].get("id") == "menu-admin" for e in page_html.elements))


def test_settings_sections():
    """The Settings answer to every name the menu and the list link to."""
    print("\nsezioni delle impostazioni")
    page_html = parse_page(server.config_page("TOKEN"))
    sections = [e for e in page_html.elements if e["tag"] == "section"]
    keys = [e["attrs"].get("data-section") for e in sections]
    expected_items = [key for key, _ in server.CONFIG_SECTIONS]
    check(f"{len(expected_items)} sezioni, nell'ordine del menu", keys == expected_items, str(keys))
    check("tutte nascoste finché admin.js non sceglie quale mostrare",
          all("hidden" in e["attrs"] for e in sections))
    titles = {e["attrs"].get("id") for e in page_html.elements if e["tag"] == "h1"}
    check("ogni sezione ha il suo titolo, che le dà il nome",
          all(e["attrs"].get("aria-labelledby") in titles for e in sections))
    cards = [e["attrs"].get("href") for e in page_html.with_class("card-setting")]
    grouped = [key for key in expected_items if key != "advanced"]
    check("il pannello ha una scheda per ogni sezione, nell'ordine",
          cards == ["#" + key for key in grouped], str(cards))
    advanced = [e for e in page_html.elements
                if e["tag"] == "a" and e["attrs"].get("href") == "#advanced"]
    check("il file di configurazione è un link in fondo al pannello", len(advanced) == 1)
    back = page_html.with_class("section-back")
    check("ogni sezione ha il ritorno all'elenco, con un nome",
          len(back) == len(expected_items)
          and all(e["attrs"].get("aria-label") for e in back))
    check("gli aiuti sotto i campi sono frasi, non parentesi",
          '<p class="help" id="base_url-help">(' not in server.config_page("TOKEN"))


def test_labels():
    """Every field has a name, and every reference points somewhere."""
    print("\netichette dei campi")
    for language in ("it", "en"):
        config.CONFIG["admin_language"] = language
        pages = {name: text for name, (text, _) in admin_pages().items()}
        pages["login"] = server.login_page("")
        for name, text in pages.items():
            page_html = parse_page(text)
            missing = unlabelled_fields(page_html)
            check(f"{language} / {name}: ogni campo ha un'etichetta",
                  len(missing) == 0, "; ".join(missing[:5]))
            broken_items = broken_references(page_html)
            check(f"{language} / {name}: nessun riferimento a un id che non c'è",
                  len(broken_items) == 0, "; ".join(broken_items[:5]))
            ids = page_html.ids()
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            check(f"{language} / {name}: nessun id ripetuto", len(duplicates) == 0, str(duplicates))
    config.CONFIG["admin_language"] = "it"


def test_help_text():
    """A hint in brackets becomes a sentence; anything else stays as it is."""
    print("\ntesti d'aiuto")
    check("toglie le parentesi e mette la maiuscola",
          server.help_text("(es. CTO e docente)") == "Es. CTO e docente")
    check("lascia stare una frase normale",
          server.help_text("Questi dati alimentano lo schema.") == "Questi dati alimentano lo schema.")
    check("lascia stare una parentesi in mezzo",
          server.help_text("Vuoto (predefinito) va bene") == "Vuoto (predefinito) va bene")


def main():
    test_menu()
    test_settings_sections()
    test_labels()
    test_help_text()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
