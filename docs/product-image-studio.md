# Product image studio

ALLTECH Hub can optionally turn raw product uploads into consistent marketplace images before the existing enhancement, watermark and responsive-WebP stages run.

## Pipeline order

1. Preserve the true uploaded original in `PRIVATE_MEDIA_ROOT/product_originals/`.
2. Correct phone-camera EXIF orientation and cap the AI input size.
3. Remove the background with the configured `rembg` model.
4. Refine the alpha edge without premultiplying the product colours.
5. Crop and centre the product on the configured catalogue canvas.
6. Apply the selected background style and a restrained contact shadow.
7. Continue through the existing conservative enhancement, watermark and responsive derivative pipeline.

The studio is fail-open. If the optional runtime, model or segmentation step fails, the normal image upload pipeline receives the original image.

## Why the implementation differs from the prototype

- OpenCV and direct scikit-image usage are unnecessary for compositing and canvas work; Pillow handles those stages with fewer production dependencies.
- Histogram matching is intentionally excluded because it can change the visible colour of products and accessories.
- Transparent images use straight RGBA alpha compositing, avoiding dark or doubled edge halos.
- The AI session is lazy, shared inside each worker process and configurable.
- The model is warmed before enabling the feature, so the first staff upload does not trigger an uncontrolled download.
- Existing originals remain compatible with `reprocess_product_images`.

## Installation on the production server

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
source .venv/bin/activate
pip install -r requirements-image-studio.txt
mkdir -p /home/admin/All-tech-hub/.models/rembg
```

Add these values to the protected production `.env` file:

```dotenv
U2NET_HOME=/home/admin/All-tech-hub/.models/rembg
OMP_NUM_THREADS=1
ALLTECH_PRODUCT_IMAGE_STUDIO_ENABLED=1
ALLTECH_PRODUCT_IMAGE_STUDIO_STYLE=clean_studio
ALLTECH_PRODUCT_IMAGE_STUDIO_MODEL=isnet-general-use
ALLTECH_PRODUCT_IMAGE_STUDIO_CANVAS_WIDTH=1600
ALLTECH_PRODUCT_IMAGE_STUDIO_CANVAS_HEIGHT=1600
ALLTECH_PRODUCT_IMAGE_STUDIO_PADDING=0.12
ALLTECH_PRODUCT_IMAGE_STUDIO_BASE_COLOR=#f6f6f8
ALLTECH_PRODUCT_IMAGE_STUDIO_MAX_INPUT_DIMENSION=2400
ALLTECH_PRODUCT_IMAGE_STUDIO_SHADOW_OPACITY=0.22
```

Load the environment and download/initialise the model before restarting the web application:

```bash
set -a
source .env
set +a
python manage.py warm_product_studio_model
python manage.py check
python manage.py test catalog.test_product_studio catalog.test_watermarks
python manage.py reprocess_product_images --dry-run
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
```

After reviewing the dry-run count, existing public product images can be rebuilt safely from their private originals:

```bash
python manage.py reprocess_product_images --limit 10
```

Review those ten products first. Then run the command without `--limit` when the output is approved.

## Styles

- `clean_studio`: off-white vertical studio gradient and a restrained contact shadow. Recommended for the shop catalogue.
- `transparent`: transparent square PNG for design reuse and marketplace exports.
- `cinematic_blur`: blurred and darkened version of the original scene behind the isolated product.
- `preserve`: bypass the studio stage while leaving the existing image pipeline active.

## Operational notes

- The feature is disabled by default in code. Enable it only after the optional requirements and model are installed.
- Keep `OMP_NUM_THREADS` low on the current CPU server because Gunicorn runs multiple workers.
- Do not expose the model directory or `private_media` through the public web server.
- New uploads are processed synchronously. Monitor upload latency and memory before increasing canvas size or choosing a heavier model.
