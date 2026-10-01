//go:build e2e

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/incident/service"
	jc "gpu-ops-advisor/job-controller/controller"
	. "gpu-ops-advisor/shared/contract"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type rig struct {
	db                                *pgxpool.Pool
	service                           *service.Server
	jc                                *jc.Controller
	incidentURL, queueURL, backendURL string
	lose                              atomic.Bool
	offline                           atomic.Bool
}

func check(t *testing.T, e error) {
	t.Helper()
	if e != nil {
		t.Fatal(e)
	}
}
func setup(t *testing.T) *rig {
	t.Helper()
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, e := pgxpool.New(ctx, dsn)
	check(t, e)
	t.Cleanup(admin.Close)
	schema := "incident_e2e_" + strings.ReplaceAll(ID(), "-", "")
	_, e = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	check(t, e)
	t.Cleanup(func() {
		_, e := admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
		if e != nil {
			t.Error(e)
		}
	})
	u, e := url.Parse(dsn)
	check(t, e)
	v := u.Query()
	v.Set("search_path", schema)
	u.RawQuery = v.Encode()
	db, e := pgxpool.New(ctx, u.String())
	check(t, e)
	t.Cleanup(db.Close)
	controller, e := jc.New(db, jc.DefaultConfig())
	check(t, e)
	check(t, controller.Prepare(ctx, false))
	_, e = db.Exec(ctx, "INSERT INTO cluster_registry(id) VALUES('cpc-1')")
	check(t, e)
	r := &rig{db: db, jc: controller}
	qs := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if r.offline.Load() {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(503)
			io.WriteString(w, `{"error":{"code":"unavailable"}}`)
			return
		}
		if req.URL.Path == "/internal/v1/jobs/rca" && r.lose.Swap(false) {
			rec := httptest.NewRecorder()
			controller.ServeHTTP(rec, req)
			if rec.Code != 202 {
				t.Errorf("JC failed before loss injection: %s", rec.Body.String())
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(503)
			io.WriteString(w, `{"error":{"code":"lost_response"}}`)
			return
		}
		controller.ServeHTTP(w, req)
	}))
	t.Cleanup(qs.Close)
	r.queueURL = qs.URL
	cfg := service.DefaultConfig()
	cfg.JCURL = qs.URL
	r.service, e = service.New(db, cfg)
	check(t, e)
	check(t, r.service.Prepare(ctx))
	check(t, r.service.Prepare(ctx))
	web := httptest.NewServer(r.service)
	t.Cleanup(web.Close)
	r.incidentURL = web.URL
	binary := os.Getenv("E2E_BACKEND_BINARY")
	if binary == "" {
		t.Fatal("E2E_BACKEND_BINARY required (build the real Backend first)")
	}
	binary, e = filepath.Abs(binary)
	check(t, e)
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	check(t, e)
	addr := listener.Addr().String()
	listener.Close()
	r.backendURL = "http://" + addr
	cmd := exec.Command(binary)
	cmd.Env = append(os.Environ(), "DATABASE_URL="+u.String(), "DSX_ADDRESS="+addr, "DSX_MIGRATE=true", "DSX_SEED=true", "DSX_SCHEDULER_ENABLED=false", "DSX_INCIDENT_URL="+web.URL, "DSX_JOB_CONTROLLER_URL="+qs.URL)
	log, e := os.CreateTemp(t.TempDir(), "backend-*.log")
	check(t, e)
	cmd.Stdout, cmd.Stderr = log, log
	check(t, cmd.Start())
	t.Cleanup(func() { cmd.Process.Kill(); cmd.Wait(); log.Close() })
	ready := false
	for i := 0; i < 100; i++ {
		resp, err := http.Get(r.backendURL + "/api/v1/health/ready")
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				ready = true
				break
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !ready {
		t.Fatal("real Backend did not become ready")
	}
	return r
}
func call(t *testing.T, base, method, path string, body any, status int, headers ...string) Object {
	t.Helper()
	raw, e := json.Marshal(body)
	check(t, e)
	req, e := http.NewRequest(method, base+path, bytes.NewReader(raw))
	check(t, e)
	req.Header.Set("Content-Type", "application/json")
	for i := 0; i < len(headers); i += 2 {
		req.Header.Set(headers[i], headers[i+1])
	}
	resp, e := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	check(t, e)
	defer resp.Body.Close()
	data, e := io.ReadAll(resp.Body)
	check(t, e)
	if resp.StatusCode != status {
		t.Fatalf("%s %s got %d want %d: %s", method, path, resp.StatusCode, status, data)
	}
	if status == 204 {
		return nil
	}
	var out Object
	check(t, json.Unmarshal(data, &out))
	return out
}
func alertBody() Object {
	return Object{"status": "firing", "fingerprint": "temperature-node-1", "startsAt": time.Now().Add(-time.Minute).UTC().Truncate(time.Second).Format(time.RFC3339Nano), "endsAt": "0001-01-01T00:00:00Z", "labels": Object{"alertname": "GPUAlert", "cluster_id": "cpc-1", "namespace": "dev", "node": "gpu-node-1", "severity": "warning"}, "annotations": Object{"summary": "GPU alert", "error_code": "Xid31"}, "values": Object{"A": 90}}
}
func batch(alerts ...any) Object {
	return Object{"version": "1", "receiver": "dsx", "status": "firing", "alerts": alerts, "truncatedAlerts": 0}
}
func item(v Object, n int) Object { return v["items"].([]any)[n].(map[string]any) }
func (r *rig) sql(t *testing.T, sql string, args ...any) {
	t.Helper()
	_, e := r.db.Exec(context.Background(), sql, args...)
	check(t, e)
}
func (r *rig) count(t *testing.T, sql string) int {
	t.Helper()
	var n int
	check(t, r.db.QueryRow(context.Background(), sql).Scan(&n))
	return n
}
func (r *rig) deliver(t *testing.T) {
	t.Helper()
	check(t, r.service.DeliverPending(context.Background()))
}
func TestIncidentEndToEnd(t *testing.T) {
	r := setup(t)
	ctx := context.Background()
	a := alertBody()
	payload := batch(a, nil, Object{"status": "firing"})
	payload["truncatedAlerts"] = 2
	receipt := call(t, r.incidentURL, "POST", "/webhooks/grafana", payload, 202)
	id := String(item(receipt, 0), "incident_id")
	if !strings.Contains(fmt.Sprint(receipt["warnings"]), "grafana_truncated_alerts") || Number(receipt, "invalid_alerts") != 2 {
		t.Fatal(receipt)
	}
	t.Run("receipt_dedup_and_invalid_children_preserved", func(t *testing.T) {
		again := call(t, r.incidentURL, "POST", "/webhooks/grafana", payload, 202)
		if receipt["receipt_id"] != again["receipt_id"] {
			t.Fatal("duplicate receipt")
		}
		if r.count(t, "SELECT count(*) FROM alert_events") != 3 || r.count(t, "SELECT count(*) FROM incidents") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 1 {
			t.Fatal("batch was not atomic/deduplicated")
		}
		var wg sync.WaitGroup
		raw, _ := json.Marshal(payload)
		errors := make(chan string, 12)
		for range 12 {
			wg.Add(1)
			go func() {
				defer wg.Done()
				resp, e := http.Post(r.incidentURL+"/webhooks/grafana", "application/json", bytes.NewReader(raw))
				if e != nil {
					errors <- e.Error()
					return
				}
				defer resp.Body.Close()
				if resp.StatusCode != 202 {
					b, _ := io.ReadAll(resp.Body)
					errors <- string(b)
				}
			}()
		}
		wg.Wait()
		close(errors)
		for e := range errors {
			t.Error(e)
		}
		if r.count(t, "SELECT count(*) FROM incident_webhook_receipts") != 1 {
			t.Fatal("concurrent duplicate")
		}
	})
	t.Run("real_JC_lost_reply_recovered_after_deadline", func(t *testing.T) {
		r.lose.Store(true)
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM jobs WHERE kind='rca'") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE status='pending'") != 1 {
			t.Fatal("lost response setup")
		}
		r.sql(t, "UPDATE enqueue_outbox SET dispatch_deadline=clock_timestamp()-interval '1 second',next_retry_at=clock_timestamp()")
		restarted, e := service.New(r.db, r.service.Config)
		check(t, e)
		check(t, restarted.DeliverPending(ctx))
		if r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE status='accepted'") != 1 || r.count(t, "SELECT count(*) FROM jobs") != 1 {
			t.Fatal("receipt reconciliation failed")
		}
		var reason string
		check(t, r.db.QueryRow(ctx, "SELECT queue_reason FROM jobs").Scan(&reason))
		if reason != "worker_unavailable" {
			t.Fatal(reason)
		}
		// Exercise the real Worker protocol to ensure complete RCA input survives every boundary.
		w := Object{"worker_id": ID(), "boot_id": ID(), "kind": "rca", "capacity_profile_id": "rca-v1"}
		call(t, r.queueURL, "POST", "/internal/v1/workers/register", w, 200)
		delete(w, "capacity_profile_id")
		cl := call(t, r.queueURL, "POST", "/internal/v1/claims", w, 200)
		input := cl["input"].(map[string]any)
		target := input["target"].(map[string]any)
		if input["incident_id"] != id || input["incident_snapshot"] == nil || target["gpu_uuid"] != nil || input["analysis_profile_revision"] != "gpu-alert-v1" {
			t.Fatal("RCA snapshot mismatch", input)
		}
		call(t, r.queueURL, "POST", "/internal/v1/jobs/"+String(cl, "job_id")+"/fail", Object{"attempt_no": cl["attempt_no"], "claim_token": cl["claim_token"], "code": "insufficient_data", "retryable": false, "remote_call_state": "not_started"}, 200)
	})
	t.Run("heartbeat_vs_meaningful_evidence_and_resolved", func(t *testing.T) {
		a["values"] = Object{"A": 91}
		v := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
		if Number(item(v, 0), "evidence_version") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 1 {
			t.Fatal("heartbeat caused RCA")
		}
		a["labels"].(map[string]any)["reason"] = "synthetic display-only update"
		v = call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
		if Number(item(v, 0), "evidence_version") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 1 {
			t.Fatal("display metadata changed evidence identity")
		}
		a["annotations"].(map[string]any)["error_code"] = "Xid79"
		v = call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
		if Number(item(v, 0), "evidence_version") != 2 {
			t.Fatal(v)
		}
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM jobs") != 2 {
			t.Fatal("new evidence not delivered")
		}
		_, e := r.db.Exec(ctx, "UPDATE incident_evidence_versions SET snapshot='{}' WHERE incident_id=$1", id)
		if e == nil {
			t.Fatal("immutable snapshot changed")
		}
		a["status"] = "resolved"
		a["endsAt"] = time.Now().UTC().Format(time.RFC3339Nano)
		call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
		state := call(t, r.incidentURL, "GET", "/internal/v1/incidents/"+id, nil, 200)
		if state["state"] != "open" || state["alarm_status"] != "resolved" || Number(state, "evidence_version") != 2 {
			t.Fatal("resolved inferred recovery/reanalysis", state)
		}
		a["status"] = "firing"
		a["endsAt"] = "0001-01-01T00:00:00Z"
		a["values"] = Object{"A": 92}
		call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
		state = call(t, r.incidentURL, "GET", "/internal/v1/incidents/"+id, nil, 200)
		if state["alarm_status"] != "resolved" || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 2 {
			t.Fatal("late firing regressed lifecycle")
		}
	})
	t.Run("real_Backend_read_patch_receipt_no_execution_side_effect", func(t *testing.T) {
		v := call(t, r.backendURL, "GET", "/api/v1/incidents/"+id, nil, 200)
		if len(v["analyses"].([]any)) != 2 {
			t.Fatal("Backend did not expose RCA jobs")
		}
		h := []string{"Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(v, "version"))}
		b := Object{"memo": "E2E verified", "state": "acknowledged", "review_status": "reviewed"}
		first := call(t, r.backendURL, "PATCH", "/api/v1/incidents/"+id, b, 200, h...)
		second := call(t, r.backendURL, "PATCH", "/api/v1/incidents/"+id, b, 200, h...)
		if first["version"] != second["version"] || second["state"] != "acknowledged" {
			t.Fatal(first, second)
		}
		b["memo"] = "changed"
		call(t, r.backendURL, "PATCH", "/api/v1/incidents/"+id, b, 409, h...)
		call(t, r.backendURL, "PATCH", "/api/v1/incidents/"+id, Object{"state": "resolved"}, 422, "Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(second, "version")))
		call(t, r.backendURL, "PATCH", "/api/v1/incidents/"+id, Object{"state": "closed"}, 200, "Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(second, "version")))
		if r.count(t, "SELECT count(*) FROM jobs") != 2 || r.count(t, "SELECT count(*) FROM incident_evidence_versions") != 2 {
			t.Fatal("metadata triggered analysis")
		}
		status := call(t, r.backendURL, "GET", "/api/v1/service-status", nil, 200)
		found := false
		for _, v := range status["items"].([]any) {
			m := v.(map[string]any)
			if m["module"] == "incident" && m["status"] == "available" {
				found = true
			}
		}
		if !found {
			t.Fatal(status)
		}
	})
	t.Run("offline_acceptance_expiry_policy_and_validation", func(t *testing.T) {
		r.offline.Store(true)
		fresh := alertBody()
		fresh["fingerprint"] = "new-offline"
		v := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(fresh), 202)
		if item(v, 0)["outbox_id"] == nil {
			t.Fatal(v)
		}
		r.deliver(t)
		r.sql(t, "UPDATE enqueue_outbox SET dispatch_deadline=clock_timestamp()-interval '1 second',next_retry_at=clock_timestamp() WHERE status='pending'")
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE status='pending'") != 1 {
			t.Fatal("outage prematurely failed outbox")
		}
		r.offline.Store(false)
		r.sql(t, "UPDATE enqueue_outbox SET next_retry_at=clock_timestamp() WHERE status='pending'")
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE status='failed' AND last_error='dispatch_deadline_exceeded'") != 1 {
			t.Fatal("expired unaccepted outbox not failed")
		}
		unknown := alertBody()
		unknown["fingerprint"] = "no-policy"
		unknown["labels"].(map[string]any)["alertname"] = "OtherAlert"
		old := alertBody()
		old["fingerprint"] = "stale"
		old["startsAt"] = time.Now().Add(-48 * time.Hour).UTC().Format(time.RFC3339Nano)
		v = call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(unknown, old), 202)
		if item(v, 0)["reason"] != "analysis_policy_unconfigured" || item(v, 1)["reason"] != "stale_alert" {
			t.Fatal(v)
		}
		call(t, r.incidentURL, "POST", "/webhooks/grafana", Object{"alerts": "wrong"}, 422)
		bad := alertBody()
		bad["startsAt"] = "2026-09-17 12:00:00"
		v = call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(bad), 202)
		if item(v, 0)["disposition"] != "invalid" {
			t.Fatal(v)
		}
		nul := alertBody()
		nul["annotations"].(map[string]any)["summary"] = "bad\x00text"
		v = call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(nul, unknown), 202)
		if item(v, 0)["reason"] != "invalid_unicode" || Number(v, "accepted_alerts") != 1 {
			t.Fatal("invalid Unicode discarded valid sibling", v)
		}
		huge := strings.Repeat("x", r.service.Config.MaxBodyBytes+1)
		call(t, r.incidentURL, "POST", "/webhooks/grafana", Object{"alerts": []any{}, "padding": huge}, 413)
		call(t, r.incidentURL, "GET", "/internal/v1/incidents?limit=1", nil, 200)
	})
}

func TestFleetProjectionUpgradeDoesNotDuplicateIncident(t *testing.T) {
	r := setup(t)
	a := alertBody()
	first := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
	id := String(item(first, 0), "incident_id")
	var hash string
	check(t, r.db.QueryRow(context.Background(), "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1 AND revision=1", id).Scan(&hash))
	labels := a["labels"].(Object)
	labels["machine_id"], labels["component"], labels["k8s_node_name"] = "machine", "accelerator-nvidia-error-sxid", "node"
	again := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
	if String(item(again, 0), "incident_id") != id || r.count(t, "SELECT count(*) FROM incidents") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 1 || r.count(t, "SELECT count(*) FROM incident_evidence_versions") != 1 {
		t.Fatal("projection-only input duplicated a legacy lifecycle", again)
	}
	var savedHash string
	check(t, r.db.QueryRow(context.Background(), "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1 AND revision=1", id).Scan(&savedHash))
	if hash != savedHash {
		t.Fatal("legacy snapshot rewritten")
	}
	a["fingerprint"] = ID()
	fresh := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
	var target Object
	check(t, r.db.QueryRow(context.Background(), "SELECT target FROM incidents WHERE id=$1", item(fresh, 0)["incident_id"]).Scan(&target))
	for _, key := range []string{"machine_id", "component", "k8s_node_name"} {
		if target[key] != labels[key] {
			t.Fatalf("new incident missing %s", key)
		}
	}
}
