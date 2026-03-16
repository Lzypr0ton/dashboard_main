To replicate these UI changes on another system:

1) Copy the updated templates and logo file into the same relative paths:
- `dashboard/templates/dashboard/base.html`
- `dashboard/templates/dashboard/home.html`
- `static/img/tata-logo.svg` (new file)

2) Ensure Django static files are collected (if you use `collectstatic` in that environment) so the logo is served:
- `python manage.py collectstatic --noinput` (only if the environment expects collected static files).

3) Run the app as usual:
- Activate venv (`.\venv\Scripts\activate`)
- `python manage.py runserver 0.0.0.0:8000`

No other files were changed.
