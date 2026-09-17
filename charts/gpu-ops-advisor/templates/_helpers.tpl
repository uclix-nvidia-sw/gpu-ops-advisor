{{- define "gpu.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "gpu.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "gpu.image" -}}
{{- $repo := printf "%s/%s/%s" .root.Values.global.imageRegistry .root.Values.global.imageNamespace .component.image.repository -}}
{{- if .component.image.digest -}}
{{- printf "%s@%s" $repo .component.image.digest -}}
{{- else -}}
{{- printf "%s:%s" $repo (default (printf "v%s" .root.Chart.AppVersion) .component.image.tag) -}}
{{- end -}}
{{- end -}}

{{- define "gpu.config" -}}
{{- $custom := index .root.Values.configuration .key -}}
{{- if $custom -}}
{{ $custom | toPrettyJson }}
{{- else -}}
{{ .root.Files.Get .file }}
{{- end -}}
{{- end -}}
