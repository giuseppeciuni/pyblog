#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyBlog - generatore di blog statico in Python puro (solo libreria standard).

Due modalita':
  python3 pyblog.py serve     -> avvia l'editor WYSIWYG su http://localhost:8000
  python3 pyblog.py build     -> rigenera tutto l'HTML statico da riga di comando

Filosofia: stile antirez. Zero dipendenze esterne, HTML leggero, pagine statiche
servite poi da nginx. I commenti sono delegati a Giscus (GitHub Discussions).
"""
import json
import os
import sys
import re
import html
import html.parser
import http.server
import socketserver
import urllib.parse
import hashlib
import secrets
import base64
import time
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# CONFIGURATION - edit these values
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"        # articles are stored here as JSON
OUTPUT_DIR = BASE_DIR / "output"      # the static HTML ends up here (nginx serves it)
MEDIA_DIR = OUTPUT_DIR / "media"      # uploaded videos end up here
CONFIG_FILE = BASE_DIR / "config.json"  # the site configuration is stored here
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
    "language": "it",
    # Language of the administration interface (it or en).
    "admin_language": "it",

    # Free-form content of the top of the homepage (written with the WYSIWYG).
    # This is where the biography, aligned images, videos, etc. go.
    # This is a presentable starting content: it shows until you
    # customise it from the "Settings and homepage" page.
    "home_content": (
        '<h2 class="ql-align-center">Benvenuto su Inside the Machine</h2>'
        '<p class="ql-align-center">Un blog tecnico su intelligenza artificiale, '
        'sistemi distribuiti e sviluppo software.</p>'
        '<p class="ql-align-center">Qui trovi articoli, guide e appunti pensati '
        'per chi costruisce con la tecnologia.</p>'
        '<p class="ql-align-center"><strong>Scorri in basso per leggere gli ultimi articoli.</strong></p>'
        '<p><br></p>'
        '<p>Per personalizzare questa presentazione, vai nella pagina '
        '<em>Impostazioni e homepage</em> della redazione: puoi scrivere la tua '
        'biografia, aggiungere una foto, cambiare i testi e impostare il titolo del site.</p>'
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
        '<p>To customize this introduction, go to the '
        '<em>Settings and homepage</em> page in the admin area: you can write your '
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

    # Order of the homepage sections, from top to bottom.
    # Possible values: "intro" (introduction), "articoli", "card".
    # Default: introduction, then the cards (who you are, projects), then
    # the articles. Reorder the list to change the page structure.
    "home_order": ["intro", "cards", "articles"],

    # Number of articles shown on each page of the homepage.
    # The next pages are generated at /pagina/2.html, /pagina/3.html...
    # With 0, pagination is disabled: all articles on a single page.
    "articles_per_page": 10,

    # Editorial cards of the homepage, shown below the introduction.
    # Each card has a title and HTML content (written with the editor).
    # You can enable/disable and edit them from the Settings page.
    "home_cards": [
        {
            "active": True,
            "title": "Biografia",
            "content": "<p>Racconta qui chi sei, la tua esperienza e di cosa ti occupi.</p>",
        },
        {
            "active": True,
            "title": "Progetti",
            "content": "<p>Elenca qui i tuoi progetti principali, con una breve descrizione di ciascuno.</p>",
        },
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
}


# ---------------------------------------------------------------------------
# SCHEMA MIGRATION (Italian keys -> English keys)
# ---------------------------------------------------------------------------
# Up to this version, config.json and the article JSON files used Italian
# keys ("title", "contenuto", "status"...). The functions below detect the
# old format when loading, convert it to the new English schema and rewrite
# the file, so existing blogs keep working with no manual step.

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


def _ai_training_config():
    """Return the 'ai_training' block of the configuration (always a dict)."""
    value = CONFIG.get("ai_training", {})
    if not isinstance(value, dict):
        return {}
    return value


def _ai_training_statement(language="it"):
    """
    Return the human-readable statement describing the training policy, in
    the given language. Uses the author's custom text if provided, otherwise
    a default wording that matches the chosen policy.
    """
    training = _ai_training_config()
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
    policy = _ai_training_config().get("policy", "open")
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
    training = _ai_training_config()
    policy = training.get("policy", "open")
    lines = [
        "# ai.txt - AI training rights statement",
        "# This is an informal convention, not a binding legal standard.",
        "",
        "Policy: " + policy,
        "",
        _ai_training_statement("en"),
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
    training = _ai_training_config()
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
    training = _ai_training_config()
    policy = training.get("policy", "open")
    contatto = training.get("contact_email", "").strip()
    licenza_url = training.get("license_url", "").strip()
    statement = html.escape(_ai_training_statement(language))

    contact_block = ""
    if policy == "licensed" and contatto != "":
        contact_block = (f'<p>{T("training_contatto", language)} '
                           f'<a href="mailto:{html.escape(contatto)}">{html.escape(contatto)}</a></p>')

    license_block = ""
    if licenza_url != "":
        license_block = (f'<p>{T("training_termini_propri", language)} '
                          f'<a href="{html.escape(licenza_url)}">{html.escape(licenza_url)}</a></p>')

    home_url_language = language_url_prefix(language) + "/"
    base = CONFIG["base_url"].rstrip("/")
    url_canonico = base + language_url_prefix(language) + "/training-rights.html"

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{T('training_titolo', language)} &middot; {html.escape(CONFIG['site_title'])}</title>
  <meta name="description" content="{statement}">
  <meta name="robots" content="noindex, follow">
  <link rel="canonical" href="{url_canonico}">
  <link rel="stylesheet" href="/style.css">
  {_theme_script()}
</head>
<body>
  {_site_header(language)}
  <main id="content" class="main-content">
    <article class="post">
      <p class="breadcrumbs"><a href="{home_url_language}">{T('home', language)}</a> &rsaquo; {T('training_titolo', language)}</p>
      <h1>{T('training_titolo', language)}</h1>
      <p>{statement}</p>
      {contact_block}
      {license_block}
    </article>
  </main>
  {_site_footer(language)}
</body>
</html>"""


def load_config():
    """
    Load the configuration from the config.json file.
    If the file does not exist, it returns the default values.
    If some fields are missing, it completes them with the defaults
    (useful after an update).
    """
    if not CONFIG_FILE.exists():
        return dict(CONFIG_DEFAULT)

    with open(CONFIG_FILE, encoding="utf-8") as fp:
        saved_config = json.load(fp)

    # Old Italian schema detected: convert it and rewrite the file once,
    # so the migration happens transparently on the first load.
    saved_config, migrata = migrate_config_schema(saved_config)
    if migrata:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            json.dump(saved_config, fp, ensure_ascii=False, indent=2)
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
    with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
        json.dump(new_config, fp, ensure_ascii=False, indent=2)


# Global variable holding the current configuration.
# It is reloaded from the file at the start of every site build.
CONFIG = load_config()


def reload_global_config():
    """Reload the global configuration from the file (after a save)."""
    global CONFIG
    CONFIG = load_config()


# ---------------------------------------------------------------------------
# INTERFACE INTERNATIONALISATION (i18n)
# ---------------------------------------------------------------------------
# All the fixed labels of the public site (not the content written by the author)
# are collected here in Italian and English. The T() function returns the
# right version based on the page language.

UI_TRANSLATIONS = {
    "leggi_articolo": {"it": "Leggi l'articolo", "en": "Read the article"},
    "articles": {"it": "Articoli", "en": "Articles"},
    "home": {"it": "Home", "en": "Home"},
    "esplora": {"it": "Esplora", "en": "Explore"},
    "articoli_correlati": {"it": "Articoli correlati", "en": "Related articles"},
    "indice": {"it": "Indice", "en": "Contents"},
    "torna_homepage": {"it": "Torna alla homepage", "en": "Back to homepage"},
    "tutti_articoli": {"it": "Tutti gli articoli", "en": "All articles"},
    "cerca_articoli": {"it": "Cerca negli articoli...", "en": "Search articles..."},
    "nessun_articolo": {"it": "Ancora nessun articolo pubblicato.", "en": "No articles published yet."},
    "nessun_risultato": {"it": "Nessun articolo trovato.", "en": "No articles found."},
    "min_lettura": {"it": "min di lettura", "en": "min read"},
    "pagina_non_trovata": {"it": "Pagina non trovata", "en": "Page not found"},
    "errore_404": {"it": "La pagina che cerchi non esiste o e' stata spostata.",
                   "en": "The page you are looking for does not exist or has been moved."},
    "tag_conteggio": {"it": "articolo/i con questo tag.", "en": "article(s) with this tag."},
    "tag": {"it": "Tag", "en": "Tag"},
    "articoli_con_tag": {"it": "Articoli su", "en": "Articles about"},
    # Archive by year
    "archivio": {"it": "Archivio", "en": "Archive"},
    "archivio_titolo": {"it": "Archivio degli articoli", "en": "Article archive"},
    "archivio_descrizione": {"it": "Tutti gli articoli del blog, raggruppati per anno.",
                             "en": "All blog articles, grouped by year."},
    # Homepage pagination
    "pagina_piu_recenti": {"it": "&larr; Piu' recenti", "en": "&larr; Newer"},
    "pagina_meno_recenti": {"it": "Meno recenti &rarr;", "en": "Older &rarr;"},
    "pagina_di": {"it": "Pagina", "en": "Page"},
    "pagina_su": {"it": "di", "en": "of"},
    # Author box and navigation between articles
    "scritto_da": {"it": "Scritto da", "en": "Written by"},
    "nav_piu_recente": {"it": "Piu' recente", "en": "Newer"},
    "nav_meno_recente": {"it": "Meno recente", "en": "Older"},
    "salta_contenuto": {"it": "Salta al contenuto", "en": "Skip to content"},
    # Messaggi di stato del JavaScript admin
    "js_translating": {"it": "Traduzione in corso...", "en": "Translating..."},
    "js_generating": {"it": "Generazione in corso...", "en": "Generating..."},
    "js_error_prefix": {"it": "Errore: ", "en": "Error: "},
    "js_net_error_translation": {"it": "Errore di rete durante la traduzione.", "en": "Network error during translation."},
    "js_net_error_generation": {"it": "Errore di rete durante la generazione.", "en": "Network error during generation."},
    "js_translated_review": {"it": "Traduzione completata. Rivedila e poi confermala.", "en": "Translation completed. Review it, then confirm it."},
    "js_translated_home": {"it": "Tradotta: rivedila e modificala come preferisci.", "en": "Translated: review it and edit it as you like."},
    "js_check_api_key": {"it": " (controlla la chiave API nelle Impostazioni)", "en": " (check the API key in the Settings)"},
    "js_delete_confirm": {"it": "Eliminare definitivamente questo articolo?", "en": "Permanently delete this article?"},
    "js_delete_named": {"it": "Eliminare definitivamente", "en": "Permanently delete"},
    # Toolbar tooltips for the editor (a small bubble on mouse hover)
    "tip_font": {"it": "Tipo di carattere", "en": "Font family"},
    "tip_size": {"it": "Dimensione del testo", "en": "Text size"},
    "tip_header": {"it": "Titolo di sezione (H1-H4)", "en": "Section heading (H1-H4)"},
    "tip_bold": {"it": "Grassetto (Ctrl+B)", "en": "Bold (Ctrl+B)"},
    "tip_italic": {"it": "Corsivo (Ctrl+I)", "en": "Italic (Ctrl+I)"},
    "tip_underline": {"it": "Sottolineato (Ctrl+U)", "en": "Underline (Ctrl+U)"},
    "tip_strike": {"it": "Barrato", "en": "Strikethrough"},
    "tip_color": {"it": "Colore del testo", "en": "Text colour"},
    "tip_background": {"it": "Colore di sfondo (evidenziatore)", "en": "Background colour (highlighter)"},
    "tip_sub": {"it": "Pedice (es. H2O)", "en": "Subscript (e.g. H2O)"},
    "tip_super": {"it": "Apice (es. m2, note)", "en": "Superscript (e.g. m2, notes)"},
    "tip_list_ordered": {"it": "Elenco numerato", "en": "Numbered list"},
    "tip_list_bullet": {"it": "Elenco puntato", "en": "Bulleted list"},
    "tip_list_check": {"it": "Elenco con caselle da spuntare", "en": "Checklist"},
    "tip_indent_less": {"it": "Riduci il rientro", "en": "Decrease indent"},
    "tip_indent_more": {"it": "Aumenta il rientro", "en": "Increase indent"},
    "tip_align_left": {"it": "Allinea a sinistra", "en": "Align left"},
    "tip_align_center": {"it": "Centra (anche le immagini)", "en": "Centre (images too)"},
    "tip_align_right": {"it": "Allinea a destra", "en": "Align right"},
    "tip_align_justify": {"it": "Giustifica", "en": "Justify"},
    "tip_blockquote": {"it": "Citazione", "en": "Quote"},
    "tip_code_block": {"it": "Blocco di codice (con evidenziazione)", "en": "Code block (with highlighting)"},
    "tip_link": {"it": "Inserisci un collegamento", "en": "Insert a link"},
    "tip_image": {"it": "Inserisci un'immagine da URL", "en": "Insert an image from a URL"},
    "tip_video": {"it": "Inserisci un video da URL", "en": "Insert a video from a URL"},
    "tip_clean": {"it": "Rimuovi la formattazione", "en": "Remove formatting"},
    # Tooltips for the custom buttons below the editor
    "tip_upload_image": {"it": "Carica un'immagine dal tuo computer (PNG, JPEG, SVG)",
                         "en": "Upload an image from your computer (PNG, JPEG, SVG)"},
    "tip_upload_video": {"it": "Carica un video dal tuo computer", "en": "Upload a video from your computer"},
    "tip_youtube": {"it": "Incolla un link YouTube e inseriscilo nell'articolo",
                    "en": "Paste a YouTube link and embed it in the article"},
    "tip_table": {"it": "Inserisci una tabella (scegli righe e colonne)",
                  "en": "Insert a table (choose rows and columns)"},
    "tip_preview": {"it": "Mostra come apparira' l'articolo pubblicato",
                    "en": "Show how the published article will look"},
    "js_uploading": {"it": "Caricamento in corso...", "en": "Uploading..."},
    "js_uploading_image": {"it": "Caricamento immagine...", "en": "Uploading image..."},
    "js_upload_error": {"it": "Errore di caricamento.", "en": "Upload error."},
    "js_video_uploaded": {"it": "Video caricato.", "en": "Video uploaded."},
    "js_image_uploaded": {"it": "Immagine caricata.", "en": "Image uploaded."},
    # --- Strings of the administration area ---
    "admin_articoli": {"it": "Articoli", "en": "Articles"},
    "admin_impostazioni": {"it": "Impostazioni", "en": "Settings"},
    "admin_vedi_blog": {"it": "Vedi blog", "en": "View blog"},
    "admin_password": {"it": "Password", "en": "Password"},
    "admin_esci": {"it": "Esci", "en": "Log out"},
    "admin_nuovo_articolo": {"it": "+ Nuovo articolo", "en": "+ New article"},
    "admin_totali": {"it": "Totali", "en": "Total"},
    "admin_pubblicati": {"it": "Pubblicati", "en": "Published"},
    "admin_bozze": {"it": "Bozze", "en": "Drafts"},
    "admin_impostazioni_home": {"it": "Impostazioni e homepage", "en": "Settings and homepage"},
    "admin_rigenera": {"it": "Rigenera sito", "en": "Rebuild site"},
    "admin_scarica_backup": {"it": "Scarica backup", "en": "Download backup"},
    "admin_filtra": {"it": "Filtra gli articoli per titolo...", "en": "Filter articles by title..."},
    "admin_nessun_corrisponde": {"it": "Nessun articolo corrisponde alla ricerca.", "en": "No articles match your search."},
    "admin_nessun_articolo": {"it": 'Ancora nessun articolo. Clicca "Nuovo articolo" per iniziare.',
                              "en": 'No articles yet. Click "New article" to start.'},
    "admin_pubblicato": {"it": "Pubblicato", "en": "Published"},
    "admin_bozza": {"it": "Bozza", "en": "Draft"},
    "admin_pubblica": {"it": "Pubblica", "en": "Publish"},
    "admin_metti_bozza": {"it": "Metti in bozza", "en": "Move to draft"},
    "admin_modifica": {"it": "Modifica", "en": "Edit"},
    "admin_anteprima": {"it": "Anteprima", "en": "Preview"},
    "admin_elimina": {"it": "Elimina", "en": "Delete"},
    "admin_titolo_pagina": {"it": "Amministrazione", "en": "Administration"},
    # Login and password
    "admin_area_riservata": {"it": "Area riservata", "en": "Restricted area"},
    "admin_login_invito": {"it": "Inserisci la password per accedere all'amministrazione del blog.",
                           "en": "Enter the password to access the blog administration."},
    "admin_accedi": {"it": "Accedi", "en": "Log in"},
    "admin_crea_password_titolo": {"it": "Benvenuto! Crea la tua password", "en": "Welcome! Create your password"},
    "admin_crea_password_invito": {"it": "Questo e' il primo avvio. Scegli una password per proteggere l'area di amministrazione del blog.",
                                   "en": "This is the first run. Choose a password to protect the blog administration area."},
    "admin_nuova_password": {"it": "Nuova password", "en": "New password"},
    "admin_conferma_password": {"it": "Conferma password", "en": "Confirm password"},
    "admin_crea_accedi": {"it": "Crea password e accedi", "en": "Create password and log in"},
    "admin_cambia_password": {"it": "Cambia password", "en": "Change password"},
    "admin_password_attuale": {"it": "Password attuale", "en": "Current password"},
    "admin_conferma_nuova": {"it": "Conferma nuova password", "en": "Confirm new password"},
    # Editor
    "admin_nuovo_articolo_titolo": {"it": "Nuovo", "en": "New"},
    "admin_modifica_articolo_titolo": {"it": "Modifica", "en": "Edit"},
    "admin_titolo": {"it": "Titolo", "en": "Title"},
    "admin_descrizione_seo": {"it": "Descrizione SEO", "en": "SEO description"},
    "admin_descrizione_hint": {"it": "(appare su Google sotto il titolo; ideale 120-160 caratteri)",
                               "en": "(appears on Google under the title; ideal 120-160 characters)"},
    "admin_suggerisci_descrizione": {"it": "Suggerisci con AI", "en": "Suggest with AI"},
    "admin_analisi_seo": {"it": "Analisi SEO e backlink", "en": "SEO & backlink analysis"},
    "admin_analisi_seo_hint": {"it": "Keyword, anchor text per i backlink, link interni e consigli per i motori AI.",
                               "en": "Keywords, backlink anchor texts, internal links and advice for AI search engines."},
    "admin_analizza_seo": {"it": "Analizza con AI", "en": "Analyze with AI"},
    "seo_primary_keywords": {"it": "Keyword principali", "en": "Primary keywords"},
    "seo_secondary_keywords": {"it": "Keyword secondarie e long-tail", "en": "Secondary and long-tail keywords"},
    "seo_suggested_tags": {"it": "Tag consigliati", "en": "Suggested tags"},
    "seo_title_variants": {"it": "Varianti di titolo SEO", "en": "SEO title variants"},
    "seo_meta_review": {"it": "Giudizio sulla meta description", "en": "Meta description review"},
    "seo_backlink_target": {"it": "URL da linkare nel backlink", "en": "Backlink target URL"},
    "seo_anchor_texts": {"it": "Anchor text per il backlink", "en": "Backlink anchor texts"},
    "seo_internal_links": {"it": "Link interni consigliati", "en": "Suggested internal links"},
    "seo_faq": {"it": "FAQ per i motori AI", "en": "FAQ for AI search engines"},
    "seo_ai_tips": {"it": "Consigli AI-SEO", "en": "AI-SEO advice"},
    "seo_apply_tags": {"it": "Usa questi tag", "en": "Use these tags"},
    "seo_apply": {"it": "Applica", "en": "Apply"},
    "seo_use_title": {"it": "Usa", "en": "Use"},
    "seo_suggested_description": {"it": "Meta description pronta", "en": "Ready-made meta description"},
    "seo_add_faq": {"it": "Aggiungi le FAQ all'articolo", "en": "Add the FAQ to the article"},
    "seo_add_related": {"it": "Aggiungi la sezione 'Per approfondire'", "en": "Add the 'Read more' section"},
    "seo_apply_all": {"it": "Applica tutto (descrizione, tag, FAQ, link)", "en": "Apply everything (description, tags, FAQ, links)"},
    "seo_applied": {"it": "Applicato: rivedi e poi salva l'articolo.", "en": "Applied: review, then save the article."},
    "seo_faq_heading": {"it": "Domande frequenti", "en": "Frequently asked questions"},
    "seo_related_heading": {"it": "Per approfondire", "en": "Read more"},
    "seo_trend_queries": {"it": "Ricerche reali degli utenti (Google Suggest)", "en": "Real user searches (Google Suggest)"},
    "seo_content_changes": {"it": "Modifiche proposte all'articolo", "en": "Proposed article changes"},
    "seo_baseurl_warning": {"it": "Attenzione: base_url e' ancora quello di esempio. Imposta il dominio vero nelle Impostazioni.",
                            "en": "Warning: base_url is still the placeholder. Set the real domain in Settings."},
    "seo_make_revision": {"it": "Prepara la revisione completa dell'articolo", "en": "Prepare the full article revision"},
    "seo_revision_title": {"it": "Revisione proposta: l'articolo con le aggiunte evidenziate",
                           "en": "Proposed revision: the article with the additions highlighted"},
    "seo_revision_intro": {"it": "Il testo originale e' intatto. I blocchi verdi sono le aggiunte proposte: togli la spunta a quelle che non vuoi. Le modifiche entrano nell'editor solo quando applichi, e nell'articolo pubblicato solo quando salvi.",
                           "en": "The original text is untouched. The green blocks are the proposed additions: untick the ones you do not want. Changes reach the editor only when you apply, and the published article only when you save."},
    "seo_revision_generating": {"it": "Preparazione della revisione in corso (fino a un minuto)...",
                                "en": "Preparing the revision (up to a minute)..."},
    "seo_revision_apply": {"it": "Applica le aggiunte selezionate", "en": "Apply the selected additions"},
    "seo_revision_cancel": {"it": "Chiudi senza applicare", "en": "Close without applying"},
    "seo_revision_applied": {"it": "Aggiunte inserite nell'editor: rivedi e poi salva.",
                             "en": "Additions inserted in the editor: review, then save."},
    "seo_revision_end_note": {"it": "(posizione non trovata: verrebbe aggiunta in fondo)",
                              "en": "(position not found: it would be added at the end)"},
    "seo_revision_why": {"it": "Perche'", "en": "Why"},
    "seo_open_report": {"it": "Report dell'analisi (fonti e motivazioni)", "en": "Analysis report (sources and rationale)"},
    "seo_report_title": {"it": "Report dell'analisi SEO", "en": "SEO analysis report"},
    "seo_report_sources": {"it": "Fonti consultate", "en": "Sources consulted"},
    "seo_report_service": {"it": "Servizio AI e modello", "en": "AI service and model"},
    "seo_report_date": {"it": "Data dell'analisi", "en": "Analysis date"},
    "seo_report_seeds": {"it": "Termini interrogati su Google Suggest", "en": "Terms looked up on Google Suggest"},
    "seo_report_collected": {"it": "Query reali raccolte", "en": "Real queries collected"},
    "seo_report_none": {"it": "nessuna (Suggest non raggiungibile o senza risultati)", "en": "none (Suggest unreachable or no results)"},
    "seo_report_keywords": {"it": "Keyword: perche' e dove", "en": "Keywords: why and where"},
    "seo_report_col_keyword": {"it": "Keyword", "en": "Keyword"},
    "seo_report_col_type": {"it": "Tipo", "en": "Type"},
    "seo_report_col_reason": {"it": "Perche' e' stata scelta", "en": "Why it was chosen"},
    "seo_report_col_queries": {"it": "Query reali di supporto", "en": "Supporting real queries"},
    "seo_report_col_placement": {"it": "Dove viene usata", "en": "Where it is used"},
    "seo_report_changes": {"it": "Modifiche proposte e loro motivo", "en": "Proposed changes and their reason"},
    "seo_report_download": {"it": "Scarica il report (HTML)", "en": "Download the report (HTML)"},
    "seo_report_close": {"it": "Chiudi", "en": "Close"},
    "seo_report_missing": {"it": "Il modello non ha fornito le motivazioni per keyword: rilancia l'analisi.",
                           "en": "The model did not provide the per-keyword rationale: run the analysis again."},
    "seo_copy": {"it": "Copia", "en": "Copy"},
    "seo_copied": {"it": "Copiato!", "en": "Copied!"},
    "js_seo_analyzing": {"it": "Analisi in corso (richiede fino a un minuto)...",
                         "en": "Analyzing (this can take up to a minute)..."},
    "js_seo_done": {"it": "Analisi completata.", "en": "Analysis completed."},
    "js_seo_save_first": {"it": "Salva prima l'articolo: l'analisi usa lo slug per costruire l'URL.",
                          "en": "Save the article first: the analysis uses the slug to build the URL."},
    "err_seo_analysis_parse": {"it": "Il modello non ha restituito un'analisi leggibile: riprova.",
                               "en": "The model did not return a readable analysis: try again."},
    "admin_table_editor_title": {"it": "Modifica tabella", "en": "Edit table"},
    "admin_table_hint": {"it": "Clicca sulla tabella per modificarla", "en": "Click the table to edit it"},
    "admin_table_add_row": {"it": "+ riga", "en": "+ row"},
    "admin_table_del_row": {"it": "- riga", "en": "- row"},
    "admin_table_add_col": {"it": "+ colonna", "en": "+ column"},
    "admin_table_del_col": {"it": "- colonna", "en": "- column"},
    "admin_table_save": {"it": "Salva tabella", "en": "Save table"},
    "admin_table_cancel": {"it": "Annulla", "en": "Cancel"},
    "admin_analytics": {"it": "Google Analytics", "en": "Google Analytics"},
    "admin_analytics_hint": {"it": "(ID misurazione GA4, tipo G-XXXXXXXXXX; vuoto = disattivato)",
                             "en": "(GA4 measurement ID, like G-XXXXXXXXXX; empty = disabled)"},
    "admin_umami": {"it": "Umami (statistiche self-hosted)", "en": "Umami (self-hosted analytics)"},
    "admin_umami_hint": {"it": "(URL della tua istanza e ID del sito; vuoti = disattivato, niente cookie)",
                         "en": "(your instance URL and the website ID; empty = disabled, no cookies)"},
    "admin_anteprima_lettori": {"it": "Anteprima per i lettori", "en": "Reader preview"},
    "admin_anteprima_hint": {"it": "(testo mostrato nella card della homepage; se vuoto si usa un estratto automatico)",
                             "en": "(text shown in the homepage card; if empty an automatic excerpt is used)"},
    "admin_genera_anteprima": {"it": "Genera con AI", "en": "Generate with AI"},
    "admin_sezione_pubblicazione": {"it": "Pubblicazione", "en": "Publishing"},
    "admin_sezione_metadati": {"it": "Dettagli articolo", "en": "Article details"},
    "admin_tag": {"it": "Tag (separati da virgola)", "en": "Tags (comma separated)"},
    "admin_immagine_copertina": {"it": "Immagine di copertina (URL)", "en": "Cover image (URL)"},
    "admin_contenuto": {"it": "Contenuto", "en": "Content"},
    "admin_stato": {"it": "Stato", "en": "Status"},
    "admin_salva_genera": {"it": "Salva e genera HTML", "en": "Save and generate HTML"},
    "admin_versione_inglese": {"it": "Versione inglese", "en": "English version"},
    "admin_traduci_auto": {"it": "Traduci automaticamente", "en": "Translate automatically"},
    "admin_conferma_traduzione": {"it": "Conferma la traduzione e pubblica la pagina inglese",
                                  "en": "Confirm the translation and publish the English page"},
    "admin_anteprima_en": {"it": "Anteprima pagina inglese", "en": "Preview English page"},
    "admin_anteprima_en_hint": {"it": "(salva l'articolo e apre la pagina inglese come la vedranno i lettori)",
                                "en": "(saves the article and opens the English page as readers will see it)"},
    "admin_autorizza_traduzione": {"it": "Autorizza la creazione della versione inglese",
                                   "en": "Allow creating the English version"},
    # Settings
    "admin_impostazioni_titolo": {"it": "Impostazioni e homepage", "en": "Settings and homepage"},
    "admin_titolo_sito": {"it": "Titolo del sito", "en": "Site title"},
    "admin_sottotitolo": {"it": "Sottotitolo", "en": "Subtitle"},
    "admin_autore": {"it": "Autore", "en": "Author"},
    "admin_salva_rigenera": {"it": "Salva e rigenera sito", "en": "Save and rebuild site"},
    "admin_carica_immagine": {"it": "Carica immagine", "en": "Upload image"},
    "admin_inserisci_youtube": {"it": "Inserisci video YouTube", "en": "Insert YouTube video"},
    "admin_carica_video": {"it": "Carica un video", "en": "Upload a video"},
    "admin_inserisci_tabella": {"it": "Inserisci tabella", "en": "Insert table"},
    "admin_mostra_anteprima": {"it": "Mostra/nascondi anteprima", "en": "Show/hide preview"},
    "admin_parte_alta_home": {"it": "Parte alta della homepage", "en": "Top of the homepage"},
    "admin_parte_alta_hint": {"it": "Scrivi qui la tua presentazione, biografia, immagini. Per posizionare un'immagine a sinistra o a destra: clicca sull'immagine, poi usa i pulsanti di allineamento nella barra dell'editor. Il testo le scorrera' intorno.",
                              "en": "Write your introduction, biography and images here. To place an image left or right: click the image, then use the alignment buttons in the editor toolbar. Text will flow around it."},
    "admin_mostra_anteprima_home": {"it": "Mostra/nascondi anteprima homepage", "en": "Show/hide homepage preview"},
    "admin_come_appare_home": {"it": "come apparira' la parte alta della home", "en": "how the top of the homepage will look"},
    "admin_presentazione_inglese": {"it": "Presentazione in inglese", "en": "English introduction"},
    "admin_presentazione_en_hint": {"it": "Versione inglese della presentazione, mostrata nella home in inglese. Puoi tradurla automaticamente dal testo italiano qui sopra, poi rivederla. Se la lasci vuota, la home inglese mostra la versione italiana.",
                                    "en": "English version of the introduction, shown on the English homepage. You can translate it automatically from the Italian text above, then review it. If left empty, the English homepage shows the Italian version."},
    "admin_traduci_dall_italiano": {"it": "Traduci automaticamente dall'italiano", "en": "Translate automatically from Italian"},
    "admin_card_home_titolo": {"it": "Card della homepage", "en": "Homepage cards"},
    "admin_card_home_hint": {"it": "Sezioni mostrate sotto la presentazione: biografia, progetti, foto, avvisi. Spunta \"Mostra questa card\" per renderle visibili. Scrivi il contenuto con l'editor visuale; per le foto usa il pulsante immagine.",
                             "en": "Sections shown below the introduction: biography, projects, photos, notices. Check \"Show this card\" to make them visible. Write the content with the visual editor; for photos use the image button."},
    "admin_mostra_card": {"it": "Mostra questa card", "en": "Show this card"},
    "admin_titolo_card": {"it": "Titolo della card", "en": "Card title"},
    "admin_impostazioni_generali": {"it": "Impostazioni generali", "en": "General settings"},
    "admin_titolo_sito": {"it": "Titolo del sito", "en": "Site title"},
    "admin_sottotitolo": {"it": "Sottotitolo", "en": "Subtitle"},
    "admin_autore": {"it": "Autore", "en": "Author"},
    "admin_dominio_sito": {"it": "Dominio del sito", "en": "Site domain"},
    "admin_dominio_hint": {"it": "(senza slash finale, es. https://miosito.it)", "en": "(without trailing slash, e.g. https://mysite.com)"},
    "admin_lingua_principale": {"it": "Lingua principale del sito", "en": "Main site language"},
    "admin_lingua_principale_hint": {"it": "(it o en): decide quale lingua sta alla radice; l'altra va in una sottocartella",
                                     "en": "(it or en): decides which language sits at the root; the other goes in a subfolder"},
    "admin_commenti_titolo": {"it": "Commenti", "en": "Comments"},
    "admin_sistema_commenti": {"it": "Sistema di commenti", "en": "Comments system"},
    "admin_commenti_nessuno": {"it": "Nessuno", "en": "None"},
    "admin_disqus_hint": {"it": "Da https://disqus.com -> crea un sito -> prendi lo shortname",
                          "en": "From https://disqus.com -> create a site -> get the shortname"},
    "admin_traduzione_titolo": {"it": "Traduzione automatica (Italiano &rarr; Inglese)", "en": "Automatic translation (Italian &rarr; English)"},
    "admin_servizio_traduzione": {"it": "Servizio di traduzione", "en": "Translation service"},
    "admin_traduzione_intro": {"it": "Inserisci la chiave del servizio che vuoi usare. Se non inserisci nessuna chiave, la traduzione resta disattivata (il blog funziona comunque). Le chiavi restano sul tuo server e non sono mai visibili al pubblico.",
                               "en": "Enter the API key of the service you want to use. If you leave it empty, translation stays disabled (the blog still works). Keys stay on your server and are never visible to the public."},
    "admin_chiave_api": {"it": "Chiave API", "en": "API key"},
    "admin_endpoint": {"it": "Endpoint", "en": "Endpoint"},
    "admin_modello_label": {"it": "Modello", "en": "Model"},
    "admin_tema_label": {"it": "Tema", "en": "Theme"},
    "admin_lascia_vuoto": {"it": "lascia vuoto per disattivare", "en": "leave empty to disable"},
    "admin_salvataggio": {"it": "Salvataggio...", "en": "Saving..."},
    "admin_config_salvata": {"it": "Configurazione salvata e sito rigenerato.", "en": "Configuration saved and site rebuilt."},
    "admin_errore_salvataggio": {"it": "Errore di salvataggio.", "en": "Save error."},
    "admin_config_avanzata": {"it": "Configurazione avanzata (modifica config.json)", "en": "Advanced configuration (edit config.json)"},
    "admin_config_avanzata_hint": {"it": "Modifica diretta del file di configurazione. Usala solo se sai cosa stai facendo: il JSON viene validato prima del salvataggio e, se contiene errori, viene rifiutato per non danneggiare il sito.",
                                   "en": "Direct edit of the configuration file. Use it only if you know what you are doing: the JSON is validated before saving and, if it contains errors, it is rejected to avoid breaking the site."},
    "admin_salva_config_raw": {"it": "Salva configurazione", "en": "Save configuration"},
    "admin_ripristina": {"it": "Ripristina", "en": "Reset"},
    "admin_config_raw_salvata": {"it": "Configurazione salvata e sito rigenerato.", "en": "Configuration saved and site rebuilt."},
    # SEO and author data section
    "admin_seo_titolo": {"it": "SEO e dati dell'autore", "en": "SEO and author data"},
    "admin_seo_intro": {"it": "Questi dati alimentano i dati strutturati (schema.org) e i meta tag social: aiutano Google a riconoscerti come autore reale. Tutti i campi sono facoltativi.",
                        "en": "This data feeds structured data (schema.org) and social meta tags: it helps Google recognise you as a real author. All fields are optional."},
    "admin_seo_autore_url": {"it": "Pagina personale (URL)", "en": "Personal page (URL)"},
    "admin_seo_autore_url_hint": {"it": "(il tuo sito o profilo professionale)", "en": "(your website or professional profile)"},
    "admin_seo_autore_immagine": {"it": "Foto dell'autore (URL)", "en": "Author photo (URL)"},
    "admin_seo_autore_ruolo": {"it": "Ruolo professionale", "en": "Job title"},
    "admin_seo_autore_ruolo_hint": {"it": "(es. CTO e docente)", "en": "(e.g. CTO and lecturer)"},
    "admin_seo_autore_bio": {"it": "Breve biografia", "en": "Short bio"},
    "admin_seo_autore_bio_hint": {"it": "(1-2 frasi professionali)", "en": "(1-2 professional sentences)"},
    "admin_seo_profili": {"it": "Profili pubblici (uno per riga)", "en": "Public profiles (one per line)"},
    "admin_seo_profili_hint": {"it": "(GitHub, LinkedIn, X... il segnale piu' importante per collegare i tuoi profili)",
                               "en": "(GitHub, LinkedIn, X... the most important signal to connect your profiles)"},
    "admin_seo_logo": {"it": "Logo del sito (URL)", "en": "Site logo (URL)"},
    "admin_seo_twitter": {"it": "Account X/Twitter del sito", "en": "Site X/Twitter account"},
    "admin_seo_twitter_hint": {"it": "(con la chiocciola, es. @tuonome)", "en": "(with the at sign, e.g. @yourname)"},
    "admin_seo_favicon": {"it": "Favicon personalizzata (URL)", "en": "Custom favicon (URL)"},
    "admin_seo_favicon_hint": {"it": "(se vuota, ne viene generata una con l'iniziale del sito)",
                               "en": "(if empty, one is generated with the site initial)"},
    # Homepage layout
    "admin_layout_titolo": {"it": "Struttura della homepage", "en": "Homepage structure"},
    "admin_layout_hint": {"it": "L'ordine delle sezioni della home, dall'alto verso il basso.",
                          "en": "The order of the homepage sections, top to bottom."},
    "admin_section_intro": {"it": "Presentazione", "en": "Introduction"},
    "admin_section_articles": {"it": "Articoli", "en": "Articles"},
    "admin_section_cards": {"it": "Card", "en": "Cards"},
    "admin_posizione": {"it": "Posizione", "en": "Position"},
    "admin_articoli_per_pagina": {"it": "Articoli per pagina", "en": "Articles per page"},
    "admin_articoli_per_pagina_hint": {"it": "(0 = tutti in una pagina, senza paginazione)",
                                       "en": "(0 = all on one page, no pagination)"},
    # AI training rights section
    "admin_ai_training_titolo": {"it": "Diritti di addestramento AI", "en": "AI training rights"},
    "admin_ai_training_intro": {
        "it": "Molti servizi di intelligenza artificiale raccolgono contenuti dal web per "
              "addestrare i loro modelli. Qui decidi come comportarti: la scelta si riflette "
              "in robots.txt, in llms.txt e in una pagina dedicata che spiega la tua posizione "
              "ai lettori e agli operatori AI.",
        "en": "Many AI services collect content from the web to train their models. Here you "
              "decide how to handle that: the choice is reflected in robots.txt, in llms.txt "
              "and in a dedicated page explaining your position to readers and AI operators."},
    "admin_ai_training_policy": {"it": "Politica sull'addestramento", "en": "Training policy"},
    "admin_ai_training_open": {"it": "Consentito \u2014 nessuna restrizione per i crawler AI",
                               "en": "Allowed \u2014 no restriction for AI crawlers"},
    "admin_ai_training_licensed": {"it": "Solo su licenza \u2014 blocca i crawler AI noti, offri un contatto per negoziare",
                                   "en": "Licensed only \u2014 block known AI crawlers, offer a contact to negotiate"},
    "admin_ai_training_disallow": {"it": "Non consentito \u2014 blocca i crawler AI noti, nessuna licenza offerta",
                                   "en": "Disallowed \u2014 block known AI crawlers, no licence offered"},
    "admin_ai_training_email": {"it": "Email per richieste di licenza", "en": "Email for licensing inquiries"},
    "admin_ai_training_email_hint": {"it": "(mostrata solo se il criterio e' \"Solo su licenza\")",
                                     "en": "(shown only when the policy is \"Licensed only\")"},
    "admin_ai_training_license_url": {"it": "URL dei tuoi termini di licenza", "en": "URL of your own licence terms"},
    "admin_ai_training_license_url_hint": {"it": "(facoltativo: se vuoto si usa la pagina generata da PyBlog)",
                                           "en": "(optional: if empty, PyBlog's own generated page is used)"},
    "admin_ai_training_statement": {"it": "Testo personalizzato (facoltativo)", "en": "Custom statement (optional)"},
    "admin_ai_training_statement_hint": {"it": "(sostituisce il testo predefinito nella pagina e in llms.txt)",
                                         "en": "(replaces the default wording on the page and in llms.txt)"},
    "admin_ai_training_nota_standard": {
        "it": "Nota: i meccanismi tecnici usati (elenco crawler in robots.txt, ai.txt, tdmrep.json) "
              "seguono le convenzioni correnti del settore, che non sono uno standard legale "
              "vincolante e possono evolvere; nessun crawler e' obbligato a rispettarle.",
        "en": "Note: the technical mechanisms used (robots.txt crawler list, ai.txt, tdmrep.json) "
              "follow current industry conventions, which are not a binding legal standard and "
              "may evolve; no crawler is obligated to honour them."},
    # Training rights page (public)
    "training_titolo": {"it": "Diritti di addestramento AI", "en": "AI training rights"},
    "training_intro_open": {
        "it": "L'autore di questo sito non pone restrizioni all'uso dei contenuti per "
              "l'addestramento di modelli di intelligenza artificiale.",
        "en": "This site's author places no restrictions on using its content to train "
              "artificial intelligence models."},
    "training_intro_licensed": {
        "it": "I contenuti di questo sito non possono essere usati per addestrare modelli di "
              "intelligenza artificiale senza una licenza. I crawler AI conosciuti sono "
              "bloccati in robots.txt.",
        "en": "This site's content may not be used to train artificial intelligence models "
              "without a licence. Known AI crawlers are blocked in robots.txt."},
    "training_intro_disallow": {
        "it": "L'autore di questo sito non concede l'uso dei contenuti per l'addestramento di "
              "modelli di intelligenza artificiale. I crawler AI conosciuti sono bloccati in "
              "robots.txt.",
        "en": "This site's author does not grant the use of its content to train artificial "
              "intelligence models. Known AI crawlers are blocked in robots.txt."},
    "training_contatto": {"it": "Per richieste di licenza, contatta:", "en": "For licensing inquiries, contact:"},
    "training_termini_propri": {"it": "I termini completi sono disponibili qui:", "en": "Full terms are available here:"},

    # Server-side error/success messages (API responses and password pages)
    "err_unknown_translation_service": {"it": "Servizio di traduzione sconosciuto.", "en": "Unknown translation service."},
    "err_service_error": {"it": "Errore dal servizio: ", "en": "Service error: "},
    "err_ssl_certificates": {
        "it": "Python non trova i certificati per verificare la connessione HTTPS. Su macOS (Python da python.org) esegui una volta: open \"/Applications/Python 3.X/Install Certificates.command\". In alternativa: pip3 install certifi e poi, prima di avviare l'editor, export SSL_CERT_FILE=\"$(python3 -m certifi)\".",
        "en": "Python cannot find the certificates to verify the HTTPS connection. On macOS (Python from python.org) run once: open \"/Applications/Python 3.X/Install Certificates.command\". Alternatively: pip3 install certifi and then, before starting the editor, export SSL_CERT_FILE=\"$(python3 -m certifi)\".",
    },
    "err_generation_needs_llm": {
        "it": "La generazione richiede un servizio LLM (Anthropic, OpenAI o DeepSeek). Selezionane uno nelle Impostazioni.",
        "en": "Generation requires an LLM service (Anthropic, OpenAI or DeepSeek). Select one in Settings."},
    "err_no_content_to_summarize": {"it": "L'articolo non ha ancora contenuto da riassumere.",
                                    "en": "The article has no content to summarise yet."},
    "err_unauthorized": {"it": "Non autorizzato. Effettua il login.", "en": "Not authorised. Please log in."},
    "err_article_not_found": {"it": "Articolo non trovato.", "en": "Article not found."},
    "err_invalid_json_prefix": {"it": "JSON non valido: ", "en": "Invalid JSON: "},
    "err_config_must_be_object": {"it": "Il file di configurazione deve essere un oggetto JSON.",
                                  "en": "The configuration file must be a JSON object."},
    "err_invalid_format": {"it": "Formato non valido.", "en": "Invalid format."},
    "err_no_file_received": {"it": "Nessun file ricevuto.", "en": "No file received."},
    "err_password_too_short": {"it": "La password deve avere almeno 6 caratteri.",
                               "en": "The password must be at least 6 characters long."},
    "err_passwords_dont_match_setup": {"it": "Le due password non coincidono.", "en": "The two passwords do not match."},
    "err_too_many_attempts": {"it": "Troppi tentativi errati. Riprova tra {n} secondi.",
                              "en": "Too many failed attempts. Try again in {n} seconds."},
    "err_wrong_password": {"it": "Password errata. Riprova.", "en": "Wrong password. Please try again."},
    "err_current_password_wrong": {"it": "La password attuale non e' corretta.", "en": "The current password is incorrect."},
    "err_new_password_too_short": {"it": "La nuova password deve avere almeno 6 caratteri.",
                                   "en": "The new password must be at least 6 characters long."},
    "err_new_passwords_dont_match": {"it": "Le due nuove password non coincidono.", "en": "The two new passwords do not match."},
    "success_password_changed": {"it": "Password cambiata con successo.", "en": "Password changed successfully."},

    # Public-site search widget (JS, follows the page language, not the admin one)
    "js_search_unavailable": {"it": "Indice di ricerca non disponibile.", "en": "Search index unavailable."},
    "js_search_no_results": {"it": "Nessun articolo trovato per", "en": "No articles found for"},
    "js_search_results_for": {"it": "risultato/i per", "en": "result(s) for"},

    # Admin editor/config JS messages
    "js_write_intro_first": {"it": "Scrivi prima la presentazione in italiano.", "en": "Write the introduction first."},
    "js_prompt_youtube_link": {"it": "Incolla il link del video YouTube:", "en": "Paste the YouTube video link:"},
    "js_youtube_not_recognized": {"it": "Link YouTube non riconosciuto.", "en": "YouTube link not recognised."},
    "js_write_article_content_first": {"it": "Scrivi prima il contenuto dell'articolo.", "en": "Write the article content first."},
    "js_suggestion_inserted": {"it": "Proposta inserita: rivedila e modificala come preferisci.",
                              "en": "Suggestion inserted: review and edit it as you like."},
    "js_desc_counter_empty": {"it": "Vuota: verra' generata in automatico dal contenuto.",
                              "en": "Empty: it will be generated automatically from the content."},
    "js_preview_counter_empty": {"it": "Vuota: verra' usato un estratto automatico del contenuto.",
                                 "en": "Empty: an automatic excerpt of the content will be used."},
    "js_chars_unit": {"it": "caratteri", "en": "characters"},
    "js_chars_too_long_google": {"it": "oltre 160 Google la taglia nei risultati.",
                                 "en": "over 160 and Google will truncate it in results."},
    "js_chars_too_short_seo": {"it": "un po' corta per la SEO.", "en": "a bit short for SEO."},
    "js_chars_ideal_length": {"it": "lunghezza ideale.", "en": "ideal length."},
    "js_recovering_pasted_images": {"it": "Recupero delle immagini incollate...", "en": "Recovering pasted images..."},
    "js_pasted_all_recovered": {"it": "Incollato: {n} immagine/i recuperata/e.", "en": "Pasted with {n} image(s) recovered."},
    "js_pasted_partial_recovered": {"it": "Incollato: {ok} di {tot} immagine/i recuperata/e.",
                                    "en": "Pasted: {ok} of {tot} image(s) recovered."},
    "js_pasted_word_image_unavailable": {
        "it": "Il testo e' stato incollato, ma il tuo sistema non ha fornito alla pagina il file dell'immagine copiata (solo un riferimento che il browser non puo' caricare): salva l'immagine come file e usa \"Carica immagine\".",
        "en": "The text was pasted, but your system did not give the page the file for the copied image (only a reference the browser cannot load): save the image as a file and use \"Upload image\"."},
}


def T(key, language="it"):
    """
    Return the translation of an interface label in the given language.
    If the key or the language does not exist, return a safe fallback.
    """
    if key not in UI_TRANSLATIONS:
        return key
    feed_items = UI_TRANSLATIONS[key]
    if language in feed_items:
        return feed_items[language]
    if "it" in feed_items:
        return feed_items["it"]
    return key


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


# ---------------------------------------------------------------------------
# AUTOMATIC TRANSLATION (IT -> EN)
# ---------------------------------------------------------------------------
# Calls to the translation services happen here, in the backend, because
# the API keys are secret and must never end up in a public page.
# We only use urllib from the standard library: no external dependency.
import urllib.request as _urlreq
import urllib.error as _urlerr


def translate_with_deepl(text, api_key):
    """
    Translate an HTML text from Italian to English using DeepL.
    DeepL keeps the HTML tags if we pass tag_handling=html.
    """
    if api_key == "":
        raise ValueError("Chiave API DeepL mancante.")

    # DeepL has two domains: free (api-free) and paid (api).
    # Free keys end with ":fx".
    if api_key.endswith(":fx"):
        url = "https://api-free.deepl.com/v2/translate"
    else:
        url = "https://api.deepl.com/v2/translate"

    parametri = {
        "text": text,
        "source_lang": "IT",
        "target_lang": "EN",
        "tag_handling": "html",
    }
    data = urllib.parse.urlencode(parametri).encode("utf-8")
    request = _urlreq.Request(url, data=data)
    request.add_header("Authorization", "DeepL-Auth-Key " + api_key)

    with _urlreq.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    return result["translations"][0]["text"]


def translate_with_google(text, api_key):
    """
    Translate an HTML text from Italian to English with Google Cloud Translation.
    With format=html, Google preserves the tags.
    """
    if api_key == "":
        raise ValueError("Chiave API Google mancante.")

    url = "https://translation.googleapis.com/language/translate/v2?key=" + api_key
    parametri = {
        "q": text,
        "source": "it",
        "target": "en",
        "format": "html",
    }
    data = urllib.parse.urlencode(parametri).encode("utf-8")
    request = _urlreq.Request(url, data=data)

    with _urlreq.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    return result["data"]["translations"][0]["translatedText"]


def translate_with_llm(text, api_key, endpoint, modello):
    """
    Translate an HTML text from Italian to English using an LLM (e.g. Claude).
    We ask the model to translate while keeping the HTML tags intact.
    """
    if api_key == "":
        raise ValueError("Chiave API dell'LLM mancante.")

    istruzione = (
        "Translate the following HTML content from Italian to English. "
        "Keep all HTML tags exactly as they are, translate only the visible text. "
        "Return only the translated HTML, with no extra comments.\n\n" + text
    )
    request_body = {
        "model": modello,
        "max_tokens": 4000,
        "messages": [
            {"role": "user", "content": istruzione},
        ],
    }
    data = json.dumps(request_body).encode("utf-8")
    request = _urlreq.Request(endpoint, data=data)
    request.add_header("Content-Type", "application/json")
    request.add_header("x-api-key", api_key)
    request.add_header("anthropic-version", "2023-06-01")

    with _urlreq.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    # Claude's response contains a list of blocks; we take the text.
    blocks = result.get("content", [])
    translated_text = ""
    for block in blocks:
        if block.get("type") == "text":
            translated_text = translated_text + block.get("text", "")
    return translated_text


def translate_with_openai_compat(text, api_key, endpoint, modello):
    """
    Translate an HTML text from Italian to English using a service
    compatible with the OpenAI API (both OpenAI and DeepSeek are).
    Both use the same 'chat completions' format, so a single function
    serves both by changing the endpoint and the model.
    """
    if api_key == "":
        raise ValueError("Chiave API mancante.")

    istruzione = (
        "Translate the following HTML content from Italian to English. "
        "Keep all HTML tags exactly as they are, translate only the visible text. "
        "Return only the translated HTML, with no extra comments.\n\n" + text
    )
    request_body = {
        "model": modello,
        "messages": [
            {"role": "user", "content": istruzione},
        ],
    }
    data = json.dumps(request_body).encode("utf-8")
    request = _urlreq.Request(endpoint, data=data)
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", "Bearer " + api_key)

    with _urlreq.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    # The response follows the OpenAI format: choices[0].message.content.
    choices = result.get("choices", [])
    if len(choices) == 0:
        return ""
    messaggio = choices[0].get("message", {})
    translated_text = messaggio.get("content", "")
    return translated_text


def _secret_setting(translation_config, key_name):
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


def translate_text(text):
    """
    Translate a text from Italian to English using the configured service.
    Return a dictionary with the outcome and the translated text (or the error).
    """
    if text is None:
        return {"ok": True, "text": ""}
    if text.strip() == "":
        return {"ok": True, "text": ""}

    translation_config = CONFIG.get("translation", {})
    service = translation_config.get("service", "deepl")

    try:
        if service == "deepl":
            tradotto = translate_with_deepl(
                text, _secret_setting(translation_config, "deepl_api_key"))
        elif service == "google":
            tradotto = translate_with_google(
                text, _secret_setting(translation_config, "google_api_key"))
        elif service == "llm":
            tradotto = translate_with_llm(
                text,
                _secret_setting(translation_config, "llm_api_key"),
                translation_config.get("llm_endpoint", ""),
                translation_config.get("llm_model", ""))
        elif service == "openai":
            tradotto = translate_with_openai_compat(
                text,
                _secret_setting(translation_config, "openai_api_key"),
                "https://api.openai.com/v1/chat/completions",
                translation_config.get("openai_model", "gpt-4o-mini"))
        elif service == "deepseek":
            tradotto = translate_with_openai_compat(
                text,
                _secret_setting(translation_config, "deepseek_api_key"),
                "https://api.deepseek.com/chat/completions",
                translation_config.get("deepseek_model", "deepseek-chat"))
        else:
            return {"ok": False, "error": T("err_unknown_translation_service", admin_language())}
        return {"ok": True, "text": tradotto}
    except _urlerr.HTTPError as error:
        return {"ok": False, "error": T("err_service_error", admin_language()) + str(error.code) + _http_error_detail(error)}
    except Exception as error:
        return {"ok": False, "error": _friendly_network_error(error)}


def _http_error_detail(error):
    """
    Extract the human-readable message from an HTTP error response.
    Providers put the actual reason in the JSON body (wrong model name,
    credit exhausted, malformed field...): showing just the status code
    hides exactly the part the person needs. Anthropic uses
    {"error": {"message": ...}}, OpenAI-compatible services the same
    shape; anything else falls back to the raw (truncated) body.
    """
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    if body != "":
        try:
            parsed = json.loads(body)
            inner = parsed.get("error", {})
            if isinstance(inner, dict):
                message = inner.get("message", "")
                if message != "":
                    return " - " + str(message)[:300]
        except Exception:
            pass
        return " - " + body[:300]
    return ""


def _friendly_network_error(error):
    """
    Turn a raw network exception into a message a person can act on.
    The classic case is macOS, where a fresh Python has no CA bundle
    linked and every HTTPS call fails with CERTIFICATE_VERIFY_FAILED:
    the raw text gives no clue about the (one-command) fix.
    """
    testo = str(error)
    if "CERTIFICATE_VERIFY_FAILED" in testo or "certificate verify failed" in testo:
        return T("err_ssl_certificates", admin_language())
    return testo


def _call_llm_with_prompt(prompt, max_tokens=300):
    """
    Send a free-form prompt to the configured LLM and return its answer.
    It only works with the LLM services (Anthropic, OpenAI, DeepSeek), because
    DeepL and Google can only translate, not reason about a text.
    max_tokens caps the length of the answer: the default fits short
    generations (descriptions, previews); longer tasks pass a higher value.
    Return a dictionary {ok, testo} or {ok: False, errore}.
    """
    translation_config = CONFIG.get("translation", {})
    service = translation_config.get("service", "deepl")

    try:
        if service == "llm":
            api_key = _secret_setting(translation_config, "llm_api_key")
            endpoint = translation_config.get("llm_endpoint", "")
            modello = translation_config.get("llm_model", "")
            if api_key == "":
                return {"ok": False, "error": "Chiave API Anthropic mancante."}
            # We reuse the structure of the Anthropic call.
            body = {
                "model": modello,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            data = json.dumps(body).encode("utf-8")
            request = _urlreq.Request(endpoint, data=data)
            request.add_header("Content-Type", "application/json")
            request.add_header("x-api-key", api_key)
            request.add_header("anthropic-version", "2023-06-01")
            with _urlreq.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text = text + block.get("text", "")
            return {"ok": True, "text": text.strip()}

        if service == "openai" or service == "deepseek":
            if service == "openai":
                api_key = _secret_setting(translation_config, "openai_api_key")
                endpoint = "https://api.openai.com/v1/chat/completions"
                modello = translation_config.get("openai_model", "gpt-4o-mini")
            else:
                api_key = _secret_setting(translation_config, "deepseek_api_key")
                endpoint = "https://api.deepseek.com/chat/completions"
                modello = translation_config.get("deepseek_model", "deepseek-chat")
            if api_key == "":
                return {"ok": False, "error": "Chiave API mancante."}
            body = {
                "model": modello,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            data = json.dumps(body).encode("utf-8")
            request = _urlreq.Request(endpoint, data=data)
            request.add_header("Content-Type", "application/json")
            request.add_header("Authorization", "Bearer " + api_key)
            with _urlreq.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
            choices = result.get("choices", [])
            if len(choices) == 0:
                return {"ok": False, "error": "Risposta vuota dal modello."}
            text = choices[0].get("message", {}).get("content", "")
            return {"ok": True, "text": text.strip()}

        # DeepL and Google cannot generate text.
        return {"ok": False, "error": T("err_generation_needs_llm", admin_language())}
    except _urlerr.HTTPError as error:
        return {"ok": False, "error": T("err_service_error", admin_language()) + str(error.code) + _http_error_detail(error)}
    except Exception as error:
        return {"ok": False, "error": _friendly_network_error(error)}


def generate_seo_description(html_content, title_value):
    """
    Generate an SEO description (meta description) from the article
    content, using the configured LLM. The description is an inviting
    summary of about 150 characters, not just the start of the text.
    """
    text = _plain_text(html_content)
    if text.strip() == "":
        return {"ok": False, "error": T("err_no_content_to_summarize", admin_language())}

    # We limit the text we send so as not to waste tokens: the first 2000 are enough.
    excerpt = text[:2000]
    prompt = (
        "Sei un esperto SEO. Scrivi una meta description in italiano per questo "
        "articolo di blog. Deve essere una sola frase invitante di circa 150 "
        "caratteri (massimo 160), che riassuma il contenuto e spinga al click. "
        "Rispondi SOLO con la descrizione, senza virgolette, senza prefissi, "
        "senza spiegazioni.\n\n"
        "Titolo: " + title_value + "\n\n"
        "Contenuto: " + excerpt
    )
    result = _call_llm_with_prompt(prompt)
    if result["ok"]:
        # We clean up any quotes or spaces around the response.
        description = result["text"].strip().strip('"').strip()
        return {"ok": True, "description": description}
    return result


def generate_reader_preview(html_content, title_value):
    """
    Generate a narrative preview for readers from the content.
    Unlike the SEO meta description (short and technical), this is an
    inviting 2-4 sentence summary telling what the article is about,
    meant for the homepage card. It uses the configured LLM.
    """
    text = _plain_text(html_content)
    if text.strip() == "":
        return {"ok": False, "error": T("err_no_content_to_summarize", admin_language())}

    excerpt = text[:2500]
    prompt = (
        "Sei un redattore di blog. Scrivi in italiano una breve presentazione "
        "di questo articolo, da mostrare nell'anteprima in homepage. Deve essere "
        "discorsiva e invitante, da 2 a 4 frasi (circa 300-500 caratteri), e far "
        "capire al lettore di cosa parla l'articolo e perche' vale la pena "
        "leggerlo. Rispondi SOLO con il testo della presentazione, senza "
        "virgolette, senza titoli, senza prefissi.\n\n"
        "Titolo: " + title_value + "\n\n"
        "Contenuto: " + excerpt
    )
    result = _call_llm_with_prompt(prompt)
    if result["ok"]:
        preview = result["text"].strip().strip('"').strip()
        return {"ok": True, "preview": preview}
    return result


def _extract_json_object(text):
    """
    Extract a JSON object from an LLM answer. Models often wrap the JSON
    in a Markdown fence or add a sentence around it: we take everything
    between the first '{' and the last '}' and parse that.
    Return the parsed dictionary, or None if no valid JSON is found.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _published_articles_for_linking(exclude_slug):
    """
    Titles and slugs of the other published articles, used to let the
    LLM suggest internal links. Internal links spread ranking signals
    across the site and help both search engines and AI crawlers
    understand which pages are related.
    """
    result = []
    for art in load_articles():
        if art.get("status") != "published":
            continue
        if art.get("slug") == exclude_slug:
            continue
        result.append({"title": art.get("title", ""), "slug": art.get("slug", "")})
    # A handful is enough for the prompt: we cap the list to keep tokens low.
    return result[:20]


def _fetch_search_suggestions(term, language="it"):
    """
    Ask Google Suggest (the search autocomplete) for the queries people
    are really typing around a term, in the given language. This is the
    same free, key-less source most SEO tools use to discover long-tail
    queries. It is not a search-volume API (those are paid services):
    it tells you WHAT is being searched, not how much.
    Failures are tolerated silently: the SEO analysis works anyway,
    just without the real-queries signal.
    """
    try:
        query = urllib.parse.urlencode({"client": "firefox", "hl": language, "q": term})
        url = "https://suggestqueries.google.com/complete/search?" + query
        request = _urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _urlreq.urlopen(request, timeout=4) as reply:
            data = json.loads(reply.read().decode("utf-8", errors="replace"))
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            result = []
            for voice in data[1]:
                if isinstance(voice, str) and voice.strip() != "":
                    result.append(voice.strip())
            return result
    except Exception:
        pass
    return []


def _collect_trend_queries(title_value, tags_value):
    """
    Build the list of real search queries around the article's topics.
    The seeds are the title and the tags: for each one we ask Google
    Suggest what people are typing. Capped to keep the analysis fast.
    """
    seeds = []
    if title_value.strip() != "":
        seeds.append(title_value.strip()[:60])
    for tag in tags_value.split(","):
        tag = tag.strip()
        if tag != "" and tag not in seeds:
            seeds.append(tag)
    seeds = seeds[:5]

    collected = []
    seen = set()
    for seed in seeds:
        for suggestion in _fetch_search_suggestions(seed):
            low = suggestion.lower()
            if low not in seen:
                seen.add(low)
                collected.append(suggestion)
    # The seeds are returned too: the analysis report declares exactly
    # which terms were looked up, so every keyword choice is traceable.
    return seeds, collected[:25]


class _RevisionSanitizer(html.parser.HTMLParser):
    """
    Rebuilds a fragment of HTML keeping only a small whitelist of tags.
    The revision content comes from the language model and is inserted
    into the article: without this step the model (or a poisoned
    response) could inject scripts or arbitrary markup into the blog.
    Allowed: structural text tags, plus links restricted to internal
    article URLs and same-page anchors.
    """
    ALLOWED = {"p", "h2", "h3", "ul", "ol", "li", "strong", "em", "b", "i", "br", "a", "blockquote", "code"}
    # Tags whose CONTENT must be dropped too: keeping the inner text of
    # a <script> would leak the code as visible (and pasteable) text.
    DROP_CONTENT = {"script", "style", "iframe", "object", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.dropping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP_CONTENT:
            self.dropping = self.dropping + 1
            return
        if self.dropping > 0:
            return
        if tag not in self.ALLOWED:
            return
        if tag == "a":
            href = ""
            for name, value in attrs:
                if name == "href" and value is not None:
                    href = value
            valid = href.startswith("/posts/") or href.startswith("#")
            if valid and re.fullmatch(r"[A-Za-z0-9/#._-]+", href) is not None:
                self.parts.append('<a href="' + href + '">')
                self.open_tags.append("a")
            else:
                # The link target is not acceptable: keep the text only.
                self.parts.append("")
                self.open_tags.append("")
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        self.parts.append("<" + tag + ">")
        self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if tag in self.DROP_CONTENT:
            if self.dropping > 0:
                self.dropping = self.dropping - 1
            return
        if self.dropping > 0:
            return
        if tag not in self.ALLOWED or tag == "br":
            return
        if len(self.open_tags) > 0:
            aperto = self.open_tags.pop()
            if aperto != "":
                self.parts.append("</" + aperto + ">")

    def handle_data(self, data):
        if self.dropping > 0:
            return
        self.parts.append(html.escape(data))

    def result(self):
        # Close anything the model left open.
        while len(self.open_tags) > 0:
            aperto = self.open_tags.pop()
            if aperto != "":
                self.parts.append("</" + aperto + ">")
        return "".join(self.parts)


def _sanitize_revision_html(fragment):
    """Sanitize a fragment proposed by the model for the revision."""
    cleaner = _RevisionSanitizer()
    try:
        cleaner.feed(str(fragment))
        cleaner.close()
    except Exception:
        return ""
    return cleaner.result()


def generate_article_revision(html_content, title_value, tags_value, analysis):
    """
    Ask the model for a set of MINIMAL, anchored edits that apply the
    SEO analysis to the article. The model never rewrites the article:
    it proposes discrete insertions, each anchored to an existing
    paragraph, and the program applies them deterministically. This is
    what guarantees the original text stays untouched except for the
    additions the operator accepts.
    Return {ok, edits: [{anchor, new_html, reason}]} or {ok: False, error}.
    """
    text = _plain_text(html_content)
    if text.strip() == "":
        return {"ok": False, "error": T("err_no_content_to_summarize", admin_language())}

    analysis_text = json.dumps(analysis, ensure_ascii=False)[:3000]
    excerpt = text[:5000]

    prompt = (
        "Sei un revisore SEO. Hai gia' prodotto questa analisi per l'articolo:\n"
        + analysis_text + "\n\n"
        "Titolo: " + title_value + "\n"
        "Tag: " + tags_value + "\n\n"
        "Testo dell'articolo (solo testo, senza markup):\n" + excerpt + "\n\n"
        "Proponi al massimo 6 MODIFICHE MINIME che applicano l'analisi. "
        "Regole tassative:\n"
        "- NON riscrivere ne' riassumere il testo esistente: solo AGGIUNTE.\n"
        "- Ogni aggiunta e' ancorata a una frase esistente: riporta in "
        "'anchor' un frammento ESATTO e testuale di 8-20 parole preso "
        "dall'articolo, dopo il cui paragrafo inserire il nuovo contenuto. "
        "Usa anchor con stringa vuota per inserire in fondo all'articolo.\n"
        "- 'new_html' contiene il contenuto nuovo, gia' scritto in "
        "italiano nello stile dell'articolo, usando SOLO questi tag: "
        "p, h2, h3, ul, ol, li, strong, em, a (i link solo verso "
        "/posts/... del blog).\n"
        "- 'reason' spiega in una frase perche' l'aggiunta serve "
        "(quale query o obiettivo SEO intercetta).\n"
        "- Includi, se pertinenti dall'analisi: una sezione FAQ, la "
        "sezione 'Per approfondire' con i link interni, e i paragrafi "
        "che rispondono alle query reali.\n\n"
        "Rispondi SOLO con JSON valido:\n"
        '{"edits": [{"anchor": "...", "new_html": "...", "reason": "..."}]}'
    )

    result = _call_llm_with_prompt(prompt, max_tokens=3500)
    if result["ok"] is not True:
        return result

    parsed = _extract_json_object(result["text"])
    if parsed is None or not isinstance(parsed.get("edits"), list):
        return {"ok": False, "error": T("err_seo_analysis_parse", admin_language())}

    edits = []
    for voice in parsed["edits"][:8]:
        if not isinstance(voice, dict):
            continue
        clean_html = _sanitize_revision_html(voice.get("new_html", ""))
        if clean_html.strip() == "":
            continue
        edits.append({
            "anchor": str(voice.get("anchor", ""))[:300],
            "new_html": clean_html,
            "reason": str(voice.get("reason", ""))[:300],
        })
    if len(edits) == 0:
        return {"ok": False, "error": T("err_seo_analysis_parse", admin_language())}
    return {"ok": True, "edits": edits}


def analyze_article_seo(html_content, title_value, slug_value, tags_value, description_value):
    """
    Full SEO and AI-SEO analysis of an article, using the configured LLM.

    The analysis is designed for this blog's real workflow: articles are
    also published on external sites (startupbusiness.it) with a backlink
    pointing here, so beyond the classic keywords it produces the anchor
    texts to use in those backlinks, internal link suggestions towards the
    other articles of the blog, and FAQ + advice for AI search engines
    (ChatGPT, Perplexity, Google AI Overviews), which increasingly drive
    traffic and read the site through llms.txt and structured data.

    Return {ok, analysis, article_url} or {ok: False, error}.
    """
    text = _plain_text(html_content)
    if text.strip() == "":
        return {"ok": False, "error": T("err_no_content_to_summarize", admin_language())}

    # The canonical URL of the article: this is the exact address to use
    # as the backlink target on the external site.
    base = CONFIG.get("base_url", "").rstrip("/")
    article_url = base + "/posts/" + str(slug_value) + ".html"

    # The external site that will host the backlink. It can be changed in
    # config.json ("seo" -> "backlink_site") without touching the code.
    seo_config = CONFIG.get("seo", {})
    backlink_site = seo_config.get("backlink_site", "startupbusiness.it")

    # The other published articles, so the model can propose internal links.
    other_articles = _published_articles_for_linking(slug_value)
    articles_lines = []
    for art in other_articles:
        articles_lines.append("- " + art["title"] + " (slug: " + art["slug"] + ")")
    if len(articles_lines) > 0:
        articles_text = "\n".join(articles_lines)
    else:
        articles_text = "(nessun altro articolo pubblicato)"

    # Real search queries around the article's topics, from Google
    # Suggest: they anchor the keyword choices to actual demand.
    trend_seeds, trend_queries = _collect_trend_queries(title_value, tags_value)
    if len(trend_queries) > 0:
        trend_text = "\n".join("- " + q for q in trend_queries)
    else:
        trend_text = "(nessuna disponibile)"

    # We limit the content excerpt to keep the token cost reasonable.
    excerpt = text[:4000]

    prompt = (
        "Sei un consulente SEO senior specializzato in blog tecnici italiani e in "
        "AI-SEO (posizionamento nelle risposte di ChatGPT, Perplexity e Google AI "
        "Overviews). Analizza questo articolo di blog.\n\n"
        "CONTESTO: l'articolo verra' ripreso o citato su " + backlink_site + " "
        "(testata italiana per startup e founder) con un link verso il blog. "
        "Gli anchor text devono quindi essere naturali in quel contesto "
        "editoriale, variati (uno esatto sulla keyword, uno parziale, uno "
        "brandizzato o discorsivo) e mai sovra-ottimizzati.\n\n"
        "Titolo: " + title_value + "\n"
        "Tag attuali: " + tags_value + "\n"
        "Meta description attuale: " + description_value + "\n"
        "URL dell'articolo: " + article_url + "\n\n"
        "Altri articoli del blog (per suggerire link interni):\n"
        + articles_text + "\n\n"
        "QUERY DI RICERCA REALI che le persone stanno digitando ora su "
        "Google intorno a questi temi (da Google Suggest). Usale come "
        "segnale di domanda: quando una query e' pertinente all'articolo, "
        "preferiscila come keyword e proponi modifiche che la intercettino.\n"
        + trend_text + "\n\n"
        "Contenuto:\n" + excerpt + "\n\n"
        "Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo, "
        "senza markdown, con esattamente queste chiavi:\n"
        "{\n"
        '  "primary_keywords": [3-5 keyword principali, in italiano],\n'
        '  "secondary_keywords": [5-8 keyword secondarie e long-tail],\n'
        '  "suggested_tags": [4-6 tag consigliati per questo blog],\n'
        '  "title_variants": [2-3 varianti di titolo SEO, max 60 caratteri],\n'
        '  "meta_description_review": "giudizio in 1-2 frasi sulla meta description attuale",\n'
        '  "suggested_description": "una meta description pronta all\'uso per questo articolo, massimo 155 caratteri, in italiano",\n'
        '  "anchor_texts": [3-5 anchor text per il backlink da ' + backlink_site + '],\n'
        '  "internal_links": [per ogni link interno consigliato un oggetto {"slug": "...", "anchor": "..."}; lista vuota se nessuno e\' pertinente],\n'
        '  "faq": [2-3 oggetti {"question": "...", "answer": "..."} con domande che i lettori farebbero a un motore AI, e risposte di 2-3 frasi tratte dall\'articolo],\n'
        '  "ai_seo_tips": [2-4 consigli concreti e specifici per QUESTO articolo per comparire nelle risposte dei motori AI],\n'
        '  "trend_queries": [le query reali dell\'elenco sopra che giudichi pertinenti per questo articolo, massimo 8; lista vuota se nessuna],\n'
        '  "content_changes": [2-4 modifiche concrete e pronte da applicare all\'articolo per intercettare le query reali: per ognuna un oggetto {"where": "dove intervenire, es. dopo la sezione X", "change": "il testo o la sezione da aggiungere, gia\' scritto in italiano"}],\n'
        '  "keyword_report": [OBBLIGATORIO: una voce per OGNI keyword delle liste primary_keywords e secondary_keywords, nello stesso ordine. Ogni voce: {"keyword": "...", "type": "primaria" o "secondaria", "reason": "perche\' e\' stata scelta: pertinenza col contenuto e intento di ricerca, in 1-2 frasi", "queries": [le query reali dell\'elenco sopra che la supportano; lista vuota se la scelta viene solo dal contenuto], "placement": "dove viene usata o dove conviene usarla: titolo, description, sezione dell\'articolo o modifica proposta"}]\n'
        "}"
    )

    result = _call_llm_with_prompt(prompt, max_tokens=4000)
    if result["ok"] is not True:
        return result

    analysis = _extract_json_object(result["text"])
    if analysis is None:
        return {"ok": False, "error": T("err_seo_analysis_parse", admin_language())}

    # The sources block makes the analysis auditable: which service and
    # model produced it, which terms were looked up on Google Suggest,
    # and which real queries came back. The report shows all of it.
    translation_config = CONFIG.get("translation", {})
    sources = {
        "service": translation_config.get("service", ""),
        "model": _current_llm_model_name(translation_config),
        "suggest_seeds": trend_seeds,
        "suggest_queries": trend_queries,
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    return {"ok": True, "analysis": analysis, "article_url": article_url, "sources": sources}


def _current_llm_model_name(translation_config):
    """The model name of the service in use, for the analysis report."""
    service = translation_config.get("service", "")
    if service == "llm":
        return translation_config.get("llm_model", "")
    if service == "openai":
        return translation_config.get("openai_model", translation_config.get("openai_modello", ""))
    if service == "deepseek":
        return translation_config.get("deepseek_model", translation_config.get("deepseek_modello", ""))
    return ""


# ---------------------------------------------------------------------------
# AUTHENTICATION OF THE ADMINISTRATION AREA
# ---------------------------------------------------------------------------
# The password is never stored in clear text: we only store its "hash"
# (a digest from which the password cannot be recovered). When the user
# logs in, we compute the hash of what they typed and compare the two.

# File where we store the hash of the administration password.
PASSWORD_FILE = BASE_DIR / "admin_password.txt"

# List of the active sessions (valid tokens). It only lives while the server
# is running: if you restart it, you have to log in again.
ACTIVE_SESSIONS = set()


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


# Protection against repeated login attempts (brute force).
# After LOGIN_MAX_TENTATIVI consecutive errors, login stays locked
# for LOGIN_SECONDI_BLOCCO seconds. The counter resets on the first
# successful login. It lives in memory: restarting the server resets it too.
LOGIN_MAX_TENTATIVI = 5
LOGIN_LOCK_SECONDS = 60
LOGIN_STATO = {"errors": 0, "locked_until": 0.0}


def login_is_locked():
    """Tell whether login is temporarily locked after too many errors."""
    return time.time() < LOGIN_STATO["locked_until"]


def record_failed_login():
    """Record a failed login attempt and turn on the lock if needed."""
    LOGIN_STATO["errors"] = LOGIN_STATO["errors"] + 1
    if LOGIN_STATO["errors"] >= LOGIN_MAX_TENTATIVI:
        LOGIN_STATO["locked_until"] = time.time() + LOGIN_LOCK_SECONDS
        LOGIN_STATO["errors"] = 0


def record_successful_login():
    """Reset the error counter after a successful login."""
    LOGIN_STATO["errors"] = 0
    LOGIN_STATO["locked_until"] = 0.0


def create_session_token():
    """Create a random token for a login session and register it."""
    token = secrets.token_urlsafe(32)
    ACTIVE_SESSIONS.add(token)
    return token


def session_is_valid(token):
    """Tell whether a session token is valid (i.e. the user is logged in)."""
    if token is None:
        return False
    if token in ACTIVE_SESSIONS:
        return True
    return False


# ---------------------------------------------------------------------------
# ARTICLE MANAGEMENT (stored as JSON files, no database)
# ---------------------------------------------------------------------------

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
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
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
        with open(path_value, encoding="utf-8") as fp:
            data = json.load(fp)
        data, migrato = migrate_article_schema(data)
        if migrato:
            with open(path_value, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        return data
    return None


def save_article(data):
    """
    Save an article as a JSON file. Return the slug.
    The article holds both the Italian and the English (translated) version.
    """
    title_value = data.get("title", "").strip()
    if title_value == "":
        title_value = "Senza titolo"

    slug = data.get("slug", "").strip()
    if slug == "":
        slug = slugify(title_value)
    else:
        # We normalise a hand-written slug too: safe characters only.
        # This prevents slugs with "/" or ".." that would escape the folder.
        slug = slugify(slug)

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

    article = {
        "title": title_value,
        "slug": slug,
        "description": data.get("description", "").strip(),
        # Reader preview: the text that appears in the homepage card.
        # If empty, the card shows an automatic excerpt of the content.
        "preview": data.get("preview", "").strip(),
        "content": data.get("content", ""),
        "tags": data.get("tags", "").strip(),
        "image": data.get("image", "").strip(),
        "status": data.get("status", "draft"),
        "date": data.get("date"),
        "date_modified": datetime.now(timezone.utc).isoformat(),
        # --- English version ---
        "title_en": title_en,
        "description_en": description_en,
        "preview_en": data.get("preview_en", "").strip(),
        "content_en": content_en,
        "translation_authorized": translation_authorized,
        "translation_confirmed": translation_confirmed,
    }
    # If the date was not present, we first try to keep the date of the
    # article already on disk (the editor does not send the date field:
    # without this step, every save would reset the publication date).
    if article["date"] is None:
        existing = None
        existing_path = POSTS_DIR / f"{slug}.json"
        if existing_path.exists():
            with open(existing_path, encoding="utf-8") as fp:
                existing = json.load(fp)
        if existing is None:
            original = data.get("original_slug", "")
            if original != "" and original != slug:
                original_path = POSTS_DIR / f"{slugify(original)}.json"
                if original_path.exists():
                    with open(original_path, encoding="utf-8") as fp:
                        existing = json.load(fp)
        if existing is not None:
            existing, _ = migrate_article_schema(existing)
            article["date"] = existing.get("date")
    # If the article is genuinely new, we use the current time.
    if article["date"] is None:
        article["date"] = datetime.now(timezone.utc).isoformat()

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(POSTS_DIR / f"{slug}.json", "w", encoding="utf-8") as fp:
        json.dump(article, fp, ensure_ascii=False, indent=2)
    return slug


# We keep the old name as an alias, so as not to break existing code.
def delete_article(slug):
    """Delete an article from disk."""
    if not slug_is_valid(slug):
        return False
    path_value = POSTS_DIR / f"{slug}.json"
    if path_value.exists():
        path_value.unlink()
        return True
    return False


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


def _markdown_inline(text):
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
            html_out.append("<p>" + _markdown_inline(content) + "</p>")
            paragraph.clear()

    def close_list():
        nonlocal tipo_lista
        if tipo_lista != "":
            html_out.append("</" + tipo_lista + ">")
            tipo_lista = ""

    def close_quote():
        if len(quote_lines) > 0:
            content = " ".join(quote_lines)
            html_out.append("<blockquote>" + _markdown_inline(content) + "</blockquote>")
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
            html_out.append(f"<h{level}>" + _markdown_inline(content) + f"</h{level}>")
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
            html_out.append("<li>" + _markdown_inline(ul_match.group(1)) + "</li>")
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
            html_out.append("<li>" + _markdown_inline(ol_match.group(1)) + "</li>")
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
        slug = save_article(data)
        print(f"  imported: {file_corrente.name} -> posts/{slug}.json ({status})")
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


# ---------------------------------------------------------------------------
# STATIC HTML GENERATION
# ---------------------------------------------------------------------------

def _image_overlay_script(language="it"):
    """
    JavaScript that keeps the image selection/resize box (the overlay of
    quill-blot-formatter) attached to its image, and recovers images
    pasted from Word documents (see handlePastedImages below).

    BUG FIXED: blot-formatter computes the box position only once, at the
    moment you select the image. If you then change the alignment from the
    toolbar ("centre", for example), the image moves but the box stays
    where it was, on the left, with the old size: it looks "detached" from
    the image. Here we recompute it every time something in the editor moves.

    This is NOT written as an f-string: the JavaScript braces stay single,
    avoiding the doubling that an f-string would need throughout ~100 lines
    of JS (a frequent source of mistakes). The few translated messages are
    injected at the end via plain text placeholders and .replace().
    """
    testo = """<script>
// Keeps the resize box glued to its image.
function attachImageOverlay(istanzaQuill) {
  if (!istanzaQuill) { return; }
  var formattatore = istanzaQuill.getModule('blotFormatter');
  if (!formattatore) { return; }

  function reposition() {
    // No image selected: there is nothing to reposition.
    if (!formattatore.currentSpec) { return; }
    // When the paragraph formatting changes, Quill may recreate the
    // image from scratch: the box would point to an element that is no
    // longer in the page. In that case we hide it.
    if (typeof formattatore.currentSpec.getTargetElement === 'function') {
      var bersaglio = formattatore.currentSpec.getTargetElement();
      if (bersaglio && !document.contains(bersaglio)) {
        if (typeof formattatore.hide === 'function') { formattatore.hide(); }
        return;
      }
    }
    // update() recomputes both the box and the corner handles.
    // If the library version does not expose it, we fall back to
    // repositioning the box alone.
    if (typeof formattatore.update === 'function') {
      formattatore.update();
    } else if (typeof formattatore.repositionOverlay === 'function') {
      formattatore.repositionOverlay();
    }
  }

  // We wait for the browser to finish repainting: before the repaint
  // we would still read the old position of the image.
  function repositionAfterPaint() {
    window.requestAnimationFrame(reposition);
  }

  // 1) Any text or format change, including the "centre" button
  //    of the toolbar.
  istanzaQuill.on('editor-change', repositionAfterPaint);

  // 2) Style or class changes inside the editor: these are what really
  //    move the image (Quill puts the ql-align-center class on the
  //    paragraph, and resizing writes width/height on the image).
  //    The box lives outside .ql-editor, so it does not self-trigger.
  if (window.MutationObserver) {
    var osservatore = new MutationObserver(repositionAfterPaint);
    osservatore.observe(istanzaQuill.root, {
      attributes: true, childList: true, subtree: true,
      attributeFilter: ['style', 'class', 'width', 'height', 'align']
    });
  }

  // 3) A freshly inserted image changes size when it finishes
  //    loading, i.e. after the box has already been drawn.
  istanzaQuill.root.addEventListener('load', repositionAfterPaint, true);

  // 4) Window resizing and editor scrolling.
  window.addEventListener('resize', repositionAfterPaint);
  istanzaQuill.root.addEventListener('scroll', repositionAfterPaint);
}

// Recovers images embedded in a pasted Word/Office document.
//
// THE PROBLEM: when you copy text and images from Word (or similar word
// processors) and paste them into the browser, the clipboard's HTML
// contains <img> tags whose "src" points to a local path on the sender's
// own computer (something like "file:///C:/Users/.../media/image1.png")
// or an internal reference the browser cannot resolve. The browser simply
// cannot load an image from another computer's disk, so the text pastes
// fine but every image silently fails and disappears. This is a limitation
// of the clipboard itself, not something specific to this editor: the same
// thing happens in most web-based rich text editors.
//
// THE FIX: alongside that broken HTML, the operating system also puts the
// actual image data in the clipboard as separate, real image items (this
// is how "paste image" works everywhere). We read those real images,
// upload each one to the server, and splice the resulting URLs into the
// pasted HTML in place of the broken ones.
//
// BUG FIXED: we used to pair the n-th clipboard image with the n-th <img>
// tag purely by position, in the order both lists happened to come in.
// That breaks when the source document mixes text and images: some
// applications place, as the clipboard's image item for that portion, a
// flattened screenshot of the text AND the image together, instead of the
// isolated picture the <img> tag actually points to. Paired by position,
// that screenshot landed inside the first <img> tag, so the text before
// the first picture visually turned into a single image, while the later
// pictures (each with a clean clipboard item of their own) still came out
// fine. The fix: whenever a pasted <img> tag declares its width/height
// (Word and Google Docs normally write them), we only pair it with a
// clipboard image whose real pixel size matches. Only tags with no
// declared size, and only when the remaining tags and remaining images
// are equal in number, fall back to the old position-based pairing.
function handlePastedImages(istanzaQuill, statusElementId) {
  istanzaQuill.root.addEventListener('paste', function(evento) {
    if (!evento.clipboardData) { return; }

    var elementiImmagine = [];
    for (var i = 0; i < evento.clipboardData.items.length; i++) {
      var voce = evento.clipboardData.items[i];
      if (voce.type && voce.type.indexOf('image/') === 0) {
        elementiImmagine.push(voce);
      }
    }
    // No embedded images in this paste: let Quill handle it as usual
    // (plain text, or a paste that already has no images at all).
    if (elementiImmagine.length === 0) {
      // Some sources (Word on Windows, when you copy text together with a
      // picture) put in the clipboard only a broken local reference
      // ("file:///C:/Users/.../image1.png") and no actual image data at
      // all: a web page has no way to read a local file path for security
      // reasons, so there is nothing here to recover. We at least warn the
      // author instead of letting the picture disappear with no
      // explanation (a plain web page copy does not have this problem:
      // browsers normally embed the picture itself in that HTML).
      var statoAvviso = statusElementId ? document.getElementById(statusElementId) : null;
      if (statoAvviso && contieneImmagineNonRecuperabile(evento.clipboardData.getData('text/html'))) {
        statoAvviso.textContent = '__MSG_WORD_IMAGE_UNAVAILABLE__';
      }
      return;
    }

    var htmlIncollato = evento.clipboardData.getData('text/html');
    // No HTML at all: a single image was copied on its own (e.g. from
    // an image viewer), not part of a larger document paste. Quill's own
    // built-in image paste handling already covers that case.
    if (!htmlIncollato) { return; }

    // From here on we take full control of this paste.
    evento.preventDefault();
    evento.stopPropagation();

    var stato = statusElementId ? document.getElementById(statusElementId) : null;
    if (stato) { stato.textContent = '__MSG_RECOVERING__'; }

    // The <img> tags found in the pasted HTML, in the order they appear,
    // together with the width/height they declare (if any). This is what
    // lets us pair each tag with the right clipboard image further down,
    // instead of just trusting the order they came in.
    var tagImmagine = [];
    var regexTagImg = /<img\\b[^>]*>/gi;
    var trovato = regexTagImg.exec(htmlIncollato);
    while (trovato !== null) {
      tagImmagine.push({
        larghezza: leggiLarghezzaDichiarata(trovato[0]),
        altezza: leggiAltezzaDichiarata(trovato[0])
      });
      trovato = regexTagImg.exec(htmlIncollato);
    }

    // We upload every clipboard image and, in parallel, decode it locally
    // to read its real pixel size: we need that size to pair it safely
    // with the right <img> tag.
    var operazioni = [];
    for (var j = 0; j < elementiImmagine.length; j++) {
      var blobCorrente = elementiImmagine[j].getAsFile();
      operazioni.push(Promise.all([caricaBlobImmagine(blobCorrente), leggiDimensioneBlob(blobCorrente)]));
    }

    Promise.all(operazioni).then(function(risultati) {
      var immaginiCaricate = [];
      for (var k = 0; k < risultati.length; k++) {
        var dimensioneReale = risultati[k][1];
        immaginiCaricate.push({
          url: risultati[k][0],
          larghezza: dimensioneReale ? dimensioneReale.larghezza : null,
          altezza: dimensioneReale ? dimensioneReale.altezza : null,
          usata: false
        });
      }

      // 1) Tags with a declared size are paired only with a clipboard
      //    image whose real size matches (within a small tolerance for
      //    Word/Google Docs rounding). This is what stops a flattened
      //    text+image screenshot from being mistaken for a real picture.
      var assegnazioni = [];
      for (var t = 0; t < tagImmagine.length; t++) {
        assegnazioni.push(null);
      }
      for (var t2 = 0; t2 < tagImmagine.length; t2++) {
        var tagCorrente = tagImmagine[t2];
        if (tagCorrente.larghezza === null || tagCorrente.altezza === null) { continue; }
        var indiceTrovato = trovaImmagineDiTagliaCorrispondente(tagCorrente, immaginiCaricate);
        if (indiceTrovato !== null) {
          assegnazioni[t2] = immaginiCaricate[indiceTrovato].url;
          immaginiCaricate[indiceTrovato].usata = true;
        }
      }

      // 2) Tags with no declared size cannot be verified: we fall back to
      //    pairing them in order with whatever images are still unused,
      //    but only if their counts match exactly. This keeps the old,
      //    simple behaviour for the common case (a plain paste with no
      //    size hints at all, where there is no ambiguity to resolve).
      var tagScoperti = [];
      for (var t3 = 0; t3 < tagImmagine.length; t3++) {
        if (assegnazioni[t3] === null) { tagScoperti.push(t3); }
      }
      var immaginiLibere = immaginiCaricate.filter(function(im) { return !im.usata; });
      if (tagScoperti.length === immaginiLibere.length) {
        for (var m = 0; m < tagScoperti.length; m++) {
          assegnazioni[tagScoperti[m]] = immaginiLibere[m].url;
        }
      }

      // We rebuild the HTML: each <img> tag with a safe pairing is
      // replaced with its uploaded URL; the others are dropped rather
      // than risking a wrong image ending up in their place.
      var indiceTag = 0;
      var htmlFinale = htmlIncollato.replace(/<img\\b[^>]*>/gi, function() {
        var urlAssegnato = assegnazioni[indiceTag];
        indiceTag = indiceTag + 1;
        if (urlAssegnato === null || urlAssegnato === undefined) { return ''; }
        return '<img src="' + urlAssegnato + '">';
      });
      var posizione = istanzaQuill.getSelection(true) || { index: istanzaQuill.getLength() };
      istanzaQuill.clipboard.dangerouslyPasteHTML(posizione.index, htmlFinale);
      if (stato) {
        var riuscite = 0;
        for (var n = 0; n < assegnazioni.length; n++) {
          if (assegnazioni[n] !== null && assegnazioni[n] !== undefined) { riuscite = riuscite + 1; }
        }
        if (riuscite === tagImmagine.length) {
          stato.textContent = '__MSG_ALL_OK__'.replace('{n}', riuscite);
        } else {
          stato.textContent = '__MSG_PARTIAL__'.replace('{ok}', riuscite).replace('{tot}', tagImmagine.length);
        }
      }
    });
  }, true);  // capture phase: we need to run before Quill's own paste handler.
}

// Detects a pasted <img> tag whose src is not a real, loadable address.
// Word (and similar word processors) leave all sorts of placeholders in
// the clipboard HTML instead of a usable picture: a local file path
// ("file:///C:/Users/...", unreadable by a web page for security reasons),
// or a bare "//:0" (the placeholder Word writes for some pictures and
// shapes when the clipboard does not carry a matching bitmap for them).
// Rather than list every placeholder we have seen, we accept only the
// addresses that are actually loadable in a browser (http/https/data, or
// a path relative to this site, like the "/media/..." PyBlog itself
// generates) and treat anything else as unrecoverable.
function contieneImmagineNonRecuperabile(html) {
  if (!html) { return false; }
  var regexTag = /<img\\b[^>]*>/gi;
  var tag = regexTag.exec(html);
  while (tag !== null) {
    var corrispondenzaSrc = tag[0].match(/\\bsrc\\s*=\\s*["']([^"']*)["']/i);
    var indirizzo = corrispondenzaSrc ? corrispondenzaSrc[1] : '';
    if (!/^(https?:|data:|\\/)/i.test(indirizzo)) {
      return true;
    }
    tag = regexTag.exec(html);
  }
  return false;
}

// Reads the width a pasted <img> tag declares, either as a plain HTML
// attribute (width="200") or as an inline style (style="width:200px").
// Returns null when the tag declares no width at all.
function leggiLarghezzaDichiarata(tag) {
  var corrispondenzaAttributo = tag.match(/\\bwidth\\s*=\\s*"(\\d+)/i);
  if (corrispondenzaAttributo) { return parseInt(corrispondenzaAttributo[1], 10); }
  var corrispondenzaStile = tag.match(/width\\s*:\\s*(\\d+)px/i);
  if (corrispondenzaStile) { return parseInt(corrispondenzaStile[1], 10); }
  return null;
}

// Same as leggiLarghezzaDichiarata, for the height.
function leggiAltezzaDichiarata(tag) {
  var corrispondenzaAttributo = tag.match(/\\bheight\\s*=\\s*"(\\d+)/i);
  if (corrispondenzaAttributo) { return parseInt(corrispondenzaAttributo[1], 10); }
  var corrispondenzaStile = tag.match(/height\\s*:\\s*(\\d+)px/i);
  if (corrispondenzaStile) { return parseInt(corrispondenzaStile[1], 10); }
  return null;
}

// Decodes an image blob locally to read its real pixel size. Resolves to
// null if the blob turns out not to be a valid image.
function leggiDimensioneBlob(blob) {
  return new Promise(function(resolve) {
    var indirizzoTemporaneo = URL.createObjectURL(blob);
    var immagine = new Image();
    immagine.onload = function() {
      URL.revokeObjectURL(indirizzoTemporaneo);
      resolve({ larghezza: immagine.naturalWidth, altezza: immagine.naturalHeight });
    };
    immagine.onerror = function() {
      URL.revokeObjectURL(indirizzoTemporaneo);
      resolve(null);
    };
    immagine.src = indirizzoTemporaneo;
  });
}

// Looks, among the uploaded images not yet paired, for one whose real
// pixel size matches the size declared by the pasted tag (with a small
// tolerance for Word/Google Docs rounding). Returns its index in
// immaginiCaricate, or null when none matches closely enough.
function trovaImmagineDiTagliaCorrispondente(tagCorrente, immaginiCaricate) {
  var tolleranza = 3; // pixel di margine per arrotondamenti/DPI
  for (var i = 0; i < immaginiCaricate.length; i++) {
    var immagine = immaginiCaricate[i];
    if (immagine.usata) { continue; }
    if (immagine.larghezza === null) { continue; }
    var differenzaLarghezza = Math.abs(immagine.larghezza - tagCorrente.larghezza);
    var differenzaAltezza = Math.abs(immagine.altezza - tagCorrente.altezza);
    if (differenzaLarghezza <= tolleranza && differenzaAltezza <= tolleranza) {
      return i;
    }
  }
  return null;
}

// Uploads a single pasted image blob to the server, reusing the same
// /upload endpoint used by the "upload image" button. Returns a promise
// that resolves to the file URL, or null if the upload failed (so one
// broken image does not stop the others from being recovered).
function caricaBlobImmagine(blob) {
  var datiForm = new FormData();
  var estensione = (blob.type && blob.type.split('/')[1]) || 'png';
  datiForm.append('video', blob, 'pasted-image.' + estensione);
  return fetch('/upload', { method: 'POST', body: datiForm })
    .then(function(risposta) { return risposta.json(); })
    .then(function(risultato) { return risultato.ok ? risultato.url : null; })
    .catch(function() { return null; });
}
</script>"""
    testo = testo.replace("__MSG_RECOVERING__", T("js_recovering_pasted_images", language))
    testo = testo.replace("__MSG_ALL_OK__", T("js_pasted_all_recovered", language))
    testo = testo.replace("__MSG_PARTIAL__", T("js_pasted_partial_recovered", language))
    testo = testo.replace("__MSG_WORD_IMAGE_UNAVAILABLE__", T("js_pasted_word_image_unavailable", language))
    return testo


def _toolbar_tooltips_script(language="it"):
    """
    JavaScript that adds an explanatory tooltip to every button of the Quill
    toolbar. Quill's own icons say nothing to a new author: hovering a button
    now shows a small bubble explaining what it does.

    The bubble is pure CSS (a data-tooltip attribute plus a ::after
    pseudo-element): no library, and it appears instantly, unlike the
    browser's native title, which waits about a second.

    The labels come from the i18n dictionary, so they follow the language
    chosen for the administration area.
    """
    # Mappa: selettore CSS del pulsante -> etichetta tradotta.
    # I selettori sono quelli generati da Quill 1.3.x.
    entries = [
        ("span.ql-font", T("tip_font", language)),
        ("span.ql-size", T("tip_size", language)),
        ("span.ql-header", T("tip_header", language)),
        ("button.ql-bold", T("tip_bold", language)),
        ("button.ql-italic", T("tip_italic", language)),
        ("button.ql-underline", T("tip_underline", language)),
        ("button.ql-strike", T("tip_strike", language)),
        ("span.ql-color", T("tip_color", language)),
        ("span.ql-background", T("tip_background", language)),
        ('button.ql-script[value="sub"]', T("tip_sub", language)),
        ('button.ql-script[value="super"]', T("tip_super", language)),
        ('button.ql-list[value="ordered"]', T("tip_list_ordered", language)),
        ('button.ql-list[value="bullet"]', T("tip_list_bullet", language)),
        ('button.ql-list[value="check"]', T("tip_list_check", language)),
        ('button.ql-indent[value="-1"]', T("tip_indent_less", language)),
        ('button.ql-indent[value="+1"]', T("tip_indent_more", language)),
        ('button.ql-align[value=""]', T("tip_align_left", language)),
        ('button.ql-align[value="center"]', T("tip_align_center", language)),
        ('button.ql-align[value="right"]', T("tip_align_right", language)),
        ('button.ql-align[value="justify"]', T("tip_align_justify", language)),
        ("button.ql-blockquote", T("tip_blockquote", language)),
        ("button.ql-code-block", T("tip_code_block", language)),
        ("button.ql-link", T("tip_link", language)),
        ("button.ql-image", T("tip_image", language)),
        ("button.ql-video", T("tip_video", language)),
        ("button.ql-clean", T("tip_clean", language)),
    ]
    # Costruiamo l'oggetto JavaScript. json.dumps mette in sicurezza gli
    # apostrophes in the Italian labels (e.g. "un'immagine").
    coppie = []
    for selettore, label in entries:
        coppie.append("  " + json.dumps(selettore) + ": " + json.dumps(label))
    mappa_js = "{\n" + ",\n".join(coppie) + "\n}"

    return """<script>
// Explanatory tooltips for the editor toolbar buttons.
var TOOLBAR_TOOLTIPS = """ + mappa_js + """;

// Adds the tooltip to every toolbar of the page. It is called after the
// Quill editors are created, because Quill builds the toolbar itself.
function applyToolbarTooltips() {
  var barre = document.querySelectorAll('.ql-toolbar');
  for (var i = 0; i < barre.length; i++) {
    for (var selettore in TOOLBAR_TOOLTIPS) {
      var elementi = barre[i].querySelectorAll(selettore);
      for (var j = 0; j < elementi.length; j++) {
        // The dropdowns (font, size, heading...) are wrapped in a
        // .ql-picker span: we put the tooltip on the wrapper, otherwise
        // it would follow the open list of options around.
        elementi[j].setAttribute('data-tooltip', TOOLBAR_TOOLTIPS[selettore]);
      }
    }
  }
}
// The toolbars exist as soon as Quill has been created; we also run it on
// DOMContentLoaded so the buttons we add later are covered too.
document.addEventListener('DOMContentLoaded', applyToolbarTooltips);
</script>"""


def _comments_script(art):
    """
    Generate the comments snippet based on CONFIG["commenti"].
    It supports "giscus", "disqus" or "nessuno" (none).
    """
    sistema = CONFIG.get("comments", "none")

    if sistema == "giscus":
        g = CONFIG["giscus"]
        return f"""
  <section class="commenti">
    <h2>Commenti</h2>
    <script src="https://giscus.app/client.js"
        data-repo="{g['repo']}"
        data-repo-id="{g['repo_id']}"
        data-category="{g['category']}"
        data-category-id="{g['category_id']}"
        data-mapping="pathname"
        data-strict="0"
        data-reactions-enabled="1"
        data-emit-metadata="0"
        data-input-position="bottom"
        data-theme="{g['theme']}"
        data-lang="{CONFIG['language']}"
        crossorigin="anonymous"
        async>
    </script>
  </section>"""

    if sistema == "disqus":
        d = CONFIG["disqus"]
        shortname = d["shortname"]
        # Disqus identifies each thread with a unique URL and identifier.
        page_url = f"{CONFIG['base_url']}/posts/{art['slug']}.html"
        identificatore = art["slug"]
        return f"""
  <section class="commenti">
    <h2>Commenti</h2>
    <div id="disqus_thread"></div>
    <script>
      var disqus_config = function () {{
        this.page.url = "{page_url}";
        this.page.identifier = "{identificatore}";
      }};
      (function() {{
        var d = document, s = d.createElement('script');
        s.src = 'https://{shortname}.disqus.com/embed.js';
        s.setAttribute('data-timestamp', +new Date());
        (d.head || d.body).appendChild(s);
      }})();
    </script>
    <noscript>Abilita JavaScript per vedere i
      <a href="https://disqus.com/?ref_noscript">commenti gestiti da Disqus</a>.
    </noscript>
  </section>"""

    return ""  # "nessuno": no comments


def _format_date(iso_string, language="it"):
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


def archive_file_name(language):
    """Name of the archive file in the given language."""
    if language == "en":
        return "archive.html"
    return "archivio.html"


def _site_header(language="it"):
    prefix = language_url_prefix(language)
    url_home = prefix + "/"
    url_archivio = prefix + "/" + archive_file_name(language)

    # Language switcher in the navbar (top right, where users
    # look for it): a link to the other language's home, compact label.
    other_language = secondary_language()
    if language != main_language():
        other_language = main_language()
    url_altra = language_url_prefix(other_language) + "/"
    other_label = other_language.upper()

    return f"""<a class="skip-to-content" href="#content">{T('salta_contenuto', language)}</a>
  <header class="site">
    <div class="site-brand">
      <h1><a href="{url_home}">{html.escape(CONFIG['site_title'])}</a></h1>
      <p class="site-subtitle">{html.escape(CONFIG['subtitle'])}</p>
    </div>
    <nav class="site-nav">
      <a href="{url_home}">{T('home', language)}</a>
      <a href="{url_home}#articles">{T('articles', language)}</a>
      <a href="{url_archivio}">{T('archivio', language)}</a>
      <a href="/rss.xml">RSS</a>
      <a class="nav-lingua" href="{url_altra}" lang="{other_language}" title="{other_label}">{other_label}</a>
      <button class="tema-toggle" onclick="toggleTheme()" aria-label="Cambia tema" title="Tema chiaro/scuro">
        <span class="tema-icona">&#9789;</span>
      </button>
    </nav>
  </header>"""


def _theme_script():
    """
    Script for the light/dark theme. It applies the saved theme right away
    (to avoid colour flashes while loading) and defines the function that
    changes it. The preference is saved in the user's browser.
    """
    return """<script>
// We apply the saved theme right away, before the page is painted.
(function() {
  try {
    var salvato = localStorage.getItem('pb-tema');
    if (salvato === 'dark') {
      document.documentElement.setAttribute('data-tema', 'dark');
    } else if (salvato === null && window.matchMedia
               && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      // No saved choice: we respect the system preference.
      document.documentElement.setAttribute('data-tema', 'dark');
    }
  } catch (e) { }
})();
// Aligns the code blocks theme (highlight.js) with the site theme.
// The link has id "hljs-tema" and only exists on the article pages.
function updateCodeTheme() {
  var link = document.getElementById('hljs-tema');
  if (!link) { return; }
  var scuro = document.documentElement.getAttribute('data-tema') === 'dark';
  if (scuro) {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css';
  } else {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  }
}
// Switches between light and dark theme and saves the choice.
function toggleTheme() {
  var attuale = document.documentElement.getAttribute('data-tema');
  if (attuale === 'dark') {
    document.documentElement.removeAttribute('data-tema');
    try { localStorage.setItem('pb-tema', 'light'); } catch (e) { }
  } else {
    document.documentElement.setAttribute('data-tema', 'dark');
    try { localStorage.setItem('pb-tema', 'dark'); } catch (e) { }
  }
  updateCodeTheme();
}
// On load, we sync the code theme with the saved one.
document.addEventListener('DOMContentLoaded', updateCodeTheme);
</script>"""


def _seo_data():
    """Return the 'seo' block of the configuration (always a dict)."""
    seo = CONFIG.get("seo", {})
    if not isinstance(seo, dict):
        return {}
    return seo


def _person_jsonld():
    """
    Build the author's schema.org Person, enriched with the configured
    personal SEO data (url, photo, role, bio, social profiles).
    This data helps Google recognise the author as a real person
    (E-E-A-T signals) and connect their public profiles together.
    """
    seo = _seo_data()
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


def _social_meta(language="it"):
    """
    Social meta tags common to every page: site name (og:site_name),
    page language (og:locale) and the X/Twitter account if configured.
    """
    seo = _seo_data()
    if language == "en":
        locale = "en_US"
    else:
        locale = "it_IT"
    lines = []
    lines.append(f'<meta property="og:site_name" content="{html.escape(CONFIG["site_title"])}">')
    lines.append(f'  <meta property="og:locale" content="{locale}">')
    if seo.get("twitter_site"):
        lines.append(f'  <meta name="twitter:site" content="{html.escape(seo["twitter_site"])}">')
    return "\n".join(lines)


def _hreflang_links(path_it, path_en):
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
        text-anchor="middle">{html.escape(initial)}</text>
</svg>
"""


def _favicon_link():
    """
    Return the favicon <link> tag for the pages' head.
    It uses the custom one from the config if set, otherwise the one
    generated automatically at build time (favicon.svg).
    """
    custom_value = _seo_data().get("favicon", "")
    if custom_value != "":
        return f'<link rel="icon" href="{html.escape(custom_value)}">'
    return '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'


def _analytics_snippet():
    """
    Return the analytics snippets for the public pages, or an empty string
    when nothing is configured. Two services are supported, independently:

    - Google Analytics 4: "analytics_id" in config.json (e.g. "G-XXXXXXXXXX").
    - Umami (self-hosted): "umami_url" (the base URL of your Umami
      instance, e.g. "https://stats.ciunix.com") and "umami_website_id"
      (the website UUID shown by Umami). Umami sets no cookies, so it
      needs no consent banner.

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
                '<script defer src="' + html.escape(umami_url) + '/script.js" '
                'data-website-id="' + html.escape(umami_id) + '"></script>')

    return "\n  ".join(parts)


def _site_footer(language="it"):
    year = datetime.now().year
    prefix = language_url_prefix(language)
    url_archivio = prefix + "/" + archive_file_name(language)

    # Configured social profiles: in the footer, for consistency with what
    # we declare to Google in the structured data (sameAs).
    profiles = _seo_data().get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    link_social = []
    for profile in profiles:
        label = html.escape(_profile_label(profile))
        link_social.append(f'<a href="{html.escape(profile)}" rel="me">{label}</a>')
    riga_social = ""
    if len(link_social) > 0:
        riga_social = ('\n    <p class="pie-social">'
                       + " &middot; ".join(link_social) + "</p>")

    return f"""<footer class="site">
    <p>&copy; {year} {html.escape(CONFIG['author'])} &middot;
       <a href="{url_archivio}">{T('archivio', language)}</a> &middot;
       <a href="/rss.xml">RSS</a></p>{riga_social}
  </footer>"""


def generate_article_page(art, language="it", all_articles=None):
    """
    Generate the full HTML of a single article, with SEO and comments.
    The lingua parameter can be "it" (Italian) or "en" (English):
    in English it uses the translated fields and changes the addresses.
    """
    # We pick the right fields based on the requested language.
    prefix = language_url_prefix(language)
    if language == "en":
        title_value = art.get("title_en", "")
        content = art.get("content_en", "")
        description = art.get("description_en", "")
        # If the SEO description is missing, we derive one from the content:
        # a real excerpt of the text is better than repeating the title.
        if description == "":
            description = _excerpt_from_html(content, 155)
        if description == "":
            description = title_value
        page_url = f"{CONFIG['base_url']}{prefix}/posts/{art['slug']}.html"
        language_code = "en"
        back_label = "&larr; " + T("tutti_articoli", "en")
        reading_time = compute_reading_time(content, "en")
    else:
        title_value = art.get("title", "")
        content = art.get("content", "")
        description = art.get("description", "")
        # If the SEO description is missing, we derive one from the content.
        if description == "":
            description = _excerpt_from_html(content, 155)
        if description == "":
            description = title_value
        page_url = f"{CONFIG['base_url']}{prefix}/posts/{art['slug']}.html"
        language_code = "it"
        back_label = "&larr; " + T("tutti_articoli", "it")
        reading_time = compute_reading_time(content, "it")

    tags_html = ""
    if art.get("tags"):
        # Tag links use the prefix of the current language.
        tag_prefix = prefix + "/tag/"
        pieces = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                tag_slug = slugify(t)
                pieces.append(f'<a class="tag" href="{tag_prefix}{tag_slug}.html">#{html.escape(t)}</a>')
        if len(pieces) > 0:
            tags_html = " &middot; " + " ".join(pieces)

    # We generate the table of contents (only for long articles).
    # The function adds the ids to the headings and gives us back the index to show.
    content, toc_html = generate_table_of_contents(content, language)

    # URL of the home in the current language (the root or the subfolder).
    home_url_language = prefix + "/"

    # "Related articles" block (in both languages).
    related_block = ""
    if all_articles is not None:
        related_block = generate_related_block(art, all_articles, language)

    og_image = ""
    if art.get("image"):
        og_image = f'''<meta property="og:image" content="{html.escape(art['image'])}">
  <meta name="twitter:card" content="summary_large_image">'''

    # Meta keywords from the article tags (a light SEO help).
    meta_keywords = ""
    if art.get("tags"):
        clean_tags = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                clean_tags.append(t)
        if len(clean_tags) > 0:
            meta_keywords = f'<meta name="keywords" content="{html.escape(", ".join(clean_tags))}">'

    # Language switcher: it appears only if a confirmed translation exists.
    language_switcher = ""
    translation_ready = art.get("translation_confirmed", False)
    if translation_ready and not html_content_is_empty(art.get("content_en", "")):
        # We build the links to the two versions using the dynamic prefixes.
        prefix_it = language_url_prefix("it")
        prefix_en = language_url_prefix("en")
        link_it = f'{prefix_it}/posts/{art["slug"]}.html'
        link_en = f'{prefix_en}/posts/{art["slug"]}.html'
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
        link_hreflang = _hreflang_links(path_it, path_en)

    # JSON-LD structured data for Google (rich results).
    # Enriched with image and keywords (tags) when available.
    # The author uses the full Person schema (url, photo, role, sameAs):
    # this is the "personal data" that strengthens Google's E-E-A-T signals.
    publisher = {"@type": "Organization", "name": CONFIG["site_title"]}
    site_logo = _seo_data().get("logo", "")
    if site_logo != "":
        publisher["logo"] = {"@type": "ImageObject", "url": site_logo}
    jsonld_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title_value,
        "description": description,
        "author": _person_jsonld(),
        "datePublished": art["date"],
        "dateModified": art.get("date_modified", art["date"]),
        "url": page_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "inLanguage": language_code,
        "publisher": publisher,
    }
    if art.get("image"):
        jsonld_data["image"] = art["image"]
    if art.get("tags"):
        # The tags become the article's keywords.
        keywords = []
        for t in art["tags"].split(","):
            t = t.strip()
            if t != "":
                keywords.append(t)
        if len(keywords) > 0:
            jsonld_data["keywords"] = ", ".join(keywords)
    jsonld = json.dumps(jsonld_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="{language_code}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{html.escape(title_value)} &middot; {html.escape(CONFIG['site_title'])}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="author" content="{html.escape(CONFIG['author'])}">
  <link rel="canonical" href="{page_url}">
  {link_hreflang}
  <meta property="og:title" content="{html.escape(title_value)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{page_url}">
  <meta property="article:published_time" content="{art['date']}">
  <meta property="article:author" content="{html.escape(CONFIG['author'])}">
  {_social_meta(language)}
  {meta_keywords}
  {og_image}
  <link rel="stylesheet" href="/style.css">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(CONFIG['site_title'])}" href="/rss.xml">
  <link id="hljs-tema" rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">
  <script type="application/ld+json">{jsonld}</script>
  {_theme_script()}
</head>
<body>
  {_site_header(language)}
  <article id="content" class="post">
    {language_switcher}
    <p class="breadcrumbs"><a href="{home_url_language}">{T('home', language)}</a> &rsaquo; {html.escape(title_value)}</p>
    <h1>{html.escape(title_value)}</h1>
    <div class="meta">{_format_date(art['date'], language)} &middot; {reading_time}{tags_html}</div>
    {toc_html}
    {content}
{generate_author_box(language)}{generate_article_nav(art, all_articles, language)}    <p style="margin-top:2rem"><a href="{home_url_language}">{back_label}</a></p>
  </article>
  {related_block}
  {_comments_script(art)}
  {_site_footer(language)}
  <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
  <script>
    // We colour the syntax in the code blocks.
    document.querySelectorAll("pre.ql-syntax").forEach(function(blocco) {{
      hljs.highlightElement(blocco);
    }});
  </script>
</body>
</html>"""


def _profile_label(url):
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


def generate_author_box(language="it"):
    """
    Generate the "Written by" box shown at the bottom of every article,
    with photo, name, role, short bio and links to the author's social
    profiles. It uses the data of the "SEO and author data" section of
    the Settings. If nothing but the name is configured, the box is not
    shown (a half-empty box makes the page worse, not better).
    """
    seo = _seo_data()
    role = seo.get("author_role", "")
    bio = seo.get("author_bio", "")
    photo = seo.get("author_image", "")
    profiles = seo.get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    if role == "" and bio == "" and photo == "" and len(profiles) == 0:
        return ""

    name_value = html.escape(CONFIG["author"])
    author_url_value = seo.get("author_url", "")
    if author_url_value != "":
        name_html = f'<a href="{html.escape(author_url_value)}">{name_value}</a>'
    else:
        name_html = name_value

    photo_block = ""
    if photo != "":
        photo_block = (f'<img class="author-box-photo" src="{html.escape(photo)}" '
                       f'alt="{name_value}" loading="lazy">')

    role_row = ""
    if role != "":
        role_row = f'<p class="author-box-role">{html.escape(role)}</p>'

    riga_bio = ""
    if bio != "":
        riga_bio = f'<p class="author-box-bio">{html.escape(bio)}</p>'

    link_social = []
    for profile in profiles:
        label = html.escape(_profile_label(profile))
        link_social.append(f'<a href="{html.escape(profile)}" rel="me">{label}</a>')
    riga_social = ""
    if len(link_social) > 0:
        riga_social = ('<p class="author-box-social">'
                       + " &middot; ".join(link_social) + "</p>")

    return f"""    <aside class="author-box">
      {photo_block}
      <div class="author-box-testo">
        <p class="author-box-name"><span class="author-box-label">{T('scritto_da', language)}</span> {name_html}</p>
        {role_row}
        {riga_bio}
        {riga_social}
      </div>
    </aside>
"""


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

    def title_of(article):
        if language != main_language():
            return article.get("title_en", article.get("title", ""))
        return article.get("title", "")

    newer_block = '<span class="article-nav-empty"></span>'
    if posizione > 0:
        neighbor = visibili[posizione - 1]
        newer_block = (
            f'<a class="article-nav-link" href="{post_prefix}{neighbor["slug"]}.html">'
            f'<span class="article-nav-label">&larr; {T("nav_piu_recente", language)}</span>'
            f'<span class="article-nav-title">{html.escape(title_of(neighbor))}</span></a>')

    older_block = '<span class="article-nav-empty"></span>'
    if posizione < len(visibili) - 1:
        neighbor = visibili[posizione + 1]
        older_block = (
            f'<a class="article-nav-link article-nav-right" href="{post_prefix}{neighbor["slug"]}.html">'
            f'<span class="article-nav-label">{T("nav_meno_recente", language)} &rarr;</span>'
            f'<span class="article-nav-title">{html.escape(title_of(neighbor))}</span></a>')

    if posizione == 0 and len(visibili) == 1:
        return ""

    return f"""    <nav class="article-nav">
      {newer_block}
      {older_block}
    </nav>
"""


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


def _card_slug(title_value):
    """Generate the slug (file name) of a card from its title."""
    slug = slugify(title_value)
    if slug == "":
        slug = "pagina"
    return slug


def _excerpt_from_html(html_content_value, lunghezza=120):
    """Derive a short text excerpt from the HTML content of a card."""
    text = _plain_text(html_content_value)
    if len(text) <= lunghezza:
        return text
    return text[:lunghezza].rstrip() + "..."


def generate_home_cards(language="it"):
    """
    Generate the homepage cards block. Each card is a link leading to its
    own dedicated page. It only shows the active cards that have content.
    """
    prefix = language_url_prefix(language) + "/pagine/"
    if language == "en":
        open_label = "Open"
    else:
        open_label = "Apri"
    section_title = T("esplora", language)

    card_lista = CONFIG.get("home_cards", [])
    card_html = []
    for card in card_lista:
        active = card.get("active", False)
        if not active:
            continue
        content = card.get("content", "")
        if html_content_is_empty(content):
            continue
        title_value = card.get("title", "")
        slug = _card_slug(title_value)
        excerpt = _excerpt_from_html(content)
        card_html.append(f"""    <a class="home-card" href="{prefix}{slug}.html">
      <h3 class="home-card-title">{html.escape(title_value)}</h3>
      <p class="home-card-excerpt">{html.escape(excerpt)}</p>
      <span class="home-card-link">{open_label} &rarr;</span>
    </a>""")

    if len(card_html) == 0:
        return ""

    block = "\n".join(card_html)
    return f"""  <section class="cards-section">
    <h2 class="articles-heading">{section_title}</h2>
    <div class="home-cards-grid">
{block}
    </div>
  </section>
"""


def generate_card_page(card, language="it"):
    """
    Generate the HTML page of a single card (Biography, Projects, etc.)
    with a polished style: prominent header and readable content.
    """
    title_value = card.get("title", "")
    content = card.get("content", "")
    slug = _card_slug(title_value)
    description = _excerpt_from_html(content, 150)
    # The canonical must point to the version in the current language:
    # it used to always point to /pagine/, even from the English version,
    # declaring a wrong canonical to Google for the /en/ pages.
    prefix = language_url_prefix(language)
    url_canonico = f"{CONFIG['base_url']}{prefix}/pagine/{slug}.html"
    home_url_language = prefix + "/"

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{html.escape(title_value)} &middot; {html.escape(CONFIG['site_title'])}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{url_canonico}">
  <meta property="og:title" content="{html.escape(title_value)}">
  <meta property="og:type" content="article">
  <link rel="stylesheet" href="/style.css">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(CONFIG['site_title'])}" href="/rss.xml">
  {_theme_script()}
</head>
<body>
  {_site_header(language)}
  <main id="content" class="main-content">
    <header class="card-hero">
      <p class="breadcrumbs"><a href="{home_url_language}">{T('home', language)}</a> &rsaquo; {html.escape(title_value)}</p>
      <h1 class="card-hero-title">{html.escape(title_value)}</h1>
    </header>
    <article class="card-page">
      {content}
    </article>
    <p class="card-ritorno"><a href="{home_url_language}">&larr; {T('torna_homepage', language)}</a></p>
  </main>
  {_site_footer(language)}
</body>
</html>"""


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


def pagination_folder(language):
    """Name of the folder holding the next pages ("pagina" or "page")."""
    if language == "en":
        return "page"
    return "pagina"


def generate_homepage(articles, language="it", page=1, totale_pagine=1):
    """
    Generate the homepage: free content at the top + article grid + search.
    With lingua="en" it generates the English version in /en/ (UI texts and
    links translated). With pagina > 1 it generates the next pages
    (/pagina/2.html, /pagina/3.html...): the introduction and the cards only
    appear on page 1, the following pages show articles only.
    """
    # Link prefix, derived from the site's main language.
    post_prefix = language_url_prefix(language) + "/posts/"

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

    feed_items = []
    for art in page_articles:
        # The translated fields are always the _en ones (translation is IT<->EN).
        if language != main_language():
            card_title = art.get("title_en", "")
            card_description = art.get("description_en", "")
            card_content = art.get("content_en", "")
            card_preview = art.get("preview_en", "")
        else:
            card_title = art.get("title", "")
            card_description = art.get("description", "")
            card_content = art.get("content", "")
            card_preview = art.get("preview", "")

        # Card preview (for readers; this is not the SEO meta description).
        # Priority: 1) preview written by the author, 2) automatic excerpt
        # of the content (about 9 lines), 3) SEO description as a last resort.
        preview_text = card_preview
        if preview_text == "":
            # Short excerpt: 2-3 lines. A long excerpt turns every card into
            # a wall of text and makes the homepage impossible to scan.
            preview_text = _excerpt_from_html(card_content, 200)
        if preview_text == "":
            preview_text = card_description
        excerpt = ""
        if preview_text != "":
            excerpt = f'<p class="card-excerpt">{html.escape(preview_text)}</p>'

        feed_items.append(f"""    <a class="article-card" href="{post_prefix}{art['slug']}.html">
      <div class="card-date">{_format_date(art['date'], language)}</div>
      <h3 class="card-title">{html.escape(card_title)}</h3>
      {excerpt}
      <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
    </a>""")

    if len(feed_items) > 0:
        lista = "\n".join(feed_items)
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
        author_photo = _seo_data().get("author_image", "")
        if author_photo != "":
            avatar = (f'<img class="home-avatar" src="{html.escape(author_photo)}" '
                      f'alt="{html.escape(CONFIG["author"])}">\n    ')
        home_block = f"""  <section class="home-intro">
    {avatar}{home_content}
  </section>
"""

    # Editorial cards (bio, projects, photos, notices).
    cards_block = generate_home_cards(language)

    # --- Navigation between pages (pagination) ---
    # It appears only if there is more than one page. The "newer" link on
    # page 2 goes back to the homepage, not to /pagina/1.html (which does not exist).
    prefix = language_url_prefix(language)
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
            link_precedente = f'<span class="paginazione-vuoto">&nbsp;</span>'
        if page < totale_pagine:
            url_successiva = f"{prefix}/{page_folder}/{page + 1}.html"
            link_successiva = f'<a href="{url_successiva}">{T("pagina_meno_recenti", language)}</a>'
        else:
            link_successiva = f'<span class="paginazione-vuoto">&nbsp;</span>'
        pagination_block = f"""    <nav class="paginazione">
      {link_precedente}
      <span class="paginazione-info">{T('pagina_di', language)} {page} {T('pagina_su', language)} {totale_pagine}</span>
      {link_successiva}
    </nav>
"""

    # --- Articles section (with search) as a standalone block ---
    articles_block = f"""  <section id="articles" class="articles-section">
    <h2 class="articles-heading">{T('articles', language)}</h2>

    <div class="search-box">
      <input type="search" id="search-box-input" placeholder="{T('cerca_articoli', language)}"
             autocomplete="off" aria-label="Cerca">
      <p id="search-box-info"></p>
    </div>

    <div class="articles-grid" id="lista-articoli">
{lista}
    </div>
{pagination_block}  </section>
"""

    # --- Order of the homepage sections, configurable ---
    # The author can reorder "intro", "articoli" and "card" from the config
    # ("ordine_home" field) to give priority to what the reader
    # should see first. Sections not listed are appended at the end.
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
    ordered_content = "".join(home_body)

    # --- Homepage SEO ---
    base = CONFIG["base_url"].rstrip("/")
    if page > 1:
        url_canonico_home = (base + language_url_prefix(language) + "/"
                             + pagination_folder(language) + f"/{page}.html")
    else:
        url_canonico_home = base + language_url_prefix(language) + "/"
    # The two homepages always exist: we declare both with hreflang.
    hreflang_home = _hreflang_links(
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
        "author": _person_jsonld(),
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{html.escape(CONFIG['site_title'])} &middot; {html.escape(CONFIG['subtitle'])}</title>
  <meta name="description" content="{html.escape(CONFIG['subtitle'])}">
  <meta name="author" content="{html.escape(CONFIG['author'])}">
  <link rel="canonical" href="{url_canonico_home}">
  {hreflang_home}
  <meta property="og:title" content="{html.escape(CONFIG['site_title'])}">
  <meta property="og:description" content="{html.escape(CONFIG['subtitle'])}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{url_canonico_home}">
  {_social_meta(language)}
  <link rel="stylesheet" href="/style.css">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(CONFIG['site_title'])}" href="/rss.xml">
  <script type="application/ld+json">{jsonld_home}</script>
  {_theme_script()}
</head>
<body>
  {_site_header(language)}

  <main id="content" class="main-content">
{ordered_content}
  </main>

  {_site_footer(language)}

  <script>
  // Browser-side search: it downloads the JSON index once and filters locally.
  // It shows a snippet of the context around the searched word, with
  // highlighting. It searches both Italian and English. A 100% static site.
  (function() {{
    const input = document.getElementById('search-box-input');
    const info = document.getElementById('search-box-info');
    const lista = document.getElementById('lista-articoli');
    let indice = [];

    // Variables that depend on the page language (injected from Python).
    const LINGUA_PAGINA = "{language}";
    const PREFISSO_POST = "{post_prefix}";
    const ETICHETTA_LEGGI = "{T('leggi_articolo', language)}";
    const MSG_SEARCH_UNAVAILABLE = "{T('js_search_unavailable', language)}";
    const MSG_NO_RESULTS_FOR = "{T('js_search_no_results', language)}";
    const MSG_RESULTS_FOR = "{T('js_search_results_for', language)}";
    // Slice of articles shown on this page (for the pagination).
    // When the search is cleared, we restore ONLY this slice,
    // not the whole index. The search itself always searches everything.
    const PAGINA_INIZIO = {start};
    const PAGINA_FINE = {end};

    // Returns the date formatted in the page language.
    function articleDate(a) {{
      if (LINGUA_PAGINA === 'en' && a.date_en) {{
        return a.date_en;
      }}
      return a.date_it;
    }}

    // Returns the right title based on the page language.
    function articleTitle(a) {{
      if (LINGUA_PAGINA === 'en') {{
        if (a.title_en) {{
          return a.title_en;
        }}
        return a.title;
      }}
      return a.title;
    }}

    // Tells whether an article should be shown in this language.
    // On the English home we only show articles with a confirmed translation.
    function articleIsVisible(a) {{
      if (LINGUA_PAGINA === 'en') {{
        return a.has_en === true;
      }}
      return true;
    }}

    // Loads the article index generated at build time.
    fetch('/search-index.json')
      .then(r => r.json())
      .then(dati => {{ indice = dati; }})
      .catch(() => {{ info.textContent = MSG_SEARCH_UNAVAILABLE; }});

    // Strips accents and lowercases, for more forgiving comparisons.
    function normalizeText(s) {{
      if (s === null || s === undefined) {{
        return '';
      }}
      return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    }}

    // Bolds the occurrences of the term in a text (already made safe).
    function highlight(testoSicuro, termine) {{
      const testoNorm = normalizeText(testoSicuro);
      const termineNorm = normalizeText(termine);
      let risultato = '';
      let posizione = 0;
      let trovato = testoNorm.indexOf(termineNorm, posizione);
      while (trovato !== -1) {{
        risultato = risultato + testoSicuro.substring(posizione, trovato);
        risultato = risultato + '<mark>' +
          testoSicuro.substring(trovato, trovato + termine.length) + '</mark>';
        posizione = trovato + termine.length;
        trovato = testoNorm.indexOf(termineNorm, posizione);
      }}
      risultato = risultato + testoSicuro.substring(posizione);
      return risultato;
    }}

    // Derives a text snippet around the first occurrence of the term.
    function extractSnippet(testo, termine) {{
      const testoNorm = normalizeText(testo);
      const termineNorm = normalizeText(termine);
      const posizione = testoNorm.indexOf(termineNorm);
      if (posizione === -1) {{
        return '';
      }}
      // We take a bit of text before and after the word we found.
      let inizio = posizione - 60;
      if (inizio < 0) {{
        inizio = 0;
      }}
      let fine = posizione + termine.length + 60;
      if (fine > testo.length) {{
        fine = testo.length;
      }}
      let frammento = testo.substring(inizio, fine);
      if (inizio > 0) {{
        frammento = '...' + frammento;
      }}
      if (fine < testo.length) {{
        frammento = frammento + '...';
      }}
      // We make the text safe and then highlight the term.
      return highlight(escapeHtml(frammento), termine);
    }}

    function searchArticles(q) {{
      const termine = q.trim();
      const termineNorm = normalizeText(termine);
      if (termineNorm === '') {{
        // Empty query: restore the original full list.
        info.textContent = '';
        renderAll();
        return;
      }}

      // For each article we check where the term appears.
      const risultati = [];
      for (let i = 0; i < indice.length; i++) {{
        const a = indice[i];
        // On the English home we skip the articles with no translation.
        if (articleIsVisible(a) === false) {{
          continue;
        }}
        const inTitolo = normalizeText(a.title).includes(termineNorm);
        const inDescr = normalizeText(a.description).includes(termineNorm);
        const inTags = normalizeText(a.tags).includes(termineNorm);
        const inTesto = normalizeText(a.text).includes(termineNorm);
        const inTestoEn = normalizeText(a.text_en).includes(termineNorm);
        const inTitoloEn = normalizeText(a.title_en).includes(termineNorm);

        if (inTitolo || inDescr || inTags || inTesto || inTestoEn || inTitoloEn) {{
          // We build the snippet from the point where the word was found.
          let snippet = '';
          if (LINGUA_PAGINA === 'en' && inTestoEn) {{
            snippet = extractSnippet(a.text_en, termine);
          }} else if (inTesto) {{
            snippet = extractSnippet(a.text, termine);
          }} else if (inTestoEn) {{
            snippet = extractSnippet(a.text_en, termine);
          }} else if (inDescr) {{
            snippet = extractSnippet(a.description, termine);
          }}
          risultati.push({{ articolo: a, snippet: snippet }});
        }}
      }}

      renderResults(risultati, termine);
      if (risultati.length === 0) {{
        info.textContent = MSG_NO_RESULTS_FOR + ' "' + termine + '".';
      }} else {{
        info.textContent = risultati.length + ' ' + MSG_RESULTS_FOR + ' "' + termine + '".';
      }}
    }}

    // Shows the search results, with highlighted title and snippet.
    function renderResults(risultati, termine) {{
      if (risultati.length === 0) {{
        lista.innerHTML = '';
        return;
      }}
      let html = '';
      for (let i = 0; i < risultati.length; i++) {{
        const a = risultati[i].articolo;
        const snippet = risultati[i].snippet;
        let bloccoSnippet = '';
        if (snippet !== '') {{
          bloccoSnippet = '<p class="card-snippet">' + snippet + '</p>';
        }}
        html = html +
          '<a class="article-card" href="' + PREFISSO_POST + a.slug + '.html">' +
          '<div class="card-date">' + articleDate(a) + '</div>' +
          '<h3 class="card-title">' + highlight(escapeHtml(articleTitle(a)), termine) + '</h3>' +
          bloccoSnippet +
          '<span class="card-read-more">' + ETICHETTA_LEGGI + ' &rarr;</span>' +
          '</a>';
      }}
      lista.innerHTML = html;
    }}

    // Shows every article (the initial state, with no search).
    function render(elenco) {{
      if (elenco.length === 0) {{
        lista.innerHTML = '';
        return;
      }}
      let html = '';
      for (let i = 0; i < elenco.length; i++) {{
        const a = elenco[i];
        if (articleIsVisible(a) === false) {{
          continue;
        }}
        // Card preview. Priority: preview written by the author,
        // then automatic excerpt (about 9 lines), then SEO description.
        let testoAnteprima = '';
        if (LINGUA_PAGINA === 'en' && a.preview_en) {{
          testoAnteprima = a.preview_en;
        }} else if (a.preview) {{
          testoAnteprima = a.preview;
        }}
        if (!testoAnteprima) {{
          let fonte = a.text;
          if (LINGUA_PAGINA === 'en' && a.text_en) {{
            fonte = a.text_en;
          }}
          if (fonte) {{
            testoAnteprima = fonte.substring(0, 640);
            if (fonte.length > 640) {{
              testoAnteprima = testoAnteprima + '...';
            }}
          }}
        }}
        if (!testoAnteprima) {{
          testoAnteprima = a.description;
        }}
        let estratto = '';
        if (testoAnteprima) {{
          estratto = '<p class="card-excerpt">' + escapeHtml(testoAnteprima) + '</p>';
        }}
        html = html +
          '<a class="article-card" href="' + PREFISSO_POST + a.slug + '.html">' +
          '<div class="card-date">' + articleDate(a) + '</div>' +
          '<h3 class="card-title">' + escapeHtml(articleTitle(a)) + '</h3>' +
          estratto +
          '<span class="card-read-more">' + ETICHETTA_LEGGI + ' &rarr;</span>' +
          '</a>';
      }}
      lista.innerHTML = html;
    }}

    function renderAll() {{
      // First we filter by language, then we take the page slice.
      const visibili = [];
      for (let i = 0; i < indice.length; i++) {{
        if (articleIsVisible(indice[i])) {{
          visibili.push(indice[i]);
        }}
      }}
      render(visibili.slice(PAGINA_INIZIO, PAGINA_FINE));
    }}

    function escapeHtml(s) {{
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }}

    let timer;
    input.addEventListener('input', function() {{
      clearTimeout(timer);
      timer = setTimeout(function() {{ searchArticles(input.value); }}, 120);
    }});
  }})();
  </script>
</body>
</html>"""


def generate_archive_page(articles, language="it"):
    """
    Generate the archive page: every article grouped by year, in a compact
    list (date and title), from the newest to the oldest.
    In the secondary language only the translated articles appear.
    """
    prefix = language_url_prefix(language)
    post_prefix = prefix + "/posts/"
    url_home = prefix + "/"

    # We group the articles by year of publication.
    # A dictionary { year: [articles...] }, then we sort the years.
    by_year = {}
    for art in articles:
        if language != main_language():
            if not art.get("translation_confirmed", False):
                continue
            item_title = art.get("title_en", "")
        else:
            item_title = art.get("title", "")
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
            short_date = _format_date(art["date"], language)
            feed_items.append(
                f'      <li><span class="archive-date">{short_date}</span> '
                f'<a href="{post_prefix}{art["slug"]}.html">{html.escape(url_entry["title"])}</a></li>')
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
    hreflang = _hreflang_links(
        language_url_prefix("it") + "/" + archive_file_name("it"),
        language_url_prefix("en") + "/" + archive_file_name("en"))

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{T('archivio_titolo', language)} &middot; {html.escape(CONFIG['site_title'])}</title>
  <meta name="description" content="{T('archivio_descrizione', language)}">
  <link rel="canonical" href="{url_canonico}">
  {hreflang}
  {_social_meta(language)}
  <link rel="stylesheet" href="/style.css">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(CONFIG['site_title'])}" href="/rss.xml">
  {_theme_script()}
</head>
<body>
  {_site_header(language)}
  <main id="content" class="main-content">
    <section class="articles-section">
      <p class="breadcrumbs"><a href="{url_home}">{T('home', language)}</a> &rsaquo; {T('archivio', language)}</p>
      <h1 class="articles-heading">{T('archivio_titolo', language)}</h1>
{body}
    </section>
  </main>
  {_site_footer(language)}
</body>
</html>"""


def generate_rss(articles):
    """Generate the RSS 2.0 feed."""
    ora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    feed_items = []
    for art in articles[:20]:
        try:
            dt = datetime.fromisoformat(art["date"])
            pubdate = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            pubdate = ora
        url = f"{CONFIG['base_url']}/posts/{art['slug']}.html"
        desc = art.get("description") or art["title"]
        feed_items.append(f"""    <item>
      <title>{html.escape(art['title'])}</title>
      <link>{url}</link>
      <guid>{url}</guid>
      <pubDate>{pubdate}</pubDate>
      <description>{html.escape(desc)}</description>
    </item>""")

    items = "\n".join(feed_items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(CONFIG['site_title'])}</title>
    <atom:link href="{CONFIG['base_url']}/rss.xml" rel="self" type="application/rss+xml"/>
    <link>{CONFIG['base_url']}/</link>
    <description>{html.escape(CONFIG['subtitle'])}</description>
    <language>{CONFIG['language']}</language>
    <lastBuildDate>{ora}</lastBuildDate>
{items}
  </channel>
</rss>"""


CSS = """/* Clean, fast styling for a blog. System fonts, a few KB, zero frameworks. */
:root {
  --testo:#1a1a1a; --secondario:#666; --link:#0066cc;
  --bordo:#e2e2e2; --codice-bg:#f5f5f5; --larghezza:720px;
  --larghezza-home:1000px; --card-bg:#fff; --card-hover:#f8f9fb;
  --sfondo:#fff; --hero-1:#f0f6ff; --hero-2:#f7f4ff; --hero-bordo:#e8eefc;
}
/* Dark theme: it only changes the variables, everything else adapts by itself. */
html[data-tema="dark"] {
  --testo:#e4e4e7; --secondario:#a1a1aa; --link:#6ba9ff;
  --bordo:#2e2e35; --codice-bg:#1c1c20; --card-bg:#18181b; --card-hover:#202028;
  --sfondo:#101013; --hero-1:#15203a; --hero-2:#1d1733; --hero-bordo:#2a2f45;
}
/* In dark mode, the elements with fixed colours must be adapted by hand,
   otherwise they stay dark on dark and become unreadable. */
html[data-tema="dark"] .home-intro p { color:#cbd5e1; }
html[data-tema="dark"] .home-intro p strong { color:#f1f5f9; }
html[data-tema="dark"] .card-snippet,
html[data-tema="dark"] .card-excerpt,
html[data-tema="dark"] .card-date,
html[data-tema="dark"] .card-read-more,
html[data-tema="dark"] .home-card-excerpt,
html[data-tema="dark"] .meta { color:var(--secondario); }
html[data-tema="dark"] .card-title,
html[data-tema="dark"] .home-card-title { color:var(--testo); }
html[data-tema="dark"] .card-snippet mark,
html[data-tema="dark"] .card-title mark { background:#7a5a00; color:#fff; }
/* Gradient headings: in dark mode we lighten the gradient for readability. */
html[data-tema="dark"] .home-intro h1, html[data-tema="dark"] .home-intro h2,
html[data-tema="dark"] .card-hero-title {
  background:linear-gradient(120deg, #6ba9ff, #b39dff); -webkit-background-clip:text;
  background-clip:text; -webkit-text-fill-color:transparent;
}
html[data-tema="dark"] .articles-heading { color:var(--testo); }
html[data-tema="dark"] .card-page { color:var(--testo); }
* { box-sizing:border-box; }
body {
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:18px; line-height:1.65; color:var(--testo);
  margin:0; background:var(--sfondo);
}
/* Header with navbar: title on the left, navigation on the right. */
header.site {
  max-width:var(--larghezza-home); margin:0 auto;
  padding:1.5rem 1.2rem; display:flex; justify-content:space-between;
  align-items:center; flex-wrap:wrap; gap:1rem;
  border-bottom:1px solid var(--bordo);
}
header.site .site-brand h1 { font-size:1.5rem; margin:0; }
header.site .site-brand h1 a { color:var(--testo); text-decoration:none; }
header.site .site-brand .site-subtitle { color:var(--secondario); font-size:0.9rem; margin:0.2rem 0 0; }
header.site .site-nav { display:flex; gap:1.5rem; }
header.site .site-nav a {
  color:var(--testo); text-decoration:none; font-size:0.95rem;
  font-weight:500; padding:0.3rem 0; border-bottom:2px solid transparent;
}
header.site .site-nav a:hover { border-bottom-color:var(--link); color:var(--link); }
.tema-toggle { background:none; border:1px solid var(--bordo); border-radius:50%; width:36px; height:36px;
  cursor:pointer; font-size:1.1rem; line-height:1; color:var(--testo); display:inline-flex;
  align-items:center; justify-content:center; padding:0; }
.tema-toggle:hover { border-color:var(--link); color:var(--link); }
/* Main container: wider on the home, for the grid. */
.main-content { max-width:var(--larghezza-home); margin:0 auto; padding:2.5rem 1.2rem 4rem; }
a { color:var(--link); }
h1,h2,h3 { line-height:1.25; font-weight:600; }
article.post h1 { font-size:2rem; margin:0 0 0.4rem; }
.meta { color:var(--secondario); font-size:0.9rem; margin-bottom:2rem; }
.tag { font-size:0.8rem; color:var(--secondario); text-decoration:none; }
.tag:hover { color:var(--link); }
.breadcrumbs { font-size:0.85rem; color:var(--secondario); margin:0 0 0.5rem; }
.breadcrumbs a { color:var(--link); text-decoration:none; }
.text-tag-conteggio { color:var(--secondario); font-size:0.9rem; margin:0 0 1.5rem; }
/* Table of contents (TOC) for long articles. */
.table-of-contents { background:var(--card-bg); border:1px solid var(--bordo); border-radius:10px;
  padding:1rem 1.4rem; margin:0 0 2rem; }
.table-of-contents .toc-title { font-weight:700; margin:0 0 0.5rem; font-size:0.95rem; text-transform:uppercase; letter-spacing:0.03em; color:var(--secondario); }
.table-of-contents ul { list-style:none; padding:0; margin:0; }
.table-of-contents li { margin:0.3rem 0; }
.table-of-contents li.toc-h3 { padding-left:1.2rem; font-size:0.92rem; }
.table-of-contents a { color:var(--link); text-decoration:none; }
.table-of-contents a:hover { text-decoration:underline; }
/* Related articles block at the bottom of the article. */
.related-articles { max-width:var(--larghezza); margin:3rem auto 0; padding:2rem 1.2rem 0; border-top:1px solid var(--bordo); }
/* Page of a card (Biography, Projects, About). */
.card-hero { text-align:center; padding:2.5rem 1rem 1.5rem; margin-bottom:2rem;
  background:linear-gradient(135deg, var(--hero-1) 0%, var(--hero-2) 100%);
  border:1px solid var(--hero-bordo); border-radius:16px; }
.card-hero .breadcrumbs { justify-content:center; }
.card-hero-title { font-size:2rem; margin:0.3rem 0 0; letter-spacing:-0.02em;
  background:linear-gradient(120deg, #0066cc, #5b3df5); -webkit-background-clip:text;
  background-clip:text; -webkit-text-fill-color:transparent; font-weight:700; }
.card-page { max-width:var(--larghezza); margin:0 auto; font-size:1.05rem; line-height:1.7; }
.card-page img { max-width:100%; border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.08); margin:1rem 0; }
.card-ritorno { max-width:var(--larghezza); margin:3rem auto 0; }
.card-ritorno a { color:var(--link); text-decoration:none; }
.language-switcher-home { text-align:right; margin:0 0 1rem; }
.language-switcher-home a { color:var(--link); text-decoration:none; font-size:0.9rem; }
/* Grid of clickable cards for the articles. */
.articles-grid {
  display:flex; flex-direction:column; gap:1rem;
}
.article-card {
  display:flex; flex-direction:column; text-decoration:none; color:var(--testo);
  background:var(--card-bg); border:1px solid var(--bordo); border-radius:12px;
  padding:1.3rem 1.5rem; transition:transform 0.15s, box-shadow 0.15s, background 0.15s;
}
.article-card:hover {
  transform:translateY(-3px); box-shadow:0 8px 24px rgba(0,0,0,0.08);
  background:var(--card-hover);
}
.card-date { color:var(--secondario); font-size:0.8rem; margin-bottom:0.4rem; }
.card-title { font-size:1.2rem; margin:0 0 0.5rem; line-height:1.3; }
.card-excerpt { color:var(--secondario); font-size:0.95rem; margin:0 0 1rem; flex-grow:1; line-height:1.6;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
/* Author avatar in the homepage hero. */
.home-avatar { width:96px; height:96px; border-radius:50%; object-fit:cover;
  border:3px solid var(--sfondo); box-shadow:0 2px 10px rgba(0,0,0,0.12);
  margin:0 auto 1rem; display:block; }
/* "Written by" box at the bottom of the articles. */
.author-box { display:flex; gap:1.2rem; align-items:flex-start;
  background:var(--card-bg); border:1px solid var(--bordo); border-radius:12px;
  padding:1.3rem 1.5rem; margin:3rem 0 0; }
.author-box-photo { width:64px; height:64px; border-radius:50%; object-fit:cover; flex-shrink:0; }
.author-box-name { margin:0 0 0.2rem; font-weight:700; }
.author-box-name a { color:var(--testo); text-decoration:none; }
.author-box-name a:hover { color:var(--link); }
.author-box-label { font-weight:400; color:var(--secondario); font-size:0.85rem; }
.author-box-role { margin:0 0 0.4rem; color:var(--secondario); font-size:0.9rem; }
.author-box-bio { margin:0 0 0.5rem; font-size:0.95rem; line-height:1.55; }
.author-box-social { margin:0; font-size:0.88rem; }
.author-box-social a { color:var(--link); text-decoration:none; }
.author-box-social a:hover { text-decoration:underline; }
/* Navigation between articles (newer / older). */
.article-nav { display:flex; justify-content:space-between; gap:1rem; margin:1.5rem 0 0; }
.article-nav-link { flex:1; max-width:48%; text-decoration:none; padding:0.8rem 1rem;
  border:1px solid var(--bordo); border-radius:10px; background:var(--card-bg); }
.article-nav-link:hover { border-color:var(--link); }
.article-nav-right { text-align:right; }
.article-nav-label { display:block; font-size:0.78rem; color:var(--secondario);
  text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.25rem; }
.article-nav-title { display:block; color:var(--testo); font-size:0.92rem;
  font-weight:600; line-height:1.35; }
.article-nav-empty { flex:1; max-width:48%; }
@media (max-width: 640px) {
  .article-nav { flex-direction:column; }
  .article-nav-link, .article-nav-empty { max-width:100%; }
  .article-nav-empty { display:none; }
  .author-box { flex-direction:column; align-items:center; text-align:center; }
}
/* Language switcher in the navbar. */
.nav-lingua { font-weight:700; font-size:0.85rem; border:1px solid var(--bordo);
  border-radius:6px; padding:0.15rem 0.5rem; }
/* Social links in the footer. */
.pie-social { margin:0.4rem 0 0; }
.pie-social a { color:var(--secondario); text-decoration:none; }
.pie-social a:hover { color:var(--link); }
/* Skip link: invisible until it receives keyboard focus. */
.skip-to-content { position:absolute; left:-9999px; top:0; background:var(--link);
  color:#fff; padding:0.6rem 1rem; border-radius:0 0 8px 0; z-index:100; text-decoration:none; }
.skip-to-content:focus { left:0; }
/* Visible focus indicator for people navigating by keyboard. */
a:focus-visible, button:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible {
  outline:2px solid var(--link); outline-offset:2px; }
/* Context snippet in the search results, with the term highlighted. */
.card-snippet { color:var(--secondario); font-size:0.9rem; margin:0 0 1rem; flex-grow:1; line-height:1.5; }
.card-snippet mark, .card-title mark { background:#fff3b0; color:inherit; padding:0 2px; border-radius:2px; }
.card-read-more { color:var(--link); font-size:0.88rem; font-weight:500; margin-top:auto; }
.no-articles { color:var(--secondario); }
/* Archive page: compact list by year, date aligned left. */
.archive-year h2 { font-size:1.3rem; margin:2rem 0 0.6rem; color:var(--testo);
  border-bottom:1px solid var(--bordo); padding-bottom:0.3rem; }
.archive-list { list-style:none; padding:0; margin:0; }
.archive-list li { margin:0.45rem 0; display:flex; gap:1rem; align-items:baseline; }
.archive-date { color:var(--secondario); font-size:0.85rem; min-width:9.5rem; flex-shrink:0; }
.archive-list a { color:var(--testo); text-decoration:none; }
.archive-list a:hover { color:var(--link); text-decoration:underline; }
@media (max-width: 640px) {
  .archive-list li { flex-direction:column; gap:0.1rem; margin:0.8rem 0; }
  .archive-date { min-width:0; }
}
/* Navigation between the homepage pages (pagination). */
.paginazione { display:flex; justify-content:space-between; align-items:center;
  margin:2rem 0 0; gap:1rem; }
.paginazione a { color:var(--link); text-decoration:none; font-size:0.95rem;
  padding:0.5rem 1rem; border:1px solid var(--bordo); border-radius:8px; }
.paginazione a:hover { border-color:var(--link); }
.paginazione .paginazione-vuoto { visibility:hidden; }
.paginazione .paginazione-info { color:var(--secondario); font-size:0.85rem; }
pre { background:var(--codice-bg); padding:1rem 1.2rem; border-radius:6px; overflow-x:auto; font-size:0.85rem; line-height:1.5; }
pre.ql-syntax, pre code { font-family:"SF Mono",Menlo,Monaco,Consolas,monospace; tab-size:4; }
pre.ql-syntax { background:var(--codice-bg); border:1px solid var(--bordo); }
/* Tables (including those pasted from Word). On mobile they scroll horizontally.
   The backgrounds use the theme variables: they used to be fixed light colours
   that became unreadable in dark mode (light text on a light background). */
.article-table { border-collapse:collapse; width:100%; margin:1.5rem 0; font-size:0.92rem; display:block; overflow-x:auto; }
.article-table th, .article-table td { border:1px solid var(--bordo); padding:0.6rem 0.8rem; text-align:left; vertical-align:top; }
.article-table th { background:var(--codice-bg); font-weight:600; }
.article-table tr:nth-child(even) td { background:var(--card-hover); }
.raw-html-block { margin:0; }
code { font-family:"SF Mono",Menlo,Monaco,Consolas,monospace; font-size:0.88em; }
p code,li code { background:var(--codice-bg); padding:0.1rem 0.35rem; border-radius:4px; }
img { max-width:100% !important; height:auto; }
video { max-width:100%; height:auto; display:block; margin:1rem 0; }
.video-youtube { position:relative; width:100%; padding-bottom:56.25%; margin:1rem 0; height:0; overflow:hidden; }
.video-youtube iframe { position:absolute; top:0; left:0; width:100%; height:100%; border:0; }
/* Alignment generated by Quill (text and images). */
.ql-align-center { text-align:center; }
.ql-align-right { text-align:right; }
.ql-align-justify { text-align:justify; }
/* Fonts and sizes chosen in the editor (Quill uses these classes). */
.ql-font-serif { font-family:Georgia,"Times New Roman",serif; }
.ql-font-monospace { font-family:Menlo,Monaco,Consolas,monospace; }
.ql-size-small { font-size:0.75em; }
.ql-size-large { font-size:1.5em; }
.ql-size-huge { font-size:2.5em; }
/* A centred image is inline: display block is needed to really centre it. */
p.ql-align-center img, .ql-align-center img { display:inline-block; }
blockquote { border-left:3px solid var(--bordo); margin-left:0; padding-left:1.2rem; color:var(--secondario); font-style:italic; }
.commenti { margin-top:3rem; padding-top:2rem; border-top:1px solid var(--bordo); }
.commenti h2 { font-size:1.2rem; }
.search-box { margin-bottom:2rem; }
.search-box input { width:100%; padding:0.7rem 1rem; font-size:1rem; border:1px solid var(--bordo); border-radius:8px; font-family:inherit; }
.search-box input:focus { border-color:var(--link); }
#search-box-info { color:var(--secondario); font-size:0.85rem; margin:0.5rem 0 0; min-height:1em; }
/* The individual article pages stay narrow, for readability. */
article.post { max-width:var(--larghezza); margin:0 auto; padding:2.5rem 1.2rem 2rem; }
/* Lists in the articles: we restore the bullets and the numbers, which some
   CSS resets remove. Without these rules bulleted lists show with no bullet. */
article.post ul { list-style:disc; padding-left:1.6rem; margin:1rem 0; }
article.post ol { list-style:decimal; padding-left:1.6rem; margin:1rem 0; }
article.post li { margin:0.3rem 0; }
/* Lists with check boxes (checklists) generated by the editor. */
article.post ul[data-checked] { list-style:none; padding-left:0.3rem; }
article.post li[data-list="unchecked"]::before { content:"\2610"; margin-right:0.5rem; }
article.post li[data-list="checked"]::before { content:"\2611"; margin-right:0.5rem; }
/* Indentation produced by the editor: 5 levels. */
article.post .ql-indent-1 { padding-left:2.5rem; }
article.post .ql-indent-2 { padding-left:5rem; }
article.post .ql-indent-3 { padding-left:7.5rem; }
article.post .ql-indent-4 { padding-left:10rem; }
article.post .ql-indent-5 { padding-left:12.5rem; }
/* Superscript and subscript (for formulas, notes, units of measure). */
article.post sub { vertical-align:sub; font-size:0.75em; }
article.post sup { vertical-align:super; font-size:0.75em; }
/* Strikethrough text. */
article.post s, article.post del { text-decoration:line-through; }
.commenti { max-width:var(--larghezza); margin:2rem auto 0; padding:2rem 1.2rem 0; border-top:1px solid var(--bordo); }
footer.site { max-width:var(--larghezza-home); margin:4rem auto 0; padding:1.5rem 1.2rem; border-top:1px solid var(--bordo); color:var(--secondario); font-size:0.85rem; text-align:center; }
/* Top of the homepage (bio, images, introduction). */
/* Welcome section (hero): elegant but very light, CSS only.
   A gentle gradient and careful typography give emphasis without images. */
.home-intro {
  margin:0 0 2rem; padding:1.3rem 2rem; border-radius:16px;
  background:linear-gradient(135deg, var(--hero-1) 0%, var(--hero-2) 100%);
  border:1px solid var(--hero-bordo); text-align:center; position:relative; overflow:hidden;
}
.home-intro::before {
  content:""; position:absolute; top:-50%; right:-10%; width:260px; height:260px;
  background:radial-gradient(circle, rgba(0,102,204,0.08) 0%, transparent 70%);
  pointer-events:none;
}
.home-intro h1, .home-intro h2 {
  font-size:1.7rem; margin:0 0 0.3rem; line-height:1.2; letter-spacing:-0.02em;
  background:linear-gradient(120deg, #0066cc, #5b3df5); -webkit-background-clip:text;
  background-clip:text; -webkit-text-fill-color:transparent; font-weight:700;
}
.home-intro p { font-size:1rem; color:#475569; max-width:620px; margin:0.2rem auto; line-height:1.5; }
.home-intro p strong { color:#1a1a1a; }
/* We hide the empty paragraphs the editor leaves behind (both <p></p> and
   <p><br></p>), so as not to add useless vertical space in the hero. */
.home-intro p:empty { display:none; }
.home-intro p:last-child:has(br:only-child) { display:none; }
.home-intro br { display:none; }
.home-intro img { border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.08); max-height:160px; width:auto; }
/* Images side by side with the text: float left/right, text wrapping around. */
.home-intro .ql-align-left img { float:left; margin:0 1.5rem 1rem 0; max-width:45%; }
.home-intro .ql-align-right img { float:right; margin:0 0 1rem 1.5rem; max-width:45%; }
.home-intro::after { content:""; display:block; clear:both; }
/* Homepage cards: each one is a link to a dedicated page. */
.home-cards-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:1.2rem; margin:0 0 3rem; }
.cards-section { margin-top:3.5rem; }
.home-card { display:flex; flex-direction:column; text-decoration:none; color:var(--testo);
  background:var(--card-bg); border:1px solid var(--bordo); border-radius:12px; padding:1.4rem;
  transition:transform 0.15s, box-shadow 0.15s, background 0.15s; }
.home-card:hover { transform:translateY(-3px); box-shadow:0 8px 24px rgba(0,0,0,0.08); background:var(--card-hover); }
.home-card-title { font-size:1.15rem; margin:0 0 0.6rem; padding-bottom:0.5rem; border-bottom:2px solid var(--link); display:inline-block; }
.home-card-excerpt { font-size:0.92rem; color:var(--secondario); margin:0 0 1rem; flex-grow:1; }
.home-card-link { color:var(--link); font-size:0.88rem; font-weight:500; margin-top:auto; }
.articles-heading { font-size:1.6rem; margin:0 0 0.3rem; font-weight:700; letter-spacing:-0.01em; }
.articles-section { position:relative; }
.articles-section::before {
  content:""; display:block; width:48px; height:4px; border-radius:2px;
  background:linear-gradient(90deg, #0066cc, #5b3df5); margin-bottom:1.2rem;
}
/* Language switcher in the article pages. */
.language-switcher { display:flex; gap:0.5rem; margin-bottom:1rem; font-size:0.85rem; }
.language-switcher a, .language-switcher span { padding:0.2rem 0.7rem; border-radius:20px; text-decoration:none; }
.language-switcher a { color:var(--link); border:1px solid var(--bordo); }
.language-switcher .lingua-attiva { background:var(--link); color:#fff; }
/* --- Responsive / mobile friendly --- */
@media (max-width: 640px) {
  body { font-size:16px; }
  header.site { padding:1rem; flex-direction:column; align-items:flex-start; gap:0.6rem; }
  header.site .site-nav { gap:1.2rem; }
  .main-content { padding:1.5rem 1rem 3rem; }
  article.post { padding:1.5rem 1rem; }
  article.post h1 { font-size:1.6rem; }
  /* Side-by-side images become full width, stacked. */
  .home-intro .ql-align-left img,
  .home-intro .ql-align-right img { float:none; max-width:100%; margin:1rem 0; display:block; }
  /* The hero adapts: less padding and a smaller title on mobile. */
  .home-intro { padding:2rem 1.2rem; border-radius:16px; }
  .home-intro h1, .home-intro h2 { font-size:1.7rem; }
  .home-intro p { font-size:1rem; }
  pre { font-size:0.8rem; padding:0.8rem 1rem; }
}
"""


def _plain_text(html_content_value):
    """Strip the HTML tags to get plain text (for the index and llms.txt)."""
    text = re.sub(r"<[^>]+>", " ", html_content_value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_related_articles(article, all_articles, maximum=3):
    """
    Find the articles related to the given one, i.e. those sharing at least
    one tag. Return at most 'massimo' articles, sorted by the number of tags
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


def generate_related_block(article, all_articles, language="it"):
    """Generate the HTML of the 'Related articles' block to put at the bottom."""
    related = find_related_articles(article, all_articles)
    if len(related) == 0:
        return ""

    feed_items = []
    for art in related:
        feed_items.append(f"""    <a class="article-card" href="/posts/{art['slug']}.html">
      <div class="card-date">{_format_date(art['date'], language)}</div>
      <h3 class="card-title">{html.escape(art['title'])}</h3>
      <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
    </a>""")
    lista = "\n".join(feed_items)

    return f"""<section class="related-articles">
    <h2 class="articles-heading">{T('articoli_correlati', language)}</h2>
    <div class="articles-grid">
{lista}
    </div>
  </section>"""


def generate_table_of_contents(html_content_value, language="it"):
    """
    Generate the table of contents (TOC) of an article.
    It finds the h2 and h3 headings in the content, adds an id to each one
    for linking, and returns two things: the modified content (with the ids)
    and the HTML of the index. With fewer than 3 headings it generates no
    index (short articles do not need one).
    """
    # We find every h2 and h3 heading in the content.
    titoli = re.findall(r"<(h[23])>(.*?)</h[23]>", html_content_value, re.IGNORECASE | re.DOTALL)

    if len(titoli) < 3:
        # Few headings: no index, content unchanged.
        return html_content_value, ""

    modified_content = html_content_value
    toc_items = []
    counter = 0
    for level, heading_text in titoli:
        counter = counter + 1
        # We derive a readable id from the heading text.
        clean_text = _plain_text(heading_text)
        ancora = slugify(clean_text)
        if ancora == "":
            ancora = "section"
        ancora = ancora + "-" + str(counter)

        # We add the id to the heading in the content (first occurrence only).
        old_item = f"<{level}>{heading_text}</{level}>"
        new_item = f'<{level} id="{ancora}">{heading_text}</{level}>'
        modified_content = modified_content.replace(old_item, new_item, 1)

        # Indentation for sub-headings (h3) relative to headings (h2).
        item_class = "toc-h2"
        if level.lower() == "h3":
            item_class = "toc-h3"
        toc_items.append(
            f'<li class="{item_class}"><a href="#{ancora}">{html.escape(clean_text)}</a></li>')

    index_html = (
        '<nav class="table-of-contents"><p class="toc-title">' + T('indice', language) + '</p><ul>'
        + "\n".join(toc_items) + "</ul></nav>"
    )
    return modified_content, index_html


def compute_reading_time(html_content_value, language="it"):
    """
    Estimate the reading time of an article by counting the words.
    It assumes an average reading speed of 200 words per minute.
    Return a string ready to be shown (e.g. "3 min read").
    """
    text = _plain_text(html_content_value)
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
            "text": _plain_text(art.get("content", "")),
            "date_it": _format_date(art["date"], "it"),
            "date_en": _format_date(art["date"], "en"),
            # Tells whether a published English version exists.
            "has_en": False,
            "title_en": "",
            "text_en": "",
            "preview_en": art.get("preview_en", ""),
        }
        # We add the English data only if the translation is confirmed.
        translation_confirmed = art.get("translation_confirmed", False)
        content_en = art.get("content_en", "")
        if translation_confirmed and content_en.strip() != "":
            url_entry["has_en"] = True
            url_entry["title_en"] = art.get("title_en", "")
            url_entry["text_en"] = _plain_text(content_en)
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
        desc = art.get("description") or _plain_text(art.get("content", ""))[:120]
        lines.append(f"- [{art['title']}]({url}): {desc}")
    lines.append("")

    # Training & licensing: makes the policy visible to any LLM/AI operator
    # reading this file, in the file's own plain-language format.
    lines.append("## Training & Licensing")
    lines.append("")
    lines.append(_ai_training_statement("en"))
    training = _ai_training_config()
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
    It includes the homepage, the articles (IT and EN) and the card pages.
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

    # Pages of the active cards (both languages: build() always generates them).
    card_lista = CONFIG.get("home_cards", [])
    for card in card_lista:
        active = card.get("active", False)
        if not active:
            continue
        content = card.get("content", "")
        if html_content_is_empty(content):
            continue
        slug = _card_slug(card.get("title", ""))
        lines.append(url_entry(main_prefix + "/pagine/" + slug + ".html"))
        lines.append(url_entry(sec_prefix + "/pagine/" + slug + ".html"))

    lines.append("</urlset>")
    return "\n".join(lines)


def generate_404_page():
    """Generate a custom 404 page, consistent with the site design."""
    # The texts follow the site's main language.
    if main_language() == "en":
        text_404 = "The page you are looking for does not exist or has been moved."
        back_text = "Back to homepage"
    else:
        text_404 = "La pagina che cerchi non esiste o e' stata spostata."
        back_text = "Torna alla homepage"
    return f"""<!DOCTYPE html>
<html lang="{CONFIG['language']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>Pagina non trovata &middot; {html.escape(CONFIG['site_title'])}</title>
  <link rel="stylesheet" href="/style.css">
  {_theme_script()}
</head>
<body>
  {_site_header(main_language())}
  <main id="content" class="main-content">
    <div style="text-align:center; padding:4rem 1rem;">
      <h1 style="font-size:3rem; margin:0;">404</h1>
      <p style="font-size:1.2rem; color:var(--secondario);">{text_404}</p>
      <p style="margin-top:2rem;"><a href="/">&larr; {back_text}</a></p>
    </div>
  </main>
  {_site_footer(main_language())}
</body>
</html>"""


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


def generate_tag_page(tag_name, tag_articles, language="it"):
    """
    Generate the index page of a tag: it lists every article using it, as
    clickable cards, with the same design as the homepage.
    With lingua="en" it generates the English version (translated articles only).
    """
    language_prefix = language_url_prefix(language)
    post_prefix = language_prefix + "/posts/"
    url_home = language_prefix + "/"

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
            excerpt = f'<p class="card-excerpt">{html.escape(card_description)}</p>'
        feed_items.append(f"""    <a class="article-card" href="{post_prefix}{art['slug']}.html">
      <div class="card-date">{_format_date(art['date'], language)}</div>
      <h3 class="card-title">{html.escape(card_title)}</h3>
      {excerpt}
      <span class="card-read-more">{T('leggi_articolo', language)} &rarr;</span>
    </a>""")
    lista = "\n".join(feed_items)

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {_favicon_link()}
  {_analytics_snippet()}
  <title>{T('articoli_con_tag', language)} {html.escape(tag_name)} &middot; {html.escape(CONFIG['site_title'])}</title>
  <meta name="description" content="{T('articoli_con_tag', language)} {html.escape(tag_name)}.">
  <link rel="stylesheet" href="/style.css">
  {_theme_script()}
</head>
<body>
  {_site_header(language)}
  <main id="content" class="main-content">
    <section class="articles-section">
      <p class="breadcrumbs"><a href="{url_home}">{T('home', language)}</a> &rsaquo; {T('tag', language)}</p>
      <h2 class="articles-heading">#{html.escape(tag_name)}</h2>
      <p class="text-tag-conteggio">{count} {T('tag_conteggio', language)}</p>
      <div class="articles-grid">
{lista}
      </div>
    </section>
  </main>
  {_site_footer(language)}
</body>
</html>"""


def build():
    """Rebuild the whole static site into the output/ folder."""
    # We reload the configuration from the file, so that changes saved
    # from the Settings page take effect immediately.
    global CONFIG
    CONFIG = load_config()

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

    # Pages of the individual articles in the main language (at the root).
    for art in published_articles:
        html_art = generate_article_page(art, lp, published_articles)
        (OUTPUT_DIR / "posts" / f"{art['slug']}.html").write_text(
            html_art, encoding="utf-8")

        # Version in the secondary language: we generate it only if the translation
        # is confirmed and the translated content is not empty.
        # The translation only exists between Italian and English (_en fields).
        translation_confirmed = art.get("translation_confirmed", False)
        content_en = art.get("content_en", "")
        if translation_confirmed and not html_content_is_empty(content_en):
            html_sec = generate_article_page(art, ls, published_articles)
            (OUTPUT_DIR / sec_folder / "posts" / f"{art['slug']}.html").write_text(
                html_sec, encoding="utf-8")

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
        (OUTPUT_DIR / "tag" / f"{tag_slug}.html").write_text(
            html_tag, encoding="utf-8")
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
            (OUTPUT_DIR / sec_folder / "tag" / f"{tag_slug}.html").write_text(
                html_tag_sec, encoding="utf-8")

    # Pages of the active cards (Biography, Projects, About...).
    card_lista = CONFIG.get("home_cards", [])
    for card in card_lista:
        active = card.get("active", False)
        if not active:
            continue
        content = card.get("content", "")
        if html_content_is_empty(content):
            continue
        slug = _card_slug(card.get("title", ""))
        # Cards in the main language (at the root).
        html_card = generate_card_page(card, lp)
        (OUTPUT_DIR / "pagine" / f"{slug}.html").write_text(
            html_card, encoding="utf-8")
        # Cards in the secondary language.
        (OUTPUT_DIR / sec_folder / "pagine").mkdir(parents=True, exist_ok=True)
        html_card_sec = generate_card_page(card, ls)
        (OUTPUT_DIR / sec_folder / "pagine" / f"{slug}.html").write_text(
            html_card_sec, encoding="utf-8")

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
                (page_folder / f"{number}.html").write_text(
                    generate_homepage(published_articles, home_language, number, totale_pagine),
                    encoding="utf-8")

    # Archive page (compact list by year) in both languages.
    (OUTPUT_DIR / archive_file_name(lp)).write_text(
        generate_archive_page(published_articles, lp), encoding="utf-8")
    (OUTPUT_DIR / sec_folder / archive_file_name(ls)).write_text(
        generate_archive_page(published_articles, ls), encoding="utf-8")

    # RSS feed.
    (OUTPUT_DIR / "rss.xml").write_text(
        generate_rss(published_articles), encoding="utf-8")

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
        generate_training_rights_page(main_language()), encoding="utf-8")
    (OUTPUT_DIR / sec_folder / "training-rights.html").write_text(
        generate_training_rights_page(secondary_language()), encoding="utf-8")

    # Custom 404 page.
    (OUTPUT_DIR / "404.html").write_text(
        generate_404_page(), encoding="utf-8")

    # Automatically generated favicon (title initial on a gradient).
    # If the author has configured a custom favicon, it is not needed.
    if _seo_data().get("favicon", "") == "":
        (OUTPUT_DIR / "favicon.svg").write_text(
            generate_favicon_svg(), encoding="utf-8")

    # CSS.
    (OUTPUT_DIR / "style.css").write_text(CSS, encoding="utf-8")

    return len(published_articles)


# ---------------------------------------------------------------------------
# THE SERVER WITH THE WYSIWYG EDITOR
# ---------------------------------------------------------------------------

# Bootstrap version loaded from a CDN for all the administration pages.
BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"

# Custom CSS shared by all the admin pages.
# Centralised here to avoid duplicating it in every page: a single place
# to change. It sits alongside Bootstrap, tweaking only a few details.
CSS_ADMIN = """
:root { --pb-blu:#0066cc; }
/* Explanatory bubble on the toolbar buttons (and any element carrying a
   data-tooltip attribute). Pure CSS: it appears instantly on hover, unlike
   the browser's native title, which waits about a second. */
[data-tooltip] { position:relative; }
[data-tooltip]::after {
  content: attr(data-tooltip);
  position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%);
  background:#1f2937; color:#fff; font-size:0.78rem; line-height:1.3;
  font-weight:400; white-space:nowrap; padding:0.35rem 0.6rem; border-radius:6px;
  box-shadow:0 2px 8px rgba(0,0,0,0.25);
  opacity:0; visibility:hidden; transition:opacity 0.12s ease 0.25s, visibility 0s linear 0.37s;
  pointer-events:none; z-index:2000;
}
/* The little arrow of the bubble, pointing at the button. */
[data-tooltip]::before {
  content:""; position:absolute; bottom:calc(100% + 3px); left:50%;
  transform:translateX(-50%); border:5px solid transparent; border-top-color:#1f2937;
  opacity:0; visibility:hidden; transition:opacity 0.12s ease 0.25s, visibility 0s linear 0.37s;
  pointer-events:none; z-index:2000;
}
[data-tooltip]:hover::after, [data-tooltip]:hover::before,
[data-tooltip]:focus-visible::after, [data-tooltip]:focus-visible::before {
  opacity:1; visibility:visible; transition-delay:0.25s, 0.25s;
}
/* Near the left edge the bubble would be cut off: we anchor it to the left. */
.ql-toolbar > span:first-child [data-tooltip]::after,
.ql-toolbar span.ql-formats:first-child > [data-tooltip]::after {
  left:0; transform:none;
}
.ql-toolbar span.ql-formats:first-child > [data-tooltip]::before { left:14px; }
body { background:#f5f6f8; }
.pb-navbar { background:#fff; border-bottom:1px solid #e4e4e7; }
.pb-navbar .navbar-brand { font-weight:600; }
.pb-content { max-width:960px; margin:0 auto; padding:1.5rem 1rem 4rem; }
.pb-card { background:#fff; border:1px solid #e4e4e7; border-radius:12px; }
.pb-editor-quill { height:380px; background:#fff; }
.pb-editor-quill-piccolo { height:300px; background:#fff; }
.pb-badge-pubblicato { background:#d4f4dd; color:#0a6b2e; }
.pb-badge-bozza { background:#fff0d4; color:#8a5a00; }
/* Centred box for login and password setup. */
.pb-box-centrato { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:1rem; }
.pb-box { max-width:380px; width:100%; }
"""


def _admin_head(title_value):
    """
    Return the <head> block shared by the administration pages:
    Bootstrap from a CDN plus the centralised admin CSS.
    """
    return f"""<!DOCTYPE html>
<html lang="it"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title_value)}</title>
<link href="{BOOTSTRAP_CSS}" rel="stylesheet">
<style>{CSS_ADMIN}</style>
</head><body>"""


def admin_language():
    """Return the current language of the admin interface (it or en)."""
    language = CONFIG.get("admin_language", "it")
    if language not in ("it", "en"):
        return "it"
    return language


def _admin_navbar(active_page=""):
    """
    Shared navigation bar of the admin area.
    pagina_attiva highlights the current item (e.g. "articoli", "config").
    The labels follow the language chosen for the administration.
    """
    la = admin_language()
    feed_items = [
        ("articles", "/admin", T("admin_articoli", la)),
        ("config", "/config", T("admin_impostazioni", la)),
    ]
    link_html = []
    for key, url, label in feed_items:
        classe = "nav-link"
        if key == active_page:
            classe = "nav-link active"
        link_html.append(
            f'<li class="nav-item"><a class="{classe}" href="{url}">{label}</a></li>')
    items_html = "\n".join(link_html)

    # The language switch shows the language you are switching to.
    if la == "it":
        next_language = "en"
        language_label = "EN"
    else:
        next_language = "it"
        language_label = "IT"

    return f"""<nav class="navbar navbar-expand-lg pb-navbar">
  <div class="container-fluid pb-content" style="padding-top:0.5rem;padding-bottom:0.5rem;">
    <a class="navbar-brand" href="/admin">PyBlog</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse"
            data-bs-target="#navAdmin" aria-controls="navAdmin"
            aria-expanded="false" aria-label="Menu">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navAdmin">
      <ul class="navbar-nav me-auto">
{items_html}
      </ul>
      <ul class="navbar-nav align-items-lg-center">
        <li class="nav-item"><a class="nav-link" href="/" target="_blank">{T("admin_vedi_blog", la)}</a></li>
        <li class="nav-item"><a class="nav-link" href="/change-password">{T("admin_password", la)}</a></li>
        <li class="nav-item"><a class="nav-link text-danger" href="/logout">{T("admin_esci", la)}</a></li>
        <li class="nav-item"><button class="btn btn-sm btn-outline-secondary ms-lg-2" onclick="changeAdminLanguage('{next_language}')" title="Lingua interfaccia">{language_label}</button></li>
      </ul>
    </div>
  </div>
  <script>
  // Changes the language of the administration interface.
  function changeAdminLanguage(lingua) {{
    fetch('/admin-language', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ language: lingua }})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(res) {{ window.location.reload(); }});
  }}
  </script>
</nav>"""


def login_page(error_message=""):
    """Login page to access the administration area."""
    la = admin_language()
    error_block = ""
    if error_message != "":
        error_block = f'<div class="alert alert-danger py-2">{html.escape(error_message)}</div>'

    return f"""{_admin_head(T("admin_area_riservata", la))}
<div class="pb-box-centrato">
  <div class="pb-box">
    <div class="card pb-card shadow-sm">
      <div class="card-body p-4">
        <h1 class="h4 mb-1">{T("admin_area_riservata", la)}</h1>
        <p class="text-secondary small mb-4">{T("admin_login_invito", la)}</p>
        {error_block}
        <form method="POST" action="/login">
          <div class="mb-3">
            <label for="password" class="form-label fw-semibold">{T("admin_password", la)}</label>
            <input type="password" class="form-control" id="password" name="password" autofocus>
          </div>
          <button type="submit" class="btn btn-primary w-100">{T("admin_accedi", la)}</button>
        </form>
      </div>
    </div>
  </div>
</div>
<script src="{BOOTSTRAP_JS}"></script>
</body></html>"""


def set_password_page(error_message=""):
    """Page shown on first run to create the administration password."""
    la = admin_language()
    error_block = ""
    if error_message != "":
        error_block = f'<div class="alert alert-danger py-2">{html.escape(error_message)}</div>'

    return f"""{_admin_head(T("admin_crea_password_titolo", la))}
<div class="pb-box-centrato">
  <div class="pb-box">
    <div class="card pb-card shadow-sm">
      <div class="card-body p-4">
        <h1 class="h4 mb-1">{T("admin_crea_password_titolo", la)}</h1>
        <p class="text-secondary small mb-4">{T("admin_crea_password_invito", la)}</p>
        {error_block}
        <form method="POST" action="/set-password">
          <div class="mb-3">
            <label for="password" class="form-label fw-semibold">{T("admin_nuova_password", la)}</label>
            <input type="password" class="form-control" id="password" name="password" autofocus>
          </div>
          <div class="mb-3">
            <label for="conferma" class="form-label fw-semibold">{T("admin_conferma_password", la)}</label>
            <input type="password" class="form-control" id="conferma" name="conferma">
          </div>
          <button type="submit" class="btn btn-primary w-100">{T("admin_crea_accedi", la)}</button>
        </form>
      </div>
    </div>
  </div>
</div>
<script src="{BOOTSTRAP_JS}"></script>
</body></html>"""


def change_password_page(error_message="", messaggio_successo=""):
    """Page to change the password while logged in."""
    la = admin_language()
    error_block = ""
    if error_message != "":
        error_block = f'<div class="alert alert-danger py-2">{html.escape(error_message)}</div>'
    success_block = ""
    if messaggio_successo != "":
        success_block = f'<div class="alert alert-success py-2">{html.escape(messaggio_successo)}</div>'

    return f"""{_admin_head(T("admin_cambia_password", la))}
{_admin_navbar("")}
<div class="pb-content" style="max-width:480px;">
  <div class="card pb-card shadow-sm">
    <div class="card-body p-4">
      <h1 class="h4 mb-3">{T("admin_cambia_password", la)}</h1>
      {error_block}
      {success_block}
      <form method="POST" action="/change-password">
        <div class="mb-3">
          <label for="attuale" class="form-label fw-semibold">{T("admin_password_attuale", la)}</label>
          <input type="password" class="form-control" id="attuale" name="attuale">
        </div>
        <div class="mb-3">
          <label for="nuova" class="form-label fw-semibold">{T("admin_nuova_password", la)}</label>
          <input type="password" class="form-control" id="nuova" name="nuova">
        </div>
        <div class="mb-3">
          <label for="conferma" class="form-label fw-semibold">{T("admin_conferma_nuova", la)}</label>
          <input type="password" class="form-control" id="conferma" name="conferma">
        </div>
        <button type="submit" class="btn btn-primary">{T("admin_cambia_password", la)}</button>
      </form>
    </div>
  </div>
</div>
<script src="{BOOTSTRAP_JS}"></script>
</body></html>"""


def admin_page(articles):
    """
    Administration dashboard: the list of every article with its status,
    a search box, and quick actions (edit, preview, delete).
    """
    la = admin_language()
    # We count published and drafts to show some statistics at the top.
    total_count = len(articles)
    published_count = 0
    draft_count = 0
    for art in articles:
        if art.get("status") == "published":
            published_count = published_count + 1
        else:
            draft_count = draft_count + 1

    # We build one row for each article.
    lines = []
    for art in articles:
        if art.get("status") == "published":
            classe_badge = "pb-badge-pubblicato"
            badge_label = T("admin_pubblicato", la)
            # If it is published, the button puts it back to draft.
            status_action = "draft"
            status_label = T("admin_metti_bozza", la)
            status_class = "btn-outline-warning"
        else:
            classe_badge = "pb-badge-bozza"
            badge_label = T("admin_bozza", la)
            # If it is a draft, the button publishes it.
            status_action = "published"
            status_label = T("admin_pubblica", la)
            status_class = "btn-outline-success"

        description = ""
        if art.get("description"):
            description = html.escape(art["description"])

        safe_title = html.escape(art["title"])
        safe_slug = html.escape(art["slug"])

        # We show a badge if the article has an English version.
        badge_en = ""
        if art.get("translation_confirmed", False):
            badge_en = '<span class="badge bg-info-subtle text-info-emphasis ms-1">EN</span>'

        # Preview of the English page: the link appears as soon as some
        # English content exists (even if not confirmed yet), so that you
        # can check the translation BEFORE confirming it.
        preview_en_link = ""
        if not html_content_is_empty(art.get("content_en", "")):
            preview_en_link = (
                f'<a class="btn btn-sm btn-outline-secondary" '
                f'href="/preview?slug={safe_slug}&amp;language=en" target="_blank">'
                f'{T("admin_anteprima", la)} EN</a>')

        lines.append(f"""    <div class="card pb-card mb-2 articolo-card" data-titolo="{safe_title.lower()}">
      <div class="card-body d-flex justify-content-between align-items-center flex-wrap gap-3">
        <div>
          <div class="d-flex align-items-center gap-2 flex-wrap">
            <span class="badge {classe_badge}">{badge_label}</span>{badge_en}
            <a class="fw-semibold text-decoration-none text-dark fs-6" href="/edit?slug={safe_slug}">{safe_title}</a>
          </div>
          <div class="text-secondary small mt-1">{_format_date(art['date'])}</div>
          <div class="text-secondary small">{description}</div>
        </div>
        <div class="d-flex gap-2 flex-shrink-0 flex-wrap">
          <button class="btn btn-sm {status_class}" onclick="changeStatus('{safe_slug}', '{status_action}')">{status_label}</button>
          <a class="btn btn-sm btn-primary" href="/edit?slug={safe_slug}">{T("admin_modifica", la)}</a>
          <a class="btn btn-sm btn-outline-secondary" href="/preview?slug={safe_slug}" target="_blank">{T("admin_anteprima", la)}</a>
          {preview_en_link}
          <button class="btn btn-sm btn-outline-danger" onclick="deleteArticle('{safe_slug}', '{safe_title}')">{T("admin_elimina", la)}</button>
        </div>
      </div>
    </div>""")

    if len(lines) > 0:
        listing = "\n".join(lines)
    else:
        listing = f'<div class="text-center text-secondary p-5 border border-dashed rounded bg-white">{T("admin_nessun_articolo", la)}</div>'

    return f"""{_admin_head(T("admin_titolo_pagina", la) + " - " + CONFIG['site_title'])}
{_admin_navbar("articles")}
<div class="pb-content">

  <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-4">
    <div>
      <h1 class="h3 mb-0">{T("admin_articoli", la)}</h1>
      <p class="text-secondary small mb-0">{html.escape(CONFIG['site_title'])}</p>
    </div>
    <a class="btn btn-primary" href="/edit">{T("admin_nuovo_articolo", la)}</a>
  </div>

  <div class="row g-3 mb-4">
    <div class="col">
      <div class="card pb-card text-center"><div class="card-body py-3">
        <div class="fs-3 fw-semibold">{total_count}</div>
        <div class="text-secondary small">{T("admin_totali", la)}</div>
      </div></div>
    </div>
    <div class="col">
      <div class="card pb-card text-center"><div class="card-body py-3">
        <div class="fs-3 fw-semibold">{published_count}</div>
        <div class="text-secondary small">{T("admin_pubblicati", la)}</div>
      </div></div>
    </div>
    <div class="col">
      <div class="card pb-card text-center"><div class="card-body py-3">
        <div class="fs-3 fw-semibold">{draft_count}</div>
        <div class="text-secondary small">{T("admin_bozze", la)}</div>
      </div></div>
    </div>
  </div>

  <div class="d-flex gap-2 flex-wrap mb-3">
    <a class="btn btn-outline-secondary btn-sm" href="/config">{T("admin_impostazioni_home", la)}</a>
    <button class="btn btn-outline-secondary btn-sm" onclick="rebuildSite()">{T("admin_rigenera", la)}</button>
    <a class="btn btn-outline-secondary btn-sm" href="/export">{T("admin_scarica_backup", la)}</a>
  </div>

  <input type="search" class="form-control mb-3" id="search-box-admin"
         placeholder="{T("admin_filtra", la)}" oninput="filterArticles()">

  <div id="elenco-articoli">
{listing}
  </div>
  <div class="text-center text-secondary p-4" id="nessun-risultato" style="display:none">
    {T("admin_nessun_corrisponde", la)}
  </div>
</div>

<script src="{BOOTSTRAP_JS}"></script>
<script>
// Filters the article cards based on the typed text.
function filterArticles() {{
  var termine = document.getElementById("search-box-admin").value.toLowerCase().trim();
  var carte = document.querySelectorAll(".articolo-card");
  var visibili = 0;
  for (var i = 0; i < carte.length; i++) {{
    var titolo = carte[i].getAttribute("data-titolo");
    if (titolo.indexOf(termine) !== -1) {{
      carte[i].style.display = "block";
      visibili = visibili + 1;
    }} else {{
      carte[i].style.display = "none";
    }}
  }}
  var avviso = document.getElementById("nessun-risultato");
  if (visibili === 0) {{
    avviso.style.display = "block";
  }} else {{
    avviso.style.display = "none";
  }}
}}

// Rebuilds the static site.
function rebuildSite() {{
  fetch("/rebuild", {{ method: "POST" }})
    .then(function(r) {{ return r.json(); }})
    .then(function(res) {{ alert("Sito rigenerato: " + res.articoli + " articoli."); }});
}}

// Changes an article's status (published/draft) and reloads the page.
function changeStatus(slug, nuovoStato) {{
  fetch("/toggle-status", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ slug: slug, status: nuovoStato }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      window.location.reload();
    }} else {{
      alert("Errore nel cambio di stato.");
    }}
  }});
}}

// Deletes an article after confirmation, then reloads the page.
function deleteArticle(slug, titolo) {{
  var conferma = confirm('{T("js_delete_named", la)} "' + titolo + '"?');
  if (conferma === false) {{
    return;
  }}
  fetch("/delete", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ slug: slug }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      window.location.reload();
    }} else {{
      alert("Errore durante l'eliminazione.");
    }}
  }});
}}
</script>
</body></html>"""


def config_page():
    """
    Site configuration page:
    - WYSIWYG editor for the top of the homepage (bio, images...)
    - general settings (title, subtitle, author, domain)
    - comment configuration (Giscus or Disqus)
    It also shows a live preview of the home content.
    """
    config = load_config()
    la = admin_language()

    # We prepare the values, escaping them to put them into the inputs.
    site_title_value = html.escape(config.get("site_title", ""))
    subtitle = html.escape(config.get("subtitle", ""))
    author = html.escape(config.get("author", ""))
    base_url = html.escape(config.get("base_url", ""))
    analytics_id = html.escape(config.get("analytics_id", ""))
    umami_url = html.escape(config.get("umami_url", ""))
    umami_website_id = html.escape(config.get("umami_website_id", ""))
    language = html.escape(config.get("language", "it"))

    # --- Values of the SEO and author data section ---
    seo = config.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}
    seo_author_url = html.escape(seo.get("author_url", ""))
    seo_author_image = html.escape(seo.get("author_image", ""))
    seo_author_role = html.escape(seo.get("author_role", ""))
    seo_author_bio = html.escape(seo.get("author_bio", ""))
    seo_logo = html.escape(seo.get("logo", ""))
    seo_twitter = html.escape(seo.get("twitter_site", ""))
    seo_favicon = html.escape(seo.get("favicon", ""))

    # --- Values of the AI training rights section ---
    ai_training = config.get("ai_training", {})
    if not isinstance(ai_training, dict):
        ai_training = {}
    ai_policy = ai_training.get("policy", "open")
    sel_ai_open = ""
    sel_ai_licensed = ""
    sel_ai_disallow = ""
    if ai_policy == "open":
        sel_ai_open = "selected"
    if ai_policy == "licensed":
        sel_ai_licensed = "selected"
    if ai_policy == "disallow":
        sel_ai_disallow = "selected"
    ai_contact_email = html.escape(ai_training.get("contact_email", ""))
    ai_license_url = html.escape(ai_training.get("license_url", ""))
    ai_statement = html.escape(ai_training.get("statement", ""))
    profiles = seo.get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    seo_profiles = html.escape("\n".join(profiles))

    # --- Values of the homepage structure ---
    order = config.get("home_order", ["intro", "cards", "articles"])
    if not isinstance(order, list) or len(order) != 3:
        order = ["intro", "cards", "articles"]
    # Three dropdowns: for each one we prepare the right "selected".
    opzioni_sezioni = ("intro", "cards", "articles")
    order_selects = []
    for posizione in range(3):
        choices = []
        for section_name in opzioni_sezioni:
            if order[posizione] == section_name:
                selected = " selected"
            else:
                selected = ""
            label = T("admin_section_" + section_name, la)
            choices.append(f'<option value="{section_name}"{selected}>{label}</option>')
        order_selects.append(
            f'<select class="ordine-home" id="ordine_home_{posizione}">'
            + "".join(choices) + "</select>")
    articles_per_page = config.get("articles_per_page", 10)
    home_content_js = json.dumps(config.get("home_content", ""))
    home_content_en_js = json.dumps(config.get("home_content_en", ""))
    # Formatted JSON text of the current config, for the advanced editor.
    config_raw_text = json.dumps(config, ensure_ascii=False, indent=2)
    config_raw_js = json.dumps(config_raw_text)

    # We prepare the fields for the editorial cards of the homepage.
    # Each card has a WYSIWYG editor (Quill) with its own unique id.
    card_lista = config.get("home_cards", [])
    card_html_parti = []
    # We collect the initial contents to pass to the JavaScript (for Quill).
    initial_contents = []
    index_value = 0
    for card in card_lista:
        card_title = html.escape(card.get("title", ""))
        card_content = card.get("content", "")
        initial_contents.append(card_content)
        active = card.get("active", False)
        if active:
            checked = "checked"
        else:
            checked = ""
        card_html_parti.append(f"""  <div class="card-config" data-indice="{index_value}">
    <label><input type="checkbox" class="card-attiva" {checked}> {T("admin_mostra_card", la)}</label>
    <label>{T("admin_titolo_card", la)}</label>
    <input type="text" class="card-title" value="{card_title}">
    <label>{T("admin_contenuto", la)}</label>
    <div class="card-editor" id="card-editor-{index_value}"></div>
  </div>""")
        index_value = index_value + 1
    card_html = "\n".join(card_html_parti)
    # The initial contents of the cards, as a JavaScript array.
    card_contents_js = json.dumps(initial_contents)

    commenti = config.get("comments", "none")
    giscus = config.get("giscus", {})
    disqus = config.get("disqus", {})

    # We work out which comment option is selected (explicit, no ternaries).
    none_selected = ""
    sel_giscus = ""
    sel_disqus = ""
    if commenti == "none":
        none_selected = "selected"
    if commenti == "giscus":
        sel_giscus = "selected"
    if commenti == "disqus":
        sel_disqus = "selected"

    giscus_repo = html.escape(giscus.get("repo", ""))
    giscus_repo_id = html.escape(giscus.get("repo_id", ""))
    giscus_category = html.escape(giscus.get("category", ""))
    giscus_category_id = html.escape(giscus.get("category_id", ""))
    giscus_theme = html.escape(giscus.get("theme", "light"))
    disqus_shortname = html.escape(disqus.get("shortname", ""))

    # We prepare the values of the translation section.
    translation = config.get("translation", {})
    translation_service = translation.get("service", "deepl")
    sel_deepl = ""
    sel_google = ""
    sel_llm = ""
    sel_openai = ""
    sel_deepseek = ""
    if translation_service == "deepl":
        sel_deepl = "selected"
    if translation_service == "google":
        sel_google = "selected"
    if translation_service == "llm":
        sel_llm = "selected"
    if translation_service == "openai":
        sel_openai = "selected"
    if translation_service == "deepseek":
        sel_deepseek = "selected"
    deepl_api_key = html.escape(translation.get("deepl_api_key", ""))
    google_api_key = html.escape(translation.get("google_api_key", ""))
    llm_api_key = html.escape(translation.get("llm_api_key", ""))
    llm_endpoint = html.escape(translation.get("llm_endpoint", ""))
    llm_modello = html.escape(translation.get("llm_model", ""))
    openai_api_key = html.escape(translation.get("openai_api_key", ""))
    openai_modello = html.escape(translation.get("openai_model", "gpt-4o-mini"))
    deepseek_api_key = html.escape(translation.get("deepseek_api_key", ""))
    deepseek_modello = html.escape(translation.get("deepseek_model", "deepseek-chat"))

    # --- Example/guide text (placeholder attributes) for empty fields ---
    # These NEVER get saved on their own: a placeholder only shows ghost
    # text while the field is empty, and disappears the moment someone
    # types. They exist purely to show what a well-filled, SEO-useful
    # profile looks like, in the site's own language.
    if language == "en":
        ph = {
            "site_title": "Inside the Machine",
            "subtitle": "Notes on Python, distributed systems and AI",
            "author": "Jane Doe",
            "base_url": "https://www.yourdomain.com",
            "seo_author_url": "https://www.yourdomain.com/about",
            "seo_author_image": "https://www.yourdomain.com/img/author.jpg",
            "seo_author_role": "CTO at Acme Labs \u00b7 Computer Science lecturer",
            "seo_author_bio": ("I'm Jane, a software engineer with 15 years in distributed "
                "systems. I write about Python, system architecture and applied AI, "
                "aimed at developers who want to build reliable products."),
            "seo_logo": "https://www.yourdomain.com/img/logo.png",
            "seo_twitter": "@yourname",
            "analytics_id": "G-XXXXXXXXXX",
            "umami_url": "https://stats.ciunix.com",
            "umami_website_id": "3e9b1c2a-1234-4f0a-9c1d-abcdef012345",
        }
    else:
        ph = {
            "site_title": "Dentro la Macchina",
            "subtitle": "Note su Python, sistemi distribuiti e intelligenza artificiale",
            "author": "Maria Rossi",
            "base_url": "https://www.tuodominio.it",
            "seo_author_url": "https://www.tuodominio.it/chi-sono",
            "seo_author_image": "https://www.tuodominio.it/img/autore.jpg",
            "seo_author_role": "CTO presso Acme Labs \u00b7 Docente di Informatica",
            "seo_author_bio": ("Sono Maria, ingegnera del software con 15 anni di esperienza "
                "in sistemi distribuiti. Scrivo di Python, architetture software e AI "
                "applicata, per chi vuole costruire prodotti affidabili."),
            "seo_logo": "https://www.tuodominio.it/img/logo.png",
            "seo_twitter": "@tuonome",
            "analytics_id": "G-XXXXXXXXXX",
            "umami_url": "https://stats.ciunix.com",
            "umami_website_id": "3e9b1c2a-1234-4f0a-9c1d-abcdef012345",
        }
    # html.escape on the placeholders too: they end up in an HTML attribute.
    ph = {k: html.escape(v) for k, v in ph.items()}

    # Placeholder (ghost text) for the two Quill editors of the homepage
    # introduction. json.dumps makes them safe for use as a JavaScript
    # string: it avoids handling quotes by hand, which is the most common
    # cause of syntax errors when writing JS strings inside an f-string.
    home_intro_ph_it_js = json.dumps(
        "Scrivi qui una breve presentazione: chi sei, di cosa ti occupi e "
        "perche' un lettore dovrebbe seguirti. Esempio: \u00abSono Maria, "
        "ingegnera del software. Scrivo di Python e architetture distribuite "
        "per chi vuole costruire sistemi affidabili.\u00bb")
    home_intro_ph_en_js = json.dumps(
        "Write a short introduction here: who you are, what you work on, "
        "and why a reader should follow you. Example: \u00abI'm Jane, a "
        "software engineer. I write about Python and distributed systems "
        "for people who want to build reliable systems.\u00bb")

    return f"""<!DOCTYPE html>
<html lang="it"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Impostazioni e homepage</title>
<link href="{BOOTSTRAP_CSS}" rel="stylesheet">
<link href="https://cdn.quilljs.com/1.3.7/quill.snow.css" rel="stylesheet">
<style>{CSS_ADMIN}
.config-wrap {{ max-width:1400px; margin:0 auto; padding:1.5rem 1rem 6rem; }}
/* Two-column layout: on the left the editorial content (introduction,
   cards) which needs room for the editors; on the right the compact
   technical settings (general, comments, translation). */
.config-layout {{ display:grid; grid-template-columns:1.4fr 1fr; gap:2rem; align-items:start; }}
.config-col-destra {{ position:sticky; top:1rem; }}
/* Save bar fixed at the bottom, always within reach. */
.config-save-bar {{ position:sticky; bottom:0; background:#fff; border-top:1px solid #e4e4e7; padding:1rem 0; margin-top:1.5rem; display:flex; gap:0.8rem; align-items:center; z-index:10; }}
@media (max-width: 1000px) {{
  .config-layout {{ grid-template-columns:1fr; gap:1rem; }}
  .config-col-destra {{ position:static; }}
}}
/* Advanced section to edit config.json by hand. */
.config-avanzata {{ margin-top:2rem; border:1px solid #e4e4e7; border-radius:8px; background:#fafafa; }}
.config-avanzata summary {{ cursor:pointer; padding:1rem; font-weight:600; user-select:none; }}
.config-avanzata-corpo {{ padding:0 1rem 1rem; }}
.config-avanzata textarea {{ width:100%; font-family:"SF Mono",Menlo,Monaco,Consolas,monospace; font-size:0.85rem; line-height:1.5; background:#fff; border:1px solid #ccc; border-radius:6px; padding:0.8rem; resize:vertical; }}
.btn-secondario {{ background:#eee; color:#333; padding:0.7rem 1.4rem; border:none; border-radius:6px; font-size:1rem; cursor:pointer; }}
h1 {{ font-size:1.5rem; }}
h2 {{ font-size:1.15rem; margin-top:2.5rem; border-top:1px solid #eee; padding-top:1.5rem; }}
label {{ display:block; font-weight:600; margin:1rem 0 0.3rem; font-size:0.9rem; }}
input,select,textarea {{ width:100%; padding:0.6rem; border:1px solid #ccc; border-radius:6px; font-size:1rem; font-family:inherit; }}
input:focus,select:focus,textarea:focus {{ outline:none; border-color:var(--pb-blu); box-shadow:0 0 0 3px rgba(0,102,204,0.12); }}
textarea {{ resize:vertical; line-height:1.55; }}
/* Bio dell'autore: spazio comodo per 2-4 frasi, coerente con lo stile del site. */
#seo_author_bio {{ min-height:5.5rem; }}
/* Profili social: un URL per riga, font leggermente monospaziato per
   leggerli piu' facilmente, altezza comoda per 4-5 profili senza scroll. */
#seo_profili {{ min-height:7rem; font-family:"SF Mono",Menlo,Monaco,Consolas,monospace; font-size:0.88rem; line-height:1.7; }}
.hint {{ color:#888; font-size:0.8rem; font-weight:400; }}
#editor-home {{ height:320px; background:#fff; margin-top:0.3rem; }}
.video-bar {{ margin-top:0.6rem; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; }}
.video-bar button {{ background:#eee; color:#333; padding:0.5rem 1rem; font-size:0.9rem; border:none; border-radius:6px; cursor:pointer; }}
.card-config {{ background:#f7f7f7; border:1px solid #e4e4e7; border-radius:8px; padding:1rem; margin-bottom:1rem; }}
.card-editor {{ height:160px; background:#fff; margin-top:0.3rem; }}
.preview-bar {{ margin-top:1rem; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; }}
.preview-bar button {{ background:#eee; color:#333; padding:0.5rem 1rem; font-size:0.9rem; border:none; border-radius:6px; cursor:pointer; }}
.preview-frame {{ width:100%; height:400px; border:1px solid #ccc; border-radius:6px; margin-top:0.5rem; background:#fff; }}
button.save-btn {{ background:#0066cc; color:#fff; padding:0.7rem 1.4rem; border:none; border-radius:6px; font-size:1rem; cursor:pointer; }}
a.back-link {{ color:#0066cc; text-decoration:none; }}
.gruppo-commenti {{ display:none; padding:1rem; background:#f7f7f7; border-radius:6px; margin-top:0.5rem; }}
.gruppo-commenti.attivo {{ display:block; }}
.translation-group {{ display:none; padding:1rem; background:#f7f7f7; border-radius:6px; margin-top:0.5rem; }}
.translation-group.attivo {{ display:block; }}
.preview-box {{ border:1px dashed #ccc; padding:1rem; border-radius:6px; margin-top:0.5rem; }}
.preview-box img {{ max-width:100%; border-radius:8px; }}
</style></head><body>
{_admin_navbar("config")}
<div class="config-wrap">
<h1>{T("admin_impostazioni_titolo", la)}</h1>

<div class="config-layout">
<div class="config-col-sinistra">

<h2>{T("admin_parte_alta_home", la)}</h2>
<p class="hint">{T("admin_parte_alta_hint", la)}</p>
<div id="editor-home"></div>

<div class="video-bar">
  <button type="button" data-tooltip="{T('tip_upload_image', la)}" onclick="document.getElementById('file-image').click()">{T("admin_carica_immagine", la)}</button>
  <button type="button" data-tooltip="{T('tip_youtube', la)}" onclick="insertYoutube()">{T("admin_inserisci_youtube", la)}</button>
  <button type="button" data-tooltip="{T('tip_upload_video', la)}" onclick="document.getElementById('file-video').click()">{T("admin_carica_video", la)}</button>
  <input type="file" id="file-image" accept="image/png, image/jpeg, image/svg+xml, .svg, .png, .jpg, .jpeg" style="display:none" onchange="uploadImage()">
  <input type="file" id="file-video" accept="video/*" style="display:none" onchange="uploadVideo()">
  <span id="upload-status" class="hint"></span>
</div>

<div class="preview-bar">
  <button type="button" data-tooltip="{T('tip_preview', la)}" onclick="togglePreview()">{T("admin_mostra_anteprima_home", la)}</button>
  <span class="hint">{T("admin_come_appare_home", la)}</span>
</div>
<iframe id="preview-iframe" class="preview-frame" style="display:none"></iframe>

<div class="sezione-home-en" style="margin-top:1.5rem; padding-top:1.5rem; border-top:1px solid #e4e4e7">
  <h2>{T("admin_presentazione_inglese", la)}</h2>
  <p class="hint">{T("admin_presentazione_en_hint", la)}</p>
  <div class="translation-bar" style="margin:0.6rem 0">
    <button type="button" onclick="translateHome()">{T("admin_traduci_dall_italiano", la)}</button>
    <span id="home-en-status" class="hint"></span>
  </div>
  <div id="editor-home-en"></div>
</div>

<h2>{T("admin_card_home_titolo", la)}</h2>
<p class="hint">{T("admin_card_home_hint", la)}</p>
{card_html}

</div><!-- fine colonna sinistra -->

<div class="config-col-destra">

<h2>{T("admin_impostazioni_generali", la)}</h2>

<label>{T("admin_titolo_sito", la)}</label>
<input type="text" id="site_title" value="{site_title_value}" placeholder="{ph['site_title']}">

<label>{T("admin_sottotitolo", la)}</label>
<input type="text" id="subtitle" value="{subtitle}" placeholder="{ph['subtitle']}">

<label>{T("admin_autore", la)}</label>
<input type="text" id="author" value="{author}" placeholder="{ph['author']}">

<label>{T("admin_dominio_sito", la)} <span class="hint">{T("admin_dominio_hint", la)}</span></label>
<input type="text" id="base_url" value="{base_url}" placeholder="{ph['base_url']}">

<label>{T("admin_analytics", la)} <span class="hint">{T("admin_analytics_hint", la)}</span></label>
<input type="text" id="analytics_id" value="{analytics_id}" placeholder="{ph['analytics_id']}">

<label>{T("admin_umami", la)} <span class="hint">{T("admin_umami_hint", la)}</span></label>
<input type="text" id="umami_url" value="{umami_url}" placeholder="{ph['umami_url']}">
<input type="text" id="umami_website_id" value="{umami_website_id}" placeholder="{ph['umami_website_id']}" style="margin-top:0.3rem">

<label>{T("admin_lingua_principale", la)} <span class="hint">{T("admin_lingua_principale_hint", la)}</span></label>
<input type="text" id="language" value="{language}">

<h2>{T("admin_layout_titolo", la)}</h2>
<p class="hint">{T("admin_layout_hint", la)}</p>

<label>{T("admin_posizione", la)} 1</label>
{order_selects[0]}
<label>{T("admin_posizione", la)} 2</label>
{order_selects[1]}
<label>{T("admin_posizione", la)} 3</label>
{order_selects[2]}

<label>{T("admin_articoli_per_pagina", la)} <span class="hint">{T("admin_articoli_per_pagina_hint", la)}</span></label>
<input type="number" id="articoli_per_pagina" min="0" value="{articles_per_page}">

<h2>{T("admin_seo_titolo", la)}</h2>
<p class="hint">{T("admin_seo_intro", la)}</p>

<label>{T("admin_seo_autore_url", la)} <span class="hint">{T("admin_seo_autore_url_hint", la)}</span></label>
<input type="text" id="seo_author_url" value="{seo_author_url}" placeholder="{ph['seo_author_url']}">

<label>{T("admin_seo_autore_immagine", la)}</label>
<input type="text" id="seo_author_image" value="{seo_author_image}" placeholder="{ph['seo_author_image']}">

<label>{T("admin_seo_autore_ruolo", la)} <span class="hint">{T("admin_seo_autore_ruolo_hint", la)}</span></label>
<input type="text" id="seo_author_role" value="{seo_author_role}" placeholder="{ph['seo_author_role']}">

<label>{T("admin_seo_autore_bio", la)} <span class="hint">{T("admin_seo_autore_bio_hint", la)}</span></label>
<textarea id="seo_author_bio" rows="3" placeholder="{ph['seo_author_bio']}">{seo_author_bio}</textarea>

<label>{T("admin_seo_profili", la)} <span class="hint">{T("admin_seo_profili_hint", la)}</span></label>
<textarea id="seo_profili" rows="4" placeholder="https://github.com/tuonome&#10;https://www.linkedin.com/in/tuonome&#10;https://x.com/tuonome">{seo_profiles}</textarea>

<label>{T("admin_seo_logo", la)}</label>
<input type="text" id="seo_logo" value="{seo_logo}" placeholder="{ph['seo_logo']}">

<label>{T("admin_seo_twitter", la)} <span class="hint">{T("admin_seo_twitter_hint", la)}</span></label>
<input type="text" id="seo_twitter" value="{seo_twitter}" placeholder="{ph['seo_twitter']}">

<label>{T("admin_seo_favicon", la)} <span class="hint">{T("admin_seo_favicon_hint", la)}</span></label>
<input type="text" id="seo_favicon" value="{seo_favicon}">

<h2>{T("admin_ai_training_titolo", la)}</h2>
<p class="hint">{T("admin_ai_training_intro", la)}</p>

<label>{T("admin_ai_training_policy", la)}</label>
<select id="ai_training_policy" onchange="updateAiTrainingGroup()">
  <option value="open" {sel_ai_open}>{T("admin_ai_training_open", la)}</option>
  <option value="licensed" {sel_ai_licensed}>{T("admin_ai_training_licensed", la)}</option>
  <option value="disallow" {sel_ai_disallow}>{T("admin_ai_training_disallow", la)}</option>
</select>

<div id="gruppo-ai-licenza" style="display:none">
  <label>{T("admin_ai_training_email", la)} <span class="hint">{T("admin_ai_training_email_hint", la)}</span></label>
  <input type="text" id="ai_training_contact_email" value="{ai_contact_email}" placeholder="licensing@tuodominio.it">
</div>

<label>{T("admin_ai_training_license_url", la)} <span class="hint">{T("admin_ai_training_license_url_hint", la)}</span></label>
<input type="text" id="ai_training_license_url" value="{ai_license_url}">

<label>{T("admin_ai_training_statement", la)} <span class="hint">{T("admin_ai_training_statement_hint", la)}</span></label>
<textarea id="ai_training_statement" rows="3">{ai_statement}</textarea>

<p class="hint">{T("admin_ai_training_nota_standard", la)}</p>

<h2>{T("admin_commenti_titolo", la)}</h2>

<label>{T("admin_sistema_commenti", la)}</label>
<select id="commenti" onchange="updateCommentGroups()">
  <option value="none" {none_selected}>{T("admin_commenti_nessuno", la)}</option>
  <option value="giscus" {sel_giscus}>Giscus (GitHub)</option>
  <option value="disqus" {sel_disqus}>Disqus</option>
</select>

<div class="gruppo-commenti" id="gruppo-giscus">
  <p class="hint">Valori da https://giscus.app</p>
  <label>Repo <span class="hint">(es. tuonome/tuorepo)</span></label>
  <input type="text" id="giscus_repo" value="{giscus_repo}">
  <label>Repo ID</label>
  <input type="text" id="giscus_repo_id" value="{giscus_repo_id}">
  <label>Category</label>
  <input type="text" id="giscus_category" value="{giscus_category}">
  <label>Category ID</label>
  <input type="text" id="giscus_category_id" value="{giscus_category_id}">
  <label>{T("admin_tema_label", la)} <span class="hint">(light / dark)</span></label>
  <input type="text" id="giscus_theme" value="{giscus_theme}">
</div>

<div class="gruppo-commenti" id="gruppo-disqus">
  <p class="hint">{T("admin_disqus_hint", la)}</p>
  <label>Shortname Disqus</label>
  <input type="text" id="disqus_shortname" value="{disqus_shortname}">
</div>

<h2>{T("admin_traduzione_titolo", la)}</h2>
<p class="hint">{T("admin_traduzione_intro", la)}</p>

<label>{T("admin_servizio_traduzione", la)}</label>
<select id="translation_service" onchange="updateTranslationGroups()">
  <option value="deepl" {sel_deepl}>DeepL</option>
  <option value="google" {sel_google}>Google Translate</option>
  <option value="llm" {sel_llm}>Anthropic Claude</option>
  <option value="openai" {sel_openai}>OpenAI (ChatGPT)</option>
  <option value="deepseek" {sel_deepseek}>DeepSeek</option>
</select>

<div class="translation-group" id="gruppo-deepl">
  <label>{T("admin_chiave_api", la)} DeepL <span class="hint">(https://www.deepl.com/pro-api)</span></label>
  <input type="password" id="deepl_api_key" value="{deepl_api_key}" placeholder="{T('admin_lascia_vuoto', la)}">
</div>

<div class="translation-group" id="gruppo-google">
  <label>{T("admin_chiave_api", la)} Google Cloud Translation</label>
  <input type="password" id="google_api_key" value="{google_api_key}" placeholder="{T('admin_lascia_vuoto', la)}">
</div>

<div class="translation-group" id="gruppo-llm">
  <label>{T("admin_chiave_api", la)} Anthropic</label>
  <input type="password" id="llm_api_key" value="{llm_api_key}" placeholder="{T('admin_lascia_vuoto', la)}">
  <label>{T("admin_endpoint", la)}</label>
  <input type="text" id="llm_endpoint" value="{llm_endpoint}">
  <label>{T("admin_modello_label", la)}</label>
  <input type="text" id="llm_modello" value="{llm_modello}">
</div>

<div class="translation-group" id="gruppo-openai">
  <label>{T("admin_chiave_api", la)} OpenAI <span class="hint">(https://platform.openai.com/api-keys)</span></label>
  <input type="password" id="openai_api_key" value="{openai_api_key}" placeholder="{T('admin_lascia_vuoto', la)}">
  <label>{T("admin_modello_label", la)} <span class="hint">(gpt-4o-mini, gpt-4o)</span></label>
  <input type="text" id="openai_modello" value="{openai_modello}">
</div>

<div class="translation-group" id="gruppo-deepseek">
  <label>{T("admin_chiave_api", la)} DeepSeek <span class="hint">(https://platform.deepseek.com)</span></label>
  <input type="password" id="deepseek_api_key" value="{deepseek_api_key}" placeholder="{T('admin_lascia_vuoto', la)}">
  <label>{T("admin_modello_label", la)} <span class="hint">(deepseek-chat)</span></label>
  <input type="text" id="deepseek_modello" value="{deepseek_modello}">
</div>

</div><!-- fine colonna destra -->
</div><!-- fine config-layout -->

<div class="azioni config-save-bar">
  <button class="save-btn" onclick="saveConfig()">{T("admin_salva_rigenera", la)}</button>
  <span id="save-status" class="hint"></span>
</div>

<details class="config-avanzata">
  <summary>{T("admin_config_avanzata", la)}</summary>
  <div class="config-avanzata-corpo">
    <p class="hint">{T("admin_config_avanzata_hint", la)}</p>
    <textarea id="config-raw" rows="20" spellcheck="false"></textarea>
    <div class="azioni" style="margin-top:0.8rem">
      <button type="button" class="save-btn" onclick="saveRawConfig()">{T("admin_salva_config_raw", la)}</button>
      <button type="button" class="btn-secondario" onclick="restoreRawConfig()">{T("admin_ripristina", la)}</button>
      <span id="config-raw-status" class="hint"></span>
    </div>
  </div>
</details>

<script src="https://cdn.quilljs.com/1.3.7/quill.min.js"></script>
<script src="https://unpkg.com/quill-blot-formatter@1.0.5/dist/quill-blot-formatter.min.js"></script>
{_image_overlay_script(la)}
{_toolbar_tooltips_script(la)}
<script>
// Module to resize and align images.
// We use quill-blot-formatter: it handles resizing in every direction well
// and follows the image when it is moved or centred.
if (window.QuillBlotFormatter) {{
  Quill.register('modules/blotFormatter', window.QuillBlotFormatter.default);
}}

const quill = new Quill('#editor-home', {{
  theme: 'snow',
  placeholder: {home_intro_ph_it_js},
  modules: {{
    blotFormatter: {{}},
    toolbar: [
    [{{ font: [] }}, {{ size: ['small', false, 'large', 'huge'] }}],
    [{{ header: [1, 2, 3, false] }}],
    ['bold', 'italic', 'underline'],
    [{{ color: [] }}, {{ background: [] }}],
    [{{ list: 'ordered' }}, {{ list: 'bullet' }}],
    [{{ align: '' }}, {{ align: 'center' }}, {{ align: 'right' }}, {{ align: 'justify' }}],
    ['blockquote', 'link', 'image'],
    ['clean']
  ]}}
}});
quill.root.innerHTML = {home_content_js};
attachImageOverlay(quill);
handlePastedImages(quill, 'upload-status');
applyToolbarTooltips();

// Quill editor for the English introduction of the homepage.
const quillHomeEn = new Quill('#editor-home-en', {{
  theme: 'snow',
  placeholder: {home_intro_ph_en_js},
  modules: {{
    blotFormatter: {{}},
    toolbar: [
    [{{ font: [] }}, {{ size: ['small', false, 'large', 'huge'] }}],
    [{{ header: [1, 2, 3, false] }}],
    ['bold', 'italic', 'underline'],
    [{{ color: [] }}, {{ background: [] }}],
    [{{ list: 'ordered' }}, {{ list: 'bullet' }}],
    [{{ align: '' }}, {{ align: 'center' }}, {{ align: 'right' }}, {{ align: 'justify' }}],
    ['blockquote', 'link', 'image'],
    ['clean']
  ]}}
}});
quillHomeEn.root.innerHTML = {home_content_en_js};
attachImageOverlay(quillHomeEn);
handlePastedImages(quillHomeEn, null);
applyToolbarTooltips();

// Translates the home introduction from Italian to English with AI.
function translateHome() {{
  var pulsante = event.target;
  var stato = document.getElementById('home-en-status');
  var contenutoIt = quill.root.innerHTML;

  if (quill.getText().trim() === '') {{
    stato.textContent = "{T("js_write_intro_first", la)}";
    return;
  }}

  pulsante.disabled = true;
  stato.textContent = "{T("js_translating", la)}";

  fetch('/translate', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ text: contenutoIt }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    pulsante.disabled = false;
    if (res.ok === true) {{
      quillHomeEn.root.innerHTML = res.text;
      stato.textContent = "{T("js_translated_home", la)}";
    }} else {{
      stato.textContent = "{T("js_error_prefix", la)}" + res.error;
    }}
  }})
  .catch(function(e) {{
    pulsante.disabled = false;
    stato.textContent = "{T("js_net_error_translation", la)}";
  }});
}}

// We create a WYSIWYG editor (Quill) for each homepage card.
var contenutiCard = {card_contents_js};
var editorCard = [];
for (var c = 0; c < contenutiCard.length; c++) {{
  var editorCardSingolo = new Quill('#card-editor-' + c, {{
    theme: 'snow',
    modules: {{
      blotFormatter: {{}},
      toolbar: [
        [{{ header: [3, false] }}],
        ['bold', 'italic', 'underline'],
        [{{ color: [] }}],
        [{{ list: 'ordered' }}, {{ list: 'bullet' }}],
        ['link', 'image'],
        ['clean']
      ]
    }}
  }});
  editorCardSingolo.root.innerHTML = contenutiCard[c];
  attachImageOverlay(editorCardSingolo);
  handlePastedImages(editorCardSingolo, null);
  editorCard.push(editorCardSingolo);
  applyToolbarTooltips();
}}

// Shows or hides the preview of the top of the homepage.
function togglePreview() {{
  var frame = document.getElementById("preview-iframe");
  if (frame.style.display === "none") {{
    frame.style.display = "block";
    updatePreview();
  }} else {{
    frame.style.display = "none";
  }}
}}

// Updates the preview with the current content of the home editor.
function updatePreview() {{
  var frame = document.getElementById("preview-iframe");
  if (frame.style.display === "none") {{
    return;
  }}
  var contenuto = quill.root.innerHTML;
  var pagina = '<!DOCTYPE html><html><head>';
  pagina = pagina + '<meta charset="utf-8">';
  pagina = pagina + '<link rel="stylesheet" href="/style.css">';
  pagina = pagina + '</head><body>';
  pagina = pagina + '<section class="home-intro">';
  pagina = pagina + contenuto;
  pagina = pagina + '</section></body></html>';
  var documento = frame.contentDocument;
  documento.open();
  documento.write(pagina);
  documento.close();
}}

quill.on("text-change", function() {{
  updatePreview();
}});

// Shows only the field group of the chosen comment system.
function updateCommentGroups() {{
  var scelta = document.getElementById('commenti').value;
  var gruppoGiscus = document.getElementById('gruppo-giscus');
  var gruppoDisqus = document.getElementById('gruppo-disqus');
  gruppoGiscus.classList.remove('attivo');
  gruppoDisqus.classList.remove('attivo');
  if (scelta === 'giscus') {{
    gruppoGiscus.classList.add('attivo');
  }}
  if (scelta === 'disqus') {{
    gruppoDisqus.classList.add('attivo');
  }}
}}
updateCommentGroups();

// Shows the licensing contact field only when the policy requires one.
function updateAiTrainingGroup() {{
  var scelta = document.getElementById('ai_training_policy').value;
  var gruppo = document.getElementById('gruppo-ai-licenza');
  if (scelta === 'licensed') {{
    gruppo.style.display = 'block';
  }} else {{
    gruppo.style.display = 'none';
  }}
}}
updateAiTrainingGroup();

// Shows only the fields of the chosen translation service.
function updateTranslationGroups() {{
  var scelta = document.getElementById('translation_service').value;
  var gruppoDeepl = document.getElementById('gruppo-deepl');
  var gruppoGoogle = document.getElementById('gruppo-google');
  var gruppoLlm = document.getElementById('gruppo-llm');
  var gruppoOpenai = document.getElementById('gruppo-openai');
  var gruppoDeepseek = document.getElementById('gruppo-deepseek');
  gruppoDeepl.classList.remove('attivo');
  gruppoGoogle.classList.remove('attivo');
  gruppoLlm.classList.remove('attivo');
  gruppoOpenai.classList.remove('attivo');
  gruppoDeepseek.classList.remove('attivo');
  if (scelta === 'deepl') {{
    gruppoDeepl.classList.add('attivo');
  }}
  if (scelta === 'google') {{
    gruppoGoogle.classList.add('attivo');
  }}
  if (scelta === 'llm') {{
    gruppoLlm.classList.add('attivo');
  }}
  if (scelta === 'openai') {{
    gruppoOpenai.classList.add('attivo');
  }}
  if (scelta === 'deepseek') {{
    gruppoDeepseek.classList.add('attivo');
  }}
}}
updateTranslationGroups();

// --- Video functions (reused from the articles editor) ---
function extractYoutubeId(url) {{
  var idVideo = "";
  if (url.indexOf("youtu.be/") !== -1) {{
    idVideo = url.split("youtu.be/")[1];
  }} else if (url.indexOf("watch?v=") !== -1) {{
    idVideo = url.split("watch?v=")[1];
  }} else if (url.indexOf("/embed/") !== -1) {{
    idVideo = url.split("/embed/")[1];
  }}
  var posAmp = idVideo.indexOf("&");
  if (posAmp !== -1) {{
    idVideo = idVideo.substring(0, posAmp);
  }}
  var posQ = idVideo.indexOf("?");
  if (posQ !== -1) {{
    idVideo = idVideo.substring(0, posQ);
  }}
  return idVideo.trim();
}}

function insertYoutube() {{
  var url = prompt("{T("js_prompt_youtube_link", la)}");
  if (url === null) {{ return; }}
  if (url === "") {{ return; }}
  var idVideo = extractYoutubeId(url);
  if (idVideo === "") {{
    alert("{T("js_youtube_not_recognized", la)}");
    return;
  }}
  var codice = '<div class="video-youtube">';
  codice = codice + '<iframe src="https://www.youtube.com/embed/' + idVideo + '"';
  codice = codice + ' allowfullscreen></iframe></div><p><br></p>';
  var posizione = quill.getSelection(true);
  quill.clipboard.dangerouslyPasteHTML(posizione.index, codice);
}}

function uploadVideo() {{
  var campoFile = document.getElementById("file-video");
  var stato = document.getElementById("upload-status");
  if (campoFile.files.length === 0) {{ return; }}
  var file = campoFile.files[0];
  var datiForm = new FormData();
  datiForm.append("video", file);
  stato.textContent = "{T('js_uploading', la)}";
  fetch("/upload", {{ method: "POST", body: datiForm }})
    .then(function(risposta) {{ return risposta.json(); }})
    .then(function(risultato) {{
      if (risultato.ok === true) {{
        var codice = '<video controls src="' + risultato.url + '"></video><p><br></p>';
        var posizione = quill.getSelection(true);
        quill.clipboard.dangerouslyPasteHTML(posizione.index, codice);
        stato.textContent = "{T('js_video_uploaded', la)}";
      }} else {{
        stato.textContent = "{T('js_error_prefix', la)}" + risultato.error;
      }}
    }})
    .catch(function(errore) {{ stato.textContent = "{T('js_upload_error', la)}"; }});
}}

// Uploads an image (PNG, JPEG or SVG) and inserts it into the editor.
function uploadImage() {{
  var campoFile = document.getElementById("file-image");
  var stato = document.getElementById("upload-status");
  if (campoFile.files.length === 0) {{
    return;
  }}
  var file = campoFile.files[0];
  var datiForm = new FormData();
  datiForm.append("video", file);
  stato.textContent = "{T('js_uploading_image', la)}";
  fetch("/upload", {{ method: "POST", body: datiForm }})
    .then(function(risposta) {{ return risposta.json(); }})
    .then(function(risultato) {{
      if (risultato.ok === true) {{
        var codice = '<img src="' + risultato.url + '"><p><br></p>';
        var posizione = quill.getSelection(true);
        quill.clipboard.dangerouslyPasteHTML(posizione.index, codice);
        stato.textContent = "{T('js_image_uploaded', la)}";
      }} else {{
        stato.textContent = "{T('js_error_prefix', la)}" + risultato.error;
      }}
    }})
    .catch(function(errore) {{ stato.textContent = "{T('js_upload_error', la)}"; }});
}}

function saveConfig() {{
  // We collect the data of the homepage cards.
  var cardElementi = document.querySelectorAll('.card-config');
  var cardDati = [];
  for (var i = 0; i < cardElementi.length; i++) {{
    var elemento = cardElementi[i];
    var attiva = elemento.querySelector('.card-attiva').checked;
    var titolo = elemento.querySelector('.card-title').value;
    // The content comes from the Quill editor matching this card.
    var contenuto = editorCard[i].root.innerHTML;
    cardDati.push({{ active: attiva, title: titolo, content: contenuto }});
  }}

  // Social profiles: from the textarea, one line per profile (blank lines excluded).
  var righeProfili = document.getElementById('seo_profili').value.split('\\n');
  var profiliSocial = [];
  for (var p = 0; p < righeProfili.length; p++) {{
    var rigaProfilo = righeProfili[p].trim();
    if (rigaProfilo !== '') {{
      profiliSocial.push(rigaProfilo);
    }}
  }}

  // Order of the homepage sections, from the three dropdowns.
  // If the user picks the same section twice, we complete with the
  // missing ones so that none is lost.
  var ordineScelto = [
    document.getElementById('ordine_home_0').value,
    document.getElementById('ordine_home_1').value,
    document.getElementById('ordine_home_2').value
  ];
  var ordineHome = [];
  for (var o = 0; o < ordineScelto.length; o++) {{
    if (ordineHome.indexOf(ordineScelto[o]) === -1) {{
      ordineHome.push(ordineScelto[o]);
    }}
  }}
  var tutteSezioni = ['intro', 'articles', 'cards'];
  for (var t = 0; t < tutteSezioni.length; t++) {{
    if (ordineHome.indexOf(tutteSezioni[t]) === -1) {{
      ordineHome.push(tutteSezioni[t]);
    }}
  }}

  var articoliPerPagina = parseInt(document.getElementById('articoli_per_pagina').value, 10);
  if (isNaN(articoliPerPagina) || articoliPerPagina < 0) {{
    articoliPerPagina = 10;
  }}

  var config = {{
    site_title: document.getElementById('site_title').value,
    subtitle: document.getElementById('subtitle').value,
    author: document.getElementById('author').value,
    base_url: document.getElementById('base_url').value,
    analytics_id: document.getElementById('analytics_id').value.trim(),
    umami_url: document.getElementById('umami_url').value.trim(),
    umami_website_id: document.getElementById('umami_website_id').value.trim(),
    language: document.getElementById('language').value,
    home_order: ordineHome,
    articles_per_page: articoliPerPagina,
    seo: {{
      author_url: document.getElementById('seo_author_url').value.trim(),
      author_image: document.getElementById('seo_author_image').value.trim(),
      author_role: document.getElementById('seo_author_role').value.trim(),
      author_bio: document.getElementById('seo_author_bio').value.trim(),
      social_profiles: profiliSocial,
      logo: document.getElementById('seo_logo').value.trim(),
      twitter_site: document.getElementById('seo_twitter').value.trim(),
      favicon: document.getElementById('seo_favicon').value.trim()
    }},
    home_content: quill.root.innerHTML,
    home_content_en: quillHomeEn.root.innerHTML,
    home_cards: cardDati,
    comments: document.getElementById('commenti').value,
    giscus: {{
      repo: document.getElementById('giscus_repo').value,
      repo_id: document.getElementById('giscus_repo_id').value,
      category: document.getElementById('giscus_category').value,
      category_id: document.getElementById('giscus_category_id').value,
      theme: document.getElementById('giscus_theme').value
    }},
    disqus: {{
      shortname: document.getElementById('disqus_shortname').value
    }},
    ai_training: {{
      policy: document.getElementById('ai_training_policy').value,
      contact_email: document.getElementById('ai_training_contact_email').value.trim(),
      license_url: document.getElementById('ai_training_license_url').value.trim(),
      statement: document.getElementById('ai_training_statement').value.trim()
    }},
    translation: {{
      service: document.getElementById('translation_service').value,
      deepl_api_key: document.getElementById('deepl_api_key').value,
      google_api_key: document.getElementById('google_api_key').value,
      llm_api_key: document.getElementById('llm_api_key').value,
      llm_endpoint: document.getElementById('llm_endpoint').value,
      llm_model: document.getElementById('llm_modello').value,
      openai_api_key: document.getElementById('openai_api_key').value,
      openai_model: document.getElementById('openai_modello').value,
      deepseek_api_key: document.getElementById('deepseek_api_key').value,
      deepseek_model: document.getElementById('deepseek_modello').value
    }}
  }};
  var stato = document.getElementById('save-status');
  stato.textContent = "{T('admin_salvataggio', la)}";
  fetch('/save-config', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(config)
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      stato.textContent = "{T('admin_config_salvata', la)}";
    }} else {{
      stato.textContent = "Error: " + res.error;
    }}
  }})
  .catch(function(e) {{ stato.textContent = "{T('admin_errore_salvataggio', la)}"; }});
}}

// --- Advanced config.json editor ---
// The initial config text (formatted) is injected from Python.
var configRawIniziale = {config_raw_js};
document.getElementById('config-raw').value = configRawIniziale;

// Puts the original config back into the textarea (discards unsaved changes).
function restoreRawConfig() {{
  document.getElementById('config-raw').value = configRawIniziale;
  document.getElementById('config-raw-status').textContent = "";
}}

// Saves the hand-edited config.json, after server-side validation.
function saveRawConfig() {{
  var stato = document.getElementById('config-raw-status');
  var contenuto = document.getElementById('config-raw').value;

  // Preliminary browser-side check: warns immediately if the JSON is broken.
  try {{
    JSON.parse(contenuto);
  }} catch (e) {{
    stato.textContent = "{T('err_invalid_json_prefix', la)}" + e.message;
    return;
  }}

  stato.textContent = "{T('admin_salvataggio', la)}";
  fetch('/save-config-raw', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ content: contenuto }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      stato.textContent = "{T('admin_config_raw_salvata', la)}";
      // We update the "original" reference to the newly saved content.
      configRawIniziale = contenuto;
    }} else {{
      stato.textContent = "Errore: " + res.error;
    }}
  }})
  .catch(function(e) {{ stato.textContent = "{T('admin_errore_salvataggio', la)}"; }});
}}
</script>
</div>
<script src="{BOOTSTRAP_JS}"></script>
</body></html>"""


def editor_page(art=None):
    """The page with the WYSIWYG editor (it uses Quill, loaded from a CDN)."""
    # If we are editing an existing article, we take its values.
    # If instead this is a new article (art is None), we start from empty fields.
    if art is not None:
        title_value = html.escape(art.get("title", ""))
        slug = art.get("slug", "")
        description = html.escape(art.get("description", ""))
        preview = html.escape(art.get("preview", ""))
        tags = html.escape(art.get("tags", ""))
        image = html.escape(art.get("image", ""))
        content = art["content"]
        status = art.get("status", "draft")
        # Fields of the English translation.
        title_en = art.get("title_en", "")
        description_en = art.get("description_en", "")
        preview_en = art.get("preview_en", "")
        content_en = art.get("content_en", "")
        translation_authorized = art.get("translation_authorized", False)
        translation_confirmed = art.get("translation_confirmed", False)
    else:
        title_value = ""
        slug = ""
        description = ""
        preview = ""
        tags = ""
        image = ""
        content = ""
        status = "draft"
        title_en = ""
        description_en = ""
        preview_en = ""
        content_en = ""
        translation_authorized = False
        translation_confirmed = False

    content_js = json.dumps(content)
    # We pass the translation values to the JavaScript safely.
    title_en_js = json.dumps(title_en)
    description_en_js = json.dumps(description_en)
    preview_en_js = json.dumps(preview_en)
    content_en_js = json.dumps(content_en)
    if translation_authorized:
        autorizzata_js = "true"
    else:
        autorizzata_js = "false"
    if translation_confirmed:
        confirmed_js = "true"
    else:
        confirmed_js = "false"

    # We work out which status option is selected in the dropdown.
    published_selected = ""
    draft_selected = ""
    if status == "published":
        published_selected = "selected"
    else:
        draft_selected = "selected"

    # The page title and the presence of the delete button depend on whether
    # the article is new or already exists.
    la = admin_language()
    if art is not None:
        page_title = T("admin_modifica_articolo_titolo", la)
        delete_button = f'<button class="delete-btn" onclick="deleteItem()">{T("admin_elimina", la)}</button>'
    else:
        page_title = T("admin_nuovo_articolo_titolo", la)
        delete_button = ""

    return f"""<!DOCTYPE html>
<html lang="it"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<link href="{BOOTSTRAP_CSS}" rel="stylesheet">
<link href="https://cdn.quilljs.com/1.3.7/quill.snow.css" rel="stylesheet">
<!-- highlight.js: colora la sintassi nei blocchi di codice -->
<link href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<style>{CSS_ADMIN}
.editor-wrap {{ max-width:800px; margin:0 auto; padding:1.5rem 1rem 4rem; }}
h1 {{ font-size:1.4rem; }}
label {{ display:block; font-weight:600; margin:1rem 0 0.3rem; font-size:0.9rem; }}
/* Two-column layout: main content on the left, sidebar on the right
   with the metadata and the actions. On narrow screens it becomes one column. */
.editor-wrap {{ max-width:1500px; margin:0 auto; }}
.editor-layout {{ display:grid; grid-template-columns:3fr 1fr; gap:1.5rem; align-items:start; }}
.editor-main {{ min-width:0; }}
.editor-sidebar {{ position:sticky; top:1rem; background:#fafafa; border:1px solid #e4e4e7; border-radius:10px; padding:1.2rem; display:flex; flex-direction:column; gap:0.3rem; max-height:calc(100vh - 2rem); overflow-y:auto; }}
.editor-sidebar h2 {{ font-size:0.95rem; text-transform:uppercase; letter-spacing:0.03em; color:#666; margin:1rem 0 0.3rem; }}
.editor-sidebar h2:first-child {{ margin-top:0; }}
/* Card for the important sidebar fields (preview, SEO): a white box
   that sets them apart visually from the rest of the metadata. */
.card-campo {{ background:#fff; border:1px solid #e4e4e7; border-radius:8px; padding:0.9rem; margin:0.8rem 0; }}
.card-campo h2 {{ margin-top:0 !important; }}
.sidebar-azioni {{ display:flex; flex-direction:column; gap:0.6rem; margin-top:1rem; padding-top:1rem; border-top:1px solid #e4e4e7; }}
.sidebar-azioni button {{ width:100%; }}
/* On medium screens (tablet) we give the sidebar more room: 25% would be too
   narrow for the fields. We switch to roughly 70/30. */
@media (max-width: 1200px) and (min-width: 901px) {{
  .editor-layout {{ grid-template-columns:2.3fr 1fr; }}
}}
@media (max-width: 900px) {{
  .editor-layout {{ grid-template-columns:1fr; }}
  .editor-sidebar {{ position:static; max-height:none; }}
}}
input,select,textarea {{ width:100%; padding:0.6rem; border:1px solid #ccc; border-radius:6px; font-size:1rem; font-family:inherit; }}
textarea {{ resize:vertical; line-height:1.5; }}
.btn-suggerisci {{ background:#6b3df5; color:#fff; border:none; border-radius:6px; padding:0.35rem 0.8rem; font-size:0.82rem; cursor:pointer; white-space:nowrap; }}
.btn-suggerisci:hover {{ background:#5a30d0; }}
/* SEO analysis results panel in the sidebar. */
#seo-results {{ margin-top:0.6rem; }}
.seo-heading {{ font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:0.03em; color:#6b3df5; margin:0.8rem 0 0.25rem; }}
.seo-row {{ display:flex; align-items:flex-start; justify-content:space-between; gap:0.5rem; font-size:0.85rem; padding:0.2rem 0; border-bottom:1px dashed #eee; word-break:break-word; }}
.seo-row span {{ flex:1; }}
.seo-copy {{ background:#f1eefe; color:#6b3df5; border:1px solid #d8ccfb; border-radius:5px; padding:0.1rem 0.5rem; font-size:0.72rem; cursor:pointer; white-space:nowrap; }}
.seo-copy:hover {{ background:#e4ddfd; }}
.seo-text {{ font-size:0.85rem; margin:0.25rem 0; line-height:1.4; }}
.seo-warning {{ background:#fef3cd; border:1px solid #f0d68a; border-radius:6px; padding:0.4rem 0.6rem; }}
.seo-apply-all {{ width:100%; margin-top:0.6rem; background:#1a8754; color:#fff; border:none; border-radius:6px; padding:0.45rem 0.8rem; font-size:0.85rem; cursor:pointer; }}
.seo-apply-all:hover {{ background:#146c43; }}
.seo-report-btn {{ width:100%; margin-top:0.4rem; background:#fff; color:#0066cc; border:1px solid #0066cc; border-radius:6px; padding:0.4rem 0.8rem; font-size:0.83rem; cursor:pointer; }}
.seo-report-btn:hover {{ background:#eef5ff; }}
/* The revision window: the article with the proposed additions. */
#revision-overlay {{ position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:1000; display:flex; align-items:center; justify-content:center; }}
.revision-window {{ background:#fff; border-radius:10px; padding:1.2rem; width:min(92vw, 860px); max-height:88vh; display:flex; flex-direction:column; gap:0.7rem; box-shadow:0 10px 40px rgba(0,0,0,0.25); }}
.revision-window h3 {{ margin:0; font-size:1rem; }}
.revision-intro {{ margin:0; font-size:0.82rem; color:#555; }}
.revision-area {{ overflow:auto; padding:0.6rem; border:1px solid #e4e4e7; border-radius:8px; line-height:1.55; }}
.revision-edit {{ background:#e8f7ee; border:1px solid #9fd8b4; border-left:4px solid #1a8754; border-radius:6px; margin:0.6rem 0; padding:0.5rem 0.7rem; }}
.revision-edit-head {{ display:flex; align-items:flex-start; gap:0.5rem; font-size:0.78rem; color:#146c43; font-weight:600; cursor:pointer; margin-bottom:0.35rem; }}
.revision-edit-head input {{ margin-top:0.15rem; }}
.revision-edit-body {{ font-size:0.95rem; }}
.revision-rejected {{ opacity:0.45; background:#f4f4f5; border-color:#d4d4d8; border-left-color:#a1a1aa; }}
.revision-rejected .revision-edit-body {{ text-decoration:line-through; }}
/* Embedded tables inside the editor: they must look like tables, and
   invite the click that opens the small table editor. */
#editor .raw-html-block {{ cursor:pointer; position:relative; margin:0.8rem 0; }}
#editor .raw-html-block:hover {{ outline:2px solid #6b3df5; outline-offset:2px; border-radius:4px; }}
#editor .raw-html-block:hover::after {{ content:"{T("admin_table_hint", la)}"; position:absolute; top:-1.6rem; left:0; background:#6b3df5; color:#fff; font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:4px; white-space:nowrap; }}
#editor .article-table {{ border-collapse:collapse; width:100%; }}
#editor .article-table th, #editor .article-table td {{ border:1px solid #d4d4d8; padding:0.35rem 0.6rem; font-size:0.9rem; text-align:left; }}
#editor .article-table th {{ background:#f4f4f5; font-weight:600; }}
/* The small table editor window. */
#table-editor-overlay {{ position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:1000; display:flex; align-items:center; justify-content:center; }}
.table-editor-window {{ background:#fff; border-radius:10px; padding:1.2rem; max-width:min(90vw, 900px); max-height:85vh; display:flex; flex-direction:column; gap:0.8rem; box-shadow:0 10px 40px rgba(0,0,0,0.25); }}
.table-editor-window h3 {{ margin:0; font-size:1rem; }}
.table-editor-area {{ overflow:auto; }}
.table-editor-area table {{ border-collapse:collapse; }}
.table-editor-area th, .table-editor-area td {{ border:1px solid #d4d4d8; padding:0.35rem 0.6rem; min-width:4rem; font-size:0.9rem; }}
.table-editor-area th {{ background:#f4f4f5; }}
.table-editor-area [contenteditable="true"]:focus {{ outline:2px solid #6b3df5; outline-offset:-2px; }}
.table-editor-bar {{ display:flex; gap:0.4rem; flex-wrap:wrap; }}
.table-editor-bar button {{ background:#f1eefe; color:#6b3df5; border:1px solid #d8ccfb; border-radius:5px; padding:0.25rem 0.7rem; font-size:0.8rem; cursor:pointer; }}
.table-editor-bar button:hover {{ background:#e4ddfd; }}
.table-editor-actions {{ display:flex; gap:0.5rem; justify-content:flex-end; }}
.table-editor-actions button {{ border:1px solid #d4d4d8; background:#fff; color:#333; border-radius:6px; padding:0.35rem 1rem; font-size:0.85rem; cursor:pointer; }}
.table-editor-actions .table-editor-save {{ background:#6b3df5; color:#fff; border-color:#6b3df5; }}
.table-editor-actions .table-editor-save:hover {{ background:#5a30d0; }}
.btn-suggerisci:disabled {{ opacity:0.6; cursor:default; }}
.hint {{ color:#888; font-size:0.8rem; font-weight:400; }}
#editor {{ height:420px; background:#fff; margin-top:0.3rem; }}
#editor-en {{ height:300px; background:#fff; margin-top:0.3rem; }}
.translation-section {{ margin-top:1rem; padding-top:1rem; border-top:1px solid #e4e4e7; }}
.translation-section h2 {{ font-size:0.95rem; text-transform:uppercase; letter-spacing:0.03em; color:#666; }}
.riga-flag {{ display:flex; align-items:flex-start; gap:0.5rem; font-weight:600; cursor:pointer; font-size:0.88rem; margin-top:0.5rem; }}
.riga-flag input {{ width:auto; margin-top:0.2rem; }}
.translation-bar {{ display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; margin:0.8rem 0; }}
.translation-bar button {{ background:#0066cc; color:#fff; padding:0.5rem 1rem; font-size:0.85rem; border:none; border-radius:6px; cursor:pointer; }}
button {{ background:#0066cc; color:#fff; padding:0.7rem 1.4rem; border:none; border-radius:6px; font-size:1rem; cursor:pointer; }}
button.delete-btn {{ background:#cc0000; }}
a.back-link {{ color:#0066cc; text-decoration:none; }}
.video-bar {{ margin-top:0.6rem; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; }}
.video-bar button {{ background:#eee; color:#333; padding:0.5rem 1rem; font-size:0.9rem; }}
.preview-bar {{ margin-top:1rem; display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; }}
.preview-bar button {{ background:#eee; color:#333; padding:0.5rem 1rem; font-size:0.9rem; border:none; border-radius:6px; cursor:pointer; }}
.preview-frame {{ width:100%; height:400px; border:1px solid #ccc; border-radius:6px; margin-top:0.5rem; background:#fff; }}
/* Readable code blocks in the editor: Quill's native style makes them
   black on black. We force a light background and dark text, as on the public site. */
.ql-editor pre, .ql-editor pre.ql-syntax {{
  background:#f6f8fa !important; color:#1f2328 !important;
  border:1px solid #e2e2e2; border-radius:6px; padding:0.8rem 1rem;
  font-family:"SF Mono",Menlo,Monaco,Consolas,monospace; white-space:pre-wrap;
}}
.ql-editor pre.ql-syntax * {{ color:inherit; }}
/* Images in the editor keep their size even when they are aligned or
   centred. Without these rules, combining resizing and alignment can make
   the image collapse and disappear. */
.ql-editor {{ overflow-x:auto; }}
/* !important is needed here: blot-formatter writes an inline width style
   on the image when you drag-resize it (e.g. style="width:1200px"), and
   an inline style always wins over a plain external stylesheet rule.
   Without !important, an image resized wider than the editor would
   overflow it horizontally instead of being visually contained. */
.ql-editor img {{ height:auto; max-width:100% !important; vertical-align:top; }}
.ql-editor .ql-align-center {{ text-align:center; }}
.ql-editor .ql-align-center img {{ display:inline-block; margin-left:auto; margin-right:auto; }}
.ql-editor .ql-align-right {{ text-align:right; }}
.ql-editor .ql-align-right img {{ display:inline-block; }}
</style></head><body>
{_admin_navbar("articles")}
<div class="editor-wrap">
<h1 class="mb-3">{page_title}</h1>

<div class="editor-layout">

  <!-- COLONNA PRINCIPALE: titolo e contenuto dell'articolo -->
  <div class="editor-main">
    <label>{T("admin_titolo", la)}</label>
    <input type="text" id="title" value="{title_value}" placeholder="">

    <label>{T("admin_contenuto", la)}</label>
    <div id="editor"></div>

    <div class="video-bar">
      <button type="button" data-tooltip="{T('tip_upload_image', la)}" onclick="document.getElementById('file-image').click()">{T("admin_carica_immagine", la)}</button>
      <button type="button" data-tooltip="{T('tip_youtube', la)}" onclick="insertYoutube()">{T("admin_inserisci_youtube", la)}</button>
      <button type="button" data-tooltip="{T('tip_upload_video', la)}" onclick="document.getElementById('file-video').click()">{T("admin_carica_video", la)}</button>
      <button type="button" data-tooltip="{T('tip_table', la)}" onclick="insertTable()">{T("admin_inserisci_tabella", la)}</button>
      <input type="file" id="file-image" accept="image/png, image/jpeg, image/svg+xml, .svg, .png, .jpg, .jpeg" style="display:none" onchange="uploadImage()">
      <input type="file" id="file-video" accept="video/*" style="display:none" onchange="uploadVideo()">
      <span id="upload-status" class="hint"></span>
    </div>

    <div class="preview-bar">
      <button type="button" data-tooltip="{T('tip_preview', la)}" onclick="togglePreview()">{T("admin_mostra_anteprima", la)}</button>
    </div>
    <iframe id="preview-iframe" class="preview-frame" style="display:none"></iframe>
  </div>

  <!-- BARRA LATERALE: metadati, preview-box lettori, SEO, stato, azioni -->
  <aside class="editor-sidebar">

    <div class="sidebar-azioni" style="margin-top:0; padding-top:0; border-top:none">
      <button onclick="saveArticle()">{T("admin_salva_genera", la)}</button>
      {delete_button}
    </div>

    <h2>{T("admin_sezione_pubblicazione", la)}</h2>
    <label>{T("admin_stato", la)}</label>
    <select id="status">
      <option value="draft" {draft_selected}>{T("admin_bozza", la)}</option>
      <option value="published" {published_selected}>{T("admin_pubblicato", la)}</option>
    </select>

    <h2>{T("admin_sezione_metadati", la)}</h2>
    <label>Slug <span class="hint">(URL)</span></label>
    <input type="text" id="slug" value="{slug}" placeholder="auto">

    <label>{T("admin_tag", la)}</label>
    <input type="text" id="tags" value="{tags}" placeholder="AI, Python">

    <label>{T("admin_immagine_copertina", la)}</label>
    <input type="text" id="image" value="{image}">

    <div class="card-campo">
      <h2>{T("admin_anteprima_lettori", la)}</h2>
      <p class="hint" style="margin:0 0 0.3rem">{T("admin_anteprima_hint", la)}</p>
      <textarea id="reader_preview" rows="6" maxlength="900" oninput="updatePreviewCounter()">{preview}</textarea>
      <div class="d-flex justify-content-between align-items-center" style="margin-top:0.2rem">
        <span class="hint" id="preview-counter"></span>
        <button type="button" class="btn-suggerisci" onclick="generatePreview()">{T("admin_genera_anteprima", la)}</button>
      </div>
      <span id="preview-status" class="hint"></span>
    </div>

    <div class="card-campo">
      <h2>{T("admin_descrizione_seo", la)}</h2>
      <p class="hint" style="margin:0 0 0.3rem">{T("admin_descrizione_hint", la)}</p>
      <textarea id="description" rows="6" maxlength="320" oninput="updateDescriptionCounter()">{description}</textarea>
      <div class="d-flex justify-content-between align-items-center" style="margin-top:0.2rem">
        <span class="hint" id="description-counter"></span>
        <button type="button" class="btn-suggerisci" onclick="suggestDescription()">{T("admin_suggerisci_descrizione", la)}</button>
      </div>
      <span id="description-status" class="hint"></span>
    </div>

    <div class="card-campo">
      <h2>{T("admin_analisi_seo", la)}</h2>
      <p class="hint" style="margin:0 0 0.3rem">{T("admin_analisi_seo_hint", la)}</p>
      <button type="button" id="seo-analyze-btn" class="btn-suggerisci" onclick="analyzeSeo()">{T("admin_analizza_seo", la)}</button>
      <span id="seo-status" class="hint"></span>
      <div id="seo-results" style="display:none"></div>
    </div>

    <div class="translation-section">
      <h2>{T("admin_versione_inglese", la)}</h2>
      <label class="riga-flag">
        <input type="checkbox" id="translation_authorized" onchange="updateTranslationSection()">
        {T("admin_autorizza_traduzione", la)}
      </label>

      <div id="translation-block" style="display:none">
        <div class="translation-bar">
          <button type="button" onclick="translateArticle()">{T("admin_traduci_auto", la)}</button>
          <span id="translation-status" class="hint"></span>
        </div>

        <label>{T("admin_titolo", la)} (EN)</label>
        <input type="text" id="title_en">

        <label>{T("admin_descrizione_seo", la)} (EN)</label>
        <input type="text" id="description_en" maxlength="160">

        <label>{T("admin_anteprima_lettori", la)} (EN)</label>
        <textarea id="preview_en" rows="3" maxlength="900"></textarea>

        <label>{T("admin_contenuto", la)} (EN)</label>
        <div id="editor-en"></div>

        <div class="translation-bar" style="margin-top:1rem">
          <button type="button" onclick="previewEnglish()">{T("admin_anteprima_en", la)}</button>
          <span class="hint">{T("admin_anteprima_en_hint", la)}</span>
        </div>

        <label class="riga-flag" style="margin-top:1rem">
          <input type="checkbox" id="translation_confirmed">
          {T("admin_conferma_traduzione", la)}
        </label>
      </div>
    </div>

  </aside>
</div>

<script src="https://cdn.quilljs.com/1.3.7/quill.min.js"></script>
<script src="https://unpkg.com/quill-blot-formatter@1.0.5/dist/quill-blot-formatter.min.js"></script>
{_image_overlay_script(la)}
{_toolbar_tooltips_script(la)}
<script>
// Module to resize and align images (resizing in every direction,
// and the overlay follows the image even when it is centred).
if (window.QuillBlotFormatter) {{
  Quill.register('modules/blotFormatter', window.QuillBlotFormatter.default);
}}

const quill = new Quill('#editor', {{
  theme: 'snow',
  modules: {{
    blotFormatter: {{}},
    syntax: true,
    toolbar: [
    [{{ font: [] }}, {{ size: ['small', false, 'large', 'huge'] }}],
    [{{ header: [1, 2, 3, 4, false] }}],
    ['bold', 'italic', 'underline', 'strike'],
    [{{ color: [] }}, {{ background: [] }}],
    [{{ script: 'sub' }}, {{ script: 'super' }}],
    [{{ list: 'ordered' }}, {{ list: 'bullet' }}, {{ list: 'check' }}],
    [{{ indent: '-1' }}, {{ indent: '+1' }}],
    [{{ align: '' }}, {{ align: 'center' }}, {{ align: 'right' }}, {{ align: 'justify' }}],
    ['blockquote', 'code-block'],
    ['link', 'image', 'video'],
    ['clean']
  ]}}
}});
quill.root.innerHTML = {content_js};
attachImageOverlay(quill);
handlePastedImages(quill, 'upload-status');
applyToolbarTooltips();

// Character counter for the SEO description, warning about Google's limit.
function updateDescriptionCounter() {{
  var campo = document.getElementById('description');
  var contatore = document.getElementById('description-counter');
  var lunghezza = campo.value.length;
  var messaggio = lunghezza + ' {T("js_chars_unit", la)}';
  // Google shows about 120-160 characters: we flag when you leave the ideal range.
  if (lunghezza === 0) {{
    messaggio = "{T("js_desc_counter_empty", la)}";
  }} else if (lunghezza > 160) {{
    messaggio = lunghezza + ' {T("js_chars_unit", la)} - ' + "{T("js_chars_too_long_google", la)}";
  }} else if (lunghezza < 50) {{
    messaggio = lunghezza + " " + "{T("js_chars_unit", la)}" + " - " + "{T("js_chars_too_short_seo", la)}";
  }} else {{
    messaggio = lunghezza + ' {T("js_chars_unit", la)} - {T("js_chars_ideal_length", la)}';
  }}
  contatore.textContent = messaggio;
}}
updateDescriptionCounter();

// Asks the AI to propose an SEO description from the article content.
// The author sees the proposal in the textarea and can edit or rewrite it.
function suggestDescription() {{
  var pulsante = document.querySelector('.btn-suggerisci');
  var stato = document.getElementById('description-status');
  var contenuto = quill.root.innerHTML;
  var titolo = document.getElementById('title').value;

  if (quill.getText().trim() === '') {{
    stato.textContent = "{T("js_write_article_content_first", la)}";
    return;
  }}

  pulsante.disabled = true;
  stato.textContent = "{T("js_generating", la)}";

  fetch('/generate-description', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ content: contenuto, title: titolo }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    pulsante.disabled = false;
    if (res.ok === true) {{
      document.getElementById('description').value = res.description;
      updateDescriptionCounter();
      stato.textContent = "{T("js_suggestion_inserted", la)}";
    }} else {{
      stato.textContent = "{T("js_error_prefix", la)}" + res.error;
    }}
  }})
  .catch(function(e) {{
    pulsante.disabled = false;
    stato.textContent = "{T("js_net_error_generation", la)}";
  }});
}}

// Full SEO / AI-SEO analysis: asks the server (which asks the LLM) for
// keywords, backlink anchor texts, internal link suggestions, FAQ and
// advice, then renders everything in the sidebar panel.
// The results are rendered with textContent only: nothing coming from the
// model is ever inserted as HTML.
function analyzeSeo() {{
  var stato = document.getElementById('seo-status');
  var pannello = document.getElementById('seo-results');

  if (quill.getText().trim() === '') {{
    stato.textContent = "{T("js_write_article_content_first", la)}";
    return;
  }}

  // The analysis needs the slug to build the article URL for the backlink.
  var slugCorrente = document.getElementById('slug').value.trim();
  if (slugCorrente === '') {{
    slugCorrente = slugOriginale;
  }}
  if (slugCorrente === '') {{
    stato.textContent = "{T("js_seo_save_first", la)}";
    return;
  }}

  var pulsante = document.getElementById('seo-analyze-btn');
  pulsante.disabled = true;
  stato.textContent = "{T("js_seo_analyzing", la)}";
  pannello.style.display = 'none';
  pannello.textContent = '';

  fetch('/analyze-seo', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{
      content: quill.root.innerHTML,
      title: document.getElementById('title').value,
      slug: slugCorrente,
      tags: document.getElementById('tags').value,
      description: document.getElementById('description').value
    }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    pulsante.disabled = false;
    if (res.ok === true) {{
      stato.textContent = "{T("js_seo_done", la)}";
      window.lastSeoSources = res.sources || null;
      window.lastSeoArticleUrl = res.article_url;
      renderSeoResults(pannello, res.analysis, res.article_url);
      pannello.style.display = 'block';
    }} else {{
      stato.textContent = "{T("js_error_prefix", la)}" + res.error;
    }}
  }})
  .catch(function(e) {{
    pulsante.disabled = false;
    stato.textContent = "{T("js_net_error_generation", la)}";
  }});
}}

// A section title inside the results panel.
function seoHeading(testo) {{
  var h = document.createElement('div');
  h.className = 'seo-heading';
  h.textContent = testo;
  return h;
}}

// A row of text with a small "copy" button next to it.
function seoCopyRow(testo) {{
  var riga = document.createElement('div');
  riga.className = 'seo-row';
  var span = document.createElement('span');
  span.textContent = testo;
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'seo-copy';
  btn.textContent = "{T("seo_copy", la)}";
  btn.onclick = function() {{ copyToClipboard(testo, btn); }};
  riga.appendChild(span);
  riga.appendChild(btn);
  return riga;
}}

// Copies a text to the clipboard and gives feedback on the button.
function copyToClipboard(testo, bottone) {{
  var conferma = function() {{
    var originale = bottone.textContent;
    bottone.textContent = "{T("seo_copied", la)}";
    setTimeout(function() {{ bottone.textContent = originale; }}, 1200);
  }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(testo).then(conferma);
  }} else {{
    // Fallback for older browsers or non-HTTPS contexts.
    var area = document.createElement('textarea');
    area.value = testo;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
    conferma();
  }}
}}

// Renders the analysis into the panel. Every field is optional: the model
// may omit some keys, and the panel simply skips the missing sections.
// Where possible, each suggestion carries a button that applies it to the
// article directly, so accepting a change is a single click.
function renderSeoResults(pannello, analisi, urlArticolo) {{
  if (!analisi) {{ return; }}

  // Warns when the site URL is still the placeholder from the example
  // config: every generated URL would be fake.
  if (urlArticolo.indexOf('tuodominio.com') >= 0) {{
    var avviso = document.createElement('div');
    avviso.className = 'seo-text seo-warning';
    avviso.textContent = "{T("seo_baseurl_warning", la)}";
    pannello.appendChild(avviso);
  }}

  // The revision editor and the report need these later.
  window.lastSeoAnalysis = analisi;
  window.lastSeoSources = window.lastSeoSources || null;

  // The main path: a full revision of the article, with every proposed
  // addition highlighted and individually acceptable.
  var revBtn = document.createElement('button');
  revBtn.type = 'button';
  revBtn.className = 'seo-apply-all';
  revBtn.textContent = "{T("seo_make_revision", la)}";
  revBtn.onclick = function() {{ requestArticleRevision(); }};
  pannello.appendChild(revBtn);

  // The report: sources consulted and the rationale of every choice.
  var repBtn = document.createElement('button');
  repBtn.type = 'button';
  repBtn.className = 'seo-report-btn';
  repBtn.textContent = "{T("seo_open_report", la)}";
  repBtn.onclick = function() {{ openSeoReport(); }};
  pannello.appendChild(repBtn);

  // One click to accept the whole package of safe changes.
  var tuttoBtn = document.createElement('button');
  tuttoBtn.type = 'button';
  tuttoBtn.className = 'seo-apply-all';
  tuttoBtn.textContent = "{T("seo_apply_all", la)}";
  tuttoBtn.onclick = function() {{
    applySeoDescription(analisi);
    applySeoTags(analisi);
    appendFaqToArticle(analisi);
    appendRelatedToArticle(analisi);
    document.getElementById('seo-status').textContent = "{T("seo_applied", la)}";
  }};
  pannello.appendChild(tuttoBtn);

  // The exact URL to use as the backlink target on the external site.
  pannello.appendChild(seoHeading("{T("seo_backlink_target", la)}"));
  pannello.appendChild(seoCopyRow(urlArticolo));

  // Ready-made meta description, with its own apply button.
  if (analisi['suggested_description']) {{
    pannello.appendChild(seoHeading("{T("seo_suggested_description", la)}"));
    var rigaDesc = seoCopyRow(String(analisi['suggested_description']));
    rigaDesc.appendChild(seoActionButton("{T("seo_apply", la)}", function() {{
      applySeoDescription(analisi);
    }}));
    pannello.appendChild(rigaDesc);
  }}

  var liste = [
    ['primary_keywords', "{T("seo_primary_keywords", la)}"],
    ['secondary_keywords', "{T("seo_secondary_keywords", la)}"],
    ['trend_queries', "{T("seo_trend_queries", la)}"],
    ['anchor_texts', "{T("seo_anchor_texts", la)}"]
  ];
  for (var i = 0; i < liste.length; i++) {{
    var chiave = liste[i][0];
    var titolo = liste[i][1];
    var valori = analisi[chiave];
    if (valori && valori.length > 0) {{
      pannello.appendChild(seoHeading(titolo));
      for (var j = 0; j < valori.length; j++) {{
        pannello.appendChild(seoCopyRow(String(valori[j])));
      }}
    }}
  }}

  // Title variants: one click replaces the article title.
  var varianti = analisi['title_variants'];
  if (varianti && varianti.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_title_variants", la)}"));
    for (var v = 0; v < varianti.length; v++) {{
      (function(testoTitolo) {{
        var riga = seoCopyRow(testoTitolo);
        riga.appendChild(seoActionButton("{T("seo_use_title", la)}", function() {{
          document.getElementById('title').value = testoTitolo;
        }}));
        pannello.appendChild(riga);
      }})(String(varianti[v]));
    }}
  }}

  // Suggested tags: shown as text, with a button applying them.
  var tagValori = analisi['suggested_tags'];
  if (tagValori && tagValori.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_suggested_tags", la)}"));
    var rigaTag = seoCopyRow(tagValori.join(', '));
    rigaTag.appendChild(seoActionButton("{T("seo_apply_tags", la)}", function() {{
      applySeoTags(analisi);
    }}));
    pannello.appendChild(rigaTag);
  }}

  // The model's opinion on the current meta description.
  if (analisi['meta_description_review']) {{
    pannello.appendChild(seoHeading("{T("seo_meta_review", la)}"));
    var giudizio = document.createElement('div');
    giudizio.className = 'seo-text';
    giudizio.textContent = String(analisi['meta_description_review']);
    pannello.appendChild(giudizio);
  }}

  // Internal links: list plus a button appending a "Read more" section.
  var interni = analisi['internal_links'];
  if (interni && interni.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_internal_links", la)}"));
    for (var k = 0; k < interni.length; k++) {{
      var voce = interni[k];
      if (voce && voce.slug) {{
        var anchor = '';
        if (voce.anchor) {{ anchor = String(voce.anchor); }}
        pannello.appendChild(seoCopyRow(anchor + '  ->  /posts/' + String(voce.slug) + '.html'));
      }}
    }}
    pannello.appendChild(seoActionButton("{T("seo_add_related", la)}", function() {{
      appendRelatedToArticle(analisi);
    }}));
  }}

  // FAQ suggested for AI answer engines, with a button that inserts
  // them at the end of the article.
  var faq = analisi['faq'];
  if (faq && faq.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_faq", la)}"));
    for (var f = 0; f < faq.length; f++) {{
      if (faq[f] && faq[f].question) {{
        var blocco = document.createElement('div');
        blocco.className = 'seo-text';
        var domanda = document.createElement('strong');
        domanda.textContent = String(faq[f].question);
        blocco.appendChild(domanda);
        blocco.appendChild(document.createElement('br'));
        blocco.appendChild(document.createTextNode(String(faq[f].answer || '')));
        pannello.appendChild(blocco);
      }}
    }}
    pannello.appendChild(seoActionButton("{T("seo_add_faq", la)}", function() {{
      appendFaqToArticle(analisi);
    }}));
  }}

  // Concrete edits proposed to intercept the real search queries.
  var modifiche = analisi['content_changes'];
  if (modifiche && modifiche.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_content_changes", la)}"));
    for (var m = 0; m < modifiche.length; m++) {{
      var voceModifica = modifiche[m];
      if (voceModifica && voceModifica.change) {{
        var dove = '';
        if (voceModifica.where) {{ dove = String(voceModifica.where) + ': '; }}
        pannello.appendChild(seoCopyRow(dove + String(voceModifica.change)));
      }}
    }}
  }}

  // Concrete AI-SEO advice for this specific article.
  var consigli = analisi['ai_seo_tips'];
  if (consigli && consigli.length > 0) {{
    pannello.appendChild(seoHeading("{T("seo_ai_tips", la)}"));
    for (var c = 0; c < consigli.length; c++) {{
      var tip = document.createElement('div');
      tip.className = 'seo-text';
      tip.textContent = '\u2022 ' + String(consigli[c]);
      pannello.appendChild(tip);
    }}
  }}
}}

// A small action button used inside the results panel.
function seoActionButton(etichetta, azione) {{
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'seo-copy';
  btn.textContent = etichetta;
  btn.onclick = azione;
  return btn;
}}

// --- Applying the suggestions to the article ---------------------------

function applySeoDescription(analisi) {{
  if (analisi['suggested_description']) {{
    document.getElementById('description').value = String(analisi['suggested_description']).slice(0, 160);
  }}
}}

function applySeoTags(analisi) {{
  var tagValori = analisi['suggested_tags'];
  if (tagValori && tagValori.length > 0) {{
    document.getElementById('tags').value = tagValori.join(', ');
  }}
}}

// Builds the FAQ section HTML. Everything coming from the model is
// escaped: the strings become article content, so they must not be able
// to carry markup of their own.
function buildFaqHtml(faq) {{
  var pezzi = ['<h2>{T("seo_faq_heading", la)}</h2>'];
  for (var i = 0; i < faq.length; i++) {{
    if (faq[i] && faq[i].question) {{
      pezzi.push('<p><strong>' + escapeCellText(String(faq[i].question)) + '</strong><br>'
                 + escapeCellText(String(faq[i].answer || '')) + '</p>');
    }}
  }}
  return pezzi.join('');
}}

// Builds the "Read more" section HTML with the internal links.
// The slug is validated (letters, numbers, hyphens only) before being
// used inside a URL.
function buildRelatedHtml(interni) {{
  var pezzi = ['<h2>{T("seo_related_heading", la)}</h2><ul>'];
  var validi = 0;
  for (var i = 0; i < interni.length; i++) {{
    var voce = interni[i];
    if (voce && voce.slug && /^[a-z0-9-]+$/.test(String(voce.slug))) {{
      var anchor = String(voce.anchor || voce.slug);
      pezzi.push('<li><a href="/posts/' + String(voce.slug) + '.html">'
                 + escapeCellText(anchor) + '</a></li>');
      validi = validi + 1;
    }}
  }}
  pezzi.push('</ul>');
  if (validi === 0) {{ return ''; }}
  return pezzi.join('');
}}

function appendFaqToArticle(analisi) {{
  var faq = analisi['faq'];
  if (!faq || faq.length === 0) {{ return; }}
  var htmlFaq = buildFaqHtml(faq);
  quill.clipboard.dangerouslyPasteHTML(quill.getLength() - 1, htmlFaq);
}}

function appendRelatedToArticle(analisi) {{
  var interni = analisi['internal_links'];
  if (!interni || interni.length === 0) {{ return; }}
  var htmlLink = buildRelatedHtml(interni);
  if (htmlLink === '') {{ return; }}
  quill.clipboard.dangerouslyPasteHTML(quill.getLength() - 1, htmlLink);
}}

// --- Full article revision --------------------------------------------
// Asks the server for the anchored edits, then opens the review window:
// the article as it is, with each proposed addition shown in place,
// highlighted, and individually selectable.

function requestArticleRevision() {{
  var stato = document.getElementById('seo-status');
  stato.textContent = "{T("seo_revision_generating", la)}";
  fetch('/revise-article', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{
      content: quill.root.innerHTML,
      title: document.getElementById('title').value,
      tags: document.getElementById('tags').value,
      analysis: window.lastSeoAnalysis || {{}}
    }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      stato.textContent = '';
      openRevisionEditor(res.edits);
    }} else {{
      stato.textContent = "{T("js_error_prefix", la)}" + res.error;
    }}
  }})
  .catch(function(e) {{
    stato.textContent = "{T("js_net_error_generation", la)}";
  }});
}}

// Normalises a text for anchor matching: whitespace collapsed,
// case-insensitive.
function normalizeAnchorText(testo) {{
  return String(testo).replace(/\\s+/g, ' ').trim().toLowerCase();
}}

// The top-level blocks of the current article, as real DOM nodes.
function articleBlocks() {{
  var contenitore = document.createElement('div');
  contenitore.innerHTML = quill.root.innerHTML;
  var blocchi = [];
  for (var i = 0; i < contenitore.children.length; i++) {{
    blocchi.push(contenitore.children[i]);
  }}
  return blocchi;
}}

// Finds the index of the block containing the anchor text; -1 when the
// anchor is empty or cannot be found (the edit then goes at the end).
function findAnchorBlock(blocchi, anchor) {{
  var cercato = normalizeAnchorText(anchor);
  if (cercato === '') {{ return -1; }}
  for (var i = 0; i < blocchi.length; i++) {{
    if (normalizeAnchorText(blocchi[i].textContent).indexOf(cercato) >= 0) {{
      return i;
    }}
  }}
  return -1;
}}

// Builds and shows the revision window.
function openRevisionEditor(edits) {{
  var esistente = document.getElementById('revision-overlay');
  if (esistente) {{ return; }}

  var blocchi = articleBlocks();

  // For every block index, the edits to insert right after it; the
  // edits with no position found go into the tail list.
  var perBlocco = {{}};
  var inCoda = [];
  for (var e = 0; e < edits.length; e++) {{
    var indice = findAnchorBlock(blocchi, edits[e].anchor);
    edits[e].found = indice >= 0;
    if (indice >= 0) {{
      if (!perBlocco[indice]) {{ perBlocco[indice] = []; }}
      perBlocco[indice].push(e);
    }} else {{
      inCoda.push(e);
    }}
  }}

  var sfondo = document.createElement('div');
  sfondo.id = 'revision-overlay';
  var finestra = document.createElement('div');
  finestra.className = 'revision-window';

  var titolo = document.createElement('h3');
  titolo.textContent = "{T("seo_revision_title", la)}";
  finestra.appendChild(titolo);
  var intro = document.createElement('p');
  intro.className = 'revision-intro';
  intro.textContent = "{T("seo_revision_intro", la)}";
  finestra.appendChild(intro);

  var area = document.createElement('div');
  area.className = 'revision-area';
  for (var b = 0; b < blocchi.length; b++) {{
    area.appendChild(blocchi[b].cloneNode(true));
    if (perBlocco[b]) {{
      for (var k = 0; k < perBlocco[b].length; k++) {{
        area.appendChild(buildEditCard(edits, perBlocco[b][k], true));
      }}
    }}
  }}
  for (var t = 0; t < inCoda.length; t++) {{
    area.appendChild(buildEditCard(edits, inCoda[t], false));
  }}
  finestra.appendChild(area);

  var azioni = document.createElement('div');
  azioni.className = 'table-editor-actions';
  var applica = tableEditorButton("{T("seo_revision_apply", la)}", function() {{
    applyRevision(edits, blocchi, perBlocco, inCoda);
  }});
  applica.className = 'table-editor-save';
  var chiudi = tableEditorButton("{T("seo_revision_cancel", la)}", function() {{
    closeRevisionEditor();
  }});
  azioni.appendChild(applica);
  azioni.appendChild(chiudi);
  finestra.appendChild(azioni);

  sfondo.appendChild(finestra);
  sfondo.addEventListener('click', function(evento) {{
    if (evento.target === sfondo) {{ closeRevisionEditor(); }}
  }});
  document.body.appendChild(sfondo);
}}

// A proposed addition, rendered in place: green block, checkbox,
// reason, and the content itself (already sanitised by the server).
function buildEditCard(edits, indice, trovato) {{
  var voce = edits[indice];
  var carta = document.createElement('div');
  carta.className = 'revision-edit';

  var testata = document.createElement('label');
  testata.className = 'revision-edit-head';
  var spunta = document.createElement('input');
  spunta.type = 'checkbox';
  spunta.checked = true;
  spunta.onchange = function() {{
    voce.accepted = spunta.checked;
    if (spunta.checked) {{
      carta.classList.remove('revision-rejected');
    }} else {{
      carta.classList.add('revision-rejected');
    }}
  }};
  voce.accepted = true;
  testata.appendChild(spunta);
  var motivo = document.createElement('span');
  motivo.textContent = "{T("seo_revision_why", la)}" + ': ' + String(voce.reason || '');
  if (!trovato) {{
    motivo.textContent = motivo.textContent + ' ' + "{T("seo_revision_end_note", la)}";
  }}
  testata.appendChild(motivo);
  carta.appendChild(testata);

  var corpo = document.createElement('div');
  corpo.className = 'revision-edit-body';
  corpo.innerHTML = voce.new_html;
  carta.appendChild(corpo);
  return carta;
}}

// Rebuilds the article: the original blocks untouched, plus the
// accepted additions in their positions, then hands it to the editor.
function applyRevision(edits, blocchi, perBlocco, inCoda) {{
  var pezzi = [];
  for (var b = 0; b < blocchi.length; b++) {{
    pezzi.push(blocchi[b].outerHTML);
    if (perBlocco[b]) {{
      for (var k = 0; k < perBlocco[b].length; k++) {{
        var voce = edits[perBlocco[b][k]];
        if (voce.accepted) {{ pezzi.push(voce.new_html); }}
      }}
    }}
  }}
  for (var t = 0; t < inCoda.length; t++) {{
    var vc = edits[inCoda[t]];
    if (vc.accepted) {{ pezzi.push(vc.new_html); }}
  }}
  var nuovoHtml = pezzi.join('');
  quill.setContents([]);
  quill.clipboard.dangerouslyPasteHTML(0, nuovoHtml);
  closeRevisionEditor();
  document.getElementById('seo-status').textContent = "{T("seo_revision_applied", la)}";
}}

function closeRevisionEditor() {{
  var sfondo = document.getElementById('revision-overlay');
  if (sfondo) {{ document.body.removeChild(sfondo); }}
}}

// --- Analysis report ---------------------------------------------------
// Shows (and lets you download) a report that makes the analysis
// auditable: which sources were consulted, why every keyword was
// chosen, which real queries support it and where it is used.

// Builds the report as standalone HTML. Everything dynamic is escaped:
// the report must be safe to open as a file on its own.
function buildReportHtml(analisi, fonti, urlArticolo) {{
  var e = escapeCellText;
  var pezzi = [];
  pezzi.push('<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">');
  pezzi.push('<title>' + "{T("seo_report_title", la)}" + '</title>');
  pezzi.push('<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}}');
  pezzi.push('h1{{font-size:1.4rem}}h2{{font-size:1.05rem;margin-top:1.6rem;color:#0066cc}}');
  pezzi.push('table{{border-collapse:collapse;width:100%;font-size:0.88rem}}th,td{{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left;vertical-align:top}}');
  pezzi.push('th{{background:#f4f4f5}}ul{{margin:0.3rem 0}}</style></head><body>');
  pezzi.push('<h1>' + "{T("seo_report_title", la)}" + '</h1>');
  pezzi.push('<p><strong>URL:</strong> ' + e(urlArticolo || '') + '</p>');

  pezzi.push('<h2>' + "{T("seo_report_sources", la)}" + '</h2><ul>');
  if (fonti) {{
    pezzi.push('<li><strong>' + "{T("seo_report_service", la)}" + ':</strong> '
               + e(String(fonti.service || '')) + ' / ' + e(String(fonti.model || '')) + '</li>');
    pezzi.push('<li><strong>' + "{T("seo_report_date", la)}" + ':</strong> ' + e(String(fonti.analyzed_at || '')) + '</li>');
    pezzi.push('<li><strong>' + "{T("seo_report_seeds", la)}" + ':</strong> '
               + e((fonti.suggest_seeds || []).join(', ')) + '</li>');
    var query = fonti.suggest_queries || [];
    if (query.length > 0) {{
      pezzi.push('<li><strong>' + "{T("seo_report_collected", la)}" + ' (' + query.length + '):</strong> '
                 + e(query.join(' | ')) + '</li>');
    }} else {{
      pezzi.push('<li><strong>' + "{T("seo_report_collected", la)}" + ':</strong> '
                 + "{T("seo_report_none", la)}" + '</li>');
    }}
  }}
  pezzi.push('</ul>');

  pezzi.push('<h2>' + "{T("seo_report_keywords", la)}" + '</h2>');
  var voci = analisi['keyword_report'];
  if (voci && voci.length > 0) {{
    pezzi.push('<table><tr><th>' + "{T("seo_report_col_keyword", la)}" + '</th><th>'
               + "{T("seo_report_col_type", la)}" + '</th><th>'
               + "{T("seo_report_col_reason", la)}" + '</th><th>'
               + "{T("seo_report_col_queries", la)}" + '</th><th>'
               + "{T("seo_report_col_placement", la)}" + '</th></tr>');
    for (var i = 0; i < voci.length; i++) {{
      var v = voci[i];
      if (!v || !v.keyword) {{ continue; }}
      var supporto = '';
      if (v.queries && v.queries.length > 0) {{ supporto = v.queries.join(' | '); }}
      pezzi.push('<tr><td><strong>' + e(String(v.keyword)) + '</strong></td><td>'
                 + e(String(v.type || '')) + '</td><td>'
                 + e(String(v.reason || '')) + '</td><td>'
                 + e(supporto) + '</td><td>'
                 + e(String(v.placement || '')) + '</td></tr>');
    }}
    pezzi.push('</table>');
  }} else {{
    pezzi.push('<p>' + "{T("seo_report_missing", la)}" + '</p>');
  }}

  var modifiche = analisi['content_changes'];
  if (modifiche && modifiche.length > 0) {{
    pezzi.push('<h2>' + "{T("seo_report_changes", la)}" + '</h2><ul>');
    for (var m = 0; m < modifiche.length; m++) {{
      var mod = modifiche[m];
      if (mod && mod.change) {{
        pezzi.push('<li><strong>' + e(String(mod.where || '')) + ':</strong> '
                   + e(String(mod.change)) + '</li>');
      }}
    }}
    pezzi.push('</ul>');
  }}
  pezzi.push('</body></html>');
  return pezzi.join('');
}}

function openSeoReport() {{
  var esistente = document.getElementById('seo-report-overlay');
  if (esistente) {{ return; }}
  var analisi = window.lastSeoAnalysis || {{}};
  var fonti = window.lastSeoSources || null;
  var urlArticolo = window.lastSeoArticleUrl || '';

  var sfondo = document.createElement('div');
  sfondo.id = 'seo-report-overlay';
  var finestra = document.createElement('div');
  finestra.className = 'revision-window';

  var area = document.createElement('div');
  area.className = 'revision-area';
  // The report body is built by us with escaped content: showing it
  // through innerHTML is safe here.
  var reportHtml = buildReportHtml(analisi, fonti, urlArticolo);
  var inizioBody = reportHtml.indexOf('<body>') + '<body>'.length;
  var fineBody = reportHtml.lastIndexOf('</body>');
  area.innerHTML = reportHtml.slice(inizioBody, fineBody);
  finestra.appendChild(area);

  var azioni = document.createElement('div');
  azioni.className = 'table-editor-actions';
  var scarica = tableEditorButton("{T("seo_report_download", la)}", function() {{
    downloadSeoReport(reportHtml);
  }});
  scarica.className = 'table-editor-save';
  var chiudi = tableEditorButton("{T("seo_report_close", la)}", function() {{
    document.body.removeChild(sfondo);
  }});
  azioni.appendChild(scarica);
  azioni.appendChild(chiudi);
  finestra.appendChild(azioni);

  sfondo.appendChild(finestra);
  sfondo.addEventListener('click', function(evento) {{
    if (evento.target === sfondo) {{ document.body.removeChild(sfondo); }}
  }});
  document.body.appendChild(sfondo);
}}

function downloadSeoReport(reportHtml) {{
  var slug = document.getElementById('slug').value.trim();
  if (slug === '') {{ slug = 'articolo'; }}
  var blob = new Blob([reportHtml], {{ type: 'text/html;charset=utf-8' }});
  var collegamento = document.createElement('a');
  collegamento.href = URL.createObjectURL(blob);
  collegamento.download = 'report-seo-' + slug + '.html';
  document.body.appendChild(collegamento);
  collegamento.click();
  document.body.removeChild(collegamento);
  URL.revokeObjectURL(collegamento.href);
}}

// Character counter for the preview meant for readers.
function updatePreviewCounter() {{
  var campo = document.getElementById('reader_preview');
  var contatore = document.getElementById('preview-counter');
  var lunghezza = campo.value.length;
  if (lunghezza === 0) {{
    contatore.textContent = "{T("js_preview_counter_empty", la)}";
  }} else {{
    contatore.textContent = lunghezza + ' {T("js_chars_unit", la)}';
  }}
}}
updatePreviewCounter();

// Asks the AI to write a narrative preview for readers (longer and more
// descriptive than the SEO meta description). The author can then edit it.
function generatePreview() {{
  var pulsante = event.target;
  var stato = document.getElementById('preview-status');
  var contenuto = quill.root.innerHTML;
  var titolo = document.getElementById('title').value;

  if (quill.getText().trim() === '') {{
    stato.textContent = "{T("js_write_article_content_first", la)}";
    return;
  }}

  pulsante.disabled = true;
  stato.textContent = "{T("js_generating", la)}";

  fetch('/generate-preview', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ content: contenuto, title: titolo }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    pulsante.disabled = false;
    if (res.ok === true) {{
      document.getElementById('reader_preview').value = res.preview;
      updatePreviewCounter();
      stato.textContent = "{T("js_suggestion_inserted", la)}";
    }} else {{
      stato.textContent = "{T("js_error_prefix", la)}" + res.error;
    }}
  }})
  .catch(function(e) {{
    pulsante.disabled = false;
    stato.textContent = "{T("js_net_error_generation", la)}";
  }});
}}
// We create a second Quill editor for the English translation, so the author
// can review and correct it before confirming it.
var quillEn = new Quill('#editor-en', {{
  theme: 'snow',
  modules: {{
    blotFormatter: {{}},
    syntax: true,
    toolbar: [
      [{{ font: [] }}, {{ size: ['small', false, 'large', 'huge'] }}],
      [{{ header: [1, 2, 3, 4, false] }}],
      ['bold', 'italic', 'underline', 'strike'],
      [{{ color: [] }}, {{ background: [] }}],
      [{{ script: 'sub' }}, {{ script: 'super' }}],
      [{{ list: 'ordered' }}, {{ list: 'bullet' }}, {{ list: 'check' }}],
      [{{ indent: '-1' }}, {{ indent: '+1' }}],
      [{{ align: '' }}, {{ align: 'center' }}, {{ align: 'right' }}, {{ align: 'justify' }}],
      ['blockquote', 'code-block'],
      ['link', 'image', 'video'],
      ['clean']
    ]
  }}
}});

attachImageOverlay(quillEn);
handlePastedImages(quillEn, null);
applyToolbarTooltips();

// We load the saved English values (if any).
var titoloEnIniziale = {title_en_js};
var descrizioneEnIniziale = {description_en_js};
var anteprimaEnIniziale = {preview_en_js};
var contenutoEnIniziale = {content_en_js};
document.getElementById('title_en').value = titoloEnIniziale;
document.getElementById('description_en').value = descrizioneEnIniziale;
document.getElementById('preview_en').value = anteprimaEnIniziale;
quillEn.root.innerHTML = contenutoEnIniziale;
document.getElementById('translation_authorized').checked = {autorizzata_js};
document.getElementById('translation_confirmed').checked = {confirmed_js};

// Shows or hides the translation block based on the authorisation flag.
function updateTranslationSection() {{
  var autorizzata = document.getElementById('translation_authorized').checked;
  var blocco = document.getElementById('translation-block');
  if (autorizzata) {{
    blocco.style.display = 'block';
  }} else {{
    blocco.style.display = 'none';
  }}
}}
updateTranslationSection();

// Asks the server to translate title, description and content into English.
// The calls happen in the backend, where the API keys are safe.
function translateArticle() {{
  var stato = document.getElementById('translation-status');
  stato.textContent = "{T("js_translating", la)}";

  // We take the Italian texts to translate.
  var titoloIt = document.getElementById('title').value;
  var descrizioneIt = document.getElementById('description').value;
  var contenutoIt = quill.root.innerHTML;

  // We translate the three pieces one after the other.
  translatePiece(titoloIt, function(titoloTradotto) {{
    document.getElementById('title_en').value = titoloTradotto;
    translatePiece(descrizioneIt, function(descrizioneTradotta) {{
      document.getElementById('description_en').value = descrizioneTradotta;
      translatePiece(contenutoIt, function(contenutoTradotto) {{
        quillEn.root.innerHTML = contenutoTradotto;
        stato.textContent = "{T("js_translated_review", la)}";
      }});
    }});
  }});
}}

// Translates a single piece of text by calling the backend.
function translatePiece(testo, quandoFinito) {{
  if (testo === null || testo.trim() === '') {{
    quandoFinito('');
    return;
  }}
  fetch('/translate', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ text: testo }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(res) {{
    if (res.ok === true) {{
      quandoFinito(res.text);
    }} else {{
      var stato = document.getElementById('translation-status');
      stato.textContent = "{T("js_error_prefix", la)}" + res.error + "{T("js_check_api_key", la)}";
      quandoFinito('');
    }}
  }})
  .catch(function(errore) {{
    var stato = document.getElementById('translation-status');
    stato.textContent = "{T("js_net_error_translation", la)}";
    quandoFinito('');
  }});
}}
// When you paste from Word, the HTML contains <table> with many proprietary
// styles. Word also uses tables purely to lay out a page: a block of text and
// an image side by side is, on the clipboard, a <table>. So a pasted <table>
// means one of two very different things, and we must tell them apart:
//
//   - a LAYOUT table (Word's page furniture): we unwrap it and let its
//     contents through as ordinary text and images, so they stay editable;
//   - a DATA table (a real grid the author wants): we rebuild it clean,
//     discarding Word's messy styles but keeping rows, cells and images.
//
// Previously EVERY pasted table became a single atomic block: that is why a
// mixed text+image selection from Word arrived as one non-editable object.
// Now only real data tables become a block (a Quill limitation: editing
// table cells in place would need a dedicated table module); to change a
// data table, delete it and paste it again, or edit the source document.
quill.clipboard.addMatcher("TABLE", function(nodo, delta) {{
  // A layout table is not a table at all, semantically. We return the delta
  // Quill already built from its children: text stays text, images stay
  // images, and everything remains editable.
  if (isLayoutTable(nodo)) {{
    return delta;
  }}
  // A real data table: rebuild it clean and keep it as a single block.
  var Delta = Quill.import("delta");
  var htmlTabella = buildCleanTable(nodo);
  return new Delta().insert({{ rawHTML: htmlTabella }});
}});

// Finds the table a row or cell really belongs to. Word nests tables inside
// tables, and querySelectorAll reaches into the nested ones too: without this
// check a nested data table would be flattened into its wrapper.
function closestTable(nodo) {{
  var corrente = nodo.parentNode;
  while (corrente) {{
    if (corrente.tagName === "TABLE") {{
      return corrente;
    }}
    corrente = corrente.parentNode;
  }}
  return null;
}}

// The <tr> elements belonging to this table only, skipping nested tables.
function ownRows(tabella) {{
  var tutte = tabella.querySelectorAll("tr");
  var proprie = [];
  for (var i = 0; i < tutte.length; i++) {{
    if (closestTable(tutte[i]) === tabella) {{
      proprie.push(tutte[i]);
    }}
  }}
  return proprie;
}}

// The cells belonging to this table only, skipping nested tables.
function ownCells(riga, tabella) {{
  var tutte = riga.querySelectorAll("td, th");
  var proprie = [];
  for (var i = 0; i < tutte.length; i++) {{
    if (closestTable(tutte[i]) === tabella) {{
      proprie.push(tutte[i]);
    }}
  }}
  return proprie;
}}

// Tells whether a pasted table is Word's page furniture rather than data.
// The rules are deliberately simple and conservative: when in doubt we treat
// it as a data table, because unwrapping a real grid loses more than keeping
// a layout wrapper would.
function isLayoutTable(tabella) {{
  // A table wrapping another table is a layout wrapper: the inner one is
  // the real grid and will be matched on its own.
  if (tabella.querySelector("table")) {{
    return true;
  }}
  var righe = ownRows(tabella);
  // A single row is a strip of blocks placed side by side, not a grid:
  // this is the classic Word "text next to image" layout.
  if (righe.length <= 1) {{
    return true;
  }}
  // A single column is a stack of blocks, not a grid.
  var maxCelle = 0;
  for (var i = 0; i < righe.length; i++) {{
    var quante = ownCells(righe[i], tabella).length;
    if (quante > maxCelle) {{
      maxCelle = quante;
    }}
  }}
  if (maxCelle <= 1) {{
    return true;
  }}
  return false;
}}

// Turns a Word <table> node into simple, clean HTML, keeping the images.
function buildCleanTable(tabella) {{
  var risultato = '<table class="article-table"><tbody>';
  var righe = ownRows(tabella);
  for (var i = 0; i < righe.length; i++) {{
    risultato = risultato + "<tr>";
    var celle = ownCells(righe[i], tabella);
    for (var j = 0; j < celle.length; j++) {{
      var contenuto = buildCleanCell(celle[j]);
      // We treat the first row as the header.
      if (i === 0) {{
        risultato = risultato + "<th>" + contenuto + "</th>";
      }} else {{
        risultato = risultato + "<td>" + contenuto + "</td>";
      }}
    }}
    risultato = risultato + "</tr>";
  }}
  risultato = risultato + "</tbody></table>";
  return risultato;
}}

// Keeps the text AND the images of a cell, dropping Word's styling.
// The old version used innerText, which silently deleted every image
// inside a table cell.
function buildCleanCell(cella) {{
  var pezzi = [];
  raccogliContenutoCella(cella, pezzi);
  return pezzi.join("").trim();
}}

function raccogliContenutoCella(nodo, pezzi) {{
  for (var i = 0; i < nodo.childNodes.length; i++) {{
    var figlio = nodo.childNodes[i];
    if (figlio.nodeType === 3) {{
      pezzi.push(escapeCellText(figlio.textContent.replace(/\\s+/g, " ")));
    }} else if (figlio.nodeType === 1) {{
      if (figlio.tagName === "IMG") {{
        // Only the src survives: Word's width/height/styles are dropped.
        var indirizzo = figlio.getAttribute("src");
        if (indirizzo) {{
          pezzi.push('<img src="' + escapeCellText(indirizzo) + '">');
        }}
      }} else if (figlio.tagName === "BR") {{
        pezzi.push(" ");
      }} else {{
        raccogliContenutoCella(figlio, pezzi);
      }}
    }}
  }}
}}

// The cell content is rebuilt as an HTML string, so text coming from the
// document must not be able to inject tags of its own.
function escapeCellText(testo) {{
  return testo
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}}

// Lets Quill insert raw HTML (our table) into the content. It must be a
// BlockEmbed: Quill actively manages the children of ordinary blocks and,
// on the first edit, its normalisation would strip the <table> markup out
// (and the save would silently lose the table). An embed is opaque to that
// process, at the cost of not being editable cell by cell inside Quill.
// True in-editor table editing would require a dedicated table module.
var BlockEmbed = Quill.import("blots/block/embed");
function RawHtmlBlot() {{}}
RawHtmlBlot = class extends BlockEmbed {{
  static create(valore) {{
    var nodo = super.create();
    nodo.innerHTML = valore;
    // The browser must not let the user type inside the embed: Quill's
    // document model would not see those changes and could revert them.
    // Editing goes through the small table editor instead (click on it).
    nodo.setAttribute("contenteditable", "false");
    return nodo;
  }}
  static value(nodo) {{
    return nodo.innerHTML;
  }}
}};
RawHtmlBlot.blotName = "rawHTML";
RawHtmlBlot.tagName = "div";
RawHtmlBlot.className = "raw-html-block";
Quill.register(RawHtmlBlot);

// --- Small table editor -----------------------------------------------
// Quill cannot edit the cells of an embedded table in place (its document
// model does not manage the embed's inner DOM). So we offer the next best
// thing: clicking a table opens a small editor where every cell can be
// changed and rows/columns added or removed. Saving rewrites the embed's
// HTML; the article save reads quill.root.innerHTML, so the change is
// picked up with no further work.

// A click anywhere on an embedded table opens the editor for that table.
quill.root.addEventListener("click", function(evento) {{
  var blocco = evento.target.closest(".raw-html-block");
  if (!blocco) {{ return; }}
  var tabella = blocco.querySelector("table");
  if (!tabella) {{ return; }}
  openTableEditor(blocco, tabella);
}});

// Builds and shows the modal with an editable copy of the table.
function openTableEditor(blocco, tabellaOriginale) {{
  // Only one editor at a time.
  var esistente = document.getElementById("table-editor-overlay");
  if (esistente) {{ return; }}

  var sfondo = document.createElement("div");
  sfondo.id = "table-editor-overlay";

  var finestra = document.createElement("div");
  finestra.className = "table-editor-window";

  var titolo = document.createElement("h3");
  titolo.textContent = "{T("admin_table_editor_title", la)}";
  finestra.appendChild(titolo);

  // An editable copy: the original stays untouched until "save".
  var copia = tabellaOriginale.cloneNode(true);
  var celle = copia.querySelectorAll("td, th");
  for (var i = 0; i < celle.length; i++) {{
    celle[i].setAttribute("contenteditable", "true");
  }}
  var areaTabella = document.createElement("div");
  areaTabella.className = "table-editor-area";
  areaTabella.appendChild(copia);
  finestra.appendChild(areaTabella);

  // Row and column controls.
  var barra = document.createElement("div");
  barra.className = "table-editor-bar";
  barra.appendChild(tableEditorButton("{T("admin_table_add_row", la)}", function() {{ tableAddRow(copia); }}));
  barra.appendChild(tableEditorButton("{T("admin_table_del_row", la)}", function() {{ tableRemoveRow(copia); }}));
  barra.appendChild(tableEditorButton("{T("admin_table_add_col", la)}", function() {{ tableAddColumn(copia); }}));
  barra.appendChild(tableEditorButton("{T("admin_table_del_col", la)}", function() {{ tableRemoveColumn(copia); }}));
  finestra.appendChild(barra);

  // Save and cancel.
  var azioni = document.createElement("div");
  azioni.className = "table-editor-actions";
  var salva = tableEditorButton("{T("admin_table_save", la)}", function() {{
    blocco.innerHTML = serializeEditedTable(copia);
    closeTableEditor();
    // Tells Quill the document changed, so autosave and counters react.
    quill.update();
  }});
  salva.className = "table-editor-save";
  var annulla = tableEditorButton("{T("admin_table_cancel", la)}", function() {{
    closeTableEditor();
  }});
  azioni.appendChild(salva);
  azioni.appendChild(annulla);
  finestra.appendChild(azioni);

  sfondo.appendChild(finestra);
  // A click on the dark background closes without saving.
  sfondo.addEventListener("click", function(evento) {{
    if (evento.target === sfondo) {{
      closeTableEditor();
    }}
  }});
  document.body.appendChild(sfondo);
}}

function closeTableEditor() {{
  var sfondo = document.getElementById("table-editor-overlay");
  if (sfondo) {{
    document.body.removeChild(sfondo);
  }}
}}

function tableEditorButton(etichetta, azione) {{
  var btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = etichetta;
  btn.onclick = azione;
  return btn;
}}

// The rows of the edited table (they all belong to it: no nesting here).
function editedTableRows(tabella) {{
  return tabella.querySelectorAll("tr");
}}

function tableAddRow(tabella) {{
  var righe = editedTableRows(tabella);
  if (righe.length === 0) {{ return; }}
  var ultima = righe[righe.length - 1];
  var colonne = ultima.querySelectorAll("td, th").length;
  var riga = document.createElement("tr");
  for (var i = 0; i < colonne; i++) {{
    var cella = document.createElement("td");
    cella.setAttribute("contenteditable", "true");
    riga.appendChild(cella);
  }}
  ultima.parentNode.appendChild(riga);
}}

function tableRemoveRow(tabella) {{
  var righe = editedTableRows(tabella);
  // The header row always stays.
  if (righe.length <= 1) {{ return; }}
  var ultima = righe[righe.length - 1];
  ultima.parentNode.removeChild(ultima);
}}

function tableAddColumn(tabella) {{
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {{
    var cella;
    if (i === 0) {{
      cella = document.createElement("th");
    }} else {{
      cella = document.createElement("td");
    }}
    cella.setAttribute("contenteditable", "true");
    righe[i].appendChild(cella);
  }}
}}

function tableRemoveColumn(tabella) {{
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {{
    var celle = righe[i].querySelectorAll("td, th");
    // At least one column always stays.
    if (celle.length <= 1) {{ return; }}
  }}
  for (var j = 0; j < righe.length; j++) {{
    var proprie = righe[j].querySelectorAll("td, th");
    righe[j].removeChild(proprie[proprie.length - 1]);
  }}
}}

// Rebuilds clean table HTML from the edited copy, with the same rules
// used when pasting: text and images survive, styling does not.
function serializeEditedTable(tabella) {{
  var risultato = '<table class="article-table"><tbody>';
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {{
    risultato = risultato + "<tr>";
    var celle = righe[i].querySelectorAll("td, th");
    for (var j = 0; j < celle.length; j++) {{
      var contenuto = buildCleanCell(celle[j]);
      if (i === 0) {{
        risultato = risultato + "<th>" + contenuto + "</th>";
      }} else {{
        risultato = risultato + "<td>" + contenuto + "</td>";
      }}
    }}
    risultato = risultato + "</tr>";
  }}
  risultato = risultato + "</tbody></table>";
  return risultato;
}}

// Inserts an empty table created by the user (rows x columns of their choice).
function insertTable() {{
  var righe = prompt("Quante righe? (intestazione inclusa)", "3");
  if (righe === null) {{ return; }}
  var colonne = prompt("Quante colonne?", "3");
  if (colonne === null) {{ return; }}
  var numRighe = parseInt(righe, 10);
  var numColonne = parseInt(colonne, 10);
  if (isNaN(numRighe) || isNaN(numColonne)) {{ return; }}
  if (numRighe < 1 || numColonne < 1) {{ return; }}

  var html = '<table class="article-table"><tbody>';
  for (var i = 0; i < numRighe; i++) {{
    html = html + "<tr>";
    for (var j = 0; j < numColonne; j++) {{
      if (i === 0) {{
        html = html + "<th>Intestazione</th>";
      }} else {{
        html = html + "<td>testo</td>";
      }}
    }}
    html = html + "</tr>";
  }}
  html = html + "</tbody></table>";

  // We insert the table directly, without going through the clipboard
  // matcher: that matcher exists to interpret Word's HTML, where a table
  // may really be page layout. A table the author asked for is always a
  // real table, even with a single row.
  var posizione = quill.getSelection(true);
  quill.insertEmbed(posizione.index, "rawHTML", html, Quill.sources.USER);
}}

// Shows or hides the article preview.
// The preview is an iframe using the same CSS as the public site,
// so you see exactly how it will look once published.
function togglePreview() {{
  var frame = document.getElementById("preview-iframe");
  if (frame.style.display === "none") {{
    frame.style.display = "block";
    updatePreview();
  }} else {{
    frame.style.display = "none";
  }}
}}

// Updates the preview content with what is currently in the editor.
function updatePreview() {{
  var frame = document.getElementById("preview-iframe");
  if (frame.style.display === "none") {{
    return;
  }}
  var titolo = document.getElementById("title").value;
  var contenuto = quill.root.innerHTML;
  var pagina = '<!DOCTYPE html><html><head>';
  pagina = pagina + '<meta charset="utf-8">';
  pagina = pagina + '<link rel="stylesheet" href="/style.css">';
  pagina = pagina + '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">';
  pagina = pagina + '</head><body>';
  pagina = pagina + '<article id="content" class="post">';
  pagina = pagina + '<h1>' + titolo + '</h1>';
  pagina = pagina + contenuto;
  pagina = pagina + '</article>';
  // We load highlight.js inside the preview to colour the code here too.
  pagina = pagina + '<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"><\\/script>';
  pagina = pagina + '<script>document.querySelectorAll("pre.ql-syntax").forEach(function(b){{hljs.highlightElement(b);}});<\\/script>';
  pagina = pagina + '</body></html>';
  var documento = frame.contentDocument;
  documento.open();
  documento.write(pagina);
  documento.close();
}}

// Every time you type in the editor, update the preview (if it is open).
quill.on("text-change", function() {{
  updatePreview();
}});

// Extracts the video identifier from a YouTube link.
// It works with the youtube.com/watch?v=ID and youtu.be/ID formats.
function extractYoutubeId(url) {{
  var idVideo = "";
  if (url.indexOf("youtu.be/") !== -1) {{
    var parti = url.split("youtu.be/");
    idVideo = parti[1];
  }} else if (url.indexOf("watch?v=") !== -1) {{
    var parti = url.split("watch?v=");
    idVideo = parti[1];
  }} else if (url.indexOf("/embed/") !== -1) {{
    var parti = url.split("/embed/");
    idVideo = parti[1];
  }}
  // Removes any extra parameters after the ID (e.g. &t=10s).
  var posizioneEsclusa = idVideo.indexOf("&");
  if (posizioneEsclusa !== -1) {{
    idVideo = idVideo.substring(0, posizioneEsclusa);
  }}
  var posizionePunto = idVideo.indexOf("?");
  if (posizionePunto !== -1) {{
    idVideo = idVideo.substring(0, posizionePunto);
  }}
  return idVideo.trim();
}}

// Asks for the link and inserts the YouTube video into the editor.
function insertYoutube() {{
  var url = prompt("{T("js_prompt_youtube_link", la)}");
  if (url === null) {{
    return;
  }}
  if (url === "") {{
    return;
  }}
  var idVideo = extractYoutubeId(url);
  if (idVideo === "") {{
    alert("{T("js_youtube_not_recognized", la)}");
    return;
  }}
  var html = '<div class="video-youtube">';
  html = html + '<iframe src="https://www.youtube.com/embed/' + idVideo + '"';
  html = html + ' allowfullscreen></iframe></div><p><br></p>';
  // Inserts the HTML at the current cursor position.
  var posizione = quill.getSelection(true);
  quill.clipboard.dangerouslyPasteHTML(posizione.index, html);
}}

// Uploads a video file to the server and inserts it into the editor.
function uploadVideo() {{
  var campoFile = document.getElementById("file-video");
  var stato = document.getElementById("upload-status");
  if (campoFile.files.length === 0) {{
    return;
  }}
  var file = campoFile.files[0];
  var datiForm = new FormData();
  datiForm.append("video", file);

  stato.textContent = "{T('js_uploading', la)}";

  fetch("/upload", {{
    method: "POST",
    body: datiForm
  }})
  .then(function(risposta) {{
    return risposta.json();
  }})
  .then(function(risultato) {{
    if (risultato.ok === true) {{
      var html = '<video controls src="' + risultato.url + '"></video><p><br></p>';
      var posizione = quill.getSelection(true);
      quill.clipboard.dangerouslyPasteHTML(posizione.index, html);
      stato.textContent = "{T('js_video_uploaded', la)}";
    }} else {{
      stato.textContent = "{T('js_error_prefix', la)}" + risultato.error;
    }}
  }})
  .catch(function(errore) {{
    stato.textContent = "{T('js_upload_error', la)}";
  }});
}}

// Uploads an image (PNG, JPEG or SVG) to the server and inserts it into the editor.
function uploadImage() {{
  var campoFile = document.getElementById("file-image");
  var stato = document.getElementById("upload-status");
  if (campoFile.files.length === 0) {{
    return;
  }}
  var file = campoFile.files[0];
  var datiForm = new FormData();
  datiForm.append("video", file);

  stato.textContent = "{T('js_uploading_image', la)}";

  fetch("/upload", {{
    method: "POST",
    body: datiForm
  }})
  .then(function(risposta) {{
    return risposta.json();
  }})
  .then(function(risultato) {{
    if (risultato.ok === true) {{
      var html = '<img src="' + risultato.url + '"><p><br></p>';
      var posizione = quill.getSelection(true);
      quill.clipboard.dangerouslyPasteHTML(posizione.index, html);
      stato.textContent = "{T('js_image_uploaded', la)}";
    }} else {{
      stato.textContent = "{T('js_error_prefix', la)}" + risultato.error;
    }}
  }})
  .catch(function(errore) {{
    stato.textContent = "{T('js_upload_error', la)}";
  }});
}}

// The slug the article is currently saved with on disk. It is
// updated after every save (including the one from the EN preview),
// so that a later slug change does not leave orphan files.
var slugOriginale = {json.dumps(slug)};

// Collects every form field into a single article object.
// Used both by the save and by the English preview.
function articleData() {{
  return {{
    title: document.getElementById('title').value,
    slug: document.getElementById('slug').value,
    description: document.getElementById('description').value,
    preview: document.getElementById('reader_preview').value,
    content: quill.root.innerHTML,
    tags: document.getElementById('tags').value,
    image: document.getElementById('image').value,
    status: document.getElementById('status').value,
    original_slug: slugOriginale,
    // Fields of the English version.
    title_en: document.getElementById('title_en').value,
    description_en: document.getElementById('description_en').value,
    preview_en: document.getElementById('preview_en').value,
    content_en: quillEn.root.innerHTML,
    translation_authorized: document.getElementById('translation_authorized').checked,
    translation_confirmed: document.getElementById('translation_confirmed').checked
  }};
}}

function saveArticle() {{
  fetch('/save', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(articleData())
  }}).then(r => r.json()).then(res => {{
    if (res.ok) window.location.href = '/admin';
    else alert("{T("js_error_prefix", la)}" + res.error);
  }});
}}

// Preview of the English page: it first SAVES the article (otherwise
// you would see the version on disk, not the one you are writing), then
// it opens /preview with lingua=en in a new tab. You stay in the editor.
function previewEnglish() {{
  fetch('/save', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(articleData())
  }}).then(r => r.json()).then(res => {{
    if (res.ok) {{
      slugOriginale = res.slug;
      window.open('/preview?slug=' + encodeURIComponent(res.slug) + '&language=en', '_blank');
    }} else {{
      alert("{T("js_error_prefix", la)}" + res.error);
    }}
  }});
}}

function deleteItem() {{
  if (!confirm("{T("js_delete_confirm", la)}")) return;
  fetch('/delete', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ slug: {json.dumps(slug)} }})
  }}).then(r => r.json()).then(res => {{
    if (res.ok) window.location.href = '/admin';
  }});
}}
</script>
</div>
<script src="{BOOTSTRAP_JS}"></script>
</body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    """Handle the editor requests and serve the static preview."""

    def _send(self, content, tipo="text/html"):
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _read_cookie_token(self):
        """Read the session token from the cookie, if present."""
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header == "":
            return None
        # Cookies are separated by semicolons: name=value; name2=value2
        pieces = cookie_header.split(";")
        for piece in pieces:
            piece = piece.strip()
            if piece.startswith("sessione="):
                return piece[len("sessione="):]
        return None

    def _user_is_authenticated(self):
        """Tell whether the current request comes from a logged-in user."""
        token = self._read_cookie_token()
        return session_is_valid(token)

    def _redirect(self, destination, cookie=None):
        """Redirect the browser to another address, optionally with a cookie."""
        self.send_response(303)
        self.send_header("Location", destination)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # --- Public pages (no authentication) ---
        if route == "/" or route == "/index.html":
            # The public homepage of the blog (a generated static file).
            self._serve_static("/index.html")
            return
        if route.startswith("/posts/") or route.startswith("/pagine/") or route.startswith("/en/") or route.startswith("/it/") or route.startswith("/tag/") or route.startswith("/pagina/") or route in (
                "/style.css", "/rss.xml", "/search-index.json", "/llms.txt",
                "/sitemap.xml", "/404.html", "/favicon.svg",
                "/archivio.html", "/archive.html", "/robots.txt",
                "/training-rights.html"):
            self._serve_static(route)
            return
        if route.startswith("/.well-known/"):
            # AI training rights files (ai.txt, tdmrep.json): public by
            # nature, like robots.txt, and read by automated agents that
            # cannot authenticate.
            self._serve_static(route)
            return
        if route.startswith("/media/"):
            self._serve_media(route)
            return
        if route == "/favicon.ico":
            # The browser always asks for it: if it exists in output we serve it,
            # otherwise we answer with a clean 404 (it used to receive the login
            # page as an "icon", which is a wrong answer).
            favicon_path = OUTPUT_DIR / "favicon.ico"
            if favicon_path.exists():
                self._serve_media("/favicon.ico")
            else:
                self.send_error(404, "No favicon.")
            return

        # --- Access pages ---
        if route == "/login":
            # If there is no password yet, send to the creation page.
            if not password_is_set():
                self._send(set_password_page())
            else:
                self._send(login_page())
            return
        if route == "/logout":
            token = self._read_cookie_token()
            if token in ACTIVE_SESSIONS:
                ACTIVE_SESSIONS.discard(token)
            self._redirect("/login", cookie="sessione=; Max-Age=0; Path=/")
            return

        # --- From here on everything is ADMINISTRATION: you must be logged in ---
        if not self._user_is_authenticated():
            # First run without a password: leads to password creation.
            if not password_is_set():
                self._send(set_password_page())
            else:
                self._send(login_page())
            return

        # --- Administration pages (protected) ---
        if route == "/admin":
            self._send(admin_page(load_articles()))
        elif route == "/config":
            self._send(config_page())
        elif route == "/edit":
            slug = query.get("slug", [None])[0]
            if slug:
                art = load_article(slug)
            else:
                art = None
            self._send(editor_page(art))
        elif route == "/change-password":
            self._send(change_password_page())
        elif route == "/preview":
            # On-the-fly preview of an article, even if it is a draft.
            slug = query.get("slug", [None])[0]
            # Preview language: ?lingua=en shows the English version.
            preview_language = query.get("language", ["it"])[0]
            if preview_language not in ("it", "en"):
                preview_language = "it"
            if slug:
                art = load_article(slug)
            else:
                art = None
            if art is None:
                self.send_error(404, "Article not found.")
            else:
                page = generate_article_page(art, preview_language)
                self._send(page)
        elif route == "/export":
            # Downloads a ZIP backup with all the articles and the configuration.
            self._handle_export()
        else:
            self.send_error(404)

    def _handle_export(self):
        """
        Create a ZIP archive in memory with every article (JSON files) and
        the configuration, and send it as a download.
        It is the complete backup of the blog contents.
        """
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # We add every JSON file of the articles.
            if POSTS_DIR.exists():
                for path_value in POSTS_DIR.glob("*.json"):
                    zip_file.write(path_value, "posts/" + path_value.name)
            # We add the configuration, if it exists.
            if CONFIG_FILE.exists():
                zip_file.write(CONFIG_FILE, "config.json")

        data = buffer.getvalue()
        # File name with today's date.
        oggi = datetime.now().strftime("%Y-%m-%d")
        file_name = "pyblog-backup-" + oggi + ".zip"

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="' + file_name + '"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _path_inside_output(self, route):
        """
        Turn a route into a file path, making sure it stays INSIDE the output
        folder. Without this check, a hand-crafted request such as
        "/posts/../../config.json" could read files outside the folder (the
        config with the API keys, the password hash).
        Return the safe path, or None if the route looks suspicious.
        """
        path_value = (OUTPUT_DIR / route.lstrip("/")).resolve()
        radice = OUTPUT_DIR.resolve()
        try:
            path_value.relative_to(radice)
        except ValueError:
            return None
        return path_value

    def _serve_static(self, route):
        if route == "/posts/" or route == "/":
            route = "/index.html"
        if route == "/en/" or route == "/en":
            route = "/en/index.html"
        if route == "/it/" or route == "/it":
            route = "/it/index.html"
        path_value = self._path_inside_output(route)
        if path_value is None:
            self.send_error(404, "Invalid path.")
            return
        if path_value.exists() and path_value.is_file():
            tipo = "text/html"
            if path_value.suffix == ".css":
                tipo = "text/css"
            elif path_value.suffix == ".xml":
                tipo = "application/rss+xml"
            elif path_value.suffix == ".json":
                tipo = "application/json"
            elif path_value.suffix == ".txt":
                tipo = "text/plain"
            elif path_value.suffix == ".svg":
                tipo = "image/svg+xml"
            self._send(path_value.read_text(encoding="utf-8"), tipo)
        else:
            self.send_error(404, "Generate the site first (the 'Rebuild site' button).")

    def _serve_media(self, route):
        """Serve a file from the media folder (video or images), as binary."""
        path_value = self._path_inside_output(route)
        if path_value is None:
            self.send_error(404, "Invalid path.")
            return
        if path_value.exists() and path_value.is_file():
            data = path_value.read_bytes()
            # We choose the content type based on the file extension.
            # For SVG images it is essential, otherwise the browser will not show them.
            estensione = path_value.suffix.lower()
            if estensione == ".png":
                tipo = "image/png"
            elif estensione == ".jpg":
                tipo = "image/jpeg"
            elif estensione == ".jpeg":
                tipo = "image/jpeg"
            elif estensione == ".gif":
                tipo = "image/gif"
            elif estensione == ".svg":
                tipo = "image/svg+xml"
            elif estensione == ".webp":
                tipo = "image/webp"
            elif estensione == ".mp4":
                tipo = "video/mp4"
            elif estensione == ".webm":
                tipo = "video/webm"
            else:
                tipo = "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404, "File not found.")

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path

        # --- Authentication routes (reachable without being logged in) ---
        if route == "/set-password":
            self._handle_set_password()
            return
        if route == "/login":
            self._handle_login()
            return

        # --- From here on everything requires authentication ---
        if not self._user_is_authenticated():
            self._send_json({"ok": False, "error": T("err_unauthorized", admin_language())})
            return

        # The password change (when logged in) and the upload have their own handlers.
        if route == "/change-password":
            self._handle_change_password()
            return
        if route == "/upload":
            self._handle_upload()
            return

        # For the other routes the body is JSON (text).
        lunghezza = int(self.headers.get("Content-Length", 0))
        if lunghezza > 0:
            body = self.rfile.read(lunghezza).decode("utf-8")
        else:
            body = "{}"

        if route == "/translate":
            # Translates a piece of text (title, description or content)
            # from Italian to English, using the configured service.
            try:
                data = json.loads(body)
                text = data.get("text", "")
                esito = translate_text(text)
                self._send_json(esito)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if route == "/generate-description":
            # Generates an SEO description from the article content with AI.
            try:
                data = json.loads(body)
                content = data.get("content", "")
                title_value = data.get("title", "")
                esito = generate_seo_description(content, title_value)
                self._send_json(esito)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if route == "/generate-preview":
            # Generates the narrative reader preview with AI.
            try:
                data = json.loads(body)
                content = data.get("content", "")
                title_value = data.get("title", "")
                esito = generate_reader_preview(content, title_value)
                self._send_json(esito)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if route == "/analyze-seo":
            # Full SEO / AI-SEO analysis of the article with the LLM:
            # keywords, backlink anchor texts, internal links, FAQ, advice.
            try:
                data = json.loads(body)
                esito = analyze_article_seo(
                    data.get("content", ""),
                    data.get("title", ""),
                    data.get("slug", ""),
                    data.get("tags", ""),
                    data.get("description", ""))
                self._send_json(esito)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if route == "/revise-article":
            # Turns the SEO analysis into anchored, minimal edits that
            # the operator reviews and accepts one by one.
            try:
                data = json.loads(body)
                esito = generate_article_revision(
                    data.get("content", ""),
                    data.get("title", ""),
                    data.get("tags", ""),
                    data.get("analysis", {}))
                self._send_json(esito)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if route == "/save":
            try:
                data = json.loads(body)
                old_slug = data.get("original_slug", "")
                new_slug = save_article(data)
                # If the slug has changed, remove the old file.
                if old_slug and old_slug != new_slug:
                    delete_article(old_slug)
                build()  # rebuilds the static HTML right away
                self._send_json({"ok": True, "slug": new_slug})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif route == "/delete":
            data = json.loads(body)
            delete_article(data["slug"])
            build()
            self._send_json({"ok": True})
        elif route == "/admin-language":
            # Changes the language of the administration interface and saves it.
            try:
                data = json.loads(body)
                new_language = data.get("language", "it")
                if new_language not in ("it", "en"):
                    new_language = "it"
                config_attuale = load_config()
                config_attuale["admin_language"] = new_language
                save_config(config_attuale)
                reload_global_config()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif route == "/toggle-status":
            # Changes an article's status (published <-> draft) without
            # having to open the editor. It loads the article, changes its status,
            # saves it and rebuilds the site.
            try:
                data = json.loads(body)
                slug = data["slug"]
                new_status = data["status"]
                article = load_article(slug)
                if article is None:
                    self._send_json({"ok": False, "error": T("err_article_not_found", admin_language())})
                else:
                    article["status"] = new_status
                    save_article(article)
                    build()
                    self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif route == "/save-config":
            try:
                new_config = json.loads(body)
                # IMPORTANT: we merge with the existing configuration instead
                # of overwriting it. The form of the Settings page does not
                # contain ALL the fields (e.g. lingua_admin, seo, ordine_home):
                # without this merge, every save would wipe them.
                config_attuale = load_config()
                for key in new_config:
                    config_attuale[key] = new_config[key]
                save_config(config_attuale)
                reload_global_config()
                build()  # rebuilds the site with the new configuration
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif route == "/save-config-raw":
            # Saves the hand-edited config.json as raw text.
            # We validate the JSON BEFORE saving: if it is malformed we reject it
            # with a clear message, so the site does not break.
            try:
                data = json.loads(body)
                config_text = data.get("content", "")
                # We try to parse the text as JSON: if it fails,
                # the error tells us the line and column of the problem.
                try:
                    config_validata = json.loads(config_text)
                except json.JSONDecodeError as json_error:
                    messaggio = T("err_invalid_json_prefix", admin_language()) + str(json_error)
                    self._send_json({"ok": False, "error": messaggio})
                    return
                # It must be an object (a dictionary), not a list or anything else.
                if not isinstance(config_validata, dict):
                    self._send_json({"ok": False, "error": T("err_config_must_be_object", admin_language())})
                    return
                save_config(config_validata)
                build()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif route == "/rebuild":
            n = build()
            self._send_json({"ok": True, "articles": n})
        else:
            self.send_error(404)

    def _read_form(self):
        """Read and decode a POST body in form format (field=value)."""
        lunghezza = int(self.headers.get("Content-Length", 0))
        if lunghezza > 0:
            body = self.rfile.read(lunghezza).decode("utf-8")
        else:
            body = ""
        return urllib.parse.parse_qs(body)

    def _handle_set_password(self):
        """First run: create the administration password."""
        # If a password already exists, we do not allow resetting it from here.
        if password_is_set():
            self._redirect("/login")
            return
        form = self._read_form()
        password = form.get("password", [""])[0]
        confirmed = form.get("conferma", [""])[0]
        la = admin_language()
        if password == "" or len(password) < 6:
            self._send(set_password_page(
                T("err_password_too_short", la)))
            return
        if password != confirmed:
            self._send(set_password_page(
                T("err_passwords_dont_match_setup", la)))
            return
        set_password(password)
        token = create_session_token()
        cookie = self._session_cookie(token)
        self._redirect("/admin", cookie=cookie)

    def _session_cookie(self, token):
        """
        Build the session cookie. Behind an HTTPS reverse proxy (which
        sets X-Forwarded-Proto) the Secure flag is added, so the browser
        never sends the session over plain HTTP. On local plain-HTTP use
        the flag is omitted, otherwise the browser would drop the cookie
        and login would silently stop working.
        """
        cookie = "sessione=" + token + "; HttpOnly; Path=/; Max-Age=86400; SameSite=Lax"
        proto = self.headers.get("X-Forwarded-Proto", "")
        if proto == "https":
            cookie = cookie + "; Secure"
        return cookie

    def _handle_login(self):
        """Verify the password and create a session."""
        # If there have been too many errors in a row, login is locked
        # for a few moments: it makes a brute-force attack pointless.
        la = admin_language()
        if login_is_locked():
            secondi = int(LOGIN_STATO["locked_until"] - time.time()) + 1
            self._send(login_page(
                T("err_too_many_attempts", la).replace("{n}", str(secondi))))
            return
        form = self._read_form()
        password = form.get("password", [""])[0]
        if verify_password(password):
            record_successful_login()
            token = create_session_token()
            cookie = self._session_cookie(token)
            self._redirect("/admin", cookie=cookie)
        else:
            record_failed_login()
            # A small pause: it slows automated attempts down even further.
            time.sleep(0.5)
            self._send(login_page(T("err_wrong_password", la)))

    def _handle_change_password(self):
        """Change the password while logged in."""
        form = self._read_form()
        attuale = form.get("attuale", [""])[0]
        new_value = form.get("nuova", [""])[0]
        confirmed = form.get("conferma", [""])[0]
        la = admin_language()
        if not verify_password(attuale):
            self._send(change_password_page(T("err_current_password_wrong", la)))
            return
        if len(new_value) < 6:
            self._send(change_password_page(T("err_new_password_too_short", la)))
            return
        if new_value != confirmed:
            self._send(change_password_page(T("err_new_passwords_dont_match", la)))
            return
        set_password(new_value)
        self._send(change_password_page("", T("success_password_changed", la)))

    def _handle_upload(self):
        """
        Receive a video uploaded from the editor (multipart/form-data),
        save it into the media folder and return the file URL.
        """
        try:
            content_type = self.headers.get("Content-Type", "")

            # In a multipart body, the header contains the "boundary" that separates
            # the parts of the form. We extract it to split the body.
            if "boundary=" not in content_type:
                self._send_json({"ok": False, "error": T("err_invalid_format", admin_language())})
                return
            parti_intestazione = content_type.split("boundary=")
            boundary = parti_intestazione[1].strip()
            boundary_bytes = ("--" + boundary).encode("utf-8")

            lunghezza = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(lunghezza)

            # We split the body into its parts using the boundary.
            blocks = body.split(boundary_bytes)

            file_name = ""
            video_data = b""

            for block in blocks:
                if b"filename=" not in block:
                    continue
                # We separate the block headers from the binary content.
                # They are divided by an empty line (\r\n\r\n).
                separatore = b"\r\n\r\n"
                if separatore not in block:
                    continue
                posizione = block.find(separatore)
                intestazioni = block[:posizione].decode("utf-8", "ignore")
                content = block[posizione + len(separatore):]

                # We remove the trailing \r\n that precedes the next boundary.
                if content.endswith(b"\r\n"):
                    content = content[:-2]

                # We extract the file name from the header.
                pieces = intestazioni.split('filename="')
                if len(pieces) >= 2:
                    resto = pieces[1]
                    end = resto.find('"')
                    file_name = resto[:end]

                video_data = content

            if file_name == "":
                self._send_json({"ok": False, "error": T("err_no_file_received", admin_language())})
                return

            url = save_uploaded_file(file_name, video_data)
            self._send_json({"ok": True, "url": url})

        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def log_message(self, *args):
        pass  # silences the request log


def serve(host="127.0.0.1", port=PORT):
    """
    Start the editor server. For safety it listens ONLY on localhost: the
    administration area must not be reachable from the local network or
    from the internet. To expose it (e.g. behind a reverse proxy) you can
    pass a different host: python3 pyblog.py serve 8000 0.0.0.0
    """
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build()  # generates the initial state
    # Lets you restart the server right away without the "port busy" error.
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), Handler) as httpd:
        print(f"\n  PyBlog - writing desk")
        print(f"  Open:  http://localhost:{port}/\n")
        if host not in ("127.0.0.1", "localhost"):
            print(f"  WARNING: the server is listening on {host}: the editor is")
            print(f"  reachable from other devices on the network too.\n")
        print(f"  Articles are saved in:      {POSTS_DIR}")
        print(f"  Static HTML is generated in: {OUTPUT_DIR}")
        print(f"  (Ctrl+C to stop)\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")


# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = "serve"

    if command == "build":
        n = build()
        print(f"Generated {n} articles in {OUTPUT_DIR}")
    elif command == "serve":
        # Usage: python3 pyblog.py serve [port] [host]
        # Examples: serve            -> localhost:8000
        #           serve 9000       -> localhost:9000
        #           serve 8000 0.0.0.0 -> reachable from the network (not recommended)
        chosen_port = PORT
        chosen_host = "127.0.0.1"
        if len(sys.argv) > 2:
            try:
                chosen_port = int(sys.argv[2])
            except ValueError:
                print(f"Invalid port: {sys.argv[2]}")
                sys.exit(1)
        if len(sys.argv) > 3:
            chosen_host = sys.argv[3]
        serve(chosen_host, chosen_port)
    elif command == "import-md":
        # Usage: python3 pyblog.py import-md <file.md or folder>
        if len(sys.argv) < 3:
            print("Usage: python3 pyblog.py import-md <file.md | folder>")
            sys.exit(1)
        n = import_markdown(sys.argv[2])
        if n > 0:
            build()
            print(f"Imported {n} articles and rebuilt the site.")
            print("Note: articles without 'status: published' in the front matter")
            print("were imported as drafts, to be reviewed in the editor.")
        else:
            print("No .md files imported.")
    elif command == "export-md":
        # Usage: python3 pyblog.py export-md <destination folder>
        if len(sys.argv) < 3:
            print("Usage: python3 pyblog.py export-md <folder>")
            sys.exit(1)
        n = export_markdown(sys.argv[2])
        print(f"Exported {n} articles to {sys.argv[2]}")
    elif command == "password":
        # Password change from the command line (useful over SSH if you forget it).
        # Usage: python3 pyblog.py password
        import getpass
        print("Set a new administration password.")
        new_value = getpass.getpass("New password: ")
        if len(new_value) < 6:
            print("Error: the password must be at least 6 characters long.")
            sys.exit(1)
        confirmed = getpass.getpass("Confirm password: ")
        if new_value != confirmed:
            print("Error: the passwords do not match.")
            sys.exit(1)
        set_password(new_value)
        print(f"Password updated. Stored (as a hash) in {PASSWORD_FILE}")
    else:
        print("Usage: python3 pyblog.py [serve [port] [host] | build | password | import-md <path> | export-md <folder>]")
