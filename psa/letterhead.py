"""Header / footer artwork for agreement PDFs (PSA > Letterhead).

Letterhead artwork is designed for the full width of the page -- its side
margins are part of the design (they're what keep the logo 20 mm from the
edge) -- so unlike pages.letter_images nothing is trimmed here: the image
is printed edge to edge exactly as drawn. It is only

  * turned upright (phone photos carry EXIF rotation),
  * kept transparent if it is (a PNG with no background stays that way),
  * scaled down to at most 2480 px wide (300 dpi across A4), never up,
  * re-encoded as PNG (logos, line art) or high-quality JPEG (photographic).

Raises ValueError with a message the admin can act on.
"""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from . import pdf

MAX_UPLOAD = 12 * 1024 * 1024
MAX_INPUT_PIXELS = 40_000_000
MAX_WIDTH = 2480            # 210 mm at 300 dpi
MIN_WIDTH = 800             # below this a full-width print looks soft
SHARP_WIDTH = 1650          # ~200 dpi across A4
JPEG_QUALITY = 92

LIMIT_MM = {"header": pdf.HEADER_MAX_H / pdf.mm, "footer": pdf.FOOTER_MAX_H / pdf.mm}


def process(raw_bytes, kind):
    """Returns (bytes, content_type, width, height)."""
    try:
        image = Image.open(BytesIO(raw_bytes))
        if image.width * image.height > MAX_INPUT_PIXELS:
            raise ValueError(f"That {kind} image is too large — use one under about 40 megapixels.")
        image = ImageOps.exif_transpose(image)
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError(f"That file isn't a readable image — upload a PNG or JPG for the {kind}.")

    if image.width < MIN_WIDTH:
        raise ValueError(
            f"That {kind} is only {image.width} px wide, so it would print blurred across the page. "
            f"Use artwork at least {MIN_WIDTH} px wide — ideally {MAX_WIDTH} px (A4 width at 300 dpi)."
        )
    if image.height > image.width:
        raise ValueError(f"That {kind} is taller than it is wide — upload the {kind} strip only, not a whole page.")

    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)

    out = BytesIO()
    if has_alpha or _flat_art(image):
        image.save(out, format="PNG", optimize=True)
        content_type = "image/png"
    else:
        image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        content_type = "image/jpeg"
    return out.getvalue(), content_type, image.width, image.height


def _flat_art(image):
    """Few distinct colours = logo / line art (PNG stays crisp and small)."""
    sample = image.copy()
    sample.thumbnail((200, 200))
    return sample.getcolors(maxcolors=1024) is not None


def printed_size(width, height, kind):
    """How the artwork prints: (width_mm, height_mm, full_width). Full-width
    unless that would make it taller than the kind's limit, in which case it
    is scaled down to the limit and centred."""
    if not width or not height:
        return None
    w_mm = pdf.PAGE_W / pdf.mm
    h_mm = w_mm * height / width
    limit = LIMIT_MM[kind]
    if h_mm > limit:
        return round(limit * width / height, 1), round(limit, 1), False
    return round(w_mm, 1), round(h_mm, 1), True
