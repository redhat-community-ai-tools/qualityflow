{{/*
Chart name, truncated for use in resource names.
*/}}
{{- define "qualityflow-dashboard.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name (release + chart), truncated to fit DNS-1035 (63 chars).
*/}}
{{- define "qualityflow-dashboard.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "qualityflow-dashboard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "qualityflow-dashboard.labels" -}}
helm.sh/chart: {{ include "qualityflow-dashboard.chart" . }}
{{ include "qualityflow-dashboard.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "qualityflow-dashboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "qualityflow-dashboard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Name of the Secret holding auth/session/tokens: the user-supplied existing
Secret, or the one this chart creates.
*/}}
{{- define "qualityflow-dashboard.secretName" -}}
{{- .Values.auth.existingSecret | default (include "qualityflow-dashboard.fullname" .) -}}
{{- end -}}
