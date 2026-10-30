package api

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	. "gpu-ops-advisor/backend/internal/contract"
	"html/template"
	"net/http"
	"sort"
	"strconv"
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

func exportMetrics(w http.ResponseWriter, id, format string, body Object, metrics []Object, projection Object) error {
	resultQuality, _ := body["quality"].(map[string]any)
	perTopic := resultQuality["topic_group_by"] != nil
	versions, _ := body["versions"].(map[string]any)
	timed := String(versions, "criteria") == "1.3" || String(versions, "criteria") == AggregateReportVersion
	var data [][]string
	for _, metric := range metrics {
		target, _ := metric["target"].(map[string]any)
		var parts []string
		for _, field := range []string{"cluster_id", "namespace", "project", "gpu_uuid", "pod_uid", "node", "condition", "status", "model", "window", "job", "instance"} {
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
		row := []string{String(metric, "id"), strings.Join(parts, " · "), value, String(metric, "unit"), String(metric, "method"), String(quality, "reason"), string(refs)}
		if perTopic {
			row = append(row, String(quality, "display_basis"))
		}
		if timed {
			period, _ := json.Marshal(metric["period"])
			row = append(row, string(period))
		}
		data = append(data, row)
	}
	if format == "csv" {
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		if _, err := w.Write([]byte("\xef\xbb\xbf")); err != nil {
			return err
		}
		writer := csv.NewWriter(w)
		writer.UseCRLF = true
		header := []string{"id", "target", "value", "unit", "method", "reason", "evidence_refs"}
		if perTopic {
			header = append(header, "display_basis")
		}
		if timed {
			header = append(header, "period")
		}
		if err := writer.Write(header); err != nil {
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
	// HTML is for reading; CSV above retains exact stored values and units.
	sort.SliceStable(data, func(i, j int) bool {
		return strings.HasPrefix(data[i][0], "O08.") && !strings.HasPrefix(data[j][0], "O08.")
	})
	for _, row := range data {
		if row[3] == "bytes" {
			if value, err := strconv.ParseFloat(row[2], 64); err == nil {
				unit := "B"
				for _, next := range []string{"KiB", "MiB", "GiB"} {
					if value < 1024 {
						break
					}
					value /= 1024
					unit = next
				}
				row[2], row[3] = strconv.FormatFloat(value, 'f', 3, 64), unit
			}
		} else if unit := map[string]string{"physical_gpu": "대", "GPU-hours": "GPU·시간", "percent": "%", "events": "건", "percentage_points": "%p"}[row[3]]; unit != "" {
			row[3] = unit
		}
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
	page := template.Must(template.New("report").Funcs(template.FuncMap{"label": reportMetricName, "reason": reportReason}).Parse(`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{.Title}}</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#182434}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}th{background:#f1f5f9}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:32px}.table{overflow:auto}.ops-advice-cluster{margin:20px 0;padding:16px 18px;border:1px solid #dce6e1;border-left:5px solid #156e57;border-radius:8px;background:#fff}.ops-advice-cluster .ops-advice-card-title{font-size:16px;margin:0 0 4px;color:#156e57}.ops-advice-cluster .ops-advice-cluster-target{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;margin:0 0 8px;font-size:13px;font-weight:400;color:#596762}.ops-advice-cluster-target>code{display:inline-block;max-width:100%;padding:1px 6px;border:1px solid #cfe1d7;border-radius:4px;background:#edf7f1;color:inherit;font-family:ui-monospace,monospace;font-size:.95em;line-height:1.5;overflow-wrap:anywhere}.ops-advice-namespace{margin:0 0 0 8px}.ops-advice-namespace+.ops-advice-namespace{margin-top:20px;padding-top:16px;border-top:1px solid #dce6e1}.ops-advice-namespace .ops-advice-identity{display:grid;grid-template-columns:6.3em .65em minmax(0,1fr);column-gap:6px;align-items:baseline;margin:0 0 8px;font-size:14px;font-weight:400;line-height:1.6;color:#596762}.ops-advice-identity>code{min-width:0;font-size:.95em;font-weight:500;color:#243c37;overflow-wrap:anywhere}.ops-advice-namespace article{margin:0;overflow-wrap:anywhere}.ops-advice-namespace article+article{margin-top:20px}.ops-advice-heading{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;margin:0 0 4px}.ops-advice-heading h6{font-size:14px;font-weight:600;line-height:1.6;margin:0}.ops-advice-history{font-size:12px;color:#596762}.ops-advice-namespace article>p{margin:0 0 10px;font-size:14px;font-weight:400;line-height:1.75;white-space:normal}.ops-advice-namespace dl{display:grid;gap:4px;margin:0;font-size:13px}.ops-advice-namespace dl>div{display:grid;grid-template-columns:6rem minmax(0,1fr);gap:4px 10px;align-items:baseline;margin:0}.ops-advice-namespace dt{font-size:12px;color:#596762}.ops-advice-namespace dd{margin:0;line-height:1.65;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.ops-advice-namespace article>.ops-advice-model,.ops-advice-namespace article>.ops-advice-scope{margin:6px 0 0;font-size:12px;font-weight:400;line-height:1.65;color:#596762}.ops-advice-namespace details{margin:6px 0 0;padding:0;border:0;font-size:13px}.ops-advice-namespace details>summary{cursor:pointer;width:fit-content;padding:4px 0;color:#596762;font-weight:400}.ops-advice-namespace details>summary:focus-visible{outline:2px solid #156e57;outline-offset:3px}.ops-advice-namespace details>p{margin:8px 0;font-size:13px;line-height:1.75}.ops-advice-basis{color:#596762}.ops-advice-time-note{font-size:12px;color:#596762;margin:0 0 16px}@media(max-width:640px){.ops-advice-cluster{padding:14px 12px}.ops-advice-namespace{margin-left:0}.ops-advice-namespace dl>div{grid-template-columns:minmax(0,1fr);gap:0}}.ops-advice-namespace details>summary:hover{color:#156e57;text-decoration:underline;text-underline-offset:3px}.ops-advice-namespace details[open]>summary{margin-bottom:8px}.ops-advice-namespace details>p{color:#596762;font-weight:400}.ops-advice-namespace details>p>strong{color:#243c37;font-weight:500}.advice-kind{display:inline-block}</style></head><body><h1>{{.Title}}</h1><p>{{.ID}}</p><p>결과: <strong>{{.Status}}</strong></p><p>분석 기간: {{.Period}}</p><p>계산 기준: {{.Criteria}}</p><p>요청 집계: {{.Grouping}}</p><p>연결 GPU 활동률은 Namespace의 실제 소비량·독점 할당량이 아닙니다. 공유·누락 구간은 보류하며 유효 관측 시간만 평균에 사용합니다.</p>{{if .Timed}}<p>시간대 대수는 최대 동시 연결 대수입니다. 저활동은 GPU별 5% 미만이 30분 이상 이어진 관측이며 낭비·회수 가능 여부가 아닙니다. Fleet 기록값은 실제 측정 시각이 미확인이며 현재 장비 상태로 단정하지 않습니다.</p>{{else}}<p>누적 연결 시간은 GPU별 연결 시간을 더한 값입니다. GPU 8대가 각각 1시간 연결되면 8 GPU·시간이며, 실제 연산 시간은 아닙니다. 관측되지 않은 구간은 제외합니다. 연결 GPU 대수는 기간 중 고유 대수이며 동시 사용 대수가 아닙니다.</p>{{end}}{{if .Narrative}}<h2>최종 보고서</h2><p>{{.Editorial}}</p>{{range .Narrative}}<section><h3>{{.title}}</h3>{{if .advice_groups}}{{template "namespaceAdvice" .advice_groups}}<details><summary>저장된 해석 원문</summary><pre>{{.text}}</pre></details>{{else}}<pre>{{.text}}</pre>{{end}}</section>{{end}}{{end}}<h2>아직 판단할 수 없는 내용·해석 제한</h2><ul>{{range .Limitations}}<li>{{.}}</li>{{end}}</ul><h2>주요 수치</h2><div class="table"><table><thead><tr><th>항목</th><th>대상</th><th>값</th><th>단위</th><th>산출 제한</th>{{if .PerTopic}}<th>표시 기준</th>{{end}}{{if .Timed}}<th>기록/분석 시각 (UTC)</th>{{end}}</tr></thead><tbody>{{range .Rows}}<tr><td>{{label (index . 0)}}</td><td>{{index . 1}}</td><td>{{index . 2}}</td><td>{{index . 3}}</td><td>{{reason (index . 5)}}</td>{{if $.PerTopic}}<td>{{index . 7}}</td>{{end}}{{if $.Timed}}<td>{{if $.PerTopic}}{{index . 8}}{{else}}{{index . 7}}{{end}}</td>{{end}}</tr>{{end}}</tbody></table></div><details><summary>근거·산식 및 {{if .Projection}}조회용{{else}}원본{{end}} 결과</summary>{{if .Projection}}<p>중복 노드 상태 구간을 생략한 조회용 결과입니다. 지표와 근거 참조는 유지합니다. 저장 원본 해시: {{.Projection.stored_content_hash}}</p>{{end}}<pre>{{.Raw}}</pre></details></body></html>` + namespaceAdviceTemplate))
	period, _ := body["time_range"].(map[string]any)
	quality, _ := body["quality"].(map[string]any)
	grouping := "기록 없음"
	if quality["requested_group_by"] != nil {
		grouping = fmt.Sprint(quality["requested_group_by"])
	}
	if perTopic {
		grouping = "소주제별 기준 적용 (각 지표의 표시 기준 참조)"
	}
	if reason := String(quality, "narrative_reason"); reason != "" {
		limitations = append(limitations, reportReason(reason))
	}
	editorial := "LLM 편집을 사용하지 못한 기본 보고서입니다. 보고서 작성 완료와 자료의 완전성은 별개입니다."
	if report, ok := quality["report"].(map[string]any); ok && String(report, "method") == "partial_interpretation" {
		editorial = "일부 주제의 AI 해석을 작성하지 못했습니다. 검증을 통과한 주제의 AI 해석과 나머지 주제의 계산 결과 요약을 표시합니다."
	} else if String(body, "narrative_status") == "complete" {
		editorial = "확인된 내용을 LLM이 정리했습니다. 보고서 작성 완료와 자료의 완전성은 별개입니다."
	}
	return page.Execute(w, Object{"Title": reportDocumentTitle(body), "Projection": projection, "Timed": timed, "PerTopic": perTopic, "Narrative": reportNarrative(body), "Editorial": editorial, "Criteria": String(versions, "criteria"), "Grouping": grouping, "ID": id, "Status": status, "Period": String(period, "start") + " – " + String(period, "end"), "Rows": data, "Limitations": limitations, "Raw": string(raw)})
}

func reportMetricName(id string) string {
	parts := strings.Split(id, ".")
	if len(parts) < 2 {
		return id
	}
	name := map[string]string{
		"namespace_connected_gpu_count":       "기간 중 연결이 확인된 GPU",
		"namespace_activity_valid_hours":      "활동률 계산에 사용한 시간",
		"namespace_connected_gpu_util":        "연결 GPU 평균 활동률",
		"low_gpu_hours":                       "저활동 관측 시간",
		"difference":                          "GPU 활동률 편차",
		"incident_rate":                       "관측 GPU시간당 사건 발생률",
		"mapped_incident_relations":           "사건 당시 GPU·작업 연결",
		"gpu_shortage":                        "GPU 부족량",
		"observed_change":                     "조치 전후 관측 변화",
		"energy_before":                       "조치 전 관측 에너지",
		"energy_after":                        "조치 후 관측 에너지",
		"observed_energy_reduction":           "관측 에너지 감소량",
		"observed_gpu_count":                  "관측된 GPU",
		"observed_devices":                    "관측된 GPU",
		"mapped_gpu_count":                    "Pod 연결이 확인된 GPU",
		"mapped_gpu_hours":                    "GPU–Pod 연결 관측 시간",
		"node_condition_seconds":              "Node 조건 관측 시간",
		"hourly_peak_gpu_count":               "시간대 최대 동시 연결 GPU",
		"hourly_gpu_activity":                 "시간대 연결 GPU 평균 활동률",
		"model_gpu_activity":                  "모델별 기간 평균 활동률",
		"observed_low_activity_seconds":       "연속 저활동 관측 시간",
		"recorded_memory_used":                "기록된 GPU 메모리 사용량",
		"recorded_memory_free":                "기록된 GPU 메모리 여유량",
		"recorded_memory_total":               "기록된 GPU 메모리 총량",
		"recorded_temperature":                "기록된 GPU 온도",
		"recorded_cpu_used":                   "기록된 Node CPU 사용률",
		"recorded_node_load":                  "기록된 Node load",
		"target_up_seconds":                   "수집 대상 정상 응답 시간",
		"target_down_seconds":                 "수집 대상 실패 응답 시간",
		"target_unknown_seconds":              "수집 대상 미관측 시간",
		"scrape_duration_mean":                "평균 수집 응답 시간",
		"scrape_duration_max":                 "최대 수집 응답 시간",
		"cluster_observed_gpu_count":          "클러스터 관측 GPU",
		"cluster_connected_gpu_count":         "클러스터 연결 확인 GPU",
		"cluster_connected_gpu_hours":         "클러스터 누적 연결 시간",
		"cluster_unlabeled_gpu_count":         "Pod 연결 라벨 없는 GPU",
		"cluster_unattributed_gpu_count":      "Pod 신원 연결 미확인 GPU",
		"observed_namespace_hours":            "Namespace별 GPU–Pod 연결 관측 시간",
		"current_allocated_gpu":               "독점 할당 GPU (기간 종료 시점)",
		"allocated_gpu_hours":                 "독점 할당 시간",
		"allocated_instance_hours":            "MIG 인스턴스 할당 시간",
		"allocation_group":                    "그룹별 독점 할당 시간",
		"vram":                                "평균 GPU 메모리 사용량",
		"temperature":                         "평균 GPU 온도",
		"gpu_memory_free_mean":                "평균 GPU 메모리 여유량",
		"gpu_memory_used_ratio":               "GPU 메모리 용량 대비 사용 비율",
		"node_cpu_used_mean":                  "평균 Node CPU 사용률",
		"node_load_by_window":                 "시간창별 Node load 평균",
		"gpu_energy":                          "관측 GPU 에너지",
		"incident_count":                      "사건 수",
		"total_coverage":                      "전체 관측률",
		"observed_healthy_collection_seconds": "정상 수집 관측 시간",
	}[parts[1]]
	if name == "" {
		return id
	}
	return parts[0] + " · " + name
}

func reportReason(reason string) string {
	text := map[string]string{
		"namespace_current_attribution_missing":       "현재 기간에 선택 범위의 Namespace 귀속 GPU 관측이 없습니다.",
		"namespace_observations_missing":              "Namespace 관측 자료가 없습니다.",
		"shared_gpu_attribution_unverified":           "GPU 공유 구간은 Namespace별 활동률을 구분할 수 없어 제외했습니다.",
		"gpu_activity_identity_unverified":            "활동 자료의 GPU·Pod 신원 또는 MIG 여부가 확인되지 않아 제외했습니다.",
		"gpu_activity_missing":                        "연결은 관측됐지만 활동 자료가 없는 구간은 평균에서 제외했습니다.",
		"source_unit_unverified":                      "원본 지표의 단위를 확인하지 못했습니다.",
		"invalid_gpu_activity":                        "활동률이 유효 범위(0~100%)를 벗어났습니다.",
		"conflicting_gpu_activity":                    "같은 GPU·시간의 활동값이 충돌해 해당 구간을 제외했습니다.",
		"gpu_model_comparison_unverified":             "GPU 모델이 다르거나 확인되지 않아 평균을 보류했습니다.",
		"gpu_pod_labels_absent":                       "Namespace·Pod 라벨이 없는 GPU 관측입니다. 유휴 상태나 회수 가능 여부는 확인되지 않았습니다.",
		"gpu_inventory_missing":                       "해당 클러스터의 GPU 관측 또는 연결 집계 근거가 부족합니다.",
		"unattributed_gpu_observation":                "일부 GPU 관측을 Namespace에 연결하지 못했습니다.",
		"unsupported_group_by":                        "이 주제에서 지원하지 않는 집계 기준입니다.",
		"group_by_not_implemented":                    "선택한 집계 기준의 계산은 아직 구현되지 않았습니다.",
		"exclusive_episode_or_activity_missing":       "독점 할당 구간 또는 활동 자료가 없어 저활동 시간을 판단하지 못했습니다.",
		"multi_gpu_workload_history_missing":          "같은 작업이 여러 GPU를 사용한 이력이 없어 편차를 계산하지 못했습니다.",
		"incident_observation_denominator_missing":    "사건 발생률의 기준이 되는 관측 GPU시간이 없습니다.",
		"incident_time_mapping_missing":               "사건 당시 GPU와 작업의 연결 이력이 없습니다.",
		"verified_workload_disruption_evidence":       "작업 중단 여부를 확인할 근거가 없습니다.",
		"scheduler_capacity_binding_evidence_missing": "스케줄러의 요청·용량·배치 연결 근거가 없습니다.",
		"actual_power_original_samples_missing":       "실제 소비전력 원본 표본이 없어 에너지를 계산하지 못했습니다.",
		"performed_action_and_comparison_required":    "수행한 조치 기록과 비교 기간이 필요합니다.",
		"comparable_workload_and_causal_evidence":     "동일 조건의 작업과 조치 효과를 확인할 근거가 필요합니다.",
		"workload_purpose_unverified":                 "작업 목적을 확인하기 전까지 판단을 보류합니다.",
		"workload_exception_review":                   "초기화·체크포인트·추론 대기·예약 목적을 확인하세요.",
		"model_not_configured":                        "보고서 설명용 모델이 설정되지 않아 AI 설명을 생략했습니다.",
		"no_verified_facts":                           "설명할 수 있는 검증된 사실이 없어 AI 설명을 생략했습니다.",
		"llm_token_budget_exhausted":                  "AI 설명 입력이 허용된 토큰 예산을 초과해 모델에 요청하지 못했습니다.",
		"llm_deadline_exhausted":                      "남은 실행시간이 없어 AI 설명을 요청하지 못했습니다.",
		"llm_http_error":                              "모델 서버가 오류 응답을 반환해 AI 설명을 생성하지 못했습니다.",
		"llm_output_truncated":                        "모델 출력이 길이 제한으로 잘려 AI 설명을 사용하지 않았습니다.",
		"llm_invalid_output":                          "모델 응답이 보고서의 근거 참조 형식에 맞지 않아 사용하지 않았습니다.",
		"discovery_budget_exhausted":                  "데이터소스 탐색 횟수 제한에 도달했습니다.",
		"discovery_deadline_exhausted":                "데이터소스 탐색 중 실행시간 제한에 도달했습니다.",
		"range_budget_exhausted":                      "요청한 기간이 허용된 조회 범위를 초과했습니다.",
		"allocation_contract_missing":                 "검증된 GPU 할당 이력이 부족합니다. GPU–Pod 연결 관측만으로는 독점 할당·저활동·작업 편차를 확정하지 않습니다.",
		"allocation_mode_unverified":                  "독점·공유·MIG 할당 방식을 확인할 수 없습니다.",
		"gpu_pod_identity_missing":                    "GPU는 관측됐지만 같은 시점의 Pod 고유 ID를 연결하지 못했습니다.",
		"observed_mapping_not_exclusive_allocation":   "GPU–Pod 연결 관측 시간은 독점 할당량이나 실제 연산 시간이 아닙니다. 공유 GPU는 Namespace 간 중복될 수 있습니다.",
		"project_owner_mapping":                       "프로젝트·소유자 연결 정보가 없어 Namespace 기준으로만 표시합니다.",
		"required_data_missing":                       "이 항목의 계산에 필요한 원본 데이터 또는 식별 정보가 없습니다.",
		"MIG_history_missing":                         "MIG 인스턴스 이력이 없어 계산하지 않았습니다. MIG 미사용 여부는 확인되지 않았습니다.",
		"incomplete_observation":                      "일부 조회 결과가 제한되거나 실패했습니다. 수집 근거에서 확인할 수 있습니다.",
		"row_limit_or_source_warning":                 "조회 응답이 수집량 제한에 걸렸거나 원본에서 경고를 반환했습니다.",
		"sample_limit_exceeded":                       "최소 조회 구간에서도 수집량 제한을 초과했습니다.",
		"response_byte_limit":                         "조회 응답 크기가 제한을 초과했습니다.",
		"source_warning":                              "데이터소스가 불완전한 결과라는 경고를 반환했습니다.",
		"budget_exhausted":                            "조회 횟수 또는 실행시간 제한으로 남은 구간을 수집하지 못했습니다.",
		"query_failed":                                "데이터 조회가 실패했습니다.",
		"binding_unselected":                          "이 환경에서 사용할 데이터 binding이 선택되지 않았습니다.",
		"binding_unverified":                          "데이터 binding의 타입·단위·대상·시간 계약이 검증되지 않았습니다.",
		"binding_environment_mismatch":                "선택한 binding의 환경과 요청 클러스터가 다릅니다.",
		"binding_scope_unavailable":                   "승인된 대상 범위로 조회할 수 있는 라벨·관계가 없습니다.",
		"binding_semantics_or_samples_missing":        "검증된 단위·타입 또는 유효한 원본 표본이 부족합니다.",
		"gpu_capacity_join_unverified":                "같은 GPU의 사용량·전체 용량·단위·유효시간을 연결하지 못했습니다.",
		"optional_query_budget_exhausted":             "기존 필수 조회 예산을 보존하기 위해 추가 조회를 보류했습니다.",
		"inventory_completeness_and_change_events":    "전체 장비 목록과 변경 이력이 없어 관측된 장비만 표시합니다.",
		"expected_inventory_denominator_missing":      "전체 기대 대상 목록이 없어 전체 관측률을 계산하지 않았습니다.",
	}[reason]
	if text == "" {
		return reason
	}
	return text
}
