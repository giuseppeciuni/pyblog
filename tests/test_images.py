#!/usr/bin/env python3
"""
Tests for core/images.py.

    python3 tests/test_images.py

The PNGs here are built by hand, with an encoder written inside this file and
independent of the one being tested. A decoder checked only against its own
encoder proves nothing: the two agree on their shared mistakes.

The forward filters below are the definitions from the PNG specification,
written out separately from the inverse ones in the module, for the same
reason.
"""
import pathlib
import struct
import sys
import zlib

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from core import images  # noqa: E402

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


# ---------------------------------------------------------------------------
# An independent PNG encoder, for the fixtures
# ---------------------------------------------------------------------------

def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def applica_filtro(tipo, riga, precedente, bpp):
    """Apply a PNG scanline filter, the forward direction."""
    out = bytearray(len(riga))
    for i in range(len(riga)):
        sinistra = riga[i - bpp] if i >= bpp else 0
        sopra = precedente[i]
        sopra_sinistra = precedente[i - bpp] if i >= bpp else 0
        if tipo == 0:
            out[i] = riga[i]
        elif tipo == 1:
            out[i] = (riga[i] - sinistra) & 0xFF
        elif tipo == 2:
            out[i] = (riga[i] - sopra) & 0xFF
        elif tipo == 3:
            out[i] = (riga[i] - ((sinistra + sopra) >> 1)) & 0xFF
        else:
            out[i] = (riga[i] - paeth(sinistra, sopra, sopra_sinistra)) & 0xFF
    return bytes(out)


def costruisci_png(width, height, channels, righe, filtro=0, bit_depth=8,
                   interlace=0, palette=None, colour_type=None):
    """Assemble a PNG from raw rows, with a chosen filter."""
    if colour_type is None:
        colour_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    grezzo = bytearray()
    precedente = bytes(width * channels)
    for riga in righe:
        grezzo.append(filtro)
        grezzo.extend(applica_filtro(filtro, riga, precedente, channels))
        precedente = riga

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    testa = struct.pack(">IIBBBBB", width, height, bit_depth, colour_type, 0, 0, interlace)
    dati = images.PNG_SIGNATURE + chunk(b"IHDR", testa)
    if palette is not None:
        dati = dati + chunk(b"PLTE", palette)
    return (dati + chunk(b"IDAT", zlib.compress(bytes(grezzo), 6))
            + chunk(b"IEND", b""))


def righe_di_prova(width, height, channels):
    """Deterministic pixels that exercise every byte value."""
    righe = []
    for y in range(height):
        riga = bytearray(width * channels)
        for x in range(width):
            for c in range(channels):
                riga[x * channels + c] = (x * 7 + y * 13 + c * 29) % 256
        righe.append(bytes(riga))
    return righe


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

def test_decodifica_ogni_filtro():
    """Every one of the five PNG filters must be undone correctly."""
    print("\ndecodifica dei cinque filtri")
    for canali in (1, 2, 3, 4):
        righe = righe_di_prova(23, 11, canali)
        for filtro in range(5):
            dati = costruisci_png(23, 11, canali, righe, filtro=filtro)
            letta = images.read_png(dati)
            uguale = letta is not None and letta["rows"] == righe
            check(f"{canali} canali, filtro {filtro}", uguale,
                  "" if letta else "decodifica fallita")


def test_rifiuta_cio_che_non_sa_leggere():
    """Anything not understood must be refused, never guessed at."""
    print("\ncasi che vanno rifiutati")
    righe = righe_di_prova(8, 4, 3)
    check("16 bit per canale",
          images.read_png(costruisci_png(8, 4, 3, righe, bit_depth=16)) is None)
    check("PNG interlacciato",
          images.read_png(costruisci_png(8, 4, 3, righe, interlace=1)) is None)
    check("non e' un PNG", images.read_png(b"non sono un png") is None)
    check("PNG troncato",
          images.read_png(costruisci_png(8, 4, 3, righe)[:40]) is None)
    check("firma giusta ma niente dentro",
          images.read_png(images.PNG_SIGNATURE) is None)
    check("filtro sconosciuto",
          images.read_png(costruisci_png(8, 4, 3, righe, filtro=7)) is None)


def test_andata_e_ritorno():
    """What the module writes, the module must read back unchanged."""
    print("\nandata e ritorno write_png / read_png")
    for canali in (1, 2, 3, 4):
        righe = righe_di_prova(17, 9, canali)
        scritto = images.write_png(17, 9, canali, righe)
        riletto = images.read_png(scritto)
        check(f"{canali} canali", riletto is not None and riletto["rows"] == righe)


def test_ridimensionamento():
    """The picture comes back smaller, in the right proportion."""
    print("\nridimensionamento")
    larga = costruisci_png(400, 200, 3, righe_di_prova(400, 200, 3), filtro=1)
    esito = images.shrink_png(larga, max_side=100)
    check("un'immagine larga viene ridotta", esito is not None)
    if esito is not None:
        check("il lato lungo diventa il massimo", esito["to"][0] == 100, str(esito["to"]))
        check("le proporzioni sono mantenute", esito["to"][1] == 50, str(esito["to"]))
        riletta = images.read_png(esito["data"])
        check("il risultato e' un PNG leggibile",
              riletta is not None and (riletta["width"], riletta["height"]) == (100, 50))

    alta = costruisci_png(200, 400, 3, righe_di_prova(200, 400, 3), filtro=1)
    esito = images.shrink_png(alta, max_side=100)
    check("un'immagine alta viene ridotta sul lato giusto",
          esito is not None and esito["to"] == (50, 100), str(esito))


def test_quando_non_ridimensionare():
    """The cases where leaving the file alone is the right answer."""
    print("\nquando il file va lasciato com'e'")
    piccola = costruisci_png(80, 60, 3, righe_di_prova(80, 60, 3))
    check("gia' sotto il massimo", images.shrink_png(piccola, max_side=1600) is None)

    poco_grande = costruisci_png(110, 80, 3, righe_di_prova(110, 80, 3))
    check("solo di poco sopra il massimo, non vale la spesa",
          images.shrink_png(poco_grande, max_side=100) is None)

    esito = images.optimise_image("x.png", piccola, max_side=1600)
    check("optimise_image lo dice", esito["action"] == "kept"
          and esito["reason"] == "already_small", str(esito))
    check("e restituisce i byte originali", esito["data"] == piccola)

    check("un formato che non sappiamo trattare resta intatto",
          images.optimise_image("x.gif", b"GIF89a....")["reason"] == "format_not_supported")


def test_mai_piu_grande():
    """Publishing a file bigger than the one uploaded would defeat the point."""
    print("\nil risultato non e' mai piu' grande dell'originale")
    # Noise does not compress: re-encoding it can only lose.
    import random
    random.seed(11)
    righe = [bytes(random.randrange(256) for _ in range(200 * 3)) for _ in range(150)]
    rumore = costruisci_png(200, 150, 3, righe, filtro=1)
    esito = images.shrink_png(rumore, max_side=40)
    if esito is None:
        check("nessun guadagno: file tenuto", True)
    else:
        check("se ridotto, e' piu' piccolo", len(esito["data"]) < len(rumore),
              f"{len(esito['data'])} vs {len(rumore)}")


def test_tetto_di_pixel():
    """Beyond the budget the file is kept, with a reason."""
    print("\ntetto di pixel")
    originale = images.MAX_RESIZE_PIXELS
    try:
        images.MAX_RESIZE_PIXELS = 100          # tiny, so the fixture stays small
        grande = costruisci_png(60, 40, 3, righe_di_prova(60, 40, 3))
        esito = images.optimise_image("x.png", grande, max_side=10)
        check("non ridimensionata", esito["action"] == "kept", str(esito))
        check("e il motivo e' il tetto", esito["reason"] == "too_many_pixels", str(esito))
        check("i byte sono quelli di partenza", esito["data"] == grande)
    finally:
        images.MAX_RESIZE_PIXELS = originale


def test_metadati_jpeg():
    """The metadata segments go, the picture stays."""
    print("\nmetadati JPEG")
    scansione = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + bytes(range(256)) * 4

    def jpeg(segmenti):
        return b"\xff\xd8" + b"".join(segmenti) + scansione + b"\xff\xd9"

    exif = b"\xff\xe1" + struct.pack(">H", 2 + 5000) + b"Exif\x00\x00" + b"\x00" * 4994
    jfif = b"\xff\xe0" + struct.pack(">H", 2 + 14) + b"JFIF\x00" + b"\x00" * 9
    quant = b"\xff\xdb" + struct.pack(">H", 2 + 65) + b"\x00" + bytes(range(64))

    con_exif = jpeg([jfif, exif, quant])
    esito = images.strip_jpeg_metadata(con_exif)
    check("l'EXIF viene rimosso", esito is not None and len(esito["data"]) < len(con_exif))
    if esito is not None:
        ripulito = esito["data"]
        check("il JFIF resta", jfif in ripulito)
        check("la tabella di quantizzazione resta", quant in ripulito)
        check("l'EXIF non c'e' piu'", b"Exif\x00\x00" not in ripulito)
        check("i dati della scansione sono intatti", ripulito.endswith(scansione + b"\xff\xd9"))
        check("i byte risparmiati sono contati", esito["removed"] > 4990, str(esito["removed"]))

    senza = jpeg([jfif, quant])
    check("niente da rimuovere: nessuna riscrittura",
          images.strip_jpeg_metadata(senza) is None)
    check("non e' un JPEG", images.strip_jpeg_metadata(b"\x00\x01\x02\x03") is None)

    esito = images.optimise_image("foto.jpg", con_exif)
    check("optimise_image instrada i JPEG allo strip", esito["action"] == "stripped", str(esito))
    esito = images.optimise_image("foto.jpg", senza)
    check("e dice quando non puo' ridimensionarli",
          esito["reason"] == "jpeg_not_resizable", str(esito))


def main():
    test_decodifica_ogni_filtro()
    test_rifiuta_cio_che_non_sa_leggere()
    test_andata_e_ritorno()
    test_ridimensionamento()
    test_quando_non_ridimensionare()
    test_mai_piu_grande()
    test_tetto_di_pixel()
    test_metadati_jpeg()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
