{{/*
Standard naming helpers.
*/}}

{{- define "enterprisecore.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "enterprisecore.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "enterprisecore.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Component-scoped fullnames so backend / frontend / postgres each get
distinct, deterministic names.
*/}}
{{- define "enterprisecore.backend.fullname" -}}
{{- printf "%s-backend" (include "enterprisecore.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "enterprisecore.frontend.fullname" -}}
{{- printf "%s-frontend" (include "enterprisecore.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "enterprisecore.postgres.fullname" -}}
{{- printf "%s-postgres" (include "enterprisecore.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "enterprisecore.ollama.fullname" -}}
{{- printf "%s-ollama" (include "enterprisecore.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "enterprisecore.labels" -}}
helm.sh/chart: {{ include "enterprisecore.chart" . }}
app.kubernetes.io/name: {{ include "enterprisecore.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Selector labels — never include version (would break rolling updates).
*/}}
{{- define "enterprisecore.selectorLabels" -}}
app.kubernetes.io/name: {{ include "enterprisecore.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "enterprisecore.backend.selectorLabels" -}}
{{ include "enterprisecore.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end -}}

{{- define "enterprisecore.frontend.selectorLabels" -}}
{{ include "enterprisecore.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end -}}

{{- define "enterprisecore.postgres.selectorLabels" -}}
{{ include "enterprisecore.selectorLabels" . }}
app.kubernetes.io/component: postgres
{{- end -}}

{{/*
Secret name to use for app secrets — either user-supplied or chart-generated.
*/}}
{{- define "enterprisecore.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "enterprisecore.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Postgres DSN resolved from either bundled Postgres or external. Used by the
backend Deployment.
*/}}
{{- define "enterprisecore.postgresDsn" -}}
{{- if .Values.postgres.enabled -}}
postgresql+psycopg2://{{ .Values.postgres.username }}:$(POSTGRES_PASSWORD)@{{ include "enterprisecore.postgres.fullname" . }}:5432/{{ .Values.postgres.database }}
{{- else -}}
{{- .Values.externalDatabase.dsn -}}
{{- end -}}
{{- end -}}
