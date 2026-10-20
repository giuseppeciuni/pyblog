#!/usr/bin/env python3
"""
Checks on updates.

    python3 tests/test_updates.py

An update from the administration replaces the code of a running server,
so the checks use real git repositories in a temporary folder: one plays
GitHub, one the server. They cover what must stop an update (files edited
by hand, local commits, code that does not start) and what must happen
before one (the backup). Nothing here touches this checkout, and nothing
restarts.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import server, updates  # noqa: E402

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


def git(folder, *args):
    environment = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="t@t",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", *args], cwd=str(folder), capture_output=True, text=True,
                          env=environment, check=True).stdout.strip()


class Repositories:
    """GitHub (a bare repository), the author's copy, and the server's."""

    def __init__(self):
        self.folder = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.folder.name)
        self.remote = root / "github.git"
        self.author = root / "autore"
        self.server = root / "server"
        git(root, "init", "--quiet", "--bare", "-b", "main", str(self.remote))
        git(root, "clone", "--quiet", str(self.remote), str(self.author))
        self.commit("modulo.py", "VALORE = 1\n", "prima versione")
        git(root, "clone", "--quiet", str(self.remote), str(self.server))
        self.saved = (updates.BASE_DIR, updates.STATE_FILE, updates.CHECK_COMMAND)
        updates.BASE_DIR = self.server
        updates.STATE_FILE = root / "stato.json"
        updates.CHECK_COMMAND = [sys.executable, "-c", "import modulo"]

    def commit(self, name, text, subject):
        (self.author / name).write_text(text)
        git(self.author, "add", name)
        git(self.author, "commit", "--quiet", "-m", subject)
        git(self.author, "push", "--quiet", "origin", "HEAD:main")

    def close(self):
        updates.BASE_DIR, updates.STATE_FILE, updates.CHECK_COMMAND = self.saved
        self.folder.cleanup()


def test_versions():
    print("\nversioni")
    check("le versioni si confrontano come numeri",
          updates.version_tuple("1.10.0") > updates.version_tuple("1.9.3"))
    check("una versione scritta male non vale niente", updates.version_tuple("1.x") == ())
    testo = 'Docstring\n"""\n\n__version__ = "1.4.2"\n'
    check("la versione si legge da core/__init__.py", updates.VERSION_LINE.search(testo).group(1) == "1.4.2")
    real = updates.latest_release
    try:
        updates.latest_release = lambda url=None: "9.0.0"
        stato = updates.release_status()
        check("una versione più nuova su GitHub si vede", stato["behind"] == 1 and stato["latest"] == "9.0.0")
        updates.latest_release = lambda url=None: None
        check("senza rete lo dice", updates.release_status() == {"kind": "other", "error": "upd_offline"})
    finally:
        updates.latest_release = real


def test_updating():
    print("\naggiornare un checkout git")
    repos = Repositories()
    try:
        stato = updates.git_status()
        check("appena installato è aggiornato", stato["behind"] == 0 and not stato["can_update"], str(stato))
        repos.commit("modulo.py", "VALORE = 2\n", "feat: una novità")
        stato = updates.git_status()
        check("una novità su GitHub si vede, con il suo titolo",
              stato["behind"] == 1 and stato["news"] == ["feat: una novità"] and stato["can_update"])
        saved_items = []
        outcome = updates.update(save_backup=lambda: saved_items.append(True))
        check("l'aggiornamento riesce", outcome["ok"] is True, str(outcome))
        check("prima ha salvato il backup", saved_items == [True])
        check("il codice nuovo è al suo posto", (repos.server / "modulo.py").read_text() == "VALORE = 2\n")

        repos.commit("modulo.py", "VALORE = (\n", "fix: un errore di sintassi")
        before = git(repos.server, "rev-parse", "HEAD")
        outcome = updates.update()
        check("un codice che non parte non viene installato", outcome["ok"] is False
              and outcome["error"] == "upd_failed_upd", str(outcome))
        check("e il checkout torna dov'era", git(repos.server, "rev-parse", "HEAD") == before
              and (repos.server / "modulo.py").read_text() == "VALORE = 2\n")

        repos.commit("modulo.py", "VALORE = 3\n", "fix: sistemato")
        (repos.server / "modulo.py").write_text("VALORE = 'a mano'\n")
        outcome = updates.update()
        check("un file modificato a mano ferma l'aggiornamento, senza toccarlo",
              outcome == {"ok": False, "error": "upd_changes_made_local_edits"}
              and "a mano" in (repos.server / "modulo.py").read_text(), str(outcome))
        git(repos.server, "checkout", "--quiet", "--", "modulo.py")
        (repos.server / "locale.py").write_text("X = 1\n")
        git(repos.server, "add", "locale.py")
        git(repos.server, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "--quiet", "-m", "locale")
        check("anche un commit fatto sul server lo ferma",
              updates.update() == {"ok": False, "error": "upd_ahead"})
    finally:
        repos.close()


def test_check():
    print("\nil controllo e la sua memoria")
    repos = Repositories()
    try:
        real = updates.is_git_checkout
        updates.is_git_checkout = lambda: True
        stato = updates.check(force=True, now=1000)
        check("il controllo dice la versione e se è automatico",
              stato["version"] and stato["auto"] is True and stato["behind"] == 0)
        repos.commit("modulo.py", "VALORE = 5\n", "feat: altra novità")
        check("entro dodici ore risponde con l'ultimo controllo, senza chiedere a GitHub",
              updates.check(now=1000 + 3600)["behind"] == 0)
        check("dopo dodici ore controlla di nuovo",
              updates.check(now=1000 + 13 * 3600)["behind"] == 1)
        updates.set_automatic_check(False)
        repos.commit("modulo.py", "VALORE = 6\n", "feat: terza novità")
        check("spento il controllo automatico, non chiede più niente da solo",
              updates.check(now=1000 + 40 * 3600)["behind"] == 1)
        check("ma «Controlla adesso» chiede sempre", updates.check(force=True)["behind"] == 2)
        updates.is_git_checkout = real
    finally:
        repos.close()


def test_pages():
    print("\nle pagine")
    page_html = server.updates_page("TOKEN")
    check("il menu porta agli aggiornamenti, con la versione",
          'aria-current="page" href="/updates"' in page_html
          and server.T("admin_version", "it").replace("{v}", updates.__version__) in page_html)
    check("il controllo automatico si spegne con la sua casella",
          'id="automatic-check"' in page_html and 'for="automatic-check"' in page_html)
    article_list = server.admin_page([], "TOKEN")
    check("la pagina Articoli ha il posto per l'avviso, nascosto finché non serve",
          'id="notice-update-notice" role="status" hidden' in article_list)
    check("aggiornare chiede il token CSRF", "/update" in server.CSRF_PROTECTED_ROUTES)
    real_ones = (updates.update, updates.restart)
    restarts = []
    try:
        updates.update = lambda save_backup=None: {"ok": True, "from": "aaa", "to": "bbb"}
        updates.restart = lambda delay=1.0: restarts.append(delay)
        handler = server.Handler.__new__(server.Handler)
        check("un aggiornamento riuscito riavvia PyBlog",
              handler._api_update({}) == {"ok": True, "from": "aaa", "to": "bbb"} and len(restarts) == 1)
        updates.update = lambda save_backup=None: {"ok": False, "error": "upd_changes_made_local_edits"}
        outcome = handler._api_update({})
        check("uno fermato non riavvia, e dice perché",
              outcome["ok"] is False and "a mano" in outcome["error"] and len(restarts) == 1)
    finally:
        updates.update, updates.restart = real_ones


def main():
    test_versions()
    test_updating()
    test_check()
    test_pages()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
