# UI refresh file placement

The reviewed corrections from `files.zip` and `files2.zip` are installed as follows:

| Source file | Project destination | Integration |
| --- | --- | --- |
| staff_refresh.css | static/css/staff_refresh.css | Loaded after staff_workspace.css in templates/staff_base.html |
| staff_refresh.js | static/js/staff_refresh.js | Loaded once, deferred, by templates/staff_base.html |
| staff_base.html | templates/staff_base.html | Merged stylesheet, search shortcut hint and script references |
| storefront_refresh.css | static/css/storefront_refresh.css | Loaded last in templates/base.html, only when public navigation is enabled |
| storefront.patch | templates/base.html and templates/catalog/_marketplace_catalog_body.html | Merged stylesheet reference and changed nested main landmark to section |

The nested ZIPs contain the same assets as the loose files. Do not install both
copies or copy the wrapper folders into the project. Patch files are change
instructions, not runtime assets; their changes have already been applied.

## Editing and maintenance

Edit templates in `templates/`, CSS in `static/css/`, and JavaScript in
`static/js/`. `staticfiles/` is generated deployment output; do not edit it by
hand. The existing CSS files still supply layouts and components: these refresh
files are intentionally ordered overrides, not complete replacements.

Staff changes remain scoped to `.staff-workspace-body`. Public changes load
only on public-facing pages. Preserve the existing CSS order and each staff
child template's `{{ block.super }}` when extending `extra_css`.

The staff script ignores typing fields, composing input, handled key events and
hidden search controls. Invalid or unavailable storage is tolerated. Revealing
the current navigation item scrolls only the sidebar, not the document.

## Local verification

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test core.test_critical_template_compilation core.test_staff_ui_completion core.test_storefront_polish core.test_mobile_commerce_pro core.test_desktop_commerce_pro --noinput
node --check static/js/staff_refresh.js
```

During deployment, run `python manage.py collectstatic --noinput` in the target
environment using its deployment settings. No database migration is needed for
these UI changes. Check public catalogue/product pages and staff list/form pages
at desktop and phone widths before publishing.
