#!/usr/bin/env python3
"""
Checks on the publishing panel of the editor, and on the preview that saves
nothing.

    python3 tests/test_editor_publish.py

The editor had "Save and generate HTML" and "Save and close", with the state
of the article in a dropdown further down: nothing next to the buttons said
whether saving would change the live site. The buttons now follow the state.
What is worth checking is what each state offers, and that the preview - the
one button that must never write - really writes nothing: previewing a
published article used to save it, and so put its half-done changes online.
"""
import re
import http.server
import json
import pathlib
import sys
import threading
import urllib.parse
import urllib.request

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

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


def test_panel_by_state():
    """Each state offers its own buttons, and only those make sense."""
    print("\nil pannello segue lo stato dell'articolo")
    draft = server.editor_page(load_article(SLUG), "TOKEN")
    check("una bozza si apre come bozza", 'data-state="draft"' in draft)
    for button in ("btn-publish", "btn-save-draft", "btn-preview", "btn-update"):
        check(f"la pagina ha {button}", f'id="{button}"' in draft)
    check("la tendina dello stato non c'è più", 'id="status"' not in draft)
    check('"Salva e chiudi" non c\'è più', "saveAndClose" not in draft)
    check("Elimina sta in fondo alla barra, dopo la traduzione",
          draft.rfind("btn-delete-article") > draft.rfind("translation-section"))
    check("c'è il link per tornare agli articoli",
          re.search(r'class="[^"]*\bback-to-articles\b[^"]*" href="/admin"', draft) is not None)

    new = server.editor_page(None, "TOKEN")
    check("un articolo nuovo è una bozza, senza Elimina",
          'data-state="draft"' in new and "btn-delete-article" not in new)

    odd = server.editor_page({"slug": SLUG, "title": "x", "status": "boh"}, "TOKEN")
    check("uno stato sconosciuto si apre come bozza", 'data-state="draft"' in odd)

    article = load_article(SLUG)
    article["status"] = "published"
    save_article(article)
    published = server.editor_page(load_article(SLUG), "TOKEN")
    check("un articolo pubblicato si apre come pubblicato", 'data-state="published"' in published)
    check("con il link alla sua pagina", f'href="/posts/{SLUG}.html"' in published)
    article["status"] = "draft"
    save_article(article)


def test_same_words_as_dashboard():
    """The dashboard and the editor call taking an article back the same way."""
    print("\nla dashboard usa le parole dell'editor")
    article = load_article(SLUG)
    article["status"] = "published"
    save_article(article)
    dashboard = server.admin_page(load_articles(), "TOKEN")
    editor = server.editor_page(load_article(SLUG), "TOKEN")
    withdraw = T("admin_withdraw", admin_language())
    check(f'la dashboard dice "{withdraw}"', withdraw in dashboard)
    check("come l'editor", withdraw in editor)
    check('"Metti in bozza" non c\'è più', "Metti in bozza" not in dashboard)
    article["status"] = "draft"
    save_article(article)


def test_save_says_where():
    """The save tells the editor where the published page lives."""
    print("\nil salvataggio restituisce l'indirizzo della pagina")
    handler = server.Handler.__new__(server.Handler)
    response = handler._api_save(dict(load_article(SLUG), original_slug=SLUG))
    check("la risposta porta l'indirizzo", response.get("url") == f"/posts/{SLUG}.html",
          json.dumps(response))


def test_preview_does_not_save():
    """The preview shows the article as the editor holds it, and writes nothing."""
    print("\nl'anteprima non scrive niente")
    article_file = POSTS_DIR / f"{SLUG}.json"
    before = article_file.read_bytes()
    list_before = sorted(p.name for p in POSTS_DIR.glob("*.json"))

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    address = f"http://127.0.0.1:{httpd.server_address[1]}/preview"
    token = create_session_token()

    def preview(payload, lingua="it", csrf=None, cookie=True):
        if csrf is None:
            csrf = csrf_token_for(token)
        corpo = urllib.parse.urlencode(
            {"csrf_token": csrf, "language": lingua, "data": json.dumps(payload)}).encode()
        intestazioni = {"Cookie": "sessione=" + token} if cookie else {}
        request_value = urllib.request.Request(address, data=corpo, headers=intestazioni)
        with urllib.request.urlopen(request_value, timeout=30) as response:
            return response.status, response.headers, response.read().decode("utf-8")

    payload = {"title": "Titolo MAI SALVATO", "slug": SLUG, "original_slug": SLUG,
            "content": "<p>Testo MAI SALVATO.</p>", "status": "published",
            "title_en": "Title NEVER SAVED", "content_en": "<p>Text NEVER SAVED.</p>",
            "translation_authorized": True, "translation_confirmed": True}
    try:
        stato, intestazioni, page_html = preview(payload)
        check("risponde con la pagina come è nell'editor",
              stato == 200 and "Titolo MAI SALVATO" in page_html and "Testo MAI SALVATO" in page_html,
              page_html[:200])
        check("senza la CSP dell'amministrazione, come le pagine pubbliche",
              "default-src" not in intestazioni.get("Content-Security-Policy", ""))
        check("ma chiusa nel sandbox: i codici esterni non raggiungono l'editor",
              intestazioni.get("Content-Security-Policy") == server.PREVIEW_SANDBOX
              and "allow-same-origin" not in server.PREVIEW_SANDBOX)
        check("il file dell'articolo non è cambiato", article_file.read_bytes() == before)

        _, _, page_html = preview(payload, "en")
        check("nell'altra lingua mostra la traduzione", "Title NEVER SAVED" in page_html)

        _, _, page_html = preview({"title": "Articolo mai salvato", "content": "<p>Ciao.</p>"})
        check("anche un articolo mai salvato ha la sua anteprima", "Articolo mai salvato" in page_html)
        check("e nessun file è nato o sparito",
              sorted(p.name for p in POSTS_DIR.glob("*.json")) == list_before)

        _, _, response = preview(payload, csrf="sbagliato")
        check("senza il token giusto non mostra niente",
              "MAI SALVATO" not in response and '"ok": false' in response, response[:120])
        _, _, response = preview(payload, cookie=False)
        check("senza essere entrati non mostra niente",
              "MAI SALVATO" not in response and '"ok": false' in response, response[:120])
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    save_article({"title": "Prova del pannello", "slug": SLUG,
                  "content": "<p>Contenuto di prova.</p>", "status": "draft", "tags": "Test"})
    try:
        test_panel_by_state()
        test_same_words_as_dashboard()
        test_save_says_where()
        test_preview_does_not_save()
    finally:
        delete_article(SLUG)
        build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
