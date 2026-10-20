#!/usr/bin/env python3
"""
Checks on a site whose main language is English.

    python3 tests/test_main_language.py

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
ARTICLE_FIXTURE = {
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


def page_title(page_html):
    """The h1 of the article (the last h1: the site title may come first)."""
    titles = re.findall(r"<h1[^>]*>(.*?)</h1>", page_html, re.DOTALL)
    if len(titles) == 0:
        return ""
    return re.sub(r"<[^>]+>", "", titles[-1]).strip()


def test_article_pages():
    print("\npagine dell'articolo con l'inglese come lingua principale")
    CONFIG["language"] = "en"
    main_html = build.generate_article_page(ARTICLE_FIXTURE, "en", [ARTICLE_FIXTURE])
    translated = build.generate_article_page(ARTICLE_FIXTURE, "it", [ARTICLE_FIXTURE])
    check("alla radice il titolo e' quello in cui l'articolo e' scritto",
          page_title(main_html) == "How an LLM writes", page_title(main_html))
    check("nella sottocartella c'e' la traduzione",
          page_title(translated) == "Come scrive un LLM", page_title(translated))
    check("e il testo tradotto", "Un modello indovina" in translated)

    home = build.generate_homepage([ARTICLE_FIXTURE], "en", 1, 1)
    check("la home principale mostra lo stesso titolo della pagina",
          "How an LLM writes" in home and "Come scrive un LLM" not in home)
    home_it = build.generate_homepage([ARTICLE_FIXTURE], "it", 1, 1)
    check("la home tradotta mostra il titolo tradotto", "Come scrive un LLM" in home_it)

    CONFIG["language"] = "it"
    main_html = build.generate_article_page(ARTICLE_FIXTURE, "it", [ARTICLE_FIXTURE])
    check("con l'italiano principale tutto resta com'era",
          page_title(main_html) == "How an LLM writes")


def test_search_knows_which_language_is_translated():
    print("\nricerca")
    CONFIG["language"] = "en"
    check("le pagine in italiano sono quelle tradotte",
          build.site_options("it")["secondary"] is True)
    check("quelle in inglese no", build.site_options("en")["secondary"] is False)
    CONFIG["language"] = "it"
    check("con l'italiano principale, l'inglese e' la traduzione",
          build.site_options("en")["secondary"] is True)


def test_comments_in_page_language():
    print("\ncommenti")
    old = CONFIG.get("comments")
    CONFIG["comments"] = "giscus"
    try:
        english = build.comments_block(ARTICLE_FIXTURE, "en")
        italian = build.comments_block(ARTICLE_FIXTURE, "it")
        check("titolo dei commenti in inglese", "<h2>Comments</h2>" in english)
        check("titolo dei commenti in italiano", "<h2>Commenti</h2>" in italian)
        check("Giscus parla la lingua della pagina", 'data-lang="en"' in english)
        CONFIG["comments"] = "disqus"
        check("anche l'avviso di Disqus senza JavaScript",
              "Enable JavaScript" in build.comments_block(ARTICLE_FIXTURE, "en"))
    finally:
        CONFIG["comments"] = old


def test_translation_direction():
    print("\ntraduzione automatica")
    seen = []
    original = ai.translate_with_deepl

    def fake(text, api_key, source="it", target="en"):
        seen.append((source, target))
        return text

    ai.translate_with_deepl = fake
    old_translation = CONFIG.get("translation")
    CONFIG["translation"] = {"service": "deepl", "deepl_api_key": "chiave-finta"}
    try:
        CONFIG["language"] = "it"
        ai.translate_text("<p>ciao</p>")
        CONFIG["language"] = "en"
        ai.translate_text("<p>hello</p>")
    finally:
        ai.translate_with_deepl = original
        CONFIG["translation"] = old_translation
        CONFIG["language"] = "it"
    check("sito italiano: dall'italiano all'inglese", seen[0] == ("it", "en"), str(seen))
    check("sito inglese: dall'inglese all'italiano", seen[1] == ("en", "it"), str(seen))
    instruction = ai.translation_instruction("<p>x</p>", "en", "it")
    check("il modello linguistico riceve la direzione giusta",
          "from English to Italian" in instruction)


def test_editor_labels():
    print("\netichette dell'editor")
    CONFIG["language"] = "it"
    check("sito italiano, admin italiano",
          server.TL("admin_version_english", "it") == "Versione in inglese")
    CONFIG["language"] = "en"
    check("sito inglese, admin italiano",
          server.TL("admin_version_english", "it") == "Versione in italiano")
    check("sito inglese, admin inglese",
          server.TL("admin_version_english", "en") == "Italian version")
    check("il pulsante di traduzione nomina la lingua di partenza",
          server.TL("admin_translate_from_the_italian", "it") == "Traduci automaticamente dall'inglese")
    check("anche le stringhe del JavaScript",
          "inglese" in server.js_translations("it")["js_write_intro_first"])
    editor = server.editor_page(dict(ARTICLE_FIXTURE), "TOKEN")
    check("i campi della traduzione dicono (IT)", "(IT)</label>" in editor)
    check("l'anteprima della traduzione apre la lingua giusta",
          '"secondary_language": "it"' in editor)
    dashboard = server.admin_page([dict(ARTICLE_FIXTURE)], "TOKEN")
    check("la dashboard dice che c'è anche in italiano", "anche in italiano" in dashboard)
    check("e l'anteprima in italiano", "language=it" in dashboard
          and "Anteprima in italiano" in dashboard)
    CONFIG["language"] = "it"


def test_main_language_is_a_choice():
    print("\nimpostazioni")
    original = server.load_config

    def english_config():
        values = original()
        values["language"] = "en"
        return values

    server.load_config = english_config
    try:
        page_html = server.config_page("TOKEN")
    finally:
        server.load_config = original
    check("la lingua principale si sceglie da un menu",
          re.search(r'<select[^>]* id="language"', page_html) is not None)
    check("con l'inglese gia' selezionato",
          re.search(r'<option value="en"\s+selected>', page_html) is not None)


def main():
    language = CONFIG.get("language", "it")
    try:
        test_article_pages()
        test_search_knows_which_language_is_translated()
        test_comments_in_page_language()
        test_translation_direction()
        test_editor_labels()
        test_main_language_is_a_choice()
    finally:
        CONFIG["language"] = language
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
