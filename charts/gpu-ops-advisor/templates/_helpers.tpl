{{- define "gpu.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "gpu.postgresName" -}}
{{- default (printf "%s-postgres" (include "gpu.fullname" .)) .Values.postgres.nameOverride -}}
{{- end -}}

{{- define "gpu.artifactsName" -}}
{{- default (printf "%s-artifacts" (include "gpu.fullname" .)) .Values.artifacts.persistence.nameOverride -}}
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

{{/* Validate the opt-in multi-worker layout without inspecting or changing cluster PVCs. */}}
{{- define "gpu.validateAgentCapacity" -}}
{{- $rca := index .Values.components "rcca-agent" -}}
{{- $ops := index .Values.components "ops-agent" -}}
{{- if or (and $rca.enabled (gt (int $rca.replicas) 1)) (and $ops.enabled (gt (int $ops.replicas) 1)) -}}
{{- $config := include "gpu.config" (dict "root" . "key" "jobController" "file" "files/job-controller.json") | fromJson -}}
{{- $limits := $config.kind_limits | default dict -}}
{{- $profiles := $config.worker_profiles | default dict -}}
{{- range $kind, $worker := dict "rca" $rca "report" $ops -}}
{{- if ne (int (index $limits $kind)) (int $worker.replicas) -}}
{{- fail (printf "multi-agent kind_limits.%s must equal its configured Agent replicas" $kind) -}}
{{- end -}}
{{- if and $worker.enabled (gt (int $worker.replicas) 1) -}}
{{- if hasKey $worker.env "WORKER_ID" -}}
{{- fail "replicated Agents must not set a shared static WORKER_ID; use the generated per-process identity" -}}
{{- end -}}
{{- end -}}
{{- if $worker.enabled -}}
{{- $profileID := printf "%s-v1" $kind -}}
{{- if hasKey $worker.env "CAPACITY_PROFILE_ID" -}}
{{- $profileID = index $worker.env "CAPACITY_PROFILE_ID" -}}
{{- end -}}
{{- $profile := index $profiles $profileID | default dict -}}
{{- if or (ne (default "" $profile.kind) $kind) (ne (int $profile.slots) 1) -}}
{{- fail (printf "multi-agent capacity profile %s must match kind %s with slots=1" $profileID $kind) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if lt (int $config.shared_limit) (int (add (int $limits.rca) (int $limits.report))) -}}
{{- fail "multi-agent shared_limit must cover the sum of rca and report kind_limits" -}}
{{- end -}}
{{- if and $ops.enabled (gt (int $ops.replicas) 1) -}}
{{- $storage := .Values.artifacts.persistence -}}
{{- if or (not $storage.enabled) (empty $storage.existingClaim) (ne (default "" $storage.existingClaimAccessMode) "ReadWriteMany") -}}
{{- fail "multiple Ops Agents require persistent artifacts on an existingClaim declared existingClaimAccessMode=ReadWriteMany; verify the PVC and preserve existing files before upgrading" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
