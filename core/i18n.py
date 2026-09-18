"""
Internationalisation of the interface (i18n).

All the fixed labels of the public site and of the administration area live
here in Italian and English; T() returns the right one for a language. Nothing
written by the author goes through this module: only the fixed chrome does.

The strings the browser needs are handed to the JavaScript as a JSON object
(window.PB_I18N), never concatenated into a script: an Italian apostrophe
would otherwise close the surrounding JavaScript string.
"""

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
    "admin_table_hint": {"it": "Clic per selezionare, doppio clic per modificare",
                         "en": "Click to select, double-click to edit"},
    "js_table_format_not_applicable": {
        "it": "Questo formato sostituirebbe la tabella. Sulla tabella puoi usare allineamento, rientro, grassetto, corsivo, sottolineato, barrato e colori.",
        "en": "This format would replace the table. On a table you can use alignment, indent, bold, italic, underline, strikethrough and colours."},
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
    "admin_immagine_copertina": {"it": "Immagine di copertina", "en": "Cover image"},
    "admin_immagine_copertina_hint": {
        "it": "(appare nel blocco \u00abUltimo articolo\u00bb in homepage e nelle anteprime social. Carica un file oppure incolla un indirizzo.)",
        "en": "(appears in the \u201cLatest article\u201d block on the homepage and in social previews. Upload a file or paste an address.)"},
    "admin_carica_copertina": {"it": "Carica un'immagine", "en": "Upload an image"},
    "admin_rimuovi_copertina": {"it": "Rimuovi", "en": "Remove"},
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

    # --- Strings added when the admin JavaScript moved to static/admin.js ---
    # Everything the browser shows now comes from here through window.PB_I18N:
    # nothing visible is written into the .js file itself.
    "js_site_rebuilt": {"it": "Sito rigenerato: {n} articoli.", "en": "Site rebuilt: {n} articles."},
    "js_status_change_error": {"it": "Errore nel cambio di stato.", "en": "Error changing the status."},
    "js_site_rebuilt_error": {"it": "Rigenerazione del sito non riuscita.",
                              "en": "The site rebuild failed."},
    "js_delete_error": {"it": "Errore durante l'eliminazione.", "en": "Error while deleting."},
    "js_table_how_many_rows": {"it": "Quante righe? (intestazione inclusa)",
                               "en": "How many rows? (header included)"},
    "js_table_how_many_cols": {"it": "Quante colonne?", "en": "How many columns?"},
    "js_table_header_cell": {"it": "Intestazione", "en": "Header"},
    "js_table_body_cell": {"it": "testo", "en": "text"},
    "js_home_intro_placeholder": {
        "it": "Scrivi qui una breve presentazione: chi sei, di cosa ti occupi e "
              "perche' un lettore dovrebbe seguirti. Esempio: \u00abSono Maria, "
              "ingegnera del software. Scrivo di Python e architetture distribuite "
              "per chi vuole costruire sistemi affidabili.\u00bb",
        "en": "Write a short introduction here: who you are, what you work on, "
              "and why a reader should follow you. Example: \u00abI'm Jane, a "
              "software engineer. I write about Python and distributed systems "
              "for people who want to build reliable systems.\u00bb"},

    # --- Security messages ---
    "err_csrf": {"it": "Richiesta non valida: token di sicurezza mancante o scaduto. Ricarica la pagina.",
                 "en": "Invalid request: missing or expired security token. Reload the page."},
    "err_request_too_large": {"it": "Richiesta troppo grande.", "en": "Request too large."},
    "err_file_too_large": {"it": "File troppo grande. Il limite e' {n} MB.",
                           "en": "File too large. The limit is {n} MB."},
    "err_file_type_not_allowed": {"it": "Tipo di file non consentito.", "en": "File type not allowed."},
    "err_file_content_mismatch": {"it": "Il contenuto del file non corrisponde all'estensione dichiarata.",
                                  "en": "The file content does not match the declared extension."},
    "err_svg_unsafe": {"it": "L'SVG contiene elementi attivi che non e' stato possibile rimuovere con certezza: rifiutato.",
                       "en": "The SVG contains active elements that could not be removed with confidence: rejected."},
    "err_malformed_upload": {"it": "Caricamento malformato.", "en": "Malformed upload."},

    # --- Shrinking uploaded images ---
    "js_image_resized_local": {
        "it": "Immagine ridimensionata a {w}\u00d7{h} prima del caricamento.",
        "en": "Image resized to {w}\u00d7{h} before uploading."},
    "img_ridimensionata": {
        "it": "Immagine ridotta da {da} a {a}: {n} KB risparmiati.",
        "en": "Image reduced from {da} to {a}: {n} KB saved."},
    "img_metadati_rimossi": {
        "it": "Rimossi i metadati dell'immagine: {n} KB risparmiati.",
        "en": "Image metadata removed: {n} KB saved."},
    "img_jpeg_non_ridimensionabile": {
        "it": "L'immagine e' grande ma e' un JPEG: il server non puo' ridimensionarlo senza una libreria esterna. Se ti serve piu' piccola, ridimensionala prima di caricarla.",
        "en": "The image is large but it is a JPEG: the server cannot resize one without an external library. If you need it smaller, resize it before uploading."},
    "img_troppi_pixel": {
        "it": "L'immagine e' troppo grande per essere ridimensionata dal server ed e' stata tenuta com'e'.",
        "en": "The image is too large for the server to resize and was kept as it is."},

    # --- Word (.docx) import ---
    "admin_importa_word": {"it": "Importa da Word (.docx)", "en": "Import from Word (.docx)"},
    "tip_import_docx": {
        "it": "Carica un documento Word: testo, titoli, liste, tabelle e immagini finiscono nell'editor",
        "en": "Upload a Word document: text, headings, lists, tables and images land in the editor"},
    "admin_docx_hint": {
        "it": "Il documento viene convertito e messo nell'editor, non salvato: rivedilo prima di pubblicare.",
        "en": "The document is converted into the editor, not saved: review it before publishing."},
    "js_docx_importing": {"it": "Conversione del documento in corso...",
                          "en": "Converting the document..."},
    "js_docx_imported": {"it": "Documento importato. Rivedilo, poi salva.",
                         "en": "Document imported. Review it, then save."},
    "js_docx_net_error": {"it": "Errore di rete durante l'importazione.",
                          "en": "Network error during the import."},
    "js_docx_overwrite_title": {"it": "Sostituire il contenuto?", "en": "Replace the content?"},
    "js_docx_overwrite_body": {
        "it": "L'editor contiene gi\u00e0 del testo. Importando il documento Word verr\u00e0 sostituito. L'articolo non viene salvato: puoi ancora annullare ricaricando la pagina senza salvare.",
        "en": "The editor already contains text. Importing the Word document will replace it. The article is not saved: you can still back out by reloading the page without saving."},
    "js_docx_overwrite_confirm": {"it": "Sostituisci", "en": "Replace"},
    "js_docx_warnings_title": {"it": "Avvisi della conversione:", "en": "Conversion warnings:"},
    "js_docx_wrong_extension": {"it": "Scegli un file con estensione .docx (il vecchio formato .doc non \u00e8 supportato).",
                                "en": "Choose a file with a .docx extension (the old .doc format is not supported)."},

    "err_docx_not_a_zip": {
        "it": "Il file non \u00e8 un documento Word valido. Se \u00e8 un vecchio .doc, riaprilo in Word e salvalo come .docx.",
        "en": "The file is not a valid Word document. If it is an old .doc, reopen it in Word and save it as .docx."},
    "err_docx_no_document": {
        "it": "L'archivio non contiene un documento Word (manca word/document.xml).",
        "en": "The archive contains no Word document (word/document.xml is missing)."},
    "err_docx_parse": {"it": "Il documento Word non \u00e8 leggibile: il contenuto XML \u00e8 danneggiato.",
                       "en": "The Word document cannot be read: its XML content is damaged."},
    "err_docx_empty": {"it": "Il documento Word non contiene testo da importare.",
                       "en": "The Word document contains no text to import."},
    "err_docx_unreadable": {"it": "Impossibile leggere il file.", "en": "The file could not be read."},

    "warn_docx_image_skipped": {
        "it": "Immagine scartata ({name}): il formato non \u00e8 mostrabile in una pagina web.",
        "en": "Image skipped ({name}): the format cannot be shown in a web page."},
    "warn_docx_image_missing": {
        "it": "Immagine non incorporata nel documento ({name}): non c'\u00e8 nulla da estrarre.",
        "en": "Image not embedded in the document ({name}): there is nothing to extract."},
    "warn_docx_link_skipped": {
        "it": "Collegamento rimosso, indirizzo non consentito ({href}). Il testo \u00e8 rimasto.",
        "en": "Link removed, address not allowed ({href}). The text was kept."},
    "warn_docx_nested_table": {
        "it": "Una tabella dentro un'altra tabella \u00e8 stata ridotta a testo.",
        "en": "A table inside another table was reduced to text."},
    "warn_docx_numbering_missing": {
        "it": "Numerazione delle liste non leggibile: sono stati usati elenchi puntati.",
        "en": "List numbering could not be read: bulleted lists were used instead."},

    # --- Shared admin dialogs (toasts, confirmation modal) ---
    "admin_annulla": {"it": "Annulla", "en": "Cancel"},
    "admin_chiudi": {"it": "Chiudi", "en": "Close"},

    # --- Editor: saving, autosave, unsaved changes ---
    "admin_salva_chiudi": {"it": "Salva e chiudi", "en": "Save and close"},
    "admin_salva_resta": {"it": "Salva", "en": "Save"},
    "js_article_saved": {"it": "Articolo salvato e sito rigenerato.",
                         "en": "Article saved and site rebuilt."},
    "js_save_error": {"it": "Salvataggio non riuscito.", "en": "The save failed."},
    "js_unsaved_changes": {"it": "Ci sono modifiche non salvate in questo articolo.",
                           "en": "This article has unsaved changes."},
    "js_autosaving": {"it": "Salvataggio della bozza...", "en": "Saving the draft..."},
    "js_autosaved_at": {"it": "Bozza salvata alle {time}", "en": "Draft saved at {time}"},
    "js_autosave_failed": {"it": "Salvataggio automatico non riuscito, riprovo tra poco.",
                           "en": "Autosave failed, retrying shortly."},
    "js_autosave_needs_title": {"it": "Scrivi un titolo perch\u00e9 il salvataggio automatico possa partire.",
                                "en": "Write a title so the autosave can start."},
    "js_delete_title": {"it": "Eliminare l'articolo?", "en": "Delete the article?"},
    "js_delete_body": {
        "it": "\u00ab{title}\u00bb verr\u00e0 eliminato definitivamente, insieme alla sua pagina pubblica. L'operazione non si pu\u00f2 annullare.",
        "en": "\u201c{title}\u201d will be permanently deleted, along with its public page. This cannot be undone."},

    # --- Dashboard: sorting and reading time ---
    "admin_ordina": {"it": "Ordina", "en": "Sort"},
    "admin_ordina_recenti": {"it": "Pi\u00f9 recenti", "en": "Newest first"},
    "admin_ordina_vecchi": {"it": "Meno recenti", "en": "Oldest first"},
    "admin_ordina_titolo": {"it": "Titolo (A-Z)", "en": "Title (A-Z)"},
    "admin_ordina_stato": {"it": "Stato (bozze prima)", "en": "Status (drafts first)"},

    # --- Public site: code blocks, 404, reading progress ---
    "copia_codice": {"it": "Copia", "en": "Copy"},
    "codice_copiato": {"it": "Copiato", "en": "Copied"},
    "copia_codice_titolo": {"it": "Copia il codice negli appunti",
                            "en": "Copy the code to the clipboard"},
    "ultimi_articoli": {"it": "Ultimi articoli", "en": "Latest articles"},
    "cerca_nel_sito": {"it": "Cerca nel sito", "en": "Search the site"},
    "progresso_lettura": {"it": "Avanzamento della lettura", "en": "Reading progress"},
    "ultimo_articolo": {"it": "Ultimo articolo", "en": "Latest article"},
    "ingrandisci_immagine": {"it": "Ingrandisci l'immagine", "en": "Enlarge the image"},
    "chiudi_immagine": {"it": "Chiudi l'immagine", "en": "Close the image"},

    # --- Settings: the cover inside the article ---
    "admin_copertina_articolo": {"it": "Mostra la copertina anche dentro l'articolo",
                                 "en": "Show the cover inside the article too"},
    "admin_copertina_articolo_hint": {
        "it": "(sotto il titolo e la data. Spenta, la copertina resta solo negli elenchi e nell'anteprima social, e l'articolo si apre sulla prima riga di testo.)",
        "en": "(under the title and the date. When off, the cover stays in the listings and the social preview only, and the article opens on its first line of text.)"},

    # --- Settings: the highlighted article ---
    "admin_home_evidenza": {"it": "Metti in evidenza l'ultimo articolo",
                            "en": "Highlight the latest article"},
    "admin_home_evidenza_hint": {
        "it": "(l'articolo pi\u00f9 recente appare in un blocco pi\u00f9 grande in cima all'elenco, con la sua immagine di copertina se ne ha una)",
        "en": "(the most recent article appears in a larger block at the top of the list, with its cover image if it has one)"},
}


def T(key, language="it"):
    """
    Return the translation of an interface label in the given language.
    If the key or the language does not exist, return a safe fallback.
    """
    if key not in UI_TRANSLATIONS:
        return key
    entries = UI_TRANSLATIONS[key]
    if language in entries:
        return entries[language]
    if "it" in entries:
        return entries["it"]
    return key


def subset(keys, language):
    """
    Return {key: translation} for the given keys, in the given language.

    This is what feeds window.PB_I18N: the templates dump the result with
    json.dumps, so the browser gets the strings it needs and nothing else.
    """
    result = {}
    for key in keys:
        result[key] = T(key, language)
    return result
