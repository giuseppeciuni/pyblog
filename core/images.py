"""
Shrinking uploaded images, without an image library.

The constraint of this project is absolute: standard library only. That draws
a hard line through this problem, and it is worth stating plainly rather than
discovering later.

  - PNG is a format we can read and write ourselves. It is zlib plus a
    handful of per-scanline filters, both of which are in the standard
    library, so a PNG is decoded, downscaled and re-encoded here.
  - JPEG is not. A baseline decoder means Huffman tables, dequantisation and
    an inverse DCT, which is a project of its own and slow in pure Python.
    What we can do losslessly is drop the metadata - the EXIF block and the
    embedded preview a phone camera leaves behind, often hundreds of
    kilobytes - and that is what happens to a JPEG here.
  - GIF and WebP are left untouched.

The gap is covered from the other side: the editor downscales an image in the
browser before uploading it, using the canvas, which can decode every format
the browser knows. This module is the backstop for everything that does not
come through a browser - above all the images extracted from a Word document,
which are often the largest a blog ever receives.
"""
import struct
import zlib

# The widest an image ever needs to be. The article column is 720px and the
# cover is capped at 340px tall, so 1600 covers a high-density screen at twice
# the size with room to spare. Anything beyond it is bytes the reader pays for
# and never sees.
DEFAULT_MAX_SIDE = 1600

# Above this, we do not attempt to resize a PNG at all.
#
# Undoing the per-scanline filters means touching every byte in Python, and
# that is what the whole operation costs: measured at roughly one microsecond
# per source pixel on an ordinary machine. So the budget is really a time
# budget - six megapixels is about six seconds, which is the most an author
# should wait for an upload to come back.
#
# Past it the file is kept as it is and the caller is told why. It rarely
# bites: the editor shrinks an image in the browser before uploading it, so
# what reaches this code is mostly the pictures pulled out of a Word
# document, which are seldom that large.
MAX_RESIZE_PIXELS = 6_000_000

# How much larger than the cap an image has to be before resizing it earns
# its cost. Below this it is left alone.
MIN_OVERSIZE = 1.25

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Channels per colour type, as defined by the PNG specification.
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


# ---------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------

def _read_chunks(data):
    """
    Walk the chunks of a PNG. Yields (type, payload).

    Returns nothing at all if the file is malformed: a truncated or corrupt
    upload must leave the original file alone, not raise.
    """
    if not data.startswith(PNG_SIGNATURE):
        return
    position = len(PNG_SIGNATURE)
    total = len(data)
    while position + 8 <= total:
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        start = position + 8
        end = start + length
        if end + 4 > total:
            return
        yield kind, data[start:end]
        position = end + 4
        if kind == b"IEND":
            return


def _paeth(a, b, c):
    """The PNG Paeth predictor: the neighbour closest to a + b - c."""
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_row(filter_type, row, previous, bytes_per_pixel):
    """
    Undo one scanline filter, in place, and return the row.

    This is the expensive part of reading a PNG, and it cannot be made cheap:
    every filter but the first reads bytes the loop has just written, so it
    has to run one byte at a time.
    """
    length = len(row)
    if filter_type == 0:                       # None
        return row
    if filter_type == 1:                       # Sub
        for i in range(bytes_per_pixel, length):
            row[i] = (row[i] + row[i - bytes_per_pixel]) & 0xFF
        return row
    if filter_type == 2:                       # Up
        for i in range(length):
            row[i] = (row[i] + previous[i]) & 0xFF
        return row
    if filter_type == 3:                       # Average
        for i in range(length):
            left = 0
            if i >= bytes_per_pixel:
                left = row[i - bytes_per_pixel]
            row[i] = (row[i] + ((left + previous[i]) >> 1)) & 0xFF
        return row
    if filter_type == 4:                       # Paeth
        for i in range(length):
            left = 0
            upper_left = 0
            if i >= bytes_per_pixel:
                left = row[i - bytes_per_pixel]
                upper_left = previous[i - bytes_per_pixel]
            row[i] = (row[i] + _paeth(left, previous[i], upper_left)) & 0xFF
        return row
    return None                                 # unknown filter: give up


def read_png(data):
    """
    Decode a PNG into {width, height, channels, rows}.

    Returns None for anything this decoder does not handle rather than
    guessing: 16 bits per channel, interlaced files, sub-byte palettes. The
    caller then keeps the original file, which is always a safe outcome.
    """
    width = 0
    height = 0
    bit_depth = 0
    colour_type = 0
    interlace = 0
    palette = b""
    transparency = b""
    compressed = []
    seen_header = False

    for kind, payload in _read_chunks(data):
        if kind == b"IHDR":
            if len(payload) < 13:
                return None
            (width, height, bit_depth, colour_type,
             _compression, _filter, interlace) = struct.unpack(">IIBBBBB", payload[:13])
            seen_header = True
        elif kind == b"PLTE":
            palette = payload
        elif kind == b"tRNS":
            transparency = payload
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            break

    if not seen_header or width == 0 or height == 0:
        return None
    if bit_depth != 8 or interlace != 0:
        return None
    if colour_type not in PNG_CHANNELS:
        return None
    if len(compressed) == 0:
        return None

    try:
        raw = zlib.decompress(b"".join(compressed))
    except zlib.error:
        return None

    channels = PNG_CHANNELS[colour_type]
    row_bytes = width * channels
    if len(raw) < height * (row_bytes + 1):
        return None

    rows = []
    previous = bytearray(row_bytes)
    position = 0
    for _ in range(height):
        filter_type = raw[position]
        current = bytearray(raw[position + 1:position + 1 + row_bytes])
        position = position + 1 + row_bytes
        restored = _unfilter_row(filter_type, current, previous, channels)
        if restored is None:
            return None
        rows.append(bytes(restored))
        previous = restored

    return {"width": width, "height": height, "channels": channels,
            "colour_type": colour_type, "rows": rows,
            "palette": palette, "transparency": transparency}


def write_png(width, height, channels, rows):
    """
    Encode rows of pixels as a PNG, filtering each scanline with Sub.

    Filter 0 was the first thing tried here, because it costs nothing. It is
    not good enough: on a photograph an unfiltered PNG compresses so poorly
    that the downscaled file came out LARGER than the original, and the
    safety check below then kept the original - the resize never won.

    Sub stores the difference from the pixel to the left, which is where the
    redundancy in a photograph is, and it costs one pass over the bytes of
    the OUTPUT image, which is the small one. The caller still compares with
    the original and keeps whichever is smaller.
    """
    colour_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    raw = bytearray()
    for row in rows:
        raw.append(1)                        # filter 1: Sub
        filtered = bytearray(row)
        for i in range(len(filtered) - 1, channels - 1, -1):
            filtered[i] = (filtered[i] - filtered[i - channels]) & 0xFF
        raw.extend(filtered)

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)
    return (PNG_SIGNATURE
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _expand_palette(row_indexes, palette, transparency):
    """Turn a row of palette indexes into RGB, or RGBA when tRNS is present."""
    if transparency == b"":
        out = bytearray(len(row_indexes) * 3)
        for i, index in enumerate(row_indexes):
            base = index * 3
            out[i * 3:i * 3 + 3] = palette[base:base + 3]
        return bytes(out), 3
    out = bytearray(len(row_indexes) * 4)
    for i, index in enumerate(row_indexes):
        base = index * 3
        out[i * 4:i * 4 + 3] = palette[base:base + 3]
        if index < len(transparency):
            out[i * 4 + 3] = transparency[index]
        else:
            out[i * 4 + 3] = 255
    return bytes(out), 4


def resize_rows(rows, width, channels, new_width, new_height):
    """
    Downscale by point sampling, taking the centre of each source block.

    The sampling is done with slice steps, which run in C: one slice read and
    one slice write per channel per output row, instead of a Python loop over
    millions of pixels. The trade-off is that this is point sampling, not an
    averaging filter, so a heavily detailed image can alias slightly. At the
    sizes involved - an image on its way from 4000px to 1600px, to then be
    drawn by the browser at 800 - that is not visible, and an averaging filter
    would cost a Python pass over every source pixel, which is exactly what
    this avoids.
    """
    height = len(rows)
    out_rows = []
    for j in range(new_height):
        source_row = rows[min(height - 1, (j * height + new_height // 2) // new_height)]
        destination = bytearray(new_width * channels)
        for c in range(channels):
            column = source_row[c::channels]
            sampled = bytearray(new_width)
            for i in range(new_width):
                sampled[i] = column[min(width - 1,
                                        (i * width + new_width // 2) // new_width)]
            destination[c::channels] = sampled
        out_rows.append(bytes(destination))
    return out_rows


def shrink_png(data, max_side=DEFAULT_MAX_SIDE):
    """
    Return a smaller PNG, or None when there is nothing to gain or nothing we
    can safely do.

    None is not a failure: it means "keep the file you already have".
    """
    image = read_png(data)
    if image is None:
        return None

    width = image["width"]
    height = image["height"]
    # Not just "bigger than the cap": bigger by enough to be worth the wait.
    # A 1800px image trimmed to 1600 measured four seconds for thirteen per
    # cent, which is a bad trade for whoever is watching the upload spinner.
    if max(width, height) <= max_side * MIN_OVERSIZE:
        return None
    if width * height > MAX_RESIZE_PIXELS:
        return None

    rows = image["rows"]
    channels = image["channels"]
    if image["colour_type"] == 3:
        if image["palette"] == b"":
            return None
        expanded = []
        for row in rows:
            new_row, channels = _expand_palette(row, image["palette"],
                                                image["transparency"])
            expanded.append(new_row)
        rows = expanded

    if max(width, height) == width:
        new_width = max_side
        new_height = max(1, round(height * max_side / width))
    else:
        new_height = max_side
        new_width = max(1, round(width * max_side / height))

    smaller = write_png(new_width, new_height, channels,
                        resize_rows(rows, width, channels, new_width, new_height))
    # Re-encoding can lose: a small palette image blown up to RGB, a picture
    # whose original encoder filtered better than we do. Publishing a bigger
    # file than the author uploaded would be the opposite of the point.
    if len(smaller) >= len(data):
        return None
    return {"data": smaller, "from": (width, height), "to": (new_width, new_height)}


# ---------------------------------------------------------------------------
# JPEG
# ---------------------------------------------------------------------------

# Segments that carry no image data. APP1 is where EXIF lives, along with the
# preview a phone camera embeds; APP2 holds colour profiles; COM is a comment.
# APP0 is kept: it is the small JFIF header some readers expect.
JPEG_DROPPABLE = set(range(0xE1, 0xF0)) | {0xFE}


def strip_jpeg_metadata(data):
    """
    Remove the metadata segments of a JPEG, losslessly.

    We cannot resize a JPEG without decoding it, but we can throw away what is
    not the picture. A photo straight from a phone often carries an EXIF block
    with a full-size preview inside it, which can be a third of the file.

    Returns None when there is nothing worth removing or the file is not one
    we recognise.
    """
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None

    out = bytearray(data[:2])
    position = 2
    total = len(data)
    removed = 0

    while position + 4 <= total:
        if data[position] != 0xFF:
            break
        marker = data[position + 1]
        # Start of scan: the compressed picture follows and must be copied
        # through untouched, to the end of the file.
        if marker == 0xDA:
            out.extend(data[position:])
            position = total
            break
        # Standalone markers carry no length.
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            out.extend(data[position:position + 2])
            position = position + 2
            continue
        length = struct.unpack(">H", data[position + 2:position + 4])[0]
        end = position + 2 + length
        if end > total:
            return None
        if marker in JPEG_DROPPABLE:
            removed = removed + (end - position)
        else:
            out.extend(data[position:end])
        position = end

    if position < total:
        out.extend(data[position:])
    if removed == 0:
        return None
    return {"data": bytes(out), "removed": removed}


# ---------------------------------------------------------------------------
# THE ENTRY POINT
# ---------------------------------------------------------------------------

def optimise_image(file_name, data, max_side=DEFAULT_MAX_SIDE):
    """
    Make an uploaded image smaller where we can, and say what happened.

    Always returns a dictionary with "data": either the smaller file or the
    one that came in. "action" describes the outcome, for the message shown
    to the author:

        "resized"   the picture was downscaled (PNG)
        "stripped"  metadata was removed without touching the picture (JPEG)
        "kept"      nothing was done, and "reason" says why
    """
    name = file_name.lower()
    result = {"data": data, "action": "kept", "reason": "", "saved": 0}

    if name.endswith(".png"):
        smaller = shrink_png(data, max_side)
        if smaller is None:
            image = read_png(data)
            if image is None:
                result["reason"] = "unsupported_png"
            elif max(image["width"], image["height"]) <= max_side * MIN_OVERSIZE:
                result["reason"] = "already_small"
            elif image["width"] * image["height"] > MAX_RESIZE_PIXELS:
                result["reason"] = "too_many_pixels"
            else:
                result["reason"] = "no_gain"
            return result
        result["data"] = smaller["data"]
        result["action"] = "resized"
        result["from"] = smaller["from"]
        result["to"] = smaller["to"]
        result["saved"] = len(data) - len(smaller["data"])
        return result

    if name.endswith(".jpg") or name.endswith(".jpeg"):
        stripped = strip_jpeg_metadata(data)
        if stripped is None:
            # Resizing a JPEG would need a decoder this project cannot carry.
            result["reason"] = "jpeg_not_resizable"
            return result
        result["data"] = stripped["data"]
        result["action"] = "stripped"
        result["saved"] = len(data) - len(stripped["data"])
        return result

    result["reason"] = "format_not_supported"
    return result
