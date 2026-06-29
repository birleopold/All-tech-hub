from django.http import Http404
from django.shortcuts import get_object_or_404

from billing.models import CommercialDocument
from billing.pdf import pdf_response


def document_pdf_response_view(request, pk: int):
    if not request.user.is_staff:
        raise Http404

    document = get_object_or_404(
        CommercialDocument.objects.prefetch_related(
            "lines__product", "lines__product_variant"
        ),
        pk=pk,
    )
    inline = request.GET.get("inline") == "1" and request.GET.get("download") != "1"
    return pdf_response(
        document,
        inline=inline,
        copy=request.GET.get("copy") == "1",
    )
