from django import template

from commerce.recommendations import recommended_products_for_order

register = template.Library()


@register.simple_tag
def order_recommendations(order, limit=4):
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 4
    return recommended_products_for_order(order, limit=parsed_limit)
