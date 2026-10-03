#!/usr/bin/env python3
"""
Checks on scheduled publishing.

    python3 tests/test_programmati.py

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


ADESSO = datetime.now(timezone.utc).replace(microsecond=0)
PASSATO = (ADESSO - timedelta(hours=1)).isoformat()
FUTURO = (ADESSO + timedelta(days=2)).isoformat()


def articolo(slug, stato, quando):
    return {"title": "Prova " + slug, "slug": slug, "content": "<p>Testo.</p>",
            "status": stato, "publish_at": quando, "tags": "Prova"}


def test_dati():
    print("\nlo stato e il momento")
    a = article_from_data(articolo("x", "scheduled", "2026-10-04T09:00:00+02:00"), "x")
    check("un programmato tiene il momento, in UTC",
          a["status"] == "scheduled" and a["publish_at"] == "2026-10-04T07:00:00+00:00", str(a["publish_at"]))
    check("la Z vale UTC", normalized_moment("2026-10-04T07:00:00.000Z") == "2026-10-04T07:00:00+00:00")
    check("senza fuso orario si legge come UTC", normalized_moment("2026-10-04T07:00") == "2026-10-04T07:00:00+00:00")
    a = article_from_data(articolo("x", "scheduled", "domani"), "x")
    check("senza un momento valido resta bozza", a["status"] == "draft" and a["publish_at"] == "")
    a = article_from_data(articolo("x", "published", FUTURO), "x")
    check("un pubblicato non tiene il momento", a["publish_at"] == "")
    a = article_from_data(articolo("x", "boh", ""), "x")
    check("uno stato sconosciuto è bozza", a["status"] == "draft")


def test_uscita():
    print("\nl'uscita all'ora giusta")
    passato = save_article(articolo("prova-programmato-passato", "scheduled", PASSATO), new_article=True)
    futuro = save_article(articolo("prova-programmato-futuro", "scheduled", FUTURO), new_article=True)
    try:
        dovuti = [a["slug"] for a in due_scheduled_articles()]
        check("è dovuto solo quello passato", passato in dovuti and futuro not in dovuti, str(dovuti))
        usciti = publish_due_articles()
        check("pubblicare i dovuti pubblica solo quello", passato in usciti and futuro not in usciti, str(usciti))
        art = load_article(passato)
        check("è pubblicato, datato al momento programmato, senza più il momento",
              art["status"] == "published" and art["date"] == normalized_moment(PASSATO) and art["publish_at"] == "",
              str({k: art.get(k) for k in ("status", "date", "publish_at")}))
        check("quello futuro aspetta", load_article(futuro)["status"] == "scheduled")
        check("una seconda passata non fa niente", publish_due_articles() == [])
        domani = ADESSO + timedelta(days=3)
        check("col tempo arriva anche l'altro", publish_due_articles(domani) == [futuro])
    finally:
        delete_article(passato)
        delete_article(futuro)


def test_amministrazione():
    print("\nl'amministrazione")
    slug = save_article(articolo("prova-programmato-admin", "scheduled", FUTURO), new_article=True)
    try:
        art = load_article(slug)
        editor = server.editor_page(art, "TOKEN")
        check("l'editor si apre nello stato programmato", 'data-stato="scheduled"' in editor)
        check("e dice quando esce, con l'ora da localizzare",
              re.search(r'<span id="programmato-quando">esce il <time class="ora-locale" datetime="[^"]+">', editor) is not None)
        check("i dati per il JavaScript hanno il momento", '"publish_at": "' + normalized_moment(FUTURO) + '"' in editor)
        bozza = server.editor_page(None, "TOKEN")
        check("un articolo nuovo ha il pulsante per programmarlo", 'id="btn-programma"' in bozza)
        elenco = server.admin_page(load_articles(), "TOKEN")
        check("nell'elenco ha la sua etichetta", 'pill-programmato' in elenco)
        check("e il filtro dei programmati compare", re.search(r'data-filtro="s" onclick="filterByStatus\(this\)">', elenco) is not None)
        check("il riepilogo li conta", "Programmati: 1" in elenco)
        check("il suo menu può pubblicarlo subito o annullare",
              "Pubblica ora" in elenco and "Annulla la programmazione" in elenco)
    finally:
        delete_article(slug)
    elenco = server.admin_page(load_articles(), "TOKEN")
    check("senza programmati il filtro resta nascosto", 'data-filtro="s" onclick="filterByStatus(this)" hidden>' in elenco)


def test_sito():
    print("\nil sito pubblico")
    from core import build
    slug = save_article(articolo("prova-programmato-sito", "scheduled", FUTURO), new_article=True)
    try:
        pubblicati = [a for a in load_articles() if a.get("status") == "published"]
        check("non è tra gli articoli che la build pubblica", slug not in [a["slug"] for a in pubblicati])
        check("la sitemap non lo nomina", slug not in build.generate_sitemap(pubblicati))
    finally:
        delete_article(slug)


def main():
    test_dati()
    test_uscita()
    test_amministrazione()
    test_sito()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
