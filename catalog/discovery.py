"""Stable, low-cost catalogue rotation for unsorted discovery views."""

from __future__ import annotations

import re
import secrets

from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat, MD5

_SEED_PATTERN = re.compile(r"^[0-9a-f]{16}$")


def new_rotation_seed() -> str:
    return secrets.token_hex(8)


def discovery_seed_for_request(request, namespace: str) -> str:
    """Return a fresh seed for a new visit and retain it across pagination.

    A harmless seed is included in pagination links so page two cannot reshuffle
    records and repeat or omit products. Reloading the first unsorted page starts
    a new discovery order.
    """

    session_key = f"catalog_discovery_seed_{namespace}"
    supplied = (request.GET.get("view") or "").strip().lower()
    page = (request.GET.get("page") or "").strip()

    if _SEED_PATTERN.fullmatch(supplied):
        request.session[session_key] = supplied
        return supplied

    if page and _SEED_PATTERN.fullmatch(str(request.session.get(session_key, ""))):
        return request.session[session_key]

    seed = new_rotation_seed()
    request.session[session_key] = seed
    return seed


def order_for_discovery(queryset, seed: str):
    """Deterministically rotate rows without an expensive database random sort."""

    return queryset.annotate(
        _discovery_order=MD5(
            Concat(
                Cast("pk", output_field=CharField()),
                Value(f":{seed}"),
                output_field=CharField(),
            )
        )
    ).order_by("_discovery_order", "pk")
