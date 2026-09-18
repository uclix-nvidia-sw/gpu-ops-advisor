package api

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	. "gpu-ops-advisor/backend/internal/contract"
	"html/template"
	"net/http"
	"strings"
)

func reportMetrics(body Object) []Object {
	var metrics []Object
	appendMetrics := func(value any) {
		if rows, ok := value.([]any); ok {
			for _, row := range rows {
				if metric, ok := row.(map[string]any); ok {
					metrics = append(metrics, metric)
				}
			}
		}
	}
	appendMetrics(body["measurements"])
	if topics, ok := body["topics"].([]any); ok {
		for _, item := range topics {
			if topic, ok := item.(map[string]any); ok {
				appendMetrics(topic["metrics"])
			}
		}
	}
	return metrics
}

func exportMetrics(w http.ResponseWriter, id, format string, body Object, metrics []Object) error {
	var data [][]string
	for _, metric := range metrics {
		target, _ := metric["target"].(map[string]any)
		var parts []string
		for _, field := range []string{"cluster_id", "namespace", "project", "gpu_uuid", "pod_uid"} {
			if v := String(target, field); v != "" {
				parts = append(parts, v)
			}
		}
		if len(parts) == 0 {
			parts = append(parts, "선택한 전체 범위")
		}
		value := "산출 불가"
		if metric["value"] != nil {
			value = fmt.Sprint(metric["value"])
		}
		quality, _ := metric["quality"].(map[string]any)
		refs, _ := json.Marshal(metric["evidence_refs"])
		data = append(data, []string{String(metric, "id"), strings.Join(parts, " · "), value, String(metric, "unit"), String(metric, "method"), String(quality, "reason"), string(refs)})
	}
	if format == "csv" {
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		if _, err := w.Write([]byte("\xef\xbb\xbf")); err != nil {
			return err
		}
		writer := csv.NewWriter(w)
		writer.UseCRLF = true
		if err := writer.Write([]string{"id", "target", "value", "unit", "method", "reason", "evidence_refs"}); err != nil {
			return err
		}
		for _, row := range data {
			for i, cell := range row {
				row[i] = csvSafe(cell)
			}
			if err := writer.Write(row); err != nil {
				return err
			}
		}
		writer.Flush()
		return writer.Error()
	}
	raw, _ := json.MarshalIndent(body, "", "  ")
	status := map[string]string{"ready": "산출 완료", "partial": "부분 산출", "blocked": "근거 부족"}[String(body, "result_status")]
	if status == "" {
		status = String(body, "result_status")
	}
	var limitations []string
	if values, ok := body["limitations"].([]any); ok {
		for _, value := range values {
			if text, ok := value.(string); ok {
				limitations = append(limitations, text)
			}
		}
	}
	if topics, ok := body["topics"].([]any); ok {
		seen := map[string]bool{}
		for _, item := range topics {
			if topic, ok := item.(map[string]any); ok {
				if reasons, ok := topic["missing_inputs"].([]any); ok {
					for _, item := range reasons {
						if reason, ok := item.(string); ok && !seen[reason] {
							limitations = append(limitations, reportReason(reason))
							seen[reason] = true
						}
					}
				}
			}
		}
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Security-Policy", "sandbox; default-src 'none'; style-src 'unsafe-inline'")
	page := template.Must(template.New("report").Funcs(template.FuncMap{"label": reportMetricName, "reason": reportReason}).Parse(`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPU 운영 보고서</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#182434}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}th{background:#f1f5f9}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:32px}.table{overflow:auto}</style></head><body><h1>GPU 운영 보고서</h1><p>{{.ID}}</p><p>결과: <strong>{{.Status}}</strong></p><p>분석 기간: {{.Period}}</p><h2>주요 수치</h2><div class="table"><table><thead><tr><th>항목</th><th>대상</th><th>값</th><th>단위</th><th>산출 제한</th></tr></thead><tbody>{{range .Rows}}<tr><td>{{label (index . 0)}}</td><td>{{index . 1}}</td><td>{{index . 2}}</td><td>{{index . 3}}</td><td>{{reason (index . 5)}}</td></tr>{{end}}</tbody></table></div><h2>해석 시 참고사항</h2><ul>{{range .Limitations}}<li>{{.}}</li>{{end}}</ul><details><summary>근거·산식 및 원본 결과</summary><pre>{{.Raw}}</pre></details></body></html>`))
	period, _ := body["time_range"].(map[string]any)
	return page.Execute(w, Object{"ID": id, "Status": status, "Period": String(period, "start") + " – " + String(period, "end"), "Rows": data, "Limitations": limitations, "Raw": string(raw)})
}

func reportMetricName(id string) string {
	parts := strings.Split(id, ".")
	if len(parts) < 2 {
		return id
	}
	name := map[string]string{"observed_gpu_count": "관측된 GPU", "observed_devices": "관측된 GPU", "mapped_gpu_count": "Pod 연결이 확인된 GPU", "mapped_gpu_hours": "GPU–Pod 연결 관측 시간", "observed_namespace_hours": "Namespace별 GPU–Pod 연결 관측 시간", "current_allocated_gpu": "독점 할당 GPU (기간 종료 시점)", "allocated_gpu_hours": "독점 할당 시간", "allocated_instance_hours": "MIG 인스턴스 할당 시간", "allocation_group": "그룹별 독점 할당 시간", "vram": "평균 GPU 메모리 사용량", "temperature": "평균 GPU 온도", "gpu_energy": "관측 GPU 에너지"}[parts[1]]
	if name == "" {
		return id
	}
	return parts[0] + " · " + name
}

func reportReason(reason string) string {
	text := map[string]string{"required_data_missing": "계산에 필요한 원본 데이터 또는 식별 정보가 없습니다.", "MIG_history_missing": "MIG 인스턴스 이력이 없습니다.", "allocation_contract_missing": "독점·공유·MIG 할당 이력이 없어 정확한 할당량을 확정할 수 없습니다.", "allocation_mode_unverified": "독점·공유·MIG 할당 방식을 확인할 수 없습니다.", "gpu_pod_identity_missing": "GPU와 같은 시점의 Pod 고유 ID를 연결하지 못했습니다.", "observed_mapping_not_exclusive_allocation": "GPU–Pod 연결 관측 시간은 독점 할당량이나 실제 연산 시간이 아닙니다. 공유 GPU는 Namespace 간 중복될 수 있습니다.", "project_owner_mapping": "프로젝트·소유자 연결 정보가 없어 Namespace 기준으로만 표시합니다.", "incomplete_observation": "일부 조회 결과가 제한되거나 실패했습니다."}[reason]
	if text == "" {
		return reason
	}
	return text
}
