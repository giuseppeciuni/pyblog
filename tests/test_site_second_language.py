#!/usr/bin/env python3
"""
Checks on the subtitle, the author's role and the bio in the second language.

    python3 tests/test_site_second_language.py

The pages in the second language used to show the subtitle and the author's
data in the main language: an English reader of an Italian site found
"Note tecniche su AI..." in the header, in the description Google shows and
in the author box. Each of the three now has its twin for the other
language, which falls back to the main text when empty. Nothing here
touches the disk: the configuration is changed in memory and put back.
"""
import copy
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.config import CONFIG, author_bio, author_role, in_language, site_subtitle  # noqa: E402

PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


IT_SUB = "Note tecniche su AI e sistemi distribuiti"
EN_SUB = "Technical notes on AI and distributed systems"


def set_up(subtitle_en, role_en, bio_en, main="it"):
    CONFIG["language"] = main
    CONFIG["subtitle"] = IT_SUB if main == "it" else EN_SUB
    CONFIG["subtitle_en"] = subtitle_en
    seo = dict(CONFIG.get("seo", {}))
    seo["author_role"] = "Programmatore"
    seo["author_bio"] = "Scrivo di AI."
    seo["author_role_en"] = role_en
    seo["author_bio_en"] = bio_en
    CONFIG["seo"] = seo


def test_in_language():
    print("\nla regola")
    check("nella lingua principale vale il testo principale",
          in_language("Ciao", "Hello", "it") == "Ciao")
    check("nell'altra lingua vale il gemello", in_language("Ciao", "Hello", "en") == "Hello")
    check("un gemello vuoto ricade sul testo principale", in_language("Ciao", "  ", "en") == "Ciao")
    check("senza lingua, il testo principale", in_language("Ciao", "Hello") == "Ciao")
    check("un valore che non è testo non rompe niente", in_language(None, 3, "en") == "")


def test_english_pages():
    print("\nle pagine nell'altra lingua")
    set_up(EN_SUB, "Software developer", "I write about AI.")
    check("sottotitolo e autore seguono la lingua",
          site_subtitle("en") == EN_SUB and site_subtitle("it") == IT_SUB
          and author_role("en") == "Software developer" and author_bio("it") == "Scrivo di AI.")
    check("la testata inglese ha il sottotitolo inglese",
          EN_SUB in build.site_header("en") and IT_SUB not in build.site_header("en"))
    check("la testata italiana resta in italiano", IT_SUB in build.site_header("it"))
    box = build.generate_author_box("en")
    check("il box dell'autore in fondo agli articoli inglesi",
          "Software developer" in box and "I write about AI." in box
          and "Programmatore" not in box, box[:200])
    profile = build.profile_box("en")
    check("il riquadro dell'autore nella barra laterale",
          "Software developer" in profile and "I write about AI." in profile)
    person = build.person_jsonld("en")
    check("i dati per Google sull'autore",
          person.get("jobTitle") == "Software developer"
          and person.get("description") == "I write about AI.", str(person))
    check("e in italiano restano italiani",
          build.person_jsonld("it").get("jobTitle") == "Programmatore")
    home = build.generate_homepage([], "en")
    description_text = re.search(r'<meta name="description" content="([^"]*)"', home)
    social = re.search(r'<meta property="og:description" content="([^"]*)"', home)
    check("la descrizione della home inglese per Google e per i social",
          description_text is not None and description_text.group(1) == EN_SUB
          and social is not None and social.group(1) == EN_SUB)
    payload = re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
    check("e quella dei dati strutturati del sito",
          payload is not None and json.loads(payload.group(1)).get("description") == EN_SUB)
    check("il feed inglese si presenta in inglese",
          f"<description>{EN_SUB}</description>" in build.generate_rss([], "en"))


def test_empty_twins():
    print("\nsenza traduzione")
    set_up("", "", "")
    check("con i gemelli vuoti le pagine inglesi mostrano l'italiano, come prima",
          IT_SUB in build.site_header("en")
          and "Programmatore" in build.generate_author_box("en"))


def test_english_main():
    """A site written in English: the twins hold the Italian."""
    print("\nsito in inglese")
    set_up("Note tecniche su AI", "Programmatore", "Scrivo di AI.", main="en")
    seo = dict(CONFIG["seo"])
    seo["author_role"] = "Software developer"
    seo["author_bio"] = "I write about AI."
    CONFIG["seo"] = seo
    check("alla radice l'inglese, nella sottocartella italiana l'italiano",
          site_subtitle("en") == EN_SUB and site_subtitle("it") == "Note tecniche su AI"
          and author_role("it") == "Programmatore")


def test_settings():
    print("\nle impostazioni")
    set_up(EN_SUB, "Software developer", "I write about AI.")
    # The Settings page reads config.json; here it reads the one in memory.
    real = server.load_config
    server.load_config = lambda: copy.deepcopy(CONFIG)
    try:
        page_html = server.config_page("TOKEN")
    finally:
        server.load_config = real
    for field in ("subtitle_en", "seo_author_role_en", "seo_author_bio_en"):
        check(f"il campo {field} c'è, con la sua etichetta",
              f'id="{field}"' in page_html and f'for="{field}"' in page_html)
    check("i campi dicono al browser in che lingua sono scritti",
          'id="subtitle_en" value="' + EN_SUB + '" lang="en"' in page_html)
    check("il pulsante traduce tutti e tre", 'onclick="translateSiteTexts(this)"' in page_html)
    check("le etichette nominano la lingua, non \"_en\"",
          "Sottotitolo in inglese" in page_html and "{other_language}" not in page_html)
    js = pathlib.Path(__file__).resolve().parent.parent.joinpath("static", "admin.js").read_text()
    check("il salvataggio manda i tre campi",
          "subtitle_en: document.getElementById('subtitle_en')" in js
          and "author_role_en: document.getElementById('seo_author_role_en')" in js
          and "author_bio_en: document.getElementById('seo_author_bio_en')" in js)


def main():
    saved = copy.deepcopy({k: CONFIG.get(k) for k in ("language", "subtitle", "subtitle_en", "seo")})
    try:
        test_in_language()
        test_english_pages()
        test_empty_twins()
        test_english_main()
        test_settings()
    finally:
        for key, value in saved.items():
            if value is None:
                CONFIG.pop(key, None)
            else:
                CONFIG[key] = value
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
