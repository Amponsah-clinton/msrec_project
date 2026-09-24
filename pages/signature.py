"""Turns whatever an admin gives us as the Chair's signature -- a photo or
scan of a signature on paper, an image file, or a stroke drawn on the
Settings page's signature pad -- into one clean, tightly-cropped
transparent PNG that drops onto any certificate.

  * A photographed / scanned signature has a paper-coloured background.
    It's removed: the paper tone is estimated from the image itself, every
    pixel's opacity is set by how much darker than the paper it is, and
    the whole signature is re-inked in the pen's own colour, so faint
    scanner shading disappears and no white box is left behind.
  * An image that already has transparency (e.g. a PNG cut-out, or the
    pad's own output) keeps its alpha as is.
  * The result is cropped to the ink itself (plus a small margin) and
    scaled down to a sensible maximum, so the certificate can fit it
    into the signature space by aspect ratio alone.

Raises ValueError with a human-readable message if the file isn't an image
or has no visible signature in it.
"""
from io import BytesIO

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

MAX_INPUT_PIXELS = 24_000_000
WORK_SIZE = (1800, 1800)
MAX_OUTPUT = (900, 360)
CROP_ALPHA = 24  # alpha above this counts as "ink" when finding the crop box
MARGIN = 0.04


def _clamp(value):
    return 0 if value < 0 else 255 if value > 255 else int(value)


def process_signature(raw_bytes):
    try:
        image = Image.open(BytesIO(raw_bytes))
        if image.width * image.height > MAX_INPUT_PIXELS:
            raise ValueError("That image is too large -- please use one under about 24 megapixels.")
        image = ImageOps.exif_transpose(image).convert("RGBA")
    except UnidentifiedImageError:
        raise ValueError("That file isn't a readable image.")
    except (OSError, Image.DecompressionBombError):
        raise ValueError("That file isn't a readable image.")

    image.thumbnail(WORK_SIZE)
    alpha = image.getchannel("A")

    if alpha.getextrema()[0] < 250:
        # Already has real transparency -- trust it.
        ink = image
    else:
        ink = _remove_paper(image)

    box = ink.getchannel("A").point(lambda a: 255 if a > CROP_ALPHA else 0).getbbox()
    if not box:
        raise ValueError("No signature could be found in that image -- use dark ink on a plain light background.")

    pad_x = int((box[2] - box[0]) * MARGIN) + 2
    pad_y = int((box[3] - box[1]) * MARGIN) + 2
    box = (
        max(0, box[0] - pad_x), max(0, box[1] - pad_y),
        min(ink.width, box[2] + pad_x), min(ink.height, box[3] + pad_y),
    )
    ink = ink.crop(box)
    ink.thumbnail(MAX_OUTPUT, Image.LANCZOS)

    out = BytesIO()
    ink.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _remove_paper(image):
    rgb = image.convert("RGB")
    gray = rgb.convert("L")

    # Paper tone = a high percentile of the luminance histogram (most of a
    # signature photo is paper); the darkest few percent is the pen.
    hist = gray.histogram()
    total = sum(hist)

    def percentile(p):
        target, running = total * p, 0
        for level, count in enumerate(hist):
            running += count
            if running >= target:
                return level
        return 255

    paper = percentile(0.80)
    pen = percentile(0.01)
    span = max(40, paper - pen)
    # Ignore the faintest paper texture / shadow, then ramp to full opacity
    # well before reaching the pen's own darkness.
    floor = paper - span * 0.18
    ceil = paper - span * 0.72
    if ceil >= floor:
        ceil = floor - 1

    lut = [_clamp((floor - v) * 255 / (floor - ceil)) for v in range(256)]
    alpha = gray.point(lut)

    strong = alpha.point(lambda a: 255 if a > 200 else 0)
    if strong.getbbox():
        r, g, b = (int(c) for c in ImageStat.Stat(rgb, mask=strong).mean)
    else:
        r, g, b = 20, 35, 63
    # A photographed pen reads a bit washed out -- deepen it slightly so it
    # prints crisply, without changing its hue.
    r, g, b = (int(c * 0.85) for c in (r, g, b))

    result = Image.new("RGBA", image.size, (r, g, b, 0))
    result.putalpha(alpha)
    return result
