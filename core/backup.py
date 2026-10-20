"""
Backups: writing one, and putting one back.

A backup is the ZIP archive the menu downloads: the articles and their
earlier versions, config.json, the newsletter's subscribers and the uploaded
media. The password is never in it.

Putting one back used to mean unpacking it on the server by hand. Now the
administration can do it, which makes it a door into the server: everything
in the archive is checked before a single file is touched. Only the names a
backup can hold are taken (an article, a version, a medium with a safe name
and an accepted type), each file has a ceiling, every JSON must parse, and a
picture must really be a picture. Anything else is left out and reported.

Before anything is replaced, the current state is saved as an automatic
backup in backups/, so a wrong restore is undone the same way. The swap
itself renames whole folders: either the old posts are there or the new
ones, never half of each.
"""
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime

from core import newsletter
from core.articles import magic_bytes_match, sanitize_file_name, sanitize_svg, upload_kind
from core.config import (BASE_DIR, CONFIG_FILE, MEDIA_DIR, POSTS_DIR,
                         write_json_atomically)

# Where the automatic backups go: next to posts/, never inside output/, so
# nginx does not publish them.
BACKUPS_DIR = BASE_DIR / "backups"
SUBSCRIBERS_FILE = newsletter.SUBSCRIBERS_FILE

# How many automatic backups are kept; the oldest go first.
KEEP_AUTOMATIC = 5

# The names a backup can hold.
POST_ENTRY = re.compile(r"posts/([a-z0-9-]+)\.json")
VERSION_ENTRY = re.compile(r"posts/\.history/([a-z0-9-]+)/(\d{8}T\d{6}Z)\.json")
MEDIA_ENTRY = re.compile(r"media/([^/]+)")
AUTOMATIC_NAME = re.compile(r"pyblog-automatico-\d{8}-\d{6}\.zip")

# Ceilings on what one file of the archive may unpack to. A video has the
# upload limit of its kind, checked separately.
MAX_JSON = 20 * 1024 * 1024
MAX_ENTRIES = 50000
MAX_TOTAL = 4 * 1024 * 1024 * 1024


class BackupError(Exception):
    """A backup that cannot be put back. The argument is an i18n key."""


# ---------------------------------------------------------------------------
# WRITING
# ---------------------------------------------------------------------------

def write_backup(fileobj):
    """
    Write the backup archive into an open binary file.

    The media are stored without compression: a JPEG, a PNG or an MP4 is
    already compressed and squeezing it again only costs time.
    """
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_DEFLATED) as zip_file:
        if POSTS_DIR.exists():
            for path_value in sorted(POSTS_DIR.glob("*.json")):
                zip_file.write(path_value, "posts/" + path_value.name)
            for path_value in sorted(POSTS_DIR.glob(".history/*/*.json")):
                zip_file.write(path_value, "posts/" + path_value.relative_to(POSTS_DIR).as_posix())
        if SUBSCRIBERS_FILE.exists():
            zip_file.write(SUBSCRIBERS_FILE, "subscribers.json")
        if CONFIG_FILE.exists():
            zip_file.write(CONFIG_FILE, "config.json")
        if MEDIA_DIR.exists():
            for path_value in sorted(MEDIA_DIR.iterdir()):
                if path_value.is_file() and not path_value.name.startswith("."):
                    zip_file.write(path_value, "media/" + path_value.name,
                                   compress_type=zipfile.ZIP_STORED)


def save_automatic_backup():
    """
    Save the current state in backups/ and drop the oldest automatic ones.
    Return the path of the new archive.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    name = "pyblog-automatico-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
    path_value = BACKUPS_DIR / name
    descriptor, temporary = tempfile.mkstemp(dir=str(BACKUPS_DIR), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as fileobj:
            write_backup(fileobj)
        os.replace(temporary, path_value)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    for old in automatic_backups()[KEEP_AUTOMATIC:]:
        try:
            (BACKUPS_DIR / old["name"]).unlink()
        except OSError:
            pass
    return path_value


def automatic_backups():
    """The automatic backups, newest first: name, date and size of each."""
    if not BACKUPS_DIR.is_dir():
        return []
    found = []
    for path_value in BACKUPS_DIR.iterdir():
        if path_value.is_file() and AUTOMATIC_NAME.fullmatch(path_value.name):
            stat = path_value.stat()
            found.append({"name": path_value.name, "size": stat.st_size,
                          "date": datetime.fromtimestamp(stat.st_mtime)})
    return sorted(found, key=lambda b: b["name"], reverse=True)


def automatic_backup_path(name):
    """The path of an automatic backup named by the browser, or None."""
    if not isinstance(name, str) or AUTOMATIC_NAME.fullmatch(name) is None:
        return None
    path_value = BACKUPS_DIR / name
    return path_value if path_value.is_file() else None


# ---------------------------------------------------------------------------
# CHECKING
# ---------------------------------------------------------------------------

def _read_entry(zip_file, info, ceiling):
    """The bytes of one entry, refusing it if it unpacks past its ceiling."""
    if info.file_size > ceiling:
        raise BackupError("err_backup_file_too_large")
    with zip_file.open(info) as source:
        data = source.read(ceiling + 1)
    if len(data) > ceiling:
        raise BackupError("err_backup_file_too_large")
    return data


def _json_object(data):
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BackupError("err_backup_json")
    if not isinstance(value, (dict, list)):
        raise BackupError("err_backup_json")
    return value


def read_backup(path_value):
    """
    Check a backup archive and return what it holds:
    {"path": the archive, "posts": {name: bytes}, "versions": {path: bytes},
     "media": {name: bytes, or the name of the entry to copy}, "config": dict
     or None, "subscribers": bytes or None, "ignored": [names]}.

    The texts are small and come back read. The media can be hundreds of
    megabytes of video: only their first bytes are read here, to check
    them, and restore_backup() copies them from the archive a piece at a
    time. An SVG comes back read, because it is rewritten without its
    active parts.

    Raise BackupError when the archive is not a PyBlog backup or one of its
    files does not pass the checks. Nothing is written.
    """
    if not zipfile.is_zipfile(path_value):
        raise BackupError("err_backup_not_zip")
    content = {"path": path_value, "posts": {}, "versions": {}, "media": {}, "config": None,
               "subscribers": None, "ignored": []}
    with zipfile.ZipFile(path_value) as zip_file:
        entries = [i for i in zip_file.infolist() if not i.is_dir()]
        if len(entries) > MAX_ENTRIES:
            raise BackupError("err_backup_too_many")
        if sum(i.file_size for i in entries) > MAX_TOTAL:
            raise BackupError("err_backup_file_too_large")
        for info in entries:
            name = info.filename
            if name == "config.json":
                value = _json_object(_read_entry(zip_file, info, MAX_JSON))
                if not isinstance(value, dict):
                    raise BackupError("err_backup_json")
                content["config"] = value
            elif name == "subscribers.json":
                data = _read_entry(zip_file, info, MAX_JSON)
                _json_object(data)
                content["subscribers"] = data
            elif POST_ENTRY.fullmatch(name):
                data = _read_entry(zip_file, info, MAX_JSON)
                if not isinstance(_json_object(data), dict):
                    raise BackupError("err_backup_json")
                content["posts"][name.split("/", 1)[1]] = data
            elif VERSION_ENTRY.fullmatch(name):
                data = _read_entry(zip_file, info, MAX_JSON)
                _json_object(data)
                content["versions"][name.split("/", 1)[1]] = data
            elif MEDIA_ENTRY.fullmatch(name):
                file_name = name.split("/", 1)[1]
                kind, limit = upload_kind(file_name)
                # The same rules as an upload: a safe name, an accepted
                # type, the size of its kind, and content that matches.
                if (kind is None or file_name.startswith(".")
                        or sanitize_file_name(file_name) != file_name):
                    content["ignored"].append(name)
                    continue
                if info.file_size > limit:
                    raise BackupError("err_backup_file_too_large")
                if file_name.lower().endswith(".svg"):
                    ok, data = sanitize_svg(_read_entry(zip_file, info, limit))
                    if not ok:
                        content["ignored"].append(name)
                        continue
                    content["media"][file_name] = data
                    continue
                with zip_file.open(info) as source:
                    head = source.read(64)
                if not magic_bytes_match("." + file_name.rsplit(".", 1)[1].lower(), head):
                    content["ignored"].append(name)
                    continue
                content["media"][file_name] = name
            else:
                content["ignored"].append(name)
    if content["config"] is None and not content["posts"]:
        raise BackupError("err_backup_not_pyblog")
    return content


# ---------------------------------------------------------------------------
# PUTTING BACK
# ---------------------------------------------------------------------------

def _copy_entry(zip_file, entry_name, fileobj):
    """
    Copy one medium out of the archive a megabyte at a time, stopping at the
    upload limit of its kind whatever the archive declares.
    """
    _, limit = upload_kind(entry_name.split("/", 1)[1])
    written = 0
    with zip_file.open(entry_name) as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                raise BackupError("err_backup_file_too_large")
            fileobj.write(chunk)


def _swap_folder(new_folder, current):
    """
    Put new_folder in the place of current, whole. The old one is renamed
    out of the way first and only deleted once the new one is in place; if
    the move fails, the old one goes back.
    """
    old = current.with_name("." + current.name + ".prima-del-ripristino")
    if old.exists():
        shutil.rmtree(old)
    if current.exists():
        os.replace(current, old)
    try:
        shutil.move(str(new_folder), str(current))
    except BaseException:
        if old.exists() and not current.exists():
            os.replace(old, current)
        raise
    if old.exists():
        shutil.rmtree(old)


def restore_backup(content):
    """
    Put back what read_backup() found. The caller has already saved the
    automatic backup and holds the build lock.

    What the archive does not hold is left as it is: a backup made before
    the media were included does not wipe the media of the site. The
    address of the administration is kept from the current configuration:
    a backup from another server must not move the editor to an address
    that does not lead here.
    """
    staging = tempfile.mkdtemp(dir=str(BASE_DIR), prefix=".ripristino-")
    try:
        if content["posts"]:
            posts = os.path.join(staging, "posts")
            os.makedirs(posts)
            for name, data in content["posts"].items():
                with open(os.path.join(posts, name), "wb") as fileobj:
                    fileobj.write(data)
            for relative, data in content["versions"].items():
                target = os.path.join(posts, *relative.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as fileobj:
                    fileobj.write(data)
            _swap_folder(posts, POSTS_DIR)
        if content["media"]:
            media = os.path.join(staging, "media")
            os.makedirs(media)
            with zipfile.ZipFile(content["path"]) as zip_file:
                for name, data in content["media"].items():
                    with open(os.path.join(media, name), "wb") as fileobj:
                        if isinstance(data, bytes):
                            fileobj.write(data)
                        else:
                            _copy_entry(zip_file, data, fileobj)
            MEDIA_DIR.parent.mkdir(parents=True, exist_ok=True)
            _swap_folder(media, MEDIA_DIR)
        if content["config"] is not None:
            new_config = dict(content["config"])
            current = {}
            if CONFIG_FILE.exists():
                try:
                    current = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    current = {}
            new_config["admin_url"] = current.get("admin_url", "") if isinstance(current, dict) else ""
            write_json_atomically(CONFIG_FILE, new_config)
        if content["subscribers"] is not None:
            target = os.path.join(staging, "subscribers.json")
            with open(target, "wb") as fileobj:
                fileobj.write(content["subscribers"])
            os.replace(target, SUBSCRIBERS_FILE)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"articles": len(content["posts"]), "versions": len(content["versions"]),
            "media": len(content["media"]), "config": content["config"] is not None,
            "subscribers": content["subscribers"] is not None,
            "ignored": content["ignored"]}

