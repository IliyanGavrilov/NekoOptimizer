# Defending the Kubernetes setup

Every decision in `Dockerfile`, `planner/health.py` and `k8s/`, written as the questions a
reviewer is likely to ask, each with a short answer and the reason behind it. Grouped
roughly by the CKAD exercise sections (https://github.com/dgkanatsios/CKAD-exercises).

---

## 0. The big picture

**What did you build?**
The same Django site that runs on Vercel, packaged as a Docker image and run on Kubernetes:
2-5 web pods behind a Service and an Ingress, Postgres in a StatefulSet with a persistent
volume, a Job that migrates and imports the data, a CronJob for weekly cleanup, config in
a ConfigMap, credentials in Secrets, network access locked down with NetworkPolicies, and
all of it also packaged as a Helm chart. CI builds the image and publishes it to ghcr.io.

**What is a container? An image?**
An image is a read-only bundle: a filesystem (Python, our dependencies, our code) plus
metadata (which command to run, environment, user). A container is a running instance
of an image: an ordinary Linux process isolated by kernel features - namespaces (its own
view of processes, network, filesystem) and cgroups (limits on CPU/memory).

**Container vs virtual machine?**
A VM emulates a whole machine with its own kernel - heavy, slow to boot. Containers share
the host's kernel and only isolate the process, so they start in about a second and add
almost no overhead. Weaker isolation than a VM, which is why we also harden them (§6).

**What is Kubernetes, in one sentence?**
A system that keeps a declared state true: you tell its API "I want 2 web pods, this
Service, this volume" (YAML), and controllers keep comparing that to what's actually
running and fix any difference - a crashed pod is replaced, a deleted one recreated.

**Declarative vs imperative?**
Imperative: "start a container" (a command, done once). Declarative: "there should be 2"
(a desired state, kept true forever). Our YAML files are declarative; `kubectl apply`
sends them, and applying the same file twice changes nothing - it's idempotent.

**What are the cluster's parts?**
Control plane: the API server (everything goes through it), etcd (the database storing
all objects), the scheduler (picks a node for each new pod), the controller manager (the
loops that reconcile Deployments, Jobs, ...). On every node: the kubelet (starts the pod's
containers, runs probes), a container runtime (containerd), kube-proxy (makes Service IPs
work), and a CNI network plugin (pod networking - Calico for us). minikube runs all of
it on one node inside Docker.

**Why Kubernetes for this site at all?**
Honestly, Vercel serves it fine for free. The point here is the skills, applied to a real
app rather than toy examples: packaging, declarative config, secrets handling, health
checks, zero-downtime rollouts, autoscaling, persistence, scheduled jobs, network
security. It became a good fit recently: the seed search and the planner now run in the
visitor's browser (WebAssembly), so the server holds no work in memory and any number of
identical web pods is safe.

**Does any of this change the public site?**
No. Additive only: new files, plus two small app changes that are harmless on Vercel too -
gunicorn in requirements.txt, and the `/livez` `/readyz` endpoints.

---

## 1. The image (Dockerfile)

**Why two stages?**
The build stage needs things the running site doesn't: network access to download the
cat icons, pip's caches, the source copies of the icons. The runtime stage copies over
only the finished virtualenv and app. Smaller image, fewer things to attack, nothing
build-only left inside.

**Why `python:3.14-slim` and not `alpine`?**
Alpine uses musl instead of glibc, and many Python packages publish prebuilt wheels only
for glibc - on Alpine they'd compile from source (slow, needs compilers). `slim` is
Debian with the extras removed: small, and every wheel just works. 3.14 matches
`.python-version`, the version CI tests on.

**Why copy `requirements.txt` before the code?**
Docker caches each instruction as a layer and reuses it if nothing it depends on changed.
Dependencies change rarely, code often - so a code change rebuilds from `COPY . .` on and
reuses the cached `pip install`. Builds take seconds instead of minutes.

**What happens at build time?**
`fetch_icons` downloads about 2,100 cat icons and 45 material icons (third-party PNGs we
never commit). `collectstatic` gathers all static files (CSS, JS, neko.wasm, icons) into
`staticfiles/`, renames each with a content hash (`app.3f9a1c.js`) and writes gzip/brotli
copies. whitenoise serves those straight from the web pods, with long cache headers.
Then the source icons are deleted - only the collected copies are needed.

**Why the fake `DJANGO_SECRET_KEY` / `DATABASE_URL` during the build?**
`settings.py` refuses to start with debug off unless they're set (a safety net against a
misconfigured deploy). collectstatic must run with debug off to produce the hashed
manifest, and it never touches the database. Those values live only in the build stage's
`ENV` and don't exist in the final image.

**Why bake icons into the image instead of downloading them at pod start?**
Reproducible and offline: every pod from one image is byte-identical, starts in seconds,
and needs no internet at runtime - which lets the NetworkPolicies forbid outbound
traffic entirely. Downloading at startup would make every pod start depend on a
third-party site being up.

**Why gunicorn and not `manage.py runserver`?**
runserver is a development server: one process, no worker management, and Django's docs
say never to use it in production. gunicorn is a production WSGI server: a master process
supervising workers, replacing any that hang (`--timeout 30`), and shutting down
gracefully on SIGTERM.

**Why 2 workers × 4 threads?**
Each worker is a separate process (~100 MB with Django loaded). Threads within a worker
share that memory and handle requests that mostly wait (database, network). 2×4 = 8
concurrent requests per pod within a 512 Mi limit. To handle more traffic, Kubernetes
adds pods (HPA) rather than us growing one.

**Why a non-root user (uid 10001)?**
If someone found a hole in the app, they'd be an unprivileged user inside a container,
not root. 10001 is above the range of system users. The Kubernetes manifests enforce it
again (`runAsNonRoot`).

**`PYTHONUNBUFFERED=1`? `PYTHONDONTWRITEBYTECODE=1`?**
Unbuffered: log lines go to stdout immediately, so `kubectl logs` shows them live instead
of in delayed chunks. No bytecode: Python normally writes `.pyc` files next to the code;
our root filesystem is read-only in the cluster, so don't try.

**`--worker-tmp-dir /dev/shm`?**
gunicorn workers signal "still alive" by touching a temp file. `/dev/shm` is RAM-backed
and always writable, so this works on a read-only root filesystem and never waits on disk.

**What's in `.dockerignore`, and why?**
Files the image shouldn't contain: `.git`, the local virtualenv, the dev database, IDE
folders, tests and fixtures, the Rust source (the compiled `neko.wasm` is committed), and
`k8s/` itself. Smaller build context, faster builds, and no secrets (`.env`) can leak into
an image by accident.

**Could you build it with Podman?**
Yes, unchanged: `podman build -t neko-optimizer:local .`. Podman reads the same
Dockerfile format and produces the same OCI image. The differences are in how it runs:
no background daemon, and it can run rootless.

---

## 2. Core concepts and pods

**What is a pod?**
The smallest thing Kubernetes runs: one or more containers that share a network address
(they reach each other on `localhost`) and can share volumes. Pods are disposable -
they're never repaired, only replaced - so we always create them through controllers
(Deployment, StatefulSet, Job), not by hand.

**Why a namespace?**
It groups everything Neko Optimizer owns: one `kubectl delete namespace neko` removes it
all, names can't collide with other apps, and quotas, limits and network policies apply
per namespace.

**What are the labels for?**
Labels are how Kubernetes objects find each other: a Service sends traffic to pods
matching its selector, a Deployment owns the pods matching its selector, and
NetworkPolicies pick pods by label. We use the standard `app.kubernetes.io/name` and
`/component` keys, plus our own `neko-optimizer/db-access=true` to mark pods allowed to
reach the database.

---

## 3. Multi-container pods

**Where are the multi-container pods?**
Init containers. The web pod runs `wait-for-db` before gunicorn starts. The setup Job's pod
runs three containers in strict order: `wait-for-db` → `migrate` → `import`.

**How do init containers behave?**
They run one at a time, before the main containers, and each must exit successfully
before the next starts. If one fails, the kubelet retries it (per restartPolicy). Main
containers never start until all init containers succeed.

**Why `wait-for-db`?**
On a fresh cluster the web pods and Postgres start together, and Postgres needs a few
seconds to initialise. Without the wait, Django would crash on its first query and the
pod would restart a few times. `pg_isready` (from the postgres image) checks
"accepts connections" without a password.

**Why does it pass `-U "$POSTGRES_USER"`?**
This was a real bug, found on the first run. Without a user name, pg_isready asks the
operating system for the current user's name. Our containers run as uid 10001, which
doesn't exist in the postgres image's `/etc/passwd`, so pg_isready gave up before even
connecting ("no attempt") and the pods waited forever. Naming the user skips that lookup.
It's also why running as non-root needs testing: software sometimes assumes a named user.

**Why is migrate an init container and import the main one?**
Ordering for free: import needs the schema migrate creates, and init containers guarantee
migrate has finished successfully first.

**What other multi-container patterns exist?**
Sidecar: a helper running alongside the main container for the pod's whole life (log
shipper, service-mesh proxy). Since Kubernetes 1.29 these are init containers with
`restartPolicy: Always`. Ambassador: a proxy that represents an outside service to the
app. Adapter: converts the app's output into a standard format (e.g. metrics). We have no
honest need for those: whitenoise serves static files in-process, and logs go to stdout,
which the cluster already collects.

---

## 4. Pod design: Deployment, StatefulSet, Jobs

**What does the Deployment do?**
It keeps the web pods running and handles updates. It doesn't manage pods directly: it
creates a ReplicaSet per version of the pod template, and each ReplicaSet keeps N
identical pods. A rollout scales the new ReplicaSet up while scaling the old one down.

**How does a rolling update go, exactly?**
`maxSurge: 1, maxUnavailable: 0`: start one new pod; once it passes its readiness probe,
remove one old pod; repeat. Capacity never drops below the desired count, so there's no
downtime. A new version that never becomes Ready stalls the rollout with the old pods
still serving.

**How do you roll back?**
`kubectl rollout undo deployment/neko-web` switches back to the previous ReplicaSet, of
which `revisionHistoryLimit: 5` keep the last five. With Helm, `helm rollback`.

**`rollout undo` printed a warning about `last-applied-configuration`. Why?**
`kubectl apply` remembers the file it last applied (in an annotation) to work out what
changed next time. `rollout undo` changes the Deployment without touching that record,
so the cluster and the record now disagree. The emergency fix is fine; the lasting fix
is to revert the YAML in git and apply it. That's the idea behind GitOps: git is the
source of truth, and the cluster follows it.

**Why no `replicas:` in the Deployment?**
The HPA owns the replica count. If the YAML also stated `replicas: 2`, every
`kubectl apply` would reset it to 2 and fight the autoscaler.

**Why is Postgres a StatefulSet and not a Deployment?**
Deployment pods are interchangeable: random names, and they'd all share (or fight over)
the same volume. A StatefulSet gives each pod a fixed identity (`postgres-0`), its own
PersistentVolumeClaim that follows it across restarts and nodes, and ordered start/stop.
That's what a database needs.

**Why only one Postgres replica?**
Plain Postgres doesn't replicate itself. Several replicas need replication set up
(streaming replicas, failover) - usually done with an operator such as CloudNativePG, or
by using a managed database. For the real site, that's Neon.

**Why is setup a Job and not part of the web container's startup?**
Two web replicas starting together would both run `migrate` at the same moment and race
each other. A Job runs to completion exactly once (retrying on failure), separately from
serving traffic.

**What do the Job settings mean?**
`backoffLimit: 3`: replace a failed pod up to 3 times, then mark the Job failed.
`activeDeadlineSeconds: 1800`: stop after 30 minutes regardless. `ttlSecondsAfterFinished`:
delete the finished Job a day later. `restartPolicy: Never`: a failed pod is replaced by a
new one rather than restarted in place, so each attempt's logs stay inspectable.

**Why does re-running the Job need `kubectl delete job setup` first?**
A Job's pod template is immutable once created. The Helm chart avoids this by putting
the release revision in the name (`neko-setup-3`), so each upgrade creates a new Job.

**What does the CronJob do, and what do its settings mean?**
Every Monday at 04:17 UTC it creates a Job that runs `manage.py prune_guests` (deletes
guest profiles holding nothing). `concurrencyPolicy: Forbid`: never two at once.
`startingDeadlineSeconds: 3600`: if the cluster was down at 04:17, still run within the
hour. History limits keep the last 3 runs for their logs. `timeZone: Etc/UTC` pins the
schedule's time zone.

**How do you trigger it by hand?**
`kubectl -n neko create job prune-now --from=cronjob/prune-guests`.

---

## 5. Configuration

**How does the app get its settings?**
`nekosite/settings.py` already reads everything from environment variables (it ran on
Render and Vercel that way). The pods receive them from a ConfigMap (all of it, via
`envFrom`) and from Secrets (one key at a time, via `secretKeyRef`).

**ConfigMap vs Secret?**
Same shape (key → value). Secrets are meant for sensitive values: they're kept apart so
RBAC can restrict who reads them, they can be encrypted at rest in etcd, and tools avoid
printing them. ConfigMaps are for ordinary settings.

**Are Secrets encrypted?**
Not by default. `data:` is base64, which is an encoding anyone can reverse
(`echo … | base64 -d`). The protection is access control (who may `get secrets` in the
namespace) plus, on a real cluster, encryption at rest. Better options for production:
Sealed Secrets (encrypted values safe to commit), External Secrets Operator (pulls from a
vault), SOPS.

**Why aren't the Secrets in git?**
Anything in git is in its history forever and visible to whoever can read the repo.
`k8s/scripts/secrets.sh` creates them in the cluster with random values (`openssl rand`).
`k8s/examples/secrets.yaml` only shows the shape. The Helm chart generates them itself.

**How is `DATABASE_URL` built without storing the password twice?**
Dependent environment variables:
`value: postgres://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):5432/$(POSTGRES_DB)`.
Kubernetes (not the shell) replaces each `$(NAME)` with that variable's value, as defined
earlier in the same container. The password exists once, in the `postgres` Secret.

**Why does the generated password use only hex/alphanumeric characters?**
It's pasted into a URL. Characters like `@`, `/` or `:` would break URL parsing.

**If you change the ConfigMap, does the app see it?**
Not by itself: environment variables are read once when the container starts. You
restart the pods (`kubectl rollout restart`). The Helm chart automates this: a hash of the
ConfigMap sits in the pod template's annotations, so any change to it changes the
template, and that triggers a rollout.

**Why does the secrets script never overwrite an existing Secret?**
Postgres sets the password once, when it first initialises its volume. A new random
password afterwards would no longer match, and the app would be locked out. The Helm
chart does the same with `lookup` (reuse what's in the cluster) and the
`helm.sh/resource-policy: keep` annotation (survive `helm uninstall`, like the volume).

**What are the LimitRange and ResourceQuota for?**
LimitRange: default requests/limits for any container that states none (e.g. a quick
`kubectl run` debug pod), and a per-container ceiling. ResourceQuota: a cap on the whole
namespace (CPU, memory, number of pods and volumes), so a runaway autoscaler or Job
can't starve the rest of the cluster. With a quota on limits, every pod must state
limits - the LimitRange's defaults make sure they do.

---

## 6. Resources and security

**Requests vs limits?**
Requests are what the scheduler reserves: a pod only lands on a node with that much free,
and the HPA's percentages are measured against them. Limits are the most a container may
use: over the memory limit it's OOM-killed (and restarted); over the CPU limit it's
throttled (slowed), never killed.

**How did you choose the numbers?**
Web: Django with 2 workers sits around 200-300 Mi, so 256 Mi requested and 512 Mi as a
ceiling; 100m CPU requested because it idles most of the time. The import Job loads four
game versions' catalogues, so it gets more memory. They're starting points, to be tuned
with `kubectl top pods`.

**What QoS class are the pods?**
Burstable: requests are set and are lower than limits. Guaranteed would need requests =
limits (wasteful for a mostly idle site). BestEffort (no requests at all) is evicted first
under memory pressure - the LimitRange prevents that.

**What does each `securityContext` setting do?**
`runAsNonRoot` / `runAsUser: 10001`: refuse to start as root. `allowPrivilegeEscalation:
false`: no setuid tricks to gain more rights. `capabilities: drop: [ALL]`: none of root's
special powers (binding low ports, changing file owners, …). `readOnlyRootFilesystem`:
the code inside a running pod can't be modified; the only writable path is an `emptyDir`
on `/tmp`. `seccompProfile: RuntimeDefault`: the kernel blocks system calls containers
never need.

**Why is Postgres's filesystem writable?**
A database must write its data files. Its volume is writable by design, and Postgres
also writes lock and socket files outside the volume. It still runs non-root (uid 70,
the image's postgres user), with no escalation and no capabilities. `fsGroup: 70` makes
the mounted volume writable for that group.

**Why `automountServiceAccountToken: false`?**
By default every pod gets a token for calling the Kubernetes API. Our app never calls it,
so the token would only help an attacker who got into a pod. The web pods also get their
own ServiceAccount, which has no permissions (no RBAC roles bound).

---

## 7. Observability: probes, logs, metrics

**What's the difference between the three probes?**
Startup: "has it finished starting?" - while it fails, the other two don't run, so slow
starts aren't killed (here: up to 60 s). Liveness: "is it stuck?" - fail 3 times in a row
and the kubelet restarts the container. Readiness: "can it take traffic now?" - while it
fails, the pod is removed from the Service's endpoints, but not restarted.

**Why doesn't liveness check the database?**
If Postgres went down, every web pod would fail liveness and get restarted at the same
time. Restarting doesn't fix the database, it just adds a restart storm. Liveness only
asks "does this process answer?". The database belongs in readiness: it takes pods out
of traffic, and they come back by themselves when the database does.

**Why does readiness also check migrations?**
During a rollout, new code may expect a column that the setup Job hasn't added yet.
`/readyz` returns 503 "migrations pending" until the schema matches the code, so new pods
take no traffic (and the old ones keep serving) until it does. The check is cached once
it passes, so later probes cost one `SELECT 1`.

**Why are the probes handled in a middleware, first in the list?**
The kubelet probes `http://<pod IP>:8000/livez`. Two of Django's normal safety checks
would reject that: the Host header is a pod IP, which isn't in `ALLOWED_HOSTS` (400), and
it's plain HTTP while production redirects to HTTPS (301). Answering these two paths
before those middlewares run is safe: they return only "ok" and accept no input.

**Where do the logs go?**
stdout/stderr: gunicorn's access log and Django's errors (settings.py logs to the console
with debug off). The container runtime stores them per container, and `kubectl logs`
reads them. The Kubernetes way is: the app writes to stdout and the cluster collects it,
rather than the app managing log files.

**How do you see resource use?**
`kubectl top pods/nodes`, through metrics-server (a minikube addon). The HPA reads the
same metrics.

**How do you debug a broken pod?**
`kubectl describe pod` (events: scheduling, image pulls, probe failures, OOM kills),
`kubectl logs <pod> --previous` (the crashed container's last output),
`kubectl get events --sort-by=.lastTimestamp`, `kubectl exec -it <pod> -- sh`.

---

## 8. Services and networking

**What does a Service do?**
It gives a changing set of pods one stable DNS name and virtual IP. `neko-web` (ClusterIP)
load-balances to whichever web pods are Ready right now. kube-proxy programs each node to
forward the virtual IP to the pods behind it (listed in EndpointSlices).

**Service types?**
ClusterIP: inside the cluster only (ours). NodePort: also opens a port on every node.
LoadBalancer: asks a cloud for an external load balancer. ExternalName: a DNS alias.
Headless (`clusterIP: None`): no virtual IP, DNS returns the pod IPs directly.

**Why is the Postgres Service headless?**
A StatefulSet requires a headless Service to give its pods stable DNS names
(`postgres-0.postgres.neko.svc.cluster.local`). With one pod, plain `postgres` resolves to
it too.

**How does the app find the database?**
Cluster DNS (CoreDNS): `postgres` → `postgres.neko.svc.cluster.local` → the pod. That's
`POSTGRES_HOST` in the ConfigMap.

**What does the Ingress do?**
An Ingress is a set of HTTP routing rules ("host neko.localhost → Service neko-web").
An Ingress controller (ingress-nginx, minikube's addon) is the actual proxy that reads
those rules and serves them. Ours also terminates HTTPS with the `neko-tls` certificate.

**How does Django know the visitor used HTTPS, if the pod only gets HTTP?**
ingress-nginx adds `X-Forwarded-Proto: https`, and settings.py trusts that header
(`SECURE_PROXY_SSL_HEADER`). Django then treats the request as secure: no redirect loop,
and secure cookies work.

**Why `neko.localhost`?**
Browsers (and curl) resolve any `*.localhost` name to this machine by themselves, so no
DNS records or hosts-file edits are needed.

**Why do you need `minikube tunnel`?**
minikube on Docker runs inside a container. The tunnel forwards your machine's ports
80/443 to the ingress controller in it.

**Why a self-signed certificate?**
There's no public domain to prove ownership of, so no real certificate authority can
issue one. On a real cluster, cert-manager would get a Let's Encrypt certificate
automatically and renew it.

**What do the NetworkPolicies do?**
By default every pod can reach every other pod and the internet. Ours change that to
"deny everything, then allow exactly":
1. `default-deny`: all traffic in and out, for every pod in the namespace.
2. `allow-dns`: every pod may query cluster DNS (otherwise nothing resolves).
3. `web-from-ingress`: web pods accept connections only from the ingress controller's
   namespace, on port 8000.
4. `db-from-app`: Postgres accepts connections only from pods labelled `db-access=true`.
5. `app-to-db`: those pods may connect out only to Postgres.

Result: Postgres isn't reachable from any other pod, and a compromised web pod can't
reach the internet or anything else in the namespace.

**Policies combine how?**
They're additive "allow" lists. Once any policy selects a pod for a direction, only
traffic some policy allows gets through. That's why one deny-all plus targeted allows
works.

**Why `--cni=calico`?**
NetworkPolicy is only an API object: the network plugin enforces it. minikube's default
plugin accepts policies and silently ignores them. Calico enforces them. (The README
shows a demo: the same `pg_isready` from a pod with and without the label.)

**Then why do the kubelet's probes still work under deny-all?**
Probes come from the node itself, not from a pod, and Calico allows host-to-local-pod
traffic by default.

---

## 9. Autoscaling and availability

**How does the HPA decide?**
Every ~15 s it reads pod CPU from metrics-server and computes
`desired = ceil(current × actualUtilization / 70%)`, clamped to 2-5. Utilization is
measured against the CPU request (100m), so 140m average use on 2 pods → 4 pods. It scales
down only after the load has stayed low for a while, to avoid flapping.

**Why at least 2 replicas?**
So a single pod restarting, being rescheduled or being replaced during a rollout never
takes the site down.

**What's the PodDisruptionBudget?**
A promise for voluntary disruptions (draining a node for maintenance, cluster
upgrades): Kubernetes won't evict a web pod if that would leave fewer than 1 Ready. It
doesn't apply to crashes - the Deployment handles those.

**And `topologySpreadConstraints`?**
On a multi-node cluster, spread the web pods across nodes, so losing one node doesn't
lose every copy. minikube has one node, so there it has no effect, but the manifest is
ready for a real cluster.

---

## 10. State persistence

**Where does the database keep its data?**
In a PersistentVolumeClaim (`data-postgres-0`, 1 Gi), created from the StatefulSet's
`volumeClaimTemplates`. minikube's default StorageClass provisions a matching
PersistentVolume automatically (dynamic provisioning).

**PV vs PVC vs StorageClass?**
PVC: a pod's request ("1 Gi, read-write by one node"). PV: the actual piece of storage.
StorageClass: how PVs get created on demand (which provisioner, which disk type). Pods
mount PVCs and never deal with the disk itself.

**What survives what?**
Pod deleted or crashed → the new `postgres-0` re-attaches the same PVC: no data lost.
StatefulSet deleted → the PVC stays (by design). Namespace deleted → everything goes,
the PVC included.

**`ReadWriteOnce`?**
Mountable read-write by one node at a time - fine for a single database pod, and what
most block storage supports. ReadWriteMany needs shared storage (NFS and similar).

**Why `PGDATA` in a subfolder?**
A freshly formatted volume can contain `lost+found`, and Postgres's `initdb` refuses to
initialise a non-empty directory.

**What about backups?**
Not set up, and I'd say so openly. The natural next step: a CronJob running `pg_dump` to
object storage. The real site's Neon database has point-in-time restore built in.

---

## 11. Helm

**What is Helm?**
A package manager for Kubernetes. A chart is templated YAML plus a `values.yaml` of
defaults. `helm install` renders the templates with your values and applies the result as
a release. Every upgrade is a numbered revision you can roll back to.

**Why both the plain YAML and a chart?**
The plain files are the easiest to read and correspond 1:1 to the CKAD exercises. The
chart shows what plain YAML can't do:
- no repetition: the app environment, security settings and wait-for-db are defined once
  in `_helpers.tpl` instead of copied into four places;
- configurable without editing files (`--set web.autoscaling.maxReplicas=8`);
- several installs side by side (each object is named after its release);
- it generates its own Secrets and TLS certificate (`randAlphaNum`, `genSelfSignedCert`)
  and keeps them across upgrades (`lookup`);
- a new setup Job on every upgrade (the revision is in its name);
- pods restart when the config changes (`checksum/config` annotation);
- one-command install, upgrade and rollback.

**Why isn't the setup Job a Helm hook?**
With `helm install --wait`, Helm waits for the web pods to be Ready before running
post-install hooks. The web pods only become Ready after the Job has migrated the
database, so each would wait for the other forever. As an ordinary resource, the Job
runs alongside the rollout, and readiness keeps the new pods out of traffic until it's
done.

**What happens to the old setup Job on an upgrade?**
Helm deletes it: `neko-setup-1` isn't part of revision 2's rendered manifests, and Helm
removes whatever a release no longer contains. Rolling back to revision 1 re-creates
`neko-setup-1`, which migrates and imports again. That's harmless, because both steps
are idempotent: running them twice leaves the same result.

**What do `helm template`, `lint`, `rollback` do?**
`template`: render the YAML without installing (to inspect it). `lint`: check the chart
for mistakes. `rollback neko`: re-apply the previous revision's rendered YAML.

---

## 12. CI and the image registry

**What does `.github/workflows/image.yml` do?**
On every pull request it builds the image, which proves the Dockerfile still works. On
main it also pushes the image to GitHub Container Registry
(`ghcr.io/<owner>/neko-optimizer`), tagged with the commit SHA and `latest`.

**Why tag with the commit SHA?**
`latest` changes meaning with every push. A SHA tag always points to exactly one build,
so a deployment pinned to it is reproducible and rollbacks are exact.

**How does it log in to the registry?**
With the workflow's own short-lived `GITHUB_TOKEN`, given `packages: write` for this job
only. No stored passwords.

**What's the build cache?**
`cache-from/to: type=gha` stores Docker layers in GitHub's cache, so unchanged layers
(the pip install) aren't rebuilt on every run.

**Why are the actions pinned to commit SHAs?**
A tag like `v6` can be moved by whoever controls the action's repository. A SHA can't.
That protects the pipeline (which holds a token that can push images) from a hijacked
action. The rest of this repo's workflows are pinned the same way.

---

## 13. Things not done, and why

**Custom Resource Definitions?**
A CRD adds a new object type to the API, together with a controller (an "operator") that
acts on it - for example a `PostgresCluster` kind. Writing one is a different job
(building an operator), and this app doesn't need a new kind of object. A database
operator like CloudNativePG would be the realistic place to *use* CRDs.

**What would change for real production?**
A managed cluster with several nodes. A managed database (or an operator with
replicas and backups). cert-manager for real certificates. External Secrets or Sealed
Secrets. Prometheus + Grafana for metrics and alerts. GitOps (Argo CD) applying the chart
from git instead of running commands by hand. Image scanning in CI.

**Known limitations?**
One Postgres pod (no failover), no backups, a self-signed certificate, and a single-node
cluster, where topology spread and the PDB can't show their full effect.

---

## 14. Quick reference: which file covers which exercise section

| CKAD section | Where |
|---|---|
| Core concepts | namespace, pods, labels: `00-namespace.yaml`, everything |
| Multi-container pods | init containers: `40-web.yaml`, `30-setup-job.yaml` |
| Pod design | Deployment + rollout/rollback, Job, CronJob, labels/selectors: `40`, `30`, `70` |
| Configuration | ConfigMap, Secrets, dependent env vars, securityContext, requests/limits, ServiceAccount, LimitRange, ResourceQuota: `10`, `scripts/secrets.sh`, `40`, `00` |
| Observability | startup/liveness/readiness probes, logs, `kubectl top`: `planner/health.py`, `40` |
| Services & networking | ClusterIP + headless Services, Ingress, NetworkPolicies: `40`, `20`, `50`, `60` |
| State persistence | StatefulSet, volumeClaimTemplates, PVC: `20` |
| Helm | `k8s/helm/neko-optimizer/` |
| Podman | same Dockerfile: `podman build` (§1) |
| CRD | not used, and why (§13) |
