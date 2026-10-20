"""
Updates: telling the author a new PyBlog is out, and installing it.

Two kinds of installation, two ways of knowing.

- A git checkout (the way the manual installs PyBlog on a server): the
  checkout knows the branch it follows on GitHub. "git fetch" tells how many
  changes are waiting and what they are, and "git pull --ff-only" brings
  them. This can be done from the administration when the checkout is
  clean: nothing edited by hand, nothing committed locally.
- Anything else (Docker image, the single-file version): the version
  written in core/__init__.py is compared with the one on GitHub's main
  branch, and the page says how to update.

The automatic check runs at most twice a day, and only when the author
opens the administration. It contacts GitHub, which sees the server's
address; it can be switched off on the Updates page.

An update is never blind. A backup of the site is saved first; after the
pull the new code must import cleanly in a separate process, or the
checkout goes back to where it was; only then does PyBlog restart itself
in place, keeping the same process for systemd or Docker.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from core import __version__
from core.config import BASE_DIR

REPOSITORY = "giuseppeciuni/pyblog"
VERSION_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/core/__init__.py"
CHANGELOG_URL = f"https://github.com/{REPOSITORY}/blob/main/CHANGELOG.md"

# The last check and the author's choice, next to config.json. Not part of
# the configuration: a backup put back must not carry another server's.
STATE_FILE = BASE_DIR / ".aggiornamenti.json"
CHECK_EVERY = 12 * 3600

VERSION_LINE = re.compile(r'^__version__\s*=\s*"(\d+(?:\.\d+){1,3})"', re.M)

# Run in a separate process after a pull: if the new code does not even
# import, the checkout goes back before anything restarts.
CHECK_COMMAND = [sys.executable, "-c", "import core.server"]

UPDATE_LOCK = threading.Lock()


def version_tuple(text):
    """"1.2.10" as (1, 2, 10), for comparing; () for anything else."""
    if not isinstance(text, str) or re.fullmatch(r"\d+(\.\d+){1,3}", text) is None:
        return ()
    return tuple(int(part) for part in text.split("."))


def is_git_checkout():
    return (BASE_DIR / ".git").exists() and shutil.which("git") is not None


def _git(*args, timeout=60):
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    return subprocess.run(["git", *args], cwd=str(BASE_DIR), capture_output=True,
                          text=True, timeout=timeout, env=environment)


# ---------------------------------------------------------------------------
# KNOWING
# ---------------------------------------------------------------------------

def git_status(fetch=True):
    """
    What is waiting on GitHub for this checkout:
    {"kind": "git", "branch", "behind", "ahead", "dirty", "news": [subjects],
     "can_update"}, or {"kind": "git", "error": key}.
    """
    if fetch:
        try:
            if _git("fetch", "--quiet", timeout=60).returncode != 0:
                return {"kind": "git", "error": "upd_offline"}
        except (subprocess.TimeoutExpired, OSError):
            return {"kind": "git", "error": "upd_offline"}
    upstream = _git("rev-parse", "--abbrev-ref", "@{u}")
    if upstream.returncode != 0:
        return {"kind": "git", "error": "upd_no_upstream"}
    behind = int(_git("rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0)
    ahead = int(_git("rev-list", "--count", "@{u}..HEAD").stdout.strip() or 0)
    dirty = _git("status", "--porcelain", "--untracked-files=no").stdout.strip() != ""
    news = [line for line in _git("log", "--format=%s", "-n", "15", "HEAD..@{u}").stdout.splitlines()
            if line.strip()]
    return {"kind": "git", "branch": upstream.stdout.strip(), "behind": behind, "ahead": ahead,
            "dirty": dirty, "news": news, "can_update": behind > 0 and ahead == 0 and not dirty}


def latest_release(url=VERSION_URL):
    """The version on GitHub's main branch, as text, or None."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PyBlog/" + __version__})
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read(64 * 1024).decode("utf-8", "replace")
    except Exception:
        return None
    found = VERSION_LINE.search(text)
    return found.group(1) if found else None


def release_status():
    """For an installation that is not a git checkout: the versions."""
    latest = latest_release()
    if latest is None:
        return {"kind": "other", "error": "upd_offline"}
    return {"kind": "other", "latest": latest,
            "behind": 1 if version_tuple(latest) > version_tuple(__version__) else 0,
            "changelog": CHANGELOG_URL}


def read_state():
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def write_state(state):
    temporary = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def automatic_check_enabled():
    return read_state().get("auto", True) is not False


def set_automatic_check(on):
    state = read_state()
    state["auto"] = on is True
    write_state(state)


def check(force=False, now=None):
    """
    The state of updates, from the last check when it is recent enough.
    Without force, and with the automatic check switched off, only the last
    known result comes back: nothing is asked of GitHub.
    """
    now = now if now is not None else time.time()
    state = read_state()
    last = state.get("result")
    fresh = isinstance(last, dict) and now - state.get("checked", 0) < CHECK_EVERY
    if not force and (fresh or not automatic_check_enabled()):
        result = last if isinstance(last, dict) else {}
    else:
        result = git_status() if is_git_checkout() else release_status()
        if "error" not in result:
            state["result"] = result
            state["checked"] = now
            write_state(state)
    result = dict(result)
    result["version"] = __version__
    result["auto"] = automatic_check_enabled()
    result["checked"] = state.get("checked", 0)
    return result


# ---------------------------------------------------------------------------
# INSTALLING
# ---------------------------------------------------------------------------

def update(save_backup=None):
    """
    Bring a clean git checkout up to date. Return {"ok": True, "from", "to"}
    or {"ok": False, "error": key, "detail": text}. The caller restarts.
    """
    if not UPDATE_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "upd_in_corso"}
    try:
        if not is_git_checkout():
            return {"ok": False, "error": "upd_non_git"}
        status = git_status()
        if "error" in status:
            return {"ok": False, "error": status["error"]}
        if not status["can_update"]:
            key = "upd_modifiche_locali" if status["dirty"] else (
                "upd_avanti" if status["ahead"] else "upd_aggiornato")
            return {"ok": False, "error": key}
        if save_backup is not None:
            save_backup()
        before = _git("rev-parse", "HEAD").stdout.strip()
        pull = _git("pull", "--ff-only", "--quiet", timeout=120)
        if pull.returncode != 0:
            return {"ok": False, "error": "upd_fallito", "detail": pull.stderr.strip()[-400:]}
        # A cache of compiled files of its own: the old ones on disk could
        # stand in for the new code (same size, same second) and hide an
        # error until the restart.
        with tempfile.TemporaryDirectory() as cache:
            environment = dict(os.environ, PYTHONPYCACHEPREFIX=cache)
            trial = subprocess.run(CHECK_COMMAND, cwd=str(BASE_DIR), capture_output=True,
                                   text=True, timeout=120, env=environment)
        if trial.returncode != 0:
            _git("reset", "--hard", "--quiet", before)
            return {"ok": False, "error": "upd_fallito", "detail": trial.stderr.strip()[-400:]}
        after = _git("rev-parse", "HEAD").stdout.strip()
        state = read_state()
        state.pop("result", None)
        state.pop("checked", None)
        write_state(state)
        return {"ok": True, "from": before[:7], "to": after[:7]}
    finally:
        UPDATE_LOCK.release()


def restart(delay=1.0):
    """
    Start the new code in place of the running process, after a moment for
    the answer to reach the browser. Same process id: systemd and Docker see
    nothing but a short pause; serve() rebuilds the site when it starts.
    """
    def again():
        # What the old process printed is still in its buffers: written now,
        # or lost with the process image.
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Timer(delay, again).start()
