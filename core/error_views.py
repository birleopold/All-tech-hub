from django.http import HttpResponse
from django.template import loader


def _render_error(request, *, status: int, title: str, message: str) -> HttpResponse:
    template = loader.get_template("errors/error.html")
    body = template.render(
        {
            "status_code": status,
            "title": title,
            "message": message,
            "request_id": getattr(request, "request_id", ""),
        }
    )
    response = HttpResponse(body, status=status)
    response["Cache-Control"] = "no-store, max-age=0"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def bad_request(request, exception=None):
    return _render_error(
        request,
        status=400,
        title="We could not process that request",
        message="Check the information and try again. No order or payment should be assumed from this page.",
    )


def permission_denied(request, exception=None):
    return _render_error(
        request,
        status=403,
        title="This page is not available to this account",
        message="Sign in with the correct account or return to the public website.",
    )


def page_not_found(request, exception=None):
    return _render_error(
        request,
        status=404,
        title="We could not find that page",
        message="The link may have changed, the product may no longer be published, or the address may be incomplete.",
    )


def server_error(request):
    return _render_error(
        request,
        status=500,
        title="Something went wrong on our side",
        message="Please try again shortly. When contacting support, include the reference shown below.",
    )
