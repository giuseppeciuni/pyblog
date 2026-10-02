#!/usr/bin/env python3
"""
Checks on the login lock.

    python3 tests/test_login.py

The lock used to be one for the whole server: five wrong passwords from
anywhere locked everybody out for a minute, the owner of the blog included.
Anyone who could reach the login page could keep the author out of their
own editor by failing on purpose. Now each address has its own counter, and
the address is read from the reverse proxy when there is one.

Nothing here touches the disk: the lock lives in memory only.
"""
import html
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import auth, server  # noqa: E402
from core.config import admin_language  # noqa: E402
from core.i18n import T  # noqa: E402

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


def sbaglia(client, volte):
    for _ in range(volte):
        auth.record_failed_login(client)


def test_blocco_per_indirizzo():
    """Five errors lock the address that made them, and only that one."""
    print("\nil blocco riguarda chi sbaglia")
    auth.LOGIN_STATE.clear()
    sbaglia("203.0.113.9", 4)
    check("quattro errori non bloccano", not auth.login_is_locked("203.0.113.9"))
    sbaglia("203.0.113.9", 1)
    check("il quinto blocca quell'indirizzo", auth.login_is_locked("203.0.113.9"))
    check("un altro indirizzo entra lo stesso", not auth.login_is_locked("198.51.100.4"))
    check("il tempo rimasto e' quello di un primo blocco",
          55 <= auth.login_lock_remaining("203.0.113.9") <= 61,
          str(auth.login_lock_remaining("203.0.113.9")))
    check("chi non e' bloccato ha 0 secondi di attesa",
          auth.login_lock_remaining("198.51.100.4") == 0)


def test_blocchi_ripetuti_si_allungano():
    """A lock that repeats lasts longer, up to a ceiling."""
    print("\nblocchi ripetuti")
    auth.LOGIN_STATE.clear()
    durate = []
    for _ in range(7):
        sbaglia("203.0.113.9", auth.LOGIN_MAX_ATTEMPTS)
        durate.append(round(auth.LOGIN_STATE["203.0.113.9"]["locked_until"] - time.time()))
        # Pretend the lock has expired, as if the attacker waited it out.
        auth.LOGIN_STATE["203.0.113.9"]["locked_until"] = 0.0
    check("ogni blocco dura il doppio del precedente",
          durate[:4] == [60, 120, 240, 480], str(durate))
    check("ma mai piu' di 15 minuti", max(durate) == auth.LOGIN_LOCK_MAX_SECONDS, str(durate))


def test_accesso_riuscito_azzera():
    """A correct password forgets the errors of that address."""
    print("\naccesso riuscito")
    auth.LOGIN_STATE.clear()
    sbaglia("203.0.113.9", 3)
    sbaglia("198.51.100.4", 3)
    auth.record_successful_login("203.0.113.9")
    check("gli errori di chi entra vengono dimenticati",
          "203.0.113.9" not in auth.LOGIN_STATE)
    check("quelli degli altri restano",
          auth.LOGIN_STATE.get("198.51.100.4", {}).get("errors") == 3)


def test_indirizzi_dimenticati():
    """Quiet addresses are dropped, so the table cannot grow forever."""
    print("\npulizia")
    auth.LOGIN_STATE.clear()
    sbaglia("203.0.113.9", 1)
    auth.LOGIN_STATE["203.0.113.9"]["seen"] = time.time() - auth.LOGIN_FORGET_SECONDS - 5
    sbaglia("198.51.100.4", 1)
    check("un indirizzo silenzioso da piu' di un'ora viene dimenticato",
          "203.0.113.9" not in auth.LOGIN_STATE)
    sbaglia("203.0.113.9", auth.LOGIN_MAX_ATTEMPTS)
    auth.LOGIN_STATE["203.0.113.9"]["seen"] = time.time() - auth.LOGIN_FORGET_SECONDS - 5
    sbaglia("198.51.100.4", 1)
    check("ma non se e' ancora bloccato", "203.0.113.9" in auth.LOGIN_STATE)


class Intestazioni(dict):
    """The headers of a fake request: dict.get is all the handler uses."""


def indirizzo(peer, intestazioni):
    gestore = server.Handler.__new__(server.Handler)
    gestore.client_address = (peer, 50000)
    gestore.headers = Intestazioni(intestazioni)
    return gestore._client_address()


def test_indirizzo_dietro_il_proxy():
    """The visitor's address is read from the proxy, and only from it."""
    print("\nindirizzo del visitatore")
    check("senza proxy conta l'indirizzo della connessione",
          indirizzo("203.0.113.9", {}) == "203.0.113.9")
    check("dietro nginx vale X-Real-IP",
          indirizzo("127.0.0.1", {"X-Real-IP": "198.51.100.4"}) == "198.51.100.4")
    check("senza X-Real-IP vale l'ultimo indirizzo di X-Forwarded-For",
          indirizzo("127.0.0.1", {"X-Forwarded-For": "10.0.0.1, 198.51.100.4"})
          == "198.51.100.4")
    check("X-Real-IP vince su X-Forwarded-For",
          indirizzo("127.0.0.1", {"X-Real-IP": "198.51.100.4",
                                  "X-Forwarded-For": "1.2.3.4"}) == "198.51.100.4")
    check("da una connessione esterna le intestazioni non contano",
          indirizzo("203.0.113.9", {"X-Real-IP": "1.2.3.4",
                                    "X-Forwarded-For": "1.2.3.4"}) == "203.0.113.9",
          "chi si collega direttamente potrebbe scrivere l'indirizzo che vuole")
    check("anche in IPv6 locale si legge il proxy",
          indirizzo("::1", {"X-Real-IP": "198.51.100.4"}) == "198.51.100.4")
    check("in locale senza proxy resta 127.0.0.1",
          indirizzo("127.0.0.1", {}) == "127.0.0.1")


def test_attraverso_il_server():
    """The whole path: real requests, as nginx would forward them."""
    print("\nrichieste vere")
    import http.server
    import tempfile
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request

    auth.LOGIN_STATE.clear()
    file_vero = auth.PASSWORD_FILE
    with tempfile.TemporaryDirectory() as cartella:
        auth.PASSWORD_FILE = pathlib.Path(cartella) / "password.txt"
        auth.set_password("giusta-123")
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        class NonSeguire(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        apri = urllib.request.build_opener(NonSeguire).open

        def accedi(password, visitatore):
            corpo = urllib.parse.urlencode({"password": password}).encode()
            richiesta = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/login", data=corpo,
                headers={"X-Real-IP": visitatore})
            try:
                with apri(richiesta, timeout=30) as risposta:
                    return risposta.status, risposta.read().decode("utf-8")
            except urllib.error.HTTPError as errore:
                return errore.code, ""

        try:
            for _ in range(auth.LOGIN_MAX_ATTEMPTS):
                accedi("sbagliata", "203.0.113.9")
            stato, pagina = accedi("giusta-123", "203.0.113.9")
            avviso = T("err_too_many_attempts", admin_language()).split("{n}")[0]
            check("chi ha sbagliato 5 volte e' bloccato anche con la password giusta",
                  stato == 200 and html.escape(avviso) in pagina, pagina[:200])
            stato, _ = accedi("giusta-123", "198.51.100.4")
            check("un altro visitatore entra subito", stato == 303, str(stato))
        finally:
            httpd.shutdown()
            httpd.server_close()
            auth.PASSWORD_FILE = file_vero


def main():
    try:
        test_blocco_per_indirizzo()
        test_blocchi_ripetuti_si_allungano()
        test_accesso_riuscito_azzera()
        test_indirizzi_dimenticati()
        test_indirizzo_dietro_il_proxy()
        test_attraverso_il_server()
    finally:
        auth.LOGIN_STATE.clear()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
