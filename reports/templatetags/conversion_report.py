from django import template

from reports.conversion import conversion_summary as build_conversion_summary

register = template.Library()


@register.simple_tag
def conversion_summary(days=30):
    try:
        parsed_days = int(days)
    except (TypeError, ValueError):
        parsed_days = 30
    return build_conversion_summary(parsed_days)
