"""
The newsletter: readers subscribe from the site, confirm by email, and get
an email when a new article is published.

Everything stays on the server: the subscribers live in subscribers.json,
next to config.json and just as private, and the emails leave through the
SMTP account set in the Settings, with the standard library's smtplib.

- Subscribing is a double opt-in: the form only records the address as
  "pending" and sends a link; the address receives nothing else until that
  link is followed. The reply never says whether an address was already
  there, so the form cannot be used to find out who reads the blog.
- Confirming and unsubscribing go through a page with a button (a POST):
  the mail scanners that follow every link in an email would otherwise
  confirm or unsubscribe on the reader's behalf. Unsubscribing is also one
  click from the mail program, through List-Unsubscribe-Post.
- A new article goes into an outbox kept on disk, and a thread of the
  editor sends it, one reader at a time: a restart does not lose it.
"""
import json
import re
import secrets
import smtplib
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from core.config import BASE_DIR, CONFIG, write_json_atomically
from core.i18n import T

SUBSCRIBERS_FILE = BASE_DIR / "subscribers.json"

# One lock for the subscribers file: the form, the Settings and the sending
# thread all read and write it.
STATE_LOCK = threading.RLock()

# The shape of an address we accept: something@something.something, no
# spaces, no line breaks (which would let a "address" add mail headers).
EMAIL_PATTERN = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")

# How often one address may ask for a confirmation email, and how many
# subscription requests one internet address may make in an hour.
RESEND_GAP = timedelta(minutes=10)
REQUESTS_PER_HOUR = 5
_requests = {}

SECURITY_CHOICES = ("starttls", "ssl", "none")


def settings(config=None):
    """The newsletter block of the configuration, every value checked."""
    if config is None:
        config = CONFIG
    value = config.get("newsletter", {})
    if not isinstance(value, dict):
        value = {}

    def text(key, default=""):
        item = value.get(key, default)
        return item.strip() if isinstance(item, str) else default

    try:
        port = int(value.get("smtp_port", 587))
    except (TypeError, ValueError):
        port = 587
    security = value.get("smtp_security", "starttls")
    if security not in SECURITY_CHOICES:
        security = "starttls"
    return {
        "enabled": value.get("enabled", False) is True,
        "in_sidebar": value.get("in_sidebar", True) is not False,
        "after_article": value.get("after_article", True) is not False,
        "send_on_publish": value.get("send_on_publish", True) is not False,
        "title": text("title"),
        "text": text("text"),
        "sender_name": text("sender_name"),
        "sender_email": text("sender_email"),
        "smtp_host": text("smtp_host"),
        "smtp_port": port,
        "smtp_security": security,
        "smtp_user": text("smtp_user"),
        "smtp_password": value.get("smtp_password", "") if isinstance(value.get("smtp_password"), str) else "",
    }


def smtp_password(current):
    """The SMTP password, from PYBLOG_SMTP_PASSWORD first, as the API keys."""
    import os
    env_value = os.environ.get("PYBLOG_SMTP_PASSWORD", "").strip()
    if env_value != "":
        return env_value
    return current["smtp_password"]


def ready(current=None):
    """Tell whether the newsletter is on and can send."""
    if current is None:
        current = settings()
    return (current["enabled"] and current["smtp_host"] != ""
            and valid_email(current["sender_email"]))


def valid_email(address):
    """Tell whether an address looks like one we can write to."""
    return (isinstance(address, str) and 3 <= len(address) <= 254
            and EMAIL_PATTERN.match(address) is not None)


# ---------------------------------------------------------------------------
# THE STATE ON DISK
# ---------------------------------------------------------------------------

def load_state():
    """The subscribers, the outbox and the last sending, as stored."""
    with STATE_LOCK:
        try:
            with open(SUBSCRIBERS_FILE, encoding="utf-8") as fp:
                state = json.load(fp)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        if not isinstance(state.get("subscribers"), list):
            state["subscribers"] = []
        if not isinstance(state.get("outbox"), list):
            state["outbox"] = []
        if not isinstance(state.get("last"), dict):
            state["last"] = {}
        state["subscribers"] = [s for s in state["subscribers"] if isinstance(s, dict)]
        return state


def save_state(state):
    """Write the state back; the file is created readable by its owner only."""
    with STATE_LOCK:
        write_json_atomically(SUBSCRIBERS_FILE, state)


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def find(state, key, value):
    """The subscriber whose key has a value, or None."""
    for subscriber in state["subscribers"]:
        if subscriber.get(key) == value:
            return subscriber
    return None


def counts():
    """How many confirmed and how many pending subscribers there are."""
    state = load_state()
    confirmed = sum(1 for s in state["subscribers"] if s.get("status") == "confirmed")
    return confirmed, len(state["subscribers"]) - confirmed


# ---------------------------------------------------------------------------
# SUBSCRIBING, CONFIRMING, UNSUBSCRIBING
# ---------------------------------------------------------------------------

def allowed_request(address_of_client, moment=None):
    """At most REQUESTS_PER_HOUR subscription requests per internet address."""
    if moment is None:
        moment = time.monotonic()
    with STATE_LOCK:
        recent = [t for t in _requests.get(address_of_client, []) if moment - t < 3600]
        if len(recent) >= REQUESTS_PER_HOUR:
            _requests[address_of_client] = recent
            return False
        recent.append(moment)
        _requests[address_of_client] = recent
        return True


def subscribe(address, language, site_url):
    """
    Record a subscription request and send the confirmation email.
    Return "ok" (whatever the address's past), "invalid" or "error".
    An address already confirmed gets nothing new; one waiting gets the
    link again, but not more than once every RESEND_GAP.
    """
    address = (address or "").strip().lower()
    if not valid_email(address):
        return "invalid"
    if language not in ("it", "en"):
        language = "it"
    with STATE_LOCK:
        state = load_state()
        subscriber = find(state, "email", address)
        if subscriber is not None and subscriber.get("status") == "confirmed":
            return "ok"
        moment = now_utc()
        if subscriber is not None:
            try:
                last = datetime.fromisoformat(subscriber.get("last_mail", ""))
            except ValueError:
                last = moment - RESEND_GAP
            if moment - last < RESEND_GAP:
                return "ok"
        else:
            subscriber = {"email": address, "status": "pending", "created": moment.isoformat()}
            state["subscribers"].append(subscriber)
        subscriber["token"] = secrets.token_urlsafe(24)
        subscriber["language"] = language
        subscriber["last_mail"] = moment.isoformat()
        save_state(state)
        token = subscriber["token"]
    try:
        send_confirmation(address, token, language, site_url)
    except (OSError, smtplib.SMTPException) as error:
        print(f"WARNING: the confirmation email to a new subscriber failed ({error}).")
        return "error"
    return "ok"


def confirm(token):
    """Confirm the subscription a token belongs to. Return True if it did."""
    with STATE_LOCK:
        state = load_state()
        subscriber = find(state, "token", token) if token else None
        if subscriber is None:
            return False
        if subscriber.get("status") != "confirmed":
            subscriber["status"] = "confirmed"
            subscriber["confirmed_at"] = now_utc().isoformat()
            save_state(state)
        return True


def token_language(token):
    """The language of the subscriber a token belongs to, or ""."""
    if not token:
        return ""
    subscriber = find(load_state(), "token", token)
    return subscriber.get("language", "it") if subscriber else ""


def unsubscribe(token):
    """Remove the subscriber a token belongs to. Return True if it did."""
    with STATE_LOCK:
        state = load_state()
        subscriber = find(state, "token", token) if token else None
        if subscriber is None:
            return False
        state["subscribers"].remove(subscriber)
        save_state(state)
        return True


def remove(address):
    """Remove an address, from the Settings. Return True if it was there."""
    with STATE_LOCK:
        state = load_state()
        subscriber = find(state, "email", (address or "").strip().lower())
        if subscriber is None:
            return False
        state["subscribers"].remove(subscriber)
        save_state(state)
        return True


def subscribers_csv():
    """The list of subscribers as CSV, for a spreadsheet or another service."""
    lines = ["email,status,language,created,confirmed_at"]
    for s in load_state()["subscribers"]:
        values = [str(s.get(k, "")) for k in ("email", "status", "language", "created", "confirmed_at")]
        lines.append(",".join('"' + v.replace('"', '""') + '"' for v in values))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# SENDING
# ---------------------------------------------------------------------------

def sender(current):
    """The From address: the name the author chose, or the site's title."""
    name = current["sender_name"] or CONFIG.get("site_title", "")
    return formataddr((name, current["sender_email"]))


def smtp_connection(current):
    """An open, logged-in SMTP connection, as the Settings describe it."""
    timeout = 20
    if current["smtp_security"] == "ssl":
        server = smtplib.SMTP_SSL(current["smtp_host"], current["smtp_port"], timeout=timeout,
                                  context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(current["smtp_host"], current["smtp_port"], timeout=timeout)
        if current["smtp_security"] == "starttls":
            server.starttls(context=ssl.create_default_context())
    password = smtp_password(current)
    if current["smtp_user"] != "" and password != "":
        server.login(current["smtp_user"], password)
    return server


def message(current, to, subject, text, html, unsubscribe_url=""):
    """One email with a plain text part and an HTML part."""
    # Header lines may be 998 characters long. With the default 78 a long
    # unsubscribe link, which has no space to fold at, would be encoded as
    # an RFC 2047 word that no mail program reads as a link.
    mail = EmailMessage(policy=policy.default.clone(max_line_length=998))
    mail["From"] = sender(current)
    mail["To"] = to
    mail["Subject"] = subject
    mail["Message-ID"] = make_msgid(domain=current["sender_email"].split("@")[-1])
    if unsubscribe_url != "":
        mail["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        mail["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    mail.set_content(text)
    mail.add_alternative(html, subtype="html")
    return mail


def email_html(language, heading, paragraphs, button_text, button_url, footer):
    """A plain, readable email: a heading, some lines, one button, a footer."""
    from core.render import esc
    body = "".join(f'<p style="margin:0 0 14px;line-height:1.6">{esc(p)}</p>' for p in paragraphs)
    return (
        f'<!doctype html><html lang="{language}"><body style="margin:0;background:#f6f7f9;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2328">'
        '<div style="max-width:560px;margin:0 auto;padding:24px">'
        '<div style="background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:24px">'
        f'<h1 style="font-size:22px;line-height:1.3;margin:0 0 16px">{esc(heading)}</h1>{body}'
        f'<p style="margin:20px 0 0"><a href="{esc(button_url)}" style="display:inline-block;'
        'background:#0066cc;color:#fff;text-decoration:none;font-weight:600;padding:10px 18px;'
        f'border-radius:8px">{esc(button_text)}</a></p></div>'
        f'<p style="font-size:13px;color:#5b6470;line-height:1.5;margin:16px 4px 0">{footer}</p>'
        '</div></body></html>')


def send_confirmation(address, token, language, site_url):
    """The email with the link that confirms a subscription."""
    current = settings()
    site = CONFIG.get("site_title", "")
    link = f"{site_url}/conferma?t={token}"
    subject = T("nl_conferma_oggetto", language).replace("{site}", site)
    lines = [T("nl_conferma_testo", language).replace("{site}", site),
             T("nl_conferma_ignora", language)]
    text = "\n\n".join([lines[0], link, lines[1]])
    html = email_html(language, subject, lines, T("nl_conferma_pulsante", language), link, "")
    with smtp_connection(current) as server:
        server.send_message(message(current, address, subject, text, html))


def send_test(current, to):
    """A test email, to check the SMTP settings from the Settings page."""
    language = CONFIG.get("admin_language", "it")
    subject = T("nl_prova_oggetto", language).replace("{site}", CONFIG.get("site_title", ""))
    text = T("nl_prova_testo", language)
    html = email_html(language, subject, [text], T("nl_prova_pulsante", language),
                      CONFIG.get("base_url", ""), "")
    with smtp_connection(current) as server:
        server.send_message(message(current, to, subject, text, html))


def queue_article(slug):
    """Put a newly published article in the outbox, once."""
    with STATE_LOCK:
        state = load_state()
        if slug not in state["outbox"]:
            state["outbox"].append(slug)
            save_state(state)


def article_email(art, subscriber, current, site_url):
    """Subject, text and HTML of the email that announces an article."""
    from core import build
    from core.articles import article_language_available
    language = subscriber.get("language", "it")
    if not article_language_available(art, language):
        language = build.main_language()
    title, _, _, _ = build.article_card_fields(art, language)
    excerpt = build.article_excerpt(art, language, 60)
    link = site_url + build.article_url(art, language)
    unsubscribe_url = f"{site_url}/disiscrivi?t={subscriber['token']}"
    site = CONFIG.get("site_title", "")
    footer_text = T("nl_piede", language).replace("{site}", site)
    from core.render import esc
    footer = (esc(footer_text) + ' <a href="' + esc(unsubscribe_url) + '" style="color:#5b6470">'
              + esc(T("nl_disiscriviti", language)) + "</a>")
    text = "\n\n".join([title, excerpt, T("nl_leggi", language) + ": " + link,
                        "--", footer_text + " " + T("nl_disiscriviti", language) + ": " + unsubscribe_url])
    html = email_html(language, title, [excerpt], T("nl_leggi", language), link, footer)
    return title, text, html, unsubscribe_url


def send_outbox(site_url):
    """
    Send every article in the outbox to every confirmed subscriber, then
    take it out and mark the article as sent. One connection per article;
    a failure for one address does not stop the others.
    """
    from core.articles import load_article, mark_newsletter_sent
    current = settings()
    if not ready(current):
        return
    while True:
        with STATE_LOCK:
            state = load_state()
            if not state["outbox"]:
                return
            slug = state["outbox"][0]
            readers = [dict(s) for s in state["subscribers"] if s.get("status") == "confirmed"]
        art = load_article(slug)
        sent = failed = 0
        if art is not None and art.get("status") == "published":
            try:
                with smtp_connection(current) as server:
                    for reader in readers:
                        try:
                            subject, text, html, unsubscribe_url = article_email(art, reader, current, site_url)
                            server.send_message(message(current, reader["email"], subject, text, html,
                                                        unsubscribe_url))
                            sent = sent + 1
                        except smtplib.SMTPRecipientsRefused:
                            failed = failed + 1
                        time.sleep(0.2)
            except (OSError, smtplib.SMTPException) as error:
                # The server cannot be reached: the article stays in the
                # outbox and the next round tries again.
                print(f"WARNING: newsletter for {slug} not sent ({error}).")
                with STATE_LOCK:
                    state = load_state()
                    state["last"] = {"slug": slug, "title": art.get("title", ""), "sent": 0,
                                     "failed": len(readers), "error": str(error),
                                     "at": now_utc().isoformat()}
                    save_state(state)
                return
            mark_newsletter_sent(slug)
        with STATE_LOCK:
            state = load_state()
            if slug in state["outbox"]:
                state["outbox"].remove(slug)
            if art is not None:
                state["last"] = {"slug": slug, "title": art.get("title", ""), "sent": sent,
                                 "failed": failed, "error": "", "at": now_utc().isoformat()}
            save_state(state)


def notify_published(slugs):
    """
    The articles that have just been published for the first time go to
    the outbox, if the newsletter is on and the author did not say no.
    """
    from core.articles import load_article
    current = settings()
    if not current["enabled"] or not current["send_on_publish"]:
        return
    for slug in slugs:
        art = load_article(slug)
        if art is None or art.get("status") != "published":
            continue
        if art.get("newsletter_sent") is True or art.get("notify_subscribers") is False:
            continue
        # Only what is published after the newsletter was switched on: an
        # old article edited later is not news to anybody.
        if (art.get("first_published") or "") < (current_enabled_since() or "9999"):
            continue
        queue_article(slug)


def current_enabled_since():
    """When the newsletter was switched on, as an ISO moment, or ""."""
    value = CONFIG.get("newsletter", {})
    if not isinstance(value, dict):
        return ""
    since = value.get("enabled_since", "")
    return since if isinstance(since, str) else ""


def sender_loop(stop, site_url_of, wake):
    """The thread of the editor that empties the outbox."""
    while not stop.is_set():
        try:
            send_outbox(site_url_of())
        except Exception as error:  # the sender must never stop the editor
            print(f"WARNING: newsletter sending failed ({error}).")
        wake.wait(60)
        wake.clear()
