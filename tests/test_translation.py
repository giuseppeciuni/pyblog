#!/usr/bin/env python3
"""
Checks on the automatic translation.

    python3 tests/test_translation.py

No network here: the external services are not called. What is checked is
the part that runs before and after them, and that is where the pictures
were being lost.

The article goes to the translator as HTML. DeepL and Google keep the tags;
a language model is asked to keep them and usually does - except when the
article is long, or the tag carries attributes it does not recognise, or it
simply decides the picture was not worth carrying. What came back then was a
good English text with the images gone, and nobody noticed until a reader
opened the English version of the article.

So the media never leaves: it is swapped for a marker and put back
afterwards. These checks hold that promise, including for the case the whole
thing exists for - the translator that loses the marker too.
"""
import pathlib
import sys

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.ai import restore_media, shield_media  # noqa: E402

PASSED = 0
FAILED = 0


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


PICTURE = '<img src="/media/foto.png" alt="Una foto">'
VIDEO = '<iframe src="https://www.youtube.com/embed/abc" width="560"></iframe>'
ARTICLE_FIXTURE = ('<h2>Titolo</h2><p>Prima riga.</p>'
            '<p class="ql-align-center">' + PICTURE + '</p>'
            '<p>Seconda riga.</p>' + VIDEO + '<p>Ultima riga.</p>')


def fake_translation(text):
    """Un traduttore che si comporta bene: cambia il testo, lascia i marcatori."""
    return (text.replace("Titolo", "Title")
                 .replace("Prima riga.", "First line.")
                 .replace("Seconda riga.", "Second line.")
                 .replace("Ultima riga.", "Last line."))


def test_full_round():
    print("\nandata e ritorno, con un traduttore che si comporta bene")
    protected, originals = shield_media(ARTICLE_FIXTURE)
    check("l'immagine non parte", "<img" not in protected, protected)
    check("il video non parte", "<iframe" not in protected, protected)
    check("restano due marcatori", protected.count("[[PBM") == 2, protected)
    check("i tag messi da parte sono due", len(originals) == 2, str(originals))
    check("il testo intorno c'e' ancora", "Prima riga." in protected, protected)

    returned, moved = restore_media(fake_translation(protected), originals)
    check("l'immagine e' tornata", PICTURE in returned, returned)
    check("il video e' tornato", VIDEO in returned, returned)
    check("nessun marcatore rimasto in pagina", "PBM" not in returned, returned)
    check("niente da rimettere a mano", moved == 0, str(moved))
    check("il testo e' quello tradotto", "First line." in returned, returned)
    check("l'immagine e' rimasta dentro il suo paragrafo",
          '<p class="ql-align-center">' + PICTURE + '</p>' in returned, returned)


def test_translator_loses_a_marker():
    print("\nil caso per cui esiste tutto questo: il marcatore sparisce")
    protected, originals = shield_media(ARTICLE_FIXTURE)

    # Il servizio restituisce il testo senza il primo marcatore.
    lost = fake_translation(protected).replace("[[PBM0]]", "")
    returned, moved = restore_media(lost, originals)
    check("l'immagine e' nell'articolo lo stesso", PICTURE in returned, returned)
    check("il video e' al suo posto", VIDEO in returned, returned)
    check("l'editor viene avvisato di una sola", moved == 1, str(moved))
    check("l'ordine e' rispettato: prima l'immagine, poi il video",
          returned.index(PICTURE) < returned.index(VIDEO), returned)

    # E il caso opposto: sparisce il secondo.
    lost_two = fake_translation(protected).replace("[[PBM1]]", "")
    returned_two, moved_two = restore_media(lost_two, originals)
    check("perso il secondo, torna comunque", VIDEO in returned_two, returned_two)
    check("e resta dopo l'immagine",
          returned_two.index(PICTURE) < returned_two.index(VIDEO), returned_two)
    check("avvisata una sola", moved_two == 1, str(moved_two))

    # Il caso peggiore: il servizio li perde tutti e due.
    all_lost = fake_translation(protected).replace("[[PBM0]]", "").replace("[[PBM1]]", "")
    returned_three, moved_three = restore_media(all_lost, originals)
    check("persi tutti, tornano tutti",
          PICTURE in returned_three and VIDEO in returned_three, returned_three)
    check("e l'ordine fra loro e' quello di partenza",
          returned_three.index(PICTURE) < returned_three.index(VIDEO), returned_three)
    check("avvisate due", moved_three == 2, str(moved_three))


def test_rewritten_marker():
    print("\nil marcatore riscritto a modo suo dal modello")
    protected, originals = shield_media(ARTICLE_FIXTURE)
    # Un modello linguistico ci mette gli spazi dentro.
    with_spaces = protected.replace("[[PBM0]]", "[[ PBM 0 ]]")
    returned, moved = restore_media(with_spaces, originals)
    check("riconosciuto lo stesso", PICTURE in returned, returned)
    check("e non contato come perso", moved == 0, str(moved))


def test_what_must_be_translated_stays():
    print("\ncio' che ha del testo dentro non viene protetto")
    text = ('<table><tbody><tr><td>comando</td><td>cosa fa</td></tr></tbody></table>'
             '<pre class="ql-syntax">def build():</pre>')
    protected, originals = shield_media(text)
    check("la tabella parte per essere tradotta", "<table" in protected, protected)
    check("le sue parole partono", "comando" in protected, protected)
    check("niente e' stato messo da parte", len(originals) == 0, str(originals))


def test_no_media_no_work():
    print("\nun articolo senza immagini non viene toccato")
    text = "<h2>Titolo</h2><p>Solo parole.</p>"
    protected, originals = shield_media(text)
    check("il testo passa intero", protected == text, protected)
    returned, moved = restore_media(protected, originals)
    check("e torna intero", returned == text, returned)
    check("senza avvisi", moved == 0, str(moved))


def main():
    test_full_round()
    test_translator_loses_a_marker()
    test_rewritten_marker()
    test_what_must_be_translated_stays()
    test_no_media_no_work()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
