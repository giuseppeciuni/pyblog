#!/usr/bin/env python3
"""
Checks on the Settings panel and on the first steps of the dashboard.

    python3 tests/test_settings_panel.py

Every section of the Settings says what it is for and how it stands: on,
off, or something to fix. The states are read from the configuration, so
each check here hands a configuration to the function and looks at what it
says. Nothing is written to disk.
"""
import copy
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import bundle, config, server, settings_panel  # noqa: E402
from core.config import CONFIG_DEFAULT  # noqa: E402
from core.i18n import T, UI_TRANSLATIONS  # noqa: E402

PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


# A gtag snippet as Google hands it out.
GTAG = ("<script async src=\"https://www.googletagmanager.com/gtag/js?id=G-WFH9MSGK86\"></script>\n"
        "<script>\n  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n  gtag('js', new Date());\n"
        "  gtag('config', 'G-WFH9MSGK86');\n</script>")


def finished_config():
    """A site with nothing left to do: the starting point of the checks."""
    c = copy.deepcopy(CONFIG_DEFAULT)
    c["site_title"] = "Inside the Machine"
    c["base_url"] = "https://www.ciunix.com"
    c["admin_url"] = "https://admin.ciunix.com"
    c["home_content"] = "<p>Scrivo di AI e sistemi distribuiti.</p>"
    c["home_content_en"] = "<p>I write about AI and distributed systems.</p>"
    c["subtitle_en"] = "Technical notes on AI, distributed systems and more"
    c["home_cards"] = [{"active": True, "title": "Contatti", "content": "<p>Scrivimi.</p>"}]
    return c


def state(section_id, c, lang="it"):
    return settings_panel.section_state(section_id, c, lang)


def test_section_descriptions():
    """Every section has a name, a description and, but the last, a group."""
    print("\nle sezioni")
    ids = [s["id"] for s in settings_panel.SECTIONS]
    check("nessuna sezione ripetuta", len(ids) == len(set(ids)))
    check("CONFIG_SECTIONS nasce dallo stesso elenco",
          [k for k, _ in server.CONFIG_SECTIONS] == ids)
    groups = {g for g, _ in settings_panel.GROUPS}
    without = [s["id"] for s in settings_panel.SECTIONS if s["group"] not in groups]
    check("solo il file di configurazione è fuori dai gruppi", without == ["advanced"], str(without))
    for lang in ("it", "en"):
        missing = [s["id"] for s in settings_panel.SECTIONS
                    if lang not in UI_TRANSLATIONS.get(s["label"], {})
                    or lang not in UI_TRANSLATIONS.get(s["label"] + "_desc", {})]
        check(f"{lang}: ogni sezione ha nome e descrizione", missing == [], str(missing))
        missing = [k for _, k in settings_panel.GROUPS if lang not in UI_TRANSLATIONS.get(k, {})]
        check(f"{lang}: ogni gruppo ha un nome", missing == [], str(missing))
    check("ogni sezione con uno stato ha la sua funzione, e nessuna funzione è orfana",
          set(settings_panel.STATE_FUNCTIONS) == set(ids) - {"advanced"})
    names = [m for m, _ in bundle.BUNDLED_MODULES]
    check("il modulo entra nel file unico, prima del server",
          "core.settings_panel" in names
          and names.index("core.settings_panel") < names.index("core.server"))


def test_everything_from_the_interface():
    """
    Every setting of config.json can be changed from the Settings: the form
    sends it when saving. A setting added to CONFIG_DEFAULT without a field
    would only be reachable by editing the file, and this check says so.
    """
    print("\ntutto dall'interfaccia")
    import re
    js = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    start = js.index("function saveConfig")
    body = js[start:js.index("\n}\n", start)]
    main_ones = set(re.findall(r"^    (\w+):", body, re.M))
    nested = set(re.findall(r"^      (\w+):", body, re.M))
    # The language of the admin changes from the menu; home_order is a
    # leftover of the single-column homepage, read by nothing any more.
    outside = {"admin_language", "home_order"}
    missing = [k for k in CONFIG_DEFAULT if k not in main_ones and k not in outside]
    check("ogni impostazione principale ha il suo campo", missing == [], str(missing))
    missing = [k for k in CONFIG_DEFAULT["seo"] if k not in nested]
    check("e anche ogni dato dell'autore", missing == [], str(missing))
    page_html = server.config_page("TOKEN")
    for field in ("max_image_width", "share_buttons", "seo_backlink_site"):
        check(f"il campo {field} è nella pagina, con l'etichetta",
              f'id="{field}"' in page_html and f'for="{field}"' in page_html)


def test_finished_site():
    """A finished site has no warnings at all."""
    print("\nun sito finito")
    c = finished_config()
    warnings_found = [(s, t) for s in settings_panel.SECTION_IDS
              for tone, t in settings_panel.section_states(s, c, "it") if tone == "warn"
              and s != "translation"]
    check("nessun avviso, a parte la chiave di traduzione", warnings_found == [], str(warnings_found))
    check("il sito mostra il dominio", state("site", c) == ("ok", "www.ciunix.com"))


def test_site_and_home():
    print("\nsito e home page")
    c = finished_config()
    c["site_title"] = ""
    c["base_url"] = "https://tuodominio.com"
    states = settings_panel.section_states("site", c, "it")
    check("titolo e dominio mancanti sono due avvisi",
          [t for _, t in states] == [T("state_missing_one_title", "it"), T("state_missing_one_domain", "it")],
          str(states))
    c = finished_config()
    c["home_content_en"] = CONFIG_DEFAULT["home_content_en"]
    check("la presentazione inglese di esempio è un avviso",
          state("home", c) == ("warn", T("state_introduction_example", "it")))
    # The older text of the example, the one on ciunix.com.
    c["home_content_en"] = ("<p>To customize this introduction, go to the <em>Settings and "
                            "homepage</em> page in the admin area.</p>")
    check("anche la versione vecchia del testo di esempio",
          state("home", c)[0] == "warn")
    c["home_content"] = "<p><br></p>"
    c["home_content_en"] = ""
    check("una presentazione vuota è spenta, non un errore", state("home", c)[0] == "off")


def test_texts_in_other_language():
    """A bilingual site with the subtitle or the bio in one language only."""
    print("\ntesti nell'altra lingua")
    c = finished_config()
    c["seo"]["author_role"] = "Programmatore"
    notice = ("warn", T("state_texts_of_only_main", "it").replace("{main_language}", "italiano"))
    check("ruolo scritto solo in italiano su un sito bilingue: avviso",
          state("site", c) == notice, str(state("site", c)))
    check("in inglese l'avviso nomina la lingua in inglese",
          state("site", c, "en")[1] == T("state_texts_of_only_main", "en")
          .replace("{main_language}", "Italian"))
    c["seo"]["author_role_en"] = "Software developer"
    check("tradotto anche il ruolo, l'avviso sparisce", state("site", c)[0] == "ok")
    c["home_content_en"] = ""
    c["subtitle_en"] = ""
    check("un sito che non usa la seconda lingua non riceve l'avviso", state("site", c)[0] == "ok")


def test_admin_address():
    """The administration and the code of outside services on one address."""
    print("\nindirizzo dell'amministrazione")
    c = finished_config()
    c["admin_url"] = ""
    check("senza codici esterni, l'admin sull'indirizzo del sito va bene", state("site", c)[0] == "ok")
    c["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG}]
    check("con un codice esterno attivo, l'avviso",
          state("site", c) == ("warn", T("state_admin_shared", "it")))
    c["custom_code"] = []
    c["analytics_id"] = "G-WFH9MSGK86"
    check("anche con Google Analytics nel campo delle Statistiche", state("site", c)[0] == "warn")
    c["base_url"] = ""
    states = [t for _, t in settings_panel.section_states("site", c, "it")]
    check("un sito non ancora online non riceve l'avviso", T("state_admin_shared", "it") not in states)
    c = finished_config()
    c["admin_url"] = "admin.ciunix.com/editor"
    check("un indirizzo scritto male lo dice, e l'admin resta dov'era",
          state("site", c) == ("warn", T("state_admin_not_valid", "it")))


def test_boxes():
    print("\nriquadri della home")
    c = finished_config()
    c["home_cards"] = [
        {"active": True, "title": "Biografia",
         "content": "<p>Racconta qui chi sei, la tua esperienza e di cosa ti occupi.</p>"},
        {"active": True, "title": "Progetti",
         "content": "<p>Elenca qui i tuoi progetti principali, con una breve descrizione di ciascuno.</p>"},
        {"active": False, "title": "Avvisi",
         "content": "<p>Usa questo spazio per avvisi importanti ai lettori.</p>"},
        {"active": True, "title": "Contatti", "content": "<p>Scrivimi.</p>"},
    ]
    check("contano solo i riquadri accesi con il testo di esempio",
          state("boxes", c) == ("warn", T("state_boxes_example", "it").replace("{n}", "2")),
          str(state("boxes", c)))
    c["home_cards"] = c["home_cards"][3:]
    check("con i testi scritti dice quanti sono accesi",
          state("boxes", c) == ("ok", T("state_n_boxes", "it").replace("{n}", "1")))
    c["home_cards_enabled"] = False
    check("con i riquadri spenti, nessun riquadro", state("boxes", c)[0] == "off")


def test_biography_projects_comments():
    print("\nbiografia, progetti, commenti")
    c = finished_config()
    check("biografia spenta", state("biography", c) == ("off", T("state_off_f", "it")))
    c["biography"] = {"enabled": True, "content": "<p><br></p>"}
    check("biografia accesa ma vuota", state("biography", c)[0] == "warn")
    c["projects"] = {"enabled": True, "items": [{"name": "", "visible": True},
                                                {"name": "PyBlog", "visible": False}]}
    check("progetti accesi ma nessuno da mostrare", state("projects", c)[0] == "warn")
    c["projects"]["items"].append({"name": "Vaitony", "visible": True})
    check("conta solo i progetti che si vedono",
          state("projects", c) == ("ok", T("state_n_projects", "it").replace("{n}", "1")))
    c["comments"] = "giscus"
    check("Giscus con i valori di esempio va configurato", state("comments", c)[0] == "warn")
    c["giscus"] = {"repo": "giuseppe/blog", "repo_id": "R_1", "category": "C", "category_id": "DIC_1"}
    check("Giscus configurato", state("comments", c) == ("ok", "Giscus"))


def test_analytics():
    """The case of ciunix.com: the same Google Analytics in two snippets."""
    print("\nstatistiche")
    c = finished_config()
    check("niente statistiche", state("analytics", c)[0] == "off")
    c["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG, "scope": "all"}]
    check("un codice esterno con Google Analytics",
          state("analytics", c) == ("ok", T("state_analytics_from_code", "it")
                                      .replace("{name}", "Google Analytics")))
    c["custom_code"].append({"id": "b", "enabled": True, "code": GTAG, "scope": "all"})
    check("lo stesso id in due codici: ogni visita conta due volte",
          state("analytics", c) == ("warn", T("state_analytics_double", "it").replace("{n}", "2")),
          str(state("analytics", c)))
    c["custom_code"][1]["enabled"] = False
    check("un codice spento non conta", state("analytics", c)[0] == "ok")
    c["analytics_id"] = "G-WFH9MSGK86"
    check("il campo delle Impostazioni più un codice con lo stesso id è un doppione",
          state("analytics", c)[0] == "warn")
    c["custom_code"] = []
    check("solo il campo: Google Analytics", state("analytics", c) == ("ok", "Google Analytics"))
    noscript = ('<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-KBF2KVQP">'
                '</iframe></noscript>')
    c["custom_code"] = [{"id": "g", "enabled": True, "code": noscript}]
    check("il pezzo noscript di Tag Manager non è un secondo Google Analytics",
          state("analytics", c) == ("ok", "Google Analytics"))
    c["umami_url"] = "https://stats.esempio.it"
    c["umami_website_id"] = "3e9b1c2a"
    check("con Umami li nomina tutti e due",
          state("analytics", c) == ("ok", "Google Analytics + Umami"))
    check("codici esterni: uno acceso", state("code", c) == ("ok", T("state_one_item_active", "it")))


def test_cookie_translation_newsletter_ai():
    print("\ncookie, traduzione, newsletter, permessi alle AI")
    c = finished_config()
    check("banner spento senza statistiche: solo spento", state("cookie", c)[0] == "off")
    c["analytics_id"] = "G-WFH9MSGK86"
    check("banner spento con Google Analytics: da sistemare",
          state("cookie", c) == ("warn", T("state_cookie_off_m_analytics", "it")))
    c["consent"] = {"enabled": True}
    check("banner acceso", state("cookie", c) == ("ok", T("state_on_m", "it")))

    # The case of ciunix.com: banner on, Google Analytics in a snippet
    # marked "necessary", nothing else asking for consent.
    c2 = finished_config()
    c2["consent"] = {"enabled": True}
    c2["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG, "consent": "necessary"},
                         {"id": "v", "enabled": True, "code": "<script src=x></script>",
                          "consent": "necessary"}]
    states = settings_panel.section_states("cookie", c2, "it")
    check("banner acceso con Google Analytics «Necessario»: due avvisi, il primo su Google Analytics",
          [t for _, t in states] == [T("state_cookie_analytics_needed", "it"),
                                    T("state_cookie_on_m_useless", "it")], str(states))
    check("lo stesso avviso nei Codici esterni, dove si sistema",
          state("code", c2) == ("warn", T("state_cookie_analytics_needed", "it")))
    c2["custom_code"][0]["consent"] = "statistics"
    check("con Google Analytics su «Statistiche» il banner serve ed è a posto",
          state("cookie", c2) == ("ok", T("state_on_m", "it")))
    check("e i Codici esterni tornano a contare",
          state("code", c2) == ("ok", T("state_n_active_pl", "it").replace("{n}", "2")))
    c2["custom_code"] = c2["custom_code"][1:]
    check("senza niente che chieda il consenso, il banner acceso non compare: si dice",
          state("cookie", c2) == ("warn", T("state_cookie_on_m_useless", "it")))

    check("DeepL senza chiave",
          state("translation", c) == ("warn", T("state_missing_one_key", "it").replace("{service}", "DeepL")))
    os.environ["PYBLOG_DEEPL_API_KEY"] = "chiave-di-prova"
    try:
        check("la chiave in una variabile d'ambiente vale come quella scritta",
              state("translation", c) == ("ok", "DeepL"))
    finally:
        del os.environ["PYBLOG_DEEPL_API_KEY"]
    c["translation"]["service"] = "llm"
    c["translation"]["llm_api_key"] = "sk-prova"
    check("Claude con la chiave", state("translation", c) == ("ok", "Anthropic Claude"))

    check("newsletter spenta", state("newsletter", c)[0] == "off")
    c["newsletter"] = {"enabled": True}
    check("newsletter accesa senza server di posta",
          state("newsletter", c) == ("warn", T("state_newsletter_without_mail", "it")))

    check("permessi alle AI: aperto per chi non ha scelto",
          state("ai", c) == ("ok", T("state_ai_open", "it")))
    c["ai_training"] = {"policy": "disallow"}
    check("permessi alle AI: non consentito", state("ai", c) == ("ok", T("state_ai_forbidden", "it")))
    check("gli stati parlano anche inglese", state("ai", c, "en") == ("ok", T("state_ai_forbidden", "en")))


def test_first_steps():
    print("\nprimi passi")
    published = [{"status": "published"}]
    c = finished_config()
    check("un sito finito con un articolo pubblicato non ha passi",
          settings_panel.setup_steps(c, published, "it") == [])
    check("senza articoli pubblicati, il primo passo è scriverne uno",
          settings_panel.setup_steps(c, [{"status": "draft"}], "it")
          == [("", T("state_first_article", "it"))])
    c["base_url"] = ""
    c["translation"]["service"] = "deepl"
    c["newsletter"] = {"enabled": True}
    steps = settings_panel.setup_steps(c, published, "it")
    check("un dominio mancante è un passo; la chiave di traduzione e la newsletter no",
          steps == [("site", T("state_missing_one_domain", "it"))], str(steps))


def test_pages():
    """The panel and the dashboard, as HTML."""
    print("\nle pagine")
    real = server.load_config
    c = finished_config()
    c["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG},
                        {"id": "b", "enabled": True, "code": GTAG}]
    server.load_config = lambda: copy.deepcopy(c)
    try:
        panel = server.config_sections_list("it", c)
        check("la scheda Statistiche avvisa del doppione, anche a chi non vede il colore",
              'href="#analytics"' in panel
              and 'class="card-state state-warn"' in panel
              and T("admin_state_tone_warn", "it") in panel)
        check("la scheda prende il colore del suo stato",
              'class="card-setting card-warn" href="#analytics"' in panel
              and 'class="card-setting card-ok" href="#site"' in panel
              and 'class="card-setting card-off" href="#biography"' in panel)
        check("il file di configurazione, senza stato, resta fuori dai gruppi colorati",
              'href="#advanced"' not in panel)
        check("il pannello ha un titolo per ogni gruppo",
              all(T(k, "it") in panel for _, k in settings_panel.GROUPS))
        check("le parole chiave stanno nella scheda, per la ricerca",
              'data-search="analytics google ga4' in panel)
        page_html = server.config_page("TOKEN")
        check("la testata di una sezione riporta al pannello e dice il gruppo",
              '<a href="#list">Impostazioni</a> <span aria-hidden="true">›</span> '
              + T("admin_settings_group_services", "it") in page_html)
        check("la sezione Statistiche ripete il suo avviso in alto",
              '<ul class="section-notices" id="notices-analytics">' in page_html
              and T("state_analytics_double", "it").replace("{n}", "2") in page_html)
        check("una sezione senza avvisi ha la lista vuota e nascosta, pronta per dopo il salvataggio",
              '<ul class="section-notices" id="notices-projects" hidden>' in page_html)
        check("la pagina ha la ricerca, con la sua etichetta",
              'for="search-settings"' in page_html and 'id="search-settings"' in page_html)

        dashboard = server.admin_page([{"status": "published", "title": "A", "slug": "a",
                                        "date": "2026-01-01", "content": ""}], "TOKEN")
        check("i primi passi in cima agli articoli, con il link alla sezione",
              'class="first-steps"' in dashboard and 'href="/config#analytics"' in dashboard)
        check("e anche del banner dei cookie spento con Google Analytics",
              'href="/config#cookie"' in dashboard)
        check("ogni passo dice di quale sezione parla",
              '<span class="step-where">' + T("admin_section_cookie", "it") + '</span>' in dashboard)
        c["custom_code"] = c["custom_code"][:1]
        c["custom_code"][0]["consent"] = "statistics"
        c["consent"] = {"enabled": True}
        dashboard = server.admin_page([{"status": "published", "title": "A", "slug": "a",
                                        "date": "2026-01-01", "content": ""}], "TOKEN")
        check("finito tutto, i primi passi spariscono", 'class="first-steps"' not in dashboard)
    finally:
        server.load_config = real


def main():
    test_section_descriptions()
    test_everything_from_the_interface()
    test_finished_site()
    test_site_and_home()
    test_texts_in_other_language()
    test_admin_address()
    test_boxes()
    test_biography_projects_comments()
    test_analytics()
    test_cookie_translation_newsletter_ai()
    test_first_steps()
    test_pages()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
