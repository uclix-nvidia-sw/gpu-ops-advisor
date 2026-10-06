package api

import (
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"testing"
	"time"
)

func TestReportProfileSelection(t *testing.T) {
	s := New(nil, config.Config{})
	for _, tc := range []struct {
		topics, groups []string
		expected       string
	}{
		{[]string{"O08"}, []string{"namespace"}, "report-namespace-v1"},
		{[]string{"O01", "O09", "O05"}, []string{"cluster"}, "local-v1"},
		{[]string{"O02", "O03", "O04"}, []string{"cluster"}, "local-v1"},
		{[]string{"O06"}, []string{"cluster"}, "local-v1"},
		{[]string{"O07"}, []string{"cluster"}, "local-v1"},
		{[]string{"O10"}, []string{"cluster"}, "local-v1"},
		{[]string{"O11"}, []string{"cluster"}, "local-v1"},
		{[]string{"O01", "O08"}, []string{"cluster", "namespace"}, "report-namespace-v1"},
		{[]string{"O08"}, []string{"cluster"}, "local-v1"},
		{[]string{"O08"}, []string{"namespace", "model"}, "local-v1"},
		{[]string{"O02"}, []string{"namespace"}, "local-v1"},
	} {
		for _, source := range []string{"manual:fixture", "schedule:fixture"} {
			input := Object{"topic_ids": tc.topics, "group_by": tc.groups}
			before := Hash(input)
			envelope := s.envelope(input, source, time.Now())
			if Hash(input) != before || Hash(envelope["input"]) != before {
				t.Fatal("report profile selection rewrote the requested topics or grouping")
			}
			if envelope["execution_profile_revision"] != tc.expected {
				t.Fatalf("%v: %v", tc, envelope)
			}
		}
	}
}

func TestMixedReportProfile(t *testing.T) {
	s := New(nil, config.Config{})
	input := Object{"topic_ids": []string{"O01", "O08"}, "group_by": []string{"cluster"}, "topic_group_by": map[string][]string{"O01": {"cluster"}, "O08": {"namespace"}}}
	before := Hash(input)
	for _, source := range []string{"manual:fixture", "schedule:fixture"} {
		if s.envelope(input, source, time.Now())["execution_profile_revision"] != "report-namespace-v1" {
			t.Fatal("namespace criteria lost")
		}
	}
	if Hash(input) != before {
		t.Fatal("input rewritten")
	}
}
