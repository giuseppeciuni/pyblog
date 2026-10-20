#!/usr/bin/env python3
"""
Checks on the administration living at an address of its own.

    python3 tests/test_admin_separato.py

The code of outside services on the public pages (analytics, ads, widgets)
runs on the site's origin. When the administration answers on that same
origin, such code can read what the logged-in author sees: settings and API
keys included. With "admin_url" set, the administration answers only at its
own address, and the public address only serves the site.

The requests here are real ones, with the headers nginx adds. Nothing is
written to disk: the configuration is changed in memory and put back.
"""
import http.server
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import config, server  # noqa: E402
from core.config import CONFIG, admin_address, url_host  # noqa: E402

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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPEN = urllib.request.build_opener(NoRedirect).open
PROXY = {"X-Real-IP": "203.0.113.9", "X-Forwarded-Proto": "https"}


def request(base, path, host, method="GET", proxied=True, body=None):
    headers = {"Host": host}
    if proxied:
        headers.update(PROXY)
    req = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with OPEN(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), ""


def test_indirizzi():
    print("\nleggere gli indirizzi")
    check("un indirizzo valido", admin_address({"admin_url": "https://admin.ciunix.com/"})
          == "https://admin.ciunix.com")
    check("vuoto: nessun indirizzo a parte", admin_address({"admin_url": ""}) == "")
    for sbagliato in ("admin.ciunix.com", "https://admin.ciunix.com/editor", "javascript:alert(1)",
                      "https://admin.ciunix.com?x=1"):
        check(f"scritto male non conta: {sbagliato}", admin_address({"admin_url": sbagliato}) == "")
    check("l'host come lo scrive il browser",
          url_host("https://Admin.Ciunix.com") == "admin.ciunix.com"
          and url_host("https://admin.ciunix.com:443") == "admin.ciunix.com"
          and url_host("http://localhost:8000") == "localhost:8000")


def test_richieste():
    print("\nrichieste vere")
    saved = {k: CONFIG.get(k) for k in ("admin_url", "base_url")}
    CONFIG["admin_url"] = "https://admin.ciunix.com"
    CONFIG["base_url"] = "https://www.ciunix.com"
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        stato, testata, _ = request(base, "/config?x=1", "www.ciunix.com")
        check("sull'indirizzo pubblico l'admin manda al suo indirizzo, con la stessa pagina",
              stato == 303 and testata.get("Location") == "https://admin.ciunix.com/config?x=1",
              f"{stato} {testata.get('Location')}")
        stato, _, _ = request(base, "/save", "www.ciunix.com", "POST", body=b"{}")
        check("sull'indirizzo pubblico nessuna richiesta all'admin arriva", stato == 404, str(stato))
        stato, _, _ = request(base, "/login", "www.ciunix.com", "POST", body=b"password=x")
        check("nemmeno il login", stato == 404, str(stato))
        # Leaving the newsletter answers even with the newsletter off.
        stato, _, _ = request(base, "/disiscrivi", "www.ciunix.com", "POST", body=b"token=x")
        check("i moduli dei lettori sì", stato != 404, str(stato))

        stato, _, pagina = request(base, "/admin", "admin.ciunix.com")
        check("sull'indirizzo dell'admin l'admin risponde (qui con l'accesso)",
              stato == 200 and "password" in pagina.lower(), str(stato))
        stato, testata, _ = request(base, "/posts/un-articolo.html", "admin.ciunix.com")
        check("sull'indirizzo dell'admin una pagina del sito va al sito pubblico",
              stato == 303 and testata.get("Location") == "https://www.ciunix.com/posts/un-articolo.html",
              f"{stato} {testata.get('Location')}")
        stato, testata, _ = request(base, "/", "admin.ciunix.com")
        check("e la radice dell'admin apre l'admin", stato == 303 and testata.get("Location") == "/admin")
        stato, _, _ = request(base, "/style.css", "admin.ciunix.com")
        check("fogli di stile e immagini restano: servono alle anteprime", stato != 303, str(stato))

        stato, _, _ = request(base, "/admin", "www.ciunix.com", proxied=False)
        check("chi arriva direttamente all'editor, senza nginx, entra come sempre", stato == 200)
        stato, _, _ = request(base, "/admin", "127.0.0.1:8000")
        check("e anche un proxy che non passa l'host: un errore di nginx non chiude fuori",
              stato == 200)

        stato, testata, corpo = request(base, "/pyblog-ping?n=inventata", "admin.ciunix.com")
        check("il segnale di vita non riconosce una parola che non ha inventato lui",
              stato == 200 and json.loads(corpo) == {"pyblog": True, "same": False})

        gestore = server.Handler.__new__(server.Handler)
        CONFIG["admin_language"] = "it"
        check("un indirizzo che porta a questo editor viene riconosciuto",
              gestore._api_check_admin_address({"url": base}) == {"ok": True, "reaches": True})
        check("un indirizzo che non risponde no",
              gestore._api_check_admin_address({"url": "http://127.0.0.1:9"})
              == {"ok": True, "reaches": False})
        check("un indirizzo scritto male viene rifiutato prima di chiedere",
              gestore._api_check_admin_address({"url": "http://127.0.0.1:9/x"})["ok"] is False)
        check("dopo il controllo la parola viene dimenticata", len(server.PING_NONCES) == 0)

        CONFIG["admin_url"] = ""
        stato, _, _ = request(base, "/admin", "www.ciunix.com")
        check("senza indirizzo a parte, tutto come prima", stato == 200)
        CONFIG["admin_url"] = "admin.ciunix.com/sbagliato"
        stato, _, _ = request(base, "/admin", "www.ciunix.com")
        check("con un indirizzo scritto male, tutto come prima", stato == 200)
    finally:
        httpd.shutdown()
        httpd.server_close()
        for key, value in saved.items():
            if value is None:
                CONFIG.pop(key, None)
            else:
                CONFIG[key] = value


def test_impostazioni():
    print("\nle impostazioni")
    pagina = server.config_page("TOKEN")
    check("il campo c'è, con la sua etichetta",
          'id="admin_url"' in pagina and 'for="admin_url"' in pagina)
    js = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("prima di salvare un indirizzo nuovo, lo fa provare al server",
          "pbPostJson('/check-admin-address'" in js
          and "checkAdminAddress(pulsante, indirizzoAdmin)" in js)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    # Every page of the administration has to reach Python: a route left
    # out of the single-address example answers 404 online.
    import re
    riga = re.search(r"location ~ \^/\(([^)]*)\)\$", nginx).group(1).replace("\\.", ".").split("|")
    rotte = {r.lstrip("/") for r in server.ADMIN_GET_ROUTES + server.CSRF_PROTECTED_ROUTES}
    rotte |= {"login", "logout", "set-password", "pyblog-ping"}
    mancanti = sorted(rotte - set(riga))
    check("con l'admin sull'indirizzo del sito, nginx porta a Python ogni rotta dell'admin",
          mancanti == [], str(mancanti))
    esempio = (pathlib.Path(__file__).resolve().parent.parent / "nginx.separate-admin.conf.example")
    check("c'è l'esempio di nginx con l'admin a parte", esempio.is_file())
    if esempio.is_file():
        testo = esempio.read_text()
        check("l'esempio passa l'host e l'indirizzo del visitatore",
              "proxy_set_header Host $host;" in testo and "X-Real-IP" in testo)


def main():
    test_indirizzi()
    test_richieste()
    test_impostazioni()
    config.CONFIG["admin_language"] = config.CONFIG.get("admin_language", "it")
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
