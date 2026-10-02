//go:build e2e

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"gpu-ops-advisor/incident/service"
	. "gpu-ops-advisor/shared/contract"
)

func TestIncidentEpisodes(t *testing.T) {
	r := setup(t)
	ctx := context.Background()
	legacy := alertBody()
	legacyReceipt := call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(legacy), 202)
	legacyID := String(item(legacyReceipt, 0), "incident_id")
	var legacyHash string
	check(t, r.db.QueryRow(ctx, "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1", legacyID).Scan(&legacyHash))
	oldService := r.service

	// This fixture checks the future JC intake boundary only; actual 1.3 JC is tested separately.
	var mu sync.Mutex
	hashes, receipts := map[string]string{}, map[string]Object{}
	lost := false
	queue := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		if req.Method == "GET" {
			key := strings.TrimPrefix(req.URL.Path, "/internal/v1/receipts/incident/")
			if receipt := receipts[key]; receipt != nil {
				json.NewEncoder(w).Encode(receipt)
			} else {
				w.WriteHeader(404)
				io.WriteString(w, `{"error":{"code":"not_found"}}`)
			}
			return
		}
		var body Object
		if e := json.NewDecoder(req.Body).Decode(&body); e != nil {
			t.Error(e)
			w.WriteHeader(422)
			return
		}
		if body["contract_version"] == "1.3" || body["contract_version"] == "1.5" {
			b, _ := json.Marshal(body)
			req.Body = io.NopCloser(bytes.NewReader(b))
			r.jc.ServeHTTP(w, req)
			return
		}
		input := body["input"].(map[string]any)
		key := String(body, "source_key")
		if body["contract_version"] != "1.4" || req.Header.Get("X-DSX-Contract-Version") != "1.4" || input["purpose_ids"] != nil || input["analysis_profile_revision"] != nil || Number(input, "evidence_version") != 1 || key != "incident:"+String(input, "incident_id")+":first" {
			t.Error("invalid 1.4 envelope", body)
		}
		if previous := hashes[key]; previous != "" && previous != Hash(body) {
			t.Error("retry mutated envelope")
		}
		hashes[key] = Hash(body)
		if receipts[key] == nil {
			receipts[key] = Object{"job_id": ID(), "kind": "rca", "status": "queued", "version": 1}
		}
		if !lost {
			lost = true
			w.WriteHeader(503)
			io.WriteString(w, `{"error":{"code":"lost_response"}}`)
			return
		}
		w.WriteHeader(202)
		json.NewEncoder(w).Encode(receipts[key])
	}))
	t.Cleanup(queue.Close)
	cfg := r.service.Config
	cfg.JCURL = queue.URL
	cfg.Episodes = &service.EpisodePolicy{Revision: "test-v1", RepeatIntervalSeconds: 60, ObservationGapSeconds: 120, OccurredAtContractRevision: "fleet-test-v1"}
	var e error
	r.service, e = service.New(r.db, cfg)
	check(t, e)
	check(t, r.service.Prepare(ctx, true))
	check(t, r.service.Prepare(ctx))
	web := httptest.NewServer(r.service)
	t.Cleanup(web.Close)
	r.incidentURL = web.URL
	post := func(alerts ...any) Object {
		return call(t, web.URL, "POST", "/webhooks/grafana", batch(alerts...), 202)
	}
	read := func(id string) Object { return call(t, web.URL, "GET", "/internal/v1/incidents/"+id, nil, 200) }
	closeEpisode := func(id string) Object {
		v := read(id)
		return call(t, web.URL, "PATCH", "/internal/v1/incidents/"+id, Object{"contract_version": "1.3", "source_module": "backend", "input": Object{"state": "closed"}}, 200, "Idempotency-Key", ID(), "If-Match", fmt.Sprint(Number(v, "version")))
	}
	fault := func(fp, component string) Object {
		a := alertBody()
		a["fingerprint"] = fp
		labels := a["labels"].(map[string]any)
		labels["alertname"], labels["machine_id"], labels["component"] = "UnregisteredFault", "machine-1", component
		return a
	}
	t.Run("legacy_cutover_and_pending_delivery", func(t *testing.T) {
		v := post(legacy)
		if v["receipt_id"] != legacyReceipt["receipt_id"] || r.count(t, "SELECT count(*) FROM enqueue_outbox") != 1 {
			t.Fatal("legacy replay created work", v)
		}
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM jobs WHERE kind='rca'") != 1 || r.count(t, "SELECT count(*) FROM incidents WHERE dedup_group IS NOT NULL") != 0 {
			t.Fatal("legacy pending envelope did not reach real JC unchanged")
		}
		var after string
		check(t, r.db.QueryRow(ctx, "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1", legacyID).Scan(&after))
		if after != legacyHash || oldService.Prepare(ctx, false) == nil {
			t.Fatal("legacy snapshot changed or old configuration remained writable")
		}
	})
	a, b := fault("a", "gpu"), fault("b", "gpu")
	a["labels"].(map[string]any)["k8s_node_name"] = "fixture-node"
	b["labels"].(map[string]any)["reason"] = "different reason"
	first := post(a, b, nil)
	id := String(item(first, 0), "incident_id")
	if id == "" || item(first, 1)["incident_id"] != id || Number(first, "invalid_alerts") != 1 {
		t.Fatal("storm grouping", first)
	}
	var storedNode, queuedNode string
	check(t, r.db.QueryRow(ctx, "SELECT target->>'k8s_node_name' FROM incidents WHERE id=$1", id).Scan(&storedNode))
	check(t, r.db.QueryRow(ctx, "SELECT input_snapshot->'input'->'target'->>'k8s_node_name' FROM enqueue_outbox WHERE source_key=$1", "incident:"+id+":first").Scan(&queuedNode))
	if storedNode != "fixture-node" || queuedNode != storedNode {
		t.Fatal("node label missing from stored incident or JC envelope", storedNode, queuedNode)
	}
	t.Run("receipt_continuity_concurrency_and_snapshot", func(t *testing.T) {
		replica, err := service.New(r.db, cfg)
		check(t, err)
		check(t, replica.Prepare(ctx))
		second := httptest.NewServer(replica)
		defer second.Close()
		storm := fault("concurrent-first", "concurrent-first")
		ids := make(chan string, 8)
		var firstGroup sync.WaitGroup
		for i := range 8 {
			firstGroup.Add(1)
			go func() {
				defer firstGroup.Done()
				base := web.URL
				if i%2 == 0 {
					base = second.URL
				}
				v := call(t, base, "POST", "/webhooks/grafana", batch(storm), 202)
				ids <- String(item(v, 0), "incident_id")
			}()
		}
		firstGroup.Wait()
		close(ids)
		winner := ""
		for received := range ids {
			if winner != "" && winner != received {
				t.Fatal("replicas created multiple episodes")
			}
			winner = received
		}
		if Number(read(winner), "observation_count") != 8 || r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE source_key='incident:"+winner+":first'") != 1 {
			t.Fatal("concurrent first receive did not converge")
		}
		for range 3 {
			post(a, b, nil)
		}
		if Number(read(id), "observation_count") != 4 {
			t.Fatal("identical bytes did not refresh continuity", read(id))
		}
		if r.count(t, "SELECT count(*) FROM alert_events WHERE incident_id='"+id+"'") != 2 {
			t.Fatal("raw alert duplication")
		}
		var wg sync.WaitGroup
		for range 8 {
			wg.Add(1)
			go func() { defer wg.Done(); post(b, a) }()
		}
		wg.Wait()
		if Number(read(id), "observation_count") != 12 || r.count(t, "SELECT count(*) FROM incident_evidence_versions WHERE incident_id='"+id+"'") != 1 {
			t.Fatal("concurrent continuity", read(id))
		}
		a["annotations"].(map[string]any)["error_code"] = "changed"
		post(a)
		if Number(read(id), "evidence_version") != 1 || r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE source_key='incident:"+id+":first'") != 1 {
			t.Fatal("evidence change triggered RCA")
		}
		if _, e = r.db.Exec(ctx, "UPDATE incident_evidence_versions SET snapshot='{}' WHERE incident_id=$1", id); e == nil {
			t.Fatal("snapshot mutable")
		}
		if _, e = r.db.Exec(ctx, "INSERT INTO incident_evidence_versions SELECT incident_id,2,snapshot,content_hash FROM incident_evidence_versions WHERE incident_id=$1", id); e == nil {
			t.Fatal("episode accepted a second evidence revision")
		}
	})
	t.Run("lost_reply_reconciled_with_same_key", func(t *testing.T) {
		r.deliver(t)
		r.sql(t, "UPDATE enqueue_outbox SET dispatch_deadline=clock_timestamp()-interval '1 second',next_retry_at=clock_timestamp() WHERE source_key=$1", "incident:"+id+":first")
		r.deliver(t)
		if r.count(t, "SELECT count(*) FROM enqueue_outbox WHERE source_key='incident:"+id+":first' AND status='accepted'") != 1 {
			t.Fatal("1.4 receipt reconciliation")
		}
	})
	t.Run("resolved_is_not_recovery_and_late_firing_is_ignored", func(t *testing.T) {
		before := Number(read(id), "observation_count")
		a["status"], a["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
		post(a)
		if read(id)["alarm_status"] != "firing" {
			t.Fatal("partial resolve ended group")
		}
		b["status"], b["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
		post(b)
		a["status"], a["endsAt"] = "firing", "0001-01-01T00:00:00Z"
		post(a)
		v := read(id)
		if v["alarm_status"] != "resolved" || v["state"] != "open" || v["observation_status"] != "observing" || Number(v, "observation_count") != before {
			t.Fatal(v)
		}
		r.sql(t, "UPDATE incidents SET last_observed_at=clock_timestamp()-interval '121 seconds' WHERE id=$1", id)
		post(a)
		if v = read(id); v["ended_reason"] != "alarm_resolved" || v["state"] != "open" {
			t.Fatal("resolved gap inferred human closure", v)
		}
		resolved := fault("resolved-first", "other")
		resolved["status"], resolved["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
		if item(post(resolved), 0)["incident_id"] != nil {
			t.Fatal("resolved-first created episode")
		}
	})
	t.Run("gap_suppression_and_operator_recurrence", func(t *testing.T) {
		current := fault("gap", "gap")
		gapID := String(item(post(current), 0), "incident_id")
		r.sql(t, "UPDATE incidents SET last_observed_at=clock_timestamp()-interval '121 seconds' WHERE id=$1", gapID)
		if read(gapID)["observation_status"] != "ended" {
			t.Fatal("read did not derive gap")
		}
		post(current) // Duplicate ends the old episode but cannot create another.
		current["startsAt"] = time.Now().UTC().Format(time.RFC3339Nano)
		v := post(current)
		nextID := String(item(v, 0), "incident_id")
		if nextID == gapID || nextID == "" || read(nextID)["prior_incident_id"] != gapID || read(nextID)["rca_eligibility_reason"] != "prior_analysis_open" || item(v, 0)["outbox_id"] != nil {
			t.Fatal("gap recurrence", v)
		}
		closed := closeEpisode(nextID)
		post(current)
		current["annotations"].(map[string]any)["summary"] = "only text changed"
		if item(post(current), 0)["reason"] != "post_episode_freshness_unknown" {
			t.Fatal("text-only recurrence")
		}
		current["annotations"].(map[string]any)["occurred_at"] = time.Now().UTC().Add(time.Second).Format("2006-01-02 15:04:05.999999999 -0700 MST")
		v = post(current)
		newID := String(item(v, 0), "incident_id")
		if newID == nextID || item(v, 0)["outbox_id"] == nil || read(newID)["prior_incident_id"] != nextID || read(nextID)["closed_at"] != closed["closed_at"] {
			t.Fatal("same-lifecycle recurrence", v)
		}
		post(current)
		if Number(read(newID), "observation_count") != 2 {
			t.Fatal("recurrence did not continue")
		}
		beforeEnd := read(gapID)["ended_at"]
		closeEpisode(gapID)
		if read(gapID)["ended_reason"] != "observation_gap" || read(gapID)["ended_at"] != beforeEnd {
			t.Fatal("late close overwrote gap")
		}
	})
	t.Run("resolved_after_episode_end_preserves_closure", func(t *testing.T) {
		for _, end := range []string{"closed_by_operator", "observation_gap"} {
			t.Run(end, func(t *testing.T) {
				a, b := fault(end+"-a", end), fault(end+"-b", end)
				id := String(item(post(a, b), 0), "incident_id")
				if end == "closed_by_operator" {
					closeEpisode(id)
				} else {
					r.sql(t, "UPDATE incidents SET last_observed_at=clock_timestamp()-interval '121 seconds' WHERE id=$1", id)
					post(a)
				}
				before := read(id)
				outboxes := r.count(t, "SELECT count(*) FROM enqueue_outbox")
				a["status"], a["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
				post(a)
				if read(id)["alarm_status"] != "firing" {
					t.Fatal("partial resolution resolved the whole ended episode")
				}
				b["status"], b["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
				post(b)
				after := read(id)
				if after["alarm_status"] != "resolved" || after["alarm_resolved_at"] == nil {
					t.Fatal("late resolved did not update ended episode", after)
				}
				for _, key := range []string{"state", "closed_at", "ended_at", "ended_reason", "last_observed_at", "observation_count", "evidence_version"} {
					if after[key] != before[key] {
						t.Fatalf("late resolved changed %s: %v -> %v", key, before[key], after[key])
					}
				}
				a["status"], a["endsAt"] = "firing", "0001-01-01T00:00:00Z"
				post(a)
				if read(id)["alarm_status"] != "resolved" || Hash(after["evidence_versions"]) != Hash(before["evidence_versions"]) || r.count(t, "SELECT count(*) FROM enqueue_outbox") != outboxes {
					t.Fatal("late lifecycle events reopened or reanalyzed the episode")
				}
			})
		}
	})
	t.Run("identity_exclusion_and_invalid_siblings", func(t *testing.T) {
		excluded, incomplete, other := fault("datasource", "gpu"), fault("incomplete", "gpu"), fault("incomplete-other", "gpu")
		excluded["labels"].(map[string]any)["alertname"] = "DatasourceNoData"
		delete(incomplete["labels"].(map[string]any), "machine_id")
		delete(other["labels"].(map[string]any), "machine_id")
		v := post(excluded, incomplete, other)
		if item(v, 0)["reason"] != "analysis_excluded" || item(v, 0)["outbox_id"] != nil || item(v, 1)["outbox_id"] == nil || item(v, 1)["incident_id"] == item(v, 2)["incident_id"] {
			t.Fatal(v)
		}
		incomplete["labels"].(map[string]any)["machine_id"] = "now-present"
		if item(post(incomplete), 0)["reason"] != "identity_conflict" {
			t.Fatal("identity moved groups")
		}
		bad := fault("invalid", "gpu")
		bad["annotations"].(map[string]any)["summary"] = "bad\x00text"
		v = post(bad, other)
		if Number(v, "invalid_alerts") != 1 || Number(v, "accepted_alerts") != 1 {
			t.Fatal(v)
		}
		call(t, web.URL, "POST", "/webhooks/grafana", Object{"alerts": []any{other}, "truncatedAlerts": -1}, 422)
		if oldService.Prepare(ctx, true) == nil {
			t.Fatal("unsafe 1.3 rollback accepted")
		}
		changed := cfg
		policy := *cfg.Episodes
		policy.ObservationGapSeconds++
		changed.Episodes = &policy
		candidate, err := service.New(r.db, changed)
		check(t, err)
		if candidate.Prepare(ctx, true) == nil {
			t.Fatal("episode policy revision was overwritten")
		}
	})
}

func TestEpisodeMigrationConflict(t *testing.T) {
	r := setup(t)
	a := alertBody()
	call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
	a["labels"].(map[string]any)["node"] = "another-target-same-lifecycle"
	call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(a), 202)
	cfg := r.service.Config
	cfg.Episodes = &service.EpisodePolicy{Revision: "test-v1", RepeatIntervalSeconds: 60, ObservationGapSeconds: 120}
	next, e := service.New(r.db, cfg)
	check(t, e)
	if e = next.Prepare(context.Background(), true); e == nil || !strings.Contains(e.Error(), "multiple incidents") {
		t.Fatal("conflicting legacy attribution was silently merged", e)
	}
	if r.count(t, "SELECT count(*) FROM incidents") != 2 || r.count(t, "SELECT count(*) FROM incident_evidence_versions") != 2 {
		t.Fatal("migration destroyed legacy evidence")
	}
}
