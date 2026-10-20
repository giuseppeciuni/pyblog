#!/usr/bin/env python3
"""
Checks on the media library.

    python3 tests/test_libreria.py

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
            (media_library.MEDIA_DIR / name).write_bytes(PNG)
        (media_library.MEDIA_DIR / ".nascosto").write_bytes(b"x")
        self.root = root

    def close(self):
        (media_library.MEDIA_DIR, media_library.TRASH_DIR,
         media_library.load_articles, media_library.load_config) = self.saved
        self.folder.cleanup()


def test_elenco_e_usi():
    print("\nfile e usi")
    lib = Library()
    try:
        nomi = sorted(m["name"] for m in media_library.media_files())
        check("elenca i file caricati, non quelli nascosti",
              nomi == ["copertina.jpg", "dimenticata.png", "foto.png", "video.mp4"], str(nomi))
        tipi = {m["name"]: m["kind"] for m in media_library.media_files()}
        check("sa cos'è un video e cos'è un'immagine",
              tipi["video.mp4"] == "video" and tipi["foto.png"] == "image")
        usi = media_library.media_uses()
        check("trova un'immagine nel testo di un articolo e nelle impostazioni",
              [u["kind"] for u in usi["foto.png"]] == ["article", "settings"], str(usi.get("foto.png")))
        check("e la copertina di una bozza, anche scritta con l'indirizzo completo",
              usi["copertina.jpg"][0]["slug"] == "bozza")
        check("un file che nessuno usa non compare", "dimenticata.png" not in usi)
    finally:
        lib.close()


def test_eliminare():
    print("\neliminare")
    lib = Library()
    try:
        fatti = media_library.delete_media(["dimenticata.png", "../segreto.txt", "a/b.png",
                                            "non-esiste.png", ".nascosto", 42])
        check("elimina solo i nomi semplici di file che ci sono", fatti == ["dimenticata.png"], str(fatti))
        check("il file va nel cestino, fuori dalla cartella pubblicata",
              not (media_library.MEDIA_DIR / "dimenticata.png").exists()
              and (media_library.TRASH_DIR / "dimenticata.png").is_file())
        check("una lista che non è una lista non elimina niente",
              media_library.delete_media("foto.png") == [])
        vecchio = media_library.TRASH_DIR / "vecchio.png"
        vecchio.write_bytes(PNG)
        un_tempo = time.time() - (media_library.TRASH_DAYS + 1) * 86400
        os.utime(vecchio, (un_tempo, un_tempo))
        media_library.empty_trash()
        check("dopo un mese il cestino si svuota da solo",
              not vecchio.exists() and (media_library.TRASH_DIR / "dimenticata.png").exists())
    finally:
        lib.close()


def test_pagina():
    print("\nla pagina")
    lib = Library()
    try:
        pagina = server.library_page("TOKEN")
        check("una scheda per file", pagina.count('<li class="media-scheda"') == 4)
        check("ogni uso porta all'articolo o alle impostazioni",
              '<a href="/edit?slug=primo">Il primo</a>' in pagina and '<a href="/config">' in pagina)
        check("il file non usato è segnato, e contato nella pulizia",
              'data-nome="dimenticata.png" data-usato="0"' in pagina
              and "(1, 1 KB)" in pagina, pagina[pagina.find("Elimina i non"):][:80])
        check("i video si vedono come video", '<video src="/media/video.mp4"' in pagina)
        check("il nome arriva al JavaScript senza virgolette in più",
              'onclick="deleteMedia(this, &quot;dimenticata.png&quot;, 0)"' in pagina
              and 'onclick="copyMediaAddress(&quot;/media/foto.png&quot;)"' in pagina,
              pagina[pagina.find("deleteMedia(this,"):][:60])
        check("il menu porta alla libreria e la segna",
              'aria-current="page" href="/media-library"' in pagina)
        barra = pagina[pagina.index('class="barra-basso"'):]
        check("ma la barra del telefono resta a quattro voci", 'href="/media-library"' not in barra
              and barra.count('class="barra-voce"') == 4)
        media_library.delete_media(["dimenticata.png"])
        pagina = server.library_page("TOKEN")
        check("senza file inutilizzati, il pulsante della pulizia si nasconde",
              'onclick="deleteUnusedMedia(this)" hidden' in pagina)
        check("l'eliminazione chiede il token CSRF", "/media-library-delete" in server.CSRF_PROTECTED_ROUTES)
    finally:
        lib.close()


def main():
    test_elenco_e_usi()
    test_eliminare()
    test_pagina()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
