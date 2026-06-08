from commerce import cart as cart_mod


def cart_summary(request):
    return {"cart_item_count": cart_mod.cart_item_count(request.session)}
