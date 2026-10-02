#!/usr/bin/env python3
"""
Checks on the publishing panel of the editor, and on the preview that saves
nothing.

    python3 tests/test_editor_pubblica.py

The editor had "Save and generate HTML" and "Save and close", with the state
of the article in a dropdown further down: nothing next to the buttons said
whether saving would change the live site. The buttons now follow the state.
What is worth checking is what each state offers, and that the preview - the
one button that must never write - really writes nothing: previewing a
published article used to save it, and so put its half-done changes online.
"""
import http.server
import json
import pathlib
import sys
import threading
import urllib.parse
import urllib.request

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from core import server  # noqa: E402
from core.articles import (delete_article, load_article, load_articles,  # noqa: E402
                           save_article)
from core.config import admin_language  # noqa: E402
from core.i18n import T  # noqa: E402
from core.auth import create_session_token, csrf_token_for  # noqa: E402
from core.build import build  # noqa: E402
from core.config import POSTS_DIR  # noqa: E402

PASSED = 0
FAILED = 0

SLUG = "zz-prova-pannello"


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED = PASSED + 1
        print(f"  ok    {description}")
    else:
        FAILED = FAILED + 1
        print(f"  FAIL  {description}")
        if detail != "":
            print(f"        {detail}")


def test_pannello_per_stato():
    """Each state offers its own buttons, and only those make sense."""
    print("\nil pannello segue lo stato dell'articolo")
    bozza = server.editor_page(load_article(SLUG), "TOKEN")
    check("una bozza si apre come bozza", 'data-stato="draft"' in bozza)
    for pulsante in ("btn-pubblica", "btn-salva-bozza", "btn-anteprima", "btn-aggiorna"):
        check(f"la pagina ha {pulsante}", f'id="{pulsante}"' in bozza)
    check("la tendina dello stato non c'è più", 'id="status"' not in bozza)
    check('"Salva e chiudi" non c\'è più', "saveAndClose" not in bozza)
    check("Elimina sta in fondo alla barra, dopo la traduzione",
          bozza.rfind("btn-elimina-articolo") > bozza.rfind("translation-section"))
    check("c'è il link per tornare agli articoli", 'class="torna-articoli" href="/admin"' in bozza)

    nuovo = server.editor_page(None, "TOKEN")
    check("un articolo nuovo è una bozza, senza Elimina",
          'data-stato="draft"' in nuovo and "btn-elimina-articolo" not in nuovo)

    strano = server.editor_page({"slug": SLUG, "title": "x", "status": "boh"}, "TOKEN")
    check("uno stato sconosciuto si apre come bozza", 'data-stato="draft"' in strano)

    articolo = load_article(SLUG)
    articolo["status"] = "published"
    save_article(articolo)
    pubblicato = server.editor_page(load_article(SLUG), "TOKEN")
    check("un articolo pubblicato si apre come pubblicato", 'data-stato="published"' in pubblicato)
    check("con il link alla sua pagina", f'href="/posts/{SLUG}.html"' in pubblicato)
    articolo["status"] = "draft"
    save_article(articolo)


def test_stesse_parole_della_dashboard():
    """The dashboard and the editor call taking an article back the same way."""
    print("\nla dashboard usa le parole dell'editor")
    articolo = load_article(SLUG)
    articolo["status"] = "published"
    save_article(articolo)
    dashboard = server.admin_page(load_articles(), "TOKEN")
    editor = server.editor_page(load_article(SLUG), "TOKEN")
    ritira = T("admin_ritira", admin_language())
    check(f'la dashboard dice "{ritira}"', ritira in dashboard)
    check("come l'editor", ritira in editor)
    check('"Metti in bozza" non c\'è più', "Metti in bozza" not in dashboard)
    articolo["status"] = "draft"
    save_article(articolo)


def test_salvataggio_dice_dove():
    """The save tells the editor where the published page lives."""
    print("\nil salvataggio restituisce l'indirizzo della pagina")
    gestore = server.Handler.__new__(server.Handler)
    risposta = gestore._api_save(dict(load_article(SLUG), original_slug=SLUG))
    check("la risposta porta l'indirizzo", risposta.get("url") == f"/posts/{SLUG}.html",
          json.dumps(risposta))


def test_anteprima_non_salva():
    """The preview shows the article as the editor holds it, and writes nothing."""
    print("\nl'anteprima non scrive niente")
    file_articolo = POSTS_DIR / f"{SLUG}.json"
    prima = file_articolo.read_bytes()
    elenco_prima = sorted(p.name for p in POSTS_DIR.glob("*.json"))

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    indirizzo = f"http://127.0.0.1:{httpd.server_address[1]}/preview"
    token = create_session_token()

    def anteprima(dati, lingua="it", csrf=None, cookie=True):
        if csrf is None:
            csrf = csrf_token_for(token)
        corpo = urllib.parse.urlencode(
            {"csrf_token": csrf, "language": lingua, "data": json.dumps(dati)}).encode()
        intestazioni = {"Cookie": "sessione=" + token} if cookie else {}
        richiesta = urllib.request.Request(indirizzo, data=corpo, headers=intestazioni)
        with urllib.request.urlopen(richiesta, timeout=30) as risposta:
            return risposta.status, risposta.headers, risposta.read().decode("utf-8")

    dati = {"title": "Titolo MAI SALVATO", "slug": SLUG, "original_slug": SLUG,
            "content": "<p>Testo MAI SALVATO.</p>", "status": "published",
            "title_en": "Title NEVER SAVED", "content_en": "<p>Text NEVER SAVED.</p>",
            "translation_authorized": True, "translation_confirmed": True}
    try:
        stato, intestazioni, pagina = anteprima(dati)
        check("risponde con la pagina come è nell'editor",
              stato == 200 and "Titolo MAI SALVATO" in pagina and "Testo MAI SALVATO" in pagina,
              pagina[:200])
        check("senza la CSP dell'amministrazione, come le pagine pubbliche",
              intestazioni.get("Content-Security-Policy") is None)
        check("il file dell'articolo non è cambiato", file_articolo.read_bytes() == prima)

        _, _, pagina = anteprima(dati, "en")
        check("nell'altra lingua mostra la traduzione", "Title NEVER SAVED" in pagina)

        _, _, pagina = anteprima({"title": "Articolo mai salvato", "content": "<p>Ciao.</p>"})
        check("anche un articolo mai salvato ha la sua anteprima", "Articolo mai salvato" in pagina)
        check("e nessun file è nato o sparito",
              sorted(p.name for p in POSTS_DIR.glob("*.json")) == elenco_prima)

        _, _, risposta = anteprima(dati, csrf="sbagliato")
        check("senza il token giusto non mostra niente",
              "MAI SALVATO" not in risposta and '"ok": false' in risposta, risposta[:120])
        _, _, risposta = anteprima(dati, cookie=False)
        check("senza essere entrati non mostra niente",
              "MAI SALVATO" not in risposta and '"ok": false' in risposta, risposta[:120])
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    save_article({"title": "Prova del pannello", "slug": SLUG,
                  "content": "<p>Contenuto di prova.</p>", "status": "draft", "tags": "Test"})
    try:
        test_pannello_per_stato()
        test_stesse_parole_della_dashboard()
        test_salvataggio_dice_dove()
        test_anteprima_non_salva()
    finally:
        delete_article(SLUG)
        build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
