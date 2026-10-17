from django.db.models import Q
from django.views.generic import ListView

from catalog.models import Category, Product
from catalog.stock_alerts import low_stock_products
from core.mixins import StaffRequiredMixin


class ProductManageListView(StaffRequiredMixin, ListView):
    """Paginated staff catalogue with stable, allow-listed filters and ordering."""

    template_name = "inventory/product_list.html"
    context_object_name = "products"
    paginate_by = 25

    SORT_OPTIONS = (
        ("category", "Category (A–Z)"),
        ("category_desc", "Category (Z–A)"),
        ("name", "Product name (A–Z)"),
        ("name_desc", "Product name (Z–A)"),
        ("price", "Price (low to high)"),
        ("price_desc", "Price (high to low)"),
        ("newest", "Newest first"),
        ("oldest", "Oldest first"),
    )

    SORT_FIELDS = {
        "category": ("category__sort_order", "category__name", "name", "pk"),
        "category_desc": ("-category__sort_order", "-category__name", "name", "pk"),
        "name": ("name", "pk"),
        "name_desc": ("-name", "pk"),
        "price": ("price", "name", "pk"),
        "price_desc": ("-price", "name", "pk"),
        "newest": ("-created_at", "-pk"),
        "oldest": ("created_at", "pk"),
    }

    def get_queryset(self):
        query = (self.request.GET.get("q") or "").strip()
        category_slug = (self.request.GET.get("category") or "").strip()
        selected_sort = self.request.GET.get("sort") or "category"
        ordering = self.SORT_FIELDS.get(selected_sort, self.SORT_FIELDS["category"])

        queryset = Product.objects.select_related("category", "category__parent").prefetch_related(
            "variants"
        )
        kind = (self.request.GET.get("kind") or "").strip()
        if kind in {Product.KIND_PHYSICAL, Product.KIND_SERVICE}:
            queryset = queryset.filter(kind=kind)
        publication = (self.request.GET.get("published") or "").strip()
        if publication == "1":
            queryset = queryset.filter(is_published=True)
        elif publication == "0":
            queryset = queryset.filter(is_published=False)

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(sku__icontains=query)
                | Q(category__name__icontains=query)
                | Q(category__parent__name__icontains=query)
                | Q(variants__sku__icontains=query)
                | Q(growth_data__brand__icontains=query)
                | Q(growth_data__mpn__icontains=query)
            ).distinct()

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        if self.request.GET.get("low") == "1":
            low_ids = [product.pk for product in low_stock_products(limit=None)]
            queryset = queryset.filter(pk__in=low_ids) if low_ids else queryset.none()

        return queryset.order_by(*ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_sort = self.request.GET.get("sort") or "category"
        if selected_sort not in self.SORT_FIELDS:
            selected_sort = "category"

        query_params = self.request.GET.copy()
        query_params.pop("page", None)

        context.update(
            {
                "q": (self.request.GET.get("q") or "").strip(),
                "categories": Category.objects.select_related("parent")
                .filter(products__isnull=False)
                .distinct()
                .order_by("sort_order", "name"),
                "selected_category": (self.request.GET.get("category") or "").strip(),
                "selected_sort": selected_sort,
                "sort_options": self.SORT_OPTIONS,
                "low_only": self.request.GET.get("low") == "1",
                "selected_kind": (self.request.GET.get("kind") or "").strip(),
                "selected_publication": (self.request.GET.get("published") or "").strip(),
                "querystring": query_params.urlencode(),
            }
        )
        return context
