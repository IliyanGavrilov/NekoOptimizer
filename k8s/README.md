# Neko Optimizer on Kubernetes

The site runs publicly on Vercel + Neon. This folder runs the **same code** a second way:
as a Docker image on a Kubernetes cluster (minikube on your machine), with its own
Postgres. Nothing here changes the public site.

```
            browser  https://neko.localhost
               │
     ┌─────────▼──────────┐   namespace ingress-nginx
     │  ingress-nginx     │   terminates HTTPS (Secret neko-tls)
     └─────────┬──────────┘
───────────────┼──────────────────────────── namespace neko ─────────────
     ┌─────────▼──────────┐
     │ Service neko-web   │   stable name + virtual IP, port 80 → 8000
     └──┬──────────────┬──┘
   ┌────▼────┐    ┌────▼────┐   Deployment neko-web (2-5 pods, HPA on CPU)
   │ web pod │    │ web pod │   init: wait-for-db → main: gunicorn + Django
   └────┬────┘    └────┬────┘
        └──────┬───────┘          Job setup:  wait-for-db → migrate → import data
     ┌─────────▼──────────┐       CronJob prune-guests: weekly cleanup
     │ Service postgres   │   headless: DNS name → the pod directly
     └─────────┬──────────┘
     ┌─────────▼──────────┐   StatefulSet postgres (1 pod, postgres-0)
     │ postgres-0         │──── PersistentVolumeClaim data-postgres-0 (1Gi)
     └────────────────────┘
ConfigMap neko-config · Secrets postgres, django, neko-tls · NetworkPolicies (deny by default)
```

## What's where

| Path | What it is |
|---|---|
| `Dockerfile`, `.dockerignore` | How the image is built (two stages) |
| `planner/health.py` | `/livez` and `/readyz`, the endpoints Kubernetes probes |
| `k8s/00-namespace.yaml` | Namespace `neko`, LimitRange, ResourceQuota |
| `k8s/10-config.yaml` | ConfigMap: the non-secret settings |
| `k8s/scripts/secrets.sh` | Creates the Secrets (DB password, Django key, TLS cert) with random values |
| `k8s/examples/secrets.yaml` | What those Secrets look like (never applied) |
| `k8s/20-postgres.yaml` | Postgres: headless Service + StatefulSet + volume |
| `k8s/30-setup-job.yaml` | Job: migrate the schema, import the game data |
| `k8s/40-web.yaml` | ServiceAccount, Deployment, Service, HPA, PodDisruptionBudget |
| `k8s/50-ingress.yaml` | Ingress: https://neko.localhost → the web Service |
| `k8s/60-network-policies.yaml` | Who may talk to whom |
| `k8s/70-cronjobs.yaml` | CronJob: weekly `prune_guests` |
| `k8s/helm/neko-optimizer/` | All of the above as one Helm chart |
| `.github/workflows/image.yml` | CI: build the image on every PR, push to ghcr.io from main |

## One-time setup (Windows)

Install the tools (PowerShell). Docker Desktop needs WSL2 and a reboot the first time:

```bash
winget install -e --id Docker.DockerDesktop
```
```bash
winget install -e --id Kubernetes.minikube
```
```bash
winget install -e --id Kubernetes.kubectl
```
```bash
winget install -e --id Helm.Helm
```

Docker Desktop has to show **Engine running**. If it reports "Windows hypervisor is not
running", Windows' boot setting `hypervisorlaunchtype` is Off. In an administrator
PowerShell, run `bcdedit /set hypervisorlaunchtype auto`, then use **Restart**. Shut down
doesn't count: Fast startup skips the boot settings.

Then create the cluster. `--cni=calico` swaps in a network plugin that **enforces**
NetworkPolicies (the default one ignores them). `--memory` must fit inside what Docker
may use: `docker info` shows it, about half the machine's RAM under WSL2.

```bash
minikube start --driver=docker --cni=calico --cpus=4 --memory=3400
```
```bash
minikube addons enable ingress
```
```bash
minikube addons enable metrics-server
```

## Run it (plain manifests)

From the repo root, in Git Bash:

```bash
minikube image build -t neko-optimizer:local .
```
```bash
kubectl apply -f k8s/00-namespace.yaml
```
```bash
bash k8s/scripts/secrets.sh
```
```bash
kubectl apply -f k8s/
```
```bash
kubectl -n neko get pods -w
```

What you'll see: `postgres-0` starts; the `setup-…` pod runs `wait-for-db` → `migrate` →
`import` (a few minutes) and ends `Completed`; the two `neko-web-…` pods are `Running`
but `0/1` Ready until the migration is done, then `1/1`.

To reach it, run this in a **separate** terminal and leave it open (it may ask for admin
rights, to listen on ports 80/443):

```bash
minikube tunnel
```

Open **https://neko.localhost**. The certificate is self-signed, so accept the warning once.

No admin rights? Forward one port to the ingress controller instead, then open
**https://neko.localhost:8443**:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8443:443
```

Run `secrets.sh` from **Git Bash**. In PowerShell, `bash` starts WSL's bash, which has no
Linux installed here.

## Run it (Helm) - instead of the above, not alongside it

```bash
helm upgrade --install neko k8s/helm/neko-optimizer --namespace neko-helm --create-namespace
```

The chart creates the Secrets and certificate itself and runs a fresh setup Job on every
upgrade. See what it would create without installing anything:

```bash
helm template neko k8s/helm/neko-optimizer
```

Change a setting:

```bash
helm upgrade neko k8s/helm/neko-optimizer -n neko-helm --set web.autoscaling.maxReplicas=8
```

Undo the last change:

```bash
helm rollback neko -n neko-helm
```

## Things to try

**Self-healing.** Delete a web pod: the Deployment notices it's one short and starts a new one.
```bash
kubectl -n neko delete pod -l app.kubernetes.io/component=web --wait=false
```
```bash
kubectl -n neko get pods -w
```

**Rolling update + rollback.** Change the pod template, watch pods replaced one at a time
(maxSurge 1, maxUnavailable 0), then go back.
```bash
kubectl -n neko set env deployment/neko-web DEMO=1
```
```bash
kubectl -n neko rollout status deployment/neko-web
```
```bash
kubectl -n neko rollout history deployment/neko-web
```
```bash
kubectl -n neko rollout undo deployment/neko-web
```

**Probes.** Readiness is what the Service uses to pick pods.
```bash
kubectl -n neko describe pod -l app.kubernetes.io/component=web
```
```bash
kubectl -n neko get endpointslices -l kubernetes.io/service-name=neko-web
```

**Logs, metrics, events.**
```bash
kubectl -n neko logs deploy/neko-web --tail=20
```
```bash
kubectl -n neko logs job/setup -c migrate
```
```bash
kubectl -n neko top pods
```
```bash
kubectl -n neko get events --sort-by=.lastTimestamp
```

**Autoscaling.** The HPA watches CPU against the 100m request.
```bash
kubectl -n neko get hpa -w
```

**Persistence.** Delete the database pod; the StatefulSet recreates `postgres-0`, it
re-attaches the same volume, and nothing is lost.
```bash
kubectl -n neko delete pod postgres-0
```
```bash
kubectl -n neko get pvc
```

**CronJob.** Run the weekly job now instead of waiting for Monday.
```bash
kubectl -n neko create job prune-now --from=cronjob/prune-guests
```
```bash
kubectl -n neko logs job/prune-now
```

**NetworkPolicy.** A pod without the `db-access` label can't reach Postgres (times out);
the same pod with the label can.
```bash
kubectl -n neko run probe --rm -it --image=postgres:17-alpine --restart=Never -- pg_isready -h postgres -U neko -t 5
```
```bash
kubectl -n neko run probe --rm -it --image=postgres:17-alpine --restart=Never --labels=neko-optimizer/db-access=true -- pg_isready -h postgres -U neko -t 5
```

**Secrets are only encoded.**
```bash
kubectl -n neko get secret postgres -o jsonpath='{.data.POSTGRES_PASSWORD}'
```

**Configuration.** Every setting arrives as an environment variable.
```bash
kubectl -n neko exec deploy/neko-web -- env
```

**Security context.** The container runs as uid 10001, can't write its filesystem.
```bash
kubectl -n neko exec deploy/neko-web -- id
```
```bash
kubectl -n neko exec deploy/neko-web -- touch /app/x
```

## New code

```bash
minikube image build -t neko-optimizer:local .
```
```bash
kubectl -n neko delete job setup --ignore-not-found
```
```bash
kubectl apply -f k8s/30-setup-job.yaml
```
```bash
kubectl -n neko rollout restart deployment/neko-web
```

## Clean up

```bash
kubectl delete namespace neko
```
```bash
minikube delete
```

`kubectl delete namespace` removes everything in it, including the database volume.
`minikube delete` removes the whole cluster.

## What has been verified

On minikube v1.39 (Kubernetes 1.37, Calico, ingress-nginx), on this laptop:
- every manifest and the rendered Helm chart pass the API server's validation
  (`kubectl apply --dry-run=server`);
- first boot: Postgres Ready, setup Job done in under 2 minutes (all migrations, 4 game
  versions imported), both web pods Ready;
- through the Ingress over HTTPS: every page 200, icons and static files served by the
  pods, brotli-compressed wasm (577 KB → 207 KB), HSTS and X-Frame-Options set, unknown
  hosts get 404;
- a deleted web pod is replaced; a rolling update and a rollback while polling the site
  twice a second: 60 out of 60 requests got 200;
- the database pod deleted and re-created: same volume, all 3,279 units still there;
- NetworkPolicy: Postgres refuses pods without the `db-access` label and accepts those
  with it; the web pods can't reach the internet;
- pods run as uid 10001 and can't write their filesystem; the CronJob runs on demand;
  `kubectl top` and the HPA read metrics;
- Helm: `install --wait` completes; an upgrade keeps the generated secrets and runs a new
  setup Job; rollback restores the previous values; uninstall keeps the Secrets and the
  database volume.

## If something's wrong

| Symptom | Look at |
|---|---|
| Pod `Pending` | `kubectl -n neko describe pod <pod>` → Events: no room (quota/requests), or PVC not bound |
| `ImagePullBackOff` | the image isn't in minikube: `minikube image ls \| grep neko` |
| `CrashLoopBackOff` | `kubectl -n neko logs <pod> --previous`, usually a missing Secret or setting |
| Web pods stuck `0/1` | `kubectl -n neko logs job/setup -c migrate`; readiness waits for migrations |
| `Init:0/1` forever | Postgres not Ready, or a NetworkPolicy blocking it: `kubectl -n neko get netpol` |
| Site doesn't open | is `minikube tunnel` running? `kubectl -n ingress-nginx get pods` |
