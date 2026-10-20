#!/usr/bin/env python3
"""
Checks on the labs.

    python3 tests/test_labs.py

A lab is an article that puts another one into practice with code. It opens
with a box linking to the project, the article it refers to points to it,
and the labs have a page of their own and an entry in the menu. Nothing is
written to disk, and the configuration is put back as it was at the end.
"""
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.articles import article_from_data  # noqa: E402
from core.config import CONFIG  # noqa: E402

PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    """Record one assertion and print its outcome."""
    global PASSED, FAILED
    if condition:
        PASSED = PASSED + 1
        print(f"  ok    {description}")
    else:
        FAILED = FAILED + 1
        print(f"  FAIL  {description}")
        if detail != "":
            print(f"        {detail}")


def article(number, **extra):
    art = {"title": f"Articolo {number}", "slug": f"articolo-{number}",
           "content": "<p>Testo dell'articolo.</p>", "status": "published",
           "date": f"2026-01-{number:02d}", "tags": "Prova"}
    art.update(extra)
    return art


THEORY = article(1)
LAB = article(2, kind="lab", lab_of="articolo-1", stack="Python 3.12, <LiteLLM>",
               run_steps="git clone https://github.com/esempio/lab\npython3 main.py <file>",
               repo_url="https://github.com/esempio/lab", title="Lab uno")
LAB_WITHOUT = article(3, kind="lab", repo_url="javascript:alert(1)", title="Lab due")
ARTICLES_FIXTURE = [article(4), LAB_WITHOUT, LAB, THEORY]


def test_data():
    print("\ni dati dell'articolo")
    saved = article_from_data({"title": "T", "kind": "lab", "lab_of": " articolo-1 ",
                                 "repo_url": " https://github.com/x/y ", "stack": " Python "}, "t")
    check("i campi del lab vengono salvati puliti",
          saved["kind"] == "lab" and saved["lab_of"] == "articolo-1"
          and saved["repo_url"] == "https://github.com/x/y" and saved["stack"] == "Python")
    check("un tipo sconosciuto e' un articolo normale",
          article_from_data({"title": "T", "kind": "altro"}, "t")["kind"] == "")
    check("senza dati non e' un lab", article_from_data({"title": "T"}, "t")["kind"] == "")


def test_lab_page():
    print("\nla pagina di un lab")
    build.note_labs(ARTICLES_FIXTURE)
    page_html = build.generate_article_page(LAB, "it", ARTICLES_FIXTURE)
    box = page_html.split('<aside class="lab-box"')[1].split("</aside>")[0]
    check("apre con il link al progetto su GitHub",
          '<a class="lab-code" href="https://github.com/esempio/lab" rel="noopener">'
          'Il codice su GitHub' in box, box)
    check("dice con cosa e' fatto, senza far passare codice HTML",
          "Fatto con: Python 3.12, &lt;LiteLLM&gt;" in box)
    check("mostra i comandi per eseguirlo, un comando per riga",
          'Per eseguirlo:</p>\n<pre class="ql-syntax" spellcheck="false">'
          'git clone https://github.com/esempio/lab\npython3 main.py &lt;file&gt;</pre>' in box,
          box)
    check("porta all'articolo che mette in pratica",
          'Mette in pratica: <a href="/posts/articolo-1.html">Articolo 1</a>' in box)
    check("il riquadro sta prima del testo",
          page_html.index("lab-box") < page_html.index('class="post-content"'))
    without = build.generate_article_page(LAB_WITHOUT, "it", ARTICLES_FIXTURE)
    box = without.split('<aside class="lab-box"')[1].split("</aside>")[0]
    check("un indirizzo non valido non diventa un link", "<a " not in box, box)

    theory = build.generate_article_page(THEORY, "it", ARTICLES_FIXTURE)
    end = theory.split('class="lab-box lab-finish"')[1].split("</aside>")[0]
    check("l'articolo di riferimento segnala il suo lab in fondo al testo",
          '<a href="/posts/articolo-2.html">Lab uno</a>' in end
          and "https://github.com/esempio/lab" in end
          and theory.index("lab-finish") > theory.index('class="post-content"'))
    check("un articolo senza lab non ha riquadri",
          "lab-box" not in build.generate_article_page(ARTICLES_FIXTURE[0], "it", ARTICLES_FIXTURE))


def test_labs_page_and_menu():
    print("\nla pagina Labs e il menu")
    build.note_labs(ARTICLES_FIXTURE)
    page_html = build.generate_labs_page(ARTICLES_FIXTURE, "it")
    listing = page_html.split('<div class="articles-list">')[1].split("</section>")[0]
    check("elenca i lab e solo quelli",
          "articolo-2.html" in listing and "articolo-3.html" in listing
          and "articolo-1.html" not in listing and "articolo-4.html" not in listing)
    check("ha titolo e indirizzo canonico",
          "<title>Labs" in page_html and 'rel="canonical" href="'
          + CONFIG["base_url"].rstrip("/") + '/labs.html"' in page_html)
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    check("con dei lab online il menu ha Labs",
          '<a href="/labs.html">Labs</a>' in home.split("</nav>")[0])
    check("negli elenchi un lab ha la sua etichetta",
          home.count('<p class="art-kicker">Lab</p>') == 2)
    check("in inglese, senza lab tradotti, niente voce e niente pagina",
          "labs.html" not in build.generate_homepage(ARTICLES_FIXTURE, "en").split("</nav>")[0]
          and "/en/labs.html" not in build.generate_sitemap(ARTICLES_FIXTURE))
    check("la sitemap elenca la pagina", "/labs.html</loc>" in build.generate_sitemap(ARTICLES_FIXTURE))
    articles_only = [THEORY, ARTICLES_FIXTURE[0]]
    build.note_labs(articles_only)
    check("senza lab il menu non la elenca",
          "labs.html" not in build.generate_homepage(articles_only, "it").split("</nav>")[0]
          and "labs.html" not in build.generate_sitemap(articles_only))


def test_home_and_create_lab():
    print("\ni lab in home e il pulsante che ne crea uno")
    build.note_labs(ARTICLES_FIXTURE)
    home = build.generate_homepage(ARTICLES_FIXTURE, "it")
    section = home.split('class="home-section home-labs"')[1].split("</section>")[0]
    check("la home ha la sezione Labs con i lab, il codice e il link a tutti",
          '<a class="lab-home-title" href="/posts/articolo-2.html">Lab uno</a>' in section
          and "https://github.com/esempio/lab" in section and "Python 3.12" in section
          and '<a href="/labs.html">Tutti i lab' in section, section[:500])
    check("sta prima dell'elenco degli articoli",
          home.index("home-labs") < home.index('id="articles"'))
    check("non compare dalla seconda pagina in poi",
          "home-labs" not in build.generate_homepage(ARTICLES_FIXTURE, "it", page=2, total_pages=2))
    check("senza lab la home non ha la sezione",
          "home-labs" not in build.generate_homepage([THEORY, ARTICLES_FIXTURE[0]], "it"))

    original = server.load_articles
    server.load_articles = lambda: ARTICLES_FIXTURE
    try:
        theory = server.editor_page(dict(THEORY), "csrf")
        lab = server.editor_page(dict(LAB), "csrf")
        new = server.editor_page(None, "csrf", dict(THEORY, tags="AI, Python"))
        listing = server.admin_page(ARTICLES_FIXTURE, "csrf")
    finally:
        server.load_articles = original
    cards = theory.split('<nav class="theme-cards"')[1].split("</nav>")[0]
    check("sopra l'editor ci sono le parti del tema: la teoria, corrente, e i suoi lab",
          '<span class="card-theme" aria-current="page"><span class="card-name">Teoria</span>'
          in cards and '<a class="card-theme" href="/edit?slug=articolo-2"' in cards
          and cards.index("Teoria") < cards.index("articolo-2"), cards)
    check("e i link che aggiungono quello che manca",
          'id="link-create-lab" href="/edit?lab_of=articolo-1">+ Lab</a>' in cards
          and 'href="/edit?lab_of=articolo-1&amp;kind=practical">+ In pratica</a>' in cards)
    lab_cards = lab.split('<nav class="theme-cards"')[1].split("</nav>")[0]
    check("dal lab si torna alla teoria con una scheda",
          '<a class="card-theme" href="/edit?slug=articolo-1"' in lab_cards
          and 'aria-current="page"><span class="card-name">Lab</span>' in lab_cards)
    check("il nuovo articolo si apre come lab gia' legato, con i tag dell'articolo",
          '<option value="lab" selected>' in new
          and '<option value="articolo-1" selected>' in new
          and 'id="tags" value="AI, Python"' in new and "Nuovo lab di: Articolo 1" in new
          and '<div id="fields-lab" class="card-lab" >' in new
          and '<span class="card-state">nuovo</span>' in new)
    original = server.load_articles
    server.load_articles = lambda: ARTICLES_FIXTURE
    try:
        practice = server.editor_page(None, "csrf", dict(THEORY), "practical")
    finally:
        server.load_articles = original
    check("allo stesso modo si crea la versione pratica",
          '<option value="practical" selected>' in practice
          and "Nuova versione pratica di: Articolo 1" in practice)
    check("anche dall'elenco degli articoli si crea il lab di un articolo",
          'href="/edit?lab_of=articolo-1">Crea il lab di questo articolo</a>' in listing
          and 'href="/edit?lab_of=articolo-2"' not in listing)


def test_three_levels():
    print("\ni tre livelli di un tema")
    practice = article(7, kind="practical", lab_of="articolo-1", title="Per chi decide")
    all_articles = [practice] + ARTICLES_FIXTURE
    build.note_labs(all_articles)
    saved = article_from_data({"title": "T", "kind": "practical", "lab_of": "articolo-1"}, "t")
    check("la versione pratica e' un tipo di articolo", saved["kind"] == "practical")

    page_html = build.generate_article_page(practice, "it", all_articles)
    opening = page_html.split('<aside class="lab-box">')[1].split("</aside>")[0]
    check("la versione pratica si apre dicendo da quale articolo parte",
          "In pratica" in opening
          and 'La versione per chi decide di <a href="/posts/articolo-1.html">Articolo 1</a>'
          in opening, opening)
    end = page_html.split('class="lab-box lab-finish"')[1].split("</aside>")[0]
    check("e in fondo porta all'idea e al lab dello stesso tema",
          "L'idea</span> <a href=\"/posts/articolo-1.html\">" in end
          and "Lab</span> <a href=\"/posts/articolo-2.html\">" in end
          and "articolo-7" not in end, end)
    idea_page = build.generate_article_page(THEORY, "it", all_articles)
    end = idea_page.split('class="lab-box lab-finish"')[1].split("</aside>")[0]
    check("l'idea porta alla versione pratica e poi al lab, in quest'ordine",
          end.index("articolo-7.html") < end.index("articolo-2.html"))
    lab = build.generate_article_page(LAB, "it", all_articles)
    end = lab.split('class="lab-box lab-finish"')[1].split("</aside>")[0]
    check("il lab porta all'idea e alla versione pratica",
          "articolo-1.html" in end and "articolo-7.html" in end)
    home = build.generate_homepage(all_articles, "it")
    check("negli elenchi la versione pratica ha la sua etichetta",
          '<p class="art-kicker">In pratica</p>' in home)
    check("non finisce nella pagina Labs",
          "articolo-7.html" not in build.generate_labs_page(all_articles, "it")
          .split('<div class="articles-list">')[1].split("</section>")[0])
    check("un lab senza articolo di riferimento non ha il riquadro in fondo",
          "lab-finish" not in build.generate_article_page(LAB_WITHOUT, "it", all_articles))


def test_english():
    print("\ni lab in inglese")
    def translated(art, title):
        return dict(art, title_en=title, content_en="<p>Text.</p>", translation_confirmed=True)
    idea_page = translated(THEORY, "The idea")
    lab = translated(LAB, "Lab one")
    all_articles = [article(4), LAB_WITHOUT, lab, idea_page]
    build.note_labs(all_articles)
    page_html = build.generate_article_page(lab, "en", all_articles)
    opening = page_html.split('<aside class="lab-box">')[1].split("</aside>")[0]
    check("il riquadro del lab e' in inglese e porta alle pagine inglesi",
          "The code on GitHub" in opening and "Built with:" in opening
          and 'Puts into practice: <a href="/en/posts/articolo-1.html">The idea</a>' in opening,
          opening)
    listing = build.generate_labs_page(all_articles, "en")
    check("la pagina Labs inglese elenca solo i lab tradotti",
          "/en/posts/articolo-2.html" in listing and "articolo-3.html" not in listing
          and 'rel="canonical" href="' + CONFIG["base_url"].rstrip("/") + '/en/labs.html"' in listing)
    check("il menu inglese ha Labs e la sitemap elenca la pagina",
          '<a href="/en/labs.html">Labs</a>' in build.generate_homepage(all_articles, "en").split("</nav>")[0]
          and "/en/labs.html</loc>" in build.generate_sitemap(all_articles))
    end = build.generate_article_page(idea_page, "en", all_articles)
    check("l'idea in inglese porta al lab in inglese",
          'Lab</span> <a href="/en/posts/articolo-2.html">Lab one</a>' in end)


def test_original():
    print("\npubblicato in origine")
    elsewhere = article(5, original_url="https://www.startupbusiness.it/rubrica/pezzo/")
    page_html = build.generate_article_page(elsewhere, "it", [elsewhere])
    check("sotto il titolo c'e' la riga con il sito e il link",
          'Pubblicato in origine su <a href="https://www.startupbusiness.it/rubrica/pezzo/" '
          'rel="noopener">startupbusiness.it</a>' in page_html
          and page_html.index("published-source") < page_html.index('class="post-content"'))
    check("senza la spunta l'indirizzo canonico resta quello di questa pagina",
          'rel="canonical" href="' + CONFIG["base_url"] + '/posts/articolo-5.html"' in page_html)
    elsewhere["original_canonical"] = True
    check("con la spunta i motori di ricerca vengono mandati all'originale",
          'rel="canonical" href="https://www.startupbusiness.it/rubrica/pezzo/"'
          in build.generate_article_page(elsewhere, "it", [elsewhere]))
    fake_value = article(6, original_url="javascript:alert(1)", original_canonical=True)
    page_html = build.generate_article_page(fake_value, "it", [fake_value])
    check("un indirizzo non valido non mostra nulla e non tocca il canonico",
          "published-source" not in page_html and "javascript:" not in page_html)
    saved = article_from_data({"title": "T", "original_url": " https://x.it/a ",
                                 "original_canonical": "si"}, "t")
    check("i campi vengono salvati puliti",
          saved["original_url"] == "https://x.it/a" and saved["original_canonical"] is False)
    check("un articolo normale non ha la riga",
          "published-source" not in build.generate_article_page(THEORY, "it", ARTICLES_FIXTURE))


def test_sharing():
    print("\ncondivisione")
    CONFIG["base_url"] = "https://esempio.it"
    art = article(8, title="Costi & modelli")
    page_html = build.generate_article_page(art, "it", [art])
    line = page_html.split('<div class="share">')[1].split("</div>")[0]
    check("sul sito c'e' solo il pulsante che copia il link",
          'class="share-copy" data-url="https://esempio.it/posts/articolo-8.html" '
          'data-done="Link copiato">Copia il link</button>' in line and "<a " not in line, line)
    check("nessun link ad altre piattaforme nella pagina pubblica",
          "linkedin.com" not in page_html and "ycombinator" not in page_html
          and "reddit.com" not in page_html and "twitter.com" not in page_html)
    CONFIG["share_buttons"] = False
    check("spento dalla configurazione non compare",
          'class="share"' not in build.generate_article_page(art, "it", [art]))
    CONFIG["share_buttons"] = True
    original = server.load_articles
    server.load_articles = lambda: [art]
    try:
        editor = server.editor_page(art, "csrf")
    finally:
        server.load_articles = original
    check("la condivisione sulle piattaforme sta nell'editor, per gli articoli pubblicati",
          '<details class="share-admin only-published">' in editor
          and all(f'id="share-{n}"' in editor for n in ("linkedin", "hn", "reddit", "x"))
          and '"public_base": "https://esempio.it"' in editor)
    script = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("e l'editor compila i link con indirizzo e titolo",
          "function updateShareLinks()" in script and "news.ycombinator.com/submitlink" in script)


def test_editor():
    print("\nl'editor")
    original = server.load_articles
    server.load_articles = lambda: ARTICLES_FIXTURE
    try:
        page_html = server.editor_page(LAB, "csrf")
        normal = server.editor_page(THEORY, "csrf")
    finally:
        server.load_articles = original
    check("il tipo e i campi del lab hanno i valori dell'articolo",
          '<option value="lab" selected>' in page_html
          and '<div id="fields-lab" class="card-lab" >' in page_html
          and '<div id="fields-reference" >' in page_html
          and 'id="repo_url" value="https://github.com/esempio/lab"' in page_html
          and 'id="stack" value="Python 3.12, &lt;LiteLLM&gt;"' in page_html)
    choice = page_html.split('<select id="lab_of"')[1].split("</select>")[0]
    check("l'articolo di riferimento si sceglie tra gli articoli che non sono lab",
          '<option value="articolo-1" selected>Articolo 1</option>' in choice
          and "articolo-4" in choice and "articolo-3" not in choice
          and 'value="articolo-2"' not in choice, choice)
    check("su un articolo normale i campi del lab sono nascosti",
          '<option value="" selected>' in normal
          and '<div id="fields-lab" class="card-lab" hidden>' in normal
          and '<div id="fields-reference" hidden>' in normal)
    def group(name):
        return page_html.split('id="group-' + name + '"')[1].split('<details class="group-editor"')[0]
    check("la colonna e' fatta di cinque gruppi, solo Dettagli aperto",
          page_html.count('<details class="group-editor"') == 5
          and '<details class="group-editor" id="group-details" open>' in page_html
          and page_html.count('<details class="group-editor" id="group-') == 5
          and page_html.count('class="group-editor" id="group-details" open') == 1
          and 'id="group-series" open' not in page_html)
    check("ogni campo sta nel gruppo che gli compete",
          'id="slug"' in group("details") and 'id="tags"' in group("details")
          and 'id="image"' in group("details")
          and 'id="series"' in group("series") and 'id="kind"' in group("series")
          and 'id="repo_url"' not in group("series")
          and 'id="description"' in group("preview") and 'id="reader_preview"' in group("preview")
          and 'id="translation_authorized"' in group("english") and 'id="editor-en"' in group("english")
          and 'id="original_url"' in group("advanced") and 'id="list-box-code-own"' in group("advanced")
          and 'id="btn-versions"' in group("advanced"))
    check("il progetto del lab sta sopra il titolo, nella colonna del testo",
          page_html.index('id="fields-lab"') < page_html.index('id="title"') < page_html.index('id="editor"'))
    check("tutto il resto sta nel pannello Dettagli, che si apre da un pulsante",
          'id="btn-details" aria-expanded="false"' in page_html
          and page_html.index('id="panel-details"') < page_html.index('id="group-details"')
          and page_html.index('id="panel-publish"') < page_html.index('id="title"'))
    check("i pulsanti per pubblicare restano fuori dai gruppi",
          page_html.index('id="panel-publish"') < page_html.index('<details class="group-editor"')
          and 'id="btn-publish"' not in "".join(group(n) for n in
                                                  ("details", "series", "preview", "english", "advanced")))
    script = (pathlib.Path(__file__).resolve().parent.parent / "static" / "admin.js").read_text()
    check("il pannello si apre, si chiude e si chiude con Esc",
          "function toggleDetails(openIt)" in script and "evt.key === 'Escape'" in script)
    check("un gruppo chiuso dice cosa contiene",
          'id="summary-series"' in page_html and "function updateGroupSummaries()" in script
          and "rememberOpenGroups();" in script)
    check("il salvataggio manda i campi del lab",
          "kind: document.getElementById('kind').value" in script
          and "repo_url: document.getElementById('repo_url').value" in script)


def main():
    saved_page = copy.deepcopy(CONFIG)
    try:
        CONFIG["language"] = "it"
        test_data()
        test_lab_page()
        test_labs_page_and_menu()
        test_home_and_create_lab()
        test_three_levels()
        test_english()
        test_original()
        test_sharing()
        test_editor()
    finally:
        CONFIG.clear()
        CONFIG.update(saved_page)
        build.LABS_ONLINE.clear()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
