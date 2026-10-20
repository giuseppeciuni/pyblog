#!/usr/bin/env python3
"""
Checks on putting a backup back.

    python3 tests/test_restore.py

Restoring from the administration turns an uploaded archive into files on
the server, so most of these checks are archives built to deceive it: names
that climb out of the folder, a web page dressed as a picture, a file that
unpacks far past what it declares. Everything runs in a temporary folder;
the real posts, media and configuration are never touched.
"""
import json
import pathlib
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import backup, server  # noqa: E402

PASSED = 0
FAILED = 0

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG_ACTIVE = (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>'
              b'<rect width="10" height="10"/></svg>')


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


class Site:
    """A whole site in a temporary folder, with backup.py pointed at it."""

    def __init__(self):
        self.folder = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.folder.name)
        self.saved = {name: getattr(backup, name) for name in
                      ("BASE_DIR", "POSTS_DIR", "MEDIA_DIR", "CONFIG_FILE", "SUBSCRIBERS_FILE",
                       "BACKUPS_DIR")}
        backup.BASE_DIR = root
        backup.POSTS_DIR = root / "posts"
        backup.MEDIA_DIR = root / "output" / "media"
        backup.CONFIG_FILE = root / "config.json"
        backup.SUBSCRIBERS_FILE = root / "subscribers.json"
        backup.BACKUPS_DIR = root / "backups"
        self.root = root
        backup.POSTS_DIR.mkdir()
        backup.MEDIA_DIR.mkdir(parents=True)
        (backup.POSTS_DIR / "vecchio.json").write_text(json.dumps({"slug": "vecchio", "title": "Vecchio"}))
        (backup.MEDIA_DIR / "vecchia.png").write_bytes(PNG)
        backup.CONFIG_FILE.write_text(json.dumps({"site_title": "Prima",
                                                  "admin_url": "https://admin.qui.it"}))

    def close(self):
        for name, value in self.saved.items():
            setattr(backup, name, value)
        self.folder.cleanup()


# The archives the checks build, all in one folder removed at the end.
ARCHIVES = tempfile.TemporaryDirectory()
COUNTER = [0]


def archive(entries):
    """A ZIP archive from {name: bytes}."""
    COUNTER[0] += 1
    path_value = pathlib.Path(ARCHIVES.name) / f"archivio-{COUNTER[0]}.zip"
    with zipfile.ZipFile(path_value, "w") as zip_file:
        for name, data in entries.items():
            zip_file.writestr(name, data)
    return path_value


def good_backup():
    return archive({
        "config.json": json.dumps({"site_title": "Dal backup", "admin_url": "https://altro.it"}),
        "posts/nuovo.json": json.dumps({"slug": "nuovo", "title": "Nuovo"}),
        "posts/.history/nuovo/20261001T120000Z.json": json.dumps({"title": "Versione"}),
        "subscribers.json": json.dumps({"subscribers": []}),
        "media/foto.png": PNG,
        "media/disegno.svg": SVG_ACTIVE,
    })


def refused(path_value):
    try:
        backup.read_backup(path_value)
    except backup.BackupError as error:
        return str(error)
    return None


def test_full_restore():
    print("\nun backup vero")
    site = Site()
    try:
        content = backup.read_backup(good_backup())
        saved = backup.save_automatic_backup()
        summary = backup.restore_backup(content)
        root = site.root
        check("gli articoli sono quelli del backup, i vecchi non ci sono più",
              sorted(p.name for p in (root / "posts").glob("*.json")) == ["nuovo.json"])
        check("con le loro versioni precedenti",
              (root / "posts" / ".history" / "nuovo" / "20261001T120000Z.json").is_file())
        check("i file multimediali sono quelli del backup",
              sorted(p.name for p in backup.MEDIA_DIR.iterdir()) == ["disegno.svg", "foto.png"])
        check("un SVG torna senza le sue parti attive",
              b"<script" not in (backup.MEDIA_DIR / "disegno.svg").read_bytes())
        config = json.loads((root / "config.json").read_text())
        check("le impostazioni sono quelle del backup", config["site_title"] == "Dal backup")
        check("ma l'indirizzo dell'amministrazione resta quello che funziona qui",
              config["admin_url"] == "https://admin.qui.it")
        check("gli iscritti tornano", (root / "subscribers.json").is_file())
        check("il riepilogo conta tutto",
              summary["articles"] == 1 and summary["versions"] == 1 and summary["media"] == 2
              and summary["config"] and summary["subscribers"] and summary["ignored"] == [], str(summary))
        with zipfile.ZipFile(saved) as zip_file:
            names = zip_file.namelist()
        check("prima, lo stato di prima è stato salvato tra i backup automatici",
              "posts/vecchio.json" in names and "media/vecchia.png" in names and "config.json" in names)
        leftovers = [p.name for p in root.iterdir() if p.name.startswith(".")]
        check("non restano cartelle di lavoro", leftovers == [], str(leftovers))
        # Undo: the automatic backup puts the old state back.
        backup.restore_backup(backup.read_backup(saved))
        check("il backup automatico rimette tutto com'era",
              sorted(p.name for p in (root / "posts").glob("*.json")) == ["vecchio.json"]
              and (backup.MEDIA_DIR / "vecchia.png").is_file())
    finally:
        site.close()


def test_partial_backup():
    print("\nun backup senza media")
    site = Site()
    try:
        content = backup.read_backup(archive({"posts/nuovo.json": json.dumps({"slug": "nuovo"})}))
        backup.restore_backup(content)
        check("le immagini del sito restano dove sono", (backup.MEDIA_DIR / "vecchia.png").is_file())
        check("e anche la configurazione",
              json.loads(backup.CONFIG_FILE.read_text())["site_title"] == "Prima")
    finally:
        site.close()


def test_deceptive_archives():
    print("\narchivi costruiti per ingannare")
    site = Site()
    try:
        testo = pathlib.Path(ARCHIVES.name) / "testo.zip"
        testo.write_text("non sono uno zip")
        check("un file che non è uno zip viene rifiutato", refused(testo) == "err_backup_not_zip")
        check("uno zip qualsiasi, senza articoli né impostazioni, non è un backup",
              refused(archive({"foto.jpg": PNG})) == "err_backup_not_pyblog")
        check("un JSON rovinato ferma tutto",
              refused(archive({"posts/a.json": "{non json"})) == "err_backup_json")
        content = backup.read_backup(archive({
            "posts/a.json": "{}",
            "../../fuori.json": "{}",
            "/etc/passwd": "x",
            "posts/../config.json": "{}",
            "media/../../escape.png": PNG,
            "media/pagina.html": "<script>alert(1)</script>",
            "media/finta.png": b"<html>non sono un png</html>",
            "media/.nascosto.png": PNG,
            "media/nome con spazi.png": PNG,
            "posts/.history/a/non-una-data.json": "{}",
        }))
        check("i nomi che escono dalle cartelle, le pagine web e i falsi PNG restano fuori",
              content["media"] == {} and list(content["posts"]) == ["a.json"]
              and len(content["ignored"]) == 9, str(content["ignored"]))
        backup.restore_backup(content)
        check("e niente è stato scritto fuori dal sito",
              not (site.root.parent / "fuori.json").exists()
              and not (site.root / "escape.png").exists())
        large = archive({"posts/a.json": "{" + " " * (backup.MAX_JSON + 10) + "}"})
        check("un file oltre il suo limite ferma tutto", refused(large) == "err_backup_file_too_large")
    finally:
        site.close()


def test_automatic_backups():
    print("\nbackup automatici")
    site = Site()
    try:
        names = []
        for i in range(backup.KEEP_AUTOMATIC + 2):
            path_value = backup.save_automatic_backup()
            # Same second: rename so each one is distinct, oldest first.
            new = path_value.with_name(f"pyblog-auto-2026010{i}-120000.zip")
            path_value.rename(new)
            names.append(new.name)
        backup.save_automatic_backup()
        remaining = [b["name"] for b in backup.automatic_backups()]
        check(f"ne restano {backup.KEEP_AUTOMATIC}, i più recenti",
              len(remaining) == backup.KEEP_AUTOMATIC and names[0] not in remaining, str(remaining))
        check("un nome inventato non apre niente",
              backup.automatic_backup_path("../config.json") is None
              and backup.automatic_backup_path("pyblog-automatico-x.zip") is None)
        check("un nome vero sì", backup.automatic_backup_path(remaining[0]) is not None)
        old = backup.BACKUPS_DIR / "pyblog-automatico-20250101-120000.zip"
        old.write_bytes(b"PK")
        check("anche un backup con il vecchio nome italiano viene riconosciuto",
              backup.automatic_backup_path(old.name) is not None)
    finally:
        site.close()


def test_page_and_menu():
    print("\npagina e menu")
    page_html = server.restore_page("TOKEN")
    check("la pagina ha il campo del file con la sua etichetta",
          'id="file-ripristino"' in page_html and 'for="file-ripristino"' in page_html)
    check("il menu porta alla pagina, e la segna", 'href="/restore"' in page_html
          and 'aria-current="page" href="/restore"' in page_html)
    site = Site()
    try:
        nome = backup.save_automatic_backup().name
        page_html = server.restore_page("TOKEN")
        check("«Rimetti questo» passa il nome giusto al JavaScript",
              f'onclick="restoreAutomatic(this, &quot;{nome}&quot;)"' in page_html)
    finally:
        site.close()
    check("il ripristino chiede il token CSRF", "/restore" in server.CSRF_PROTECTED_ROUTES
          and "/restore-automatic" in server.CSRF_PROTECTED_ROUTES)
    check("il backup scaricato e quello automatico sono lo stesso archivio",
          "backup.write_backup(archive)" in pathlib.Path(server.__file__).read_text())
    names = [m for m, _ in __import__("core.bundle", fromlist=["x"]).BUNDLED_MODULES]
    check("il modulo entra nel file unico, prima del server",
          names.index("core.backup") < names.index("core.server"))


def main():
    try:
        test_full_restore()
        test_partial_backup()
        test_deceptive_archives()
        test_automatic_backups()
        test_page_and_menu()
    finally:
        ARCHIVES.cleanup()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
