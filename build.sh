#!/usr/bin/env bash
# Render's build. Free instances have no pre-deploy step, so migrations run here too; the
# icons are third-party PNGs, never committed, so every build fetches them afresh.
set -o errexit

pip install -r requirements.txt
python manage.py fetch_icons
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py check --deploy --fail-level WARNING
