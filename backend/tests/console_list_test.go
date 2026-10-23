//go:build e2e

package tests

import (
	"context"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
)

func TestConsoleLists(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, err := pgxpool.New(ctx, dsn)
	must(t, err)
	defer admin.Close()
	schema := "console_" + strings.ReplaceAll(ID(), "-", "")
	_, err = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	must(t, err)
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	u, err := url.Parse(dsn)
	must(t, err)
	params := u.Query()
	params.Set("search_path", schema)
	u.RawQuery = params.Encode()
	db, err := store.Open(ctx, u.String())
	must(t, err)
	defer db.Pool.Close()
	must(t, db.Migrate(ctx))
	must(t, db.EnsureDefaults(ctx))
	_, err = db.Pool.Exec(ctx, "INSERT INTO cluster_registry(id) VALUES('cpc-1'),('cpc-2')")
	must(t, err)
	server := httptest.NewServer(api.New(db, config.Config{}))
	defer server.Close()
	scope := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": nil}}}
	other := Object{"clusters": []any{Object{"cluster_id": "cpc-2", "namespaces": nil}}}
	get := func(path string, query url.Values, status int) Object {
		t.Helper()
		return request(t, server.URL+"/api/v1"+path+"?"+query.Encode(), "GET", nil, status)
	}
	addReport := func(input, body Object, published bool, sc Object) string {
		t.Helper()
		id := ID()
		_, err := db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,created_at) VALUES($1::uuid,'report','backend',$1::text,$2,$3,'fixture','succeeded',now()+interval '1 day','2026-10-12T00:00:00Z')", id, sc, input)
		must(t, err)
		if body != nil {
			candidate := ID()
			_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,'report','1.3',$3,'stored-preview-hash','valid')", candidate, id, body)
			must(t, err)
			if published {
				_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", id, candidate)
				must(t, err)
			}
		}
		return id
	}

	t.Run("analysis_period_is_overlap_not_receipt_date", func(t *testing.T) {
		for _, period := range []Object{
			{"start": "2026-10-09T00:00:00Z", "end": "2026-10-10T00:00:00Z"},
			{"start": "2026-10-10T09:00:00+09:00", "end": "2026-10-11T09:00:00+09:00"},
			{"start": "2026-10-11T00:00:00Z", "end": "2026-10-12T00:00:00Z"},
			{"start": "not a timestamp", "end": "not a timestamp"},
			{"start": "not a timestamp", "end": "2026-10-11T00:00:00Z"},
			{"start": "2026-10-10T00:00:00Z", "end": "not a timestamp"},
			{"start": "2026-10-11T00:00:00Z", "end": "2026-10-10T00:00:00Z"},
			{},
		} {
			addReport(Object{"time_range": period, "topic_ids": []string{"PERIOD"}}, nil, false, scope)
		}
		for _, tc := range []struct {
			from, to, received string
			count              int
		}{
			{"2026-10-10T00:00:00Z", "2026-10-11T00:00:00Z", "", 1},
			{"2026-10-10T12:00:00Z", "2026-10-11T12:00:00Z", "", 2},
			{"2026-10-10T00:00:00Z", "", "", 2},
			{"", "2026-10-11T00:00:00Z", "", 2},
			{"2026-10-10T00:00:00Z", "2026-10-11T00:00:00Z", "2026-10-13T00:00:00Z", 0},
		} {
			query := url.Values{"topic_id": {"PERIOD"}, "analysis_from": {tc.from}, "analysis_to": {tc.to}, "from": {tc.received}}
			if items := get("/reports", query, 200)["items"].([]any); len(items) != tc.count {
				t.Fatalf("period %v: got %d want %d", query, len(items), tc.count)
			}
		}
		for _, query := range []url.Values{
			{"analysis_from": {"bad"}}, {"analysis_to": {"bad"}},
			{"analysis_from": {"2026-10-11T00:00:00Z"}, "analysis_to": {"2026-10-10T00:00:00Z"}},
			{"analysis_from": {"2026-10-11T00:00:00Z"}, "analysis_to": {"2026-10-11T00:00:00Z"}},
		} {
			get("/reports", query, 422)
		}
		query := url.Values{"analysis_from": {"2026-10-09T00:00:00Z"}, "limit": {"1"}}
		query.Set("cursor", String(get("/reports", query, 200), "next_cursor"))
		query.Set("analysis_from", "2026-10-10T00:00:00Z")
		get("/reports", query, 422)
		get("/jobs", url.Values{"analysis_from": {"2026-10-10T00:00:00Z"}}, 422)
	})

	t.Run("node_search_uses_stored_names_and_uids_without_current_identity", func(t *testing.T) {
		for _, sc := range []Object{scope, other} {
			addReport(Object{"target": Object{"kind": "gpu", "node": "dgx-node-07", "node_uid": "uid-07"}}, nil, false, sc)
		}
		for _, node := range []string{"dgx-node-07", "uid-07"} {
			page := get("/jobs", url.Values{"node": {node}, "scope": {jsonString(scope)}}, 200)
			if len(page["items"].([]any)) != 1 {
				t.Fatalf("node %s failed scope filtering", node)
			}
		}
		if len(get("/jobs", url.Values{"node": {"dgx-node"}}, 200)["items"].([]any)) != 0 {
			t.Fatal("node filter became fuzzy")
		}
		query := url.Values{"node": {"dgx-node-07"}, "limit": {"1"}}
		query.Set("cursor", String(get("/jobs", query, 200), "next_cursor"))
		query.Set("node", "uid-07")
		get("/jobs", query, 422)
		get("/jobs", url.Values{"node": {strings.Repeat("n", 254)}}, 422)
		get("/reports", url.Values{"node": {"dgx-node-07"}}, 422)
	})

	t.Run("unclosed_includes_old_acknowledged_and_legacy_open_cases", func(t *testing.T) {
		for _, state := range []any{"open", "acknowledged", "closed", nil} {
			_, err := db.Pool.Exec(ctx, "INSERT INTO incidents(id,cluster_id,scope,state,status,occurred_at,first_seen,created_at) VALUES($1,'cpc-1',$2,$3,'open','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')", ID(), scope, state)
			must(t, err)
		}
		query := url.Values{"status": {"unclosed"}, "scope": {jsonString(scope)}, "limit": {"2"}}
		page := get("/incidents", query, 200)
		if len(page["items"].([]any)) != 2 || String(page, "next_cursor") == "" {
			t.Fatal("unclosed pagination omitted old incidents")
		}
		query.Set("cursor", String(page, "next_cursor"))
		if len(get("/incidents", query, 200)["items"].([]any)) != 1 {
			t.Fatal("unclosed cursor lost legacy open state")
		}
		query.Set("status", "closed")
		get("/incidents", query, 422)
		query.Del("cursor")
		if len(get("/incidents", query, 200)["items"].([]any)) != 1 {
			t.Fatal("closed filter changed")
		}
		query.Set("status", "unclosed")
		query.Set("from", "2026-10-10T00:00:00Z")
		if len(get("/incidents", query, 200)["items"].([]any)) != 0 {
			t.Fatal("explicit incident period was ignored")
		}
	})

	t.Run("preview_is_bounded_published_aggregate_prose", func(t *testing.T) {
		input := Object{"topic_ids": []string{"PREVIEW"}}
		body := Object{
			"quality":       Object{"report_format": "report-aggregate-v1", "report": Object{"method": "llm_interpreted"}},
			"result_status": "partial", "narrative_status": "complete",
			"narrative":   []any{Object{"topic_id": "namespace_usage", "observation": "저장된 활동 관측", "interpretation_limit": "배타적 할당 미확인"}, Object{"topic_id": "incident_summary", "summary_text": "저장된 사건 변화", "text": "not selected"}},
			"limitations": []string{"실시간 상태 아님"},
			"topics":      []any{Object{"missing_inputs": []string{"partial_source_error"}, "rows": strings.Repeat("PRIVATE_ROWS", 100000)}},
		}
		id := addReport(input, body, true, scope)
		addReport(input, body, false, scope)
		legacy := addReport(input, Object{"narrative": body["narrative"]}, true, scope)
		malformed := addReport(input, Object{"quality": body["quality"], "narrative": "bad", "topics": "bad", "limitations": []any{Object{"secret": "PRIVATE_LIMIT"}}}, true, scope)
		large := addReport(input, Object{"quality": body["quality"], "narrative_status": "failed", "narrative": []any{Object{"text": strings.Repeat("관", 600)}, Object{"text": "two"}, Object{"text": "three"}, Object{"text": "four"}}, "limitations": []string{"1", "2", "3", "4"}, "topics": []any{Object{"missing_inputs": []string{"1", "2", "3", "4", "5", "6", "7"}}}}, true, scope)
		_, err := db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,2,'report','1.3',$3,'unpublished','valid')", ID(), id, Object{"quality": body["quality"], "narrative": []any{Object{"text": "UNPUBLISHED_TEXT"}}})
		must(t, err)
		page := get("/reports", url.Values{"topic_id": {"PREVIEW"}}, 200)
		for _, raw := range page["items"].([]any) {
			item := raw.(map[string]any)
			preview, exists := item["report_preview"].(map[string]any)
			switch item["id"] {
			case id:
				if !exists || preview["method"] != "llm_interpreted" || preview["narrative_status"] != "complete" || preview["truncated"] != false || len(preview["summaries"].([]any)) != 2 || len(preview["limitations"].([]any)) != 2 || len(preview["missing_inputs"].([]any)) != 1 {
					t.Fatalf("stored aggregate projection changed: %v", preview)
				}
				if preview["summaries"].([]any)[0].(map[string]any)["text"] != "저장된 활동 관측" {
					t.Fatal("preview did not use stored observation")
				}
			case large:
				if !exists || preview["truncated"] != true || preview["narrative_status"] != "failed" || len(preview["summaries"].([]any)) != 3 || len(preview["limitations"].([]any)) != 3 || len(preview["missing_inputs"].([]any)) != 6 || len([]rune(preview["summaries"].([]any)[0].(map[string]any)["text"].(string))) != 400 {
					t.Fatalf("preview limits not applied: %v", preview)
				}
			case malformed:
				if !exists || preview["narrative_status"] != nil || len(preview["summaries"].([]any)) != 0 || len(preview["limitations"].([]any)) != 0 {
					t.Fatal("malformed aggregate projected non-text fields")
				}
			case legacy:
				if exists {
					t.Fatal("legacy report received invented preview")
				}
			default:
				if exists {
					t.Fatal("unpublished report received preview")
				}
			}
		}
		encoded := jsonString(page)
		if len(encoded) > 14000 || strings.Contains(encoded, "PRIVATE_") || strings.Contains(encoded, "UNPUBLISHED_TEXT") || strings.Contains(encoded, "not selected") {
			t.Fatal("preview transported raw, unpublished or unbounded body")
		}
		var stored string
		must(t, db.Pool.QueryRow(ctx, "SELECT body::text FROM result_candidates WHERE id=(SELECT published_result_id FROM jobs WHERE id=$1)", id).Scan(&stored))
		if !strings.Contains(stored, "PRIVATE_ROWS") {
			t.Fatal("preview changed stored body")
		}
		for _, raw := range get("/jobs", url.Values{"topic_id": {"PREVIEW"}}, 200)["items"].([]any) {
			if raw.(map[string]any)["report_preview"] != nil {
				t.Fatal("job list unnecessarily loaded report prose")
			}
		}
		_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=NULL WHERE id=$1", id)
		must(t, err)
		_, err = db.Pool.Exec(ctx, "INSERT INTO report_deletions(job_id,deleted_at,reason,evidence_count,candidate_count) VALUES($1,now(),'fixture deletion',0,2)", id)
		must(t, err)
		for _, raw := range get("/reports", url.Values{"topic_id": {"PREVIEW"}}, 200)["items"].([]any) {
			if raw.(map[string]any)["id"] == id {
				t.Fatal("deleted report preview remained in reports")
			}
		}
	})
}
