"""
Configuration of the blog: default values, the config.json file, migration of
the old Italian schema and the language layout of the public site.

CONFIG is a module-level dictionary that everything else imports. It is
updated IN PLACE by reload_global_config(), never rebound, so a module that
did "from core.config import CONFIG" always sees the current values.
"""
import json
import os
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
POSTS_DIR = BASE_DIR / "posts"          # articles are stored here as JSON
OUTPUT_DIR = BASE_DIR / "output"        # the static HTML ends up here (nginx serves it)
MEDIA_DIR = OUTPUT_DIR / "media"        # uploaded videos end up here
CONFIG_FILE = BASE_DIR / "config.json"  # the site configuration is stored here
TEMPLATES_DIR = BASE_DIR / "templates"  # .html templates
STATIC_DIR = BASE_DIR / "static"        # .css and .js sources
PASSWORD_FILE = BASE_DIR / "admin_password.txt"
PORT = 8000



# Default configuration. Used only the first time, until you save
# your own configuration from the "Settings" page in the editor.
CONFIG_DEFAULT = {
    "site_title": "Inside the Machine",
    "subtitle": "Note tecniche su AI, sistemi distribuiti e dintorni",
    "author": "Giuseppe Ciuni",
    "base_url": "https://tuodominio.com",
    # Google Analytics 4 measurement ID (e.g. "G-XXXXXXXXXX").
    # Empty means no analytics script on the public pages.
    "analytics_id": "",
    # Self-hosted Umami analytics: base URL of the instance and
    # website UUID. Both empty means Umami is disabled.
    "umami_url": "",
    "umami_website_id": "",

    # Custom code injected into the public pages: tracking pixels, chat
    # widgets, embeds. Each entry is a dictionary:
    #
    #   id        stable identifier, generated once and never reused. The
    #             articles refer to a snippet by this, so renaming one does
    #             not detach it from the articles that enabled it.
    #   name      label shown in the admin, free text.
    #   enabled   False parks a snippet without deleting it.
    #   position  "head", "body_start" or "body_end".
    #   scope     "home"          -> homepage only
    #             "home_articles" -> homepage and every article
    #             "home_optin"    -> homepage, plus the articles that tick it
    #   code      the HTML/JS, injected verbatim.
    "custom_code": [],

    "language": "it",
    # Language of the administration interface (it or en).
    "admin_language": "it",

    # Free-form content of the top of the homepage (written with the WYSIWYG).
    # This is where the biography, aligned images, videos, etc. go.
    # This is a presentable starting content: it shows until you
    # customise it from Settings > Homepage.
    "home_content": (
        '<h2 class="ql-align-center">Benvenuto su Inside the Machine</h2>'
        '<p class="ql-align-center">Un blog tecnico su intelligenza artificiale, '
        'sistemi distribuiti e sviluppo software.</p>'
        '<p class="ql-align-center">Qui trovi articoli, guide e appunti pensati '
        'per chi costruisce con la tecnologia.</p>'
        '<p class="ql-align-center"><strong>Scorri in basso per leggere gli ultimi articoli.</strong></p>'
        '<p><br></p>'
        '<p>Per personalizzare questa presentazione, vai in '
        '<em>Impostazioni &rsaquo; Home page</em> nell\'amministrazione: puoi scrivere la tua '
        'biografia, aggiungere una foto, cambiare i testi e impostare il titolo del sito.</p>'
    ),
    # English version of the homepage introduction. If empty, the English
    # home shows the Italian version above.
    "home_content_en": (
        '<h2 class="ql-align-center">Welcome to Inside the Machine</h2>'
        '<p class="ql-align-center">A technical blog about artificial intelligence, '
        'distributed systems and software development.</p>'
        '<p class="ql-align-center">Here you will find articles, guides and notes '
        'for those who build with technology.</p>'
        '<p class="ql-align-center"><strong>Scroll down to read the latest articles.</strong></p>'
        '<p><br></p>'
        '<p>To customize this introduction, go to '
        '<em>Settings &rsaquo; Homepage</em> in the admin area: you can write your '
        'biography, add a photo, change the texts and set the site title.</p>'
    ),

    # Comment system: "nessuno" (none), "giscus" or "disqus".
    "comments": "none",

    "giscus": {
        "repo": "tuonome/tuorepo",
        "repo_id": "R_xxxxxxxx",
        "category": "Comments",
        "category_id": "DIC_xxxxxxxx",
        "theme": "light",
    },

    "disqus": {
        "shortname": "tuo-shortname",
    },

    # --- Automatic translation IT -> EN ---
    # Choose the service: "deepl", "google" or "llm".
    # API keys are entered from the Settings page and stay on the
    # server (never exposed to the public).
    "translation": {
        "service": "deepl",
        "deepl_api_key": "",
        "google_api_key": "",
        "llm_api_key": "",
        "llm_endpoint": "https://api.anthropic.com/v1/messages",
        "llm_model": "claude-sonnet-4-6",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "deepseek_api_key": "",
        "deepseek_model": "deepseek-chat",
    },

    # --- Personal data for SEO (E-E-A-T, schema.org Person) ---
    # This data feeds the JSON-LD structured data and the social meta tags.
    # Filling it in helps Google link the articles to a real author.
    "seo": {
        # External site that republishes the articles and hosts the
        # backlinks towards this blog (used by the SEO analysis).
        "backlink_site": "startupbusiness.it",
        # URL of your personal or professional page (site, LinkedIn...).
        "author_url": "",
        # Absolute URL of a photo of you (used in the Person schema).
        "author_image": "",
        # Short professional bio (1-2 sentences, used in the Person schema).
        "author_bio": "",
        # Job title/role (e.g. "CTO and lecturer"). The jobTitle field of schema.org.
        "author_role": "",
        # List of your public profiles (sameAs): GitHub, LinkedIn, X, etc.
        # Example: ["https://github.com/yourname", "https://linkedin.com/in/yourname"]
        "social_profiles": [],
        # Absolute URL of the site logo (for the publisher schema).
        "logo": "",
        # The site's X/Twitter account, with the at sign (e.g. "@yourname").
        "twitter_site": "",
        # URL of a custom favicon. If empty, PyBlog generates one
        # automatically with the initial of the site title (favicon.svg).
        "favicon": "",
    },

    # --- AI training rights ---
    # Lets the author declare whether AI/LLM companies may use this
    # content to train their models, and where to reach out for a paid
    # licence if not. Reflected in robots.txt (known AI crawlers),
    # llms.txt, a dedicated /.well-known/ai.txt file, a best-effort
    # /.well-known/tdmrep.json (TDM Reservation Protocol), and a plain
    # language /training-rights.html page.
    "ai_training": {
        # "open": no restriction, AI crawlers are welcome like any other.
        # "licensed": crawling is blocked for known AI/LLM bots in
        #   robots.txt; a licence is required for training use; contact
        #   details are published for anyone who wants to negotiate one.
        # "disallow": crawling is blocked, no licence is offered either.
        "policy": "open",
        # Contact for licensing inquiries (shown on the rights page, in
        # llms.txt and in ai.txt). Leave empty to show no contact.
        "contact_email": "",
        # Optional: a URL with your own full licensing terms. If empty,
        # PyBlog's own /training-rights.html page is used instead.
        "license_url": "",
        # Optional free-text statement overriding the default wording.
        "statement": "",
    },

    # Kept for old configurations, no longer read. It ordered the three
    # stacked sections of the single-column homepage ("intro", "cards",
    # "articles"); the two-column layout has the articles in the main column
    # and the rest in the sidebar, so there is no order left to choose.
    "home_order": ["intro", "cards", "articles"],

    # Where the free introduction of the homepage (home_content) goes:
    # "sidebar" puts it in the first box of the sidebar, so the articles
    # start at the top of the page; "top" puts it above the articles, as a
    # short presentation across the main column.
    "home_intro_position": "sidebar",

    # How many words of an article the lists show when the author has not
    # written a preview: the opening of the article, cut at a word boundary.
    "home_excerpt_words": 40,

    # Highlight the most recent article in a larger block at the top of the
    # article list, with its cover image when it has one. With False the
    # homepage is a plain list, as it was before.
    "home_featured": True,

    # Widest an uploaded image is kept at, in pixels. The article column is
    # 720px and the cover is capped at 340px tall, so 1600 covers a
    # high-density screen at twice the size. Larger uploads are downscaled,
    # in the browser before they are sent and on the server for the images
    # pulled out of a Word document. 0 disables it and keeps every upload at
    # its original size.
    "max_image_width": 1600,

    # Show the cover image inside the article page as well, under the title
    # and the date. With False the cover only appears in the listings and in
    # the social preview, and the article opens straight on its first line.
    "article_cover": True,

    # Number of articles shown on each page of the homepage.
    # The next pages are generated at /pagina/2.html, /pagina/3.html...
    # With 0, pagination is disabled: all articles on a single page.
    "articles_per_page": 10,

    # Master switch of the cards block. With False the whole block
    # disappears from the homepage, whatever each card says: it is the way
    # to put the section aside for a while without having to switch off the
    # cards one by one and switch them back on later.
    "home_cards_enabled": True,

    # Editorial cards of the homepage, shown below the introduction.
    # Each card has a title and HTML content (written with the editor).
    # You can enable/disable and edit them from the Settings page.
    # The biography and the projects have sections of their own (below), so
    # they are not among the starting cards: they would show twice.
    "home_cards": [
        {
            "active": True,
            "title": "Informazioni in evidenza",
            "content": "<p>Metti qui le informazioni che vuoi mettere in evidenza: contatti, link utili, o una galleria di immagini.</p>",
        },
        {
            "active": False,
            "title": "Comunicazioni di servizio",
            "content": "<p>Usa questo spazio per avvisi importanti ai lettori.</p>",
        },
    ],

    # The biography: a few lines and the photo on the homepage, with a link
    # to the page that holds it whole. position is "sidebar", "top" (above
    # the articles) or "bottom" (below them). Off until the author turns it on.
    "biography": {
        "enabled": False,
        "position": "sidebar",
        "photo": "",
        "content": "",
        "content_en": "",
    },

    # The projects: one card each, in a grid on the homepage (a list when
    # they sit in the sidebar). Every item has name, description,
    # description_en, url, image and visible; the order of the list is the
    # order on the page. Off until the author turns it on.
    "projects": {
        "enabled": False,
        "position": "top",
        "items": [],
    },

    # The row of links at the end of an article that hands it to LinkedIn,
    # Hacker News, Reddit or X, and copies its address. They are plain
    # links: nothing is loaded from those sites until the reader clicks.
    "share_buttons": True,

    # "Work with me": a button in the menu of every page and an invitation
    # at the end of every article, both leading to url - a page of the site,
    # a mailto: address, a profile. Empty label and text use the defaults.
    "work_with_me": {
        "enabled": False,
        "url": "",
        "label": "",
        "label_en": "",
        "text": "",
        "text_en": "",
    },
}


# ---------------------------------------------------------------------------
# SCHEMA MIGRATION (Italian keys -> English keys)
# ---------------------------------------------------------------------------
# Up to this version, config.json and the article JSON files used Italian
# keys ("title", "contenuto", "status"...). The functions below detect the
# old format when loading, convert it to the new English schema and rewrite


OLD_ARTICLE_KEYS = {
    "titolo": "title", "descrizione": "description", "anteprima": "preview",
    "contenuto": "content", "tag": "tags", "immagine": "image", "stato": "status",
    "data": "date", "data_modifica": "date_modified",
    "titolo_en": "title_en", "descrizione_en": "description_en",
    "anteprima_en": "preview_en", "contenuto_en": "content_en",
    "traduzione_autorizzata": "translation_authorized",
    "traduzione_confermata": "translation_confirmed",
    "slug_originale": "original_slug",
}
OLD_STATUS_VALUES = {"pubblicato": "published", "bozza": "draft"}

OLD_CONFIG_KEYS = {
    "titolo_sito": "site_title", "sottotitolo": "subtitle", "autore": "author",
    "lingua": "language", "lingua_admin": "admin_language",
    "home_contenuto": "home_content", "home_contenuto_en": "home_content_en",
    "commenti": "comments", "traduzione": "translation",
    "ordine_home": "home_order", "articoli_per_pagina": "articles_per_page",
    "card_home": "home_cards",
}
OLD_TRANSLATION_KEYS = {"servizio": "service", "llm_modello": "llm_model",
                        "openai_modello": "openai_model", "deepseek_modello": "deepseek_model"}
OLD_SEO_KEYS = {"autore_url": "author_url", "autore_immagine": "author_image",
                "autore_bio": "author_bio", "autore_ruolo": "author_role",
                "profili_social": "social_profiles"}
OLD_CARD_KEYS = {"attiva": "active", "titolo": "title", "contenuto": "content"}
OLD_SECTION_VALUES = {"articoli": "articles", "card": "cards"}
OLD_COMMENT_VALUES = {"nessuno": "none"}


def migrate_article_schema(data):
    """
    Convert an article dictionary from the old Italian schema to the new
    English one. Return (converted_dict, was_migrated). Dictionaries
    already in the new format come back untouched.
    """
    if not any(k in data for k in OLD_ARTICLE_KEYS):
        return data, False
    converted = {}
    for key in data:
        converted[OLD_ARTICLE_KEYS.get(key, key)] = data[key]
    if converted.get("status") in OLD_STATUS_VALUES:
        converted["status"] = OLD_STATUS_VALUES[converted["status"]]
    return converted, True


def migrate_config_schema(data):
    """
    Convert a configuration dictionary from the old Italian schema to the
    new English one, including nested sections (translation, seo, cards)
    and the values that changed name (status of comments, section order).
    Return (converted_dict, was_migrated).
    """
    nested_old = (isinstance(data.get("traduzione"), dict)
                  or isinstance(data.get("seo"), dict) and any(k in data["seo"] for k in OLD_SEO_KEYS))
    if not any(k in data for k in OLD_CONFIG_KEYS) and not nested_old:
        return data, False

    converted = {}
    for key in data:
        converted[OLD_CONFIG_KEYS.get(key, key)] = data[key]

    # Nested: translation service and model names.
    if isinstance(converted.get("translation"), dict):
        old_config = converted["translation"]
        converted["translation"] = {OLD_TRANSLATION_KEYS.get(k, k): old_config[k] for k in old_config}

    # Nested: seo (author data).
    if isinstance(converted.get("seo"), dict):
        old_config = converted["seo"]
        converted["seo"] = {OLD_SEO_KEYS.get(k, k): old_config[k] for k in old_config}

    # Nested: homepage cards.
    if isinstance(converted.get("home_cards"), list):
        nuove = []
        for card in converted["home_cards"]:
            if isinstance(card, dict):
                nuove.append({OLD_CARD_KEYS.get(k, k): card[k] for k in card})
            else:
                nuove.append(card)
        converted["home_cards"] = nuove

    # Values: comment system and homepage section order.
    if converted.get("comments") in OLD_COMMENT_VALUES:
        converted["comments"] = OLD_COMMENT_VALUES[converted["comments"]]
    if isinstance(converted.get("home_order"), list):
        converted["home_order"] = [OLD_SECTION_VALUES.get(v, v) for v in converted["home_order"]]

    return converted, True


# ---------------------------------------------------------------------------
# AI TRAINING RIGHTS
# ---------------------------------------------------------------------------
# User-agent strings of the crawlers used by AI/LLM companies to gather
# training data, as best known at the time of writing. This is NOT an
# official or exhaustive list, and crawler names change over time: it is a
# good-faith, best-effort set covering the major current operators. None of
# this is a legally binding standard - a crawler is only as compliant as its

def write_json_atomically(path_value, data):
    """
    Write a JSON file so that it is either the old version or the new one,
    never half of each.

    Writing straight into the file truncates it first: a crash, a full disk
    or a killed process in the middle leaves a file that is no longer valid
    JSON, and for config.json that used to mean a site that would not even
    start. The data goes to a temporary file next to the real one, is pushed
    to disk, and only then takes the real name in a single rename, which the
    operating system performs as one step.
    """
    path_value = Path(path_value)
    path_value.parent.mkdir(parents=True, exist_ok=True)
    # The temporary name ends in .tmp, so the "*.json" listing of the posts
    # folder never mistakes a half-written file for an article.
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path_value.parent), prefix="." + path_value.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temporary, path_value)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


# Where a config.json that cannot be read is set aside. It is never
# overwritten: the first broken copy is the one worth recovering by hand.
BROKEN_CONFIG_FILE = BASE_DIR / "config.broken.json"


def set_broken_config_aside(reason):
    """
    Keep a copy of an unreadable config.json and say so on the console.

    The site then starts on the default values instead of refusing to start
    at all. Without the copy, the next save from the Settings page would
    write the defaults over the file and whatever was still recoverable in
    it would be gone.
    """
    print(f"WARNING: config.json cannot be read ({reason}). "
          "The site is running on the default settings.")
    if BROKEN_CONFIG_FILE.exists():
        return
    try:
        BROKEN_CONFIG_FILE.write_bytes(CONFIG_FILE.read_bytes())
        print(f"A copy of the unreadable file is in {BROKEN_CONFIG_FILE.name}.")
    except OSError:
        pass


def load_config():
    """
    Load the configuration from the config.json file.
    If the file does not exist, it returns the default values.
    If some fields are missing, it completes them with the defaults
    (useful after an update).
    """
    if not CONFIG_FILE.exists():
        return dict(CONFIG_DEFAULT)

    try:
        with open(CONFIG_FILE, encoding="utf-8") as fp:
            saved_config = json.load(fp)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        set_broken_config_aside(error)
        return dict(CONFIG_DEFAULT)
    if not isinstance(saved_config, dict):
        set_broken_config_aside("it is not a JSON object")
        return dict(CONFIG_DEFAULT)

    # Old Italian schema detected: convert it and rewrite the file once,
    # so the migration happens transparently on the first load.
    saved_config, migrata = migrate_config_schema(saved_config)
    if migrata:
        write_json_atomically(CONFIG_FILE, saved_config)
        print("config.json migrated to the new English schema.")

    # We start from the defaults and overwrite with the saved values.
    # This way, if we add a field later, old configs stay valid.
    config_finale = dict(CONFIG_DEFAULT)
    for key in saved_config:
        default_value = CONFIG_DEFAULT.get(key)
        saved_value = saved_config[key]
        # If both the default and the saved value are dictionaries, we merge them:
        # this way a new sub-field added later is not lost.
        if isinstance(default_value, dict) and isinstance(saved_value, dict):
            merged = dict(default_value)
            for sub_key in saved_value:
                merged[sub_key] = saved_value[sub_key]
            config_finale[key] = merged
        else:
            config_finale[key] = saved_value
    return config_finale


def save_config(new_config):
    """Save the site configuration to the config.json file."""
    write_json_atomically(CONFIG_FILE, new_config)


# Global variable holding the current configuration.

# Global dictionary holding the current configuration. It is reloaded from
# the file at the start of every site build. Modules import this object, so it
# is refilled in place instead of being replaced.
CONFIG = dict(CONFIG_DEFAULT)
CONFIG.update(load_config())


def reload_global_config():
    """Reload the global configuration from the file (after a save)."""
    fresh = load_config()
    CONFIG.clear()
    CONFIG.update(fresh)


# ---------------------------------------------------------------------------
# LANGUAGE ARCHITECTURE OF THE PUBLIC SITE
# ---------------------------------------------------------------------------
# The "main" language (set in CONFIG["language"]) sits at the root "/".
# The other language (the "secondary" one) sits in a subfolder: /en/ or /it/.
# All the generation functions derive their link prefixes from here, so that
# changing a single setting flips the whole site consistently.

def main_language():
    """The language of the site at the root (it or en). Default: it."""
    language = CONFIG.get("language", "it")
    if language not in ("it", "en"):
        return "it"
    return language


def secondary_language():
    """The other language, the one that lives in a subfolder."""
    if main_language() == "it":
        return "en"
    return "it"


def language_url_prefix(language):
    """
    Return the URL prefix for a language.
    The main language sits at the root (empty prefix), the secondary one
    sits in its own subfolder (e.g. "/en" or "/it").
    """
    if language == main_language():
        return ""
    return "/" + language


def language_subfolder(language):
    """
    Return the output subfolder for a language.
    Empty for the main language, "en"/"it" for the secondary one.
    """
    if language == main_language():
        return ""
    return language


def admin_language():
    """Return the current language of the admin interface (it or en)."""
    language = CONFIG.get("admin_language", "it")
    if language not in ("it", "en"):
        return "it"
    return language


def archive_file_name(language):
    """Name of the archive file in the given language."""
    if language == "en":
        return "archive.html"
    return "archivio.html"


def feed_file_name(language):
    """
    Name of the RSS file of a language. The main language keeps the historical
    /rss.xml, so existing subscriptions never break; the secondary language
    gets its own feed next to it.
    """
    if language == main_language():
        return "rss.xml"
    return "rss-" + language + ".xml"


def pagination_folder(language):
    """Name of the folder holding the next pages ("pagina" or "page")."""
    if language == "en":
        return "page"
    return "pagina"


def articles_per_page_count():
    """
    Read from the config how many articles to show per homepage page.
    With 0 (or an invalid, negative value) pagination is disabled.
    """
    value = CONFIG.get("articles_per_page", 10)
    try:
        value = int(value)
    except (ValueError, TypeError):
        value = 10
    if value < 0:
        value = 0
    return value


def seo_data():
    """Return the 'seo' block of the configuration (always a dict)."""
    seo = CONFIG.get("seo", {})
    if not isinstance(seo, dict):
        return {}
    return seo


def ai_training_config():
    """Return the 'ai_training' block of the configuration (always a dict)."""
    value = CONFIG.get("ai_training", {})
    if not isinstance(value, dict):
        return {}
    return value


def secret_setting(translation_config, key_name):
    """
    Return an API key, preferring an environment variable over config.json.
    The variable name is "PYBLOG_" plus the key name in upper case
    (e.g. PYBLOG_LLM_API_KEY overrides translation.llm_api_key).
    On an internet-facing server this lets the key live in the systemd
    unit instead of a file on disk, and keeps it out of the Settings
    page, which only ever shows what is written in config.json.
    """
    env_name = "PYBLOG_" + key_name.upper()
    env_value = os.environ.get(env_name, "").strip()
    if env_value != "":
        return env_value
    return translation_config.get(key_name, "")
