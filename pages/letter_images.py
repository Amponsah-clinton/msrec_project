"""Header / footer images for the approval letter (Site Settings > Approval
Documents > Letterhead).

An admin uploads a scan or export of their letterhead artwork -- any size,
PNG / JPG / WEBP. It is normalised here into one clean image that the PDF
renderer can place on an A4 page without further thought:

  * orientation fixed (phone photos carry EXIF rotation),
  * transparency kept (a PNG logo strip with no background stays that way),
  * an empty white/transparent margin trimmed off, so the artwork itself
    sits flush to the page edge instead of floating inside a blank canvas,
  * scaled down to a print-sharp maximum (2480 px wide = 300 dpi at A4),
    never up -- a small image is placed at its natural size, not blurred,
  * re-encoded as PNG (line art, logos) or high-quality JPEG (photographic).

Raises ValueError with a message an admin can act on.
"""
from io import BytesIO

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

MAX_INPUT_PIXELS = 40_000_000
MAX_WIDTH = 2480          # 210 mm at 300 dpi
MIN_WIDTH = 300
JPEG_QUALITY = 90
KIND_LABEL = {"header": "header", "footer": "footer"}


def _trim_margin(image):
    """Crops the blank white / transparent border around the artwork (with
    a hairline of padding). Transparency is composited onto white first, so
    a transparent margin and a white margin are both treated as blank."""
    if image.mode == "RGBA":
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
    else:
        flat = image
    diff = ImageChops.difference(flat, Image.new("RGB", image.size, (255, 255, 255))).convert("L")
    box = diff.point(lambda v: 255 if v > 12 else 0).getbbox()
    if box is None:
        return image
    pad = 2
    return image.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                       min(image.width, box[2] + pad), min(image.height, box[3] + pad)))


def process_letter_image(raw_bytes, kind="header"):
    """Returns (image_bytes, ext, width, height). `ext` is "png" or "jpg"."""
    label = KIND_LABEL.get(kind, "image")
    try:
        image = Image.open(BytesIO(raw_bytes))
        if image.width * image.height > MAX_INPUT_PIXELS:
            raise ValueError(f"That {label} image is too large -- please use one under about 40 megapixels.")
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError(f"That file isn't a readable image -- upload a PNG, JPG or WEBP for the {label}.")

    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")
    image = _trim_margin(image)

    if image.width < MIN_WIDTH:
        raise ValueError(
            f"That {label} image is only {image.width}px wide -- use at least {MIN_WIDTH}px "
            f"(about 2480px for a sharp full-width print)."
        )
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.LANCZOS)

    out = BytesIO()
    if image.mode == "RGBA" or _is_flat_art(image):
        image.save(out, format="PNG", optimize=True)
        ext = "png"
    else:
        image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        ext = "jpg"
    return out.getvalue(), ext, image.width, image.height


def _is_flat_art(image):
    """Few distinct colours = logo / line art (PNG stays crisp and small);
    many = a photograph (JPEG is far smaller)."""
    sample = image.copy()
    sample.thumbnail((200, 200))
    return sample.getcolors(maxcolors=1024) is not None
