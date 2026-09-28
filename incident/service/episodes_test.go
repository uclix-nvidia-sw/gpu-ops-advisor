package service

import (
	"testing"
	"time"

	. "gpu-ops-advisor/shared/contract"
)

func TestEpisodeNodeLabelAndAnnotation(t *testing.T) {
	now := time.Date(2026, 9, 28, 10, 0, 0, 0, time.UTC)
	cfg := DefaultConfig()
	cfg.Episodes = &EpisodePolicy{Revision: "test-v1", RepeatIntervalSeconds: 60, ObservationGapSeconds: 120}
	s := &Server{Config: cfg}
	for _, tc := range []struct{ label, annotation, want, reason string }{
		{"node-1", "", "node-1", ""},
		{"", "node-2", "node-2", ""},
		{"node-1", "node-1", "node-1", ""},
		{"node-1", "node-2", "", "conflicting_node_name"},
	} {
		raw := Object{"fingerprint": "f", "status": "firing", "startsAt": now.Format(time.RFC3339Nano),
			"labels":      Object{"cluster_id": "c", "alertname": "GPUAlert", "machine_id": "machine", "component": "accelerator-nvidia-error-xid", "k8s_node_name": tc.label},
			"annotations": Object{"k8s_node_name": tc.annotation}}
		before := Hash(raw)
		got, reason := s.parseEpisode(raw, now)
		if reason != tc.reason || (reason == "" && String(got.target, "k8s_node_name") != tc.want) || before != Hash(raw) {
			t.Fatalf("node projection: target=%v reason=%s", got.target, reason)
		}
	}
}

func TestEpisodeDecisions(t *testing.T) {
	now := time.Date(2026, 9, 23, 10, 0, 0, 0, time.UTC)
	cfg := DefaultConfig()
	cfg.Episodes = &EpisodePolicy{Revision: "test-v1", RepeatIntervalSeconds: 60, ObservationGapSeconds: 120}
	s := &Server{Config: cfg}
	raw := Object{"fingerprint": "f", "status": "firing", "startsAt": now.Add(-time.Minute).Format(time.RFC3339Nano),
		"labels":      Object{"cluster_id": "c", "alertname": "UnknownFault", "machine_id": "m", "component": "x"},
		"annotations": Object{"occurred_at": now.Add(-30 * time.Second).Format("2006-01-02 15:04:05.999999999 -0700 MST")}}
	a, reason := s.parseEpisode(raw, now)
	if reason != "" || a.group != `["component","local-grafana","c","m","x"]` || a.timeBasis != "occurred_at_unverified" || !a.at.Equal(a.starts) {
		t.Fatalf("unverified source: %+v %s", a, reason)
	}
	cfg.Episodes.OccurredAtContractRevision = "fleet-test-v1"
	a, reason = s.parseEpisode(raw, now)
	if reason != "" || a.timeBasis != "occurred_at" || !a.at.Equal(now.Add(-30*time.Second)) {
		t.Fatalf("verified source: %+v %s", a, reason)
	}
	j := Object{"dedup_group": a.group, "last_observed_at": now.Format(time.RFC3339Nano), "observation_gap_seconds": 120, "alarm_status": "firing"}
	for _, tc := range []struct {
		seconds int
		ended   bool
	}{{120, false}, {121, true}} {
		_, why := episodeEnd(j, now.Add(time.Duration(tc.seconds)*time.Second))
		if (why != "") != tc.ended {
			t.Fatalf("gap %d: %q", tc.seconds, why)
		}
	}
	j["closed_at"] = now.Add(-45 * time.Second).Format(time.RFC3339Nano)
	if !freshAfterEpisode(a, j) {
		t.Fatal("verified occurrence after close must be fresh")
	}
	a.timeBasis = "occurred_at_unverified"
	if freshAfterEpisode(a, j) {
		t.Fatal("unverified occurrence must not reopen a closed episode")
	}
	labels := raw["labels"].(map[string]any)
	delete(labels, "component")
	a, reason = s.parseEpisode(raw, now)
	if reason != "" || len(a.missing) != 1 || a.group == String(j, "dedup_group") {
		t.Fatal("missing identity must be isolated", a, reason)
	}
	labels["alertname"] = "DatasourceNoData"
	a, reason = s.parseEpisode(raw, now)
	if reason != "" || !a.excluded {
		t.Fatal("collection faults are valid but excluded", reason)
	}
	raw["annotations"].(map[string]any)["occurred_at"] = now.Add(time.Hour).Format(time.RFC3339Nano)
	if _, reason = s.parseEpisode(raw, now); reason != "future_occurred_at" {
		t.Fatal(reason)
	}
	cfg.Episodes.ObservationGapSeconds = 119
	if cfg.Validate() == nil {
		t.Fatal("unverified observation gap accepted")
	}
}
