"""
The sections of the Settings, described in one place.

Each section says which group it belongs to, the words it can be searched
by, and how to tell at a glance what state it is in: the Settings panel,
the side menu of a phone, the search and the "First steps" list of the
dashboard are all built from what is written here. A new feature that adds
a section adds an entry to SECTIONS and, if it has something to say about
its state, a function to STATE_FUNCTIONS - nothing else has to change.

A state is a tone and one line of text. "ok" is a feature that is on and
working, "off" one that is switched off (a normal choice, not a fault), and
"warn" something a reader of the site would notice or that does not work as
the author probably thinks: a placeholder text still on the homepage, a key
that is missing, analytics loaded twice.
"""
import html
import re

from core import newsletter
from core.build import projects_settings
from core.config import secret_setting
from core.i18n import T

# The groups of the panel, in order. The advanced section belongs to none:
# it is a link at the bottom, for whoever knows what config.json is.
GROUPS = [
    ("sito", "admin_imp_gruppo_sito"),
    ("lettori", "admin_imp_gruppo_lettori"),
    ("servizi", "admin_imp_gruppo_servizi"),
    ("regole", "admin_imp_gruppo_regole"),
]

# Every section, in the order of the panel. The id is the one in the
# address (/config#codici) and in the template; "label" is the i18n key of
# the name, whose description is the same key plus "_desc". The keywords
# are what the search finds a section by, on top of its name, its
# description and the labels of its fields; they are mostly the technical
# names someone might type, in both languages.
SECTIONS = [
    {"id": "sito", "group": "sito", "label": "admin_sez_sito",
     "keywords": "titolo title dominio domain url lingua language autore author "
                 "foto photo seo logo favicon linkedin social"},
    {"id": "home", "group": "sito", "label": "admin_sez_home",
     "keywords": "homepage presentazione introduction disposizione layout copertina cover"},
    {"id": "biografia", "group": "sito", "label": "admin_sez_biografia",
     "keywords": "bio about chi sono who am i"},
    {"id": "progetti", "group": "sito", "label": "admin_sez_progetti",
     "keywords": "projects portfolio"},
    {"id": "pagine", "group": "sito", "label": "admin_sez_pagine",
     "keywords": "esplora explore riquadri cards contatti contacts avvisi lavora con me "
                 "work with me hire"},
    {"id": "commenti", "group": "lettori", "label": "admin_sez_commenti",
     "keywords": "comments giscus disqus"},
    {"id": "newsletter", "group": "lettori", "label": "admin_sez_newsletter",
     "keywords": "email mail iscritti subscribers smtp"},
    {"id": "traduzione", "group": "lettori", "label": "admin_sez_traduzione",
     "keywords": "translation inglese english deepl google claude openai deepseek chiave key api"},
    {"id": "statistiche", "group": "servizi", "label": "admin_sez_statistiche",
     "keywords": "analytics google ga4 gtag umami visite visits"},
    {"id": "codici", "group": "servizi", "label": "admin_sez_codici",
     "keywords": "code script widget chat annunci ads adsense pixel tag manager gtm "
                 "clarity ads.txt"},
    {"id": "cookie", "group": "regole", "label": "admin_sez_cookie",
     "keywords": "cookies consenso consent gdpr privacy banner"},
    {"id": "ai", "group": "regole", "label": "admin_sez_ai",
     "keywords": "intelligenza artificiale artificial intelligence crawler bot gptbot "
                 "claudebot chatgpt addestramento training robots.txt llms.txt"},
    {"id": "avanzate", "group": None, "label": "admin_sez_avanzate",
     "keywords": "config.json json avanzate advanced"},
]

SECTION_IDS = [s["id"] for s in SECTIONS]

# The sections whose warnings are a first step: what a visitor of the site
# would see, or what makes a link of the site wrong. A translation key that
# is missing is a warning on its card, but not a step: plenty of blogs never
# translate anything.
SETUP_SECTIONS = ("sito", "home", "pagine", "statistiche", "cookie")

# The texts the first configuration puts in the homepage cards and in the
# introduction, so that a new site does not open empty. On a site that is
# online they are a sign the author never got round to them.
PLACEHOLDER_TEXTS = (
    "Racconta qui chi sei, la tua esperienza e di cosa ti occupi.",
    "Elenca qui i tuoi progetti principali, con una breve descrizione di ciascuno.",
    "Metti qui le informazioni che vuoi mettere in evidenza",
    "Usa questo spazio per avvisi importanti ai lettori.",
    "Per personalizzare questa presentazione",
    "To customize this introduction",
)

# The example values of a new configuration that are not a real setting.
PLACEHOLDER_DOMAINS = ("tuodominio", "mysite", "example.com")
PLACEHOLDER_GISCUS = ("tuonome/tuorepo", "R_xxxxxxxx", "DIC_xxxxxxxx")
PLACEHOLDER_DISQUS = ("tuo-shortname", "")

# The translation services, the name shown for each and the key it needs.
TRANSLATION_SERVICES = {
    "deepl": ("DeepL", "deepl_api_key"),
    "google": ("Google Translate", "google_api_key"),
    "llm": ("Anthropic Claude", "llm_api_key"),
    "openai": ("OpenAI", "openai_api_key"),
    "deepseek": ("DeepSeek", "deepseek_api_key"),
}

# A Google Analytics 4 measurement id, as it appears in the field or in the
# gtag snippet Google gives out.
GA_ID = re.compile(r"\bG-[A-Z0-9]{4,}\b")


def section(section_id):
    """The entry of SECTIONS with this id, or None."""
    for entry in SECTIONS:
        if entry["id"] == section_id:
            return entry
    return None


def sections_of(group_id):
    """The sections of one group, in the order of the panel."""
    return [s for s in SECTIONS if s["group"] == group_id]


def group_label(section_id):
    """The i18n key of the group a section belongs to, or "" for none."""
    entry = section(section_id)
    for group_id, label_key in GROUPS:
        if entry is not None and entry["group"] == group_id:
            return label_key
    return ""


# ---------------------------------------------------------------------------
# READING THE CONFIGURATION
# ---------------------------------------------------------------------------

def _dict(config, key):
    value = config.get(key, {})
    return value if isinstance(value, dict) else {}


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def plain_text(fragment):
    """The visible text of a piece of HTML written in the editor."""
    if not isinstance(fragment, str):
        return ""
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def has_placeholder(fragment):
    """Tell whether a piece of HTML still holds one of the example texts."""
    text = " ".join(plain_text(fragment).split())
    return any(p in text for p in PLACEHOLDER_TEXTS)


def domain_is_set(config):
    base = _text(config.get("base_url", ""))
    return base != "" and not any(p in base for p in PLACEHOLDER_DOMAINS)


def enabled_snippets(config):
    """The custom code snippets that are switched on."""
    snippets = config.get("custom_code", [])
    if not isinstance(snippets, list):
        return []
    return [s for s in snippets if isinstance(s, dict) and s.get("enabled", False) is True]


def analytics_loads(config):
    """
    Every place that loads Google Analytics, as a list of measurement ids:
    the field of the Settings once, and each snippet switched on that loads
    gtag.js once per id it names. The same id twice means every visit is
    counted twice.
    """
    loads = []
    field = _text(config.get("analytics_id", ""))
    if field != "":
        loads.append(field)
    for snippet in enabled_snippets(config):
        code = snippet.get("code", "")
        if not isinstance(code, str) or "gtag" not in code:
            continue
        loads.extend(sorted(set(GA_ID.findall(code))))
    return loads


def umami_is_set(config):
    return (_text(config.get("umami_url", "")) != ""
            and _text(config.get("umami_website_id", "")) != "")


# ---------------------------------------------------------------------------
# THE STATE OF EACH SECTION
# ---------------------------------------------------------------------------
# Each function returns a list of (tone, text) in order of importance: the
# first is what the card shows, the warnings among them are the first steps.

def _state_site(config, la):
    problems = []
    if _text(config.get("site_title", "")) == "":
        problems.append(("warn", T("stato_manca_titolo", la)))
    if not domain_is_set(config):
        problems.append(("warn", T("stato_manca_dominio", la)))
    if _text(config.get("author", "")) == "":
        problems.append(("warn", T("stato_manca_autore", la)))
    if problems:
        return problems
    domain = re.sub(r"^https?://", "", _text(config.get("base_url", ""))).rstrip("/")
    return [("ok", domain)]


def _state_home(config, la):
    contents = [config.get("home_content", ""), config.get("home_content_en", "")]
    if any(has_placeholder(c) for c in contents):
        return [("warn", T("stato_presentazione_esempio", la))]
    if plain_text(contents[0]) == "":
        return [("off", T("stato_presentazione_vuota", la))]
    return [("ok", T("stato_presentazione_scritta", la))]


def _state_biography(config, la):
    bio = _dict(config, "biography")
    if bio.get("enabled", False) is not True:
        return [("off", T("stato_spenta", la))]
    if plain_text(bio.get("content", "")) == "":
        return [("warn", T("stato_accesa_vuota", la))]
    return [("ok", T("stato_accesa", la))]


def _state_projects(config, la):
    # The same rule as the homepage: a project shows when it is visible and
    # has a name.
    projects = projects_settings(config)
    shown = [p for p in projects["items"] if p["visible"] and p["name"] != ""]
    if not projects["enabled"]:
        return [("off", T("stato_spenti", la))]
    if len(shown) == 0:
        return [("warn", T("stato_accesi_senza_progetti", la))]
    return [("ok", T("stato_n_progetti", la).replace("{n}", str(len(shown))))]


def _state_cards(config, la):
    cards = config.get("home_cards", [])
    if not isinstance(cards, list) or config.get("home_cards_enabled", True) is not True:
        cards = []
    active = [c for c in cards if isinstance(c, dict) and c.get("active", True) is not False]
    example = [c for c in active
               if has_placeholder(c.get("content", "")) or has_placeholder(c.get("content_en", ""))]
    if len(example) == 1:
        return [("warn", T("stato_riquadro_esempio", la))]
    if len(example) > 1:
        return [("warn", T("stato_riquadri_esempio", la).replace("{n}", str(len(example))))]
    if len(active) == 0:
        return [("off", T("stato_nessun_riquadro", la))]
    return [("ok", T("stato_n_riquadri", la).replace("{n}", str(len(active))))]


def _state_comments(config, la):
    system = config.get("comments", "none")
    if system == "giscus":
        giscus = _dict(config, "giscus")
        values = [_text(giscus.get(k, "")) for k in ("repo", "repo_id", "category_id")]
        if any(v == "" or v in PLACEHOLDER_GISCUS for v in values):
            return [("warn", T("stato_giscus_da_configurare", la))]
        return [("ok", "Giscus")]
    if system == "disqus":
        if _text(_dict(config, "disqus").get("shortname", "")) in PLACEHOLDER_DISQUS:
            return [("warn", T("stato_disqus_da_configurare", la))]
        return [("ok", "Disqus")]
    return [("off", T("stato_spenti", la))]


def _state_newsletter(config, la):
    current = newsletter.settings(config)
    if not current["enabled"]:
        return [("off", T("stato_spenta", la))]
    if not newsletter.ready(current):
        return [("warn", T("stato_newsletter_senza_posta", la))]
    confirmed, _ = newsletter.counts()
    return [("ok", T("stato_n_iscritti", la).replace("{n}", str(confirmed)))]


def _state_translation(config, la):
    translation = _dict(config, "translation")
    service = translation.get("service", "deepl")
    if service not in TRANSLATION_SERVICES:
        service = "deepl"
    name, key_name = TRANSLATION_SERVICES[service]
    if _text(secret_setting(translation, key_name)) == "":
        return [("warn", T("stato_manca_chiave", la).replace("{servizio}", name))]
    return [("ok", name)]


def _state_analytics(config, la):
    loads = analytics_loads(config)
    doubled = sorted({i for i in loads if loads.count(i) > 1})
    if doubled:
        return [("warn", T("stato_analytics_doppio", la)
                 .replace("{n}", str(loads.count(doubled[0]))))]
    names = []
    if loads:
        names.append("Google Analytics")
    if umami_is_set(config):
        names.append("Umami")
    if not names:
        return [("off", T("stato_nessuna", la))]
    text = " + ".join(names)
    if loads and _text(config.get("analytics_id", "")) == "":
        text = T("stato_analytics_da_codice", la).replace("{nome}", text)
    return [("ok", text)]


def _state_code(config, la):
    count = len(enabled_snippets(config))
    if count == 0:
        return [("off", T("stato_nessuno", la))]
    if count == 1:
        return [("ok", T("stato_uno_attivo", la))]
    return [("ok", T("stato_n_attivi", la).replace("{n}", str(count)))]


def _state_consent(config, la):
    consent = _dict(config, "consent")
    if consent.get("enabled", False) is True:
        return [("ok", T("stato_acceso", la))]
    # Google Analytics sets cookies, and in Europe it needs consent first.
    if analytics_loads(config):
        return [("warn", T("stato_cookie_spento_analytics", la))]
    return [("off", T("stato_spento", la))]


def _state_ai(config, la):
    policy = _dict(config, "ai_training").get("policy", "open")
    keys = {"licensed": "stato_ai_licenza", "disallow": "stato_ai_vietato"}
    return [("ok", T(keys.get(policy, "stato_ai_aperto"), la))]


STATE_FUNCTIONS = {
    "sito": _state_site,
    "home": _state_home,
    "biografia": _state_biography,
    "progetti": _state_projects,
    "pagine": _state_cards,
    "commenti": _state_comments,
    "newsletter": _state_newsletter,
    "traduzione": _state_translation,
    "statistiche": _state_analytics,
    "codici": _state_code,
    "cookie": _state_consent,
    "ai": _state_ai,
}


def section_states(section_id, config, la):
    """Everything worth saying about a section, most important first."""
    function = STATE_FUNCTIONS.get(section_id)
    if function is None:
        return []
    return function(config, la)


def section_state(section_id, config, la):
    """What the card of a section shows: (tone, text), or None."""
    states = section_states(section_id, config, la)
    return states[0] if states else None


def setup_steps(config, articles, la):
    """
    The first steps of the dashboard: every warning of the sections a
    visitor of the site would notice, then the first article to publish.
    Each step is (section id or "", text); the empty id stands for the
    editor of a new article.
    """
    steps = []
    for section_id in SETUP_SECTIONS:
        for tone, text in section_states(section_id, config, la):
            if tone == "warn":
                steps.append((section_id, text))
    if not any(a.get("status") == "published" for a in articles):
        steps.append(("", T("stato_primo_articolo", la)))
    return steps
