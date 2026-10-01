package api

import (
	. "gpu-ops-advisor/backend/internal/contract"
	"testing"
)

func TestReportOriginDTO(t *testing.T) {
	for _, tc := range []struct{ kind, module, key, want string }{
		{"report", "backend", "manual:request", "manual"},
		{"report", "backend", "schedule:occurrence", "schedule"},
		{"report", "backend", "manual:", "unknown"},
		{"report", "backend", "legacy", "unknown"},
		{"report", "other", "schedule:occurrence", "unknown"},
		{"rca", "incident", "manual:request", ""},
	} {
		value, err := (&Server{}).jobDTO(&Request{}, Object{"kind": tc.kind, "source_module": tc.module, "source_key": tc.key}, false)
		if err != nil || String(value, "report_origin") != tc.want {
			t.Fatalf("%+v: %v %v", tc, value, err)
		}
		if _, ok := value["source_key"]; ok {
			t.Fatal("raw source key exposed")
		}
	}
}
