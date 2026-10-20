#!/usr/bin/env python3
"""
Checks on the newsletter.

    python3 tests/test_newsletter.py

A tiny SMTP server runs inside the test and keeps the emails it receives,
so the real sending code is exercised without anything leaving the machine.
The subscribers file is a temporary one, the configuration is put back and
the test articles are removed.
"""
import copy
import email
import pathlib
import re
import socketserver
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from email import policy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, newsletter, server  # noqa: E402
from core.articles import delete_article, load_article, save_article  # noqa: E402
from core.config import CONFIG, POSTS_DIR, write_json_atomically  # noqa: E402

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


# --- A minimal SMTP server --------------------------------------------------

RECEIVED = []


class MailServer(socketserver.StreamRequestHandler):
    """Speaks just enough SMTP for smtplib, and keeps every message."""

    def handle(self):
        self.wfile.write(b"220 prova\r\n")
        recipients = []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode("utf-8", "replace").strip().upper()
            if command.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250 prova\r\n")
            elif command.startswith("MAIL FROM"):
                recipients = []
                self.wfile.write(b"250 ok\r\n")
            elif command.startswith("RCPT TO"):
                recipients.append(command)
                self.wfile.write(b"250 ok\r\n")
            elif command == "DATA":
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


def start_mail_server():
    server_thread = socketserver.ThreadingTCPServer(("127.0.0.1", 0), MailServer)
    server_thread.daemon_threads = True
    threading.Thread(target=server_thread.serve_forever, daemon=True).start()
    return server_thread


def text_of(messaggio):
    parti = [p.get_content() for p in messaggio.walk() if p.get_content_type() == "text/plain"]
    return "\n".join(parti)


SITE_URL = "https://blog.example.org"


def set_value(port, **altro):
    nl = {"enabled": True, "sender_email": "blog@example.org", "sender_name": "Il blog",
          "smtp_host": "127.0.0.1", "smtp_port": port, "smtp_security": "none",
          "enabled_since": (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()}
    nl.update(altro)
    CONFIG["newsletter"] = nl


def test_settings():
    print("\nimpostazioni e indirizzi")
    s = newsletter.settings({"newsletter": {"smtp_port": "abc", "smtp_security": "boh", "enabled": "si"}})
    check("valori sbagliati tornano ai predefiniti", s["smtp_port"] == 587 and s["smtp_security"] == "starttls"
          and s["enabled"] is False)
    check("un indirizzo normale è valido", newsletter.valid_email("anna@example.org"))
    for bad in ("anna", "anna@", "a b@example.org", "anna@example.org\nBcc: x@y.z", "<anna@example.org>"):
        check(f"{bad!r} non è valido", not newsletter.valid_email(bad))


def test_subscription(port):
    print("\nl'iscrizione con doppio consenso")
    set_value(port)
    RECEIVED.clear()
    check("un indirizzo sbagliato non entra", newsletter.subscribe("non-un-indirizzo", "it", SITE_URL) == "invalid")
    check("un indirizzo buono riceve la risposta di sempre", newsletter.subscribe("Anna@Example.org ", "it", SITE_URL) == "ok")
    stato = newsletter.load_state()
    anna_entry = newsletter.find(stato, "email", "anna@example.org")
    check("è in attesa, in minuscolo, con la sua lingua", anna_entry and anna_entry["status"] == "pending" and anna_entry["language"] == "it")
    check("è arrivata un'email di conferma", len(RECEIVED) == 1 and "Conferma" in RECEIVED[0]["Subject"])
    link = re.search(r"https://blog\.example\.org/confirm\?t=([\w-]+)", text_of(RECEIVED[0]))
    check("con il link di conferma giusto", link is not None and link.group(1) == anna_entry["token"])
    newsletter.subscribe("anna@example.org", "it", SITE_URL)
    check("chiedere di nuovo subito non manda un'altra email", len(RECEIVED) == 1)
    check("un link sbagliato non conferma niente", newsletter.confirm("sbagliato") is False)
    check("il link giusto conferma", newsletter.confirm(anna_entry["token"]) is True)
    check("e l'iscritto risulta confermato",
          newsletter.find(newsletter.load_state(), "email", "anna@example.org")["status"] == "confirmed")
    RECEIVED.clear()
    check("un confermato che si iscrive di nuovo non riceve niente",
          newsletter.subscribe("anna@example.org", "it", SITE_URL) == "ok" and RECEIVED == [])
    check("la lingua si ritrova dal token", newsletter.token_language(anna_entry["token"]) == "it")
    check("l'elenco CSV ha l'indirizzo", '"anna@example.org","confirmed"' in newsletter.subscribers_csv())


def test_limits():
    print("\nlimiti contro gli abusi")
    newsletter._requests.clear()
    responses = [newsletter.allowed_request("203.0.113.5", moment=1000 + i) for i in range(7)]
    check(f"{newsletter.REQUESTS_PER_HOUR} richieste in un'ora, poi basta",
          responses == [True] * newsletter.REQUESTS_PER_HOUR + [False] * (7 - newsletter.REQUESTS_PER_HOUR))
    check("dopo un'ora si riparte", newsletter.allowed_request("203.0.113.5", moment=1000 + 3700))
    check("un altro indirizzo non ne risente", newsletter.allowed_request("203.0.113.6", moment=1001))


def test_articles(port):
    print("\nl'invio dei nuovi articoli")
    set_value(port)
    newsletter.remove("anna@example.org")
    newsletter.subscribe("bruno@example.org", "en", SITE_URL)
    bruno_entry = newsletter.find(newsletter.load_state(), "email", "bruno@example.org")
    newsletter.subscribe("carla@example.org", "it", SITE_URL)  # never confirms
    newsletter.confirm(bruno_entry["token"])
    new = save_article({"title": "Articolo per gli iscritti", "slug": "prova-nl-nuovo",
                          "content": "<p>Testo da leggere per intero.</p>", "status": "draft"}, new_article=True)
    excluded = save_article({"title": "Articolo escluso", "slug": "prova-nl-escluso",
                            "content": "<p>No.</p>", "status": "draft", "notify_subscribers": False}, new_article=True)
    # An article published long before the newsletter, written the way an
    # older version of PyBlog left it: without first_published.
    old = "prova-nl-vecchio"
    write_json_atomically(POSTS_DIR / f"{old}.json", {
        "title": "Articolo vecchio", "slug": old, "content": "<p>Vecchio.</p>",
        "status": "published", "date": "2020-01-01T00:00:00+00:00"})
    try:
        for slug in (new, excluded):
            art = load_article(slug)
            art["status"] = "published"
            art["original_slug"] = slug
            save_article(art)
        check("pubblicandolo si segna quando è uscito la prima volta", load_article(new).get("first_published"))
        # Edited today: it keeps counting as published in 2020.
        art = load_article(old)
        art["original_slug"] = old
        art["content"] = "<p>Corretto oggi.</p>"
        save_article(art)
        check("un articolo di prima, corretto oggi, resta uscito alla sua data",
              load_article(old).get("first_published") == "2020-01-01T00:00:00+00:00")
        newsletter.notify_published([new, excluded, old])
        queue = newsletter.load_state()["outbox"]
        check("in coda va solo l'articolo nuovo", queue == [new], str(queue))
        RECEIVED.clear()
        newsletter.send_outbox(SITE_URL)
        check("parte un'email sola, all'unico confermato", len(RECEIVED) == 1 and RECEIVED[0]["To"] == "bruno@example.org",
              str([m["To"] for m in RECEIVED]))
        if RECEIVED:
            m = RECEIVED[0]
            check("con il titolo come oggetto", m["Subject"] == "Articolo per gli iscritti")
            check("con il link all'articolo e alla disiscrizione",
                  f"{SITE_URL}/posts/{new}.html" in text_of(m) and "/unsubscribe?t=" in text_of(m))
            check("e la disiscrizione con un clic per i programmi di posta",
                  m["List-Unsubscribe"].startswith(f"<{SITE_URL}/unsubscribe?t=")
                  and m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click")
            check("il mittente è quello scelto", m["From"] == "Il blog <blog@example.org>")
        stato = newsletter.load_state()
        check("la coda si svuota e l'invio viene ricordato",
              stato["outbox"] == [] and stato["last"]["sent"] == 1 and stato["last"]["title"] == "Articolo per gli iscritti")
        check("l'articolo è segnato come mandato", load_article(new).get("newsletter_sent") is True)
        art = load_article(new)
        art["original_slug"] = new
        art["content"] = "<p>Corretto.</p>"
        save_article(art)
        newsletter.notify_published([new])
        check("correggerlo e salvarlo non lo rimanda", newsletter.load_state()["outbox"] == [])
        check("disiscriversi toglie l'iscritto", newsletter.unsubscribe(bruno_entry["token"]) is True
              and newsletter.find(newsletter.load_state(), "email", "bruno@example.org") is None)
        CONFIG["newsletter"]["send_on_publish"] = False
        newsletter.notify_published([excluded])
        check("con l'invio automatico spento non va in coda niente", newsletter.load_state()["outbox"] == [])
    finally:
        for slug in (new, excluded, old):
            delete_article(slug)


def test_site(port):
    print("\nil modulo sul sito")
    set_value(port, in_sidebar=True, after_article=True)
    pubblicati = [a for a in build.load_articles() if a.get("status") == "published"]
    home = build.generate_homepage(pubblicati, "it")
    check("il modulo è nella barra laterale", 'class="box box-newsletter"' in home and 'action="/subscribe"' in home)
    check("con il campo trappola per i robot", 'name="website" tabindex="-1"' in home)
    check("e la lingua della pagina", 'name="language" value="it"' in home)
    article = build.generate_article_page(pubblicati[0], "it", pubblicati)
    check("e in fondo all'articolo", 'class="newsletter-article"' in article)
    set_value(port, in_sidebar=False, after_article=False)
    check("dove l'autore non lo vuole, non c'è", 'action="/subscribe"' not in build.generate_homepage(pubblicati, "it"))
    set_value(port, enabled=False)
    check("con la newsletter spenta non c'è da nessuna parte",
          'action="/subscribe"' not in build.generate_article_page(pubblicati[0], "it", pubblicati))
    page_html = build.newsletter_message_page("en", "Check your inbox", "An email has arrived.")
    check("le pagine di risposta hanno la grafica del sito e non si indicizzano",
          "<h1>Check your inbox</h1>" in page_html and 'content="noindex"' in page_html)


def test_administration(port):
    print("\nl'amministrazione")
    set_value(port)
    settings_value = server.config_page("TOKEN")
    check("la sezione Newsletter c'è", 'id="section-newsletter"' in settings_value)
    check("la password salvata non torna mai nella pagina", 'id="nl_smtp_password" value=""' in settings_value)
    check("le rotte dell'amministrazione chiedono l'accesso e il token",
          "/newsletter-subscribers.csv" in server.ADMIN_GET_ROUTES
          and "/newsletter-test" in server.CSRF_PROTECTED_ROUTES
          and "/newsletter-remove" in server.CSRF_PROTECTED_ROUTES)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    check("nginx porta a Python le rotte pubbliche, con un limite loro",
          "location ~ ^/(subscribe|confirm|unsubscribe|iscriviti|conferma|disiscrivi)$" in nginx and "zone=pyblog_newsletter" in nginx)
    check("e quelle dell'amministrazione", "newsletter-test|newsletter-remove|newsletter-subscribers" in nginx)
    editor = server.editor_page(None, "TOKEN")
    check("nell'editor di una bozza c'è la spunta per avvisare gli iscritti", 'id="notify_subscribers" checked' in editor)
    RECEIVED.clear()
    newsletter.send_test(newsletter.settings(), "blog@example.org")
    check("l'email di prova parte", len(RECEIVED) == 1 and "Prova" in RECEIVED[0]["Subject"])


def main():
    saved_page = copy.deepcopy(CONFIG)
    real_file = newsletter.SUBSCRIBERS_FILE
    folder = tempfile.TemporaryDirectory()
    newsletter.SUBSCRIBERS_FILE = pathlib.Path(folder.name) / "subscribers.json"
    mail_server = start_mail_server()
    port = mail_server.server_address[1]
    try:
        test_settings()
        test_subscription(port)
        test_limits()
        test_articles(port)
        test_site(port)
        test_administration(port)
    finally:
        mail_server.shutdown()
        newsletter.SUBSCRIBERS_FILE = real_file
        folder.cleanup()
        CONFIG.clear()
        CONFIG.update(saved_page)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
