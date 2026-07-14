# LEOSOFT product image enhancement and watermarks

Product and gallery images are processed automatically whenever a new file is uploaded or an existing image is replaced.

## Processing order

The public image pipeline runs in this order:

1. preserve the exact original in private storage;
2. correct EXIF orientation;
3. normalise an embedded colour profile to browser-safe sRGB when possible;
4. resize only when the image is wider than the configured maximum, preserving its aspect ratio;
5. apply tightly capped brightness and contrast correction only when the image is genuinely dark or flat;
6. apply mild sharpening;
7. add LEOSOFT branding;
8. save a high-quality JPEG, PNG or WebP public copy.

The system does **not** crop, stretch, change aspect ratio, boost saturation, remove or replace backgrounds, retouch product defects, or use generative AI. Product colours and physical condition must remain truthful.

## Conservative enhancement defaults

The default enhancement limits are intentionally mild:

- brightness gain: at most `1.06` (6%);
- contrast gain: at most `1.04` (4%);
- sharpening: `35`, with a small radius and threshold;
- saturation adjustment: none;
- maximum public width: `1800` pixels;
- smaller images are never enlarged.

Balanced images are not brightened or contrast-adjusted. Dark or flat images receive only a proportional correction up to the configured cap.

## Public watermark

Each public image receives:

- repeated semi-transparent diagonal text;
- a stronger bottom-right LEOSOFT UG LTD and `leosoftug.com` label;
- a watermark layout that reduces its font size automatically on narrow images.

The default text is:

```text
LEOSOFT UG LTD • leosoftug.com
```

A watermark discourages unauthorised reuse and keeps the brand visible, but it cannot make a browser image impossible to download or screenshot.

## Private original archive

Before enhancement or watermarking, the exact unmodified upload is copied outside the public media directory under:

```text
/home/admin/All-tech-hub/private_media/product_originals/YYYY/MM/
```

The website never links to this archive. Include `private_media` in protected server backups and do not expose it through Nginx.

## Optional environment controls

The defaults are recommended. Add these to `.env` only when adjustment is necessary:

```dotenv
ALLTECH_PRODUCT_IMAGE_WATERMARK_ENABLED=1
ALLTECH_PRODUCT_IMAGE_ENHANCEMENT_ENABLED=1
ALLTECH_PRODUCT_IMAGE_ARCHIVE_ORIGINALS=1
ALLTECH_PRODUCT_IMAGE_WATERMARK_TEXT="LEOSOFT UG LTD • leosoftug.com"
ALLTECH_PRODUCT_IMAGE_WATERMARK_OPACITY=58
ALLTECH_PRODUCT_IMAGE_WATERMARK_MAX_WIDTH=1800
ALLTECH_PRODUCT_IMAGE_MAX_BRIGHTNESS_GAIN=1.06
ALLTECH_PRODUCT_IMAGE_MAX_CONTRAST_GAIN=1.04
ALLTECH_PRODUCT_IMAGE_SHARPEN_PERCENT=35
```

Safety limits enforced by the application:

- watermark opacity: 20–150;
- maximum public width: 600–4000 pixels;
- brightness gain: 1.00–1.12;
- contrast gain: 1.00–1.10;
- sharpening: 0–80.

Restart Gunicorn after changing environment values.

## Existing unwatermarked images

Preview how many old images require first-time processing:

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a
python manage.py watermark_product_images --dry-run
```

Process a small sample first:

```bash
python manage.py watermark_product_images --limit 10
```

After checking the sample on the website, process the remainder:

```bash
python manage.py watermark_product_images
```

Images whose public filenames begin with `wm_` are skipped by this command.

## Safely update images that are already watermarked

Use the dedicated reprocessing command. It rebuilds each public copy from its archived original, so it does not layer another watermark over the existing watermark.

Preview available originals:

```bash
python manage.py reprocess_product_images --dry-run
```

Reprocess a sample of five:

```bash
python manage.py reprocess_product_images --limit 5
```

After visually checking the sample, rebuild the remaining watermarked images:

```bash
python manage.py reprocess_product_images
```

An already-watermarked image is skipped when no matching private original can be found. The current public image is not modified in that situation.

Avoid `watermark_product_images --force` for previously watermarked files. The safe command for them is `reprocess_product_images`.

## Deployment checks

```bash
python manage.py check
python manage.py test catalog.test_watermarks
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
```

After deployment, upload one test product image and confirm:

1. the public filename begins with `wm_`;
2. the image is correctly oriented and retains its original proportions;
3. real product colours and condition remain accurate;
4. the diagonal and bottom-right brand marks are visible;
5. the product page loads normally;
6. an exact original file exists under `private_media/product_originals`.
