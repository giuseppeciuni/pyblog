#!/usr/bin/env python3
"""
Checks on the media library.

    python3 tests/test_media_library.py

The library lists the uploaded files and says where each is used, so the
author can clear out the ones nothing uses without leaving a hole in a page.
Deleting moves a file to a trash outside the published folder, where it
waits a month. Everything runs in a temporary folder: the real media are
never touched.
"""
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import media_library, server  # noqa: E402

PASSED = 0
FAILED = 0
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


ARTICLES = [
    {"slug": "primo", "title": "Il primo", "status": "published",
     "content": '<p><img src="/media/foto.png"></p><video src="/media/video.mp4"></video>',
     "image": ""},
    {"slug": "bozza", "title": "Una bozza", "status": "draft",
     "content": "", "image": "https://www.ciunix.com/media/copertina.jpg"},
]
CONFIG = {"seo": {"author_image": "/media/foto.png"}, "projects": {"items": []}}


class Library:
    """A media folder and a trash in a temporary folder."""

    def __init__(self):
        self.folder = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.folder.name)
        self.saved = (media_library.MEDIA_DIR, media_library.TRASH_DIR,
                      media_library.load_articles, media_library.load_config)
        media_library.MEDIA_DIR = root / "output" / "media"
        media_library.TRASH_DIR = root / "backups" / "deleted-media"
        media_library.load_articles = lambda: ARTICLES
        media_library.load_config = lambda: CONFIG
        media_library.MEDIA_DIR.mkdir(parents=True)
        for name in ("foto.png", "copertina.jpg", "dimenticata.png", "video.mp4"):
            (media_library.MEDIA_DIR / name).write_bytes(PNG + name.encode())
        (media_library.MEDIA_DIR / ".nascosto").write_bytes(b"x")
        self.root = root

    def close(self):
        (media_library.MEDIA_DIR, media_library.TRASH_DIR,
         media_library.load_articles, media_library.load_config) = self.saved
        self.folder.cleanup()


def test_list_and_uses():
    print("\nfile e usi")
    lib = Library()
    try:
        names = sorted(m["name"] for m in media_library.media_files())
        check("elenca i file caricati, non quelli nascosti",
              names == ["copertina.jpg", "dimenticata.png", "foto.png", "video.mp4"], str(names))
        kinds = {m["name"]: m["kind"] for m in media_library.media_files()}
        check("sa cos'è un video e cos'è un'immagine",
              kinds["video.mp4"] == "video" and kinds["foto.png"] == "image")
        uses = media_library.media_uses()
        check("trova un'immagine nel testo di un articolo e nelle impostazioni",
              [u["kind"] for u in uses["foto.png"]] == ["article", "settings"], str(uses.get("foto.png")))
        check("e la copertina di una bozza, anche scritta con l'indirizzo completo",
              uses["copertina.jpg"][0]["slug"] == "bozza")
        check("un file che nessuno usa non compare", "dimenticata.png" not in uses)
    finally:
        lib.close()


def test_deleting():
    print("\neliminare")
    lib = Library()
    try:
        done = media_library.delete_media(["dimenticata.png", "../segreto.txt", "a/b.png",
                                            "non-esiste.png", ".nascosto", 42])
        check("elimina solo i nomi semplici di file che ci sono", done == ["dimenticata.png"], str(done))
        check("il file va nel cestino, fuori dalla cartella pubblicata",
              not (media_library.MEDIA_DIR / "dimenticata.png").exists()
              and (media_library.TRASH_DIR / "dimenticata.png").is_file())
        check("una lista che non è una lista non elimina niente",
              media_library.delete_media("foto.png") == [])
        old = media_library.TRASH_DIR / "vecchio.png"
        old.write_bytes(PNG)
        long_ago = time.time() - (media_library.TRASH_DAYS + 1) * 86400
        os.utime(old, (long_ago, long_ago))
        media_library.empty_trash()
        check("dopo un mese il cestino si svuota da solo",
              not old.exists() and (media_library.TRASH_DIR / "dimenticata.png").exists())
    finally:
        lib.close()


def test_page():
    print("\nla pagina")
    lib = Library()
    try:
        page_html = server.library_page("TOKEN")
        check("una scheda per file", page_html.count('<li class="media-card"') == 4)
        check("ogni uso porta all'articolo o alle impostazioni",
              '<a href="/edit?slug=primo">Il primo</a>' in page_html and '<a href="/config">' in page_html)
        check("il file non usato è segnato, e contato nella pulizia",
              'data-name="dimenticata.png" data-used="0"' in page_html
              and "(1, 1 KB)" in page_html, page_html[page_html.find("Elimina i non"):][:80])
        check("i video si vedono come video", '<video src="/media/video.mp4"' in page_html)
        saved_batch = server.MEDIA_BATCH
        server.MEDIA_BATCH = 3
        try:
            paged = server.library_page("TOKEN")
        finally:
            server.MEDIA_BATCH = saved_batch
        check("una libreria grande mostra un blocco alla volta: le schede dopo il primo partono nascoste",
              paged.count('<li class="media-card"') == 4
              and len([line for line in paged.splitlines()
                       if '<li class="media-card"' in line and line.endswith(" hidden>")]) == 1)
        check("con il pulsante per gli altri e la misura del blocco per lo script",
              'id="media-library-more"' in paged and '"media_batch": 3' in paged)
        check("il nome arriva al JavaScript senza virgolette in più",
              'onclick="deleteMedia(this, &quot;dimenticata.png&quot;, 0)"' in page_html
              and 'onclick="copyMediaAddress(&quot;/media/foto.png&quot;)"' in page_html,
              page_html[page_html.find("deleteMedia(this,"):][:60])
        check("il menu porta alla libreria e la segna",
              'aria-current="page" href="/media-library"' in page_html)
        sidebar_html = page_html[page_html.index('class="bar-bottom"'):]
        check("ma la barra del telefono resta a quattro voci", 'href="/media-library"' not in sidebar_html
              and sidebar_html.count('class="bar-item"') == 4)
        media_library.delete_media(["dimenticata.png"])
        page_html = server.library_page("TOKEN")
        check("senza file inutilizzati, il pulsante della pulizia si nasconde",
              'onclick="deleteUnusedMedia(this)" hidden' in page_html)
        check("l'eliminazione chiede il token CSRF", "/media-library-delete" in server.CSRF_PROTECTED_ROUTES)
    finally:
        lib.close()


def test_duplicates():
    print("\nla stessa immagine salvata più volte")
    folder = tempfile.TemporaryDirectory()
    root = pathlib.Path(folder.name)
    from core import articles
    saved = (media_library.MEDIA_DIR, media_library.TRASH_DIR, media_library.POSTS_DIR,
             media_library.load_articles, media_library.load_config, media_library.save_config,
             articles.MEDIA_DIR)
    media_dir = root / "output" / "media"
    media_dir.mkdir(parents=True)
    posts = root / "posts"
    posts.mkdir()
    config = {"seo": {"author_image": "/media/schema-1.png"}}
    stored = []
    try:
        media_library.MEDIA_DIR = articles.MEDIA_DIR = media_dir
        media_library.TRASH_DIR = root / "backups" / "deleted-media"
        media_library.POSTS_DIR = posts
        media_library.load_config = lambda: config
        media_library.save_config = stored.append
        picture = PNG + b"schema"
        first = articles.save_uploaded_file("schema.png", picture)
        again = articles.save_uploaded_file("doc-image1.png", picture)
        check("caricare di nuovo la stessa immagine riusa il file che c'è",
              first == again == "/media/schema.png" and sorted(p.name for p in media_dir.iterdir()) == ["schema.png"],
              str((first, again)))
        other = articles.save_uploaded_file("schema.png", PNG + b"altro")
        check("un'immagine diversa con lo stesso nome prende un nome nuovo", other == "/media/schema-1.png")

        # Copies left by the imports of before: same bytes, other names.
        (media_dir / "schema-2.png").write_bytes(picture)
        (media_dir / "schema-3.png").write_bytes(picture)
        os.utime(media_dir / "schema.png", (time.time() - 100, time.time() - 100))
        groups = media_library.duplicate_groups()
        check("trova le copie, la più vecchia per prima",
              groups == [["schema.png", "schema-2.png", "schema-3.png"]], str(groups))
        article = {"slug": "uno", "title": "Uno", "status": "published",
                   "content": '<p><img src="/media/schema-2.png"></p><p><img src="/media/schema-3.png"></p>',
                   "image": "/media/schema-10.png"}
        (posts / "uno.json").write_text(__import__("json").dumps(article))
        media_library.load_articles = lambda: [__import__("json").loads((posts / "uno.json").read_text())]
        outcome = media_library.merge_duplicates()
        merged = __import__("json").loads((posts / "uno.json").read_text())
        # The copy that stays is the one already used: fewer uses to rewrite.
        check("unire i doppioni tiene la copia già usata e toglie le altre", outcome == {"merged": 2, "articles": 1}
              and sorted(p.name for p in media_dir.iterdir()) == ["schema-1.png", "schema-2.png"], str(outcome))
        check("e l'articolo usa la copia che resta",
              merged["content"].count("/media/schema-2.png") == 2 and "schema-3" not in merged["content"])
        check("senza toccare un nome che comincia allo stesso modo", merged["image"] == "/media/schema-10.png")
        check("le copie vanno nel cestino", (media_library.TRASH_DIR / "schema.png").is_file()
              and (media_library.TRASH_DIR / "schema-3.png").is_file())
        check("le impostazioni che non usano copie restano come sono", stored == [])
        check("una seconda volta non c'è più niente da unire",
              media_library.merge_duplicates() == {"merged": 0, "articles": 0})
    finally:
        (media_library.MEDIA_DIR, media_library.TRASH_DIR, media_library.POSTS_DIR,
         media_library.load_articles, media_library.load_config, media_library.save_config,
         articles.MEDIA_DIR) = saved
        folder.cleanup()


def test_sizes():
    print("\nle versioni leggere delle immagini")
    lib = Library()
    from core import build
    try:
        webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 20
        check("una versione WebP di un'immagine che c'è si salva",
              media_library.save_size("foto.png", 480, webp)
              and (media_library.MEDIA_DIR / "_sizes" / "foto.png" / "480.webp").is_file())
        media_library.save_size("foto.png", 960, webp)
        check("si rifiuta ciò che non è WebP", not media_library.save_size("foto.png", 480, PNG))
        check("e le versioni di un file che non c'è, o di un nome che porta altrove",
              not media_library.save_size("manca.png", 480, webp)
              and not media_library.save_size("../foto.png", 480, webp)
              and not media_library.save_size("video.mp4", 480, webp))
        check("e le larghezze assurde", not media_library.save_size("foto.png", 99999, webp)
              and not media_library.save_size("foto.png", "480", webp))
        check("le larghezze si leggono in ordine", media_library.sized_widths("foto.png") == [480, 960])
        names = [m["name"] for m in media_library.media_files()]
        check("la cartella delle versioni non compare tra i file", "_sizes" not in names, str(names))
        content = build.responsive_images('<p><img src="/media/foto.png" width="300"></p>'
                                          '<p><img src="https://example.com/x.png"></p>')
        check("la pagina offre le versioni in srcset, con la misura dell'immagine nell'editor",
              'srcset="/media/_sizes/foto.png/480.webp 480w, /media/_sizes/foto.png/960.webp 960w"' in content
              and 'sizes="(max-width: 760px) 100vw, 300px"' in content, content)
        check("un'immagine di un altro sito resta com'è", '<img src="https://example.com/x.png">' in content)
        check("anche con l'indirizzo completo del sito",
              "srcset=" in build.responsive_attributes("https://www.ciunix.com/media/foto.png", "720px"))
        media_library.delete_media(["foto.png"])
        check("eliminando l'immagine se ne vanno anche le versioni",
              not (media_library.MEDIA_DIR / "_sizes" / "foto.png").exists())
    finally:
        lib.close()
    check("il caricamento delle versioni passa dalla rotta di sempre, già in nginx",
          "size_of" in pathlib.Path(server.__file__).read_text())


def main():
    test_list_and_uses()
    test_sizes()
    test_deleting()
    test_page()
    test_duplicates()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
