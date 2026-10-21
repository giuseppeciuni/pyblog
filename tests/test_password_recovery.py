#!/usr/bin/env python3
"""
Checks on the password recovery by email.

    python3 tests/test_password_recovery.py

A forgotten password used to need a terminal on the server. Now the login
page sends a link to the recovery email of the Settings: valid for half an
hour, once only, pointing at the site's own address and never at the Host
of the request. Everything runs against a real server and a small SMTP
server in memory, in a temporary folder.
"""
import email
import html
import pathlib
import re
import socketserver
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from email import policy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import auth, server  # noqa: E402
from core.config import CONFIG, admin_language  # noqa: E402
from core.i18n import T  # noqa: E402

PASSED = 0
FAILED = 0
RECEIVED = []


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


class MailServer(socketserver.StreamRequestHandler):
    """Speaks just enough SMTP for smtplib, and keeps every message."""

    def handle(self):
        self.wfile.write(b"220 prova\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode("utf-8", "replace").strip().upper()
            if command == "DATA":
                self.wfile.write(b"354 avanti\r\n")
                payload = []
                while True:
                    r = self.rfile.readline()
                    if r in (b".\r\n", b".\n", b""):
                        break
                    payload.append(r[1:] if r.startswith(b"..") else r)
                RECEIVED.append(email.message_from_bytes(b"".join(payload), policy=policy.default))
                self.wfile.write(b"250 ok\r\n")
            elif command == "QUIT":
                self.wfile.write(b"221 ciao\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


def test_tokens():
    print("\nil link di recupero")
    real_file = auth.PASSWORD_RESET_FILE
    with tempfile.TemporaryDirectory() as folder:
        auth.PASSWORD_RESET_FILE = pathlib.Path(folder) / ".password-reset.json"
        try:
            token = auth.create_reset_token(now=1000)
            check("un link appena creato vale", auth.reset_token_is_valid(token, now=1000))
            check("sul disco c'è solo l'impronta, non il link",
                  token not in auth.PASSWORD_RESET_FILE.read_text())
            check("dopo mezz'ora non vale più", not auth.reset_token_is_valid(token, now=1000 + 31 * 60))
            check("un link inventato non vale", not auth.reset_token_is_valid("inventato", now=1000))
            newer = auth.create_reset_token(now=1000)
            check("chiederne uno nuovo spegne il precedente",
                  not auth.reset_token_is_valid(token, now=1000) and auth.reset_token_is_valid(newer, now=1000))
            check("si usa una volta sola", auth.use_reset_token(newer, now=1001)
                  and not auth.use_reset_token(newer, now=1002))
        finally:
            auth.PASSWORD_RESET_FILE = real_file
    auth._LAST_RESET_EMAIL["at"] = 0.0
    check("al massimo un'email ogni due minuti",
          auth.reset_email_allowed(now=5000) and not auth.reset_email_allowed(now=5060)
          and auth.reset_email_allowed(now=5000 + auth.RESET_EMAIL_INTERVAL))


def test_link_address():
    print("\nl'indirizzo del link")
    saved = dict(CONFIG)
    try:
        CONFIG["admin_url"] = ""
        CONFIG["base_url"] = "https://www.example.org/"
        check("senza amministrazione separata, il dominio del sito", server.recovery_base() == "https://www.example.org")
        CONFIG["admin_url"] = "https://admin.example.org"
        check("con l'amministrazione separata, il suo indirizzo", server.recovery_base() == "https://admin.example.org")
        CONFIG["admin_url"] = ""
        CONFIG["base_url"] = server.CONFIG_DEFAULT["base_url"]
        check("con il dominio d'esempio non si manda niente", server.recovery_base() == ""
              and not server.recovery_available())
    finally:
        CONFIG.clear()
        CONFIG.update(saved)


def test_through_the_server():
    print("\nrichieste vere")
    saved = dict(CONFIG)
    real_files = (auth.PASSWORD_FILE, auth.PASSWORD_RESET_FILE)
    mail = socketserver.ThreadingTCPServer(("127.0.0.1", 0), MailServer)
    mail.daemon_threads = True
    threading.Thread(target=mail.serve_forever, daemon=True).start()
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    class DoNotFollow(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    open_url = urllib.request.build_opener(DoNotFollow).open

    def ask(path_value, fields=None, host=None):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        headers = {"Host": host} if host else {}
        request_value = urllib.request.Request(base + path_value, data=data, headers=headers)
        try:
            with open_url(request_value, timeout=30) as response:
                return response.status, response.read().decode("utf-8"), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace"), error.headers

    with tempfile.TemporaryDirectory() as folder:
        auth.PASSWORD_FILE = pathlib.Path(folder) / "password.txt"
        auth.PASSWORD_RESET_FILE = pathlib.Path(folder) / ".password-reset.json"
        auth.set_password("vecchia-123")
        CONFIG["base_url"] = "https://www.example.org"
        CONFIG["admin_url"] = ""
        CONFIG["newsletter"] = {"sender_email": "blog@example.org", "smtp_host": "127.0.0.1",
                                "smtp_port": mail.server_address[1], "smtp_security": "none"}
        lang = admin_language()
        try:
            CONFIG["recovery_email"] = ""
            _, page_html, _ = ask("/login?forgot=1")
            check("senza email di recupero la pagina dice come fare dal server",
                  "python3 pyblog.py password" in page_html)
            _, page_html, _ = ask("/login")
            check("la pagina di accesso porta al recupero", 'href="/login?forgot=1"' in page_html)

            CONFIG["recovery_email"] = "Autore@Example.org"
            auth._LAST_RESET_EMAIL["at"] = 0.0
            RECEIVED.clear()
            state, page_html, _ = ask("/login", {"action": "forgot", "email": "altro@example.org"})
            sent_text = html.escape(T("admin_recovery_sent", lang)[:40])
            check("un'email sbagliata riceve la stessa risposta, e nessuna email parte",
                  state == 200 and sent_text in page_html and RECEIVED == [])
            state, page_html, _ = ask("/login", {"action": "forgot", "email": "autore@example.org"},
                                      host="evil.example.com")
            check("l'email giusta (maiuscole a parte) riceve il link", len(RECEIVED) == 1
                  and RECEIVED[0]["To"] == "Autore@Example.org", str([m["To"] for m in RECEIVED]))
            body = RECEIVED[0].get_body(("plain",)).get_content() if RECEIVED else ""
            link = re.search(r"https?://\S+", body)
            link = link.group(0) if link else ""
            check("il link punta al sito, non all'host scritto nella richiesta",
                  link.startswith("https://www.example.org/login?reset=") and "evil" not in body, link)
            token = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("reset", [""])[0]
            ask("/login", {"action": "forgot", "email": "autore@example.org"})
            check("una seconda richiesta subito dopo non manda un'altra email", len(RECEIVED) == 1)

            _, page_html, _ = ask("/login?reset=" + token)
            check("il link apre la pagina della password nuova", 'name="action" value="reset"' in page_html)
            _, page_html, _ = ask("/login", {"action": "reset", "token": token,
                                             "password": "nuova-456", "confirm": "diversa-456"})
            check("due password diverse vengono rifiutate",
                  html.escape(T("err_new_passwords_dont_match", lang)) in page_html
                  and auth.verify_password("vecchia-123"))
            state, _, headers = ask("/login", {"action": "reset", "token": token,
                                               "password": "nuova-456", "confirm": "nuova-456"})
            check("la password nuova si salva e si entra", state == 303
                  and headers.get("Location", "").endswith("/admin")
                  and "session=" in headers.get("Set-Cookie", "")
                  and auth.verify_password("nuova-456") and not auth.verify_password("vecchia-123"))
            _, page_html, _ = ask("/login", {"action": "reset", "token": token,
                                             "password": "terza-789", "confirm": "terza-789"})
            check("lo stesso link non funziona una seconda volta",
                  html.escape(T("admin_reset_invalid", lang)[:30]) in page_html
                  and auth.verify_password("nuova-456"))
        finally:
            httpd.shutdown()
            httpd.server_close()
            mail.shutdown()
            mail.server_close()
            auth.PASSWORD_FILE, auth.PASSWORD_RESET_FILE = real_files
            auth.LOGIN_STATE.clear()
            CONFIG.clear()
            CONFIG.update(saved)


def main():
    test_tokens()
    test_link_address()
    test_through_the_server()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
