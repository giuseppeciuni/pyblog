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


class Pagina(html.parser.HTMLParser):
    """Collects the elements of a page with the labels that wrap them."""

    def __init__(self):
        super().__init__()
        self.elementi = []
        self.aperti = []
        self.etichette_per = []

    def handle_starttag(self, tag, attrs):
        attributi = dict(attrs)
        dentro_label = any(e["tag"] == "label" for e in self.aperti)
        elemento = {"tag": tag, "attrs": attributi, "in_label": dentro_label,
                    "antenati": [e["tag"] + "." + e["attrs"].get("class", "")
                                 for e in self.aperti]}
        self.elementi.append(elemento)
        if tag == "label" and attributi.get("for"):
            self.etichette_per.append(attributi["for"])
        if tag not in VOID_TAGS:
            self.aperti.append(elemento)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.aperti:
            self.aperti.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.aperti) - 1, -1, -1):
            if self.aperti[i]["tag"] == tag:
                del self.aperti[i:]
                return

    def ids(self):
        return [e["attrs"]["id"] for e in self.elementi if e["attrs"].get("id")]

    def con_classe(self, classe):
        return [e for e in self.elementi
                if classe in e["attrs"].get("class", "").split()]


def analizza(testo):
    pagina = Pagina()
    pagina.feed(testo)
    return pagina


def campi_senza_etichetta(pagina):
    """Every field a person can type into or choose from, without a name."""
    ids = set(pagina.ids())
    mancanti = []
    for e in pagina.elementi:
        if e["tag"] not in ("input", "select", "textarea"):
            continue
        a = e["attrs"]
        if a.get("type") == "hidden":
            continue
        if a.get("id") and a["id"] in pagina.etichette_per:
            continue
        if e["in_label"] or a.get("aria-label"):
            continue
        if a.get("aria-labelledby") and a["aria-labelledby"] in ids:
            continue
        mancanti.append(f'{e["tag"]}#{a.get("id", "")}.{a.get("class", "")}')
    return mancanti


def riferimenti_rotti(pagina):
    """Labels, descriptions and controls that point at an id nobody has."""
    ids = set(pagina.ids())
    rotti = []
    for e in pagina.elementi:
        for nome in ("aria-describedby", "aria-labelledby", "aria-controls"):
            for valore in e["attrs"].get(nome, "").split():
                if valore not in ids:
                    rotti.append(f'{nome}="{valore}"')
    for valore in pagina.etichette_per:
        if valore not in ids:
            rotti.append(f'for="{valore}"')
    return rotti


def pagine_admin():
    """The pages with the menu, and the voice the menu should mark on each."""
    articoli = load_articles()
    esistente = articoli[0]
    return {
        "dashboard": (server.admin_page(articoli, "TOKEN"), "/admin"),
        "editor nuovo": (server.editor_page(None, "TOKEN"), "/edit"),
        "editor": (server.editor_page(esistente, "TOKEN"), "/admin"),
        "impostazioni": (server.config_page("TOKEN"), None),
        "cambio password": (server.change_password_page("TOKEN"), "/change-password"),
    }


def test_menu():
    """Every admin page has the menu, and it marks where you are."""
    print("\nmenu laterale")
    for lingua in ("it", "en"):
        config.CONFIG["admin_language"] = lingua
        for nome, (testo, attesa) in pagine_admin().items():
            pagina = analizza(testo)
            menu = [e for e in pagina.elementi if e["attrs"].get("id") == "menu-admin"]
            salta = [e for e in pagina.elementi
                     if e["tag"] == "a" and e["attrs"].get("href") == "#contenuto"]
            principale = [e for e in pagina.elementi
                          if e["tag"] == "main" and e["attrs"].get("id") == "contenuto"]
            check(f"{lingua} / {nome}: un menu, il salto al contenuto e il main",
                  len(menu) == 1 and len(salta) == 1 and len(principale) == 1)
            correnti = [e["attrs"].get("href") for e in pagina.con_classe("voce")
                        if e["attrs"].get("aria-current") == "page"]
            if attesa is None:
                check(f"{lingua} / {nome}: nessuna voce segnata dal server (lo fa admin.js)",
                      correnti == [], str(correnti))
            else:
                check(f"{lingua} / {nome}: segnata solo la voce {attesa}",
                      correnti == [attesa], str(correnti))
            sotto = pagina.con_classe("voce-sotto")
            if nome == "impostazioni":
                attese = ["/config#" + chiave for chiave, _ in server.CONFIG_SECTIONS]
                check(f"{lingua} / {nome}: le sotto-voci delle sezioni, in ordine",
                      [e["attrs"].get("href") for e in sotto] == attese)
            else:
                check(f"{lingua} / {nome}: niente sotto-voci", len(sotto) == 0)
    config.CONFIG["admin_language"] = "it"

    pagina = analizza(server.login_page(""))
    check("il login non ha il menu",
          not any(e["attrs"].get("id") == "menu-admin" for e in pagina.elementi))


def test_sezioni_impostazioni():
    """The Settings answer to every name the menu and the list link to."""
    print("\nsezioni delle impostazioni")
    pagina = analizza(server.config_page("TOKEN"))
    sezioni = [e for e in pagina.elementi if e["tag"] == "section"]
    chiavi = [e["attrs"].get("data-sezione") for e in sezioni]
    attese = [chiave for chiave, _ in server.CONFIG_SECTIONS]
    check(f"{len(attese)} sezioni, nell'ordine del menu", chiavi == attese, str(chiavi))
    check("tutte nascoste finché admin.js non sceglie quale mostrare",
          all("hidden" in e["attrs"] for e in sezioni))
    titoli = {e["attrs"].get("id") for e in pagina.elementi if e["tag"] == "h1"}
    check("ogni sezione ha il suo titolo, che le dà il nome",
          all(e["attrs"].get("aria-labelledby") in titoli for e in sezioni))
    elenco = [e["attrs"].get("href") for e in pagina.con_classe("sezioni-voce")]
    check("l'elenco del telefono porta a ogni sezione",
          elenco == ["#" + chiave for chiave in attese], str(elenco))
    indietro = pagina.con_classe("sezione-indietro")
    check("ogni sezione ha il ritorno all'elenco, con un nome",
          len(indietro) == len(attese)
          and all(e["attrs"].get("aria-label") for e in indietro))
    check("gli aiuti sotto i campi sono frasi, non parentesi",
          '<p class="aiuto" id="base_url-aiuto">(' not in server.config_page("TOKEN"))


def test_etichette():
    """Every field has a name, and every reference points somewhere."""
    print("\netichette dei campi")
    for lingua in ("it", "en"):
        config.CONFIG["admin_language"] = lingua
        pagine = {nome: testo for nome, (testo, _) in pagine_admin().items()}
        pagine["login"] = server.login_page("")
        for nome, testo in pagine.items():
            pagina = analizza(testo)
            mancanti = campi_senza_etichetta(pagina)
            check(f"{lingua} / {nome}: ogni campo ha un'etichetta",
                  len(mancanti) == 0, "; ".join(mancanti[:5]))
            rotti = riferimenti_rotti(pagina)
            check(f"{lingua} / {nome}: nessun riferimento a un id che non c'è",
                  len(rotti) == 0, "; ".join(rotti[:5]))
            ids = pagina.ids()
            doppi = sorted({i for i in ids if ids.count(i) > 1})
            check(f"{lingua} / {nome}: nessun id ripetuto", len(doppi) == 0, str(doppi))
    config.CONFIG["admin_language"] = "it"


def test_testo_aiuto():
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
    test_sezioni_impostazioni()
    test_etichette()
    test_testo_aiuto()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
