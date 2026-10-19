#!/usr/bin/env python3
"""
Checks on the Settings panel and on the first steps of the dashboard.

    python3 tests/test_pannello_impostazioni.py

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
    c["home_content"] = "<p>Scrivo di AI e sistemi distribuiti.</p>"
    c["home_content_en"] = "<p>I write about AI and distributed systems.</p>"
    c["home_cards"] = [{"active": True, "title": "Contatti", "content": "<p>Scrivimi.</p>"}]
    return c


def state(section_id, c, la="it"):
    return settings_panel.section_state(section_id, c, la)


def test_descrizione_delle_sezioni():
    """Every section has a name, a description and, but the last, a group."""
    print("\nle sezioni")
    ids = [s["id"] for s in settings_panel.SECTIONS]
    check("nessuna sezione ripetuta", len(ids) == len(set(ids)))
    check("CONFIG_SECTIONS nasce dallo stesso elenco",
          [k for k, _ in server.CONFIG_SECTIONS] == ids)
    gruppi = {g for g, _ in settings_panel.GROUPS}
    senza = [s["id"] for s in settings_panel.SECTIONS if s["group"] not in gruppi]
    check("solo il file di configurazione è fuori dai gruppi", senza == ["avanzate"], str(senza))
    for la in ("it", "en"):
        mancanti = [s["id"] for s in settings_panel.SECTIONS
                    if la not in UI_TRANSLATIONS.get(s["label"], {})
                    or la not in UI_TRANSLATIONS.get(s["label"] + "_desc", {})]
        check(f"{la}: ogni sezione ha nome e descrizione", mancanti == [], str(mancanti))
        mancanti = [k for _, k in settings_panel.GROUPS if la not in UI_TRANSLATIONS.get(k, {})]
        check(f"{la}: ogni gruppo ha un nome", mancanti == [], str(mancanti))
    check("ogni sezione con uno stato ha la sua funzione, e nessuna funzione è orfana",
          set(settings_panel.STATE_FUNCTIONS) == set(ids) - {"avanzate"})
    nomi = [m for m, _ in bundle.BUNDLED_MODULES]
    check("il modulo entra nel file unico, prima del server",
          "core.settings_panel" in nomi
          and nomi.index("core.settings_panel") < nomi.index("core.server"))


def test_sito_finito():
    """A finished site has no warnings at all."""
    print("\nun sito finito")
    c = finished_config()
    avvisi = [(s, t) for s in settings_panel.SECTION_IDS
              for tono, t in settings_panel.section_states(s, c, "it") if tono == "warn"
              and s != "traduzione"]
    check("nessun avviso, a parte la chiave di traduzione", avvisi == [], str(avvisi))
    check("il sito mostra il dominio", state("sito", c) == ("ok", "www.ciunix.com"))


def test_sito_e_home():
    print("\nsito e home page")
    c = finished_config()
    c["site_title"] = ""
    c["base_url"] = "https://tuodominio.com"
    stati = settings_panel.section_states("sito", c, "it")
    check("titolo e dominio mancanti sono due avvisi",
          [t for _, t in stati] == [T("stato_manca_titolo", "it"), T("stato_manca_dominio", "it")],
          str(stati))
    c = finished_config()
    c["home_content_en"] = CONFIG_DEFAULT["home_content_en"]
    check("la presentazione inglese di esempio è un avviso",
          state("home", c) == ("warn", T("stato_presentazione_esempio", "it")))
    # The older text of the example, the one on ciunix.com.
    c["home_content_en"] = ("<p>To customize this introduction, go to the <em>Settings and "
                            "homepage</em> page in the admin area.</p>")
    check("anche la versione vecchia del testo di esempio",
          state("home", c)[0] == "warn")
    c["home_content"] = "<p><br></p>"
    c["home_content_en"] = ""
    check("una presentazione vuota è spenta, non un errore", state("home", c)[0] == "off")


def test_riquadri():
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
          state("pagine", c) == ("warn", T("stato_riquadri_esempio", "it").replace("{n}", "2")),
          str(state("pagine", c)))
    c["home_cards"] = c["home_cards"][3:]
    check("con i testi scritti dice quanti sono accesi",
          state("pagine", c) == ("ok", T("stato_n_riquadri", "it").replace("{n}", "1")))
    c["home_cards_enabled"] = False
    check("con i riquadri spenti, nessun riquadro", state("pagine", c)[0] == "off")


def test_biografia_progetti_commenti():
    print("\nbiografia, progetti, commenti")
    c = finished_config()
    check("biografia spenta", state("biografia", c) == ("off", T("stato_spenta", "it")))
    c["biography"] = {"enabled": True, "content": "<p><br></p>"}
    check("biografia accesa ma vuota", state("biografia", c)[0] == "warn")
    c["projects"] = {"enabled": True, "items": [{"name": "", "visible": True},
                                                {"name": "PyBlog", "visible": False}]}
    check("progetti accesi ma nessuno da mostrare", state("progetti", c)[0] == "warn")
    c["projects"]["items"].append({"name": "Vaitony", "visible": True})
    check("conta solo i progetti che si vedono",
          state("progetti", c) == ("ok", T("stato_n_progetti", "it").replace("{n}", "1")))
    c["comments"] = "giscus"
    check("Giscus con i valori di esempio va configurato", state("commenti", c)[0] == "warn")
    c["giscus"] = {"repo": "giuseppe/blog", "repo_id": "R_1", "category": "C", "category_id": "DIC_1"}
    check("Giscus configurato", state("commenti", c) == ("ok", "Giscus"))


def test_statistiche():
    """The case of ciunix.com: the same Google Analytics in two snippets."""
    print("\nstatistiche")
    c = finished_config()
    check("niente statistiche", state("statistiche", c)[0] == "off")
    c["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG, "scope": "all"}]
    check("un codice esterno con Google Analytics",
          state("statistiche", c) == ("ok", T("stato_analytics_da_codice", "it")
                                      .replace("{nome}", "Google Analytics")))
    c["custom_code"].append({"id": "b", "enabled": True, "code": GTAG, "scope": "all"})
    check("lo stesso id in due codici: ogni visita conta due volte",
          state("statistiche", c) == ("warn", T("stato_analytics_doppio", "it").replace("{n}", "2")),
          str(state("statistiche", c)))
    c["custom_code"][1]["enabled"] = False
    check("un codice spento non conta", state("statistiche", c)[0] == "ok")
    c["analytics_id"] = "G-WFH9MSGK86"
    check("il campo delle Impostazioni più un codice con lo stesso id è un doppione",
          state("statistiche", c)[0] == "warn")
    c["custom_code"] = []
    check("solo il campo: Google Analytics", state("statistiche", c) == ("ok", "Google Analytics"))
    noscript = ('<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-KBF2KVQP">'
                '</iframe></noscript>')
    c["custom_code"] = [{"id": "g", "enabled": True, "code": noscript}]
    check("il pezzo noscript di Tag Manager non è un secondo Google Analytics",
          state("statistiche", c) == ("ok", "Google Analytics"))
    c["umami_url"] = "https://stats.esempio.it"
    c["umami_website_id"] = "3e9b1c2a"
    check("con Umami li nomina tutti e due",
          state("statistiche", c) == ("ok", "Google Analytics + Umami"))
    check("codici esterni: uno acceso", state("codici", c) == ("ok", T("stato_uno_attivo", "it")))


def test_cookie_traduzione_newsletter_ai():
    print("\ncookie, traduzione, newsletter, permessi alle AI")
    c = finished_config()
    check("banner spento senza statistiche: solo spento", state("cookie", c)[0] == "off")
    c["analytics_id"] = "G-WFH9MSGK86"
    check("banner spento con Google Analytics: da sistemare",
          state("cookie", c) == ("warn", T("stato_cookie_spento_analytics", "it")))
    c["consent"] = {"enabled": True}
    check("banner acceso", state("cookie", c) == ("ok", T("stato_acceso", "it")))

    check("DeepL senza chiave",
          state("traduzione", c) == ("warn", T("stato_manca_chiave", "it").replace("{servizio}", "DeepL")))
    os.environ["PYBLOG_DEEPL_API_KEY"] = "chiave-di-prova"
    try:
        check("la chiave in una variabile d'ambiente vale come quella scritta",
              state("traduzione", c) == ("ok", "DeepL"))
    finally:
        del os.environ["PYBLOG_DEEPL_API_KEY"]
    c["translation"]["service"] = "llm"
    c["translation"]["llm_api_key"] = "sk-prova"
    check("Claude con la chiave", state("traduzione", c) == ("ok", "Anthropic Claude"))

    check("newsletter spenta", state("newsletter", c)[0] == "off")
    c["newsletter"] = {"enabled": True}
    check("newsletter accesa senza server di posta",
          state("newsletter", c) == ("warn", T("stato_newsletter_senza_posta", "it")))

    check("permessi alle AI: aperto per chi non ha scelto",
          state("ai", c) == ("ok", T("stato_ai_aperto", "it")))
    c["ai_training"] = {"policy": "disallow"}
    check("permessi alle AI: non consentito", state("ai", c) == ("ok", T("stato_ai_vietato", "it")))
    check("gli stati parlano anche inglese", state("ai", c, "en") == ("ok", T("stato_ai_vietato", "en")))


def test_primi_passi():
    print("\nprimi passi")
    pubblicato = [{"status": "published"}]
    c = finished_config()
    check("un sito finito con un articolo pubblicato non ha passi",
          settings_panel.setup_steps(c, pubblicato, "it") == [])
    check("senza articoli pubblicati, il primo passo è scriverne uno",
          settings_panel.setup_steps(c, [{"status": "draft"}], "it")
          == [("", T("stato_primo_articolo", "it"))])
    c["base_url"] = ""
    c["translation"]["service"] = "deepl"
    c["newsletter"] = {"enabled": True}
    passi = settings_panel.setup_steps(c, pubblicato, "it")
    check("un dominio mancante è un passo; la chiave di traduzione e la newsletter no",
          passi == [("sito", T("stato_manca_dominio", "it"))], str(passi))


def test_pagine():
    """The panel and the dashboard, as HTML."""
    print("\nle pagine")
    vero = server.load_config
    c = finished_config()
    c["custom_code"] = [{"id": "a", "enabled": True, "code": GTAG},
                        {"id": "b", "enabled": True, "code": GTAG}]
    server.load_config = lambda: copy.deepcopy(c)
    try:
        pannello = server.config_sections_list("it", c)
        check("la scheda Statistiche avvisa del doppione, anche a chi non vede il colore",
              'href="#statistiche"' in pannello
              and 'class="scheda-stato stato-warn"' in pannello
              and T("admin_stato_tono_warn", "it") in pannello)
        check("il pannello ha un titolo per ogni gruppo",
              all(T(k, "it") in pannello for _, k in settings_panel.GROUPS))
        check("le parole chiave stanno nella scheda, per la ricerca",
              'data-cerca="analytics google ga4' in pannello)
        pagina = server.config_page("TOKEN")
        check("la testata di una sezione riporta al pannello e dice il gruppo",
              '<a href="#elenco">Impostazioni</a> <span aria-hidden="true">›</span> '
              + T("admin_imp_gruppo_servizi", "it") in pagina)
        check("la sezione Statistiche ripete il suo avviso in alto",
              '<ul class="sezione-avvisi" id="avvisi-statistiche">' in pagina
              and T("stato_analytics_doppio", "it").replace("{n}", "2") in pagina)
        check("una sezione senza avvisi ha la lista vuota e nascosta, pronta per dopo il salvataggio",
              '<ul class="sezione-avvisi" id="avvisi-progetti" hidden>' in pagina)
        check("la pagina ha la ricerca, con la sua etichetta",
              'for="cerca-impostazioni"' in pagina and 'id="cerca-impostazioni"' in pagina)

        dashboard = server.admin_page([{"status": "published", "title": "A", "slug": "a",
                                        "date": "2026-01-01", "content": ""}], "TOKEN")
        check("i primi passi in cima agli articoli, con il link alla sezione",
              'class="primi-passi"' in dashboard and 'href="/config#statistiche"' in dashboard)
        check("e anche del banner dei cookie spento con Google Analytics",
              'href="/config#cookie"' in dashboard)
        check("ogni passo dice di quale sezione parla",
              '<span class="passo-dove">' + T("admin_sez_cookie", "it") + '</span>' in dashboard)
        c["custom_code"] = c["custom_code"][:1]
        c["consent"] = {"enabled": True}
        dashboard = server.admin_page([{"status": "published", "title": "A", "slug": "a",
                                        "date": "2026-01-01", "content": ""}], "TOKEN")
        check("finito tutto, i primi passi spariscono", 'class="primi-passi"' not in dashboard)
    finally:
        server.load_config = vero


def main():
    test_descrizione_delle_sezioni()
    test_sito_finito()
    test_sito_e_home()
    test_riquadri()
    test_biografia_progetti_commenti()
    test_statistiche()
    test_cookie_traduzione_newsletter_ai()
    test_primi_passi()
    test_pagine()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
