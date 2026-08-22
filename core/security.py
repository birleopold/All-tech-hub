"""Authentication helpers shared by every staff entry point."""

STAFF_TWO_FACTOR_SESSION_KEY = "alltech_staff_two_factor_user_id"


def mark_staff_two_factor_verified(request, user) -> None:
    """Bind a successful authenticator challenge to this exact login session."""
    request.session[STAFF_TWO_FACTOR_SESSION_KEY] = str(user.pk)


def clear_staff_two_factor_verification(request) -> None:
    request.session.pop(STAFF_TWO_FACTOR_SESSION_KEY, None)


def staff_two_factor_is_verified(request, user) -> bool:
    return request.session.get(STAFF_TWO_FACTOR_SESSION_KEY) == str(user.pk)
