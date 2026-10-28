//go:build e2e

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"gpu-ops-advisor/incident/service"
	. "gpu-ops-advisor/shared/contract"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestFiringOncePerLifecycle(t *testing.T) {
	r := setup(t)
	post := func(alerts ...any) Object {
		return call(t, r.incidentURL, "POST", "/webhooks/grafana", batch(alerts...), 202)
	}
	count := func(table, id string) int {
		column := "incident_id::text"
		if table == "enqueue_outbox" {
			column = "input_snapshot->'input'->>'incident_id'"
		}
		return r.count(t, "SELECT count(*) FROM "+table+" WHERE "+column+"='"+id+"'")
	}
	for _, resolvedFirst := range []bool{true, false} {
		t.Run(fmt.Sprintf("mixed_batch_resolved_first_%t", resolvedFirst), func(t *testing.T) {
			firing := alertBody()
			firing["fingerprint"] = ID()
			resolved, e := Decode[Object](firing)
			check(t, e)
			resolved["status"], resolved["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
			alerts := []any{firing, resolved}
			if resolvedFirst {
				alerts = []any{resolved, firing}
			}
			response := post(alerts...)
			id := String(item(response, 0), "incident_id")
			if count("enqueue_outbox", id) != 1 {
				t.Fatal("mixed status batch did not create exactly one request", response)
			}
			post(alerts...)
			firing["annotations"].(map[string]any)["error_code"] = "Xid79"
			firing["labels"].(map[string]any)["severity"] = "critical"
			// Target enrichment must not split a lifecycle, even when the old target differs.
			firing["labels"].(map[string]any)["gpu_uuid"] = "GPU-added-later"
			if got := String(item(post(firing), 0), "incident_id"); got != id {
				t.Fatal("target/evidence change split the lifecycle", got, id)
			}
			r.deliver(t)
			if count("enqueue_outbox", id) != 1 || count("jobs", id) != 1 {
				t.Fatal("repeat created another request/job")
			}
			v := call(t, r.backendURL, "GET", "/api/v1/incidents/"+id, nil, 200)
			if v["alarm_status"] != "resolved" || len(v["analyses"].([]any)) != 1 {
				t.Fatal("receipt state or Backend result links changed", v)
			}
			// No resolve receipt is required to recognize a later start as a new event.
			firing["startsAt"] = time.Now().Add(-time.Second).UTC().Format(time.RFC3339Nano)
			next := String(item(post(firing), 0), "incident_id")
			if next == id || count("enqueue_outbox", next) != 1 {
				t.Fatal("recurrence without resolve receipt was suppressed")
			}
		})
	}
	t.Run("scope_conflict_does_not_consume_the_first_request", func(t *testing.T) {
		a := alertBody()
		a["fingerprint"] = ID()
		a["status"], a["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
		id := String(item(post(a), 0), "incident_id")
		a["status"], a["endsAt"] = "firing", "0001-01-01T00:00:00Z"
		a["labels"].(map[string]any)["namespace"] = "other-namespace"
		conflict := post(a)
		if item(conflict, 0)["reason"] != "identity_conflict" || count("enqueue_outbox", id) != 0 {
			t.Fatal("scope conflict consumed the first request", conflict)
		}
		a["labels"].(map[string]any)["namespace"] = "dev"
		post(a)
		r.deliver(t)
		if count("enqueue_outbox", id) != 1 || count("jobs", id) != 1 {
			t.Fatal("valid firing after conflict was not delivered")
		}
	})
	t.Run("legacy_resolved_snapshot_and_identical_skipped_firing_replay", func(t *testing.T) {
		a := alertBody()
		a["fingerprint"] = ID()
		a["status"], a["endsAt"] = "resolved", time.Now().UTC().Format(time.RFC3339Nano)
		id := String(item(post(a), 0), "incident_id")
		// Simulate a deployed target-based key and a firing receipt skipped by the old producer.
		r.sql(t, "UPDATE incidents SET event_key=$2,state='closed' WHERE id=$1", id, Hash(Object{"legacy_target": id}))
		var snapshotHash string
		check(t, r.db.QueryRow(context.Background(), "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1 AND revision=1", id).Scan(&snapshotHash))
		a["status"], a["endsAt"] = "firing", "0001-01-01T00:00:00Z"
		r.service.Config.MaxAgeSeconds = 1
		check(t, r.service.Prepare(context.Background(), true))
		skipped := post(a)
		if item(skipped, 0)["reason"] != "stale_alert" || count("enqueue_outbox", id) != 0 {
			t.Fatal("skipped firing fixture", skipped)
		}
		r.service.Config.MaxAgeSeconds = 86400
		check(t, r.service.Prepare(context.Background(), true))
		again := post(a)
		delete(again, "request_id")
		delete(skipped, "request_id")
		if Hash(again) != Hash(skipped) || count("enqueue_outbox", id) != 1 || count("incident_evidence_versions", id) != 2 {
			t.Fatal("replay failed to enqueue once while preserving receipt", again)
		}
		post(a)
		var after string
		check(t, r.db.QueryRow(context.Background(), "SELECT content_hash FROM incident_evidence_versions WHERE incident_id=$1 AND revision=1", id).Scan(&after))
		if after != snapshotHash || count("enqueue_outbox", id) != 1 || count("alert_events", id) != 2 {
			t.Fatal("legacy history was rewritten or duplicated")
		}
	})
	t.Run("legacy_outbox_policy_change_and_failure_never_enqueue_again", func(t *testing.T) {
		a := alertBody()
		a["fingerprint"] = ID()
		id := String(item(post(a), 0), "incident_id")
		// Legacy keys must also count as already requested, regardless of delivery outcome.
		r.sql(t, "UPDATE incidents SET event_key=$2 WHERE id=$1", id, Hash(Object{"legacy_target": id}))
		r.sql(t, "UPDATE enqueue_outbox SET source_key=$2,status='failed' WHERE input_snapshot->'input'->>'incident_id'=$1", id, "incident:"+id+":evidence:1:profile:gpu-alert-runbook-v1")
		r.service.Config.Policies[0].Revision = "firing-test-v2"
		check(t, r.service.Prepare(context.Background(), true))
		a["values"] = Object{"A": 99}
		response := post(a)
		if String(item(response, 0), "incident_id") != id || item(response, 0)["reason"] != "analysis_already_requested" || count("enqueue_outbox", id) != 1 || count("incident_evidence_versions", id) != 1 {
			t.Fatal("legacy failed request or new policy caused a new analysis", response)
		}
	})
	t.Run("concurrent_first_firing_with_different_payloads", func(t *testing.T) {
		a := alertBody()
		a["fingerprint"] = ID()
		var wg sync.WaitGroup
		errors := make(chan string, 12)
		for n := range 12 {
			copy, e := Decode[Object](a)
			check(t, e)
			copy["values"] = Object{"A": n}
			raw, e := json.Marshal(batch(copy))
			check(t, e)
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
					errors <- resp.Status
				}
			}()
		}
		wg.Wait()
		close(errors)
		for e := range errors {
			t.Error(e)
		}
		id := String(item(post(a), 0), "incident_id")
		r.deliver(t)
		if count("enqueue_outbox", id) != 1 || count("jobs", id) != 1 || count("incident_evidence_versions", id) != 1 {
			t.Fatal("concurrent firing created duplicate analysis")
		}
	})
	t.Run("old_producer_configuration_is_fenced", func(t *testing.T) {
		r.sql(t, "UPDATE incident_sources SET config_revision=$2 WHERE source=$1", r.service.Config.Source, Hash(r.service.Config))
		old, e := service.New(r.db, r.service.Config)
		check(t, e)
		if e = old.Prepare(context.Background()); e == nil || !strings.Contains(e.Error(), "configuration_mismatch") {
			t.Fatal("legacy configuration accepted", e)
		}
		check(t, old.Prepare(context.Background(), true))
		check(t, old.Prepare(context.Background()))
	})
}
