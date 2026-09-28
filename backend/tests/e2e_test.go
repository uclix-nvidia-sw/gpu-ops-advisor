//go:build e2e

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// Real HTTP and PostgreSQL. JC is a commit-capable contract fixture, not an Agent implementation.
func TestBackendE2E(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, e := pgxpool.New(ctx, dsn)
	must(t, e)
	defer admin.Close()
	schema := "e2e_" + strings.ReplaceAll(ID(), "-", "")
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
	must(t, db.Seed(ctx))
	must(t, db.Migrate(ctx))
	fixture := &controller{db: db}
	jc := httptest.NewServer(fixture)
	defer jc.Close()
	cfg := config.Config{Modules: map[string]string{"job_controller": jc.URL}, SchedulerEnabled: true}
	handler := api.New(db, cfg)
	server := httptest.NewServer(handler)
	defer func() { server.Close() }()
	call := func(method, path string, b any, status int, headers ...string) Object {
		t.Helper()
		return request(t, server.URL+"/api/v1"+path, method, b, status, headers...)
	}
	sc := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": []string{"dev"}}}}
	report := func() Object {
		return Object{"scope": sc, "time_range": Object{"start": "2026-09-15T00:00:00+09:00", "end": "2026-09-16T00:00:00+09:00"}, "timezone": "Asia/Seoul", "topic_ids": []string{"O11", "O02"}, "group_by": []string{"cluster"}}
	}
	var reportID string
	t.Run("new_contract_and_removed_routes", func(t *testing.T) {
		call("GET", "/health/ready", nil, 200)
		for _, p := range []string{"/me", "/conversations", "/settings/C07", "/settings/access-grants"} {
			call("GET", p, nil, 404)
		}
		call("POST", "/analyses", Object{}, 404)
		call("POST", "/webhooks/grafana/a", Object{}, 404)
		var auth bool
		must(t, db.Pool.QueryRow(ctx, "SELECT to_regclass('access_grants') IS NOT NULL").Scan(&auth))
		if auth {
			t.Fatal("product authentication tables created")
		}
		call("POST", "/reports", report(), 422)
		for _, scope := range []Object{{"clusters": []any{}}, {"clusters": []any{Object{"cluster_id": "unknown", "namespaces": nil}}}, {"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": nil}, Object{"cluster_id": "cpc-1", "namespaces": nil}}}} {
			b := report()
			b["scope"] = scope
			call("POST", "/reports", b, 422, "Idempotency-Key", ID())
		}
		b := report()
		b["time_range"] = Object{"start": "2026-09-16T00:00:00Z", "end": "2026-09-15T00:00:00Z"}
		call("POST", "/reports", b, 422, "Idempotency-Key", ID())
	})
	t.Run("JC_commit_lost_response_stable_input_and_report_only_commands", func(t *testing.T) {
		fixture.lose.Store(true)
		call("POST", "/reports", report(), 503, "Idempotency-Key", "manual-lost")
		first := call("POST", "/reports", report(), 202, "Idempotency-Key", "manual-lost")
		reportID = String(first, "job_id")
		equivalent := report()
		equivalent["topic_ids"] = []string{"O02", "O11"}
		equivalent["time_range"] = Object{"start": "2026-09-14T15:00:00Z", "end": "2026-09-15T15:00:00Z"}
		again := call("POST", "/reports", equivalent, 202, "Idempotency-Key", "manual-lost")
		if again["job_id"] != reportID || first["report_id"] != reportID {
			t.Fatal("duplicate report")
		}
		different := report()
		different["topic_ids"] = []string{"O01"}
		call("POST", "/reports", different, 409, "Idempotency-Key", "manual-lost")
		job := call("GET", "/jobs/"+reportID, nil, 200)
		if job["status"] != "queued" || job["queue_reason"] != "worker_unavailable" {
			t.Fatal(job)
		}
		call("POST", "/jobs/"+reportID+"/cancel", Object{"reason": "test"}, 200, "Idempotency-Key", "cancel", "If-Match", "1")
		call("POST", "/jobs/"+reportID+"/cancel", Object{"reason": "test"}, 200, "Idempotency-Key", "cancel", "If-Match", "1")
		call("POST", "/jobs/"+reportID+"/cancel", Object{"reason": "changed"}, 409, "Idempotency-Key", "cancel", "If-Match", "1")
		rca := ID()
		_, e = db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at) VALUES($1::uuid,'rca','incident',$1::text,$2,'{}','x','queued',now()+interval '1 day')", rca, sc)
		must(t, e)
		call("POST", "/jobs/"+rca+"/retry", Object{"reason": "test"}, 409, "Idempotency-Key", "rca-retry", "If-Match", "1")
		job = call("GET", "/jobs/"+rca, nil, 200)
		if job["can_retry"] != false || job["can_cancel"] != false {
			t.Fatal(job)
		}
		page := call("GET", "/jobs?limit=1", nil, 200)
		cursor := url.QueryEscape(String(page, "next_cursor"))
		call("GET", "/jobs?limit=1&cursor="+cursor, nil, 200)
		call("GET", "/jobs?kind=report&cursor="+cursor, nil, 422)
	})
	t.Run("only_published_candidate_and_safe_export_survive_restart", func(t *testing.T) {
		candidate := ID()
		body := Object{"result_status": "partial", "narrative_status": "omitted", "note": "<script>alert(1)</script>", "formula": "=1+1",
			"topics": []any{Object{"topic_id": "O02", "metrics": []any{Object{"id": "O02.mapped_gpu_hours", "value": 1.5, "unit": "GPU-hours", "method": "observed_gpu_pod_interval_union", "target": Object{"namespace": "=1+1"}, "quality": Object{}}}}}}
		_, e = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,'report','1.3',$3,'hash','valid')", candidate, reportID, body)
		must(t, e)
		job := call("GET", "/reports/"+reportID, nil, 200)
		if job["result"] != nil || job["result_status"] != "unpublished" {
			t.Fatal("candidate leaked")
		}
		call("GET", "/reports/"+reportID+"/export?format=html", nil, 409)
		// Test fixture acts as JC publication; Backend never performs this update.
		_, e = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2,status='succeeded' WHERE id=$1", reportID, candidate)
		must(t, e)
		server.Close()
		server = httptest.NewServer(api.New(db, cfg))
		job = call("GET", "/reports/"+reportID, nil, 200)
		if job["result_ref"] != candidate {
			t.Fatal(job)
		}
		for _, format := range []string{"html", "csv"} {
			resp, e := http.Get(server.URL + "/api/v1/reports/" + reportID + "/export?format=" + format)
			must(t, e)
			data, e := io.ReadAll(resp.Body)
			resp.Body.Close()
			must(t, e)
			if resp.StatusCode != 200 {
				t.Fatal(string(data))
			}
			if format == "html" && strings.Contains(string(data), "<script>") {
				t.Fatal("HTML injection")
			}
			if format == "html" && !strings.Contains(string(data), "<table>") {
				t.Fatal("report metrics were not rendered")
			}
			if format == "csv" && !strings.Contains(string(data), "'=1+1") {
				t.Fatal("CSV formula injection")
			}
		}
	})
	t.Run("native_receipts_knowledge_hash_and_immutable_revision", func(t *testing.T) {
		b := Object{"knowledge_key": "e2e", "kind": "runbook", "visibility": "common", "content": Object{"text": "check facts"}}
		first := call("POST", "/knowledge", b, 201, "Idempotency-Key", "draft")
		again := call("POST", "/knowledge", b, 201, "Idempotency-Key", "draft")
		if first["id"] != again["id"] {
			t.Fatal("duplicate native write")
		}
		path := "/knowledge/" + String(first, "knowledge_id") + "/revisions/1"
		for i, action := range []string{"request", "approve"} {
			call("POST", path+"/review", Object{"action": action, "comment": "verified"}, 200, "Idempotency-Key", action, "If-Match", fmt.Sprint(i+1))
		}
		call("POST", path+"/review", Object{"action": "approve", "comment": "verified"}, 200, "Idempotency-Key", "approve", "If-Match", "2")
		_, e = db.Pool.Exec(ctx, "UPDATE knowledge_revisions SET reviewed_content_hash='wrong' WHERE id=$1", first["id"])
		must(t, e)
		call("POST", path+"/publish", Object{}, 409, "Idempotency-Key", "publish", "If-Match", "3")
		_, e = db.Pool.Exec(ctx, "UPDATE knowledge_revisions SET reviewed_content_hash=content_hash WHERE id=$1", first["id"])
		must(t, e)
		call("POST", path+"/publish", Object{}, 200, "Idempotency-Key", "publish", "If-Match", "3")
		call("PATCH", path, Object{"content": Object{"text": "replace"}}, 409, "Idempotency-Key", "edit", "If-Match", "4")
	})
	t.Run("v1_runbook_draft_binding_publish_search_and_retire", func(t *testing.T) {
		raw, err := os.ReadFile("../../rcca-agent/runbooks/sxid/RB-SXID-11001.json")
		must(t, err)
		var b Object
		must(t, json.Unmarshal(raw, &b))
		first := call("POST", "/knowledge", b, 201, "Idempotency-Key", "sxid-draft")
		path := "/knowledge/" + String(first, "knowledge_id") + "/revisions/1"
		call("POST", path+"/review", Object{"action": "request", "comment": "fixture review"}, 200, "Idempotency-Key", "sxid-request", "If-Match", "1")
		call("POST", path+"/review", Object{"action": "approve", "comment": "unbound"}, 422, "Idempotency-Key", "sxid-reject", "If-Match", "2")
		call("PATCH", path, Object{"compatibility": Object{"cluster_id": "cpc-1"}}, 200, "Idempotency-Key", "sxid-bind", "If-Match", "2")
		call("POST", path+"/review", Object{"action": "request", "comment": "fixture binding"}, 200, "Idempotency-Key", "sxid-request-bound", "If-Match", "3")
		call("POST", path+"/review", Object{"action": "approve", "comment": "fixture-only verification"}, 200, "Idempotency-Key", "sxid-approve", "If-Match", "4")
		published := call("POST", path+"/publish", Object{}, 200, "Idempotency-Key", "sxid-publish", "If-Match", "5")
		if String(published, "state") != "published" || String(published, "content_hash") != String(published, "reviewed_content_hash") {
			t.Fatal("invalid publication")
		}
		found := call("GET", "/knowledge?kind=runbook&code=sxid%3A11001", nil, 200)
		if len(found["items"].([]any)) != 1 {
			t.Fatal("v1 code lookup failed")
		}
		wrong := call("GET", "/knowledge?kind=runbook&code=xid%3A11001", nil, 200)
		if len(wrong["items"].([]any)) != 0 {
			t.Fatal("code namespaces mixed")
		}
		call("PATCH", path, Object{"content": Object{"schema": "bad"}}, 409, "Idempotency-Key", "sxid-immutable", "If-Match", "6")
		call("POST", path+"/retire", Object{"reason": "fixture complete"}, 200, "Idempotency-Key", "sxid-retire", "If-Match", "6")
		next := call("POST", "/knowledge/"+String(first, "knowledge_id")+"/revisions", b, 201, "Idempotency-Key", "sxid-next")
		if Number(next, "revision") != 2 || String(next, "state") != "draft" {
			t.Fatal("new revision did not preserve draft lifecycle")
		}
	})
	t.Run("replica_safe_schedule_outbox_recovery_and_revision", func(t *testing.T) {
		template := report()
		delete(template, "time_range")
		delete(template, "timezone")
		schedule := call("POST", "/schedules", Object{"frequency": "daily", "local_time": "09:00", "timezone": "Asia/Seoul", "period": "previous_complete_day", "enabled": true, "report_spec": template}, 201, "Idempotency-Key", "schedule")
		id := String(schedule, "id")
		due := time.Now().UTC().Add(-time.Minute)
		_, e = db.Pool.Exec(ctx, "UPDATE schedules SET next_run_at=$2 WHERE id=$1", id, due)
		must(t, e)
		var wg sync.WaitGroup
		errs := make(chan error, 2)
		for i := 0; i < 2; i++ {
			wg.Add(1)
			go func() { defer wg.Done(); errs <- api.New(db, cfg).GenerateOccurrences(ctx) }()
		}
		wg.Wait()
		close(errs)
		for e := range errs {
			must(t, e)
		}
		var count int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM schedule_occurrences WHERE schedule_id=$1", id).Scan(&count))
		if count != 1 {
			t.Fatalf("duplicate occurrence %d", count)
		}
		occurrences := call("GET", "/schedules/"+id+"/occurrences", nil, 200)
		occ := occurrences["items"].([]any)[0].(map[string]any)
		if occ["status"] != "pending" {
			t.Fatal(occ)
		}
		fixture.lose.Store(true)
		must(t, handler.DeliverPending(ctx))
		// Force delivery deadline after JC commit whose response was lost: receipt must win over expiry.
		_, e = db.Pool.Exec(ctx, "UPDATE enqueue_outbox SET dispatch_deadline=now()-interval '1 second',next_retry_at=now() WHERE id=$1", occ["outbox_id"])
		must(t, e)
		must(t, api.New(db, cfg).DeliverPending(ctx))
		occurrences = call("GET", "/schedules/"+id+"/occurrences", nil, 200)
		occ = occurrences["items"].([]any)[0].(map[string]any)
		if occ["status"] != "accepted" || occ["job_id"] == nil {
			t.Fatal(occ)
		}
		call("PATCH", "/schedules/"+id, Object{"enabled": false}, 200, "Idempotency-Key", "pause", "If-Match", "1")
		call("PATCH", "/schedules/"+id, Object{"enabled": false}, 200, "Idempotency-Key", "pause", "If-Match", "1")
		current := call("GET", "/schedules/"+id, nil, 200)
		if Number(current, "revision") != 2 {
			t.Fatal(current)
		}
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM schedule_revisions WHERE schedule_id=$1", id).Scan(&count))
		if count != 2 {
			t.Fatal("revision overwritten")
		}
		occurrences = call("GET", "/schedules/"+id+"/occurrences", nil, 200)
		if occurrences["items"].([]any)[0].(map[string]any)["status"] != "accepted" {
			t.Fatal("pause cancelled accepted job")
		}
	})

	t.Run("calendar_catchup_limits_duplicates_and_pending_delivery_during_pause", func(t *testing.T) {
		template := report()
		delete(template, "time_range")
		delete(template, "timezone")
		b := Object{"frequency": "daily", "local_time": "09:00", "timezone": "UTC", "period": "previous_complete_day", "enabled": true, "report_spec": template}
		schedule := call("POST", "/schedules", b, 201, "Idempotency-Key", "backlog")
		id := String(schedule, "id")
		midnight := time.Now().UTC().Truncate(24 * time.Hour)
		_, e = db.Pool.Exec(ctx, "UPDATE schedules SET next_run_at=$2 WHERE id=$1", id, midnight.AddDate(0, 0, -5).Add(9*time.Hour))
		must(t, e)
		limited := api.New(db, config.Config{Modules: cfg.Modules, MaxCatchup: 2, CatchupWindow: 72 * time.Hour})
		must(t, limited.GenerateOccurrences(ctx))
		var pending, missed int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FILTER(WHERE status='pending'),count(*) FILTER(WHERE status='missed') FROM schedule_occurrences WHERE schedule_id=$1", id).Scan(&pending, &missed))
		if pending != 2 || missed < 2 {
			t.Fatalf("catchup pending=%d missed=%d", pending, missed)
		}
		var latest time.Time
		must(t, db.Pool.QueryRow(ctx, "SELECT max(scheduled_for) FROM schedule_occurrences WHERE schedule_id=$1", id).Scan(&latest))
		_, e = db.Pool.Exec(ctx, "UPDATE schedules SET next_run_at=$2 WHERE id=$1", id, latest.Add(time.Minute))
		must(t, e)
		must(t, limited.GenerateOccurrences(ctx))
		var duplicates int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM schedule_occurrences WHERE schedule_id=$1 AND reason='already_reserved_period' AND NOT canonical AND canonical_occurrence_id IS NOT NULL", id).Scan(&duplicates))
		if duplicates != 1 {
			t.Fatal("canonical period not reserved")
		}
		call("PATCH", "/schedules/"+id, Object{"enabled": false}, 200, "Idempotency-Key", "pause-backlog", "If-Match", "1")
		must(t, limited.DeliverPending(ctx))
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM schedule_occurrences WHERE schedule_id=$1 AND status='accepted'", id).Scan(&pending))
		if pending != 2 {
			t.Fatal("pause blocked pending delivery")
		}
	})
	t.Run("model_revisions_routing_secret_ref_and_action_label", func(t *testing.T) {
		cfg.ModelHosts = []string{"127.0.0.1:19999"}
		server.Close()
		server = httptest.NewServer(api.New(db, cfg))
		minimal := Object{"endpoint_url": "http://127.0.0.1:19999/v1", "model_name": "minimal-model"}
		created := call("POST", "/models", minimal, 201, "Idempotency-Key", "minimal-model")
		if created["name"] != "minimal-model" || created["limits_profile_id"] != "C07" || created["enabled"] != true {
			t.Fatal("minimal model defaults missing", created)
		}
		if caps, ok := created["capabilities"].(map[string]any); !ok || len(caps) != 0 {
			t.Fatal("default capabilities must be empty")
		}
		for _, key := range []string{"artifact_revision", "engine_revision", "precision"} {
			if _, exists := created[key]; exists {
				t.Fatal("unspecified model metadata fabricated", key)
			}
		}
		if again := call("POST", "/models", minimal, 201, "Idempotency-Key", "minimal-model"); again["id"] != created["id"] {
			t.Fatal("minimal registration is not idempotent")
		}
		invalidValues := Object{"endpoint_url": "https://unapproved.example/v1", "model_name": "", "artifact_revision": 12, "capabilities": nil, "limits_profile_id": "missing", "secret_ref": "raw-key-must-not-be-stored"}
		for key, invalid := range invalidValues {
			body := Object{"endpoint_url": minimal["endpoint_url"], "model_name": minimal["model_name"]}
			body[key] = invalid
			call("POST", "/models", body, 422, "Idempotency-Key", ID())
		}
		profile := Object{"name": "model-e2e", "endpoint_url": "http://127.0.0.1:19999/v1", "model_name": "test", "artifact_revision": "r1", "engine_revision": "e1", "precision": "fp16", "secret_ref": "env:LLM_API_KEY", "capabilities": Object{}, "limits_profile_id": "C07"}
		model := call("POST", "/models", profile, 201, "Idempotency-Key", "model-create")
		id := String(model, "id")
		if model["secret_ref"] != "env:LLM_API_KEY" {
			t.Fatal("secret ref omitted")
		}
		routes := call("GET", "/model-routes", nil, 200)
		call("PATCH", "/model-routes", Object{"report": Object{"model_id": id, "model_revision": 1}}, 200, "Idempotency-Key", "route", "If-Match", fmt.Sprint(Number(routes, "version")))
		call("PATCH", "/models/"+id, Object{"enabled": false}, 409, "Idempotency-Key", "disable", "If-Match", "1")
		updated := call("PATCH", "/models/"+id, Object{"artifact_revision": "r2"}, 200, "Idempotency-Key", "model-revision", "If-Match", "1")
		if updated["engine_revision"] != "e1" || updated["precision"] != "fp16" || updated["secret_ref"] != "env:LLM_API_KEY" {
			t.Fatal("optional metadata or secret reference lost on edit")
		}
		var revisions int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM profile_revisions WHERE profile_id=$1", id).Scan(&revisions))
		if revisions != 2 {
			t.Fatal("model revision overwritten")
		}
		routes = call("GET", "/model-routes", nil, 200)
		if Number(routes["report"].(map[string]any), "model_revision") != 1 {
			t.Fatal("route silently switched revision")
		}
		call("PATCH", "/model-routes", Object{"assistant": nil}, 422, "Idempotency-Key", "assistant", "If-Match", fmt.Sprint(Number(routes, "version")))
		call("PATCH", "/settings/C02", Object{"replicas": 100}, 422, "Idempotency-Key", "replicas", "If-Match", "1")
		_, e = db.Pool.Exec(ctx, "INSERT INTO identity_history(id,cluster_id,relation_kind,subject_key,subject_kind,valid_from,identity_status,attributes) VALUES($1,'cpc-1','inventory','pod-test','pod',now()-interval '1 day','verified','{\"namespace\":\"dev\"}')", ID())
		must(t, e)
		action := Object{"subject_type": "job", "subject_id": reportID, "kind": "action", "occurred_at": time.Now().UTC().Format(time.RFC3339), "performed_by": "operator input", "action_summary": "checked manually", "target": Object{"kind": "pod", "cluster_id": "cpc-1", "namespace": "dev", "pod_uid": "pod-test"}}
		record := call("POST", "/reviews", action, 201, "Idempotency-Key", "action")
		if record["body"].(map[string]any)["performed_by_verified"] != false {
			t.Fatal("unverified action label missing")
		}
	})
	t.Run("read_adapters_registered_scope_and_dependency_outage", func(t *testing.T) {
		params := url.Values{"scope": {jsonString(sc)}, "time_range": {jsonString(report()["time_range"])}}
		call("GET", "/dashboard?"+params.Encode(), nil, 200)
		call("GET", "/assets?"+params.Encode(), nil, 200)
		call("GET", "/workloads?"+params.Encode(), nil, 200)
		call("GET", "/observation-quality?"+params.Encode(), nil, 200)
		call("GET", "/incidents", nil, 200)
		call("GET", "/procedures", nil, 200)
		outage := httptest.NewServer(api.New(db, config.Config{}))
		defer outage.Close()
		request(t, outage.URL+"/api/v1/reports", "POST", report(), 503, "Idempotency-Key", "outage")
	})
}

type controller struct {
	db   *store.Store
	lose atomic.Bool
}

func (f *controller) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var b Object
	_ = json.NewDecoder(r.Body).Decode(&b)
	if r.Method == "GET" && strings.HasPrefix(r.URL.Path, "/internal/v1/receipts/backend/") {
		key := strings.TrimPrefix(r.URL.Path, "/internal/v1/receipts/backend/")
		v, e := store.One(ctx, f.db.Pool, "SELECT jsonb_build_object('job_id',id,'kind',kind,'status',status,'version',version) FROM jobs WHERE source_module='backend' AND source_key=$1", key)
		if e != nil {
			respond(w, 404, Object{"error": Object{"code": "not_found"}})
			return
		}
		respond(w, 200, v)
		return
	}
	if r.URL.Path == "/internal/v1/jobs/report" {
		if b["contract_version"] != "1.3" || b["source_module"] != "backend" || b["kind"] != "report" || b["execution_profile_revision"] == nil || b["delegation"] != nil {
			respond(w, 422, Object{"error": Object{"code": "invalid_input"}})
			return
		}
		var result Object
		e := f.db.Transaction(ctx, func(tx pgx.Tx) error {
			var hash string
			err := tx.QueryRow(ctx, "SELECT request_hash FROM jobs WHERE source_module='backend' AND source_key=$1", b["source_key"]).Scan(&hash)
			if err == nil {
				if hash != Hash(b) {
					return Fail(409, "idempotency_conflict", "input changed")
				}
			} else if err == pgx.ErrNoRows {
				input, _ := b["input"].(map[string]any)
				_, err = tx.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,queue_reason,deadline_at) VALUES($1,'report','backend',$2,$3,$4,$5,'queued','worker_unavailable',$6)", ID(), b["source_key"], input["scope"], input, Hash(b), b["deadline_at"])
				if err != nil {
					return err
				}
			} else {
				return err
			}
			result, err = store.One(ctx, tx, "SELECT jsonb_build_object('job_id',id,'kind',kind,'status',status,'version',version) FROM jobs WHERE source_module='backend' AND source_key=$1", b["source_key"])
			return err
		})
		if e != nil {
			respond(w, 409, Object{"error": Object{"code": "idempotency_conflict", "message": e.Error()}})
			return
		}
		if f.lose.Swap(false) {
			respond(w, 503, Object{"error": Object{"code": "dependency_unavailable"}})
			return
		}
		respond(w, 202, result)
		return
	}
	if r.Method == "POST" && strings.HasSuffix(r.URL.Path, "/cancel") {
		parts := strings.Split(r.URL.Path, "/")
		id := parts[len(parts)-2]
		key := r.Header.Get("Idempotency-Key")
		operation := "fixture-cancel:" + id
		input, _ := b["input"].(map[string]any)
		var result Object
		err := f.db.Transaction(ctx, func(tx pgx.Tx) error {
			var hash string
			e := tx.QueryRow(ctx, "SELECT request_hash,response FROM backend_receipts WHERE operation=$1 AND key=$2", operation, key).Scan(&hash, &result)
			if e == nil {
				if hash != Hash(input) {
					return Fail(409, "idempotency_conflict", "different")
				}
				return nil
			}
			if e != pgx.ErrNoRows {
				return e
			}
			job, e := store.One(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id::text=$1", id)
			if e != nil {
				return e
			}
			if fmt.Sprint(Number(job, "version")) != strings.Trim(r.Header.Get("If-Match"), "\\\"") {
				return Fail(409, "version_conflict", "version")
			}
			_, e = tx.Exec(ctx, "UPDATE jobs SET status='cancelled',version=version+1 WHERE id::text=$1", id)
			if e != nil {
				return e
			}
			result = Object{"id": id, "status": "cancelled", "version": Number(job, "version") + 1}
			_, e = tx.Exec(ctx, "INSERT INTO backend_receipts(operation,key,request_hash,status,response) VALUES($1,$2,$3,200,$4)", operation, key, Hash(input), result)
			return e
		})
		if err != nil {
			respond(w, 409, Object{"error": Object{"code": "idempotency_conflict", "message": err.Error()}})
			return
		}
		respond(w, 200, result)
		return
	}
	respond(w, 200, Object{"status": "ok"})
}
func jsonString(v any) string { b, _ := json.Marshal(v); return string(b) }
func respond(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
func request(t *testing.T, u, method string, b any, status int, headers ...string) Object {
	t.Helper()
	data, _ := json.Marshal(b)
	r, e := http.NewRequest(method, u, bytes.NewReader(data))
	must(t, e)
	r.Header.Set("Content-Type", "application/json")
	for i := 0; i < len(headers); i += 2 {
		r.Header.Set(headers[i], headers[i+1])
	}
	resp, e := http.DefaultClient.Do(r)
	must(t, e)
	defer resp.Body.Close()
	data, e = io.ReadAll(resp.Body)
	must(t, e)
	if resp.StatusCode != status {
		t.Fatalf("%s %s: got %d want %d: %s", method, u, resp.StatusCode, status, data)
	}
	if status == http.StatusNoContent {
		return nil
	}
	var out Object
	must(t, json.Unmarshal(data, &out))
	return out
}
func must(t *testing.T, e error) {
	t.Helper()
	if e != nil {
		t.Fatal(e)
	}
}
