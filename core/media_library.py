"""
The media library: every file uploaded to the site, and where it is used.

An uploaded picture lives in output/media and is named by its address,
/media/<name>, wherever it is used: in the text of an article, as its cover,
in the settings (the author's photo, the logo, a project). Nothing kept a
list of them, so a picture removed from an article stayed on disk for ever,
and deleting one by hand could leave a hole in a page nobody remembered.

The library finds the uses by reading the articles and the configuration
for those addresses. It reads the current version of each article only: an
earlier version that names a picture does not keep it alive, and putting
that version back says so in the editor anyway.
"""
import json
import os
import re
import shutil
import time
from datetime import datetime

from core.articles import load_articles, upload_kind
from core.config import BASE_DIR, MEDIA_DIR, load_config

# Deleted media wait here for a month before they are gone for good: a
# picture deleted by mistake can still be put back by hand. The folder sits
# next to the automatic backups, outside what nginx publishes.
TRASH_DIR = BASE_DIR / "backups" / "deleted-media"
TRASH_DAYS = 30

# How a medium is named in an article or in the settings, relative or with
# the site's address in front: the name is what follows /media/.
MEDIA_REFERENCE = re.compile(r"/media/([A-Za-z0-9._-]+)")

# A name the library will act on: the names uploads are saved under.
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def media_files():
    """Every uploaded file, newest first: name, kind, size and date."""
    if not MEDIA_DIR.is_dir():
        return []
    found = []
    for path_value in MEDIA_DIR.iterdir():
        if not path_value.is_file() or SAFE_NAME.fullmatch(path_value.name) is None:
            continue
        kind, _ = upload_kind(path_value.name)
        stat = path_value.stat()
        found.append({"name": path_value.name, "kind": kind or "other",
                      "size": stat.st_size, "date": datetime.fromtimestamp(stat.st_mtime)})
    return sorted(found, key=lambda m: (m["date"], m["name"]), reverse=True)


def references(value):
    """The media names a piece of data mentions, as a set."""
    return set(MEDIA_REFERENCE.findall(json.dumps(value, ensure_ascii=False)))


def media_uses(articles=None, config=None):
    """
    Where each medium is used: {name: [use, ...]}, where a use is
    {"kind": "article", "slug", "title", "status"} or {"kind": "settings"}.
    """
    if articles is None:
        articles = load_articles()
    if config is None:
        config = load_config()
    uses = {}
    for art in articles:
        for name in references(art):
            uses.setdefault(name, []).append({
                "kind": "article", "slug": art.get("slug", ""),
                "title": art.get("title", "") or art.get("slug", ""),
                "status": art.get("status", "draft")})
    for name in references(config):
        uses.setdefault(name, []).append({"kind": "settings"})
    return uses


def delete_media(names):
    """
    Move uploaded files to the trash by name. Only plain names of files that
    are in the media folder are taken: a name with a slash, or one that
    leads anywhere else, is skipped. Return the names actually moved.
    """
    deleted = []
    if not isinstance(names, list):
        return deleted
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        if not isinstance(name, str) or SAFE_NAME.fullmatch(name) is None:
            continue
        path_value = MEDIA_DIR / name
        if path_value.parent != MEDIA_DIR or not path_value.is_file():
            continue
        target = TRASH_DIR / name
        # output/ can sit on another disk than the project (a Docker volume).
        shutil.move(str(path_value), str(target))
        # The move keeps the upload date; the month in the trash starts now.
        os.utime(target, None)
        deleted.append(name)
    empty_trash()
    return deleted


def empty_trash(now=None):
    """Remove from the trash what has been there longer than a month."""
    if not TRASH_DIR.is_dir():
        return
    limit = (now if now is not None else time.time()) - TRASH_DAYS * 86400
    for path_value in TRASH_DIR.iterdir():
        if path_value.is_file() and path_value.stat().st_mtime < limit:
            path_value.unlink()
