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

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

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


IMMAGINE = '<img src="/media/foto.png" alt="Una foto">'
VIDEO = '<iframe src="https://www.youtube.com/embed/abc" width="560"></iframe>'
ARTICOLO = ('<h2>Titolo</h2><p>Prima riga.</p>'
            '<p class="ql-align-center">' + IMMAGINE + '</p>'
            '<p>Seconda riga.</p>' + VIDEO + '<p>Ultima riga.</p>')


def traduzione_finta(testo):
    """Un traduttore che si comporta bene: cambia il testo, lascia i marcatori."""
    return (testo.replace("Titolo", "Title")
                 .replace("Prima riga.", "First line.")
                 .replace("Seconda riga.", "Second line.")
                 .replace("Ultima riga.", "Last line."))


def test_il_giro_completo():
    print("\nandata e ritorno, con un traduttore che si comporta bene")
    protetto, originali = shield_media(ARTICOLO)
    check("l'immagine non parte", "<img" not in protetto, protetto)
    check("il video non parte", "<iframe" not in protetto, protetto)
    check("restano due marcatori", protetto.count("[[PBM") == 2, protetto)
    check("i tag messi da parte sono due", len(originali) == 2, str(originali))
    check("il testo intorno c'e' ancora", "Prima riga." in protetto, protetto)

    tornato, spostate = restore_media(traduzione_finta(protetto), originali)
    check("l'immagine e' tornata", IMMAGINE in tornato, tornato)
    check("il video e' tornato", VIDEO in tornato, tornato)
    check("nessun marcatore rimasto in pagina", "PBM" not in tornato, tornato)
    check("niente da rimettere a mano", spostate == 0, str(spostate))
    check("il testo e' quello tradotto", "First line." in tornato, tornato)
    check("l'immagine e' rimasta dentro il suo paragrafo",
          '<p class="ql-align-center">' + IMMAGINE + '</p>' in tornato, tornato)


def test_il_traduttore_perde_un_marcatore():
    print("\nil caso per cui esiste tutto questo: il marcatore sparisce")
    protetto, originali = shield_media(ARTICOLO)

    # Il servizio restituisce il testo senza il primo marcatore.
    perso = traduzione_finta(protetto).replace("[[PBM0]]", "")
    tornato, spostate = restore_media(perso, originali)
    check("l'immagine e' nell'articolo lo stesso", IMMAGINE in tornato, tornato)
    check("il video e' al suo posto", VIDEO in tornato, tornato)
    check("l'editor viene avvisato di una sola", spostate == 1, str(spostate))
    check("l'ordine e' rispettato: prima l'immagine, poi il video",
          tornato.index(IMMAGINE) < tornato.index(VIDEO), tornato)

    # E il caso opposto: sparisce il secondo.
    perso_due = traduzione_finta(protetto).replace("[[PBM1]]", "")
    tornato_due, spostate_due = restore_media(perso_due, originali)
    check("perso il secondo, torna comunque", VIDEO in tornato_due, tornato_due)
    check("e resta dopo l'immagine",
          tornato_due.index(IMMAGINE) < tornato_due.index(VIDEO), tornato_due)
    check("avvisata una sola", spostate_due == 1, str(spostate_due))

    # Il caso peggiore: il servizio li perde tutti e due.
    tutti_persi = traduzione_finta(protetto).replace("[[PBM0]]", "").replace("[[PBM1]]", "")
    tornato_tre, spostate_tre = restore_media(tutti_persi, originali)
    check("persi tutti, tornano tutti",
          IMMAGINE in tornato_tre and VIDEO in tornato_tre, tornato_tre)
    check("e l'ordine fra loro e' quello di partenza",
          tornato_tre.index(IMMAGINE) < tornato_tre.index(VIDEO), tornato_tre)
    check("avvisate due", spostate_tre == 2, str(spostate_tre))


def test_il_marcatore_riscritto():
    print("\nil marcatore riscritto a modo suo dal modello")
    protetto, originali = shield_media(ARTICOLO)
    # Un modello linguistico ci mette gli spazi dentro.
    con_spazi = protetto.replace("[[PBM0]]", "[[ PBM 0 ]]")
    tornato, spostate = restore_media(con_spazi, originali)
    check("riconosciuto lo stesso", IMMAGINE in tornato, tornato)
    check("e non contato come perso", spostate == 0, str(spostate))


def test_quello_che_va_tradotto_resta():
    print("\ncio' che ha del testo dentro non viene protetto")
    testo = ('<table><tbody><tr><td>comando</td><td>cosa fa</td></tr></tbody></table>'
             '<pre class="ql-syntax">def build():</pre>')
    protetto, originali = shield_media(testo)
    check("la tabella parte per essere tradotta", "<table" in protetto, protetto)
    check("le sue parole partono", "comando" in protetto, protetto)
    check("niente e' stato messo da parte", len(originali) == 0, str(originali))


def test_niente_media_niente_lavoro():
    print("\nun articolo senza immagini non viene toccato")
    testo = "<h2>Titolo</h2><p>Solo parole.</p>"
    protetto, originali = shield_media(testo)
    check("il testo passa intero", protetto == testo, protetto)
    tornato, spostate = restore_media(protetto, originali)
    check("e torna intero", tornato == testo, tornato)
    check("senza avvisi", spostate == 0, str(spostate))


def main():
    test_il_giro_completo()
    test_il_traduttore_perde_un_marcatore()
    test_il_marcatore_riscritto()
    test_quello_che_va_tradotto_resta()
    test_niente_media_niente_lavoro()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
