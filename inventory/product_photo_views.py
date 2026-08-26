import base64
from io import BytesIO

import qrcode
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from catalog.models import Product, ProductImage
from inventory.product_photo_models import ProductPhotoSession, StaffPushSubscription
from inventory.product_photo_push import send_product_photo_push

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_PHOTOS_PER_REQUEST = 12
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def _staff_only(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        raise Http404


def _owned_session(request, token):
    _staff_only(request)
    session = get_object_or_404(
        ProductPhotoSession.objects.select_related("product", "owner"),
        token=token,
        owner=request.user,
    )
    if not session.is_open:
        raise Http404
    return session


@login_required
@require_POST
def start_product_photo_session(request, product_id):
    _staff_only(request)
    product = get_object_or_404(Product, pk=product_id)
    ProductPhotoSession.objects.filter(
        product=product, owner=request.user, closed_at__isnull=True
    ).update(closed_at=timezone.now())
    session = ProductPhotoSession.objects.create(product=product, owner=request.user)
    mobile_path = reverse("staff_product_photo_mobile", kwargs={"token": session.token})
    mobile_url = request.build_absolute_uri(mobile_path)
    sent = send_product_photo_push(
        request.user,
        title="Add product photos",
        body=f"Take or choose photos for {product.name}.",
        url=mobile_url,
    )
    return JsonResponse(
        {
            "url": mobile_url,
            "status_url": reverse(
                "staff_product_photo_status", kwargs={"token": session.token}
            ),
            "qr_url": reverse("staff_product_photo_qr", kwargs={"token": session.token}),
            "push_sent": sent,
            "expires_at": session.expires_at.isoformat(),
        }
    )


@login_required
@require_GET
def product_photo_mobile(request, token):
    session = _owned_session(request, token)
    return render(
        request,
        "inventory/product_photo_mobile.html",
        {"photo_session": session, "product": session.product},
    )


@login_required
@require_POST
def product_photo_upload(request, token):
    session = _owned_session(request, token)
    files = request.FILES.getlist("photos")
    if not files:
        return JsonResponse({"error": "Choose at least one photo."}, status=400)
    if len(files) > MAX_PHOTOS_PER_REQUEST:
        return JsonResponse(
            {"error": f"Upload no more than {MAX_PHOTOS_PER_REQUEST} photos at once."},
            status=400,
        )

    # Validate the entire batch before persisting anything, so one bad file
    # cannot leave a partial gallery behind.
    for upload in files:
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            return JsonResponse({"error": f"{upload.name} is not a supported image."}, status=400)
        if upload.size > MAX_PHOTO_BYTES:
            return JsonResponse({"error": f"{upload.name} is larger than 12 MB."}, status=400)
        try:
            width, height = get_image_dimensions(upload)
        except (TypeError, ValueError, ValidationError):
            return JsonResponse({"error": f"{upload.name} is not a valid image."}, status=400)
        if not width or not height:
            return JsonResponse({"error": f"{upload.name} is not a valid image."}, status=400)
        upload.seek(0)

    created = []
    next_sort = (
        ProductImage.objects.filter(product=session.product)
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
        or 0
    )
    for upload in files:
        next_sort += 10
        image = ProductImage.objects.create(
            product=session.product,
            image=upload,
            sort_order=next_sort,
            alt_text=session.product.name,
        )
        created.append({"id": image.pk, "url": image.image.url, "name": upload.name})

    session.last_upload_at = timezone.now()
    session.save(update_fields=["last_upload_at"])
    return JsonResponse({"uploaded": created, "count": len(created)})


@login_required
@require_GET
def product_photo_status(request, token):
    session = _owned_session(request, token)
    images = [
        {"id": image.pk, "url": image.image.url, "alt_text": image.alt_text}
        for image in session.product.gallery_images.order_by("sort_order", "id")
        if image.image
    ]
    return JsonResponse(
        {
            "images": images,
            "count": len(images),
            "last_upload_at": (
                session.last_upload_at.isoformat() if session.last_upload_at else None
            ),
        }
    )


@login_required
@require_GET
def product_photo_qr(request, token):
    session = _owned_session(request, token)
    url = request.build_absolute_uri(
        reverse("staff_product_photo_mobile", kwargs={"token": session.token})
    )
    image = qrcode.make(url)
    output = BytesIO()
    image.save(output, format="PNG")
    return JsonResponse({"image": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()})


@login_required
@require_GET
def push_public_key(request):
    _staff_only(request)
    return JsonResponse({"public_key": getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")})


@login_required
@require_POST
def save_push_subscription(request):
    _staff_only(request)
    try:
        import json
        data = json.loads(request.body)
        endpoint = data["endpoint"]
        keys = data["keys"]
        p256dh = keys["p256dh"]
        auth = keys["auth"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid push subscription."}, status=400)
    StaffPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.headers.get("User-Agent", "")[:500],
        },
    )
    return JsonResponse({"ok": True})
