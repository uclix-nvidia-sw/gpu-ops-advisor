//go:build e2e

package tests

import (
	"context"
	"fmt"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	jc "gpu-ops-advisor/job-controller/controller"
	"gpu-ops-advisor/shared/migrations"
)

func TestReportDeletion(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, err := pgxpool.New(ctx, dsn)
	must(t, err)
	defer admin.Close()
	schema := "delete_e2e_" + strings.ReplaceAll(ID(), "-", "")
	_, err = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	must(t, err)
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	u, err := url.Parse(dsn)
	must(t, err)
	query := u.Query()
	query.Set("search_path", schema)
	u.RawQuery = query.Encode()
	db, err := store.Open(ctx, u.String())
	must(t, err)
	defer db.Pool.Close()
	// Upgrade an existing installation, then reapply both service startup paths.
	for _, sql := range []string{migrations.Baseline, migrations.Upgrade, migrations.Queue, migrations.WorkerContracts, migrations.RunbookContract} {
		_, err = db.Pool.Exec(ctx, sql)
		must(t, err)
	}
	legacyJob, legacyCandidate := ID(), ID()
	_, err = db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at) VALUES($1::uuid,'report','backend',$1::text,'{}','{}','unchanged-request','succeeded',now()+interval '1 day')", legacyJob)
	must(t, err)
	_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,'report','1.3','{\"legacy\":true}','unchanged-result','valid')", legacyCandidate, legacyJob)
	must(t, err)
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", legacyJob, legacyCandidate)
	must(t, err)
	controller, err := jc.New(db.Pool, jc.DefaultConfig())
	must(t, err)
	must(t, controller.Prepare(ctx, true))
	must(t, controller.Prepare(ctx, true))
	must(t, db.Migrate(ctx))
	must(t, db.Migrate(ctx))
	var legacyPreserved bool
	must(t, db.Pool.QueryRow(ctx, `SELECT j.request_hash='unchanged-request' AND j.status='succeeded'
 AND c.content_hash='unchanged-result' AND c.body='{"legacy":true}'::jsonb
 FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id WHERE j.id=$1`, legacyJob).Scan(&legacyPreserved))
	if !legacyPreserved {
		t.Fatal("migration changed historical request/publication/body/hash")
	}
	must(t, db.Seed(ctx))
	queue := httptest.NewServer(controller)
	defer queue.Close()
	web := httptest.NewServer(api.New(db, config.Config{Modules: map[string]string{"job_controller": queue.URL}}))
	defer web.Close()
	scope := Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": nil}}}
	exec := func(t *testing.T, sql string, args ...any) {
		t.Helper()
		_, e := db.Pool.Exec(ctx, sql, args...)
		must(t, e)
	}
	fixture := func(t *testing.T, status string) (string, string, string) {
		t.Helper()
		id, candidate, evidence := ID(), ID(), ID()
		input := Object{"scope": scope, "time_range": Object{"start": "2026-10-01T00:00:00Z", "end": "2026-10-02T00:00:00Z"}, "timezone": "Asia/Seoul", "topic_ids": []string{"O01"}, "group_by": []string{"cluster"}}
		exec(t, `INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,versions,status,stage,deadline_at,attempt_no,max_attempts,token_budget,retryable,termination_reason)
 VALUES($1::uuid,'report','backend',$1::text,$2,$3,'request-hash',$4,$5,$5,now()+interval '1 day',1,3,98304,true,'timeout')`, id, scope, input, Object{"execution": jc.DefaultConfig().Execution["local-v1"]}, status)
		exec(t, `INSERT INTO job_attempts(job_id,attempt_no,started_at,ended_at,claim_token,completion_response)
 VALUES($1::uuid,1,now()-interval '1 minute',now(),$1::text,$2)`, id, Object{"candidate_id": candidate, "content_hash": "saved-hash", "published_result_id": candidate})
		exec(t, "INSERT INTO evidence(id,job_id,attempt_no,scope,tool_status,snapshot) VALUES($1::uuid,$2,1,$3,'success','{\"data\":[1,2,3]}')", evidence, id, scope)
		exec(t, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1::uuid,$2,1,'report','1.3',$3,'saved-hash','valid')", candidate, id, Object{"result_status": "partial", "evidence_refs": []string{evidence}})
		if status == "succeeded" {
			exec(t, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", id, candidate)
		}
		return id, candidate, evidence
	}
	remove := func(t *testing.T, id, key string, version, status int) Object {
		t.Helper()
		return request(t, web.URL+"/api/v1/jobs/"+id+"/delete", "POST", Object{"reason": "Remove report test data"}, status, "Idempotency-Key", key, "If-Match", fmt.Sprintf("\"%d\"", version))
	}
	assertCounts := func(t *testing.T, id string, evidence, candidates, deleted int) {
		t.Helper()
		var e, c, d int
		must(t, db.Pool.QueryRow(ctx, `SELECT (SELECT count(*) FROM evidence WHERE job_id=$1),
 (SELECT count(*) FROM result_candidates WHERE job_id=$1),(SELECT count(*) FROM report_deletions WHERE job_id=$1)`, id).Scan(&e, &c, &d))
		if e != evidence || c != candidates || d != deleted {
			t.Fatalf("rows evidence=%d candidates=%d deletions=%d", e, c, d)
		}
	}
	t.Run("older controller policy is fenced", func(t *testing.T) {
		old, err := jc.New(db.Pool, jc.DefaultConfig())
		must(t, err)
		old.Revision = Hash(Object{"config": old.Config, "execution_policy": "release-ended-attempt-v1", "dispatch_policy": "independent-kind-capacity-v1"})
		oldQueue := httptest.NewServer(old)
		defer oldQueue.Close()
		request(t, oldQueue.URL+"/internal/v1/health/ready", "GET", nil, 503)
		request(t, oldQueue.URL+"/internal/v1/jobs", "GET", nil, 503)
	})
	t.Run("terminal reports purge only owned payload and preserve history", func(t *testing.T) {
		for _, status := range []string{"succeeded", "failed", "cancelled", "expired"} {
			t.Run(status, func(t *testing.T) {
				id, candidate, evidence := fixture(t, status)
				// Previous failed-attempt payloads are reclaimed as well.
				exec(t, "INSERT INTO evidence(id,job_id,attempt_no,scope,tool_status,snapshot) VALUES($1::uuid,$2,0,$3,'error','{}')", ID(), id, scope)
				exec(t, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1::uuid,$2,0,'report','1.3','{}','old-hash','invalid')", ID(), id)
				key := ID()
				response := remove(t, id, key, 1, 200)
				deletion := response["deletion"].(map[string]any)
				if response["status"] != status || response["published_result_id"] != nil || deletion["artifact_cleanup_state"] != "pending" || Number(deletion, "evidence_count") != 2 || Number(deletion, "candidate_count") != 2 {
					t.Fatalf("unexpected deletion response: %v", response)
				}
				if status == "succeeded" && (deletion["published_result_id"] != candidate || deletion["content_hash"] != "saved-hash") {
					t.Fatal("original publication/hash not retained")
				}
				assertCounts(t, id, 0, 0, 1)
				var attempts, audits int
				var preservedStatus, sourceKey, requestHash string
				must(t, db.Pool.QueryRow(ctx, `SELECT j.status,j.source_key,j.request_hash,
 (SELECT count(*) FROM job_attempts WHERE job_id=j.id),(SELECT count(*) FROM audit_events WHERE resource_id=j.id AND action='delete') FROM jobs j WHERE id=$1`, id).Scan(&preservedStatus, &sourceKey, &requestHash, &attempts, &audits))
				if preservedStatus != status || sourceKey != id || requestHash != "request-hash" || attempts != 1 || audits != 1 {
					t.Fatal("history changed or audit missing")
				}
				replayed := remove(t, id, key, 1, 200)
				if replayed["version"] != response["version"] {
					t.Fatal("delete replay was not idempotent")
				}
				request(t, web.URL+"/api/v1/jobs/"+id+"/delete", "POST", Object{"reason": "different"}, 409, "Idempotency-Key", key, "If-Match", "\"1\"")
				detail := request(t, web.URL+"/api/v1/reports/"+id, "GET", nil, 200)
				if detail["result_status"] != "deleted" || detail["result_ref"] != nil || detail["can_retry"] != false || detail["can_delete"] != false {
					t.Fatalf("deleted report was exposed: %v", detail)
				}
				for _, resource := range []string{"reports", "jobs"} {
					list := request(t, web.URL+"/api/v1/"+resource+"?limit=100", "GET", nil, 200)
					found := false
					for _, value := range list["items"].([]any) {
						item := value.(map[string]any)
						if item["id"] == id {
							found = true
							if item["result_status"] != "deleted" || item["deletion"] == nil {
								t.Fatal("job history lost deletion metadata")
							}
						}
					}
					if found != (resource == "jobs") {
						t.Fatalf("unexpected deleted report membership in %s: %v", resource, found)
					}
				}
				request(t, web.URL+"/api/v1/evidence/"+evidence, "GET", nil, 404)
				for _, op := range []string{"cancel", "retry"} {
					request(t, queue.URL+"/internal/v1/jobs/"+id+"/"+op, "POST", Object{"contract_version": "1.3", "source_module": "backend", "input": Object{"reason": "retry deleted"}}, 409, "Idempotency-Key", ID(), "If-Match", "\"2\"")
				}
				for _, op := range []string{"complete", "fail", "heartbeat"} {
					body := Object{"attempt_no": 1, "claim_token": id}
					if op == "complete" {
						body["candidate_id"], body["content_hash"] = candidate, "saved-hash"
					}
					request(t, queue.URL+"/internal/v1/jobs/"+id+"/"+op, "POST", body, 409)
				}
			})
		}
	})
	t.Run("active states and reservations refuse deletion", func(t *testing.T) {
		for _, status := range []string{"queued", "retry_wait", "running"} {
			id, _, _ := fixture(t, status)
			remove(t, id, ID(), 1, 409)
			assertCounts(t, id, 1, 1, 0)
			// Keep later route sweeps from turning these synthetic active fixtures terminal.
			exec(t, "UPDATE jobs SET status='cancelled' WHERE id=$1", id)
		}
		for _, state := range []string{"active", "quarantined"} {
			id, _, _ := fixture(t, "failed")
			exec(t, "UPDATE job_attempts SET ended_at=NULL WHERE job_id=$1", id)
			exec(t, "INSERT INTO slot_reservations(id,job_id,attempt_no,worker_id,boot_id,kind,state,reserved_at) VALUES($1::uuid,$2,1,'worker',$3,'report',$4,now())", ID(), id, ID(), state)
			remove(t, id, ID(), 1, 409)
			assertCounts(t, id, 1, 1, 0)
		}
	})
	t.Run("empty reports still require version and reason", func(t *testing.T) {
		id, _, _ := fixture(t, "cancelled")
		exec(t, "DELETE FROM evidence WHERE job_id=$1", id)
		exec(t, "DELETE FROM result_candidates WHERE job_id=$1", id)
		remove(t, id, ID(), 2, 409)
		request(t, web.URL+"/api/v1/jobs/"+id+"/delete", "POST", Object{"reason": "  "}, 422, "Idempotency-Key", ID(), "If-Match", "\"1\"")
		assertCounts(t, id, 0, 0, 0)
		remove(t, id, ID(), 1, 200)
		assertCounts(t, id, 0, 0, 1)
	})
	t.Run("foreign references rollback without changing publication", func(t *testing.T) {
		cases := map[string]func(*testing.T, string, string){
			"identity": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO identity_history(id,cluster_id,relation_kind,subject_key,subject_kind,valid_from,identity_status,evidence_id) VALUES($1::uuid,'cpc-1','gpu-pod','gpu','gpu',now(),'verified',$2)", ID(), evidence)
			},
			"collection": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO collection_observations(id,cluster_id,source,evaluated_at,scope,success,completeness,dedup_key,evidence_refs) VALUES($1::uuid,'cpc-1','test',now(),$2,true,'complete',$1::text,$3)", ID(), scope, []string{evidence})
			},
			"allocation": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO allocation_observations(id,cluster_id,allocation_mode,relation_status,identity_status,time_basis,evaluated_at,relation_key,evidence_refs) VALUES($1::uuid,'cpc-1','unknown','unknown','unknown','observed',now(),$1::text,$2)", ID(), []string{evidence})
			},
			"knowledge": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,scope,content,content_hash,source_refs) VALUES($1::uuid,$1::uuid,$1::text,1,'reference','draft','scoped',$2,'{}','test',$3)", ID(), scope, []string{evidence})
			},
			"review": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO review_records(id,subject_type,subject_id,kind,author,body,scope) VALUES($1::uuid,'job',$2,'comment','test',$3,$4)", ID(), ID(), Object{"evidence_refs": []string{evidence}}, scope)
			},
			"knowledge review audit": func(t *testing.T, evidence, candidate string) {
				exec(t, "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,request_id,after_ref) VALUES($1,'unverified','POST:reviewed','knowledge',$2,$3,$4)", ID(), ID(), ID(), Object{"command": Object{"evidence_refs": []string{evidence}}})
			},
			"result evidence": func(t *testing.T, evidence, candidate string) {
				other, _, _ := fixture(t, "failed")
				exec(t, "UPDATE result_candidates SET body=$2 WHERE job_id=$1", other, Object{"evidence_refs": []string{evidence}})
			},
		}
		for name, reference := range cases {
			t.Run(name, func(t *testing.T) {
				id, candidate, evidence := fixture(t, "succeeded")
				reference(t, evidence, candidate)
				remove(t, id, ID(), 1, 409)
				assertCounts(t, id, 1, 1, 0)
				var published string
				var version int
				must(t, db.Pool.QueryRow(ctx, "SELECT published_result_id::text,version FROM jobs WHERE id=$1", id).Scan(&published, &version))
				if published != candidate || version != 1 {
					t.Fatal("rejected deletion changed publication/version")
				}
				_, e := db.Pool.Exec(ctx, "DELETE FROM result_candidates WHERE id=$1", candidate)
				if e == nil {
					t.Fatal("published-candidate guard was weakened")
				}
			})
		}
	})
	t.Run("reference and deletion transactions cannot leave dangling evidence", func(t *testing.T) {
		for _, first := range []string{"reference", "deletion"} {
			t.Run(first+" first", func(t *testing.T) {
				id, _, evidence := fixture(t, "succeeded")
				const gate = 78264113
				conn, err := db.Pool.Acquire(ctx)
				must(t, err)
				defer conn.Release()
				_, err = conn.Exec(ctx, "SELECT pg_advisory_lock($1)", gate)
				must(t, err)
				defer conn.Exec(ctx, "SELECT pg_advisory_unlock($1)", gate)
				exec(t, fmt.Sprintf(`CREATE OR REPLACE FUNCTION deletion_test_gate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock(%d); IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$`, gate))
				table, event := "knowledge_revisions", "INSERT"
				if first == "deletion" {
					table, event = "evidence", "DELETE"
				}
				exec(t, "CREATE TRIGGER deletion_test_gate BEFORE "+event+" ON "+table+" FOR EACH ROW EXECUTE FUNCTION deletion_test_gate()")
				defer exec(t, "DROP TRIGGER deletion_test_gate ON "+table)
				wait := func(sql string, args ...any) {
					t.Helper()
					deadline := time.Now().Add(time.Second)
					for time.Now().Before(deadline) {
						var waiting bool
						must(t, db.Pool.QueryRow(ctx, sql, args...).Scan(&waiting))
						if waiting {
							return
						}
						time.Sleep(10 * time.Millisecond)
					}
					t.Fatal("expected database lock wait not reached")
				}
				knowledgeStatus, deleteStatus := 201, 409
				if first == "deletion" {
					knowledgeStatus, deleteStatus = 404, 200
				}
				knowledgeDone, deleteDone := make(chan struct{}), make(chan struct{})
				createKnowledge := func() {
					defer close(knowledgeDone)
					request(t, web.URL+"/api/v1/knowledge", "POST", Object{"knowledge_key": ID(), "kind": "reference", "visibility": "scoped", "scope": scope, "content": Object{"title": "referenced evidence"}, "source_refs": []string{evidence}}, knowledgeStatus, "Idempotency-Key", ID())
				}
				deleteReport := func() {
					defer close(deleteDone)
					remove(t, id, ID(), 1, deleteStatus)
				}
				if first == "reference" {
					go createKnowledge()
				} else {
					go deleteReport()
				}
				wait("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=$1 AND NOT granted)", gate)
				if first == "reference" {
					go deleteReport()
					wait("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE 'SELECT id FROM evidence WHERE job_id=%')")
				} else {
					go createKnowledge()
					wait("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%FROM evidence WHERE id%FOR KEY SHARE%')")
				}
				_, err = conn.Exec(ctx, "SELECT pg_advisory_unlock($1)", gate)
				must(t, err)
				for _, done := range []chan struct{}{knowledgeDone, deleteDone} {
					select {
					case <-done:
					case <-time.After(5 * time.Second):
						t.Fatal("request did not finish after releasing the test gate")
					}
				}
				if first == "reference" {
					assertCounts(t, id, 1, 1, 0)
				} else {
					assertCounts(t, id, 0, 0, 1)
				}
			})
		}
	})
	t.Run("busy evidence rolls back with a bounded conflict", func(t *testing.T) {
		id, _, evidence := fixture(t, "succeeded")
		tx, err := db.Pool.Begin(ctx)
		must(t, err)
		defer tx.Rollback(ctx)
		_, err = tx.Exec(ctx, "SELECT id FROM evidence WHERE id=$1 FOR KEY SHARE", evidence)
		must(t, err)
		response := remove(t, id, ID(), 1, 409)
		if response["error"].(map[string]any)["code"] != "report_busy" {
			t.Fatalf("unexpected busy response: %v", response)
		}
		assertCounts(t, id, 1, 1, 0)
	})
	t.Run("RCA is not a deletable report", func(t *testing.T) {
		incidentID, id := ID(), ID()
		exec(t, "INSERT INTO incidents(id,cluster_id,scope) VALUES($1::uuid,'cpc-1',$2)", incidentID, scope)
		exec(t, "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1::uuid,1,'{}','snapshot-hash')", incidentID)
		exec(t, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,incident_id,evidence_version) VALUES($1::uuid,'rca','incident',$1::text,$2,'{}','request-hash','succeeded',$3,$4,1)", id, scope, time.Now().Add(time.Hour), incidentID)
		request(t, queue.URL+"/internal/v1/jobs/"+id+"/delete", "POST", Object{"contract_version": "1.3", "source_module": "incident", "input": Object{"incident_id": incidentID, "reason": "not allowed"}}, 409, "Idempotency-Key", ID(), "If-Match", "\"1\"")
		var count int
		must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM incident_evidence_versions WHERE incident_id=$1", incidentID).Scan(&count))
		if count != 1 {
			t.Fatal("RCA snapshot deleted")
		}
	})
}
