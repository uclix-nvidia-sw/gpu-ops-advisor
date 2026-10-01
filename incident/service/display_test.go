package service

import (
	. "gpu-ops-advisor/shared/contract"
	"testing"
	"time"
)

func TestDisplayTitlePreservesLifecycleIdentity(t *testing.T) {
	now := time.Now().UTC()
	s := &Server{Config: DefaultConfig()}
	labels := Object{"cluster_id": "c", "alertname": "GPUAlert"}
	raw := Object{"fingerprint": "f", "status": "firing", "startsAt": now.Format(time.RFC3339Nano), "labels": labels}
	original, reason := s.parse(raw, now)
	if reason != "" {
		t.Fatal(reason)
	}
	for _, title := range []string{"XID 79 reported", "synthetic XID"} {
		labels["reason"] = title
		got, reason := s.parse(raw, now)
		if reason != "" || got.eventKey != original.eventKey || got.target["title"] != title {
			t.Fatal("display changed lifecycle identity")
		}
	}
	if got, _ := s.parse(raw, now); got.target["test_alarm"] != true {
		t.Fatal("missing test badge metadata")
	}
	delete(labels, "reason")
	raw["annotations"] = Object{"summary": "summary fallback"}
	got, _ := s.parse(raw, now)
	if got.target["title"] != "summary fallback" {
		t.Fatal("missing summary")
	}
}
