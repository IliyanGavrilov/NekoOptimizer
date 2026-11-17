#!/usr/bin/env bash
# Create the namespace's two Secrets with fresh random values. Run once per cluster, after
# `kubectl apply -f k8s/00-namespace.yaml`. Re-running keeps the existing values: the
# database was initialised with the first password, so a new one would lock the app out.
set -o errexit -o nounset -o pipefail
# Git Bash on Windows rewrites arguments that look like paths into Windows paths: keep it
# off the certificate subject ("/CN=..." below), but not the temp files openssl writes.
# Elsewhere this variable means nothing.
export MSYS2_ARG_CONV_EXCL="/CN="

NS=neko

if ! kubectl -n "$NS" get secret postgres >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic postgres \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi

if ! kubectl -n "$NS" get secret django >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic django \
    --from-literal=DJANGO_SECRET_KEY="$(openssl rand -base64 48)"
fi

# The Ingress's HTTPS certificate: self-signed for neko.localhost, so the browser warns
# once - fine for a local cluster (a real one would get it from cert-manager/Let's Encrypt).
if ! kubectl -n "$NS" get secret neko-tls >/dev/null 2>&1; then
  dir=$(mktemp -d)
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$dir/tls.key" -out "$dir/tls.crt" \
    -subj "/CN=neko.localhost" -addext "subjectAltName=DNS:neko.localhost"
  kubectl -n "$NS" create secret tls neko-tls --cert="$dir/tls.crt" --key="$dir/tls.key"
  rm -rf "$dir"
fi

kubectl -n "$NS" get secrets
