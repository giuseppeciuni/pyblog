"""
The HTTP server of the administration area.

It serves three different things:

  - the generated static site (output/), so you can preview the blog locally;
  - the private administration pages (dashboard, editor, settings, password);
  - a small JSON API the editor calls with fetch().

Everything that changes state is protected three ways: a session cookie, a
CSRF token bound to that session, and a size limit on the request body.
"""
import http.server
import json
import mimetypes
import secrets
import tempfile
import threading
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone

from core import build as build_module
from core import i18n, newsletter, render
from core.ai import (analyze_article_seo, generate_reader_preview,
                     generate_seo_description, translate_text)
from core.articles import (MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, SlugTakenError,
                           article_for_preview, collect_series, delete_article,
                           due_scheduled_articles, html_content_is_empty,
                           list_versions, load_article, load_articles,
                           load_version, publish_due_articles,
                           max_image_side, requested_slug, save_article,
                           save_uploaded_file, validate_upload)
from core.docx_import import convert_docx, looks_like_docx
from core.auth import (create_session_token, csrf_token_for,
                       csrf_token_is_valid, destroy_all_sessions,
                       destroy_session, login_is_locked, login_lock_remaining,
                       password_is_set, record_failed_login,
                       record_successful_login, session_is_valid, set_password,
                       verify_password)
from core.build import (BUILD_LOCK, build, compute_reading_time, format_date,
                        generate_article_page)
from core.config import (CONFIG, CONFIG_FILE, MEDIA_DIR, OUTPUT_DIR, PORT,
                         POSTS_DIR, admin_language, load_config, main_language,
                         reload_global_config, save_config, secondary_language)
from core.i18n import LANGUAGE_NAMES, T
from core.render import esc, js, js_attr

# Bootstrap version loaded from a CDN for all the administration pages.
BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"

QUILL_CSS = "https://cdn.quilljs.com/1.3.7/quill.snow.css"
QUILL_JS = "https://cdn.quilljs.com/1.3.7/quill.min.js"
BLOT_FORMATTER_JS = "https://unpkg.com/quill-blot-formatter@1.0.5/dist/quill-blot-formatter.min.js"
HLJS_CSS = "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css"
HLJS_JS = "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"

# CodeMirror 5 for the boxes of the custom code: colours, line numbers and
# indentation instead of a bare textarea. Only the two pages with such boxes
# load it, and admin.js keeps the textarea when the CDN does not answer.
# htmlmixed needs the three modes before it to colour the scripts and styles
# inside the HTML.
CODEMIRROR_BASE = "https://cdn.jsdelivr.net/npm/codemirror@5.65.16"
CODEMIRROR_CSS = CODEMIRROR_BASE + "/lib/codemirror.min.css"
CODEMIRROR_JS = (
    CODEMIRROR_BASE + "/lib/codemirror.min.js",
    CODEMIRROR_BASE + "/mode/xml/xml.min.js",
    CODEMIRROR_BASE + "/mode/javascript/javascript.min.js",
    CODEMIRROR_BASE + "/mode/css/css.min.js",
    CODEMIRROR_BASE + "/mode/htmlmixed/htmlmixed.min.js",
)

# Content-Security-Policy for the administration pages. It allows this origin
# plus exactly the CDNs the editor really loads, and nothing else: a script
# injected into an article could no longer call out to a server of its own.
# 'unsafe-inline' is still needed for the onclick attributes and the small
# JSON block that carries PB_I18N; the host allowlist is what does the work.
ADMIN_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
    "https://cdn.quilljs.com https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.quilljs.com; "
    "img-src 'self' data: blob: https:; "
    "media-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Hard ceiling on a request body, applied before a single byte is read.
# Uploads get the larger one because a video legitimately reaches it; every
# other endpoint speaks JSON and never needs more than a few megabytes.
MAX_UPLOAD_BODY = 100 * 1024 * 1024   # 100 MB
MAX_JSON_BODY = 32 * 1024 * 1024      # 32 MB
# A Word document is text and a handful of images; anything past this is not
# an article. The cap is checked before the body is read.
MAX_DOCX_BODY = 30 * 1024 * 1024      # 30 MB

# POST endpoints that change state and therefore require a valid CSRF token.
# /login and /set-password are absent on purpose: there is no session yet, so
# there is no token to check, and neither of them can act on existing data.
CSRF_PROTECTED_ROUTES = (
    "/save", "/delete", "/save-config", "/save-config-raw", "/toggle-status",
    "/rebuild", "/upload", "/admin-language", "/change-password",
    "/translate", "/generate-description", "/generate-preview", "/analyze-seo",
    "/import-docx", "/preview", "/newsletter-prova", "/newsletter-rimuovi",
)

# The files the administration area serves from static/. Naming them makes
# the route an allowlist rather than a path check.
ADMIN_STATIC_FILES = ("common.css", "admin.css", "admin.js")

# The GET routes handled by the administration, as opposed to the static site.
ADMIN_GET_ROUTES = ("/admin", "/config", "/edit", "/change-password",
                    "/preview", "/export", "/scegli-punto", "/versioni",
                    "/versione", "/newsletter-iscritti.csv")


# ---------------------------------------------------------------------------
# STRINGS HANDED TO THE ADMIN JAVASCRIPT
# ---------------------------------------------------------------------------
# admin.js contains no translated text at all: everything it displays is
# looked up in window.PB_I18N. These are the keys it can ask for.

JS_TRANSLATION_KEYS = (
    # Pasting from Word and uploads
    "js_recovering_pasted_images", "js_pasted_all_recovered",
    "js_pasted_partial_recovered", "js_pasted_word_image_unavailable",
    "js_uploading", "js_uploading_image",
    "js_video_uploaded", "js_image_uploaded", "js_upload_error",
    "js_image_resized_local", "js_error_prefix",
    # YouTube
    "js_prompt_youtube_link", "js_youtube_not_recognized",
    # Tables
    "admin_table_hint", "admin_table_editor_title", "admin_table_add_row",
    "admin_table_del_row", "admin_table_add_col", "admin_table_del_col",
    "admin_table_save", "admin_table_cancel", "js_table_how_many_rows",
    "js_table_how_many_cols", "js_table_header_cell", "js_table_body_cell",
    "js_table_format_not_applicable",
    # Dashboard
    "js_site_rebuilt", "js_status_change_error", "js_delete_named",
    "js_delete_error", "js_delete_confirm",
    # Editor: generation, counters, SEO analysis
    "js_write_article_content_first", "js_generating", "js_suggestion_inserted",
    "js_net_error_generation", "js_seo_save_first", "js_seo_analyzing",
    "js_seo_done", "js_desc_counter_empty", "js_chars_unit",
    "js_chars_too_long_google", "js_chars_too_short_seo",
    "js_chars_ideal_length", "js_preview_counter_empty",
    "seo_copy", "seo_copied", "seo_backlink_target", "seo_primary_keywords",
    "seo_secondary_keywords", "seo_title_variants", "seo_anchor_texts",
    "seo_suggested_tags", "seo_meta_review", "seo_internal_links", "seo_faq",
    "seo_ai_tips", "seo_apply_tags",
    # Translation
    "js_translating", "js_translated_review", "js_check_api_key",
    "js_net_error_translation", "js_write_intro_first", "js_translated_home",
    "js_media_recovered",
    # Settings
    "admin_codice_titolo", "admin_codice_elimina",
    "admin_salvataggio", "admin_config_salvata", "admin_errore_salvataggio",
    "admin_config_raw_salvata", "err_invalid_json_prefix",
    # Custom code: the folded summary of a card, the ready-made templates,
    # the consent banner
    "admin_codice_attivo", "admin_codice_spento", "admin_codice_senza_nome",
    "consenso_necessary", "consenso_statistics", "consenso_marketing",
    "js_modello_campo_ga4", "js_modello_campo_gtm", "js_modello_campo_pub",
    "js_modello_campo_slot", "js_modello_campo_aw", "js_modello_campo_pixel",
    "js_modello_campo_clarity", "js_modello_non_valido", "js_modello_creato",
    "js_modello_ads_txt", "js_modello_ga4_doppio", "js_consenso_rinnovato",
    # Shared dialogs, saving, autosave and the Word import
    "admin_chiudi", "admin_annulla", "admin_elimina",
    "js_save_error", "js_unsaved_changes", "js_slug_was_taken",
    "js_autosaving", "js_autosaved_at", "js_autosave_failed",
    "js_autosave_needs_title", "js_delete_title", "js_delete_body",
    "js_site_rebuilt_error",
    "js_docx_importing", "js_docx_imported", "js_docx_net_error",
    "js_docx_overwrite_title", "js_docx_overwrite_body",
    "js_docx_overwrite_confirm", "js_docx_warnings_title",
    "js_docx_wrong_extension", "err_file_too_large",
    # Editor: publishing, the state of the article
    "admin_pubblica", "admin_ritira", "js_bozza_salvata", "js_pubblicato",
    "js_aggiornato", "js_ritirato", "js_pubblica_titolo", "js_pubblica_corpo",
    "js_ritira_titolo", "js_ritira_corpo", "js_titolo_per_pubblicare",
    "js_modifiche_da_salvare", "admin_annulla_modifiche",
    "js_annulla_modifiche_titolo", "js_annulla_modifiche_corpo",
    "js_impostazioni_non_salvate", "admin_progetto_senza_nome",
    "admin_progetto_elimina", "js_aggiornato_alle",
    "js_programma_titolo", "js_programma_corpo", "js_programma_data",
    "js_programmato", "js_programmazione_annullata", "js_modifiche_salvate",
    "admin_pubblica_ora", "admin_programma_annulla", "admin_esce_il",
    "admin_programma_conferma", "js_salvato_alle",
    "admin_versioni", "js_versioni_vuoto", "js_versione_mostra",
    "js_versione_ripristina", "js_versione_ripristinata", "js_versione_parole",
    "js_versione_errore", "js_versione_perdi", "admin_stato_bozza",
    "admin_stato_pubblicato", "admin_stato_programmato", "admin_chiudi",
    "js_versione_scegli",
    "js_nl_prova_ok", "js_nl_prova_errore", "js_nl_rimuovi_titolo", "js_nl_rimosso",
    "admin_nl_rimuovi",
) + tuple(key for key in i18n.UI_TRANSLATIONS
          # The window that chooses a point on the page, and the names it
          # gives the blocks of the page.
          if key.startswith(("js_sp_", "js_pd_")))

# Toolbar tooltips: CSS selector of the Quill button -> translated label.
# The selectors are the ones Quill 1.3.x generates.
TOOLBAR_TOOLTIP_KEYS = (
    ("span.ql-font", "tip_font"),
    ("span.ql-size", "tip_size"),
    ("span.ql-header", "tip_header"),
    ("button.ql-bold", "tip_bold"),
    ("button.ql-italic", "tip_italic"),
    ("button.ql-underline", "tip_underline"),
    ("button.ql-strike", "tip_strike"),
    ("span.ql-color", "tip_color"),
    ("span.ql-background", "tip_background"),
    ('button.ql-script[value="sub"]', "tip_sub"),
    ('button.ql-script[value="super"]', "tip_super"),
    ('button.ql-list[value="ordered"]', "tip_list_ordered"),
    ('button.ql-list[value="bullet"]', "tip_list_bullet"),
    ('button.ql-list[value="check"]', "tip_list_check"),
    ('button.ql-indent[value="-1"]', "tip_indent_less"),
    ('button.ql-indent[value="+1"]', "tip_indent_more"),
    ('button.ql-align[value=""]', "tip_align_left"),
    ('button.ql-align[value="center"]', "tip_align_center"),
    ('button.ql-align[value="right"]', "tip_align_right"),
    ('button.ql-align[value="justify"]', "tip_align_justify"),
    ("button.ql-blockquote", "tip_blockquote"),
    ("button.ql-code-block", "tip_code_block"),
    ("button.ql-link", "tip_link"),
    ("button.ql-image", "tip_image"),
    ("button.ql-video", "tip_video"),
    ("button.ql-clean", "tip_clean"),
)


def fill_languages(text, language):
    """
    Put the names of the site's two languages into an interface label.

    The translation goes from the main language to the other one, and which
    is which depends on the site: Italian to English, or English to Italian.
    The labels say {principale} and {lingua} instead of naming them, and
    {CODICE} is the short code of the translation ("EN" or "IT").
    """
    main = main_language()
    other = secondary_language()
    main_name = LANGUAGE_NAMES[main].get(language, LANGUAGE_NAMES[main]["it"])
    other_name = LANGUAGE_NAMES[other].get(language, LANGUAGE_NAMES[other]["it"])
    return (text.replace("{principale}", main_name)
                .replace("{Principale}", main_name[:1].upper() + main_name[1:])
                .replace("{lingua}", other_name)
                .replace("{Lingua}", other_name[:1].upper() + other_name[1:])
                .replace("{CODICE}", other.upper()))


def TL(key, language):
    """T() for the labels that name the site's languages."""
    return fill_languages(T(key, language), language)


def js_translations(language):
    """
    Build the object injected as window.PB_I18N: the strings admin.js needs,
    the toolbar tooltip map, and the two homepage placeholders (which are
    always needed in both languages, one per editor).
    """
    result = i18n.subset(JS_TRANSLATION_KEYS, language)
    for key in result:
        result[key] = fill_languages(result[key], language)

    tooltips = {}
    for selector, key in TOOLBAR_TOOLTIP_KEYS:
        tooltips[selector] = T(key, language)
    result["tooltips"] = tooltips

    # The Italian editor gets the Italian ghost text and the English one the
    # English text, whatever the language of the interface.
    result["js_home_intro_placeholder_it"] = T("js_home_intro_placeholder", "it")
    result["js_home_intro_placeholder_en"] = T("js_home_intro_placeholder", "en")
    return result


def optimisation_note(optimisation, language):
    """
    One sentence describing what was done to an uploaded image, or "".

    The author chose that file; if it comes back smaller, or comes back
    unchanged when they expected it not to, they should be told which.
    """
    if optimisation is None:
        return ""
    action = optimisation.get("action", "")
    saved_kb = optimisation.get("saved", 0) // 1024

    if action == "resized":
        da = "%dx%d" % optimisation["from"]
        a = "%dx%d" % optimisation["to"]
        return (T("img_ridimensionata", language)
                .replace("{da}", da).replace("{a}", a).replace("{n}", str(saved_kb)))
    if action == "stripped" and saved_kb > 0:
        return T("img_metadati_rimossi", language).replace("{n}", str(saved_kb))

    reason = optimisation.get("reason", "")
    if reason == "jpeg_not_resizable":
        return T("img_jpeg_non_ridimensionabile", language)
    if reason == "too_many_pixels":
        return T("img_troppi_pixel", language)
    return ""


def translate_warnings(warnings, language):
    """
    Turn the importer's warning records into sentences for the author.

    The converter records {"key": ..., "name": ...} rather than text, because
    it does not know which language the admin area is running in. Here we look
    the key up and substitute the parameters into the message.
    """
    messages = []
    for warning in warnings:
        text = T(warning.get("key", ""), language)
        for name in warning:
            if name == "key":
                continue
            text = text.replace("{" + name + "}", str(warning[name]))
        messages.append(text)
    return messages


# ---------------------------------------------------------------------------
# ADMIN PAGES
# ---------------------------------------------------------------------------

def icon(path, size=18):
    """An inline SVG icon drawn with lines, in the colour of the text around it."""
    return (f'<svg class="icona" width="{size}" height="{size}" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true" focusable="false">{path}</svg>')


# The icons of the admin menu, as SVG paths on a 24x24 grid.
ICON_ARTICLES = '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>'
ICON_NEW = '<path d="M12 5v14M5 12h14"/>'
ICON_SETTINGS = ('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8'
                 'l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5'
                 'V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1'
                 '-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1'
                 'a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1'
                 'a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5'
                 ' 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9'
                 'a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>')
ICON_REBUILD = '<path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5"/>'
ICON_BACKUP = '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>'
ICON_BLOG = ('<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>')
ICON_PASSWORD = ('<rect x="4" y="11" width="16" height="10" rx="2"/>'
                 '<path d="M8 11V7a4 4 0 0 1 8 0v4"/>')
ICON_LANGUAGE = ('<circle cx="12" cy="12" r="9"/>'
                 '<path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>')
ICON_LOGOUT = '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h10"/>'
ICON_BACK = '<path d="M15 18l-6-6 6-6"/>'
ICON_UP = '<path d="M12 19V5M5 12l7-7 7 7"/>'
ICON_DOWN = '<path d="M12 5v14M19 12l-7 7-7-7"/>'
ICON_NEXT = '<path d="M9 18l6-6-6-6"/>'

# The sections of the Settings page, in the order of the menu: the things
# set once and looked at often first, the technical ones last.
CONFIG_SECTIONS = [
    ("sito", "admin_sez_sito"),
    ("home", "admin_sez_home"),
    ("biografia", "admin_sez_biografia"),
    ("progetti", "admin_sez_progetti"),
    ("pagine", "admin_sez_pagine"),
    ("commenti", "admin_sez_commenti"),
    ("newsletter", "admin_sez_newsletter"),
    ("traduzione", "admin_sez_traduzione"),
    ("codici", "admin_sez_codici"),
    ("cookie", "admin_sez_cookie"),
    ("ai", "admin_sez_ai"),
    ("avanzate", "admin_sez_avanzate"),
]
ICON_MORE = ('<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/>'
             '<circle cx="19" cy="12" r="1"/>')


def admin_navbar(active_page, language, articles_count=None):
    """
    The side menu of the admin area, and the bar that replaces it at the
    bottom of a phone screen.
    active_page marks the current item: "articles", "new", "config" or
    "password". articles_count is the number shown next to Articles; the
    pages that already hold the list pass it, the others leave it to us.
    """
    if articles_count is None:
        articles_count = len(load_articles())

    voci = [
        ("articles", "/admin", ICON_ARTICLES, T("admin_articoli", language),
         T("admin_articoli", language), str(articles_count)),
        ("new", "/edit", ICON_NEW, T("admin_nuovo_articolo_titolo", language),
         T("admin_nuovo", language), ""),
        ("config", "/config", ICON_SETTINGS, T("admin_impostazioni", language),
         T("admin_impostazioni", language), ""),
    ]
    menu_html = []
    bar_html = []
    for key, url, path, label, short_label, count in voci:
        current = ""
        if key == active_page:
            current = ' aria-current="page"'
        count_html = ""
        if count != "":
            count_html = f'<span class="voce-conta">{count}</span>'
        if key == "config" and active_page == "config":
            # On the Settings page the item opens up into its sections;
            # admin.js marks the one on screen.
            menu_html.append(
                f'    <a class="voce voce-genitore" href="{url}">{icon(path)}'
                f'<span class="voce-testo">{label}</span></a>')
            menu_html.append(
                f'    <div class="voce-sotto-gruppo" role="group" aria-label="{label}">')
            for section, label_key in CONFIG_SECTIONS:
                menu_html.append(
                    f'      <a class="voce voce-sotto" href="{url}#{section}" '
                    f'data-sezione="{section}"><span class="voce-testo">'
                    f'{T(label_key, language)}</span></a>')
            menu_html.append('    </div>')
        else:
            menu_html.append(
                f'    <a class="voce"{current} href="{url}">{icon(path)}'
                f'<span class="voce-testo">{label}</span>{count_html}</a>')
        bar_html.append(
            f'  <a class="barra-voce"{current} href="{url}">{icon(path, 22)}'
            f'<span>{short_label}</span></a>')

    # The language switch names the language you are switching to, in that
    # language: whoever cannot read the current one can still find theirs.
    if language == "it":
        next_language = "en"
        next_language_name = "English"
    else:
        next_language = "it"
        next_language_name = "Italiano"

    current_password = ""
    if active_page == "password":
        current_password = ' aria-current="page"'

    return render.render(
        "admin/navbar.html",
        label_menu=T("admin_menu", language),
        titolo_sito=esc(CONFIG["site_title"]),
        voci="\n".join(menu_html),
        voci_barra="\n".join(bar_html),
        label_strumenti=T("admin_strumenti", language),
        icona_rigenera=icon(ICON_REBUILD),
        label_rigenera=T("admin_rigenera", language),
        desc_rigenera=T("admin_rigenera_desc", language),
        desc_backup=T("admin_backup_desc", language),
        desc_vedi_sito=T("admin_vedi_sito_desc", language),
        icona_backup=icon(ICON_BACKUP),
        label_backup=T("admin_scarica_backup", language),
        icona_blog=icon(ICON_BLOG),
        label_vedi_blog=T("admin_vedi_blog", language),
        label_nuova_scheda=T("admin_nuova_scheda", language),
        corrente_password=current_password,
        icona_password=icon(ICON_PASSWORD),
        label_password=T("admin_cambia_password", language),
        prossima_lingua=next_language,
        icona_lingua=icon(ICON_LANGUAGE),
        nome_prossima_lingua=next_language_name,
        label_lingua=esc(T("admin_lingua_interfaccia", language)),
        icona_esci=icon(ICON_LOGOUT),
        label_esci=T("admin_esci", language),
        icona_altro=icon(ICON_MORE, 22),
        label_altro=T("admin_altro", language),
    )


def admin_page_shell(titolo, contenuto, language, csrf="", navbar="",
                     head_extra="", script_extra="", page_data=None,
                     body_class=""):
    """Wrap an admin page body in templates/admin/base.html."""
    if page_data is None:
        page_data = {}
    # The skip link only makes sense when there is a menu to skip.
    skip_link = ""
    if navbar != "":
        skip_link = (f'<a class="salta-contenuto" href="#contenuto">'
                     f'{T("admin_salta_contenuto", language)}</a>\n')
        body_class = (body_class + " con-menu").strip()
    return render.render(
        "admin/base.html",
        lang=language,
        titolo_pagina=esc(titolo),
        bootstrap_css=BOOTSTRAP_CSS,
        bootstrap_js=BOOTSTRAP_JS,
        head_extra=build_module.block(head_extra),
        classe_body=body_class,
        salta_contenuto=skip_link,
        navbar=build_module.block(navbar),
        label_chiudi=T("admin_chiudi", language),
        label_annulla=T("admin_annulla", language),
        contenuto=contenuto,
        i18n=js(js_translations(language)),
        csrf=js(csrf),
        page_data=js(page_data),
        script_extra=build_module.block(script_extra),
        # A fingerprint of each file in its address: after an update the
        # address changes, so no cache - the browser's, Cloudflare's - can
        # pair the new page with the old stylesheet or script.
        v_common=build_module.asset_version("common.css"),
        v_admin_css=build_module.asset_version("admin.css"),
        v_admin_js=build_module.asset_version("admin.js"),
    )


def notify_checkbox(art, la):
    """
    "Tell the subscribers when it is published", in the publishing panel of
    a draft or a scheduled article, when the newsletter can send. Not for an
    article the subscribers already had.
    """
    current = newsletter.settings()
    if not current["enabled"] or not current["send_on_publish"] or art.get("newsletter_sent"):
        return ""
    checked = checked_if(art.get("notify_subscribers", True) is not False)
    return ('      <label class="riga-flag avvisa-iscritti solo-non-pubblicato">'
            f'<input type="checkbox" id="notify_subscribers" {checked}> '
            f'{T("admin_nl_avvisa", la)}</label>\n')


def moment_html(moment, la):
    """
    "goes out on <date>" for a scheduled article. The date is written by
    admin.js in the reader's own time zone and language; the text inside is
    what shows without JavaScript, in UTC.
    """
    if moment == "":
        return ""
    fallback = moment.replace("T", " ")[:16] + " UTC"
    return T("admin_esce_il", la).replace(
        "{date}", f'<time class="ora-locale" datetime="{esc(moment)}">{esc(fallback)}</time>')


def alert_block(message, kind):
    """A message above a form ("danger" or "success"), or nothing."""
    if message == "":
        return ""
    role = "alert" if kind == "danger" else "status"
    return f'<p class="avviso avviso-{kind}" role="{role}">{esc(message)}</p>'


def login_page(error_message=""):
    """Login page to access the administration area."""
    la = admin_language()
    contenuto = render.render(
        "admin/login.html",
        titolo=T("admin_area_riservata", la),
        invito=T("admin_login_invito", la),
        errore=alert_block(error_message, "danger"),
        label_password=T("admin_password", la),
        accedi=T("admin_accedi", la),
    )
    return admin_page_shell(T("admin_area_riservata", la), contenuto, la)


def set_password_page(error_message=""):
    """Page shown on first run to create the administration password."""
    la = admin_language()
    contenuto = render.render(
        "admin/set_password.html",
        titolo=T("admin_crea_password_titolo", la),
        invito=T("admin_crea_password_invito", la),
        errore=alert_block(error_message, "danger"),
        label_nuova=T("admin_nuova_password", la),
        label_conferma=T("admin_conferma_password", la),
        hint_lunghezza=T("admin_password_lunghezza", la),
        crea_accedi=T("admin_crea_accedi", la),
    )
    return admin_page_shell(T("admin_crea_password_titolo", la), contenuto, la)


def change_password_page(csrf, error_message="", success_message=""):
    """Page to change the password while logged in."""
    la = admin_language()
    contenuto = render.render(
        "admin/change_password.html",
        titolo=T("admin_cambia_password", la),
        sottotitolo=T("admin_cambia_password_desc", la),
        hint_lunghezza=T("admin_password_lunghezza", la),
        errore=alert_block(error_message, "danger"),
        successo=alert_block(success_message, "success"),
        csrf_token=esc(csrf),
        label_attuale=T("admin_password_attuale", la),
        label_nuova=T("admin_nuova_password", la),
        label_conferma=T("admin_conferma_nuova", la),
    )
    return admin_page_shell(T("admin_cambia_password", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("password", la))


def admin_page(articles, csrf):
    """
    Administration dashboard: the list of every article with its status,
    filters by status, a search box, and the actions on each article (edit
    in sight, the rarer ones in a small menu).
    """
    la = admin_language()
    # We count published and drafts for the summary and the filters.
    published_count = 0
    draft_count = 0
    scheduled_count = 0
    for art in articles:
        if art.get("status") == "published":
            published_count = published_count + 1
        elif art.get("status") == "scheduled":
            scheduled_count = scheduled_count + 1
        else:
            draft_count = draft_count + 1

    other = secondary_language()
    other_name = LANGUAGE_NAMES[other].get(la, LANGUAGE_NAMES[other]["it"])

    # We build one row for each article.
    lines = []
    for number, art in enumerate(articles):
        if art.get("status") == "published":
            pill_class = "pill-pubblicato"
            status_label = T("admin_pubblicato", la)
            # If it is published, the menu puts it back to draft. Same
            # words as the editor's link, from the same key, so the two
            # cannot drift apart again.
            status_action = "draft"
            status_action_label = T("admin_ritira", la)
            # Sorting happens in the browser, so every row carries the keys
            # it can be sorted by. Drafts sort first, because they are the
            # ones still waiting for work.
            status_order = "1"
        elif art.get("status") == "scheduled":
            # Scheduled: it goes out by itself. The quick action publishes
            # it at once; the second one, in the menu, takes the schedule back.
            pill_class = "pill-programmato"
            status_label = T("admin_stato_programmato", la)
            status_action = "published"
            status_action_label = T("admin_pubblica_ora", la)
            status_order = "s"
        else:
            pill_class = "pill-bozza"
            status_label = T("admin_bozza", la)
            status_action = "published"
            status_action_label = T("admin_pubblica", la)
            status_order = "0"

        # The translated version, said in words next to the date.
        also_in = ""
        if art.get("translation_confirmed", False):
            also_in = " &middot; " + T("admin_anche_in", la).replace("{language}", other_name)

        # Preview of the translated page: the link appears as soon as some
        # translated content exists (even if not confirmed yet), so that you
        # can check the translation BEFORE confirming it.
        preview_other_link = ""
        if not html_content_is_empty(art.get("content_en", "")):
            preview_label = T("admin_anteprima_lingua", la).replace("{language}", other_name)
            preview_other_link = (
                f'<a role="menuitem" tabindex="-1" '
                f'href="/preview?slug={esc(art["slug"])}&amp;language={other}" '
                f'target="_blank" rel="noopener">{preview_label}'
                f'<span class="icona-esterna" aria-hidden="true"></span></a>')

        # A scheduled article says when it goes out instead of its date, and
        # its menu can also take the schedule back.
        shown_date = format_date(art["date"], la)
        cancel_item = ""
        if art.get("status") == "scheduled":
            shown_date = moment_html(art.get("publish_at", ""), la)
            cancel_item = (f'<button role="menuitem" tabindex="-1" type="button" '
                           f'onclick="changeStatus(this, {js_attr(art["slug"])}, &quot;draft&quot;)">'
                           f'{T("admin_programma_annulla", la)}</button>')

        lines.append(render.render(
            "admin/dashboard_row.html",
            numero=number,
            voce_annulla_programmazione=cancel_item,
            titolo_minuscolo=esc(art["title"].lower()),
            data_iso=esc(art.get("date", "")),
            ordine_stato=status_order,
            tempo_lettura=compute_reading_time(art.get("content", ""), la),
            classe_pill=pill_class,
            etichetta_stato=status_label,
            anche_in=also_in,
            slug=esc(art["slug"]),
            # These three land inside an onclick attribute, so they need the
            # HTML layer on top of the JavaScript one.
            slug_js=js_attr(art["slug"]),
            titolo=esc(art["title"]),
            titolo_js=js_attr(art["title"]),
            data=shown_date,
            label_modifica=T("admin_modifica", la),
            label_altre_azioni=esc(T("admin_altre_azioni", la).replace("{title}", art["title"])),
            icona_altro=icon(ICON_MORE, 20),
            label_anteprima=T("admin_anteprima", la),
            link_anteprima_lingua=preview_other_link,
            azione_stato_js=js_attr(status_action),
            etichetta_azione_stato=status_action_label,
            label_elimina=T("admin_elimina", la),
        ).rstrip("\n"))

    if len(lines) > 0:
        listing = "\n".join(lines)
    else:
        listing = f'<p class="elenco-vuoto">{T("admin_nessun_articolo", la)}</p>'

    summary = (T("admin_riepilogo_articoli", la)
               .replace("{p}", str(published_count))
               .replace("{b}", str(draft_count)))
    if scheduled_count > 0:
        summary = summary + T("admin_riepilogo_programmati", la).replace(
            "{s}", str(scheduled_count))

    contenuto = render.render(
        "admin/dashboard.html",
        label_articoli=T("admin_articoli", la),
        riepilogo=summary,
        nuovo_articolo=T("admin_nuovo_articolo_titolo", la),
        label_mostra=T("admin_mostra_gruppo", la),
        label_tutti=T("admin_filtro_tutti", la),
        totale=len(articles),
        label_pubblicati=T("admin_pubblicati", la),
        pubblicati=published_count,
        label_bozze=T("admin_bozze", la),
        bozze=draft_count,
        label_programmati=T("admin_programmati", la),
        programmati=scheduled_count,
        programmati_nascosto="" if scheduled_count > 0 else " hidden",
        label_cerca=esc(T("admin_cerca_articoli", la)),
        label_ordina=T("admin_ordina", la),
        ordina_recenti=T("admin_ordina_recenti", la),
        ordina_vecchi=T("admin_ordina_vecchi", la),
        ordina_titolo=T("admin_ordina_titolo", la),
        ordina_stato=T("admin_ordina_stato", la),
        elenco=listing,
        nessun_corrisponde=T("admin_nessun_corrisponde", la),
    )

    return admin_page_shell(
        T("admin_titolo_pagina", la) + " - " + CONFIG["site_title"],
        contenuto, la, csrf=csrf,
        navbar=admin_navbar("articles", la, len(articles)),
        page_data={"page": "dashboard"})


def codemirror_scripts():
    """The script tags of CodeMirror and of the modes it needs, in order."""
    return "\n".join(f'<script src="{url}"></script>' for url in CODEMIRROR_JS)


def lab_of_options(art, la):
    """
    The articles a lab can refer to, as the options of a select: every
    article but the labs and the article itself, newest first.
    """
    chosen = art.get("lab_of", "")
    options = [f'<option value="">{esc(T("admin_lab_nessuno", la))}</option>']
    for other in load_articles():
        slug = other.get("slug", "")
        if other.get("kind") == "lab" or slug == "" or slug == art.get("slug"):
            continue
        selected = " selected" if slug == chosen else ""
        options.append(f'<option value="{esc(slug)}"{selected}>'
                       f'{esc(other.get("title", slug))}</option>')
    return "".join(options)


def editor_page(art, csrf):
    """The page with the WYSIWYG editor (it uses Quill, loaded from a CDN)."""
    la = admin_language()

    # If we are editing an existing article, we take its values.
    # If instead this is a new article (art is None), we start from empty fields.
    if art is not None:
        page_title = T("admin_modifica_articolo_titolo", la)
        menu_item = "articles"
        # Deleting sits at the very bottom of the sidebar, small: it used to
        # be a red button as big as Save, right under it.
        delete_button = (f'<button type="button" class="pulsante pulsante-testo pulsante-pericolo pulsante-piccolo btn-elimina-articolo" '
                         f'onclick="deleteItem()">{T("admin_elimina_articolo", la)}</button>')
    else:
        art = {}
        page_title = T("admin_nuovo_articolo_titolo", la)
        menu_item = "new"
        delete_button = ""

    # The buttons follow the state of the article: a draft can be saved or
    # published, a published article updated or taken back. Anything else
    # on disk is treated as a draft, as everywhere else.
    status = art.get("status", "draft")
    if status not in ("published", "scheduled"):
        status = "draft"
    publish_at = art.get("publish_at", "") if status == "scheduled" else ""
    url_online = ""
    if art.get("slug", "") != "":
        url_online = build_module.article_url(art, main_language())

    contenuto = render.render(
        "admin/editor.html",
        titolo_pagina_h1=page_title,
        label_titolo=T("admin_titolo", la),
        valore_titolo=esc(art.get("title", "")),
        label_contenuto=T("admin_contenuto", la),
        tip_import_docx=esc(T("tip_import_docx", la)),
        label_importa_word=T("admin_importa_word", la),
        hint_docx=T("admin_docx_hint", la),
        tip_upload_image=esc(T("tip_upload_image", la)),
        label_carica_immagine=T("admin_carica_immagine", la),
        tip_youtube=esc(T("tip_youtube", la)),
        label_youtube=T("admin_inserisci_youtube", la),
        tip_upload_video=esc(T("tip_upload_video", la)),
        label_carica_video=T("admin_carica_video", la),
        tip_table=esc(T("tip_table", la)),
        label_tabella=T("admin_inserisci_tabella", la),
        label_torna_articoli=T("admin_torna_articoli", la),
        label_inserisci=T("admin_inserisci", la),
        label_indirizzo=T("admin_indirizzo_slug", la),
        hint_indirizzo=T("admin_indirizzo_slug_hint", la),
        stato=status,
        label_stato_bozza=T("admin_stato_bozza", la),
        hint_stato_bozza=T("admin_stato_bozza_hint", la),
        label_stato_pubblicato=T("admin_stato_pubblicato", la),
        label_stato_programmato=T("admin_stato_programmato", la),
        spunta_avvisa=notify_checkbox(art, la),
        label_versioni=T("admin_versioni", la),
        hint_versioni=T("admin_versioni_hint", la),
        versioni_nascosto="" if art.get("slug", "") else " hidden",
        esce_il=moment_html(publish_at, la),
        label_salva_modifiche=T("admin_salva_modifiche", la),
        label_pubblica_ora=T("admin_pubblica_ora", la),
        label_programma_annulla=T("admin_programma_annulla", la),
        label_programma=T("admin_programma", la),
        label_programma_cambia=T("admin_programma_cambia", la),
        label_programma_quando=T("admin_programma_quando", la),
        hint_programma=T("admin_programma_hint", la),
        label_programma_conferma=T("admin_programma_conferma", la),
        url_online=esc(url_online),
        label_vedi_online=T("admin_vedi_online", la),
        label_pubblica=T("admin_pubblica", la),
        tip_pubblica=esc(T("tip_pubblica_articolo", la)),
        label_aggiorna=T("admin_aggiorna_articolo", la),
        tip_aggiorna=esc(T("tip_aggiorna_articolo", la)),
        label_salva_bozza=T("admin_salva_bozza", la),
        tip_salva_bozza=esc(T("tip_salva_bozza", la)),
        label_anteprima=T("admin_anteprima_pagina", la),
        tip_anteprima=esc(T("tip_anteprima_pagina", la)),
        label_ritira=T("admin_ritira", la),
        bottone_elimina=delete_button,
        label_sezione_metadati=T("admin_sezione_metadati", la),
        valore_slug=esc(art.get("slug", "")),
        label_tag=T("admin_tag", la),
        valore_tag=esc(art.get("tags", "")),
        label_serie=T("admin_serie", la),
        valore_serie=esc(art.get("series", "")),
        valore_serie_numero=art.get("series_number") or "",
        label_serie_numero=esc(T("admin_serie_numero", la)),
        hint_serie=help_text(T("admin_serie_hint", la)),
        serie_esistenti="".join(f'<option value="{esc(entry["name"])}">'
                                for entry in collect_series(load_articles()).values()),
        label_originale=T("admin_originale", la),
        valore_originale=esc(art.get("original_url", "")),
        hint_originale=help_text(T("admin_originale_hint", la)),
        originale_canonico_checked="checked" if art.get("original_canonical") is True else "",
        label_originale_canonico=T("admin_originale_canonico", la),
        hint_originale_canonico=help_text(T("admin_originale_canonico_hint", la)),
        label_lab=T("admin_lab", la),
        hint_lab=help_text(T("admin_lab_hint", la)),
        lab_checked="checked" if art.get("kind") == "lab" else "",
        lab_hidden="" if art.get("kind") == "lab" else "hidden",
        label_lab_di=T("admin_lab_di", la),
        opzioni_lab_di=lab_of_options(art, la),
        label_lab_repo=T("admin_lab_repo", la),
        valore_repo=esc(art.get("repo_url", "")),
        label_lab_stack=T("admin_lab_stack", la),
        valore_stack=esc(art.get("stack", "")),
        label_immagine=T("admin_immagine_copertina", la),
        hint_immagine=help_text(T("admin_immagine_copertina_hint", la)),
        valore_immagine=esc(art.get("image", "")),
        ph_immagine="https://... /media/...",
        label_carica_copertina=T("admin_carica_copertina", la),
        label_rimuovi_copertina=T("admin_rimuovi_copertina", la),
        label_anteprima_lettori=T("admin_anteprima_lettori", la),
        hint_anteprima=help_text(T("admin_anteprima_hint", la)),
        valore_anteprima=esc(art.get("preview", "")),
        label_genera_anteprima=T("admin_genera_anteprima", la),
        label_descrizione_seo=T("admin_descrizione_seo", la),
        hint_descrizione=help_text(T("admin_descrizione_hint", la)),
        valore_descrizione=esc(art.get("description", "")),
        label_suggerisci=T("admin_suggerisci_descrizione", la),
        label_analisi_seo=T("admin_analisi_seo", la),
        hint_analisi_seo=T("admin_analisi_seo_hint", la),
        label_analizza=T("admin_analizza_seo", la),
        label_versione_inglese=TL("admin_versione_inglese", la),
        label_autorizza=TL("admin_autorizza_traduzione", la),
        label_traduci=T("admin_traduci_auto", la),
        label_anteprima_en=TL("admin_anteprima_en", la),
        hint_anteprima_en=help_text(TL("admin_anteprima_en_hint", la)),
        label_conferma_traduzione=TL("admin_conferma_traduzione", la),
        codice_traduzione=secondary_language().upper(),
        label_codice_titolo=T("admin_codice_articolo_titolo", la),
        hint_codice=T("admin_codice_articolo_hint", la),
        codice_articolo_html=article_custom_code_html(art, la),
        label_codice_proprio=T("admin_codice_proprio_titolo", la),
        hint_codice_proprio=T("admin_codice_proprio_hint", la),
        codice_proprio_html=article_own_code_html(art, la),
        codice_proprio_modello=custom_code_blank_card(la, own=True),
        label_codice_proprio_aggiungi=T("admin_codice_proprio_aggiungi", la),
    )

    # The article content and the translation flags travel as JSON, never as
    # text pasted into a script: an apostrophe or a "</script>" inside an
    # article would otherwise break - or escape - the surrounding JavaScript.
    page_data = {
        "page": "editor",
        "preview_kind": "article",
        # The browser checks these before uploading, so an oversized file
        # produces a clear message instead of a connection the server drops
        # halfway through. The real limits are still enforced server-side.
        "max_docx_mb": MAX_DOCX_BODY // (1024 * 1024),
        "max_image_mb": MAX_IMAGE_BYTES // (1024 * 1024),
        "max_video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
        # The browser applies the same cap before sending, which is how a
        # JPEG gets resized at all: the server cannot decode one.
        "max_image_width": max_image_side(),
        "slug": art.get("slug", ""),
        "content": art.get("content", ""),
        "title_en": art.get("title_en", ""),
        "description_en": art.get("description_en", ""),
        "preview_en": art.get("preview_en", ""),
        "content_en": art.get("content_en", ""),
        "translation_authorized": art.get("translation_authorized", False),
        "translation_confirmed": art.get("translation_confirmed", False),
        "status": status,
        "publish_at": publish_at,
        "main_language": main_language(),
        "secondary_language": secondary_language(),
        # The article's choices about the site's code, as saved: admin.js
        # keeps the ones about snippets the editor does not list.
        "custom_code_ids": list(build_module.article_snippet_ids(art)),
        "custom_code_off_ids": list(build_module.article_off_ids(art)),
    }

    head_extra = (f'<link href="{QUILL_CSS}" rel="stylesheet">\n'
                  f'<link href="{HLJS_CSS}" rel="stylesheet">\n'
                  f'<link href="{CODEMIRROR_CSS}" rel="stylesheet">\n'
                  f'<script src="{HLJS_JS}"></script>')
    script_extra = (f'<script src="{QUILL_JS}"></script>\n'
                    f'<script src="{BLOT_FORMATTER_JS}"></script>\n'
                    + codemirror_scripts())

    return admin_page_shell(page_title, contenuto, la, csrf=csrf,
                            navbar=admin_navbar(menu_item, la),
                            head_extra=head_extra, script_extra=script_extra,
                            page_data=page_data, body_class="menu-compatto")


def with_snippet_ids(snippets):
    """
    Give an id to every custom code snippet that arrives without one.

    The browser generates the id when you add a card, so normally there is
    nothing to do here. This is the safety net for a snippet added by hand in
    the advanced config.json editor: without an id it could never be ticked
    on an article. Existing ids are left exactly as they are, because the
    articles refer to them.
    """
    if not isinstance(snippets, list):
        return []
    # Every id already in the list, including the ones further down that we
    # have not reached yet: a freshly minted id must avoid those too.
    taken = set()
    for snippet in snippets:
        if isinstance(snippet, dict) and str(snippet.get("id", "")) != "":
            taken.add(str(snippet["id"]))

    used = set()
    cleaned = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        snippet_id = str(snippet.get("id", ""))
        # An id we have already handed out in this pass is a duplicate, so
        # the second one gets replaced. An id seen only once is kept as is.
        if snippet_id == "" or snippet_id in used:
            snippet_id = "snip-" + secrets.token_hex(4)
            while snippet_id in taken or snippet_id in used:
                snippet_id = "snip-" + secrets.token_hex(4)
        used.add(snippet_id)
        snippet["id"] = snippet_id
        cleaned.append(snippet)
    return cleaned


# The positions of a snippet, with the key of their label, in the order the
# dropdown lists them.
POSITION_LABEL_KEYS = {
    "head": "admin_codice_pos_head",
    "body_start": "admin_codice_pos_body_start",
    "body_end": "admin_codice_pos_body_end",
    "nav": "admin_codice_pos_nav",
    "after_header": "admin_codice_pos_after_header",
    "sidebar": "admin_codice_pos_sidebar",
    "home_feed": "admin_codice_pos_home_feed",
    "article_start": "admin_codice_pos_article_start",
    "article_middle": "admin_codice_pos_article_middle",
    "article_end": "admin_codice_pos_article_end",
    "before_footer": "admin_codice_pos_before_footer",
    "anchor": "admin_codice_pos_anchor",
}

SCOPE_LABEL_KEYS = {
    "all": "admin_codice_scope_tutto",
    "home": "admin_codice_scope_home",
    "articles": "admin_codice_scope_solo_articoli",
    "home_articles": "admin_codice_scope_articles",
    "optin": "admin_codice_scope_solo_optin",
    "home_optin": "admin_codice_scope_optin",
}


def snippet_summary(snippet, la, own=False):
    """
    The line under the name of a folded card: where the code goes, on which
    pages, and whether it waits for consent. A long list of cards can then be
    read without opening any of them.
    """
    position = snippet.get("position", "head")
    pieces = [T(POSITION_LABEL_KEYS.get(position, "admin_codice_pos_head"), la)]
    if position == "anchor" and str(snippet.get("anchor_label", "")).strip() != "":
        pieces = [str(snippet["anchor_label"]).strip()]
    if not own:
        pieces.append(T(SCOPE_LABEL_KEYS.get(snippet.get("scope", "home"),
                                             "admin_codice_scope_home"), la))
    consent = snippet.get("consent", "necessary")
    if consent not in ("necessary", "statistics", "marketing"):
        consent = "necessary"
    pieces.append(T("consenso_" + consent, la))
    return " · ".join(pieces)


def custom_code_card(snippet, index_value, la, own=False, open_card=False):
    """
    Build one card for a custom code snippet: a folded summary, and the
    fields underneath.

    The id travels in a data attribute rather than a field: it is machinery,
    not something to edit. admin.js reads it back when saving so a snippet
    keeps the same id across saves, and the articles keep pointing at it.

    own=True is the card of a snippet written inside an article: it has no
    "on which pages" choice, because its page is the article.
    """
    position = snippet.get("position", "head")
    scope = snippet.get("scope", "home")
    consent = snippet.get("consent", "necessary")
    enabled = snippet.get("enabled", False) is True
    name = snippet.get("name", "")
    shown_name = name
    if shown_name.strip() == "":
        shown_name = T("admin_codice_senza_nome", la)

    scope_block = ""
    if not own:
        scope_block = render.render(
            "admin/custom_code_scope.html",
            label_ambito=T("admin_codice_ambito", la),
            sel_tutto=selected_if(scope, "all"),
            label_scope_tutto=T("admin_codice_scope_tutto", la),
            sel_home=selected_if(scope, "home"),
            label_scope_home=T("admin_codice_scope_home", la),
            sel_solo_articoli=selected_if(scope, "articles"),
            label_scope_solo_articoli=T("admin_codice_scope_solo_articoli", la),
            sel_articles=selected_if(scope, "home_articles"),
            label_scope_articles=T("admin_codice_scope_articles", la),
            sel_solo_optin=selected_if(scope, "optin"),
            label_scope_solo_optin=T("admin_codice_scope_solo_optin", la),
            sel_optin=selected_if(scope, "home_optin"),
            label_scope_optin=T("admin_codice_scope_optin", la),
            hint_ambito=T("admin_codice_scope_hint", la),
        )

    values = {
        "indice": index_value,
        "id_snippet": esc(snippet.get("id", "")),
        "aperto": " open" if open_card else "",
        "nome_mostrato": esc(shown_name),
        "riassunto": esc(snippet_summary(snippet, la, own)),
        "stato": T("admin_codice_attivo", la) if enabled else T("admin_codice_spento", la),
        "classe_spento": "" if enabled else " spento",
        "checked": checked_if(enabled),
        "label_attivo": T("admin_codice_attivo", la),
        "label_elimina": T("admin_codice_elimina", la),
        "label_nome": T("admin_codice_nome", la),
        "nome": esc(name),
        "ph_nome": esc(T("admin_codice_nome_ph", la)),
        "label_posizione": T("admin_codice_posizione", la),
        "gruppo_tecnico": T("admin_codice_pos_gruppo_tecnico", la),
        "gruppo_visibile": T("admin_codice_pos_gruppo_visibile", la),
        "blocco_ambito": scope_block,
        "label_consenso": T("admin_codice_consenso", la),
        "sel_necessary": selected_if(consent, "necessary"),
        "label_cons_necessary": T("admin_codice_cons_necessary", la),
        "sel_statistics": selected_if(consent, "statistics"),
        "label_cons_statistics": T("admin_codice_cons_statistics", la),
        "sel_marketing": selected_if(consent, "marketing"),
        "label_cons_marketing": T("admin_codice_cons_marketing", la),
        # The homepage list is no place for code that belongs to one article.
        "solo_sito": " hidden disabled" if own else "",
        "hint_posizione": T("admin_codice_pos_hint_proprio" if own else "admin_codice_pos_hint", la),
        "hint_consenso": T("admin_codice_consenso_hint_proprio" if own else "admin_codice_consenso_hint", la),
        "label_codice": esc(T("admin_codice_codice", la)),
        "codice": esc(snippet.get("code", "")),
        # The point chosen on the page, for the "anchor" position.
        "punto_nascosto": "" if position == "anchor" else " hidden",
        "label_punto": T("admin_punto", la),
        "punto_testo": esc(str(snippet.get("anchor_label", "")).strip()
                           or T("admin_punto_nessuno", la)),
        "label_scegli_punto": T("admin_scegli_punto", la),
        "hint_punto": T("admin_punto_hint", la),
        "ancora": esc(str(snippet.get("anchor_selector", ""))),
        "ancora_dove": esc(str(snippet.get("anchor_where", "after"))),
        "ancora_etichetta": esc(str(snippet.get("anchor_label", ""))),
        "ancora_pagina": esc(str(snippet.get("anchor_page", ""))),
    }
    for key, label_key in POSITION_LABEL_KEYS.items():
        values["sel_" + key] = selected_if(position, key)
        values["label_pos_" + key] = T(label_key, la)
    return render.render("admin/custom_code_card.html", **values).rstrip("\n")


def custom_code_cards(config, la):
    """Build the settings card of every configured custom code snippet."""
    snippets = config.get("custom_code", [])
    if not isinstance(snippets, list):
        snippets = []

    parts = []
    index_value = 0
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        parts.append(custom_code_card(snippet, index_value, la))
        index_value = index_value + 1
    return "\n".join(parts)


def custom_code_blank_card(la, own=False):
    """
    The empty card that the "Add code" button clones, rendered once into a
    <template>. Cloning beats building the markup in JavaScript: the fields
    and their translated labels stay defined in the one template file, so
    they cannot drift apart. A new snippet starts active and open, because
    you add one in order to use it.

    Code written for one article is mostly something to see there - an ad,
    an embed, a widget - so its card starts at the end of the text.
    """
    blank = {"enabled": True, "scope": "all", "position": "head"}
    if own:
        blank = {"enabled": True, "position": "article_end"}
    return custom_code_card(blank, 0, la, own=own, open_card=True)


def article_custom_code_html(art, la):
    """
    The site-wide snippets that can reach this article, one checkbox each.

    A snippet scoped to "selected articles" is off until ticked here. One
    that goes on every article is on until unticked here: that is how a
    single article says no to an advertisement the others carry. Snippets
    that never reach an article (homepage only) are not listed.
    """
    snippets = CONFIG.get("custom_code", [])
    if not isinstance(snippets, list):
        snippets = []
    ticked = build_module.article_snippet_ids(art)
    switched_off = build_module.article_off_ids(art)

    rows = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        if snippet.get("enabled", False) is not True:
            continue
        scope = snippet.get("scope", "home")
        if scope not in ("optin", "home_optin", "articles", "home_articles", "all"):
            continue
        snippet_id = str(snippet.get("id", ""))
        name = esc(snippet.get("name", "")) or esc(snippet_id)
        optin = scope in ("optin", "home_optin")
        if optin:
            checked = " checked" if snippet_id in ticked else ""
            kind = T("admin_codice_articolo_scelto", la)
        else:
            checked = "" if snippet_id in switched_off else " checked"
            kind = T("admin_codice_articolo_sempre", la)
        where = esc(T(POSITION_LABEL_KEYS.get(snippet.get("position", "head"),
                                              "admin_codice_pos_head"), la))
        rows.append(
            '<label class="riga-flag codice-articolo-riga">'
            f'<input type="checkbox" class="codice-articolo" value="{esc(snippet_id)}"'
            f' data-tipo="{"optin" if optin else "sempre"}"{checked}> {name} '
            f'<span class="hint">({where}, {esc(kind)})</span></label>')

    if len(rows) == 0:
        return f'<p class="hint">{T("admin_codice_articolo_vuoto", la)}</p>'
    return "\n".join(rows)


def article_own_code_html(art, la):
    """The cards of the snippets written inside this article."""
    parts = []
    index_value = 0
    for snippet in build_module.article_own_snippets(art):
        parts.append(custom_code_card(snippet, index_value, la, own=True))
        index_value = index_value + 1
    return "\n".join(parts)



def config_placeholders(language):
    """
    Example text for the empty fields of the Settings page.

    These are placeholder attributes: they NEVER get saved on their own, they
    only show ghost text while a field is empty. They exist to show what a
    well-filled, SEO-useful profile looks like, in the site's own language.
    """
    if language == "en":
        return {
            "site_title": "Inside the Machine",
            "subtitle": "Notes on Python, distributed systems and AI",
            "author": "Jane Doe",
            "base_url": "https://www.yourdomain.com",
            "seo_author_url": "https://www.yourdomain.com/about",
            "seo_author_image": "https://www.yourdomain.com/img/author.jpg",
            "seo_author_role": "CTO at Acme Labs · Computer Science lecturer",
            "seo_author_bio": ("I'm Jane, a software engineer with 15 years in distributed "
                "systems. I write about Python, system architecture and applied AI, "
                "aimed at developers who want to build reliable products."),
            "seo_logo": "https://www.yourdomain.com/img/logo.png",
            "seo_twitter": "@yourname",
            "analytics_id": "G-XXXXXXXXXX",
            "umami_url": "https://stats.ciunix.com",
            "umami_website_id": "3e9b1c2a-1234-4f0a-9c1d-abcdef012345",
        }
    return {
        "site_title": "Dentro la Macchina",
        "subtitle": "Note su Python, sistemi distribuiti e intelligenza artificiale",
        "author": "Maria Rossi",
        "base_url": "https://www.tuodominio.it",
        "seo_author_url": "https://www.tuodominio.it/chi-sono",
        "seo_author_image": "https://www.tuodominio.it/img/autore.jpg",
        "seo_author_role": "CTO presso Acme Labs · Docente di Informatica",
        "seo_author_bio": ("Sono Maria, ingegnera del software con 15 anni di esperienza "
            "in sistemi distribuiti. Scrivo di Python, architetture software e AI "
            "applicata, per chi vuole costruire prodotti affidabili."),
        "seo_logo": "https://www.tuodominio.it/img/logo.png",
        "seo_twitter": "@tuonome",
        "analytics_id": "G-XXXXXXXXXX",
        "umami_url": "https://stats.ciunix.com",
        "umami_website_id": "3e9b1c2a-1234-4f0a-9c1d-abcdef012345",
    }


def selected_if(value, expected):
    """Return the "selected" attribute when the two values match."""
    if value == expected:
        return "selected"
    return ""


def checked_if(value):
    """Return the "checked" attribute for a true value."""
    if value:
        return "checked"
    return ""


def project_card(item, la):
    """
    The card of one project in the Settings. With item None it is the blank
    card admin.js clones for "Add a project".
    """
    if item is None:
        item = {"name": "", "description": "", "description_en": "",
                "url": "", "image": "", "visible": True}
    return render.render(
        "admin/project_card.html",
        checked=checked_if(item.get("visible", True)),
        label_visibile=T("admin_progetto_visibile", la),
        label_su=esc(T("admin_sposta_su", la)),
        label_giu=esc(T("admin_sposta_giu", la)),
        icona_su=icon(ICON_UP),
        icona_giu=icon(ICON_DOWN),
        label_elimina=T("admin_progetto_elimina", la),
        label_nome=T("admin_progetto_nome", la),
        nome=esc(item.get("name", "")),
        label_descrizione=T("admin_progetto_descrizione", la),
        descrizione=esc(item.get("description", "")),
        hint_descrizione=T("admin_progetto_descrizione_hint", la),
        label_descrizione_en=TL("admin_progetto_descrizione_en", la),
        descrizione_en=esc(item.get("description_en", "")),
        label_link=T("admin_progetto_link", la),
        link=esc(item.get("url", "")),
        hint_link=T("admin_progetto_link_hint", la),
        label_immagine=T("admin_progetto_immagine", la),
        immagine=esc(item.get("image", "")),
        hint_immagine=T("admin_progetto_immagine_hint", la),
        label_carica=T("admin_carica_immagine", la),
    ).rstrip("\n")


def code_guide(la, open_it):
    """The three worked examples above the list of external code."""
    return render.render(
        "admin/codici_guida.html",
        aperta=" open" if open_it else "",
        titolo=T("admin_guida_codici_titolo", la),
        intro=T("admin_guida_codici_intro", la),
        ti_danno=T("admin_guida_ti_danno", la),
        cosa_fai=T("admin_guida_cosa_fai", la),
        es1_titolo=T("admin_guida_es1_titolo", la),
        es1_passi=T("admin_guida_es1_passi", la),
        es2_titolo=T("admin_guida_es2_titolo", la),
        es2_passi=T("admin_guida_es2_passi", la),
        es3_titolo=T("admin_guida_es3_titolo", la),
        es3_passi=T("admin_guida_es3_passi", la),
        fiducia=T("admin_guida_fiducia", la),
    ).rstrip("\n")


def help_text(text):
    """
    A hint written to sit in brackets after a label, turned into a sentence
    for under the field: "(es. CTO e docente)" becomes "Es. CTO e docente".
    """
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
        text = text[:1].upper() + text[1:]
    return text


def config_sections_list(la):
    """The list of the Settings sections, what /config opens on a phone."""
    rows = []
    for key, label_key in CONFIG_SECTIONS:
        rows.append(
            f'    <li><a class="sezioni-voce" href="#{key}">'
            f'<span class="sezioni-voce-nome">{T(label_key, la)}</span>'
            f'<span class="sezioni-voce-desc">{TL(label_key + "_desc", la)}</span>'
            f'{icon(ICON_NEXT, 20)}</a></li>')
    return "\n".join(rows)


def config_section_header(key, la):
    """
    The top of a Settings section: on a phone a link back to the list, then
    the name of the section and one line about what it holds.
    """
    label_key = dict(CONFIG_SECTIONS)[key]
    return (
        '  <div class="sezione-testata">\n'
        f'    <a class="pulsante pulsante-icona sezione-indietro" href="#elenco" '
        f'aria-label="{esc(T("admin_torna_impostazioni", la))}">{icon(ICON_BACK, 22)}</a>\n'
        '    <div>\n'
        f'      <p class="sezione-occhiello">{T("admin_impostazioni", la)}</p>\n'
        f'      <h1 class="pagina-titolo" id="titolo-{key}">{T(label_key, la)}</h1>\n'
        f'      <p class="pagina-sottotitolo">{TL(label_key + "_desc", la)}</p>\n'
        '    </div>\n'
        '  </div>')


def config_page(csrf):
    """
    Site configuration page:
    - WYSIWYG editor for the top of the homepage (bio, images...)
    - general settings (title, subtitle, author, domain)
    - comment configuration (Giscus or Disqus)
    It also shows a live preview of the home content.
    """
    config = load_config()
    la = admin_language()
    site_language = config.get("language", "it")

    seo = config.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}
    profiles = seo.get("social_profiles", [])
    if not isinstance(profiles, list):
        profiles = []

    ai_training = config.get("ai_training", {})
    if not isinstance(ai_training, dict):
        ai_training = {}
    ai_policy = ai_training.get("policy", "open")

    # The consent banner, with the defaults filled in the same way the build
    # fills them: what the form shows is what the site does.
    consent = build_module.consent_settings(config)

    # --- Homepage: where the introduction goes, how long the excerpts are ---
    intro_position = config.get("home_intro_position", "sidebar")
    if intro_position not in ("sidebar", "top"):
        intro_position = "sidebar"

    # --- Editorial cards: one WYSIWYG editor each, filled in by admin.js ---
    card_lista = config.get("home_cards", [])
    card_html_parti = []
    card_contents = []
    index_value = 0
    for card in card_lista:
        card_contents.append(card.get("content", ""))
        checked = ""
        if card.get("active", False):
            checked = "checked"
        card_html_parti.append(render.render(
            "admin/config_card.html",
            indice=index_value,
            checked=checked,
            label_mostra=T("admin_mostra_card", la),
            label_titolo=T("admin_titolo_card", la),
            titolo=esc(card.get("title", "")),
            label_contenuto=T("admin_contenuto", la),
        ).rstrip("\n"))
        index_value = index_value + 1

    commenti = config.get("comments", "none")
    giscus = config.get("giscus", {})
    disqus = config.get("disqus", {})
    translation = config.get("translation", {})
    translation_service = translation.get("service", "deepl")

    ph = config_placeholders(site_language)
    # html.escape on the placeholders too: they end up in an HTML attribute.
    ph = {k: esc(v) for k, v in ph.items()}

    biography = build_module.biography_settings(config)
    lavoro = build_module.work_settings(config)
    projects = build_module.projects_settings(config)
    project_cards = [project_card(item, la) for item in projects["items"]]
    empty_note_hidden = ""
    if len(project_cards) > 0:
        empty_note_hidden = " hidden"

    nl = newsletter.settings(config)
    nl_state = newsletter.load_state()
    nl_rows = []
    for reader in nl_state["subscribers"]:
        stato = T("admin_nl_confermato" if reader.get("status") == "confirmed" else "admin_nl_attesa", la)
        email = esc(reader.get("email", ""))
        nl_rows.append(
            f'      <li><span class="nl-email">{email}</span> <span class="hint">{stato}</span>'
            f'<button type="button" class="pulsante pulsante-testo pulsante-pericolo pulsante-piccolo" '
            f'data-email="{email}" onclick="removeSubscriber(this)">{T("admin_nl_rimuovi", la)}</button></li>')
    if nl_rows:
        nl_list = '    <ul class="nl-elenco">\n' + "\n".join(nl_rows) + "\n    </ul>"
    else:
        nl_list = f'    <p class="aiuto">{T("admin_nl_nessuno", la)}</p>'
    nl_confirmed = sum(1 for r in nl_state["subscribers"] if r.get("status") == "confirmed")
    last = nl_state["last"]
    nl_last = ""
    if last.get("title"):
        if last.get("error"):
            nl_last = (f'    <p class="avviso avviso-danger">' + esc(T("admin_nl_ultimo_errore", la)
                       .replace("{title}", last["title"]).replace("{error}", last["error"])) + "</p>")
        else:
            nl_last = (f'    <p class="aiuto">' + esc(T("admin_nl_ultimo", la)
                       .replace("{title}", last["title"]).replace("{sent}", str(last.get("sent", 0)))) + "</p>")

    context = dict(
        titolo_impostazioni=T("admin_impostazioni", la),
        checked_nl=checked_if(nl["enabled"]),
        label_nl_attiva=T("admin_nl_attiva", la),
        hint_nl_attiva=T("admin_nl_attiva_hint", la),
        label_nl_dove=T("admin_nl_dove", la),
        checked_nl_barra=checked_if(nl["in_sidebar"]),
        label_nl_barra=T("admin_nl_barra", la),
        checked_nl_articolo=checked_if(nl["after_article"]),
        label_nl_articolo=T("admin_nl_articolo", la),
        label_nl_titolo=T("admin_nl_titolo", la),
        valore_nl_titolo=esc(nl["title"]),
        ph_nl_titolo=esc(T("nl_titolo_default", site_language)),
        label_nl_testo=T("admin_nl_testo", la),
        valore_nl_testo=esc(nl["text"]),
        ph_nl_testo=esc(T("nl_testo_default", site_language)),
        hint_nl_testi=T("admin_nl_testi_hint", la),
        checked_nl_invio=checked_if(nl["send_on_publish"]),
        label_nl_invio=T("admin_nl_invio_auto", la),
        hint_nl_invio=T("admin_nl_invio_auto_hint", la),
        label_gr_nl_spedizione=T("admin_gr_nl_spedizione", la),
        hint_gr_nl_spedizione=T("admin_gr_nl_spedizione_hint", la),
        label_nl_mittente_nome=T("admin_nl_mittente_nome", la),
        valore_nl_mittente_nome=esc(nl["sender_name"]),
        hint_nl_mittente_nome=T("admin_nl_mittente_nome_hint", la),
        label_nl_mittente_email=T("admin_nl_mittente_email", la),
        valore_nl_mittente_email=esc(nl["sender_email"]),
        label_nl_smtp_host=T("admin_nl_smtp_host", la),
        valore_nl_smtp_host=esc(nl["smtp_host"]),
        label_nl_smtp_port=T("admin_nl_smtp_port", la),
        valore_nl_smtp_port=nl["smtp_port"],
        hint_nl_smtp_port=T("admin_nl_smtp_port_hint", la),
        label_nl_smtp_sicurezza=T("admin_nl_smtp_sicurezza", la),
        sel_nl_starttls=selected_if(nl["smtp_security"], "starttls"),
        sel_nl_ssl=selected_if(nl["smtp_security"], "ssl"),
        sel_nl_none=selected_if(nl["smtp_security"], "none"),
        label_nl_starttls=T("admin_nl_sic_starttls", la),
        label_nl_ssl=T("admin_nl_sic_ssl", la),
        label_nl_none=T("admin_nl_sic_none", la),
        label_nl_smtp_utente=T("admin_nl_smtp_utente", la),
        valore_nl_smtp_utente=esc(nl["smtp_user"]),
        label_nl_smtp_password=T("admin_nl_smtp_password", la),
        # The password is never written back into the page: an empty field
        # keeps the saved one, as the translation keys do.
        ph_nl_password=esc(T("admin_nl_password_salvata", la)) if nl["smtp_password"] else "",
        hint_nl_smtp_password=T("admin_nl_smtp_password_hint", la),
        label_nl_prova=T("admin_nl_prova", la),
        hint_nl_prova=T("admin_nl_prova_hint", la),
        label_gr_nl_iscritti=T("admin_gr_nl_iscritti", la),
        nl_conteggio=T("admin_nl_conteggio", la).replace("{c}", str(nl_confirmed)).replace(
            "{p}", str(len(nl_state["subscribers"]) - nl_confirmed)),
        nl_ultimo=nl_last,
        nl_elenco=nl_list,
        label_nl_esporta=T("admin_nl_esporta", la),
        checked_bio=checked_if(biography["enabled"]),
        label_bio_attiva=T("admin_bio_attiva", la),
        hint_bio_attiva=T("admin_bio_attiva_hint", la),
        label_posizione_home=T("admin_posizione_home", la),
        label_pos_sidebar=T("admin_pos_sidebar", la),
        label_pos_top=T("admin_pos_top", la),
        label_pos_bottom=T("admin_pos_bottom", la),
        sel_bio_sidebar=selected_if(biography["position"], "sidebar"),
        sel_bio_top=selected_if(biography["position"], "top"),
        sel_bio_bottom=selected_if(biography["position"], "bottom"),
        label_bio_foto=T("admin_bio_foto", la),
        valore_bio_foto=esc(biography["photo"]),
        hint_bio_foto=T("admin_bio_foto_hint", la),
        label_carica_foto=T("admin_carica_foto", la),
        label_rimuovi=T("admin_rimuovi", la),
        label_bio_testo=T("admin_bio_testo", la),
        label_bio_testo_en=TL("admin_bio_testo_en", la),
        hint_bio_testo_en=TL("admin_bio_testo_en_hint", la),
        checked_progetti=checked_if(projects["enabled"]),
        label_progetti_attivi=T("admin_progetti_attivi", la),
        hint_progetti_attivi=T("admin_progetti_attivi_hint", la),
        sel_progetti_sidebar=selected_if(projects["position"], "sidebar"),
        sel_progetti_top=selected_if(projects["position"], "top"),
        sel_progetti_bottom=selected_if(projects["position"], "bottom"),
        progetti_html="\n".join(project_cards),
        progetti_vuoto_nascosto=empty_note_hidden,
        label_progetti_vuoto=T("admin_progetti_vuoto", la),
        label_progetto_aggiungi=T("admin_progetto_aggiungi", la),
        progetto_modello=project_card(None, la),
        elenco_sezioni=config_sections_list(la),
        label_gr_sito=T("admin_gr_sito", la),
        label_gr_autore=T("admin_gr_autore", la),
        label_gr_immagini=T("admin_gr_immagini", la),
        label_gr_disposizione=T("admin_gr_disposizione", la),
        label_gr_pagina_articolo=T("admin_gr_pagina_articolo", la),
        label_gr_statistiche=T("admin_gr_statistiche", la),
        label_umami_url=T("admin_umami_url", la),
        label_umami_id=T("admin_umami_id", la),
        hint_giscus="https://giscus.app",
        label_annulla_modifiche=T("admin_annulla_modifiche", la),
        nota_salva=T("admin_salva_nota", la),
        guida_codici=code_guide(la, len(config.get("custom_code", []) or []) == 0),
        label_inserisci=T("admin_inserisci", la),
        label_parte_alta=T("admin_parte_alta_home", la),
        hint_parte_alta=T("admin_parte_alta_hint", la),
        tip_upload_image=esc(T("tip_upload_image", la)),
        label_carica_immagine=T("admin_carica_immagine", la),
        tip_youtube=esc(T("tip_youtube", la)),
        label_youtube=T("admin_inserisci_youtube", la),
        tip_upload_video=esc(T("tip_upload_video", la)),
        label_carica_video=T("admin_carica_video", la),
        tip_preview=esc(T("tip_preview", la)),
        label_mostra_anteprima_home=T("admin_mostra_anteprima_home", la),
        hint_come_appare=T("admin_come_appare_home", la),
        label_presentazione_inglese=TL("admin_presentazione_inglese", la),
        hint_presentazione_en=TL("admin_presentazione_en_hint", la),
        label_traduci_italiano=TL("admin_traduci_dall_italiano", la),
        label_lavoro_titolo=T("admin_lavoro_titolo", la),
        checked_lavoro=checked_if(lavoro["enabled"]),
        label_lavoro_attivo=T("admin_lavoro_attivo", la),
        hint_lavoro_attivo=T("admin_lavoro_attivo_hint", la),
        label_lavoro_url=T("admin_lavoro_url", la),
        hint_lavoro_url=T("admin_lavoro_url_hint", la),
        valore_lavoro_url=esc(lavoro["url"]),
        label_lavoro_label=T("admin_lavoro_label", la),
        valore_lavoro_label=esc(lavoro["label"]),
        ph_lavoro_label=esc(T("lavora_con_me", "it")),
        label_lavoro_label_en=T("admin_lavoro_label_en", la),
        valore_lavoro_label_en=esc(lavoro["label_en"]),
        ph_lavoro_label_en=esc(T("lavora_con_me", "en")),
        label_lavoro_testo=T("admin_lavoro_testo", la),
        valore_lavoro_testo=esc(lavoro["text"]),
        ph_lavoro_testo=esc(T("lavora_invito", "it")),
        label_lavoro_testo_en=T("admin_lavoro_testo_en", la),
        valore_lavoro_testo_en=esc(lavoro["text_en"]),
        ph_lavoro_testo_en=esc(T("lavora_invito", "en")),
        hint_card_home=T("admin_card_home_hint", la),
        checked_card_home_attiva=checked_if(config.get("home_cards_enabled", True)),
        label_card_home_attiva=T("admin_card_home_attiva", la),
        hint_card_home_attiva=T("admin_card_home_attiva_hint", la),
        card_html="\n".join(card_html_parti),
        label_codice_titolo=T("admin_codice_titolo", la),
        hint_codice=T("admin_codice_hint", la),
        codice_html=custom_code_cards(config, la),
        codice_modello=custom_code_blank_card(la),
        label_codice_vuoto=T("admin_codice_vuoto", la),
        label_codice_aggiungi=T("admin_codice_aggiungi", la),
        label_codice_modelli=T("admin_codice_modelli", la),
        hint_codice_modelli=T("admin_codice_modelli_hint", la),
        label_modello_libero=T("admin_codice_libero", la),
        label_modello_adsense_auto=T("admin_modello_adsense_auto", la),
        label_modello_adsense_unita=T("admin_modello_adsense_unita", la),
        label_modello_google_ads=T("admin_modello_google_ads", la),
        label_modello_altri=esc(T("admin_modello_altri", la)),
        label_codice_crea=T("admin_codice_crea", la),
        label_annulla_scelta=T("admin_annulla_scelta", la),
        label_ads_txt=T("admin_ads_txt", la),
        hint_ads_txt=T("admin_ads_txt_hint", la),
        valore_ads_txt=esc(config.get("ads_txt", "")),
        hint_consenso=T("admin_consenso_intro", la),
        checked_consenso=checked_if(consent["enabled"]),
        label_consenso_attivo=T("admin_consenso_attivo", la),
        label_consenso_testo=T("admin_consenso_testo", la),
        hint_consenso_testo=T("admin_consenso_testo_hint", la),
        valore_consenso_testo=esc(consent["text"]),
        ph_consenso_testo=esc(T("consenso_testo", main_language())),
        label_consenso_testo_en=TL("admin_consenso_testo_en", la),
        valore_consenso_testo_en=esc(consent["text_en"]),
        ph_consenso_testo_en=esc(T("consenso_testo", secondary_language())),
        label_consenso_privacy=T("admin_consenso_privacy", la),
        valore_consenso_privacy=esc(consent["privacy_url"]),
        ph_consenso_privacy=ph["base_url"] + "/privacy.html",
        label_consenso_rinnova=T("admin_consenso_rinnova", la),
        hint_consenso_rinnova=T("admin_consenso_rinnova_hint", la),
        label_titolo_sito=T("admin_titolo_sito", la),
        valore_titolo_sito=esc(config.get("site_title", "")),
        ph_site_title=ph["site_title"],
        label_sottotitolo=T("admin_sottotitolo", la),
        valore_sottotitolo=esc(config.get("subtitle", "")),
        ph_subtitle=ph["subtitle"],
        label_autore=T("admin_autore", la),
        valore_autore=esc(config.get("author", "")),
        ph_author=ph["author"],
        label_dominio=T("admin_dominio_sito", la),
        hint_dominio=T("admin_dominio_hint", la),
        valore_dominio=esc(config.get("base_url", "")),
        ph_base_url=ph["base_url"],
        label_analytics=T("admin_analytics", la),
        hint_analytics=T("admin_analytics_hint", la),
        valore_analytics=esc(config.get("analytics_id", "")),
        ph_analytics_id=ph["analytics_id"],
        label_umami=T("admin_umami", la),
        hint_umami=T("admin_umami_hint", la),
        valore_umami_url=esc(config.get("umami_url", "")),
        ph_umami_url=ph["umami_url"],
        valore_umami_id=esc(config.get("umami_website_id", "")),
        ph_umami_website_id=ph["umami_website_id"],
        label_lingua_principale=T("admin_lingua_principale", la),
        hint_lingua_principale=T("admin_lingua_principale_hint", la),
        sel_lingua_it=selected_if(site_language, "it"),
        sel_lingua_en=selected_if(site_language, "en"),
        hint_layout=T("admin_layout_hint", la),
        label_intro_posizione=T("admin_intro_posizione", la),
        hint_intro_posizione=T("admin_intro_posizione_hint", la),
        sel_intro_barra=selected_if(intro_position, "sidebar"),
        label_intro_barra=T("admin_intro_barra", la),
        sel_intro_sopra=selected_if(intro_position, "top"),
        label_intro_sopra=T("admin_intro_sopra", la),
        label_parole_anteprima=T("admin_parole_anteprima", la),
        hint_parole_anteprima=T("admin_parole_anteprima_hint", la),
        valore_parole_anteprima=esc(config.get("home_excerpt_words", 40)),
        label_articoli_per_pagina=T("admin_articoli_per_pagina", la),
        hint_articoli_per_pagina=T("admin_articoli_per_pagina_hint", la),
        valore_articoli_per_pagina=esc(config.get("articles_per_page", 10)),
        checked_home_evidenza=checked_if(config.get("home_featured", True)),
        label_home_evidenza=T("admin_home_evidenza", la),
        hint_home_evidenza=T("admin_home_evidenza_hint", la),
        checked_copertina_articolo=checked_if(config.get("article_cover", True)),
        label_copertina_articolo=T("admin_copertina_articolo", la),
        hint_copertina_articolo=T("admin_copertina_articolo_hint", la),
        hint_seo=T("admin_seo_intro", la),
        label_seo_autore_url=T("admin_seo_autore_url", la),
        hint_seo_autore_url=T("admin_seo_autore_url_hint", la),
        valore_seo_autore_url=esc(seo.get("author_url", "")),
        ph_seo_author_url=ph["seo_author_url"],
        label_seo_autore_immagine=T("admin_seo_autore_immagine", la),
        valore_seo_autore_immagine=esc(seo.get("author_image", "")),
        ph_seo_author_image=ph["seo_author_image"],
        label_seo_autore_ruolo=T("admin_seo_autore_ruolo", la),
        hint_seo_autore_ruolo=T("admin_seo_autore_ruolo_hint", la),
        valore_seo_autore_ruolo=esc(seo.get("author_role", "")),
        ph_seo_author_role=ph["seo_author_role"],
        label_seo_autore_bio=T("admin_seo_autore_bio", la),
        hint_seo_autore_bio=T("admin_seo_autore_bio_hint", la),
        valore_seo_autore_bio=esc(seo.get("author_bio", "")),
        ph_seo_author_bio=ph["seo_author_bio"],
        label_seo_profili=T("admin_seo_profili", la),
        hint_seo_profili=T("admin_seo_profili_hint", la),
        valore_seo_profili=esc("\n".join(profiles)),
        label_seo_logo=T("admin_seo_logo", la),
        valore_seo_logo=esc(seo.get("logo", "")),
        ph_seo_logo=ph["seo_logo"],
        label_seo_twitter=T("admin_seo_twitter", la),
        hint_seo_twitter=T("admin_seo_twitter_hint", la),
        valore_seo_twitter=esc(seo.get("twitter_site", "")),
        ph_seo_twitter=ph["seo_twitter"],
        label_seo_favicon=T("admin_seo_favicon", la),
        hint_seo_favicon=T("admin_seo_favicon_hint", la),
        valore_seo_favicon=esc(seo.get("favicon", "")),
        hint_ai_training=T("admin_ai_training_intro", la),
        label_ai_policy=T("admin_ai_training_policy", la),
        sel_ai_open=selected_if(ai_policy, "open"),
        label_ai_open=T("admin_ai_training_open", la),
        sel_ai_licensed=selected_if(ai_policy, "licensed"),
        label_ai_licensed=T("admin_ai_training_licensed", la),
        sel_ai_disallow=selected_if(ai_policy, "disallow"),
        label_ai_disallow=T("admin_ai_training_disallow", la),
        label_ai_email=T("admin_ai_training_email", la),
        hint_ai_email=T("admin_ai_training_email_hint", la),
        valore_ai_email=esc(ai_training.get("contact_email", "")),
        label_ai_license_url=T("admin_ai_training_license_url", la),
        hint_ai_license_url=T("admin_ai_training_license_url_hint", la),
        valore_ai_license_url=esc(ai_training.get("license_url", "")),
        label_ai_statement=T("admin_ai_training_statement", la),
        hint_ai_statement=T("admin_ai_training_statement_hint", la),
        valore_ai_statement=esc(ai_training.get("statement", "")),
        nota_ai_standard=T("admin_ai_training_nota_standard", la),
        label_sistema_commenti=T("admin_sistema_commenti", la),
        sel_commenti_nessuno=selected_if(commenti, "none"),
        label_commenti_nessuno=T("admin_commenti_nessuno", la),
        sel_giscus=selected_if(commenti, "giscus"),
        sel_disqus=selected_if(commenti, "disqus"),
        valore_giscus_repo=esc(giscus.get("repo", "")),
        valore_giscus_repo_id=esc(giscus.get("repo_id", "")),
        valore_giscus_category=esc(giscus.get("category", "")),
        valore_giscus_category_id=esc(giscus.get("category_id", "")),
        label_tema=T("admin_tema_label", la),
        valore_giscus_theme=esc(giscus.get("theme", "light")),
        hint_disqus=T("admin_disqus_hint", la),
        valore_disqus_shortname=esc(disqus.get("shortname", "")),
        label_traduzione=TL("admin_traduzione_titolo", la),
        hint_traduzione=T("admin_traduzione_intro", la),
        label_servizio_traduzione=T("admin_servizio_traduzione", la),
        sel_deepl=selected_if(translation_service, "deepl"),
        sel_google=selected_if(translation_service, "google"),
        sel_llm=selected_if(translation_service, "llm"),
        sel_openai=selected_if(translation_service, "openai"),
        sel_deepseek=selected_if(translation_service, "deepseek"),
        label_chiave_api=T("admin_chiave_api", la),
        ph_lascia_vuoto=esc(T("admin_lascia_vuoto", la)),
        valore_deepl_key=esc(translation.get("deepl_api_key", "")),
        valore_google_key=esc(translation.get("google_api_key", "")),
        valore_llm_key=esc(translation.get("llm_api_key", "")),
        label_endpoint=T("admin_endpoint", la),
        valore_llm_endpoint=esc(translation.get("llm_endpoint", "")),
        label_modello=T("admin_modello_label", la),
        valore_llm_modello=esc(translation.get("llm_model", "")),
        valore_openai_key=esc(translation.get("openai_api_key", "")),
        valore_openai_modello=esc(translation.get("openai_model", "gpt-4o-mini")),
        valore_deepseek_key=esc(translation.get("deepseek_api_key", "")),
        valore_deepseek_modello=esc(translation.get("deepseek_model", "deepseek-chat")),
        label_salva_rigenera=T("admin_salva_rigenera", la),
        label_config_avanzata=T("admin_config_avanzata", la),
        hint_config_avanzata=T("admin_config_avanzata_hint", la),
        label_salva_config_raw=T("admin_salva_config_raw", la),
        label_ripristina=T("admin_ripristina", la),
    )
    for key, _ in CONFIG_SECTIONS:
        context["testata_" + key] = config_section_header(key, la)
    # The hints used to sit in brackets after the label; under the field
    # they read as a sentence of their own.
    for key in context:
        if key.startswith("hint_"):
            context[key] = help_text(context[key])
    contenuto = render.render("admin/config.html", **context)

    page_data = {
        "page": "config",
        "preview_kind": "home",
        "max_image_mb": MAX_IMAGE_BYTES // (1024 * 1024),
        "max_video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
        # The browser applies the same cap before sending, which is how a
        # JPEG gets resized at all: the server cannot decode one.
        "max_image_width": max_image_side(),
        "home_content": config.get("home_content", ""),
        "home_content_en": config.get("home_content_en", ""),
        "card_contents": card_contents,
        # The pages offered by the window that chooses a point for code.
        "articoli_punto": [{"slug": a["slug"], "title": a.get("title", "")}
                           for a in load_articles() if a.get("status") == "published"][:30],
        "bio_content": biography["content"],
        "bio_content_en": biography["content_en"],
        "config_raw": json.dumps(config, ensure_ascii=False, indent=2),
        # "Ask everyone again" raises this number by one; the visitors'
        # browsers keep the number their choice was made under.
        "consent_version": consent["version"],
    }

    head_extra = (f'<link href="{QUILL_CSS}" rel="stylesheet">\n'
                  f'<link href="{CODEMIRROR_CSS}" rel="stylesheet">')
    script_extra = (f'<script src="{QUILL_JS}"></script>\n'
                    f'<script src="{BLOT_FORMATTER_JS}"></script>\n'
                    + codemirror_scripts())

    return admin_page_shell(T("admin_impostazioni", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("config", la),
                            head_extra=head_extra, script_extra=script_extra,
                            page_data=page_data, body_class="pagina-config")


# ---------------------------------------------------------------------------
# THE HTTP HANDLER
# ---------------------------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    """Handle the editor requests and serve the static preview."""

    # --- Response helpers ---------------------------------------------------

    def _security_headers(self, with_csp):
        """
        Add the headers that harden an administration response.

        nosniff stops the browser guessing a content type of its own;
        DENY stops the page being framed (clickjacking); the referrer policy
        keeps our URLs out of third-party logs; the CSP restricts where
        scripts, styles and connections may come from.
        """
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if with_csp:
            self.send_header("Content-Security-Policy", ADMIN_CSP)

    def _no_store(self):
        """
        Forbid the browser from keeping a copy of an administration response.

        The editor page and admin.js are served from fixed addresses with no
        version in them and no validator, so the browser is free to reuse the
        copy it already has. After an update that means the page is the new
        one and its JavaScript is the old one: a field added to the Settings
        form is drawn by the server, the reader sees it and ticks it, and the
        save silently leaves it out because the script collecting the fields
        knows nothing about it. Nothing looks broken, so the hunt goes to the
        code that is in fact correct. The editor runs on a local machine and
        has nothing to gain from a cache, so it asks not to be cached at all.
        """
        self.send_header("Cache-Control", "no-store")

    def _send(self, content, tipo="text/html", with_csp=True):
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self._no_store()
        self._security_headers(with_csp)
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._no_store()
        self._security_headers(False)
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, destination, cookie=None):
        """Redirect the browser to another address, optionally with a cookie."""
        self.send_response(303)
        self.send_header("Location", destination)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self._security_headers(False)
        self.end_headers()

    # --- Session ------------------------------------------------------------

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

    def _client_address(self):
        """
        The address a request really comes from, for the login lock.

        Behind nginx every request reaches us from 127.0.0.1, so on its own
        the connection address would put every visitor in the same bucket
        and one of them could lock out all the others. The reverse proxy
        writes the visitor's address in a header, and we read it - but only
        when the request does come from this machine. Someone talking to the
        server directly could write any header they like; the proxy is the
        only one we believe.

        X-Real-IP comes first: when nginx sets it, it overwrites whatever the
        visitor sent. Otherwise the LAST address of X-Forwarded-For, which is
        the one nginx itself appended; the ones before it come from the
        visitor and prove nothing.
        """
        peer = ""
        if self.client_address:
            peer = str(self.client_address[0])
        if peer.startswith("127.") or peer in ("::1", "::ffff:127.0.0.1"):
            real_ip = self.headers.get("X-Real-IP", "").strip()
            if real_ip != "":
                return real_ip
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded.strip() != "":
                return forwarded.split(",")[-1].strip()
        return peer

    def _user_is_authenticated(self):
        """Tell whether the current request comes from a logged-in user."""
        return session_is_valid(self._read_cookie_token())

    def _csrf(self):
        """The CSRF token bound to this request's session."""
        return csrf_token_for(self._read_cookie_token())

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

    def _login_or_setup_page(self):
        """Send the login page, or the password creation page on first run."""
        if not password_is_set():
            self._send(set_password_page())
        else:
            self._send(login_page())

    # --- Request bodies -----------------------------------------------------

    def _content_length(self, maximum):
        """
        Return the declared body length, or None if it is missing, malformed
        or above the ceiling. The check happens BEFORE any read: a body that
        is too large is refused without ever being buffered in memory.
        """
        raw = self.headers.get("Content-Length", "")
        if raw == "":
            return 0
        try:
            length = int(raw)
        except ValueError:
            return None
        if length < 0 or length > maximum:
            return None
        return length

    def _read_json_body(self):
        """
        Read and parse a JSON request body.
        Return (data, None) on success, or (None, message) on failure.
        """
        length = self._content_length(MAX_JSON_BODY)
        if length is None:
            return None, T("err_request_too_large", admin_language())
        if length == 0:
            return {}, None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            return None, T("err_invalid_json_prefix", admin_language()) + str(error)

    def _read_form(self):
        """Read and decode a POST body in form format (field=value)."""
        length = self._content_length(MAX_JSON_BODY)
        if length is None or length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8", "replace")
        return urllib.parse.parse_qs(body)

    # --- Static files -------------------------------------------------------

    def _path_inside(self, root, route, prefix=""):
        """
        Turn a route into a file path, making sure it stays INSIDE root.
        Without this check, a hand-crafted request such as
        "/posts/../../config.json" could read files outside the folder (the
        config with the API keys, the password hash).
        Return the safe path, or None if the route looks suspicious.
        """
        relative = route[len(prefix):].lstrip("/")
        path_value = (root / relative).resolve()
        try:
            path_value.relative_to(root.resolve())
        except ValueError:
            return None
        return path_value

    def _content_type_for(self, path_value):
        """Guess the content type of a file from its extension."""
        if path_value.name.startswith("rss") and path_value.suffix == ".xml":
            return "application/rss+xml"
        guessed, _ = mimetypes.guess_type(path_value.name)
        if guessed is not None:
            return guessed
        return "application/octet-stream"

    def _send_file(self, path_value, with_csp=False):
        """Send a file from disk as binary, with its content type."""
        data = path_value.read_bytes()
        tipo = self._content_type_for(path_value)
        if tipo.startswith("text/") or tipo in ("application/json",
                                                "application/javascript",
                                                "application/rss+xml",
                                                "image/svg+xml"):
            tipo = tipo + "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers(with_csp)
        self.end_headers()
        self.wfile.write(data)

    def _serve_output(self, route):
        """Serve a file of the generated static site."""
        if route in ("/", "/posts/"):
            route = "/index.html"
        if route in ("/en", "/en/"):
            route = "/en/index.html"
        if route in ("/it", "/it/"):
            route = "/it/index.html"
        if route.endswith("/"):
            route = route + "index.html"
        path_value = self._path_inside(OUTPUT_DIR, route)
        if path_value is None:
            self.send_error(404, "Invalid path.")
            return
        if path_value.exists() and path_value.is_file():
            self._send_file(path_value)
            return
        # A missing page answers with the site's own 404 page, as nginx does
        # online: the preview should show what readers will see.
        not_found = OUTPUT_DIR / "404.html"
        if not_found.is_file():
            data = not_found.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._security_headers(False)
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404, "Generate the site first (the 'Rebuild site' button).")

    def _serve_admin_static(self, route):
        """
        Serve a file of static/ under /admin-static/.

        Only the handful of names this project ships are served, which is a
        stricter rule than a path check: a route can name nothing else, so it
        cannot climb out of the folder to reach config.json or the password
        file. The contents come from render.read_static, so the route works
        from the single-file bundle too, where static/ does not exist.
        """
        name = route[len("/admin-static/"):]
        if name not in ADMIN_STATIC_FILES or not render.static_exists(name):
            self.send_error(404, "File not found.")
            return
        if name.endswith(".css"):
            tipo = "text/css"
        else:
            tipo = "text/javascript"
        self._send(render.read_static(name), tipo, with_csp=False)

    # --- GET ----------------------------------------------------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # --- The stylesheets and script of the admin area ---
        # These are served BEFORE the authentication check, and deliberately.
        # The login page and the first-run password page link to them, and
        # they are not logged in by definition: behind the check they were
        # answered with the login page itself, as text/html, so the browser
        # discarded both stylesheets and drew those two pages unstyled.
        # There is nothing to protect here anyway - the files are the same
        # bytes for every visitor, like the Bootstrap CSS these pages already
        # load from a CDN. Only the three names in ADMIN_STATIC_FILES are
        # served, so this opens nothing else.
        if route.startswith("/admin-static/"):
            self._serve_admin_static(route)
            return

        # --- Access pages (no authentication) ---
        if route == "/login":
            self._login_or_setup_page()
            return
        if route == "/logout":
            destroy_session(self._read_cookie_token())
            self._redirect("/login", cookie="sessione=; Max-Age=0; Path=/")
            return

        # --- Administration (authentication required) ---
        if route in ADMIN_GET_ROUTES:
            if not self._user_is_authenticated():
                self._login_or_setup_page()
                return
            self._handle_admin_get(route, query)
            return

        # --- The newsletter's links from the emails ---
        if route in ("/conferma", "/disiscrivi"):
            self._handle_newsletter_link(route, query)
            return

        # --- Everything else is the public static site ---
        if route == "/favicon.ico":
            # The browser always asks for it: if it exists in output we serve
            # it, otherwise we answer with a clean 404 (it used to receive the
            # login page as an "icon", which is a wrong answer).
            favicon_path = OUTPUT_DIR / "favicon.ico"
            if favicon_path.exists():
                self._send_file(favicon_path)
            else:
                self.send_error(404, "No favicon.")
            return
        self._serve_output(route)

    def _handle_admin_get(self, route, query):
        """Serve an administration page. The caller checked authentication."""
        csrf = self._csrf()

        if route == "/admin":
            self._send(admin_page(load_articles(), csrf))
        elif route == "/config":
            self._send(config_page(csrf))
        elif route == "/edit":
            slug = query.get("slug", [None])[0]
            art = None
            if slug:
                art = load_article(slug)
            self._send(editor_page(art, csrf))
        elif route == "/change-password":
            self._send(change_password_page(csrf))
        elif route == "/preview":
            # On-the-fly preview of an article, even if it is a draft.
            slug = query.get("slug", [None])[0]
            # Preview language: ?language=en shows the English version.
            preview_language = query.get("language", [main_language()])[0]
            if preview_language not in ("it", "en"):
                preview_language = main_language()
            art = None
            if slug:
                art = load_article(slug)
            if art is None:
                self.send_error(404, "Article not found.")
            else:
                # The preview is a public page: it must not carry the admin
                # CSP, which would block the CDNs the public pages use.
                self._send(generate_article_page(art, preview_language),
                           with_csp=False)
        elif route == "/export":
            # Downloads a ZIP backup with all the articles and the configuration.
            self._handle_export()
        elif route == "/scegli-punto":
            self._handle_point_page(query)
        elif route == "/newsletter-iscritti.csv":
            data = newsletter.subscribers_csv().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="iscritti.csv"')
            self.send_header("Content-Length", str(len(data)))
            self._no_store()
            self._security_headers(False)
            self.end_headers()
            self.wfile.write(data)
        elif route == "/versioni":
            # The earlier versions of an article, for the editor's window.
            self._send_json({"ok": True, "versions": list_versions(query.get("slug", [""])[0])})
        elif route == "/versione":
            version = load_version(query.get("slug", [""])[0], query.get("id", [""])[0])
            if version is None:
                self._send_json({"ok": False, "error": T("err_article_not_found", admin_language())})
            else:
                self._send_json({"ok": True, "version": version})
        else:
            self.send_error(404)

    # --- Newsletter -----------------------------------------------------------

    def _site_url(self):
        """The site's address for the links in the emails."""
        host = self.headers.get("Host", f"localhost:{PORT}")
        proto = self.headers.get("X-Forwarded-Proto", "http")
        return public_site_url(f"{proto}://{host}")

    def _send_public(self, page, status=200):
        """A public page answered by Python: no admin CSP, never cached."""
        data = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._no_store()
        self._security_headers(False)
        self.end_headers()
        self.wfile.write(data)

    def _newsletter_page(self, language, prefix, action="", status=200):
        """One of the answers of the newsletter, as a page of the site."""
        site = CONFIG.get("site_title", "")
        self._send_public(build_module.newsletter_message_page(
            language, T(prefix + "_titolo", language),
            T(prefix + "_testo", language).replace("{site}", site), action), status)

    def _handle_newsletter_post(self, route):
        """
        The sign-up form of the site, and the buttons of the confirmation
        and unsubscribe pages. None of them needs a session: the form asks
        for nothing more than an address, the others carry their token.
        """
        form = self._read_form()
        language = form.get("lingua", [main_language()])[0]
        if language not in ("it", "en"):
            language = main_language()
        # Leaving always works, even with the newsletter switched off.
        if route != "/disiscrivi" and not newsletter.settings()["enabled"]:
            self.send_error(404)
            return
        if route == "/iscriviti":
            # The hidden field is invisible to people: whoever fills it in is
            # a robot, and gets the same answer as everybody, with no email.
            if form.get("sito", [""])[0].strip() != "":
                self._newsletter_page(language, "nl_richiesta")
                return
            if not newsletter.allowed_request(self._client_address()):
                self._newsletter_page(language, "nl_troppi", status=429)
                return
            result = newsletter.subscribe(form.get("email", [""])[0], language, self._site_url())
            if result == "invalid":
                self._newsletter_page(language, "nl_invalido", status=400)
            elif result == "error":
                self._newsletter_page(language, "nl_errore", status=503)
            else:
                self._newsletter_page(language, "nl_richiesta")
            return
        token = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("t", [""])[0]
        language = newsletter.token_language(token) or language
        if route == "/conferma":
            done = newsletter.confirm(token)
            self._newsletter_page(language, "nl_confermata" if done else "nl_link")
        else:
            done = newsletter.unsubscribe(token)
            self._newsletter_page(language, "nl_disiscritto" if done else "nl_link")

    def _handle_newsletter_link(self, route, query):
        """
        The page a link in an email opens: a button that does the thing. The
        link alone changes nothing, because mail scanners open every link.
        """
        token = query.get("t", [""])[0]
        language = newsletter.token_language(token)
        if language == "" or (route == "/conferma" and not newsletter.settings()["enabled"]):
            self._newsletter_page(language or main_language(), "nl_link", status=404)
            return
        if route == "/conferma":
            prefix, button = "nl_conferma_pagina", T("nl_conferma_pulsante", language)
        else:
            prefix, button = "nl_disiscrivi", T("nl_disiscrivi_pulsante", language)
        action = (f'        <form method="post" action="{route}?t={urllib.parse.quote(token)}">\n'
                  f'          <input type="hidden" name="lingua" value="{language}">\n'
                  f'          <button class="pulsante pulsante-primario" type="submit">{esc(button)}</button>\n'
                  '        </form>')
        self._newsletter_page(language, prefix, action)

    def _handle_point_page(self, query):
        """
        The real page - the homepage or an article - on which the author
        clicks to choose where a piece of code goes. It is generated on the
        spot, in the site's main language and without any custom code, and
        it may be framed by the administration only.
        """
        published = [a for a in load_articles() if a.get("status") == "published"]
        slug = query.get("slug", [""])[0]
        language = main_language()
        build_module.CODE_SWITCH.off = True
        try:
            if slug != "":
                art = load_article(slug)
                if art is None:
                    self.send_error(404, "Article not found.")
                    return
                page = generate_article_page(art, language, published)
            else:
                page = build_module.generate_homepage(published, language, 1, 1)
        finally:
            build_module.CODE_SWITCH.off = False
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._no_store()
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.end_headers()
        self.wfile.write(data)

    def _handle_export(self):
        """
        Send a ZIP archive with every article (JSON files), the
        configuration and the uploaded images and videos.

        The media used to be left out, so a blog restored from its backup
        came back with every picture missing: the articles only hold the
        address of an image, the file itself lives in output/media. They are
        stored without compression, because a JPEG, a PNG or an MP4 is
        already compressed and squeezing it again only costs time.

        The archive is built in a temporary file rather than in memory: with
        a few videos it can be hundreds of megabytes.
        """
        archive = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # We add every JSON file of the articles.
            if POSTS_DIR.exists():
                for path_value in sorted(POSTS_DIR.glob("*.json")):
                    zip_file.write(path_value, "posts/" + path_value.name)
                # The newsletter's subscribers, when there are any.
                if newsletter.SUBSCRIBERS_FILE.exists():
                    zip_file.write(newsletter.SUBSCRIBERS_FILE, "subscribers.json")
                # The earlier versions of the articles come along.
                for path_value in sorted(POSTS_DIR.glob(".history/*/*.json")):
                    zip_file.write(path_value, path_value.relative_to(POSTS_DIR.parent).as_posix())
            # We add the configuration, if it exists.
            if CONFIG_FILE.exists():
                zip_file.write(CONFIG_FILE, "config.json")
            # The uploaded images and videos, under the path they are
            # published at, so unpacking the archive in output/ restores them.
            if MEDIA_DIR.exists():
                for path_value in sorted(MEDIA_DIR.iterdir()):
                    if path_value.is_file() and not path_value.name.startswith("."):
                        zip_file.write(path_value, "media/" + path_value.name,
                                       compress_type=zipfile.ZIP_STORED)

        size = archive.tell()
        archive.seek(0)
        # File name with today's date.
        oggi = datetime.now().strftime("%Y-%m-%d")
        file_name = "pyblog-backup-" + oggi + ".zip"

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="' + file_name + '"')
        self.send_header("Content-Length", str(size))
        self._security_headers(False)
        self.end_headers()
        while True:
            chunk = archive.read(1024 * 1024)
            if not chunk:
                break
            self.wfile.write(chunk)
        archive.close()

    # --- POST ---------------------------------------------------------------

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        la = admin_language()
        # One handler instance serves every request of a keep-alive
        # connection, so the form stashed by the CSRF check must not survive
        # into the next request.
        self._pending_form = None

        # --- Authentication routes (reachable without being logged in) ---
        # They carry no CSRF token because there is no session yet, and
        # neither of them can change existing content.
        if route == "/set-password":
            self._handle_set_password()
            return
        if route == "/login":
            self._handle_login()
            return

        # --- The newsletter's public forms (readers, not the author) ---
        if route in ("/iscriviti", "/conferma", "/disiscrivi"):
            self._handle_newsletter_post(route)
            return

        # --- From here on everything requires authentication ---
        if not self._user_is_authenticated():
            self._send_json({"ok": False, "error": T("err_unauthorized", la)})
            return

        # --- ...and a valid CSRF token ---
        # A session cookie alone proves the browser is logged in, not that the
        # request came from one of our pages. Another site can make the browser
        # send the cookie; only our pages know this token.
        if route in CSRF_PROTECTED_ROUTES:
            if not self._csrf_token_ok(route):
                if route == "/change-password":
                    self._send(change_password_page(self._csrf(), T("err_csrf", la)))
                else:
                    self._send_json({"ok": False, "error": T("err_csrf", la)})
                return

        # The password change (a form) and the upload (multipart) have their
        # own handlers: neither of them speaks JSON.
        if route == "/change-password":
            self._handle_change_password()
            return
        if route == "/upload":
            self._handle_upload()
            return
        if route == "/import-docx":
            self._handle_import_docx()
            return
        if route == "/preview":
            self._handle_preview_post()
            return

        data, error = self._read_json_body()
        if error is not None:
            self._send_json({"ok": False, "error": error})
            return

        handlers = {
            "/translate": self._api_translate,
            "/generate-description": self._api_generate_description,
            "/generate-preview": self._api_generate_preview,
            "/analyze-seo": self._api_analyze_seo,
            "/save": self._api_save,
            "/delete": self._api_delete,
            "/admin-language": self._api_admin_language,
            "/toggle-status": self._api_toggle_status,
            "/save-config": self._api_save_config,
            "/save-config-raw": self._api_save_config_raw,
            "/rebuild": self._api_rebuild,
            "/newsletter-prova": self._api_newsletter_test,
            "/newsletter-rimuovi": self._api_newsletter_remove,
        }
        handler = handlers.get(route)
        if handler is None:
            self.send_error(404)
            return
        try:
            self._send_json(handler(data))
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)})

    def _csrf_token_ok(self, route):
        """
        Check the CSRF token of a state-changing request.
        The fetch() calls send it in the X-CSRF-Token header; the password
        form, which is a plain HTML form, sends it as a hidden field.
        """
        submitted = self.headers.get("X-CSRF-Token", "")
        if submitted == "" and route in ("/change-password", "/preview"):
            # A form body can only be read once, so we keep it for the handler.
            self._pending_form = self._read_form()
            submitted = self._pending_form.get("csrf_token", [""])[0]
        return csrf_token_is_valid(self._read_cookie_token(), submitted)

    # --- JSON API endpoints -------------------------------------------------

    def _api_translate(self, data):
        """Translate a piece of text with the configured service."""
        return translate_text(data.get("text", ""))

    def _api_generate_description(self, data):
        """Generate an SEO description from the article content with AI."""
        return generate_seo_description(data.get("content", ""), data.get("title", ""))

    def _api_generate_preview(self, data):
        """Generate the narrative reader preview with AI."""
        return generate_reader_preview(data.get("content", ""), data.get("title", ""))

    def _api_analyze_seo(self, data):
        """Full SEO / AI-SEO analysis of the article with the LLM."""
        return analyze_article_seo(
            data.get("content", ""),
            data.get("title", ""),
            data.get("slug", ""),
            data.get("tags", ""),
            data.get("description", ""))

    def _api_save(self, data):
        """
        Save an article and rebuild the site.

        An empty original_slug means the article has never been saved: if its
        slug belongs to another article it gets a free one instead, and the
        editor is told so. A rename onto another article's slug is refused.
        """
        la = admin_language()
        old_slug = str(data.get("original_slug", "") or "").strip()
        with BUILD_LOCK:
            try:
                new_slug = save_article(data, new_article=(old_slug == ""))
            except SlugTakenError as error:
                return {"ok": False,
                        "error": T("err_slug_taken", la).replace("{slug}", error.slug)}
            # If the slug has changed, remove the old file.
            if old_slug and old_slug != new_slug:
                delete_article(old_slug)
            build()  # rebuilds the static HTML right away
        self._announce([new_slug])
        # The address of the public page, for the editor's "View online".
        result = {"ok": True, "slug": new_slug,
                  "url": build_module.article_url({"slug": new_slug}, main_language())}
        wanted = requested_slug(data)
        if old_slug == "" and new_slug != wanted:
            result["notice"] = (T("js_slug_was_taken", la)
                                .replace("{slug}", wanted).replace("{new}", new_slug))
        return result

    def _api_delete(self, data):
        """Delete an article and rebuild the site."""
        with BUILD_LOCK:
            deleted = delete_article(str(data.get("slug", "")))
            build()
        if not deleted:
            # Saying "done" for an article that is still there is how a
            # deletion used to fail without anybody noticing.
            return {"ok": False,
                    "error": T("err_article_not_found", admin_language())}
        return {"ok": True}

    def _api_admin_language(self, data):
        """Change the language of the administration interface and save it."""
        new_language = data.get("language", "it")
        if new_language not in ("it", "en"):
            new_language = "it"
        with BUILD_LOCK:
            config_attuale = load_config()
            config_attuale["admin_language"] = new_language
            save_config(config_attuale)
            reload_global_config()
        return {"ok": True}

    def _api_toggle_status(self, data):
        """
        Change an article's status (published <-> draft) without having to
        open the editor: load it, change the status, save and rebuild.
        """
        new_status = data.get("status", "")
        if new_status not in ("draft", "published"):
            return {"ok": False, "error": T("js_status_change_error", admin_language())}
        with BUILD_LOCK:
            article = load_article(str(data.get("slug", "")))
            if article is None:
                return {"ok": False,
                        "error": T("err_article_not_found", admin_language())}
            article["status"] = new_status
            save_article(article)
            build()
        self._announce([article["slug"]])
        return {"ok": True}

    def _announce(self, slugs):
        """
        Hand the articles just published to the newsletter, which sends each
        one the first time only, and wake the sending thread.
        """
        newsletter.notify_published(slugs)
        if NEWSLETTER_WAKE is not None:
            NEWSLETTER_WAKE.set()

    def _api_newsletter_test(self, data):
        """A test email with the values of the form, saved or not."""
        values = dict(newsletter.settings({"newsletter": data}))
        if values["smtp_password"] == "" and data.get("keep_password", True):
            values["smtp_password"] = newsletter.settings()["smtp_password"]
        if not newsletter.valid_email(values["sender_email"]) or values["smtp_host"] == "":
            return {"ok": False, "error": T("admin_nl_mittente_email", admin_language()) + " / "
                    + T("admin_nl_smtp_host", admin_language())}
        try:
            newsletter.send_test(values, values["sender_email"])
        except (OSError, newsletter.smtplib.SMTPException) as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "to": values["sender_email"]}

    def _api_newsletter_remove(self, data):
        """Remove a subscriber from the Settings."""
        return {"ok": newsletter.remove(str(data.get("email", "")))}

    def _api_save_config(self, data):
        """Save the settings form and rebuild the site."""
        if "custom_code" in data:
            data["custom_code"] = with_snippet_ids(data["custom_code"])
        with BUILD_LOCK:
            # IMPORTANT: we merge with the existing configuration instead of
            # overwriting it. The form of the Settings page does not contain
            # ALL the fields (e.g. admin_language): without this merge, every
            # save would wipe them.
            config_attuale = load_config()
            # The moment the newsletter is switched on: only what is
            # published from then on goes to the subscribers.
            nuova = data.get("newsletter")
            if isinstance(nuova, dict):
                vecchia = config_attuale.get("newsletter", {})
                if not isinstance(vecchia, dict):
                    vecchia = {}
                since = vecchia.get("enabled_since", "")
                if nuova.get("enabled") is True and since == "":
                    since = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                nuova["enabled_since"] = since
                # An empty password field keeps the saved password.
                if nuova.get("smtp_password", "") == "" and vecchia.get("smtp_password"):
                    nuova["smtp_password"] = vecchia["smtp_password"]
            for key in data:
                config_attuale[key] = data[key]
            save_config(config_attuale)
            reload_global_config()
            build()  # rebuilds the site with the new configuration
        return {"ok": True}

    def _api_save_config_raw(self, data):
        """
        Save the hand-edited config.json as raw text.
        We validate the JSON BEFORE saving: if it is malformed we reject it
        with a clear message, so the site does not break.
        """
        la = admin_language()
        config_text = data.get("content", "")
        # We try to parse the text as JSON: if it fails,
        # the error tells us the line and column of the problem.
        try:
            config_validata = json.loads(config_text)
        except json.JSONDecodeError as json_error:
            return {"ok": False,
                    "error": T("err_invalid_json_prefix", la) + str(json_error)}
        # It must be an object (a dictionary), not a list or anything else.
        if not isinstance(config_validata, dict):
            return {"ok": False, "error": T("err_config_must_be_object", la)}
        with BUILD_LOCK:
            save_config(config_validata)
            reload_global_config()
            build()
        return {"ok": True}

    def _api_rebuild(self, data):
        """Rebuild the static site on demand."""
        return {"ok": True, "articles": build()}

    # --- Password and upload ------------------------------------------------

    def _handle_preview_post(self):
        """
        The preview of the article as it is in the editor, unsaved.

        The editor posts its fields in a form that opens in a new tab, and the
        page comes back as a public page, without the admin CSP, which would
        block the CDNs and the custom code of the public pages. Nothing is
        written: previewing a published article must not put its half-done
        changes online.
        """
        form = self._pending_form
        if form is None:
            form = self._read_form()
        try:
            data = json.loads(form.get("data", ["{}"])[0])
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            self.send_error(400, "Article data missing or malformed.")
            return
        language = form.get("language", [main_language()])[0]
        if language not in ("it", "en"):
            language = main_language()
        self._send(generate_article_page(article_for_preview(data), language),
                   with_csp=False)

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
            self._send(set_password_page(T("err_password_too_short", la)))
            return
        if password != confirmed:
            self._send(set_password_page(T("err_passwords_dont_match_setup", la)))
            return
        set_password(password)
        token = create_session_token()
        self._redirect("/admin", cookie=self._session_cookie(token))

    def _handle_login(self):
        """Verify the password and create a session."""
        # If there have been too many errors in a row, login is locked
        # for a few moments: it makes a brute-force attack pointless.
        la = admin_language()
        client = self._client_address()
        if login_is_locked(client):
            self._send(login_page(
                T("err_too_many_attempts", la).replace("{n}", str(login_lock_remaining(client)))))
            return
        form = self._read_form()
        password = form.get("password", [""])[0]
        if verify_password(password):
            record_successful_login(client)
            token = create_session_token()
            self._redirect("/admin", cookie=self._session_cookie(token))
        else:
            record_failed_login(client)
            # A small pause: it slows automated attempts down even further.
            time.sleep(0.5)
            self._send(login_page(T("err_wrong_password", la)))

    def _handle_change_password(self):
        """Change the password while logged in."""
        # The CSRF check already read the form body; reading it again would
        # block, because the socket has no bytes left.
        form = getattr(self, "_pending_form", None)
        if form is None:
            form = self._read_form()
        self._pending_form = None

        attuale = form.get("attuale", [""])[0]
        new_value = form.get("nuova", [""])[0]
        confirmed = form.get("conferma", [""])[0]
        la = admin_language()
        csrf = self._csrf()

        if not verify_password(attuale):
            self._send(change_password_page(csrf, T("err_current_password_wrong", la)))
            return
        if len(new_value) < 6:
            self._send(change_password_page(csrf, T("err_new_password_too_short", la)))
            return
        if new_value != confirmed:
            self._send(change_password_page(csrf, T("err_new_passwords_dont_match", la)))
            return

        set_password(new_value)
        # Every existing session is invalidated and a fresh one is issued:
        # whoever knew the old password must not keep a working session, and
        # the new session gets a new CSRF token as well.
        destroy_all_sessions()
        token = create_session_token()
        page = change_password_page(csrf_token_for(token), "",
                                    T("success_password_changed", la))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Set-Cookie", self._session_cookie(token))
        self._security_headers(True)
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def _handle_upload(self):
        """
        Receive a file uploaded from the editor (multipart/form-data),
        validate it and save it into the media folder, then return its URL.

        The Content-Length is checked before the body is read at all, so an
        oversized upload never reaches memory. The per-type limit (10 MB for
        an image, 100 MB for a video) is applied right after, once the file
        name tells us which kind of file this is.
        """
        la = admin_language()
        try:
            content_type = self.headers.get("Content-Type", "")

            # In a multipart body, the header contains the "boundary" that
            # separates the parts of the form. We extract it to split the body.
            if "boundary=" not in content_type:
                self._send_json({"ok": False, "error": T("err_invalid_format", la)})
                return
            boundary = content_type.split("boundary=")[1].strip()
            # A quoted boundary is legal: boundary="----abc".
            boundary = boundary.strip('"')
            if boundary == "":
                self._send_json({"ok": False, "error": T("err_invalid_format", la)})
                return
            boundary_bytes = ("--" + boundary).encode("utf-8")

            length = self._content_length(MAX_UPLOAD_BODY)
            if length is None:
                self._send_json({
                    "ok": False,
                    "error": T("err_file_too_large", la).replace(
                        "{n}", str(MAX_UPLOAD_BODY // (1024 * 1024)))})
                return
            body = self.rfile.read(length)

            file_name, file_data = self._parse_multipart_file(body, boundary_bytes)
            if file_name is None:
                self._send_json({"ok": False, "error": T("err_malformed_upload", la)})
                return
            if file_name == "":
                self._send_json({"ok": False, "error": T("err_no_file_received", la)})
                return

            check = validate_upload(file_name, file_data)
            if not check["ok"]:
                message = T(check["error_key"], la)
                if "limit_mb" in check:
                    message = message.replace("{n}", str(check["limit_mb"]))
                self._send_json({"ok": False, "error": message})
                return

            url = save_uploaded_file(file_name, check["data"])
            self._send_json({"ok": True, "url": url,
                             "note": optimisation_note(check.get("optimisation"), la)})

        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_import_docx(self):
        """
        Receive a .docx uploaded from the editor, convert it and hand the
        result back as JSON. Nothing is saved: the browser drops the title and
        the HTML into the form, and the author decides whether to keep them.

        The body is capped at 30 MB before it is read, and the first bytes
        must be a ZIP signature: a .doc, a PDF or a renamed executable is
        refused before the converter ever sees it.
        """
        la = admin_language()
        try:
            content_type = self.headers.get("Content-Type", "")
            if "boundary=" not in content_type:
                self._send_json({"ok": False, "error": T("err_invalid_format", la)})
                return
            boundary = content_type.split("boundary=")[1].strip().strip('"')
            if boundary == "":
                self._send_json({"ok": False, "error": T("err_invalid_format", la)})
                return

            length = self._content_length(MAX_DOCX_BODY)
            if length is None:
                self._send_json({
                    "ok": False,
                    "error": T("err_file_too_large", la).replace(
                        "{n}", str(MAX_DOCX_BODY // (1024 * 1024)))})
                return
            body = self.rfile.read(length)

            file_name, file_data = self._parse_multipart_file(
                body, ("--" + boundary).encode("utf-8"))
            if file_name is None:
                self._send_json({"ok": False, "error": T("err_malformed_upload", la)})
                return
            if file_name == "":
                self._send_json({"ok": False, "error": T("err_no_file_received", la)})
                return
            if not file_name.lower().endswith(".docx"):
                self._send_json({"ok": False, "error": T("js_docx_wrong_extension", la)})
                return
            if not looks_like_docx(file_data):
                self._send_json({"ok": False, "error": T("err_docx_not_a_zip", la)})
                return

            fallback_title = file_name.rsplit(".", 1)[0]
            # Extracting the images writes into the media folder, so the
            # conversion takes the same lock as a save.
            with BUILD_LOCK:
                result = convert_docx(file_data, fallback_title=fallback_title)

            if not result["ok"]:
                self._send_json({"ok": False, "error": T(result["error_key"], la)})
                return

            self._send_json({
                "ok": True,
                "title": result["title"],
                "subtitle": result.get("subtitle", ""),
                "content": result["content"],
                "warnings": translate_warnings(result["warnings"], la),
            })
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)})

    def _parse_multipart_file(self, body, boundary_bytes):
        """
        Pull the first uploaded file out of a multipart body.

        Return (file_name, data), ("", b"") when the body is well formed but
        carries no file, or (None, b"") when the body is malformed. Only the
        shape we produce ourselves is accepted; anything else is refused
        rather than guessed at.
        """
        if not body.startswith(boundary_bytes):
            return None, b""

        blocks = body.split(boundary_bytes)
        separatore = b"\r\n\r\n"

        for block in blocks:
            if b"filename=" not in block:
                continue
            # We separate the block headers from the binary content.
            # They are divided by an empty line (\r\n\r\n).
            posizione = block.find(separatore)
            if posizione == -1:
                continue
            intestazioni = block[:posizione].decode("utf-8", "ignore")
            content = block[posizione + len(separatore):]

            # We remove the trailing \r\n that precedes the next boundary.
            if content.endswith(b"\r\n"):
                content = content[:-2]

            # We extract the file name from the header.
            pieces = intestazioni.split('filename="')
            if len(pieces) < 2:
                continue
            resto = pieces[1]
            end = resto.find('"')
            if end == -1:
                return None, b""
            return resto[:end], content

        return "", b""

    def log_message(self, *args):
        pass  # silences the request log


def public_site_url(fallback):
    """
    The site's address for the links in the emails: the domain of the
    Settings, or - while it is still empty or the example one - the address
    the editor is reached at, which at least works for a try on a computer.
    """
    base = CONFIG.get("base_url", "").rstrip("/")
    if base != "" and "tuodominio" not in base and "mysite" not in base:
        return base
    return fallback


# Set by serve(): wakes the newsletter's sending thread when an article is
# published, instead of waiting for its next round.
NEWSLETTER_WAKE = None

# How often the editor looks for scheduled articles whose moment has come.
SCHEDULE_CHECK_SECONDS = 60


def publish_when_due(stop):
    """
    The scheduler: while the editor runs, a scheduled article goes out
    within a minute of its moment, with nobody at the keyboard. The check
    is a scan of the articles, the build happens only when one is due.
    """
    while not stop.wait(SCHEDULE_CHECK_SECONDS):
        try:
            if due_scheduled_articles():
                with BUILD_LOCK:
                    published = publish_due_articles()
                    build()
                newsletter.notify_published(published)
                if NEWSLETTER_WAKE is not None:
                    NEWSLETTER_WAKE.set()
        except Exception as error:  # the scheduler must never stop the editor
            print(f"WARNING: scheduled publishing failed ({error}).")


def serve(host="127.0.0.1", port=PORT):
    """
    Start the editor server. For safety it listens ONLY on localhost: the
    administration area must not be reachable from the local network or
    from the internet. To expose it (e.g. behind a reverse proxy) you can
    pass a different host: python3 pyblog.py serve 8000 0.0.0.0

    The server is threaded, so a long request (an LLM call taking a minute)
    no longer freezes every other tab. The writes that a thread can perform -
    saving an article, saving the configuration, rebuilding - are serialised
    by BUILD_LOCK.
    """
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build()  # generates the initial state

    # Lets you restart the server right away without the "port busy" error.
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer((host, port), Handler) as httpd:
        print("\n  PyBlog - writing desk")
        print(f"  Open:  http://localhost:{port}/\n")
        if host not in ("127.0.0.1", "localhost"):
            print(f"  WARNING: the server is listening on {host}: the editor is")
            print("  reachable from other devices on the network too.\n")
        print(f"  Articles are saved in:       {POSTS_DIR}")
        print(f"  Static HTML is generated in: {OUTPUT_DIR}")
        print("  (Ctrl+C to stop)\n")
        stop = threading.Event()
        threading.Thread(target=publish_when_due, args=(stop,), daemon=True).start()
        global NEWSLETTER_WAKE
        NEWSLETTER_WAKE = threading.Event()
        # The links in the emails need the site's address; on a computer
        # without one, the editor's own address will do for a try.
        threading.Thread(target=newsletter.sender_loop,
                         args=(stop, lambda: public_site_url(f"http://localhost:{port}"),
                               NEWSLETTER_WAKE),
                         daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
        finally:
            stop.set()
