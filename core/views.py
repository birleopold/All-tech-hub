from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from core.forms import ContactForm


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        from catalog.models import Product

        ctx = super().get_context_data(**kwargs)
        ctx["featured_products"] = (
            Product.objects.filter(is_published=True, is_featured=True)
            .select_related("category")
            .prefetch_related("gallery_images", "variants")[:8]
        )
        ctx["featured_services"] = Product.objects.filter(
            is_published=True, kind=Product.KIND_SERVICE, is_featured=True
        ).select_related("category")[:6]
        return ctx


class AboutView(TemplateView):
    template_name = "core/about.html"


def contact_view(request):
    from core.models import hours_summary, is_open_now

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks — we will get back to you shortly.")
            return redirect("contact")
    else:
        form = ContactForm()
    return render(
        request,
        "core/contact.html",
        {
            "form": form,
            "business_hours": hours_summary(),
            "is_open_now": is_open_now(),
        },
    )
