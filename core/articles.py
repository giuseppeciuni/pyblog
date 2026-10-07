"""
Articles on disk, uploaded files and Markdown import/export.

An article is one JSON file in posts/. There is no database: the whole
content of the blog is a folder of readable files you can copy, diff and
put under version control.
"""
import html
import json
import re
import secrets
import shutil
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import images
from core.config import (CONFIG, MEDIA_DIR, POSTS_DIR, main_language,
                         migrate_article_schema, write_json_atomically)


class SlugTakenError(ValueError):
    """
    Raised when an article would be renamed onto the address of another one.

    Saving under that slug would replace the other article on disk, so the
    save is refused and nothing is written. The message is not shown as is:
    the caller translates it, and it carries the slug that was asked for.
    """

    def __init__(self, slug):
        super().__init__(slug)
        self.slug = slug



def slugify(text):
    """Turn a title into a slug suitable for URLs."""
    text = text.lower().strip()
    text = re.sub(r"[àáâä]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if not text:
        text = "article"
    return text


def slug_is_valid(slug):
    """
    Tell whether a slug is safe to use as a file name.
    We only allow lowercase letters, digits and hyphens: this way a slug
    can never contain paths like "../" and escape the posts folder.
    """
    if slug is None or slug == "":
        return False
    if re.fullmatch(r"[a-z0-9-]+", slug) is None:
        return False
    return True


def load_articles():
    """Read every article from the JSON files, sorted by descending date."""
    articles = []
    for f in POSTS_DIR.glob("*.json"):
        # A single corrupted file must not bring down the whole blog:
        # we skip it and report it in the console, the rest carries on.
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"WARNING: {f.name} is not valid JSON "
                  f"and will be skipped ({error}).")
            continue
        # Old Italian schema: convert and rewrite the file once.
        data, migrato = migrate_article_schema(data)
        if migrato:
            write_json_atomically(f, data)
            print(f"{f.name} migrated to the new English schema.")
        data["_file"] = f.name
        articles.append(data)
    articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    return articles


def load_article(slug):
    """Load a single article from its slug."""
    if not slug_is_valid(slug):
        return None
    path_value = POSTS_DIR / f"{slug}.json"
    if path_value.exists():
        # The same rule as load_articles: a damaged file is reported and
        # skipped, it does not turn the editor page into a server error.
        try:
            with open(path_value, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"WARNING: {path_value.name} is not valid JSON ({error}).")
            return None
        data, migrato = migrate_article_schema(data)
        if migrato:
            write_json_atomically(path_value, data)
        return data
    return None


def requested_slug(data):
    """
    The slug an article asks for: the one typed in the editor, or the one
    derived from its title. Normalised either way, so a hand-written slug
    with "/" or ".." can never escape the posts folder.

    An article that already exists and arrives with the slug field empty
    keeps the slug it has: changing the title must not move a published
    page to a new address behind the author's back.
    """
    slug = str(data.get("slug", "") or "").strip()
    if slug != "":
        return slugify(slug)
    original = str(data.get("original_slug", "") or "").strip()
    if original != "":
        return slugify(original)
    title_value = str(data.get("title", "") or "").strip()
    if title_value == "":
        title_value = "Senza titolo"
    return slugify(title_value)


def free_slug(slug):
    """
    The slug itself when no article uses it yet, otherwise the first free
    variant with a number on the end: "note", "note-2", "note-3"...
    """
    if not (POSTS_DIR / f"{slug}.json").exists():
        return slug
    number = 2
    while (POSTS_DIR / f"{slug}-{number}.json").exists():
        number = number + 1
    return f"{slug}-{number}"


# Attributes the editor puts on the content for its own use. They mean
# nothing on a published page: the hint over a table and the outline of the
# table that happened to be selected when the author pressed Save.
EDITOR_ONLY_ATTRIBUTES = re.compile(r'\sdata-hint="[^"]*"')
EDITOR_ONLY_CLASS = re.compile(r'(class="[^"]*?)\s*\bpb-tabella-selezionata\b([^"]*")')


def clean_editor_markup(html_value):
    """Remove the editor's own markers from a piece of article content."""
    if not isinstance(html_value, str) or html_value == "":
        return html_value
    html_value = EDITOR_ONLY_ATTRIBUTES.sub("", html_value)
    return EDITOR_ONLY_CLASS.sub(r"\1\2", html_value)


def id_list(value):
    """A list of snippet ids as strings, whatever the editor sent."""
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, (str, int))]


def own_snippets(value):
    """
    The pieces of code written inside an article, in the shape the build
    reads. They have no scope - their only page is the article - and each
    gets an id of its own, so the cards keep it from one save to the next.
    Position and consent are kept as written: the build reads anything it
    does not know as the head and as necessary.
    """
    if not isinstance(value, list):
        return []
    cleaned = []
    used = set()
    for snippet in value:
        if not isinstance(snippet, dict):
            continue
        snippet_id = str(snippet.get("id", "") or "")
        while snippet_id == "" or snippet_id in used:
            snippet_id = "art-" + secrets.token_hex(4)
        used.add(snippet_id)
        cleaned.append({
            "id": snippet_id,
            "name": str(snippet.get("name", "") or "").strip(),
            "enabled": snippet.get("enabled", True) is not False,
            "position": str(snippet.get("position", "") or "article_end"),
            "consent": str(snippet.get("consent", "") or "necessary"),
            "code": str(snippet.get("code", "") or ""),
        })
    return cleaned


def original_slug(data):
    """The slug the article has on disk, as the editor reports it, or ""."""
    original_text = str(data.get("original_slug", "") or "").strip()
    if original_text == "":
        return ""
    return slugify(original_text)


def article_from_data(data, slug):
    """
    The article dictionary from what the editor sent, every field cleaned
    the way a save cleans it. Nothing is written here, and the date is the
    one the data carries, or None.

    The article holds both the main-language and the translated version.
    """
    title_value = data.get("title", "").strip()
    if title_value == "":
        title_value = "Senza titolo"

    # We recover any fields of the English translation.
    # If they are missing, they stay empty strings.
    title_en = data.get("title_en", "").strip()
    description_en = data.get("description_en", "").strip()
    content_en = data.get("content_en", "")

    # Translation management flags.
    # traduzione_autorizzata: the author has approved creating the English draft.
    # traduzione_confermata: the English draft has been reviewed and approved for publishing.
    translation_authorized = data.get("translation_authorized", False)
    translation_confirmed = data.get("translation_confirmed", False)

    # Ids of the custom code snippets ticked for this article. Only the
    # snippets set to one of the "selected articles" scopes read this list; the
    # ids themselves live in config.json. An id of a snippet that has since
    # been deleted stays here harmlessly: the build simply never finds it.
    snippet_ids = id_list(data.get("custom_code_ids", []))
    # The opposite list: snippets that go on every article, switched off on
    # this one. Same rule for ids that no longer exist.
    off_ids = id_list(data.get("custom_code_off_ids", []))

    # Anything but the known states would be published by nobody and
    # listed as a draft by the dashboard: it is a draft. A scheduled article
    # needs the moment it goes out; without a valid one it stays a draft.
    status = data.get("status", "draft")
    if status not in ("draft", "published", "scheduled"):
        status = "draft"
    publish_at = ""
    if status == "scheduled":
        publish_at = normalized_moment(data.get("publish_at", ""))
        if publish_at == "":
            status = "draft"

    return {
        "title": title_value,
        "slug": slug,
        "description": data.get("description", "").strip(),
        # Reader preview: the text that appears in the homepage card.
        # If empty, the card shows an automatic excerpt of the content.
        "preview": data.get("preview", "").strip(),
        "content": clean_editor_markup(data.get("content", "")),
        "tags": data.get("tags", "").strip(),
        # The series the article is a part of, and its place in it.
        "series": str(data.get("series", "") or "").strip(),
        "series_number": series_number(data.get("series_number")),
        # A lab is the article that puts another one into practice: its
        # code, where the code lives and what it is written with.
        "kind": "lab" if data.get("kind") == "lab" else "",
        "lab_of": str(data.get("lab_of", "") or "").strip(),
        "repo_url": str(data.get("repo_url", "") or "").strip(),
        "stack": str(data.get("stack", "") or "").strip(),
        "image": data.get("image", "").strip(),
        "status": status,
        "publish_at": publish_at,
        "custom_code_ids": snippet_ids,
        "custom_code_off_ids": off_ids,
        "custom_code": own_snippets(data.get("custom_code", [])),
        # Whether the subscribers get an email when it is first published.
        "notify_subscribers": data.get("notify_subscribers", True) is not False,
        "date": data.get("date"),
        "date_modified": datetime.now(timezone.utc).isoformat(),
        # --- Translated version (the language that is not the main one) ---
        "title_en": title_en,
        "description_en": description_en,
        "preview_en": data.get("preview_en", "").strip(),
        "content_en": clean_editor_markup(content_en),
        "translation_authorized": translation_authorized,
        "translation_confirmed": translation_confirmed,
    }


def normalized_moment(value):
    """
    A moment in time as ISO 8601 in UTC, or "" when it is not one. The
    editor sends the author's local time with its offset; a moment without
    an offset is read as UTC.
    """
    if not isinstance(value, str) or value.strip() == "":
        return ""
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def due_scheduled_articles(now=None):
    """The scheduled articles whose moment has come, oldest moment first."""
    if now is None:
        now = datetime.now(timezone.utc)
    due = []
    for art in load_articles():
        if art.get("status") != "scheduled":
            continue
        moment = normalized_moment(art.get("publish_at", ""))
        if moment != "" and datetime.fromisoformat(moment) <= now:
            due.append(art)
    due.sort(key=lambda a: a.get("publish_at", ""))
    return due


def publish_due_articles(now=None):
    """
    Publish the scheduled articles whose moment has come, and return their
    slugs. The article goes out dated at the moment it was scheduled for, so
    it takes its place at the top of the lists as a new article does.
    """
    published = []
    for art in due_scheduled_articles(now):
        art.pop("_file", None)
        art["date"] = normalized_moment(art.get("publish_at", ""))
        art["status"] = "published"
        if not art.get("first_published"):
            art["first_published"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        art["publish_at"] = ""
        art["date_modified"] = datetime.now(timezone.utc).isoformat()
        write_json_atomically(POSTS_DIR / f"{art['slug']}.json", art)
        published.append(art["slug"])
    return published


# ---------------------------------------------------------------------------
# HISTORY: the earlier versions of an article
# ---------------------------------------------------------------------------
# Every save keeps the version it replaces in posts/.history/<slug>/, one
# file per version named after the moment it was saved. Autosave writes a
# draft every minute, so versions closer than HISTORY_GAP to the last one
# kept are not kept again - except a published version, which is always
# kept: it is the one readers saw. HISTORY_LIMIT versions per article.

HISTORY_DIR = POSTS_DIR / ".history"
HISTORY_LIMIT = 50
HISTORY_GAP = timedelta(minutes=10)
VERSION_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
# The fields that make a version: a save that changes none of them (only
# date_modified) is not a new version.
VERSION_FIELDS = ("title", "description", "preview", "content", "tags", "image",
                  "status", "publish_at", "title_en", "description_en",
                  "preview_en", "content_en", "custom_code")


def history_folder(slug):
    """The folder with the earlier versions of an article."""
    return HISTORY_DIR / slug


def version_id(moment):
    """The file name of a version saved at a moment: 20261003T094400Z."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def version_moment(identifier):
    """The moment of a version id, as an aware datetime."""
    return datetime.strptime(identifier, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def keep_version(slug, previous, new_article, now=None):
    """
    Keep the version an article is about to replace, when it is worth it:
    something that makes a version changed, and either the last version kept
    is older than HISTORY_GAP or the version replaced was the published one.
    """
    if previous is None:
        return
    if all(previous.get(field) == new_article.get(field) for field in VERSION_FIELDS):
        return
    if now is None:
        now = datetime.now(timezone.utc)
    folder = history_folder(slug)
    kept = sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []
    if kept and previous.get("status") != "published":
        if now - version_moment(kept[-1]) < HISTORY_GAP:
            return
    folder.mkdir(parents=True, exist_ok=True)
    previous = {k: v for k, v in previous.items() if k != "_file"}
    write_json_atomically(folder / f"{version_id(now)}.json", previous)
    kept.append(version_id(now))
    for old in sorted(set(kept))[:-HISTORY_LIMIT]:
        (folder / f"{old}.json").unlink(missing_ok=True)


def move_history(old_slug, new_slug):
    """A renamed article takes its versions with it."""
    old_folder = history_folder(old_slug)
    if not old_folder.is_dir() or old_slug == new_slug:
        return
    new_folder = history_folder(new_slug)
    if new_folder.exists():
        shutil.rmtree(new_folder)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    old_folder.rename(new_folder)


def list_versions(slug):
    """
    The earlier versions of an article, newest first: id, the moment it
    was replaced, title, status and number of words.
    """
    if not slug_is_valid(slug):
        return []
    folder = history_folder(slug)
    if not folder.is_dir():
        return []
    versions = []
    for path_value in sorted(folder.glob("*.json"), reverse=True):
        if not VERSION_ID_PATTERN.match(path_value.stem):
            continue
        data = read_article_file(path_value)
        if data is None:
            continue
        versions.append({
            "id": path_value.stem,
            "saved_at": version_moment(path_value.stem).isoformat(),
            "title": data.get("title", ""),
            "status": data.get("status", "draft"),
            "words": len(plain_text(data.get("content", "")).split()),
        })
    return versions


def load_version(slug, identifier):
    """One earlier version of an article, or None."""
    if not slug_is_valid(slug) or not VERSION_ID_PATTERN.match(str(identifier)):
        return None
    data = read_article_file(history_folder(slug) / f"{identifier}.json")
    if data is None:
        return None
    data.pop("_file", None)
    return data


def saved_date(slug, original):
    """
    The publication date of the article already on disk, or None.

    The editor does not send the date field: without this, every save would
    reset the publication date. A renamed article finds it under the slug it
    had before.
    """
    candidates = [POSTS_DIR / f"{slug}.json"]
    if original != "" and original != slug:
        candidates.append(POSTS_DIR / f"{original}.json")
    for candidate in candidates:
        existing = read_article_file(candidate)
        if existing is not None:
            return existing.get("date")
    return None


def save_article(data, new_article=False):
    """
    Save an article as a JSON file. Return the slug it was saved under.

    Two articles can never share a file, and that is what this function
    guards. With new_article=True (the first save of an article written in
    the editor, an imported document) a slug that is already taken gets a
    number on the end instead of replacing the article that owns it. An
    existing article renamed onto someone else's slug - original_slug says
    where it was - raises SlugTakenError before anything is written.
    """
    slug = requested_slug(data)
    original = original_slug(data)
    if new_article:
        slug = free_slug(slug)
    elif original != "" and original != slug and (POSTS_DIR / f"{slug}.json").exists():
        raise SlugTakenError(slug)

    article = article_from_data(data, slug)
    if article["date"] is None:
        article["date"] = saved_date(slug, original)
    # If the article is genuinely new, we use the current time.
    if article["date"] is None:
        article["date"] = datetime.now(timezone.utc).isoformat()

    # The version this save replaces goes to the history, which follows the
    # article when its slug changes.
    previous_slug = original if original != "" and original != slug else slug
    previous = None
    if not new_article:
        previous = read_article_file(POSTS_DIR / f"{previous_slug}.json")
        if previous_slug != slug:
            move_history(previous_slug, slug)
        keep_version(slug, previous, article)
    remember_publication(article, previous)
    write_json_atomically(POSTS_DIR / f"{slug}.json", article)
    return slug


def remember_publication(article, previous):
    """
    Carry over what the editor does not send: whether the newsletter already
    announced the article, and when it was first published. An article
    published before this field existed counts as published on its date.
    """
    if previous is not None:
        for key in ("newsletter_sent", "first_published"):
            if previous.get(key):
                article[key] = previous[key]
    if article.get("status") == "published" and not article.get("first_published"):
        if previous is not None and previous.get("status") == "published":
            article["first_published"] = previous.get("date") or article["date"]
        else:
            article["first_published"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def mark_newsletter_sent(slug):
    """Note on the article that the subscribers have had it."""
    path_value = POSTS_DIR / f"{slug}.json"
    art = read_article_file(path_value)
    if art is None:
        return
    art["newsletter_sent"] = True
    write_json_atomically(path_value, art)


def article_language_available(art, language):
    """Tell whether an article can be read in a language of the site."""
    if language == main_language():
        return True
    return art.get("translation_confirmed", False) is True


def article_for_preview(data):
    """
    The article as the editor holds it right now, for the preview: built
    exactly like a save, and never written. Previewing a published article
    must not put its half-done changes online. One already on disk keeps
    its date; a new one gets today's.
    """
    original = original_slug(data)
    article = article_from_data(data, requested_slug(data))
    if article["date"] is None and original != "":
        article["date"] = saved_date(original, original)
    if article["date"] is None:
        article["date"] = datetime.now(timezone.utc).isoformat()
    return article


def read_article_file(path_value):
    """The article stored in a file, or None if it is missing or unreadable."""
    if not path_value.exists():
        return None
    try:
        with open(path_value, encoding="utf-8") as fp:
            existing = json.load(fp)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(existing, dict):
        return None
    existing, _ = migrate_article_schema(existing)
    return existing


def delete_article(slug):
    """Delete an article from disk."""
    if not slug_is_valid(slug):
        return False
    path_value = POSTS_DIR / f"{slug}.json"
    if path_value.exists():
        path_value.unlink()
        # Its versions go with it: the backup is the way back. A history
        # folder left empty goes too, so nothing remains of the article.
        if history_folder(slug).is_dir():
            shutil.rmtree(history_folder(slug))
        if HISTORY_DIR.is_dir() and not any(HISTORY_DIR.iterdir()):
            HISTORY_DIR.rmdir()
        return True
    return False


def html_content_is_empty(html_content_value):
    """
    Tell whether an HTML content is "empty in practice".
    The Quill editor, when you clear it, still leaves tags like <p><br></p>.
    Here we strip the tags and the spaces: if nothing is left, it is empty.
    """
    if html_content_value is None:
        return True
    # We remove every HTML tag.
    without_tags = re.sub(r"<[^>]+>", "", html_content_value)
    # We remove spaces and invisible line breaks.
    without_tags = without_tags.replace("&nbsp;", " ")
    without_tags = without_tags.strip()
    if without_tags == "":
        return True
    return False


def card_slug(title_value):
    """Generate the slug (file name) of a card from its title."""
    slug = slugify(title_value)
    if slug == "":
        slug = "pagina"
    return slug


def excerpt_from_html(html_content_value, lunghezza=120):
    """Derive a short text excerpt from the HTML content of a card."""
    text = plain_text(html_content_value)
    if len(text) <= lunghezza:
        return text
    return text[:lunghezza].rstrip() + "..."

def plain_text(html_content_value):
    """Strip the HTML tags to get plain text (for the index and llms.txt)."""
    text = re.sub(r"<[^>]+>", " ", html_content_value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def articles_visible_in_language(articles, language):
    """
    Return the articles visible in a language: in the main language all of
    them, in the secondary one only those with a confirmed translation.
    """
    if language == main_language():
        return list(articles)
    visibili = []
    for art in articles:
        if art.get("translation_confirmed", False):
            visibili.append(art)
    return visibili

def extract_article_tags(art):
    """
    Return the list of an article's tags, cleaned up (no blanks).
    The tags are stored as a comma-separated string.
    """
    result = []
    tag_text = art.get("tags", "")
    if tag_text == "":
        return result
    for piece in tag_text.split(","):
        piece = piece.strip()
        if piece != "":
            result.append(piece)
    return result


def series_number(value):
    """The place of an article in its series: a number from 1 up, or 0 for none."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    if number < 1:
        return 0
    return number


def collect_series(articles):
    """
    Gather the articles into their series: { series slug: {"name": the name
    as written, "articles": [the parts, first to last]} }.

    The slug is the key, so "Inside the Machine" and "Inside the machine"
    are one series and not two. A part with a number goes where the number
    says; the ones without follow, in the order they were published.
    """
    found = {}
    for art in articles:
        name = str(art.get("series", "") or "").strip()
        if name == "":
            continue
        slug = slugify(name)
        if slug not in found:
            found[slug] = {"name": name, "articles": []}
        found[slug]["articles"].append(art)
    for entry in found.values():
        entry["articles"].sort(key=lambda art: (
            series_number(art.get("series_number")) or 10 ** 6, art.get("date") or ""))
        # The name is the one written on the first part.
        entry["name"] = str(entry["articles"][0].get("series", "")).strip()
    return found


def collect_tags(articles):
    """
    Collect every tag present in the articles and, for each one, the list
    of the articles using it. Return a dictionary:
    { tag_name: [article, article, ...] }.
    """
    mappa = {}
    for art in articles:
        for tag in extract_article_tags(art):
            if tag not in mappa:
                mappa[tag] = []
            mappa[tag].append(art)
    return mappa

# ---------------------------------------------------------------------------
# UPLOADED FILES
# ---------------------------------------------------------------------------
# An upload is the one place where a browser hands the server a file to keep.
# Three independent checks stand between that file and the media folder:
#
#   1. a size limit, applied by the server BEFORE reading the body, so a huge
#      upload is refused instead of being buffered in memory;
#   2. an extension whitelist, so nothing executable is ever written;
#   3. a check of the first bytes of the file, so a .png that is really
#      something else is refused even though its name looked fine.
#
# SVG is the exception: it is text, not a binary format, and it can carry
# scripts. It is parsed, stripped of anything active, and re-serialised; if it
# cannot be parsed with confidence, it is refused rather than guessed at.

MAX_IMAGE_BYTES = 10 * 1024 * 1024     # 10 MB
MAX_VIDEO_BYTES = 100 * 1024 * 1024    # 100 MB

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
VIDEO_EXTENSIONS = (".mp4", ".webm")

# First bytes that identify each format. A list per extension, because JPEG
# and MP4 have more than one legitimate opening.
MAGIC_SIGNATURES = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    # WebP and MP4 are RIFF/ISO containers: the marker sits after a 4-byte
    # length field, so it is checked separately in magic_bytes_match().
    ".webp": [],
    ".mp4": [],
    ".webm": [b"\x1a\x45\xdf\xa3"],
}


def upload_kind(file_name):
    """
    Return ("image", limit), ("video", limit) or (None, 0) for a file name.
    The extension decides both the whitelist and the size limit that applies.
    """
    extension = ""
    if "." in file_name:
        extension = "." + file_name.rsplit(".", 1)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return "image", MAX_IMAGE_BYTES
    if extension in VIDEO_EXTENSIONS:
        return "video", MAX_VIDEO_BYTES
    return None, 0


def magic_bytes_match(extension, data):
    """
    Tell whether the first bytes of the file match the declared extension.
    SVG is text and has no magic number: it is handled by sanitize_svg().
    """
    extension = extension.lower()
    if extension == ".svg":
        return True

    if extension == ".webp":
        # RIFF....WEBP
        if len(data) < 12:
            return False
        return data[0:4] == b"RIFF" and data[8:12] == b"WEBP"

    if extension == ".mp4":
        # An ISO base media file starts with a size field followed by "ftyp".
        if len(data) < 12:
            return False
        return data[4:8] == b"ftyp"

    signatures = MAGIC_SIGNATURES.get(extension, [])
    for signature in signatures:
        if data.startswith(signature):
            return True
    return False


# Attributes and elements that make an SVG active. Everything here is removed;
# if the document cannot be parsed at all, it is refused instead.
SVG_DANGEROUS_TAGS = ("script", "foreignObject", "handler", "set", "animate",
                      "animateTransform", "animateMotion")


def sanitize_svg(binary_data):
    """
    Remove every active element from an SVG and return (ok, cleaned_bytes).

    An SVG is XML, so it can contain <script>, on* event handlers and
    javascript: links; served from our own origin it would run with the full
    privileges of the site. We parse it, drop those constructs and write it
    back out. If parsing fails, or the file declares its own entities (a
    classic expansion attack), we return ok=False: an SVG we cannot fully
    understand is not one we should publish.
    """
    try:
        text = binary_data.decode("utf-8")
    except UnicodeDecodeError:
        return False, b""

    # A DOCTYPE or an ENTITY declaration has no place in an uploaded image and
    # is the usual vehicle for entity-expansion attacks. We refuse both.
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        return False, b""

    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    ElementTree.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return False, b""

    def local_name(tag):
        """The tag name without its {namespace} prefix."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def clean(element):
        # Attributes: drop every on* handler and every javascript: target.
        for attribute in list(element.attrib.keys()):
            name = local_name(attribute).lower()
            value = element.attrib[attribute]
            if name.startswith("on"):
                del element.attrib[attribute]
                continue
            if name in ("href", "xlink:href", "src"):
                if value.strip().lower().replace("\t", "").startswith("javascript:"):
                    del element.attrib[attribute]
                    continue
            if name == "style" and "javascript:" in value.lower():
                del element.attrib[attribute]

        # Children: remove the active elements, recurse into the rest.
        for child in list(element):
            if local_name(child.tag) in SVG_DANGEROUS_TAGS:
                element.remove(child)
            else:
                clean(child)

    if local_name(root.tag) != "svg":
        return False, b""
    clean(root)

    cleaned = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    return True, cleaned


def max_image_side():
    """The widest an uploaded image is kept at, from the configuration."""
    value = CONFIG.get("max_image_width", images.DEFAULT_MAX_SIDE)
    try:
        value = int(value)
    except (ValueError, TypeError):
        value = images.DEFAULT_MAX_SIDE
    if value <= 0:
        return 0
    return value


def validate_upload(file_name, binary_data):
    """
    Run every check on an uploaded file, and shrink it where we can.

    Return {"ok": True, "data": bytes, "optimisation": {...}} with the
    content to write, or {"ok": False, "error_key": "...", "limit_mb": n}
    describing why it was refused. The caller turns the key into a translated
    message.

    The shrinking happens AFTER the checks, never before: an image is only
    decoded once we know it is really an image of a type we accept.
    """
    kind, limit = upload_kind(file_name)
    if kind is None:
        return {"ok": False, "error_key": "err_file_type_not_allowed"}

    if len(binary_data) > limit:
        return {"ok": False, "error_key": "err_file_too_large",
                "limit_mb": limit // (1024 * 1024)}

    extension = "." + file_name.rsplit(".", 1)[1].lower()

    if extension == ".svg":
        ok, cleaned = sanitize_svg(binary_data)
        if not ok:
            return {"ok": False, "error_key": "err_svg_unsafe"}
        return {"ok": True, "data": cleaned}

    if not magic_bytes_match(extension, binary_data):
        return {"ok": False, "error_key": "err_file_content_mismatch"}

    if kind == "video":
        return {"ok": True, "data": binary_data}

    side = max_image_side()
    if side == 0:
        return {"ok": True, "data": binary_data}
    optimisation = images.optimise_image(file_name, binary_data, side)
    return {"ok": True, "data": optimisation["data"], "optimisation": optimisation}


def sanitize_file_name(name_value):
    """
    Make the name of an uploaded file safe.
    It keeps only letters, digits, dots, hyphens and underscores.
    """
    clean_name = ""
    caratteri_ammessi = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
    for character in name_value:
        if character in caratteri_ammessi:
            clean_name = clean_name + character
        else:
            clean_name = clean_name + "_"
    return clean_name


def save_uploaded_file(file_name, binary_data):
    """
    Save an uploaded file (video or image) into the media folder and
    return its URL. If a file with the same name already exists, it
    appends a progressive number so that nothing is overwritten.

    The caller must have run validate_upload() first: this function writes
    what it is given.
    """
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_file_name(file_name)
    if safe_name == "":
        safe_name = "file"

    path_value = MEDIA_DIR / safe_name

    # If the name already exists, look for a free one by adding a number.
    counter = 1
    while path_value.exists():
        parti = safe_name.rsplit(".", 1)
        if len(parti) == 2:
            new_name = parti[0] + "-" + str(counter) + "." + parti[1]
        else:
            new_name = safe_name + "-" + str(counter)
        path_value = MEDIA_DIR / new_name
        counter = counter + 1

    with open(path_value, "wb") as fp:
        fp.write(binary_data)

    url = "/media/" + path_value.name
    return url


# ---------------------------------------------------------------------------
# MARKDOWN IMPORT/EXPORT (to migrate from/to Hugo, Jekyll and the like)
# ---------------------------------------------------------------------------
# Markdown -> HTML converter written in pure Python, with no dependencies.
# It deliberately covers a SUBSET of Markdown: headings, bold, italic,
# inline and block code, links, images, lists, quotes, horizontal
# rules and paragraphs. It does not cover: tables, footnotes, complex
# mixed HTML. For a blog it is more than enough.


def markdown_inline(text):
    """
    Convert the formatting INSIDE a line: bold, italic, inline code,
    images and links. The text is first made safe (HTML escape), then
    the substitutions are applied.
    """
    text = html.escape(text, quote=False)
    # Images: ![alt text](url) - BEFORE links, which have a
    # similar syntax but without the exclamation mark.
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                   r'<img src="\2" alt="\1">', text)
    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                   r'<a href="\2">\1</a>', text)
    # Inline code: `code` - before bold/italic, so that the
    # asterisks inside the code are not interpreted.
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    # Italic: *text* or _text_ (after bold).
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<em>\1</em>", text)
    return text


def markdown_to_html(md_text):
    """
    Convert a Markdown text into HTML compatible with what the Quill
    editor produces (same classes, so the blog styling applies).
    It works line by line, handling multi-line blocks (code, lists, quotes).
    """
    lines = md_text.replace("\r\n", "\n").split("\n")
    html_out = []
    paragraph = []          # lines of the paragraph being built
    in_code_block = False       # inside a ``` block?
    code_lines = []
    tipo_lista = ""         # "ul", "ol" or "" (no list open)
    quote_lines = []

    def close_paragraph():
        if len(paragraph) > 0:
            content = " ".join(paragraph)
            html_out.append("<p>" + markdown_inline(content) + "</p>")
            paragraph.clear()

    def close_list():
        nonlocal tipo_lista
        if tipo_lista != "":
            html_out.append("</" + tipo_lista + ">")
            tipo_lista = ""

    def close_quote():
        if len(quote_lines) > 0:
            content = " ".join(quote_lines)
            html_out.append("<blockquote>" + markdown_inline(content) + "</blockquote>")
            quote_lines.clear()

    for line in lines:
        # --- Fenced code blocks (```) ---
        if line.strip().startswith("```"):
            if in_code_block:
                # End of the block: we emit the code as it is (escaped).
                code = html.escape("\n".join(code_lines))
                html_out.append('<pre class="ql-syntax">' + code + "</pre>")
                code_lines = []
                in_code_block = False
            else:
                close_paragraph()
                close_list()
                close_quote()
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(line)
            continue

        stripped = line.strip()

        # --- Blank line: closes paragraph, list and quote ---
        if stripped == "":
            close_paragraph()
            close_list()
            close_quote()
            continue

        # --- Horizontal rule ---
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            close_paragraph()
            close_list()
            close_quote()
            html_out.append("<hr>")
            continue

        # --- Headings: from # to ###### ---
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            close_paragraph()
            close_list()
            close_quote()
            level = len(heading_match.group(1))
            content = heading_match.group(2).strip()
            html_out.append(f"<h{level}>" + markdown_inline(content) + f"</h{level}>")
            continue

        # --- Quotes: lines starting with > ---
        if stripped.startswith(">"):
            close_paragraph()
            close_list()
            quote_lines.append(stripped.lstrip("> ").strip())
            continue

        # --- Bulleted lists: -, * or + followed by a space ---
        ul_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if ul_match:
            close_paragraph()
            close_quote()
            if tipo_lista != "ul":
                close_list()
                html_out.append("<ul>")
                tipo_lista = "ul"
            html_out.append("<li>" + markdown_inline(ul_match.group(1)) + "</li>")
            continue

        # --- Numbered lists: 1. 2. 3. ---
        ol_match = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if ol_match:
            close_paragraph()
            close_quote()
            if tipo_lista != "ol":
                close_list()
                html_out.append("<ol>")
                tipo_lista = "ol"
            html_out.append("<li>" + markdown_inline(ol_match.group(1)) + "</li>")
            continue

        # --- Normal text: accumulates into the current paragraph ---
        close_list()
        close_quote()
        paragraph.append(stripped)

    # End of file: we close everything that is still open.
    close_paragraph()
    close_list()
    close_quote()
    if in_code_block and len(code_lines) > 0:
        code = html.escape("\n".join(code_lines))
        html_out.append('<pre class="ql-syntax">' + code + "</pre>")

    return "\n".join(html_out)


def html_to_markdown(html_content_value):
    """
    Convert an article's HTML into simplified Markdown (for the export).
    It is a lossy conversion: Quill's advanced formatting (alignment,
    colours, sizes) becomes plain text.
    """
    text = html_content_value

    # Code blocks: the content must be preserved with no other conversion.
    # We pull them out first and put them back at the end using placeholders.
    code_blocks = []

    def stash_code_block(match):
        content = html.unescape(match.group(1))
        code_blocks.append(content)
        return "\n\x00CODICE" + str(len(code_blocks) - 1) + "\x00\n"

    text = re.sub(r'<pre[^>]*>(.*?)</pre>', stash_code_block, text, flags=re.DOTALL)

    # Headings h1..h6 -> #..######
    for level in range(6, 0, -1):
        cancelletti = "#" * level
        text = re.sub(rf"<h{level}[^>]*>(.*?)</h{level}>",
                       rf"\n{cancelletti} \1\n", text, flags=re.DOTALL)

    # Bold, italic, inline code.
    text = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL)
    text = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)

    # Images and links.
    text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>', r"![\2](\1)", text)
    text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*>', r"![](\1)", text)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL)

    # Quotes.
    text = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>", r"\n> \1\n", text, flags=re.DOTALL)

    # Lists: every <li> becomes a line with - (numbered ones lose their
    # explicit numbers but stay readable; it is a declared simplification).
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n", text)

    # Horizontal rules and line breaks.
    text = re.sub(r"<hr[^>]*>", "\n---\n", text)
    text = re.sub(r"<br[^>]*>", "\n", text)

    # Paragraphs -> lines separated by a blank line.
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)

    # Any other remaining tag is removed.
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)

    # We put the code blocks back in place.
    for block_index in range(len(code_blocks)):
        placeholder = "\x00CODICE" + str(block_index) + "\x00"
        block = "```\n" + code_blocks[block_index].strip("\n") + "\n```"
        text = text.replace(placeholder, block)

    # We normalise multiple blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def read_front_matter(md_text):
    """
    Read the "front matter" of a Markdown file: the metadata block
    between two "---" lines at the start of the file (Hugo/Jekyll style).
    Return (metadata_dictionary, text_without_front_matter).
    It supports simple "key: value" values and [a, b, c] lists.
    """
    metadata = {}
    lines = md_text.replace("\r\n", "\n").split("\n")
    if len(lines) == 0 or lines[0].strip() != "---":
        return metadata, md_text

    end = -1
    for index_value in range(1, len(lines)):
        if lines[index_value].strip() == "---":
            end = index_value
            break
    if end == -1:
        return metadata, md_text

    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        # We strip any quotes around the value.
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        # Lists in [a, b, c] style -> string "a, b, c" (PyBlog tag format).
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            pieces = []
            for piece in inner.split(","):
                piece = piece.strip().strip("\"'")
                if piece != "":
                    pieces.append(piece)
            value = ", ".join(pieces)
        metadata[key] = value

    body = "\n".join(lines[end + 1:])
    return metadata, body


def import_markdown(path_value):
    """
    Import one or more Markdown files as PyBlog articles.
    It accepts a single .md file or a folder (it imports every .md).
    The metadata is read from the front matter; the missing pieces are
    derived (title from the first #, slug from the title, "draft" status).
    Return the number of imported articles.
    """
    path_value = Path(path_value)
    if path_value.is_dir():
        file_md = sorted(path_value.glob("*.md"))
    elif path_value.is_file():
        file_md = [path_value]
    else:
        print(f"Error: {path_value} does not exist.")
        return 0

    imported_count = 0
    for file_corrente in file_md:
        text = file_corrente.read_text(encoding="utf-8")
        metadata, body = read_front_matter(text)

        # Title: from the front matter, or from the first # heading, or from the file name.
        # English keys first; the old Italian front matter keys still work.
        title_value = metadata.get("title", metadata.get("titolo", ""))
        if title_value == "":
            match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
            if match:
                title_value = match.group(1).strip()
                # We remove the title from the body: it becomes the page's <h1>.
                body = body.replace(match.group(0), "", 1)
        if title_value == "":
            title_value = file_corrente.stem.replace("-", " ").replace("_", " ").title()

        # Status: "pubblicato"/"published", otherwise draft (the cautious default).
        raw_status = metadata.get("status", metadata.get("stato", metadata.get("draft", "")))
        if raw_status in ("published", "pubblicato"):
            status = "published"
        elif raw_status == "false":
            # Hugo uses "draft: false" to mean "published".
            status = "published"
        else:
            status = "draft"

        data = {
            "title": title_value,
            "slug": metadata.get("slug", ""),
            "description": metadata.get("description", metadata.get("descrizione", "")),
            "content": markdown_to_html(body),
            "tags": metadata.get("tags", metadata.get("tag", "")),
            "status": status,
            "date": metadata.get("date", metadata.get("data", None)),
        }
        # An import never replaces an article that is already there: running
        # the same import twice, or importing a file whose title matches an
        # existing article, adds a copy with a numbered slug instead.
        slug = save_article(data, new_article=True)
        print(f"  imported: {file_corrente.name} -> posts/{slug}.json ({status})")
        if slug != requested_slug(data):
            print(f"    note: {requested_slug(data)} was already taken, saved as {slug}")
        imported_count = imported_count + 1

    return imported_count


def export_markdown(destination_folder):
    """
    Export every article to Markdown files with front matter, into the
    given folder (which is created if it does not exist).
    Return the number of exported articles.
    """
    destination = Path(destination_folder)
    destination.mkdir(parents=True, exist_ok=True)

    articles = load_articles()
    exported_count = 0
    for art in articles:
        lines = ["---"]
        lines.append("title: " + art.get("title", ""))
        lines.append("slug: " + art.get("slug", ""))
        lines.append("date: " + str(art.get("date", "")))
        lines.append("status: " + art.get("status", "draft"))
        if art.get("description", "") != "":
            lines.append("description: " + art["description"])
        if art.get("tags", "") != "":
            lines.append("tags: [" + art["tags"] + "]")
        lines.append("---")
        lines.append("")
        lines.append(html_to_markdown(art.get("content", "")))
        md_content = "\n".join(lines)
        (destination / (art["slug"] + ".md")).write_text(md_content, encoding="utf-8")
        print(f"  exported: {art['slug']}.md")
        exported_count = exported_count + 1

    return exported_count