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
import json
import re
import threading
from datetime import datetime, timezone

from core import render
from core.articles import (articles_visible_in_language, card_slug,
                           collect_tags, excerpt_from_html,
                           extract_article_tags, html_content_is_empty,
                           load_articles, plain_text, slugify)
from core.config import (CONFIG, CONFIG_DEFAULT, MEDIA_DIR, OUTPUT_DIR,
                         ai_training_config, archive_file_name,
                         articles_per_page_count, feed_file_name,
                         language_url_prefix, main_language,
                         pagination_folder, reload_global_config,
                         secondary_language, seo_data)
from core.i18n import T
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


def tag_links(art, language, css_class="card-tag"):
    """
    Render an article's tags as small links, for the homepage cards.

    Seeing the topics before clicking is how a reader decides whether an
    article is for them; the links also give the tag pages somewhere to be
    found from.
    """
    tags = extract_article_tags(art)
    if len(tags) == 0:
        return ""
    prefix = language_url_prefix(language) + "/tag/"
    pieces = []
    for tag in tags:
        tag_slug = slugify(tag)
        if tag_slug == "":
            continue
        pieces.append(f'<a class="{css_class}" href="{prefix}{tag_slug}.html">'
                      f"#{esc(tag)}</a>")
    if len(pieces) == 0:
        return ""
    return '<span class="card-tags">' + "".join(pieces) + "</span>"


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

    measurement_id = str(CONFIG.get("analytics_id", "")).strip()
    if measurement_id != "":
        if re.fullmatch(r"[A-Za-z0-9-]+", measurement_id) is not None:
            parts.append(
                '<script async src="https://www.googletagmanager.com/gtag/js?id='
                + measurement_id + '"></script>\n'
                '  <script>\n'
                '    window.dataLayer = window.dataLayer || [];\n'
                '    function gtag(){dataLayer.push(arguments);}\n'
                "    gtag('js', new Date());\n"
                "    gtag('config', '" + measurement_id + "');\n"
                '  </script>')

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

def custom_code_list():
    """
    Return the custom code snippets of the configuration, skipping anything
    malformed. A hand-edited config.json is the only way to get a snippet
    that is not a dictionary here, and one bad entry should not stop a build.
    """
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


# The scopes a snippet can have, in the order the Settings dropdown lists
# them. "home", "home_articles" and "home_optin" came first: a configuration
# written before the list grew keeps behaving exactly as it did.
SNIPPET_SCOPES = ("home", "articles", "home_articles",
                  "optin", "home_optin", "all")

# Where a snippet can be injected. The first three are positions in the HTML
# and exist on every page; the others are places in the visible layout, and a
# page that has no such place simply leaves the snippet out. "nav" is the
# header menu, next to Home, Articles, Archive and RSS: made for a link such as
# a chat widget's "Ask the assistant". It came last, so it is last here too.
SNIPPET_POSITIONS = ("head", "body_start", "body_end",
                     "after_header", "before_footer", "article_end", "nav")


def snippet_applies(snippet, page_kind, article_ids):
    """
    Tell whether a snippet belongs on the page being generated.

    Each scope names the pages it wants: the homepage, the articles, both, or
    the whole site. "optin" and "home_optin" narrow the articles down to the
    ones that ticked the snippet while being written.

    A snippet whose id is no longer anywhere in the configuration simply never
    matches, which is what makes deleting one safe: the articles that ticked
    it keep the dead id in their JSON and nothing goes wrong.
    """
    if snippet.get("enabled", False) is not True:
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


def custom_code_block(position, page_kind, article_ids):
    """
    Collect the snippets that go into one position of one page.

    The code is injected VERBATIM: escaping it would defeat the point. It is
    written by whoever can log into the editor, which is the same trust level
    as "home_content", already raw HTML. It never comes from a reader.
    """
    parts = []
    for snippet in custom_code_list():
        where = snippet.get("position", "head")
        if where not in SNIPPET_POSITIONS:
            where = "head"
        if where != position:
            continue
        if not snippet_applies(snippet, page_kind, article_ids):
            continue
        code = str(snippet.get("code", "")).strip()
        if code != "":
            parts.append(code)
    return "\n".join(parts)


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
    lines.append(f'<meta property="og:site_name" content="{esc(CONFIG["site_title"])}">')
    lines.append(f'  <meta property="og:locale" content="{locale}">')
    if seo.get("twitter_site"):
        lines.append(f'  <meta name="twitter:site" content="{esc(seo["twitter_site"])}">')
    return "\n".join(lines)


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


def site_header(language="it", nav_extra=""):
    """
    The header shared by every public page, with the language switcher.

    nav_extra is the custom code for the "nav" position: extra entries of the
    menu, after RSS and before the language switcher, so they sit with the
    other links and pick up their style.
    """
    prefix = language_url_prefix(language)

    # Language switcher in the navbar (top right, where users
    # look for it): a link to the other language's home, compact label.
    other_language = secondary_language()
    if language != main_language():
        other_language = main_language()

    return render.render(
        "public/header.html",
        salta_contenuto=T("salta_contenuto", language),
        url_home=prefix + "/",
        titolo_sito=esc(CONFIG["site_title"]),
        sottotitolo=esc(CONFIG["subtitle"]),
        label_home=T("home", language),
        label_articoli=T("articles", language),
        url_archivio=prefix + "/" + archive_file_name(language),
        label_archivio=T("archivio", language),
        url_feed=feed_url(language),
        voci_extra=("\n      " + nav_extra.strip()) if nav_extra.strip() else "",
        url_altra_lingua=language_url_prefix(other_language) + "/",
        altra_lingua=other_language,
        altra_lingua_label=other_language.upper(),
        aria_tema="Cambia tema",
        title_tema="Tema chiaro/scuro",
    ).rstrip("\n")


def site_footer(language="it"):
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


def render_page(language, titolo_pagina, contenuto, meta_extra="",
                head_extra="", script_extra="", feed_links=None,
                site_extra=None, page_kind="other", article_ids=()):
    """
    Wrap a page body in the shared public layout (templates/base.html).

    titolo_pagina is inserted as-is: the caller has already escaped the parts
    that come from the configuration or from an article.

    page_kind ("home", "article" or "other") and article_ids are what the
    custom code snippets are matched against. A caller that passes neither
    gets only the snippets scoped to the whole site, which is right for the
    tag, archive, card and 404 pages: no other scope names them.
    """
    head_extra = block(head_extra) + (
        "  <script>window.PB_SITE = "
        + js(site_options(language, site_extra)) + ";</script>")

    # Custom code goes LAST in its position: in the head after PB_SITE, so a
    # snippet can read it, and at the end of the body after the scripts of
    # the page, so a snippet can use what they define.
    head_extra = block(head_extra) + custom_code_block(
        "head", page_kind, article_ids)
    script_extra = block(script_extra) + custom_code_block(
        "body_end", page_kind, article_ids)
    body_open = custom_code_block("body_start", page_kind, article_ids)

    # The two visible slots of the shared layout. The third one, the end of
    # the article text, is filled by generate_article_page: it is the only
    # page that has such a place.
    after_header = custom_code_block("after_header", page_kind, article_ids)
    before_footer = custom_code_block("before_footer", page_kind, article_ids)
    nav_extra = custom_code_block("nav", page_kind, article_ids)
    if feed_links is None:
        feed_links = ('  <link rel="alternate" type="application/rss+xml" '
                      f'title="{esc(CONFIG["site_title"])}" href="{feed_url(language)}">\n')
    return render.render(
        "base.html",
        lang=language,
        favicon=favicon_link(),
        analytics=analytics_snippet(),
        titolo_pagina=titolo_pagina,
        meta_extra=block(meta_extra),
        feed_links=block(feed_links),
        head_extra=block(head_extra),
        body_open=block(body_open),
        header=site_header(language, nav_extra),
        after_header=block(after_header),
        contenuto=block(contenuto),
        before_footer=block(before_footer),
        footer=site_footer(language),
        script_extra=block(script_extra),
    )


# ---------------------------------------------------------------------------
# COMMENTS
# ---------------------------------------------------------------------------

def comments_block(art):
    """
    Generate the comments snippet based on CONFIG["comments"].
    It supports "giscus", "disqus" or "none".
    """
    sistema = CONFIG.get("comments", "none")

    if sistema == "giscus":
        g = CONFIG["giscus"]
        return render.render(
            "public/comments_giscus.html",
            repo=esc(g["repo"]),
            repo_id=esc(g["repo_id"]),
            category=esc(g["category"]),
            category_id=esc(g["category_id"]),
            theme=esc(g["theme"]),
            lingua=esc(CONFIG["language"]),
        ).rstrip("\n")

    if sistema == "disqus":
        d = CONFIG["disqus"]
        # Disqus identifies each thread with a unique URL and identifier.
        # Both cross into JavaScript, so both go through json.dumps.
        page_url = f"{CONFIG['base_url']}/posts/{art['slug']}.html"
        embed_url = f"https://{d['shortname']}.disqus.com/embed.js"
        return render.render(
            "public/comments_disqus.html",
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

    index_html = (
        '<nav class="table-of-contents"><p class="toc-title">' + T('indice', language) + '</p><ul>'
        + "\n".join(toc_items) + "</ul></nav>"
    )
    return modified_content, index_html


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

    post_prefix = language_url_prefix(language) + "/posts/"
    feed_items = []
    for art in visibili:
        feed_items.append(f"""    <a class="article-card" href="{post_prefix}{art['slug']}.html">
      <div class="card-date">{format_date(art['date'], language)}</div>
      <h3 class="card-title">{esc(title_in_language(art, language))}</h3>
      <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
    </a>""")

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


def generate_article_nav(art, all_articles, language="it"):
    """
    Generate the "newer / older article" navigation at the bottom of the
    article. The articles are already sorted newest first: the previous
    one in the list is the newer, the next one is the older.
    In the secondary language you only navigate between translated articles.
    """
    if all_articles is None:
        return ""
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
# ARTICLE PAGE
# ---------------------------------------------------------------------------

def generate_article_page(art, language="it", all_articles=None):
    """
    Generate the full HTML of a single article, with SEO and comments.
    The language parameter can be "it" or "en": in the secondary language it
    uses the translated fields and changes the addresses.
    """
    prefix = language_url_prefix(language)

    # We pick the right fields based on the requested language.
    if language == "en":
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
    content, toc_html = generate_table_of_contents(content, language)
    content = add_lazy_loading(content)

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
        og_image = (f'  <meta property="og:image" content="{esc(media_url(art["image"]))}">\n'
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
        jsonld_data["image"] = media_url(art["image"])
    if art.get("tags"):
        # The tags become the article's keywords.
        keywords = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                keywords.append(t)
        if len(keywords) > 0:
            jsonld_data["keywords"] = ", ".join(keywords)

    meta_extra = "\n".join(x for x in [
        f'  <meta name="description" content="{esc(description)}">',
        f'  <meta name="author" content="{esc(CONFIG["author"])}">',
        f'  <link rel="canonical" href="{page_url}">',
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

    contenuto = render.render(
        "public/article.html",
        language_switcher=language_switcher,
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=esc(title_value),
        data=format_date(art["date"], language),
        tempo_lettura=reading_time,
        tags_html=tags_html,
        copertina=block(cover_block),
        toc=toc_html,
        contenuto_articolo=content,
        codice_fine_testo=block(custom_code_block(
            "article_end", "article", article_snippet_ids(art))),
        author_box=generate_author_box(language),
        article_nav=generate_article_nav(art, all_articles, language),
        back_label=back_label,
        related=related_block,
        comments=comments_block(art),
    )

    return render_page(
        language,
        f"{esc(title_value)} &middot; {esc(CONFIG['site_title'])}",
        contenuto,
        meta_extra=meta_extra,
        head_extra=head_extra,
        script_extra='  <script src="https://cdn.jsdelivr.net/gh/highlightjs/'
                     'cdn-release@11.9.0/build/highlight.min.js"></script>',
        page_kind="article",
        article_ids=article_snippet_ids(art),
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
    published = []
    for card in CONFIG.get("home_cards", []):
        if not card.get("active", False):
            continue
        if html_content_is_empty(card.get("content", "")):
            continue
        published.append(card)
    return published


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


def card_preview_text(preview, content, description, length):
    """
    The text shown under a card title.

    Priority: what the author wrote, then an automatic excerpt of the article,
    then the SEO description as a last resort.
    """
    if preview != "":
        return preview
    excerpt = excerpt_from_html(content, length)
    if excerpt != "":
        return excerpt
    return description


def card_cover_image(art, title_value, css_class):
    """
    The thumbnail of an article for a listing, or an empty string.

    Every card uses it, so an article with a cover looks the same wherever it
    is listed. Until now only the highlighted block carried one, which made
    the newest article look different from the rest for a reason the reader
    could not see.
    """
    image_url = media_url(art.get("image", ""))
    if image_url == "":
        return ""
    return ('<img class="' + css_class + '" src="' + esc(image_url)
            + '" alt="' + esc(title_value) + '" loading="lazy">')


def generate_featured_article(art, language):
    """
    Render the most recent article as a larger block at the top of the list.

    The cover image is used here and nowhere else on the homepage: until now
    it only fed og:image and the structured data, so an author who filled it
    in saw nothing for it. When there is no image the block keeps the same
    markup and simply reads as a wider card, so it never looks half-finished.
    """
    prefix = language_url_prefix(language)
    title_value, description, content, preview = article_card_fields(art, language)

    cover = card_cover_image(art, title_value, "in-evidenza-copertina")
    if cover != "":
        cover = "        " + cover + NEWLINE

    # A longer excerpt than the ordinary cards get: this block has the room
    # for it, and it is what earns the extra space.
    excerpt = card_preview_text(preview, content, description, 340)

    tags_row = tag_links(art, language)
    if tags_row != "":
        tags_row = "      " + tags_row + "\n"

    return render.render(
        "public/home_featured.html",
        etichetta=T("ultimo_articolo", language),
        url=f"{prefix}/posts/{art['slug']}.html",
        copertina=cover,
        titolo=esc(title_value),
        data=format_date(art["date"], language),
        tempo_lettura=compute_reading_time(content, language),
        estratto=esc(excerpt),
        leggi=T("leggi_articolo", language),
        tags=tags_row,
    )


def generate_home_cards(language="it"):
    """
    Generate the homepage cards block. Each card is a link leading to its
    own dedicated page. It only shows the published cards, and nothing at all
    when the block is switched off.
    """
    prefix = language_url_prefix(language) + "/pagine/"
    if language == "en":
        open_label = "Open"
    else:
        open_label = "Apri"

    card_html = []
    for card in published_home_cards():
        content = card.get("content", "")
        title_value = card.get("title", "")
        slug = card_slug(title_value)
        excerpt = excerpt_from_html(content)
        card_html.append(f"""    <a class="home-card" href="{prefix}{slug}.html">
      <h3 class="home-card-title">{esc(title_value)}</h3>
      <p class="home-card-excerpt">{esc(excerpt)}</p>
      <span class="home-card-link">{open_label} &rarr;</span>
    </a>""")

    if len(card_html) == 0:
        return ""

    return render.render(
        "public/home_cards.html",
        titolo_sezione=T("esplora", language),
        lista="\n".join(card_html),
    )


def generate_card_page(card, language="it"):
    """
    Generate the HTML page of a single card (Biography, Projects, etc.)
    with a polished style: prominent header and readable content.
    """
    title_value = card.get("title", "")
    content = card.get("content", "")
    slug = card_slug(title_value)
    description = excerpt_from_html(content, 150)
    # The canonical must point to the version in the current language:
    # it used to always point to /pagine/, even from the English version,
    # declaring a wrong canonical to Google for the /en/ pages.
    prefix = language_url_prefix(language)
    url_canonico = f"{CONFIG['base_url']}{prefix}/pagine/{slug}.html"

    contenuto = render.render(
        "public/card_page.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        titolo=esc(title_value),
        contenuto_card=add_lazy_loading(content),
        torna_home=T("torna_homepage", language),
    )

    meta_extra = "\n".join([
        f'  <meta name="description" content="{esc(description)}">',
        f'  <link rel="canonical" href="{url_canonico}">',
        f'  <meta property="og:title" content="{esc(title_value)}">',
        '  <meta property="og:type" content="article">',
    ])

    return render_page(
        language,
        f"{esc(title_value)} &middot; {esc(CONFIG['site_title'])}",
        contenuto,
        meta_extra=meta_extra,
    )


# ---------------------------------------------------------------------------
# HOMEPAGE
# ---------------------------------------------------------------------------

def generate_homepage(articles, language="it", page=1, totale_pagine=1):
    """
    Generate the homepage: free content at the top + article grid + search.
    With language="en" it generates the English version in /en/ (UI texts and
    links translated). With page > 1 it generates the next pages
    (/pagina/2.html, /pagina/3.html...): the introduction and the cards only
    appear on page 1, the following pages show articles only.
    """
    # Link prefix, derived from the site's main language.
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

    # The most recent article gets its own block above the list, on the first
    # page only. It is REMOVED from the list rather than repeated in it: the
    # same article twice in a row reads as a mistake. The page still holds the
    # same number of articles, so the pagination maths is unchanged - only the
    # slice the browser restores when a search is cleared starts one later.
    featured_article = None
    if home_featured_enabled() and page == 1 and len(page_articles) > 0:
        featured_article = page_articles[0]
        page_articles = page_articles[1:]
        start = start + 1

    feed_items = []
    for art in page_articles:
        # The translated fields are always the _en ones (translation is IT<->EN).
        card_title, card_description, card_content, card_preview = \
            article_card_fields(art, language)

        # Short excerpt: 2-3 lines. A long excerpt turns every card into
        # a wall of text and makes the homepage impossible to scan.
        preview_text = card_preview_text(card_preview, card_content,
                                         card_description, 200)
        excerpt = ""
        if preview_text != "":
            excerpt = f'<p class="card-excerpt">{esc(preview_text)}</p>'

        # The card is a link, so the tags cannot be links inside it: nested
        # anchors are invalid HTML and browsers unnest them unpredictably.
        # They sit as a sibling row under the card instead.
        tags_row = tag_links(art, language)
        if tags_row != "":
            tags_row = "\n    " + tags_row

        thumbnail = card_cover_image(art, card_title, "card-copertina")
        if thumbnail != "":
            thumbnail = "      " + thumbnail + NEWLINE

        feed_items.append(f"""    <a class="article-card" href="{post_prefix}{art['slug']}.html">
{thumbnail}      <div class="card-corpo">
        <div class="card-date">{format_date(art['date'], language)}</div>
        <h3 class="card-title">{esc(card_title)}</h3>
        {excerpt}
        <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
      </div>
    </a>{tags_row}""")

    if len(feed_items) > 0:
        lista = "\n".join(feed_items)
    elif featured_article is not None:
        # Every article of this page went into the highlighted block, so the
        # list below is empty. That is not an empty blog: saying "no articles
        # published yet" right under an article would be plainly wrong.
        lista = ""
    else:
        lista = f'    <p class="no-articles">{T("nessun_articolo", language)}</p>'

    # Top of the home: free content written with the WYSIWYG (bio, images...).
    # For the secondary language we use the translated version (_en field), if any.
    if language != main_language():
        home_content = CONFIG.get("home_content_en", "")
        # If the translation is missing we fall back to the main content, so
        # the introduction shows anyway (better in Italian than empty).
        if html_content_is_empty(home_content):
            home_content = CONFIG.get("home_content", "")
    else:
        home_content = CONFIG.get("home_content", "")
    home_block = ""
    if not html_content_is_empty(home_content):
        # If the author has configured a photo of their own ("SEO and author
        # data" section), we show it as a round avatar at the top of the hero:
        # for a personal blog the face is the first element of trust.
        avatar = ""
        author_photo = seo_data().get("author_image", "")
        if author_photo != "":
            avatar = (f'<img class="home-avatar" src="{esc(author_photo)}" '
                      f'alt="{esc(CONFIG["author"])}" loading="lazy">\n    ')
        home_block = render.render(
            "public/home_intro.html",
            avatar=avatar,
            contenuto_intro=add_lazy_loading(home_content),
        )

    # Editorial cards (bio, projects, photos, notices).
    cards_block = generate_home_cards(language)

    # --- Navigation between pages (pagination) ---
    # It appears only if there is more than one page. The "newer" link on
    # page 2 goes back to the homepage, not to /pagina/1.html (which does not exist).
    pagination_block = ""
    if totale_pagine > 1:
        page_folder = pagination_folder(language)
        if page > 1:
            if page == 2:
                url_precedente = prefix + "/"
            else:
                url_precedente = f"{prefix}/{page_folder}/{page - 1}.html"
            link_precedente = f'<a href="{url_precedente}">{T("pagina_piu_recenti", language)}</a>'
        else:
            link_precedente = '<span class="paginazione-vuoto">&nbsp;</span>'
        if page < totale_pagine:
            url_successiva = f"{prefix}/{page_folder}/{page + 1}.html"
            link_successiva = f'<a href="{url_successiva}">{T("pagina_meno_recenti", language)}</a>'
        else:
            link_successiva = '<span class="paginazione-vuoto">&nbsp;</span>'
        pagination_block = render.render(
            "public/pagination.html",
            precedente=link_precedente,
            label_pagina=T("pagina_di", language),
            numero=page,
            label_su=T("pagina_su", language),
            totale=totale_pagine,
            successiva=link_successiva,
        )

    # --- Articles section (with search) as a standalone block ---
    featured_block = ""
    if featured_article is not None:
        featured_block = generate_featured_article(featured_article, language)

    articles_block = render.render(
        "public/home_articles.html",
        titolo_sezione=T("articles", language),
        placeholder_ricerca=esc(T("cerca_articoli", language)),
        aria_ricerca="Cerca",
        in_evidenza=block(featured_block),
        lista=lista,
        paginazione=block(pagination_block),
    )

    # --- Order of the homepage sections, configurable ---
    # The author can reorder "intro", "articles" and "cards" from the config
    # ("home_order" field) to give priority to what the reader should see
    # first. Sections not listed are appended at the end.
    blocks = {
        "intro": home_block,
        "articles": articles_block,
        "cards": cards_block,
    }
    # From page 2 on we only show the articles: the introduction and the
    # cards belong to the first page, repeating them would be noise.
    if page > 1:
        blocks["intro"] = ""
        blocks["cards"] = ""
    order = CONFIG.get("home_order", ["intro", "cards", "articles"])
    if not isinstance(order, list):
        order = ["intro", "cards", "articles"]
    home_body = []
    for section_name in order:
        if section_name in blocks:
            home_body.append(blocks.pop(section_name))
    # Sections forgotten in the order: we add them at the bottom anyway.
    for section_name in ("intro", "cards", "articles"):
        if section_name in blocks:
            home_body.append(blocks.pop(section_name))

    contenuto = render.render("public/home.html", sezioni="".join(home_body))

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
    search_options = {
        "post_prefix": post_prefix,
        "tag_prefix": prefix + "/tag/",
        "read_label": T("leggi_articolo", language),
        "msg_unavailable": T("js_search_unavailable", language),
        "msg_no_results": T("js_search_no_results", language),
        "msg_results_for": T("js_search_results_for", language),
        "page_start": start,
        "page_end": end,
    }

    head_extra = '  <script type="application/ld+json">' + jsonld_home + "</script>"

    return render_page(
        language,
        f"{esc(CONFIG['site_title'])} &middot; {esc(CONFIG['subtitle'])}",
        contenuto,
        meta_extra=meta_extra,
        head_extra=head_extra,
        site_extra=search_options,
        page_kind="home",
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

    contenuto = render.render(
        "public/archive.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_archivio=T("archivio", language),
        titolo_archivio=T("archivio_titolo", language),
        corpo=body,
    )

    meta_extra = "\n".join([
        f'  <meta name="description" content="{T("archivio_descrizione", language)}">',
        f'  <link rel="canonical" href="{url_canonico}">',
        "  " + hreflang,
        "  " + social_meta(language),
    ])

    return render_page(
        language,
        f"{T('archivio_titolo', language)} &middot; {esc(CONFIG['site_title'])}",
        contenuto,
        meta_extra=meta_extra,
    )


def generate_tag_page(tag_name, tag_articles, language="it"):
    """
    Generate the index page of a tag: it lists every article using it, as
    clickable cards, with the same design as the homepage.
    In the secondary language only the translated articles are listed.
    """
    prefix = language_url_prefix(language)
    post_prefix = prefix + "/posts/"

    feed_items = []
    count = 0
    for art in tag_articles:
        # In the secondary version we only show the translated articles.
        if language != main_language():
            if not art.get("translation_confirmed", False):
                continue
            card_title = art.get("title_en", "")
            card_description = art.get("description_en", "")
        else:
            card_title = art.get("title", "")
            card_description = art.get("description", "")

        count = count + 1
        excerpt = ""
        if card_description:
            excerpt = f'<p class="card-excerpt">{esc(card_description)}</p>'
        feed_items.append(f"""    <a class="article-card" href="{post_prefix}{art['slug']}.html">
      <div class="card-date">{format_date(art['date'], language)}</div>
      <h3 class="card-title">{esc(card_title)}</h3>
      {excerpt}
      <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
    </a>""")

    contenuto = render.render(
        "public/tag.html",
        url_home=prefix + "/",
        label_home=T("home", language),
        label_tag=T("tag", language),
        nome_tag=esc(tag_name),
        conteggio=count,
        label_conteggio=T("tag_conteggio", language),
        lista="\n".join(feed_items),
    )

    meta_extra = (f'  <meta name="description" '
                  f'content="{T("articoli_con_tag", language)} {esc(tag_name)}.">')

    return render_page(
        language,
        f"{T('articoli_con_tag', language)} {esc(tag_name)} &middot; {esc(CONFIG['site_title'])}",
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
        f"{T('pagina_non_trovata', language)} &middot; {esc(CONFIG['site_title'])}",
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
        }
        # We add the English data only if the translation is confirmed.
        translation_confirmed = art.get("translation_confirmed", False)
        content_en = art.get("content_en", "")
        if translation_confirmed and content_en.strip() != "":
            url_entry["has_en"] = True
            url_entry["title_en"] = art.get("title_en", "")
            url_entry["text_en"] = plain_text(content_en)
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
        f"{T('training_titolo', language)} &middot; {esc(CONFIG['site_title'])}",
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

    tutti = load_articles()
    published_articles = [a for a in tutti if a.get("status") == "published"]

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
        html_tag = generate_tag_page(tag_name, tag_articles, lp)
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
            html_tag_sec = generate_tag_page(tag_name, tag_articles, ls)
            write_page(OUTPUT_DIR / sec_folder / "tag" / f"{tag_slug}.html",
                       html_tag_sec)

    # Pages of the published cards (Biography, Projects, About...). A card
    # switched off, or left empty, or with the whole block switched off, has
    # no page: the sweep at the end of build() then removes the file it had.
    for card in published_home_cards():
        slug = card_slug(card.get("title", ""))
        # Cards in the main language (at the root).
        write_page(OUTPUT_DIR / "pagine" / f"{slug}.html",
                   generate_card_page(card, lp))
        # Cards in the secondary language.
        (OUTPUT_DIR / sec_folder / "pagine").mkdir(parents=True, exist_ok=True)
        write_page(OUTPUT_DIR / sec_folder / "pagine" / f"{slug}.html",
                   generate_card_page(card, ls))

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
