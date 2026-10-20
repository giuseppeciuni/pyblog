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


def fail_login(client, times):
    for _ in range(times):
        auth.record_failed_login(client)


def test_lock_per_address():
    """Five errors lock the address that made them, and only that one."""
    print("\nil blocco riguarda chi sbaglia")
    auth.LOGIN_STATE.clear()
    fail_login("203.0.113.9", 4)
    check("quattro errori non bloccano", not auth.login_is_locked("203.0.113.9"))
    fail_login("203.0.113.9", 1)
    check("il quinto blocca quell'indirizzo", auth.login_is_locked("203.0.113.9"))
    check("un altro indirizzo entra lo stesso", not auth.login_is_locked("198.51.100.4"))
    check("il tempo rimasto e' quello di un primo blocco",
          55 <= auth.login_lock_remaining("203.0.113.9") <= 61,
          str(auth.login_lock_remaining("203.0.113.9")))
    check("chi non e' bloccato ha 0 secondi di attesa",
          auth.login_lock_remaining("198.51.100.4") == 0)


def test_repeated_locks_grow_longer():
    """A lock that repeats lasts longer, up to a ceiling."""
    print("\nblocchi ripetuti")
    auth.LOGIN_STATE.clear()
    durations = []
    for _ in range(7):
        fail_login("203.0.113.9", auth.LOGIN_MAX_ATTEMPTS)
        durations.append(round(auth.LOGIN_STATE["203.0.113.9"]["locked_until"] - time.time()))
        # Pretend the lock has expired, as if the attacker waited it out.
        auth.LOGIN_STATE["203.0.113.9"]["locked_until"] = 0.0
    check("ogni blocco dura il doppio del precedente",
          durations[:4] == [60, 120, 240, 480], str(durations))
    check("ma mai piu' di 15 minuti", max(durations) == auth.LOGIN_LOCK_MAX_SECONDS, str(durations))


def test_successful_login_resets():
    """A correct password forgets the errors of that address."""
    print("\naccesso riuscito")
    auth.LOGIN_STATE.clear()
    fail_login("203.0.113.9", 3)
    fail_login("198.51.100.4", 3)
    auth.record_successful_login("203.0.113.9")
    check("gli errori di chi entra vengono dimenticati",
          "203.0.113.9" not in auth.LOGIN_STATE)
    check("quelli degli altri restano",
          auth.LOGIN_STATE.get("198.51.100.4", {}).get("errors") == 3)


def test_forgotten_addresses():
    """Quiet addresses are dropped, so the table cannot grow forever."""
    print("\npulizia")
    auth.LOGIN_STATE.clear()
    fail_login("203.0.113.9", 1)
    auth.LOGIN_STATE["203.0.113.9"]["seen"] = time.time() - auth.LOGIN_FORGET_SECONDS - 5
    fail_login("198.51.100.4", 1)
    check("un indirizzo silenzioso da piu' di un'ora viene dimenticato",
          "203.0.113.9" not in auth.LOGIN_STATE)
    fail_login("203.0.113.9", auth.LOGIN_MAX_ATTEMPTS)
    auth.LOGIN_STATE["203.0.113.9"]["seen"] = time.time() - auth.LOGIN_FORGET_SECONDS - 5
    fail_login("198.51.100.4", 1)
    check("ma non se e' ancora bloccato", "203.0.113.9" in auth.LOGIN_STATE)


class Headers(dict):
    """The headers of a fake request: dict.get is all the handler uses."""


def address(peer, header_lines):
    handler = server.Handler.__new__(server.Handler)
    handler.client_address = (peer, 50000)
    handler.headers = Headers(header_lines)
    return handler._client_address()


def test_address_behind_proxy():
    """The visitor's address is read from the proxy, and only from it."""
    print("\nindirizzo del visitatore")
    check("senza proxy conta l'indirizzo della connessione",
          address("203.0.113.9", {}) == "203.0.113.9")
    check("dietro nginx vale X-Real-IP",
          address("127.0.0.1", {"X-Real-IP": "198.51.100.4"}) == "198.51.100.4")
    check("senza X-Real-IP vale l'ultimo indirizzo di X-Forwarded-For",
          address("127.0.0.1", {"X-Forwarded-For": "10.0.0.1, 198.51.100.4"})
          == "198.51.100.4")
    check("X-Real-IP vince su X-Forwarded-For",
          address("127.0.0.1", {"X-Real-IP": "198.51.100.4",
                                  "X-Forwarded-For": "1.2.3.4"}) == "198.51.100.4")
    check("da una connessione esterna le intestazioni non contano",
          address("203.0.113.9", {"X-Real-IP": "1.2.3.4",
                                    "X-Forwarded-For": "1.2.3.4"}) == "203.0.113.9",
          "chi si collega direttamente potrebbe scrivere l'indirizzo che vuole")
    check("anche in IPv6 locale si legge il proxy",
          address("::1", {"X-Real-IP": "198.51.100.4"}) == "198.51.100.4")
    check("in locale senza proxy resta 127.0.0.1",
          address("127.0.0.1", {}) == "127.0.0.1")


def test_through_the_server():
    """The whole path: real requests, as nginx would forward them."""
    print("\nrichieste vere")
    import http.server
    import tempfile
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request

    auth.LOGIN_STATE.clear()
    real_file = auth.PASSWORD_FILE
    with tempfile.TemporaryDirectory() as folder:
        auth.PASSWORD_FILE = pathlib.Path(folder) / "password.txt"
        auth.set_password("giusta-123")
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        class DoNotFollow(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        open_url = urllib.request.build_opener(DoNotFollow).open

        def log_in(password, visitor):
            body = urllib.parse.urlencode({"password": password}).encode()
            request_value = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/login", data=body,
                headers={"X-Real-IP": visitor})
            try:
                with open_url(request_value, timeout=30) as response:
                    return response.status, response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                return error.code, ""

        try:
            for _ in range(auth.LOGIN_MAX_ATTEMPTS):
                log_in("sbagliata", "203.0.113.9")
            state, page_html = log_in("giusta-123", "203.0.113.9")
            notice = T("err_too_many_attempts", admin_language()).split("{n}")[0]
            check("chi ha sbagliato 5 volte e' bloccato anche con la password giusta",
                  state == 200 and html.escape(notice) in page_html, page_html[:200])
            state, _ = log_in("giusta-123", "198.51.100.4")
            check("un altro visitatore entra subito", state == 303, str(state))
        finally:
            httpd.shutdown()
            httpd.server_close()
            auth.PASSWORD_FILE = real_file


def test_server_defences():
    """First password, HEAD, CSRF on every route, links in the emails."""
    print("\ndifese del server")
    import http.server
    import json
    import os
    import stat
    import tempfile
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request

    class DoNotFollow(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    open_url = urllib.request.build_opener(DoNotFollow).open
    real_file = auth.PASSWORD_FILE
    with tempfile.TemporaryDirectory() as folder:
        auth.PASSWORD_FILE = pathlib.Path(folder) / "password.txt"
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def ask(path_value, body=None, header_lines=None, method_name=None):
            request_value = urllib.request.Request(base + path_value, data=body,
                                               headers=header_lines or {}, method=method_name)
            try:
                with open_url(request_value, timeout=30) as response:
                    return response.status, response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                return error.code, ""

        before = urllib.parse.urlencode({"password": "nuova-123", "confirm": "nuova-123"}).encode()
        try:
            ask("/set-password", before, {"X-Real-IP": "203.0.113.9"})
            check("la prima password non si crea da fuori, attraverso nginx",
                  not auth.PASSWORD_FILE.exists())
            state, _ = ask("/set-password", before)
            check("si crea collegandosi direttamente all'editor",
                  state == 303 and auth.PASSWORD_FILE.exists(), str(state))
            permissions = stat.S_IMODE(os.stat(auth.PASSWORD_FILE).st_mode)
            check("il file della password lo legge solo il proprietario",
                  permissions == 0o600, oct(permissions))
            check("e non lascia file temporanei",
                  [f.name for f in pathlib.Path(folder).iterdir()] == ["password.txt"])

            state, _ = ask("/admin_password.txt", method_name="HEAD")
            check("HEAD non serve piu' i file della cartella", state == 501, str(state))

            token = auth.create_session_token()
            state, text = ask("/rotta-nuova", b"{}", {"Cookie": "session=" + token})
            response = json.loads(text or "{}")
            check("una rotta POST non elencata chiede comunque il token CSRF",
                  response.get("error") == T("err_csrf", admin_language()), text[:200])
        finally:
            httpd.shutdown()
            httpd.server_close()
            auth.PASSWORD_FILE = real_file

    handler = server.Handler.__new__(server.Handler)
    handler.headers = Headers({"Host": "sito-di-un-altro.example"})
    check("i link delle email non prendono l'indirizzo dall'intestazione Host",
          "sito-di-un-altro" not in handler._site_url())


def main():
    try:
        test_lock_per_address()
        test_repeated_locks_grow_longer()
        test_successful_login_resets()
        test_forgotten_addresses()
        test_address_behind_proxy()
        test_through_the_server()
        test_server_defences()
    finally:
        auth.LOGIN_STATE.clear()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
