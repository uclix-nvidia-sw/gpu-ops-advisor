//go:build e2e

package tests

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"sort"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"gpu-ops-advisor/shared/migrations"
)

func TestJobListProjection(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, err := pgxpool.New(ctx, dsn)
	must(t, err)
	defer admin.Close()
	schema := "list_" + strings.ReplaceAll(ID(), "-", "")
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
	get := func(t *testing.T, path string, status int) Object {
		t.Helper()
		return request(t, server.URL+"/api/v1"+path, "GET", nil, status)
	}
	devScope := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": []string{"dev"}}}}
	allScope := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": nil}}}
	rcaScope := Object{"clusters": []any{Object{"cluster_id": "cpc-2", "namespaces": []string{"training"}}}}
	t.Run("backend_schema_without_job_controller_columns", func(t *testing.T) {
		id := ID()
		_, err := db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at) VALUES($1,'report','backend','manual:standalone',$2,'{}','fixture','failed',now()+interval '1 day')", id, devScope)
		must(t, err)
		for _, route := range []string{"jobs", "reports"} {
			page := get(t, "/"+route, 200)
			items := page["items"].([]any)
			if len(items) != 1 || items[0].(map[string]any)["can_retry"] != false {
				t.Fatal("standalone Backend list requires optional JC columns")
			}
		}
		if len(get(t, "/analyses", 200)["items"].([]any)) != 0 {
			t.Fatal("standalone RCA list was not empty")
		}
		_, err = db.Pool.Exec(ctx, "DELETE FROM jobs WHERE id=$1", id)
		must(t, err)
	})
	_, err = db.Pool.Exec(ctx, migrations.Queue)
	must(t, err)
	incident := ID()
	_, err = db.Pool.Exec(ctx, "INSERT INTO incidents(id,cluster_id,scope) VALUES($1,'cpc-2',$2)", incident, rcaScope)
	must(t, err)
	_, err = db.Pool.Exec(ctx, "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,1,'{}','fixture')", incident)
	must(t, err)
	target := Object{"kind": "pod", "cluster_id": "cpc-1", "namespace": "dev", "pod_uid": "fixture-pod"}
	_, err = db.Pool.Exec(ctx, "INSERT INTO identity_history(id,cluster_id,relation_kind,subject_kind,subject_key,valid_from,identity_status,attributes) VALUES($1,'cpc-1','identity','pod','fixture-pod','2026-10-01T00:00:00Z','verified','{\"namespace\":\"dev\"}')", ID())
	must(t, err)
	input := Object{
		"target": target, "time_range": Object{"start": "2026-10-10T00:00:00Z", "end": "2026-10-11T00:00:00Z"},
		"timezone": "Asia/Seoul", "topic_ids": []string{"O01", "O08"}, "purpose_ids": []string{"fixture-purpose"},
		"group_by": []string{"cluster"}, "topic_group_by": Object{"O01": []string{"gpu"}, "O08": []string{"cluster", "namespace"}},
		"comparison_range": nil, "symptom": "fixture symptom", "snapshot": strings.Repeat("PRIVATE_INPUT", 4096),
	}
	largeBody := Object{"result_status": "partial", "narrative_status": "omitted", "payload": strings.Repeat("BODY_ONLY", 128*1024), "secret": "PRIVATE_RESULT"}
	fixtures := []struct {
		name, kind, status, source, origin string
		scope, input, body                 Object
		published, retry, cancel           bool
	}{
		{"manual", "report", "succeeded", "manual:fixture", "manual", devScope, input, largeBody, true, false, false},
		{"schedule", "report", "queued", "schedule:fixture", "schedule", devScope, Object{"topic_ids": []string{"O08"}}, Object{"result_status": "complete"}, false, false, true},
		{"legacy", "report", "succeeded", "legacy-fixture", "unknown", allScope, Object{}, Object{}, true, false, false},
		{"rca", "rca", "succeeded", "rca-fixture", "", rcaScope, Object{"incident_id": incident, "symptom": "fixture RCA"}, Object{"result_status": "blocked", "narrative_status": "complete"}, true, false, false},
		{"retry", "report", "failed", "manual:retry", "manual", devScope, Object{}, nil, false, true, false},
		{"budget_exhausted", "report", "failed", "manual:exhausted", "manual", devScope, Object{}, nil, false, false, false},
		{"cancel_requested", "report", "queued", "manual:cancel", "manual", devScope, Object{}, nil, false, false, false},
	}
	ids, candidates := map[string]string{}, map[string]string{}
	for _, fixture := range fixtures {
		id, source := ID(), "backend"
		var incidentID any
		if fixture.kind == "rca" {
			source, incidentID = "incident", incident
		}
		ids[fixture.name] = id
		versions := Object{"execution": Object{"attempt_budget": 100}, "snapshot": strings.Repeat("PRIVATE_VERSION", 4096)}
		_, err = db.Pool.Exec(ctx, `INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,versions,request_hash,status,stage,deadline_at,created_at,started_at,incident_id,evidence_version,attempt_no,max_attempts,token_budget,budget_used,retryable,termination_reason,queue_reason,version)
VALUES($1,$2,$3,$4,$5,$6,$7,'PRIVATE_REQUEST_HASH',$8,'collection',now()+interval '1 day','2026-10-12T00:00:00.123456Z','2026-10-12T00:00:01Z',$9,1,1,3,300,100,true,'timeout','worker_unavailable',7)`, id, fixture.kind, source, fixture.source, fixture.scope, fixture.input, versions, fixture.status, incidentID)
		must(t, err)
		if fixture.body != nil {
			candidate := ID()
			candidates[fixture.name] = candidate
			_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,$3,'1.3',$4,'fixture','valid')", candidate, id, fixture.kind, fixture.body)
			must(t, err)
			if fixture.published {
				_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", id, candidate)
				must(t, err)
			}
		}
	}
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET budget_used=300 WHERE id=$1", ids["budget_exhausted"])
	must(t, err)
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET cancel_requested_at=now() WHERE id=$1", ids["cancel_requested"])
	must(t, err)
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET created_at='2026-10-11T00:00:00Z' WHERE id=$1", ids["legacy"])
	must(t, err)
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET parent_job_id=$2 WHERE id=$1", ids["retry"], ids["manual"])
	must(t, err)
	_, err = db.Pool.Exec(ctx, "INSERT INTO job_attempts(job_id,attempt_no,started_at,stage,claim_token,remote_call_state) VALUES($1,1,now(),'collection','PRIVATE_CLAIM','unknown')", ids["manual"])
	must(t, err)
	// A later, unpublished attempt must never replace the explicitly published one.
	_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,2,'report','1.3','{\"result_status\":\"complete\",\"payload\":\"UNPUBLISHED_RESULT\"}','later','valid')", ID(), ids["manual"])
	must(t, err)

	t.Run("lists_match_detail_without_body_or_attempts", func(t *testing.T) {
		for _, route := range []string{"jobs", "reports", "analyses"} {
			page := get(t, "/"+route+"?limit=30", 200)
			items := page["items"].([]any)
			wantCount := len(fixtures)
			if route == "reports" {
				wantCount--
			} else if route == "analyses" {
				wantCount = 1
			}
			if len(items) != wantCount || page["next_cursor"] != nil {
				t.Fatalf("%s: unexpected page size/cursor", route)
			}
			for _, raw := range items {
				item := raw.(map[string]any)
				detail := get(t, "/"+route+"/"+String(item, "id"), 200)
				delete(detail, "result")
				delete(detail, "attempts")
				delete(detail, "request_id")
				if jsonString(item) != jsonString(detail) {
					t.Fatalf("%s list/detail mismatch:\nlist=%s\ndetail=%s", route, jsonString(item), jsonString(detail))
				}
				for _, fixture := range fixtures {
					if ids[fixture.name] != item["id"] {
						continue
					}
					if item["can_retry"] != fixture.retry || item["can_cancel"] != fixture.cancel {
						t.Fatalf("%s: changed command availability: %v", fixture.name, item)
					}
					if fixture.kind == "report" && item["report_origin"] != fixture.origin {
						t.Fatalf("%s: changed report origin", fixture.name)
					}
					if fixture.kind == "rca" {
						if _, present := item["report_origin"]; present {
							t.Fatal("RCA received a report origin")
						}
					}
					if fixture.published {
						if item["result_ref"] != candidates[fixture.name] || item["result_status"] != fixture.body["result_status"] || item["narrative_status"] != fixture.body["narrative_status"] {
							t.Fatalf("%s: changed publication metadata", fixture.name)
						}
					} else if item["result_ref"] != nil || item["result_status"] != "unpublished" || item["narrative_status"] != nil {
						t.Fatalf("%s: unpublished candidate exposed", fixture.name)
					}
				}
			}
			encoded := jsonString(page)
			for _, forbidden := range []string{"PRIVATE_", "BODY_ONLY", "UNPUBLISHED_RESULT", "input_snapshot", "versions", "published_result_id", "claim_token"} {
				if strings.Contains(encoded, forbidden) {
					t.Fatalf("%s list exposed %s", route, forbidden)
				}
			}
			if len(encoded) > 20000 {
				t.Fatalf("%s: large snapshots expanded the public list to %d bytes", route, len(encoded))
			}
		}
	})

	t.Run("retry_and_cancel_boundaries", func(t *testing.T) {
		for _, tc := range []struct{ name, update string }{
			{"attempts_exhausted", "attempt_no=max_attempts"},
			{"deadline_elapsed", "deadline_at=now()-interval '1 day'"},
			{"not_retryable", "retryable=false"},
			{"terminal_reason", "termination_reason='invalid_result'"},
			{"legacy_execution_missing", "versions='{}'"},
		} {
			t.Run(tc.name, func(t *testing.T) {
				_, err := db.Pool.Exec(ctx, "UPDATE jobs SET attempt_no=1,deadline_at=now()+interval '1 day',retryable=true,termination_reason='timeout',versions='{\"execution\":{\"attempt_budget\":100}}' WHERE id=$1", ids["retry"])
				must(t, err)
				_, err = db.Pool.Exec(ctx, "UPDATE jobs SET "+tc.update+" WHERE id=$1", ids["retry"])
				must(t, err)
				for _, raw := range get(t, "/reports?status=failed", 200)["items"].([]any) {
					if raw.(map[string]any)["can_retry"] != false {
						t.Fatalf("%s exposed an unavailable retry", tc.name)
					}
				}
			})
		}
		_, err := db.Pool.Exec(ctx, "UPDATE jobs SET deadline_at=now()-interval '1 day' WHERE id=$1", ids["schedule"])
		must(t, err)
		for _, raw := range get(t, "/reports?status=queued", 200)["items"].([]any) {
			if raw.(map[string]any)["can_cancel"] != false {
				t.Fatal("expired or already requested cancellation remained available")
			}
		}
	})

	t.Run("filters_and_cursor_preserve_page_membership", func(t *testing.T) {
		cases := []struct {
			name, route string
			query       url.Values
			want        []string
		}{
			{"scope", "jobs", url.Values{"scope": {jsonString(devScope)}}, []string{"manual", "schedule", "retry", "budget_exhausted", "cancel_requested"}},
			{"kind", "jobs", url.Values{"kind": {"rca"}}, []string{"rca"}},
			{"status", "reports", url.Values{"status": {"failed"}}, []string{"retry", "budget_exhausted"}},
			{"topic", "reports", url.Values{"topic_id": {"O08"}}, []string{"manual", "schedule"}},
			{"target", "reports", url.Values{"target": {jsonString(target)}}, []string{"manual"}},
			{"date", "reports", url.Values{"from": {"2026-10-11T00:00:00Z"}, "to": {"2026-10-12T00:00:00Z"}}, []string{"legacy"}},
			{"incident", "analyses", url.Values{"incident_id": {incident}}, []string{"rca"}},
			{"combined", "jobs", url.Values{"scope": {jsonString(devScope)}, "kind": {"report"}, "status": {"succeeded"}, "topic_id": {"O08"}, "target": {jsonString(target)}, "from": {"2026-10-12T00:00:00Z"}, "to": {"2026-10-13T00:00:00Z"}}, []string{"manual"}},
			{"empty", "reports", url.Values{"topic_id": {"O11"}}, nil},
		}
		for _, tc := range cases {
			t.Run(tc.name, func(t *testing.T) {
				page := get(t, "/"+tc.route+"?"+tc.query.Encode(), 200)
				got := []string{}
				for _, raw := range page["items"].([]any) {
					got = append(got, String(raw.(map[string]any), "id"))
				}
				want := []string{}
				for _, name := range tc.want {
					want = append(want, ids[name])
				}
				sort.Strings(got)
				sort.Strings(want)
				if strings.Join(got, ",") != strings.Join(want, ",") || page["next_cursor"] != nil {
					t.Fatalf("filter %s: got %v want %v", tc.name, got, want)
				}
			})
		}
		full := get(t, "/jobs?limit=30", 200)["items"].([]any)
		tiedIDs := []string{}
		for name, id := range ids {
			if name != "legacy" {
				tiedIDs = append(tiedIDs, id)
			}
		}
		sort.Sort(sort.Reverse(sort.StringSlice(tiedIDs)))
		orderedIDs := append(tiedIDs, ids["legacy"])
		for i, raw := range full {
			if String(raw.(map[string]any), "id") != orderedIDs[i] {
				t.Fatal("list changed created_at DESC/id DESC ordering")
			}
		}
		got := []any{}
		query := url.Values{"limit": {"2"}}
		for i := 0; ; i++ {
			if i >= len(fixtures) {
				t.Fatal("cursor did not terminate")
			}
			page := get(t, "/jobs?"+query.Encode(), 200)
			items := page["items"].([]any)
			if len(items) > 2 {
				t.Fatal("limit+1 probe row leaked into the page")
			}
			got = append(got, items...)
			cursor := String(page, "next_cursor")
			if cursor == "" {
				break
			}
			if i == 0 {
				get(t, "/jobs?kind=rca&cursor="+url.QueryEscape(cursor), 422)
			}
			query.Set("cursor", cursor)
		}
		if jsonString(got) != jsonString(full) {
			t.Fatal("same-timestamp pagination omitted, duplicated, or reordered jobs")
		}
	})

	t.Run("large_published_body_remains_available_only_in_detail_and_exports", func(t *testing.T) {
		detail := get(t, "/reports/"+ids["manual"], 200)
		body := detail["result"].(map[string]any)
		if body["payload"] != largeBody["payload"] || body["secret"] != nil || len(detail["attempts"].([]any)) != 1 {
			t.Fatal("detail lost or exposed stored result/attempt fields")
		}
		for _, format := range []string{"html", "csv"} {
			resp, err := http.Get(server.URL + "/api/v1/reports/" + ids["manual"] + "/export?format=" + format)
			must(t, err)
			data, err := io.ReadAll(resp.Body)
			resp.Body.Close()
			must(t, err)
			if resp.StatusCode != 200 || !strings.Contains(string(data), "BODY_ONLY") || strings.Contains(string(data), "PRIVATE_RESULT") {
				t.Fatalf("%s export did not preserve the sanitized published body", format)
			}
		}
		get(t, "/reports/"+ids["schedule"]+"/export?format=html", 409)
	})

	t.Run("publication_requires_candidate_id_job_and_kind", func(t *testing.T) {
		badJob, wrongKind := ID(), ID()
		_, err := db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,created_at) VALUES($1::uuid,'report','backend',$1::text,$2,'{\"topic_ids\":[\"BAD\"]}','fixture','succeeded',now()+interval '1 day','2026-10-10T00:00:00Z')", badJob, devScope)
		must(t, err)
		_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,'rca','1.3','{\"result_status\":\"complete\"}','fixture','valid')", wrongKind, badJob)
		must(t, err)
		for _, tc := range []struct{ name, candidate string }{{"missing", ID()}, {"different_job", candidates["manual"]}, {"different_kind", wrongKind}} {
			t.Run(tc.name, func(t *testing.T) {
				_, err := db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", badJob, tc.candidate)
				must(t, err)
				for _, route := range []string{"jobs", "reports"} {
					get(t, "/"+route+"?topic_id=BAD", 404)
					get(t, "/"+route+"/"+badJob, 404)
				}
				// The extra pagination probe is not part of this page and must not be hydrated.
				page := get(t, "/jobs?limit=7", 200)
				if len(page["items"].([]any)) != 7 || page["next_cursor"] == nil {
					t.Fatal("invalid candidate outside the requested page changed its contents")
				}
			})
		}
	})
}
