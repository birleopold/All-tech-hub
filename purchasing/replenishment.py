"""Small, deterministic purchasing policy shared by the staff workspace."""

from math import ceil


def suggested_reorder_quantity(*, on_hand, reorder_level, recent_sales, recent_enquiries, pending_inbound):
    on_hand = max(0, int(on_hand or 0))
    reorder_level = max(0, int(reorder_level or 0))
    recent_sales = max(0, int(recent_sales or 0))
    recent_enquiries = max(0, int(recent_enquiries or 0))
    pending_inbound = max(0, int(pending_inbound or 0))
    target = max(reorder_level * 2, ceil(recent_sales * 1.25), recent_enquiries)
    return max(0, target - on_hand - pending_inbound)
