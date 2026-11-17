# syntax=docker/dockerfile:1
# Neko Optimizer's image: Django served by gunicorn, its static files (CSS, JS, neko.wasm,
# the cat icons) collected and precompressed for whitenoise. Two stages: "build" has the
# tools and the network to assemble everything; "runtime" receives only the result.

ARG PYTHON=3.14

# ---- build: dependencies, icons, static files ------------------------------------------
FROM python:${PYTHON}-slim AS build

# A virtualenv is one folder to hand over to the runtime stage whole.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# Requirements first, on their own layer: code changes then reuse the cached install.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Settings demand production values with DEBUG off; these exist only for the build steps
# below and never reach the runtime stage. Building with DEBUG off is what makes
# collectstatic write whitenoise's hashed, compressed manifest.
ENV DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=build-only-not-secret \
    DATABASE_URL=sqlite:////tmp/build.sqlite3
# The cat and material icons are third-party PNGs, never committed: fetch them, collect
# everything under staticfiles/, then drop the source copies the runtime never reads.
RUN python manage.py fetch_icons \
    && python manage.py collectstatic --no-input \
    && rm -rf planner/static/planner/icons

# ---- runtime: just Python, the venv and the app -----------------------------------------
FROM python:${PYTHON}-slim AS runtime

# An unprivileged user to run as: nothing in the container needs root.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin neko

# PYTHONUNBUFFERED: logs go straight to stdout/stderr, where `kubectl logs` reads them.
# PYTHONDONTWRITEBYTECODE: the root filesystem is read-only in the cluster, so no .pyc.
# NEKO_*_BASE: the icons now live only in the collected static files; point pages there.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_DEBUG=0 \
    NEKO_ICON_BASE=/static/planner/icons/u \
    NEKO_ITEM_BASE=/static/planner/icons/r

COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=root:root /app /app
WORKDIR /app

USER 10001
EXPOSE 8000

# 2 worker processes x 4 threads each. Logs to stdout. --worker-tmp-dir in RAM, since
# the root filesystem is read-only. Workers that hang 30s are replaced.
CMD ["gunicorn", "nekosite.wsgi", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "4", \
     "--worker-tmp-dir", "/dev/shm", \
     "--timeout", "30", \
     "--access-logfile", "-"]
