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
import os
import pathlib
import secrets
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from core import build as build_module
from core import (__version__, backup, i18n, media_library, newsletter, render,
                  settings_panel, updates)
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
                         POSTS_DIR, admin_address, admin_language, load_config,
                         main_language, reload_global_config, save_config,
                         secondary_language, url_host)
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
# The readers' pages of the newsletter, and the Italian addresses they had
# before: emails already sent and cached pages still use those.
NEWSLETTER_ROUTES = ("/subscribe", "/confirm", "/unsubscribe")
LEGACY_NEWSLETTER_ROUTES = {"/iscriviti": "/subscribe", "/conferma": "/confirm",
                            "/disiscrivi": "/unsubscribe"}

# The words the server is waiting to hear back from /pyblog-ping, while it
# checks a new address for the administration.
PING_NONCES = set()
PING_LOCK = threading.Lock()

# The policy of a public page shown by the editor: scripts, forms and
# popups work, but the page gets an origin of its own (no allow-same-origin).
PREVIEW_SANDBOX = "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"

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
# A backup holds every medium of the site, videos included.
MAX_BACKUP_BODY = 2 * 1024 * 1024 * 1024   # 2 GB

# The POST endpoints of the logged-in author. Every one of them is checked
# against the CSRF token, and so is any route added later: do_POST checks the
# token before it even looks the route up, so forgetting to list a new
# endpoint here cannot leave it unprotected. /login, /set-password and the
# newsletter forms are absent on purpose: there is no session yet, so there is
# no token to check, and none of them can act on existing data.
CSRF_PROTECTED_ROUTES = (
    "/save", "/delete", "/save-config", "/save-config-raw", "/toggle-status",
    "/rebuild", "/upload", "/admin-language", "/change-password",
    "/translate", "/generate-description", "/generate-preview", "/analyze-seo",
    "/import-docx", "/preview", "/newsletter-test", "/newsletter-remove",
    "/check-admin-address", "/restore", "/restore-automatic",
    "/media-library-delete", "/update", "/updates-auto",
)

# The files the administration area serves from static/. Naming them makes
# the route an allowlist rather than a path check.
ADMIN_STATIC_FILES = ("common.css", "admin.css", "admin.js")

# The GET routes handled by the administration, as opposed to the static site.
ADMIN_GET_ROUTES = ("/admin", "/config", "/edit", "/change-password",
                    "/preview", "/export", "/pick-point", "/versions",
                    "/version", "/newsletter-subscribers.csv", "/restore",
                    "/automatic-backup", "/media-library", "/updates",
                    "/updates-status", "/media-library-items")


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
    "admin_table_of_the_row", "admin_table_add_col", "admin_table_of_the_col",
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
    # The one-line summaries of the editor's groups
    "js_summary_without_tag", "js_summary_cover", "js_summary_part", "js_summary_missing_one_description",
    "js_summary_description_ok", "js_summary_not_translated_m", "js_summary_draft_translation_of",
    "js_summary_translation_of_ok",
    # Translation
    "js_translating", "js_translated_review", "js_check_api_key",
    "js_net_error_translation", "js_write_intro_first", "js_translated_home",
    "js_translated_site_texts", "js_write_site_texts_first",
    "js_admin_url_not_valid", "js_admin_url_unreachable",
    "js_admin_url_confirm_title", "js_admin_url_confirm_body", "js_admin_url_confirm",
    "js_choose_backup", "js_restoring_title", "js_restoring_body", "js_restoring_confirm",
    "js_restoring_automatic_body", "js_restoring_in_progress", "js_restoring_made",
    "js_restoring_ignored", "js_restoring_failure_rete",
    "js_media_copied", "js_media_delete_title", "js_media_delete_body",
    "js_media_delete_used", "js_media_cleanup_body", "js_media_uploading",
    "upd_checking", "upd_installation", "upd_restarting", "upd_restarted", "upd_confirm_title",
    "upd_confirm_body", "admin_update_now", "upd_offline",
    "js_media_picker_title", "js_media_picker_search", "js_media_picker_empty",
    "js_media_picker_loading", "js_media_picker_error",
    "js_image_details_title", "js_image_alt_label", "js_image_alt_hint", "js_image_caption_label",
    "js_image_caption_hint", "js_image_details_apply", "js_image_alt_missing", "js_image_alt_missing_one",
    "js_media_recovered",
    # Settings
    "admin_code_title", "admin_code_delete",
    "admin_saving", "admin_config_saved_f", "admin_failure_saving",
    "admin_config_raw_saved_f", "err_invalid_json_prefix",
    # Custom code: the folded summary of a card, the ready-made templates,
    # the consent banner
    "admin_code_active", "admin_code_off_m", "admin_code_without_name",
    "consent_necessary", "consent_statistics", "consent_marketing",
    "js_template_field_ga4", "js_template_field_gtm", "js_template_field_pub",
    "js_template_field_slot", "js_template_field_aw", "js_template_field_pixel",
    "js_template_field_clarity", "js_template_not_valid", "js_template_created",
    "js_template_ads_txt", "js_template_ga4_double", "js_consent_renewed",
    # Shared dialogs, saving, autosave and the Word import
    "admin_close", "admin_cancel", "admin_delete",
    "js_save_error", "js_unsaved_changes", "js_slug_was_taken",
    "js_autosaving", "js_autosaved_at", "js_autosave_failed",
    "js_autosave_needs_title", "js_delete_title", "js_delete_body",
    "js_site_rebuilt_error",
    "js_docx_importing", "js_docx_imported", "js_docx_net_error",
    "js_docx_overwrite_title", "js_docx_overwrite_body",
    "js_docx_overwrite_confirm", "js_docx_warnings_title",
    "js_docx_wrong_extension", "err_file_too_large",
    # Editor: publishing, the state of the article
    "admin_publish", "admin_withdraw", "js_draft_saved_f", "js_published",
    "js_updated", "js_withdrawn", "js_publish_title", "js_publish_body",
    "js_withdraw_title", "js_withdraw_body", "js_title_for_to_publish",
    "js_changes_made_from_to_save", "admin_cancel_changes_made",
    "js_cancel_changes_made_title", "js_cancel_changes_made_body",
    "js_settings_page_not_saved_pl", "admin_project_without_name",
    "admin_project_delete", "js_updated_at",
    "js_schedule_title", "js_schedule_body", "js_schedule_data",
    "js_scheduled", "js_scheduling_cancelled", "js_changes_made_saved_pl",
    "admin_publish_now", "admin_schedule_cancel", "admin_goes_out_the",
    "admin_schedule_confirm", "js_saved_at",
    "admin_versions", "js_versions_empty_m", "js_version_show",
    "js_version_restore", "js_version_restored_f", "js_version_words",
    "js_version_failure", "js_version_lose", "admin_state_draft",
    "admin_state_published", "admin_state_scheduled", "admin_close",
    "js_version_choose",
    "js_nl_test_ok", "js_nl_test_failure", "js_nl_remove_title", "js_nl_removed",
    "admin_nl_remove",
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
        return (T("img_resized_f", language)
                .replace("{da}", da).replace("{a}", a).replace("{n}", str(saved_kb)))
    if action == "stripped" and saved_kb > 0:
        return T("img_metadata_removed_pl", language).replace("{n}", str(saved_kb))

    reason = optimisation.get("reason", "")
    if reason == "jpeg_not_resizable":
        return T("img_jpeg_not_resizable", language)
    if reason == "too_many_pixels":
        return T("img_too_many_pixel", language)
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
    return (f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" '
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
ICON_RESTORE = '<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>'
ICON_UPDATE = '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/><path d="M12 8v5l3 2"/>'
ICON_MEDIA = ('<rect x="3" y="4" width="18" height="16" rx="2"/>'
              '<circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5L5 20"/>')
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
ICON_AI_SPARKLE = ('<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/>'
                   '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>')

# The sections of the Settings page, in the order of the panel, as (id,
# i18n key of the name). They are described in core/settings_panel.py.
CONFIG_SECTIONS = [(entry["id"], entry["label"]) for entry in settings_panel.SECTIONS]
ICON_WARN = ('<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5h.01"/>')
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

    # The last field says whether the item is also in the phone's bar, which
    # has room for four: the others are in the menu "More" opens.
    voci = [
        ("articles", "/admin", ICON_ARTICLES, T("admin_articles", language),
         T("admin_articles", language), str(articles_count), True),
        ("new", "/edit", ICON_NEW, T("admin_new_article_title", language),
         T("admin_new", language), "", True),
        ("media", "/media-library", ICON_MEDIA, T("admin_media_library", language),
         T("admin_media_library", language), "", False),
        ("config", "/config", ICON_SETTINGS, T("admin_settings_page", language),
         T("admin_settings_page", language), "", True),
    ]
    menu_html = []
    bar_html = []
    for key, url, path, label, short_label, count, in_bar in voci:
        current = ""
        if key == active_page:
            current = ' aria-current="page"'
        count_html = ""
        if count != "":
            count_html = f'<span class="item-count">{count}</span>'
        # The Settings item stays one line: its sections are in the panel
        # it opens, each with what it is for and how it stands.
        menu_html.append(
            f'    <a class="item"{current} href="{url}">{icon(path)}'
            f'<span class="item-text">{label}</span>{count_html}</a>')
        if in_bar:
            bar_html.append(
                f'  <a class="bar-item"{current} href="{url}">{icon(path, 22)}'
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
        title_site=esc(CONFIG["site_title"]),
        entries="\n".join(menu_html),
        entries_bar="\n".join(bar_html),
        label_tools=T("admin_tools", language),
        icon_rebuild=icon(ICON_REBUILD),
        label_rebuild=T("admin_rebuild", language),
        desc_rebuild=T("admin_rebuild_desc", language),
        desc_backup=T("admin_backup_desc", language),
        desc_see_site=T("admin_see_site_desc", language),
        icon_backup=icon(ICON_BACKUP),
        label_backup=T("admin_download_backup", language),
        icon_restoring=icon(ICON_RESTORE),
        label_restoring=T("admin_restore_backup", language),
        desc_restoring=T("admin_restore_backup_desc", language),
        current_item_restoring=' aria-current="page"' if active_page == "restore" else "",
        icon_updates=icon(ICON_UPDATE),
        label_updates=T("admin_updates", language),
        desc_updates=T("admin_version", language).replace("{v}", __version__),
        current_item_updates=' aria-current="page"' if active_page == "updates" else "",
        icon_blog=icon(ICON_BLOG),
        label_see_blog=T("admin_see_blog", language),
        label_new_f_card=T("admin_new_f_card", language),
        current_item_password=current_password,
        icon_password=icon(ICON_PASSWORD),
        label_password=T("admin_change_password", language),
        next_f_language=next_language,
        icon_language=icon(ICON_LANGUAGE),
        name_next_f_language=next_language_name,
        label_language=esc(T("admin_language_interface", language)),
        icon_logout=icon(ICON_LOGOUT),
        label_logout=T("admin_logout", language),
        icon_other=icon(ICON_MORE, 22),
        label_other=T("admin_other", language),
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
        skip_link = (f'<a class="skip-content" href="#content">'
                     f'{T("admin_skip_content", language)}</a>\n')
        body_class = (body_class + " with-menu").strip()
    return render.render(
        "admin/base.html",
        lang=language,
        title_page=esc(titolo),
        bootstrap_css=BOOTSTRAP_CSS,
        bootstrap_js=BOOTSTRAP_JS,
        head_extra=build_module.block(head_extra),
        css_class_body=body_class,
        skip_content=skip_link,
        navbar=build_module.block(navbar),
        label_close=T("admin_close", language),
        label_cancel=T("admin_cancel", language),
        content=contenuto,
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
    return ('      <label class="row-flag notify-subscribers only-not-published">'
            f'<input type="checkbox" id="notify_subscribers" {checked}> '
            f'{T("admin_nl_notify", la)}</label>\n')


def moment_html(moment, la):
    """
    "goes out on <date>" for a scheduled article. The date is written by
    admin.js in the reader's own time zone and language; the text inside is
    what shows without JavaScript, in UTC.
    """
    if moment == "":
        return ""
    fallback = moment.replace("T", " ")[:16] + " UTC"
    return T("admin_goes_out_the", la).replace(
        "{date}", f'<time class="now-local" datetime="{esc(moment)}">{esc(fallback)}</time>')


def alert_block(message, kind):
    """A message above a form ("danger" or "success"), or nothing."""
    if message == "":
        return ""
    role = "alert" if kind == "danger" else "status"
    return f'<p class="notice notice-{kind}" role="{role}">{esc(message)}</p>'


def login_page(error_message=""):
    """Login page to access the administration area."""
    la = admin_language()
    contenuto = render.render(
        "admin/login.html",
        title=T("admin_area_reserved", la),
        invitation=T("admin_login_invitation", la),
        failure=alert_block(error_message, "danger"),
        label_password=T("admin_password", la),
        login=T("admin_login", la),
    )
    return admin_page_shell(T("admin_area_reserved", la), contenuto, la)


def set_password_page(error_message=""):
    """Page shown on first run to create the administration password."""
    la = admin_language()
    contenuto = render.render(
        "admin/set_password.html",
        title=T("admin_create_password_title", la),
        invitation=T("admin_create_password_invitation", la),
        failure=alert_block(error_message, "danger"),
        label_new_f=T("admin_new_f_password", la),
        label_confirm=T("admin_confirm_password", la),
        hint_length_of=T("admin_password_length_of", la),
        create_login=T("admin_create_login", la),
    )
    return admin_page_shell(T("admin_create_password_title", la), contenuto, la)


def change_password_page(csrf, error_message="", success_message=""):
    """Page to change the password while logged in."""
    la = admin_language()
    contenuto = render.render(
        "admin/change_password.html",
        title=T("admin_change_password", la),
        subtitle=T("admin_change_password_desc", la),
        hint_length_of=T("admin_password_length_of", la),
        failure=alert_block(error_message, "danger"),
        success=alert_block(success_message, "success"),
        csrf_token=esc(csrf),
        label_current=T("admin_password_current", la),
        label_new_f=T("admin_new_f_password", la),
        label_confirm=T("admin_confirm_new_f", la),
    )
    return admin_page_shell(T("admin_change_password", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("password", la))


def updates_state(force=False):
    """
    The state of updates for the browser, with the sentences already
    written: what the page shows, and whether the dashboard should say
    something.
    """
    la = admin_language()
    try:
        result = updates.check(force=force)
    except Exception:
        result = {"error": "upd_offline", "version": __version__,
                  "auto": updates.automatic_check_enabled()}
    message = ""
    available = False
    if result.get("error"):
        message = T(result["error"], la)
    elif result.get("kind") == "git":
        if result.get("behind", 0) > 0:
            available = True
            message = T("upd_news", la).replace("{n}", str(result["behind"]))
            if result.get("dirty"):
                message = message + " " + T("upd_changes_made_local_edits", la)
            elif result.get("ahead"):
                message = message + " " + T("upd_ahead", la)
        else:
            message = T("upd_updated", la)
    elif result.get("kind") == "other":
        if result.get("behind"):
            available = True
            message = (T("upd_version", la).replace("{v}", result.get("latest", ""))
                       .replace("{c}", __version__))
        else:
            message = T("upd_updated", la)
    else:
        message = T("upd_never_checked", la)
    return {"ok": True, "message": message, "available": available,
            "can_update": result.get("can_update") is True,
            "news": result.get("news", []) if result.get("kind") == "git" else [],
            "instructions": result.get("kind") == "other" and available,
            "auto": result.get("auto", True), "version": __version__}


def updates_page(csrf):
    """The Updates page: the version, what is new, and the update button."""
    la = admin_language()
    contenuto = render.render(
        "admin/updates.html",
        title=T("admin_updates", la),
        version_installed=T("admin_version_installed", la).replace("{v}", __version__),
        label_state=T("admin_updates_state", la),
        label_checking=T("upd_checking", la),
        instructions=T("upd_instructions", la).replace("{url}", updates.CHANGELOG_URL),
        label_update=T("admin_update_now", la),
        label_check_now=T("admin_check_now_now", la),
        hint_update=T("admin_update_hint", la),
        label_automatic=T("admin_checking_automatic_title", la),
        label_checking_automatic=T("admin_checking_automatic", la),
        hint_checking_automatic=T("admin_checking_automatic_hint", la),
        checked_automatic=checked_if(updates.automatic_check_enabled()),
    )
    return admin_page_shell(T("admin_updates", la), contenuto, la, csrf=csrf,
                            navbar=admin_navbar("updates", la), page_data={"page": "updates"})


def file_size_text(size):
    """A file size for people: KB under a megabyte, MB with one decimal above."""
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def media_library_items():
    """
    The uploaded files for the editor's picker, newest first: name, address,
    kind and how many places use each. The addresses are built from names
    the library already checked, so they can go into the editor as they are.
    """
    uses = media_library.media_uses()
    items = [{"name": item["name"], "url": "/media/" + item["name"], "kind": item["kind"],
              "size": file_size_text(item["size"]), "used": len(uses.get(item["name"], []))}
             for item in media_library.media_files()]
    return {"ok": True, "items": items}


def library_page(csrf):
    """
    The media library: every uploaded file with where it is used, to copy
    its address, upload new ones and clear out the ones nothing uses.
    """
    la = admin_language()
    files = media_library.media_files()
    uses = media_library.media_uses()
    cards = []
    unused_size = 0
    unused_count = 0
    for item in files:
        name = item["name"]
        where = uses.get(name, [])
        if not where:
            unused_size += item["size"]
            unused_count += 1
        address = "/media/" + name
        if item["kind"] == "video":
            preview = f'<video src="{esc(address)}" preload="metadata" muted></video>'
        else:
            preview = f'<img src="{esc(address)}" alt="" loading="lazy">'
        if where:
            links = []
            for use in where:
                if use["kind"] == "article":
                    links.append(f'<a href="/edit?slug={esc(use["slug"])}">{esc(use["title"])}</a>')
                else:
                    links.append(f'<a href="/config">{T("admin_settings_page", la)}</a>')
            usage = f'{T("admin_media_used_f_in", la)} ' + ", ".join(links)
        else:
            usage = f'<span class="media-unused">{T("admin_media_not_used_f", la)}</span>'
        cards.append(
            f'    <li class="media-card" data-name="{esc(name.lower())}" data-used="{1 if where else 0}" '
            f'data-where="{len(where)}">\n'
            f'      <div class="media-preview">{preview}</div>\n'
            f'      <div class="media-info">\n'
            f'        <p class="media-name">{esc(name)}</p>\n'
            f'        <p class="media-meta">{file_size_text(item["size"])} · '
            f'{item["date"].strftime("%d/%m/%Y")}</p>\n'
            f'        <p class="media-usi">{usage}</p>\n'
            f'        <div class="media-actions">'
            f'<button type="button" class="button button-small" '
            f'onclick="copyMediaAddress({js_attr(address)})">{T("admin_media_copy", la)}'
            f'<span class="vh"> {esc(name)}</span></button>'
            f'<button type="button" class="button button-small button-danger" '
            f'onclick="deleteMedia(this, {js_attr(name)}, {len(where)})">{T("admin_delete", la)}'
            f'<span class="vh"> {esc(name)}</span></button></div>\n'
            f'      </div>\n'
            f'    </li>')
    total_size = sum(item["size"] for item in files)
    summary = (T("admin_media_overview", la).replace("{n}", str(len(files)))
               .replace("{peso}", file_size_text(total_size) if files else "0 KB"))
    cleanup = (T("admin_media_cleanup", la).replace("{n}", str(unused_count))
               .replace("{peso}", file_size_text(unused_size) if unused_count else "0 KB"))
    contenuto = render.render(
        "admin/library.html",
        title=T("admin_media_library", la),
        overview=summary,
        label_upload=T("admin_media_upload", la),
        label_show=T("admin_show_group", la),
        label_all=T("admin_filter_all", la),
        total=len(files),
        label_used_pl=T("admin_media_used_pl", la),
        used_pl=len(files) - unused_count,
        label_not_used_pl=T("admin_media_not_used_pl", la),
        not_used_pl=unused_count,
        label_search=esc(T("admin_media_search", la)),
        label_cleanup=cleanup,
        cleanup_hidden_f="" if unused_count > 0 else " hidden",
        cards="\n".join(cards),
        empty_f_hidden_f="" if not files else " hidden",
        label_empty_f=T("admin_media_empty_f", la),
        label_no_one_outcome=T("admin_no_one_matches", la),
        hint_trash=T("admin_media_trash_hint", la),
    )
    return admin_page_shell(T("admin_media_library", la), contenuto, la, csrf=csrf,
                            navbar=admin_navbar("media", la),
                            page_data={"page": "library",
                                       "max_image_mb": MAX_IMAGE_BYTES // (1024 * 1024),
                                       "max_video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
                                       "max_image_width": max_image_side()})


def restore_page(csrf):
    """
    The page that puts a backup back: from a file, or from one of the
    automatic backups saved before every restore, which is how a restore
    is undone.
    """
    la = admin_language()
    rows = []
    for item in backup.automatic_backups():
        when = item["date"].strftime("%d/%m/%Y %H:%M:%S")
        size = file_size_text(item["size"])
        rows.append(
            f'      <li><span class="backup-when">{when} · {size}</span>'
            f'<span class="backup-actions">'
            f'<a class="button button-small" href="/automatic-backup?file={esc(item["name"])}">'
            f'{T("admin_download", la)}</a>'
            f'<button type="button" class="button button-small" '
            f'onclick="restoreAutomatic(this, {js_attr(item["name"])})">'
            f'{T("admin_restore_this", la)}</button></span></li>')
    if rows:
        listing = '    <ul class="list-box-backup">\n' + "\n".join(rows) + "\n    </ul>"
    else:
        listing = f'    <p class="list-empty">{T("admin_no_one_backup_automatic", la)}</p>'
    contenuto = render.render(
        "admin/restore.html",
        title=T("admin_restore_backup", la),
        subtitle=T("admin_restoring_subtitle", la),
        label_from_file=T("admin_restoring_from_file", la),
        hint_from_file=T("admin_restoring_from_file_hint", la),
        label_choose_file=T("admin_restoring_choose", la),
        label_restore=T("admin_restore_now", la),
        label_automatic_pl=T("admin_backup_automatic_pl", la),
        hint_automatic_pl=T("admin_backup_automatic_pl_hint", la),
        list_automatic_pl=listing,
    )
    return admin_page_shell(T("admin_restore_backup", la), contenuto, la, csrf=csrf,
                            navbar=admin_navbar("restore", la), page_data={"page": "restore"})


def setup_steps_html(articles, la):
    """
    The "First steps" box at the top of the dashboard: what a visitor of the
    site would notice is unfinished, each with a link to where it is fixed.
    It disappears once there is nothing left.
    """
    steps = settings_panel.setup_steps(load_config(), articles, la)
    if not steps:
        return ""
    rows = []
    for section_id, text in steps:
        if section_id == "":
            href, action, where = "/edit", T("admin_write_it", la), ""
        else:
            href, action = "/config#" + section_id, T("admin_fix", la)
            # "Off, but Google Analytics uses cookies" needs to say what is off.
            where = (f'<span class="step-where">'
                     f'{T(settings_panel.section(section_id)["label"], la)}</span> ')
        rows.append(
            f'      <li><span class="step-text">{icon(ICON_WARN, 18)}'
            f'<span>{where}{esc(text)}</span></span>'
            f'<a class="step-link" href="{href}">{action}'
            f'<span class="vh">: {esc(text)}</span>{icon(ICON_NEXT, 16)}</a></li>')
    return (
        '  <section class="first-steps" aria-labelledby="first-steps-title">\n'
        f'    <h2 id="first-steps-title">{T("admin_first_steps_of_steps", la)} '
        f'<span class="first-steps-count">{len(steps)}</span></h2>\n'
        f'    <p class="help">{T("admin_first_steps_of_steps_desc", la)}</p>\n'
        '    <ul>\n' + "\n".join(rows) + '\n    </ul>\n'
        '  </section>')


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
            pill_class = "pill-published"
            status_label = T("admin_published", la)
            # If it is published, the menu puts it back to draft. Same
            # words as the editor's link, from the same key, so the two
            # cannot drift apart again.
            status_action = "draft"
            status_action_label = T("admin_withdraw", la)
            # Sorting happens in the browser, so every row carries the keys
            # it can be sorted by. Drafts sort first, because they are the
            # ones still waiting for work.
            status_order = "1"
        elif art.get("status") == "scheduled":
            # Scheduled: it goes out by itself. The quick action publishes
            # it at once; the second one, in the menu, takes the schedule back.
            pill_class = "pill-scheduled"
            status_label = T("admin_state_scheduled", la)
            status_action = "published"
            status_action_label = T("admin_publish_now", la)
            status_order = "s"
        else:
            pill_class = "pill-draft"
            status_label = T("admin_draft", la)
            status_action = "published"
            status_action_label = T("admin_publish", la)
            status_order = "0"

        # The translated version, said in words next to the date.
        also_in = ""
        if art.get("translation_confirmed", False):
            also_in = " &middot; " + T("admin_also_in", la).replace("{language}", other_name)

        # Preview of the translated page: the link appears as soon as some
        # translated content exists (even if not confirmed yet), so that you
        # can check the translation BEFORE confirming it.
        preview_other_link = ""
        if not html_content_is_empty(art.get("content_en", "")):
            preview_label = T("admin_preview_language", la).replace("{language}", other_name)
            preview_other_link = (
                f'<a role="menuitem" tabindex="-1" '
                f'href="/preview?slug={esc(art["slug"])}&amp;language={other}" '
                f'target="_blank" rel="noopener">{preview_label}'
                f'<span class="icon-external" aria-hidden="true"></span></a>')

        # A scheduled article says when it goes out instead of its date, and
        # its menu can also take the schedule back.
        shown_date = format_date(art["date"], la)
        cancel_item = ""
        if art.get("status") == "scheduled":
            shown_date = moment_html(art.get("publish_at", ""), la)
            cancel_item = (f'<button role="menuitem" tabindex="-1" type="button" '
                           f'onclick="changeStatus(this, {js_attr(art["slug"])}, &quot;draft&quot;)">'
                           f'{T("admin_schedule_cancel", la)}</button>')

        # A plain article can get its lab from here: the editor opens on a
        # new article already tied to this one.
        lab_item = ""
        if art.get("kind", "") == "":
            lab_item = (f'<a role="menuitem" tabindex="-1" '
                        f'href="/edit?lab_of={esc(art["slug"])}">{T("admin_create_lab", la)}</a>')

        lines.append(render.render(
            "admin/dashboard_row.html",
            number=number,
            entry_cancel_scheduling=cancel_item + lab_item,
            title_lowercase=esc(art["title"].lower()),
            data_iso=esc(art.get("date", "")),
            order_state=status_order,
            time_reading=compute_reading_time(art.get("content", ""), la),
            css_class_pill=pill_class,
            label_text_state=status_label,
            also_in=also_in,
            slug=esc(art["slug"]),
            # These three land inside an onclick attribute, so they need the
            # HTML layer on top of the JavaScript one.
            slug_js=js_attr(art["slug"]),
            title=esc(art["title"]),
            title_js=js_attr(art["title"]),
            data=shown_date,
            label_edit=T("admin_edit", la),
            label_others_f_actions=esc(T("admin_others_f_actions", la).replace("{title}", art["title"])),
            icon_other=icon(ICON_MORE, 20),
            label_preview=T("admin_preview", la),
            link_preview_language=preview_other_link,
            action_state_js=js_attr(status_action),
            label_text_action_state=status_action_label,
            label_delete=T("admin_delete", la),
        ).rstrip("\n"))

    if len(lines) > 0:
        listing = "\n".join(lines)
    else:
        listing = f'<p class="list-empty">{T("admin_no_one_article", la)}</p>'

    summary = (T("admin_overview_articles", la)
               .replace("{p}", str(published_count))
               .replace("{b}", str(draft_count)))
    if scheduled_count > 0:
        summary = summary + T("admin_overview_scheduled_pl", la).replace(
            "{s}", str(scheduled_count))

    contenuto = render.render(
        "admin/dashboard.html",
        label_articles=T("admin_articles", la),
        overview=summary,
        new_article=T("admin_new_article_title", la),
        label_show=T("admin_show_group", la),
        label_all=T("admin_filter_all", la),
        total=len(articles),
        label_published_pl=T("admin_published_pl", la),
        published_pl=published_count,
        label_drafts=T("admin_drafts", la),
        drafts=draft_count,
        label_scheduled_pl=T("admin_scheduled_pl", la),
        scheduled_pl=scheduled_count,
        scheduled_pl_hidden_m="" if scheduled_count > 0 else " hidden",
        label_search=esc(T("admin_search_articles", la)),
        label_sort=T("admin_sort", la),
        sort_recent=T("admin_sort_recenti", la),
        sort_old=T("admin_sort_old", la),
        sort_title=T("admin_sort_title", la),
        sort_state=T("admin_sort_state", la),
        list=listing,
        no_one_matches=T("admin_no_one_matches", la),
        first_steps_of_steps=setup_steps_html(articles, la),
        label_see_update_notice=T("admin_see_update_notice", la),
    )

    return admin_page_shell(
        T("admin_title_page", la) + " - " + CONFIG["site_title"],
        contenuto, la, csrf=csrf,
        navbar=admin_navbar("articles", la, len(articles)),
        page_data={"page": "dashboard"})


def codemirror_scripts():
    """The script tags of CodeMirror and of the modes it needs, in order."""
    return "\n".join(f'<script src="{url}"></script>' for url in CODEMIRROR_JS)


def lab_of_options(art, la):
    """
    The articles a lab or a practical version can start from, as the
    options of a select: every plain article but the one being edited.
    """
    chosen = art.get("lab_of", "")
    options = [f'<option value="">{esc(T("admin_lab_nobody", la))}</option>']
    for other in load_articles():
        slug = other.get("slug", "")
        if other.get("kind") in ("lab", "practical") or slug == "" or slug == art.get("slug"):
            continue
        selected = " selected" if slug == chosen else ""
        options.append(f'<option value="{esc(slug)}"{selected}>'
                       f'{esc(other.get("title", slug))}</option>')
    return "".join(options)


def subject_tabs(art, la):
    """
    The tabs over the editor: the articles on the same subject - the theory,
    its practical version, its labs - with the state of each, and the links
    that add the ones still missing. The author moves between the theory
    and its lab without going back to the list.
    """
    state_words = {"published": T("admin_state_published", la),
                   "scheduled": T("admin_state_scheduled", la),
                   "draft": T("admin_state_draft", la)}
    labels = {"": T("admin_card_theory", la), "practical": T("admin_card_practice", la),
              "lab": T("admin_card_lab", la)}
    everything = load_articles()
    kind = art.get("kind", "") or ""
    root_slug = art.get("slug", "")
    if kind in ("lab", "practical"):
        root_slug = art.get("lab_of", "")
    group = [other for other in everything
             if root_slug != "" and other.get("slug") == root_slug]
    group = group + [other for other in everything
                     if root_slug != "" and other.get("lab_of") == root_slug
                     and other.get("kind") in ("lab", "practical")
                     and other.get("slug") != root_slug]
    if not any(other.get("slug") == art.get("slug") for other in group) or not art.get("slug"):
        # The article on screen, when it is new or stands alone.
        group.append(art)
    group.sort(key=lambda other: ("", "practical", "lab").index(other.get("kind") or ""))

    tabs = []
    for other in group:
        name = labels[other.get("kind") or ""]
        if not other.get("slug"):
            state = T("admin_card_new", la)
        else:
            state = state_words.get(other.get("status", "draft"), state_words["draft"])
        text = f'<span class="card-name">{name}</span><span class="card-state">{esc(state)}</span>'
        if other is art or (other.get("slug") and other.get("slug") == art.get("slug")):
            tabs.append(f'    <span class="card-theme" aria-current="page">{text}</span>')
        else:
            tabs.append(f'    <a class="card-theme" href="/edit?slug={esc(other["slug"])}" '
                        f'title="{esc(other.get("title", ""))}">{text}</a>')
    # What can still be added to a subject whose theory is saved.
    if root_slug != "" and any(other.get("slug") == root_slug for other in everything):
        if not any(other.get("kind") == "practical" for other in group):
            tabs.append(f'    <a class="card-theme card-add" '
                        f'href="/edit?lab_of={esc(root_slug)}&amp;kind=practical">'
                        f'{T("admin_card_add_practice", la)}</a>')
        tabs.append(f'    <a class="card-theme card-add" id="link-create-lab" '
                    f'href="/edit?lab_of={esc(root_slug)}">{T("admin_card_add_lab", la)}</a>')
    return "\n".join(tabs)


def editor_page(art, csrf, starts_from=None, new_kind="lab"):
    """
    The page with the WYSIWYG editor (it uses Quill, loaded from a CDN).
    starts_from is the article a new lab (or practical version, new_kind)
    is being created for: the new article opens already tied to it, with
    its tags.
    """
    la = admin_language()

    # If we are editing an existing article, we take its values.
    # If instead this is a new article (art is None), we start from empty fields.
    if art is not None:
        page_title = T("admin_edit_article_title", la)
        menu_item = "articles"
        # Deleting sits at the very bottom of the sidebar, small: it used to
        # be a red button as big as Save, right under it.
        delete_button = (f'<button type="button" class="button button-text button-danger button-small btn-delete-article" '
                         f'onclick="deleteItem()">{T("admin_delete_article", la)}</button>')
    else:
        art = {}
        page_title = T("admin_new_article_title", la)
        if starts_from is not None:
            art = {"kind": new_kind, "lab_of": starts_from.get("slug", ""),
                   "tags": starts_from.get("tags", "")}
            title_key = "admin_lab_new_of"
            if new_kind == "practical":
                title_key = "admin_practice_new_f_of"
            page_title = T(title_key, la).replace("{title}", starts_from.get("title", ""))
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
        title_page_h1=page_title,
        label_title=T("admin_title", la),
        value_title=esc(art.get("title", "")),
        label_content=T("admin_content", la),
        tip_import_docx=esc(T("tip_import_docx", la)),
        label_import_from_word=T("admin_import_from_word", la),
        hint_docx=T("admin_docx_hint", la),
        tip_upload_image=esc(T("tip_upload_image", la)),
        label_from_library=T("admin_from_media_library", la),
        label_image_details=T("admin_image_details", la),
        label_image_alt_fix=T("admin_image_alt_fix", la),
        label_upload_picture=T("admin_upload_picture", la),
        tip_youtube=esc(T("tip_youtube", la)),
        label_youtube=T("admin_insert_youtube", la),
        tip_upload_video=esc(T("tip_upload_video", la)),
        label_upload_video=T("admin_upload_video", la),
        tip_table=esc(T("tip_table", la)),
        label_table=T("admin_insert_table", la),
        label_back_to_articles=T("admin_back_to_articles", la),
        label_insert=T("admin_insert", la),
        label_address=T("admin_address_slug", la),
        hint_address=T("admin_address_slug_hint", la),
        state=status,
        label_state_draft=T("admin_state_draft", la),
        hint_state_draft=T("admin_state_draft_hint", la),
        label_state_published=T("admin_state_published", la),
        label_state_scheduled=T("admin_state_scheduled", la),
        tick_notify=notify_checkbox(art, la),
        label_versions=T("admin_versions", la),
        hint_versions=T("admin_versions_hint", la),
        versions_hidden_m="" if art.get("slug", "") else " hidden",
        goes_out_the=moment_html(publish_at, la),
        label_save_changes_made=T("admin_save_changes_made", la),
        label_publish_now=T("admin_publish_now", la),
        label_schedule_cancel=T("admin_schedule_cancel", la),
        label_schedule=T("admin_schedule", la),
        label_schedule_change=T("admin_schedule_change", la),
        label_schedule_when=T("admin_schedule_when", la),
        hint_schedule=T("admin_schedule_hint", la),
        label_schedule_confirm=T("admin_schedule_confirm", la),
        url_online=esc(url_online),
        label_cards_theme=esc(T("admin_cards_theme", la)),
        cards_theme=subject_tabs(art, la),
        label_details=T("admin_details", la),
        label_close=T("admin_close", la),
        label_lab_project=T("admin_lab_project", la),
        label_share=T("admin_share", la),
        hint_share=T("admin_share_hint", la),
        label_see_online=T("admin_see_online", la),
        label_publish=T("admin_publish", la),
        tip_publish=esc(T("tip_publish_article", la)),
        label_update=T("admin_update_article", la),
        tip_update=esc(T("tip_update_article", la)),
        label_save_draft=T("admin_save_draft", la),
        tip_save_draft=esc(T("tip_save_draft", la)),
        label_preview=T("admin_preview_page", la),
        tip_preview_page=esc(T("tip_preview_page", la)),
        label_withdraw=T("admin_withdraw", la),
        button_el_delete=delete_button,
        label_section_of_metadata=T("admin_section_of_metadata", la),
        label_group_series=T("admin_group_series", la),
        label_group_preview=T("admin_group_preview", la),
        label_group_advanced=T("admin_group_advanced", la),
        overview_advanced=T("admin_group_advanced_overview", la),
        value_slug=esc(art.get("slug", "")),
        label_tag=T("admin_tag", la),
        value_tag=esc(art.get("tags", "")),
        label_series=T("admin_series", la),
        value_series=esc(art.get("series", "")),
        value_series_number=art.get("series_number") or "",
        label_series_number=esc(T("admin_series_number", la)),
        hint_series=help_text(T("admin_series_hint", la)),
        series_existing="".join(f'<option value="{esc(entry["name"])}">'
                                for entry in collect_series(load_articles()).values()),
        label_original=T("admin_original", la),
        value_original=esc(art.get("original_url", "")),
        hint_original=help_text(T("admin_original_hint", la)),
        original_canonical_checked="checked" if art.get("original_canonical") is True else "",
        label_original_canonical=T("admin_original_canonical", la),
        hint_original_canonical=help_text(T("admin_original_canonical_hint", la)),
        label_kind=T("admin_kind", la),
        hint_kind=help_text(T("admin_kind_hint", la)),
        label_kind_article=T("admin_kind_article", la),
        label_kind_practice=T("admin_kind_practice", la),
        label_kind_lab=T("admin_kind_lab", la),
        sel_kind_article=selected_if(art.get("kind", ""), ""),
        sel_kind_practice=selected_if(art.get("kind", ""), "practical"),
        sel_kind_lab=selected_if(art.get("kind", ""), "lab"),
        reference_hidden="" if art.get("kind") in ("lab", "practical") else "hidden",
        lab_hidden="" if art.get("kind") == "lab" else "hidden",
        label_lab_of=T("admin_lab_of", la),
        options_lab_of=lab_of_options(art, la),
        label_lab_repo=T("admin_lab_repo", la),
        value_repo=esc(art.get("repo_url", "")),
        label_lab_stack=T("admin_lab_stack", la),
        value_stack=esc(art.get("stack", "")),
        label_lab_commands=T("admin_lab_commands", la),
        value_commands=esc(art.get("run_steps", "")),
        label_picture=T("admin_picture_cover", la),
        hint_picture=help_text(T("admin_picture_cover_hint", la)),
        value_picture=esc(art.get("image", "")),
        ph_picture="https://... /media/...",
        label_upload_cover=T("admin_upload_cover", la),
        label_remove_cover=T("admin_remove_cover", la),
        label_preview_readers=T("admin_preview_readers", la),
        hint_preview=help_text(T("admin_preview_hint", la)),
        value_preview=esc(art.get("preview", "")),
        label_generate_preview=T("admin_generate_preview", la),
        label_description_seo=T("admin_description_seo", la),
        hint_description=help_text(T("admin_description_hint", la)),
        value_description=esc(art.get("description", "")),
        label_suggest=T("admin_suggest_description", la),
        label_analysis_seo=T("admin_analysis_seo", la),
        hint_analysis_seo=T("admin_analysis_seo_hint", la),
        label_analyze=T("admin_analyze_seo", la),
        label_version_english=TL("admin_version_english", la),
        label_authorize=TL("admin_authorize_translation_of", la),
        label_translate=T("admin_translate_auto", la),
        label_preview_en=TL("admin_preview_en", la),
        hint_preview_en=help_text(TL("admin_preview_en_hint", la)),
        label_confirm_translation_of=TL("admin_confirm_translation_of", la),
        code_translation_of=secondary_language().upper(),
        label_code_title=T("admin_code_article_title", la),
        hint_code=T("admin_code_article_hint", la),
        code_article_html=article_custom_code_html(art, la),
        label_code_own=T("admin_code_own_title", la),
        hint_code_own=T("admin_code_own_hint", la),
        code_own_html=article_own_code_html(art, la),
        code_own_template=custom_code_blank_card(la, own=True),
        label_code_own_add=T("admin_code_own_add", la),
    )

    # The article content and the translation flags travel as JSON, never as
    # text pasted into a script: an apostrophe or a "</script>" inside an
    # article would otherwise break - or escape - the surrounding JavaScript.
    page_data = {
        "page": "editor",
        # The public address of the site, for the links that share an article.
        "public_base": CONFIG.get("base_url", "").rstrip("/"),
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
    "head": "admin_code_pos_head",
    "body_start": "admin_code_pos_body_start",
    "body_end": "admin_code_pos_body_end",
    "nav": "admin_code_pos_nav",
    "after_header": "admin_code_pos_after_header",
    "sidebar": "admin_code_pos_sidebar",
    "home_feed": "admin_code_pos_home_feed",
    "article_start": "admin_code_pos_article_start",
    "article_middle": "admin_code_pos_article_middle",
    "article_end": "admin_code_pos_article_end",
    "before_footer": "admin_code_pos_before_footer",
    "anchor": "admin_code_pos_anchor",
}

SCOPE_LABEL_KEYS = {
    "all": "admin_code_scope_everything",
    "home": "admin_code_scope_home",
    "articles": "admin_code_scope_only_articles",
    "home_articles": "admin_code_scope_articles",
    "optin": "admin_code_scope_only_optin",
    "home_optin": "admin_code_scope_optin",
}


def snippet_summary(snippet, la, own=False):
    """
    The line under the name of a folded card: where the code goes, on which
    pages, and whether it waits for consent. A long list of cards can then be
    read without opening any of them.
    """
    position = snippet.get("position", "head")
    pieces = [T(POSITION_LABEL_KEYS.get(position, "admin_code_pos_head"), la)]
    if position == "anchor" and str(snippet.get("anchor_label", "")).strip() != "":
        pieces = [str(snippet["anchor_label"]).strip()]
    if not own:
        pieces.append(T(SCOPE_LABEL_KEYS.get(snippet.get("scope", "home"),
                                             "admin_code_scope_home"), la))
    consent = snippet.get("consent", "necessary")
    if consent not in ("necessary", "statistics", "marketing"):
        consent = "necessary"
    pieces.append(T("consent_" + consent, la))
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
        shown_name = T("admin_code_without_name", la)

    scope_block = ""
    if not own:
        scope_block = render.render(
            "admin/custom_code_scope.html",
            label_scope=T("admin_code_scope", la),
            sel_everything=selected_if(scope, "all"),
            label_scope_everything=T("admin_code_scope_everything", la),
            sel_home=selected_if(scope, "home"),
            label_scope_home=T("admin_code_scope_home", la),
            sel_only_articles=selected_if(scope, "articles"),
            label_scope_only_articles=T("admin_code_scope_only_articles", la),
            sel_articles=selected_if(scope, "home_articles"),
            label_scope_articles=T("admin_code_scope_articles", la),
            sel_only_optin=selected_if(scope, "optin"),
            label_scope_only_optin=T("admin_code_scope_only_optin", la),
            sel_optin=selected_if(scope, "home_optin"),
            label_scope_optin=T("admin_code_scope_optin", la),
            hint_scope=T("admin_code_scope_hint", la),
        )

    values = {
        "toc_index": index_value,
        "id_snippet": esc(snippet.get("id", "")),
        "open": " open" if open_card else "",
        "name_shown": esc(shown_name),
        "summary_text": esc(snippet_summary(snippet, la, own)),
        "state": T("admin_code_active", la) if enabled else T("admin_code_off_m", la),
        "css_class_off_m": "" if enabled else " off",
        "checked": checked_if(enabled),
        "label_active": T("admin_code_active", la),
        "label_delete": T("admin_code_delete", la),
        "label_name": T("admin_code_name", la),
        "name": esc(name),
        "ph_name": esc(T("admin_code_name_ph", la)),
        "label_position": T("admin_code_position", la),
        "group_technical": T("admin_code_pos_group_technical", la),
        "group_visible": T("admin_code_pos_group_visible", la),
        "lock_scope": scope_block,
        "label_consent": T("admin_code_consent", la),
        "sel_necessary": selected_if(consent, "necessary"),
        "label_consent_choice_necessary": T("admin_code_consent_choice_necessary", la),
        "sel_statistics": selected_if(consent, "statistics"),
        "label_consent_choice_statistics": T("admin_code_consent_choice_statistics", la),
        "sel_marketing": selected_if(consent, "marketing"),
        "label_consent_choice_marketing": T("admin_code_consent_choice_marketing", la),
        # The homepage list is no place for code that belongs to one article.
        "only_site": " hidden disabled" if own else "",
        "hint_position": T("admin_code_pos_hint_own" if own else "admin_code_pos_hint", la),
        "hint_consent": T("admin_code_consent_hint_own" if own else "admin_code_consent_hint", la),
        "label_code": esc(T("admin_code_code", la)),
        "code": esc(snippet.get("code", "")),
        # The point chosen on the page, for the "anchor" position.
        "point_hidden_m": "" if position == "anchor" else " hidden",
        "label_point": T("admin_point", la),
        "point_text": esc(str(snippet.get("anchor_label", "")).strip()
                           or T("admin_point_nobody", la)),
        "label_choose_point": T("admin_choose_point", la),
        "hint_point": T("admin_point_hint", la),
        "anchor_point": esc(str(snippet.get("anchor_selector", ""))),
        "anchor_point_where": esc(str(snippet.get("anchor_where", "after"))),
        "anchor_point_label_text": esc(str(snippet.get("anchor_label", ""))),
        "anchor_point_page": esc(str(snippet.get("anchor_page", ""))),
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
            kind = T("admin_code_article_chosen", la)
        else:
            checked = "" if snippet_id in switched_off else " checked"
            kind = T("admin_code_article_always", la)
        where = esc(T(POSITION_LABEL_KEYS.get(snippet.get("position", "head"),
                                              "admin_code_pos_head"), la))
        rows.append(
            '<label class="row-flag code-article-row">'
            f'<input type="checkbox" class="code-article" value="{esc(snippet_id)}"'
            f' data-kind="{"optin" if optin else "sempre"}"{checked}> {name} '
            f'<span class="hint">({where}, {esc(kind)})</span></label>')

    if len(rows) == 0:
        return f'<p class="hint">{T("admin_code_article_empty_m", la)}</p>'
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
        label_visible=T("admin_project_visible", la),
        label_on_top=esc(T("admin_move_on_top", la)),
        label_down=esc(T("admin_move_down", la)),
        icon_on_top=icon(ICON_UP),
        icon_down=icon(ICON_DOWN),
        label_delete=T("admin_project_delete", la),
        label_name=T("admin_project_name", la),
        name=esc(item.get("name", "")),
        label_description=T("admin_project_description", la),
        description=esc(item.get("description", "")),
        hint_description=T("admin_project_description_hint", la),
        label_description_en=TL("admin_project_description_en", la),
        description_en=esc(item.get("description_en", "")),
        label_link=T("admin_project_link", la),
        link=esc(item.get("url", "")),
        hint_link=T("admin_project_link_hint", la),
        label_picture=T("admin_project_picture", la),
        picture=esc(item.get("image", "")),
        hint_picture=T("admin_project_picture_hint", la),
        label_upload=T("admin_upload_picture", la),
    ).rstrip("\n")


def code_guide(la, open_it):
    """The three worked examples above the list of external code."""
    return render.render(
        "admin/code_guide.html",
        open_f=" open" if open_it else "",
        title=T("admin_guide_codes_title", la),
        intro=T("admin_guide_codes_intro", la),
        you_give=T("admin_guide_you_give", la),
        what_do=T("admin_guide_what_do", la),
        ex1_title=T("admin_guide_ex1_title", la),
        ex1_steps=T("admin_guide_ex1_steps", la),
        ex2_title=T("admin_guide_ex2_title", la),
        ex2_steps=T("admin_guide_ex2_steps", la),
        ex3_title=T("admin_guide_ex3_title", la),
        ex3_steps=T("admin_guide_ex3_steps", la),
        trust=T("admin_guide_trust", la),
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


def section_state_html(section_id, config, la):
    """The state line of a card: a tone the CSS colours, and its text."""
    state = settings_panel.section_state(section_id, config, la)
    if state is None:
        return ""
    tone, text = state
    warn = ""
    if tone == "warn":
        # The colour alone would leave a screen reader with no warning.
        warn = icon(ICON_WARN, 16) + f'<span class="vh">{T("admin_state_tone_warn", la)}: </span>'
    return f'<span class="card-state state-{tone}">{warn}{esc(text)}</span>'


def section_warnings_html(key, config, la):
    """
    What a section has to fix, at the top of the section itself: whoever
    opens Analytics because the panel warned about it finds the warning
    again where the fields are. The list is there even when empty, so that
    admin.js can fill it after a save.
    """
    rows = [f'    <li>{icon(ICON_WARN, 18)}{esc(text)}</li>'
            for tone, text in settings_panel.section_states(key, config, la) if tone == "warn"]
    hidden = "" if rows else " hidden"
    return (f'  <ul class="section-notices" id="notices-{key}"{hidden}>\n'
            + "\n".join(rows) + ("\n" if rows else "") + '  </ul>')


def config_sections_list(la, config=None):
    """
    The Settings panel, what /config opens on: the sections grouped, each
    card with what it is for and how it stands now. data-search carries the
    words the search matches besides the visible ones; admin.js adds the
    labels of the section's fields.
    """
    if config is None:
        config = CONFIG
    parts = []
    for group_id, group_key in settings_panel.GROUPS:
        cards = []
        for entry in settings_panel.sections_of(group_id):
            key = entry["id"]
            # The card takes the colour of its state: green when it is in
            # order, orange when something is to fix, plain when off.
            state = settings_panel.section_state(key, config, la)
            tone = state[0] if state else "off"
            cards.append(
                f'      <li><a class="card-setting card-{tone}" href="#{key}" data-section="{key}" '
                f'data-search="{esc(entry["keywords"])}">'
                f'<span class="card-name">{T(entry["label"], la)}</span>'
                f'<span class="card-desc">{TL(entry["label"] + "_desc", la)}</span>'
                f'{section_state_html(key, config, la)}'
                f'{icon(ICON_NEXT, 20)}</a></li>')
        parts.append(
            f'  <div class="panel-group" role="group" aria-labelledby="group-{group_id}">\n'
            f'    <h2 class="panel-group-title" id="group-{group_id}">{T(group_key, la)}</h2>\n'
            f'    <ul class="panel-cards">\n' + "\n".join(cards) + '\n    </ul>\n'
            '  </div>')
    return "\n".join(parts)


def config_section_header(key, la, config=None):
    """
    The top of a Settings section: on a phone a link back to the list, then
    the name of the section and one line about what it holds.
    """
    label_key = dict(CONFIG_SECTIONS)[key]
    # The way back is the first word of the breadcrumb, on every screen;
    # the phone also gets the arrow it expects in the corner.
    trail = f'<a href="#list">{T("admin_settings_page", la)}</a>'
    group_key = settings_panel.group_label(key)
    if group_key != "":
        trail = trail + f' <span aria-hidden="true">›</span> {T(group_key, la)}'
    return (
        '  <div class="section-header">\n'
        f'    <a class="button button-icon section-back" href="#list" '
        f'aria-label="{esc(T("admin_back_to_settings_page", la))}">{icon(ICON_BACK, 22)}</a>\n'
        '    <div>\n'
        f'      <p class="section-eyebrow">{trail}</p>\n'
        f'      <h1 class="page-title" id="title-{key}">{T(label_key, la)}</h1>\n'
        f'      <p class="page-subtitle">{TL(label_key + "_desc", la)}</p>\n'
        '    </div>\n'
        '  </div>\n'
        + section_warnings_html(key, config if config is not None else CONFIG, la))


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
            toc_index=index_value,
            checked=checked,
            label_show=T("admin_show_card", la),
            label_title=T("admin_title_card", la),
            title=esc(card.get("title", "")),
            label_content=T("admin_content", la),
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
        stato = T("admin_nl_confirmed" if reader.get("status") == "confirmed" else "admin_nl_waiting", la)
        email = esc(reader.get("email", ""))
        nl_rows.append(
            f'      <li><span class="nl-email">{email}</span> <span class="hint">{stato}</span>'
            f'<button type="button" class="button button-text button-danger button-small" '
            f'data-email="{email}" onclick="removeSubscriber(this)">{T("admin_nl_remove", la)}</button></li>')
    if nl_rows:
        nl_list = '    <ul class="nl-list">\n' + "\n".join(nl_rows) + "\n    </ul>"
    else:
        nl_list = f'    <p class="help">{T("admin_nl_nobody", la)}</p>'
    nl_confirmed = sum(1 for r in nl_state["subscribers"] if r.get("status") == "confirmed")
    last = nl_state["last"]
    nl_last = ""
    if last.get("title"):
        if last.get("error"):
            nl_last = (f'    <p class="notice notice-danger">' + esc(T("admin_nl_last_failure", la)
                       .replace("{title}", last["title"]).replace("{error}", last["error"])) + "</p>")
        else:
            nl_last = (f'    <p class="help">' + esc(T("admin_nl_last", la)
                       .replace("{title}", last["title"]).replace("{sent}", str(last.get("sent", 0)))) + "</p>")

    context = dict(
        title_settings_page=T("admin_settings_page", la),
        checked_nl=checked_if(nl["enabled"]),
        label_nl_active_f=T("admin_nl_active_f", la),
        hint_nl_active_f=T("admin_nl_active_f_hint", la),
        label_nl_where=T("admin_nl_where", la),
        checked_nl_bar=checked_if(nl["in_sidebar"]),
        label_nl_bar=T("admin_nl_bar", la),
        checked_nl_article=checked_if(nl["after_article"]),
        label_nl_article=T("admin_nl_article", la),
        label_nl_title=T("admin_nl_title", la),
        value_nl_title=esc(nl["title"]),
        ph_nl_title=esc(T("nl_title_default", site_language)),
        label_nl_text=T("admin_nl_text", la),
        value_nl_text=esc(nl["text"]),
        ph_nl_text=esc(T("nl_text_default", site_language)),
        hint_nl_texts_of=T("admin_nl_texts_of_hint", la),
        checked_nl_sending=checked_if(nl["send_on_publish"]),
        label_nl_sending=T("admin_nl_sending_auto", la),
        hint_nl_sending=T("admin_nl_sending_auto_hint", la),
        label_grp_nl_shipping=T("admin_grp_nl_shipping", la),
        hint_grp_nl_shipping=T("admin_grp_nl_shipping_hint", la),
        label_nl_sender_name=T("admin_nl_sender_name", la),
        value_nl_sender_name=esc(nl["sender_name"]),
        hint_nl_sender_name=T("admin_nl_sender_name_hint", la),
        label_nl_sender_email=T("admin_nl_sender_email", la),
        value_nl_sender_email=esc(nl["sender_email"]),
        label_nl_smtp_host=T("admin_nl_smtp_host", la),
        value_nl_smtp_host=esc(nl["smtp_host"]),
        label_nl_smtp_port=T("admin_nl_smtp_port", la),
        value_nl_smtp_port=nl["smtp_port"],
        hint_nl_smtp_port=T("admin_nl_smtp_port_hint", la),
        label_nl_smtp_security=T("admin_nl_smtp_security", la),
        sel_nl_starttls=selected_if(nl["smtp_security"], "starttls"),
        sel_nl_ssl=selected_if(nl["smtp_security"], "ssl"),
        sel_nl_none=selected_if(nl["smtp_security"], "none"),
        label_nl_starttls=T("admin_nl_sic_starttls", la),
        label_nl_ssl=T("admin_nl_sic_ssl", la),
        label_nl_none=T("admin_nl_sic_none", la),
        label_nl_smtp_user=T("admin_nl_smtp_user", la),
        value_nl_smtp_user=esc(nl["smtp_user"]),
        label_nl_smtp_password=T("admin_nl_smtp_password", la),
        # The password is never written back into the page: an empty field
        # keeps the saved one, as the translation keys do.
        ph_nl_password=esc(T("admin_nl_password_saved_f", la)) if nl["smtp_password"] else "",
        hint_nl_smtp_password=T("admin_nl_smtp_password_hint", la),
        label_nl_test=T("admin_nl_test", la),
        hint_nl_test=T("admin_nl_test_hint", la),
        label_grp_nl_subscribers=T("admin_grp_nl_subscribers", la),
        nl_count=T("admin_nl_count", la).replace("{c}", str(nl_confirmed)).replace(
            "{p}", str(len(nl_state["subscribers"]) - nl_confirmed)),
        nl_last=nl_last,
        nl_list=nl_list,
        label_nl_export=T("admin_nl_export", la),
        checked_bio=checked_if(biography["enabled"]),
        label_bio_active_f=T("admin_bio_active_f", la),
        hint_bio_active_f=T("admin_bio_active_f_hint", la),
        label_position_home=T("admin_position_home", la),
        label_pos_sidebar=T("admin_pos_sidebar", la),
        label_pos_top=T("admin_pos_top", la),
        label_pos_bottom=T("admin_pos_bottom", la),
        sel_bio_sidebar=selected_if(biography["position"], "sidebar"),
        sel_bio_top=selected_if(biography["position"], "top"),
        sel_bio_bottom=selected_if(biography["position"], "bottom"),
        label_bio_photo=T("admin_bio_photo", la),
        value_bio_photo=esc(biography["photo"]),
        hint_bio_photo=T("admin_bio_photo_hint", la),
        label_upload_photo=T("admin_upload_photo", la),
        label_remove=T("admin_remove", la),
        label_bio_text=T("admin_bio_text", la),
        label_bio_text_en=TL("admin_bio_text_en", la),
        hint_bio_text_en=TL("admin_bio_text_en_hint", la),
        checked_projects=checked_if(projects["enabled"]),
        label_projects_active_pl=T("admin_projects_active_pl", la),
        hint_projects_active_pl=T("admin_projects_active_pl_hint", la),
        sel_projects_sidebar=selected_if(projects["position"], "sidebar"),
        sel_projects_top=selected_if(projects["position"], "top"),
        sel_projects_bottom=selected_if(projects["position"], "bottom"),
        projects_html="\n".join(project_cards),
        projects_empty_m_hidden_m=empty_note_hidden,
        label_projects_empty_m=T("admin_projects_empty_m", la),
        label_project_add=T("admin_project_add", la),
        project_template=project_card(None, la),
        list_sections=config_sections_list(la, config),
        panel_subtitle=T("admin_panel_subtitle", la),
        label_search_setting=T("admin_search_setting", la),
        ph_search_setting=esc(T("admin_search_setting_ph", la)),
        none_f_setting=T("admin_none_f_setting", la),
        advanced_invitation=T("admin_advanced_invitation", la),
        advanced_link=T("admin_advanced_link", la),
        label_grp_site=T("admin_grp_site", la),
        label_grp_author=T("admin_grp_author", la),
        label_grp_pictures=T("admin_grp_pictures", la),
        label_grp_layout_section=T("admin_grp_layout_section", la),
        label_grp_page_article=T("admin_grp_page_article", la),
        label_gr_statistiche=T("admin_grp_analytics_section", la),
        label_umami_url=T("admin_umami_url", la),
        label_umami_id=T("admin_umami_id", la),
        hint_giscus="https://giscus.app",
        label_cancel_changes_made=T("admin_cancel_changes_made", la),
        note_text_save=T("admin_save_note_text", la),
        guide_codes=code_guide(la, len(config.get("custom_code", []) or []) == 0),
        label_insert=T("admin_insert", la),
        label_part_top=T("admin_part_top_home", la),
        hint_part_top=T("admin_part_top_hint", la),
        tip_upload_image=esc(T("tip_upload_image", la)),
        label_from_library=T("admin_from_media_library", la),
        label_image_details=T("admin_image_details", la),
        label_image_alt_fix=T("admin_image_alt_fix", la),
        label_upload_picture=T("admin_upload_picture", la),
        tip_youtube=esc(T("tip_youtube", la)),
        label_youtube=T("admin_insert_youtube", la),
        tip_upload_video=esc(T("tip_upload_video", la)),
        label_upload_video=T("admin_upload_video", la),
        tip_preview=esc(T("tip_preview", la)),
        label_show_preview_home=T("admin_show_preview_home", la),
        hint_how_appears=T("admin_how_appears_home", la),
        label_introduction_english=TL("admin_introduction_english", la),
        hint_introduction_en=TL("admin_introduction_en_hint", la),
        label_translate_italian=TL("admin_translate_from_the_italian", la),
        label_job_title=T("admin_job_title", la),
        checked_job=checked_if(lavoro["enabled"]),
        label_job_active=T("admin_job_active", la),
        hint_job_active=T("admin_job_active_hint", la),
        label_job_url=T("admin_job_url", la),
        hint_job_url=T("admin_job_url_hint", la),
        value_job_url=esc(lavoro["url"]),
        label_job_label=T("admin_job_label", la),
        value_job_label=esc(lavoro["label"]),
        ph_job_label=esc(T("work_with_me", "it")),
        label_job_label_en=T("admin_job_label_en", la),
        value_job_label_en=esc(lavoro["label_en"]),
        ph_job_label_en=esc(T("work_with_me", "en")),
        label_job_text=T("admin_job_text", la),
        value_job_text=esc(lavoro["text"]),
        ph_job_text=esc(T("work_invitation", "it")),
        label_job_text_en=T("admin_job_text_en", la),
        value_job_text_en=esc(lavoro["text_en"]),
        ph_job_text_en=esc(T("work_invitation", "en")),
        hint_card_home=T("admin_card_home_hint", la),
        checked_card_home_active_f=checked_if(config.get("home_cards_enabled", True)),
        label_card_home_active_f=T("admin_card_home_active_f", la),
        hint_card_home_active_f=T("admin_card_home_active_f_hint", la),
        card_html="\n".join(card_html_parti),
        label_code_title=T("admin_code_title", la),
        hint_code=T("admin_code_hint", la),
        code_html=custom_code_cards(config, la),
        code_template=custom_code_blank_card(la),
        label_code_empty_m=T("admin_code_empty_m", la),
        label_code_add=T("admin_code_add", la),
        label_code_templates=T("admin_code_templates", la),
        hint_code_templates=T("admin_code_templates_hint", la),
        label_template_free=T("admin_code_free", la),
        label_template_adsense_auto=T("admin_template_adsense_auto", la),
        label_template_adsense_unit_ad=T("admin_template_adsense_unit_ad", la),
        label_template_google_ads=T("admin_template_google_ads", la),
        label_template_others=esc(T("admin_template_others", la)),
        label_code_create=T("admin_code_create", la),
        label_cancel_choice=T("admin_cancel_choice", la),
        label_ads_txt=T("admin_ads_txt", la),
        hint_ads_txt=T("admin_ads_txt_hint", la),
        value_ads_txt=esc(config.get("ads_txt", "")),
        hint_consent=T("admin_consent_intro", la),
        checked_consent=checked_if(consent["enabled"]),
        label_consent_active=T("admin_consent_active", la),
        label_consent_text=T("admin_consent_text", la),
        hint_consent_text=T("admin_consent_text_hint", la),
        value_consent_text=esc(consent["text"]),
        ph_consent_text=esc(T("consent_text", main_language())),
        label_consent_text_en=TL("admin_consent_text_en", la),
        value_consent_text_en=esc(consent["text_en"]),
        ph_consent_text_en=esc(T("consent_text", secondary_language())),
        label_consent_privacy=T("admin_consent_privacy", la),
        value_consent_privacy=esc(consent["privacy_url"]),
        ph_consent_privacy=ph["base_url"] + "/privacy.html",
        label_consent_renew=T("admin_consent_renew", la),
        hint_consent_renew=T("admin_consent_renew_hint", la),
        label_title_site=T("admin_title_site", la),
        value_title_site=esc(config.get("site_title", "")),
        ph_site_title=ph["site_title"],
        label_subtitle=T("admin_subtitle", la),
        value_subtitle=esc(config.get("subtitle", "")),
        ph_subtitle=ph["subtitle"],
        label_author=T("admin_author", la),
        value_author=esc(config.get("author", "")),
        ph_author=ph["author"],
        label_domain=T("admin_domain_site", la),
        hint_domain=T("admin_domain_hint", la),
        value_domain=esc(config.get("base_url", "")),
        label_address_admin=T("admin_address_admin", la),
        hint_address_admin=T("admin_address_admin_hint", la),
        value_address_admin=esc(str(config.get("admin_url", "") or "")),
        ph_base_url=ph["base_url"],
        label_analytics=T("admin_analytics", la),
        label_ga_id=T("admin_ga_id", la),
        hint_analytics=T("admin_analytics_hint", la),
        value_analytics=esc(config.get("analytics_id", "")),
        ph_analytics_id=ph["analytics_id"],
        label_umami=T("admin_umami", la),
        hint_umami=T("admin_umami_hint", la),
        value_umami_url=esc(config.get("umami_url", "")),
        ph_umami_url=ph["umami_url"],
        value_umami_id=esc(config.get("umami_website_id", "")),
        ph_umami_website_id=ph["umami_website_id"],
        label_language_main=T("admin_language_main", la),
        hint_language_main=T("admin_language_main_hint", la),
        sel_language_it=selected_if(site_language, "it"),
        sel_language_en=selected_if(site_language, "en"),
        hint_layout=T("admin_layout_hint", la),
        label_intro_position=T("admin_intro_position", la),
        hint_intro_position=T("admin_intro_position_hint", la),
        sel_intro_bar=selected_if(intro_position, "sidebar"),
        label_intro_bar=T("admin_intro_bar", la),
        sel_intro_above=selected_if(intro_position, "top"),
        label_intro_above=T("admin_intro_above", la),
        label_words_preview=T("admin_words_preview", la),
        hint_words_preview=T("admin_words_preview_hint", la),
        value_words_preview=esc(config.get("home_excerpt_words", 40)),
        label_articles_for_page=T("admin_articles_for_page", la),
        hint_articles_for_page=T("admin_articles_for_page_hint", la),
        value_articles_for_page=esc(config.get("articles_per_page", 10)),
        checked_home_featured=checked_if(config.get("home_featured", True)),
        label_home_featured=T("admin_home_featured", la),
        hint_home_featured=T("admin_home_featured_hint", la),
        checked_cover_article=checked_if(config.get("article_cover", True)),
        label_copy_link=T("admin_copy_link", la),
        hint_copy_link=T("admin_copy_link_hint", la),
        checked_copy_link=checked_if(config.get("share_buttons", True) is not False),
        label_width_pictures=T("admin_width_pictures", la),
        hint_width_pictures=T("admin_width_pictures_hint", la),
        value_width_pictures=max_image_side(),
        label_grp_helpers_ai=T("admin_grp_helpers_ai", la),
        label_backlink=T("admin_backlink", la),
        hint_backlink=T("admin_backlink_hint", la),
        value_backlink=esc(seo.get("backlink_site", "")),
        label_cover_article=T("admin_cover_article", la),
        hint_cover_article=T("admin_cover_article_hint", la),
        hint_seo=T("admin_seo_intro", la),
        label_seo_author_url=T("admin_seo_author_url", la),
        hint_seo_author_url=T("admin_seo_author_url_hint", la),
        value_seo_author_url=esc(seo.get("author_url", "")),
        ph_seo_author_url=ph["seo_author_url"],
        label_seo_author_picture=T("admin_seo_author_picture", la),
        value_seo_author_picture=esc(seo.get("author_image", "")),
        ph_seo_author_image=ph["seo_author_image"],
        label_seo_author_role=T("admin_seo_author_role", la),
        hint_seo_author_role=T("admin_seo_author_role_hint", la),
        value_seo_author_role=esc(seo.get("author_role", "")),
        ph_seo_author_role=ph["seo_author_role"],
        label_seo_author_bio=T("admin_seo_author_bio", la),
        hint_seo_author_bio=T("admin_seo_author_bio_hint", la),
        value_seo_author_bio=esc(seo.get("author_bio", "")),
        label_grp_other_f_language=TL("admin_grp_other_f_language", la),
        hint_other_f_language=TL("admin_other_f_language_hint", la),
        label_subtitle_en=TL("admin_subtitle_en", la),
        value_subtitle_en=esc(config.get("subtitle_en", "")),
        label_role_en=TL("admin_role_en", la),
        value_role_en=esc(seo.get("author_role_en", "")),
        label_bio_en=TL("admin_bio_en", la),
        value_bio_en=esc(seo.get("author_bio_en", "")),
        code_other_f_language="en" if site_language == "it" else "it",
        icon_ai=icon(ICON_AI_SPARKLE),
        ph_seo_author_bio=ph["seo_author_bio"],
        label_seo_profiles=T("admin_seo_profiles", la),
        hint_seo_profiles=T("admin_seo_profiles_hint", la),
        value_seo_profiles=esc("\n".join(profiles)),
        label_seo_logo=T("admin_seo_logo", la),
        value_seo_logo=esc(seo.get("logo", "")),
        ph_seo_logo=ph["seo_logo"],
        label_seo_twitter=T("admin_seo_twitter", la),
        hint_seo_twitter=T("admin_seo_twitter_hint", la),
        value_seo_twitter=esc(seo.get("twitter_site", "")),
        ph_seo_twitter=ph["seo_twitter"],
        label_seo_favicon=T("admin_seo_favicon", la),
        hint_seo_favicon=T("admin_seo_favicon_hint", la),
        value_seo_favicon=esc(seo.get("favicon", "")),
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
        value_ai_email=esc(ai_training.get("contact_email", "")),
        label_ai_license_url=T("admin_ai_training_license_url", la),
        hint_ai_license_url=T("admin_ai_training_license_url_hint", la),
        value_ai_license_url=esc(ai_training.get("license_url", "")),
        label_ai_statement=T("admin_ai_training_statement", la),
        hint_ai_statement=T("admin_ai_training_statement_hint", la),
        value_ai_statement=esc(ai_training.get("statement", "")),
        note_text_ai_standard=T("admin_ai_training_note_text_standard", la),
        label_fix_comments=T("admin_fix_comments", la),
        sel_comments_nobody=selected_if(commenti, "none"),
        label_comments_nobody=T("admin_comments_nobody", la),
        sel_giscus=selected_if(commenti, "giscus"),
        sel_disqus=selected_if(commenti, "disqus"),
        value_giscus_repo=esc(giscus.get("repo", "")),
        value_giscus_repo_id=esc(giscus.get("repo_id", "")),
        value_giscus_category=esc(giscus.get("category", "")),
        value_giscus_category_id=esc(giscus.get("category_id", "")),
        label_theme=T("admin_theme_label", la),
        value_giscus_theme=esc(giscus.get("theme", "light")),
        hint_disqus=T("admin_disqus_hint", la),
        value_disqus_shortname=esc(disqus.get("shortname", "")),
        label_translation_of=TL("admin_translation_of_title", la),
        hint_translation_of=T("admin_translation_of_intro", la),
        label_service_translation_of=T("admin_service_translation_of", la),
        sel_deepl=selected_if(translation_service, "deepl"),
        sel_google=selected_if(translation_service, "google"),
        sel_llm=selected_if(translation_service, "llm"),
        sel_openai=selected_if(translation_service, "openai"),
        sel_deepseek=selected_if(translation_service, "deepseek"),
        label_key_api=T("admin_key_api", la),
        ph_leave_empty_m=esc(T("admin_leave_empty_m", la)),
        value_deepl_key=esc(translation.get("deepl_api_key", "")),
        value_google_key=esc(translation.get("google_api_key", "")),
        value_llm_key=esc(translation.get("llm_api_key", "")),
        label_endpoint=T("admin_endpoint", la),
        value_llm_endpoint=esc(translation.get("llm_endpoint", "")),
        label_template=T("admin_template_label", la),
        value_llm_template=esc(translation.get("llm_model", "")),
        value_openai_key=esc(translation.get("openai_api_key", "")),
        value_openai_template=esc(translation.get("openai_model", "gpt-4o-mini")),
        value_deepseek_key=esc(translation.get("deepseek_api_key", "")),
        value_deepseek_template=esc(translation.get("deepseek_model", "deepseek-chat")),
        label_save_rebuild=T("admin_save_rebuild", la),
        label_config_advanced_f=T("admin_config_advanced_f", la),
        hint_config_advanced_f=T("admin_config_advanced_f_hint", la),
        label_save_config_raw=T("admin_save_config_raw", la),
        label_restore=T("admin_restore", la),
    )
    for key, _ in CONFIG_SECTIONS:
        context["section_header_" + key] = config_section_header(key, la, config)
    # The hints used to sit in brackets after the label; under the field
    # they read as a sentence of their own.
    for key in context:
        if key.startswith("hint_"):
            context[key] = help_text(context[key])
    contenuto = render.render("admin/config.html", **context)

    page_data = {
        "page": "config",
        "preview_kind": "home",
        # The admin address as saved: changing it is checked before saving.
        "admin_url": admin_address(config),
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

    return admin_page_shell(T("admin_settings_page", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("config", la),
                            head_extra=head_extra, script_extra=script_extra,
                            page_data=page_data, body_class="page-config")


# ---------------------------------------------------------------------------
# THE HTTP HANDLER
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    """
    Handle the editor requests and serve the static preview.

    It derives from the bare BaseHTTPRequestHandler, not from
    SimpleHTTPRequestHandler: every page is served by our own code, and the
    file serving of the parent class only stayed reachable through HEAD,
    which it answered for any file of the working directory -
    admin_password.txt and config.json included. Without a do_HEAD a HEAD
    request now gets 501.
    """

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

    def _send(self, content, tipo="text/html", with_csp=True, sandbox=False):
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self._no_store()
        self._security_headers(with_csp)
        if sandbox:
            # A public page shown by the editor runs the code of outside
            # services, which the preview is there to show. The sandbox gives
            # the page an origin of its own: the code runs, but it cannot read
            # the session cookie or ask the editor for its settings.
            self.send_header("Content-Security-Policy", PREVIEW_SANDBOX)
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

    def _proxied(self):
        """Whether the request came through the reverse proxy."""
        return (self.headers.get("X-Real-IP", "").strip() != ""
                or self.headers.get("X-Forwarded-For", "").strip() != "")

    def _side(self):
        """
        Which address the request came to, when the administration has an
        address of its own: "admin", "public", or "any" when the split does
        not apply - no admin address set, a request that reached the editor
        directly (on a computer, through an SSH tunnel), or a proxy that does
        not pass the Host on. Those keep working as they always did, so a
        mistake in the setup never locks the author out.
        """
        admin = admin_address()
        if admin == "" or not self._proxied():
            return "any"
        host = self.headers.get("Host", "").strip().lower()
        for default_port in (":80", ":443"):
            if host.endswith(default_port):
                host = host[:-len(default_port)]
        name = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
        if name in ("", "localhost", "127.0.0.1", "[::1]"):
            return "any"
        return "admin" if host == url_host(admin) else "public"

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

    def _may_set_first_password(self):
        """
        Tell whether this request may create the first password.

        Until a password exists, whoever fills in the form becomes the
        author. On a computer that is the person installing PyBlog; on a
        server published through nginx before the password was set, it would
        be the first visitor to find the page. A request the reverse proxy
        forwarded therefore has to come from this very machine; one that
        reaches the editor directly (on a computer, or Docker's port bound to
        localhost) is let through, as before.
        """
        if not self._proxied():
            return True
        client = self._client_address()
        return client.startswith("127.") or client in ("::1", "::ffff:127.0.0.1")

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

        # --- The administration on an address of its own ---
        # On the public address the administration is not there: an old
        # bookmark is sent on to the new address, so nothing of the editor
        # is ever served next to the code of outside services. On the admin
        # address, the pages of the public site are sent to the public one.
        side = self._side()
        if side == "public" and (route in ("/login", "/logout") or route in ADMIN_GET_ROUTES):
            self._redirect(admin_address() + self.path)
            return
        if route == "/pyblog-ping":
            self._send_ping(query.get("n", [""])[0])
            return
        if route in LEGACY_NEWSLETTER_ROUTES:
            # Emails already sent carry the old Italian addresses: they keep
            # working, and land on the new one.
            target = LEGACY_NEWSLETTER_ROUTES[route]
            if parsed.query:
                target = target + "?" + parsed.query
            self.send_response(301)
            self.send_header("Location", target)
            self._security_headers(False)
            self.end_headers()
            return

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
        if route in ("/confirm", "/unsubscribe"):
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
        if side == "admin" and pathlib.PurePosixPath(route).suffix in ("", ".html", ".htm"):
            # A page of the public site carries the code of outside services:
            # on the admin address it would run next to the editor. Stylesheets,
            # scripts and images are files, not pages, and stay here: the
            # editor's previews and the uploads need them.
            if route == "/":
                self._redirect("/admin")
                return
            public = public_site_url("")
            if public == "":
                self.send_error(404, "The public site has no address in the Settings.")
                return
            self._redirect(public + self.path)
            return
        self._serve_output(route)

    def _send_ping(self, nonce):
        """
        A sign of life. Before saving an address of its own for the
        administration, the server asks that address for this page with a
        word only it knows (see _api_check_admin_address): the word coming
        back means the address already leads to this very editor, so the
        author is not sent to an address that leads nowhere, or elsewhere.
        """
        with PING_LOCK:
            known = nonce != "" and nonce in PING_NONCES
        payload = json.dumps({"pyblog": True, "same": known}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._no_store()
        self.end_headers()
        self.wfile.write(payload)

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
            # "Create the lab of this article": a new article, tied to it.
            starts_from = None
            if art is None and query.get("lab_of", [""])[0] != "":
                starts_from = load_article(query["lab_of"][0])
            new_kind = "lab"
            if query.get("kind", [""])[0] == "practical":
                new_kind = "practical"
            self._send(editor_page(art, csrf, starts_from, new_kind))
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
                           with_csp=False, sandbox=True)
        elif route == "/restore":
            self._send(restore_page(csrf))
        elif route == "/media-library":
            self._send(library_page(csrf))
        elif route == "/media-library-items":
            self._send_json(media_library_items())
        elif route == "/updates":
            self._send(updates_page(csrf))
        elif route == "/updates-status":
            self._send_json(updates_state(query.get("force", [""])[0] == "1"))
        elif route == "/automatic-backup":
            path_value = backup.automatic_backup_path(query.get("file", [""])[0])
            if path_value is None:
                self.send_error(404)
                return
            self._send_download(path_value, "application/zip")
        elif route == "/export":
            # Downloads a ZIP backup with all the articles and the configuration.
            self._handle_export()
        elif route == "/pick-point":
            self._handle_point_page(query)
        elif route == "/newsletter-subscribers.csv":
            data = newsletter.subscribers_csv().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="iscritti.csv"')
            self.send_header("Content-Length", str(len(data)))
            self._no_store()
            self._security_headers(False)
            self.end_headers()
            self.wfile.write(data)
        elif route == "/versions":
            # The earlier versions of an article, for the editor's window.
            self._send_json({"ok": True, "versions": list_versions(query.get("slug", [""])[0])})
        elif route == "/version":
            version = load_version(query.get("slug", [""])[0], query.get("id", [""])[0])
            if version is None:
                self._send_json({"ok": False, "error": T("err_article_not_found", admin_language())})
            else:
                self._send_json({"ok": True, "version": version})
        else:
            self.send_error(404)

    # --- Newsletter -----------------------------------------------------------

    def _site_url(self):
        """
        The site's address for the links in the emails.

        Without a domain in the Settings it falls back to localhost, never to
        the Host header: that one is written by whoever sends the request,
        and a confirmation email would carry their address to the reader.
        """
        return public_site_url(f"http://localhost:{PORT}")

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
            language, T(prefix + "_title", language),
            T(prefix + "_text", language).replace("{site}", site), action), status)

    def _handle_newsletter_post(self, route):
        """
        The sign-up form of the site, and the buttons of the confirmation
        and unsubscribe pages. None of them needs a session: the form asks
        for nothing more than an address, the others carry their token.
        """
        form = self._read_form()
        # The old Italian field names still arrive from pages cached before
        # the names went English.
        language = form.get("language", form.get("lingua", [main_language()]))[0]
        if language not in ("it", "en"):
            language = main_language()
        # Leaving always works, even with the newsletter switched off.
        if route != "/unsubscribe" and not newsletter.settings()["enabled"]:
            self.send_error(404)
            return
        if route == "/subscribe":
            # The hidden field is invisible to people: whoever fills it in is
            # a robot, and gets the same answer as everybody, with no email.
            if form.get("website", form.get("sito", [""]))[0].strip() != "":
                self._newsletter_page(language, "nl_request_sent")
                return
            if not newsletter.allowed_request(self._client_address()):
                self._newsletter_page(language, "nl_too_many", status=429)
                return
            result = newsletter.subscribe(form.get("email", [""])[0], language, self._site_url())
            if result == "invalid":
                self._newsletter_page(language, "nl_invalid_value", status=400)
            elif result == "error":
                self._newsletter_page(language, "nl_failure", status=503)
            else:
                self._newsletter_page(language, "nl_request_sent")
            return
        token = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("t", [""])[0]
        language = newsletter.token_language(token) or language
        if route == "/confirm":
            done = newsletter.confirm(token)
            self._newsletter_page(language, "nl_confirmed_f" if done else "nl_link")
        else:
            done = newsletter.unsubscribe(token)
            self._newsletter_page(language, "nl_unsubscribed" if done else "nl_link")

    def _handle_newsletter_link(self, route, query):
        """
        The page a link in an email opens: a button that does the thing. The
        link alone changes nothing, because mail scanners open every link.
        """
        token = query.get("t", [""])[0]
        language = newsletter.token_language(token)
        if language == "" or (route == "/confirm" and not newsletter.settings()["enabled"]):
            self._newsletter_page(language or main_language(), "nl_link", status=404)
            return
        if route == "/confirm":
            prefix, button = "nl_confirm_page", T("nl_confirm_button", language)
        else:
            prefix, button = "nl_unsubscribe", T("nl_unsubscribe_button", language)
        action = (f'        <form method="post" action="{route}?t={urllib.parse.quote(token)}">\n'
                  f'          <input type="hidden" name="language" value="{language}">\n'
                  f'          <button class="button button-primary" type="submit">{esc(button)}</button>\n'
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
        backup.write_backup(archive)

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

        # --- On the public address only the readers' forms answer ---
        if route in LEGACY_NEWSLETTER_ROUTES:
            route = LEGACY_NEWSLETTER_ROUTES[route]
        if self._side() == "public" and route not in NEWSLETTER_ROUTES:
            self.send_error(404)
            return

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
        if route in NEWSLETTER_ROUTES:
            self._handle_newsletter_post(route)
            return

        # --- From here on everything requires authentication ---
        if not self._user_is_authenticated():
            self._send_json({"ok": False, "error": T("err_unauthorized", la)})
            return

        # --- ...and a valid CSRF token ---
        # A session cookie alone proves the browser is logged in, not that the
        # request came from one of our pages. Another site can make the browser
        # send the cookie; only our pages know this token. The check covers
        # every route, listed or not.
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
        if route == "/restore":
            self._handle_restore_upload()
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
            "/newsletter-test": self._api_newsletter_test,
            "/check-admin-address": self._api_check_admin_address,
            "/restore-automatic": self._api_restore_automatic,
            "/media-library-delete": self._api_delete_media,
            "/update": self._api_update,
            "/updates-auto": self._api_automatic_check,
            "/newsletter-remove": self._api_newsletter_remove,
        }
        handler = handlers.get(route)
        if handler is None:
            self.send_error(404)
            return
        try:
            self._send_json(handler(data))
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)})

    def _send_download(self, path_value, content_type):
        """Send a file as a download, a megabyte at a time."""
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", 'attachment; filename="' + path_value.name + '"')
        self.send_header("Content-Length", str(path_value.stat().st_size))
        self._no_store()
        self._security_headers(False)
        self.end_headers()
        with open(path_value, "rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _handle_restore_upload(self):
        """
        Receive a backup archive and put it back.

        The browser sends the file as it is, not as a form: an archive with
        videos can weigh hundreds of megabytes, and it goes straight to a
        temporary file next to the others instead of into memory.
        """
        la = admin_language()
        length = self._content_length(MAX_BACKUP_BODY)
        if length is None:
            self._send_json({"ok": False, "error": T("err_file_too_large", la).replace(
                "{n}", str(MAX_BACKUP_BODY // (1024 * 1024)))})
            return
        if length == 0:
            self._send_json({"ok": False, "error": T("err_no_file_received", la)})
            return
        backup.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=str(backup.BACKUPS_DIR), suffix=".caricato")
        try:
            with os.fdopen(descriptor, "wb") as target:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        break
                    target.write(chunk)
                    remaining -= len(chunk)
            if remaining > 0:
                self._send_json({"ok": False, "error": T("err_malformed_upload", la)})
                return
            self._send_json(self._restore_from(pathlib.Path(temporary)))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _api_update(self, data):
        """
        Install the update and restart. The site's backup is saved first,
        among the automatic ones of the restore page.
        """
        la = admin_language()
        result = updates.update(save_backup=backup.save_automatic_backup)
        if result.get("ok") is not True:
            message = T(result.get("error", "upd_failed_upd"), la)
            if result.get("detail"):
                message = message + " " + result["detail"]
            return {"ok": False, "error": message}
        updates.restart()
        return {"ok": True, "from": result["from"], "to": result["to"]}

    def _api_automatic_check(self, data):
        updates.set_automatic_check(data.get("on") is True)
        return {"ok": True, "auto": updates.automatic_check_enabled()}

    def _api_delete_media(self, data):
        """Move uploaded files to the trash of the media library."""
        deleted = media_library.delete_media(data.get("names", []))
        return {"ok": True, "deleted": deleted}

    def _api_restore_automatic(self, data):
        """Put back one of the automatic backups, to undo a restore."""
        path_value = backup.automatic_backup_path(data.get("file", ""))
        if path_value is None:
            return {"ok": False, "error": T("err_backup_not_found", admin_language())}
        return self._restore_from(path_value)

    def _restore_from(self, path_value):
        """
        Check an archive, save the current state, put the archive back and
        rebuild the site, all under the build lock: no save and no build can
        run in the middle.
        """
        la = admin_language()
        with BUILD_LOCK:
            try:
                content = backup.read_backup(path_value)
                saved = backup.save_automatic_backup()
                summary = backup.restore_backup(content)
            except backup.BackupError as error:
                return {"ok": False, "error": T(str(error), la)}
            reload_global_config()
            build()
        summary["ok"] = True
        summary["automatic"] = saved.name
        return summary

    def _api_check_admin_address(self, data):
        """
        Check that a new address for the administration leads here.

        The browser cannot ask another address itself (the admin's policy
        allows connections to its own address only), so the server does:
        it asks the address for /pyblog-ping with a word it just made up,
        and only this process can recognise it. The certificate is checked
        too, as a browser would.
        """
        address = str(data.get("url", "")).strip().rstrip("/")
        if admin_address({"admin_url": address}) == "":
            return {"ok": False, "error": T("js_admin_url_not_valid", admin_language())}
        nonce = secrets.token_urlsafe(16)
        with PING_LOCK:
            PING_NONCES.add(nonce)
        try:
            request = urllib.request.Request(address + "/pyblog-ping?n=" + nonce,
                                             headers={"User-Agent": "PyBlog"})
            with urllib.request.urlopen(request, timeout=8) as response:
                answer = json.loads(response.read(2048).decode("utf-8"))
            same = isinstance(answer, dict) and answer.get("same") is True
        except Exception:
            same = False
        finally:
            with PING_LOCK:
                PING_NONCES.discard(nonce)
        return {"ok": True, "reaches": same}

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
            return {"ok": False, "error": T("admin_nl_sender_email", admin_language()) + " / "
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
                   with_csp=False, sandbox=True)

    def _handle_set_password(self):
        """First run: create the administration password."""
        # If a password already exists, we do not allow resetting it from here.
        if password_is_set():
            self._redirect("/login")
            return
        la = admin_language()
        if not self._may_set_first_password():
            self._send(set_password_page(T("err_setup_remote", la)))
            return
        form = self._read_form()
        password = form.get("password", [""])[0]
        confirmed = form.get("conferma", [""])[0]
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
