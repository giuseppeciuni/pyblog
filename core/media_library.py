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
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime

from core.articles import load_articles, upload_kind
from core.config import (BASE_DIR, MEDIA_DIR, POSTS_DIR, load_config, save_config,
                         write_json_atomically)

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

# The lighter versions of a picture: WebP at a few widths, made by the
# browser when the picture is uploaded (Python alone cannot re-encode a JPEG
# or a PNG) and kept in media/_sizes/<name>/<width>.webp. The pages offer
# them in srcset, so a phone downloads a 480-pixel picture, not a
# 1600-pixel one. The folder name cannot be the name of an upload (those
# start with a letter or a digit), and it is not in the backups: the
# versions can always be made again from the picture.
SIZES_FOLDER = "_sizes"
MAX_SIZE_WIDTH = 2000
# The pictures the browser can make lighter versions of.
RESIZABLE = (".jpg", ".jpeg", ".png", ".webp")


def can_have_sizes(name):
    """Tell whether lighter versions of this file can be made."""
    return name.lower().endswith(RESIZABLE)


def sizes_folder(name):
    """The folder of the lighter versions of a picture."""
    return MEDIA_DIR / SIZES_FOLDER / name


def sized_widths(name):
    """The widths a picture has lighter versions at, smallest first."""
    if SAFE_NAME.fullmatch(name or "") is None:
        return []
    folder = sizes_folder(name)
    if not folder.is_dir():
        return []
    return sorted(int(p.stem) for p in folder.glob("*.webp") if p.stem.isdigit())


def save_size(name, width, data):
    """
    Keep a lighter version of an uploaded picture. Only a WebP, of a picture
    that is in the media folder, at a sensible width: anything else is
    refused, so this door cannot be used to put other files on the site.
    Return True when it was saved.
    """
    if SAFE_NAME.fullmatch(name or "") is None or not can_have_sizes(name):
        return False
    if not (MEDIA_DIR / name).is_file():
        return False
    if not isinstance(width, int) or width < 16 or width > MAX_SIZE_WIDTH:
        return False
    if len(data) < 12 or len(data) > 10 * 1024 * 1024 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return False
    folder = sizes_folder(name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{width}.webp").write_bytes(data)
    return True


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
                      "size": stat.st_size, "date": datetime.fromtimestamp(stat.st_mtime),
                      "resizable": can_have_sizes(path_value.name),
                      "sized": sized_widths(path_value.name)})
    return sorted(found, key=lambda m: (m["date"], m["name"]), reverse=True)


def duplicate_groups(files=None):
    """
    The files saved more than once with the same bytes: a list of groups,
    each a list of names, oldest first. Files of a size no other file has
    are never read.
    """
    if files is None:
        files = media_files()
    by_size = {}
    for item in files:
        by_size.setdefault(item["size"], []).append(item)
    groups = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_content = {}
        for item in sorted(same_size, key=lambda m: (m["date"], m["name"])):
            try:
                digest = hashlib.sha256((MEDIA_DIR / item["name"]).read_bytes()).hexdigest()
            except OSError:
                continue
            by_content.setdefault(digest, []).append(item["name"])
        groups.extend(names for names in by_content.values() if len(names) > 1)
    return sorted(groups)


def merge_duplicates():
    """
    Keep one file for each picture saved more than once, and point every use
    of the others at it: the articles and the settings name the copy that
    stays, and the others go to the trash, as a deletion would send them.
    The copy that stays is the most used one, the oldest when it is a tie.
    Return {"merged": copies removed, "articles": articles changed}.
    The caller rebuilds the site.
    """
    uses = media_uses()
    renames = {}
    for names in duplicate_groups():
        keep = max(names, key=lambda n: (len(uses.get(n, [])), -names.index(n)))
        for name in names:
            if name != keep:
                renames[name] = keep
    if not renames:
        return {"merged": 0, "articles": 0}
    pattern = re.compile(r"/media/(" + "|".join(map(re.escape, sorted(renames, key=len, reverse=True)))
                         + r")(?![A-Za-z0-9._-])")

    def renamed(value):
        text = json.dumps(value, ensure_ascii=False)
        new_text = pattern.sub(lambda m: "/media/" + renames[m.group(1)], text)
        return None if new_text == text else json.loads(new_text)

    changed_articles = 0
    for path_value in sorted(POSTS_DIR.glob("*.json")):
        try:
            article = json.loads(path_value.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        new_article = renamed(article)
        if new_article is not None:
            write_json_atomically(path_value, new_article)
            changed_articles += 1
    new_config = renamed(load_config())
    if new_config is not None:
        save_config(new_config)
    deleted = delete_media(sorted(renames))
    return {"merged": len(deleted), "articles": changed_articles}


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
        # Its lighter versions go with it: they can be made again.
        shutil.rmtree(sizes_folder(name), ignore_errors=True)
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
