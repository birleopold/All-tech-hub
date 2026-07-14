# LEOSOFT product image watermarks

Product and gallery images are now watermarked automatically when a new file is uploaded or an existing image is replaced.

## Public watermark

Each public image receives:

- repeated semi-transparent diagonal text;
- a stronger bottom-right LEOSOFT UG LTD and `leosoftug.com` label;
- EXIF orientation correction;
- a public-size limit to reduce reuse of unnecessarily large originals.

The default text is:

```text
LEOSOFT UG LTD • leosoftug.com
```

A watermark discourages unauthorised reuse and keeps the brand visible, but it cannot make a browser image impossible to download or screenshot.

## Private original archive

Before watermarking, the unmodified upload is copied outside the public media directory under:

```text
/home/admin/All-tech-hub/private_media/product_originals/YYYY/MM/
```

The website never links to this archive. Include `private_media` in protected server backups and do not expose it through Nginx.

## Optional environment controls

Add these only when the defaults need changing:

```dotenv
ALLTECH_PRODUCT_IMAGE_WATERMARK_ENABLED=1
ALLTECH_PRODUCT_IMAGE_ARCHIVE_ORIGINALS=1
ALLTECH_PRODUCT_IMAGE_WATERMARK_TEXT="LEOSOFT UG LTD • leosoftug.com"
ALLTECH_PRODUCT_IMAGE_WATERMARK_OPACITY=58
ALLTECH_PRODUCT_IMAGE_WATERMARK_MAX_WIDTH=1800
```

- Opacity is clamped between 20 and 150.
- Maximum public width is clamped between 600 and 4000 pixels.
- Images smaller than the maximum are not enlarged.
- JPEG, PNG and WebP output are supported.

Restart Gunicorn after changing environment values.

## Existing product images

Preview the number of existing images that require watermarking:

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a
python manage.py watermark_product_images --dry-run
```

Apply the watermark:

```bash
python manage.py watermark_product_images
```

Process only a small batch first:

```bash
python manage.py watermark_product_images --limit 10
```

Images whose public filenames begin with `wm_` are skipped. `--force` reprocesses them and should normally be avoided because it layers a new watermark over the current public copy.

## Deployment checks

```bash
python manage.py check
python manage.py test catalog.test_watermarks
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
```

After deployment, upload one test product image and confirm:

1. the public filename begins with `wm_`;
2. the diagonal and bottom-right brand marks are visible;
3. the product page still loads normally;
4. an original file was created under `private_media/product_originals`.
