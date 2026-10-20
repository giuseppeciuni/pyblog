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
from core.build import projects_settings, snippet_consent
from core.config import admin_address, secret_setting
from core.i18n import LANGUAGE_NAMES, T

# The groups of the panel, in order. The advanced section belongs to none:
# it is a link at the bottom, for whoever knows what config.json is.
GROUPS = [
    ("site", "admin_settings_group_site"),
    ("readers", "admin_settings_group_readers"),
    ("services", "admin_settings_group_services"),
    ("rules", "admin_settings_group_rules"),
]

# Every section, in the order of the panel. The id is the one in the
# address (/config#codici) and in the template; "label" is the i18n key of
# the name, whose description is the same key plus "_desc". The keywords
# are what the search finds a section by, on top of its name, its
# description and the labels of its fields; they are mostly the technical
# names someone might type, in both languages.
SECTIONS = [
    {"id": "site", "group": "site", "label": "admin_section_site",
     "keywords": "titolo title dominio domain url lingua language autore author "
                 "foto photo seo logo favicon linkedin social immagini images larghezza width"},
    {"id": "home", "group": "site", "label": "admin_section_home",
     "keywords": "homepage presentazione introduction disposizione layout copertina cover "
                 "condividi share copia link"},
    {"id": "biography", "group": "site", "label": "admin_section_biography",
     "keywords": "bio about chi sono who am i"},
    {"id": "projects", "group": "site", "label": "admin_section_projects",
     "keywords": "projects portfolio"},
    {"id": "boxes", "group": "site", "label": "admin_section_pages",
     "keywords": "esplora explore riquadri cards contatti contacts avvisi lavora con me "
                 "work with me hire"},
    {"id": "comments", "group": "readers", "label": "admin_section_comments",
     "keywords": "comments giscus disqus"},
    {"id": "newsletter", "group": "readers", "label": "admin_section_newsletter",
     "keywords": "email mail iscritti subscribers smtp"},
    {"id": "translation", "group": "readers", "label": "admin_section_translation_of",
     "keywords": "translation inglese english deepl google claude openai deepseek chiave key api "
                 "seo backlink anchor ai"},
    {"id": "analytics", "group": "services", "label": "admin_section_analytics_section",
     "keywords": "analytics google ga4 gtag umami visite visits"},
    {"id": "code", "group": "services", "label": "admin_section_codes",
     "keywords": "code script widget chat annunci ads adsense pixel tag manager gtm "
                 "clarity ads.txt"},
    {"id": "cookie", "group": "rules", "label": "admin_section_cookie",
     "keywords": "cookies consenso consent gdpr privacy banner"},
    {"id": "ai", "group": "rules", "label": "admin_section_ai",
     "keywords": "intelligenza artificiale artificial intelligence crawler bot gptbot "
                 "claudebot chatgpt addestramento training robots.txt llms.txt"},
    {"id": "advanced", "group": None, "label": "admin_section_advanced",
     "keywords": "config.json json avanzate advanced"},
]

SECTION_IDS = [s["id"] for s in SECTIONS]

# The sections whose warnings are a first step: what a visitor of the site
# would see, or what makes a link of the site wrong. A translation key that
# is missing is a warning on its card, but not a step: plenty of blogs never
# translate anything.
SETUP_SECTIONS = ("site", "home", "boxes", "analytics", "cookie")

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


def consent_categories(config):
    """
    The consent categories the code of the whole site asks for: the same rule
    as the public pages, where the banner only shows when some code waits
    for it. Code written inside a single article is left out: it asks on
    that article alone.
    """
    used = set()
    if _text(config.get("analytics_id", "")) != "":
        used.add("statistics")
    for snippet in enabled_snippets(config):
        used.add(snippet_consent(snippet))
    return [c for c in ("statistics", "marketing") if c in used]


def analytics_without_consent(config):
    """The snippets switched on that load Google Analytics as "necessary"."""
    found = []
    for snippet in enabled_snippets(config):
        code = snippet.get("code", "")
        if (isinstance(code, str) and "gtag" in code and GA_ID.search(code)
                and snippet_consent(snippet) == "necessary"):
            found.append(snippet)
    return found


def site_is_bilingual(config):
    """
    Whether the site already speaks its second language: the homepage
    introduction has its translation. A cheap sign, read from the
    configuration alone, that the pages in the other language are in use.
    """
    return plain_text(config.get("home_content_en", "")) != ""


def texts_only_in_main_language(config):
    """Whether the subtitle, the role or the bio is written but not translated."""
    seo = _dict(config, "seo")
    pairs = [(config.get("subtitle", ""), config.get("subtitle_en", "")),
             (seo.get("author_role", ""), seo.get("author_role_en", "")),
             (seo.get("author_bio", ""), seo.get("author_bio_en", ""))]
    return any(_text(main) != "" and _text(other) == "" for main, other in pairs)


def outside_code(config):
    """Whether the public pages load code from outside services."""
    return bool(enabled_snippets(config) or _text(config.get("analytics_id", "")) != ""
                or umami_is_set(config))


def umami_is_set(config):
    return (_text(config.get("umami_url", "")) != ""
            and _text(config.get("umami_website_id", "")) != "")


# ---------------------------------------------------------------------------
# THE STATE OF EACH SECTION
# ---------------------------------------------------------------------------
# Each function returns a list of (tone, text) in order of importance: the
# first is what the card shows, the warnings among them are the first steps.

def _state_site(config, lang):
    problems = []
    if _text(config.get("site_title", "")) == "":
        problems.append(("warn", T("state_missing_one_title", lang)))
    if not domain_is_set(config):
        problems.append(("warn", T("state_missing_one_domain", lang)))
    if _text(config.get("author", "")) == "":
        problems.append(("warn", T("state_missing_one_author", lang)))
    if _text(str(config.get("admin_url", "") or "")) != "" and admin_address(config) == "":
        problems.append(("warn", T("state_admin_not_valid", lang)))
    elif admin_address(config) == "" and domain_is_set(config) and outside_code(config):
        # Code of outside services on the site's own address can read what
        # the logged-in author sees there, settings and keys included.
        problems.append(("warn", T("state_admin_shared", lang)))
    if site_is_bilingual(config) and texts_only_in_main_language(config):
        main = config.get("language", "it") if config.get("language") in ("it", "en") else "it"
        problems.append(("warn", T("state_texts_of_only_main", lang)
                         .replace("{main_language}", LANGUAGE_NAMES[main][lang])))
    if problems:
        return problems
    domain = re.sub(r"^https?://", "", _text(config.get("base_url", ""))).rstrip("/")
    return [("ok", domain)]


def _state_home(config, lang):
    contents = [config.get("home_content", ""), config.get("home_content_en", "")]
    if any(has_placeholder(c) for c in contents):
        return [("warn", T("state_introduction_example", lang))]
    if plain_text(contents[0]) == "":
        return [("off", T("state_introduction_empty_f", lang))]
    return [("ok", T("state_introduction_written_f", lang))]


def _state_biography(config, lang):
    bio = _dict(config, "biography")
    if bio.get("enabled", False) is not True:
        return [("off", T("state_off_f", lang))]
    if plain_text(bio.get("content", "")) == "":
        return [("warn", T("state_on_f_empty_f", lang))]
    return [("ok", T("state_on_f", lang))]


def _state_projects(config, lang):
    # The same rule as the homepage: a project shows when it is visible and
    # has a name.
    projects = projects_settings(config)
    shown = [p for p in projects["items"] if p["visible"] and p["name"] != ""]
    if not projects["enabled"]:
        return [("off", T("state_off_pl", lang))]
    if len(shown) == 0:
        return [("warn", T("state_on_pl_without_projects", lang))]
    return [("ok", T("state_n_projects", lang).replace("{n}", str(len(shown))))]


def _state_cards(config, lang):
    cards = config.get("home_cards", [])
    if not isinstance(cards, list) or config.get("home_cards_enabled", True) is not True:
        cards = []
    active = [c for c in cards if isinstance(c, dict) and c.get("active", True) is not False]
    example = [c for c in active
               if has_placeholder(c.get("content", "")) or has_placeholder(c.get("content_en", ""))]
    if len(example) == 1:
        return [("warn", T("state_box_example", lang))]
    if len(example) > 1:
        return [("warn", T("state_boxes_example", lang).replace("{n}", str(len(example))))]
    if len(active) == 0:
        return [("off", T("state_no_one_box", lang))]
    return [("ok", T("state_n_boxes", lang).replace("{n}", str(len(active))))]


def _state_comments(config, lang):
    system = config.get("comments", "none")
    if system == "giscus":
        giscus = _dict(config, "giscus")
        values = [_text(giscus.get(k, "")) for k in ("repo", "repo_id", "category_id")]
        if any(v == "" or v in PLACEHOLDER_GISCUS for v in values):
            return [("warn", T("state_giscus_from_configure", lang))]
        return [("ok", "Giscus")]
    if system == "disqus":
        if _text(_dict(config, "disqus").get("shortname", "")) in PLACEHOLDER_DISQUS:
            return [("warn", T("state_disqus_from_configure", lang))]
        return [("ok", "Disqus")]
    return [("off", T("state_off_pl", lang))]


def _state_newsletter(config, lang):
    current = newsletter.settings(config)
    if not current["enabled"]:
        return [("off", T("state_off_f", lang))]
    if not newsletter.ready(current):
        return [("warn", T("state_newsletter_without_mail", lang))]
    confirmed, _ = newsletter.counts()
    return [("ok", T("state_n_subscribers", lang).replace("{n}", str(confirmed)))]


def _state_translation(config, lang):
    translation = _dict(config, "translation")
    service = translation.get("service", "deepl")
    if service not in TRANSLATION_SERVICES:
        service = "deepl"
    name, key_name = TRANSLATION_SERVICES[service]
    if _text(secret_setting(translation, key_name)) == "":
        return [("warn", T("state_missing_one_key", lang).replace("{service}", name))]
    return [("ok", name)]


def _state_analytics(config, lang):
    loads = analytics_loads(config)
    doubled = sorted({i for i in loads if loads.count(i) > 1})
    if doubled:
        return [("warn", T("state_analytics_double", lang)
                 .replace("{n}", str(loads.count(doubled[0]))))]
    names = []
    if loads:
        names.append("Google Analytics")
    if umami_is_set(config):
        names.append("Umami")
    if not names:
        return [("off", T("state_none_f", lang))]
    text = " + ".join(names)
    if loads and _text(config.get("analytics_id", "")) == "":
        text = T("state_analytics_from_code", lang).replace("{name}", text)
    return [("ok", text)]


def _state_code(config, lang):
    # The warning of the cookie banner, again where it is fixed: the
    # consent of a card of code is chosen here.
    if _dict(config, "consent").get("enabled", False) is True and analytics_without_consent(config):
        return [("warn", T("state_cookie_analytics_needed", lang))]
    count = len(enabled_snippets(config))
    if count == 0:
        return [("off", T("state_nobody", lang))]
    if count == 1:
        return [("ok", T("state_one_item_active", lang))]
    return [("ok", T("state_n_active_pl", lang).replace("{n}", str(count)))]


def _state_consent(config, lang):
    consent = _dict(config, "consent")
    if consent.get("enabled", False) is True:
        problems = []
        # Google Analytics marked "necessary" runs before anyone agrees,
        # banner or not: the most common way to get this wrong.
        if analytics_without_consent(config):
            problems.append(("warn", T("state_cookie_analytics_needed", lang)))
        # With nothing waiting for consent the banner never shows, and the
        # author who switched it on is left wondering why.
        if not consent_categories(config):
            problems.append(("warn", T("state_cookie_on_m_useless", lang)))
        return problems or [("ok", T("state_on_m", lang))]
    # Google Analytics sets cookies, and in Europe it needs consent first.
    if analytics_loads(config):
        return [("warn", T("state_cookie_off_m_analytics", lang))]
    return [("off", T("state_off_m", lang))]


def _state_ai(config, lang):
    policy = _dict(config, "ai_training").get("policy", "open")
    keys = {"licensed": "state_ai_licence", "disallow": "state_ai_forbidden"}
    return [("ok", T(keys.get(policy, "state_ai_open"), lang))]


STATE_FUNCTIONS = {
    "site": _state_site,
    "home": _state_home,
    "biography": _state_biography,
    "projects": _state_projects,
    "boxes": _state_cards,
    "comments": _state_comments,
    "newsletter": _state_newsletter,
    "translation": _state_translation,
    "analytics": _state_analytics,
    "code": _state_code,
    "cookie": _state_consent,
    "ai": _state_ai,
}


def section_states(section_id, config, lang):
    """Everything worth saying about a section, most important first."""
    function = STATE_FUNCTIONS.get(section_id)
    if function is None:
        return []
    return function(config, lang)


def section_state(section_id, config, lang):
    """What the card of a section shows: (tone, text), or None."""
    states = section_states(section_id, config, lang)
    return states[0] if states else None


def setup_steps(config, articles, lang):
    """
    The first steps of the dashboard: every warning of the sections a
    visitor of the site would notice, then the first article to publish.
    Each step is (section id or "", text); the empty id stands for the
    editor of a new article.
    """
    steps = []
    for section_id in SETUP_SECTIONS:
        for tone, text in section_states(section_id, config, lang):
            if tone == "warn":
                steps.append((section_id, text))
    if not any(a.get("status") == "published" for a in articles):
        steps.append(("", T("state_first_article", lang)))
    return steps
