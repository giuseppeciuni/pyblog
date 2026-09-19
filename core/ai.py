"""
Automatic translation and the LLM-backed generators.

Every call to an external service happens here, in the backend, because the
API keys are secret and must never end up in a public page. Only urllib from
the standard library is used: no external dependency.

Three kinds of work live in this module:

  - translation IT -> EN (DeepL, Google, or an LLM);
  - short generations for the editor (SEO description, reader preview);
  - the full SEO / AI-SEO analysis of an article.

The last two need a model that can reason about a text, so they only work
with the LLM services: DeepL and Google can translate, not write.
"""
import json
import re
import urllib.parse
import urllib.error as _urlerr
import urllib.request as _urlreq

from core.articles import load_articles, plain_text
from core.config import CONFIG, admin_language, secret_setting
from core.i18n import T



# ---------------------------------------------------------------------------
# PROTECTING WHAT MUST NOT BE TRANSLATED
# ---------------------------------------------------------------------------
# An image has no text to translate, but it does go through the translator
# along with the rest of the article, and it does not always come back. DeepL
# and Google keep the tags; a language model is asked to keep them and mostly
# does, except when the article is long, or the tag carries a data- attribute,
# or the model decides the picture was not important. What comes back then is
# a perfectly good English text with the pictures missing, which nobody
# notices until a reader opens the English version.
#
# So the media never leaves: each tag is swapped for a short marker, the text
# around it is translated, and the tags are put back exactly as they were.
# Alt text is the one thing inside them that a reader sees, and it stays
# untranslated - the alternative is handing the whole tag back to the service
# that loses it.

MEDIA_TAGS = ("img", "iframe", "video", "audio", "source", "embed", "object")

# <img ...>, <iframe ...>...</iframe>: the pair form has to be caught whole,
# marker included, or the closing tag would come back on its own.
MEDIA_PATTERN = re.compile(
    r"<(" + "|".join(MEDIA_TAGS) + r")\b[^>]*>(?:.*?</\1\s*>)?",
    re.IGNORECASE | re.DOTALL)

# The marker as it goes out, and as we look for it on the way back. It is
# read by a machine translator and by a language model, so it is deliberately
# dull: no words to translate, no punctuation to tidy up. Coming back it is
# matched loosely, because a model can add a space inside the brackets.
MARKER = "[[PBM{n}]]"
MARKER_PATTERN = re.compile(r"\[\[\s*PBM\s*(\d+)\s*\]\]")


def shield_media(text):
    """
    Replace every media tag with a marker.

    Return the text to translate and the list of the original tags, in the
    order they appeared: their position in that list is the number in the
    marker.
    """
    originals = []

    def to_marker(match):
        originals.append(match.group(0))
        return MARKER.format(n=len(originals) - 1)

    return MEDIA_PATTERN.sub(to_marker, text), originals


def restore_media(text, originals):
    """
    Put the original tags back where their markers are.

    Return the restored text and how many tags the translator dropped along
    the way. A dropped tag is put back straight after the previous one that
    survived - not where it was, but in the same order as the others and
    still in the article, which is the whole point. The caller says so to
    the author, because a picture that moved is worth a second look.
    """
    if len(originals) == 0:
        return text, 0

    restored = set()

    def to_tag(match):
        index_value = int(match.group(1))
        if index_value < 0 or index_value >= len(originals):
            return ""
        restored.add(index_value)
        return originals[index_value]

    text = MARKER_PATTERN.sub(to_tag, text)

    missing = [i for i in range(len(originals)) if i not in restored]
    for index_value in missing:
        tag = originals[index_value]
        # After the nearest tag that did come back, or before the nearest one
        # that follows it, so the pictures stay in the order they were
        # written even when the translator dropped the first of them.
        previous = None
        for candidate in range(index_value - 1, -1, -1):
            if candidate in restored and originals[candidate] in text:
                previous = candidate
                break
        following = None
        for candidate in range(index_value + 1, len(originals)):
            if candidate in restored and originals[candidate] in text:
                following = candidate
                break
        if previous is not None:
            cut = text.index(originals[previous]) + len(originals[previous])
            text = text[:cut] + tag + text[cut:]
        elif following is not None:
            text = text[:text.index(originals[following])] + tag \
                + text[text.index(originals[following]):]
        else:
            text = text + tag
        restored.add(index_value)

    return text, len(missing)


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
    # A translation cut off at the token ceiling is the other way an article
    # loses its second half, pictures included, without anything looking
    # wrong: the text that comes back reads fine right up to where it stops.
    # Better to refuse it and say so than to save half an article.
    if result.get("stop_reason") == "max_tokens":
        raise ValueError(T("err_translation_truncated", admin_language()))
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
    if choices[0].get("finish_reason") == "length":
        raise ValueError(T("err_translation_truncated", admin_language()))
    messaggio = choices[0].get("message", {})
    translated_text = messaggio.get("content", "")
    return translated_text

def translate_text(text):
    """
    Translate a text from Italian to English using the configured service.
    Return a dictionary with the outcome and the translated text (or the error).
    """
    if text is None:
        return {"ok": True, "text": ""}
    if text.strip() == "":
        return {"ok": True, "text": ""}

    # The pictures, the videos and the embeds stay here and are put back
    # afterwards: see shield_media above for why they are not allowed to
    # travel to the translator.
    text, media = shield_media(text)

    translation_config = CONFIG.get("translation", {})
    service = translation_config.get("service", "deepl")

    try:
        if service == "deepl":
            tradotto = translate_with_deepl(
                text, secret_setting(translation_config, "deepl_api_key"))
        elif service == "google":
            tradotto = translate_with_google(
                text, secret_setting(translation_config, "google_api_key"))
        elif service == "llm":
            tradotto = translate_with_llm(
                text,
                secret_setting(translation_config, "llm_api_key"),
                translation_config.get("llm_endpoint", ""),
                translation_config.get("llm_model", ""))
        elif service == "openai":
            tradotto = translate_with_openai_compat(
                text,
                secret_setting(translation_config, "openai_api_key"),
                "https://api.openai.com/v1/chat/completions",
                translation_config.get("openai_model", "gpt-4o-mini"))
        elif service == "deepseek":
            tradotto = translate_with_openai_compat(
                text,
                secret_setting(translation_config, "deepseek_api_key"),
                "https://api.deepseek.com/chat/completions",
                translation_config.get("deepseek_model", "deepseek-chat"))
        else:
            return {"ok": False, "error": T("err_unknown_translation_service", admin_language())}
        tradotto, spostate = restore_media(tradotto, media)
        return {"ok": True, "text": tradotto, "media_recovered": spostate}
    except _urlerr.HTTPError as error:
        return {"ok": False, "error": T("err_service_error", admin_language()) + str(error.code)}
    except Exception as error:
        return {"ok": False, "error": str(error)}

def call_llm_with_prompt(prompt, max_tokens=300):
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
            api_key = secret_setting(translation_config, "llm_api_key")
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
                api_key = secret_setting(translation_config, "openai_api_key")
                endpoint = "https://api.openai.com/v1/chat/completions"
                modello = translation_config.get("openai_model", "gpt-4o-mini")
            else:
                api_key = secret_setting(translation_config, "deepseek_api_key")
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
        return {"ok": False, "error": T("err_service_error", admin_language()) + str(error.code)}
    except Exception as error:
        return {"ok": False, "error": str(error)}

def generate_seo_description(html_content, title_value):
    """
    Generate an SEO description (meta description) from the article
    content, using the configured LLM. The description is an inviting
    summary of about 150 characters, not just the start of the text.
    """
    text = plain_text(html_content)
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
    result = call_llm_with_prompt(prompt)
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
    text = plain_text(html_content)
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
    result = call_llm_with_prompt(prompt)
    if result["ok"]:
        preview = result["text"].strip().strip('"').strip()
        return {"ok": True, "preview": preview}
    return result


def extract_json_object(text):
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


def published_articles_for_linking(exclude_slug):
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
    text = plain_text(html_content)
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
    other_articles = published_articles_for_linking(slug_value)
    articles_lines = []
    for art in other_articles:
        articles_lines.append("- " + art["title"] + " (slug: " + art["slug"] + ")")
    if len(articles_lines) > 0:
        articles_text = "\n".join(articles_lines)
    else:
        articles_text = "(nessun altro articolo pubblicato)"

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
        "Contenuto:\n" + excerpt + "\n\n"
        "Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo, "
        "senza markdown, con esattamente queste chiavi:\n"
        "{\n"
        '  "primary_keywords": [3-5 keyword principali, in italiano],\n'
        '  "secondary_keywords": [5-8 keyword secondarie e long-tail],\n'
        '  "suggested_tags": [4-6 tag consigliati per questo blog],\n'
        '  "title_variants": [2-3 varianti di titolo SEO, max 60 caratteri],\n'
        '  "meta_description_review": "giudizio in 1-2 frasi sulla meta description attuale, con proposta se migliorabile",\n'
        '  "anchor_texts": [3-5 anchor text per il backlink da ' + backlink_site + '],\n'
        '  "internal_links": [per ogni link interno consigliato un oggetto {"slug": "...", "anchor": "..."}; lista vuota se nessuno e\' pertinente],\n'
        '  "faq": [2-3 oggetti {"question": "...", "answer": "..."} con domande che i lettori farebbero a un motore AI, e risposte di 2-3 frasi tratte dall\'articolo],\n'
        '  "ai_seo_tips": [2-4 consigli concreti e specifici per QUESTO articolo per comparire nelle risposte dei motori AI]\n'
        "}"
    )

    result = call_llm_with_prompt(prompt, max_tokens=2000)
    if result["ok"] is not True:
        return result

    analysis = extract_json_object(result["text"])
    if analysis is None:
        return {"ok": False, "error": T("err_seo_analysis_parse", admin_language())}

    return {"ok": True, "analysis": analysis, "article_url": article_url}