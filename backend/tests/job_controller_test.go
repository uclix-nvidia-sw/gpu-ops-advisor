//go:build e2e

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	jc "gpu-ops-advisor/job-controller/controller"
	"gpu-ops-advisor/shared/migrations"
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

// Real Backend + real JC over HTTP and real PostgreSQL. Only the Agent/LLM is a protocol driver.
func TestRealJobController(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, e := pgxpool.New(ctx, dsn)
	must(t, e)
	defer admin.Close()
	schema := "jc_e2e_" + strings.ReplaceAll(ID(), "-", "")
	_, e = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	must(t, e)
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	u, e := url.Parse(dsn)
	must(t, e)
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	db, e := store.Open(ctx, u.String())
	must(t, e)
	defer db.Pool.Close()
	must(t, db.Migrate(ctx))
	must(t, db.Seed(ctx))
	cfg := jc.DefaultConfig()
	attemptBudget := cfg.Execution["local-v1"].AttemptBudget
	controller, e := jc.New(db.Pool, cfg)
	must(t, e)
	// Upgrade an actual pre-runbook worker constraint, retaining its existing row.
	for _, migration := range []string{migrations.Queue, migrations.WorkerContracts} {
		_, e = db.Pool.Exec(ctx, migration)
		must(t, e)
	}
	oldBoot := ID()
	_, e = db.Pool.Exec(ctx, "INSERT INTO workers(worker_id,boot_id,kind,profile_id,last_seen_at) VALUES('upgrade-fixture',$1,'rca','rca-v1',now())", oldBoot)
	must(t, e)
	must(t, controller.Prepare(ctx, false))
	must(t, controller.Prepare(ctx, false))
	_, e = db.Pool.Exec(ctx, `UPDATE workers SET supported_contract_versions='["1.3","1.4","1.5"]' WHERE worker_id='upgrade-fixture' AND boot_id=$1`, oldBoot)
	must(t, e)
	_, e = db.Pool.Exec(ctx, `UPDATE workers SET supported_contract_versions='["1.6"]' WHERE worker_id='upgrade-fixture'`)
	if e == nil {
		t.Fatal("unsupported worker contract accepted after upgrade")
	}
	_, e = db.Pool.Exec(ctx, "DELETE FROM workers WHERE worker_id='upgrade-fixture'")
	must(t, e)
	var lose atomic.Bool
	queue := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/internal/v1/jobs/report" && lose.Swap(false) {
			rec := httptest.NewRecorder()
			controller.ServeHTTP(rec, r)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(503)
			_, _ = io.WriteString(w, `{"error":{"code":"lost_response"}}`)
			return
		}
		controller.ServeHTTP(w, r)
	}))
	defer queue.Close()
	backend := api.New(db, config.Config{Modules: map[string]string{"job_controller": queue.URL}, SchedulerEnabled: true})
	web := httptest.NewServer(backend)
	defer web.Close()
	activeTest := t
	call := func(path string, b any, status int) Object {
		activeTest.Helper()
		method := "POST"
		if b == nil {
			method = "GET"
		}
		return request(activeTest, queue.URL+"/internal/v1"+path, method, b, status)
	}
	apiCall := func(method, path string, b any, status int, h ...string) Object {
		activeTest.Helper()
		return request(activeTest, web.URL+"/api/v1"+path, method, b, status, h...)
	}
	exec := func(sql string, args ...any) {
		activeTest.Helper()
		_, err := db.Pool.Exec(ctx, sql, args...)
		must(activeTest, err)
	}
	reset := func() {
		exec("TRUNCATE jobs,workers RESTART IDENTITY CASCADE")
		exec("UPDATE capacity_state SET last_granted_kind=NULL")
	}
	scope := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": []string{"dev"}}}}
	input := func() Object {
		return Object{"scope": scope, "time_range": Object{"start": "2026-09-15T00:00:00Z", "end": "2026-09-16T00:00:00Z"}, "timezone": "Asia/Seoul", "topic_ids": []string{"O02"}, "group_by": []string{"cluster"}}
	}
	submit := func() string {
		activeTest.Helper()
		v := apiCall("POST", "/reports", input(), 202, "Idempotency-Key", ID())
		return String(v, "job_id")
	}
	worker := func(kind string) Object {
		activeTest.Helper()
		b := Object{"worker_id": ID(), "boot_id": ID(), "kind": kind, "capacity_profile_id": kind + "-v1"}
		call("/workers/register", b, 200)
		delete(b, "capacity_profile_id")
		return b
	}
	finish := func(cl Object) {
		activeTest.Helper()
		call("/jobs/"+String(cl, "job_id")+"/fail", Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "code": "insufficient_data", "retryable": false, "remote_call_state": "not_started"}, 200)
	}
	candidate := func(cl Object) Object {
		activeTest.Helper()
		body := Object{"result_status": "complete", "narrative_status": "available", "summary": "E2E protocol fixture, not an actual analysis", "sections": []any{}}
		cid := ID()
		hash := Hash(body)
		exec("INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,$3,$4,'1.3',$5,$6,'valid')", cid, cl["job_id"], cl["attempt_no"], cl["kind"], body, hash)
		return Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "candidate_id": cid, "content_hash": hash}
	}
	t.Run("backend_receipt_cancel_and_conflict", func(t *testing.T) {
		activeTest = t
		reset()
		lose.Store(true)
		apiCall("POST", "/reports", input(), 503, "Idempotency-Key", "lost")
		accepted := apiCall("POST", "/reports", input(), 202, "Idempotency-Key", "lost")
		id := String(accepted, "job_id")
		v := apiCall("GET", "/jobs/"+id, nil, 200)
		if v["queue_reason"] != "worker_unavailable" {
			t.Fatalf("queue: %v", v)
		}
		modified := input()
		modified["topic_ids"] = []string{"O03"}
		apiCall("POST", "/reports", modified, 409, "Idempotency-Key", "lost")
		r := call("/receipts/backend/manual:lost", nil, 200)
		if r["job_id"] != id {
			t.Fatal(r)
		}
		headers := []string{"If-Match", fmt.Sprint(Number(v, "version")), "Idempotency-Key", "cancel"}
		a := apiCall("POST", "/jobs/"+id+"/cancel", Object{"reason": "E2E"}, 200, headers...)
		b := apiCall("POST", "/jobs/"+id+"/cancel", Object{"reason": "E2E"}, 200, headers...)
		if a["version"] != b["version"] || b["status"] != "cancelled" {
			t.Fatal(a, b)
		}
		apiCall("POST", "/jobs/"+id+"/cancel", Object{"reason": "different"}, 409, headers...)
		apiCall("GET", "/service-status", nil, 200)
	})
	t.Run("twenty_concurrent_claims_single_owner_and_publication", func(t *testing.T) {
		activeTest = t
		reset()
		id := submit()
		w := worker("report")
		raw, _ := json.Marshal(w)
		var wg sync.WaitGroup
		var wins atomic.Int32
		var mu sync.Mutex
		var claimed Object
		errs := make(chan string, 20)
		for i := 0; i < 20; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				resp, err := http.Post(queue.URL+"/internal/v1/claims", "application/json", bytes.NewReader(raw))
				if err != nil {
					errs <- err.Error()
					return
				}
				defer resp.Body.Close()
				if resp.StatusCode == 200 {
					var obj Object
					if json.NewDecoder(resp.Body).Decode(&obj) != nil {
						errs <- "decode"
						return
					}
					wins.Add(1)
					mu.Lock()
					claimed = obj
					mu.Unlock()
				} else if resp.StatusCode != 204 {
					body, _ := io.ReadAll(resp.Body)
					errs <- string(body)
				}
			}()
		}
		wg.Wait()
		close(errs)
		for err := range errs {
			t.Error(err)
		}
		if wins.Load() != 1 {
			t.Fatalf("owners=%d", wins.Load())
		}
		if claimed["job_id"] != id {
			t.Fatal(claimed)
		}
		done := candidate(claimed)
		wrong := Object{}
		for k, v := range done {
			wrong[k] = v
		}
		wrong["content_hash"] = "wrong"
		call("/jobs/"+id+"/complete", wrong, 422)
		a := call("/jobs/"+id+"/complete", done, 200)
		b := call("/jobs/"+id+"/complete", done, 200)
		if a["published_result_id"] != b["published_result_id"] || a["version"] != b["version"] {
			t.Fatal(a, b)
		}
		call("/jobs/"+id+"/complete", wrong, 409)
		view := apiCall("GET", "/reports/"+id, nil, 200)
		if view["result"] == nil {
			t.Fatal("published result not exposed", view)
		}
		_, err := db.Pool.Exec(ctx, "UPDATE result_candidates SET body='{}' WHERE id=$1", done["candidate_id"])
		if err == nil {
			t.Fatal("published result mutated")
		}
	})
	t.Run("cancel_wins_late_complete_and_remote_confirmation", func(t *testing.T) {
		activeTest = t
		reset()
		id := submit()
		w := worker("report")
		cl := call("/claims", w, 200)
		done := candidate(cl)
		job := apiCall("GET", "/jobs/"+id, nil, 200)
		apiCall("POST", "/jobs/"+id+"/cancel", Object{"reason": "E2E cancellation"}, 200, "Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(job, "version")))
		call("/jobs/"+id+"/complete", done, 409)
		hb := Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "stage": "stopping", "remote_call_state": "running"}
		v := call("/jobs/"+id+"/heartbeat", hb, 200)
		if v["cancel_requested"] != true {
			t.Fatal(v)
		}
		call("/jobs/"+id+"/fail", Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "code": "cancelled", "retryable": false, "remote_call_state": "terminated"}, 200)
		v = apiCall("GET", "/jobs/"+id, nil, 200)
		if v["status"] != "cancelled" {
			t.Fatal(v)
		}
	})
	t.Run("lease_quarantine_restart_stale_attempt_retry_budget", func(t *testing.T) {
		activeTest = t
		reset()
		id := submit()
		w := worker("report")
		cl := call("/claims", w, 200)
		done := candidate(cl)
		exec("UPDATE job_attempts SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id=$1", id)
		must(t, controller.Sweep(ctx))
		call("/jobs/"+id+"/complete", done, 409)
		exec("UPDATE jobs SET eligible_at=clock_timestamp()-interval '1 second' WHERE id=$1", id)
		call("/claims", w, 204)
		job := apiCall("GET", "/jobs/"+id, nil, 200)
		if job["queue_reason"] != "inference_quarantined" {
			t.Fatal(job)
		}
		must(t, controller.ReleaseQuarantine(ctx, id, 1, "E2E remote endpoint verified terminated"))
		cl2 := call("/claims", w, 200)
		if Number(cl2, "attempt_no") != 2 || cl2["claim_token"] == cl["claim_token"] {
			t.Fatal(cl2)
		}
		call("/jobs/"+id+"/complete", done, 409)
		oldBoot := w["boot_id"]
		w["boot_id"] = ID()
		reg := Object{"worker_id": w["worker_id"], "boot_id": w["boot_id"], "kind": "report", "capacity_profile_id": "report-v1"}
		call("/workers/register", reg, 200)
		call("/claims", w, 204)
		reg["boot_id"] = oldBoot
		call("/workers/register", reg, 409)
		must(t, controller.ReleaseQuarantine(ctx, id, 2, "E2E old boot inference verified stopped"))
		exec("UPDATE jobs SET eligible_at=clock_timestamp()-interval '1 second' WHERE id=$1", id)
		cl3 := call("/claims", w, 200)
		v := call("/jobs/"+id+"/fail", Object{"attempt_no": cl3["attempt_no"], "claim_token": cl3["claim_token"], "code": "transient_error", "retryable": true, "remote_call_state": "terminated"}, 200)
		if v["status"] != "failed" || Number(v, "budget_used") != 3*attemptBudget {
			t.Fatalf("expected failed job with three reserved attempt budgets (%d): %v", 3*attemptBudget, v)
		}
		apiCall("POST", "/jobs/"+id+"/retry", Object{"reason": "E2E retry"}, 409, "If-Match", fmt.Sprint(Number(v, "version")), "Idempotency-Key", ID())
	})
	t.Run("cross_kind_fairness_without_blocking_absent_workers", func(t *testing.T) {
		activeTest = t
		reset()
		r1 := submit()
		r2 := submit()
		rw := worker("report")
		incident := ID()
		exec("INSERT INTO incidents(id,cluster_id,scope) VALUES($1,'cpc-1',$2)", incident, scope)
		rcaInput := Object{"scope": scope, "incident_id": incident, "evidence_version": 1, "analysis_profile_revision": "incident-v1", "target": Object{"node": "e2e-node"}, "incident_time": "2026-09-15T12:00:00Z", "time_range": Object{"start": "2026-09-15T00:00:00Z", "end": "2026-09-16T00:00:00Z"}, "purpose_ids": []string{"R01"}}
		snapshot := Object{"input": rcaInput, "evidence": Object{"summary": "incident E2E"}}
		exec("INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,1,$2,$3)", incident, snapshot, Hash(snapshot))
		env := Object{"contract_version": "1.3", "source_module": "incident", "source_key": "incident:" + incident + ":1", "kind": "rca", "input": rcaInput, "deadline_at": time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano), "dispatch_deadline": time.Now().Add(time.Minute).UTC().Format(time.RFC3339Nano), "snapshot_ref": Object{"incident_id": incident, "revision": 1}, "execution_profile_revision": "local-v1"}
		rcaInput["analysis_profile_revision"] = "mismatched"
		call("/jobs/rca", env, 422)
		rcaInput["analysis_profile_revision"] = "incident-v1"
		env["execution_profile_revision"] = "report-namespace-v1"
		call("/jobs/rca", env, 422)
		env["execution_profile_revision"] = "local-v1"
		rca := call("/jobs/rca", env, 202)
		cl := call("/claims", rw, 200)
		if cl["job_id"] != r1 {
			t.Fatal("FIFO", cl)
		}
		finish(cl)
		cl = call("/claims", rw, 200)
		if cl["job_id"] != r2 {
			t.Fatal("absent RCA worker blocked report")
		}
		finish(cl)
		submit()
		aw := worker("rca")
		call("/claims", rw, 204)
		cl = call("/claims", aw, 200)
		if versions, _ := cl["versions"].(map[string]any); String(versions, "criteria") != "unconfigured" {
			t.Fatal("report criteria leaked into RCA", versions)
		}
		if cl["job_id"] != rca["job_id"] {
			t.Fatal(cl)
		}
		finish(cl)
		cl = call("/claims", rw, 200)
		finish(cl)
	})
	t.Run("input_contract_intake_mixed_workers_and_publication", func(t *testing.T) {
		activeTest = t
		reset()
		rcaEnvelope := func(version string) Object {
			id := ID()
			exec("INSERT INTO incidents(id,cluster_id,scope) VALUES($1,'cpc-1',$2)", id, scope)
			data := Object{"scope": scope, "incident_id": id, "evidence_version": 1, "incident_time": "2026-09-15T12:00:00Z", "time_range": Object{"start": "2026-09-15T00:00:00Z", "end": "2026-09-16T00:00:00Z"}}
			if version == "1.3" {
				data["purpose_ids"] = []string{"R01"}
				data["analysis_profile_revision"] = "legacy-v1"
			}
			snapshot := Object{"input": data, "alert": Object{"status": "firing", "labels": Object{"cluster_id": "cpc-1"}}}
			exec("INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,1,$2,$3)", id, snapshot, Hash(snapshot))
			return Object{"contract_version": version, "source_module": "incident", "source_key": "incident:" + id + ":first", "kind": "rca", "input": data, "deadline_at": time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano), "dispatch_deadline": time.Now().Add(time.Minute).UTC().Format(time.RFC3339Nano), "snapshot_ref": Object{"incident_id": id, "revision": 1}, "execution_profile_revision": "local-v1"}
		}
		newEnvelope := rcaEnvelope("1.4")
		newInput := newEnvelope["input"].(Object)
		newInput["incident_time"] = "2026-09-15T13:00:00Z"
		call("/jobs/rca", newEnvelope, 422)
		newInput["incident_time"] = "2026-09-15T12:00:00Z"
		newJob := call("/jobs/rca", newEnvelope, 202)
		id := String(newJob, "job_id")
		if call("/jobs/rca", newEnvelope, 202)["job_id"] != id {
			t.Fatal("duplicate intake")
		}
		newEnvelope["deadline_at"] = time.Now().Add(2 * time.Hour).UTC().Format(time.RFC3339Nano)
		call("/jobs/rca", newEnvelope, 409)
		legacy := call("/jobs/rca", rcaEnvelope("1.3"), 202)
		oldWorker := worker("rca")
		cl := call("/claims", oldWorker, 200)
		if cl["job_id"] != legacy["job_id"] || cl["versions"].(Object)["input_contract"] != "1.3" {
			t.Fatal("legacy worker claimed incompatible head", cl)
		}
		finish(cl)
		call("/claims", oldWorker, 204)
		if call("/jobs/"+id, nil, 200)["queue_reason"] != "worker_unavailable" {
			t.Fatal("missing compatible worker reason")
		}
		rw := worker("report")
		for range 2 {
			rid := submit()
			cl = call("/claims", rw, 200)
			if cl["job_id"] != rid {
				t.Fatal("incompatible RCA blocked report fairness")
			}
			finish(cl)
		}
		registration := Object{"worker_id": ID(), "boot_id": ID(), "kind": "rca", "capacity_profile_id": "rca-v1", "supported_contract_versions": []string{"1.4", "1.3"}}
		call("/workers/register", registration, 200)
		registration["supported_contract_versions"] = []string{"1.3", "1.4"}
		call("/workers/register", registration, 200)
		registration["supported_contract_versions"] = []string{"1.3"}
		call("/workers/register", registration, 409)
		registration["supported_contract_versions"] = []string{"1.4"}
		call("/claims", registration, 422)
		w := Object{"worker_id": registration["worker_id"], "boot_id": registration["boot_id"], "kind": "rca"}
		for _, value := range []any{nil, []string{}, []string{"2.0"}, []any{1.4}, "1.4"} {
			registration["supported_contract_versions"] = value
			call("/workers/register", registration, 422)
		}
		call("/workers/register", Object{"worker_id": ID(), "boot_id": ID(), "kind": "report", "capacity_profile_id": "report-v1", "supported_contract_versions": []string{"1.4"}}, 422)
		submit() // Both kinds now have runnable work; report must yield its last turn.
		call("/claims", rw, 204)
		cl = call("/claims", w, 200)
		if cl["job_id"] != id || cl["versions"].(Object)["input_contract"] != "1.4" {
			t.Fatal("version not pinned", cl)
		}
		if _, exists := cl["input"].(Object)["purpose_ids"]; exists {
			t.Fatal("purposes injected")
		}
		cid := ID()
		for _, version := range []any{nil, "1.3", "2.0", "1.4"} {
			body := Object{"result_status": "blocked"}
			if version != nil {
				body["versions"] = Object{"input_contract": version}
			}
			hash := Hash(body)
			exec("INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,$3,'rca','1.3',$4,$5,'valid') ON CONFLICT(id) DO UPDATE SET body=EXCLUDED.body,content_hash=EXCLUDED.content_hash", cid, id, cl["attempt_no"], body, hash)
			done := Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "candidate_id": cid, "content_hash": hash}
			if version != "1.4" {
				call("/jobs/"+id+"/complete", done, 422)
			} else {
				call("/jobs/"+id+"/complete", done, 200)
				call("/jobs/"+id+"/complete", done, 200)
			}
		}
		// A new boot may roll back capabilities; pending 1.4 is preserved, not downgraded.
		pending := call("/jobs/rca", rcaEnvelope("1.4"), 202)
		registration["boot_id"] = ID()
		registration["supported_contract_versions"] = []string{"1.3"}
		call("/workers/register", registration, 200)
		call("/claims", w, 409)
		call("/claims", Object{"worker_id": registration["worker_id"], "boot_id": registration["boot_id"], "kind": "rca"}, 204)
		if call("/jobs/"+String(pending, "job_id"), nil, 200)["queue_reason"] != "worker_unavailable" {
			t.Fatal("rollback lost queued job")
		}
		exec("UPDATE jobs SET deadline_at=clock_timestamp()-interval '1 second' WHERE id=$1", pending["job_id"])
		if call("/jobs/"+String(pending, "job_id"), nil, 200)["status"] != "expired" {
			t.Fatal("unsupported jobs must still expire")
		}
	})
	t.Run("worker_contract_upgrade_preserves_legacy_jobs", func(t *testing.T) {
		activeTest = t
		reset()
		id := submit()
		w := worker("report")
		// Simulate the exact pre-upgrade schema and a job without the new JSON key.
		exec("ALTER TABLE workers DROP COLUMN supported_contract_versions")
		exec("DELETE FROM jc_migrations WHERE version=2")
		exec("UPDATE jobs SET versions=versions-'input_contract' WHERE id=$1", id)
		var before, after Object
		must(t, db.Pool.QueryRow(ctx, "SELECT jsonb_build_object('input',input_snapshot,'hash',request_hash,'versions',versions) FROM jobs WHERE id=$1", id).Scan(&before))
		must(t, controller.Prepare(ctx, false))
		must(t, controller.Prepare(ctx, false))
		cl := call("/claims", w, 200)
		if cl["versions"].(Object)["input_contract"] != "1.3" {
			t.Fatal("legacy interpretation")
		}
		must(t, db.Pool.QueryRow(ctx, "SELECT jsonb_build_object('input',input_snapshot,'hash',request_hash,'versions',versions) FROM jobs WHERE id=$1", id).Scan(&after))
		if Hash(before) != Hash(after) {
			t.Fatal("legacy snapshot/hash/versions rewritten")
		}
		call("/jobs/"+id+"/complete", candidate(cl), 200)
		id = submit()
		for _, value := range []string{`"2.0"`, `null`, `""`} {
			exec("UPDATE jobs SET versions=jsonb_set(versions,'{input_contract}',$2::jsonb) WHERE id=$1", id, value)
			call("/claims", w, 204)
		}
	})
	t.Run("scheduler_outbox_lost_response_receipt_recovery", func(t *testing.T) {
		activeTest = t
		reset()
		spec := input()
		spec["topic_ids"] = []string{"O08"}
		spec["group_by"] = []string{"namespace"}
		delete(spec, "time_range")
		delete(spec, "timezone")
		v := apiCall("POST", "/schedules", Object{"frequency": "daily", "local_time": "09:00", "timezone": "Asia/Seoul", "period": "previous_complete_day", "enabled": true, "report_spec": spec}, 201, "Idempotency-Key", ID())
		exec("UPDATE schedules SET next_run_at=clock_timestamp()-interval '1 minute' WHERE id=$1", v["id"])
		must(t, backend.GenerateOccurrences(ctx))
		lose.Store(true)
		must(t, backend.DeliverPending(ctx))
		exec("UPDATE enqueue_outbox SET next_retry_at=clock_timestamp()-interval '1 second',dispatch_deadline=clock_timestamp()-interval '1 second' WHERE status='pending'")
		must(t, backend.DeliverPending(ctx))
		var count, accepted int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM jobs").Scan(&count))
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM schedule_occurrences WHERE status='accepted'").Scan(&accepted))
		var criteria, profile string
		must(t, db.Pool.QueryRow(ctx, "SELECT versions->>'criteria', versions->>'execution_profile_revision' FROM jobs WHERE source_key LIKE 'schedule:%' ORDER BY created_at DESC LIMIT 1").Scan(&criteria, &profile))
		if criteria != "1.2" || profile != "report-namespace-v1" {
			t.Fatal("namespace schedule used wrong profile", criteria, profile)
		}
		if controller.Config.Versions["criteria"] != "unconfigured" {
			t.Fatal("global criteria changed")
		}
		if count != 1 || accepted != 1 {
			t.Fatalf("jobs=%d accepted=%d", count, accepted)
		}
	})

	t.Run("capacity_reduction_preserves_running_and_fences_old_config", func(t *testing.T) {
		activeTest = t
		reset()
		for range 3 {
			submit()
		}
		wide := jc.DefaultConfig()
		wide.SharedLimit = 2
		wide.KindLimits["report"] = 2
		wide.Workers["report-v1"] = jc.WorkerProfile{Kind: "report", Slots: 2}
		expanded, e := jc.New(db.Pool, wide)
		must(t, e)
		must(t, expanded.Prepare(ctx, true))
		wideHTTP := httptest.NewServer(expanded)
		defer wideHTTP.Close()
		wc := func(path string, b Object, status int) Object {
			return request(t, wideHTTP.URL+"/internal/v1"+path, "POST", b, status)
		}
		w := Object{"worker_id": ID(), "boot_id": ID(), "kind": "report", "capacity_profile_id": "report-v1"}
		wc("/workers/register", w, 200)
		delete(w, "capacity_profile_id")
		cl1 := wc("/claims", w, 200)
		cl2 := wc("/claims", w, 200)
		must(t, controller.Prepare(ctx, true))
		wc("/claims", w, 503)
		call("/claims", w, 204)
		var running int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM jobs WHERE status='running'").Scan(&running))
		if running != 2 {
			t.Fatal("capacity update killed running jobs")
		}
		finish(cl1)
		call("/claims", w, 204)
		finish(cl2)
		finish(call("/claims", w, 200))
	})
	t.Run("cancel_unknown_remote_waits_for_evidence_and_manual_retry_receipt", func(t *testing.T) {
		activeTest = t
		reset()
		id := submit()
		w := worker("report")
		cl := call("/claims", w, 200)
		v := apiCall("GET", "/jobs/"+id, nil, 200)
		apiCall("POST", "/jobs/"+id+"/cancel", Object{"reason": "E2E"}, 200, "Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(v, "version")))
		v = call("/jobs/"+id+"/fail", Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "code": "cancelled", "retryable": false, "remote_call_state": "unknown"}, 200)
		if v["status"] != "running" {
			t.Fatal("unconfirmed cancellation became terminal", v)
		}
		must(t, controller.ReleaseQuarantine(ctx, id, 1, "E2E cancellation remote termination verified"))
		v = apiCall("GET", "/jobs/"+id, nil, 200)
		if v["status"] != "cancelled" {
			t.Fatal(v)
		}
		// Restore a persisted retryable failed job, as on recovery from an older JC policy.
		id = submit()
		cl = call("/claims", w, 200)
		finish(cl)
		exec("UPDATE jobs SET retryable=true,termination_reason='transient_error' WHERE id=$1", id)
		v = apiCall("GET", "/jobs/"+id, nil, 200)
		if v["can_retry"] != true {
			t.Fatal(v)
		}
		headers := []string{"Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(v, "version"))}
		a := apiCall("POST", "/jobs/"+id+"/retry", Object{"reason": "recover"}, 200, headers...)
		b := apiCall("POST", "/jobs/"+id+"/retry", Object{"reason": "recover"}, 200, headers...)
		if a["version"] != b["version"] || Number(b, "budget_used") != attemptBudget || Number(b, "attempt_no") != 1 {
			t.Fatalf("retry receipt must preserve one reserved attempt budget (%d): %v %v", attemptBudget, a, b)
		}
		cl = call("/claims", w, 200)
		if Number(cl, "attempt_no") != 2 {
			t.Fatal(cl)
		}
		finish(cl)
	})
	t.Run("database_failure_fails_closed", func(t *testing.T) {
		activeTest = t
		reset()
		submit()
		w := worker("report")
		cl := call("/claims", w, 200)
		done := candidate(cl)
		isolated, e := pgxpool.New(ctx, u.String())
		must(t, e)
		broken, e := jc.New(isolated, cfg)
		must(t, e)
		isolated.Close()
		server := httptest.NewServer(broken)
		defer server.Close()
		for _, op := range []string{"claims", "jobs/" + String(cl, "job_id") + "/heartbeat", "jobs/" + String(cl, "job_id") + "/complete"} {
			b := done
			if op == "claims" {
				b = w
			}
			request(t, server.URL+"/internal/v1/"+op, "POST", b, 503)
		}
	})
}
