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
		{[]string{"O01", "O08"}, []string{"cluster", "namespace"}, "report-namespace-v1"},
		{[]string{"O08"}, []string{"cluster"}, "local-v1"},
		{[]string{"O08"}, []string{"namespace", "model"}, "local-v1"},
		{[]string{"O02"}, []string{"namespace"}, "local-v1"},
	} {
		for _, source := range []string{"manual:fixture", "schedule:fixture"} {
			envelope := s.envelope(Object{"topic_ids": tc.topics, "group_by": tc.groups}, source, time.Now())
			if envelope["execution_profile_revision"] != tc.expected {
				t.Fatalf("%v: %v", tc, envelope)
			}
		}
	}
}
