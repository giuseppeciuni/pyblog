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

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

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


def apply_filter(tipo, line, precedente, bpp):
    """Apply a PNG scanline filter, the forward direction."""
    out = bytearray(len(line))
    for i in range(len(line)):
        left = line[i - bpp] if i >= bpp else 0
        above = precedente[i]
        above_left = precedente[i - bpp] if i >= bpp else 0
        if tipo == 0:
            out[i] = line[i]
        elif tipo == 1:
            out[i] = (line[i] - left) & 0xFF
        elif tipo == 2:
            out[i] = (line[i] - above) & 0xFF
        elif tipo == 3:
            out[i] = (line[i] - ((left + above) >> 1)) & 0xFF
        else:
            out[i] = (line[i] - paeth(left, above, above_left)) & 0xFF
    return bytes(out)


def build_png(width, height, channels, lines, filter_value=0, bit_depth=8,
                   interlace=0, palette=None, colour_type=None):
    """Assemble a PNG from raw rows, with a chosen filter."""
    if colour_type is None:
        colour_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    raw = bytearray()
    precedente = bytes(width * channels)
    for line in lines:
        raw.append(filter_value)
        raw.extend(apply_filter(filter_value, line, precedente, channels))
        precedente = line

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    head = struct.pack(">IIBBBBB", width, height, bit_depth, colour_type, 0, 0, interlace)
    payload_value = images.PNG_SIGNATURE + chunk(b"IHDR", head)
    if palette is not None:
        payload_value = payload_value + chunk(b"PLTE", palette)
    return (payload_value + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def test_lines(width, height, channels):
    """Deterministic pixels that exercise every byte value."""
    lines = []
    for y in range(height):
        line = bytearray(width * channels)
        for x in range(width):
            for c in range(channels):
                line[x * channels + c] = (x * 7 + y * 13 + c * 29) % 256
        lines.append(bytes(line))
    return lines


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

def test_decode_every_filter():
    """Every one of the five PNG filters must be undone correctly."""
    print("\ndecodifica dei cinque filtri")
    for channel_values in (1, 2, 3, 4):
        lines = test_lines(23, 11, channel_values)
        for filter_value in range(5):
            payload_value = build_png(23, 11, channel_values, lines, filter_value=filter_value)
            read_back = images.read_png(payload_value)
            same = read_back is not None and read_back["rows"] == lines
            check(f"{channel_values} canali, filtro {filter_value}", same,
                  "" if read_back else "decodifica fallita")


def test_refuses_what_it_cannot_read():
    """Anything not understood must be refused, never guessed at."""
    print("\ncasi che vanno rifiutati")
    lines = test_lines(8, 4, 3)
    check("16 bit per canale",
          images.read_png(build_png(8, 4, 3, lines, bit_depth=16)) is None)
    check("PNG interlacciato",
          images.read_png(build_png(8, 4, 3, lines, interlace=1)) is None)
    check("non e' un PNG", images.read_png(b"non sono un png") is None)
    check("PNG troncato",
          images.read_png(build_png(8, 4, 3, lines)[:40]) is None)
    check("firma giusta ma niente dentro",
          images.read_png(images.PNG_SIGNATURE) is None)
    check("filtro sconosciuto",
          images.read_png(build_png(8, 4, 3, lines, filter_value=7)) is None)


def test_round_trip():
    """What the module writes, the module must read back unchanged."""
    print("\nandata e ritorno write_png / read_png")
    for channel_values in (1, 2, 3, 4):
        lines = test_lines(17, 9, channel_values)
        written = images.write_png(17, 9, channel_values, lines)
        reread_value = images.read_png(written)
        check(f"{channel_values} canali", reread_value is not None and reread_value["rows"] == lines)


def test_resizing():
    """The picture comes back smaller, in the right proportion."""
    print("\nridimensionamento")
    wide = build_png(400, 200, 3, test_lines(400, 200, 3), filter_value=1)
    outcome = images.shrink_png(wide, max_side=100)
    check("un'immagine larga viene ridotta", outcome is not None)
    if outcome is not None:
        check("il lato lungo diventa il massimo", outcome["to"][0] == 100, str(outcome["to"]))
        check("le proporzioni sono mantenute", outcome["to"][1] == 50, str(outcome["to"]))
        reread = images.read_png(outcome["data"])
        check("il risultato e' un PNG leggibile",
              reread is not None and (reread["width"], reread["height"]) == (100, 50))

    high = build_png(200, 400, 3, test_lines(200, 400, 3), filter_value=1)
    outcome = images.shrink_png(high, max_side=100)
    check("un'immagine alta viene ridotta sul lato giusto",
          outcome is not None and outcome["to"] == (50, 100), str(outcome))


def test_when_not_to_resize():
    """The cases where leaving the file alone is the right answer."""
    print("\nquando il file va lasciato com'e'")
    small = build_png(80, 60, 3, test_lines(80, 60, 3))
    check("gia' sotto il massimo", images.shrink_png(small, max_side=1600) is None)

    slightly_large = build_png(110, 80, 3, test_lines(110, 80, 3))
    check("solo di poco sopra il massimo, non vale la spesa",
          images.shrink_png(slightly_large, max_side=100) is None)

    outcome = images.optimise_image("x.png", small, max_side=1600)
    check("optimise_image lo dice", outcome["action"] == "kept"
          and outcome["reason"] == "already_small", str(outcome))
    check("e restituisce i byte originali", outcome["data"] == small)

    check("un formato che non sappiamo trattare resta intatto",
          images.optimise_image("x.gif", b"GIF89a....")["reason"] == "format_not_supported")


def test_never_larger():
    """Publishing a file bigger than the one uploaded would defeat the point."""
    print("\nil risultato non e' mai piu' grande dell'originale")
    # Noise does not compress: re-encoding it can only lose.
    import random
    random.seed(11)
    lines = [bytes(random.randrange(256) for _ in range(200 * 3)) for _ in range(150)]
    noise = build_png(200, 150, 3, lines, filter_value=1)
    outcome = images.shrink_png(noise, max_side=40)
    if outcome is None:
        check("nessun guadagno: file tenuto", True)
    else:
        check("se ridotto, e' piu' piccolo", len(outcome["data"]) < len(noise),
              f"{len(outcome['data'])} vs {len(noise)}")


def test_pixel_ceiling():
    """Beyond the budget the file is kept, with a reason."""
    print("\ntetto di pixel")
    originale = images.MAX_RESIZE_PIXELS
    try:
        images.MAX_RESIZE_PIXELS = 100          # tiny, so the fixture stays small
        large = build_png(60, 40, 3, test_lines(60, 40, 3))
        outcome = images.optimise_image("x.png", large, max_side=10)
        check("non ridimensionata", outcome["action"] == "kept", str(outcome))
        check("e il motivo e' il tetto", outcome["reason"] == "too_many_pixels", str(outcome))
        check("i byte sono quelli di partenza", outcome["data"] == large)
    finally:
        images.MAX_RESIZE_PIXELS = originale


def test_jpeg_metadata():
    """The metadata segments go, the picture stays."""
    print("\nmetadati JPEG")
    scan = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + bytes(range(256)) * 4

    def jpeg(segments):
        return b"\xff\xd8" + b"".join(segments) + scan + b"\xff\xd9"

    exif = b"\xff\xe1" + struct.pack(">H", 2 + 5000) + b"Exif\x00\x00" + b"\x00" * 4994
    jfif = b"\xff\xe0" + struct.pack(">H", 2 + 14) + b"JFIF\x00" + b"\x00" * 9
    how_many_text = b"\xff\xdb" + struct.pack(">H", 2 + 65) + b"\x00" + bytes(range(64))

    with_exif = jpeg([jfif, exif, how_many_text])
    outcome = images.strip_jpeg_metadata(with_exif)
    check("l'EXIF viene rimosso", outcome is not None and len(outcome["data"]) < len(with_exif))
    if outcome is not None:
        cleaned = outcome["data"]
        check("il JFIF resta", jfif in cleaned)
        check("la tabella di quantizzazione resta", how_many_text in cleaned)
        check("l'EXIF non c'e' piu'", b"Exif\x00\x00" not in cleaned)
        check("i dati della scansione sono intatti", cleaned.endswith(scan + b"\xff\xd9"))
        check("i byte risparmiati sono contati", outcome["removed"] > 4990, str(outcome["removed"]))

    without = jpeg([jfif, how_many_text])
    check("niente da rimuovere: nessuna riscrittura",
          images.strip_jpeg_metadata(without) is None)
    check("non e' un JPEG", images.strip_jpeg_metadata(b"\x00\x01\x02\x03") is None)

    outcome = images.optimise_image("foto.jpg", with_exif)
    check("optimise_image instrada i JPEG allo strip", outcome["action"] == "stripped", str(outcome))
    outcome = images.optimise_image("foto.jpg", without)
    check("e dice quando non puo' ridimensionarli",
          outcome["reason"] == "jpeg_not_resizable", str(outcome))


def main():
    test_decode_every_filter()
    test_refuses_what_it_cannot_read()
    test_round_trip()
    test_resizing()
    test_when_not_to_resize()
    test_never_larger()
    test_pixel_ceiling()
    test_jpeg_metadata()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
