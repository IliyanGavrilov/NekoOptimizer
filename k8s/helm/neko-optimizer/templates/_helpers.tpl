{{/*
Snippets the templates share - what the plain k8s/*.yaml files had to repeat by hand.
Call one with: {{ include "neko.name" . }}
*/}}

{{/* The prefix of every object's name: the release name (helm install <release> ...). */}}
{{- define "neko.name" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels every object carries: the standard app.kubernetes.io set. */}}
{{- define "neko.labels" -}}
app.kubernetes.io/name: neko-optimizer
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* The labels a selector matches on: only ones that never change between versions.
     Usage: include "neko.selector" (list . "web") */}}
{{- define "neko.selector" -}}
{{- $ := index . 0 -}}
app.kubernetes.io/name: neko-optimizer
app.kubernetes.io/instance: {{ $.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end -}}

{{/* The app image reference. */}}
{{- define "neko.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}

{{/* The environment every app container gets: the ConfigMap, the two secret values, and
     DATABASE_URL built from them ($(NAME) is expanded by Kubernetes, not Helm). */}}
{{- define "neko.appEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "neko.name" . }}-config
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "neko.name" . }}-db
        key: POSTGRES_PASSWORD
  - name: DJANGO_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: {{ include "neko.name" . }}-django
        key: DJANGO_SECRET_KEY
  - name: DATABASE_URL
    value: postgres://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):5432/$(POSTGRES_DB)
{{- end -}}

{{/* Pod-level security: never root, the kernel's default syscall filter. */}}
{{- define "neko.podSecurity" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/* Container-level security: no privilege escalation, no Linux capabilities, and a
     read-only root filesystem. */}}
{{- define "neko.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* The init container that waits until Postgres accepts connections. */}}
{{- define "neko.waitForDb" -}}
- name: wait-for-db
  image: {{ .Values.postgres.image }}
  command: ["sh", "-c", 'until pg_isready -h "$POSTGRES_HOST" -p 5432 -U "$POSTGRES_USER"; do sleep 2; done']
  envFrom:
    - configMapRef:
        name: {{ include "neko.name" . }}-config
  resources:
    requests: { cpu: 10m, memory: 16Mi }
    limits: { cpu: 100m, memory: 64Mi }
  securityContext:
    {{- include "neko.containerSecurity" . | nindent 4 }}
{{- end -}}
