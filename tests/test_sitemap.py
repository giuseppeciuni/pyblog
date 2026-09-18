#!/usr/bin/env python3
"""
Checks on sitemap.xml and on the pages left behind by a build.

    python3 tests/test_sitemap.py

The sitemap is the only list Google reads to find the pages, and it is
rewritten from scratch at every build, so it is always in step with the
articles on disk. The part that used to drift is the other direction: a build
only ever wrote files, it never removed them. Delete an article or change its
slug and its page stayed in output/, answering 200 to anyone who asked while
having disappeared from the sitemap - an indexed page that no longer exists,
and, for a changed slug, the same article at two addresses.

The test creates its own articles, with a recognisable slug, and removes them
again at the end.
"""
import pathlib
import re
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from core.articles import delete_article, save_article  # noqa: E402
from core.build import build  # noqa: E402
from core.config import CONFIG, OUTPUT_DIR  # noqa: E402

PASSED = 0
FAILED = 0

# Slugs used by this test only, so that the cleanup cannot touch a real article.
SLUG_UNO = "zzz-prova-sitemap-uno"
SLUG_DUE = "zzz-prova-sitemap-due"
SLUG_NUOVO = "zzz-prova-sitemap-uno-rinominato"


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED = PASSED + 1
        print(f"  ok    {description}")
    else:
        FAILED = FAILED + 1
        print(f"  FAIL  {description}")
        if detail != "":
            print(f"        {detail}")


def indirizzi_della_sitemap():
    """The <loc> addresses of the sitemap, in the order they are written."""
    testo = (OUTPUT_DIR / "sitemap.xml").read_text(encoding="utf-8")
    return re.findall(r"<loc>(.*?)</loc>", testo)


def percorso_di(indirizzo):
    """The file that should answer an address of the sitemap."""
    base = CONFIG["base_url"].rstrip("/")
    resto = indirizzo[len(base):].lstrip("/")
    if resto == "" or resto.endswith("/"):
        resto = resto + "index.html"
    return OUTPUT_DIR / resto


def articolo(titolo, slug, stato="published", tags="Prova"):
    return {"title": titolo, "slug": slug, "content": "<p>Testo di prova.</p>",
            "status": stato, "tags": tags}


def test_la_sitemap_esiste():
    """A build always writes sitemap.xml, and robots.txt points at it."""
    print("\nla sitemap viene creata a ogni build")
    build()
    sitemap = OUTPUT_DIR / "sitemap.xml"
    check("sitemap.xml esiste", sitemap.exists())
    testo = sitemap.read_text(encoding="utf-8")
    check("dichiara il namespace dei sitemap",
          "http://www.sitemaps.org/schemas/sitemap/0.9" in testo)
    check("contiene almeno la home", len(indirizzi_della_sitemap()) > 0)
    robots = (OUTPUT_DIR / "robots.txt").read_text(encoding="utf-8")
    check("robots.txt indica la sitemap", "Sitemap: " in robots,
          robots.strip())


def test_ogni_indirizzo_ha_una_pagina():
    """Every address in the sitemap must be answered by a file."""
    print("\nogni indirizzo della sitemap corrisponde a una pagina")
    base = CONFIG["base_url"].rstrip("/")
    mancanti = []
    fuori_dominio = []
    for indirizzo in indirizzi_della_sitemap():
        if not indirizzo.startswith(base + "/"):
            fuori_dominio.append(indirizzo)
            continue
        if not percorso_di(indirizzo).is_file():
            mancanti.append(indirizzo)
    check("nessun indirizzo fuori dal dominio del sito",
          fuori_dominio == [], ", ".join(fuori_dominio))
    check("nessun indirizzo senza pagina", mancanti == [],
          ", ".join(mancanti))


def test_nessuna_pagina_orfana():
    """
    And the other way round: no page in output/ may be missing from the
    sitemap. A page nobody lists is a page left behind by an older build.
    """
    print("\nnessuna pagina orfana in output/")
    elencate = set()
    for indirizzo in indirizzi_della_sitemap():
        elencate.add(percorso_di(indirizzo).resolve())
    orfane = []
    for cartella in ("posts", "tag", "pagine"):
        for radice in (OUTPUT_DIR, OUTPUT_DIR / "en"):
            if not (radice / cartella).is_dir():
                continue
            for pagina in (radice / cartella).glob("*.html"):
                if pagina.resolve() not in elencate:
                    orfane.append(str(pagina.relative_to(OUTPUT_DIR)))
    check("nessuna pagina fuori dalla sitemap", orfane == [],
          ", ".join(orfane))


def test_il_ciclo_di_vita_di_un_articolo():
    """Create, rename, delete: the sitemap and output/ follow every step."""
    print("\ncreazione, cambio di slug e cancellazione")

    # 1. A new published article appears in the sitemap and on disk.
    save_article(articolo("Prova sitemap uno", SLUG_UNO))
    save_article(articolo("Prova sitemap due", SLUG_DUE))
    build()
    indirizzi = indirizzi_della_sitemap()
    check("il nuovo articolo entra nella sitemap",
          any(SLUG_UNO + ".html" in i for i in indirizzi))
    check("e la sua pagina esiste",
          (OUTPUT_DIR / "posts" / f"{SLUG_UNO}.html").is_file())

    # 2. Changing the slug: the old page must not survive as a duplicate.
    #    This is what the editor does when the slug field changes.
    dati = articolo("Prova sitemap uno", SLUG_NUOVO)
    dati["original_slug"] = SLUG_UNO
    save_article(dati)
    delete_article(SLUG_UNO)
    build()
    indirizzi = indirizzi_della_sitemap()
    check("il nuovo slug e' nella sitemap",
          any(SLUG_NUOVO + ".html" in i for i in indirizzi))
    check("il vecchio slug non e' piu' nella sitemap",
          not any(f"/{SLUG_UNO}.html" in i for i in indirizzi))
    check("e la pagina del vecchio slug e' sparita da output/",
          not (OUTPUT_DIR / "posts" / f"{SLUG_UNO}.html").exists())

    # 3. Unpublishing: a draft has no public page.
    bozza = articolo("Prova sitemap due", SLUG_DUE, stato="draft")
    save_article(bozza)
    build()
    check("l'articolo messo in bozza esce dalla sitemap",
          not any(SLUG_DUE + ".html" in i for i in indirizzi_della_sitemap()))
    check("e la sua pagina non resta online",
          not (OUTPUT_DIR / "posts" / f"{SLUG_DUE}.html").exists())

    # 4. Deleting: page and sitemap entry both go.
    delete_article(SLUG_NUOVO)
    delete_article(SLUG_DUE)
    build()
    check("l'articolo cancellato esce dalla sitemap",
          not any(SLUG_NUOVO + ".html" in i for i in indirizzi_della_sitemap()))
    check("e la sua pagina e' sparita da output/",
          not (OUTPUT_DIR / "posts" / f"{SLUG_NUOVO}.html").exists())
    check("anche l'indice del tag inutilizzato e' sparito",
          not (OUTPUT_DIR / "tag" / "prova.html").exists())


def test_le_pagine_vere_restano():
    """The sweep must only remove leftovers, never a page still in use."""
    print("\nla pulizia non tocca le pagine buone")
    build()
    for nome in ("index.html", "archivio.html", "404.html", "robots.txt",
                 "sitemap.xml", "rss.xml", "search-index.json", "llms.txt",
                 "style.css", "site.js", "training-rights.html"):
        check(f"{nome} resta al suo posto", (OUTPUT_DIR / nome).is_file())
    check("la home inglese resta", (OUTPUT_DIR / "en" / "index.html").is_file())
    check("la cartella media non viene toccata",
          (OUTPUT_DIR / "media").is_dir())


def main():
    try:
        test_la_sitemap_esiste()
        test_il_ciclo_di_vita_di_un_articolo()
        test_ogni_indirizzo_ha_una_pagina()
        test_nessuna_pagina_orfana()
        test_le_pagine_vere_restano()
    finally:
        # Whatever happened, the test articles must not stay behind.
        for slug in (SLUG_UNO, SLUG_DUE, SLUG_NUOVO):
            delete_article(slug)
        build()

    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
