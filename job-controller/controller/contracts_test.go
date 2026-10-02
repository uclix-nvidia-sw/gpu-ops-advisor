package controller

import (
	. "gpu-ops-advisor/shared/contract"
	"testing"
)

func TestRCAContractNormalization(t *testing.T) {
	for _, tc := range []struct {
		name    string
		version string
		change  func(Object)
		valid   bool
	}{
		{"legacy", "1.3", func(Object) {}, true},
		{"first", "1.4", func(Object) {}, true},
		{"legacy_purposes_required", "1.3", func(b Object) { delete(b["input"].(Object), "purpose_ids") }, false},
		{"legacy_profile_required", "1.3", func(b Object) { delete(b["input"].(Object), "analysis_profile_revision") }, false},
		{"new_purposes_forbidden_even_null", "1.4", func(b Object) { b["input"].(Object)["purpose_ids"] = nil }, false},
		{"new_profile_forbidden", "1.4", func(b Object) { b["input"].(Object)["analysis_profile_revision"] = "old" }, false},
		{"first_revision_only", "1.4", func(b Object) { b["input"].(Object)["evidence_version"] = 2 }, false},
		{"first_key_only", "1.4", func(b Object) { b["source_key"] = "legacy-key" }, false},
		{"snapshot_identity", "1.4", func(b Object) { b["snapshot_ref"].(Object)["incident_id"] = ID() }, false},
		{"snapshot_revision", "1.4", func(b Object) { b["snapshot_ref"].(Object)["revision"] = 2 }, false},
		{"prior", "1.4", func(b Object) { b["input"].(Object)["prior_incident_id"] = ID() }, true},
		{"self_prior", "1.4", func(b Object) { b["input"].(Object)["prior_incident_id"] = b["input"].(Object)["incident_id"] }, false},
		{"runbook", "1.5", func(b Object) { b["input"].(Object)["analysis_profile_revision"] = "runbook-v1" }, true},
		{"runbook_purposes_forbidden", "1.5", func(b Object) {
			b["input"].(Object)["analysis_profile_revision"] = "runbook-v1"
			b["input"].(Object)["purpose_ids"] = []string{"R01"}
		}, false},
		{"runbook_revision_required", "1.5", func(Object) {}, false},
		{"unknown", "1.6", func(Object) {}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			id := ID()
			input := Object{"incident_id": id, "evidence_version": 1, "scope": Object{"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": nil}}}, "incident_time": "2026-09-23T09:00:00+09:00", "time_range": Object{"start": "2026-09-23T08:00:00+09:00", "end": "2026-09-23T10:00:00+09:00"}}
			if tc.version == "1.3" {
				input["purpose_ids"] = []string{"R02", "R01"}
				input["analysis_profile_revision"] = "old"
			}
			b := Object{"contract_version": tc.version, "kind": "rca", "source_module": "incident", "source_key": "incident:" + id + ":first", "input": input, "deadline_at": "2026-09-24T00:00:00Z", "dispatch_deadline": "2026-09-23T01:00:00Z", "snapshot_ref": Object{"incident_id": id, "revision": 1}}
			tc.change(b)
			if err := normalize("rca", b); (err == nil) != tc.valid {
				t.Fatalf("valid=%v err=%v", tc.valid, err)
			}
			if tc.valid && tc.version == "1.4" {
				if _, exists := input["purpose_ids"]; exists {
					t.Fatal("JC injected purposes")
				}
			}
		})
	}
}

func TestCandidateInputContract(t *testing.T) {
	for _, tc := range []struct {
		name, kind  string
		job, result Object
		valid       bool
	}{
		{"legacy_missing", "rca", Object{}, Object{}, true},
		{"legacy_candidate", "rca", Object{"input_contract": "1.3"}, Object{}, true},
		{"new", "rca", Object{"input_contract": "1.4"}, Object{"input_contract": "1.4"}, true},
		{"new_missing", "rca", Object{"input_contract": "1.4"}, Object{}, false},
		{"mismatch", "rca", Object{"input_contract": "1.4"}, Object{"input_contract": "1.3"}, false},
		{"unknown", "rca", Object{"input_contract": "9"}, Object{"input_contract": "9"}, false},
		{"null", "rca", Object{}, Object{"input_contract": nil}, false},
		{"empty", "rca", Object{}, Object{"input_contract": ""}, false},
		{"report", "report", Object{}, Object{"input_contract": "1.3"}, true},
		{"report_new", "report", Object{"input_contract": "1.4"}, Object{"input_contract": "1.4"}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := candidateContractMatches(Object{"kind": tc.kind, "versions": tc.job}, Object{"body": Object{"versions": tc.result}}); got != tc.valid {
				t.Fatalf("match=%v want=%v", got, tc.valid)
			}
		})
	}
}
