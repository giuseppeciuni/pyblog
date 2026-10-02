"""
Authentication of the administration area.

The password is never stored in clear text: we only store its digest (a value
from which the password cannot be recovered). When the user logs in, we
compute the digest of what they typed and compare the two.

A session is a random token kept in memory. It carries two things: when it was
created, so it can expire, and a CSRF token, so a state-changing request can
prove it came from one of our own pages and not from another site that merely
knows the browser holds a valid cookie.

Everything here lives in memory only: restarting the server invalidates every
session and resets the login rate limiter.
"""
import hashlib
import secrets
import threading
import time

from core.config import PASSWORD_FILE


# How long a session stays valid, in seconds. After this the token is refused
# and cleaned up, even if the browser still sends the cookie.
SESSION_MAX_AGE = 24 * 60 * 60

# token -> {"created": float, "csrf": str}
ACTIVE_SESSIONS = {}

# Sessions are read and written from several request threads at once, so the
# dictionary is guarded. The lock is held only for the dictionary operation
# itself, never across a request.
_SESSION_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# PASSWORD
# ---------------------------------------------------------------------------

def compute_legacy_password_hash(password, salt):
    """
    Compute the digest (hash) of a password with the old method (plain
    SHA-256). It is only used to verify passwords saved before the
    upgrade to PBKDF2. New passwords do not use this function.
    """
    text = salt + password
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest


def compute_pbkdf2_hash(password, salt):
    """
    Compute the password digest with PBKDF2 (200,000 iterations).
    Unlike a plain hash, PBKDF2 is deliberately slow: it makes trying
    millions of passwords far more expensive for an attacker.
    """
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200000)
    return digest.hex()


def set_password(password):
    """Save the hash of a new administration password to file."""
    salt = secrets.token_hex(16)
    digest = compute_pbkdf2_hash(password, salt)
    # Format: method, salt and digest separated by colons.
    content = "pbkdf2:" + salt + ":" + digest
    PASSWORD_FILE.write_text(content, encoding="utf-8")


def password_is_set():
    """Tell whether an administration password has already been set."""
    if PASSWORD_FILE.exists():
        return True
    return False


def verify_password(password):
    """
    Check whether the password entered matches the saved one.
    It supports two formats: the new PBKDF2 one ("pbkdf2:salt:hash") and
    the old one ("salt:hash"). If the login succeeds with the old format,
    the file is automatically rewritten in the new, safer one.
    """
    if not PASSWORD_FILE.exists():
        return False
    content = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    parti = content.split(":")

    if len(parti) == 3 and parti[0] == "pbkdf2":
        # New format: pbkdf2:salt:digest
        salt = parti[1]
        stored_digest = parti[2]
        computed_digest = compute_pbkdf2_hash(password, salt)
        return secrets.compare_digest(computed_digest, stored_digest)

    if len(parti) == 2:
        # Old format: salt:digest (plain SHA-256).
        salt = parti[0]
        stored_digest = parti[1]
        computed_digest = compute_legacy_password_hash(password, salt)
        corretta = secrets.compare_digest(computed_digest, stored_digest)
        if corretta:
            # Automatic migration to the new format, now that we know
            # the password in clear text (only in memory, during login).
            set_password(password)
        return corretta

    return False


# ---------------------------------------------------------------------------
# LOGIN RATE LIMITING
# ---------------------------------------------------------------------------
# After LOGIN_MAX_ATTEMPTS consecutive errors from the same address, THAT
# address is locked out for a while. Every other address can still log in.
#
# The lock used to be one for the whole server: five wrong passwords from
# anywhere locked everybody out, the owner of the blog included, so anyone
# could keep the author out of their own editor just by failing on purpose
# once a minute. Now each address has its own counter. A lock that repeats
# lasts longer each time, so guessing from one address stays slow without
# ever punishing anyone else.

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 60
# The longest a repeated lock can last: 60, 120, 240, 480 seconds, then 15
# minutes at most.
LOGIN_LOCK_MAX_SECONDS = 15 * 60
# An address that has been quiet this long is forgotten, lock history
# included, so the table cannot grow without limit.
LOGIN_FORGET_SECONDS = 60 * 60

# address -> {"errors": int, "locked_until": float, "locks": int, "seen": float}
LOGIN_STATE = {}
_LOGIN_LOCK = threading.Lock()


def _forget_quiet_clients(now):
    """Drop the addresses that are not locked and have been quiet for long.
    The caller must already hold _LOGIN_LOCK."""
    for client in list(LOGIN_STATE):
        entry = LOGIN_STATE[client]
        if entry["locked_until"] <= now and now - entry["seen"] > LOGIN_FORGET_SECONDS:
            del LOGIN_STATE[client]


def login_is_locked(client=""):
    """Tell whether login is temporarily locked for this address."""
    with _LOGIN_LOCK:
        entry = LOGIN_STATE.get(client)
        if entry is None:
            return False
        return time.time() < entry["locked_until"]


def login_lock_remaining(client=""):
    """Seconds left before this address may try again (0 when not locked)."""
    with _LOGIN_LOCK:
        entry = LOGIN_STATE.get(client)
        if entry is None:
            return 0
        remaining = int(entry["locked_until"] - time.time()) + 1
    if remaining < 0:
        return 0
    return remaining


def record_failed_login(client=""):
    """Record a failed attempt from an address and lock it if needed."""
    now = time.time()
    with _LOGIN_LOCK:
        _forget_quiet_clients(now)
        entry = LOGIN_STATE.setdefault(
            client, {"errors": 0, "locked_until": 0.0, "locks": 0, "seen": now})
        entry["seen"] = now
        entry["errors"] = entry["errors"] + 1
        if entry["errors"] >= LOGIN_MAX_ATTEMPTS:
            duration = LOGIN_LOCK_SECONDS * (2 ** entry["locks"])
            if duration > LOGIN_LOCK_MAX_SECONDS:
                duration = LOGIN_LOCK_MAX_SECONDS
            entry["locked_until"] = now + duration
            entry["locks"] = entry["locks"] + 1
            entry["errors"] = 0


def record_successful_login(client=""):
    """Forget the errors of an address after it logged in correctly."""
    with _LOGIN_LOCK:
        if client in LOGIN_STATE:
            del LOGIN_STATE[client]


# ---------------------------------------------------------------------------
# SESSIONS AND CSRF TOKENS
# ---------------------------------------------------------------------------

def _purge_expired_sessions():
    """
    Drop the sessions that are past their maximum age.
    Called on every session lookup: the number of sessions on a personal blog
    is tiny, so a full sweep costs nothing and keeps the dictionary honest.
    The caller must already hold _SESSION_LOCK.
    """
    now = time.time()
    scaduti = []
    for token in ACTIVE_SESSIONS:
        if now - ACTIVE_SESSIONS[token]["created"] > SESSION_MAX_AGE:
            scaduti.append(token)
    for token in scaduti:
        del ACTIVE_SESSIONS[token]


def create_session_token():
    """Create a random token for a login session and register it."""
    token = secrets.token_urlsafe(32)
    with _SESSION_LOCK:
        _purge_expired_sessions()
        ACTIVE_SESSIONS[token] = {
            "created": time.time(),
            "csrf": secrets.token_urlsafe(32),
        }
    return token


def session_is_valid(token):
    """
    Tell whether a session token is valid, i.e. the user is logged in AND the
    session has not aged out. An expired token is removed as we find it.
    """
    if token is None:
        return False
    with _SESSION_LOCK:
        _purge_expired_sessions()
        return token in ACTIVE_SESSIONS


def destroy_session(token):
    """Forget a session (used on logout)."""
    if token is None:
        return
    with _SESSION_LOCK:
        if token in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[token]


def destroy_all_sessions():
    """
    Forget every session. Called after a password change: whoever knew the old
    password must not keep a working session, on this browser or any other.
    """
    with _SESSION_LOCK:
        ACTIVE_SESSIONS.clear()


def csrf_token_for(session_token):
    """
    Return the CSRF token bound to a session, or an empty string if the
    session is unknown. The value is put into every admin page and sent back
    by the browser in the X-CSRF-Token header.
    """
    if session_token is None:
        return ""
    with _SESSION_LOCK:
        entry = ACTIVE_SESSIONS.get(session_token)
        if entry is None:
            return ""
        return entry["csrf"]


def csrf_token_is_valid(session_token, submitted_token):
    """
    Tell whether the CSRF token sent with a request matches the one bound to
    the session. compare_digest keeps the comparison constant-time.

    A cookie alone is not enough to authorise a change: any other site can make
    the browser send it. Only our own pages know this token.
    """
    expected = csrf_token_for(session_token)
    if expected == "":
        return False
    if submitted_token is None or submitted_token == "":
        return False
    return secrets.compare_digest(expected, submitted_token)
