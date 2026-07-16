from django import template
from django.utils.html import format_html, format_html_join

from catalog.responsive_images import existing_responsive_sources, source_dimensions

register = template.Library()


@register.simple_tag
def responsive_image(
    field_file,
    alt="",
    css_class="",
    sizes="100vw",
    loading="lazy",
    fetchpriority="auto",
):
    """Render a proportional responsive picture with the original as fallback."""

    if not field_file:
        return ""
    try:
        source_url = field_file.url
    except Exception:
        return ""

    sources = existing_responsive_sources(field_file)
    srcset = format_html_join(
        ", ",
        "{} {}w",
        ((url, width) for width, url in sources),
    )
    width, height = source_dimensions(field_file)
    dimension_attrs = ""
    if width and height:
        dimension_attrs = format_html(' width="{}" height="{}"', width, height)

    source = ""
    if sources:
        source = format_html(
            '<source type="image/webp" srcset="{}" sizes="{}">',
            srcset,
            sizes,
        )
    priority = fetchpriority if fetchpriority in {"high", "low", "auto"} else "auto"
    load_mode = loading if loading in {"lazy", "eager"} else "lazy"
    return format_html(
        '<picture>{}<img src="{}" alt="{}" class="{}" sizes="{}" loading="{}" decoding="async" fetchpriority="{}"{}></picture>',
        source,
        source_url,
        alt,
        css_class,
        sizes,
        load_mode,
        priority,
        dimension_attrs,
    )
