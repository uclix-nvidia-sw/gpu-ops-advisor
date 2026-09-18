package api

import (
	"encoding/csv"
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestReportDownloadRendersMetricsAndEscapesUntrustedFields(t *testing.T) {
	var body Object
	err := json.Unmarshal([]byte(`{"result_status":"partial","topics":[{"metrics":[{"id":"O02.mapped_gpu_hours","target":{"namespace":"=CMD()"},"value":1.5,"unit":"<script>alert(1)</script>","method":"observed_gpu_pod_interval_union","quality":{},"evidence_refs":["e1"]},{"id":"O02.allocated_gpu_hours","value":null,"quality":{"reason":"required_data_missing"}}],"missing_inputs":["observed_mapping_not_exclusive_allocation"]}],"limitations":["<script>bad</script>"]}`), &body)
	if err != nil {
		t.Fatal(err)
	}
	metrics := reportMetrics(body)
	if len(metrics) != 2 {
		t.Fatalf("metrics: %v", metrics)
	}
	html := httptest.NewRecorder()
	if err := exportMetrics(html, "report-id", "html", body, metrics); err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"<table>", "GPU–Pod 연결 관측 시간", "1.5", "산출 불가", "독점 할당량이나 실제 연산 시간이 아닙니다", "&lt;script&gt;"} {
		if !strings.Contains(html.Body.String(), expected) {
			t.Errorf("missing %q", expected)
		}
	}
	if strings.Contains(html.Body.String(), "<script>") {
		t.Fatal("unescaped HTML")
	}
	out := httptest.NewRecorder()
	if err := exportMetrics(out, "report-id", "csv", body, metrics); err != nil {
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
