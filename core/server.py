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
import io
import json
import mimetypes
import time
import urllib.parse
import zipfile
from datetime import datetime

from core import build as build_module
from core import i18n, render
from core.ai import (analyze_article_seo, generate_reader_preview,
                     generate_seo_description, translate_text)
from core.articles import (MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, delete_article,
                           html_content_is_empty, load_article, load_articles,
                           save_article, save_uploaded_file, validate_upload)
from core.docx_import import convert_docx, looks_like_docx
from core.auth import (create_session_token, csrf_token_for,
                       csrf_token_is_valid, destroy_all_sessions,
                       destroy_session, login_is_locked, login_lock_remaining,
                       password_is_set, record_failed_login,
                       record_successful_login, session_is_valid, set_password,
                       verify_password)
from core.build import (BUILD_LOCK, build, compute_reading_time, format_date,
                        generate_article_page)
from core.config import (CONFIG, CONFIG_FILE, OUTPUT_DIR, PORT, POSTS_DIR,
                         admin_language, load_config, reload_global_config,
                         save_config)
from core.i18n import T
from core.render import esc, js

# Bootstrap version loaded from a CDN for all the administration pages.
BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"

QUILL_CSS = "https://cdn.quilljs.com/1.3.7/quill.snow.css"
QUILL_JS = "https://cdn.quilljs.com/1.3.7/quill.min.js"
BLOT_FORMATTER_JS = "https://unpkg.com/quill-blot-formatter@1.0.5/dist/quill-blot-formatter.min.js"
HLJS_CSS = "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css"
HLJS_JS = "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"

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
    "/import-docx",
)

# The files the administration area serves from static/. Naming them makes
# the route an allowlist rather than a path check.
ADMIN_STATIC_FILES = ("common.css", "admin.css", "admin.js")

# The GET routes handled by the administration, as opposed to the static site.
ADMIN_GET_ROUTES = ("/admin", "/config", "/edit", "/change-password",
                    "/preview", "/export")


# ---------------------------------------------------------------------------
# STRINGS HANDED TO THE ADMIN JAVASCRIPT
# ---------------------------------------------------------------------------
# admin.js contains no translated text at all: everything it displays is
# looked up in window.PB_I18N. These are the keys it can ask for.

JS_TRANSLATION_KEYS = (
    # Pasting from Word and uploads
    "js_recovering_pasted_images", "js_pasted_all_recovered",
    "js_pasted_partial_recovered", "js_uploading", "js_uploading_image",
    "js_video_uploaded", "js_image_uploaded", "js_upload_error",
    "js_error_prefix",
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
    # Settings
    "admin_salvataggio", "admin_config_salvata", "admin_errore_salvataggio",
    "admin_config_raw_salvata", "err_invalid_json_prefix",
    # Shared dialogs, saving, autosave and the Word import
    "admin_chiudi", "admin_annulla", "admin_elimina",
    "js_article_saved", "js_save_error", "js_unsaved_changes",
    "js_autosaving", "js_autosaved_at", "js_autosave_failed",
    "js_autosave_needs_title", "js_delete_title", "js_delete_body",
    "js_site_rebuilt_error",
    "js_docx_importing", "js_docx_imported", "js_docx_net_error",
    "js_docx_overwrite_title", "js_docx_overwrite_body",
    "js_docx_overwrite_confirm", "js_docx_warnings_title",
    "js_docx_wrong_extension", "err_file_too_large",
)

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


def js_translations(language):
    """
    Build the object injected as window.PB_I18N: the strings admin.js needs,
    the toolbar tooltip map, and the two homepage placeholders (which are
    always needed in both languages, one per editor).
    """
    result = i18n.subset(JS_TRANSLATION_KEYS, language)

    tooltips = {}
    for selector, key in TOOLBAR_TOOLTIP_KEYS:
        tooltips[selector] = T(key, language)
    result["tooltips"] = tooltips

    # The Italian editor gets the Italian ghost text and the English one the
    # English text, whatever the language of the interface.
    result["js_home_intro_placeholder_it"] = T("js_home_intro_placeholder", "it")
    result["js_home_intro_placeholder_en"] = T("js_home_intro_placeholder", "en")
    return result


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

def admin_navbar(active_page, language):
    """
    Shared navigation bar of the admin area.
    active_page highlights the current item ("articles" or "config").
    """
    voci = [
        ("articles", "/admin", T("admin_articoli", language)),
        ("config", "/config", T("admin_impostazioni", language)),
    ]
    link_html = []
    for key, url, label in voci:
        classe = "nav-link"
        if key == active_page:
            classe = "nav-link active"
        link_html.append(
            f'<li class="nav-item"><a class="{classe}" href="{url}">{label}</a></li>')

    # The language switch shows the language you are switching to.
    if language == "it":
        next_language = "en"
        language_label = "EN"
    else:
        next_language = "it"
        language_label = "IT"

    return render.render(
        "admin/navbar.html",
        voci="\n".join(link_html),
        vedi_blog=T("admin_vedi_blog", language),
        password=T("admin_password", language),
        esci=T("admin_esci", language),
        prossima_lingua=next_language,
        title_lingua="Lingua interfaccia",
        etichetta_lingua=language_label,
    )


def admin_page_shell(titolo, contenuto, language, csrf="", navbar="",
                     head_extra="", script_extra="", page_data=None):
    """Wrap an admin page body in templates/admin/base.html."""
    if page_data is None:
        page_data = {}
    return render.render(
        "admin/base.html",
        lang=language,
        titolo_pagina=esc(titolo),
        bootstrap_css=BOOTSTRAP_CSS,
        bootstrap_js=BOOTSTRAP_JS,
        head_extra=build_module.block(head_extra),
        navbar=build_module.block(navbar),
        label_chiudi=T("admin_chiudi", language),
        label_annulla=T("admin_annulla", language),
        contenuto=contenuto,
        i18n=js(js_translations(language)),
        csrf=js(csrf),
        page_data=js(page_data),
        script_extra=build_module.block(script_extra),
    )


def alert_block(message, kind):
    """A Bootstrap alert, or nothing when there is no message."""
    if message == "":
        return ""
    return f'<div class="alert alert-{kind} py-2">{esc(message)}</div>'


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
        crea_accedi=T("admin_crea_accedi", la),
    )
    return admin_page_shell(T("admin_crea_password_titolo", la), contenuto, la)


def change_password_page(csrf, error_message="", success_message=""):
    """Page to change the password while logged in."""
    la = admin_language()
    contenuto = render.render(
        "admin/change_password.html",
        titolo=T("admin_cambia_password", la),
        errore=alert_block(error_message, "danger"),
        successo=alert_block(success_message, "success"),
        csrf_token=esc(csrf),
        label_attuale=T("admin_password_attuale", la),
        label_nuova=T("admin_nuova_password", la),
        label_conferma=T("admin_conferma_nuova", la),
    )
    return admin_page_shell(T("admin_cambia_password", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("", la))


def admin_page(articles, csrf):
    """
    Administration dashboard: the list of every article with its status,
    a search box, and quick actions (edit, preview, delete).
    """
    la = admin_language()
    # We count published and drafts to show some statistics at the top.
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
                f'href="/preview?slug={esc(art["slug"])}&amp;language=en" target="_blank">'
                f'{T("admin_anteprima", la)} EN</a>')

        # Sorting happens in the browser, so every row carries the keys it
        # can be sorted by. Drafts sort first, because they are the ones
        # still waiting for work.
        if art.get("status") == "published":
            status_order = "1"
        else:
            status_order = "0"

        lines.append(render.render(
            "admin/dashboard_row.html",
            titolo_minuscolo=esc(art["title"].lower()),
            data_iso=esc(art.get("date", "")),
            ordine_stato=status_order,
            tempo_lettura=compute_reading_time(art.get("content", ""), la),
            classe_badge=classe_badge,
            etichetta_badge=badge_label,
            badge_en=badge_en,
            slug=esc(art["slug"]),
            slug_js=js(art["slug"]),
            titolo=esc(art["title"]),
            titolo_js=js(art["title"]),
            data=format_date(art["date"], la),
            descrizione=esc(art.get("description", "")),
            classe_stato=status_class,
            azione_stato_js=js(status_action),
            etichetta_stato=status_label,
            label_modifica=T("admin_modifica", la),
            label_anteprima=T("admin_anteprima", la),
            link_anteprima_en=preview_en_link,
            label_elimina=T("admin_elimina", la),
        ).rstrip("\n"))

    if len(lines) > 0:
        listing = "\n".join(lines)
    else:
        listing = ('<div class="text-center text-secondary p-5 border border-dashed '
                   f'rounded bg-white">{T("admin_nessun_articolo", la)}</div>')

    contenuto = render.render(
        "admin/dashboard.html",
        label_articoli=T("admin_articoli", la),
        titolo_sito=esc(CONFIG["site_title"]),
        nuovo_articolo=T("admin_nuovo_articolo", la),
        totale=len(articles),
        label_totali=T("admin_totali", la),
        pubblicati=published_count,
        label_pubblicati=T("admin_pubblicati", la),
        bozze=draft_count,
        label_bozze=T("admin_bozze", la),
        label_impostazioni=T("admin_impostazioni_home", la),
        label_rigenera=T("admin_rigenera", la),
        label_backup=T("admin_scarica_backup", la),
        placeholder_filtro=esc(T("admin_filtra", la)),
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
        contenuto, la, csrf=csrf, navbar=admin_navbar("articles", la),
        page_data={"page": "dashboard"})


def editor_page(art, csrf):
    """The page with the WYSIWYG editor (it uses Quill, loaded from a CDN)."""
    la = admin_language()

    # If we are editing an existing article, we take its values.
    # If instead this is a new article (art is None), we start from empty fields.
    if art is not None:
        page_title = T("admin_modifica_articolo_titolo", la)
        delete_button = (f'<button class="delete-btn" onclick="deleteItem()">'
                         f'{T("admin_elimina", la)}</button>')
    else:
        art = {}
        page_title = T("admin_nuovo_articolo_titolo", la)
        delete_button = ""

    status = art.get("status", "draft")
    published_selected = ""
    draft_selected = ""
    if status == "published":
        published_selected = "selected"
    else:
        draft_selected = "selected"

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
        tip_preview=esc(T("tip_preview", la)),
        label_anteprima=T("admin_mostra_anteprima", la),
        label_salva=T("admin_salva_genera", la),
        label_salva_chiudi=T("admin_salva_chiudi", la),
        bottone_elimina=delete_button,
        label_sezione_pubblicazione=T("admin_sezione_pubblicazione", la),
        label_stato=T("admin_stato", la),
        selected_bozza=draft_selected,
        label_bozza=T("admin_bozza", la),
        selected_pubblicato=published_selected,
        label_pubblicato=T("admin_pubblicato", la),
        label_sezione_metadati=T("admin_sezione_metadati", la),
        valore_slug=esc(art.get("slug", "")),
        label_tag=T("admin_tag", la),
        valore_tag=esc(art.get("tags", "")),
        label_immagine=T("admin_immagine_copertina", la),
        valore_immagine=esc(art.get("image", "")),
        label_anteprima_lettori=T("admin_anteprima_lettori", la),
        hint_anteprima=T("admin_anteprima_hint", la),
        valore_anteprima=esc(art.get("preview", "")),
        label_genera_anteprima=T("admin_genera_anteprima", la),
        label_descrizione_seo=T("admin_descrizione_seo", la),
        hint_descrizione=T("admin_descrizione_hint", la),
        valore_descrizione=esc(art.get("description", "")),
        label_suggerisci=T("admin_suggerisci_descrizione", la),
        label_analisi_seo=T("admin_analisi_seo", la),
        hint_analisi_seo=T("admin_analisi_seo_hint", la),
        label_analizza=T("admin_analizza_seo", la),
        label_versione_inglese=T("admin_versione_inglese", la),
        label_autorizza=T("admin_autorizza_traduzione", la),
        label_traduci=T("admin_traduci_auto", la),
        label_anteprima_en=T("admin_anteprima_en", la),
        hint_anteprima_en=T("admin_anteprima_en_hint", la),
        label_conferma_traduzione=T("admin_conferma_traduzione", la),
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
        "slug": art.get("slug", ""),
        "content": art.get("content", ""),
        "title_en": art.get("title_en", ""),
        "description_en": art.get("description_en", ""),
        "preview_en": art.get("preview_en", ""),
        "content_en": art.get("content_en", ""),
        "translation_authorized": art.get("translation_authorized", False),
        "translation_confirmed": art.get("translation_confirmed", False),
    }

    head_extra = (f'<link href="{QUILL_CSS}" rel="stylesheet">\n'
                  f'<link href="{HLJS_CSS}" rel="stylesheet">\n'
                  f'<script src="{HLJS_JS}"></script>')
    script_extra = (f'<script src="{QUILL_JS}"></script>\n'
                    f'<script src="{BLOT_FORMATTER_JS}"></script>')

    return admin_page_shell(page_title, contenuto, la, csrf=csrf,
                            navbar=admin_navbar("articles", la),
                            head_extra=head_extra, script_extra=script_extra,
                            page_data=page_data)


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

    # --- Homepage structure: three dropdowns, one per position ---
    order = config.get("home_order", ["intro", "cards", "articles"])
    if not isinstance(order, list) or len(order) != 3:
        order = ["intro", "cards", "articles"]
    sezioni = ("intro", "cards", "articles")
    order_selects = []
    for posizione in range(3):
        choices = []
        for section_name in sezioni:
            selected = ""
            if order[posizione] == section_name:
                selected = " selected"
            label = T("admin_section_" + section_name, la)
            choices.append(f'<option value="{section_name}"{selected}>{label}</option>')
        order_selects.append(
            f'<select class="ordine-home" id="ordine_home_{posizione}">'
            + "".join(choices) + "</select>")

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

    contenuto = render.render(
        "admin/config.html",
        titolo_pagina_h1=T("admin_impostazioni_titolo", la),
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
        label_presentazione_inglese=T("admin_presentazione_inglese", la),
        hint_presentazione_en=T("admin_presentazione_en_hint", la),
        label_traduci_italiano=T("admin_traduci_dall_italiano", la),
        label_card_home=T("admin_card_home_titolo", la),
        hint_card_home=T("admin_card_home_hint", la),
        card_html="\n".join(card_html_parti),
        label_impostazioni_generali=T("admin_impostazioni_generali", la),
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
        valore_lingua=esc(site_language),
        label_layout=T("admin_layout_titolo", la),
        hint_layout=T("admin_layout_hint", la),
        label_posizione=T("admin_posizione", la),
        select_ordine_0=order_selects[0],
        select_ordine_1=order_selects[1],
        select_ordine_2=order_selects[2],
        label_articoli_per_pagina=T("admin_articoli_per_pagina", la),
        hint_articoli_per_pagina=T("admin_articoli_per_pagina_hint", la),
        valore_articoli_per_pagina=esc(config.get("articles_per_page", 10)),
        label_seo=T("admin_seo_titolo", la),
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
        label_ai_training=T("admin_ai_training_titolo", la),
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
        label_commenti=T("admin_commenti_titolo", la),
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
        label_traduzione=T("admin_traduzione_titolo", la),
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

    page_data = {
        "page": "config",
        "preview_kind": "home",
        "max_image_mb": MAX_IMAGE_BYTES // (1024 * 1024),
        "max_video_mb": MAX_VIDEO_BYTES // (1024 * 1024),
        "home_content": config.get("home_content", ""),
        "home_content_en": config.get("home_content_en", ""),
        "card_contents": card_contents,
        "config_raw": json.dumps(config, ensure_ascii=False, indent=2),
    }

    head_extra = f'<link href="{QUILL_CSS}" rel="stylesheet">'
    script_extra = (f'<script src="{QUILL_JS}"></script>\n'
                    f'<script src="{BLOT_FORMATTER_JS}"></script>')

    return admin_page_shell(T("admin_impostazioni_titolo", la), contenuto, la,
                            csrf=csrf, navbar=admin_navbar("config", la),
                            head_extra=head_extra, script_extra=script_extra,
                            page_data=page_data)


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

    def _send(self, content, tipo="text/html", with_csp=True):
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self._security_headers(with_csp)
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
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
        else:
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
            preview_language = query.get("language", ["it"])[0]
            if preview_language not in ("it", "en"):
                preview_language = "it"
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
        else:
            self.send_error(404)

    def _handle_export(self):
        """
        Create a ZIP archive in memory with every article (JSON files) and
        the configuration, and send it as a download.
        It is the complete backup of the blog contents.
        """
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
        self._security_headers(False)
        self.end_headers()
        self.wfile.write(data)

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
        if submitted == "" and route == "/change-password":
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
        """Save an article and rebuild the site."""
        with BUILD_LOCK:
            old_slug = data.get("original_slug", "")
            new_slug = save_article(data)
            # If the slug has changed, remove the old file.
            if old_slug and old_slug != new_slug:
                delete_article(old_slug)
            build()  # rebuilds the static HTML right away
        return {"ok": True, "slug": new_slug}

    def _api_delete(self, data):
        """Delete an article and rebuild the site."""
        with BUILD_LOCK:
            delete_article(data["slug"])
            build()
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
        with BUILD_LOCK:
            article = load_article(data["slug"])
            if article is None:
                return {"ok": False,
                        "error": T("err_article_not_found", admin_language())}
            article["status"] = data["status"]
            save_article(article)
            build()
        return {"ok": True}

    def _api_save_config(self, data):
        """Save the settings form and rebuild the site."""
        with BUILD_LOCK:
            # IMPORTANT: we merge with the existing configuration instead of
            # overwriting it. The form of the Settings page does not contain
            # ALL the fields (e.g. admin_language): without this merge, every
            # save would wipe them.
            config_attuale = load_config()
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
        if login_is_locked():
            self._send(login_page(
                T("err_too_many_attempts", la).replace("{n}", str(login_lock_remaining()))))
            return
        form = self._read_form()
        password = form.get("password", [""])[0]
        if verify_password(password):
            record_successful_login()
            token = create_session_token()
            self._redirect("/admin", cookie=self._session_cookie(token))
        else:
            record_failed_login()
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
            self._send_json({"ok": True, "url": url})

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
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
