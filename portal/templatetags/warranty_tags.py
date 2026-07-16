from django import template

from catalog.models import ProductSerial

register = template.Library()


@register.simple_tag
def customer_warranty_summary(customer):
    if not customer:
        return {"total": 0, "active": 0}
    warranties = list(ProductSerial.objects.filter(sold_to=customer).only("sold_at", "warranty_months"))
    return {
        "total": len(warranties),
        "active": sum(1 for item in warranties if item.is_under_warranty),
    }
