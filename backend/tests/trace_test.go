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
	"gpu-ops-advisor/shared/migrations"
)

func TestStoredWebTrace(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, e := pgxpool.New(ctx, dsn)
	must(t, e)
	defer admin.Close()
	schema := "trace_" + strings.ReplaceAll(ID(), "-", "")
	_, e = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	must(t, e)
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	u, e := url.Parse(dsn)
	must(t, e)
	params := u.Query()
	params.Set("search_path", schema)
	u.RawQuery = params.Encode()
	db, e := store.Open(ctx, u.String())
	must(t, e)
	defer db.Pool.Close()
	must(t, db.Migrate(ctx))
	must(t, db.EnsureDefaults(ctx))
	server := httptest.NewServer(api.New(db, config.Config{}))
	defer server.Close()
	get := func(path string, status int) Object {
		t.Helper()
		return request(t, server.URL+"/api/v1"+path, "GET", nil, status)
	}
	scope := Object{"clusters": []any{Object{"cluster_id": "fixture", "namespaces": nil}}}
	report := ID()
	_, e = db.Pool.Exec(ctx, `INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at) VALUES($1,'report','backend','manual:trace',$2,'{"topic_ids":["O08"]}','x','queued',now()+interval '1 day')`, report, scope)
	must(t, e)
	unavailable := get("/jobs/"+report+"/trace", 200)
	if jsonString(unavailable["incident_snapshot"]) != `{"record":null,"state":"schema_unavailable"}` {
		t.Fatal(unavailable)
	}
	_, e = db.Pool.Exec(ctx, migrations.Queue)
	must(t, e)
	_, e = db.Pool.Exec(ctx, migrations.Incident)
	must(t, e)
	incident, job, receipt, event, outbox := ID(), ID(), ID(), ID(), ID()
	_, e = db.Pool.Exec(ctx, `INSERT INTO incidents(id,cluster_id,scope,evidence_version) VALUES($1,'fixture',$2,99)`, incident, scope)
	must(t, e)
	input := Object{"incident_id": incident, "target": Object{"alertname": "Synthetic", "machine_id": "node-1"}, "time_range": Object{"end": "2026-09-30T08:07:48.122307Z"}, "Authorization": "SECRET"}
	_, e = db.Pool.Exec(ctx, `INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,2,$2,'pinned'),($1,99,'{"newer":true}','latest')`, incident, Object{"input": input})
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,incident_id,evidence_version,attempt_no) VALUES($1,'rca','incident','trace-source',$2,$3,'x','succeeded',now()+interval '1 day',$4,2,2)`, job, scope, input, incident)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO enqueue_outbox(id,source_module,source_key,kind,input_snapshot,request_hash,status,dispatch_deadline,job_id) VALUES($1,'incident','trace-source','rca',$2,'x','accepted',now(),$3)`, outbox, Object{"input": input}, job)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO incident_webhook_receipts(id,source,body_hash,raw_payload,received_at,response,http_status) VALUES($1,'fixture','h','{"Authorization":"SECRET"}',now(),'{}',202)`, receipt)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO alert_events(id,source,cluster_id,status,payload_hash,raw_payload,observed_at,receipt_id,alert_index,incident_id,disposition) VALUES($1,'fixture','fixture','firing','h','{"labels":{"machine_id":"node-1","api_key":"SECRET"}}',now(),$2,0,$3,'recorded')`, event, receipt, incident)
	must(t, e)
	candidate := ID()
	_, e = db.Pool.Exec(ctx, `INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,2,'rca','1.3','{"private":"PRIVATE_BODY"}','hash','valid')`, candidate, job)
	must(t, e)
	trace := get("/jobs/"+job+"/trace", 200)
	serialized := jsonString(trace)
	if strings.Contains(serialized, "SECRET") || strings.Contains(serialized, "PRIVATE_BODY") || strings.Contains(serialized, "newer") || !strings.Contains(serialized, ".122307Z") || !strings.Contains(serialized, "node-1") || !strings.Contains(serialized, "accepted") {
		t.Fatal(trace)
	}
	pinned := trace["incident_snapshot"].(map[string]any)["record"].(map[string]any)
	if Number(pinned, "revision") != 2 {
		t.Fatal(pinned)
	}
	_, e = db.Pool.Exec(ctx, `UPDATE jobs SET published_result_id=$1 WHERE id=$2`, candidate, job)
	must(t, e)
	published := get("/jobs/"+job+"/trace", 200)
	if !strings.Contains(jsonString(published["publication"]), candidate) || strings.Contains(jsonString(published), "PRIVATE_BODY") {
		t.Fatal(published)
	}
	ids := []string{ID(), ID(), ID()}
	for i, id := range ids {
		attempt := 1
		if i == 2 {
			attempt = 2
		}
		_, e = db.Pool.Exec(ctx, `INSERT INTO evidence(id,job_id,attempt_no,scope,query_id,tool_status,input,snapshot) VALUES($1,$2,$3,$4,'D05','partial','{"logql":"{cluster_id=fixture}","startRfc3339":"2026-09-30T08:07:48.122Z","Authorization":"SECRET","endpoint":"SECRET"}','{"rows":["Healthy","Unhealthy"],"password":"SECRET"}')`, id, job, attempt, scope)
		must(t, e)
	}
	first := get("/jobs/"+job+"/evidence?attempt=1&limit=1", 200)
	cursor := String(first, "next_cursor")
	if cursor == "" {
		t.Fatal(first)
	}
	second := get("/jobs/"+job+"/evidence?attempt=1&limit=1&cursor="+url.QueryEscape(cursor), 200)
	if len(first["items"].([]any)) != 1 || len(second["items"].([]any)) != 1 || second["next_cursor"] != nil {
		t.Fatal(first, second)
	}
	get("/jobs/"+job+"/evidence?attempt=2&cursor="+url.QueryEscape(cursor), 422)
	get("/jobs/"+job+"/evidence?attempt=-1", 422)
	get("/jobs/"+job+"/evidence?limit=201", 422)
	get("/jobs/"+report+"/evidence/"+ids[0]+"?attempt=1", 404)
	get("/jobs/"+job+"/evidence/"+ids[0]+"?attempt=2", 404)
	detail := get("/jobs/"+job+"/evidence/"+ids[0]+"?attempt=1", 200)
	if strings.Contains(jsonString(detail), "SECRET") || !strings.Contains(jsonString(detail), "logql") || !strings.Contains(jsonString(detail), "Unhealthy") {
		t.Fatal(detail)
	}
	get("/jobs/"+ID()+"/trace", 404)
	get("/jobs/"+job+"/trace?sql=anything", 422)
	_, e = db.Pool.Exec(ctx, `INSERT INTO manual_report_intents(source_key,request_hash,envelope) VALUES('manual:trace','x','{"input":{"topic_ids":["O08"]}}')`)
	must(t, e)
	manual := get("/jobs/"+report+"/trace", 200)
	if !strings.Contains(jsonString(manual["manual_request"]), "O08") {
		t.Fatal(manual)
	}
	schedule, occurrence := ID(), ID()
	_, e = db.Pool.Exec(ctx, `INSERT INTO schedules(id,enabled,current_revision,effective_at,next_run_at) VALUES($1,true,9,now(),now())`, schedule)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO schedule_revisions(schedule_id,revision,frequency,local_time,timezone,period,report_spec,enabled,effective_at) VALUES($1,2,'daily','09:00','Asia/Seoul','previous_day','{"topic_ids":["O08"]}',true,now())`, schedule)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `INSERT INTO schedule_occurrences(id,schedule_id,revision,scheduled_for,period_start,period_end,canonical,status,job_id) VALUES($1,$2,2,now(),now()-interval '1 day',now(),true,'accepted',$3)`, occurrence, schedule, report)
	must(t, e)
	scheduled := get("/jobs/"+report+"/trace", 200)["schedule"].(map[string]any)["record"].(map[string]any)
	if Number(scheduled["revision"].(map[string]any), "revision") != 2 {
		t.Fatal(scheduled)
	}
	empty := get("/jobs/"+report+"/evidence?attempt=0", 200)
	if len(empty["items"].([]any)) != 0 {
		t.Fatal(empty)
	}
}
