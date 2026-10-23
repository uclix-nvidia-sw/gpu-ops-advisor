package api

import (
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAdviceExportGroupsWithoutChangingStoredResponse(t *testing.T) {
	var body Object
	if err := json.Unmarshal([]byte(`{"kind":"report","versions":{"criteria":"report-aggregate-v1"},"narrative":[{"topic_id":"namespace_usage","text":"stored original","advice":[{"fact_id":"a","kind":"capacity_review","target":{"cluster_id":"cpc-1","namespace":"batch"},"summary":"exact AI sentence","period":{"start":"2026-10-22T00:00:00Z","end":"2026-10-22T03:00:00Z"}},{"fact_id":"b","kind":"queue_review","target":{"cluster_id":"cpc-1","namespace":"research"}},{"fact_id":"c","kind":"batch_progress","target":{"cluster_id":"cpc-1","namespace":"batch"}},{"fact_id":"d","kind":"resident_memory","target":{"cluster_id":"cpc-2","namespace":"batch"}}]},{"topic_id":"incident_summary","title":"Incident","text":"unchanged incident"}],"measurements":[{"id":"O08.test","value":8,"unit":"events"}]}`), &body); err != nil {
		t.Fatal(err)
	}
	original, _ := json.Marshal(body)
	out := httptest.NewRecorder()
	if err := exportMetrics(out, "id", "html", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	page := out.Body.String()
	for needle, count := range map[string]int{`class="ops-advice-cluster"`: 2, `class="ops-advice-namespace"`: 3, `<article data-advice-id=`: 4} {
		if strings.Count(page, needle) != count {
			t.Fatalf("%s: wrong group count", needle)
		}
	}
	if strings.Index(page, `data-advice-id="c"`) > strings.Index(page, `data-advice-id="b"`) {
		t.Fatal("nonadjacent same Namespace advice not grouped")
	}
	for _, want := range []string{`class="ops-advice-card-title">AI 운영 해석</h4>`, `대상 클러스터 :</span> <code>cpc-1</code>`, "exact AI sentence", "stored original", "unchanged incident", "2026. 10. 22. 09:00 ~ 12:00 KST"} {
		if !strings.Contains(page, want) {
			t.Fatal("missing", want)
		}
	}
	current, _ := json.Marshal(body)
	if string(current) != string(original) {
		t.Fatal("stored response mutated")
	}
	csv := httptest.NewRecorder()
	if err := exportMetrics(csv, "id", "csv", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	delete(body, "narrative")
	plain := httptest.NewRecorder()
	if err := exportMetrics(plain, "id", "csv", body, reportMetrics(body), nil); err != nil {
		t.Fatal(err)
	}
	if csv.Body.String() != plain.Body.String() {
		t.Fatal("advice changed CSV")
	}
}

func TestAdviceExportKindsTimeAndEscaping(t *testing.T) {
	for kind, title := range adviceTitles {
		t.Run(kind, func(t *testing.T) {
			period := Object{"start": "2026-10-22T11:00:00Z", "end": "2026-10-22T15:00:00Z"}
			item := Object{"kind": kind, "summary": "<script>bad</script>", "target": Object{"cluster_id": "<cluster>", "namespace": "<namespace>"}, "period": period, "reference_period": period, "observed_periods": []any{period, period}, "evidence_refs": []any{"<source>"}, "gpu_models": []any{"<model>", 7, ""}}
			body := Object{"versions": Object{"criteria": AggregateReportVersion}, "narrative": []any{Object{"topic_id": "namespace_usage", "advice": []any{item}}}}
			out := httptest.NewRecorder()
			if err := exportMetrics(out, "id", "html", body, nil, nil); err != nil {
				t.Fatal(err)
			}
			page := out.Body.String()
			for _, want := range []string{adviceColors[kind], title, adviceBases[kind], `class="ops-advice-heading"`, `class="ops-advice-model"`, "GPU 모델 · &lt;model&gt;", "&lt;cluster&gt;", "&lt;namespace&gt;", "&lt;script&gt;", "&lt;source&gt;", "2026. 10. 22. 20:00 ~ 2026. 10. 23. 00:00 KST"} {
				if !strings.Contains(page, want) {
					t.Fatal("missing", want)
				}
			}
			article := page[strings.Index(page, "<article"):]
			if strings.Index(article, "&lt;script&gt;") > strings.Index(article, "<dl>") || strings.Index(article, adviceBases[kind]) < strings.Index(article, "<details>") {
				t.Fatal("advice body must precede metadata; generic basis belongs in details")
			}
			if strings.Contains(page, "<script>") {
				t.Fatal("unescaped HTML")
			}
			if strings.Contains(page, "<dt>비교 구간</dt>") != (kind == "relative_activity") {
				t.Fatal("invented or missing comparison")
			}
			if kind == "repeated_activity" && !strings.Contains(page, "관측 구간 2") {
				t.Fatal("separate observations lost")
			}
		})
	}
	for _, p := range []any{nil, Object{}, Object{"start": "bad"}, Object{"start": "2026-10-22T00:00:00", "end": "2026-10-22T01:00:00"}, Object{"start": "2026-10-22T01:00:00Z", "end": "2026-10-22T00:00:00Z"}} {
		if adviceTime(p) != "시간 범위 미확인" {
			t.Fatal("invalid period accepted")
		}
	}
}

func TestAdviceExportMissingTargetsAndLegacy(t *testing.T) {
	body := Object{"versions": Object{"criteria": AggregateReportVersion}, "narrative": []any{Object{"topic_id": "namespace_usage", "text": "old text", "advice": []any{Object{}, Object{}}}}}
	view := reportNarrative(body)
	if len(view[0]["advice_groups"].([]adviceCluster)) != 2 {
		t.Fatal("unknown targets merged")
	}
	body["versions"] = Object{"criteria": "1.3"}
	if reportNarrative(body)[0]["advice_groups"] != nil {
		t.Fatal("legacy/RCA presentation changed")
	}
}

func TestAdviceExportNameOrderKeepsStoredInnerOrder(t *testing.T) {
	items := []any{}
	for _, v := range [][3]string{{"cpc-2", "zebra", "c2"}, {"cpc-1", "zebra", "z-first"}, {"cpc-1", "alpha", "alpha"}, {"cpc-1", "zebra", "a-last"}, {"cpc-1", "", "unknown-ns"}, {"", "", "unknown-cluster"}} {
		items = append(items, Object{"fact_id": v[2], "target": Object{"cluster_id": v[0], "namespace": v[1]}})
	}
	body := Object{"versions": Object{"criteria": AggregateReportVersion}, "narrative": []any{Object{"topic_id": "namespace_usage", "advice": items}}}
	before, _ := json.Marshal(body)
	groups := reportNarrative(body)[0]["advice_groups"].([]adviceCluster)
	if len(groups) != 3 || groups[0].Cluster != "cpc-1" || groups[1].Cluster != "cpc-2" || groups[2].Cluster != "" {
		t.Fatal("cluster name order changed")
	}
	ns := groups[0].Namespaces
	if len(ns) != 3 || ns[0].Namespace != "alpha" || ns[1].Namespace != "zebra" || ns[2].Namespace != "" {
		t.Fatal("Namespace name order changed")
	}
	if len(ns[1].Advice) != 2 || ns[1].Advice[0].ID != "z-first" || ns[1].Advice[1].ID != "a-last" {
		t.Fatal("stored inner order changed")
	}
	after, _ := json.Marshal(body)
	if string(before) != string(after) {
		t.Fatal("stored response mutated")
	}
}

func TestAggregateDocumentTitleUsesAnalysisDate(t *testing.T) {
	for _, v := range [][3]string{
		{"2026-10-21T15:00:00Z", "2026-10-22T15:00:00Z", "2026년 10월 22일"},
		{"2026-10-15T15:00:00Z", "2026-10-22T15:00:00Z", "2026년 10월 16일 ~ 2026년 10월 22일"},
		{"invalid", "invalid", ""},
	} {
		body := Object{"versions": Object{"criteria": AggregateReportVersion}, "time_range": Object{"start": v[0], "end": v[1]}, "created_at": "2026-10-23T04:00:00Z"}
		want := "GPU 클러스터 운영 분석 보고서"
		if v[2] != "" {
			want = v[2] + " " + want
		}
		if got := reportDocumentTitle(body); got != want {
			t.Fatalf("got %q, want %q", got, want)
		}
	}
	if reportDocumentTitle(Object{}) != "GPU 운영 보고서" {
		t.Fatal("legacy title changed")
	}
}
