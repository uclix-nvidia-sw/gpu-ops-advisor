package api

import (
	"encoding/csv"
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
)

func TestOptionalBindingMetricsExportKeepsZeroAndMissingDistinct(t *testing.T) {
	for _, suffix := range []string{"", ".0", ".17"} {
		t.Run("suffix="+suffix, func(t *testing.T) {
			body := Object{"topics": []any{Object{"metrics": []any{
				Object{"id": "O01.gpu_memory_free_mean" + suffix, "value": 0, "unit": "MiB", "quality": Object{"optional": true}},
				Object{"id": "O01.gpu_memory_used_ratio" + suffix, "value": nil, "unit": "ratio", "quality": Object{"optional": true, "reason": "gpu_capacity_join_unverified"}},
				Object{"id": "O01.node_cpu_used_mean" + suffix, "value": 25, "unit": "percent"},
				Object{"id": "O01.node_load_by_window" + suffix, "value": 1.25, "unit": "load"},
			}}}}
			html := httptest.NewRecorder()
			metrics := reportMetrics(body)
			if err := exportMetrics(html, "binding-fixture", "html", body, metrics, nil); err != nil {
				t.Fatal(err)
			}
			for _, want := range []string{"평균 GPU 메모리 여유량", "GPU 메모리 용량 대비 사용 비율", "평균 Node CPU 사용률", "시간창별 Node load 평균", "산출 불가", "유효시간을 연결하지 못했습니다"} {
				if !strings.Contains(html.Body.String(), want) {
					t.Errorf("missing %s", want)
				}
			}
			out := httptest.NewRecorder()
			if err := exportMetrics(out, "binding-fixture", "csv", body, metrics, nil); err != nil {
				t.Fatal(err)
			}
			rows, err := csv.NewReader(strings.NewReader(strings.TrimPrefix(out.Body.String(), "\ufeff"))).ReadAll()
			if err != nil || len(rows) != 5 {
				t.Fatalf("CSV: %v %v", rows, err)
			}
			for i, value := range []string{"0", "산출 불가", "25", "1.25"} {
				if rows[i+1][0] != String(metrics[i], "id") || rows[i+1][2] != value || rows[i+1][3] != String(metrics[i], "unit") {
					t.Errorf("CSV changed stored ID/value/unit: %v", rows[i+1])
				}
			}
		})
	}
}

func TestReportDownloadRendersMetricsAndEscapesUntrustedFields(t *testing.T) {
	var body Object
	err := json.Unmarshal([]byte(`{"result_status":"partial","topics":[{"metrics":[{"id":"O02.mapped_gpu_hours","target":{"namespace":"=CMD()"},"value":1.5,"unit":"<script>alert(1)</script>","method":"observed_gpu_pod_interval_union","quality":{},"evidence_refs":["e1"]},{"id":"O02.allocated_gpu_hours","value":null,"quality":{"reason":"allocation_contract_missing"}}],"missing_inputs":["observed_mapping_not_exclusive_allocation"]}],"limitations":["<script>bad</script>"]}`), &body)
	if err != nil {
		t.Fatal(err)
	}
	metrics := reportMetrics(body)
	body["narrative"] = []any{Object{"title": "분석 범위와 결과", "text": "<script>report</script>"}}
	if len(metrics) != 2 {
		t.Fatalf("metrics: %v", metrics)
	}
	html := httptest.NewRecorder()
	if err := exportMetrics(html, "report-id", "html", body, metrics, nil); err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"최종 보고서", "분석 범위와 결과", "기본 보고서", "<table>", "GPU–Pod 연결 관측 시간", "검증된 GPU 할당 이력이 부족합니다", "1.5", "산출 불가", "독점 할당량이나 실제 연산 시간이 아닙니다", "&lt;script&gt;"} {
		if !strings.Contains(html.Body.String(), expected) {
			t.Errorf("missing %q", expected)
		}
	}
	if strings.Contains(html.Body.String(), "<script>") {
		t.Fatal("unescaped HTML")
	}
	out := httptest.NewRecorder()
	if err := exportMetrics(out, "report-id", "csv", body, metrics, nil); err != nil {
		t.Fatal(err)
	}
	rows, err := csv.NewReader(strings.NewReader(strings.TrimPrefix(out.Body.String(), "\ufeff"))).ReadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 3 || rows[1][1] != "'=CMD()" || rows[1][2] != "1.5" || rows[2][2] != "산출 불가" {
		t.Fatalf("invalid CSV: %v", rows)
	}
}

func TestNamespaceExportPreservesRawCSVAndFormatsHTML(t *testing.T) {
	var body Object
	if err := json.Unmarshal([]byte(`{"versions":{"criteria":"1.2"},"quality":{"requested_group_by":["namespace"],"narrative_reason":"llm_http_error"},"topics":[{"metrics":[{"id":"O01.vram.0","value":3145728,"unit":"bytes"},{"id":"O08.namespace_connected_gpu_util.0","value":0,"unit":"percent","target":{"cluster_id":"cpc-1","namespace":"test"}},{"id":"O08.namespace_connected_gpu_util.1","value":null,"unit":"percent","quality":{"reason":"shared_gpu_attribution_unverified"}}]}]}`), &body); err != nil {
		t.Fatal(err)
	}
	html := httptest.NewRecorder()
	if err := exportMetrics(html, "fixture", "html", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"연결 GPU 평균 활동률", "3.000", "MiB", "산출 불가", "Namespace의 실제 소비량", "모델 서버가 오류 응답", "1.2"} {
		if !strings.Contains(html.Body.String(), expected) {
			t.Errorf("missing %s", expected)
		}
	}
	csv := httptest.NewRecorder()
	if err := exportMetrics(csv, "fixture", "csv", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(csv.Body.String(), ",bytes,") {
		t.Fatal("CSV raw unit changed")
	}
	rawValue := strings.Split(strings.Split(csv.Body.String(), "\r\n")[1], ",")[2]
	value, err := strconv.ParseFloat(rawValue, 64)
	if err != nil || value != 3145728 {
		t.Fatal("CSV raw value changed", rawValue)
	}
}

func TestNamespaceTimeMeaningAndRawPrecision(t *testing.T) {
	var body Object
	if err := json.Unmarshal([]byte(`{"result_status":"partial","topics":[{"missing_inputs":["unattributed_gpu_observation"],"metrics":[{"id":"O08.namespace_connected_gpu_count.0","value":8,"unit":"physical_gpu"},{"id":"O08.observed_namespace_hours.0","value":7.9864155557420515,"unit":"GPU-hours"}]}]}`), &body); err != nil {
		t.Fatal(err)
	}
	html := httptest.NewRecorder()
	if err := exportMetrics(html, "fixture", "html", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"기간 중 연결이 확인된 GPU", "8대가 각각 1시간", "GPU·시간", "동시 사용 대수가 아닙니다"} {
		if !strings.Contains(html.Body.String(), want) {
			t.Errorf("missing %q", want)
		}
	}
	if strings.Index(html.Body.String(), "일부 GPU 관측") > strings.Index(html.Body.String(), "<h2>주요 수치") {
		t.Fatal("limitations hidden after metrics")
	}
	out := httptest.NewRecorder()
	if err := exportMetrics(out, "fixture", "csv", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.Body.String(), ",7.9864155557420515,GPU-hours,") {
		t.Fatal("CSV precision or raw unit changed")
	}
}

func TestClusterObservationExportKeepsZeroUnknownAndLabels(t *testing.T) {
	var body Object
	if err := json.Unmarshal([]byte(`{"topics":[{"metrics":[{"id":"O08.cluster_observed_gpu_count.0","target":{"cluster_id":"cpc-2"},"value":8,"unit":"physical_gpu"},{"id":"O08.cluster_connected_gpu_count.0","target":{"cluster_id":"cpc-2"},"value":0,"unit":"physical_gpu"},{"id":"O08.cluster_unlabeled_gpu_count.0","target":{"cluster_id":"cpc-2"},"value":8,"quality":{"reason":"gpu_pod_labels_absent"}},{"id":"O08.cluster_connected_gpu_hours.1","target":{"cluster_id":"cpc-3"},"value":null,"quality":{"reason":"gpu_inventory_missing"}}]}]}`), &body); err != nil {
		t.Fatal(err)
	}
	w := httptest.NewRecorder()
	if err := exportMetrics(w, "fixture", "html", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"클러스터 관측 GPU", "클러스터 연결 확인 GPU", "<td>0</td>", "산출 불가", "Pod 연결 라벨 없는 GPU", "유휴 상태나 회수 가능 여부는 확인되지", "cpc-2", "cpc-3"} {
		if !strings.Contains(w.Body.String(), want) {
			t.Fatalf("missing %s", want)
		}
	}
	w = httptest.NewRecorder()
	if err := exportMetrics(w, "fixture", "csv", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(w.Body.String(), "O08.cluster_connected_gpu_count.0,cpc-2,0,physical_gpu") {
		t.Fatal(w.Body.String())
	}
}

func TestNamespaceMissingInputsHaveReadableDownloadReasons(t *testing.T) {
	for code, want := range map[string]string{
		"namespace_current_attribution_missing": "현재 기간에 선택 범위의 Namespace 귀속 GPU 관측이 없습니다.",
		"namespace_observations_missing":        "Namespace 관측 자료가 없습니다.",
	} {
		t.Run(code, func(t *testing.T) {
			body := Object{"topics": []any{Object{"missing_inputs": []any{code}}}}
			out := httptest.NewRecorder()
			if err := exportMetrics(out, "missing-namespace", "html", body, nil, nil); err != nil {
				t.Fatal(err)
			}
			html := out.Body.String()
			if !strings.Contains(html, "<li>"+want+"</li>") || strings.Contains(html, "<li>"+code+"</li>") {
				t.Fatalf("untranslated limitation: %s", html)
			}
			if !strings.Contains(html, code) {
				t.Fatal("stored raw reason was lost")
			}
		})
	}
}

func TestPartialInterpretationHTMLKeepsAIAndLabelsCalculatedFallback(t *testing.T) {
	body := Object{
		"narrative_status": "failed",
		"quality":          Object{"report": Object{"method": "partial_interpretation"}},
		"narrative": []any{
			Object{"topic_id": "namespace_usage", "title": "Namespace AI 운영 해석", "text": "채택된 AI 문장을 보존합니다."},
			Object{"topic_id": "incident_summary", "title": "장애 알림 · 계산 결과 요약", "text": "저장된 사건 집계입니다.", "interpretation_source": "deterministic_fallback"},
		},
	}
	w := httptest.NewRecorder()
	if err := exportMetrics(w, "partial-fixture", "html", body, nil, nil); err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"일부 주제의 AI 해석을 작성하지 못했습니다", "채택된 AI 문장을 보존합니다.", "장애 알림 · 계산 결과 요약", "저장된 사건 집계입니다."} {
		if !strings.Contains(w.Body.String(), want) {
			t.Fatalf("missing partial interpretation content: %s", want)
		}
	}
	if strings.Contains(w.Body.String(), "LLM 편집을 사용하지 못한 기본 보고서") {
		t.Fatal("partial AI success described as a fully calculated report")
	}
}

func TestAggregateReportLimitationsFollowNarrativeAndPrecedeMetrics(t *testing.T) {
	body := Object{"result_status": "partial", "limitations": []any{"부분 관측 안내"},
		"narrative": []any{map[string]any{"title": "계산 결과 요약", "text": "보고서 본문"}}}
	out := httptest.NewRecorder()
	if err := exportMetrics(out, "preview", "html", body, nil, nil); err != nil {
		t.Fatal(err)
	}
	text := out.Body.String()
	narrative := strings.Index(text, "<h2>최종 보고서</h2>")
	limits := strings.Index(text, "<h2>아직 판단할 수 없는 내용·해석 제한</h2>")
	metrics := strings.Index(text, "<h2>주요 수치</h2>")
	if narrative < 0 || limits <= narrative || metrics <= limits {
		t.Fatal("unexpected report section order")
	}
}
