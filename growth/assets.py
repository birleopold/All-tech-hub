from io import BytesIO
from textwrap import wrap

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from django.http import HttpResponse

from core.models import CompanySettings
from growth.services import absolute_public_url


FORMATS = {
    "square": (1080, 1080),
    "story": (1080, 1920),
}


def _font(size: int, bold: bool = False):
    names = (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _open_image(field, size):
    if not field:
        return None
    try:
        field.open("rb")
        image = Image.open(field).convert("RGB")
        return ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    except Exception:
        return None
    finally:
        try:
            field.close()
        except Exception:
            pass


def _draw_wrapped(draw, text, xy, width_chars, font, fill, spacing=10):
    x, y = xy
    lines = []
    for paragraph in str(text or "").splitlines() or [""]:
        lines.extend(wrap(paragraph, width=width_chars) or [""])
    draw.multiline_text((x, y), "\n".join(lines), font=font, fill=fill, spacing=spacing)
    bbox = draw.multiline_textbbox(
        (x, y), "\n".join(lines), font=font, spacing=spacing
    )
    return bbox[3]


def product_marketing_image(product, format_name: str) -> bytes:
    if format_name not in FORMATS:
        raise ValueError("Unsupported marketing image format")
    width, height = FORMATS[format_name]
    company = CompanySettings.load()
    navy = (11, 31, 51)
    blue = (31, 111, 235)
    white = (255, 255, 255)
    light = (238, 244, 250)
    muted = (90, 105, 120)

    canvas = Image.new("RGB", (width, height), light)
    draw = ImageDraw.Draw(canvas)
    header_height = 170 if format_name == "square" else 220
    draw.rectangle((0, 0, width, header_height), fill=navy)
    draw.text(
        (60, 48 if format_name == "square" else 70),
        company.legal_name or company.company_name,
        font=_font(44 if format_name == "square" else 50, bold=True),
        fill=white,
    )

    product_image = _open_image(
        product.primary_display_image,
        (width - 120, 470 if format_name == "square" else 850),
    )
    image_top = header_height + 35
    image_area_height = 500 if format_name == "square" else 900
    draw.rounded_rectangle(
        (50, image_top, width - 50, image_top + image_area_height),
        radius=28,
        fill=white,
    )
    if product_image:
        x = (width - product_image.width) // 2
        y = image_top + (image_area_height - product_image.height) // 2
        canvas.paste(product_image, (x, y))
    else:
        draw.text(
            (width // 2, image_top + image_area_height // 2),
            "PRODUCT IMAGE",
            font=_font(36, bold=True),
            fill=muted,
            anchor="mm",
        )

    content_top = image_top + image_area_height + 30
    title_size = 52 if format_name == "square" else 64
    title_bottom = _draw_wrapped(
        draw,
        product.name,
        (60, content_top),
        29 if format_name == "square" else 25,
        _font(title_size, bold=True),
        navy,
        8,
    )
    price = product.min_active_variant_price or product.price
    price_y = title_bottom + 22
    draw.text(
        (60, price_y),
        f"{company.currency_code} {price}",
        font=_font(48 if format_name == "square" else 58, bold=True),
        fill=blue,
    )
    status = "AVAILABLE NOW" if product.available_to_sell else "ASK FOR AVAILABILITY"
    draw.text(
        (60, price_y + 70),
        status,
        font=_font(27 if format_name == "square" else 34, bold=True),
        fill=navy,
    )

    product_url = absolute_public_url(product.get_absolute_url())
    qr = qrcode.make(product_url).convert("RGB")
    qr_size = 155 if format_name == "square" else 200
    qr = qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    qr_x = width - qr_size - 55
    qr_y = height - qr_size - 45
    canvas.paste(qr, (qr_x, qr_y))
    draw.text(
        (60, height - 92),
        "Scan to view or order",
        font=_font(28 if format_name == "square" else 34, bold=True),
        fill=navy,
    )
    draw.text(
        (60, height - 52),
        "leosoftug.com",
        font=_font(25 if format_name == "square" else 30),
        fill=muted,
    )

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def marketing_image_response(product, format_name: str) -> HttpResponse:
    content = product_marketing_image(product, format_name)
    response = HttpResponse(content, content_type="image/png")
    response["Content-Disposition"] = (
        f'attachment; filename="leosoft-{product.slug}-{format_name}.png"'
    )
    return response
