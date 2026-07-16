from django import template

from commerce.progress import order_progress

register = template.Library()


@register.simple_tag
def order_progress_data(order):
    return order_progress(order)
