#!/usr/bin/env python3
"""
Checks on how articles and settings reach the disk.

    python3 tests/test_saves.py

The bug behind this file destroyed a published article without a sound: a
new article given the title of an existing one was saved under the same
slug, so it replaced the old file. The autosave made it worse, because it
does that on its own a minute after the title is typed. Importing a Word or
Markdown file with a familiar title did the same.

The rest is the same family: a config.json half written by an interrupted
save, a backup that came back without its pictures, a deletion that reported
success for an article it had not touched.

Every article and file created here is removed at the end, and config.json
is put back exactly as it was found.
"""
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import urllib.request
import zipfile

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core import config, server  # noqa: E402
from core.articles import (SlugTakenError, clean_editor_markup,  # noqa: E402
                           delete_article, import_markdown, load_article,
                           requested_slug, save_article)
from core.auth import create_session_token  # noqa: E402
from core.config import MEDIA_DIR, POSTS_DIR, write_json_atomically  # noqa: E402

PASSED = 0
FAILED = 0

# The article everybody else collides with. It is created by the test, so
# the real articles of the blog are never part of the experiment.
ORIGINAL = {
    "title": "Prova salvataggi",
    "slug": "prova-salvataggi",
    "content": "<p>Il testo che non deve sparire.</p>",
    "status": "published",
}

# Slugs this file may create: all of them are removed at the end.
TEST_SLUG = ["prova-salvataggi", "prova-salvataggi-2", "prova-salvataggi-3",
                 "prova-salvataggi-rinominato", "prova-salvataggi-md"]


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


def handler():
    """A request handler with no socket: enough to call the JSON endpoints."""
    return server.Handler.__new__(server.Handler)


def test_new_article_does_not_overwrite():
    """A new article with a taken slug gets a free one."""
    print("\nun articolo nuovo non prende il posto di un altro")
    save_article(dict(ORIGINAL))

    # Exactly what the editor sends for an article never saved before.
    new = {"title": ORIGINAL["title"], "slug": "", "original_slug": "",
             "content": "<p>bozza nuova</p>", "status": "draft"}
    response = handler()._api_save(dict(new))
    check("il salvataggio riesce", response.get("ok") is True, str(response))
    check("finisce su un indirizzo libero",
          response.get("slug") == "prova-salvataggi-2", str(response.get("slug")))
    check("l'editor viene avvisato del cambio di indirizzo",
          "prova-salvataggi-2" in response.get("notice", ""))

    old = load_article("prova-salvataggi")
    check("l'articolo originale e' ancora pubblicato",
          old is not None and old.get("status") == "published")
    check("e ha ancora il suo testo",
          old is not None and "non deve sparire" in old.get("content", ""))

    third = handler()._api_save(dict(new))
    check("un terzo con lo stesso titolo va su -3",
          third.get("slug") == "prova-salvataggi-3", str(third.get("slug")))


def test_update_and_rename():
    """Saving an article in place still works, renaming onto another does not."""
    print("\naggiornare e rinominare")

    # The second save of the article created above: original_slug is set.
    response = handler()._api_save({
        "title": "Seconda versione", "slug": "prova-salvataggi-2",
        "original_slug": "prova-salvataggi-2", "content": "<p>aggiornato</p>",
        "status": "draft"})
    check("salvare di nuovo aggiorna lo stesso file",
          response.get("slug") == "prova-salvataggi-2"
          and "aggiornato" in load_article("prova-salvataggi-2").get("content", ""))
    check("senza avvisi di cambio indirizzo", "notice" not in response)

    # A rename onto the address of the original article.
    before = (POSTS_DIR / "prova-salvataggi.json").read_text(encoding="utf-8")
    response = handler()._api_save({
        "title": "Seconda versione", "slug": "prova-salvataggi",
        "original_slug": "prova-salvataggi-2", "content": "<p>invasore</p>",
        "status": "draft"})
    check("la rinomina su un indirizzo occupato viene rifiutata",
          response.get("ok") is False and "prova-salvataggi" in response.get("error", ""),
          str(response))
    check("l'articolo che aveva quell'indirizzo non e' cambiato di un byte",
          (POSTS_DIR / "prova-salvataggi.json").read_text(encoding="utf-8") == before)
    check("e quello che voleva rinominarsi c'e' ancora",
          load_article("prova-salvataggi-2") is not None)

    try:
        save_article({"title": "x", "slug": "prova-salvataggi",
                       "original_slug": "prova-salvataggi-3"})
        check("save_article solleva SlugTakenError", False)
    except SlugTakenError as error:
        check("save_article solleva SlugTakenError con lo slug chiesto",
              error.slug == "prova-salvataggi")

    # A free rename still works, and removes the old address.
    response = handler()._api_save({
        "title": "Seconda versione", "slug": "prova-salvataggi-rinominato",
        "original_slug": "prova-salvataggi-3", "content": "<p>spostato</p>",
        "status": "draft"})
    check("una rinomina libera riesce",
          response.get("slug") == "prova-salvataggi-rinominato")
    check("e il vecchio indirizzo non esiste piu'",
          load_article("prova-salvataggi-3") is None)


def test_empty_slug_keeps_the_old_one():
    """Changing the title of a saved article must not move it."""
    print("\nil titolo cambia, l'indirizzo no")
    check("slug vuoto con original_slug: resta l'originale",
          requested_slug({"title": "Tutt'altro titolo", "slug": "",
                          "original_slug": "prova-salvataggi"}) == "prova-salvataggi")
    check("slug vuoto senza original_slug: viene dal titolo",
          requested_slug({"title": "Tutt'altro titolo"}) == "tutt-altro-titolo")
    check("uno slug scritto a mano viene ripulito",
          requested_slug({"slug": "../Fuori/Strada"}) == "fuori-strada")


def test_valid_state():
    """Only the two known states reach the disk."""
    print("\nstato dell'articolo")
    save_article({"title": "x", "slug": "prova-salvataggi-rinominato",
                  "status": "pubblicatissimo"})
    check("uno stato sconosciuto diventa bozza",
          load_article("prova-salvataggi-rinominato").get("status") == "draft")
    response = handler()._api_toggle_status({"slug": "prova-salvataggi-rinominato",
                                             "status": "<script>"})
    check("il cambio di stato rifiuta valori inventati", response.get("ok") is False)
    response = handler()._api_toggle_status({"slug": "prova-salvataggi-rinominato",
                                             "status": "published"})
    check("e accetta quelli veri", response.get("ok") is True
          and load_article("prova-salvataggi-rinominato").get("status") == "published")


def test_honest_deletion():
    """Deleting something that is not there is an error, not a success."""
    print("\ncancellare")
    response = handler()._api_delete({"slug": "non-esiste-proprio"})
    check("cancellare un articolo inesistente non risponde ok", response.get("ok") is False)
    response = handler()._api_delete({})
    check("una richiesta senza slug non fa danni", response.get("ok") is False)


def test_editor_marks_removed():
    """The editor's own markers never reach a published page."""
    print("\nsegni dell'editor")
    html_editor = ('<div class="raw-html-block pb-table-selected" contenteditable="false" '
                   'data-hint="Doppio clic per modificare"><table class="article-table">'
                   '<tbody><tr><td>a</td></tr></tbody></table></div><p>testo</p>')
    clean = clean_editor_markup(html_editor)
    check("il suggerimento sopra la tabella sparisce", "data-hint" not in clean)
    check("la classe di selezione sparisce", "pb-table-selected" not in clean)
    check("le classi vere restano", 'class="raw-html-block"' in clean)
    check("contenteditable resta (serve all'editor quando ricarica)",
          'contenteditable="false"' in clean)
    save_article({"title": "x", "slug": "prova-salvataggi-rinominato",
                  "original_slug": "prova-salvataggi-rinominato",
                  "content": html_editor})
    check("e non arrivano nel file salvato",
          "data-hint" not in load_article("prova-salvataggi-rinominato")["content"])


def test_atomic_write():
    """A failed write leaves the old file whole and no debris behind."""
    print("\nscrittura a prova di interruzione")
    with tempfile.TemporaryDirectory() as folder:
        path_value = pathlib.Path(folder) / "dati.json"
        write_json_atomically(path_value, {"versione": 1})
        check("il file scritto e' JSON valido",
              json.loads(path_value.read_text(encoding="utf-8")) == {"versione": 1})
        try:
            # A set cannot be turned into JSON: the dump fails halfway.
            write_json_atomically(path_value, {"versione": 2, "rotto": {1, 2}})
        except TypeError:
            pass
        check("dopo un errore il file vecchio e' intatto",
              json.loads(path_value.read_text(encoding="utf-8")) == {"versione": 1})
        check("e non restano file temporanei",
              sorted(p.name for p in pathlib.Path(folder).iterdir()) == ["dati.json"])


def test_broken_config():
    """An unreadable config.json does not stop the site."""
    print("\nconfig.json illeggibile")
    real_file = config.CONFIG_FILE
    real_copy = config.BROKEN_CONFIG_FILE
    with tempfile.TemporaryDirectory() as folder:
        fake_value = pathlib.Path(folder) / "config.json"
        fake_value.write_text('{"site_title": "Mezzo file', encoding="utf-8")
        config.CONFIG_FILE = fake_value
        config.BROKEN_CONFIG_FILE = pathlib.Path(folder) / "config.broken.json"
        try:
            loaded = config.load_config()
            check("si parte con i valori predefiniti",
                  loaded.get("site_title") == config.CONFIG_DEFAULT["site_title"])
            check("il file rotto viene messo da parte",
                  config.BROKEN_CONFIG_FILE.read_text(encoding="utf-8") == '{"site_title": "Mezzo file')
            fake_value.write_text("[1, 2, 3]", encoding="utf-8")
            check("anche un JSON che non e' un oggetto non blocca nulla",
                  isinstance(config.load_config(), dict))
        finally:
            config.CONFIG_FILE = real_file
            config.BROKEN_CONFIG_FILE = real_copy


def test_broken_article_does_not_block_editor():
    """A damaged article file is skipped, not a server error."""
    print("\narticolo illeggibile")
    broken_value = POSTS_DIR / "prova-salvataggi-md.json"
    broken_value.write_text("{ non e' json", encoding="utf-8")
    check("load_article restituisce None invece di esplodere",
          load_article("prova-salvataggi-md") is None)
    broken_value.unlink()


def test_markdown_import_does_not_overwrite():
    """Importing a file with a familiar title adds a copy."""
    print("\nimport Markdown")
    with tempfile.TemporaryDirectory() as folder:
        md = pathlib.Path(folder) / "doppione.md"
        md.write_text("---\ntitle: Prova salvataggi\nslug: prova-salvataggi\n---\n\n"
                      "Testo importato.\n", encoding="utf-8")
        before = (POSTS_DIR / "prova-salvataggi.json").read_text(encoding="utf-8")
        output = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = output
        try:
            import_markdown(str(md))
        finally:
            sys.stdout = old_stdout
        check("l'articolo con quello slug e' intatto",
              (POSTS_DIR / "prova-salvataggi.json").read_text(encoding="utf-8") == before)
        check("la console dice dove e' finito l'import",
              "already taken" in output.getvalue(), output.getvalue())
    # The copy took the first free numbered slug: clean it up.
    for slug in ("prova-salvataggi-2", "prova-salvataggi-3", "prova-salvataggi-4"):
        article = load_article(slug)
        if article is not None and "importato" in article.get("content", ""):
            delete_article(slug)
            TEST_SLUG.append(slug)


def test_backup_with_images():
    """The backup carries the uploaded media, not only the texts."""
    print("\nbackup")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    image = MEDIA_DIR / "zz-prova-backup.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        token = create_session_token()
        request_value = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/export",
            headers={"Cookie": "session=" + token})
        with urllib.request.urlopen(request_value, timeout=30) as response:
            payload = response.read()
        archive = zipfile.ZipFile(io.BytesIO(payload))
        names = archive.namelist()
        check("il backup contiene gli articoli",
              any(n.startswith("posts/") for n in names))
        check("il backup contiene le immagini caricate",
              "media/zz-prova-backup.png" in names, str(names[:8]))
        check("le immagini non vengono ricompresse",
              archive.getinfo("media/zz-prova-backup.png").compress_type == zipfile.ZIP_STORED)
        check("e arrivano intatte",
              archive.read("media/zz-prova-backup.png") == image.read_bytes())
    finally:
        httpd.shutdown()
        httpd.server_close()
        image.unlink(missing_ok=True)


def main():
    original_config = None
    if config.CONFIG_FILE.exists():
        original_config = config.CONFIG_FILE.read_text(encoding="utf-8")
    try:
        test_new_article_does_not_overwrite()
        test_update_and_rename()
        test_empty_slug_keeps_the_old_one()
        test_valid_state()
        test_honest_deletion()
        test_editor_marks_removed()
        test_atomic_write()
        test_broken_config()
        test_broken_article_does_not_block_editor()
        test_markdown_import_does_not_overwrite()
        test_backup_with_images()
    finally:
        for slug in TEST_SLUG:
            delete_article(slug)
        if original_config is None:
            config.CONFIG_FILE.unlink(missing_ok=True)
        else:
            config.CONFIG_FILE.write_text(original_config, encoding="utf-8")
        server.build_module.build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
