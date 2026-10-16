#!/usr/bin/env bash
# Vercel's build command. It runs after the dependencies install and before Vercel's own
# collectstatic, so the icons - third-party PNGs, never committed - land in that collection.
set -o errexit

python manage.py fetch_icons
# Only the production build touches the live database: a preview never migrates it early.
if [ "$VERCEL_ENV" = production ]; then
  python manage.py migrate --no-input
fi
# Warnings only; CI enforces the deploy checks at WARNING level.
python manage.py check --deploy
