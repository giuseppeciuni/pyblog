#!/usr/bin/env python3
"""
Checks on scheduled publishing.

    python3 tests/test_scheduled.py

A scheduled article carries the moment it goes out, in UTC; until then
readers cannot see it, and the first build (or the editor's check, once a
minute) after that moment publishes it, dated at that moment. The test
articles are written to posts/ and removed at the end.
"""
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import server  # noqa: E402
from core.articles import (article_from_data, delete_article,  # noqa: E402
                           due_scheduled_articles, load_article, load_articles,
                           normalized_moment, publish_due_articles, save_article)

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


NOW = datetime.now(timezone.utc).replace(microsecond=0)
PAST = (NOW - timedelta(hours=1)).isoformat()
FUTURE = (NOW + timedelta(days=2)).isoformat()


def article(slug, state, moment):
    return {"title": "Prova " + slug, "slug": slug, "content": "<p>Testo.</p>",
            "status": state, "publish_at": moment, "tags": "Prova"}


def test_data():
    print("\nlo stato e il momento")
    a = article_from_data(article("x", "scheduled", "2026-10-04T09:00:00+02:00"), "x")
    check("un programmato tiene il momento, in UTC",
          a["status"] == "scheduled" and a["publish_at"] == "2026-10-04T07:00:00+00:00", str(a["publish_at"]))
    check("la Z vale UTC", normalized_moment("2026-10-04T07:00:00.000Z") == "2026-10-04T07:00:00+00:00")
    check("senza fuso orario si legge come UTC", normalized_moment("2026-10-04T07:00") == "2026-10-04T07:00:00+00:00")
    a = article_from_data(article("x", "scheduled", "domani"), "x")
    check("senza un momento valido resta bozza", a["status"] == "draft" and a["publish_at"] == "")
    a = article_from_data(article("x", "published", FUTURE), "x")
    check("un pubblicato non tiene il momento", a["publish_at"] == "")
    a = article_from_data(article("x", "boh", ""), "x")
    check("uno stato sconosciuto è bozza", a["status"] == "draft")


def test_logout():
    print("\nl'uscita all'ora giusta")
    past = save_article(article("prova-programmato-passato", "scheduled", PAST), new_article=True)
    future = save_article(article("prova-programmato-futuro", "scheduled", FUTURE), new_article=True)
    try:
        due = [a["slug"] for a in due_scheduled_articles()]
        check("è dovuto solo quello passato", past in due and future not in due, str(due))
        gone_out = publish_due_articles()
        check("pubblicare i dovuti pubblica solo quello", past in gone_out and future not in gone_out, str(gone_out))
        art = load_article(past)
        check("è pubblicato, datato al momento programmato, senza più il momento",
              art["status"] == "published" and art["date"] == normalized_moment(PAST) and art["publish_at"] == "",
              str({k: art.get(k) for k in ("status", "date", "publish_at")}))
        check("quello futuro aspetta", load_article(future)["status"] == "scheduled")
        check("una seconda passata non fa niente", publish_due_articles() == [])
        tomorrow = NOW + timedelta(days=3)
        check("col tempo arriva anche l'altro", publish_due_articles(tomorrow) == [future])
    finally:
        delete_article(past)
        delete_article(future)


def test_administration():
    print("\nl'amministrazione")
    slug = save_article(article("prova-programmato-admin", "scheduled", FUTURE), new_article=True)
    try:
        art = load_article(slug)
        editor = server.editor_page(art, "TOKEN")
        check("l'editor si apre nello stato programmato", 'data-state="scheduled"' in editor)
        check("e dice quando esce, con l'ora da localizzare",
              re.search(r'<span id="scheduled-when">esce il <time class="now-local" datetime="[^"]+">', editor) is not None)
        check("i dati per il JavaScript hanno il momento", '"publish_at": "' + normalized_moment(FUTURE) + '"' in editor)
        draft = server.editor_page(None, "TOKEN")
        check("un articolo nuovo ha il pulsante per programmarlo", 'id="btn-schedule"' in draft)
        listing = server.admin_page(load_articles(), "TOKEN")
        check("nell'elenco ha la sua etichetta", 'pill-scheduled' in listing)
        check("e il filtro dei programmati compare", re.search(r'data-filter="s" onclick="filterByStatus\(this\)">', listing) is not None)
        check("il riepilogo li conta", "Programmati: 1" in listing)
        check("il suo menu può pubblicarlo subito o annullare",
              "Pubblica ora" in listing and "Annulla la programmazione" in listing)
    finally:
        delete_article(slug)
    listing = server.admin_page(load_articles(), "TOKEN")
    check("senza programmati il filtro resta nascosto", 'data-filter="s" onclick="filterByStatus(this)" hidden>' in listing)


def test_site():
    print("\nil sito pubblico")
    from core import build
    slug = save_article(article("prova-programmato-sito", "scheduled", FUTURE), new_article=True)
    try:
        published = [a for a in load_articles() if a.get("status") == "published"]
        check("non è tra gli articoli che la build pubblica", slug not in [a["slug"] for a in published])
        check("la sitemap non lo nomina", slug not in build.generate_sitemap(published))
    finally:
        delete_article(slug)


def main():
    test_data()
    test_logout()
    test_administration()
    test_site()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
