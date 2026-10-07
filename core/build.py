"""
Generation of the static site.

Everything under output/ is produced here: the article pages, the two
homepages, the archives, the tag indexes, the card pages, the feeds, the
sitemap, robots.txt, llms.txt and the AI-training files.

The HTML itself lives in templates/; this module only decides what goes into
the placeholders. Two rules are absolute:

  - a value that ends up in HTML goes through render.esc();
  - a value that ends up in JavaScript goes through render.js().
"""
import hashlib
import html
import html.parser
import json
import re
import urllib.parse
import threading
from datetime import datetime, timezone

from core import newsletter, render
from core.articles import (articles_visible_in_language, card_slug,
                           collect_series, collect_tags, excerpt_from_html,
                           extract_article_tags, html_content_is_empty,
                           load_articles, plain_text, publish_due_articles,
                           slugify)
from core.config import (CONFIG, CONFIG_DEFAULT, MEDIA_DIR, OUTPUT_DIR,
                         ai_training_config, archive_file_name,
                         articles_per_page_count, feed_file_name,
                         language_url_prefix, main_language,
                         pagination_folder, reload_global_config,
                         secondary_language, seo_data)
from core.i18n import LANGUAGE_NAMES, T
from core.render import esc, js

# A build rewrites the whole output folder. Two requests rebuilding at the
# same time would interleave their writes, so every build - and every save
# that triggers one - runs under this lock. It is reentrant because build()
# takes it itself and callers wrap a save-plus-build sequence in it.
BUILD_LOCK = threading.RLock()

# A literal newline, for the places where HTML is assembled by hand.
NEWLINE = "\n"


# ---------------------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------------------

def block(text):
    """
    Prepare an optional chunk for a template placeholder sitting at column 0:
    empty stays empty, anything else gets a trailing newline. This keeps blank
    lines out of the generated HTML when a section is not present.
    """
    if text is None or text == "":
        return ""
    if text.endswith("\n"):
        return text
    return text + "\n"


def format_date(iso_string, language="it"):
    """Convert an ISO date into a readable format, in the page language."""
    try:
        dt = datetime.fromisoformat(iso_string)
        if language == "en":
            months = ["January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"]
            return f"{months[dt.month - 1]} {dt.day}, {dt.year}"
        months = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except (ValueError, IndexError):
        return iso_string


def feed_url(language):
    """Absolute-from-root URL of the RSS feed of a language."""
    return "/" + feed_file_name(language)


def profile_label(url):
    """
    Derive a readable label from a social profile URL:
    "https://github.com/name" -> "GitHub". If the domain is not known,
    it uses the domain itself (e.g. "mastodon.social").
    """
    noti = {
        "github.com": "GitHub", "linkedin.com": "LinkedIn",
        "x.com": "X", "twitter.com": "X", "youtube.com": "YouTube",
        "instagram.com": "Instagram", "facebook.com": "Facebook",
        "medium.com": "Medium", "dev.to": "DEV",
    }
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    if m is None:
        return url
    domain = m.group(1).lower()
    if domain in noti:
        return noti[domain]
    return domain


def social_profile_links():
    """The configured social profiles as a list of ready <a> elements."""
    profiles = seo_data().get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    links = []
    for profile in profiles:
        label = esc(profile_label(profile))
        links.append(f'<a href="{esc(profile)}" rel="me">{label}</a>')
    return links


# Matches an <img> tag that does not already carry a loading attribute.
LAZY_IMAGE_PATTERN = re.compile(r"<img(?![^>]*\bloading=)([^>]*)>", re.IGNORECASE)
# The src of an image, with the quote it is written with, so the value can be
# rewritten without touching the rest of the tag.
IMAGE_SRC_PATTERN = re.compile(r'(<img[^>]*\ssrc=")([^"]*)(")', re.IGNORECASE)


# An address that already says where it points: another site, the page's own
# protocol, the site root, or the file carried inside the page itself.
ABSOLUTE_URL_PATTERN = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|/)", re.IGNORECASE)


def media_url(url):
    """
    Make a picture's address absolute, when it is one of ours.

    A cover typed as "media/foto.png" works on the homepage and nowhere else.
    The English homepage lives at /en/, so the browser looks for
    /en/media/foto.png and finds nothing: the thumbnail is there in Italian
    and gone in English, which reads as a translation problem and is not one.
    The same address on an article page asks for /posts/media/foto.png.

    Rather than leave that to whoever fills the field, an address that points
    nowhere in particular is read as pointing at the site root, which for a
    static site is the only thing it can sensibly mean.
    """
    if url is None:
        return ""
    url = url.strip()
    if url == "" or ABSOLUTE_URL_PATTERN.match(url):
        return url
    return "/" + url.lstrip("./")


def shared_url(url):
    """
    The address of a picture for whoever reads it away from the site: a
    social network building a preview, a search engine. "/media/foto.png"
    means nothing there, so an address of ours gets the site in front.
    """
    url = media_url(url)
    if url.startswith("/") and not url.startswith("//"):
        return CONFIG["base_url"].rstrip("/") + url
    return url


def with_site_title(page_title):
    """
    The <title> of a page: its own title, a dot and the name of the site.
    A site that has no name yet gets the page title alone, not a title
    that ends with a dot.
    """
    site_title = esc(CONFIG.get("site_title", "").strip())
    if site_title == "":
        return page_title
    return f"{page_title} &middot; {site_title}"


def absolute_image_sources(html_content_value):
    """Apply media_url to the src of every image of a piece of content."""
    def fix(match):
        return match.group(1) + media_url(match.group(2)) + match.group(3)
    return IMAGE_SRC_PATTERN.sub(fix, html_content_value)


def add_lazy_loading(html_content_value):
    """
    Add loading="lazy" to every image that does not already have it.

    An article can carry a dozen photos, and a reader on a phone should not
    pay for the ones below the fold. The attribute is added here rather than
    in the editor so it also covers articles written before this existed, and
    content pasted from Word or imported from Markdown.

    The addresses are made absolute in the same pass, for the reason spelled
    out in media_url: a relative one shows the picture on the homepage and
    loses it everywhere else, the English pages included.
    """
    if html_content_value is None or html_content_value == "":
        return ""
    html_content_value = absolute_image_sources(html_content_value)
    return LAZY_IMAGE_PATTERN.sub(r'<img\1 loading="lazy">', html_content_value)


def excerpt_word_count():
    """How many words of an article the lists show, from the configuration."""
    value = CONFIG.get("home_excerpt_words", 40)
    try:
        value = int(value)
    except (ValueError, TypeError):
        value = 40
    return max(10, min(value, 200))


def excerpt_words(html_content_value, words):
    """
    The opening of an article as plain text, cut after a number of words.

    It used to be cut after a number of CHARACTERS, which stops in the middle
    of a word as often as not ("Un modello linguistico non sa nul...").
    Counting words keeps every word whole, and the ellipsis says the text
    goes on.
    """
    text = plain_text(prose_only(html_content_value or ""))
    if text == "":
        text = plain_text(html_content_value or "")
    pieces = text.split()
    if len(pieces) <= words:
        return text
    # A cut that falls after a full stop would read "artificiale.…": the
    # punctuation goes, and the ellipsis alone says the text goes on.
    return " ".join(pieces[:words]).rstrip(",;:-.!?…") + "…"


# The parts of an article that are not running text: headings, code, tables
# and the [n] marks of the footnotes. In an excerpt they read as noise - a
# heading glued to the next sentence ("...del blog. Il problema Ogni...").
NOT_PROSE_PATTERN = re.compile(
    r"<(h[1-6]|pre|table|figcaption)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
FOOTNOTE_MARK_PATTERN = re.compile(r"<sup>\[\d+\]</sup>", re.IGNORECASE)
# Tags that live inside a line of text. They are removed without leaving a
# space, so "E=mc<sup>2</sup>" stays "E=mc2" and a bold word stays glued to
# its comma; block tags still turn into spaces between sentences.
INLINE_TAG_PATTERN = re.compile(
    r"</?(a|strong|b|em|i|u|s|sup|sub|code|span|mark|small)\b[^>]*>", re.IGNORECASE)


def prose_only(html_content_value):
    """An article's HTML without the blocks that are not running text."""
    text = NOT_PROSE_PATTERN.sub(" ", html_content_value)
    text = FOOTNOTE_MARK_PATTERN.sub("", text)
    return INLINE_TAG_PATTERN.sub("", text)


def asset_version(*names):
    """
    A short fingerprint of a public CSS or JavaScript file, for its address.

    The pages link "/style.css?v=..." instead of "/style.css": when the file
    changes, so does the address, and a browser holding the old stylesheet in
    its cache fetches the new one instead of showing the new page with the
    old look. nginx serves these files with a long cache lifetime, which is
    right as long as the address changes with the content.
    """
    digest = hashlib.sha256()
    for name in names:
        if render.static_exists(name):
            digest.update(render.read_static(name).encode("utf-8"))
    return "?v=" + digest.hexdigest()[:10]


def compute_reading_time(html_content_value, language="it"):
    """
    Estimate the reading time of an article by counting the words.
    It assumes an average reading speed of 200 words per minute.
    Return a string ready to be shown (e.g. "3 min read").
    """
    text = plain_text(html_content_value)
    if text == "":
        word_count = 0
    else:
        word_count = len(text.split())

    # 200 words per minute is a common average for reading.
    minutes = word_count // 200
    if minutes < 1:
        minutes = 1

    if language == "en":
        return str(minutes) + " min read"
    return str(minutes) + " min di lettura"


# ---------------------------------------------------------------------------
# SHARED HEAD AND CHROME
# ---------------------------------------------------------------------------

def generate_favicon_svg():
    """
    Generate an SVG favicon with the initial of the site title on a
    gradient background (the same blue-purple as the design). No binary
    files, no external tools: it is just SVG text.
    """
    title_value = CONFIG.get("site_title", "P").strip()
    if title_value == "":
        initial = "P"
    else:
        initial = title_value[0].upper()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0066cc"/>
      <stop offset="1" stop-color="#5b3df5"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <text x="32" y="44" font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
        font-size="36" font-weight="700" fill="#ffffff"
        text-anchor="middle">{esc(initial)}</text>
</svg>
"""


def favicon_link():
    """
    Return the favicon <link> tag for the pages' head.
    It uses the custom one from the config if set, otherwise the one
    generated automatically at build time (favicon.svg).
    """
    custom_value = seo_data().get("favicon", "")
    if custom_value != "":
        return f'<link rel="icon" href="{esc(custom_value)}">'
    return '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'


def analytics_snippet():
    """
    Return the analytics snippets for the public pages, or an empty string
    when nothing is configured. Two services are supported, independently:

    - Google Analytics 4: "analytics_id" in config.json (e.g. "G-XXXXXXXXXX").
    - Umami (self-hosted): "umami_url" (the base URL of your Umami
      instance) and "umami_website_id" (the website UUID shown by Umami).
      Umami sets no cookies, so it needs no consent banner.

    The snippets are only injected into the PUBLIC pages: the private
    editor is not tracked. Every value crosses HTML and JS, so each one
    is validated against the characters it can legitimately contain,
    to rule out injection from a hand-edited config file.
    """
    parts = []

    # Google Analytics sets cookies, so with the consent banner switched on
    # it waits, inert, until the visitor accepts the statistics. Umami sets
    # none and is left alone.
    measurement_id = str(CONFIG.get("analytics_id", "")).strip()
    if measurement_id != "":
        if re.fullmatch(r"[A-Za-z0-9-]+", measurement_id) is not None:
            parts.append(wrap_for_consent(
                '<script async src="https://www.googletagmanager.com/gtag/js?id='
                + measurement_id + '"></script>\n'
                '  <script>\n'
                '    window.dataLayer = window.dataLayer || [];\n'
                '    function gtag(){dataLayer.push(arguments);}\n'
                "    gtag('js', new Date());\n"
                "    gtag('config', '" + measurement_id + "');\n"
                '  </script>', "statistics"))

    umami_url = str(CONFIG.get("umami_url", "")).strip().rstrip("/")
    umami_id = str(CONFIG.get("umami_website_id", "")).strip()
    if umami_url != "" and umami_id != "":
        url_valid = re.fullmatch(r"https?://[A-Za-z0-9.:_/-]+", umami_url) is not None
        id_valid = re.fullmatch(r"[A-Fa-f0-9-]+", umami_id) is not None
        if url_valid and id_valid:
            parts.append(
                '<script defer src="' + esc(umami_url) + '/script.js" '
                'data-website-id="' + esc(umami_id) + '"></script>')

    return "\n  ".join(parts)


# ---------------------------------------------------------------------------
# CUSTOM CODE
# ---------------------------------------------------------------------------

# The page the author uses to choose a point for a piece of code is the real
# page, generated on the spot, but without the code itself: an advertisement
# or a tracker has no business running in the administration. The switch is
# per thread, so the pages the server builds meanwhile are not affected.
CODE_SWITCH = threading.local()


def code_suppressed():
    """Tell whether the page being generated leaves out every custom code."""
    return getattr(CODE_SWITCH, "off", False) is True


def custom_code_list():
    """
    Return the custom code snippets of the configuration, skipping anything
    malformed. A hand-edited config.json is the only way to get a snippet
    that is not a dictionary here, and one bad entry should not stop a build.
    """
    if code_suppressed():
        return []
    snippets = CONFIG.get("custom_code", [])
    if not isinstance(snippets, list):
        return []
    return [s for s in snippets if isinstance(s, dict)]


def article_snippet_ids(art):
    """The ids of the snippets ticked on an article, as a tuple of strings."""
    ids = art.get("custom_code_ids", [])
    if not isinstance(ids, list):
        return ()
    return tuple(str(x) for x in ids)


def article_off_ids(art):
    """
    The ids of the site-wide snippets switched off on one article.

    "Every article" is right for an analytics tag and wrong, now and then,
    for an advertisement on an article that should have none: the article
    can say no to a snippet without the snippet changing for the others.
    """
    ids = art.get("custom_code_off_ids", [])
    if not isinstance(ids, list):
        return ()
    return tuple(str(x) for x in ids)


def article_own_snippets(art):
    """The pieces of code written inside one article, for that article only."""
    if code_suppressed():
        return []
    own = art.get("custom_code", [])
    if not isinstance(own, list):
        return []
    return [snippet for snippet in own if isinstance(snippet, dict)]


def code_context(article):
    """
    What a page says about the custom code: the snippets it ticked, the ones
    it switched off and the ones of its own.

    The callers pass the article itself, or - the homepage, the old tests -
    just a tuple of ticked ids.
    """
    if isinstance(article, dict):
        return article_snippet_ids(article), article_off_ids(article), article_own_snippets(article)
    if article is None:
        return (), (), []
    return tuple(article), (), []


# ---------------------------------------------------------------------------
# CONSENT
# ---------------------------------------------------------------------------
# Statistics and advertising code sets cookies, and in Europe it may only do
# so after the visitor agrees. Each snippet says which kind it is; with the
# banner switched on, the snippets that are not "necessary" reach the page as
# inert <template> elements, and site.js turns them into live code once the
# visitor accepts that category. Google's own tags are told the same through
# Consent Mode.

CONSENT_CATEGORIES = ("necessary", "statistics", "marketing")


def consent_settings(config=None):
    """
    The consent block of the configuration, with its defaults filled in.
    config is the configuration to read, the running one when omitted: the
    Settings page passes the one it has just loaded from disk.
    """
    if config is None:
        config = CONFIG
    value = config.get("consent", {})
    if not isinstance(value, dict):
        value = {}
    try:
        version = int(value.get("version", 1))
    except (ValueError, TypeError):
        version = 1
    return {
        "enabled": value.get("enabled", False) is True,
        "text": str(value.get("text", "") or ""),
        "text_en": str(value.get("text_en", "") or ""),
        "privacy_url": str(value.get("privacy_url", "") or "").strip(),
        "version": version,
    }


def consent_enabled():
    """Tell whether the code that needs consent has to wait for it."""
    return consent_settings()["enabled"]


def snippet_consent(snippet):
    """The consent category of a snippet: necessary, statistics or marketing."""
    value = snippet.get("consent", "necessary")
    if value not in CONSENT_CATEGORIES:
        return "necessary"
    return value


def wrap_for_consent(code, category):
    """
    The code itself, or the code held back until the visitor consents.

    A <template> is inert: its scripts do not run, its images and iframes do
    not load. It is allowed in the head as well as in the body, so the code
    waits in the very place it will run from.
    """
    if category == "necessary" or not consent_enabled():
        return code
    return '<template data-pb-consenso="' + category + '">' + code + "</template>"


def consent_categories_used(article=None):
    """The categories some code on the page needs consent for, in order."""
    used = set()
    if str(CONFIG.get("analytics_id", "")).strip() != "":
        used.add("statistics")
    for snippet in custom_code_list():
        if snippet.get("enabled", False) is True:
            used.add(snippet_consent(snippet))
    if isinstance(article, dict):
        for snippet in article_own_snippets(article):
            if snippet.get("enabled", True) is not False:
                used.add(snippet_consent(snippet))
    return [category for category in ("statistics", "marketing") if category in used]


def consent_default_script():
    """
    Google's Consent Mode defaults: everything denied until the visitor
    decides. It has to run before any Google tag, so it opens the head.
    """
    return ("<script>\n"
            "    window.dataLayer = window.dataLayer || [];\n"
            "    function gtag(){dataLayer.push(arguments);}\n"
            "    gtag('consent', 'default', {ad_storage: 'denied', ad_user_data: 'denied',\n"
            "      ad_personalization: 'denied', analytics_storage: 'denied', wait_for_update: 500});\n"
            "  </script>")


def consent_banner_html(language, categories):
    """The banner that asks for consent, with one switch per category in use."""
    settings = consent_settings()
    text = settings["text"]
    if language != main_language() and settings["text_en"] != "":
        text = settings["text_en"]
    if text == "":
        text = T("consenso_testo", language)
    privacy = ""
    if settings["privacy_url"] != "":
        privacy = (' <a href="' + esc(settings["privacy_url"]) + '">'
                   + T("consenso_privacy", language) + "</a>")
    switches = []
    for category in categories:
        switches.append(
            f'        <label class="consenso-voce"><input type="checkbox" data-categoria="{category}"> '
            f'<span><strong>{T("consenso_" + category, language)}</strong> '
            f'{T("consenso_" + category + "_hint", language)}</span></label>')
    return render.render(
        "public/consent_banner.html",
        titolo=T("consenso_titolo", language),
        testo=esc(text),
        privacy=privacy,
        label_necessari=T("consenso_necessary", language),
        hint_necessari=T("consenso_necessary_hint", language),
        voci="\n".join(switches),
        chiudi=esc(T("consenso_chiudi", language)),
        rifiuta=T("consenso_rifiuta", language),
        personalizza=T("consenso_personalizza", language),
        salva=T("consenso_salva", language),
        accetta=T("consenso_accetta", language),
    ).rstrip("\n")


# The scopes a snippet can have, in the order the Settings dropdown lists
# them. "home", "home_articles" and "home_optin" came first: a configuration
# written before the list grew keeps behaving exactly as it did.
SNIPPET_SCOPES = ("home", "articles", "home_articles",
                  "optin", "home_optin", "all")

# Where a snippet can be injected. The first three are positions in the HTML
# and exist on every page; the others are places in the visible layout, and a
# page that has no such place simply leaves the snippet out. "nav" is the
# header menu, next to Home, Articles, Archive and RSS: made for a link such as
# a chat widget's "Ask the assistant".
#
# The last four are the places an advertisement usually goes, and came with
# the two-column layout: the top of an article (after the title and the
# cover), its middle (between two paragraphs, half way down the text), the
# list of articles on the homepage (after the third one) and the sidebar.
SNIPPET_POSITIONS = ("head", "body_start", "body_end",
                     "after_header", "before_footer", "article_end", "nav",
                     "article_start", "article_middle", "home_feed", "sidebar",
                     "anchor")

# "anchor" is a point the author chose by clicking on the page itself: a CSS
# selector and whether the code goes before or after what it names. The
# page carries the code inert, and site.js moves it there and runs it.
ANCHOR_SIDES = ("before", "after")

def snippet_anchor(snippet):
    """
    The point chosen on the page, as (selector, side), or None when the
    snippet has none worth using. The selector is written by admin.js; a
    hand-edited one that could close the attribute is refused.
    """
    selector = snippet.get("anchor_selector", "")
    if not isinstance(selector, str):
        return None
    selector = selector.strip()
    if selector == "" or len(selector) > 400 or any(c in selector for c in "<\n\r"):
        return None
    side = snippet.get("anchor_where", "after")
    if side not in ANCHOR_SIDES:
        side = "after"
    return selector, side


def snippet_applies(snippet, page_kind, article_ids, off_ids=()):
    """
    Tell whether a snippet belongs on the page being generated.

    Each scope names the pages it wants: the homepage, the articles, both, or
    the whole site. "optin" and "home_optin" narrow the articles down to the
    ones that ticked the snippet while being written; off_ids are the ones an
    article switched off for itself.

    A snippet whose id is no longer anywhere in the configuration simply never
    matches, which is what makes deleting one safe: the articles that ticked
    it keep the dead id in their JSON and nothing goes wrong.
    """
    if snippet.get("enabled", False) is not True:
        return False
    if page_kind == "article" and str(snippet.get("id", "")) in off_ids:
        return False
    scope = snippet.get("scope", "home")
    if scope not in SNIPPET_SCOPES:
        # A scope typed by hand into config.json that we do not recognise:
        # fall back to the default rather than letting the snippet vanish
        # from every page with no sign of why.
        scope = "home"
    if scope == "all":
        return True
    if page_kind == "home":
        return scope in ("home", "home_articles", "home_optin")
    if page_kind == "article":
        if scope in ("articles", "home_articles"):
            return True
        if scope in ("optin", "home_optin"):
            return snippet.get("id", "") in article_ids
    return False


def snippet_position(snippet):
    """Where a snippet goes, with an unknown position read as the head."""
    where = snippet.get("position", "head")
    if where not in SNIPPET_POSITIONS:
        return "head"
    return where


def custom_code_block(position, page_kind, article=()):
    """
    Collect the snippets that go into one position of one page.

    article is the article being generated (or, for the other pages, a tuple
    of ticked ids): the site-wide snippets it switched off stay out, and the
    code written inside it goes in after them.

    The code is injected VERBATIM: escaping it would defeat the point. It is
    written by whoever can log into the editor, which is the same trust level
    as "home_content", already raw HTML. It never comes from a reader. Code
    that needs the visitor's consent arrives held back, see wrap_for_consent.
    """
    ticked, switched_off, own = code_context(article)
    if position == "anchor":
        return anchored_code_block(page_kind, article)
    parts = []
    for snippet in custom_code_list():
        if snippet_position(snippet) != position:
            continue
        if not snippet_applies(snippet, page_kind, ticked, switched_off):
            continue
        code = str(snippet.get("code", "")).strip()
        if code != "":
            parts.append(wrap_for_consent(code, snippet_consent(snippet)))
    if page_kind == "article":
        for snippet in own:
            if snippet.get("enabled", True) is False or snippet_position(snippet) != position:
                continue
            code = str(snippet.get("code", "")).strip()
            if code != "":
                parts.append(wrap_for_consent(code, snippet_consent(snippet)))
    return "\n".join(parts)


def anchored_code(snippet):
    """
    One snippet with a chosen point, held in a <template> that names the
    point. site.js moves it there; code that needs consent keeps waiting in
    its template, in the new place, exactly as it waits anywhere else.
    """
    anchor = snippet_anchor(snippet)
    code = str(snippet.get("code", "")).strip()
    if anchor is None or code == "":
        return ""
    selector, side = anchor
    category = snippet_consent(snippet)
    consent = ""
    if category != "necessary" and consent_enabled():
        consent = ' data-pb-consenso="' + category + '"'
    return (f'<template data-pb-ancora="{esc(selector)}" data-pb-dove="{side}"{consent}>'
            + code + "</template>")


def anchored_code_block(page_kind, article=()):
    """The snippets of a page that go to a point chosen on the page."""
    ticked, switched_off, own = code_context(article)
    parts = []
    for snippet in custom_code_list():
        if snippet_position(snippet) == "anchor" and snippet_applies(
                snippet, page_kind, ticked, switched_off):
            parts.append(anchored_code(snippet))
    if page_kind == "article":
        for snippet in own:
            if snippet.get("enabled", True) is not False and snippet_position(snippet) == "anchor":
                parts.append(anchored_code(snippet))
    return "\n".join(part for part in parts if part != "")


def person_jsonld():
    """
    Build the author's schema.org Person, enriched with the configured
    personal SEO data (url, photo, role, bio, social profiles).
    This data helps Google recognise the author as a real person
    (E-E-A-T signals) and connect their public profiles together.
    """
    seo = seo_data()
    person = {"@type": "Person", "name": CONFIG["author"]}
    if seo.get("author_url"):
        person["url"] = seo["author_url"]
    if seo.get("author_image"):
        person["image"] = seo["author_image"]
    if seo.get("author_role"):
        person["jobTitle"] = seo["author_role"]
    if seo.get("author_bio"):
        person["description"] = seo["author_bio"]
    profiles = seo.get("social_profiles", [])
    if isinstance(profiles, list) and len(profiles) > 0:
        person["sameAs"] = profiles
    return person


def social_meta(language="it"):
    """
    Social meta tags common to every page: site name (og:site_name),
    page language (og:locale) and the X/Twitter account if configured.
    """
    seo = seo_data()
    if language == "en":
        locale = "en_US"
    else:
        locale = "it_IT"
    lines = []
    if CONFIG["site_title"].strip() != "":
        lines.append(f'<meta property="og:site_name" content="{esc(CONFIG["site_title"])}">')
    lines.append(f'<meta property="og:locale" content="{locale}">')
    if seo.get("twitter_site"):
        lines.append(f'<meta name="twitter:site" content="{esc(seo["twitter_site"])}">')
    return "\n  ".join(lines)


def hreflang_links(path_it, path_en):
    """
    Generate the hreflang links that tell search engines which are the
    Italian and English versions of the same page. Without these links,
    Google may treat the two versions as duplicate content, or show the
    wrong language to users. x-default points to the main language.
    """
    base = CONFIG["base_url"].rstrip("/")
    url_it = base + path_it
    url_en = base + path_en
    if main_language() == "en":
        url_default = url_en
    else:
        url_default = url_it
    return (
        f'<link rel="alternate" hreflang="it" href="{url_it}">\n'
        f'  <link rel="alternate" hreflang="en" href="{url_en}">\n'
        f'  <link rel="alternate" hreflang="x-default" href="{url_default}">'
    )


def site_header(language="it", nav_extra="", is_home=False):
    """
    The header shared by every public page, with the language switcher.

    nav_extra is the custom code for the "nav" position: extra entries of the
    menu, after RSS and before the language switcher, so they sit with the
    other links and pick up their style.

    The name of the site is the <h1> of the homepage only. On every other
    page the h1 is the page's own title - an article, a tag, the archive -
    and a second one in the header told search engines the page had two
    main subjects.
    """
    prefix = language_url_prefix(language)

    # Language switcher in the navbar (top right, where users
    # look for it): a link to the other language's home, compact label.
    other_language = secondary_language()
    if language != main_language():
        other_language = main_language()

    # The labs are what a developer comes for: they have their place in the menu.
    if labs_online(language):
        nav_extra = (f'<a href="{labs_page_url(language)}">{T("labs", language)}</a>'
                     + ("\n      " + nav_extra.strip() if nav_extra.strip() else ""))
    # The page that says who writes is one click away from every page.
    if biography_published():
        nav_extra = (f'<a href="{biography_page_url(language)}">{T("chi_sono", language)}</a>'
                     + ("\n      " + nav_extra.strip() if nav_extra.strip() else ""))

    # The button that asks to get in touch closes the menu.
    work = work_link(language)
    if work is not None:
        nav_extra = ((nav_extra.strip() + "\n      " if nav_extra.strip() else "")
                     + f'<a class="nav-lavoro" href="{esc(work[0])}">{esc(work[1])}</a>')

    link_titolo = f'<a href="{prefix}/">{esc(CONFIG["site_title"])}</a>'
    if is_home:
        titolo_sito = '<h1 class="site-title">' + link_titolo + "</h1>"
    else:
        titolo_sito = '<p class="site-title">' + link_titolo + "</p>"

    return render.render(
        "public/header.html",
        salta_contenuto=T("salta_contenuto", language),
        url_home=prefix + "/",
        titolo_sito=titolo_sito,
        sottotitolo=esc(CONFIG["subtitle"]),
        label_menu=T("menu", language),
        aria_menu=esc(T("menu_principale", language)),
        label_home=T("home", language),
        label_articoli=T("articles", language),
        url_archivio=prefix + "/" + archive_file_name(language),
        label_archivio=T("archivio", language),
        url_feed=feed_url(language),
        voci_extra=("\n      " + nav_extra.strip()) if nav_extra.strip() else "",
        url_altra_lingua=language_url_prefix(other_language) + "/",
        altra_lingua=other_language,
        altra_lingua_label=other_language.upper(),
        altra_lingua_nome=esc(LANGUAGE_NAMES[other_language][other_language].capitalize()),
        title_rss=esc(T("rss_titolo", language)),
        aria_tema=esc(T("cambia_tema", language)),
        title_tema=esc(T("tema_chiaro_scuro", language)),
    ).rstrip("\n")


def site_footer(language="it", consent_active=False):
    """The footer shared by every public page."""
    prefix = language_url_prefix(language)

    # Configured social profiles: in the footer, for consistency with what
    # we declare to Google in the structured data (sameAs).
    link_social = social_profile_links()
    riga_social = ""
    if len(link_social) > 0:
        riga_social = ('\n    <p class="pie-social">'
                       + " &middot; ".join(link_social) + "</p>")

    return render.render(
        "public/footer.html",
        anno=datetime.now().year,
        autore=esc(CONFIG["author"]),
        url_archivio=prefix + "/" + archive_file_name(language),
        label_archivio=T("archivio", language),
        url_feed=feed_url(language),
        title_rss=esc(T("rss_titolo", language)),
        link_preferenze=consent_footer_link(language, consent_active),
        riga_social=riga_social,
    ).rstrip("\n")


def site_options(language, extra=None):
    """
    The values site.js needs, as a plain dictionary.

    Every public page gets one: the page language and the labels of the copy
    button on code blocks. The homepage adds the search settings on top. It
    travels as JSON, never as text concatenated into a script, so a translated
    label with an apostrophe cannot break the page.
    """
    options = {
        "language": language,
        # True on the pages of the translated language: they read the _en
        # fields of the search index, whichever language those are in.
        "secondary": language != main_language(),
        "copy_label": T("copia_codice", language),
        "copied_label": T("codice_copiato", language),
        "copy_title": T("copia_codice_titolo", language),
        "progress_label": T("progresso_lettura", language),
        "zoom_label": T("ingrandisci_immagine", language),
        "close_label": T("chiudi_immagine", language),
    }
    if extra is not None:
        options.update(extra)
    return options


def consent_footer_link(language, active):
    """
    The "cookie preferences" link of the footer: the way back to the banner
    for a visitor who wants to change the choice made.
    """
    if not active:
        return ""
    return (' &middot; <button type="button" class="link-preferenze" data-consenso="apri">'
            + T("consenso_preferenze", language) + "</button>")


def render_page(language, titolo_pagina, contenuto, meta_extra="",
                head_extra="", script_extra="", feed_links=None,
                site_extra=None, page_kind="other", article_ids=(),
                is_home=False, article=None):
    """
    Wrap a page body in the shared public layout (templates/base.html).

    titolo_pagina is inserted as-is: the caller has already escaped the parts
    that come from the configuration or from an article.

    page_kind ("home", "article" or "other") and the article (or, for the
    other pages, article_ids) are what the custom code snippets are matched
    against. A caller that passes neither gets only the snippets scoped to
    the whole site, which is right for the tag, archive, card and 404 pages:
    no other scope names them.
    """
    context = article_ids
    if article is not None:
        context = article

    # The consent banner, when it is switched on and some code on this page
    # needs it. PB_SITE tells site.js which categories to ask about.
    categories = []
    if consent_enabled():
        categories = consent_categories_used(article)
    if len(categories) > 0:
        if site_extra is None:
            site_extra = {}
        site_extra = dict(site_extra)
        site_extra["consent"] = {"version": consent_settings()["version"],
                                 "categories": categories}

    head_extra = block(head_extra) + (
        "  <script>window.PB_SITE = "
        + js(site_options(language, site_extra)) + ";</script>")

    # Custom code goes LAST in its position: in the head after PB_SITE, so a
    # snippet can read it, and at the end of the body after the scripts of
    # the page, so a snippet can use what they define.
    head_extra = block(head_extra) + custom_code_block("head", page_kind, context)
    script_extra = block(script_extra) + custom_code_block("body_end", page_kind, context)
    script_extra = block(script_extra) + custom_code_block("anchor", page_kind, context)
    body_open = custom_code_block("body_start", page_kind, context)
    if len(categories) > 0:
        script_extra = block(script_extra) + consent_banner_html(language, categories)

    # The visible slots of the shared layout. The ones inside the text and
    # the sidebar are filled by the pages that have such places.
    after_header = custom_code_block("after_header", page_kind, context)
    before_footer = custom_code_block("before_footer", page_kind, context)
    nav_extra = custom_code_block("nav", page_kind, context)
    if feed_links is None:
        feed_links = ('  <link rel="alternate" type="application/rss+xml" '
                      f'title="{esc(CONFIG["site_title"])}" href="{feed_url(language)}">\n')

    # Google's consent defaults have to run before any Google tag, the
    # analytics one included, so they go first.
    analytics = analytics_snippet()
    if len(categories) > 0:
        analytics = consent_default_script() + "\n  " + analytics
    return render.render(
        "base.html",
        lang=language,
        favicon=favicon_link(),
        analytics=analytics,
        titolo_pagina=titolo_pagina,
        meta_extra=block(meta_extra),
        feed_links=block(feed_links),
        head_extra=block(head_extra),
        body_open=block(body_open),
        header=site_header(language, nav_extra, is_home),
        after_header=block(after_header),
        contenuto=block(contenuto),
        before_footer=block(before_footer),
        footer=site_footer(language, len(categories) > 0),
        script_extra=block(script_extra),
        versione_css=asset_version("common.css", "style.css"),
        versione_js=asset_version("site.js"),
        tipo_pagina=page_kind,
    )



# ---------------------------------------------------------------------------
# COMMENTS
# ---------------------------------------------------------------------------

def comments_block(art, language=None):
    """
    Generate the comments snippet based on CONFIG["comments"].
    It supports "giscus", "disqus" or "none".

    The heading and the widget's own interface follow the language of the
    page: an English article used to get "Commenti" and an Italian Giscus.
    """
    if language is None:
        language = main_language()
    sistema = CONFIG.get("comments", "none")

    if sistema == "giscus":
        g = CONFIG["giscus"]
        return render.render(
            "public/comments_giscus.html",
            titolo=T("commenti", language),
            repo=esc(g["repo"]),
            repo_id=esc(g["repo_id"]),
            category=esc(g["category"]),
            category_id=esc(g["category_id"]),
            theme=esc(g["theme"]),
            lingua=esc(language),
        ).rstrip("\n")

    if sistema == "disqus":
        d = CONFIG["disqus"]
        # Disqus identifies each thread with a unique URL and identifier.
        # Both cross into JavaScript, so both go through json.dumps.
        page_url = f"{CONFIG['base_url']}/posts/{art['slug']}.html"
        embed_url = f"https://{d['shortname']}.disqus.com/embed.js"
        return render.render(
            "public/comments_disqus.html",
            titolo=T("commenti", language),
            noscript=T("commenti_disqus_noscript", language),
            page_url=js(page_url),
            identifier=js(art["slug"]),
            embed_url=js(embed_url),
        ).rstrip("\n")

    return ""  # "none": no comments


# ---------------------------------------------------------------------------
# TABLE OF CONTENTS, RELATED ARTICLES, AUTHOR BOX, ARTICLE NAV
# ---------------------------------------------------------------------------

# Headings with attributes must match too. The editor writes classes on them
# (<h2 class="ql-align-center">), and the old pattern, which only accepted a
# bare <h2>, silently skipped every heading the author had aligned or styled:
# those articles ended up with an incomplete table of contents, or none at all.
HEADING_PATTERN = re.compile(r"<(h[23])(\s[^>]*)?>(.*?)</h[23]>",
                             re.IGNORECASE | re.DOTALL)


def generate_table_of_contents(html_content_value, language="it"):
    """
    Generate the table of contents (TOC) of an article.
    It finds the h2 and h3 headings in the content, adds an id to each one
    for linking, and returns two things: the modified content (with the ids)
    and the HTML of the index. With fewer than 3 headings it generates no
    index (short articles do not need one).
    """
    titoli = HEADING_PATTERN.findall(html_content_value)
    if len(titoli) < 3:
        # Few headings: no index, content unchanged.
        return html_content_value, ""

    toc_items = []
    stato = {"counter": 0}

    def add_anchor(match):
        level = match.group(1)
        attributi = match.group(2)
        if attributi is None:
            attributi = ""
        heading_text = match.group(3)

        stato["counter"] = stato["counter"] + 1
        # We derive a readable id from the heading text.
        clean_text = plain_text(heading_text)
        ancora = slugify(clean_text)
        if ancora == "":
            ancora = "section"
        ancora = ancora + "-" + str(stato["counter"])

        # An id already on the heading would collide with ours: we replace it.
        attributi = re.sub(r'\s+id\s*=\s*"[^"]*"', "", attributi)

        item_class = "toc-h2"
        if level.lower() == "h3":
            item_class = "toc-h3"
        toc_items.append(
            f'<li class="{item_class}"><a href="#{ancora}">{esc(clean_text)}</a></li>')

        return f'<{level}{attributi} id="{ancora}">{heading_text}</{level}>'

    modified_content = HEADING_PATTERN.sub(add_anchor, html_content_value)

    # Only the list: the article page shows it twice, in the sidebar on a
    # wide screen and folded at the top of the text on a phone.
    index_html = '<ul class="toc-lista">' + "".join(toc_items) + "</ul>"
    return modified_content, index_html


def toc_sidebar_html(toc_list, language):
    """The table of contents as the last box of the article's sidebar."""
    return ('      <nav class="box box-indice" aria-label="' + esc(T("indice", language)) + '">\n'
            '        <h2 class="box-titolo">' + T("in_questo_articolo", language) + "</h2>\n"
            "        " + toc_list + "\n      </nav>")


def toc_phone_html(toc_list, language):
    """The table of contents folded at the top of the text, for narrow screens."""
    return ('        <details class="toc-telefono">\n'
            "          <summary>" + T("indice", language) + "</summary>\n"
            "          " + toc_list + "\n        </details>\n")


# Elements with no closing tag: they never open a level of nesting.
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "source", "track", "wbr"}


class _TopLevelBlocks(html.parser.HTMLParser):
    """Collects where each top-level element of a piece of HTML ends."""

    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_starts = [0]
        for index_value, character in enumerate(text):
            if character == "\n":
                self.line_starts.append(index_value + 1)
        self.depth = 0
        self.ends = []

    def _offset(self):
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.depth = self.depth + 1

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        self.depth = max(0, self.depth - 1)
        if self.depth == 0:
            close = self.text.find(">", self._offset())
            if close != -1:
                self.ends.append((close + 1, tag))


def insert_in_middle(content, code):
    """
    Put a piece of HTML half way down an article, between two paragraphs.

    The content is a flat run of blocks - paragraphs, headings, lists,
    tables - and the code goes after the paragraph nearest the middle, never
    between a heading and its first paragraph. An article too short to have
    a middle gets the code at the end of the text instead, so it is not lost.
    """
    if code == "":
        return content
    parser = _TopLevelBlocks(content)
    try:
        parser.feed(content)
        parser.close()
    except Exception:
        return content + code
    paragraph_ends = [end for end, tag in parser.ends if tag == "p"]
    if len(parser.ends) < 4 or len(paragraph_ends) == 0:
        return content + code
    middle = len(content) / 2
    # Not after the very last block: that would be the end, not the middle.
    candidates = [end for end in paragraph_ends if end < parser.ends[-1][0]]
    if len(candidates) == 0:
        return content + code
    best = min(candidates, key=lambda end: abs(end - middle))
    return content[:best] + code + content[best:]


def find_related_articles(article, all_articles, maximum=3):
    """
    Find the articles related to the given one, i.e. those sharing at least
    one tag. Return at most 'maximum' articles, sorted by the number of tags
    in common (more tags in common = more related).
    """
    article_tags = set(extract_article_tags(article))
    if len(article_tags) == 0:
        return []

    candidates = []
    for altro in all_articles:
        # We skip the article itself and the drafts.
        if altro["slug"] == article["slug"]:
            continue
        if altro.get("status") != "published":
            continue
        other_tags = set(extract_article_tags(altro))
        comuni = article_tags.intersection(other_tags)
        common_count = len(comuni)
        if common_count > 0:
            candidates.append((common_count, altro))

    # We sort by number of tags in common, highest first.
    candidates.sort(key=lambda coppia: coppia[0], reverse=True)

    result = []
    for common_count, altro in candidates:
        result.append(altro)
        if len(result) >= maximum:
            break
    return result


def article_has_page_in(art, language):
    """
    Tell whether an article has a real page in a language. In the main
    language every published article does; in the secondary one only those
    whose translation has been confirmed and is not empty.
    """
    if language == main_language():
        return True
    if not art.get("translation_confirmed", False):
        return False
    return not html_content_is_empty(art.get("content_en", ""))


def title_in_language(art, language):
    """The article title in a language, falling back to the main one."""
    if language == main_language():
        return art.get("title", "")
    translated = art.get("title_en", "")
    if translated != "":
        return translated
    return art.get("title", "")


def generate_related_block(article, all_articles, language="it"):
    """
    Generate the HTML of the 'Related articles' block to put at the bottom.

    The links used to be hardcoded to /posts/, with the Italian title, on
    every page: on an English page they therefore pointed at the Italian
    article and showed its Italian title. Now the prefix follows the page
    language, only articles that really have a page in that language are
    listed, and the title is the translated one.
    """
    related = find_related_articles(article, all_articles)

    visibili = []
    for art in related:
        if article_has_page_in(art, language):
            visibili.append(art)
    if len(visibili) == 0:
        return ""

    # The same rows as the homepage: thumbnail, title, date, the opening of
    # the text. They used to be bare cards whose date, title and link sat
    # side by side on one line.
    feed_items = [article_row(art, language) for art in visibili]
    return render.render(
        "public/related.html",
        titolo_sezione=T("articoli_correlati", language),
        lista="\n".join(feed_items),
    ).rstrip("\n")


def generate_author_box(language="it"):
    """
    Generate the "Written by" box shown at the bottom of every article,
    with photo, name, role, short bio and links to the author's social
    profiles. It uses the data of the "SEO and author data" section of
    the Settings. If nothing but the name is configured, the box is not
    shown (a half-empty box makes the page worse, not better).
    """
    seo = seo_data()
    role = seo.get("author_role", "")
    bio = seo.get("author_bio", "")
    photo = seo.get("author_image", "")
    profiles = seo.get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    if role == "" and bio == "" and photo == "" and len(profiles) == 0:
        return ""

    name_value = esc(CONFIG["author"])
    author_url_value = seo.get("author_url", "")
    if author_url_value != "":
        name_html = f'<a href="{esc(author_url_value)}">{name_value}</a>'
    else:
        name_html = name_value

    photo_block = ""
    if photo != "":
        photo_block = (f'<img class="author-box-photo" src="{esc(photo)}" '
                       f'alt="{name_value}" loading="lazy">')

    role_row = ""
    if role != "":
        role_row = f'<p class="author-box-role">{esc(role)}</p>'

    bio_row = ""
    if bio != "":
        bio_row = f'<p class="author-box-bio">{esc(bio)}</p>'

    link_social = social_profile_links()
    social_row = ""
    if len(link_social) > 0:
        social_row = ('<p class="author-box-social">'
                      + " &middot; ".join(link_social) + "</p>")

    return render.render(
        "public/author_box.html",
        foto=photo_block,
        scritto_da=T("scritto_da", language),
        nome=name_html,
        ruolo=role_row,
        bio=bio_row,
        social=social_row,
    )


def share_row(page_url, language="it"):
    """
    The button at the end of an article that copies its address, for the
    reader who wants to pass it on. Posting the article on LinkedIn, Hacker
    News and the like is the author's job, done from the editor.
    """
    if CONFIG.get("share_buttons", True) is not True:
        return ""
    return ('        <div class="condividi">\n'
            f'          <button type="button" class="condividi-copia" data-url="{esc(page_url)}" '
            f'data-fatto="{esc(T("condividi_copiato", language))}">'
            f'{T("condividi_copia", language)}</button>\n'
            "        </div>\n")


def work_settings(config=None):
    """The "work with me" block of the configuration, every value checked."""
    if config is None:
        config = CONFIG
    value = config.get("work_with_me", {})
    if not isinstance(value, dict):
        value = {}
    return {
        "enabled": value.get("enabled", False) is True,
        "url": text_setting(value.get("url", "")),
        "label": text_setting(value.get("label", "")),
        "label_en": text_setting(value.get("label_en", "")),
        "text": text_setting(value.get("text", "")),
        "text_en": text_setting(value.get("text_en", "")),
    }


def work_link(language):
    """
    Where "work with me" leads and what the button and the invitation say
    in a language: (address, label, sentence), or None when it is off or
    has nowhere safe to lead. A page of the site gets the language prefix.
    """
    work = work_settings()
    link = safe_link(work["url"])
    if not work["enabled"] or link == "":
        return None
    if link.startswith("/") and not link.startswith("//"):
        link = language_url_prefix(language) + link
    label = work["label"]
    text = work["text"]
    if language != main_language():
        label = work["label_en"]
        text = work["text_en"]
    return link, label or T("lavora_con_me", language), text or T("lavora_invito", language)


def work_invitation(language="it"):
    """The invitation at the end of an article: one sentence and the button."""
    work = work_link(language)
    if work is None:
        return ""
    link, label, text = work
    return ('        <aside class="invito-lavoro">\n'
            f'          <p>{esc(text)}</p>\n'
            f'          <a class="invito-pulsante" href="{esc(link)}">{esc(label)} &rarr;</a>\n'
            "        </aside>\n")


def original_address(art):
    """The address an article was first published at, or "" when it is not a web address."""
    link = safe_link(art.get("original_url", ""))
    if link.lower().startswith(("http://", "https://")):
        return link
    return ""


def original_note(art, language="it"):
    """
    The line under the title of an article that came out somewhere else
    first: the name of that site, taken from the address, and the link.
    """
    link = original_address(art)
    if link == "":
        return ""
    site = link.split("//", 1)[1].split("/", 1)[0]
    if site.lower().startswith("www."):
        site = site[4:]
    return (f'        <p class="pubblicato-origine">{T("pubblicato_in_origine", language)} '
            f'<a href="{esc(link)}" rel="noopener">{esc(site)}</a></p>\n')


def is_lab(art):
    """Tell whether an article is a lab."""
    return art.get("kind") == "lab"


def labs_page_url(language):
    """The address of the page that lists the labs."""
    return language_url_prefix(language) + "/labs.html"


# Whether the site has labs online, per language: the menu of every page
# needs to know, and build() says so once instead of each page asking the disk.
LABS_ONLINE = {}


def note_labs(articles):
    """Record, for the menu, in which languages at least one lab is online."""
    for language in (main_language(), secondary_language()):
        LABS_ONLINE[language] = any(
            is_lab(art) for art in articles_visible_in_language(articles, language))


def labs_online(language):
    """Tell whether the Labs page exists in a language."""
    if language not in LABS_ONLINE:
        note_labs([a for a in load_articles() if a.get("status") == "published"])
    return LABS_ONLINE.get(language, False)


def repository_link(art, language):
    """The link to the code of a lab, or "" when it has none worth a link."""
    link = safe_link(art.get("repo_url", ""))
    if not link.lower().startswith(("http://", "https://")):
        return ""
    label = T("lab_codice", language)
    if "github.com" in link.lower():
        label = T("lab_codice_github", language)
    return f'<a class="lab-codice" href="{esc(link)}" rel="noopener">{label} &rarr;</a>'


def starting_article(art, all_articles, language):
    """
    The article a lab or a practical version starts from, when it has a
    page in this language; None for a plain article or a missing one.
    """
    if art.get("kind") not in ("lab", "practical") or all_articles is None:
        return None
    for other in articles_visible_in_language(all_articles, language):
        if other.get("slug") == art.get("lab_of") and other.get("slug") != art.get("slug"):
            return other
    return None


def lab_box(art, all_articles, language="it"):
    """
    The box that opens a lab or a practical version. A lab says where its
    code is and what it is built with - a developer decides in the first
    seconds whether there is something to run, so the link comes first -
    and both say which article they start from.
    """
    start = starting_article(art, all_articles, language)
    start_link = ""
    if start is not None:
        start_link = (f'<a href="{article_url(start, language)}">'
                      f'{esc(title_in_language(start, language))}</a>')
    if art.get("kind") == "practical":
        rows = [f'          <p class="lab-etichetta">{T("livello_pratica", language)}</p>']
        if start_link != "":
            rows.append(f'          <p>{T("pratica_intro", language)} {start_link}</p>')
    elif is_lab(art):
        rows = [f'          <p class="lab-etichetta">{T("lab", language)}</p>']
        link = repository_link(art, language)
        if link != "":
            rows.append("          <p>" + link + "</p>")
        stack = str(art.get("stack", "") or "").strip()
        if stack != "":
            rows.append(f'          <p>{T("lab_fatto_con", language)}: {esc(stack)}</p>')
        steps = str(art.get("run_steps", "") or "").strip()
        if steps != "":
            rows.append(f'          <p>{T("lab_per_eseguirlo", language)}:</p>\n'
                        f'<pre class="ql-syntax" spellcheck="false">{esc(steps)}</pre>')
        if start_link != "":
            rows.append(f'          <p>{T("lab_mette_in_pratica", language)}: {start_link}</p>')
    else:
        return ""
    return ('        <aside class="lab-box">\n' + "\n".join(rows) + "\n        </aside>\n")


def other_levels(art, all_articles, language="it"):
    """
    At the end of an article, the other articles on the same subject: the
    idea, its practical version, its labs. Each of the three leads to the
    other two, so a reader who came for one level finds the others.
    """
    if all_articles is None:
        return ""
    root = starting_article(art, all_articles, language)
    if root is None:
        if art.get("kind") in ("lab", "practical"):
            return ""
        root = art
    labels = {"": "livello_idea", "practical": "livello_pratica", "lab": "lab"}
    group = [root] + [other for other in articles_visible_in_language(all_articles, language)
                      if other.get("kind") in ("lab", "practical")
                      and other.get("lab_of") == root.get("slug")
                      and other.get("slug") != root.get("slug")]
    # The idea first, then the practical version, then the labs.
    group.sort(key=lambda other: ("", "practical", "lab").index(other.get("kind") or ""))
    rows = []
    for other in group:
        if other.get("slug") == art.get("slug"):
            continue
        row = (f'<span class="lab-etichetta">{T(labels[other.get("kind") or ""], language)}</span> '
               f'<a href="{article_url(other, language)}">'
               f'{esc(title_in_language(other, language))}</a>')
        if is_lab(other) and repository_link(other, language) != "":
            row = row + " &middot; " + repository_link(other, language)
        rows.append("            <li>" + row + "</li>")
    if len(rows) == 0:
        return ""
    return ('        <aside class="lab-box lab-fine">\n'
            f'          <p>{T("livelli_titolo", language)}</p>\n'
            "          <ul>\n" + "\n".join(rows) + "\n          </ul>\n        </aside>\n")


def generate_labs_page(articles, language="it"):
    """The page of the labs: every lab online, newest first, as on the homepage."""
    prefix = language_url_prefix(language)
    labs = [art for art in articles_visible_in_language(articles, language) if is_lab(art)]
    principale = render.render(
        "public/labs.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_labs=T("labs", language),
        intro=T("labs_intro", language),
        lista="\n".join(article_row(art, language) for art in labs),
    )
    contenuto = two_columns(principale, build_sidebar(language, "other", articles), language)
    url_canonico = CONFIG["base_url"].rstrip("/") + labs_page_url(language)
    meta_extra = (f'  <meta name="description" content="{esc(T("labs_intro", language))}">\n'
                  f'  <link rel="canonical" href="{url_canonico}">')
    return render_page(language, with_site_title(T("labs", language)), contenuto,
                       meta_extra=meta_extra)


def series_of(art, all_articles, language):
    """
    The series an article is a part of, as it reads in a language: its slug,
    its name, the parts that have a page in that language (first to last)
    and the place of the article among them. None for an article on its own,
    or the only part published so far.
    """
    if all_articles is None:
        return None
    name = str(art.get("series", "") or "").strip()
    if name == "":
        return None
    slug = slugify(name)
    entry = collect_series(articles_visible_in_language(all_articles, language)).get(slug)
    if entry is None or len(entry["articles"]) < 2:
        return None
    for position, part in enumerate(entry["articles"]):
        if part.get("slug") == art.get("slug"):
            return {"slug": slug, "name": entry["name"], "parts": entry["articles"],
                    "position": position}
    return None


def series_page_url(slug, language):
    """The address of the page that lists a series."""
    return f"{language_url_prefix(language)}/serie/{slug}.html"


def series_box(art, all_articles, language="it"):
    """
    The box that opens an article of a series: which series, which part,
    and the list of all the parts. Whoever lands on part seven from a search
    engine has to see at once that six come before it.
    """
    series = series_of(art, all_articles, language)
    if series is None:
        return ""
    post_prefix = language_url_prefix(language) + "/posts/"
    rows = []
    for position, part in enumerate(series["parts"]):
        title = esc(title_in_language(part, language))
        if position == series["position"]:
            rows.append(f'            <li aria-current="page">{title}</li>')
        else:
            rows.append(f'            <li><a href="{post_prefix}{part["slug"]}.html">{title}</a></li>')
    place = T("serie_parte", language).replace("{n}", str(series["position"] + 1)) \
        .replace("{tot}", str(len(series["parts"])))
    return (
        f'        <nav class="serie-box" aria-label="{T("serie", language)}">\n'
        f'          <p><span class="serie-etichetta">{T("serie", language)}</span> '
        f'<a class="serie-nome" href="{series_page_url(series["slug"], language)}">'
        f'{esc(series["name"])}</a> &middot; {place}</p>\n'
        f'          <details>\n            <summary>{T("serie_tutte", language)}</summary>\n'
        f'            <ol>\n' + "\n".join(rows) + '\n            </ol>\n          </details>\n'
        '        </nav>\n')


def generate_series_page(slug, series, language="it", all_articles=None):
    """
    The page of a series: its parts from the first to the last, with the
    same rows as the homepage. In the secondary language only the translated
    parts are listed.
    """
    if all_articles is None:
        all_articles = series["articles"]
    prefix = language_url_prefix(language)
    visibili = articles_visible_in_language(series["articles"], language)
    rows = ["<li>\n" + article_row(art, language) + "\n</li>" for art in visibili]
    principale = render.render(
        "public/serie.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_serie=T("serie", language),
        nome_serie=esc(series["name"]),
        conteggio=len(visibili),
        label_conteggio=T("serie_conteggio", language),
        lista="\n".join(rows),
    )
    contenuto = two_columns(principale, build_sidebar(language, "other", all_articles),
                            language)
    url_canonico = CONFIG["base_url"].rstrip("/") + series_page_url(slug, language)
    meta_extra = (f'  <meta name="description" '
                  f'content="{T("serie_descrizione", language)} {esc(series["name"])}.">\n'
                  f'  <link rel="canonical" href="{url_canonico}">')
    return render_page(
        language,
        with_site_title(f'{T("serie", language)}: {esc(series["name"])}'),
        contenuto,
        meta_extra=meta_extra,
    )


def generate_article_nav(art, all_articles, language="it"):
    """
    Generate the navigation at the bottom of the article. A part of a series
    leads to the part before and the part after; any other article to the
    newer and the older one. The articles are already sorted newest first:
    the previous one in the list is the newer, the next one is the older.
    In the secondary language you only navigate between translated articles.
    """
    if all_articles is None:
        return ""
    series = series_of(art, all_articles, language)
    if series is not None:
        post_prefix = language_url_prefix(language) + "/posts/"
        blocks = []
        for step, label, css, arrow in ((-1, "serie_precedente", "", "&larr; {}"),
                                        (1, "serie_successiva", " article-nav-right", "{} &rarr;")):
            position = series["position"] + step
            if position < 0 or position >= len(series["parts"]):
                blocks.append('<span class="article-nav-empty"></span>')
                continue
            neighbor = series["parts"][position]
            blocks.append(
                f'<a class="article-nav-link{css}" href="{post_prefix}{neighbor["slug"]}.html">'
                f'<span class="article-nav-label">{arrow.format(T(label, language))}</span>'
                f'<span class="article-nav-title">{esc(title_in_language(neighbor, language))}</span></a>')
        return render.render("public/article_nav.html", precedente=blocks[0],
                             successivo=blocks[1])
    visibili = articles_visible_in_language(all_articles, language)
    posizione = -1
    for index_value in range(len(visibili)):
        if visibili[index_value].get("slug") == art.get("slug"):
            posizione = index_value
            break
    if posizione == -1:
        return ""

    post_prefix = language_url_prefix(language) + "/posts/"

    newer_block = '<span class="article-nav-empty"></span>'
    if posizione > 0:
        neighbor = visibili[posizione - 1]
        newer_block = (
            f'<a class="article-nav-link" href="{post_prefix}{neighbor["slug"]}.html">'
            f'<span class="article-nav-label">&larr; {T("nav_piu_recente", language)}</span>'
            f'<span class="article-nav-title">{esc(title_in_language(neighbor, language))}</span></a>')

    older_block = '<span class="article-nav-empty"></span>'
    if posizione < len(visibili) - 1:
        neighbor = visibili[posizione + 1]
        older_block = (
            f'<a class="article-nav-link article-nav-right" href="{post_prefix}{neighbor["slug"]}.html">'
            f'<span class="article-nav-label">{T("nav_meno_recente", language)} &rarr;</span>'
            f'<span class="article-nav-title">{esc(title_in_language(neighbor, language))}</span></a>')

    if posizione == 0 and len(visibili) == 1:
        return ""

    return render.render(
        "public/article_nav.html",
        precedente=newer_block,
        successivo=older_block,
    )


# ---------------------------------------------------------------------------
# THE TWO-COLUMN LAYOUT: ARTICLE ROWS, TOPICS, SIDEBAR, PAGINATION
# ---------------------------------------------------------------------------
# Every page but the 404 has the same frame: the content in a main column and
# a sidebar next to it (below it on a phone). The pieces of that frame are
# built here, so the homepage, the articles, the tags and the archive cannot
# drift apart.

def article_url(art, language):
    """Address of an article's page in a language, from the site root."""
    return language_url_prefix(language) + "/posts/" + art["slug"] + ".html"


def article_excerpt(art, language, words):
    """
    The text under the title in a list of articles.

    Priority: the preview the author wrote, then the opening of the article
    (its first words, cut at a word boundary), then the SEO description as a
    last resort.
    """
    title_value, description, content, preview = article_card_fields(art, language)
    if preview.strip() != "":
        return preview.strip()
    opening = excerpt_words(content, words)
    if opening != "":
        return opening
    return description


def article_tile_label(art):
    """The word on the tile shown when an article has no cover: its first tag."""
    tags = extract_article_tags(art)
    if len(tags) > 0:
        return tags[0]
    title_value = CONFIG.get("site_title", "").strip()
    if title_value == "":
        return "·"
    return title_value[0].upper()


def article_thumbnail(art):
    """
    The cover as a thumbnail, or a tile with the article's first tag.

    The tile keeps the rows aligned when some articles have a cover and some
    do not. The image has an empty alt: the title next to it says everything,
    and a screen reader would otherwise read the title twice.
    """
    image_url = media_url(art.get("image", ""))
    if image_url != "":
        return ('<img class="art-thumb-img" src="' + esc(image_url)
                + '" alt="" loading="lazy">')
    return '<span class="art-tile">' + esc(article_tile_label(art)) + "</span>"


def article_tags_line(art, language):
    """The tags of an article as links, for its row in a list."""
    prefix = language_url_prefix(language) + "/tag/"
    pieces = []
    for tag in extract_article_tags(art):
        tag_slug = slugify(tag)
        if tag_slug == "":
            continue
        pieces.append(f'<a class="art-tag" href="{prefix}{tag_slug}.html">#{esc(tag)}</a>')
    if len(pieces) == 0:
        return ""
    return '          <p class="art-tags">' + "".join(pieces) + "</p>\n"


def article_row(art, language, lead=False):
    """
    One article in a list: thumbnail, tags, title, date and reading time, and
    the opening of the text.

    The same markup serves the homepage, the tag pages, the related articles
    and - rebuilt by site.js - the search results. The whole row is clickable
    through the title link; the tags stay links of their own on top of it.
    The lead row (the most recent article on the first page) shows twice as
    many words and a "read" prompt.
    """
    title_value, description, content, preview = article_card_fields(art, language)
    words = excerpt_word_count()
    css_class = ""
    label = ""
    read = ""
    if lead:
        words = words * 2
        css_class = " art-lead"
        label = '          <p class="art-kicker">' + T("ultimo_articolo", language) + "</p>\n"
    if is_lab(art):
        label = '          <p class="art-kicker">' + T("lab", language) + "</p>\n"
    elif art.get("kind") == "practical":
        label = '          <p class="art-kicker">' + T("livello_pratica", language) + "</p>\n"
        read = ('          <span class="art-more" aria-hidden="true">'
                + T("leggi_articolo", language) + " &rarr;</span>\n")
    return render.render(
        "public/article_row.html",
        classe=css_class,
        url=article_url(art, language),
        miniatura=article_thumbnail(art),
        etichetta=label,
        tags=article_tags_line(art, language),
        titolo=esc(title_value),
        data=format_date(art["date"], language),
        tempo_lettura=compute_reading_time(content, language),
        estratto=esc(article_excerpt(art, language, words)),
        leggi=read,
    ).rstrip("\n")


def tag_counts(articles, language):
    """Every tag of the articles visible in a language, with how many use it."""
    counts = {}
    for art in articles_visible_in_language(articles, language):
        for tag in extract_article_tags(art):
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].lower()))


def topics_bar(articles, language, current_tag=""):
    """
    The row of topics under the header: the most used tags, with a count.

    It is the quickest way into the blog for a reader who came for one
    subject. On a phone it scrolls sideways instead of wrapping onto lines.
    """
    prefix = language_url_prefix(language) + "/tag/"
    items = []
    for tag, count in tag_counts(articles, language)[:12]:
        tag_slug = slugify(tag)
        if tag_slug == "":
            continue
        current = ""
        if tag == current_tag:
            current = ' aria-current="page"'
        items.append(f'      <a class="argomento" href="{prefix}{tag_slug}.html"{current}>'
                     f'{esc(tag)} <span class="argomento-conteggio">{count}</span></a>')
    if len(items) == 0:
        return ""
    return render.render("public/topics_bar.html", aria=esc(T("argomenti", language)),
                         voci="\n".join(items))


def sidebar_box(css_class, title, content):
    """One box of the sidebar. An empty title leaves the heading out."""
    titolo = ""
    if title != "":
        titolo = title
    html_box = render.render("public/sidebar_box.html", classe=css_class,
                             titolo=titolo, contenuto=block(content))
    if titolo == "":
        html_box = html_box.replace('        <h2 class="box-titolo"></h2>\n', "")
    return html_box


def author_initials(name):
    """Up to two initials of the author, for the avatar when there is no photo."""
    letters = [piece[0].upper() for piece in name.split() if piece]
    if len(letters) == 0:
        return "·"
    return "".join(letters[:2])


def avatar_html(css_class):
    """The author's photo, or their initials in a circle."""
    photo = seo_data().get("author_image", "")
    if photo != "":
        return f'<img class="{css_class}" src="{esc(photo)}" alt="" loading="lazy">'
    return (f'<span class="{css_class} avatar-iniziali" aria-hidden="true">'
            f'{esc(author_initials(CONFIG.get("author", "")))}</span>')


def profile_box(language):
    """
    The author in brief: photo or initials, name, role and bio.

    Shown on every page with a sidebar, except the homepage that has the
    full introduction in that place. A link to the author's own page is
    added when one is configured.
    """
    seo = seo_data()
    role = seo.get("author_role", "") or CONFIG.get("subtitle", "")
    lines = ['        <div class="profilo">' + avatar_html("profilo-foto")
             + '<div><p class="profilo-nome">' + esc(CONFIG.get("author", ""))
             + '</p><p class="profilo-ruolo">' + esc(role) + "</p></div></div>"]
    bio = seo.get("author_bio", "")
    if bio != "":
        lines.append('        <p class="profilo-bio">' + esc(bio) + "</p>")
    author_url = seo.get("author_url", "")
    if author_url != "":
        lines.append(f'        <p class="profilo-link"><a href="{esc(author_url)}" rel="me">'
                     f'{T("chi_sono", language)} &rarr;</a></p>')
    return sidebar_box("box-profilo", T("chi_scrive", language), "\n".join(lines))


def home_intro_html(language):
    """The free introduction of the homepage (home_content), or ""."""
    if language != main_language():
        home_content = CONFIG.get("home_content_en", "")
        # Without a translation, the introduction shows in the main language:
        # better than nothing at all.
        if html_content_is_empty(home_content):
            home_content = CONFIG.get("home_content", "")
    else:
        home_content = CONFIG.get("home_content", "")
    if html_content_is_empty(home_content):
        return ""
    avatar = ""
    if seo_data().get("author_image", "") != "":
        avatar = avatar_html("home-avatar") + "\n        "
    return render.render("public/home_intro.html", avatar=avatar,
                         contenuto_intro=add_lazy_loading(home_content)).rstrip("\n")


def home_intro_position():
    """Where the introduction goes: "sidebar" (default) or "top"."""
    if CONFIG.get("home_intro_position", "sidebar") == "top":
        return "top"
    return "sidebar"


def explore_box(language):
    """The editorial cards (biography, projects...) as links to their pages."""
    cards = published_home_cards()
    if len(cards) == 0:
        return ""
    prefix = language_url_prefix(language) + "/pagine/"
    items = []
    for card in cards:
        slug = card_slug(card.get("title", ""))
        items.append(f'          <li><a href="{prefix}{slug}.html">{esc(card.get("title", ""))}</a>'
                     f'<span class="esplora-estratto">{esc(excerpt_words(card.get("content", ""), 12))}'
                     "</span></li>")
    return sidebar_box("box-esplora", T("esplora", language),
                       '        <ul class="esplora-lista">\n' + "\n".join(items) + "\n        </ul>")


def topics_box(articles, language):
    """The tags as a cloud, for the pages that have no topics bar."""
    prefix = language_url_prefix(language) + "/tag/"
    pieces = []
    for tag, count in tag_counts(articles, language):
        tag_slug = slugify(tag)
        if tag_slug == "":
            continue
        pieces.append(f'<a class="argomento" href="{prefix}{tag_slug}.html">{esc(tag)} '
                      f'<span class="argomento-conteggio">{count}</span></a>')
    if len(pieces) == 0:
        return ""
    return sidebar_box("box-argomenti", T("argomenti", language),
                       '        <p class="nuvola">' + "".join(pieces) + "</p>")


def follow_box(language):
    """The feed of the page's language and the author's social profiles."""
    items = [f'          <li><a href="{feed_url(language)}">RSS</a></li>']
    for link in social_profile_links():
        items.append("          <li>" + link + "</li>")
    return sidebar_box("box-segui", T("seguimi", language),
                       '        <ul class="segui-lista">\n' + "\n".join(items) + "\n        </ul>")


def sidebar_ads(page_kind, article):
    """The custom code placed in the sidebar (an advertisement, a widget)."""
    code = custom_code_block("sidebar", page_kind, article)
    if code == "":
        return ""
    return '      <div class="annuncio annuncio-barra">\n' + code + "\n      </div>"


def build_sidebar(language, page_kind, articles, article=(), toc_html="",
                  intro="", biography="", projects=""):
    """
    The sidebar of a page.

    Homepage: the introduction (when it lives in the sidebar), the sidebar
    code, the cards, the follow links. Article: the author, the sidebar
    code, and the table of contents last, because it is the one that stays
    on screen while the article scrolls. Other pages: the author, the code,
    the cards, the topics and the follow links. The homepage can also hold
    the biography (after the introduction) and the projects (after the
    sidebar code), when the author put them there.
    """
    parts = []
    if intro != "":
        parts.append(sidebar_box("box-intro", "", intro))
    elif biography == "":
        parts.append(profile_box(language))
    parts.append(biography)
    parts.append(sidebar_ads(page_kind, article))
    parts.append(projects)
    parts.append(newsletter_sidebar_box(language))
    if page_kind == "article" and toc_html != "":
        parts.append(toc_html)
        return "\n".join(part for part in parts if part != "")
    parts.append(explore_box(language))
    if page_kind not in ("home",):
        parts.append(topics_box(articles, language))
    parts.append(follow_box(language))
    return "\n".join(part for part in parts if part != "")


def two_columns(principale, barra, language, argomenti="", main_has_id=True):
    """The main column and the sidebar, with the topics bar above them."""
    attributi = ""
    if main_has_id:
        attributi = ' id="content"'
    return render.render(
        "public/layout_colonne.html",
        argomenti=block(argomenti),
        attributi_main=attributi,
        principale=block(principale),
        aria_barra=esc(T("barra_laterale", language)),
        barra=block(barra),
    )


def pages_to_show(page, total):
    """The page numbers of the pagination: the first, the last, the current
    one and its neighbours, with None where numbers are skipped."""
    wanted = {1, total, page - 1, page, page + 1}
    numbers = sorted(n for n in wanted if 1 <= n <= total)
    result = []
    previous = 0
    for number in numbers:
        if number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return result


def pagination_html(page, total, language):
    """
    The navigation between the pages of the homepage, with the page numbers.

    It used to say only "newer" and "older": with numbers a reader sees how
    much there is, and can jump to the last page of the archive in one go.
    """
    if total <= 1:
        return ""
    prefix = language_url_prefix(language)
    folder = pagination_folder(language)

    def address(number):
        if number == 1:
            return prefix + "/"
        return f"{prefix}/{folder}/{number}.html"

    if page > 1:
        previous = (f'<a class="paginazione-freccia" href="{address(page - 1)}" rel="prev">'
                    f'{T("pagina_piu_recenti", language)}</a>')
    else:
        previous = '<span class="paginazione-vuoto"></span>'
    if page < total:
        following = (f'<a class="paginazione-freccia" href="{address(page + 1)}" rel="next">'
                     f'{T("pagina_meno_recenti", language)}</a>')
    else:
        following = '<span class="paginazione-vuoto"></span>'

    numbers = []
    for number in pages_to_show(page, total):
        if number is None:
            numbers.append('<span class="paginazione-salto">&hellip;</span>')
        elif number == page:
            numbers.append(f'<span class="paginazione-numero" aria-current="page">{number}</span>')
        else:
            numbers.append(f'<a class="paginazione-numero" href="{address(number)}">{number}</a>')
    return render.render(
        "public/pagination.html",
        aria=esc(T("pagine", language)),
        precedente=previous,
        numeri="".join(numbers),
        successiva=following,
    )


# ---------------------------------------------------------------------------
# ARTICLE PAGE
# ---------------------------------------------------------------------------

def generate_article_page(art, language="it", all_articles=None):
    """
    Generate the full HTML of a single article, with SEO and comments.
    The language parameter can be "it" or "en": in the secondary language it
    uses the translated fields and changes the addresses.
    """
    prefix = language_url_prefix(language)

    # We pick the right fields based on the requested language. The _en
    # fields hold the translation, whichever language that is: with English
    # as the main language they hold the Italian version. This used to test
    # for language == "en" and so, on an English site, served the Italian
    # translation at the root while the homepage listed the English title.
    if language != main_language():
        title_value = art.get("title_en", "")
        content = art.get("content_en", "")
        description = art.get("description_en", "")
    else:
        title_value = art.get("title", "")
        content = art.get("content", "")
        description = art.get("description", "")
    # If the SEO description is missing, we derive one from the content:
    # a real excerpt of the text is better than repeating the title.
    if description == "":
        description = excerpt_from_html(content, 155)
    if description == "":
        description = title_value

    page_url = f"{CONFIG['base_url']}{prefix}/posts/{art['slug']}.html"
    back_label = "&larr; " + T("tutti_articoli", language)
    reading_time = compute_reading_time(content, language)

    tags_html = ""
    if art.get("tags"):
        # Tag links use the prefix of the current language.
        tag_prefix = prefix + "/tag/"
        pieces = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                tag_slug = slugify(t)
                pieces.append(f'<a class="tag" href="{tag_prefix}{tag_slug}.html">#{esc(t)}</a>')
        if len(pieces) > 0:
            tags_html = " &middot; " + " ".join(pieces)

    # We generate the table of contents (only for long articles).
    # The function adds the ids to the headings and gives us back the index to show.
    content, toc_list = generate_table_of_contents(content, language)
    content = add_lazy_loading(content)
    toc_sidebar = ""
    toc_phone = ""
    if toc_list != "":
        toc_sidebar = toc_sidebar_html(toc_list, language)
        toc_phone = toc_phone_html(toc_list, language)

    # The custom code that lives inside the text: at the top, after the
    # title and the cover, and half way down, between two paragraphs.
    start_code = custom_code_block("article_start", "article", art)
    if start_code != "":
        start_code = ('        <div class="annuncio annuncio-testo">\n' + start_code
                      + "\n        </div>\n")
    middle_code = custom_code_block("article_middle", "article", art)
    if middle_code != "":
        content = insert_in_middle(
            content, '<div class="annuncio annuncio-testo">' + middle_code + "</div>")

    # The cover inside the article, under the title and the date.
    #
    # It sits AFTER the heading and the metadata, never above them: a cover is
    # usually decorative, and putting it first would push the opening line of
    # the article off the first screen on a phone. Its height is capped for
    # the same reason. Because that cap crops the image, a click opens it full
    # size - which is also why the same click does nothing on the homepage,
    # where the picture sits inside the link to the article.
    cover_block = ""
    if CONFIG.get("article_cover", True) is True:
        cover_url = media_url(art.get("image", ""))
        if cover_url != "":
            cover_block = render.render(
                "public/article_cover.html",
                url=esc(cover_url),
                alt=esc(title_value),
                titolo_zoom=esc(T("ingrandisci_immagine", language)),
            )

    # "Related articles" block (in both languages).
    related_block = ""
    if all_articles is not None:
        related_block = generate_related_block(art, all_articles, language)

    og_image = ""
    if art.get("image"):
        og_image = (f'  <meta property="og:image" content="{esc(shared_url(art["image"]))}">\n'
                    '  <meta name="twitter:card" content="summary_large_image">')

    # Meta keywords from the article tags (a light SEO help).
    meta_keywords = ""
    if art.get("tags"):
        clean_tags = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                clean_tags.append(t)
        if len(clean_tags) > 0:
            meta_keywords = f'  <meta name="keywords" content="{esc(", ".join(clean_tags))}">'

    # Language switcher: it appears only if a confirmed translation exists.
    language_switcher = ""
    translation_ready = art.get("translation_confirmed", False)
    if translation_ready and not html_content_is_empty(art.get("content_en", "")):
        # We build the links to the two versions using the dynamic prefixes.
        link_it = f'{language_url_prefix("it")}/posts/{art["slug"]}.html'
        link_en = f'{language_url_prefix("en")}/posts/{art["slug"]}.html'
        if language == "en":
            language_switcher = (
                f'<div class="language-switcher">'
                f'<a href="{link_it}">Italiano</a>'
                f'<span class="lingua-attiva">English</span>'
                f'</div>'
            )
        else:
            language_switcher = (
                f'<div class="language-switcher">'
                f'<span class="lingua-attiva">Italiano</span>'
                f'<a href="{link_en}">English</a>'
                f'</div>'
            )

    # hreflang links: only if both versions really exist.
    link_hreflang = ""
    if translation_ready and not html_content_is_empty(art.get("content_en", "")):
        path_it = language_url_prefix("it") + f"/posts/{art['slug']}.html"
        path_en = language_url_prefix("en") + f"/posts/{art['slug']}.html"
        link_hreflang = "  " + hreflang_links(path_it, path_en)

    # JSON-LD structured data for Google (rich results).
    # Enriched with image and keywords (tags) when available.
    # The author uses the full Person schema (url, photo, role, sameAs):
    # this is the "personal data" that strengthens Google's E-E-A-T signals.
    publisher = {"@type": "Organization", "name": CONFIG["site_title"]}
    site_logo = seo_data().get("logo", "")
    if site_logo != "":
        publisher["logo"] = {"@type": "ImageObject", "url": site_logo}
    jsonld_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title_value,
        "description": description,
        "author": person_jsonld(),
        "datePublished": art["date"],
        "dateModified": art.get("date_modified", art["date"]),
        "url": page_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "inLanguage": language,
        "publisher": publisher,
    }
    if art.get("image"):
        jsonld_data["image"] = shared_url(art["image"])
    if art.get("tags"):
        # The tags become the article's keywords.
        keywords = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                keywords.append(t)
        if len(keywords) > 0:
            jsonld_data["keywords"] = ", ".join(keywords)

    # An article republished as it is says where the original lives, so the
    # two sites do not compete for the same text.
    canonical_url = page_url
    if art.get("original_canonical") is True and original_address(art) != "":
        canonical_url = original_address(art)
    meta_extra = "\n".join(x for x in [
        f'  <meta name="description" content="{esc(description)}">',
        f'  <meta name="author" content="{esc(CONFIG["author"])}">',
        f'  <link rel="canonical" href="{esc(canonical_url)}">',
        link_hreflang,
        f'  <meta property="og:title" content="{esc(title_value)}">',
        f'  <meta property="og:description" content="{esc(description)}">',
        '  <meta property="og:type" content="article">',
        f'  <meta property="og:url" content="{page_url}">',
        f'  <meta property="article:published_time" content="{art["date"]}">',
        f'  <meta property="article:author" content="{esc(CONFIG["author"])}">',
        "  " + social_meta(language),
        meta_keywords,
        og_image,
    ] if x != "")

    head_extra = (
        '  <link id="hljs-tema" rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">\n'
        '  <script type="application/ld+json">'
        + json.dumps(jsonld_data, ensure_ascii=False) + "</script>")

    principale = render.render(
        "public/article.html",
        language_switcher=language_switcher,
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=esc(title_value),
        data=format_date(art["date"], language),
        tempo_lettura=reading_time,
        tags_html=tags_html,
        originale=original_note(art, language),
        copertina=block(cover_block),
        serie=series_box(art, all_articles, language) + lab_box(art, all_articles, language),
        codice_inizio_testo=start_code,
        toc_telefono=toc_phone,
        contenuto_articolo=content,
        codice_fine_testo=block(custom_code_block("article_end", "article", art)),
        author_box=(share_row(page_url, language)
                    + other_levels(art, all_articles, language)
                    + work_invitation(language) + generate_author_box(language) + newsletter_after_article(language)),
        article_nav=generate_article_nav(art, all_articles, language),
        back_label=back_label,
        related=block(related_block),
        comments=block(comments_block(art, language)),
    )
    if all_articles is None:
        all_articles = [art]
    contenuto = two_columns(
        principale,
        build_sidebar(language, "article", all_articles, art, toc_html=toc_sidebar),
        language,
        main_has_id=False,
    )

    return render_page(
        language,
        with_site_title(f"{esc(title_value)}"),
        contenuto,
        meta_extra=meta_extra,
        head_extra=head_extra,
        script_extra='  <script src="https://cdn.jsdelivr.net/gh/highlightjs/'
                     'cdn-release@11.9.0/build/highlight.min.js"></script>',
        page_kind="article",
        article=art,
    )


# ---------------------------------------------------------------------------
# HOMEPAGE CARDS AND CARD PAGES
# ---------------------------------------------------------------------------

def home_featured_enabled():
    """Tell whether the homepage should highlight its most recent article."""
    return CONFIG.get("home_featured", True) is True


def home_cards_enabled():
    """Tell whether the homepage should show the block of editorial cards."""
    return CONFIG.get("home_cards_enabled", True) is True


def published_home_cards():
    """
    The cards that go online: the ones switched on, with something written
    in them, and only if the block itself is switched on.

    The homepage, the sitemap and the page writer all need the same list. Read
    separately in three places, they would sooner or later disagree, and a card
    left out of the homepage would still have its page and its sitemap entry.
    """
    if not home_cards_enabled():
        return []
    # A card named like the biography would write its page over the
    # biography's: while the biography is online, the biography wins.
    taken = ""
    if biography_published():
        taken = biography_slug()
    published = []
    for card in CONFIG.get("home_cards", []):
        if not card.get("active", False):
            continue
        if html_content_is_empty(card.get("content", "")):
            continue
        if taken != "" and card_slug(card.get("title", "")) == taken:
            continue
        published.append(card)
    return published


# ---------------------------------------------------------------------------
# BIOGRAPHY AND PROJECTS
# ---------------------------------------------------------------------------

# Where the biography and the projects can sit on the homepage.
HOME_POSITIONS = ("sidebar", "top", "bottom")


def home_position(value, default):
    """A position from the configuration, or the default when it is not one."""
    if value in HOME_POSITIONS:
        return value
    return default


def text_setting(value):
    """A text value of the configuration, whatever was saved in its place."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def safe_link(url):
    """
    An address fit for a link: http, https, mailto or a path on the site.
    Anything else - a javascript: address above all - becomes "".
    """
    url = text_setting(url)
    if url == "":
        return ""
    lowered = url.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "/", "#")):
        return url
    if ":" in url.split("/")[0]:
        return ""
    return url


def biography_settings(config=None):
    """
    The biography block of the configuration, with its defaults filled in.
    The form saves it as it is, so every value is checked here.
    """
    if config is None:
        config = CONFIG
    value = config.get("biography", {})
    if not isinstance(value, dict):
        value = {}
    return {
        "enabled": value.get("enabled", False) is True,
        "position": home_position(value.get("position"), "sidebar"),
        "photo": text_setting(value.get("photo", "")),
        "content": value.get("content", "") if isinstance(value.get("content"), str) else "",
        "content_en": value.get("content_en", "") if isinstance(value.get("content_en"), str) else "",
    }


def biography_published():
    """The biography goes online when it is switched on and has a text."""
    bio = biography_settings()
    return bio["enabled"] and not html_content_is_empty(bio["content"])


def biography_slug():
    """The file name of the biography page, in the site's main language."""
    return card_slug(T("biografia", main_language()))


def biography_content(language):
    """The biography in a language, or in the main one when not translated."""
    bio = biography_settings()
    if language != main_language() and not html_content_is_empty(bio["content_en"]):
        return bio["content_en"]
    return bio["content"]


def biography_photo_html(css_class):
    """The photo of the biography, the author's one when it has none of its own."""
    photo = biography_settings()["photo"] or seo_data().get("author_image", "")
    if photo == "":
        return ""
    return (f'<img class="{css_class}" src="{esc(photo)}" '
            f'alt="{esc(CONFIG.get("author", ""))}" loading="lazy">')


def biography_page_url(language):
    """The address of the biography page in a language."""
    return f"{language_url_prefix(language)}/pagine/{biography_slug()}.html"


def biography_home_html(language):
    """
    The biography on the homepage: the photo, its first lines and the link to
    the whole of it. A box in the sidebar, a section in the main column.
    """
    photo = biography_photo_html("bio-foto")
    if photo != "":
        photo = photo + "\n          "
    # The sidebar is narrow: fewer words, or the box outgrows the others.
    words = 45
    if biography_settings()["position"] == "sidebar":
        words = 30
    inner = render.render(
        "public/biografia_breve.html",
        foto=photo,
        estratto=esc(excerpt_words(biography_content(language), words)),
        url_pagina=biography_page_url(language),
        leggi=T("leggi_biografia", language),
    )
    if biography_settings()["position"] == "sidebar":
        return sidebar_box("box-biografia", T("biografia", language), inner)
    return render.render("public/home_sezione.html", classe="home-biografia",
                         id_titolo="titolo-biografia", titolo=T("biografia", language),
                         contenuto=inner).rstrip("\n")


def projects_settings(config=None):
    """
    The projects block of the configuration, with its defaults filled in and
    every item checked: a project needs at least a name.
    """
    if config is None:
        config = CONFIG
    value = config.get("projects", {})
    if not isinstance(value, dict):
        value = {}
    items = []
    raw_items = value.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        items.append({
            "name": text_setting(item.get("name", "")),
            "description": text_setting(item.get("description", "")),
            "description_en": text_setting(item.get("description_en", "")),
            "url": text_setting(item.get("url", "")),
            "image": text_setting(item.get("image", "")),
            "visible": item.get("visible", True) is not False,
        })
    return {
        "enabled": value.get("enabled", False) is True,
        "position": home_position(value.get("position"), "top"),
        "items": items,
    }


def published_projects():
    """The projects that show: the block switched on, the item visible and named."""
    settings = projects_settings()
    if not settings["enabled"]:
        return []
    return [item for item in settings["items"] if item["visible"] and item["name"] != ""]


def projects_home_html(language):
    """The projects on the homepage: a grid in the main column, a list in the sidebar."""
    projects = published_projects()
    if len(projects) == 0:
        return ""
    rows = []
    for item in projects:
        name = esc(item["name"])
        link = safe_link(item["url"])
        if link != "":
            name = f'<a href="{esc(link)}">{name}</a>'
        image = ""
        if item["image"] != "":
            image = (f'<img class="progetto-immagine" src="{esc(item["image"])}" '
                     'alt="" loading="lazy">\n            ')
        description = item["description"]
        if language != main_language() and item["description_en"] != "":
            description = item["description_en"]
        if description != "":
            description = f'<p class="progetto-descrizione">{esc(description)}</p>\n          '
        rows.append(render.render("public/progetto.html", immagine=image, nome=name,
                                  descrizione=description).rstrip("\n"))
    if projects_settings()["position"] == "sidebar":
        return sidebar_box("box-progetti", T("progetti", language),
                           '        <ul class="progetti-lista">\n' + "\n".join(rows)
                           + "\n        </ul>")
    return render.render("public/home_sezione.html", classe="home-progetti",
                         id_titolo="titolo-progetti", titolo=T("progetti", language),
                         contenuto='        <ul class="progetti-griglia">\n' + "\n".join(rows)
                         + "\n        </ul>\n").rstrip("\n")


def newsletter_form(language, place):
    """The sign-up form of the newsletter; place keeps its ids unique."""
    current = newsletter.settings()
    text = current["text"] or T("nl_testo_default", language)
    privacy = ""
    privacy_url = consent_settings()["privacy_url"]
    if privacy_url != "":
        privacy = (f'          <p class="newsletter-privacy"><a href="{esc(privacy_url)}">'
                   f'{T("consenso_privacy", language)}</a></p>\n')
    return render.render(
        "public/newsletter_form.html",
        testo=esc(text),
        lingua=language,
        id="nl-" + place,
        label_email=esc(T("nl_email_label", language)),
        iscriviti=T("nl_iscriviti", language),
        privacy=privacy,
    ).rstrip("\n")


def newsletter_title(language):
    return newsletter.settings()["title"] or T("nl_titolo_default", language)


def newsletter_sidebar_box(language):
    """The form as a box of the sidebar, when the author put it there."""
    current = newsletter.settings()
    if not current["enabled"] or not current["in_sidebar"]:
        return ""
    return sidebar_box("box-newsletter", esc(newsletter_title(language)),
                       newsletter_form(language, "barra"))


def newsletter_after_article(language):
    """The form at the end of every article, when the author wants it there."""
    current = newsletter.settings()
    if not current["enabled"] or not current["after_article"]:
        return ""
    return ('    <aside class="newsletter-articolo" aria-labelledby="nl-articolo-titolo">\n'
            f'      <h2 id="nl-articolo-titolo">{esc(newsletter_title(language))}</h2>\n'
            + newsletter_form(language, "articolo") + "\n    </aside>\n")


def newsletter_message_page(language, title, text, action=""):
    """
    The pages the subscription answers with: "check your inbox", "confirm",
    "you are out". action is an optional form with the button that does it.
    """
    prefix = language_url_prefix(language)
    principale = render.render(
        "public/newsletter_pagina.html",
        titolo=esc(title),
        testo=esc(text),
        azione=block(action),
        url_home=prefix + "/",
        torna_home=T("torna_homepage", language),
    )
    contenuto = ('  <main id="content" class="main-content">\n' + principale
                 + '  </main>\n')
    meta_extra = '  <meta name="robots" content="noindex">'
    return render_page(language, with_site_title(f"{esc(title)}"),
                       contenuto, meta_extra=meta_extra)


def generate_biography_page(language="it", articles=None):
    """The page with the whole biography, in the same frame as the cards' pages."""
    if articles is None:
        articles = []
    title_value = T("biografia", language)
    content = biography_content(language)
    photo = biography_photo_html("bio-pagina-foto")
    if photo != "":
        photo = photo + "\n        "
    prefix = language_url_prefix(language)
    principale = render.render(
        "public/card_page.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=esc(title_value),
        contenuto_card=photo + add_lazy_loading(content),
        torna_home=T("torna_homepage", language),
    )
    contenuto = two_columns(principale, build_sidebar(language, "card", articles), language)
    url_canonico = CONFIG["base_url"] + biography_page_url(language)
    meta_extra = "\n".join([
        f'  <meta name="description" content="{esc(excerpt_from_html(content, 150))}">',
        f'  <link rel="canonical" href="{url_canonico}">',
        f'  <meta property="og:title" content="{esc(title_value)}">',
        '  <meta property="og:type" content="profile">',
    ])
    return render_page(
        language,
        with_site_title(f"{esc(title_value)}"),
        contenuto,
        meta_extra=meta_extra,
    )


def article_card_fields(art, language):
    """
    The title, description, content and reader preview of an article in one
    language. The homepage cards and the highlighted block both need the same
    four values, picked the same way.
    """
    if language != main_language():
        return (art.get("title_en", ""), art.get("description_en", ""),
                art.get("content_en", ""), art.get("preview_en", ""))
    return (art.get("title", ""), art.get("description", ""),
            art.get("content", ""), art.get("preview", ""))


def generate_card_page(card, language="it", articles=None):
    """
    Generate the HTML page of a single card (Biography, Projects, etc.)
    with a polished style: prominent header and readable content, and the
    sidebar every page shares.
    """
    if articles is None:
        articles = []
    title_value = card.get("title", "")
    content = card.get("content", "")
    slug = card_slug(title_value)
    description = excerpt_from_html(content, 150)
    # The canonical must point to the version in the current language:
    # it used to always point to /pagine/, even from the English version,
    # declaring a wrong canonical to Google for the /en/ pages.
    prefix = language_url_prefix(language)
    url_canonico = f"{CONFIG['base_url']}{prefix}/pagine/{slug}.html"

    principale = render.render(
        "public/card_page.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=esc(title_value),
        contenuto_card=add_lazy_loading(content),
        torna_home=T("torna_homepage", language),
    )
    contenuto = two_columns(principale, build_sidebar(language, "card", articles), language)

    meta_extra = "\n".join([
        f'  <meta name="description" content="{esc(description)}">',
        f'  <link rel="canonical" href="{url_canonico}">',
        f'  <meta property="og:title" content="{esc(title_value)}">',
        '  <meta property="og:type" content="article">',
    ])

    return render_page(
        language,
        with_site_title(f"{esc(title_value)}"),
        contenuto,
        meta_extra=meta_extra,
    )


# ---------------------------------------------------------------------------
# HOMEPAGE
# ---------------------------------------------------------------------------

def generate_homepage(articles, language="it", page=1, totale_pagine=1):
    """
    Generate the homepage: the articles in the main column, with the opening
    of each one, and the sidebar with the introduction, the cards and the
    follow links. With language="en" (or whichever language is the
    secondary one) it generates the translated version in its subfolder.
    With page > 1 it generates the next pages (/pagina/2.html, ...).
    """
    prefix = language_url_prefix(language)
    post_prefix = prefix + "/posts/"

    # Articles visible in this language, then the slice of the current page.
    visibili = articles_visible_in_language(articles, language)
    per_page = articles_per_page_count()
    if per_page > 0:
        start = (page - 1) * per_page
        end = start + per_page
        page_articles = visibili[start:end]
    else:
        start = 0
        end = len(visibili)
        page_articles = visibili

    # The most recent article leads the list on the first page: a bigger
    # thumbnail and twice the text. It stays in the list rather than in a
    # block of its own, so a search that replaces the list leaves nothing
    # stale above it.
    rows = []
    for index_value, art in enumerate(page_articles):
        lead = home_featured_enabled() and page == 1 and index_value == 0
        rows.append(article_row(art, language, lead=lead))
        # The "between the articles" custom code (an in-feed advertisement)
        # goes after the third one, once per page.
        if index_value == 2 and len(page_articles) > 3:
            feed_code = custom_code_block("home_feed", "home", ())
            if feed_code != "":
                rows.append('      <div class="annuncio annuncio-elenco">\n'
                            + feed_code + "\n      </div>")

    if len(rows) > 0:
        lista = "\n".join(rows)
    else:
        lista = f'      <p class="no-articles">{T("nessun_articolo", language)}</p>'

    articles_block = render.render(
        "public/home_articles.html",
        titolo_sezione=T("articles", language),
        placeholder_ricerca=esc(T("cerca_articoli", language)),
        aria_ricerca=esc(T("cerca", language)),
        lista=lista,
        paginazione=block(pagination_html(page, totale_pagine, language)),
    )

    # The introduction lives in the sidebar, or above the articles when the
    # author prefers it there. From page 2 on it is left out of the main
    # column: whoever reached page 2 has already seen it.
    intro = ""
    if page == 1:
        intro = home_intro_html(language)
    above = []
    below = []
    sidebar_intro = ""
    if intro != "" and home_intro_position() == "top":
        above.append(intro)
    elif intro != "":
        sidebar_intro = intro

    # The biography and the projects, on the first page only like the
    # introduction, wherever the author put them.
    side = {"biography": "", "projects": ""}
    if page == 1:
        pieces = []
        if biography_published():
            pieces.append(("biography", biography_settings()["position"],
                           biography_home_html(language)))
        projects_html = projects_home_html(language)
        if projects_html != "":
            pieces.append(("projects", projects_settings()["position"], projects_html))
        for name, position, html_piece in pieces:
            if position == "sidebar":
                side[name] = html_piece
            elif position == "top":
                above.append(html_piece)
            else:
                below.append(html_piece)

    principale = "".join(block(piece) for piece in above) + articles_block
    principale = principale + "".join(block(piece) for piece in below)

    contenuto = two_columns(
        principale,
        build_sidebar(language, "home", articles, intro=sidebar_intro,
                      biography=side["biography"], projects=side["projects"]),
        language,
        argomenti=topics_bar(articles, language),
    )

    # --- Homepage SEO ---
    base = CONFIG["base_url"].rstrip("/")
    if page > 1:
        url_canonico_home = (base + prefix + "/"
                             + pagination_folder(language) + f"/{page}.html")
    else:
        url_canonico_home = base + prefix + "/"
    # The two homepages always exist: we declare both with hreflang.
    hreflang_home = hreflang_links(
        language_url_prefix("it") + "/", language_url_prefix("en") + "/")
    # Structured data: the site (WebSite) and its author (Person).
    # This is where the personal SEO data (bio, role, social profiles)
    # is communicated to the search engines.
    jsonld_home = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": CONFIG["site_title"],
        "description": CONFIG["subtitle"],
        "url": base + "/",
        "inLanguage": language,
        "author": person_jsonld(),
    }, ensure_ascii=False)

    meta_extra = "\n".join([
        f'  <meta name="description" content="{esc(CONFIG["subtitle"])}">',
        f'  <meta name="author" content="{esc(CONFIG["author"])}">',
        f'  <link rel="canonical" href="{url_canonico_home}">',
        "  " + hreflang_home,
        f'  <meta property="og:title" content="{esc(CONFIG["site_title"])}">',
        f'  <meta property="og:description" content="{esc(CONFIG["subtitle"])}">',
        '  <meta property="og:type" content="website">',
        f'  <meta property="og:url" content="{url_canonico_home}">',
        "  " + social_meta(language),
    ])

    # rel=prev/next tell a search engine that the paginated pages are one
    # sequence rather than a pile of near-duplicates.
    if totale_pagine > 1:
        page_folder = pagination_folder(language)
        if page > 1:
            if page == 2:
                previous_url = base + prefix + "/"
            else:
                previous_url = f"{base}{prefix}/{page_folder}/{page - 1}.html"
            meta_extra = meta_extra + f'\n  <link rel="prev" href="{previous_url}">'
        if page < totale_pagine:
            next_url = f"{base}{prefix}/{page_folder}/{page + 1}.html"
            meta_extra = meta_extra + f'\n  <link rel="next" href="{next_url}">'

    # Values the client-side search needs, on top of the ones every page gets.
    # The slice tells the browser which articles to put back when the search
    # box is emptied; the lead flag tells it the first one was the lead row.
    search_options = {
        "post_prefix": post_prefix,
        "tag_prefix": prefix + "/tag/",
        "read_label": T("leggi_articolo", language),
        "latest_label": T("ultimo_articolo", language),
        "msg_unavailable": T("js_search_unavailable", language),
        "msg_no_results": T("js_search_no_results", language),
        "msg_results_for": T("js_search_results_for", language),
        "page_start": start,
        "page_end": end,
        "lead": home_featured_enabled() and page == 1,
    }

    head_extra = '  <script type="application/ld+json">' + jsonld_home + "</script>"

    return render_page(
        language,
        " &middot; ".join(esc(part) for part in (CONFIG["site_title"].strip(),
                                                    CONFIG["subtitle"].strip()) if part != ""),
        contenuto,
        meta_extra=meta_extra,
        head_extra=head_extra,
        site_extra=search_options,
        page_kind="home",
        is_home=True,
    )


# ---------------------------------------------------------------------------
# ARCHIVE, TAGS, 404
# ---------------------------------------------------------------------------

def generate_archive_page(articles, language="it"):
    """
    Generate the archive page: every article grouped by year, in a compact
    list (date and title), from the newest to the oldest.
    In the secondary language only the translated articles appear.
    """
    prefix = language_url_prefix(language)
    post_prefix = prefix + "/posts/"

    # We group the articles by year of publication.
    # A dictionary { year: [articles...] }, then we sort the years.
    by_year = {}
    for art in articles:
        if language != main_language():
            if not art.get("translation_confirmed", False):
                continue
        item_title = title_in_language(art, language)
        try:
            year = datetime.fromisoformat(art["date"]).year
        except (ValueError, KeyError, TypeError):
            year = 0
        if year not in by_year:
            by_year[year] = []
        by_year[year].append({"title": item_title, "art": art})

    anni_ordinati = sorted(by_year.keys(), reverse=True)

    year_blocks = []
    for year in anni_ordinati:
        feed_items = []
        for url_entry in by_year[year]:
            art = url_entry["art"]
            short_date = format_date(art["date"], language)
            feed_items.append(
                f'      <li><span class="archive-date">{short_date}</span> '
                f'<a href="{post_prefix}{art["slug"]}.html">{esc(url_entry["title"])}</a></li>')
        listing = "\n".join(feed_items)
        if year == 0:
            year_label = "?"
        else:
            year_label = str(year)
        year_blocks.append(f"""    <section class="archive-year">
      <h2>{year_label}</h2>
      <ul class="archive-list">
{listing}
      </ul>
    </section>""")

    if len(year_blocks) > 0:
        body = "\n".join(year_blocks)
    else:
        body = f'    <p class="no-articles">{T("nessun_articolo", language)}</p>'

    base = CONFIG["base_url"].rstrip("/")
    url_canonico = base + prefix + "/" + archive_file_name(language)
    hreflang = hreflang_links(
        language_url_prefix("it") + "/" + archive_file_name("it"),
        language_url_prefix("en") + "/" + archive_file_name("en"))

    principale = render.render(
        "public/archive.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_archivio=T("archivio", language),
        titolo_archivio=T("archivio_titolo", language),
        corpo=body,
    )
    contenuto = two_columns(principale, build_sidebar(language, "other", articles),
                            language, argomenti=topics_bar(articles, language))

    meta_extra = "\n".join([
        f'  <meta name="description" content="{T("archivio_descrizione", language)}">',
        f'  <link rel="canonical" href="{url_canonico}">',
        "  " + hreflang,
        "  " + social_meta(language),
    ])

    return render_page(
        language,
        with_site_title(f"{T('archivio_titolo', language)}"),
        contenuto,
        meta_extra=meta_extra,
    )


def generate_tag_page(tag_name, tag_articles, language="it", all_articles=None):
    """
    Generate the index page of a tag: every article using it, with the same
    rows as the homepage - thumbnail, title, date and the opening of the
    text - and the shared sidebar. In the secondary language only the
    translated articles are listed.

    The tag pages used to show the SEO description only, so an article
    without one appeared as a bare title, unlike on the homepage.
    """
    if all_articles is None:
        all_articles = tag_articles
    prefix = language_url_prefix(language)

    visibili = articles_visible_in_language(tag_articles, language)
    rows = [article_row(art, language) for art in visibili]

    principale = render.render(
        "public/tag.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_tag=T("tag", language),
        nome_tag=esc(tag_name),
        conteggio=len(visibili),
        label_conteggio=T("tag_conteggio", language),
        lista="\n".join(rows),
    )
    contenuto = two_columns(principale, build_sidebar(language, "other", all_articles),
                            language, argomenti=topics_bar(all_articles, language, tag_name))

    meta_extra = (f'  <meta name="description" '
                  f'content="{T("articoli_con_tag", language)} {esc(tag_name)}.">')

    return render_page(
        language,
        with_site_title(f"{T('articoli_con_tag', language)} {esc(tag_name)}"),
        contenuto,
        meta_extra=meta_extra,
    )



def generate_404_page(articles=None):
    """
    Generate a custom 404 page, consistent with the site design.

    A dead end is not a good place to leave a reader, so the page offers two
    ways out: a search box, which submits to the homepage where the
    client-side search picks the query up from ?q=, and the five most recent
    articles. Both are plain links and a plain form, so the page still works
    as a static file with no JavaScript at all.
    """
    language = main_language()
    prefix = language_url_prefix(language)
    post_prefix = prefix + "/posts/"

    latest_block = ""
    if articles is not None:
        visibili = articles_visible_in_language(articles, language)
        feed_items = []
        for art in visibili[:5]:
            feed_items.append(
                f'        <li><a href="{post_prefix}{art["slug"]}.html">'
                f'{esc(title_in_language(art, language))}</a>'
                f'<span class="errore-404-data">{format_date(art["date"], language)}</span></li>')
        if len(feed_items) > 0:
            latest_block = ('      <section class="errore-404-ultimi">\n'
                            f'        <h2>{T("ultimi_articoli", language)}</h2>\n'
                            "        <ul>\n" + "\n".join(feed_items)
                            + "\n        </ul>\n      </section>\n")

    contenuto = render.render(
        "public/404.html",
        testo=T("errore_404", language),
        url_home=prefix + "/",
        label_cerca=T("cerca_nel_sito", language),
        placeholder_ricerca=esc(T("cerca_articoli", language)),
        ultimi_articoli=latest_block,
        torna_home=T("torna_homepage", language),
    )
    return render_page(
        language,
        with_site_title(f"{T('pagina_non_trovata', language)}"),
        contenuto,
    )


# ---------------------------------------------------------------------------
# FEEDS, SEARCH INDEX, SITEMAP, llms.txt
# ---------------------------------------------------------------------------

def generate_rss(articles, language=None):
    """
    Generate the RSS 2.0 feed of a language.

    The main language keeps /rss.xml, so existing subscriptions never break.
    The secondary language gets its own feed listing only the articles whose
    translation has been confirmed, with the translated titles and links:
    before this, a reader of the English site had no feed at all.
    """
    if language is None:
        language = main_language()

    prefix = language_url_prefix(language)
    base = CONFIG["base_url"].rstrip("/")
    ora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    feed_articles = []
    for art in articles:
        if article_has_page_in(art, language):
            feed_articles.append(art)

    feed_items = []
    for art in feed_articles[:20]:
        try:
            dt = datetime.fromisoformat(art["date"])
            pubdate = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            pubdate = ora
        url = f"{base}{prefix}/posts/{art['slug']}.html"
        item_title = title_in_language(art, language)
        if language == main_language():
            desc = art.get("description") or item_title
        else:
            desc = art.get("description_en") or item_title
        feed_items.append(f"""    <item>
      <title>{esc(item_title)}</title>
      <link>{url}</link>
      <guid>{url}</guid>
      <pubDate>{pubdate}</pubDate>
      <description>{esc(desc)}</description>
    </item>""")

    items = "\n".join(feed_items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(CONFIG['site_title'])}</title>
    <atom:link href="{base}/{feed_file_name(language)}" rel="self" type="application/rss+xml"/>
    <link>{base}{prefix}/</link>
    <description>{esc(CONFIG['subtitle'])}</description>
    <language>{language}</language>
    <lastBuildDate>{ora}</lastBuildDate>
{items}
  </channel>
</rss>"""


def tag_link_data(art):
    """
    An article's tags as {name, slug} pairs, ready for a link.

    Used by the search index: the browser rebuilds the cards when someone
    searches, and it has to be able to build the tag links too.
    """
    result = []
    for tag in extract_article_tags(art):
        tag_slug = slugify(tag)
        if tag_slug == "":
            continue
        result.append({"name": tag, "slug": tag_slug})
    return result


def generate_search_index(articles):
    """
    Generate the JSON index used by the browser-side search.
    It includes the Italian text and, if present and confirmed, the English
    one, so the search finds words in both languages and shows the snippet.
    """
    index_value = []
    for art in articles:
        url_entry = {
            "title": art["title"],
            "slug": art["slug"],
            "description": art.get("description", ""),
            "preview": art.get("preview", ""),
            "tags": art.get("tags", ""),
            "text": plain_text(art.get("content", "")),
            "date_it": format_date(art["date"], "it"),
            "date_en": format_date(art["date"], "en"),
            # Tells whether a published English version exists.
            "has_en": False,
            "title_en": "",
            "text_en": "",
            "preview_en": art.get("preview_en", ""),
            # The browser rebuilds the cards when you search, so it needs the
            # cover too: without it a search would quietly drop every
            # thumbnail from the page.
            "image": media_url(art.get("image", "")),
            # The tags as name AND slug. The slug has to come from here
            # because slugify folds accents, and reimplementing that in
            # JavaScript would be a second version of the rule to keep in
            # step. Same reason the cover travels in this index.
            "tag_links": tag_link_data(art),
            # What a row of the list shows, computed here once so the rows
            # the browser builds for a search say exactly what the rows of
            # the page say: the opening of the article, the reading time and
            # the word on the tile of an article with no cover.
            "excerpt": article_excerpt(art, main_language(), excerpt_word_count()),
            "reading": compute_reading_time(art.get("content", ""), main_language()),
            "tile": article_tile_label(art),
            "excerpt_en": "",
            "reading_en": "",
        }
        # We add the English data only if the translation is confirmed.
        translation_confirmed = art.get("translation_confirmed", False)
        content_en = art.get("content_en", "")
        if translation_confirmed and content_en.strip() != "":
            url_entry["has_en"] = True
            url_entry["title_en"] = art.get("title_en", "")
            url_entry["text_en"] = plain_text(content_en)
            url_entry["excerpt_en"] = article_excerpt(art, secondary_language(),
                                                      excerpt_word_count())
            url_entry["reading_en"] = compute_reading_time(content_en, secondary_language())
        index_value.append(url_entry)
    return json.dumps(index_value, ensure_ascii=False)


def generate_llms_txt(articles):
    """
    Generate the llms.txt file: a Markdown map of the site for AI crawlers
    (ChatGPT, Claude, Perplexity). The GEO/llms.txt standard.
    """
    lines = [
        f"# {CONFIG['site_title']}",
        "",
        f"> {CONFIG['subtitle']}",
        "",
        f"Autore: {CONFIG['author']}.",
        "",
        "## Articoli",
        "",
    ]
    for art in articles:
        url = f"{CONFIG['base_url']}/posts/{art['slug']}.html"
        desc = art.get("description") or plain_text(art.get("content", ""))[:120]
        lines.append(f"- [{art['title']}]({url}): {desc}")
    lines.append("")

    # Training & licensing: makes the policy visible to any LLM/AI operator
    # reading this file, in the file's own plain-language format.
    lines.append("## Training & Licensing")
    lines.append("")
    lines.append(ai_training_statement("en"))
    training = ai_training_config()
    contatto = training.get("contact_email", "").strip()
    if training.get("policy", "open") == "licensed" and contatto != "":
        lines.append("")
        lines.append(f"Licensing contact: {contatto}")
    lines.append("")
    lines.append(f"Full statement: {CONFIG['base_url']}/training-rights.html")
    lines.append("")
    return "\n".join(lines)


def generate_sitemap(articles):
    """
    Generate the standard sitemap.xml: the list of the site addresses,
    which helps search engines find every page.
    It includes the homepage, the articles (both languages) and the card pages.
    """
    base = CONFIG["base_url"].rstrip("/")
    main_prefix = language_url_prefix(main_language())
    sec_prefix = language_url_prefix(secondary_language())

    def url_entry(path_value, lastmod=""):
        """Build a <url> entry of the sitemap, with the date if available."""
        if lastmod != "":
            # The sitemap wants the date in ISO format: we keep only YYYY-MM-DD.
            short_date = lastmod[:10]
            return ("  <url><loc>" + base + path_value + "</loc>"
                    "<lastmod>" + short_date + "</lastmod></url>")
        return "  <url><loc>" + base + path_value + "</loc></url>"

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # The two homepages (main language at the root, secondary in a folder).
    lines.append(url_entry(main_prefix + "/"))
    lines.append(url_entry(sec_prefix + "/"))

    # Next pages of the homepage (if pagination is active).
    per_page = articles_per_page_count()
    for home_language in (main_language(), secondary_language()):
        visibili = articles_visible_in_language(articles, home_language)
        if per_page > 0 and len(visibili) > per_page:
            totale_pagine = (len(visibili) + per_page - 1) // per_page
            home_prefix = language_url_prefix(home_language)
            for number in range(2, totale_pagine + 1):
                lines.append(url_entry(home_prefix + "/"
                                  + pagination_folder(home_language)
                                  + f"/{number}.html"))

    # Archive pages in both languages.
    lines.append(url_entry(main_prefix + "/" + archive_file_name(main_language())))
    lines.append(url_entry(sec_prefix + "/" + archive_file_name(secondary_language())))

    # Published articles (main language and, if confirmed, secondary).
    # lastmod helps the engines understand which pages have changed.
    for art in articles:
        ultima_modifica = art.get("date_modified", art.get("date", ""))
        lines.append(url_entry(main_prefix + "/posts/" + art["slug"] + ".html",
                          ultima_modifica))
        translation_confirmed = art.get("translation_confirmed", False)
        content_en = art.get("content_en", "")
        if translation_confirmed and content_en.strip() != "":
            lines.append(url_entry(sec_prefix + "/posts/" + art["slug"] + ".html",
                              ultima_modifica))

    # Tag index pages (mirroring what build() generates).
    mappa_tag = collect_tags(articles)
    for tag_name in mappa_tag:
        tag_slug = slugify(tag_name)
        if tag_slug == "":
            continue
        lines.append(url_entry(main_prefix + "/tag/" + tag_slug + ".html"))
        # The secondary version exists only if at least one article is translated.
        for art_tag in mappa_tag[tag_name]:
            if art_tag.get("translation_confirmed", False):
                lines.append(url_entry(sec_prefix + "/tag/" + tag_slug + ".html"))
                break

    # The page of the labs, in the languages that have any.
    for language, prefix_value in ((main_language(), main_prefix),
                                   (secondary_language(), sec_prefix)):
        if any(is_lab(art) for art in articles_visible_in_language(articles, language)):
            lines.append(url_entry(prefix_value + "/labs.html"))

    # Series pages (mirroring what build() generates).
    for series_slug, series in collect_series(articles).items():
        if len(series["articles"]) < 2:
            continue
        lines.append(url_entry(main_prefix + "/serie/" + series_slug + ".html"))
        if len(articles_visible_in_language(series["articles"], secondary_language())) >= 2:
            lines.append(url_entry(sec_prefix + "/serie/" + series_slug + ".html"))

    # The biography page, in both languages like the cards.
    if biography_published():
        lines.append(url_entry(main_prefix + "/pagine/" + biography_slug() + ".html"))
        lines.append(url_entry(sec_prefix + "/pagine/" + biography_slug() + ".html"))

    # Pages of the published cards (both languages: build() always writes them).
    for card in published_home_cards():
        slug = card_slug(card.get("title", ""))
        lines.append(url_entry(main_prefix + "/pagine/" + slug + ".html"))
        lines.append(url_entry(sec_prefix + "/pagine/" + slug + ".html"))

    lines.append("</urlset>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI TRAINING RIGHTS
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# User-agent strings of the crawlers used by AI/LLM companies to gather
# training data, as best known at the time of writing. This is NOT an
# official or exhaustive list, and crawler names change over time: it is a
# good-faith, best-effort set covering the major current operators. None of
# this is a legally binding standard - a crawler is only as compliant as its
# operator chooses to be. Review and update this list periodically.
KNOWN_AI_CRAWLERS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",           # OpenAI
    "Google-Extended",                                   # Google (Gemini/Bard training)
    "Applebot-Extended",                                 # Apple (distinct from Applebot/Siri)
    "CCBot",                                              # Common Crawl (used by many LLMs)
    "anthropic-ai", "ClaudeBot", "Claude-Web",            # Anthropic
    "Bytespider",                                         # ByteDance
    "PerplexityBot",                                      # Perplexity AI
    "Amazonbot",                                          # Amazon
    "cohere-ai",                                          # Cohere
    "Diffbot",                                            # Diffbot
    "FacebookBot", "meta-externalagent",                  # Meta
    "Timpibot", "ImagesiftBot", "Omgilibot", "Omgili",    # various data brokers
]


def ai_training_statement(language="it"):
    """
    Return the human-readable statement describing the training policy, in
    the given language. Uses the author's custom text if provided, otherwise
    a default wording that matches the chosen policy.
    """
    training = ai_training_config()
    custom = training.get("statement", "").strip()
    if custom != "":
        return custom
    policy = training.get("policy", "open")
    if policy == "licensed":
        return T("training_intro_licensed", language)
    if policy == "disallow":
        return T("training_intro_disallow", language)
    return T("training_intro_open", language)


def generate_robots_block_ai_crawlers():
    """
    Generate the robots.txt lines that block known AI/LLM crawlers, if the
    configured policy is "licensed" or "disallow". Returns an empty string
    for the "open" policy (no special treatment for AI crawlers).
    """
    policy = ai_training_config().get("policy", "open")
    if policy not in ("licensed", "disallow"):
        return ""
    lines = ["", "# AI training crawlers: see /training-rights.html"]
    for agente in KNOWN_AI_CRAWLERS:
        lines.append(f"User-agent: {agente}")
        lines.append("Disallow: /")
    return "\n".join(lines) + "\n"


def generate_ai_txt():
    """
    Generate a plain-text /.well-known/ai.txt file: a simple, human- and
    machine-readable statement of the training policy, following the
    informal "ai.txt" convention some AI operators check for. Not a formal
    or universally adopted standard.
    """
    training = ai_training_config()
    policy = training.get("policy", "open")
    lines = [
        "# ai.txt - AI training rights statement",
        "# This is an informal convention, not a binding legal standard.",
        "",
        "Policy: " + policy,
        "",
        ai_training_statement("en"),
    ]
    contatto = training.get("contact_email", "").strip()
    if contatto != "" and policy == "licensed":
        lines.append("")
        lines.append("Contact: " + contatto)
    licenza_url = training.get("license_url", "").strip()
    if licenza_url != "":
        lines.append("License: " + licenza_url)
    else:
        base = CONFIG.get("base_url", "").rstrip("/")
        lines.append("License: " + base + "/training-rights.html")
    return "\n".join(lines) + "\n"


def generate_tdmrep_json():
    """
    Generate a best-effort /.well-known/tdmrep.json file, following the
    community TDM Reservation Protocol (a mechanism for websites to declare
    text-and-data-mining permissions in machine-readable form). This is
    implemented in good faith from current public documentation; the
    protocol is still evolving, is not universally adopted by AI operators,
    and this file has no legal force on its own.
    """
    training = ai_training_config()
    policy = training.get("policy", "open")
    # TDMRep reservation values: 1 = TDM reserved (permission required),
    # 0 = TDM not reserved (no restriction).
    if policy == "open":
        reservation = 0
    else:
        reservation = 1
    base = CONFIG.get("base_url", "").rstrip("/")
    licenza_url = training.get("license_url", "").strip()
    if licenza_url == "":
        licenza_url = base + "/training-rights.html"
    data_value = {
        "tdm-reservation": reservation,
        "tdm-policy": licenza_url,
    }
    return json.dumps(data_value, ensure_ascii=False, indent=2) + "\n"



def generate_training_rights_page(language="it"):
    """
    Generate the public, plain-language page explaining the AI training
    policy: what it is, why it may matter to a reader, and how to reach out
    for a licence if one is required. Linked from robots.txt and llms.txt.
    """
    training = ai_training_config()
    policy = training.get("policy", "open")
    contatto = training.get("contact_email", "").strip()
    licenza_url = training.get("license_url", "").strip()
    statement = esc(ai_training_statement(language))

    contact_block = ""
    if policy == "licensed" and contatto != "":
        contact_block = (f'<p>{T("training_contatto", language)} '
                         f'<a href="mailto:{esc(contatto)}">{esc(contatto)}</a></p>')

    license_block = ""
    if licenza_url != "":
        license_block = (f'<p>{T("training_termini_propri", language)} '
                         f'<a href="{esc(licenza_url)}">{esc(licenza_url)}</a></p>')

    prefix = language_url_prefix(language)
    base = CONFIG["base_url"].rstrip("/")
    url_canonico = base + prefix + "/training-rights.html"

    contenuto = render.render(
        "public/training_rights.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=T("training_titolo", language),
        statement=statement,
        blocco_contatto=contact_block,
        blocco_licenza=license_block,
    )

    meta_extra = "\n".join([
        f'  <meta name="description" content="{statement}">',
        '  <meta name="robots" content="noindex, follow">',
        f'  <link rel="canonical" href="{url_canonico}">',
    ])

    return render_page(
        language,
        with_site_title(f"{T('training_titolo', language)}"),
        contenuto,
        meta_extra=meta_extra,
    )


# ---------------------------------------------------------------------------
# THE BUILD
# ---------------------------------------------------------------------------

# Files copied verbatim from static/ into output/ on every build. The admin
# stylesheet and script are NOT here: they are served by the editor from
# /admin-static/ and have no business being published.
PUBLIC_ASSETS = ("common.css", "style.css", "site.js")


def copy_public_assets():
    """
    Write the public CSS and JavaScript into output/.

    The contents come from render.read_static, so this works both from a
    normal checkout, where they are files under static/, and from the
    single-file bundle, where they are strings inside the script.
    """
    for name in PUBLIC_ASSETS:
        if render.static_exists(name):
            (OUTPUT_DIR / name).write_text(render.read_static(name), encoding="utf-8")


def remove_stale_pages(written_pages, lp, ls, sec_folder):
    """
    Delete the generated pages that this build did not write again.

    The folders swept here hold nothing but generated pages, so a file that was
    not written this time round is a leftover: the article that was deleted, the
    page of a slug that changed, the index of a tag nobody uses any more, the
    card that was switched off, a pagination page no longer needed. Left in
    place, that file keeps answering 200 while having disappeared from the
    sitemap - a ghost page the search engine goes on showing, and duplicate
    content every time a slug changed. Removing it turns the old address into a
    404, which is what makes the engine drop it.
    """
    folders = []
    for root in (OUTPUT_DIR, OUTPUT_DIR / sec_folder):
        folders.append(root / "posts")
        folders.append(root / "tag")
        folders.append(root / "serie")
        folders.append(root / "pagine")
        # The pagination folder is named after the language ("pagina", "page"):
        # we sweep both names, so that flipping the site language cleans up too.
        for language in (lp, ls):
            folders.append(root / pagination_folder(language))

    for folder in folders:
        if not folder.is_dir():
            continue
        keep = written_pages.get(folder, set())
        for file_value in folder.glob("*.html"):
            if file_value.name not in keep:
                file_value.unlink()

    # The archive sits next to pages this function does not manage (index.html,
    # 404.html, the feeds...), so instead of sweeping the whole folder we only
    # look at the two names the archive can take: flipping the site language
    # would otherwise leave the old one behind.
    archive_names = {archive_file_name("it"), archive_file_name("en")}
    for root in (OUTPUT_DIR, OUTPUT_DIR / sec_folder):
        keep = written_pages.get(root, set())
        for name in archive_names:
            if name in keep:
                continue
            leftover = root / name
            if leftover.is_file():
                leftover.unlink()


def warn_if_base_url_is_a_placeholder():
    """
    Warn when base_url is empty or still the example domain.

    Every address in sitemap.xml, in the canonical tags and in the feeds is
    built on base_url. Leave it at the example value and the sitemap describes
    a site at a domain that is not yours: Google fetches it, sees addresses
    that do not belong to the site it is crawling, and indexes nothing.
    """
    base = CONFIG.get("base_url", "").strip()
    if base == "":
        print("WARNING: base_url is empty: sitemap.xml and the canonical tags "
              "will carry relative addresses and search engines will reject "
              "them. Set it in Settings.")
    elif base.rstrip("/") == CONFIG_DEFAULT["base_url"].rstrip("/"):
        print(f"WARNING: base_url is still the example value ({base}): "
              "sitemap.xml, the canonical tags and the feeds all point to a "
              "domain that is not yours, so your pages will not be indexed. "
              "Set it in Settings.")


def build():
    """
    Rebuild the whole static site into the output/ folder.

    It runs under BUILD_LOCK: with a threaded server two requests could
    otherwise rebuild at the same time and interleave their writes, leaving
    half-written pages behind.
    """
    with BUILD_LOCK:
        return _build_unlocked()


def _build_unlocked():
    """The body of build(). The caller already holds BUILD_LOCK."""
    # We reload the configuration from the file, so that changes saved
    # from the Settings page take effect immediately.
    reload_global_config()

    (OUTPUT_DIR / "posts").mkdir(parents=True, exist_ok=True)
    # The "pagine" folder holds the card pages (bio, projects...).
    (OUTPUT_DIR / "pagine").mkdir(parents=True, exist_ok=True)
    # The media folder holds the uploaded videos: build() does not touch it,
    # we only make sure it exists.
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # We work out the main language (at the root) and the secondary one (in a
    # subfolder). Changing CONFIG["language"] flips the whole site.
    lp = main_language()
    ls = secondary_language()
    sec_folder = ls  # subfolder of the secondary language (e.g. "en" or "it")

    # The folder of the secondary language.
    (OUTPUT_DIR / sec_folder / "posts").mkdir(parents=True, exist_ok=True)

    # Scheduled articles whose moment has come go out with this build: a
    # site rebuilt by cron, with no editor running, publishes them too.
    publish_due_articles()
    tutti = load_articles()
    published_articles = [a for a in tutti if a.get("status") == "published"]
    note_labs(published_articles)

    # Pages written by this build, grouped by folder. At the end
    # remove_stale_pages() deletes from those folders whatever is left over
    # from an earlier build: the page of a deleted article, the page of an old
    # slug, the index of a tag nobody uses any more. Without that sweep the
    # stale file stays online and answers 200, so a search engine keeps it
    # indexed even though the sitemap stopped listing it.
    written_pages = {}

    def write_page(path_value, content):
        """Write a generated page and record it, so the sweep keeps it."""
        path_value.parent.mkdir(parents=True, exist_ok=True)
        path_value.write_text(content, encoding="utf-8")
        written_pages.setdefault(path_value.parent, set()).add(path_value.name)

    # Pages of the individual articles in the main language (at the root).
    for art in published_articles:
        html_art = generate_article_page(art, lp, published_articles)
        write_page(OUTPUT_DIR / "posts" / f"{art['slug']}.html", html_art)

        # Version in the secondary language: we generate it only if the
        # translation is confirmed and the translated content is not empty.
        # The translation only exists between Italian and English (_en fields).
        if article_has_page_in(art, ls):
            html_sec = generate_article_page(art, ls, published_articles)
            write_page(OUTPUT_DIR / sec_folder / "posts" / f"{art['slug']}.html",
                       html_sec)

    # Tag index pages (one for every tag used in the articles).
    (OUTPUT_DIR / "tag").mkdir(parents=True, exist_ok=True)
    mappa_tag = collect_tags(published_articles)
    for tag_name in mappa_tag:
        tag_articles = mappa_tag[tag_name]
        tag_slug = slugify(tag_name)
        if tag_slug == "":
            continue
        # Tags in the main language (at the root).
        html_tag = generate_tag_page(tag_name, tag_articles, lp, published_articles)
        write_page(OUTPUT_DIR / "tag" / f"{tag_slug}.html", html_tag)
        # Tags in the secondary language, only if at least one article
        # with that tag has a confirmed translation.
        has_translated_articles = False
        for art_tag in tag_articles:
            if art_tag.get("translation_confirmed", False):
                has_translated_articles = True
                break
        if has_translated_articles:
            (OUTPUT_DIR / sec_folder / "tag").mkdir(parents=True, exist_ok=True)
            html_tag_sec = generate_tag_page(tag_name, tag_articles, ls, published_articles)
            write_page(OUTPUT_DIR / sec_folder / "tag" / f"{tag_slug}.html",
                       html_tag_sec)

    # The page of the labs, where there are any; without, the old one goes.
    for language, folder in ((lp, OUTPUT_DIR), (ls, OUTPUT_DIR / sec_folder)):
        if labs_online(language):
            write_page(folder / "labs.html", generate_labs_page(published_articles, language))
        elif (folder / "labs.html").exists():
            (folder / "labs.html").unlink()

    # The page of every series with at least two parts online.
    for series_slug, series in collect_series(published_articles).items():
        if len(series["articles"]) < 2:
            continue
        (OUTPUT_DIR / "serie").mkdir(parents=True, exist_ok=True)
        write_page(OUTPUT_DIR / "serie" / f"{series_slug}.html",
                   generate_series_page(series_slug, series, lp, published_articles))
        if len(articles_visible_in_language(series["articles"], ls)) >= 2:
            (OUTPUT_DIR / sec_folder / "serie").mkdir(parents=True, exist_ok=True)
            write_page(OUTPUT_DIR / sec_folder / "serie" / f"{series_slug}.html",
                       generate_series_page(series_slug, series, ls, published_articles))

    # Pages of the published cards (Biography, Projects, About...). A card
    # switched off, or left empty, or with the whole block switched off, has
    # no page: the sweep at the end of build() then removes the file it had.
    for card in published_home_cards():
        slug = card_slug(card.get("title", ""))
        # Cards in the main language (at the root).
        write_page(OUTPUT_DIR / "pagine" / f"{slug}.html",
                   generate_card_page(card, lp, published_articles))
        # Cards in the secondary language.
        (OUTPUT_DIR / sec_folder / "pagine").mkdir(parents=True, exist_ok=True)
        write_page(OUTPUT_DIR / sec_folder / "pagine" / f"{slug}.html",
                   generate_card_page(card, ls, published_articles))

    # The page of the whole biography, in both languages. Switched off, it is
    # not written, and the sweep removes the one a previous build left.
    if biography_published():
        (OUTPUT_DIR / "pagine").mkdir(parents=True, exist_ok=True)
        write_page(OUTPUT_DIR / "pagine" / f"{biography_slug()}.html",
                   generate_biography_page(lp, published_articles))
        (OUTPUT_DIR / sec_folder / "pagine").mkdir(parents=True, exist_ok=True)
        write_page(OUTPUT_DIR / sec_folder / "pagine" / f"{biography_slug()}.html",
                   generate_biography_page(ls, published_articles))

    # Homepage in the main language (at the root) and in the secondary one.
    # If pagination is active, we also generate /pagina/2.html, /pagina/3...
    (OUTPUT_DIR / sec_folder).mkdir(parents=True, exist_ok=True)
    per_page = articles_per_page_count()
    for home_language in (lp, ls):
        visibili = articles_visible_in_language(published_articles, home_language)
        if per_page > 0 and len(visibili) > per_page:
            totale_pagine = (len(visibili) + per_page - 1) // per_page
        else:
            totale_pagine = 1
        # Destination folder: the root for the main language, a subfolder
        # for the secondary one.
        if home_language == lp:
            base_folder = OUTPUT_DIR
        else:
            base_folder = OUTPUT_DIR / sec_folder
        # Page 1: this is the homepage proper.
        (base_folder / "index.html").write_text(
            generate_homepage(published_articles, home_language, 1, totale_pagine),
            encoding="utf-8")
        # Next pages, only if they are needed.
        if totale_pagine > 1:
            page_folder = base_folder / pagination_folder(home_language)
            page_folder.mkdir(parents=True, exist_ok=True)
            for number in range(2, totale_pagine + 1):
                write_page(page_folder / f"{number}.html",
                           generate_homepage(published_articles, home_language,
                                             number, totale_pagine))

    # Archive page (compact list by year) in both languages.
    write_page(OUTPUT_DIR / archive_file_name(lp),
               generate_archive_page(published_articles, lp))
    write_page(OUTPUT_DIR / sec_folder / archive_file_name(ls),
               generate_archive_page(published_articles, ls))

    # RSS feeds: one per language, both at the root. The main language keeps
    # the historical /rss.xml so existing subscriptions do not break.
    (OUTPUT_DIR / feed_file_name(lp)).write_text(
        generate_rss(published_articles, lp), encoding="utf-8")
    (OUTPUT_DIR / feed_file_name(ls)).write_text(
        generate_rss(published_articles, ls), encoding="utf-8")

    # JSON search index (for the browser-side search bar).
    (OUTPUT_DIR / "search-index.json").write_text(
        generate_search_index(published_articles), encoding="utf-8")

    # llms.txt (a Markdown map for AI crawlers / GEO).
    (OUTPUT_DIR / "llms.txt").write_text(
        generate_llms_txt(published_articles), encoding="utf-8")

    # Standard XML sitemap (for the search engines).
    (OUTPUT_DIR / "sitemap.xml").write_text(
        generate_sitemap(published_articles), encoding="utf-8")

    # robots.txt: allows indexing and points to the sitemap.
    base = CONFIG.get("base_url", "").rstrip("/")
    robots_content = "User-agent: *\nAllow: /\n"
    robots_content = robots_content + generate_robots_block_ai_crawlers()
    if base != "":
        robots_content = robots_content + "Sitemap: " + base + "/sitemap.xml\n"
    (OUTPUT_DIR / "robots.txt").write_text(robots_content, encoding="utf-8")

    # ads.txt: the list of who may sell advertising on this site. AdSense
    # asks for it at the root of the domain and limits the ads it serves
    # until it finds it. Written only when the author filled it in; when the
    # field is emptied the old file goes, or it would keep authorising.
    ads_txt = str(CONFIG.get("ads_txt", "") or "").strip()
    if ads_txt != "":
        (OUTPUT_DIR / "ads.txt").write_text(ads_txt + "\n", encoding="utf-8")
    elif (OUTPUT_DIR / "ads.txt").exists():
        (OUTPUT_DIR / "ads.txt").unlink()

    # AI training rights: /.well-known files and a plain-language page,
    # in both site languages. Always generated (the "open" policy is the
    # default and simply states no restrictions apply).
    well_known_dir = OUTPUT_DIR / ".well-known"
    well_known_dir.mkdir(parents=True, exist_ok=True)
    (well_known_dir / "ai.txt").write_text(generate_ai_txt(), encoding="utf-8")
    (well_known_dir / "tdmrep.json").write_text(generate_tdmrep_json(), encoding="utf-8")
    (OUTPUT_DIR / "training-rights.html").write_text(
        generate_training_rights_page(lp), encoding="utf-8")
    (OUTPUT_DIR / sec_folder / "training-rights.html").write_text(
        generate_training_rights_page(ls), encoding="utf-8")

    # Custom 404 page, with a search box and the latest articles.
    (OUTPUT_DIR / "404.html").write_text(
        generate_404_page(published_articles), encoding="utf-8")

    # Automatically generated favicon (title initial on a gradient).
    # If the author has configured a custom favicon, it is not needed.
    if seo_data().get("favicon", "") == "":
        (OUTPUT_DIR / "favicon.svg").write_text(
            generate_favicon_svg(), encoding="utf-8")

    # A misconfigured base_url makes the whole sitemap useless: say so out loud.
    warn_if_base_url_is_a_placeholder()

    # Pages left over from an earlier build: the article that was deleted, the slug
    # that changed, the tag that disappeared, the card that was switched off.
    remove_stale_pages(written_pages, lp, ls, sec_folder)

    # Public CSS and JavaScript, copied straight from static/.
    copy_public_assets()

    return len(published_articles)
