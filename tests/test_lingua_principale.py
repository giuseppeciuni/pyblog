#!/usr/bin/env python3
"""
Checks on a site whose main language is English.

    python3 tests/test_lingua_principale.py

The configuration lets the author choose the main language, but half of the
code assumed it was Italian. With English at the root, the article pages read
the translation fields while the homepage read the original ones, so the
same article had an Italian title on the homepage and an English one on its
own page; the automatic translation still went from Italian to English, and
the editor kept calling the translation "the English version".

Everything here works on the configuration in memory: config.json is never
written, and the articles are built on the fly.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import ai, build, server  # noqa: E402
from core.config import CONFIG  # noqa: E402

PASSED = 0
FAILED = 0

# An article written in English, with its Italian translation confirmed.
ARTICOLO = {
    "title": "How an LLM writes", "slug": "how-an-llm-writes",
    "content": "<p>A model guesses the next token.</p>",
    "description": "English description", "preview": "",
    "title_en": "Come scrive un LLM", "content_en": "<p>Un modello indovina il token successivo.</p>",
    "description_en": "Descrizione italiana", "preview_en": "",
    "translation_authorized": True, "translation_confirmed": True,
    "tags": "AI", "image": "", "status": "published",
    "date": "2026-03-01T09:00:00+00:00", "date_modified": "2026-03-01T09:00:00+00:00",
}


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


def titolo_pagina(pagina):
    """The h1 of the article (the last h1: the site title may come first)."""
    titoli = re.findall(r"<h1[^>]*>(.*?)</h1>", pagina, re.DOTALL)
    if len(titoli) == 0:
        return ""
    return re.sub(r"<[^>]+>", "", titoli[-1]).strip()


def test_pagine_articolo():
    print("\npagine dell'articolo con l'inglese come lingua principale")
    CONFIG["language"] = "en"
    principale = build.generate_article_page(ARTICOLO, "en", [ARTICOLO])
    tradotta = build.generate_article_page(ARTICOLO, "it", [ARTICOLO])
    check("alla radice il titolo e' quello in cui l'articolo e' scritto",
          titolo_pagina(principale) == "How an LLM writes", titolo_pagina(principale))
    check("nella sottocartella c'e' la traduzione",
          titolo_pagina(tradotta) == "Come scrive un LLM", titolo_pagina(tradotta))
    check("e il testo tradotto", "Un modello indovina" in tradotta)

    home = build.generate_homepage([ARTICOLO], "en", 1, 1)
    check("la home principale mostra lo stesso titolo della pagina",
          "How an LLM writes" in home and "Come scrive un LLM" not in home)
    home_it = build.generate_homepage([ARTICOLO], "it", 1, 1)
    check("la home tradotta mostra il titolo tradotto", "Come scrive un LLM" in home_it)

    CONFIG["language"] = "it"
    principale = build.generate_article_page(ARTICOLO, "it", [ARTICOLO])
    check("con l'italiano principale tutto resta com'era",
          titolo_pagina(principale) == "How an LLM writes")


def test_ricerca_sa_quale_lingua_e_tradotta():
    print("\nricerca")
    CONFIG["language"] = "en"
    check("le pagine in italiano sono quelle tradotte",
          build.site_options("it")["secondary"] is True)
    check("quelle in inglese no", build.site_options("en")["secondary"] is False)
    CONFIG["language"] = "it"
    check("con l'italiano principale, l'inglese e' la traduzione",
          build.site_options("en")["secondary"] is True)


def test_commenti_nella_lingua_della_pagina():
    print("\ncommenti")
    vecchio = CONFIG.get("comments")
    CONFIG["comments"] = "giscus"
    try:
        inglese = build.comments_block(ARTICOLO, "en")
        italiano = build.comments_block(ARTICOLO, "it")
        check("titolo dei commenti in inglese", "<h2>Comments</h2>" in inglese)
        check("titolo dei commenti in italiano", "<h2>Commenti</h2>" in italiano)
        check("Giscus parla la lingua della pagina", 'data-lang="en"' in inglese)
        CONFIG["comments"] = "disqus"
        check("anche l'avviso di Disqus senza JavaScript",
              "Enable JavaScript" in build.comments_block(ARTICOLO, "en"))
    finally:
        CONFIG["comments"] = vecchio


def test_direzione_della_traduzione():
    print("\ntraduzione automatica")
    viste = []
    originale = ai.translate_with_deepl

    def finta(text, api_key, source="it", target="en"):
        viste.append((source, target))
        return text

    ai.translate_with_deepl = finta
    vecchia_traduzione = CONFIG.get("translation")
    CONFIG["translation"] = {"service": "deepl", "deepl_api_key": "chiave-finta"}
    try:
        CONFIG["language"] = "it"
        ai.translate_text("<p>ciao</p>")
        CONFIG["language"] = "en"
        ai.translate_text("<p>hello</p>")
    finally:
        ai.translate_with_deepl = originale
        CONFIG["translation"] = vecchia_traduzione
        CONFIG["language"] = "it"
    check("sito italiano: dall'italiano all'inglese", viste[0] == ("it", "en"), str(viste))
    check("sito inglese: dall'inglese all'italiano", viste[1] == ("en", "it"), str(viste))
    istruzione = ai.translation_instruction("<p>x</p>", "en", "it")
    check("il modello linguistico riceve la direzione giusta",
          "from English to Italian" in istruzione)


def test_etichette_dell_editor():
    print("\netichette dell'editor")
    CONFIG["language"] = "it"
    check("sito italiano, admin italiano",
          server.TL("admin_versione_inglese", "it") == "Versione in inglese")
    CONFIG["language"] = "en"
    check("sito inglese, admin italiano",
          server.TL("admin_versione_inglese", "it") == "Versione in italiano")
    check("sito inglese, admin inglese",
          server.TL("admin_versione_inglese", "en") == "Italian version")
    check("il pulsante di traduzione nomina la lingua di partenza",
          server.TL("admin_traduci_dall_italiano", "it") == "Traduci automaticamente dall'inglese")
    check("anche le stringhe del JavaScript",
          "inglese" in server.js_translations("it")["js_write_intro_first"])
    editor = server.editor_page(dict(ARTICOLO), "TOKEN")
    check("i campi della traduzione dicono (IT)", "(IT)</label>" in editor)
    check("l'anteprima della traduzione apre la lingua giusta",
          '"secondary_language": "it"' in editor)
    dashboard = server.admin_page([dict(ARTICOLO)], "TOKEN")
    check("la dashboard mostra il badge IT", ">IT</span>" in dashboard)
    check("e l'anteprima in italiano", "language=it" in dashboard)
    CONFIG["language"] = "it"


def test_lingua_principale_e_una_scelta():
    print("\nimpostazioni")
    originale = server.load_config

    def config_inglese():
        valori = originale()
        valori["language"] = "en"
        return valori

    server.load_config = config_inglese
    try:
        pagina = server.config_page("TOKEN")
    finally:
        server.load_config = originale
    check("la lingua principale si sceglie da un menu", '<select id="language">' in pagina)
    check("con l'inglese gia' selezionato",
          re.search(r'<option value="en"\s+selected>', pagina) is not None)


def main():
    lingua = CONFIG.get("language", "it")
    try:
        test_pagine_articolo()
        test_ricerca_sa_quale_lingua_e_tradotta()
        test_commenti_nella_lingua_della_pagina()
        test_direzione_della_traduzione()
        test_etichette_dell_editor()
        test_lingua_principale_e_una_scelta()
    finally:
        CONFIG["language"] = lingua
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
