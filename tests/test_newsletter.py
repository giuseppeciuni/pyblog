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

RICEVUTE = []


class Postino(socketserver.StreamRequestHandler):
    """Speaks just enough SMTP for smtplib, and keeps every message."""

    def handle(self):
        self.wfile.write(b"220 prova\r\n")
        destinatari = []
        while True:
            riga = self.rfile.readline()
            if not riga:
                return
            comando = riga.decode("utf-8", "replace").strip().upper()
            if comando.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250 prova\r\n")
            elif comando.startswith("MAIL FROM"):
                destinatari = []
                self.wfile.write(b"250 ok\r\n")
            elif comando.startswith("RCPT TO"):
                destinatari.append(comando)
                self.wfile.write(b"250 ok\r\n")
            elif comando == "DATA":
                self.wfile.write(b"354 avanti\r\n")
                dati = []
                while True:
                    r = self.rfile.readline()
                    if r in (b".\r\n", b".\n", b""):
                        break
                    dati.append(r[1:] if r.startswith(b"..") else r)
                RICEVUTE.append(email.message_from_bytes(b"".join(dati), policy=policy.default))
                self.wfile.write(b"250 ok\r\n")
            elif comando == "QUIT":
                self.wfile.write(b"221 ciao\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


def avvia_postino():
    servitore = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Postino)
    servitore.daemon_threads = True
    threading.Thread(target=servitore.serve_forever, daemon=True).start()
    return servitore


def testo_di(messaggio):
    parti = [p.get_content() for p in messaggio.walk() if p.get_content_type() == "text/plain"]
    return "\n".join(parti)


SITO = "https://blog.example.org"


def imposta(porta, **altro):
    nl = {"enabled": True, "sender_email": "blog@example.org", "sender_name": "Il blog",
          "smtp_host": "127.0.0.1", "smtp_port": porta, "smtp_security": "none",
          "enabled_since": (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()}
    nl.update(altro)
    CONFIG["newsletter"] = nl


def test_impostazioni():
    print("\nimpostazioni e indirizzi")
    s = newsletter.settings({"newsletter": {"smtp_port": "abc", "smtp_security": "boh", "enabled": "si"}})
    check("valori sbagliati tornano ai predefiniti", s["smtp_port"] == 587 and s["smtp_security"] == "starttls"
          and s["enabled"] is False)
    check("un indirizzo normale è valido", newsletter.valid_email("anna@example.org"))
    for cattivo in ("anna", "anna@", "a b@example.org", "anna@example.org\nBcc: x@y.z", "<anna@example.org>"):
        check(f"{cattivo!r} non è valido", not newsletter.valid_email(cattivo))


def test_iscrizione(porta):
    print("\nl'iscrizione con doppio consenso")
    imposta(porta)
    RICEVUTE.clear()
    check("un indirizzo sbagliato non entra", newsletter.subscribe("non-un-indirizzo", "it", SITO) == "invalid")
    check("un indirizzo buono riceve la risposta di sempre", newsletter.subscribe("Anna@Example.org ", "it", SITO) == "ok")
    stato = newsletter.load_state()
    anna = newsletter.find(stato, "email", "anna@example.org")
    check("è in attesa, in minuscolo, con la sua lingua", anna and anna["status"] == "pending" and anna["language"] == "it")
    check("è arrivata un'email di conferma", len(RICEVUTE) == 1 and "Conferma" in RICEVUTE[0]["Subject"])
    link = re.search(r"https://blog\.example\.org/conferma\?t=([\w-]+)", testo_di(RICEVUTE[0]))
    check("con il link di conferma giusto", link is not None and link.group(1) == anna["token"])
    newsletter.subscribe("anna@example.org", "it", SITO)
    check("chiedere di nuovo subito non manda un'altra email", len(RICEVUTE) == 1)
    check("un link sbagliato non conferma niente", newsletter.confirm("sbagliato") is False)
    check("il link giusto conferma", newsletter.confirm(anna["token"]) is True)
    check("e l'iscritto risulta confermato",
          newsletter.find(newsletter.load_state(), "email", "anna@example.org")["status"] == "confirmed")
    RICEVUTE.clear()
    check("un confermato che si iscrive di nuovo non riceve niente",
          newsletter.subscribe("anna@example.org", "it", SITO) == "ok" and RICEVUTE == [])
    check("la lingua si ritrova dal token", newsletter.token_language(anna["token"]) == "it")
    check("l'elenco CSV ha l'indirizzo", '"anna@example.org","confirmed"' in newsletter.subscribers_csv())


def test_limiti():
    print("\nlimiti contro gli abusi")
    newsletter._requests.clear()
    risposte = [newsletter.allowed_request("203.0.113.5", moment=1000 + i) for i in range(7)]
    check(f"{newsletter.REQUESTS_PER_HOUR} richieste in un'ora, poi basta",
          risposte == [True] * newsletter.REQUESTS_PER_HOUR + [False] * (7 - newsletter.REQUESTS_PER_HOUR))
    check("dopo un'ora si riparte", newsletter.allowed_request("203.0.113.5", moment=1000 + 3700))
    check("un altro indirizzo non ne risente", newsletter.allowed_request("203.0.113.6", moment=1001))


def test_articoli(porta):
    print("\nl'invio dei nuovi articoli")
    imposta(porta)
    newsletter.remove("anna@example.org")
    newsletter.subscribe("bruno@example.org", "en", SITO)
    bruno = newsletter.find(newsletter.load_state(), "email", "bruno@example.org")
    newsletter.subscribe("carla@example.org", "it", SITO)  # never confirms
    newsletter.confirm(bruno["token"])
    nuovo = save_article({"title": "Articolo per gli iscritti", "slug": "prova-nl-nuovo",
                          "content": "<p>Testo da leggere per intero.</p>", "status": "draft"}, new_article=True)
    escluso = save_article({"title": "Articolo escluso", "slug": "prova-nl-escluso",
                            "content": "<p>No.</p>", "status": "draft", "notify_subscribers": False}, new_article=True)
    # An article published long before the newsletter, written the way an
    # older version of PyBlog left it: without first_published.
    vecchio = "prova-nl-vecchio"
    write_json_atomically(POSTS_DIR / f"{vecchio}.json", {
        "title": "Articolo vecchio", "slug": vecchio, "content": "<p>Vecchio.</p>",
        "status": "published", "date": "2020-01-01T00:00:00+00:00"})
    try:
        for slug in (nuovo, escluso):
            art = load_article(slug)
            art["status"] = "published"
            art["original_slug"] = slug
            save_article(art)
        check("pubblicandolo si segna quando è uscito la prima volta", load_article(nuovo).get("first_published"))
        # Edited today: it keeps counting as published in 2020.
        art = load_article(vecchio)
        art["original_slug"] = vecchio
        art["content"] = "<p>Corretto oggi.</p>"
        save_article(art)
        check("un articolo di prima, corretto oggi, resta uscito alla sua data",
              load_article(vecchio).get("first_published") == "2020-01-01T00:00:00+00:00")
        newsletter.notify_published([nuovo, escluso, vecchio])
        coda = newsletter.load_state()["outbox"]
        check("in coda va solo l'articolo nuovo", coda == [nuovo], str(coda))
        RICEVUTE.clear()
        newsletter.send_outbox(SITO)
        check("parte un'email sola, all'unico confermato", len(RICEVUTE) == 1 and RICEVUTE[0]["To"] == "bruno@example.org",
              str([m["To"] for m in RICEVUTE]))
        if RICEVUTE:
            m = RICEVUTE[0]
            check("con il titolo come oggetto", m["Subject"] == "Articolo per gli iscritti")
            check("con il link all'articolo e alla disiscrizione",
                  f"{SITO}/posts/{nuovo}.html" in testo_di(m) and "/disiscrivi?t=" in testo_di(m))
            check("e la disiscrizione con un clic per i programmi di posta",
                  m["List-Unsubscribe"].startswith(f"<{SITO}/disiscrivi?t=")
                  and m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click")
            check("il mittente è quello scelto", m["From"] == "Il blog <blog@example.org>")
        stato = newsletter.load_state()
        check("la coda si svuota e l'invio viene ricordato",
              stato["outbox"] == [] and stato["last"]["sent"] == 1 and stato["last"]["title"] == "Articolo per gli iscritti")
        check("l'articolo è segnato come mandato", load_article(nuovo).get("newsletter_sent") is True)
        art = load_article(nuovo)
        art["original_slug"] = nuovo
        art["content"] = "<p>Corretto.</p>"
        save_article(art)
        newsletter.notify_published([nuovo])
        check("correggerlo e salvarlo non lo rimanda", newsletter.load_state()["outbox"] == [])
        check("disiscriversi toglie l'iscritto", newsletter.unsubscribe(bruno["token"]) is True
              and newsletter.find(newsletter.load_state(), "email", "bruno@example.org") is None)
        CONFIG["newsletter"]["send_on_publish"] = False
        newsletter.notify_published([escluso])
        check("con l'invio automatico spento non va in coda niente", newsletter.load_state()["outbox"] == [])
    finally:
        for slug in (nuovo, escluso, vecchio):
            delete_article(slug)


def test_sito(porta):
    print("\nil modulo sul sito")
    imposta(porta, in_sidebar=True, after_article=True)
    pubblicati = [a for a in build.load_articles() if a.get("status") == "published"]
    home = build.generate_homepage(pubblicati, "it")
    check("il modulo è nella barra laterale", 'class="box box-newsletter"' in home and 'action="/iscriviti"' in home)
    check("con il campo trappola per i robot", 'name="sito" tabindex="-1"' in home)
    check("e la lingua della pagina", 'name="lingua" value="it"' in home)
    articolo = build.generate_article_page(pubblicati[0], "it", pubblicati)
    check("e in fondo all'articolo", 'class="newsletter-articolo"' in articolo)
    imposta(porta, in_sidebar=False, after_article=False)
    check("dove l'autore non lo vuole, non c'è", 'action="/iscriviti"' not in build.generate_homepage(pubblicati, "it"))
    imposta(porta, enabled=False)
    check("con la newsletter spenta non c'è da nessuna parte",
          'action="/iscriviti"' not in build.generate_article_page(pubblicati[0], "it", pubblicati))
    pagina = build.newsletter_message_page("en", "Check your inbox", "An email has arrived.")
    check("le pagine di risposta hanno la grafica del sito e non si indicizzano",
          "<h1>Check your inbox</h1>" in pagina and 'content="noindex"' in pagina)


def test_amministrazione(porta):
    print("\nl'amministrazione")
    imposta(porta)
    impostazioni = server.config_page("TOKEN")
    check("la sezione Newsletter c'è", 'id="sezione-newsletter"' in impostazioni)
    check("la password salvata non torna mai nella pagina", 'id="nl_smtp_password" value=""' in impostazioni)
    check("le rotte dell'amministrazione chiedono l'accesso e il token",
          "/newsletter-iscritti.csv" in server.ADMIN_GET_ROUTES
          and "/newsletter-prova" in server.CSRF_PROTECTED_ROUTES
          and "/newsletter-rimuovi" in server.CSRF_PROTECTED_ROUTES)
    nginx = (pathlib.Path(__file__).resolve().parent.parent / "nginx.conf.example").read_text()
    check("nginx porta a Python le rotte pubbliche, con un limite loro",
          "location ~ ^/(iscriviti|conferma|disiscrivi)$" in nginx and "zone=pyblog_newsletter" in nginx)
    check("e quelle dell'amministrazione", "newsletter-prova|newsletter-rimuovi|newsletter-iscritti" in nginx)
    editor = server.editor_page(None, "TOKEN")
    check("nell'editor di una bozza c'è la spunta per avvisare gli iscritti", 'id="notify_subscribers" checked' in editor)
    RICEVUTE.clear()
    newsletter.send_test(newsletter.settings(), "blog@example.org")
    check("l'email di prova parte", len(RICEVUTE) == 1 and "Prova" in RICEVUTE[0]["Subject"])


def main():
    salvata = copy.deepcopy(CONFIG)
    file_vero = newsletter.SUBSCRIBERS_FILE
    cartella = tempfile.TemporaryDirectory()
    newsletter.SUBSCRIBERS_FILE = pathlib.Path(cartella.name) / "subscribers.json"
    postino = avvia_postino()
    porta = postino.server_address[1]
    try:
        test_impostazioni()
        test_iscrizione(porta)
        test_limiti()
        test_articoli(porta)
        test_sito(porta)
        test_amministrazione(porta)
    finally:
        postino.shutdown()
        newsletter.SUBSCRIBERS_FILE = file_vero
        cartella.cleanup()
        CONFIG.clear()
        CONFIG.update(salvata)
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
