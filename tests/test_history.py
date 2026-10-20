#!/usr/bin/env python3
"""
Checks on the history of an article.

    python3 tests/test_history.py

Every save keeps the version it replaces, unless nothing changed or the
last version kept is too recent (autosave writes every minute); a published
version is always kept. The versions follow a renamed article and go with a
deleted one. The test articles and their versions are removed at the end.
"""
import pathlib
import shutil
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import articles, server  # noqa: E402
from core.articles import (HISTORY_DIR, delete_article, history_folder,  # noqa: E402
                           keep_version, list_versions, load_article,
                           load_version, save_article)

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


def payload(slug, text, state="draft", original=None):
    d = {"title": "Cronologia " + slug, "slug": slug, "content": f"<p>{text}</p>",
         "status": state, "tags": "Prova"}
    d["original_slug"] = slug if original is None else original
    return d


def test_saves():
    print("\ni salvataggi tengono la versione sostituita")
    slug = save_article(payload("prova-cronologia", "Uno"), new_article=True)
    try:
        check("un articolo nuovo non ha versioni", list_versions(slug) == [])
        save_article(payload(slug, "Due"))
        versions = list_versions(slug)
        check("salvare un cambiamento tiene la versione di prima", len(versions) == 1, str(versions))
        old_value = load_version(slug, versions[0]["id"])
        check("la versione tenuta ha il testo di prima", old_value and old_value["content"] == "<p>Uno</p>")
        check("l'elenco dice titolo, stato e parole",
              versions[0]["title"] == "Cronologia prova-cronologia" and versions[0]["status"] == "draft"
              and versions[0]["words"] == 1, str(versions[0]))
        save_article(payload(slug, "Tre"))
        check("un altro salvataggio a pochi minuti non ne tiene un'altra (l'autosalvataggio)",
              len(list_versions(slug)) == 1)
        save_article(payload(slug, "Tre"))
        check("un salvataggio senza cambiamenti non conta", len(list_versions(slug)) == 1)

        # The gap and the published versions, with explicit moments.
        after_value = datetime.now(timezone.utc) + timedelta(minutes=11)
        keep_version(slug, load_article(slug), dict(load_article(slug), content="<p>Quattro</p>"), now=after_value)
        check("dopo dieci minuti si tiene di nuovo", len(list_versions(slug)) == 2)
        published_page = dict(load_article(slug), status="published")
        keep_version(slug, published_page, dict(published_page, content="<p>Cinque</p>"), now=after_value + timedelta(seconds=30))
        check("una versione pubblicata si tiene sempre", len(list_versions(slug)) == 3)

        base = after_value + timedelta(hours=1)
        for n in range(60):
            keep_version(slug, dict(load_article(slug), content=f"<p>{n}</p>"),
                         dict(load_article(slug), content=f"<p>{n + 1}</p>"), now=base + timedelta(minutes=11 * n))
        check(f"se ne tengono al massimo {articles.HISTORY_LIMIT}",
              len(list_versions(slug)) == articles.HISTORY_LIMIT, str(len(list_versions(slug))))
        recent = list_versions(slug)
        check("la più recente per prima", recent[0]["id"] > recent[-1]["id"])
    finally:
        delete_article(slug)
    check("eliminare l'articolo elimina le sue versioni", not history_folder(slug).exists())


def test_rename():
    print("\nun articolo rinominato si porta dietro le versioni")
    slug = save_article(payload("prova-cronologia-vecchio", "Uno"), new_article=True)
    save_article(payload(slug, "Due"))
    new = save_article(payload("prova-cronologia-nuovo", "Tre", original=slug))
    delete_article(slug)  # what the server does after a rename
    try:
        # One version: the rename came within ten minutes of the first save.
        versions = list_versions(new)
        check("le versioni sono sotto il nome nuovo",
              len(versions) == 1 and load_version(new, versions[0]["id"])["content"] == "<p>Uno</p>", str(versions))
        check("sotto il nome vecchio non resta niente", not history_folder(slug).exists())
    finally:
        delete_article(new)


def test_safe_reads():
    print("\nletture sicure")
    check("un id che non è un momento non legge niente", load_version("qualcosa", "../../config") is None)
    check("uno slug non valido non legge niente", list_versions("../posts") == [])
    check("un articolo senza versioni dà un elenco vuoto", list_versions("non-esiste-proprio") == [])


def test_interface():
    print("\nl'editor e le rotte")
    slug = save_article(payload("prova-cronologia-editor", "Uno"), new_article=True)
    try:
        check("un articolo salvato ha il pulsante delle versioni",
              'id="btn-versions" onclick="openVersions()"\n              aria-describedby="versions-help">'
              in server.editor_page(load_article(slug), "TOKEN"))
        check("uno nuovo lo ha nascosto",
              'aria-describedby="versions-help" hidden>' in server.editor_page(None, "TOKEN"))
    finally:
        delete_article(slug)
    check("le rotte chiedono l'accesso",
          "/versions" in server.ADMIN_GET_ROUTES and "/version" in server.ADMIN_GET_ROUTES)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    check("nginx le porta a Python", "|versions|version|" in nginx or "|versions|version)$" in nginx)


def main():
    was_there = HISTORY_DIR.exists()
    try:
        test_saves()
        test_rename()
        test_safe_reads()
        test_interface()
    finally:
        # The folder of the versions is left as it was found.
        if not was_there and HISTORY_DIR.exists() and not any(HISTORY_DIR.iterdir()):
            shutil.rmtree(HISTORY_DIR)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
